"""Canonical V3 Signal input mapping and Candidate-scoped assembly."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
    require_unique_text,
)
from market_regime_alpha.features.materialization_v2 import VerifiedFeatureBundleV2
from market_regime_alpha.features.technical.catalog import (
    CAPITAL_VOLUME_FEATURE_ID,
    MOVING_AVERAGE_FEATURE_ID,
    OVERHEAT_FEATURE_ID,
    PRICE_ACTION_FEATURE_ID,
    VWAP_FEATURE_ID,
)
from market_regime_alpha.features.technical.observables import FeatureValueState
from market_regime_alpha.market_data import Timeframe, VerifiedMarketDataDataset
from market_regime_alpha.market_data.contracts import (
    canonical_decimal,
    parse_canonical_decimal,
    parse_utc_second,
    require_utc_second,
)
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.signals.candidate_view import CandidateFeatureView
from market_regime_alpha.signals.input_assembly import SignalFactorName
from market_regime_alpha.signals.policies import (
    FactorFreshnessState,
    SignalFactorFreshnessPolicy,
    SignalFactorRequirementPolicy,
)


SIGNAL_FACTOR_MAPPING_V2_SCHEMA = "signal-factor-mapping-v2"
SIGNAL_INPUT_MAPPING_V2_SCHEMA = "signal-input-mapping-configuration-v2"
SIGNAL_FACTOR_OBSERVATION_V3_SCHEMA = "signal-factor-observation-v3"
SIGNAL_OBSERVATION_V3_SCHEMA = "signal-observation-v3"


@dataclass(frozen=True, slots=True)
class SignalFactorMappingV2:
    factor_name: SignalFactorName
    source_feature_id: str
    source_output_id: str
    timeframe: Timeframe
    required: bool

    def __post_init__(self) -> None:
        require_text("source_feature_id", self.source_feature_id)
        require_text("source_output_id", self.source_output_id)
        if not isinstance(self.required, bool):
            raise TypeError("required must be boolean")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SIGNAL_FACTOR_MAPPING_V2_SCHEMA,
            "factor_name": self.factor_name.value,
            "source_feature_id": self.source_feature_id,
            "source_output_id": self.source_output_id,
            "timeframe": self.timeframe.value,
            "required": self.required,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> SignalFactorMappingV2:
        if set(payload) != {
            "schema_version",
            "factor_name",
            "source_feature_id",
            "source_output_id",
            "timeframe",
            "required",
        } or payload["schema_version"] != SIGNAL_FACTOR_MAPPING_V2_SCHEMA:
            raise ValueError("Signal Factor Mapping V2 fields mismatch")
        required = payload["required"]
        if not isinstance(required, bool):
            raise ValueError("Signal Factor Mapping V2 required must be boolean")
        return cls(
            factor_name=SignalFactorName(str(payload["factor_name"])),
            source_feature_id=str(payload["source_feature_id"]),
            source_output_id=str(payload["source_output_id"]),
            timeframe=Timeframe(str(payload["timeframe"])),
            required=required,
        )


@dataclass(frozen=True, slots=True)
class SignalInputMappingConfigurationV2:
    schema_version: str
    configuration_id: ArtifactId
    configuration_hash: str
    configuration_version: str
    effective_from: datetime
    mappings: tuple[SignalFactorMappingV2, ...]
    allowed_data_eligibility: tuple[DataEligibility, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != SIGNAL_INPUT_MAPPING_V2_SCHEMA:
            raise ValueError("unsupported Signal Input Mapping V2 schema")
        require_sha256("configuration_hash", self.configuration_hash)
        require_text("configuration_version", self.configuration_version)
        require_utc_second("effective_from", self.effective_from)
        factors = tuple(item.factor_name.value for item in self.mappings)
        if factors != tuple(sorted(item.value for item in SignalFactorName)):
            raise ValueError("Signal Input Mapping V2 must exactly cover five factors")
        paths = tuple(
            (item.source_feature_id, item.source_output_id, item.timeframe.value)
            for item in self.mappings
        )
        if len(paths) != len(set(paths)):
            raise ValueError("Signal Input Mapping V2 source paths must be unique")
        if not self.allowed_data_eligibility or self.allowed_data_eligibility != tuple(
            sorted(set(self.allowed_data_eligibility), key=lambda item: item.value)
        ):
            raise ValueError("allowed Data Eligibility must be non-empty and sorted")
        require_unique_text("limitation", self.limitations)
        if self.limitations != tuple(sorted(self.limitations)):
            raise ValueError("Signal Input Mapping V2 limitations must be sorted")

    @classmethod
    def create(
        cls,
        *,
        configuration_version: str,
        effective_from: datetime,
        mappings: tuple[SignalFactorMappingV2, ...],
        allowed_data_eligibility: tuple[DataEligibility, ...],
        limitations: tuple[str, ...],
    ) -> SignalInputMappingConfigurationV2:
        ordered = tuple(sorted(mappings, key=lambda item: item.factor_name.value))
        eligibility = tuple(
            sorted(allowed_data_eligibility, key=lambda item: item.value)
        )
        ordered_limitations = tuple(sorted(limitations))
        semantic = _mapping_payload(
            configuration_version=configuration_version,
            effective_from=effective_from,
            mappings=ordered,
            allowed_data_eligibility=eligibility,
            limitations=ordered_limitations,
        )
        configuration_hash = canonical_hash(semantic)
        result = cls(
            schema_version=SIGNAL_INPUT_MAPPING_V2_SCHEMA,
            configuration_id=ArtifactId(
                f"signal-input-mapping-v2-{configuration_hash.split(':', 1)[1][:24]}"
            ),
            configuration_hash=configuration_hash,
            configuration_version=configuration_version,
            effective_from=effective_from,
            mappings=ordered,
            allowed_data_eligibility=eligibility,
            limitations=ordered_limitations,
        )
        result.verify_identity()
        return result

    def validate_requirement_policy(
        self, policy: SignalFactorRequirementPolicy
    ) -> None:
        policy.verify_identity()
        policy.validate_mapping_requirements(
            {item.factor_name: item.required for item in self.mappings}
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _mapping_payload(
            configuration_version=self.configuration_version,
            effective_from=self.effective_from,
            mappings=self.mappings,
            allowed_data_eligibility=self.allowed_data_eligibility,
            limitations=self.limitations,
        )

    def verify_identity(self) -> None:
        expected = canonical_hash(self.semantic_payload())
        if self.configuration_hash != expected:
            raise ValueError("Signal Input Mapping V2 hash mismatch")
        if str(self.configuration_id) != (
            f"signal-input-mapping-v2-{expected.split(':', 1)[1][:24]}"
        ):
            raise ValueError("Signal Input Mapping V2 identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> SignalInputMappingConfigurationV2:
        if set(payload) != {
            "schema_version",
            "configuration_id",
            "configuration_hash",
            "configuration_version",
            "effective_from",
            "mappings",
            "allowed_data_eligibility",
            "limitations",
        }:
            raise ValueError("Signal Input Mapping V2 fields mismatch")
        raw_mappings = _objects(payload["mappings"], "mappings")
        result = cls(
            schema_version=str(payload["schema_version"]),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
            configuration_version=str(payload["configuration_version"]),
            effective_from=parse_utc_second("effective_from", payload["effective_from"]),
            mappings=tuple(
                SignalFactorMappingV2.from_canonical_dict(item)
                for item in raw_mappings
            ),
            allowed_data_eligibility=tuple(
                DataEligibility(item)
                for item in _strings(
                    payload["allowed_data_eligibility"], "allowed_data_eligibility"
                )
            ),
            limitations=_strings(payload["limitations"], "limitations"),
        )
        result.verify_identity()
        return result


@dataclass(frozen=True, slots=True)
class SignalFactorObservationV3:
    schema_version: str
    factor_name: SignalFactorName
    value: Decimal | None
    source_artifact_id: ArtifactId
    source_content_hash: str
    source_feature_id: str
    source_output_id: str
    timeframe: Timeframe
    source_available_at: datetime
    freshness_state: FactorFreshnessState
    session_date: str | None
    session_lag: int | None
    elapsed_seconds: int | None
    missing_reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != SIGNAL_FACTOR_OBSERVATION_V3_SCHEMA:
            raise ValueError("unsupported Signal Factor Observation V3 schema")
        require_sha256("source_content_hash", self.source_content_hash)
        require_utc_second("source_available_at", self.source_available_at)
        if self.value is not None and (
            not isinstance(self.value, Decimal) or not self.value.is_finite()
        ):
            raise ValueError("Signal factor value must be finite Decimal")
        require_unique_text("missing_reason_code", self.missing_reason_codes)
        if self.missing_reason_codes != tuple(sorted(self.missing_reason_codes)):
            raise ValueError("Signal factor missing reasons must be sorted")
        if (self.value is None) != bool(self.missing_reason_codes):
            raise ValueError("Signal factor value and missing reasons are inconsistent")
        if self.freshness_state is not FactorFreshnessState.FRESH and self.value is not None:
            raise ValueError("non-fresh Signal factor cannot carry a value")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "factor_name": self.factor_name.value,
            "value": (
                canonical_decimal(self.value, label="Signal factor value")
                if self.value is not None
                else None
            ),
            "source_artifact_id": str(self.source_artifact_id),
            "source_content_hash": self.source_content_hash,
            "source_feature_id": self.source_feature_id,
            "source_output_id": self.source_output_id,
            "timeframe": self.timeframe.value,
            "source_available_at": canonical_datetime(self.source_available_at),
            "freshness_state": self.freshness_state.value,
            "session_date": self.session_date,
            "session_lag": self.session_lag,
            "elapsed_seconds": self.elapsed_seconds,
            "missing_reason_codes": list(self.missing_reason_codes),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> SignalFactorObservationV3:
        expected = {
            "schema_version",
            "factor_name",
            "value",
            "source_artifact_id",
            "source_content_hash",
            "source_feature_id",
            "source_output_id",
            "timeframe",
            "source_available_at",
            "freshness_state",
            "session_date",
            "session_lag",
            "elapsed_seconds",
            "missing_reason_codes",
        }
        if set(payload) != expected:
            raise ValueError("Signal Factor Observation V3 fields mismatch")
        raw_value = payload["value"]
        return cls(
            schema_version=str(payload["schema_version"]),
            factor_name=SignalFactorName(str(payload["factor_name"])),
            value=(
                parse_canonical_decimal("Signal factor value", raw_value)
                if raw_value is not None
                else None
            ),
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
            source_content_hash=str(payload["source_content_hash"]),
            source_feature_id=str(payload["source_feature_id"]),
            source_output_id=str(payload["source_output_id"]),
            timeframe=Timeframe(str(payload["timeframe"])),
            source_available_at=parse_utc_second(
                "source_available_at", payload["source_available_at"]
            ),
            freshness_state=FactorFreshnessState(str(payload["freshness_state"])),
            session_date=(
                str(payload["session_date"])
                if payload["session_date"] is not None
                else None
            ),
            session_lag=_optional_integer(payload["session_lag"]),
            elapsed_seconds=_optional_integer(payload["elapsed_seconds"]),
            missing_reason_codes=_strings(
                payload["missing_reason_codes"], "missing_reason_codes"
            ),
        )


@dataclass(frozen=True, slots=True)
class SignalObservationV3:
    schema_version: str
    observation_id: ArtifactId
    content_hash: str
    symbol: str
    decision_time: datetime
    candidate_set_id: ArtifactId
    candidate_set_hash: str
    candidate_feature_view_id: ArtifactId
    candidate_feature_view_hash: str
    mapping_configuration_id: ArtifactId
    mapping_configuration_hash: str
    requirement_policy_id: ArtifactId
    requirement_policy_hash: str
    freshness_policy_id: ArtifactId
    freshness_policy_hash: str
    trading_calendar_id: ArtifactId
    trading_calendar_hash: str
    factors: tuple[SignalFactorObservationV3, ...]
    factor_requirements_satisfied: bool
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != SIGNAL_OBSERVATION_V3_SCHEMA:
            raise ValueError("unsupported Signal Observation V3 schema")
        require_sha256("content_hash", self.content_hash)
        require_text("symbol", self.symbol)
        require_utc_second("decision_time", self.decision_time)
        for label, value in (
            ("candidate_set_hash", self.candidate_set_hash),
            ("candidate_feature_view_hash", self.candidate_feature_view_hash),
            ("mapping_configuration_hash", self.mapping_configuration_hash),
            ("requirement_policy_hash", self.requirement_policy_hash),
            ("freshness_policy_hash", self.freshness_policy_hash),
            ("trading_calendar_hash", self.trading_calendar_hash),
        ):
            require_sha256(label, value)
        names = tuple(item.factor_name.value for item in self.factors)
        if names != tuple(sorted(item.value for item in SignalFactorName)):
            raise ValueError("Signal Observation V3 must exactly cover five factors")
        require_unique_text("reason_code", self.reason_codes)
        require_unique_text("limitation", self.limitations)
        if self.reason_codes != tuple(sorted(self.reason_codes)) or self.limitations != tuple(sorted(self.limitations)):
            raise ValueError("Signal Observation V3 reasons and limitations must be sorted")

    @classmethod
    def create(
        cls,
        *,
        symbol: str,
        decision_time: datetime,
        candidate_set: CandidateSet,
        candidate_feature_view: CandidateFeatureView,
        mapping_configuration: SignalInputMappingConfigurationV2,
        requirement_policy: SignalFactorRequirementPolicy,
        freshness_policy: SignalFactorFreshnessPolicy,
        trading_calendar: TradingCalendarArtifact,
        factors: tuple[SignalFactorObservationV3, ...],
        factor_requirements_satisfied: bool,
        reason_codes: tuple[str, ...],
    ) -> SignalObservationV3:
        ordered_factors = tuple(sorted(factors, key=lambda item: item.factor_name.value))
        ordered_reasons = tuple(sorted(reason_codes))
        limitations = tuple(
            sorted(
                {
                    "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
                    "MODEL_ASSUMPTION",
                    "NO_TRADING_AUTHORITY",
                    "RESEARCH_ONLY",
                }
            )
        )
        semantic = _observation_payload(
            symbol=symbol,
            decision_time=decision_time,
            candidate_set_id=candidate_set.envelope.artifact_id,
            candidate_set_hash=candidate_set.envelope.content_hash,
            candidate_feature_view_id=candidate_feature_view.view_id,
            candidate_feature_view_hash=candidate_feature_view.content_hash,
            mapping_configuration_id=mapping_configuration.configuration_id,
            mapping_configuration_hash=mapping_configuration.configuration_hash,
            requirement_policy_id=requirement_policy.policy_id,
            requirement_policy_hash=requirement_policy.policy_hash,
            freshness_policy_id=freshness_policy.policy_id,
            freshness_policy_hash=freshness_policy.policy_hash,
            trading_calendar_id=trading_calendar.artifact_id,
            trading_calendar_hash=trading_calendar.content_hash,
            factors=ordered_factors,
            factor_requirements_satisfied=factor_requirements_satisfied,
            reason_codes=ordered_reasons,
            limitations=limitations,
        )
        content_hash = canonical_hash(semantic)
        result = cls(
            schema_version=SIGNAL_OBSERVATION_V3_SCHEMA,
            observation_id=ArtifactId(
                f"signal-observation-v3-{content_hash.split(':', 1)[1][:24]}"
            ),
            content_hash=content_hash,
            symbol=symbol,
            decision_time=decision_time,
            candidate_set_id=candidate_set.envelope.artifact_id,
            candidate_set_hash=candidate_set.envelope.content_hash,
            candidate_feature_view_id=candidate_feature_view.view_id,
            candidate_feature_view_hash=candidate_feature_view.content_hash,
            mapping_configuration_id=mapping_configuration.configuration_id,
            mapping_configuration_hash=mapping_configuration.configuration_hash,
            requirement_policy_id=requirement_policy.policy_id,
            requirement_policy_hash=requirement_policy.policy_hash,
            freshness_policy_id=freshness_policy.policy_id,
            freshness_policy_hash=freshness_policy.policy_hash,
            trading_calendar_id=trading_calendar.artifact_id,
            trading_calendar_hash=trading_calendar.content_hash,
            factors=ordered_factors,
            factor_requirements_satisfied=factor_requirements_satisfied,
            reason_codes=ordered_reasons,
            limitations=limitations,
        )
        result.verify_identity()
        return result

    def semantic_payload(self) -> dict[str, Any]:
        return _observation_payload(
            symbol=self.symbol,
            decision_time=self.decision_time,
            candidate_set_id=self.candidate_set_id,
            candidate_set_hash=self.candidate_set_hash,
            candidate_feature_view_id=self.candidate_feature_view_id,
            candidate_feature_view_hash=self.candidate_feature_view_hash,
            mapping_configuration_id=self.mapping_configuration_id,
            mapping_configuration_hash=self.mapping_configuration_hash,
            requirement_policy_id=self.requirement_policy_id,
            requirement_policy_hash=self.requirement_policy_hash,
            freshness_policy_id=self.freshness_policy_id,
            freshness_policy_hash=self.freshness_policy_hash,
            trading_calendar_id=self.trading_calendar_id,
            trading_calendar_hash=self.trading_calendar_hash,
            factors=self.factors,
            factor_requirements_satisfied=self.factor_requirements_satisfied,
            reason_codes=self.reason_codes,
            limitations=self.limitations,
        )

    def verify_identity(self) -> None:
        expected = canonical_hash(self.semantic_payload())
        if self.content_hash != expected:
            raise ValueError("Signal Observation V3 hash mismatch")
        if str(self.observation_id) != f"signal-observation-v3-{expected.split(':', 1)[1][:24]}":
            raise ValueError("Signal Observation V3 identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "observation_id": str(self.observation_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> SignalObservationV3:
        expected = {
            "schema_version",
            "observation_id",
            "content_hash",
            "symbol",
            "decision_time",
            "candidate_set_id",
            "candidate_set_hash",
            "candidate_feature_view_id",
            "candidate_feature_view_hash",
            "mapping_configuration_id",
            "mapping_configuration_hash",
            "requirement_policy_id",
            "requirement_policy_hash",
            "freshness_policy_id",
            "freshness_policy_hash",
            "trading_calendar_id",
            "trading_calendar_hash",
            "factors",
            "factor_requirements_satisfied",
            "reason_codes",
            "limitations",
        }
        if set(payload) != expected:
            raise ValueError("Signal Observation V3 fields mismatch")
        raw_satisfied = payload["factor_requirements_satisfied"]
        if not isinstance(raw_satisfied, bool):
            raise ValueError("factor_requirements_satisfied must be boolean")
        result = cls(
            schema_version=str(payload["schema_version"]),
            observation_id=ArtifactId(str(payload["observation_id"])),
            content_hash=str(payload["content_hash"]),
            symbol=str(payload["symbol"]),
            decision_time=parse_utc_second("decision_time", payload["decision_time"]),
            candidate_set_id=ArtifactId(str(payload["candidate_set_id"])),
            candidate_set_hash=str(payload["candidate_set_hash"]),
            candidate_feature_view_id=ArtifactId(str(payload["candidate_feature_view_id"])),
            candidate_feature_view_hash=str(payload["candidate_feature_view_hash"]),
            mapping_configuration_id=ArtifactId(str(payload["mapping_configuration_id"])),
            mapping_configuration_hash=str(payload["mapping_configuration_hash"]),
            requirement_policy_id=ArtifactId(str(payload["requirement_policy_id"])),
            requirement_policy_hash=str(payload["requirement_policy_hash"]),
            freshness_policy_id=ArtifactId(str(payload["freshness_policy_id"])),
            freshness_policy_hash=str(payload["freshness_policy_hash"]),
            trading_calendar_id=ArtifactId(str(payload["trading_calendar_id"])),
            trading_calendar_hash=str(payload["trading_calendar_hash"]),
            factors=tuple(
                SignalFactorObservationV3.from_canonical_dict(item)
                for item in _objects(payload["factors"], "factors")
            ),
            factor_requirements_satisfied=raw_satisfied,
            reason_codes=_strings(payload["reason_codes"], "reason_codes"),
            limitations=_strings(payload["limitations"], "limitations"),
        )
        result.verify_identity()
        return result


class SignalInputAssemblerV3:
    def assemble(
        self,
        *,
        candidate_set: CandidateSet,
        candidate_feature_view: CandidateFeatureView,
        feature_bundle: VerifiedFeatureBundleV2,
        verified_dataset: VerifiedMarketDataDataset,
        mapping_configuration: SignalInputMappingConfigurationV2,
        requirement_policy: SignalFactorRequirementPolicy,
        freshness_policy: SignalFactorFreshnessPolicy,
        trading_calendar: TradingCalendarArtifact,
        decision_time: DecisionTime,
    ) -> tuple[SignalObservationV3, ...]:
        mapping_configuration.verify_identity()
        mapping_configuration.validate_requirement_policy(requirement_policy)
        freshness_policy.verify_identity()
        candidate_feature_view.verify_identity()
        expected_view = CandidateFeatureView.create(
            candidate_set=candidate_set,
            feature_bundle=feature_bundle,
            verified_dataset=verified_dataset,
            minimum_data_eligibility=candidate_set.envelope.data_eligibility,
        )
        if expected_view != candidate_feature_view:
            raise ValueError("Candidate Feature View is not reconstructible")
        if mapping_configuration.effective_from > decision_time.value:
            raise ValueError("Signal Input Mapping V2 is not effective at DecisionTime")
        if feature_bundle.artifact.data_eligibility not in mapping_configuration.allowed_data_eligibility:
            raise ValueError("Feature Bundle Data Eligibility is not allowed")
        observations = tuple(
            self._assemble_symbol(
                symbol=symbol,
                candidate_set=candidate_set,
                candidate_feature_view=candidate_feature_view,
                feature_bundle=feature_bundle,
                mapping_configuration=mapping_configuration,
                requirement_policy=requirement_policy,
                freshness_policy=freshness_policy,
                trading_calendar=trading_calendar,
                decision_time=decision_time.value,
            )
            for symbol in candidate_feature_view.candidate_symbols
        )
        if tuple(item.symbol for item in observations) != candidate_feature_view.candidate_symbols:
            raise ValueError("Signal Observation V3 scope mismatch")
        return observations

    def _assemble_symbol(
        self,
        *,
        symbol: str,
        candidate_set: CandidateSet,
        candidate_feature_view: CandidateFeatureView,
        feature_bundle: VerifiedFeatureBundleV2,
        mapping_configuration: SignalInputMappingConfigurationV2,
        requirement_policy: SignalFactorRequirementPolicy,
        freshness_policy: SignalFactorFreshnessPolicy,
        trading_calendar: TradingCalendarArtifact,
        decision_time: datetime,
    ) -> SignalObservationV3:
        allowed_ids = {
            item.artifact_id for item in candidate_feature_view.feature_artifact_references
        }
        factors: list[SignalFactorObservationV3] = []
        reasons: set[str] = set()
        for mapping in mapping_configuration.mappings:
            artifacts = tuple(
                item.artifact
                for item in feature_bundle.artifacts
                if item.artifact.artifact_id in allowed_ids
                and item.artifact.symbol == symbol
                and item.artifact.feature_id == mapping.source_feature_id
                and item.artifact.timeframe is mapping.timeframe
            )
            if len(artifacts) != 1:
                raise ValueError("Signal V3 source Feature Artifact is not unique")
            artifact = artifacts[0]
            values = tuple(
                item for item in artifact.values if item.output_id == mapping.source_output_id
            )
            if len(values) != 1:
                raise ValueError("Signal V3 source Feature output is not unique")
            source = values[0]
            freshness = freshness_policy.assess(
                factor_name=mapping.factor_name,
                source_available_at=source.available_at,
                decision_time=decision_time,
                timeframe=mapping.timeframe,
                trading_calendar=trading_calendar,
            )
            missing = set(source.missing_reason_codes)
            value = source.value if isinstance(source.value, Decimal) else None
            if source.state is FeatureValueState.MISSING:
                value = None
            elif not isinstance(source.value, Decimal):
                missing.add("SOURCE_FEATURE_VALUE_NOT_DECIMAL")
            if freshness.state is not FactorFreshnessState.FRESH:
                value = None
                missing.update(freshness.reason_codes)
            if value is None:
                missing.add("SOURCE_FEATURE_VALUE_MISSING") if not missing else None
                reasons.add(f"FACTOR_{mapping.factor_name.value}_MISSING")
            factors.append(
                SignalFactorObservationV3(
                    schema_version=SIGNAL_FACTOR_OBSERVATION_V3_SCHEMA,
                    factor_name=mapping.factor_name,
                    value=value,
                    source_artifact_id=artifact.artifact_id,
                    source_content_hash=artifact.content_hash,
                    source_feature_id=artifact.feature_id,
                    source_output_id=source.output_id,
                    timeframe=artifact.timeframe,
                    source_available_at=source.available_at,
                    freshness_state=freshness.state,
                    session_date=freshness.session_date,
                    session_lag=freshness.session_lag,
                    elapsed_seconds=freshness.elapsed_seconds,
                    missing_reason_codes=tuple(sorted(missing)),
                )
            )
        assessment = requirement_policy.assess(
            {item.factor_name: item.value for item in factors}
        )
        reasons.update(assessment.reason_codes)
        return SignalObservationV3.create(
            symbol=symbol,
            decision_time=decision_time,
            candidate_set=candidate_set,
            candidate_feature_view=candidate_feature_view,
            mapping_configuration=mapping_configuration,
            requirement_policy=requirement_policy,
            freshness_policy=freshness_policy,
            trading_calendar=trading_calendar,
            factors=tuple(factors),
            factor_requirements_satisfied=assessment.sufficient,
            reason_codes=tuple(sorted(reasons)),
        )


def canonical_signal_input_mapping_v2(
    *, effective_from: datetime
) -> SignalInputMappingConfigurationV2:
    return SignalInputMappingConfigurationV2.create(
        configuration_version="canonical-five-factor-mapping-v2",
        effective_from=effective_from,
        mappings=(
            SignalFactorMappingV2(
                SignalFactorName.PRICE_ACTION_RETURN,
                PRICE_ACTION_FEATURE_ID,
                "return_3",
                Timeframe.DAILY,
                True,
            ),
            SignalFactorMappingV2(
                SignalFactorName.VOLUME_RATIO,
                CAPITAL_VOLUME_FEATURE_ID,
                "amount_ratio_5",
                Timeframe.DAILY,
                True,
            ),
            SignalFactorMappingV2(
                SignalFactorName.TREND_RETURN,
                MOVING_AVERAGE_FEATURE_ID,
                "price_vs_sma20_return",
                Timeframe.DAILY,
                True,
            ),
            SignalFactorMappingV2(
                SignalFactorName.PRICE_VS_VWAP_RETURN,
                VWAP_FEATURE_ID,
                "price_vs_vwap_return",
                Timeframe.MINUTE_5,
                True,
            ),
            SignalFactorMappingV2(
                SignalFactorName.OVERHEAT_RETURN,
                OVERHEAT_FEATURE_ID,
                "short_return",
                Timeframe.DAILY,
                True,
            ),
        ),
        allowed_data_eligibility=(DataEligibility.EXPLORATORY,),
        limitations=(
            "MODEL_ASSUMPTION",
            "NOT_EMPIRICALLY_VALIDATED",
            "RESEARCH_ONLY",
            "TRADING_AUTHORITY_NOT_GRANTED",
        ),
    )


def _mapping_payload(
    *,
    configuration_version: str,
    effective_from: datetime,
    mappings: tuple[SignalFactorMappingV2, ...],
    allowed_data_eligibility: tuple[DataEligibility, ...],
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": SIGNAL_INPUT_MAPPING_V2_SCHEMA,
        "configuration_version": configuration_version,
        "effective_from": canonical_datetime(effective_from),
        "mappings": [item.to_canonical_dict() for item in mappings],
        "allowed_data_eligibility": [item.value for item in allowed_data_eligibility],
        "limitations": list(limitations),
    }


def _observation_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": SIGNAL_OBSERVATION_V3_SCHEMA,
        "symbol": values["symbol"],
        "decision_time": canonical_datetime(values["decision_time"]),
        "candidate_set_id": str(values["candidate_set_id"]),
        "candidate_set_hash": values["candidate_set_hash"],
        "candidate_feature_view_id": str(values["candidate_feature_view_id"]),
        "candidate_feature_view_hash": values["candidate_feature_view_hash"],
        "mapping_configuration_id": str(values["mapping_configuration_id"]),
        "mapping_configuration_hash": values["mapping_configuration_hash"],
        "requirement_policy_id": str(values["requirement_policy_id"]),
        "requirement_policy_hash": values["requirement_policy_hash"],
        "freshness_policy_id": str(values["freshness_policy_id"]),
        "freshness_policy_hash": values["freshness_policy_hash"],
        "trading_calendar_id": str(values["trading_calendar_id"]),
        "trading_calendar_hash": values["trading_calendar_hash"],
        "factors": [item.to_canonical_dict() for item in values["factors"]],
        "factor_requirements_satisfied": values["factor_requirements_satisfied"],
        "reason_codes": list(values["reason_codes"]),
        "limitations": list(values["limitations"]),
    }


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be an array of strings")
    return tuple(value)


def _objects(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be an array of objects")
    return value


def _optional_integer(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("optional integer is invalid")
    return value


__all__ = [
    "SignalFactorMappingV2",
    "SignalFactorObservationV3",
    "SignalInputAssemblerV3",
    "SignalInputMappingConfigurationV2",
    "SignalObservationV3",
    "canonical_signal_input_mapping_v2",
]
