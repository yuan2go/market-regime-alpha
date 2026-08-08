"""Immutable contracts for account observation and research decision closure."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping
import unicodedata

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
)
from market_regime_alpha.market_data.contracts import (
    canonical_decimal,
    parse_canonical_decimal,
)


MANUAL_ACCOUNT_OBSERVATION_SCHEMA = "manual_account_observation/v1"
ACCOUNT_RECONCILIATION_SCHEMA = "account_reconciliation_report/v1"
DECISION_LINEAGE_SCHEMA = "decision_lineage/v3"
LEGACY_DECISION_LINEAGE_SCHEMA = "decision_lineage/v2"
SUMMARY_CANDIDATE_SCHEMA = "daily_summary_candidate/v2"
DAILY_DECISION_SUMMARY_SCHEMA = "daily_decision_window_summary/v1"
RESEARCH_PORTFOLIO_PROPOSAL_SCHEMA = "research_portfolio_proposal/v1"
DECISION_RISK_CONFIGURATION_SCHEMA = "decision_risk_configuration/v1"
RECONCILIATION_TOLERANCE_SCHEMA = "reconciliation_tolerance/v1"
INDEPENDENT_RISK_DECISION_SCHEMA = "independent_risk_decision/v1"
FILL_DERIVED_POSITION_REFERENCE_SCHEMA = "fill_derived_position_reference/v1"
PORTFOLIO_PROPOSAL_LINE_SCHEMA = "portfolio_proposal_line/v1"


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


class DecisionModelQualification(str, Enum):
    QUALIFIED = "QUALIFIED"
    UNQUALIFIED = "UNQUALIFIED"
    UNKNOWN = "UNKNOWN"


class DecisionOrderability(str, Enum):
    ORDERABLE = "ORDERABLE"
    NOT_ORDERABLE = "NOT_ORDERABLE"
    UNKNOWN = "UNKNOWN"


class DecisionSignalState(str, Enum):
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    INACTIVE = "INACTIVE"
    WATCH = "WATCH"
    CONFIRMED_FOR_RESEARCH = "CONFIRMED_FOR_RESEARCH"


class DecisionForecastBias(str, Enum):
    UP_BIAS = "UP_BIAS"
    DOWN_BIAS = "DOWN_BIAS"
    NEUTRAL = "NEUTRAL"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


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
            symbol=_string(payload["symbol"]),
            total_quantity=_int(payload["total_quantity"]),
            available_quantity=_int(payload["available_quantity"]),
            frozen_quantity=_int(payload["frozen_quantity"]),
            average_cost=_optional_decimal(payload["average_cost"]),
            observed_market_value=_as_decimal(payload["observed_market_value"]),
            notes=_string(payload["notes"], allow_empty=True),
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
    schema_version: str = field(
        default=MANUAL_ACCOUNT_OBSERVATION_SCHEMA,
        init=False,
    )

    def __post_init__(self) -> None:
        _schema(self.schema_version, MANUAL_ACCOUNT_OBSERVATION_SCHEMA)
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
        if _canonical_hash(self.semantic_payload()) != self.content_hash:
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
        digest = _canonical_hash(
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
            "schema_version", "observation_id", "content_hash", "account_id", "trading_date",
            "as_of_time", "total_equity", "available_cash", "frozen_cash",
            "source", "actor", "reason", "notes", "idempotency_key",
            "revision", "previous_observation_id", "positions", "created_at",
        }
        _fields(payload, required, "ManualAccountObservation")
        _schema_value(payload, MANUAL_ACCOUNT_OBSERVATION_SCHEMA)
        return cls(
            observation_id=ArtifactId(_string(payload["observation_id"])),
            content_hash=_string(payload["content_hash"]),
            account_id=_string(payload["account_id"]),
            trading_date=_date_value(payload["trading_date"]),
            as_of_time=_instant(payload["as_of_time"]),
            total_equity=_as_decimal(payload["total_equity"]),
            available_cash=_as_decimal(payload["available_cash"]),
            frozen_cash=_as_decimal(payload["frozen_cash"]),
            source=_string(payload["source"]),
            actor=_string(payload["actor"]),
            reason=_string(payload["reason"]),
            notes=_string(payload["notes"], allow_empty=True),
            idempotency_key=_string(payload["idempotency_key"]),
            revision=_int(payload["revision"]),
            previous_observation_id=_optional_id(payload["previous_observation_id"]),
            positions=tuple(
                ManualPositionObservation.from_canonical_dict(_mapping(item))
                for item in _sequence(payload["positions"])
            ),
            created_at=_instant(payload["created_at"]),
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
    schema_version: str = field(
        default=FILL_DERIVED_POSITION_REFERENCE_SCHEMA,
        init=False,
    )

    def __post_init__(self) -> None:
        _schema(self.schema_version, FILL_DERIVED_POSITION_REFERENCE_SCHEMA)
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
            "schema_version": self.schema_version,
            "snapshot_id": str(self.snapshot_id),
            "snapshot_hash": self.snapshot_hash,
            "account_id": self.account_id,
            "symbol": self.symbol,
            "as_of_time": canonical_datetime(self.as_of_time),
            "total_quantity": self.total_quantity,
            "available_quantity": self.available_quantity,
            "frozen_quantity": self.frozen_quantity,
            "average_cost": _decimal_text(self.average_cost),
            "source_fill_ids": list(self.source_fill_ids),
            "complete": self.complete,
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> FillDerivedPositionReference:
        _fields(
            payload,
            {
                "schema_version", "snapshot_id", "snapshot_hash", "account_id",
                "symbol", "as_of_time", "total_quantity", "available_quantity",
                "frozen_quantity", "average_cost", "source_fill_ids", "complete",
            },
            "FillDerivedPositionReference",
        )
        _schema_value(payload, FILL_DERIVED_POSITION_REFERENCE_SCHEMA)
        return cls(
            snapshot_id=ArtifactId(_string(payload["snapshot_id"])),
            snapshot_hash=_string(payload["snapshot_hash"]),
            account_id=_string(payload["account_id"]),
            symbol=_string(payload["symbol"]),
            as_of_time=_instant(payload["as_of_time"]),
            total_quantity=_int(payload["total_quantity"]),
            available_quantity=_optional_int(payload["available_quantity"]),
            frozen_quantity=_optional_int(payload["frozen_quantity"]),
            average_cost=_optional_decimal(payload["average_cost"]),
            source_fill_ids=tuple(
                _string(item) for item in _sequence(payload["source_fill_ids"])
            ),
            complete=_bool(payload["complete"]),
        )


@dataclass(frozen=True, slots=True)
class ReconciliationTolerance:
    configuration_id: ArtifactId
    configuration_hash: str
    equity_tolerance: Decimal
    cash_tolerance: Decimal
    average_cost_tolerance: Decimal
    schema_version: str = field(
        default=RECONCILIATION_TOLERANCE_SCHEMA,
        init=False,
    )

    def __post_init__(self) -> None:
        _schema(self.schema_version, RECONCILIATION_TOLERANCE_SCHEMA)
        require_sha256("configuration_hash", self.configuration_hash)
        for label, value in (
            ("equity_tolerance", self.equity_tolerance),
            ("cash_tolerance", self.cash_tolerance),
            ("average_cost_tolerance", self.average_cost_tolerance),
        ):
            _decimal(label, value)
        expected = _canonical_hash(self.semantic_payload())
        if expected != self.configuration_hash:
            raise ValueError("Reconciliation Tolerance hash mismatch")
        _verify_id("reconciliation-tolerance", self.configuration_id, expected)

    @classmethod
    def create(
        cls,
        *,
        equity_tolerance: Decimal,
        cash_tolerance: Decimal,
        average_cost_tolerance: Decimal,
    ) -> ReconciliationTolerance:
        payload = _reconciliation_tolerance_payload(
            equity_tolerance=equity_tolerance,
            cash_tolerance=cash_tolerance,
            average_cost_tolerance=average_cost_tolerance,
        )
        digest = _canonical_hash(payload)
        return cls(
            configuration_id=_id("reconciliation-tolerance", digest),
            configuration_hash=digest,
            equity_tolerance=equity_tolerance,
            cash_tolerance=cash_tolerance,
            average_cost_tolerance=average_cost_tolerance,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _reconciliation_tolerance_payload(
            equity_tolerance=self.equity_tolerance,
            cash_tolerance=self.cash_tolerance,
            average_cost_tolerance=self.average_cost_tolerance,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
            "equity_tolerance": _decimal_text(self.equity_tolerance),
            "cash_tolerance": _decimal_text(self.cash_tolerance),
            "average_cost_tolerance": _decimal_text(self.average_cost_tolerance),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> ReconciliationTolerance:
        _fields(
            payload,
            {
                "schema_version", "configuration_id", "configuration_hash",
                "equity_tolerance", "cash_tolerance", "average_cost_tolerance",
            },
            "ReconciliationTolerance",
        )
        _schema_value(payload, RECONCILIATION_TOLERANCE_SCHEMA)
        return cls(
            configuration_id=ArtifactId(_string(payload["configuration_id"])),
            configuration_hash=_string(payload["configuration_hash"]),
            equity_tolerance=_as_decimal(payload["equity_tolerance"]),
            cash_tolerance=_as_decimal(payload["cash_tolerance"]),
            average_cost_tolerance=_as_decimal(
                payload["average_cost_tolerance"]
            ),
        )


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
        _fields(
            payload,
            {
                "difference_type", "symbol", "expected_value", "observed_value",
                "absolute_difference", "reason_code",
            },
            "ReconciliationDifference",
        )
        return cls(
            difference_type=ReconciliationDifferenceType(
                _string(payload["difference_type"])
            ),
            symbol=None if payload["symbol"] is None else _string(payload["symbol"]),
            expected_value=_optional_decimal(payload["expected_value"]),
            observed_value=_optional_decimal(payload["observed_value"]),
            absolute_difference=_optional_decimal(payload["absolute_difference"]),
            reason_code=_string(payload["reason_code"]),
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
    schema_version: str = field(
        default=ACCOUNT_RECONCILIATION_SCHEMA,
        init=False,
    )

    def __post_init__(self) -> None:
        _schema(self.schema_version, ACCOUNT_RECONCILIATION_SCHEMA)
        _text("account_id", self.account_id)
        require_sha256("fill_ledger_head", self.fill_ledger_head)
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
        if _canonical_hash(self.semantic_payload()) != self.content_hash:
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
        digest = _canonical_hash(_reconciliation_payload(**normalized))
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
        _fields(
            payload,
            {
                "schema_version", "reconciliation_id", "content_hash", "account_id",
                "trading_date", "as_of_time", "manual_observation_id",
                "position_snapshot_ids", "fill_ledger_head", "fill_ledger_complete",
                "tolerance_configuration_id", "tolerance_configuration_hash",
                "status", "differences", "reason_codes", "revision",
                "previous_reconciliation_id", "idempotency_key", "created_at",
            },
            "AccountReconciliationReport",
        )
        _schema_value(payload, ACCOUNT_RECONCILIATION_SCHEMA)
        return cls(
            reconciliation_id=ArtifactId(_string(payload["reconciliation_id"])),
            content_hash=_string(payload["content_hash"]),
            account_id=_string(payload["account_id"]),
            trading_date=_date_value(payload["trading_date"]),
            as_of_time=_instant(payload["as_of_time"]),
            manual_observation_id=ArtifactId(_string(payload["manual_observation_id"])),
            position_snapshot_ids=tuple(
                ArtifactId(_string(item)) for item in _sequence(payload["position_snapshot_ids"])
            ),
            fill_ledger_head=_string(payload["fill_ledger_head"]),
            fill_ledger_complete=_bool(payload["fill_ledger_complete"]),
            tolerance_configuration_id=ArtifactId(_string(payload["tolerance_configuration_id"])),
            tolerance_configuration_hash=_string(payload["tolerance_configuration_hash"]),
            status=ReconciliationStatus(_string(payload["status"])),
            differences=tuple(
                ReconciliationDifference.from_canonical_dict(_mapping(item))
                for item in _sequence(payload["differences"])
            ),
            reason_codes=tuple(_string(item) for item in _sequence(payload["reason_codes"])),
            revision=_int(payload["revision"]),
            previous_reconciliation_id=_optional_id(payload["previous_reconciliation_id"]),
            idempotency_key=_string(payload["idempotency_key"]),
            created_at=_instant(payload["created_at"]),
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
    candidate_binding_id: ArtifactId
    candidate_binding_hash: str
    signal_bundle_id: ArtifactId
    signal_bundle_hash: str
    forecast_bundle_id: ArtifactId
    forecast_bundle_hash: str
    signal_ids: tuple[ArtifactId, ...]
    forecast_ids: tuple[ArtifactId, ...]
    position_snapshot_ids: tuple[ArtifactId, ...]
    model_ids: tuple[ArtifactId, ...]
    configuration_ids: tuple[ArtifactId, ...]
    data_eligibility: DataEligibility
    as_of_time: datetime
    available_at: datetime
    schema_version: str = DECISION_LINEAGE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version not in {
            LEGACY_DECISION_LINEAGE_SCHEMA,
            DECISION_LINEAGE_SCHEMA,
        }:
            raise ValueError("unsupported DecisionLineage schema")
        if (
            self.schema_version == LEGACY_DECISION_LINEAGE_SCHEMA
            and self.data_eligibility is not DataEligibility.UNQUALIFIED
        ):
            raise ValueError(
                "legacy DecisionLineage has UNQUALIFIED data authority"
            )
        require_sha256("state_receipt_hash", self.state_receipt_hash)
        require_sha256("candidate_binding_hash", self.candidate_binding_hash)
        require_sha256("signal_bundle_hash", self.signal_bundle_hash)
        require_sha256("forecast_bundle_hash", self.forecast_bundle_hash)
        if not isinstance(self.data_eligibility, DataEligibility):
            raise TypeError("Decision lineage data_eligibility must be DataEligibility")
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
        payload = {
            "schema_version": self.schema_version,
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
            "candidate_binding_id": str(self.candidate_binding_id),
            "candidate_binding_hash": self.candidate_binding_hash,
            "signal_bundle_id": str(self.signal_bundle_id),
            "signal_bundle_hash": self.signal_bundle_hash,
            "forecast_bundle_id": str(self.forecast_bundle_id),
            "forecast_bundle_hash": self.forecast_bundle_hash,
            "signal_ids": [str(item) for item in self.signal_ids],
            "forecast_ids": [str(item) for item in self.forecast_ids],
            "position_snapshot_ids": [str(item) for item in self.position_snapshot_ids],
            "model_ids": [str(item) for item in self.model_ids],
            "configuration_ids": [str(item) for item in self.configuration_ids],
            "as_of_time": canonical_datetime(self.as_of_time),
            "available_at": canonical_datetime(self.available_at),
        }
        if self.schema_version == DECISION_LINEAGE_SCHEMA:
            payload["data_eligibility"] = self.data_eligibility.value
        return payload

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> DecisionLineage:
        def ids(name: str) -> tuple[ArtifactId, ...]:
            return tuple(ArtifactId(_string(item)) for item in _sequence(payload[name]))

        schema = _string(payload.get("schema_version"))
        expected = {
                "schema_version", "continuous_operation_id", "runtime_tick_id",
                "state_receipt_id", "state_receipt_hash", "market_state_id",
                "etf_state_ids", "theme_state_ids", "capital_state_id",
                "dynamic_pool_id", "candidate_set_id", "candidate_binding_id",
                "candidate_binding_hash", "signal_bundle_id", "signal_bundle_hash",
                "forecast_bundle_id", "forecast_bundle_hash", "signal_ids",
                "forecast_ids", "position_snapshot_ids", "model_ids",
                "configuration_ids", "as_of_time", "available_at",
        }
        if schema == DECISION_LINEAGE_SCHEMA:
            expected.add("data_eligibility")
        elif schema != LEGACY_DECISION_LINEAGE_SCHEMA:
            raise ValueError("unsupported DecisionLineage schema")
        _fields(payload, expected, "DecisionLineage")

        return cls(
            continuous_operation_id=ArtifactId(_string(payload["continuous_operation_id"])),
            runtime_tick_id=ArtifactId(_string(payload["runtime_tick_id"])),
            state_receipt_id=ArtifactId(_string(payload["state_receipt_id"])),
            state_receipt_hash=_string(payload["state_receipt_hash"]),
            market_state_id=ArtifactId(_string(payload["market_state_id"])),
            etf_state_ids=ids("etf_state_ids"),
            theme_state_ids=ids("theme_state_ids"),
            capital_state_id=ArtifactId(_string(payload["capital_state_id"])),
            dynamic_pool_id=ArtifactId(_string(payload["dynamic_pool_id"])),
            candidate_set_id=ArtifactId(_string(payload["candidate_set_id"])),
            candidate_binding_id=ArtifactId(_string(payload["candidate_binding_id"])),
            candidate_binding_hash=_string(payload["candidate_binding_hash"]),
            signal_bundle_id=ArtifactId(_string(payload["signal_bundle_id"])),
            signal_bundle_hash=_string(payload["signal_bundle_hash"]),
            forecast_bundle_id=ArtifactId(_string(payload["forecast_bundle_id"])),
            forecast_bundle_hash=_string(payload["forecast_bundle_hash"]),
            signal_ids=ids("signal_ids"),
            forecast_ids=ids("forecast_ids"),
            position_snapshot_ids=ids("position_snapshot_ids"),
            model_ids=ids("model_ids"),
            configuration_ids=ids("configuration_ids"),
            data_eligibility=(
                DataEligibility(_string(payload["data_eligibility"]))
                if schema == DECISION_LINEAGE_SCHEMA
                else DataEligibility.UNQUALIFIED
            ),
            as_of_time=_instant(payload["as_of_time"]),
            available_at=_instant(payload["available_at"]),
            schema_version=schema,
        )


@dataclass(frozen=True, slots=True)
class SummaryCandidate:
    symbol: str
    dynamic_pool_membership: bool
    dynamic_pool_id: ArtifactId
    candidate_set_id: ArtifactId
    candidate_binding_id: ArtifactId
    etf: str | None
    theme: str | None
    candidate_rank: int
    candidate_score: Decimal
    signal_id: ArtifactId
    signal_hash: str
    signal_symbol: str
    signal_candidate_binding_id: ArtifactId
    signal_model_id: ArtifactId
    signal_state: DecisionSignalState
    factor_coverage: Decimal
    forecast_id: ArtifactId
    forecast_hash: str
    forecast_symbol: str
    forecast_signal_id: ArtifactId
    forecast_candidate_binding_id: ArtifactId
    forecast_model_id: ArtifactId
    forecast_bias: DecisionForecastBias
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
    risk_result: IndependentRiskResult | None
    model_qualification: DecisionModelQualification
    liquidity: Decimal
    orderability: DecisionOrderability
    schema_version: str = field(default=SUMMARY_CANDIDATE_SCHEMA, init=False)

    def __post_init__(self) -> None:
        _schema(self.schema_version, SUMMARY_CANDIDATE_SCHEMA)
        _text("symbol", self.symbol)
        if self.etf is not None:
            _text("etf", self.etf)
        if self.theme is not None:
            _text("theme", self.theme)
        if not isinstance(self.dynamic_pool_membership, bool):
            raise TypeError("dynamic_pool_membership must be bool")
        require_sha256("signal_hash", self.signal_hash)
        require_sha256("forecast_hash", self.forecast_hash)
        if self.signal_symbol != self.symbol or self.forecast_symbol != self.symbol:
            raise ValueError("Candidate/Signal/Forecast Symbol lineage mismatch")
        if self.signal_candidate_binding_id != self.candidate_binding_id:
            raise ValueError("Candidate/Signal binding lineage mismatch")
        if self.forecast_candidate_binding_id != self.candidate_binding_id:
            raise ValueError("Candidate/Forecast binding lineage mismatch")
        if self.forecast_signal_id != self.signal_id:
            raise ValueError("Signal/Forecast lineage mismatch")
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
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "dynamic_pool_membership": self.dynamic_pool_membership,
            "dynamic_pool_id": str(self.dynamic_pool_id),
            "candidate_set_id": str(self.candidate_set_id),
            "candidate_binding_id": str(self.candidate_binding_id),
            "etf": self.etf,
            "theme": self.theme,
            "candidate_rank": self.candidate_rank,
            "candidate_score": _decimal_text(self.candidate_score),
            "signal_id": str(self.signal_id),
            "signal_hash": self.signal_hash,
            "signal_symbol": self.signal_symbol,
            "signal_candidate_binding_id": str(self.signal_candidate_binding_id),
            "signal_model_id": str(self.signal_model_id),
            "signal_state": self.signal_state.value,
            "factor_coverage": _decimal_text(self.factor_coverage),
            "forecast_id": str(self.forecast_id),
            "forecast_hash": self.forecast_hash,
            "forecast_symbol": self.forecast_symbol,
            "forecast_signal_id": str(self.forecast_signal_id),
            "forecast_candidate_binding_id": str(self.forecast_candidate_binding_id),
            "forecast_model_id": str(self.forecast_model_id),
            "forecast_bias": self.forecast_bias.value,
            "empirical_mfe": _decimal_text(self.empirical_mfe),
            "empirical_mae": _decimal_text(self.empirical_mae),
            "sample_count": self.sample_count,
            "data_coverage": _decimal_text(self.data_coverage),
            "main_evidence": list(self.main_evidence),
            "counter_evidence": list(self.counter_evidence),
            "risk_points": list(self.risk_points),
            "invalidation_conditions": list(self.invalidation_conditions),
            "valid_until": canonical_datetime(self.valid_until),
            "current_quantity": self.current_quantity,
            "research_exposure_ceiling": _decimal_text(self.research_exposure_ceiling),
            "risk_result": None if self.risk_result is None else self.risk_result.value,
            "model_qualification": self.model_qualification.value,
            "liquidity": _decimal_text(self.liquidity),
            "orderability": self.orderability.value,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> SummaryCandidate:
        expected = {
            "schema_version", "symbol", "dynamic_pool_membership", "dynamic_pool_id",
            "candidate_set_id", "candidate_binding_id", "etf", "theme",
            "candidate_rank", "candidate_score", "signal_id", "signal_hash",
            "signal_symbol", "signal_candidate_binding_id", "signal_model_id",
            "signal_state", "factor_coverage", "forecast_id", "forecast_hash",
            "forecast_symbol", "forecast_signal_id", "forecast_candidate_binding_id",
            "forecast_model_id", "forecast_bias", "empirical_mfe", "empirical_mae",
            "sample_count", "data_coverage", "main_evidence", "counter_evidence",
            "risk_points", "invalidation_conditions", "valid_until",
            "current_quantity", "research_exposure_ceiling", "risk_result",
            "model_qualification", "liquidity", "orderability",
        }
        _fields(payload, expected, "SummaryCandidate")
        _schema_value(payload, SUMMARY_CANDIDATE_SCHEMA)
        raw_risk = payload["risk_result"]
        return cls(
            symbol=_string(payload["symbol"]),
            dynamic_pool_membership=_bool(payload["dynamic_pool_membership"]),
            dynamic_pool_id=ArtifactId(_string(payload["dynamic_pool_id"])),
            candidate_set_id=ArtifactId(_string(payload["candidate_set_id"])),
            candidate_binding_id=ArtifactId(_string(payload["candidate_binding_id"])),
            etf=None if payload["etf"] is None else _string(payload["etf"]),
            theme=None if payload["theme"] is None else _string(payload["theme"]),
            candidate_rank=_int(payload["candidate_rank"]),
            candidate_score=_as_decimal(payload["candidate_score"]),
            signal_id=ArtifactId(_string(payload["signal_id"])),
            signal_hash=_string(payload["signal_hash"]),
            signal_symbol=_string(payload["signal_symbol"]),
            signal_candidate_binding_id=ArtifactId(
                _string(payload["signal_candidate_binding_id"])
            ),
            signal_model_id=ArtifactId(_string(payload["signal_model_id"])),
            signal_state=DecisionSignalState(_string(payload["signal_state"])),
            factor_coverage=_as_decimal(payload["factor_coverage"]),
            forecast_id=ArtifactId(_string(payload["forecast_id"])),
            forecast_hash=_string(payload["forecast_hash"]),
            forecast_symbol=_string(payload["forecast_symbol"]),
            forecast_signal_id=ArtifactId(_string(payload["forecast_signal_id"])),
            forecast_candidate_binding_id=ArtifactId(
                _string(payload["forecast_candidate_binding_id"])
            ),
            forecast_model_id=ArtifactId(_string(payload["forecast_model_id"])),
            forecast_bias=DecisionForecastBias(_string(payload["forecast_bias"])),
            empirical_mfe=_optional_decimal(payload["empirical_mfe"]),
            empirical_mae=_optional_decimal(payload["empirical_mae"]),
            sample_count=_int(payload["sample_count"]),
            data_coverage=_as_decimal(payload["data_coverage"]),
            main_evidence=tuple(_string(item) for item in _sequence(payload["main_evidence"])),
            counter_evidence=tuple(_string(item) for item in _sequence(payload["counter_evidence"])),
            risk_points=tuple(_string(item) for item in _sequence(payload["risk_points"])),
            invalidation_conditions=tuple(_string(item) for item in _sequence(payload["invalidation_conditions"])),
            valid_until=_instant(payload["valid_until"]),
            current_quantity=_int(payload["current_quantity"]),
            research_exposure_ceiling=_as_decimal(payload["research_exposure_ceiling"]),
            risk_result=(
                None
                if raw_risk is None
                else IndependentRiskResult(_string(raw_risk))
            ),
            model_qualification=DecisionModelQualification(
                _string(payload["model_qualification"])
            ),
            liquidity=_as_decimal(payload["liquidity"]),
            orderability=DecisionOrderability(_string(payload["orderability"])),
        )


def decision_signal_evidence_hash(candidate: SummaryCandidate) -> str:
    return _canonical_hash(
        {
            "schema_version": "decision_signal_evidence/v1",
            "signal_id": str(candidate.signal_id),
            "symbol": candidate.signal_symbol,
            "candidate_binding_id": str(candidate.signal_candidate_binding_id),
            "model_id": str(candidate.signal_model_id),
            "signal_state": candidate.signal_state.value,
            "factor_coverage": _decimal_text(candidate.factor_coverage),
        }
    )


def decision_forecast_evidence_hash(candidate: SummaryCandidate) -> str:
    return _canonical_hash(
        {
            "schema_version": "decision_forecast_evidence/v1",
            "forecast_id": str(candidate.forecast_id),
            "symbol": candidate.forecast_symbol,
            "signal_id": str(candidate.forecast_signal_id),
            "candidate_binding_id": str(
                candidate.forecast_candidate_binding_id
            ),
            "model_id": str(candidate.forecast_model_id),
            "forecast_bias": candidate.forecast_bias.value,
            "empirical_mfe": _decimal_text(candidate.empirical_mfe),
            "empirical_mae": _decimal_text(candidate.empirical_mae),
            "sample_count": candidate.sample_count,
            "data_coverage": _decimal_text(candidate.data_coverage),
        }
    )


def bind_decision_candidate_evidence(
    lineage: DecisionLineage,
    candidates: tuple[SummaryCandidate, ...],
) -> DecisionLineage:
    ordered = tuple(sorted(candidates, key=lambda item: item.candidate_rank))
    candidate_hash = _canonical_hash(
        {
            "schema_version": (
                "decision_candidate_binding/v2"
                if lineage.schema_version == DECISION_LINEAGE_SCHEMA
                else "decision_candidate_binding/v1"
            ),
            "candidate_binding_id": str(lineage.candidate_binding_id),
            "candidate_set_id": str(lineage.candidate_set_id),
            "dynamic_pool_id": str(lineage.dynamic_pool_id),
            "candidates": [
                {
                    "symbol": item.symbol,
                    "dynamic_pool_membership": item.dynamic_pool_membership,
                    "etf": item.etf,
                    "theme": item.theme,
                    "candidate_rank": item.candidate_rank,
                    "candidate_score": _decimal_text(item.candidate_score),
                    "main_evidence": list(item.main_evidence),
                    "counter_evidence": list(item.counter_evidence),
                    "risk_points": list(item.risk_points),
                    "invalidation_conditions": list(
                        item.invalidation_conditions
                    ),
                    "valid_until": canonical_datetime(item.valid_until),
                    "research_exposure_ceiling": _decimal_text(
                        item.research_exposure_ceiling
                    ),
                    **(
                        {}
                        if lineage.schema_version == DECISION_LINEAGE_SCHEMA
                        else {
                            "model_qualification": item.model_qualification.value
                        }
                    ),
                    "liquidity": _decimal_text(item.liquidity),
                    "orderability": item.orderability.value,
                }
                for item in ordered
            ],
        }
    )
    signal_payload = {
            "schema_version": (
                "decision_signal_bundle/v2"
                if lineage.schema_version == DECISION_LINEAGE_SCHEMA
                else "decision_signal_bundle/v1"
            ),
            "signal_bundle_id": str(lineage.signal_bundle_id),
            "signals": [
                {
                    "signal_id": str(item.signal_id),
                    "content_hash": item.signal_hash,
                }
                for item in ordered
            ],
        }
    if lineage.schema_version == DECISION_LINEAGE_SCHEMA:
        signal_payload["data_eligibility"] = lineage.data_eligibility.value
    signal_hash = _canonical_hash(signal_payload)
    forecast_payload = {
            "schema_version": (
                "decision_forecast_bundle/v2"
                if lineage.schema_version == DECISION_LINEAGE_SCHEMA
                else "decision_forecast_bundle/v1"
            ),
            "forecast_bundle_id": str(lineage.forecast_bundle_id),
            "forecasts": [
                {
                    "forecast_id": str(item.forecast_id),
                    "content_hash": item.forecast_hash,
                }
                for item in ordered
            ],
        }
    if lineage.schema_version == DECISION_LINEAGE_SCHEMA:
        forecast_payload["data_eligibility"] = lineage.data_eligibility.value
    forecast_hash = _canonical_hash(forecast_payload)
    return replace(
        lineage,
        candidate_binding_hash=candidate_hash,
        signal_bundle_hash=signal_hash,
        forecast_bundle_hash=forecast_hash,
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
    schema_version: str = field(
        default=DAILY_DECISION_SUMMARY_SCHEMA,
        init=False,
    )

    def __post_init__(self) -> None:
        _schema(self.schema_version, DAILY_DECISION_SUMMARY_SCHEMA)
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
        if any(
            item.dynamic_pool_id != self.lineage.dynamic_pool_id
            or item.candidate_set_id != self.lineage.candidate_set_id
            or item.candidate_binding_id != self.lineage.candidate_binding_id
            for item in self.candidates
        ):
            raise ValueError("Summary Candidate/Pool binding lineage mismatch")
        if tuple(sorted((item.signal_id for item in self.candidates), key=str)) != self.lineage.signal_ids:
            raise ValueError("Summary Candidate/Signal lineage mismatch")
        if tuple(sorted((item.forecast_id for item in self.candidates), key=str)) != self.lineage.forecast_ids:
            raise ValueError("Summary Candidate/Forecast lineage mismatch")
        if any(
            item.signal_model_id not in self.lineage.model_ids
            or item.forecast_model_id not in self.lineage.model_ids
            for item in self.candidates
        ):
            raise ValueError("Summary Candidate/Model lineage mismatch")
        if any(
            item.signal_hash != decision_signal_evidence_hash(item)
            or item.forecast_hash != decision_forecast_evidence_hash(item)
            for item in self.candidates
        ):
            raise ValueError("Summary Signal/Forecast content hash mismatch")
        expected_lineage = bind_decision_candidate_evidence(
            self.lineage,
            self.candidates,
        )
        if expected_lineage != self.lineage:
            raise ValueError("Summary Candidate bundle content lineage mismatch")
        if any(item.valid_until < self.as_of_time for item in self.candidates):
            raise ValueError("Summary candidate expired before AsOfTime")
        terminal = self.lifecycle_state in {
            DecisionWindowState.FINALIZED,
            DecisionWindowState.BLOCKED,
            DecisionWindowState.CORRECTED,
        }
        if self.candidates and terminal != all(
            item.risk_result is not None for item in self.candidates
        ):
            raise ValueError("Summary terminal Risk result lineage mismatch")
        if self.lifecycle_state is DecisionWindowState.BLOCKED and self.outcome in {
            DailyDecisionOutcome.NO_ACTION,
            DailyDecisionOutcome.WATCH,
            DailyDecisionOutcome.RESEARCH_BUY_CANDIDATE,
        }:
            raise ValueError("Blocked Summary requires a blocking outcome")
        require_sha256("content_hash", self.content_hash)
        if _canonical_hash(self.semantic_payload()) != self.content_hash:
            raise ValueError("Daily Summary hash mismatch")
        _verify_id("daily-decision-summary", self.summary_id, self.content_hash)

    @classmethod
    def create(cls, **values: Any) -> DailyDecisionWindowSummary:
        normalized = dict(values)
        normalized["candidates"] = tuple(
            sorted(values["candidates"], key=lambda item: item.candidate_rank)
        )
        digest = _canonical_hash(_summary_payload(**normalized))
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
        _fields(
            payload,
            {
                "schema_version", "summary_id", "content_hash", "account_id",
                "trading_date", "strategy_configuration_id",
                "strategy_configuration_hash", "as_of_time", "available_at",
                "lifecycle_state", "outcome", "manual_observation_id",
                "reconciliation_id", "lineage", "candidates", "revision",
                "previous_summary_id", "correction_of_summary_id",
                "idempotency_key", "created_at",
            },
            "DailyDecisionWindowSummary",
        )
        _schema_value(payload, DAILY_DECISION_SUMMARY_SCHEMA)
        return cls(
            summary_id=ArtifactId(_string(payload["summary_id"])),
            content_hash=_string(payload["content_hash"]),
            account_id=_string(payload["account_id"]),
            trading_date=_date_value(payload["trading_date"]),
            strategy_configuration_id=ArtifactId(_string(payload["strategy_configuration_id"])),
            strategy_configuration_hash=_string(payload["strategy_configuration_hash"]),
            as_of_time=_instant(payload["as_of_time"]),
            available_at=_instant(payload["available_at"]),
            lifecycle_state=DecisionWindowState(_string(payload["lifecycle_state"])),
            outcome=DailyDecisionOutcome(_string(payload["outcome"])),
            manual_observation_id=ArtifactId(_string(payload["manual_observation_id"])),
            reconciliation_id=ArtifactId(_string(payload["reconciliation_id"])),
            lineage=DecisionLineage.from_canonical_dict(_mapping(payload["lineage"])),
            candidates=tuple(SummaryCandidate.from_canonical_dict(_mapping(item)) for item in _sequence(payload["candidates"])),
            revision=_int(payload["revision"]),
            previous_summary_id=_optional_id(payload["previous_summary_id"]),
            correction_of_summary_id=_optional_id(payload["correction_of_summary_id"]),
            idempotency_key=_string(payload["idempotency_key"]),
            created_at=_instant(payload["created_at"]),
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
    model_qualification: DecisionModelQualification
    orderability: DecisionOrderability
    schema_version: str = field(default=PORTFOLIO_PROPOSAL_LINE_SCHEMA, init=False)

    def __post_init__(self) -> None:
        _schema(self.schema_version, PORTFOLIO_PROPOSAL_LINE_SCHEMA)
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
            "schema_version": self.schema_version,
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
            "model_qualification": self.model_qualification.value,
            "orderability": self.orderability.value,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> PortfolioProposalLine:
        _fields(
            payload,
            {
                "schema_version", "symbol", "current_weight",
                "proposed_research_weight", "weight_delta", "research_amount",
                "theme_exposure", "single_symbol_exposure",
                "liquidity_constraint", "position_constraint", "reason_codes",
                "invalidation_conditions", "model_qualification", "orderability",
            },
            "PortfolioProposalLine",
        )
        _schema_value(payload, PORTFOLIO_PROPOSAL_LINE_SCHEMA)
        return cls(
            symbol=_string(payload["symbol"]),
            current_weight=_as_decimal(payload["current_weight"]),
            proposed_research_weight=_as_decimal(payload["proposed_research_weight"]),
            weight_delta=_as_decimal(payload["weight_delta"]),
            research_amount=_as_decimal(payload["research_amount"]),
            theme_exposure=_as_decimal(payload["theme_exposure"]),
            single_symbol_exposure=_as_decimal(payload["single_symbol_exposure"]),
            liquidity_constraint=_string(payload["liquidity_constraint"]),
            position_constraint=_string(payload["position_constraint"]),
            reason_codes=tuple(_string(item) for item in _sequence(payload["reason_codes"])),
            invalidation_conditions=tuple(_string(item) for item in _sequence(payload["invalidation_conditions"])),
            model_qualification=DecisionModelQualification(
                _string(payload["model_qualification"])
            ),
            orderability=DecisionOrderability(_string(payload["orderability"])),
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
    schema_version: str = field(
        default=RESEARCH_PORTFOLIO_PROPOSAL_SCHEMA,
        init=False,
    )

    def __post_init__(self) -> None:
        _schema(self.schema_version, RESEARCH_PORTFOLIO_PROPOSAL_SCHEMA)
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
        if _canonical_hash(self.semantic_payload()) != self.content_hash:
            raise ValueError("Portfolio Proposal hash mismatch")
        _verify_id("research-portfolio-proposal", self.proposal_id, self.content_hash)

    @classmethod
    def create(cls, **values: Any) -> ResearchPortfolioProposal:
        normalized = dict(values)
        normalized["lines"] = tuple(sorted(values["lines"], key=lambda item: item.symbol))
        normalized["reason_codes"] = tuple(sorted(set(values["reason_codes"])))
        digest = _canonical_hash(_proposal_payload(**normalized))
        return cls(proposal_id=_id("research-portfolio-proposal", digest), content_hash=digest, **normalized)

    def semantic_payload(self) -> dict[str, Any]:
        return _proposal_payload(**_dataclass_values(self, exclude={"proposal_id", "content_hash"}))

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"proposal_id": str(self.proposal_id), "content_hash": self.content_hash, **self.semantic_payload()}

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ResearchPortfolioProposal:
        _fields(
            payload,
            {
                "schema_version", "proposal_id", "content_hash", "account_id",
                "trading_date", "as_of_time", "summary_id",
                "manual_observation_id", "reconciliation_id",
                "risk_configuration_id", "risk_configuration_hash", "status",
                "lines", "reason_codes", "idempotency_key", "created_at",
            },
            "ResearchPortfolioProposal",
        )
        _schema_value(payload, RESEARCH_PORTFOLIO_PROPOSAL_SCHEMA)
        return cls(
            proposal_id=ArtifactId(_string(payload["proposal_id"])),
            content_hash=_string(payload["content_hash"]),
            account_id=_string(payload["account_id"]),
            trading_date=_date_value(payload["trading_date"]),
            as_of_time=_instant(payload["as_of_time"]),
            summary_id=ArtifactId(_string(payload["summary_id"])),
            manual_observation_id=ArtifactId(_string(payload["manual_observation_id"])),
            reconciliation_id=ArtifactId(_string(payload["reconciliation_id"])),
            risk_configuration_id=ArtifactId(_string(payload["risk_configuration_id"])),
            risk_configuration_hash=_string(payload["risk_configuration_hash"]),
            status=ProposalStatus(_string(payload["status"])),
            lines=tuple(PortfolioProposalLine.from_canonical_dict(_mapping(item)) for item in _sequence(payload["lines"])),
            reason_codes=tuple(_string(item) for item in _sequence(payload["reason_codes"])),
            idempotency_key=_string(payload["idempotency_key"]),
            created_at=_instant(payload["created_at"]),
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
    schema_version: str = field(
        default=DECISION_RISK_CONFIGURATION_SCHEMA,
        init=False,
    )

    def __post_init__(self) -> None:
        _schema(self.schema_version, DECISION_RISK_CONFIGURATION_SCHEMA)
        require_sha256("configuration_hash", self.configuration_hash)
        _positive_integer("maximum_observation_age_seconds", self.maximum_observation_age_seconds)
        _positive_integer("maximum_data_age_seconds", self.maximum_data_age_seconds)
        for label in ("maximum_single_symbol_weight", "maximum_theme_weight", "minimum_liquidity"):
            _decimal_ratio(label, getattr(self, label))
        if self.daily_loss_limit is not None:
            _decimal("daily_loss_limit", self.daily_loss_limit)
        expected = _canonical_hash(self.semantic_payload())
        if expected != self.configuration_hash:
            raise ValueError("Decision Risk Configuration hash mismatch")
        _verify_id("decision-risk-configuration", self.configuration_id, expected)

    @classmethod
    def create(
        cls,
        *,
        maximum_observation_age_seconds: int,
        maximum_data_age_seconds: int,
        maximum_single_symbol_weight: Decimal,
        maximum_theme_weight: Decimal,
        minimum_liquidity: Decimal,
        daily_loss_limit: Decimal | None,
    ) -> DecisionRiskConfiguration:
        payload = _decision_risk_configuration_payload(
            maximum_observation_age_seconds=maximum_observation_age_seconds,
            maximum_data_age_seconds=maximum_data_age_seconds,
            maximum_single_symbol_weight=maximum_single_symbol_weight,
            maximum_theme_weight=maximum_theme_weight,
            minimum_liquidity=minimum_liquidity,
            daily_loss_limit=daily_loss_limit,
        )
        digest = _canonical_hash(payload)
        return cls(
            configuration_id=_id("decision-risk-configuration", digest),
            configuration_hash=digest,
            maximum_observation_age_seconds=maximum_observation_age_seconds,
            maximum_data_age_seconds=maximum_data_age_seconds,
            maximum_single_symbol_weight=maximum_single_symbol_weight,
            maximum_theme_weight=maximum_theme_weight,
            minimum_liquidity=minimum_liquidity,
            daily_loss_limit=daily_loss_limit,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _decision_risk_configuration_payload(
            maximum_observation_age_seconds=self.maximum_observation_age_seconds,
            maximum_data_age_seconds=self.maximum_data_age_seconds,
            maximum_single_symbol_weight=self.maximum_single_symbol_weight,
            maximum_theme_weight=self.maximum_theme_weight,
            minimum_liquidity=self.minimum_liquidity,
            daily_loss_limit=self.daily_loss_limit,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
            "maximum_observation_age_seconds": self.maximum_observation_age_seconds,
            "maximum_data_age_seconds": self.maximum_data_age_seconds,
            "maximum_single_symbol_weight": _decimal_text(self.maximum_single_symbol_weight),
            "maximum_theme_weight": _decimal_text(self.maximum_theme_weight),
            "minimum_liquidity": _decimal_text(self.minimum_liquidity),
            "daily_loss_limit": _decimal_text(self.daily_loss_limit),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> DecisionRiskConfiguration:
        _fields(
            payload,
            {
                "schema_version", "configuration_id", "configuration_hash",
                "maximum_observation_age_seconds", "maximum_data_age_seconds",
                "maximum_single_symbol_weight", "maximum_theme_weight",
                "minimum_liquidity", "daily_loss_limit",
            },
            "DecisionRiskConfiguration",
        )
        _schema_value(payload, DECISION_RISK_CONFIGURATION_SCHEMA)
        return cls(
            configuration_id=ArtifactId(_string(payload["configuration_id"])),
            configuration_hash=_string(payload["configuration_hash"]),
            maximum_observation_age_seconds=_int(
                payload["maximum_observation_age_seconds"]
            ),
            maximum_data_age_seconds=_int(payload["maximum_data_age_seconds"]),
            maximum_single_symbol_weight=_as_decimal(
                payload["maximum_single_symbol_weight"]
            ),
            maximum_theme_weight=_as_decimal(payload["maximum_theme_weight"]),
            minimum_liquidity=_as_decimal(payload["minimum_liquidity"]),
            daily_loss_limit=_optional_decimal(payload["daily_loss_limit"]),
        )


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
    schema_version: str = field(
        default=INDEPENDENT_RISK_DECISION_SCHEMA,
        init=False,
    )

    def __post_init__(self) -> None:
        _schema(self.schema_version, INDEPENDENT_RISK_DECISION_SCHEMA)
        _aware("as_of_time", self.as_of_time)
        _aware("created_at", self.created_at)
        _decimal_ratio("approved_research_weight", self.approved_research_weight)
        _sorted_unique_text("reason_codes", self.reason_codes)
        require_sha256("risk_configuration_hash", self.risk_configuration_hash)
        require_sha256("content_hash", self.content_hash)
        if _canonical_hash(self.semantic_payload()) != self.content_hash:
            raise ValueError("Independent Risk Decision hash mismatch")
        _verify_id("independent-risk-decision", self.risk_decision_id, self.content_hash)

    @classmethod
    def create(cls, **values: Any) -> IndependentRiskDecision:
        normalized = dict(values)
        normalized["reason_codes"] = tuple(sorted(set(values["reason_codes"])))
        digest = _canonical_hash(_risk_payload(**normalized))
        return cls(risk_decision_id=_id("independent-risk-decision", digest), content_hash=digest, **normalized)

    def semantic_payload(self) -> dict[str, Any]:
        return _risk_payload(**_dataclass_values(self, exclude={"risk_decision_id", "content_hash"}))

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"risk_decision_id": str(self.risk_decision_id), "content_hash": self.content_hash, **self.semantic_payload()}

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> IndependentRiskDecision:
        _fields(
            payload,
            {
                "schema_version", "risk_decision_id", "content_hash",
                "proposal_id", "account_id", "trading_date", "as_of_time",
                "result", "approved_research_weight", "reason_codes",
                "risk_configuration_id", "risk_configuration_hash",
                "idempotency_key", "created_at",
            },
            "IndependentRiskDecision",
        )
        _schema_value(payload, INDEPENDENT_RISK_DECISION_SCHEMA)
        return cls(
            risk_decision_id=ArtifactId(_string(payload["risk_decision_id"])),
            content_hash=_string(payload["content_hash"]),
            proposal_id=ArtifactId(_string(payload["proposal_id"])),
            account_id=_string(payload["account_id"]),
            trading_date=_date_value(payload["trading_date"]),
            as_of_time=_instant(payload["as_of_time"]),
            result=IndependentRiskResult(_string(payload["result"])),
            approved_research_weight=_as_decimal(payload["approved_research_weight"]),
            reason_codes=tuple(_string(item) for item in _sequence(payload["reason_codes"])),
            risk_configuration_id=ArtifactId(_string(payload["risk_configuration_id"])),
            risk_configuration_hash=_string(payload["risk_configuration_hash"]),
            idempotency_key=_string(payload["idempotency_key"]),
            created_at=_instant(payload["created_at"]),
        )


def _account_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": MANUAL_ACCOUNT_OBSERVATION_SCHEMA,
        "account_id": values["account_id"],
        "trading_date": values["trading_date"].isoformat(),
        "as_of_time": canonical_datetime(values["as_of_time"]),
        "total_equity": _decimal_text(values["total_equity"]),
        "available_cash": _decimal_text(values["available_cash"]),
        "frozen_cash": _decimal_text(values["frozen_cash"]),
        "source": values["source"], "actor": values["actor"],
        "reason": values["reason"], "notes": values["notes"],
        "idempotency_key": values["idempotency_key"],
        "revision": values["revision"],
        "previous_observation_id": _id_text(values["previous_observation_id"]),
        "positions": [item.to_canonical_dict() for item in values["positions"]],
        "created_at": canonical_datetime(values["created_at"]),
    }


def _reconciliation_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": ACCOUNT_RECONCILIATION_SCHEMA,
        "account_id": values["account_id"],
        "trading_date": values["trading_date"].isoformat(),
        "as_of_time": canonical_datetime(values["as_of_time"]),
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
        "created_at": canonical_datetime(values["created_at"]),
    }


def _summary_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": DAILY_DECISION_SUMMARY_SCHEMA,
        "account_id": values["account_id"],
        "trading_date": values["trading_date"].isoformat(),
        "strategy_configuration_id": str(values["strategy_configuration_id"]),
        "strategy_configuration_hash": values["strategy_configuration_hash"],
        "as_of_time": canonical_datetime(values["as_of_time"]),
        "available_at": canonical_datetime(values["available_at"]),
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
        "created_at": canonical_datetime(values["created_at"]),
    }


def _proposal_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": RESEARCH_PORTFOLIO_PROPOSAL_SCHEMA,
        "account_id": values["account_id"],
        "trading_date": values["trading_date"].isoformat(),
        "as_of_time": canonical_datetime(values["as_of_time"]),
        "summary_id": str(values["summary_id"]),
        "manual_observation_id": str(values["manual_observation_id"]),
        "reconciliation_id": str(values["reconciliation_id"]),
        "risk_configuration_id": str(values["risk_configuration_id"]),
        "risk_configuration_hash": values["risk_configuration_hash"],
        "status": values["status"].value,
        "lines": [item.to_canonical_dict() for item in values["lines"]],
        "reason_codes": list(values["reason_codes"]),
        "idempotency_key": values["idempotency_key"],
        "created_at": canonical_datetime(values["created_at"]),
    }


def _risk_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": INDEPENDENT_RISK_DECISION_SCHEMA,
        "proposal_id": str(values["proposal_id"]),
        "account_id": values["account_id"],
        "trading_date": values["trading_date"].isoformat(),
        "as_of_time": canonical_datetime(values["as_of_time"]),
        "result": values["result"].value,
        "approved_research_weight": _decimal_text(values["approved_research_weight"]),
        "reason_codes": list(values["reason_codes"]),
        "risk_configuration_id": str(values["risk_configuration_id"]),
        "risk_configuration_hash": values["risk_configuration_hash"],
        "idempotency_key": values["idempotency_key"],
        "created_at": canonical_datetime(values["created_at"]),
    }


def _reconciliation_tolerance_payload(
    *,
    equity_tolerance: Decimal,
    cash_tolerance: Decimal,
    average_cost_tolerance: Decimal,
) -> dict[str, Any]:
    return {
        "schema_version": RECONCILIATION_TOLERANCE_SCHEMA,
        "equity_tolerance": _decimal_text(equity_tolerance),
        "cash_tolerance": _decimal_text(cash_tolerance),
        "average_cost_tolerance": _decimal_text(average_cost_tolerance),
    }


def _decision_risk_configuration_payload(
    *,
    maximum_observation_age_seconds: int,
    maximum_data_age_seconds: int,
    maximum_single_symbol_weight: Decimal,
    maximum_theme_weight: Decimal,
    minimum_liquidity: Decimal,
    daily_loss_limit: Decimal | None,
) -> dict[str, Any]:
    return {
        "schema_version": DECISION_RISK_CONFIGURATION_SCHEMA,
        "maximum_observation_age_seconds": maximum_observation_age_seconds,
        "maximum_data_age_seconds": maximum_data_age_seconds,
        "maximum_single_symbol_weight": _decimal_text(
            maximum_single_symbol_weight
        ),
        "maximum_theme_weight": _decimal_text(maximum_theme_weight),
        "minimum_liquidity": _decimal_text(minimum_liquidity),
        "daily_loss_limit": _decimal_text(daily_loss_limit),
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
    return parse_canonical_decimal("Decision decimal", value)


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else _as_decimal(value)


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else canonical_decimal(value)


def _aware(label: str, value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    if value.microsecond != 0:
        raise ValueError(f"{label} must use whole-second precision")


def _text(label: str, value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty trimmed text")
    if value != unicodedata.normalize("NFC", value):
        raise ValueError(f"{label} must use Unicode NFC")


def _positive_integer(label: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")


def _nonnegative_integer(label: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")


def _sorted_unique_text(label: str, values: tuple[str, ...]) -> None:
    if values != tuple(sorted(set(values))) or any(
        not item
        or item != item.strip()
        or item != unicodedata.normalize("NFC", item)
        for item in values
    ):
        raise ValueError(f"{label} must be sorted, unique and non-empty")


def _id(prefix: str, digest: str) -> ArtifactId:
    return ArtifactId(f"{prefix}-{digest.split(':', 1)[1][:24]}")


def _verify_id(prefix: str, value: ArtifactId, digest: str) -> None:
    if value != _id(prefix, digest):
        raise ValueError(f"{prefix} identity mismatch")


def _id_text(value: ArtifactId | None) -> str | None:
    return None if value is None else str(value)


def _optional_id(value: object) -> ArtifactId | None:
    return None if value is None else ArtifactId(_string(value))


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
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("expected integer")
    return value


def _optional_int(value: object) -> int | None:
    return None if value is None else _int(value)


def _bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("expected boolean")
    return value


def _string(value: object, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError("expected string")
    if not allow_empty and not value:
        raise ValueError("expected non-empty string")
    if value != unicodedata.normalize("NFC", value):
        raise ValueError("string is not Unicode NFC")
    return value


def _instant(value: object) -> datetime:
    raw = _string(value)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("expected canonical datetime") from exc
    if canonical_datetime(parsed) != raw:
        raise ValueError("expected canonical UTC-second datetime")
    return parsed


def _date_value(value: object) -> date:
    raw = _string(value)
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("expected canonical date") from exc
    if parsed.isoformat() != raw:
        raise ValueError("expected canonical date")
    return parsed


def _schema(actual: str, expected: str) -> None:
    if actual != expected:
        raise ValueError(f"unsupported schema version: {actual}")


def _schema_value(payload: Mapping[str, Any], expected: str) -> None:
    _schema(_string(payload["schema_version"]), expected)


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    normalized = _normalize_canonical_value(payload)
    if not isinstance(normalized, dict):
        raise TypeError("canonical payload must be an object")
    if normalized != payload:
        raise ValueError("canonical payload strings must use Unicode NFC")
    return canonical_hash(normalized)


def _normalize_canonical_value(value: object) -> object:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Mapping):
        return {
            unicodedata.normalize("NFC", _string(key)): _normalize_canonical_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_canonical_value(item) for item in value]
    return value


def _dataclass_values(value: object, *, exclude: set[str]) -> dict[str, Any]:
    return {
        name: getattr(value, name)
        for name in value.__dataclass_fields__  # type: ignore[attr-defined]
        if name not in exclude
    }


__all__ = [
    "AccountReconciliationReport", "DailyDecisionOutcome",
    "DailyDecisionWindowSummary", "DecisionForecastBias", "DecisionLineage",
    "DecisionModelQualification", "DecisionOrderability",
    "DecisionRiskConfiguration", "DecisionSignalState", "DecisionWindowState",
    "FillDerivedPositionReference", "IndependentRiskDecision",
    "IndependentRiskResult", "ManualAccountObservation", "ManualPositionObservation",
    "PortfolioProposalLine", "ProposalStatus", "ReconciliationDifference",
    "ReconciliationDifferenceType", "ReconciliationStatus",
    "ReconciliationTolerance", "ResearchPortfolioProposal", "SummaryCandidate",
    "bind_decision_candidate_evidence", "decision_forecast_evidence_hash",
    "decision_signal_evidence_hash",
]
