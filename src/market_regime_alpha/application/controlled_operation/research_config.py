"""Versioned configuration for Controlled research without B0/B1 factors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, cast

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.research.platform_v2.configs import (
    ASSUMPTIONS,
    CapitalEvolutionModelConfig,
    MarketRegimeModelConfig,
    ThemeRotationModelConfig,
)


CONTROLLED_CANDIDATE_CONFIG_SCHEMA = "controlled-candidate-discovery-config-v2"
CONTROLLED_RESEARCH_CONFIG_SCHEMA = "controlled-research-pipeline-config-v1"


@dataclass(frozen=True, slots=True)
class ControlledCandidateDiscoveryConfig:
    schema_version: str
    configuration_id: ArtifactId
    configuration_hash: str
    model_id: ModelId
    model_version: str
    market_regime_weight: float
    theme_rotation_weight: float
    capital_evolution_weight: float
    price_action_weight: float
    volume_structure_weight: float
    price_action_scale: float
    volume_ratio_scale: float
    top_n: int
    minimum_candidate_population: int
    boundary_selection_policy: str
    assumptions: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != CONTROLLED_CANDIDATE_CONFIG_SCHEMA:
            raise ValueError("unsupported Controlled Candidate configuration schema")
        require_sha256("configuration_hash", self.configuration_hash)
        weights = (
            self.market_regime_weight,
            self.theme_rotation_weight,
            self.capital_evolution_weight,
            self.price_action_weight,
            self.volume_structure_weight,
        )
        if any(value < 0 or value > 1 for value in weights) or abs(sum(weights) - 1) > 1e-12:
            raise ValueError("Controlled Candidate weights must be within [0,1] and sum to 1")
        if self.price_action_scale <= 0 or self.volume_ratio_scale <= 0:
            raise ValueError("Controlled Candidate scales must be positive")
        if self.top_n <= 0 or self.minimum_candidate_population <= 0:
            raise ValueError("Controlled Candidate population bounds must be positive")
        if self.boundary_selection_policy != "INCLUDE_ALL_BOUNDARY_TIES_V1":
            raise ValueError("Controlled Candidate requires the frozen boundary policy")
        if self.assumptions != ASSUMPTIONS:
            raise ValueError("Controlled Candidate assumptions are frozen")
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        model_id: ModelId = ModelId("controlled-candidate-discovery-v1"),
        model_version: str = "1.1.0-exploratory",
        market_regime_weight: float = 0.15,
        theme_rotation_weight: float = 0.25,
        capital_evolution_weight: float = 0.30,
        price_action_weight: float = 0.15,
        volume_structure_weight: float = 0.15,
        price_action_scale: float = 0.10,
        volume_ratio_scale: float = 2.0,
        top_n: int = 5,
        minimum_candidate_population: int = 5,
        boundary_selection_policy: str = "INCLUDE_ALL_BOUNDARY_TIES_V1",
        assumptions: tuple[str, ...] = ASSUMPTIONS,
    ) -> ControlledCandidateDiscoveryConfig:
        values = {
            "model_id": model_id,
            "model_version": model_version,
            "market_regime_weight": market_regime_weight,
            "theme_rotation_weight": theme_rotation_weight,
            "capital_evolution_weight": capital_evolution_weight,
            "price_action_weight": price_action_weight,
            "volume_structure_weight": volume_structure_weight,
            "price_action_scale": price_action_scale,
            "volume_ratio_scale": volume_ratio_scale,
            "top_n": top_n,
            "minimum_candidate_population": minimum_candidate_population,
            "boundary_selection_policy": boundary_selection_policy,
            "assumptions": assumptions,
        }
        digest = canonical_hash(_candidate_payload(**values))
        return cls(
            schema_version=CONTROLLED_CANDIDATE_CONFIG_SCHEMA,
            configuration_id=ArtifactId(f"controlled-candidate-config-{digest.split(':', 1)[1][:24]}"),
            configuration_hash=digest,
            **cast(Any, values),
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _candidate_payload(**_candidate_values(self))

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.configuration_hash:
            raise ValueError("Controlled Candidate configuration hash mismatch")
        expected = f"controlled-candidate-config-{digest.split(':', 1)[1][:24]}"
        if str(self.configuration_id) != expected:
            raise ValueError("Controlled Candidate configuration identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ControlledCandidateDiscoveryConfig:
        if set(payload) != {"configuration_id", "configuration_hash", *_candidate_payload_keys()}:
            raise ValueError("Controlled Candidate configuration fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
            model_id=ModelId(str(payload["model_id"])),
            model_version=str(payload["model_version"]),
            market_regime_weight=float(payload["market_regime_weight"]),
            theme_rotation_weight=float(payload["theme_rotation_weight"]),
            capital_evolution_weight=float(payload["capital_evolution_weight"]),
            price_action_weight=float(payload["price_action_weight"]),
            volume_structure_weight=float(payload["volume_structure_weight"]),
            price_action_scale=float(payload["price_action_scale"]),
            volume_ratio_scale=float(payload["volume_ratio_scale"]),
            top_n=int(payload["top_n"]),
            minimum_candidate_population=int(payload["minimum_candidate_population"]),
            boundary_selection_policy=str(payload["boundary_selection_policy"]),
            assumptions=_strings(payload["assumptions"], "assumptions"),
        )


@dataclass(frozen=True, slots=True)
class ControlledResearchPipelineConfig:
    schema_version: str
    configuration_id: ArtifactId
    configuration_hash: str
    market_regime: MarketRegimeModelConfig
    theme_rotation: ThemeRotationModelConfig
    capital_evolution: CapitalEvolutionModelConfig
    candidate_discovery: ControlledCandidateDiscoveryConfig
    assumptions: tuple[str, ...] = field(default=ASSUMPTIONS)

    def __post_init__(self) -> None:
        if self.schema_version != CONTROLLED_RESEARCH_CONFIG_SCHEMA:
            raise ValueError("unsupported Controlled Research configuration schema")
        require_sha256("configuration_hash", self.configuration_hash)
        if self.assumptions != ASSUMPTIONS:
            raise ValueError("Controlled Research assumptions are frozen")
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        market_regime: MarketRegimeModelConfig | None = None,
        theme_rotation: ThemeRotationModelConfig | None = None,
        capital_evolution: CapitalEvolutionModelConfig | None = None,
        candidate_discovery: ControlledCandidateDiscoveryConfig | None = None,
    ) -> ControlledResearchPipelineConfig:
        values = {
            "market_regime": market_regime or MarketRegimeModelConfig(),
            "theme_rotation": theme_rotation or ThemeRotationModelConfig(),
            "capital_evolution": capital_evolution or CapitalEvolutionModelConfig(),
            "candidate_discovery": candidate_discovery or ControlledCandidateDiscoveryConfig.create(),
            "assumptions": ASSUMPTIONS,
        }
        digest = canonical_hash(_pipeline_payload(**values))
        return cls(
            schema_version=CONTROLLED_RESEARCH_CONFIG_SCHEMA,
            configuration_id=ArtifactId(f"controlled-research-config-{digest.split(':', 1)[1][:24]}"),
            configuration_hash=digest,
            **cast(Any, values),
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _pipeline_payload(
            market_regime=self.market_regime,
            theme_rotation=self.theme_rotation,
            capital_evolution=self.capital_evolution,
            candidate_discovery=self.candidate_discovery,
            assumptions=self.assumptions,
        )

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.configuration_hash:
            raise ValueError("Controlled Research configuration hash mismatch")
        expected = f"controlled-research-config-{digest.split(':', 1)[1][:24]}"
        if str(self.configuration_id) != expected:
            raise ValueError("Controlled Research configuration identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ControlledResearchPipelineConfig:
        expected = {
            "schema_version", "configuration_id", "configuration_hash",
            "market_regime", "theme_rotation", "capital_evolution",
            "candidate_discovery", "assumptions",
        }
        if set(payload) != expected:
            raise ValueError("Controlled Research configuration fields mismatch")
        result = cls(
            schema_version=str(payload["schema_version"]),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
            market_regime=MarketRegimeModelConfig.from_canonical_dict(
                _object(payload["market_regime"], "market_regime")
            ),
            theme_rotation=ThemeRotationModelConfig.from_canonical_dict(
                _object(payload["theme_rotation"], "theme_rotation")
            ),
            capital_evolution=CapitalEvolutionModelConfig.from_canonical_dict(
                _object(payload["capital_evolution"], "capital_evolution")
            ),
            candidate_discovery=ControlledCandidateDiscoveryConfig.from_canonical_dict(
                _object(payload["candidate_discovery"], "candidate_discovery")
            ),
            assumptions=_strings(payload["assumptions"], "assumptions"),
        )
        result.verify_identity()
        return result


def _candidate_values(item: ControlledCandidateDiscoveryConfig) -> dict[str, Any]:
    return {
        "model_id": item.model_id,
        "model_version": item.model_version,
        "market_regime_weight": item.market_regime_weight,
        "theme_rotation_weight": item.theme_rotation_weight,
        "capital_evolution_weight": item.capital_evolution_weight,
        "price_action_weight": item.price_action_weight,
        "volume_structure_weight": item.volume_structure_weight,
        "price_action_scale": item.price_action_scale,
        "volume_ratio_scale": item.volume_ratio_scale,
        "top_n": item.top_n,
        "minimum_candidate_population": item.minimum_candidate_population,
        "boundary_selection_policy": item.boundary_selection_policy,
        "assumptions": item.assumptions,
    }


def _candidate_payload_keys() -> set[str]:
    return {"schema_version", *_candidate_values_names()}


def _candidate_values_names() -> tuple[str, ...]:
    return (
        "model_id", "model_version", "market_regime_weight",
        "theme_rotation_weight", "capital_evolution_weight",
        "price_action_weight", "volume_structure_weight", "price_action_scale",
        "volume_ratio_scale", "top_n", "minimum_candidate_population",
        "boundary_selection_policy", "assumptions",
    )


def _candidate_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": CONTROLLED_CANDIDATE_CONFIG_SCHEMA,
        "model_id": str(values["model_id"]),
        "model_version": values["model_version"],
        **{
            name: values[name]
            for name in _candidate_values_names()
            if name not in {"model_id", "model_version", "assumptions"}
        },
        "assumptions": list(values["assumptions"]),
    }


def _pipeline_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": CONTROLLED_RESEARCH_CONFIG_SCHEMA,
        "market_regime": values["market_regime"].to_canonical_dict(),
        "theme_rotation": values["theme_rotation"].to_canonical_dict(),
        "capital_evolution": values["capital_evolution"].to_canonical_dict(),
        "candidate_discovery": values["candidate_discovery"].to_canonical_dict(),
        "assumptions": list(values["assumptions"]),
    }


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    return tuple(value)


def _object(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


__all__ = [
    "ControlledCandidateDiscoveryConfig",
    "ControlledResearchPipelineConfig",
]
