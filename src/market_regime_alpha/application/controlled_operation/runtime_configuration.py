"""Content-addressed configuration and model manifests for Controlled operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from market_regime_alpha.application.controlled_operation.research_config import (
    ControlledResearchPipelineConfig,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.features.spine import FeatureSetConfiguration
from market_regime_alpha.forecasting.path import PathForecastConfig
from market_regime_alpha.signals.decimal_model import SignalModelConfigurationV2
from market_regime_alpha.signals.input_v3 import SignalInputMappingConfigurationV2
from market_regime_alpha.signals.policies import (
    SignalFactorFreshnessPolicy,
    SignalFactorRequirementPolicy,
)


CONTROLLED_RUNTIME_CONFIGURATION_SCHEMA = "controlled-operation-runtime-configuration-v1"
CONTROLLED_MODEL_MANIFEST_SCHEMA = "controlled-operation-model-manifest-v1"


@dataclass(frozen=True, slots=True)
class ControlledOperationRuntimeConfiguration:
    schema_version: str
    configuration_id: ArtifactId
    configuration_hash: str
    static_feature_set: FeatureSetConfiguration
    intraday_feature_set: FeatureSetConfiguration
    research: ControlledResearchPipelineConfig
    signal_model: SignalModelConfigurationV2
    signal_mapping: SignalInputMappingConfigurationV2
    signal_requirement: SignalFactorRequirementPolicy
    signal_freshness: SignalFactorFreshnessPolicy
    path_forecast: PathForecastConfig
    feature_max_workers: int
    minute_concurrency_limit: int
    minute_per_request_timeout_seconds: float
    minute_max_attempts: int
    minute_retry_backoff_seconds: float
    provider_profile_id: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != CONTROLLED_RUNTIME_CONFIGURATION_SCHEMA:
            raise ValueError("unsupported Controlled runtime configuration schema")
        require_sha256("configuration_hash", self.configuration_hash)
        if self.feature_max_workers <= 0 or self.minute_concurrency_limit <= 0:
            raise ValueError("Controlled runtime worker bounds must be positive")
        if self.minute_per_request_timeout_seconds <= 0 or self.minute_max_attempts <= 0:
            raise ValueError("Controlled minute timeout/attempt bounds must be positive")
        if self.minute_retry_backoff_seconds < 0:
            raise ValueError("Controlled minute retry backoff cannot be negative")
        if not self.provider_profile_id.strip():
            raise ValueError("Controlled minute provider profile is required")
        if not self.limitations or self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Controlled runtime limitations must be non-empty and sorted")
        self.signal_mapping.validate_requirement_policy(self.signal_requirement)
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        static_feature_set: FeatureSetConfiguration,
        intraday_feature_set: FeatureSetConfiguration,
        research: ControlledResearchPipelineConfig,
        signal_model: SignalModelConfigurationV2,
        signal_mapping: SignalInputMappingConfigurationV2,
        signal_requirement: SignalFactorRequirementPolicy,
        signal_freshness: SignalFactorFreshnessPolicy,
        path_forecast: PathForecastConfig,
        feature_max_workers: int = 4,
        minute_concurrency_limit: int = 5,
        minute_per_request_timeout_seconds: float = 3.0,
        minute_max_attempts: int = 2,
        minute_retry_backoff_seconds: float = 0.1,
        provider_profile_id: str = "tencent-public-minute-controlled-v1",
        limitations: tuple[str, ...] = (
            "CONTENT_ADDRESSED_CONFIGURATION",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "TRADING_AUTHORITY_NOT_GRANTED",
        ),
    ) -> ControlledOperationRuntimeConfiguration:
        values: dict[str, Any] = {
            "static_feature_set": static_feature_set,
            "intraday_feature_set": intraday_feature_set,
            "research": research,
            "signal_model": signal_model,
            "signal_mapping": signal_mapping,
            "signal_requirement": signal_requirement,
            "signal_freshness": signal_freshness,
            "path_forecast": path_forecast,
            "feature_max_workers": feature_max_workers,
            "minute_concurrency_limit": minute_concurrency_limit,
            "minute_per_request_timeout_seconds": float(minute_per_request_timeout_seconds),
            "minute_max_attempts": minute_max_attempts,
            "minute_retry_backoff_seconds": float(minute_retry_backoff_seconds),
            "provider_profile_id": provider_profile_id,
            "limitations": tuple(sorted(set(limitations))),
        }
        digest = canonical_hash(_payload(**values))
        return cls(
            schema_version=CONTROLLED_RUNTIME_CONFIGURATION_SCHEMA,
            configuration_id=ArtifactId(f"controlled-runtime-config-{digest.split(':', 1)[1][:24]}"),
            configuration_hash=digest,
            **values,
        )

    @property
    def model_manifest_payload(self) -> dict[str, Any]:
        return {
            "schema_version": CONTROLLED_MODEL_MANIFEST_SCHEMA,
            "models": [
                {
                    "model_id": str(item[0]),
                    "model_version": item[1],
                }
                for item in sorted(
                    {
                        (self.research.market_regime.model_id, self.research.market_regime.model_version),
                        (self.research.theme_rotation.model_id, self.research.theme_rotation.model_version),
                        (self.research.capital_evolution.model_id, self.research.capital_evolution.model_version),
                        (
                            self.research.candidate_discovery.model_id,
                            self.research.candidate_discovery.model_version,
                        ),
                        (self.signal_model.model_id, self.signal_model.model_version),
                        (self.path_forecast.model_id, self.path_forecast.model_version),
                    },
                    key=lambda item: (str(item[0]), item[1]),
                )
            ],
            "limitations": [
                "NO_MODEL_AUTO_PROMOTION",
                "PATH_SAMPLE_AUTHORITY_NOT_ESTABLISHED",
                "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            ],
        }

    @property
    def model_manifest_hash(self) -> str:
        return canonical_hash(self.model_manifest_payload)

    @property
    def model_manifest_id(self) -> ArtifactId:
        return ArtifactId(
            f"controlled-model-manifest-{self.model_manifest_hash.split(':', 1)[1][:24]}"
        )

    @property
    def configuration_hashes(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    self.configuration_hash,
                    self.static_feature_set.content_hash,
                    self.intraday_feature_set.content_hash,
                    self.research.configuration_hash,
                    self.signal_model.configuration_hash,
                    self.signal_mapping.configuration_hash,
                    self.signal_requirement.policy_hash,
                    self.signal_freshness.policy_hash,
                    self.path_forecast.configuration_hash,
                }
            )
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _payload(**{name: getattr(self, name) for name in _value_names()})

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.configuration_hash:
            raise ValueError("Controlled runtime configuration hash mismatch")
        expected = f"controlled-runtime-config-{digest.split(':', 1)[1][:24]}"
        if str(self.configuration_id) != expected:
            raise ValueError("Controlled runtime configuration identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ControlledOperationRuntimeConfiguration:
        if set(payload) != {"configuration_id", "configuration_hash", *_payload_keys()}:
            raise ValueError("Controlled runtime configuration fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
            static_feature_set=FeatureSetConfiguration.from_canonical_dict(
                _object(payload["static_feature_set"], "static feature set")
            ),
            intraday_feature_set=FeatureSetConfiguration.from_canonical_dict(
                _object(payload["intraday_feature_set"], "intraday feature set")
            ),
            research=ControlledResearchPipelineConfig.from_canonical_dict(
                _object(payload["research"], "research")
            ),
            signal_model=SignalModelConfigurationV2.from_canonical_dict(
                _object(payload["signal_model"], "signal model")
            ),
            signal_mapping=SignalInputMappingConfigurationV2.from_canonical_dict(
                _object(payload["signal_mapping"], "signal mapping")
            ),
            signal_requirement=SignalFactorRequirementPolicy.from_canonical_dict(
                _object(payload["signal_requirement"], "signal requirement")
            ),
            signal_freshness=SignalFactorFreshnessPolicy.from_canonical_dict(
                _object(payload["signal_freshness"], "signal freshness")
            ),
            path_forecast=PathForecastConfig.from_canonical_dict(
                dict(_object(payload["path_forecast"], "path forecast"))
            ),
            feature_max_workers=int(payload["feature_max_workers"]),
            minute_concurrency_limit=int(payload["minute_concurrency_limit"]),
            minute_per_request_timeout_seconds=float(
                payload["minute_per_request_timeout_seconds"]
            ),
            minute_max_attempts=int(payload["minute_max_attempts"]),
            minute_retry_backoff_seconds=float(payload["minute_retry_backoff_seconds"]),
            provider_profile_id=str(payload["provider_profile_id"]),
            limitations=_strings(payload["limitations"], "limitations"),
        )


def _value_names() -> tuple[str, ...]:
    return (
        "static_feature_set", "intraday_feature_set", "research", "signal_model",
        "signal_mapping", "signal_requirement", "signal_freshness", "path_forecast",
        "feature_max_workers", "minute_concurrency_limit",
        "minute_per_request_timeout_seconds", "minute_max_attempts",
        "minute_retry_backoff_seconds", "provider_profile_id", "limitations",
    )


def _payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": CONTROLLED_RUNTIME_CONFIGURATION_SCHEMA,
        "static_feature_set": values["static_feature_set"].to_canonical_dict(),
        "intraday_feature_set": values["intraday_feature_set"].to_canonical_dict(),
        "research": values["research"].to_canonical_dict(),
        "signal_model": values["signal_model"].to_canonical_dict(),
        "signal_mapping": values["signal_mapping"].to_canonical_dict(),
        "signal_requirement": values["signal_requirement"].to_canonical_dict(),
        "signal_freshness": values["signal_freshness"].to_canonical_dict(),
        "path_forecast": values["path_forecast"].to_canonical_dict(),
        "feature_max_workers": values["feature_max_workers"],
        "minute_concurrency_limit": values["minute_concurrency_limit"],
        "minute_per_request_timeout_seconds": values["minute_per_request_timeout_seconds"],
        "minute_max_attempts": values["minute_max_attempts"],
        "minute_retry_backoff_seconds": values["minute_retry_backoff_seconds"],
        "provider_profile_id": values["provider_profile_id"],
        "limitations": list(values["limitations"]),
    }


def _payload_keys() -> set[str]:
    return {"schema_version", *_value_names()}


def _object(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    return tuple(value)


__all__ = [
    "CONTROLLED_MODEL_MANIFEST_SCHEMA",
    "CONTROLLED_RUNTIME_CONFIGURATION_SCHEMA",
    "ControlledOperationRuntimeConfiguration",
]
