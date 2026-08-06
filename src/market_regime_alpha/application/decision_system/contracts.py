"""Immutable contracts for account observation and research decision closure."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256


class DecisionWindowState(str, Enum):
    WINDOW_NOT_OPEN = "WINDOW_NOT_OPEN"
    PREVIEW_AVAILABLE = "PREVIEW_AVAILABLE"
    WAITING_FOR_REQUIRED_EVIDENCE = "WAITING_FOR_REQUIRED_EVIDENCE"
    FINALIZING = "FINALIZING"
    FINALIZED = "FINALIZED"
    BLOCKED = "BLOCKED"
    CORRECTED = "CORRECTED"


class DailyDecisionOutcome(str, Enum):
    NO_ACTION = "NO_ACTION"
    WATCH = "WATCH"
    RESEARCH_BUY_CANDIDATE = "RESEARCH_BUY_CANDIDATE"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    ACCOUNT_NOT_CALIBRATED = "ACCOUNT_NOT_CALIBRATED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    RISK_BLOCKED = "RISK_BLOCKED"
    MODEL_NOT_QUALIFIED = "MODEL_NOT_QUALIFIED"


class ReconciliationStatus(str, Enum):
    RECONCILED = "RECONCILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


class ReconciliationDifferenceType(str, Enum):
    TOTAL_EQUITY_DIFFERENCE = "TOTAL_EQUITY_DIFFERENCE"
    CASH_DIFFERENCE = "CASH_DIFFERENCE"
    SYMBOL_QUANTITY_DIFFERENCE = "SYMBOL_QUANTITY_DIFFERENCE"
    AVAILABLE_QUANTITY_DIFFERENCE = "AVAILABLE_QUANTITY_DIFFERENCE"
    FROZEN_QUANTITY_DIFFERENCE = "FROZEN_QUANTITY_DIFFERENCE"
    AVERAGE_COST_DIFFERENCE = "AVERAGE_COST_DIFFERENCE"
    SYSTEM_MISSING_POSITION = "SYSTEM_MISSING_POSITION"
    MANUAL_MISSING_POSITION = "MANUAL_MISSING_POSITION"
    UNRECORDED_TRADE_SUSPECTED = "UNRECORDED_TRADE_SUSPECTED"
    CORPORATE_ACTION_SUSPECTED = "CORPORATE_ACTION_SUSPECTED"
    T_PLUS_ONE_DIFFERENCE = "T_PLUS_ONE_DIFFERENCE"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


class ProposalStatus(str, Enum):
    PROPOSED = "PROPOSED"
    NO_ACTION = "NO_ACTION"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    MODEL_NOT_QUALIFIED = "MODEL_NOT_QUALIFIED"
    ORDERABILITY_UNKNOWN = "ORDERABILITY_UNKNOWN"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class IndependentRiskResult(str, Enum):
    RESEARCH_APPROVED = "RESEARCH_APPROVED"
    RESEARCH_REDUCED = "RESEARCH_REDUCED"
    RISK_BLOCKED = "RISK_BLOCKED"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    ACCOUNT_NOT_CALIBRATED = "ACCOUNT_NOT_CALIBRATED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    MODEL_NOT_QUALIFIED = "MODEL_NOT_QUALIFIED"
    ORDERABILITY_UNKNOWN = "ORDERABILITY_UNKNOWN"


@dataclass(frozen=True, slots=True)
class ManualPositionObservation:
    symbol: str
    total_quantity: int
    available_quantity: int
    frozen_quantity: int
    average_cost: Decimal | None
    observed_market_value: Decimal
    notes: str = ""

    def __post_init__(self) -> None:
        _text("symbol", self.symbol)
        for label, value in (
            ("total_quantity", self.total_quantity),
            ("available_quantity", self.available_quantity),
            ("frozen_quantity", self.frozen_quantity),
        ):
            _nonnegative_integer(label, value)
        if self.available_quantity + self.frozen_quantity != self.total_quantity:
            raise ValueError("manual position quantity partition mismatch")
        if (self.total_quantity == 0) != (self.average_cost is None):
            raise ValueError("manual position average cost presence mismatch")
        if self.average_cost is not None:
            _decimal("average_cost", self.average_cost, positive=True)
        _decimal("observed_market_value", self.observed_market_value)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "total_quantity": self.total_quantity,
            "available_quantity": self.available_quantity,
            "frozen_quantity": self.frozen_quantity,
            "average_cost": _decimal_text(self.average_cost),
            "observed_market_value": _decimal_text(self.observed_market_value),
            "notes": self.notes,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ManualPositionObservation:
        _fields(
            payload,
            {
                "symbol", "total_quantity", "available_quantity",
                "frozen_quantity", "average_cost", "observed_market_value",
                "notes",
            },
            "ManualPositionObservation",
        )
        return cls(
            symbol=str(payload["symbol"]),
            total_quantity=_int(payload["total_quantity"]),
            available_quantity=_int(payload["available_quantity"]),
            frozen_quantity=_int(payload["frozen_quantity"]),
            average_cost=_optional_decimal(payload["average_cost"]),
            observed_market_value=_as_decimal(payload["observed_market_value"]),
            notes=str(payload["notes"]),
        )


@dataclass(frozen=True, slots=True)
class ManualAccountObservation:
    observation_id: ArtifactId
    content_hash: str
    account_id: str
    trading_date: date
    as_of_time: datetime
    total_equity: Decimal
    available_cash: Decimal
    frozen_cash: Decimal
    source: str
    actor: str
    reason: str
    notes: str
    idempotency_key: str
    revision: int
    previous_observation_id: ArtifactId | None
    positions: tuple[ManualPositionObservation, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        for label, value in (
            ("account_id", self.account_id),
            ("source", self.source),
            ("actor", self.actor),
            ("reason", self.reason),
            ("idempotency_key", self.idempotency_key),
        ):
            _text(label, value)
        _aware("as_of_time", self.as_of_time)
        _aware("created_at", self.created_at)
        for amount_label, amount in (
            ("total_equity", self.total_equity),
            ("available_cash", self.available_cash),
            ("frozen_cash", self.frozen_cash),
        ):
            _decimal(amount_label, amount)
        if self.available_cash + self.frozen_cash > self.total_equity:
            raise ValueError("manual cash exceeds total equity")
        _positive_integer("revision", self.revision)
        if (self.revision == 1) != (self.previous_observation_id is None):
            raise ValueError("manual observation revision lineage mismatch")
        symbols = tuple(item.symbol for item in self.positions)
        if len(symbols) != len(set(symbols)) or symbols != tuple(sorted(symbols)):
            raise ValueError("manual position symbols must be sorted and unique")
        require_sha256("content_hash", self.content_hash)
        if canonical_hash(self.semantic_payload()) != self.content_hash:
            raise ValueError("manual account observation hash mismatch")
        _verify_id("manual-account-observation", self.observation_id, self.content_hash)

    @classmethod
    def create(
        cls,
        *,
        account_id: str,
        trading_date: date,
        as_of_time: datetime,
        total_equity: Decimal,
        available_cash: Decimal,
        frozen_cash: Decimal,
        source: str,
        actor: str,
        reason: str,
        notes: str,
        idempotency_key: str,
        revision: int,
        previous_observation_id: ArtifactId | None,
        positions: tuple[ManualPositionObservation, ...],
        created_at: datetime,
    ) -> ManualAccountObservation:
        sorted_positions = tuple(sorted(positions, key=lambda item: item.symbol))
        digest = canonical_hash(
            _account_payload(
                account_id=account_id,
                trading_date=trading_date,
                as_of_time=as_of_time,
                total_equity=total_equity,
                available_cash=available_cash,
                frozen_cash=frozen_cash,
                source=source,
                actor=actor,
                reason=reason,
                notes=notes,
                idempotency_key=idempotency_key,
                revision=revision,
                previous_observation_id=previous_observation_id,
                positions=sorted_positions,
                created_at=created_at,
            )
        )
        return cls(
            observation_id=_id("manual-account-observation", digest),
            content_hash=digest,
            account_id=account_id,
            trading_date=trading_date,
            as_of_time=as_of_time,
            total_equity=total_equity,
            available_cash=available_cash,
            frozen_cash=frozen_cash,
            source=source,
            actor=actor,
            reason=reason,
            notes=notes,
            idempotency_key=idempotency_key,
            revision=revision,
            previous_observation_id=previous_observation_id,
            positions=sorted_positions,
            created_at=created_at,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _account_payload(
            account_id=self.account_id,
            trading_date=self.trading_date,
            as_of_time=self.as_of_time,
            total_equity=self.total_equity,
            available_cash=self.available_cash,
            frozen_cash=self.frozen_cash,
            source=self.source,
            actor=self.actor,
            reason=self.reason,
            notes=self.notes,
            idempotency_key=self.idempotency_key,
            revision=self.revision,
            previous_observation_id=self.previous_observation_id,
            positions=self.positions,
            created_at=self.created_at,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "observation_id": str(self.observation_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ManualAccountObservation:
        required = {
            "observation_id", "content_hash", "account_id", "trading_date",
            "as_of_time", "total_equity", "available_cash", "frozen_cash",
            "source", "actor", "reason", "notes", "idempotency_key",
            "revision", "previous_observation_id", "positions", "created_at",
        }
        _fields(payload, required, "ManualAccountObservation")
        return cls(
            observation_id=ArtifactId(str(payload["observation_id"])),
            content_hash=str(payload["content_hash"]),
            account_id=str(payload["account_id"]),
            trading_date=date.fromisoformat(str(payload["trading_date"])),
            as_of_time=datetime.fromisoformat(str(payload["as_of_time"])),
            total_equity=_as_decimal(payload["total_equity"]),
            available_cash=_as_decimal(payload["available_cash"]),
            frozen_cash=_as_decimal(payload["frozen_cash"]),
            source=str(payload["source"]),
            actor=str(payload["actor"]),
            reason=str(payload["reason"]),
            notes=str(payload["notes"]),
            idempotency_key=str(payload["idempotency_key"]),
            revision=_int(payload["revision"]),
            previous_observation_id=_optional_id(payload["previous_observation_id"]),
            positions=tuple(
                ManualPositionObservation.from_canonical_dict(_mapping(item))
                for item in _sequence(payload["positions"])
            ),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
        )


@dataclass(frozen=True, slots=True)
class FillDerivedPositionReference:
    snapshot_id: ArtifactId
    snapshot_hash: str
    account_id: str
    symbol: str
    as_of_time: datetime
    total_quantity: int
    available_quantity: int | None
    frozen_quantity: int | None
    average_cost: Decimal | None
    source_fill_ids: tuple[str, ...]
    complete: bool

    def __post_init__(self) -> None:
        require_sha256("snapshot_hash", self.snapshot_hash)
        _text("account_id", self.account_id)
        _text("symbol", self.symbol)
        _aware("as_of_time", self.as_of_time)
        _nonnegative_integer("total_quantity", self.total_quantity)
        if self.available_quantity is not None:
            _nonnegative_integer("available_quantity", self.available_quantity)
        if self.frozen_quantity is not None:
            _nonnegative_integer("frozen_quantity", self.frozen_quantity)
        if self.available_quantity is not None and self.frozen_quantity is not None:
            if self.available_quantity + self.frozen_quantity != self.total_quantity:
                raise ValueError("Fill-derived position quantity partition mismatch")
        if self.average_cost is not None:
            _decimal("average_cost", self.average_cost, positive=True)
        if not isinstance(self.complete, bool):
            raise TypeError("complete must be bool")
        if len(self.source_fill_ids) != len(set(self.source_fill_ids)):
            raise ValueError("source Fill IDs must be unique")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": str(self.snapshot_id),
            "snapshot_hash": self.snapshot_hash,
            "account_id": self.account_id,
            "symbol": self.symbol,
            "as_of_time": self.as_of_time.isoformat(),
            "total_quantity": self.total_quantity,
            "available_quantity": self.available_quantity,
            "frozen_quantity": self.frozen_quantity,
            "average_cost": _decimal_text(self.average_cost),
            "source_fill_ids": list(self.source_fill_ids),
            "complete": self.complete,
        }


@dataclass(frozen=True, slots=True)
class ReconciliationTolerance:
    configuration_id: ArtifactId
    configuration_hash: str
    equity_tolerance: Decimal
    cash_tolerance: Decimal
    average_cost_tolerance: Decimal

    def __post_init__(self) -> None:
        require_sha256("configuration_hash", self.configuration_hash)
        for label, value in (
            ("equity_tolerance", self.equity_tolerance),
            ("cash_tolerance", self.cash_tolerance),
            ("average_cost_tolerance", self.average_cost_tolerance),
        ):
            _decimal(label, value)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
            "equity_tolerance": _decimal_text(self.equity_tolerance),
            "cash_tolerance": _decimal_text(self.cash_tolerance),
            "average_cost_tolerance": _decimal_text(self.average_cost_tolerance),
        }


@dataclass(frozen=True, slots=True)
class ReconciliationDifference:
    difference_type: ReconciliationDifferenceType
    symbol: str | None
    expected_value: Decimal | None
    observed_value: Decimal | None
    absolute_difference: Decimal | None
    reason_code: str

    def __post_init__(self) -> None:
        if self.symbol is not None:
            _text("symbol", self.symbol)
        _text("reason_code", self.reason_code)
        for label, value in (
            ("expected_value", self.expected_value),
            ("observed_value", self.observed_value),
            ("absolute_difference", self.absolute_difference),
        ):
            if value is not None:
                _decimal(label, value)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "difference_type": self.difference_type.value,
            "symbol": self.symbol,
            "expected_value": _decimal_text(self.expected_value),
            "observed_value": _decimal_text(self.observed_value),
            "absolute_difference": _decimal_text(self.absolute_difference),
            "reason_code": self.reason_code,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ReconciliationDifference:
        return cls(
            difference_type=ReconciliationDifferenceType(
                str(payload["difference_type"])
            ),
            symbol=None if payload["symbol"] is None else str(payload["symbol"]),
            expected_value=_optional_decimal(payload["expected_value"]),
            observed_value=_optional_decimal(payload["observed_value"]),
            absolute_difference=_optional_decimal(payload["absolute_difference"]),
            reason_code=str(payload["reason_code"]),
        )


@dataclass(frozen=True, slots=True)
class AccountReconciliationReport:
    reconciliation_id: ArtifactId
    content_hash: str
    account_id: str
    trading_date: date
    as_of_time: datetime
    manual_observation_id: ArtifactId
    position_snapshot_ids: tuple[ArtifactId, ...]
    fill_ledger_head: str
    fill_ledger_complete: bool
    tolerance_configuration_id: ArtifactId
    tolerance_configuration_hash: str
    status: ReconciliationStatus
    differences: tuple[ReconciliationDifference, ...]
    reason_codes: tuple[str, ...]
    revision: int
    previous_reconciliation_id: ArtifactId | None
    idempotency_key: str
    created_at: datetime

    def __post_init__(self) -> None:
        _text("account_id", self.account_id)
        _text("fill_ledger_head", self.fill_ledger_head)
        _text("idempotency_key", self.idempotency_key)
        _aware("as_of_time", self.as_of_time)
        _aware("created_at", self.created_at)
        require_sha256("tolerance_configuration_hash", self.tolerance_configuration_hash)
        _positive_integer("revision", self.revision)
        if (self.revision == 1) != (self.previous_reconciliation_id is None):
            raise ValueError("reconciliation revision lineage mismatch")
        if self.position_snapshot_ids != tuple(
            sorted(set(self.position_snapshot_ids), key=str)
        ):
            raise ValueError("position snapshot IDs must be sorted and unique")
        _sorted_unique_text("reason_codes", self.reason_codes)
        require_sha256("content_hash", self.content_hash)
        if canonical_hash(self.semantic_payload()) != self.content_hash:
            raise ValueError("Account Reconciliation hash mismatch")
        _verify_id("account-reconciliation", self.reconciliation_id, self.content_hash)

    @classmethod
    def create(cls, **values: Any) -> AccountReconciliationReport:
        normalized = dict(values)
        normalized["position_snapshot_ids"] = tuple(
            sorted(set(values["position_snapshot_ids"]), key=str)
        )
        normalized["differences"] = tuple(values["differences"])
        normalized["reason_codes"] = tuple(sorted(set(values["reason_codes"])))
        digest = canonical_hash(_reconciliation_payload(**normalized))
        return cls(
            reconciliation_id=_id("account-reconciliation", digest),
            content_hash=digest,
            **normalized,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _reconciliation_payload(**_dataclass_values(self, exclude={"reconciliation_id", "content_hash"}))

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "reconciliation_id": str(self.reconciliation_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> AccountReconciliationReport:
        return cls(
            reconciliation_id=ArtifactId(str(payload["reconciliation_id"])),
            content_hash=str(payload["content_hash"]),
            account_id=str(payload["account_id"]),
            trading_date=date.fromisoformat(str(payload["trading_date"])),
            as_of_time=datetime.fromisoformat(str(payload["as_of_time"])),
            manual_observation_id=ArtifactId(str(payload["manual_observation_id"])),
            position_snapshot_ids=tuple(
                ArtifactId(str(item)) for item in _sequence(payload["position_snapshot_ids"])
            ),
            fill_ledger_head=str(payload["fill_ledger_head"]),
            fill_ledger_complete=bool(payload["fill_ledger_complete"]),
            tolerance_configuration_id=ArtifactId(str(payload["tolerance_configuration_id"])),
            tolerance_configuration_hash=str(payload["tolerance_configuration_hash"]),
            status=ReconciliationStatus(str(payload["status"])),
            differences=tuple(
                ReconciliationDifference.from_canonical_dict(_mapping(item))
                for item in _sequence(payload["differences"])
            ),
            reason_codes=tuple(str(item) for item in _sequence(payload["reason_codes"])),
            revision=_int(payload["revision"]),
            previous_reconciliation_id=_optional_id(payload["previous_reconciliation_id"]),
            idempotency_key=str(payload["idempotency_key"]),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
        )


@dataclass(frozen=True, slots=True)
class DecisionLineage:
    continuous_operation_id: ArtifactId
    runtime_tick_id: ArtifactId
    state_receipt_id: ArtifactId
    state_receipt_hash: str
    market_state_id: ArtifactId
    etf_state_ids: tuple[ArtifactId, ...]
    theme_state_ids: tuple[ArtifactId, ...]
    capital_state_id: ArtifactId
    dynamic_pool_id: ArtifactId
    candidate_set_id: ArtifactId
    signal_ids: tuple[ArtifactId, ...]
    forecast_ids: tuple[ArtifactId, ...]
    position_snapshot_ids: tuple[ArtifactId, ...]
    model_ids: tuple[ArtifactId, ...]
    configuration_ids: tuple[ArtifactId, ...]
    as_of_time: datetime
    available_at: datetime

    def __post_init__(self) -> None:
        require_sha256("state_receipt_hash", self.state_receipt_hash)
        _aware("as_of_time", self.as_of_time)
        _aware("available_at", self.available_at)
        if self.available_at > self.as_of_time:
            raise ValueError("Decision lineage AvailableAt exceeds AsOfTime")
        for label in (
            "etf_state_ids", "theme_state_ids", "signal_ids", "forecast_ids",
            "position_snapshot_ids", "model_ids", "configuration_ids",
        ):
            values = getattr(self, label)
            if values != tuple(sorted(set(values), key=str)):
                raise ValueError(f"{label} must be sorted and unique")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "continuous_operation_id": str(self.continuous_operation_id),
            "runtime_tick_id": str(self.runtime_tick_id),
            "state_receipt_id": str(self.state_receipt_id),
            "state_receipt_hash": self.state_receipt_hash,
            "market_state_id": str(self.market_state_id),
            "etf_state_ids": [str(item) for item in self.etf_state_ids],
            "theme_state_ids": [str(item) for item in self.theme_state_ids],
            "capital_state_id": str(self.capital_state_id),
            "dynamic_pool_id": str(self.dynamic_pool_id),
            "candidate_set_id": str(self.candidate_set_id),
            "signal_ids": [str(item) for item in self.signal_ids],
            "forecast_ids": [str(item) for item in self.forecast_ids],
            "position_snapshot_ids": [str(item) for item in self.position_snapshot_ids],
            "model_ids": [str(item) for item in self.model_ids],
            "configuration_ids": [str(item) for item in self.configuration_ids],
            "as_of_time": self.as_of_time.isoformat(),
            "available_at": self.available_at.isoformat(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> DecisionLineage:
        def ids(name: str) -> tuple[ArtifactId, ...]:
            return tuple(ArtifactId(str(item)) for item in _sequence(payload[name]))

        return cls(
            continuous_operation_id=ArtifactId(str(payload["continuous_operation_id"])),
            runtime_tick_id=ArtifactId(str(payload["runtime_tick_id"])),
            state_receipt_id=ArtifactId(str(payload["state_receipt_id"])),
            state_receipt_hash=str(payload["state_receipt_hash"]),
            market_state_id=ArtifactId(str(payload["market_state_id"])),
            etf_state_ids=ids("etf_state_ids"),
            theme_state_ids=ids("theme_state_ids"),
            capital_state_id=ArtifactId(str(payload["capital_state_id"])),
            dynamic_pool_id=ArtifactId(str(payload["dynamic_pool_id"])),
            candidate_set_id=ArtifactId(str(payload["candidate_set_id"])),
            signal_ids=ids("signal_ids"),
            forecast_ids=ids("forecast_ids"),
            position_snapshot_ids=ids("position_snapshot_ids"),
            model_ids=ids("model_ids"),
            configuration_ids=ids("configuration_ids"),
            as_of_time=datetime.fromisoformat(str(payload["as_of_time"])),
            available_at=datetime.fromisoformat(str(payload["available_at"])),
        )


@dataclass(frozen=True, slots=True)
class SummaryCandidate:
    symbol: str
    dynamic_pool_membership: bool
    etf: str | None
    theme: str | None
    candidate_rank: int
    candidate_score: Decimal
    signal_id: ArtifactId
    signal_state: str
    factor_coverage: Decimal
    forecast_id: ArtifactId
    forecast_bias: str
    empirical_mfe: Decimal | None
    empirical_mae: Decimal | None
    sample_count: int
    data_coverage: Decimal
    main_evidence: tuple[str, ...]
    counter_evidence: tuple[str, ...]
    risk_points: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    valid_until: datetime
    current_quantity: int
    research_exposure_ceiling: Decimal
    risk_result: str
    model_qualification: str
    liquidity: Decimal
    orderability: str

    def __post_init__(self) -> None:
        _text("symbol", self.symbol)
        _positive_integer("candidate_rank", self.candidate_rank)
        _decimal("candidate_score", self.candidate_score, allow_negative=True)
        _decimal_ratio("factor_coverage", self.factor_coverage)
        _decimal_ratio("data_coverage", self.data_coverage)
        _decimal_ratio("research_exposure_ceiling", self.research_exposure_ceiling)
        _decimal_ratio("liquidity", self.liquidity)
        _nonnegative_integer("sample_count", self.sample_count)
        _nonnegative_integer("current_quantity", self.current_quantity)
        _aware("valid_until", self.valid_until)
        for label in (
            "main_evidence", "counter_evidence", "risk_points",
            "invalidation_conditions",
        ):
            _sorted_unique_text(label, getattr(self, label))

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "dynamic_pool_membership": self.dynamic_pool_membership,
            "etf": self.etf,
            "theme": self.theme,
            "candidate_rank": self.candidate_rank,
            "candidate_score": _decimal_text(self.candidate_score),
            "signal_id": str(self.signal_id),
            "signal_state": self.signal_state,
            "factor_coverage": _decimal_text(self.factor_coverage),
            "forecast_id": str(self.forecast_id),
            "forecast_bias": self.forecast_bias,
            "empirical_mfe": _decimal_text(self.empirical_mfe),
            "empirical_mae": _decimal_text(self.empirical_mae),
            "sample_count": self.sample_count,
            "data_coverage": _decimal_text(self.data_coverage),
            "main_evidence": list(self.main_evidence),
            "counter_evidence": list(self.counter_evidence),
            "risk_points": list(self.risk_points),
            "invalidation_conditions": list(self.invalidation_conditions),
            "valid_until": self.valid_until.isoformat(),
            "current_quantity": self.current_quantity,
            "research_exposure_ceiling": _decimal_text(self.research_exposure_ceiling),
            "risk_result": self.risk_result,
            "model_qualification": self.model_qualification,
            "liquidity": _decimal_text(self.liquidity),
            "orderability": self.orderability,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> SummaryCandidate:
        return cls(
            symbol=str(payload["symbol"]),
            dynamic_pool_membership=bool(payload["dynamic_pool_membership"]),
            etf=None if payload["etf"] is None else str(payload["etf"]),
            theme=None if payload["theme"] is None else str(payload["theme"]),
            candidate_rank=_int(payload["candidate_rank"]),
            candidate_score=_as_decimal(payload["candidate_score"]),
            signal_id=ArtifactId(str(payload["signal_id"])),
            signal_state=str(payload["signal_state"]),
            factor_coverage=_as_decimal(payload["factor_coverage"]),
            forecast_id=ArtifactId(str(payload["forecast_id"])),
            forecast_bias=str(payload["forecast_bias"]),
            empirical_mfe=_optional_decimal(payload["empirical_mfe"]),
            empirical_mae=_optional_decimal(payload["empirical_mae"]),
            sample_count=_int(payload["sample_count"]),
            data_coverage=_as_decimal(payload["data_coverage"]),
            main_evidence=tuple(str(item) for item in _sequence(payload["main_evidence"])),
            counter_evidence=tuple(str(item) for item in _sequence(payload["counter_evidence"])),
            risk_points=tuple(str(item) for item in _sequence(payload["risk_points"])),
            invalidation_conditions=tuple(str(item) for item in _sequence(payload["invalidation_conditions"])),
            valid_until=datetime.fromisoformat(str(payload["valid_until"])),
            current_quantity=_int(payload["current_quantity"]),
            research_exposure_ceiling=_as_decimal(payload["research_exposure_ceiling"]),
            risk_result=str(payload["risk_result"]),
            model_qualification=str(payload["model_qualification"]),
            liquidity=_as_decimal(payload["liquidity"]),
            orderability=str(payload["orderability"]),
        )


@dataclass(frozen=True, slots=True)
class DailyDecisionWindowSummary:
    summary_id: ArtifactId
    content_hash: str
    account_id: str
    trading_date: date
    strategy_configuration_id: ArtifactId
    strategy_configuration_hash: str
    as_of_time: datetime
    available_at: datetime
    lifecycle_state: DecisionWindowState
    outcome: DailyDecisionOutcome
    manual_observation_id: ArtifactId
    reconciliation_id: ArtifactId
    lineage: DecisionLineage
    candidates: tuple[SummaryCandidate, ...]
    revision: int
    previous_summary_id: ArtifactId | None
    correction_of_summary_id: ArtifactId | None
    idempotency_key: str
    created_at: datetime

    def __post_init__(self) -> None:
        _text("account_id", self.account_id)
        _text("idempotency_key", self.idempotency_key)
        require_sha256("strategy_configuration_hash", self.strategy_configuration_hash)
        _aware("as_of_time", self.as_of_time)
        _aware("available_at", self.available_at)
        _aware("created_at", self.created_at)
        if self.available_at > self.as_of_time:
            raise ValueError("Summary AvailableAt exceeds AsOfTime")
        if self.lineage.as_of_time != self.as_of_time:
            raise ValueError("Summary and lineage AsOfTime differ")
        if self.lineage.available_at > self.available_at:
            raise ValueError("Summary predates lineage availability")
        _positive_integer("revision", self.revision)
        if (self.revision == 1) != (self.previous_summary_id is None):
            raise ValueError("Summary revision lineage mismatch")
        if self.lifecycle_state is DecisionWindowState.CORRECTED:
            if self.correction_of_summary_id is None:
                raise ValueError("Correction requires original Summary")
        elif self.correction_of_summary_id is not None:
            raise ValueError("only Correction may bind corrected Summary")
        symbols = tuple(item.symbol for item in self.candidates)
        ranks = tuple(item.candidate_rank for item in self.candidates)
        if len(symbols) != len(set(symbols)) or len(ranks) != len(set(ranks)):
            raise ValueError("Summary candidates require unique symbols and ranks")
        if any(not item.dynamic_pool_membership for item in self.candidates):
            raise ValueError("Summary candidate is outside Dynamic Pool")
        if any(item.signal_id not in self.lineage.signal_ids for item in self.candidates):
            raise ValueError("Summary Candidate/Signal lineage mismatch")
        if any(item.forecast_id not in self.lineage.forecast_ids for item in self.candidates):
            raise ValueError("Summary Candidate/Forecast lineage mismatch")
        require_sha256("content_hash", self.content_hash)
        if canonical_hash(self.semantic_payload()) != self.content_hash:
            raise ValueError("Daily Summary hash mismatch")
        _verify_id("daily-decision-summary", self.summary_id, self.content_hash)

    @classmethod
    def create(cls, **values: Any) -> DailyDecisionWindowSummary:
        normalized = dict(values)
        normalized["candidates"] = tuple(
            sorted(values["candidates"], key=lambda item: item.candidate_rank)
        )
        digest = canonical_hash(_summary_payload(**normalized))
        return cls(
            summary_id=_id("daily-decision-summary", digest),
            content_hash=digest,
            **normalized,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _summary_payload(**_dataclass_values(self, exclude={"summary_id", "content_hash"}))

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"summary_id": str(self.summary_id), "content_hash": self.content_hash, **self.semantic_payload()}

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> DailyDecisionWindowSummary:
        return cls(
            summary_id=ArtifactId(str(payload["summary_id"])),
            content_hash=str(payload["content_hash"]),
            account_id=str(payload["account_id"]),
            trading_date=date.fromisoformat(str(payload["trading_date"])),
            strategy_configuration_id=ArtifactId(str(payload["strategy_configuration_id"])),
            strategy_configuration_hash=str(payload["strategy_configuration_hash"]),
            as_of_time=datetime.fromisoformat(str(payload["as_of_time"])),
            available_at=datetime.fromisoformat(str(payload["available_at"])),
            lifecycle_state=DecisionWindowState(str(payload["lifecycle_state"])),
            outcome=DailyDecisionOutcome(str(payload["outcome"])),
            manual_observation_id=ArtifactId(str(payload["manual_observation_id"])),
            reconciliation_id=ArtifactId(str(payload["reconciliation_id"])),
            lineage=DecisionLineage.from_canonical_dict(_mapping(payload["lineage"])),
            candidates=tuple(SummaryCandidate.from_canonical_dict(_mapping(item)) for item in _sequence(payload["candidates"])),
            revision=_int(payload["revision"]),
            previous_summary_id=_optional_id(payload["previous_summary_id"]),
            correction_of_summary_id=_optional_id(payload["correction_of_summary_id"]),
            idempotency_key=str(payload["idempotency_key"]),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
        )


@dataclass(frozen=True, slots=True)
class PortfolioProposalLine:
    symbol: str
    current_weight: Decimal
    proposed_research_weight: Decimal
    weight_delta: Decimal
    research_amount: Decimal
    theme_exposure: Decimal
    single_symbol_exposure: Decimal
    liquidity_constraint: str
    position_constraint: str
    reason_codes: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    model_qualification: str
    orderability: str

    def __post_init__(self) -> None:
        _text("symbol", self.symbol)
        for label in ("current_weight", "proposed_research_weight", "theme_exposure", "single_symbol_exposure"):
            _decimal_ratio(label, getattr(self, label))
        _decimal("weight_delta", self.weight_delta, allow_negative=True)
        _decimal("research_amount", self.research_amount)
        if self.weight_delta != self.proposed_research_weight - self.current_weight:
            raise ValueError("Proposal line weight delta mismatch")
        _sorted_unique_text("reason_codes", self.reason_codes)
        _sorted_unique_text("invalidation_conditions", self.invalidation_conditions)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "current_weight": _decimal_text(self.current_weight),
            "proposed_research_weight": _decimal_text(self.proposed_research_weight),
            "weight_delta": _decimal_text(self.weight_delta),
            "research_amount": _decimal_text(self.research_amount),
            "theme_exposure": _decimal_text(self.theme_exposure),
            "single_symbol_exposure": _decimal_text(self.single_symbol_exposure),
            "liquidity_constraint": self.liquidity_constraint,
            "position_constraint": self.position_constraint,
            "reason_codes": list(self.reason_codes),
            "invalidation_conditions": list(self.invalidation_conditions),
            "model_qualification": self.model_qualification,
            "orderability": self.orderability,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> PortfolioProposalLine:
        return cls(
            symbol=str(payload["symbol"]),
            current_weight=_as_decimal(payload["current_weight"]),
            proposed_research_weight=_as_decimal(payload["proposed_research_weight"]),
            weight_delta=_as_decimal(payload["weight_delta"]),
            research_amount=_as_decimal(payload["research_amount"]),
            theme_exposure=_as_decimal(payload["theme_exposure"]),
            single_symbol_exposure=_as_decimal(payload["single_symbol_exposure"]),
            liquidity_constraint=str(payload["liquidity_constraint"]),
            position_constraint=str(payload["position_constraint"]),
            reason_codes=tuple(str(item) for item in _sequence(payload["reason_codes"])),
            invalidation_conditions=tuple(str(item) for item in _sequence(payload["invalidation_conditions"])),
            model_qualification=str(payload["model_qualification"]),
            orderability=str(payload["orderability"]),
        )


@dataclass(frozen=True, slots=True)
class ResearchPortfolioProposal:
    proposal_id: ArtifactId
    content_hash: str
    account_id: str
    trading_date: date
    as_of_time: datetime
    summary_id: ArtifactId
    manual_observation_id: ArtifactId
    reconciliation_id: ArtifactId
    risk_configuration_id: ArtifactId
    risk_configuration_hash: str
    status: ProposalStatus
    lines: tuple[PortfolioProposalLine, ...]
    reason_codes: tuple[str, ...]
    idempotency_key: str
    created_at: datetime

    def __post_init__(self) -> None:
        _aware("as_of_time", self.as_of_time)
        _aware("created_at", self.created_at)
        require_sha256("risk_configuration_hash", self.risk_configuration_hash)
        _sorted_unique_text("reason_codes", self.reason_codes)
        symbols = tuple(item.symbol for item in self.lines)
        if symbols != tuple(sorted(set(symbols))):
            raise ValueError("Proposal symbols must be sorted and unique")
        if sum((item.proposed_research_weight for item in self.lines), Decimal("0")) > Decimal("1"):
            raise ValueError("Proposal weights exceed one")
        require_sha256("content_hash", self.content_hash)
        if canonical_hash(self.semantic_payload()) != self.content_hash:
            raise ValueError("Portfolio Proposal hash mismatch")
        _verify_id("research-portfolio-proposal", self.proposal_id, self.content_hash)

    @classmethod
    def create(cls, **values: Any) -> ResearchPortfolioProposal:
        normalized = dict(values)
        normalized["lines"] = tuple(sorted(values["lines"], key=lambda item: item.symbol))
        normalized["reason_codes"] = tuple(sorted(set(values["reason_codes"])))
        digest = canonical_hash(_proposal_payload(**normalized))
        return cls(proposal_id=_id("research-portfolio-proposal", digest), content_hash=digest, **normalized)

    def semantic_payload(self) -> dict[str, Any]:
        return _proposal_payload(**_dataclass_values(self, exclude={"proposal_id", "content_hash"}))

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"proposal_id": str(self.proposal_id), "content_hash": self.content_hash, **self.semantic_payload()}

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ResearchPortfolioProposal:
        return cls(
            proposal_id=ArtifactId(str(payload["proposal_id"])),
            content_hash=str(payload["content_hash"]),
            account_id=str(payload["account_id"]),
            trading_date=date.fromisoformat(str(payload["trading_date"])),
            as_of_time=datetime.fromisoformat(str(payload["as_of_time"])),
            summary_id=ArtifactId(str(payload["summary_id"])),
            manual_observation_id=ArtifactId(str(payload["manual_observation_id"])),
            reconciliation_id=ArtifactId(str(payload["reconciliation_id"])),
            risk_configuration_id=ArtifactId(str(payload["risk_configuration_id"])),
            risk_configuration_hash=str(payload["risk_configuration_hash"]),
            status=ProposalStatus(str(payload["status"])),
            lines=tuple(PortfolioProposalLine.from_canonical_dict(_mapping(item)) for item in _sequence(payload["lines"])),
            reason_codes=tuple(str(item) for item in _sequence(payload["reason_codes"])),
            idempotency_key=str(payload["idempotency_key"]),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
        )


@dataclass(frozen=True, slots=True)
class DecisionRiskConfiguration:
    configuration_id: ArtifactId
    configuration_hash: str
    maximum_observation_age_seconds: int
    maximum_data_age_seconds: int
    maximum_single_symbol_weight: Decimal
    maximum_theme_weight: Decimal
    minimum_liquidity: Decimal
    daily_loss_limit: Decimal | None

    def __post_init__(self) -> None:
        require_sha256("configuration_hash", self.configuration_hash)
        _positive_integer("maximum_observation_age_seconds", self.maximum_observation_age_seconds)
        _positive_integer("maximum_data_age_seconds", self.maximum_data_age_seconds)
        for label in ("maximum_single_symbol_weight", "maximum_theme_weight", "minimum_liquidity"):
            _decimal_ratio(label, getattr(self, label))
        if self.daily_loss_limit is not None:
            _decimal("daily_loss_limit", self.daily_loss_limit)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
            "maximum_observation_age_seconds": self.maximum_observation_age_seconds,
            "maximum_data_age_seconds": self.maximum_data_age_seconds,
            "maximum_single_symbol_weight": _decimal_text(self.maximum_single_symbol_weight),
            "maximum_theme_weight": _decimal_text(self.maximum_theme_weight),
            "minimum_liquidity": _decimal_text(self.minimum_liquidity),
            "daily_loss_limit": _decimal_text(self.daily_loss_limit),
        }


@dataclass(frozen=True, slots=True)
class IndependentRiskDecision:
    risk_decision_id: ArtifactId
    content_hash: str
    proposal_id: ArtifactId
    account_id: str
    trading_date: date
    as_of_time: datetime
    result: IndependentRiskResult
    approved_research_weight: Decimal
    reason_codes: tuple[str, ...]
    risk_configuration_id: ArtifactId
    risk_configuration_hash: str
    idempotency_key: str
    created_at: datetime

    def __post_init__(self) -> None:
        _aware("as_of_time", self.as_of_time)
        _aware("created_at", self.created_at)
        _decimal_ratio("approved_research_weight", self.approved_research_weight)
        _sorted_unique_text("reason_codes", self.reason_codes)
        require_sha256("risk_configuration_hash", self.risk_configuration_hash)
        require_sha256("content_hash", self.content_hash)
        if canonical_hash(self.semantic_payload()) != self.content_hash:
            raise ValueError("Independent Risk Decision hash mismatch")
        _verify_id("independent-risk-decision", self.risk_decision_id, self.content_hash)

    @classmethod
    def create(cls, **values: Any) -> IndependentRiskDecision:
        normalized = dict(values)
        normalized["reason_codes"] = tuple(sorted(set(values["reason_codes"])))
        digest = canonical_hash(_risk_payload(**normalized))
        return cls(risk_decision_id=_id("independent-risk-decision", digest), content_hash=digest, **normalized)

    def semantic_payload(self) -> dict[str, Any]:
        return _risk_payload(**_dataclass_values(self, exclude={"risk_decision_id", "content_hash"}))

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"risk_decision_id": str(self.risk_decision_id), "content_hash": self.content_hash, **self.semantic_payload()}

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> IndependentRiskDecision:
        return cls(
            risk_decision_id=ArtifactId(str(payload["risk_decision_id"])),
            content_hash=str(payload["content_hash"]),
            proposal_id=ArtifactId(str(payload["proposal_id"])),
            account_id=str(payload["account_id"]),
            trading_date=date.fromisoformat(str(payload["trading_date"])),
            as_of_time=datetime.fromisoformat(str(payload["as_of_time"])),
            result=IndependentRiskResult(str(payload["result"])),
            approved_research_weight=_as_decimal(payload["approved_research_weight"]),
            reason_codes=tuple(str(item) for item in _sequence(payload["reason_codes"])),
            risk_configuration_id=ArtifactId(str(payload["risk_configuration_id"])),
            risk_configuration_hash=str(payload["risk_configuration_hash"]),
            idempotency_key=str(payload["idempotency_key"]),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
        )


def _account_payload(**values: Any) -> dict[str, Any]:
    return {
        "account_id": values["account_id"],
        "trading_date": values["trading_date"].isoformat(),
        "as_of_time": values["as_of_time"].isoformat(),
        "total_equity": _decimal_text(values["total_equity"]),
        "available_cash": _decimal_text(values["available_cash"]),
        "frozen_cash": _decimal_text(values["frozen_cash"]),
        "source": values["source"], "actor": values["actor"],
        "reason": values["reason"], "notes": values["notes"],
        "idempotency_key": values["idempotency_key"],
        "revision": values["revision"],
        "previous_observation_id": _id_text(values["previous_observation_id"]),
        "positions": [item.to_canonical_dict() for item in values["positions"]],
        "created_at": values["created_at"].isoformat(),
    }


def _reconciliation_payload(**values: Any) -> dict[str, Any]:
    return {
        "account_id": values["account_id"],
        "trading_date": values["trading_date"].isoformat(),
        "as_of_time": values["as_of_time"].isoformat(),
        "manual_observation_id": str(values["manual_observation_id"]),
        "position_snapshot_ids": [str(item) for item in values["position_snapshot_ids"]],
        "fill_ledger_head": values["fill_ledger_head"],
        "fill_ledger_complete": values["fill_ledger_complete"],
        "tolerance_configuration_id": str(values["tolerance_configuration_id"]),
        "tolerance_configuration_hash": values["tolerance_configuration_hash"],
        "status": values["status"].value,
        "differences": [item.to_canonical_dict() for item in values["differences"]],
        "reason_codes": list(values["reason_codes"]),
        "revision": values["revision"],
        "previous_reconciliation_id": _id_text(values["previous_reconciliation_id"]),
        "idempotency_key": values["idempotency_key"],
        "created_at": values["created_at"].isoformat(),
    }


def _summary_payload(**values: Any) -> dict[str, Any]:
    return {
        "account_id": values["account_id"],
        "trading_date": values["trading_date"].isoformat(),
        "strategy_configuration_id": str(values["strategy_configuration_id"]),
        "strategy_configuration_hash": values["strategy_configuration_hash"],
        "as_of_time": values["as_of_time"].isoformat(),
        "available_at": values["available_at"].isoformat(),
        "lifecycle_state": values["lifecycle_state"].value,
        "outcome": values["outcome"].value,
        "manual_observation_id": str(values["manual_observation_id"]),
        "reconciliation_id": str(values["reconciliation_id"]),
        "lineage": values["lineage"].to_canonical_dict(),
        "candidates": [item.to_canonical_dict() for item in values["candidates"]],
        "revision": values["revision"],
        "previous_summary_id": _id_text(values["previous_summary_id"]),
        "correction_of_summary_id": _id_text(values["correction_of_summary_id"]),
        "idempotency_key": values["idempotency_key"],
        "created_at": values["created_at"].isoformat(),
    }


def _proposal_payload(**values: Any) -> dict[str, Any]:
    return {
        "account_id": values["account_id"],
        "trading_date": values["trading_date"].isoformat(),
        "as_of_time": values["as_of_time"].isoformat(),
        "summary_id": str(values["summary_id"]),
        "manual_observation_id": str(values["manual_observation_id"]),
        "reconciliation_id": str(values["reconciliation_id"]),
        "risk_configuration_id": str(values["risk_configuration_id"]),
        "risk_configuration_hash": values["risk_configuration_hash"],
        "status": values["status"].value,
        "lines": [item.to_canonical_dict() for item in values["lines"]],
        "reason_codes": list(values["reason_codes"]),
        "idempotency_key": values["idempotency_key"],
        "created_at": values["created_at"].isoformat(),
    }


def _risk_payload(**values: Any) -> dict[str, Any]:
    return {
        "proposal_id": str(values["proposal_id"]),
        "account_id": values["account_id"],
        "trading_date": values["trading_date"].isoformat(),
        "as_of_time": values["as_of_time"].isoformat(),
        "result": values["result"].value,
        "approved_research_weight": _decimal_text(values["approved_research_weight"]),
        "reason_codes": list(values["reason_codes"]),
        "risk_configuration_id": str(values["risk_configuration_id"]),
        "risk_configuration_hash": values["risk_configuration_hash"],
        "idempotency_key": values["idempotency_key"],
        "created_at": values["created_at"].isoformat(),
    }


def _decimal(label: str, value: Decimal, *, positive: bool = False, allow_negative: bool = False) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise TypeError(f"{label} must be a finite Decimal")
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -10:
        raise ValueError(f"{label} precision exceeds ten decimal places")
    if positive and value <= 0:
        raise ValueError(f"{label} must be positive")
    if not positive and not allow_negative and value < 0:
        raise ValueError(f"{label} must be non-negative")


def _decimal_ratio(label: str, value: Decimal) -> None:
    _decimal(label, value)
    if value > 1:
        raise ValueError(f"{label} must be between zero and one")


def _as_decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid Decimal value") from exc


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else _as_decimal(value)


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _aware(label: str, value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _text(label: str, value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty trimmed text")


def _positive_integer(label: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")


def _nonnegative_integer(label: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")


def _sorted_unique_text(label: str, values: tuple[str, ...]) -> None:
    if values != tuple(sorted(set(values))) or any(not item for item in values):
        raise ValueError(f"{label} must be sorted, unique and non-empty")


def _id(prefix: str, digest: str) -> ArtifactId:
    return ArtifactId(f"{prefix}-{digest.split(':', 1)[1][:24]}")


def _verify_id(prefix: str, value: ArtifactId, digest: str) -> None:
    if value != _id(prefix, digest):
        raise ValueError(f"{prefix} identity mismatch")


def _id_text(value: ArtifactId | None) -> str | None:
    return None if value is None else str(value)


def _optional_id(value: object) -> ArtifactId | None:
    return None if value is None else ArtifactId(str(value))


def _fields(payload: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(payload) != expected:
        raise ValueError(f"{label} fields mismatch")


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected object")
    return value


def _sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("expected array")
    return tuple(value)


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer")
    return int(str(value))


def _dataclass_values(value: object, *, exclude: set[str]) -> dict[str, Any]:
    return {
        name: getattr(value, name)
        for name in value.__dataclass_fields__  # type: ignore[attr-defined]
        if name not in exclude
    }


__all__ = [
    "AccountReconciliationReport", "DailyDecisionOutcome",
    "DailyDecisionWindowSummary", "DecisionLineage", "DecisionRiskConfiguration",
    "DecisionWindowState", "FillDerivedPositionReference", "IndependentRiskDecision",
    "IndependentRiskResult", "ManualAccountObservation", "ManualPositionObservation",
    "PortfolioProposalLine", "ProposalStatus", "ReconciliationDifference",
    "ReconciliationDifferenceType", "ReconciliationStatus",
    "ReconciliationTolerance", "ResearchPortfolioProposal", "SummaryCandidate",
]
