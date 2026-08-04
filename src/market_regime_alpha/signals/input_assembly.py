"""Versioned assembly of five-factor Signal observations from Feature Bundles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
    require_unique_text,
)
from market_regime_alpha.features.materialization_v2 import VerifiedFeatureBundleV2
from market_regime_alpha.features.spine import FeatureValidationStatus
from market_regime_alpha.features.technical.catalog import (
    CAPITAL_VOLUME_FEATURE_ID,
    MOVING_AVERAGE_FEATURE_ID,
    OVERHEAT_FEATURE_ID,
    PRICE_ACTION_FEATURE_ID,
    VWAP_FEATURE_ID,
)
from market_regime_alpha.features.technical.observables import FeatureValueState
from market_regime_alpha.market_data import Timeframe
from market_regime_alpha.market_data.contracts import (
    parse_utc_second,
    require_utc_second,
)
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet


SIGNAL_FACTOR_MAPPING_SCHEMA = "signal-factor-mapping-v1"
SIGNAL_INPUT_MAPPING_CONFIGURATION_SCHEMA = "signal-input-mapping-configuration-v1"
SIGNAL_OBSERVATION_V2_SCHEMA = "signal-observation-v2"


class SignalFactorName(str, Enum):
    PRICE_ACTION_RETURN = "PRICE_ACTION_RETURN"
    VOLUME_RATIO = "VOLUME_RATIO"
    TREND_RETURN = "TREND_RETURN"
    PRICE_VS_VWAP_RETURN = "PRICE_VS_VWAP_RETURN"
    OVERHEAT_RETURN = "OVERHEAT_RETURN"


@dataclass(frozen=True, slots=True)
class SignalFactorMapping:
    factor_name: SignalFactorName
    source_feature_id: str
    source_output_id: str
    timeframe: Timeframe
    maximum_age_seconds: int
    required: bool

    def __post_init__(self) -> None:
        require_text("source_feature_id", self.source_feature_id)
        require_text("source_output_id", self.source_output_id)
        if isinstance(self.maximum_age_seconds, bool) or self.maximum_age_seconds <= 0:
            raise ValueError("maximum_age_seconds must be a positive integer")
        if not isinstance(self.required, bool):
            raise TypeError("required must be boolean")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SIGNAL_FACTOR_MAPPING_SCHEMA,
            "factor_name": self.factor_name.value,
            "source_feature_id": self.source_feature_id,
            "source_output_id": self.source_output_id,
            "timeframe": self.timeframe.value,
            "maximum_age_seconds": self.maximum_age_seconds,
            "required": self.required,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> SignalFactorMapping:
        expected = {
            "schema_version",
            "factor_name",
            "source_feature_id",
            "source_output_id",
            "timeframe",
            "maximum_age_seconds",
            "required",
        }
        if set(payload) != expected or payload["schema_version"] != SIGNAL_FACTOR_MAPPING_SCHEMA:
            raise ValueError("Signal Factor Mapping fields mismatch")
        return cls(
            factor_name=SignalFactorName(str(payload["factor_name"])),
            source_feature_id=str(payload["source_feature_id"]),
            source_output_id=str(payload["source_output_id"]),
            timeframe=Timeframe(str(payload["timeframe"])),
            maximum_age_seconds=_positive_int(
                payload["maximum_age_seconds"], "maximum_age_seconds"
            ),
            required=_boolean(payload["required"], "required"),
        )


@dataclass(frozen=True, slots=True)
class SignalInputMappingConfiguration:
    schema_version: str
    configuration_id: ArtifactId
    configuration_hash: str
    configuration_version: str
    effective_from: datetime
    mappings: tuple[SignalFactorMapping, ...]
    minimum_factor_count: int
    allowed_data_eligibility: tuple[DataEligibility, ...]
    validation_status: FeatureValidationStatus
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != SIGNAL_INPUT_MAPPING_CONFIGURATION_SCHEMA:
            raise ValueError("unsupported Signal Input Mapping Configuration schema")
        require_sha256("configuration_hash", self.configuration_hash)
        require_text("configuration_version", self.configuration_version)
        require_utc_second("effective_from", self.effective_from)
        factors = tuple(item.factor_name.value for item in self.mappings)
        expected_factors = tuple(sorted(item.value for item in SignalFactorName))
        if factors != expected_factors:
            raise ValueError("Signal Input mappings must exactly cover five factors")
        source_keys = tuple(
            (item.source_feature_id, item.source_output_id, item.timeframe.value)
            for item in self.mappings
        )
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("Signal Input mappings must have unique source paths")
        if not 1 <= self.minimum_factor_count <= len(self.mappings):
            raise ValueError("minimum_factor_count must be within the factor count")
        if not self.allowed_data_eligibility or self.allowed_data_eligibility != tuple(
            sorted(set(self.allowed_data_eligibility), key=lambda item: item.value)
        ):
            raise ValueError("allowed Data Eligibility must be non-empty and sorted")
        require_unique_text("limitation", self.limitations)
        if self.limitations != tuple(sorted(self.limitations)):
            raise ValueError("Signal Input Mapping limitations must be sorted")
        required_limitations = {
            "MODEL_ASSUMPTION",
            "NOT_EMPIRICALLY_VALIDATED",
            "RESEARCH_ONLY",
        }
        if not required_limitations.issubset(self.limitations):
            raise ValueError("Signal Input Mapping must declare research limitations")

    @classmethod
    def create(
        cls,
        *,
        configuration_version: str,
        effective_from: datetime,
        mappings: tuple[SignalFactorMapping, ...],
        minimum_factor_count: int,
        allowed_data_eligibility: tuple[DataEligibility, ...],
        validation_status: FeatureValidationStatus,
        limitations: tuple[str, ...],
    ) -> SignalInputMappingConfiguration:
        ordered_mappings = tuple(sorted(mappings, key=lambda item: item.factor_name.value))
        ordered_eligibility = tuple(
            sorted(allowed_data_eligibility, key=lambda item: item.value)
        )
        ordered_limitations = tuple(sorted(limitations))
        payload = _mapping_configuration_payload(
            configuration_version=configuration_version,
            effective_from=effective_from,
            mappings=ordered_mappings,
            minimum_factor_count=minimum_factor_count,
            allowed_data_eligibility=ordered_eligibility,
            validation_status=validation_status,
            limitations=ordered_limitations,
        )
        configuration_hash = canonical_hash(payload)
        result = cls(
            schema_version=SIGNAL_INPUT_MAPPING_CONFIGURATION_SCHEMA,
            configuration_id=ArtifactId(
                f"signal-input-mapping-{configuration_hash.split(':', 1)[1][:24]}"
            ),
            configuration_hash=configuration_hash,
            configuration_version=configuration_version,
            effective_from=effective_from,
            mappings=ordered_mappings,
            minimum_factor_count=minimum_factor_count,
            allowed_data_eligibility=ordered_eligibility,
            validation_status=validation_status,
            limitations=ordered_limitations,
        )
        result.verify_identity()
        return result

    def semantic_payload(self) -> dict[str, Any]:
        return _mapping_configuration_payload(
            configuration_version=self.configuration_version,
            effective_from=self.effective_from,
            mappings=self.mappings,
            minimum_factor_count=self.minimum_factor_count,
            allowed_data_eligibility=self.allowed_data_eligibility,
            validation_status=self.validation_status,
            limitations=self.limitations,
        )

    def verify_identity(self) -> None:
        expected_hash = canonical_hash(self.semantic_payload())
        if self.configuration_hash != expected_hash:
            raise ValueError("Signal Input Mapping payload hash mismatch")
        expected_id = f"signal-input-mapping-{expected_hash.split(':', 1)[1][:24]}"
        if str(self.configuration_id) != expected_id:
            raise ValueError("Signal Input Mapping identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> SignalInputMappingConfiguration:
        expected = {
            "schema_version",
            "configuration_id",
            "configuration_hash",
            "configuration_version",
            "effective_from",
            "mappings",
            "minimum_factor_count",
            "allowed_data_eligibility",
            "validation_status",
            "limitations",
        }
        if set(payload) != expected:
            raise ValueError("Signal Input Mapping Configuration fields mismatch")
        raw_mappings = _object_array(payload["mappings"], "mappings")
        result = cls(
            schema_version=str(payload["schema_version"]),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
            configuration_version=str(payload["configuration_version"]),
            effective_from=parse_utc_second("effective_from", payload["effective_from"]),
            mappings=tuple(
                SignalFactorMapping.from_canonical_dict(item) for item in raw_mappings
            ),
            minimum_factor_count=_positive_int(
                payload["minimum_factor_count"], "minimum_factor_count"
            ),
            allowed_data_eligibility=tuple(
                DataEligibility(item)
                for item in _string_tuple(
                    payload["allowed_data_eligibility"], "allowed_data_eligibility"
                )
            ),
            validation_status=FeatureValidationStatus(str(payload["validation_status"])),
            limitations=_string_tuple(payload["limitations"], "limitations"),
        )
        result.verify_identity()
        return result


@dataclass(frozen=True, slots=True)
class SignalFactorObservation:
    factor_name: SignalFactorName
    value: Decimal | None
    source_artifact_id: ArtifactId
    source_content_hash: str
    source_feature_id: str
    source_output_id: str
    timeframe: Timeframe
    available_at: datetime
    missing_reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_sha256("source_content_hash", self.source_content_hash)
        require_text("source_feature_id", self.source_feature_id)
        require_text("source_output_id", self.source_output_id)
        require_utc_second("available_at", self.available_at)
        if self.value is not None and (
            not isinstance(self.value, Decimal) or not self.value.is_finite()
        ):
            raise ValueError("Signal factor value must be finite Decimal")
        require_unique_text("missing_reason_code", self.missing_reason_codes)
        if self.missing_reason_codes != tuple(sorted(self.missing_reason_codes)):
            raise ValueError("Signal factor missing reasons must be sorted")
        if (self.value is None) != bool(self.missing_reason_codes):
            raise ValueError("Signal factor value and missing reasons are inconsistent")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "factor_name": self.factor_name.value,
            "value": _canonical_decimal(self.value) if self.value is not None else None,
            "source_artifact_id": str(self.source_artifact_id),
            "source_content_hash": self.source_content_hash,
            "source_feature_id": self.source_feature_id,
            "source_output_id": self.source_output_id,
            "timeframe": self.timeframe.value,
            "available_at": canonical_datetime(self.available_at),
            "missing_reason_codes": list(self.missing_reason_codes),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> SignalFactorObservation:
        expected = {
            "factor_name",
            "value",
            "source_artifact_id",
            "source_content_hash",
            "source_feature_id",
            "source_output_id",
            "timeframe",
            "available_at",
            "missing_reason_codes",
        }
        if set(payload) != expected:
            raise ValueError("Signal Factor Observation fields mismatch")
        raw_value = payload["value"]
        value = Decimal(raw_value) if isinstance(raw_value, str) else None
        if value is not None and _canonical_decimal(value) != raw_value:
            raise ValueError("Signal factor Decimal is not canonical")
        if raw_value is not None and value is None:
            raise ValueError("Signal factor value must be a decimal string or null")
        return cls(
            factor_name=SignalFactorName(str(payload["factor_name"])),
            value=value,
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
            source_content_hash=str(payload["source_content_hash"]),
            source_feature_id=str(payload["source_feature_id"]),
            source_output_id=str(payload["source_output_id"]),
            timeframe=Timeframe(str(payload["timeframe"])),
            available_at=parse_utc_second("available_at", payload["available_at"]),
            missing_reason_codes=_string_tuple(
                payload["missing_reason_codes"], "missing_reason_codes"
            ),
        )


@dataclass(frozen=True, slots=True)
class SignalObservationV2:
    schema_version: str
    observation_id: ArtifactId
    content_hash: str
    symbol: str
    decision_time: datetime
    feature_bundle_id: ArtifactId
    feature_bundle_hash: str
    mapping_configuration_id: ArtifactId
    mapping_configuration_hash: str
    factors: tuple[SignalFactorObservation, ...]
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != SIGNAL_OBSERVATION_V2_SCHEMA:
            raise ValueError("unsupported Signal Observation V2 schema")
        require_sha256("content_hash", self.content_hash)
        require_text("symbol", self.symbol)
        require_utc_second("decision_time", self.decision_time)
        require_sha256("feature_bundle_hash", self.feature_bundle_hash)
        require_sha256("mapping_configuration_hash", self.mapping_configuration_hash)
        factor_names = tuple(item.factor_name.value for item in self.factors)
        if factor_names != tuple(sorted(item.value for item in SignalFactorName)):
            raise ValueError("Signal Observation V2 must contain exactly five factors")
        require_unique_text("reason_code", self.reason_codes)
        if self.reason_codes != tuple(sorted(self.reason_codes)):
            raise ValueError("Signal Observation V2 reasons must be sorted")
        require_unique_text("limitation", self.limitations)
        if self.limitations != tuple(sorted(self.limitations)):
            raise ValueError("Signal Observation V2 limitations must be sorted")
        if "TRADING_AUTHORITY_NOT_GRANTED" not in self.limitations:
            raise ValueError("Signal Observation V2 cannot receive trading authority")

    @classmethod
    def create(
        cls,
        *,
        symbol: str,
        decision_time: datetime,
        feature_bundle_id: ArtifactId,
        feature_bundle_hash: str,
        mapping_configuration: SignalInputMappingConfiguration,
        factors: tuple[SignalFactorObservation, ...],
        reason_codes: tuple[str, ...],
    ) -> SignalObservationV2:
        ordered_factors = tuple(sorted(factors, key=lambda item: item.factor_name.value))
        ordered_reasons = tuple(sorted(reason_codes))
        limitations = (
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "MODEL_ASSUMPTION",
            "NOT_EMPIRICALLY_VALIDATED",
            "RESEARCH_ONLY",
            "TRADING_AUTHORITY_NOT_GRANTED",
        )
        payload = _observation_payload(
            symbol=symbol,
            decision_time=decision_time,
            feature_bundle_id=feature_bundle_id,
            feature_bundle_hash=feature_bundle_hash,
            mapping_configuration_id=mapping_configuration.configuration_id,
            mapping_configuration_hash=mapping_configuration.configuration_hash,
            factors=ordered_factors,
            reason_codes=ordered_reasons,
            limitations=limitations,
        )
        content_hash = canonical_hash(payload)
        result = cls(
            schema_version=SIGNAL_OBSERVATION_V2_SCHEMA,
            observation_id=ArtifactId(
                f"signal-observation-v2-{content_hash.split(':', 1)[1][:24]}"
            ),
            content_hash=content_hash,
            symbol=symbol,
            decision_time=decision_time,
            feature_bundle_id=feature_bundle_id,
            feature_bundle_hash=feature_bundle_hash,
            mapping_configuration_id=mapping_configuration.configuration_id,
            mapping_configuration_hash=mapping_configuration.configuration_hash,
            factors=ordered_factors,
            reason_codes=ordered_reasons,
            limitations=limitations,
        )
        result.verify_identity()
        return result

    def semantic_payload(self) -> dict[str, Any]:
        return _observation_payload(
            symbol=self.symbol,
            decision_time=self.decision_time,
            feature_bundle_id=self.feature_bundle_id,
            feature_bundle_hash=self.feature_bundle_hash,
            mapping_configuration_id=self.mapping_configuration_id,
            mapping_configuration_hash=self.mapping_configuration_hash,
            factors=self.factors,
            reason_codes=self.reason_codes,
            limitations=self.limitations,
        )

    def verify_identity(self) -> None:
        expected_hash = canonical_hash(self.semantic_payload())
        if self.content_hash != expected_hash:
            raise ValueError("Signal Observation V2 payload hash mismatch")
        expected_id = f"signal-observation-v2-{expected_hash.split(':', 1)[1][:24]}"
        if str(self.observation_id) != expected_id:
            raise ValueError("Signal Observation V2 identity mismatch")

    def factor(self, name: SignalFactorName) -> SignalFactorObservation:
        return next(item for item in self.factors if item.factor_name is name)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "observation_id": str(self.observation_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> SignalObservationV2:
        expected = {
            "schema_version",
            "observation_id",
            "content_hash",
            "symbol",
            "decision_time",
            "feature_bundle_id",
            "feature_bundle_hash",
            "mapping_configuration_id",
            "mapping_configuration_hash",
            "factors",
            "reason_codes",
            "limitations",
        }
        if set(payload) != expected:
            raise ValueError("Signal Observation V2 fields mismatch")
        raw_factors = _object_array(payload["factors"], "factors")
        result = cls(
            schema_version=str(payload["schema_version"]),
            observation_id=ArtifactId(str(payload["observation_id"])),
            content_hash=str(payload["content_hash"]),
            symbol=str(payload["symbol"]),
            decision_time=parse_utc_second("decision_time", payload["decision_time"]),
            feature_bundle_id=ArtifactId(str(payload["feature_bundle_id"])),
            feature_bundle_hash=str(payload["feature_bundle_hash"]),
            mapping_configuration_id=ArtifactId(
                str(payload["mapping_configuration_id"])
            ),
            mapping_configuration_hash=str(payload["mapping_configuration_hash"]),
            factors=tuple(
                SignalFactorObservation.from_canonical_dict(item) for item in raw_factors
            ),
            reason_codes=_string_tuple(payload["reason_codes"], "reason_codes"),
            limitations=_string_tuple(payload["limitations"], "limitations"),
        )
        result.verify_identity()
        return result


class SignalInputAssembler:
    def assemble(
        self,
        *,
        candidate_set: CandidateSet,
        feature_bundle: VerifiedFeatureBundleV2,
        configuration: SignalInputMappingConfiguration,
        decision_time: DecisionTime,
    ) -> tuple[SignalObservationV2, ...]:
        candidate_set.envelope.verify_payload(candidate_set.artifact_payload())
        feature_bundle.artifact.verify_identity()
        configuration.verify_identity()
        if configuration.effective_from > decision_time.value:
            raise ValueError("Signal Input Mapping is not effective at DecisionTime")
        if candidate_set.envelope.decision_time != decision_time or (
            feature_bundle.artifact.decision_time != decision_time.value
        ):
            raise ValueError("Signal Input assembly DecisionTime mismatch")
        selected_symbols = tuple(sorted(item.symbol for item in candidate_set.selected))
        if selected_symbols != feature_bundle.artifact.symbols:
            raise ValueError("Candidate symbols must exactly match Feature Bundle symbols")
        if (
            feature_bundle.artifact.data_eligibility
            not in configuration.allowed_data_eligibility
        ):
            raise ValueError("Feature Bundle Data Eligibility is not allowed")
        observations = tuple(
            self._assemble_symbol(
                symbol=symbol,
                feature_bundle=feature_bundle,
                configuration=configuration,
                decision_time=decision_time.value,
            )
            for symbol in selected_symbols
        )
        return observations

    def _assemble_symbol(
        self,
        *,
        symbol: str,
        feature_bundle: VerifiedFeatureBundleV2,
        configuration: SignalInputMappingConfiguration,
        decision_time: datetime,
    ) -> SignalObservationV2:
        factors: list[SignalFactorObservation] = []
        reasons: set[str] = set()
        for mapping in configuration.mappings:
            artifacts = tuple(
                item.artifact
                for item in feature_bundle.artifacts
                if item.artifact.symbol == symbol
                and item.artifact.feature_id == mapping.source_feature_id
                and item.artifact.timeframe is mapping.timeframe
            )
            if len(artifacts) != 1:
                raise ValueError("Signal factor source Feature Artifact is not unique")
            artifact = artifacts[0]
            values = tuple(
                item
                for item in artifact.values
                if item.output_id == mapping.source_output_id
            )
            if len(values) != 1:
                raise ValueError("Signal factor source output is not unique")
            source = values[0]
            missing_reasons = set(source.missing_reason_codes)
            value: Decimal | None
            if source.state is FeatureValueState.MISSING:
                value = None
            elif not isinstance(source.value, Decimal):
                value = None
                missing_reasons.add("SOURCE_FEATURE_VALUE_NOT_DECIMAL")
            else:
                value = source.value
            if source.available_at > decision_time:
                value = None
                missing_reasons.add("FACTOR_EVIDENCE_FROM_FUTURE")
            elif decision_time - source.available_at > timedelta(
                seconds=mapping.maximum_age_seconds
            ):
                value = None
                missing_reasons.add("FACTOR_EVIDENCE_STALE")
            if value is None:
                reasons.add(f"FACTOR_{mapping.factor_name.value}_MISSING")
                if not missing_reasons:
                    missing_reasons.add("SOURCE_FEATURE_VALUE_MISSING")
            factors.append(
                SignalFactorObservation(
                    factor_name=mapping.factor_name,
                    value=value,
                    source_artifact_id=artifact.artifact_id,
                    source_content_hash=artifact.content_hash,
                    source_feature_id=artifact.feature_id,
                    source_output_id=source.output_id,
                    timeframe=artifact.timeframe,
                    available_at=source.available_at,
                    missing_reason_codes=tuple(sorted(missing_reasons)),
                )
            )
        available_count = sum(item.value is not None for item in factors)
        if available_count < configuration.minimum_factor_count:
            reasons.add("MINIMUM_SIGNAL_FACTOR_COUNT_NOT_MET")
        if not reasons:
            reasons.add("SIGNAL_FACTORS_ASSEMBLED_FROM_VERIFIED_FEATURES")
        return SignalObservationV2.create(
            symbol=symbol,
            decision_time=decision_time,
            feature_bundle_id=feature_bundle.artifact.bundle_id,
            feature_bundle_hash=feature_bundle.artifact.content_hash,
            mapping_configuration=configuration,
            factors=tuple(factors),
            reason_codes=tuple(sorted(reasons)),
        )


def canonical_signal_input_mapping(
    *, effective_from: datetime
) -> SignalInputMappingConfiguration:
    return SignalInputMappingConfiguration.create(
        configuration_version="canonical-five-factor-mapping-v1",
        effective_from=effective_from,
        mappings=(
            SignalFactorMapping(
                SignalFactorName.PRICE_ACTION_RETURN,
                PRICE_ACTION_FEATURE_ID,
                "return_3",
                Timeframe.DAILY,
                172800,
                True,
            ),
            SignalFactorMapping(
                SignalFactorName.VOLUME_RATIO,
                CAPITAL_VOLUME_FEATURE_ID,
                "amount_ratio_5",
                Timeframe.DAILY,
                172800,
                True,
            ),
            SignalFactorMapping(
                SignalFactorName.TREND_RETURN,
                MOVING_AVERAGE_FEATURE_ID,
                "price_vs_sma20_return",
                Timeframe.DAILY,
                172800,
                True,
            ),
            SignalFactorMapping(
                SignalFactorName.PRICE_VS_VWAP_RETURN,
                VWAP_FEATURE_ID,
                "price_vs_vwap_return",
                Timeframe.MINUTE_5,
                7200,
                True,
            ),
            SignalFactorMapping(
                SignalFactorName.OVERHEAT_RETURN,
                OVERHEAT_FEATURE_ID,
                "short_return",
                Timeframe.DAILY,
                172800,
                True,
            ),
        ),
        minimum_factor_count=1,
        allowed_data_eligibility=(DataEligibility.EXPLORATORY,),
        validation_status=FeatureValidationStatus.MODEL_ASSUMPTION,
        limitations=(
            "MODEL_ASSUMPTION",
            "NOT_EMPIRICALLY_VALIDATED",
            "RESEARCH_ONLY",
            "TRADING_AUTHORITY_NOT_GRANTED",
        ),
    )


def _mapping_configuration_payload(
    *,
    configuration_version: str,
    effective_from: datetime,
    mappings: tuple[SignalFactorMapping, ...],
    minimum_factor_count: int,
    allowed_data_eligibility: tuple[DataEligibility, ...],
    validation_status: FeatureValidationStatus,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": SIGNAL_INPUT_MAPPING_CONFIGURATION_SCHEMA,
        "configuration_version": configuration_version,
        "effective_from": canonical_datetime(effective_from),
        "mappings": [item.to_canonical_dict() for item in mappings],
        "minimum_factor_count": minimum_factor_count,
        "allowed_data_eligibility": [item.value for item in allowed_data_eligibility],
        "validation_status": validation_status.value,
        "limitations": list(limitations),
    }


def _observation_payload(
    *,
    symbol: str,
    decision_time: datetime,
    feature_bundle_id: ArtifactId,
    feature_bundle_hash: str,
    mapping_configuration_id: ArtifactId,
    mapping_configuration_hash: str,
    factors: tuple[SignalFactorObservation, ...],
    reason_codes: tuple[str, ...],
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": SIGNAL_OBSERVATION_V2_SCHEMA,
        "symbol": symbol,
        "decision_time": canonical_datetime(decision_time),
        "feature_bundle_id": str(feature_bundle_id),
        "feature_bundle_hash": feature_bundle_hash,
        "mapping_configuration_id": str(mapping_configuration_id),
        "mapping_configuration_hash": mapping_configuration_hash,
        "factors": [item.to_canonical_dict() for item in factors],
        "reason_codes": list(reason_codes),
        "limitations": list(limitations),
    }


def _canonical_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    return "0" if normalized == 0 else format(normalized, "f")


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be an array of strings")
    return tuple(value)


def _object_array(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be an array of objects")
    return value


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value
