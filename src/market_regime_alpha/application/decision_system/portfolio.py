"""Deterministic research-only portfolio proposal; no execution dependency."""

from __future__ import annotations

from decimal import Decimal

from market_regime_alpha.application.decision_system.contracts import (
    AccountReconciliationReport,
    DailyDecisionWindowSummary,
    DecisionRiskConfiguration,
    DecisionModelQualification,
    DecisionOrderability,
    FillDerivedPositionReference,
    ManualAccountObservation,
    PortfolioProposalLine,
    ProposalStatus,
    ReconciliationStatus,
    ResearchPortfolioProposal,
)


_WEIGHT_QUANTUM = Decimal("0.00000001")
_MONEY_QUANTUM = Decimal("0.000001")


def build_research_portfolio_proposal(
    *,
    summary: DailyDecisionWindowSummary,
    observation: ManualAccountObservation,
    reconciliation: AccountReconciliationReport,
    positions: tuple[FillDerivedPositionReference, ...],
    configuration: DecisionRiskConfiguration,
    idempotency_key: str,
) -> ResearchPortfolioProposal:
    _validate_lineage(
        summary,
        observation,
        reconciliation,
        positions,
        configuration,
    )
    reasons: set[str] = set()
    lines: list[PortfolioProposalLine] = []
    status = ProposalStatus.PROPOSED
    if reconciliation.status is not ReconciliationStatus.RECONCILED:
        status = ProposalStatus.RECONCILIATION_REQUIRED
        reasons.add("RECONCILIATION_NOT_RESOLVED")
    elif any(
        item.model_qualification is not DecisionModelQualification.QUALIFIED
        for item in summary.candidates
    ):
        status = ProposalStatus.MODEL_NOT_QUALIFIED
        reasons.add("MODEL_NOT_QUALIFIED")
    elif any(
        item.orderability is not DecisionOrderability.ORDERABLE
        for item in summary.candidates
    ):
        status = ProposalStatus.ORDERABILITY_UNKNOWN
        reasons.add("ORDERABILITY_UNKNOWN")
    elif not summary.candidates:
        status = ProposalStatus.NO_ACTION
        reasons.add("NO_RESEARCH_CANDIDATE")

    fill_positions = {item.symbol: item for item in positions}
    observed_positions = {item.symbol: item for item in observation.positions}
    remaining_cash = observation.available_cash
    theme_weights: dict[str, Decimal] = {}
    for candidate in summary.candidates:
        fill_position = fill_positions.get(candidate.symbol)
        observed_position = observed_positions.get(candidate.symbol)
        current_market_value = (
            Decimal("0")
            if fill_position is None or observed_position is None
            else observed_position.observed_market_value
        )
        current_weight = _weight(Decimal("0") if observation.total_equity == 0 else current_market_value / observation.total_equity)
        line_reasons: set[str] = set()
        proposed = current_weight
        liquidity_constraint = "SATISFIED"
        position_constraint = "SATISFIED"
        if status is ProposalStatus.PROPOSED:
            if candidate.liquidity < configuration.minimum_liquidity:
                liquidity_constraint = "LIQUIDITY_INSUFFICIENT"
                line_reasons.add("LIQUIDITY_BELOW_MINIMUM")
            else:
                proposed = _weight(
                    min(
                        candidate.research_exposure_ceiling,
                        configuration.maximum_single_symbol_weight,
                    )
                )
                theme_key = candidate.theme or "UNCLASSIFIED"
                theme_used = theme_weights.get(theme_key, Decimal("0"))
                proposed = _weight(
                    min(
                        proposed,
                        max(
                            Decimal("0"),
                            configuration.maximum_theme_weight - theme_used,
                        ),
                    )
                )
                required_cash = max(
                    Decimal("0"),
                    (proposed - current_weight) * observation.total_equity,
                )
                if required_cash > remaining_cash:
                    proposed = _weight(
                        current_weight + (Decimal("0") if observation.total_equity == 0 else remaining_cash / observation.total_equity)
                    )
                    position_constraint = "AVAILABLE_CASH_CAPPED"
                    line_reasons.add("AVAILABLE_CASH_INSUFFICIENT_FOR_TARGET")
                    required_cash = remaining_cash
                remaining_cash -= required_cash
                theme_weights[theme_key] = theme_used + proposed
        else:
            line_reasons.update(reasons)
            position_constraint = "FAIL_CLOSED"
        delta = proposed - current_weight
        lines.append(
            PortfolioProposalLine(
                symbol=candidate.symbol,
                current_weight=current_weight,
                proposed_research_weight=proposed,
                weight_delta=delta,
                research_amount=_money(proposed * observation.total_equity),
                theme_exposure=theme_weights.get(candidate.theme or "UNCLASSIFIED", proposed),
                single_symbol_exposure=proposed,
                liquidity_constraint=liquidity_constraint,
                position_constraint=position_constraint,
                reason_codes=tuple(sorted(line_reasons)),
                invalidation_conditions=candidate.invalidation_conditions,
                model_qualification=candidate.model_qualification,
                orderability=candidate.orderability,
            )
        )
    if status is ProposalStatus.PROPOSED and not any(item.weight_delta > 0 for item in lines):
        status = ProposalStatus.NO_ACTION
        reasons.add("NO_OPEN_OR_ADD_RESEARCH_DELTA")
    return ResearchPortfolioProposal.create(
        account_id=summary.account_id,
        trading_date=summary.trading_date,
        as_of_time=summary.as_of_time,
        summary_id=summary.summary_id,
        manual_observation_id=observation.observation_id,
        reconciliation_id=reconciliation.reconciliation_id,
        risk_configuration_id=configuration.configuration_id,
        risk_configuration_hash=configuration.configuration_hash,
        status=status,
        lines=tuple(lines),
        reason_codes=tuple(sorted(reasons)),
        idempotency_key=idempotency_key,
        created_at=summary.created_at,
    )


def _validate_lineage(
    summary: DailyDecisionWindowSummary,
    observation: ManualAccountObservation,
    reconciliation: AccountReconciliationReport,
    positions: tuple[FillDerivedPositionReference, ...],
    configuration: DecisionRiskConfiguration,
) -> None:
    if not configuration.configuration_hash:
        raise ValueError("Risk Configuration is invalid")
    if summary.account_id != observation.account_id or summary.account_id != reconciliation.account_id:
        raise ValueError("Portfolio Account lineage mismatch")
    if summary.trading_date != observation.trading_date or summary.trading_date != reconciliation.trading_date:
        raise ValueError("Portfolio TradingDate lineage mismatch")
    if summary.manual_observation_id != observation.observation_id:
        raise ValueError("Portfolio Manual Account lineage mismatch")
    if summary.reconciliation_id != reconciliation.reconciliation_id:
        raise ValueError("Portfolio Reconciliation lineage mismatch")
    if reconciliation.manual_observation_id != observation.observation_id:
        raise ValueError("Reconciliation/Observation lineage mismatch")
    if reconciliation.position_snapshot_ids != tuple(
        sorted((item.snapshot_id for item in positions), key=str)
    ):
        raise ValueError("Portfolio Fill Position lineage mismatch")
    fill_by_symbol = {item.symbol: item for item in positions}
    if any(
        item.current_quantity
        != (
            0
            if item.symbol not in fill_by_symbol
            else fill_by_symbol[item.symbol].total_quantity
        )
        for item in summary.candidates
    ):
        raise ValueError("Portfolio current Position lineage mismatch")
    if observation.as_of_time > summary.as_of_time or reconciliation.as_of_time > summary.as_of_time:
        raise ValueError("Portfolio input is later than Summary AsOfTime")


def _weight(value: Decimal) -> Decimal:
    return value.quantize(_WEIGHT_QUANTUM)


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANTUM)


__all__ = ["build_research_portfolio_proposal"]
