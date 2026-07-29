"""Strict, versioned and content-addressed Research Layer model configurations."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, ClassVar, Mapping, Self, TypeVar, cast

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.evidence.canonical import canonical_hash


ASSUMPTIONS = ("MODEL_ASSUMPTION", "NOT_EMPIRICALLY_VALIDATED")


def _identified(
    prefix: str, payload: Mapping[str, Any]
) -> tuple[str, ArtifactId]:
    value = canonical_hash(payload)
    return value, ArtifactId(f"{prefix}-{value.split(':', 1)[1][:24]}")


def _require_unit_weights(values: tuple[float, ...]) -> None:
    if any(value < 0.0 or value > 1.0 for value in values):
        raise ValueError("model weights must be within [0, 1]")
    if abs(sum(values) - 1.0) > 1e-12:
        raise ValueError("model weights must sum to 1")


class _IdentifiedConfig:
    SCHEMA_VERSION: ClassVar[str]
    ID_PREFIX: ClassVar[str]
    configuration_hash: str
    configuration_id: ArtifactId

    def semantic_payload(self) -> dict[str, Any]:
        raise NotImplementedError

    def _bind_identity(self) -> None:
        value, identity = _identified(self.ID_PREFIX, self.semantic_payload())
        object.__setattr__(self, "configuration_hash", value)
        object.__setattr__(self, "configuration_id", identity)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "configuration_hash": self.configuration_hash,
            "configuration_id": str(self.configuration_id),
        }


ConfigT = TypeVar("ConfigT", bound=_IdentifiedConfig)


@dataclass(frozen=True, slots=True)
class MarketRegimeModelConfig(_IdentifiedConfig):
    SCHEMA_VERSION: ClassVar[str] = "market-regime-model-config-v1"
    ID_PREFIX: ClassVar[str] = "market-regime-config"

    model_id: ModelId = ModelId("market-regime-mr2a-adapter-v0")
    model_version: str = "0.1.0"
    direction_weight: float = 0.25
    breadth_weight: float = 0.25
    liquidity_weight: float = 0.20
    volatility_weight: float = 0.20
    limit_structure_weight: float = 0.10
    direction_scale: float = 0.02
    liquidity_scale: float = 0.50
    volatility_scale: float = 0.04
    risk_on_threshold: float = 0.35
    neutral_threshold: float = -0.10
    extreme_risk_threshold: float = -0.60
    restricted_exposure: float = 0.50
    minimum_coverage: float = 1.0
    assumptions: tuple[str, ...] = ASSUMPTIONS
    configuration_hash: str = field(init=False)
    configuration_id: ArtifactId = field(init=False)

    def __post_init__(self) -> None:
        _require_unit_weights(
            (
                self.direction_weight,
                self.breadth_weight,
                self.liquidity_weight,
                self.volatility_weight,
                self.limit_structure_weight,
            )
        )
        if not (
            self.extreme_risk_threshold
            < self.neutral_threshold
            < self.risk_on_threshold
        ):
            raise ValueError("Market Regime thresholds must be ordered")
        if any(
            value <= 0.0
            for value in (
                self.direction_scale,
                self.liquidity_scale,
                self.volatility_scale,
            )
        ):
            raise ValueError("Market Regime scales must be positive")
        if not 0.0 <= self.restricted_exposure <= 1.0:
            raise ValueError("restricted_exposure must be within [0, 1]")
        self._bind_identity()

    def semantic_payload(self) -> dict[str, Any]:
        return _simple_payload(self)

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> Self:
        return _simple_from_payload(cls, payload)


@dataclass(frozen=True, slots=True)
class ThemeRotationModelConfig(_IdentifiedConfig):
    SCHEMA_VERSION: ClassVar[str] = "theme-rotation-model-config-v1"
    ID_PREFIX: ClassVar[str] = "theme-rotation-config"

    model_id: ModelId = ModelId("theme-rotation-v0")
    model_version: str = "0.1.0"
    relative_strength_1d_weight: float = 0.05
    relative_strength_3d_weight: float = 0.10
    relative_strength_5d_weight: float = 0.15
    relative_strength_10d_weight: float = 0.10
    amount_expansion_weight: float = 0.15
    breadth_weight: float = 0.10
    new_high_breadth_weight: float = 0.10
    leader_strength_weight: float = 0.10
    participation_change_weight: float = 0.05
    persistence_weight: float = 0.10
    return_scale: float = 0.05
    amount_scale: float = 0.50
    leading_threshold: float = 0.60
    strengthening_threshold: float = 0.30
    starting_threshold: float = 0.05
    weakening_threshold: float = -0.25
    divergence_participation_threshold: float = -0.05
    divergence_breadth_threshold: float = 0.35
    minimum_confidence: float = 0.60
    assumptions: tuple[str, ...] = ASSUMPTIONS
    configuration_hash: str = field(init=False)
    configuration_id: ArtifactId = field(init=False)

    def __post_init__(self) -> None:
        _require_unit_weights(
            (
                self.relative_strength_1d_weight,
                self.relative_strength_3d_weight,
                self.relative_strength_5d_weight,
                self.relative_strength_10d_weight,
                self.amount_expansion_weight,
                self.breadth_weight,
                self.new_high_breadth_weight,
                self.leader_strength_weight,
                self.participation_change_weight,
                self.persistence_weight,
            )
        )
        if not (
            self.weakening_threshold
            < self.starting_threshold
            < self.strengthening_threshold
            < self.leading_threshold
        ):
            raise ValueError("Theme Rotation thresholds must be ordered")
        if self.return_scale <= 0.0 or self.amount_scale <= 0.0:
            raise ValueError("Theme Rotation scales must be positive")
        self._bind_identity()

    def semantic_payload(self) -> dict[str, Any]:
        return _simple_payload(self)

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> Self:
        return _simple_from_payload(cls, payload)


@dataclass(frozen=True, slots=True)
class CapitalEvolutionModelConfig(_IdentifiedConfig):
    SCHEMA_VERSION: ClassVar[str] = "capital-evolution-model-config-v1"
    ID_PREFIX: ClassVar[str] = "capital-evolution-config"

    model_id: ModelId = ModelId("capital-evolution-v0")
    model_version: str = "0.1.0"
    relative_strength_weight: float = 0.15
    etf_amount_weight: float = 0.10
    theme_amount_weight: float = 0.15
    breadth_weight: float = 0.10
    new_high_breadth_weight: float = 0.05
    leader_strength_weight: float = 0.10
    participation_weight: float = 0.10
    concentration_weight: float = 0.05
    rank_persistence_weight: float = 0.05
    amount_persistence_weight: float = 0.05
    diffusion_weight: float = 0.10
    accumulation_threshold: float = 0.10
    ignition_threshold: float = 0.30
    diffusion_threshold: float = 0.50
    acceleration_threshold: float = 0.70
    exhaustion_threshold: float = -0.25
    collapse_threshold: float = -0.60
    divergence_concentration_threshold: float = 0.75
    divergence_participation_threshold: float = -0.05
    minimum_theme_confidence: float = 0.60
    assumptions: tuple[str, ...] = ASSUMPTIONS
    configuration_hash: str = field(init=False)
    configuration_id: ArtifactId = field(init=False)

    def __post_init__(self) -> None:
        _require_unit_weights(
            (
                self.relative_strength_weight,
                self.etf_amount_weight,
                self.theme_amount_weight,
                self.breadth_weight,
                self.new_high_breadth_weight,
                self.leader_strength_weight,
                self.participation_weight,
                self.concentration_weight,
                self.rank_persistence_weight,
                self.amount_persistence_weight,
                self.diffusion_weight,
            )
        )
        if not (
            self.collapse_threshold
            < self.exhaustion_threshold
            < self.accumulation_threshold
            < self.ignition_threshold
            < self.diffusion_threshold
            < self.acceleration_threshold
        ):
            raise ValueError("Capital Evolution thresholds must be ordered")
        self._bind_identity()

    def semantic_payload(self) -> dict[str, Any]:
        return _simple_payload(self)

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> Self:
        return _simple_from_payload(cls, payload)


@dataclass(frozen=True, slots=True)
class CandidateDiscoveryModelConfig(_IdentifiedConfig):
    SCHEMA_VERSION: ClassVar[str] = "candidate-discovery-model-config-v2"
    ID_PREFIX: ClassVar[str] = "candidate-discovery-config"

    model_id: ModelId = ModelId("candidate-discovery-v2")
    model_version: str = "2.0.0"
    market_regime_weight: float = 0.10
    theme_rotation_weight: float = 0.25
    capital_evolution_weight: float = 0.35
    b0_momentum_weight: float = 0.15
    b1_balanced_weight: float = 0.15
    top_n: int = 5
    minimum_candidate_population: int = 5
    assumptions: tuple[str, ...] = ASSUMPTIONS
    configuration_hash: str = field(init=False)
    configuration_id: ArtifactId = field(init=False)

    def __post_init__(self) -> None:
        _require_unit_weights(
            (
                self.market_regime_weight,
                self.theme_rotation_weight,
                self.capital_evolution_weight,
                self.b0_momentum_weight,
                self.b1_balanced_weight,
            )
        )
        if self.top_n <= 0 or self.minimum_candidate_population <= 0:
            raise ValueError("Candidate Discovery population bounds must be positive")
        self._bind_identity()

    def semantic_payload(self) -> dict[str, Any]:
        return _simple_payload(self)

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> Self:
        return _simple_from_payload(cls, payload)


@dataclass(frozen=True, slots=True)
class ResearchPipelineConfig(_IdentifiedConfig):
    SCHEMA_VERSION: ClassVar[str] = "research-pipeline-config-v1"
    ID_PREFIX: ClassVar[str] = "research-pipeline-config"

    market_regime: MarketRegimeModelConfig
    theme_rotation: ThemeRotationModelConfig
    capital_evolution: CapitalEvolutionModelConfig
    candidate_discovery: CandidateDiscoveryModelConfig
    assumptions: tuple[str, ...] = ASSUMPTIONS
    configuration_hash: str = field(init=False)
    configuration_id: ArtifactId = field(init=False)

    def __post_init__(self) -> None:
        if self.assumptions != ASSUMPTIONS:
            raise ValueError("Research Pipeline assumptions are frozen for V1")
        self._bind_identity()

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "market_regime": self.market_regime.to_canonical_dict(),
            "theme_rotation": self.theme_rotation.to_canonical_dict(),
            "capital_evolution": self.capital_evolution.to_canonical_dict(),
            "candidate_discovery": self.candidate_discovery.to_canonical_dict(),
            "assumptions": list(self.assumptions),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ResearchPipelineConfig:
        expected = {
            "schema_version",
            "market_regime",
            "theme_rotation",
            "capital_evolution",
            "candidate_discovery",
            "assumptions",
            "configuration_hash",
            "configuration_id",
        }
        if set(payload) != expected or payload["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("ResearchPipelineConfig fields or schema mismatch")
        result = cls(
            market_regime=MarketRegimeModelConfig.from_canonical_dict(
                _mapping(payload["market_regime"])
            ),
            theme_rotation=ThemeRotationModelConfig.from_canonical_dict(
                _mapping(payload["theme_rotation"])
            ),
            capital_evolution=CapitalEvolutionModelConfig.from_canonical_dict(
                _mapping(payload["capital_evolution"])
            ),
            candidate_discovery=CandidateDiscoveryModelConfig.from_canonical_dict(
                _mapping(payload["candidate_discovery"])
            ),
            assumptions=tuple(str(item) for item in _array(payload["assumptions"])),
        )
        _verify_identity(result, payload)
        return result


def default_research_pipeline_config() -> ResearchPipelineConfig:
    return ResearchPipelineConfig(
        market_regime=MarketRegimeModelConfig(),
        theme_rotation=ThemeRotationModelConfig(),
        capital_evolution=CapitalEvolutionModelConfig(),
        candidate_discovery=CandidateDiscoveryModelConfig(),
    )


def _simple_payload(value: _IdentifiedConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {"schema_version": value.SCHEMA_VERSION}
    for item_field in fields(cast(Any, value)):
        name = item_field.name
        if name in {"configuration_hash", "configuration_id"}:
            continue
        item = getattr(value, name)
        if isinstance(item, ModelId):
            payload[name] = str(item)
        elif isinstance(item, tuple):
            payload[name] = list(item)
        else:
            payload[name] = item
    return payload


def _simple_from_payload(
    cls: type[ConfigT], payload: Mapping[str, Any]
) -> ConfigT:
    field_names = tuple(
        item.name
        for item in fields(cast(Any, cls))
        if item.name not in {"configuration_hash", "configuration_id"}
    )
    expected = {
        "schema_version",
        *field_names,
        "configuration_hash",
        "configuration_id",
    }
    if set(payload) != expected or payload["schema_version"] != cls.SCHEMA_VERSION:
        raise ValueError(f"{cls.__name__} fields or schema mismatch")
    kwargs: dict[str, Any] = {}
    for name in field_names:
        item = payload[name]
        if name == "model_id":
            kwargs[name] = ModelId(str(item))
        elif name == "assumptions":
            kwargs[name] = tuple(str(value) for value in _array(item))
        else:
            kwargs[name] = item
    result = cls(**kwargs)
    _verify_identity(result, payload)
    return result


def _verify_identity(
    value: _IdentifiedConfig, payload: Mapping[str, Any]
) -> None:
    if (
        value.configuration_hash != payload["configuration_hash"]
        or str(value.configuration_id) != payload["configuration_id"]
    ):
        raise ValueError("configuration identity mismatch")


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("configuration value must be an object")
    return value


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("configuration value must be an array")
    return value
