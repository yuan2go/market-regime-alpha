"""Additive Candidate/Signal/Forecast bindings for stateful research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_text,
)
from market_regime_alpha.forecasting.contracts import CalibrationStatus
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.research.state_system.pool import DynamicStockPoolVersion


def _ordered_text(label: str, values: tuple[str, ...]) -> None:
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} must be unique and sorted")


def _ordered_ids(label: str, values: tuple[ArtifactId, ...]) -> None:
    if values != tuple(sorted(set(values), key=str)):
        raise ValueError(f"{label} must be unique and sorted")


@dataclass(frozen=True, slots=True)
class CandidatePoolBindingRecord:
    symbol: str
    included: bool
    pool_gate_result: str
    candidate_gate_result: str
    candidate_score: float | None
    candidate_rank: int | None
    exclusion_reasons: tuple[str, ...]
    data_coverage: Decimal
    source_pool_version: int

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "included": self.included,
            "pool_gate_result": self.pool_gate_result,
            "candidate_gate_result": self.candidate_gate_result,
            "candidate_score": self.candidate_score,
            "candidate_rank": self.candidate_rank,
            "exclusion_reasons": list(self.exclusion_reasons),
            "data_coverage": str(self.data_coverage),
            "source_pool_version": self.source_pool_version,
        }


@dataclass(frozen=True, slots=True)
class StateBoundCandidateSet:
    binding_id: ArtifactId
    binding_hash: str
    candidate_set_id: ArtifactId
    candidate_set_hash: str
    dynamic_pool_id: ArtifactId
    market_regime_state_id: ArtifactId
    etf_rotation_state_ids: tuple[ArtifactId, ...]
    theme_rotation_state_ids: tuple[ArtifactId, ...]
    capital_state_id: ArtifactId
    feature_bundle_id: ArtifactId
    runtime_tick_id: ArtifactId
    records: tuple[CandidatePoolBindingRecord, ...]
    available_at: datetime
    as_of_time: datetime
    rule_version: str
    configuration_version: str

    @property
    def entry_authority_granted(self) -> bool:
        return False

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": "state_bound_candidate_set/v1",
            "candidate_set_id": str(self.candidate_set_id),
            "candidate_set_hash": self.candidate_set_hash,
            "dynamic_pool_id": str(self.dynamic_pool_id),
            "market_regime_state_id": str(self.market_regime_state_id),
            "etf_rotation_state_ids": [str(value) for value in self.etf_rotation_state_ids],
            "theme_rotation_state_ids": [str(value) for value in self.theme_rotation_state_ids],
            "capital_state_id": str(self.capital_state_id),
            "feature_bundle_id": str(self.feature_bundle_id),
            "runtime_tick_id": str(self.runtime_tick_id),
            "records": [record.to_canonical_dict() for record in self.records],
            "available_at": canonical_datetime(self.available_at),
            "as_of_time": canonical_datetime(self.as_of_time),
            "rule_version": self.rule_version,
            "configuration_version": self.configuration_version,
        }


def bind_candidate_set(
    *,
    candidate_set: CandidateSet,
    dynamic_pool: DynamicStockPoolVersion,
    market_regime_state_id: ArtifactId,
    etf_rotation_state_ids: tuple[ArtifactId, ...],
    theme_rotation_state_ids: tuple[ArtifactId, ...],
    capital_state_id: ArtifactId,
    feature_bundle_id: ArtifactId,
    runtime_tick_id: ArtifactId,
    available_at: datetime,
    as_of_time: datetime,
    rule_version: str,
    configuration_version: str,
) -> StateBoundCandidateSet:
    require_text("rule_version", rule_version)
    require_text("configuration_version", configuration_version)
    if available_at > as_of_time or dynamic_pool.available_at > as_of_time:
        raise ValueError("Candidate binding available_at exceeds As-of Time")
    if (
        market_regime_state_id != dynamic_pool.market_regime_state_id
        or etf_rotation_state_ids != dynamic_pool.etf_rotation_state_ids
        or theme_rotation_state_ids != dynamic_pool.theme_rotation_state_ids
        or capital_state_id != dynamic_pool.capital_state_id
        or runtime_tick_id != dynamic_pool.runtime_tick_id
    ):
        raise ValueError("Candidate binding State/Pool lineage mismatch")
    candidate_by_symbol = {record.symbol: record for record in candidate_set.records}
    pool_by_symbol = {member.symbol: member for member in dynamic_pool.members}
    if set(candidate_by_symbol) != set(pool_by_symbol):
        raise ValueError("CandidateSet must preserve the complete Pool cross section")
    records = tuple(
        CandidatePoolBindingRecord(
            symbol=symbol,
            included=pool_by_symbol[symbol].included,
            pool_gate_result=pool_by_symbol[symbol].gate_result,
            candidate_gate_result=candidate_by_symbol[symbol].selection_status.value,
            candidate_score=candidate_by_symbol[symbol].candidate_discovery_score,
            candidate_rank=candidate_by_symbol[symbol].rank,
            exclusion_reasons=tuple(
                sorted(
                    set(pool_by_symbol[symbol].exclusion_reasons)
                    | set(candidate_by_symbol[symbol].reason_codes)
                )
            ),
            data_coverage=pool_by_symbol[symbol].data_coverage,
            source_pool_version=dynamic_pool.pool_version,
        )
        for symbol in sorted(candidate_by_symbol)
    )
    prototype = {
        "schema": "state_bound_candidate_set/v1",
        "candidate_set_id": str(candidate_set.envelope.artifact_id),
        "candidate_set_hash": candidate_set.envelope.content_hash,
        "dynamic_pool_id": str(dynamic_pool.pool_id),
        "market_regime_state_id": str(market_regime_state_id),
        "etf_rotation_state_ids": [str(value) for value in etf_rotation_state_ids],
        "theme_rotation_state_ids": [str(value) for value in theme_rotation_state_ids],
        "capital_state_id": str(capital_state_id),
        "feature_bundle_id": str(feature_bundle_id),
        "runtime_tick_id": str(runtime_tick_id),
        "records": [record.to_canonical_dict() for record in records],
        "available_at": canonical_datetime(available_at),
        "as_of_time": canonical_datetime(as_of_time),
        "rule_version": rule_version,
        "configuration_version": configuration_version,
    }
    digest = canonical_hash(prototype)
    return StateBoundCandidateSet(
        binding_id=ArtifactId(f"candidate-state-binding:{digest[7:]}"),
        binding_hash=digest,
        candidate_set_id=candidate_set.envelope.artifact_id,
        candidate_set_hash=candidate_set.envelope.content_hash,
        dynamic_pool_id=dynamic_pool.pool_id,
        market_regime_state_id=market_regime_state_id,
        etf_rotation_state_ids=etf_rotation_state_ids,
        theme_rotation_state_ids=theme_rotation_state_ids,
        capital_state_id=capital_state_id,
        feature_bundle_id=feature_bundle_id,
        runtime_tick_id=runtime_tick_id,
        records=records,
        available_at=available_at,
        as_of_time=as_of_time,
        rule_version=rule_version,
        configuration_version=configuration_version,
    )


class SignalV4State(str, Enum):
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    INACTIVE = "INACTIVE"
    WATCH = "WATCH"
    CONFIRMED_FOR_RESEARCH = "CONFIRMED_FOR_RESEARCH"


@dataclass(frozen=True, slots=True)
class StateBoundSignalV4:
    signal_id: ArtifactId
    signal_hash: str
    symbol: str
    candidate_binding_id: ArtifactId
    dynamic_pool_id: ArtifactId
    feature_bundle_id: ArtifactId
    active_factors: tuple[str, ...]
    failed_factors: tuple[str, ...]
    missing_factors: tuple[str, ...]
    factor_coverage: Decimal
    signal_state: SignalV4State
    rule_id: ArtifactId
    rule_version: str
    configuration_id: ArtifactId
    configuration_version: str
    decision_time: datetime
    available_at: datetime

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema": "state_bound_signal/v4",
            "signal_id": str(self.signal_id),
            "signal_hash": self.signal_hash,
            "symbol": self.symbol,
            "candidate_binding_id": str(self.candidate_binding_id),
            "dynamic_pool_id": str(self.dynamic_pool_id),
            "feature_bundle_id": str(self.feature_bundle_id),
            "active_factors": list(self.active_factors),
            "failed_factors": list(self.failed_factors),
            "missing_factors": list(self.missing_factors),
            "factor_coverage": str(self.factor_coverage),
            "signal_state": self.signal_state.value,
            "rule_id": str(self.rule_id),
            "rule_version": self.rule_version,
            "configuration_id": str(self.configuration_id),
            "configuration_version": self.configuration_version,
            "decision_time": canonical_datetime(self.decision_time),
            "available_at": canonical_datetime(self.available_at),
        }


def project_signal_v4(
    *,
    symbol: str,
    candidate_binding_id: ArtifactId,
    dynamic_pool_id: ArtifactId,
    feature_bundle_id: ArtifactId,
    active_factors: tuple[str, ...],
    failed_factors: tuple[str, ...],
    missing_factors: tuple[str, ...],
    signal_state: SignalV4State,
    rule_id: ArtifactId,
    rule_version: str,
    configuration_id: ArtifactId,
    configuration_version: str,
    decision_time: datetime,
    available_at: datetime,
) -> StateBoundSignalV4:
    require_text("symbol", symbol)
    require_text("rule_version", rule_version)
    require_text("configuration_version", configuration_version)
    for label, values in (
        ("active_factors", active_factors),
        ("failed_factors", failed_factors),
        ("missing_factors", missing_factors),
    ):
        _ordered_text(label, values)
    all_factors = (*active_factors, *failed_factors, *missing_factors)
    if len(all_factors) != len(set(all_factors)):
        raise ValueError("Signal factor classifications must be disjoint")
    if available_at > decision_time:
        raise ValueError("Signal available_at must not exceed Decision Time")
    coverage = Decimal("0") if not all_factors else Decimal(len(active_factors)) / Decimal(len(all_factors))
    identity = {
        "schema": "state_bound_signal/v4",
        "symbol": symbol,
        "candidate_binding_id": str(candidate_binding_id),
        "dynamic_pool_id": str(dynamic_pool_id),
        "feature_bundle_id": str(feature_bundle_id),
        "active_factors": list(active_factors),
        "failed_factors": list(failed_factors),
        "missing_factors": list(missing_factors),
        "factor_coverage": str(coverage),
        "signal_state": signal_state.value,
        "rule_id": str(rule_id),
        "rule_version": rule_version,
        "configuration_id": str(configuration_id),
        "configuration_version": configuration_version,
        "decision_time": canonical_datetime(decision_time),
        "available_at": canonical_datetime(available_at),
    }
    digest = canonical_hash(identity)
    return StateBoundSignalV4(
        signal_id=ArtifactId(f"state-bound-signal-v4:{digest[7:]}"),
        signal_hash=digest,
        symbol=symbol,
        candidate_binding_id=candidate_binding_id,
        dynamic_pool_id=dynamic_pool_id,
        feature_bundle_id=feature_bundle_id,
        active_factors=active_factors,
        failed_factors=failed_factors,
        missing_factors=missing_factors,
        factor_coverage=coverage,
        signal_state=signal_state,
        rule_id=rule_id,
        rule_version=rule_version,
        configuration_id=configuration_id,
        configuration_version=configuration_version,
        decision_time=decision_time,
        available_at=available_at,
    )


class EmpiricalForecastBias(str, Enum):
    UP_BIAS = "UP_BIAS"
    DOWN_BIAS = "DOWN_BIAS"
    NEUTRAL = "NEUTRAL"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


class EmpiricalForecastStatus(str, Enum):
    AVAILABLE_FOR_RESEARCH = "AVAILABLE_FOR_RESEARCH"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


@dataclass(frozen=True, slots=True)
class StateBoundEmpiricalForecastV2:
    forecast_id: ArtifactId
    forecast_hash: str
    forecast_kind: str
    symbol: str
    bias: EmpiricalForecastBias
    forecast_horizon: str
    observation_time: datetime
    as_of_time: datetime
    available_at: datetime
    sample_count: int
    data_coverage: Decimal
    historical_distribution: tuple[Decimal, ...]
    calibration_status: CalibrationStatus
    status: EmpiricalForecastStatus
    source_state_ids: tuple[ArtifactId, ...]
    dynamic_pool_id: ArtifactId
    model_id: ModelId
    model_version: str
    configuration_id: ArtifactId
    configuration_version: str
    reason_codes: tuple[str, ...]

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema": "state_bound_empirical_path_forecast/v2",
            "forecast_id": str(self.forecast_id),
            "forecast_hash": self.forecast_hash,
            "forecast_kind": self.forecast_kind,
            "symbol": self.symbol,
            "bias": self.bias.value,
            "forecast_horizon": self.forecast_horizon,
            "observation_time": canonical_datetime(self.observation_time),
            "as_of_time": canonical_datetime(self.as_of_time),
            "available_at": canonical_datetime(self.available_at),
            "sample_count": self.sample_count,
            "data_coverage": str(self.data_coverage),
            "historical_distribution": [str(value) for value in self.historical_distribution],
            "calibration_status": self.calibration_status.value,
            "status": self.status.value,
            "source_state_ids": [str(value) for value in self.source_state_ids],
            "dynamic_pool_id": str(self.dynamic_pool_id),
            "model_id": str(self.model_id),
            "model_version": self.model_version,
            "configuration_id": str(self.configuration_id),
            "configuration_version": self.configuration_version,
            "reason_codes": list(self.reason_codes),
        }


def project_empirical_forecast_v2(
    *,
    symbol: str,
    forecast_horizon: str,
    observation_time: datetime,
    as_of_time: datetime,
    available_at: datetime,
    historical_returns: tuple[Decimal, ...] | None,
    data_coverage: Decimal,
    minimum_sample_count: int,
    source_state_ids: tuple[ArtifactId, ...],
    dynamic_pool_id: ArtifactId,
    model_id: ModelId,
    model_version: str,
    configuration_id: ArtifactId,
    configuration_version: str,
) -> StateBoundEmpiricalForecastV2:
    require_text("symbol", symbol)
    require_text("forecast_horizon", forecast_horizon)
    require_text("model_version", model_version)
    require_text("configuration_version", configuration_version)
    _ordered_ids("source_state_ids", source_state_ids)
    if not source_state_ids:
        raise ValueError("source_state_ids must not be empty")
    if available_at > as_of_time or observation_time > as_of_time:
        raise ValueError("Forecast cannot consume future evidence")
    if not Decimal("0") <= data_coverage <= Decimal("1"):
        raise ValueError("data_coverage must be within [0, 1]")
    if minimum_sample_count <= 0:
        raise ValueError("minimum_sample_count must be positive")
    distribution = () if historical_returns is None else tuple(sorted(historical_returns))
    reasons: tuple[str, ...]
    if len(distribution) < minimum_sample_count:
        bias = EmpiricalForecastBias.DATA_INSUFFICIENT
        status = EmpiricalForecastStatus.DATA_INSUFFICIENT
        calibration = CalibrationStatus.DATA_INSUFFICIENT
        reasons = ("EMPIRICAL_SAMPLE_PROVIDER_UNAVAILABLE_OR_INSUFFICIENT",)
        distribution = ()
    else:
        middle = len(distribution) // 2
        median = (
            distribution[middle]
            if len(distribution) % 2
            else (distribution[middle - 1] + distribution[middle]) / Decimal("2")
        )
        bias = (
            EmpiricalForecastBias.UP_BIAS
            if median > 0
            else EmpiricalForecastBias.DOWN_BIAS
            if median < 0
            else EmpiricalForecastBias.NEUTRAL
        )
        status = EmpiricalForecastStatus.AVAILABLE_FOR_RESEARCH
        calibration = CalibrationStatus.NOT_CALIBRATED
        reasons = ("EMPIRICAL_PATH_DISTRIBUTION", "NOT_CALIBRATED")
    identity = {
        "schema": "state_bound_empirical_path_forecast/v2",
        "forecast_kind": "EMPIRICAL_PATH_DISTRIBUTION",
        "symbol": symbol,
        "bias": bias.value,
        "forecast_horizon": forecast_horizon,
        "observation_time": canonical_datetime(observation_time),
        "as_of_time": canonical_datetime(as_of_time),
        "available_at": canonical_datetime(available_at),
        "sample_count": 0 if historical_returns is None else len(historical_returns),
        "data_coverage": str(data_coverage),
        "historical_distribution": [str(value) for value in distribution],
        "calibration_status": calibration.value,
        "status": status.value,
        "source_state_ids": [str(value) for value in source_state_ids],
        "dynamic_pool_id": str(dynamic_pool_id),
        "model_id": str(model_id),
        "model_version": model_version,
        "configuration_id": str(configuration_id),
        "configuration_version": configuration_version,
        "reason_codes": list(reasons),
    }
    digest = canonical_hash(identity)
    return StateBoundEmpiricalForecastV2(
        forecast_id=ArtifactId(f"empirical-path-forecast-v2:{digest[7:]}"),
        forecast_hash=digest,
        forecast_kind="EMPIRICAL_PATH_DISTRIBUTION",
        symbol=symbol,
        bias=bias,
        forecast_horizon=forecast_horizon,
        observation_time=observation_time,
        as_of_time=as_of_time,
        available_at=available_at,
        sample_count=0 if historical_returns is None else len(historical_returns),
        data_coverage=data_coverage,
        historical_distribution=distribution,
        calibration_status=calibration,
        status=status,
        source_state_ids=source_state_ids,
        dynamic_pool_id=dynamic_pool_id,
        model_id=model_id,
        model_version=model_version,
        configuration_id=configuration_id,
        configuration_version=configuration_version,
        reason_codes=reasons,
    )


@dataclass(frozen=True, slots=True)
class FeatureExposureAudit:
    audit_id: ArtifactId
    audit_hash: str
    audit_rule_version: str
    factor_names: tuple[str, ...]
    duplicate_exposures: tuple[tuple[str, tuple[str, ...]], ...]
    weights_changed: bool = False


_EXPOSURE_TERMS = {
    "MOMENTUM": ("momentum",),
    "PRICE_ACTION": ("price_action", "breakout", "return"),
    "VOLUME": ("volume",),
    "AMOUNT": ("amount", "turnover"),
    "ETF_STRENGTH": ("etf",),
    "THEME_STRENGTH": ("theme",),
    "CAPITAL_STRENGTH": ("capital",),
    "SIGNAL_CONFIRMATION": ("signal", "confirmation"),
}


def audit_feature_exposures(
    factor_names: tuple[str, ...],
    *,
    audit_rule_version: str,
) -> FeatureExposureAudit:
    require_text("audit_rule_version", audit_rule_version)
    _ordered_text("factor_names", tuple(sorted(factor_names)))
    ordered = tuple(sorted(factor_names))
    duplicates = tuple(
        (category, matches)
        for category, terms in sorted(_EXPOSURE_TERMS.items())
        if len(
            matches := tuple(
                factor for factor in ordered if any(term in factor.lower() for term in terms)
            )
        )
        > 1
    )
    identity = {
        "schema": "feature_exposure_audit/v1",
        "audit_rule_version": audit_rule_version,
        "factor_names": list(ordered),
        "duplicate_exposures": [
            {"category": category, "factors": list(factors)}
            for category, factors in duplicates
        ],
        "weights_changed": False,
    }
    digest = canonical_hash(identity)
    return FeatureExposureAudit(
        audit_id=ArtifactId(f"feature-exposure-audit:{digest[7:]}"),
        audit_hash=digest,
        audit_rule_version=audit_rule_version,
        factor_names=ordered,
        duplicate_exposures=duplicates,
    )
