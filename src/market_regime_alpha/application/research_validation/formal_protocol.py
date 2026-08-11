"""Frozen Phase C research protocol and OutcomeTarget-bound Forecast contracts.

This module does not grant PIT, OOS, calibration, Entry, or Production
authority.  It freezes every result-affecting selection before evidence is
resolved and defines the exact Forecast/Outcome Target identity boundary that
later qualification owners must reload from PostgreSQL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeTargetProtocol,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
    content_identity,
    decimal_text,
    timestamp,
)
from market_regime_alpha.application.research_validation.formal_evaluation import (
    FormalEvaluationProtocol,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_sha256,
    require_text,
)


_REFERENCE_KINDS = {
    "trading_calendar_reference": "TRADING_CALENDAR",
    "universe_reference": "UNIVERSE",
    "dataset_reference": "MARKET_DATA_DATASET",
    "historical_sample_dataset_reference": "HISTORICAL_SAMPLE_DATASET",
    "feature_reference": "FEATURE_DEFINITION_SET",
    "factor_reference": "FACTOR_CATALOG",
    "model_reference": "MODEL_VERSION_LINEAGE",
    "threshold_policy_reference": "THRESHOLD_POLICY",
    "formal_oos_qualification_policy_reference": "FORMAL_OOS_QUALIFICATION_POLICY",
    "cost_policy_reference": "SHADOW_PORTFOLIO_POLICY",
    "calibration_policy_reference": "CALIBRATION_POLICY",
    "strategy_policy_reference": "STRATEGY_SHADOW_POLICY",
    "entry_holding_exit_qualification_policy_reference": (
        "ENTRY_HOLDING_EXIT_QUALIFICATION_POLICY"
    ),
}


@dataclass(frozen=True, slots=True)
class FormalResearchProtocol:
    """Content-addressed freeze of all Phase C result-affecting choices."""

    protocol_id: ArtifactId
    protocol_hash: str
    protocol_version: str
    outcome_target_protocol_reference: ValidationArtifactReference
    target_references: tuple[ValidationArtifactReference, ...]
    trading_calendar_reference: ValidationArtifactReference
    frozen_trading_dates: tuple[date, ...]
    evaluation_protocol_reference: ValidationArtifactReference
    universe_reference: ValidationArtifactReference
    dataset_reference: ValidationArtifactReference
    historical_sample_dataset_reference: ValidationArtifactReference
    feature_reference: ValidationArtifactReference
    factor_reference: ValidationArtifactReference
    model_reference: ValidationArtifactReference
    threshold_policy_reference: ValidationArtifactReference
    formal_oos_qualification_policy_reference: ValidationArtifactReference
    cost_policy_reference: ValidationArtifactReference
    calibration_policy_reference: ValidationArtifactReference
    strategy_policy_reference: ValidationArtifactReference
    entry_holding_exit_qualification_policy_reference: ValidationArtifactReference
    locked_at: datetime
    locked_oos_reuse_policy: str = "NEVER_REUSE_FOR_SELECTION_OR_TUNING"
    schema_version: str = "formal-research-protocol/v1"

    def __post_init__(self) -> None:
        require_sha256("protocol_hash", self.protocol_hash)
        require_text("protocol_version", self.protocol_version)
        if self.schema_version != "formal-research-protocol/v1":
            raise ValueError("unsupported Formal Research Protocol schema")
        if self.locked_oos_reuse_policy != "NEVER_REUSE_FOR_SELECTION_OR_TUNING":
            raise ValueError("Locked OOS reuse policy cannot be weakened")
        if self.locked_at.tzinfo is None or self.locked_at.utcoffset() is None:
            raise ValueError("Formal Research Protocol lock time must be timezone-aware")
        if (
            not self.frozen_trading_dates
            or self.frozen_trading_dates != tuple(sorted(set(self.frozen_trading_dates)))
        ):
            raise ValueError("Frozen Trading Calendar dates must be non-empty, unique and sorted")
        if self.target_references != tuple(
            sorted(
                set(self.target_references),
                key=lambda item: str(item.artifact_id),
            )
        ):
            raise ValueError("Outcome Target references must be unique and sorted")
        for field_name, expected_kind in _REFERENCE_KINDS.items():
            reference = getattr(self, field_name)
            if reference.artifact_kind != expected_kind:
                raise ValueError(f"{field_name} must reference {expected_kind}")
        if self.outcome_target_protocol_reference.artifact_kind != "OUTCOME_TARGET_PROTOCOL":
            raise ValueError("Formal protocol requires Outcome Target Protocol authority")
        if self.trading_calendar_reference.artifact_kind != "TRADING_CALENDAR":
            raise ValueError("Formal protocol requires Frozen Trading Calendar authority")
        if self.evaluation_protocol_reference.artifact_kind != "FORMAL_EVALUATION_PROTOCOL":
            raise ValueError("Formal protocol requires Formal Evaluation Protocol authority")
        if canonical_hash(self.identity_payload()) != self.protocol_hash:
            raise ValueError("Formal Research Protocol hash mismatch")
        if self.protocol_id != ArtifactId(
            f"formal-research-protocol:{self.protocol_hash[7:]}"
        ):
            raise ValueError("Formal Research Protocol identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        protocol_version: str,
        target_protocol: OutcomeTargetProtocol,
        trading_calendar: TradingCalendarArtifact,
        evaluation_protocol: FormalEvaluationProtocol,
        universe_reference: ValidationArtifactReference,
        dataset_reference: ValidationArtifactReference,
        historical_sample_dataset_reference: ValidationArtifactReference,
        feature_reference: ValidationArtifactReference,
        factor_reference: ValidationArtifactReference,
        model_reference: ValidationArtifactReference,
        threshold_policy_reference: ValidationArtifactReference,
        formal_oos_qualification_policy_reference: ValidationArtifactReference,
        cost_policy_reference: ValidationArtifactReference,
        calibration_policy_reference: ValidationArtifactReference,
        strategy_policy_reference: ValidationArtifactReference,
        entry_holding_exit_qualification_policy_reference: ValidationArtifactReference,
        locked_at: datetime,
    ) -> FormalResearchProtocol:
        target_protocol_reference = ValidationArtifactReference(
            "OUTCOME_TARGET_PROTOCOL",
            target_protocol.protocol_id,
            target_protocol.protocol_hash,
        )
        if evaluation_protocol.target_protocol_reference != target_protocol_reference:
            raise ValueError(
                "Formal Evaluation Target Protocol must equal the frozen Outcome Target Protocol"
            )
        if evaluation_protocol.locked_at > locked_at:
            raise ValueError(
                "Formal Evaluation Protocol must be locked before the Formal Research Protocol"
            )
        calendar_dates = trading_calendar.trading_dates
        calendar_date_set = set(calendar_dates)
        if any(
            window.start_date not in calendar_date_set
            or window.end_date not in calendar_date_set
            for window in evaluation_protocol.windows
        ):
            raise ValueError(
                "Formal Evaluation windows must be bounded by the Frozen Trading Calendar"
            )
        target_references = tuple(
            sorted(
                (
                    ValidationArtifactReference(
                        "OUTCOME_TARGET",
                        target.target_id,
                        target.target_hash,
                    )
                    for target in target_protocol.targets
                ),
                key=lambda item: str(item.artifact_id),
            )
        )
        calendar_reference = ValidationArtifactReference(
            "TRADING_CALENDAR",
            trading_calendar.artifact_id,
            trading_calendar.content_hash,
        )
        evaluation_reference = ValidationArtifactReference(
            "FORMAL_EVALUATION_PROTOCOL",
            evaluation_protocol.protocol_id,
            evaluation_protocol.protocol_hash,
        )
        payload = _formal_protocol_payload(
            protocol_version=protocol_version,
            outcome_target_protocol_reference=target_protocol_reference,
            target_references=target_references,
            trading_calendar_reference=calendar_reference,
            frozen_trading_dates=calendar_dates,
            evaluation_protocol_reference=evaluation_reference,
            universe_reference=universe_reference,
            dataset_reference=dataset_reference,
            historical_sample_dataset_reference=historical_sample_dataset_reference,
            feature_reference=feature_reference,
            factor_reference=factor_reference,
            model_reference=model_reference,
            threshold_policy_reference=threshold_policy_reference,
            formal_oos_qualification_policy_reference=formal_oos_qualification_policy_reference,
            cost_policy_reference=cost_policy_reference,
            calibration_policy_reference=calibration_policy_reference,
            strategy_policy_reference=strategy_policy_reference,
            entry_holding_exit_qualification_policy_reference=(
                entry_holding_exit_qualification_policy_reference
            ),
            locked_at=locked_at,
        )
        protocol_id, protocol_hash = content_identity(
            "formal-research-protocol", payload
        )
        return cls(
            protocol_id,
            protocol_hash,
            protocol_version,
            target_protocol_reference,
            target_references,
            calendar_reference,
            calendar_dates,
            evaluation_reference,
            universe_reference,
            dataset_reference,
            historical_sample_dataset_reference,
            feature_reference,
            factor_reference,
            model_reference,
            threshold_policy_reference,
            formal_oos_qualification_policy_reference,
            cost_policy_reference,
            calibration_policy_reference,
            strategy_policy_reference,
            entry_holding_exit_qualification_policy_reference,
            locked_at,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _formal_protocol_payload(
            protocol_version=self.protocol_version,
            outcome_target_protocol_reference=self.outcome_target_protocol_reference,
            target_references=self.target_references,
            trading_calendar_reference=self.trading_calendar_reference,
            frozen_trading_dates=self.frozen_trading_dates,
            evaluation_protocol_reference=self.evaluation_protocol_reference,
            universe_reference=self.universe_reference,
            dataset_reference=self.dataset_reference,
            historical_sample_dataset_reference=self.historical_sample_dataset_reference,
            feature_reference=self.feature_reference,
            factor_reference=self.factor_reference,
            model_reference=self.model_reference,
            threshold_policy_reference=self.threshold_policy_reference,
            formal_oos_qualification_policy_reference=self.formal_oos_qualification_policy_reference,
            cost_policy_reference=self.cost_policy_reference,
            calibration_policy_reference=self.calibration_policy_reference,
            strategy_policy_reference=self.strategy_policy_reference,
            entry_holding_exit_qualification_policy_reference=(
                self.entry_holding_exit_qualification_policy_reference
            ),
            locked_at=self.locked_at,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "protocol_id": str(self.protocol_id),
            "protocol_hash": self.protocol_hash,
            **self.identity_payload(),
        }

    def component_references(
        self,
    ) -> dict[str, ValidationArtifactReference]:
        return {
            field_name: getattr(self, field_name)
            for field_name in _REFERENCE_KINDS
        }

    @classmethod
    def from_canonical_dict(cls, value: dict[str, Any]) -> FormalResearchProtocol:
        return cls(
            protocol_id=ArtifactId(str(value["protocol_id"])),
            protocol_hash=str(value["protocol_hash"]),
            protocol_version=str(value["protocol_version"]),
            outcome_target_protocol_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["outcome_target_protocol_reference"])
            ),
            target_references=tuple(
                ValidationArtifactReference.from_canonical_dict(_mapping(item))
                for item in _sequence(value["target_references"])
            ),
            trading_calendar_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["trading_calendar_reference"])
            ),
            frozen_trading_dates=tuple(
                date.fromisoformat(str(item))
                for item in _sequence(value["frozen_trading_dates"])
            ),
            evaluation_protocol_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["evaluation_protocol_reference"])
            ),
            universe_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["universe_reference"])
            ),
            dataset_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["dataset_reference"])
            ),
            historical_sample_dataset_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["historical_sample_dataset_reference"])
            ),
            feature_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["feature_reference"])
            ),
            factor_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["factor_reference"])
            ),
            model_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["model_reference"])
            ),
            threshold_policy_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["threshold_policy_reference"])
            ),
            formal_oos_qualification_policy_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["formal_oos_qualification_policy_reference"])
            ),
            cost_policy_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["cost_policy_reference"])
            ),
            calibration_policy_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["calibration_policy_reference"])
            ),
            strategy_policy_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["strategy_policy_reference"])
            ),
            entry_holding_exit_qualification_policy_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["entry_holding_exit_qualification_policy_reference"])
            ),
            locked_at=datetime.fromisoformat(str(value["locked_at"])),
            locked_oos_reuse_policy=str(value["locked_oos_reuse_policy"]),
            schema_version=str(value["schema_version"]),
        )


class OutcomeTargetForecastStatus(str, Enum):
    AVAILABLE_FOR_RESEARCH = "AVAILABLE_FOR_RESEARCH"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


@dataclass(frozen=True, slots=True)
class OutcomeTargetForecastEstimate:
    """One uncalibrated estimate for one exact Outcome Target identity."""

    target_id: ArtifactId
    target_hash: str
    status: OutcomeTargetForecastStatus
    score: Decimal | None
    expected_return: Decimal | None
    expected_mfe: Decimal | None
    expected_mae: Decimal | None
    barrier_scores: tuple[tuple[str, Decimal], ...]
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_sha256("target_hash", self.target_hash)
        if self.barrier_scores != tuple(sorted(set(self.barrier_scores))):
            raise ValueError("Forecast barrier scores must be unique and sorted")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Forecast reasons must be unique and sorted")
        if self.status is OutcomeTargetForecastStatus.NOT_ESTIMABLE:
            if any(
                value is not None
                for value in (
                    self.score,
                    self.expected_return,
                    self.expected_mfe,
                    self.expected_mae,
                )
            ) or self.barrier_scores:
                raise ValueError("NOT_ESTIMABLE Forecast cannot carry estimates")
            if not self.reason_codes:
                raise ValueError("NOT_ESTIMABLE Forecast requires reason codes")
        elif self.score is None:
            raise ValueError("available Outcome Target Forecast requires a score")
        if self.expected_mfe is not None and self.expected_mfe < 0:
            raise ValueError("Forecast MFE cannot be negative")
        if self.expected_mae is not None and self.expected_mae > 0:
            raise ValueError("Forecast MAE cannot be positive")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "target_id": str(self.target_id),
            "target_hash": self.target_hash,
            "status": self.status.value,
            "score": decimal_text(self.score),
            "expected_return": decimal_text(self.expected_return),
            "expected_mfe": decimal_text(self.expected_mfe),
            "expected_mae": decimal_text(self.expected_mae),
            "barrier_scores": [
                {"barrier_id": barrier_id, "score": str(score)}
                for barrier_id, score in self.barrier_scores
            ],
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(
        cls, value: dict[str, Any]
    ) -> OutcomeTargetForecastEstimate:
        def optional_decimal(name: str) -> Decimal | None:
            raw = value[name]
            return None if raw is None else Decimal(str(raw))

        return cls(
            target_id=ArtifactId(str(value["target_id"])),
            target_hash=str(value["target_hash"]),
            status=OutcomeTargetForecastStatus(str(value["status"])),
            score=optional_decimal("score"),
            expected_return=optional_decimal("expected_return"),
            expected_mfe=optional_decimal("expected_mfe"),
            expected_mae=optional_decimal("expected_mae"),
            barrier_scores=tuple(
                (str(_mapping(item)["barrier_id"]), Decimal(str(_mapping(item)["score"])))
                for item in _sequence(value["barrier_scores"])
            ),
            reason_codes=tuple(str(item) for item in _sequence(value["reason_codes"])),
        )


@dataclass(frozen=True, slots=True)
class OutcomeTargetBoundMultiTargetForecast:
    forecast_id: ArtifactId
    forecast_hash: str
    target_protocol_reference: ValidationArtifactReference
    symbol: str
    decision_time: datetime
    estimates: tuple[OutcomeTargetForecastEstimate, ...]
    source_references: tuple[ValidationArtifactReference, ...]
    model_reference: ValidationArtifactReference
    created_at: datetime
    calibrated: bool
    production_authorized: bool
    limitations: tuple[str, ...]
    schema_version: str = "outcome-target-bound-multi-target-forecast/v1"

    def __post_init__(self) -> None:
        require_sha256("forecast_hash", self.forecast_hash)
        require_text("symbol", self.symbol)
        if self.target_protocol_reference.artifact_kind != "OUTCOME_TARGET_PROTOCOL":
            raise ValueError("MultiTargetForecast requires Outcome Target Protocol")
        if self.model_reference.artifact_kind != "MODEL_VERSION_LINEAGE":
            raise ValueError("MultiTargetForecast requires Model Version Lineage")
        if self.decision_time.tzinfo is None or self.decision_time.utcoffset() is None:
            raise ValueError("Forecast DecisionTime must be timezone-aware")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("Forecast created_at must be timezone-aware")
        if self.created_at < self.decision_time:
            raise ValueError("Forecast cannot be created before DecisionTime")
        if self.estimates != tuple(
            sorted(self.estimates, key=lambda item: str(item.target_id))
        ) or len({item.target_id for item in self.estimates}) != len(self.estimates):
            raise ValueError("MultiTargetForecast estimates must be unique and sorted")
        if not self.source_references or self.source_references != tuple(
            sorted(
                set(self.source_references),
                key=lambda item: (
                    item.artifact_kind,
                    str(item.artifact_id),
                    item.content_hash,
                ),
            )
        ):
            raise ValueError("Forecast source references must be non-empty, unique and sorted")
        if self.calibrated or self.production_authorized:
            raise ValueError("C0 MultiTargetForecast cannot claim Calibration or Production authority")
        required_limitations = {
            "CALIBRATED_FALSE",
            "FORECAST_NOT_OUTCOME",
            "NO_TRADING_AUTHORITY",
            "PRODUCTION_AUTHORIZED_FALSE",
        }
        if not required_limitations.issubset(self.limitations):
            raise ValueError("MultiTargetForecast evidence ceiling is incomplete")
        if canonical_hash(self.identity_payload()) != self.forecast_hash:
            raise ValueError("MultiTargetForecast hash mismatch")
        if self.forecast_id != ArtifactId(
            f"outcome-target-forecast:{self.forecast_hash[7:]}"
        ):
            raise ValueError("MultiTargetForecast identity mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "target_protocol_reference": self.target_protocol_reference.to_canonical_dict(),
            "symbol": self.symbol,
            "decision_time": timestamp(self.decision_time),
            "estimates": [item.to_canonical_dict() for item in self.estimates],
            "source_references": [
                item.to_canonical_dict() for item in self.source_references
            ],
            "model_reference": self.model_reference.to_canonical_dict(),
            "created_at": timestamp(self.created_at),
            "calibrated": False,
            "production_authorized": False,
            "limitations": list(self.limitations),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "forecast_id": str(self.forecast_id),
            "forecast_hash": self.forecast_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, value: dict[str, Any]
    ) -> OutcomeTargetBoundMultiTargetForecast:
        return cls(
            forecast_id=ArtifactId(str(value["forecast_id"])),
            forecast_hash=str(value["forecast_hash"]),
            target_protocol_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["target_protocol_reference"])
            ),
            symbol=str(value["symbol"]),
            decision_time=datetime.fromisoformat(str(value["decision_time"])),
            estimates=tuple(
                OutcomeTargetForecastEstimate.from_canonical_dict(dict(_mapping(item)))
                for item in _sequence(value["estimates"])
            ),
            source_references=tuple(
                ValidationArtifactReference.from_canonical_dict(_mapping(item))
                for item in _sequence(value["source_references"])
            ),
            model_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["model_reference"])
            ),
            created_at=datetime.fromisoformat(str(value["created_at"])),
            calibrated=bool(value["calibrated"]),
            production_authorized=bool(value["production_authorized"]),
            limitations=tuple(str(item) for item in _sequence(value["limitations"])),
            schema_version=str(value["schema_version"]),
        )


def build_outcome_target_bound_forecast(
    *,
    target_protocol: OutcomeTargetProtocol,
    symbol: str,
    decision_time: datetime,
    estimates: tuple[OutcomeTargetForecastEstimate, ...],
    source_references: tuple[ValidationArtifactReference, ...],
    model_reference: ValidationArtifactReference,
    created_at: datetime,
) -> OutcomeTargetBoundMultiTargetForecast:
    """Build an exact Target-bound set; an Entry target can never be substituted."""

    expected = {
        (str(target.target_id), target.target_hash): target
        for target in target_protocol.targets
    }
    actual = {(str(item.target_id), item.target_hash) for item in estimates}
    if actual != set(expected):
        actual_ids = {target_id for target_id, _target_hash in actual}
        expected_ids = {target_id for target_id, _target_hash in expected}
        if actual_ids == expected_ids:
            raise ValueError("Forecast and Outcome Target identity/hash mismatch")
        raise ValueError("MultiTargetForecast must bind exactly every Outcome Target")
    for estimate in estimates:
        target = expected[(str(estimate.target_id), estimate.target_hash)]
        barrier_ids = tuple(item.barrier_id for item in target.barriers)
        estimate_barrier_ids = tuple(item[0] for item in estimate.barrier_scores)
        if (
            estimate.status is OutcomeTargetForecastStatus.AVAILABLE_FOR_RESEARCH
            and estimate_barrier_ids != barrier_ids
        ):
            raise ValueError("available Forecast must score every frozen Target barrier")
    target_reference = ValidationArtifactReference(
        "OUTCOME_TARGET_PROTOCOL",
        target_protocol.protocol_id,
        target_protocol.protocol_hash,
    )
    ordered_estimates = tuple(sorted(estimates, key=lambda item: str(item.target_id)))
    ordered_sources = tuple(
        sorted(
            set(source_references),
            key=lambda item: (
                item.artifact_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )
    limitations = (
        "CALIBRATED_FALSE",
        "FORECAST_NOT_OUTCOME",
        "NO_TRADING_AUTHORITY",
        "PRODUCTION_AUTHORIZED_FALSE",
    )
    payload = {
        "schema_version": "outcome-target-bound-multi-target-forecast/v1",
        "target_protocol_reference": target_reference.to_canonical_dict(),
        "symbol": symbol,
        "decision_time": timestamp(decision_time),
        "estimates": [item.to_canonical_dict() for item in ordered_estimates],
        "source_references": [item.to_canonical_dict() for item in ordered_sources],
        "model_reference": model_reference.to_canonical_dict(),
        "created_at": timestamp(created_at),
        "calibrated": False,
        "production_authorized": False,
        "limitations": list(limitations),
    }
    forecast_id, forecast_hash = content_identity(
        "outcome-target-forecast", payload
    )
    return OutcomeTargetBoundMultiTargetForecast(
        forecast_id,
        forecast_hash,
        target_reference,
        symbol,
        decision_time,
        ordered_estimates,
        ordered_sources,
        model_reference,
        created_at,
        False,
        False,
        limitations,
    )


def _formal_protocol_payload(
    *,
    protocol_version: str,
    outcome_target_protocol_reference: ValidationArtifactReference,
    target_references: tuple[ValidationArtifactReference, ...],
    trading_calendar_reference: ValidationArtifactReference,
    frozen_trading_dates: tuple[date, ...],
    evaluation_protocol_reference: ValidationArtifactReference,
    universe_reference: ValidationArtifactReference,
    dataset_reference: ValidationArtifactReference,
    historical_sample_dataset_reference: ValidationArtifactReference,
    feature_reference: ValidationArtifactReference,
    factor_reference: ValidationArtifactReference,
    model_reference: ValidationArtifactReference,
    threshold_policy_reference: ValidationArtifactReference,
    formal_oos_qualification_policy_reference: ValidationArtifactReference,
    cost_policy_reference: ValidationArtifactReference,
    calibration_policy_reference: ValidationArtifactReference,
    strategy_policy_reference: ValidationArtifactReference,
    entry_holding_exit_qualification_policy_reference: ValidationArtifactReference,
    locked_at: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": "formal-research-protocol/v1",
        "protocol_version": protocol_version,
        "outcome_target_protocol_reference": outcome_target_protocol_reference.to_canonical_dict(),
        "target_references": [item.to_canonical_dict() for item in target_references],
        "trading_calendar_reference": trading_calendar_reference.to_canonical_dict(),
        "frozen_trading_dates": [item.isoformat() for item in frozen_trading_dates],
        "evaluation_protocol_reference": evaluation_protocol_reference.to_canonical_dict(),
        "universe_reference": universe_reference.to_canonical_dict(),
        "dataset_reference": dataset_reference.to_canonical_dict(),
        "historical_sample_dataset_reference": (
            historical_sample_dataset_reference.to_canonical_dict()
        ),
        "feature_reference": feature_reference.to_canonical_dict(),
        "factor_reference": factor_reference.to_canonical_dict(),
        "model_reference": model_reference.to_canonical_dict(),
        "threshold_policy_reference": threshold_policy_reference.to_canonical_dict(),
        "formal_oos_qualification_policy_reference": (
            formal_oos_qualification_policy_reference.to_canonical_dict()
        ),
        "cost_policy_reference": cost_policy_reference.to_canonical_dict(),
        "calibration_policy_reference": calibration_policy_reference.to_canonical_dict(),
        "strategy_policy_reference": strategy_policy_reference.to_canonical_dict(),
        "entry_holding_exit_qualification_policy_reference": (
            entry_holding_exit_qualification_policy_reference.to_canonical_dict()
        ),
        "locked_at": timestamp(locked_at),
        "locked_oos_reuse_policy": "NEVER_REUSE_FOR_SELECTION_OR_TUNING",
    }


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Formal protocol payload is not an object")
    return value


def _sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("Formal protocol payload is not an array")
    return tuple(value)


__all__ = [
    "FormalResearchProtocol",
    "OutcomeTargetBoundMultiTargetForecast",
    "OutcomeTargetForecastEstimate",
    "OutcomeTargetForecastStatus",
    "build_outcome_target_bound_forecast",
]
