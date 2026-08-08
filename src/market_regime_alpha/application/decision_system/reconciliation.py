"""Deterministic Manual Account versus Fill-derived Position reconciliation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from market_regime_alpha.application.decision_system.contracts import (
    AccountReconciliationReport,
    FillDerivedPositionReference,
    ManualAccountObservation,
    ReconciliationDifference,
    ReconciliationDifferenceType,
    ReconciliationStatus,
    ReconciliationTolerance,
)
from market_regime_alpha.core.identity import ArtifactId


class ReconciliationBlocked(ValueError):
    """Typed blocker for OPEN/ADD research proposals."""


def reconcile_account(
    *,
    observation: ManualAccountObservation,
    positions: tuple[FillDerivedPositionReference, ...],
    fill_ledger_head: str,
    fill_ledger_complete: bool,
    tolerance: ReconciliationTolerance,
    authoritative_total_equity: Decimal | None,
    authoritative_available_cash: Decimal | None,
    authoritative_frozen_cash: Decimal | None,
    as_of_time: datetime,
    revision: int,
    previous_reconciliation_id: ArtifactId | None,
    idempotency_key: str,
    created_at: datetime,
) -> AccountReconciliationReport:
    if observation.as_of_time > as_of_time:
        raise ValueError("Account Observation is later than Reconciliation AsOfTime")
    if any(item.account_id != observation.account_id for item in positions):
        raise ValueError("Position/Account lineage mismatch")
    if any(item.as_of_time > as_of_time for item in positions):
        raise ValueError("Position snapshot is later than Reconciliation AsOfTime")
    if len({item.symbol for item in positions}) != len(positions):
        raise ValueError("Fill-derived Position symbols must be unique")

    differences: list[ReconciliationDifference] = []
    if authoritative_total_equity is None:
        differences.append(_missing("TOTAL_EQUITY_UNAVAILABLE"))
    else:
        _money_difference(
            differences,
            ReconciliationDifferenceType.TOTAL_EQUITY_DIFFERENCE,
            expected=authoritative_total_equity,
            observed=observation.total_equity,
            tolerance=tolerance.equity_tolerance,
            reason="TOTAL_EQUITY_MISMATCH",
        )
    if authoritative_available_cash is None or authoritative_frozen_cash is None:
        differences.append(_missing("CASH_AUTHORITY_UNAVAILABLE"))
    else:
        _money_difference(
            differences,
            ReconciliationDifferenceType.CASH_DIFFERENCE,
            expected=authoritative_available_cash + authoritative_frozen_cash,
            observed=observation.available_cash + observation.frozen_cash,
            tolerance=tolerance.cash_tolerance,
            reason="CASH_MISMATCH",
        )
    if not fill_ledger_complete or any(not item.complete for item in positions):
        differences.append(_missing("FILL_LEDGER_INCOMPLETE"))

    manual = {item.symbol: item for item in observation.positions}
    system = {item.symbol: item for item in positions if item.total_quantity > 0}
    for symbol in sorted(set(manual) | set(system)):
        manual_item = manual.get(symbol)
        system_item = system.get(symbol)
        if manual_item is None:
            differences.append(
                ReconciliationDifference(
                    ReconciliationDifferenceType.MANUAL_MISSING_POSITION,
                    symbol,
                    Decimal(system_item.total_quantity) if system_item else None,
                    None,
                    None,
                    "MANUAL_POSITION_MISSING",
                )
            )
            continue
        if system_item is None:
            differences.extend(
                (
                    ReconciliationDifference(
                        ReconciliationDifferenceType.SYSTEM_MISSING_POSITION,
                        symbol,
                        Decimal("0"),
                        Decimal(manual_item.total_quantity),
                        Decimal(manual_item.total_quantity),
                        "UNKNOWN_MANUAL_POSITION",
                    ),
                    ReconciliationDifference(
                        ReconciliationDifferenceType.UNRECORDED_TRADE_SUSPECTED,
                        symbol,
                        None,
                        Decimal(manual_item.total_quantity),
                        None,
                        "UNRECORDED_TRADE_REQUIRES_MANUAL_REVIEW",
                    ),
                )
            )
            continue
        if system_item.total_quantity != manual_item.total_quantity:
            delta = abs(system_item.total_quantity - manual_item.total_quantity)
            differences.append(
                ReconciliationDifference(
                    ReconciliationDifferenceType.SYMBOL_QUANTITY_DIFFERENCE,
                    symbol,
                    Decimal(system_item.total_quantity),
                    Decimal(manual_item.total_quantity),
                    Decimal(delta),
                    "POSITION_QUANTITY_MISMATCH",
                )
            )
            suspicion = (
                ReconciliationDifferenceType.CORPORATE_ACTION_SUSPECTED
                if _corporate_action_ratio(
                    system_item.total_quantity, manual_item.total_quantity
                )
                else ReconciliationDifferenceType.UNRECORDED_TRADE_SUSPECTED
            )
            differences.append(
                ReconciliationDifference(
                    suspicion,
                    symbol,
                    Decimal(system_item.total_quantity),
                    Decimal(manual_item.total_quantity),
                    Decimal(delta),
                    (
                        "CORPORATE_ACTION_REQUIRES_ADJUSTMENT_ARTIFACT"
                        if suspicion is ReconciliationDifferenceType.CORPORATE_ACTION_SUSPECTED
                        else "UNRECORDED_TRADE_REQUIRES_MANUAL_REVIEW"
                    ),
                )
            )
        if system_item.available_quantity is None or system_item.frozen_quantity is None:
            differences.append(_missing("T_PLUS_ONE_AUTHORITY_UNAVAILABLE", symbol=symbol))
        else:
            if system_item.available_quantity != manual_item.available_quantity:
                difference_type = (
                    ReconciliationDifferenceType.T_PLUS_ONE_DIFFERENCE
                    if system_item.total_quantity == manual_item.total_quantity
                    else ReconciliationDifferenceType.AVAILABLE_QUANTITY_DIFFERENCE
                )
                differences.append(
                    ReconciliationDifference(
                        difference_type,
                        symbol,
                        Decimal(system_item.available_quantity),
                        Decimal(manual_item.available_quantity),
                        Decimal(abs(system_item.available_quantity - manual_item.available_quantity)),
                        "AVAILABLE_QUANTITY_OR_T_PLUS_ONE_MISMATCH",
                    )
                )
            if system_item.frozen_quantity != manual_item.frozen_quantity:
                differences.append(
                    ReconciliationDifference(
                        ReconciliationDifferenceType.FROZEN_QUANTITY_DIFFERENCE,
                        symbol,
                        Decimal(system_item.frozen_quantity),
                        Decimal(manual_item.frozen_quantity),
                        Decimal(abs(system_item.frozen_quantity - manual_item.frozen_quantity)),
                        "FROZEN_QUANTITY_MISMATCH",
                    )
                )
        if system_item.average_cost is None or manual_item.average_cost is None:
            if system_item.total_quantity > 0 or manual_item.total_quantity > 0:
                differences.append(_missing("AVERAGE_COST_UNAVAILABLE", symbol=symbol))
        elif abs(system_item.average_cost - manual_item.average_cost) > tolerance.average_cost_tolerance:
            differences.append(
                ReconciliationDifference(
                    ReconciliationDifferenceType.AVERAGE_COST_DIFFERENCE,
                    symbol,
                    system_item.average_cost,
                    manual_item.average_cost,
                    abs(system_item.average_cost - manual_item.average_cost),
                    "AVERAGE_COST_MISMATCH",
                )
            )

    types = {item.difference_type for item in differences}
    if not differences:
        status = ReconciliationStatus.RECONCILED
        reasons: tuple[str, ...] = ("ACCOUNT_AND_FILL_POSITION_RECONCILED",)
    elif ReconciliationDifferenceType.DATA_INSUFFICIENT in types:
        status = ReconciliationStatus.DATA_INSUFFICIENT
        reasons = tuple(sorted({item.reason_code for item in differences}))
    elif ReconciliationDifferenceType.CORPORATE_ACTION_SUSPECTED in types:
        status = ReconciliationStatus.MANUAL_REVIEW_REQUIRED
        reasons = tuple(sorted({item.reason_code for item in differences}))
    else:
        status = ReconciliationStatus.RECONCILIATION_REQUIRED
        reasons = tuple(sorted({item.reason_code for item in differences}))
    return AccountReconciliationReport.create(
        account_id=observation.account_id,
        trading_date=observation.trading_date,
        as_of_time=as_of_time,
        manual_observation_id=observation.observation_id,
        position_snapshot_ids=tuple(item.snapshot_id for item in positions),
        fill_ledger_head=fill_ledger_head,
        fill_ledger_complete=fill_ledger_complete,
        tolerance_configuration_id=tolerance.configuration_id,
        tolerance_configuration_hash=tolerance.configuration_hash,
        status=status,
        differences=tuple(differences),
        reason_codes=reasons,
        revision=revision,
        previous_reconciliation_id=previous_reconciliation_id,
        idempotency_key=idempotency_key,
        created_at=created_at,
    )


def require_open_add_calibrated(
    report: AccountReconciliationReport,
) -> None:
    if report.status is not ReconciliationStatus.RECONCILED:
        raise ReconciliationBlocked(report.status.value)
    if not report.fill_ledger_complete:
        raise ReconciliationBlocked("FILL_LEDGER_INCOMPLETE")
    if report.differences:
        raise ReconciliationBlocked("UNRESOLVED_RECONCILIATION_DIFFERENCE")


def _money_difference(
    differences: list[ReconciliationDifference],
    difference_type: ReconciliationDifferenceType,
    *,
    expected: Decimal,
    observed: Decimal,
    tolerance: Decimal,
    reason: str,
) -> None:
    delta = abs(expected - observed)
    if delta > tolerance:
        differences.append(
            ReconciliationDifference(
                difference_type,
                None,
                expected,
                observed,
                delta,
                reason,
            )
        )


def _missing(reason: str, *, symbol: str | None = None) -> ReconciliationDifference:
    return ReconciliationDifference(
        ReconciliationDifferenceType.DATA_INSUFFICIENT,
        symbol,
        None,
        None,
        None,
        reason,
    )


def _corporate_action_ratio(system_quantity: int, manual_quantity: int) -> bool:
    smaller = min(system_quantity, manual_quantity)
    larger = max(system_quantity, manual_quantity)
    return smaller > 0 and larger % smaller == 0 and larger // smaller in {2, 3, 5, 10}


__all__ = [
    "ReconciliationBlocked",
    "reconcile_account",
    "require_open_add_calibrated",
]
