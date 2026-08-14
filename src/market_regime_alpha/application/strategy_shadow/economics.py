"""Target-bound A-share Strategy Economics V1 research kernel."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.application.controlled_operation.prospective_outcome import (
    OutcomeAvailabilityStatus,
    OutcomeMarketCondition,
)
from market_regime_alpha.application.research_evaluation.targeted_outcome import (
    BarrierOrderingOutcome,
    TargetOutcomeLabel,
)
from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeCheckpoint,
    TargetDefinition,
)
from market_regime_alpha.application.research_validation.common import (
    ENGINEERING_LIMITATIONS,
    ResearchEvidenceAuthority,
    ValidationArtifactReference,
    content_identity,
    decimal_text,
    timestamp,
)
from market_regime_alpha.application.research_validation.liquidity_capacity import (
    LiquidityCapacityAssessment,
)
from market_regime_alpha.application.strategy_shadow.portfolio import (
    ShadowParameterProvenance,
    ShadowPortfolioParameter,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_sha256,
    require_text,
)


class StrategyEntryKind(str, Enum):
    FROZEN_DECISION_REFERENCE = "FROZEN_DECISION_REFERENCE"


class StrategyExitKind(str, Enum):
    FIXED_TIME = "FIXED_TIME"
    BARRIER = "BARRIER"
    FORECAST_AWARE = "FORECAST_AWARE"


class StrategyEconomicsStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    NO_ENTRY = "NO_ENTRY"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


class StrategyExecutionPhase(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


@dataclass(frozen=True, slots=True)
class StrategyExecutionObservation:
    """Side-aware execution evidence; the Target label owns the holding path."""

    phase: StrategyExecutionPhase
    symbol: str
    price: Decimal | None
    market_conditions: tuple[OutcomeMarketCondition, ...]
    effective_at: datetime
    available_at: datetime
    source_reference: ValidationArtifactReference

    def __post_init__(self) -> None:
        require_text("Strategy execution symbol", self.symbol)
        if self.price is not None and self.price <= 0:
            raise ValueError("Strategy execution price must be positive")
        if self.market_conditions != tuple(
            sorted(set(self.market_conditions), key=lambda item: item.value)
        ):
            raise ValueError(
                "Strategy execution market conditions must be unique and sorted"
            )
        if self.available_at < self.effective_at:
            raise ValueError("Strategy execution availability predates observation")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "symbol": self.symbol,
            "price": decimal_text(self.price),
            "market_conditions": [item.value for item in self.market_conditions],
            "effective_at": timestamp(self.effective_at),
            "available_at": timestamp(self.available_at),
            "source_reference": self.source_reference.to_canonical_dict(),
        }


_REQUIRED_COST_PARAMETERS = frozenset(
    {"commission_bps", "stamp_duty_bps", "spread_slippage_bps"}
)


@dataclass(frozen=True, slots=True)
class StrategyEconomicsPolicy:
    policy_id: ArtifactId
    policy_hash: str
    policy_version: str
    prediction_target_reference: ValidationArtifactReference
    prediction_checkpoint: OutcomeCheckpoint
    entry_kind: StrategyEntryKind
    exit_kind: StrategyExitKind
    fixed_exit_checkpoint: OutcomeCheckpoint
    barrier_id: str | None
    barrier_return: Decimal | None
    forecast_raw_score_threshold: Decimal | None
    lot_size: int
    t_plus_one: bool
    parameters: tuple[ShadowPortfolioParameter, ...]
    created_at: datetime
    limitations: tuple[str, ...]
    schema_version: str = "strategy-economics-policy/v1"

    def __post_init__(self) -> None:
        require_sha256("policy_hash", self.policy_hash)
        if self.lot_size != 100 or not self.t_plus_one:
            raise ValueError("Strategy Economics must enforce A-share lot size and T+1")
        if {item.name for item in self.parameters} != _REQUIRED_COST_PARAMETERS:
            raise ValueError("Strategy Economics cost parameter set mismatch")
        if self.parameters != tuple(sorted(self.parameters, key=lambda item: item.name)):
            raise ValueError("Strategy Economics parameters must be sorted")
        if self.exit_kind is StrategyExitKind.BARRIER:
            if self.barrier_id is None or self.barrier_return is None:
                raise ValueError("Barrier exit must bind one Target barrier")
        elif self.barrier_id is not None or self.barrier_return is not None:
            raise ValueError("Non-barrier exit cannot bind a Target barrier")
        if (self.exit_kind is StrategyExitKind.FORECAST_AWARE) != (
            self.forecast_raw_score_threshold is not None
        ):
            raise ValueError("Forecast-aware exit requires one raw-score threshold")
        if canonical_hash(self.identity_payload()) != self.policy_hash:
            raise ValueError("Strategy Economics Policy hash mismatch")

    @classmethod
    def create(
        cls,
        *,
        policy_version: str,
        prediction_target: TargetDefinition,
        entry_kind: StrategyEntryKind,
        exit_kind: StrategyExitKind,
        fixed_exit_checkpoint: OutcomeCheckpoint,
        barrier_id: str | None,
        forecast_raw_score_threshold: Decimal | None,
        lot_size: int,
        t_plus_one: bool,
        parameters: Mapping[
            str, tuple[Decimal, ShadowParameterProvenance]
        ],
        created_at: datetime,
    ) -> StrategyEconomicsPolicy:
        require_text("policy_version", policy_version)
        if prediction_target.schema_version != "outcome_target_definition/v2":
            raise ValueError("Strategy Economics requires TargetDefinition V2")
        if prediction_target.canonical_horizon.session_offset != 1:
            raise ValueError("Strategy Economics V1 requires a T+1 prediction target")
        if fixed_exit_checkpoint != prediction_target.checkpoint:
            raise ValueError(
                "Strategy fixed exit checkpoint must bind the prediction Target checkpoint"
            )
        if set(parameters) != _REQUIRED_COST_PARAMETERS:
            raise ValueError("Strategy Economics requires exact cost assumptions")
        ordered = tuple(
            ShadowPortfolioParameter(name, value, provenance)
            for name, (value, provenance) in sorted(parameters.items())
        )
        barrier_return: Decimal | None = None
        if exit_kind is StrategyExitKind.BARRIER:
            matched = tuple(
                item
                for item in prediction_target.barriers
                if item.barrier_id == barrier_id
            )
            if len(matched) != 1:
                raise ValueError("Strategy barrier must exist in TargetDefinition V2")
            barrier_return = matched[0].return_threshold * (
                Decimal("1") if matched[0].direction == "UP" else Decimal("-1")
            )
        target_reference = ValidationArtifactReference(
            "OUTCOME_TARGET_DEFINITION",
            prediction_target.target_id,
            prediction_target.target_hash,
        )
        limitations = tuple(
            sorted(
                {
                    *ENGINEERING_LIMITATIONS,
                    "EXPLORATORY_NOT_FORMAL_ALPHA_EVIDENCE",
                    "COST_ASSUMPTIONS_NOT_EMPIRICALLY_CALIBRATED",
                    "PREDICTION_HORIZON_NOT_AUTOMATIC_HOLDING_POLICY",
                    "NOT_REAL_FILL",
                    "NO_BROKER",
                }
            )
        )
        values = _policy_payload(
            policy_version,
            target_reference,
            prediction_target.checkpoint,
            entry_kind,
            exit_kind,
            fixed_exit_checkpoint,
            barrier_id,
            barrier_return,
            forecast_raw_score_threshold,
            lot_size,
            t_plus_one,
            ordered,
            created_at,
            limitations,
        )
        policy_id, digest = content_identity("strategy-economics-policy", values)
        return cls(
            policy_id,
            digest,
            policy_version,
            target_reference,
            prediction_target.checkpoint,
            entry_kind,
            exit_kind,
            fixed_exit_checkpoint,
            barrier_id,
            barrier_return,
            forecast_raw_score_threshold,
            lot_size,
            t_plus_one,
            ordered,
            created_at,
            limitations,
        )

    def parameter(self, name: str) -> Decimal:
        return next(item.value for item in self.parameters if item.name == name)

    def identity_payload(self) -> dict[str, Any]:
        return _policy_payload(
            self.policy_version,
            self.prediction_target_reference,
            self.prediction_checkpoint,
            self.entry_kind,
            self.exit_kind,
            self.fixed_exit_checkpoint,
            self.barrier_id,
            self.barrier_return,
            self.forecast_raw_score_threshold,
            self.lot_size,
            self.t_plus_one,
            self.parameters,
            self.created_at,
            self.limitations,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "policy_id": str(self.policy_id),
            "policy_hash": self.policy_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, value: Mapping[str, Any]
    ) -> StrategyEconomicsPolicy:
        holding = value.get("holding_exit_policy")
        parameters = value.get("parameters")
        limitations = value.get("limitations")
        if not isinstance(holding, Mapping):
            raise ValueError("Strategy Economics holding/exit policy is malformed")
        if not isinstance(parameters, (list, tuple)):
            raise ValueError("Strategy Economics parameters are malformed")
        if not isinstance(limitations, (list, tuple)):
            raise ValueError("Strategy Economics limitations are malformed")
        return cls(
            policy_id=ArtifactId(str(value["policy_id"])),
            policy_hash=str(value["policy_hash"]),
            policy_version=str(value["policy_version"]),
            prediction_target_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["prediction_target_reference"])
            ),
            prediction_checkpoint=OutcomeCheckpoint(
                str(value["prediction_checkpoint"])
            ),
            entry_kind=StrategyEntryKind(str(value["entry_kind"])),
            exit_kind=StrategyExitKind(str(value["exit_kind"])),
            fixed_exit_checkpoint=OutcomeCheckpoint(
                str(holding["fixed_exit_checkpoint"])
            ),
            barrier_id=(
                None if holding.get("barrier_id") is None else str(holding["barrier_id"])
            ),
            barrier_return=_optional_decimal(holding.get("barrier_return")),
            forecast_raw_score_threshold=_optional_decimal(
                holding.get("forecast_raw_score_threshold")
            ),
            lot_size=int(value["lot_size"]),
            t_plus_one=bool(value["t_plus_one"]),
            parameters=tuple(
                ShadowPortfolioParameter(
                    name=str(_mapping(item)["name"]),
                    value=Decimal(str(_mapping(item)["value"])),
                    provenance=ShadowParameterProvenance(
                        str(_mapping(item)["provenance"])
                    ),
                )
                for item in parameters
            ),
            created_at=datetime.fromisoformat(str(value["created_at"])),
            limitations=tuple(str(item) for item in limitations),
            schema_version=str(value["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class StrategyEconomicsResult:
    result_id: ArtifactId
    result_hash: str
    policy_reference: ValidationArtifactReference
    target_label_reference: ValidationArtifactReference
    liquidity_reference: ValidationArtifactReference
    entry_execution_reference: ValidationArtifactReference
    exit_execution_reference: ValidationArtifactReference
    symbol: str
    status: StrategyEconomicsStatus
    requested_notional: Decimal
    capacity_ceiling: Decimal | None
    filled_quantity: Decimal
    entry_price: Decimal | None
    exit_price: Decimal | None
    gross_return: Decimal | None
    cost_return: Decimal | None
    net_return: Decimal | None
    turnover: Decimal
    mfe: Decimal | None
    mae: Decimal | None
    reason_codes: tuple[str, ...]
    evaluated_at: datetime
    authority: ResearchEvidenceAuthority
    limitations: tuple[str, ...]
    schema_version: str = "strategy-economics-result/v1"

    def __post_init__(self) -> None:
        require_sha256("result_hash", self.result_hash)
        if self.authority is not ResearchEvidenceAuthority.EXPLORATORY:
            raise ValueError("Strategy Economics result is exploratory only")
        if self.status is StrategyEconomicsStatus.AVAILABLE and any(
            item is None
            for item in (
                self.entry_price,
                self.exit_price,
                self.gross_return,
                self.cost_return,
                self.net_return,
            )
        ):
            raise ValueError("Available Strategy Economics requires complete economics")
        if self.status is not StrategyEconomicsStatus.AVAILABLE and any(
            item is not None
            for item in (self.gross_return, self.cost_return, self.net_return)
        ):
            raise ValueError("Unavailable Strategy Economics cannot contain returns")
        if canonical_hash(self.identity_payload()) != self.result_hash:
            raise ValueError("Strategy Economics Result hash mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return _result_payload(
            self.policy_reference,
            self.target_label_reference,
            self.liquidity_reference,
            self.entry_execution_reference,
            self.exit_execution_reference,
            self.symbol,
            self.status,
            self.requested_notional,
            self.capacity_ceiling,
            self.filled_quantity,
            self.entry_price,
            self.exit_price,
            self.gross_return,
            self.cost_return,
            self.net_return,
            self.turnover,
            self.mfe,
            self.mae,
            self.reason_codes,
            self.evaluated_at,
            self.limitations,
        )


def evaluate_strategy_economics(
    *,
    policy: StrategyEconomicsPolicy,
    label: TargetOutcomeLabel,
    liquidity: LiquidityCapacityAssessment,
    entry_execution: StrategyExecutionObservation,
    exit_execution: StrategyExecutionObservation,
    requested_notional: Decimal,
    evaluated_at: datetime,
    forecast_raw_score: Decimal | None = None,
) -> StrategyEconomicsResult:
    if requested_notional <= 0:
        raise ValueError("Strategy Economics requested notional must be positive")
    if (
        label.target.artifact_id != policy.prediction_target_reference.artifact_id
        or label.target.content_hash
        != policy.prediction_target_reference.content_hash
    ):
        raise ValueError("Strategy/Outcome TargetDefinition identity mismatch")
    if liquidity.symbol != label.symbol:
        raise ValueError("Strategy Liquidity assessment symbol mismatch")
    if (
        entry_execution.phase is not StrategyExecutionPhase.ENTRY
        or exit_execution.phase is not StrategyExecutionPhase.EXIT
        or entry_execution.symbol != label.symbol
        or exit_execution.symbol != label.symbol
    ):
        raise ValueError("Strategy execution phase/symbol lineage mismatch")
    if entry_execution.effective_at >= exit_execution.effective_at:
        raise ValueError("Strategy Entry must precede Exit execution evidence")
    if entry_execution.effective_at > label.label_interval_start:
        raise ValueError("Strategy Entry occurs after the holding path starts")
    if exit_execution.effective_at < label.label_interval_end:
        raise ValueError("Strategy Exit precedes the intended checkpoint")
    if evaluated_at < max(
        label.outcome_available_at,
        liquidity.created_at,
        entry_execution.available_at,
        exit_execution.available_at,
    ):
        raise ValueError("Strategy Economics cannot precede required input availability")
    reasons: set[str] = set(label.reason_codes)
    unavailable_conditions = {
        OutcomeMarketCondition.SUSPENDED,
        OutcomeMarketCondition.MISSING_QUOTE,
        OutcomeMarketCondition.UNAVAILABLE,
        OutcomeMarketCondition.NON_TRADING_DAY,
        OutcomeMarketCondition.CORPORATE_ACTION,
    }
    entry_conditions = set(entry_execution.market_conditions)
    exit_conditions = set(exit_execution.market_conditions)
    if (
        entry_execution.price is None
        or bool(entry_conditions & unavailable_conditions)
        or OutcomeMarketCondition.LIMIT_UP in entry_conditions
    ):
        reasons.add("ENTRY_MARKET_CONDITION_NOT_FILLABLE")
    if (
        exit_execution.price is None
        or bool(exit_conditions & unavailable_conditions)
        or OutcomeMarketCondition.LIMIT_DOWN in exit_conditions
    ):
        reasons.add("EXIT_MARKET_CONDITION_NOT_FILLABLE")
    if liquidity.fillability <= 0:
        reasons.add("LIQUIDITY_FILLABILITY_ZERO")
    if label.availability_status is OutcomeAvailabilityStatus.UNAVAILABLE:
        reasons.add("TARGET_OUTCOME_UNAVAILABLE")
    if label.checkpoint_price is None or exit_execution.price is None:
        reasons.add("EXIT_PRICE_NOT_ESTIMABLE")
    if (
        policy.exit_kind is StrategyExitKind.BARRIER
        and label.barrier_ordering
        is BarrierOrderingOutcome.AMBIGUOUS_NOT_OBSERVABLE
    ):
        reasons.add("BARRIER_ORDERING_NOT_OBSERVABLE")
    if policy.exit_kind is StrategyExitKind.FORECAST_AWARE:
        if forecast_raw_score is None:
            reasons.add("FORECAST_RAW_SCORE_MISSING")
        elif forecast_raw_score < (policy.forecast_raw_score_threshold or Decimal("0")):
            reasons.add("FORECAST_RAW_SCORE_BELOW_ENTRY_THRESHOLD")
            return _make_result(
                policy,
                label,
                liquidity,
                entry_execution,
                exit_execution,
                StrategyEconomicsStatus.NO_ENTRY,
                requested_notional,
                Decimal("0"),
                None,
                None,
                None,
                None,
                None,
                Decimal("0"),
                tuple(sorted(reasons)),
                evaluated_at,
            )
    if reasons & {
        "ENTRY_MARKET_CONDITION_NOT_FILLABLE",
        "LIQUIDITY_FILLABILITY_ZERO",
    }:
        return _make_result(
            policy,
            label,
            liquidity,
            entry_execution,
            exit_execution,
            StrategyEconomicsStatus.NO_ENTRY,
            requested_notional,
            Decimal("0"),
            None,
            None,
            None,
            None,
            None,
            Decimal("0"),
            tuple(sorted(reasons)),
            evaluated_at,
        )
    entry_price = entry_execution.price
    assert entry_price is not None
    executable_notional = min(
        requested_notional,
        liquidity.capacity_ceiling or requested_notional,
        requested_notional * liquidity.fillability,
    )
    filled_quantity = (
        executable_notional / entry_price / Decimal(policy.lot_size)
    ).to_integral_value(rounding=ROUND_DOWN) * Decimal(policy.lot_size)
    if filled_quantity == 0:
        reasons.add("ZERO_EXECUTABLE_ROUND_LOT")
        return _make_result(
            policy,
            label,
            liquidity,
            entry_execution,
            exit_execution,
            StrategyEconomicsStatus.NO_ENTRY,
            requested_notional,
            Decimal("0"),
            None,
            None,
            None,
            None,
            None,
            Decimal("0"),
            tuple(sorted(reasons)),
            evaluated_at,
        )
    if reasons & {
        "TARGET_OUTCOME_UNAVAILABLE",
        "EXIT_PRICE_NOT_ESTIMABLE",
        "EXIT_MARKET_CONDITION_NOT_FILLABLE",
        "BARRIER_ORDERING_NOT_OBSERVABLE",
        "FORECAST_RAW_SCORE_MISSING",
    }:
        return _make_result(
            policy,
            label,
            liquidity,
            entry_execution,
            exit_execution,
            StrategyEconomicsStatus.NOT_ESTIMABLE,
            requested_notional,
            filled_quantity,
            entry_price,
            None,
            None,
            None,
            None,
            Decimal("1"),
            tuple(sorted(reasons)),
            evaluated_at,
        )
    exit_price = exit_execution.price
    gross_return = label.checkpoint_return
    if policy.exit_kind is StrategyExitKind.BARRIER:
        assert policy.barrier_return is not None
        selected_passage = next(
            at for barrier_id, at in label.barrier_passages
            if barrier_id == policy.barrier_id
        )
        if selected_passage is not None:
            gross_return = policy.barrier_return
            exit_price = entry_price * (Decimal("1") + gross_return)
            if exit_execution.price != exit_price:
                raise ValueError(
                    "Strategy barrier Exit price diverges from execution owner"
                )
        else:
            reasons.add("SELECTED_BARRIER_NOT_TOUCHED_FIXED_TIME_FALLBACK")
    assert gross_return is not None and exit_price is not None
    if (
        policy.exit_kind is not StrategyExitKind.BARRIER
        and exit_execution.price != label.checkpoint_price
    ):
        raise ValueError("Strategy Exit price diverges from Target checkpoint owner")
    impact_bps = liquidity.estimated_market_impact_bps or Decimal("0")
    round_trip_bps = (
        policy.parameter("commission_bps") * Decimal("2")
        + policy.parameter("stamp_duty_bps")
        + policy.parameter("spread_slippage_bps") * Decimal("2")
        + impact_bps * Decimal("2")
    )
    cost_return = round_trip_bps / Decimal("10000")
    return _make_result(
        policy,
        label,
        liquidity,
        entry_execution,
        exit_execution,
        StrategyEconomicsStatus.AVAILABLE,
        requested_notional,
        filled_quantity,
        entry_price,
        exit_price,
        gross_return,
        cost_return,
        gross_return - cost_return,
        Decimal("2"),
        tuple(sorted(reasons or {"ECONOMICS_AVAILABLE"})),
        evaluated_at,
    )


def _make_result(
    policy: StrategyEconomicsPolicy,
    label: TargetOutcomeLabel,
    liquidity: LiquidityCapacityAssessment,
    entry_execution: StrategyExecutionObservation,
    exit_execution: StrategyExecutionObservation,
    status: StrategyEconomicsStatus,
    requested_notional: Decimal,
    filled_quantity: Decimal,
    entry_price: Decimal | None,
    exit_price: Decimal | None,
    gross_return: Decimal | None,
    cost_return: Decimal | None,
    net_return: Decimal | None,
    turnover: Decimal,
    reason_codes: tuple[str, ...],
    evaluated_at: datetime,
) -> StrategyEconomicsResult:
    policy_reference = ValidationArtifactReference(
        "STRATEGY_ECONOMICS_POLICY", policy.policy_id, policy.policy_hash
    )
    label_reference = ValidationArtifactReference(
        "TARGET_OUTCOME_LABEL", label.label_id, label.label_hash
    )
    liquidity_reference = ValidationArtifactReference(
        "LIQUIDITY_CAPACITY_ASSESSMENT",
        liquidity.assessment_id,
        liquidity.assessment_hash,
    )
    values = _result_payload(
        policy_reference,
        label_reference,
        liquidity_reference,
        entry_execution.source_reference,
        exit_execution.source_reference,
        label.symbol,
        status,
        requested_notional,
        liquidity.capacity_ceiling,
        filled_quantity,
        entry_price,
        exit_price,
        gross_return,
        cost_return,
        net_return,
        turnover,
        label.mfe,
        label.mae,
        reason_codes,
        evaluated_at,
        policy.limitations,
    )
    result_id, digest = content_identity("strategy-economics-result", values)
    return StrategyEconomicsResult(
        result_id,
        digest,
        policy_reference,
        label_reference,
        liquidity_reference,
        entry_execution.source_reference,
        exit_execution.source_reference,
        label.symbol,
        status,
        requested_notional,
        liquidity.capacity_ceiling,
        filled_quantity,
        entry_price,
        exit_price,
        gross_return,
        cost_return,
        net_return,
        turnover,
        label.mfe,
        label.mae,
        reason_codes,
        evaluated_at,
        ResearchEvidenceAuthority.EXPLORATORY,
        policy.limitations,
    )


def _policy_payload(
    policy_version: str,
    target_reference: ValidationArtifactReference,
    prediction_checkpoint: OutcomeCheckpoint,
    entry_kind: StrategyEntryKind,
    exit_kind: StrategyExitKind,
    fixed_exit_checkpoint: OutcomeCheckpoint,
    barrier_id: str | None,
    barrier_return: Decimal | None,
    forecast_raw_score_threshold: Decimal | None,
    lot_size: int,
    t_plus_one: bool,
    parameters: tuple[ShadowPortfolioParameter, ...],
    created_at: datetime,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": "strategy-economics-policy/v1",
        "policy_version": policy_version,
        "prediction_target_reference": target_reference.to_canonical_dict(),
        "prediction_checkpoint": prediction_checkpoint.value,
        "entry_kind": entry_kind.value,
        "exit_kind": exit_kind.value,
        "holding_exit_policy": {
            "fixed_exit_checkpoint": fixed_exit_checkpoint.value,
            "barrier_id": barrier_id,
            "barrier_return": decimal_text(barrier_return),
            "forecast_raw_score_threshold": decimal_text(
                forecast_raw_score_threshold
            ),
        },
        "lot_size": lot_size,
        "t_plus_one": t_plus_one,
        "parameters": [item.to_canonical_dict() for item in parameters],
        "created_at": timestamp(created_at),
        "limitations": list(limitations),
    }


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Strategy Economics payload is not an object")
    return value


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _result_payload(
    policy_reference: ValidationArtifactReference,
    target_label_reference: ValidationArtifactReference,
    liquidity_reference: ValidationArtifactReference,
    entry_execution_reference: ValidationArtifactReference,
    exit_execution_reference: ValidationArtifactReference,
    symbol: str,
    status: StrategyEconomicsStatus,
    requested_notional: Decimal,
    capacity_ceiling: Decimal | None,
    filled_quantity: Decimal,
    entry_price: Decimal | None,
    exit_price: Decimal | None,
    gross_return: Decimal | None,
    cost_return: Decimal | None,
    net_return: Decimal | None,
    turnover: Decimal,
    mfe: Decimal | None,
    mae: Decimal | None,
    reason_codes: tuple[str, ...],
    evaluated_at: datetime,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": "strategy-economics-result/v1",
        "policy_reference": policy_reference.to_canonical_dict(),
        "target_label_reference": target_label_reference.to_canonical_dict(),
        "liquidity_reference": liquidity_reference.to_canonical_dict(),
        "entry_execution_reference": entry_execution_reference.to_canonical_dict(),
        "exit_execution_reference": exit_execution_reference.to_canonical_dict(),
        "symbol": symbol,
        "status": status.value,
        "requested_notional": str(requested_notional),
        "capacity_ceiling": decimal_text(capacity_ceiling),
        "filled_quantity": str(filled_quantity),
        "entry_price": decimal_text(entry_price),
        "exit_price": decimal_text(exit_price),
        "gross_return": decimal_text(gross_return),
        "cost_return": decimal_text(cost_return),
        "net_return": decimal_text(net_return),
        "turnover": str(turnover),
        "mfe": decimal_text(mfe),
        "mae": decimal_text(mae),
        "reason_codes": list(reason_codes),
        "evaluated_at": timestamp(evaluated_at),
        "authority": ResearchEvidenceAuthority.EXPLORATORY.value,
        "limitations": list(limitations),
    }


__all__ = [
    "StrategyEconomicsPolicy",
    "StrategyEconomicsResult",
    "StrategyEconomicsStatus",
    "StrategyExecutionObservation",
    "StrategyExecutionPhase",
    "StrategyEntryKind",
    "StrategyExitKind",
    "evaluate_strategy_economics",
]
