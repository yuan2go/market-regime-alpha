"""Versioned State transition policy and cross-session series authority."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256, require_text
from market_regime_alpha.research.state_system.configuration import (
    DynamicPoolConfiguration,
    MissingDataPolicy,
    TransitionThresholds,
)
from market_regime_alpha.research.state_system.common import StateLineage


class StateAuthorityDomain(str, Enum):
    MARKET_REGIME = "MARKET_REGIME"
    ETF_ROTATION = "ETF_ROTATION"
    THEME_ROTATION = "THEME_ROTATION"
    CAPITAL_STATE = "CAPITAL_STATE"
    DYNAMIC_POOL = "DYNAMIC_POOL"


# Historical V1 evaluators had these constants embedded in their functions.
# They live here only to make V1 replay deterministic.  Every V2 executable
# path persists the same values through a content-addressed Policy authority.
_LEGACY_V1_DOMAIN_PARAMETERS: dict[StateAuthorityDomain, dict[str, Decimal]] = {
    StateAuthorityDomain.MARKET_REGIME: {
        "overheated_threshold": Decimal("0.85"),
    },
    StateAuthorityDomain.ETF_ROTATION: {
        "divergence_diffusion_threshold": Decimal("0.40"),
        "failed_score_threshold": Decimal("0"),
        "initial_pulse_threshold": Decimal("0.20"),
        "leading_amount_persistence_threshold": Decimal("0.60"),
        "leading_diffusion_threshold": Decimal("0.60"),
        "leading_score_threshold": Decimal("0.70"),
        "negative_failure_threshold": Decimal("-0.20"),
        "starting_score_threshold": Decimal("0.20"),
    },
    StateAuthorityDomain.THEME_ROTATION: {
        "concentration_distance_multiplier": Decimal("2"),
        "concentration_midpoint": Decimal("0.50"),
        "conflict_breadth_threshold": Decimal("0.45"),
        "conflict_etf_strength_threshold": Decimal("0.65"),
        "conflict_participation_threshold": Decimal("0.45"),
        "failed_score_threshold": Decimal("0.20"),
        "initial_pulse_threshold": Decimal("0.20"),
        "leader_conflict_resonance_threshold": Decimal("0.75"),
        "leading_score_threshold": Decimal("0.70"),
        "starting_score_threshold": Decimal("0.20"),
    },
    StateAuthorityDomain.CAPITAL_STATE: {
        "accumulation_price_abs_threshold": Decimal("0.20"),
        "amount_expansion_threshold": Decimal("0.50"),
        "concentration_threshold": Decimal("0.60"),
        "distribution_breadth_threshold": Decimal("-0.30"),
        "distribution_participation_threshold": Decimal("-0.30"),
        "volume_expansion_threshold": Decimal("0.50"),
    },
    StateAuthorityDomain.DYNAMIC_POOL: {},
}


@dataclass(frozen=True, slots=True)
class StateTransitionPolicy:
    policy_id: ArtifactId
    policy_version: str
    policy_hash: str
    domain: StateAuthorityDomain
    thresholds: TransitionThresholds
    transition_parameters: tuple[tuple[str, Decimal], ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text("policy_version", self.policy_version)
        require_sha256("policy_hash", self.policy_hash)
        names = tuple(name for name, _value in self.transition_parameters)
        if names != tuple(sorted(set(names))):
            raise ValueError("State transition parameter names must be unique and sorted")
        if any(not isinstance(value, Decimal) for _name, value in self.transition_parameters):
            raise TypeError("State transition parameters must be Decimal")
        if set(names) != set(_LEGACY_V1_DOMAIN_PARAMETERS[self.domain]):
            raise ValueError("State transition parameters do not match domain contract")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("State policy limitations must be unique and sorted")
        if self.policy_hash != canonical_hash(self.identity_payload()):
            raise ValueError("State policy hash does not match content")
        if str(self.policy_id) != f"state-policy:{self.policy_hash[7:]}":
            raise ValueError("State policy id does not match content")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": "state_transition_policy/v1",
            "domain": self.domain.value,
            "policy_version": self.policy_version,
            "thresholds": self.thresholds.to_canonical_dict(),
            "transition_parameters": {
                name: str(value) for name, value in self.transition_parameters
            },
            "limitations": list(self.limitations),
        }

    def parameter(self, name: str) -> Decimal:
        try:
            return dict(self.transition_parameters)[name]
        except KeyError as exc:
            raise ValueError(f"State Policy parameter is missing: {name}") from exc

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "policy_id": str(self.policy_id),
            "policy_hash": self.policy_hash,
            **self.identity_payload(),
        }

    @classmethod
    def create(
        cls,
        *,
        domain: StateAuthorityDomain,
        policy_version: str,
        thresholds: TransitionThresholds,
        transition_parameters: Mapping[str, Decimal],
        limitations: tuple[str, ...] = ("ENGINEERING_DEFAULT_NOT_ECONOMIC_TRUTH",),
    ) -> StateTransitionPolicy:
        ordered = tuple(sorted(set(limitations)))
        ordered_parameters = tuple(sorted(transition_parameters.items()))
        identity = {
            "schema": "state_transition_policy/v1",
            "domain": domain.value,
            "policy_version": policy_version,
            "thresholds": thresholds.to_canonical_dict(),
            "transition_parameters": {
                name: str(value) for name, value in ordered_parameters
            },
            "limitations": list(ordered),
        }
        digest = canonical_hash(identity)
        return cls(
            policy_id=ArtifactId(f"state-policy:{digest[7:]}"),
            policy_version=policy_version,
            policy_hash=digest,
            domain=domain,
            thresholds=thresholds,
            transition_parameters=ordered_parameters,
            limitations=ordered,
        )


@dataclass(frozen=True, slots=True)
class DynamicPoolPolicy:
    policy_id: ArtifactId
    policy_version: str
    policy_hash: str
    allowed_etf_states: tuple[str, ...]
    allowed_theme_states: tuple[str, ...]
    minimum_state_dwell_seconds: int
    minimum_evidence_coverage: Decimal
    material_change_threshold: Decimal
    missing_data_policy: MissingDataPolicy
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text("policy_version", self.policy_version)
        require_sha256("policy_hash", self.policy_hash)
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Dynamic Pool policy limitations must be unique and sorted")
        if self.policy_hash != canonical_hash(self.identity_payload()):
            raise ValueError("Dynamic Pool policy hash does not match content")
        if str(self.policy_id) != f"dynamic-pool-policy:{self.policy_hash[7:]}":
            raise ValueError("Dynamic Pool policy id does not match content")
        # Reuse the established value validation without making this Policy a
        # Model Configuration.
        self.as_legacy_configuration()

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": "dynamic_pool_policy/v1",
            "policy_version": self.policy_version,
            "allowed_etf_states": list(self.allowed_etf_states),
            "allowed_theme_states": list(self.allowed_theme_states),
            "minimum_state_dwell_seconds": self.minimum_state_dwell_seconds,
            "minimum_evidence_coverage": str(self.minimum_evidence_coverage),
            "material_change_threshold": str(self.material_change_threshold),
            "missing_data_policy": self.missing_data_policy.value,
            "limitations": list(self.limitations),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "policy_id": str(self.policy_id),
            "policy_hash": self.policy_hash,
            **self.identity_payload(),
        }

    def as_legacy_configuration(self) -> DynamicPoolConfiguration:
        # The legacy evaluator still consumes DynamicPoolConfiguration, but
        # that adapter is not the Policy authority and therefore has a
        # distinct identity.  Policy ID/hash remain explicit in StateLineage.
        return DynamicPoolConfiguration.create(
            configuration_id=ArtifactId(
                f"dynamic-pool-transition-configuration:{self.policy_hash[7:]}"
            ),
            configuration_version="adapter-v1",
            allowed_etf_states=self.allowed_etf_states,
            allowed_theme_states=self.allowed_theme_states,
            minimum_state_dwell_seconds=self.minimum_state_dwell_seconds,
            minimum_evidence_coverage=self.minimum_evidence_coverage,
            material_change_threshold=self.material_change_threshold,
        )

    @classmethod
    def create(
        cls,
        *,
        policy_version: str,
        allowed_etf_states: tuple[str, ...],
        allowed_theme_states: tuple[str, ...],
        minimum_state_dwell_seconds: int,
        minimum_evidence_coverage: Decimal,
        material_change_threshold: Decimal,
        missing_data_policy: MissingDataPolicy,
        limitations: tuple[str, ...] = ("ENGINEERING_DEFAULT_NOT_ECONOMIC_TRUTH",),
    ) -> DynamicPoolPolicy:
        ordered = tuple(sorted(set(limitations)))
        identity = {
            "schema": "dynamic_pool_policy/v1",
            "policy_version": policy_version,
            "allowed_etf_states": list(allowed_etf_states),
            "allowed_theme_states": list(allowed_theme_states),
            "minimum_state_dwell_seconds": minimum_state_dwell_seconds,
            "minimum_evidence_coverage": str(minimum_evidence_coverage),
            "material_change_threshold": str(material_change_threshold),
            "missing_data_policy": missing_data_policy.value,
            "limitations": list(ordered),
        }
        digest = canonical_hash(identity)
        return cls(
            policy_id=ArtifactId(f"dynamic-pool-policy:{digest[7:]}"),
            policy_version=policy_version,
            policy_hash=digest,
            allowed_etf_states=allowed_etf_states,
            allowed_theme_states=allowed_theme_states,
            minimum_state_dwell_seconds=minimum_state_dwell_seconds,
            minimum_evidence_coverage=minimum_evidence_coverage,
            material_change_threshold=material_change_threshold,
            missing_data_policy=missing_data_policy,
            limitations=ordered,
        )


@dataclass(frozen=True, slots=True)
class StateSeries:
    """Stable State stream identity. Runtime/date/tick are deliberately absent."""

    series_id: ArtifactId
    series_hash: str
    domain: StateAuthorityDomain
    logical_scope: str
    research_family: str
    authority_mode: str
    universe_policy_id: ArtifactId
    universe_policy_hash: str
    model_id: ModelId
    model_version: str
    configuration_id: ArtifactId
    configuration_hash: str
    state_policy_id: ArtifactId
    state_policy_version: str
    state_policy_hash: str

    def __post_init__(self) -> None:
        for label, value in (
            ("logical_scope", self.logical_scope),
            ("research_family", self.research_family),
            ("authority_mode", self.authority_mode),
            ("model_version", self.model_version),
            ("state_policy_version", self.state_policy_version),
        ):
            require_text(label, value)
        for label, value in (
            ("series_hash", self.series_hash),
            ("universe_policy_hash", self.universe_policy_hash),
            ("configuration_hash", self.configuration_hash),
            ("state_policy_hash", self.state_policy_hash),
        ):
            require_sha256(label, value)
        if self.series_hash != canonical_hash(self.identity_payload()):
            raise ValueError("State Series hash does not match content")
        if str(self.series_id) != f"state-series:{self.series_hash[7:]}":
            raise ValueError("State Series id does not match content")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": "state_series/v1",
            "domain": self.domain.value,
            "logical_scope": self.logical_scope,
            "research_family": self.research_family,
            "authority_mode": self.authority_mode,
            "universe_policy_id": str(self.universe_policy_id),
            "universe_policy_hash": self.universe_policy_hash,
            "model_id": str(self.model_id),
            "model_version": self.model_version,
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
            "state_policy_id": str(self.state_policy_id),
            "state_policy_version": self.state_policy_version,
            "state_policy_hash": self.state_policy_hash,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "series_id": str(self.series_id),
            "series_hash": self.series_hash,
            **self.identity_payload(),
        }

    @classmethod
    def create(
        cls,
        *,
        domain: StateAuthorityDomain,
        logical_scope: str,
        research_family: str,
        authority_mode: str,
        universe_policy_id: ArtifactId,
        universe_policy_hash: str,
        model_id: ModelId,
        model_version: str,
        configuration_id: ArtifactId,
        configuration_hash: str,
        state_policy_id: ArtifactId,
        state_policy_version: str,
        state_policy_hash: str,
    ) -> StateSeries:
        values = {
            "schema": "state_series/v1",
            "domain": domain.value,
            "logical_scope": logical_scope,
            "research_family": research_family,
            "authority_mode": authority_mode,
            "universe_policy_id": str(universe_policy_id),
            "universe_policy_hash": universe_policy_hash,
            "model_id": str(model_id),
            "model_version": model_version,
            "configuration_id": str(configuration_id),
            "configuration_hash": configuration_hash,
            "state_policy_id": str(state_policy_id),
            "state_policy_version": state_policy_version,
            "state_policy_hash": state_policy_hash,
        }
        digest = canonical_hash(values)
        return cls(
            series_id=ArtifactId(f"state-series:{digest[7:]}"),
            series_hash=digest,
            domain=domain,
            logical_scope=logical_scope,
            research_family=research_family,
            authority_mode=authority_mode,
            universe_policy_id=universe_policy_id,
            universe_policy_hash=universe_policy_hash,
            model_id=model_id,
            model_version=model_version,
            configuration_id=configuration_id,
            configuration_hash=configuration_hash,
            state_policy_id=state_policy_id,
            state_policy_version=state_policy_version,
            state_policy_hash=state_policy_hash,
        )


def engineering_state_transition_policy(
    domain: StateAuthorityDomain,
) -> StateTransitionPolicy:
    """Explicit V1 default; its identity is persisted, never hidden in composition."""

    if domain is StateAuthorityDomain.DYNAMIC_POOL:
        raise ValueError("Dynamic Pool uses DynamicPoolPolicy")
    return StateTransitionPolicy.create(
        domain=domain,
        policy_version="engineering-v1",
        thresholds=TransitionThresholds(
            enter_threshold=Decimal("0.60"),
            exit_threshold=Decimal("0.40"),
            hysteresis=Decimal("0.20"),
            confirmation_count=1,
            minimum_dwell_seconds=0,
            minimum_coverage=Decimal("0.50"),
            missing_data_policy=MissingDataPolicy.FAIL_CLOSED,
        ),
        transition_parameters=_LEGACY_V1_DOMAIN_PARAMETERS[domain],
    )


def engineering_dynamic_pool_policy() -> DynamicPoolPolicy:
    return DynamicPoolPolicy.create(
        policy_version="engineering-v1",
        allowed_etf_states=("LEADING", "STARTING", "STRENGTHENING"),
        allowed_theme_states=("LEADING", "STARTING", "STRENGTHENING"),
        minimum_state_dwell_seconds=0,
        minimum_evidence_coverage=Decimal("0.50"),
        material_change_threshold=Decimal("0.05"),
        missing_data_policy=MissingDataPolicy.FAIL_CLOSED,
    )


def state_series_from_dict(payload: Mapping[str, Any]) -> StateSeries:
    return StateSeries(
        series_id=ArtifactId(str(payload["series_id"])),
        series_hash=str(payload["series_hash"]),
        domain=StateAuthorityDomain(str(payload["domain"])),
        logical_scope=str(payload["logical_scope"]),
        research_family=str(payload["research_family"]),
        authority_mode=str(payload["authority_mode"]),
        universe_policy_id=ArtifactId(str(payload["universe_policy_id"])),
        universe_policy_hash=str(payload["universe_policy_hash"]),
        model_id=ModelId(str(payload["model_id"])),
        model_version=str(payload["model_version"]),
        configuration_id=ArtifactId(str(payload["configuration_id"])),
        configuration_hash=str(payload["configuration_hash"]),
        state_policy_id=ArtifactId(str(payload["state_policy_id"])),
        state_policy_version=str(payload["state_policy_version"]),
        state_policy_hash=str(payload["state_policy_hash"]),
    )


def require_transition_policy(
    lineage: StateLineage,
    policy: StateTransitionPolicy | None,
    domain: StateAuthorityDomain,
) -> StateTransitionPolicy | None:
    """Require exact policy content on V2 lineage while retaining V1 replay."""

    if lineage.state_policy_id is None:
        if policy is not None:
            raise ValueError("Legacy State lineage cannot acquire a V2 State Policy")
        return None
    if policy is None:
        raise ValueError("State V2 evaluation requires its State Policy")
    if (
        policy.domain is not domain
        or lineage.state_policy_id != policy.policy_id
        or lineage.state_policy_version != policy.policy_version
        or lineage.state_policy_hash != policy.policy_hash
    ):
        raise ValueError("State evaluation Policy lineage mismatch")
    if policy.thresholds.missing_data_policy is not MissingDataPolicy.FAIL_CLOSED:
        raise ValueError("State Policy missing-data behavior is not implemented")
    return policy


def state_transition_parameter(
    policy: StateTransitionPolicy | None,
    domain: StateAuthorityDomain,
    name: str,
) -> Decimal:
    """Resolve V2 Policy values or an explicitly named V1 replay constant."""

    if policy is not None:
        if policy.domain is not domain:
            raise ValueError("State Policy domain mismatch")
        return policy.parameter(name)
    try:
        return _LEGACY_V1_DOMAIN_PARAMETERS[domain][name]
    except KeyError as exc:
        raise ValueError(f"Legacy V1 State parameter is missing: {name}") from exc


__all__ = [
    "DynamicPoolPolicy",
    "StateAuthorityDomain",
    "StateSeries",
    "StateTransitionPolicy",
    "engineering_dynamic_pool_policy",
    "engineering_state_transition_policy",
    "require_transition_policy",
    "state_transition_parameter",
    "state_series_from_dict",
]
