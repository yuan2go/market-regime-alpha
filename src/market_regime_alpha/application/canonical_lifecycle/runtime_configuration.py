"""Strict, typed configuration loading for restartable lifecycle processes.

The lifecycle command stores only immutable references.  This Reader rebuilds
the exact existing configuration class from a controlled local JSON locator and
then checks all three persisted bindings: identity, version and semantic hash.
No default configuration is manufactured at this boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, TypeAlias

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleConfigurationKind,
    LifecycleConfigurationReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.forecasting.path import PathForecastConfig
from market_regime_alpha.portfolio.account_authority import (
    CompleteAccountRiskConfiguration,
)
from market_regime_alpha.execution.risk_reduction import (
    RiskReductionConfirmationPolicy,
)
from market_regime_alpha.portfolio.risk_routes import (
    RiskReducingGateConfiguration,
)
from market_regime_alpha.research.platform_v2.configs import ResearchPipelineConfig
from market_regime_alpha.signals.engine import SignalModelConfig


RuntimeConfiguration: TypeAlias = (
    ResearchPipelineConfig
    | SignalModelConfig
    | PathForecastConfig
    | CompleteAccountRiskConfiguration
    | RiskReducingGateConfiguration
    | RiskReductionConfirmationPolicy
)


class RuntimeConfigurationError(ValueError):
    """A configuration locator or its persisted identity binding is invalid."""


@dataclass(frozen=True, slots=True)
class LoadedRuntimeConfiguration:
    reference: LifecycleConfigurationReference
    configuration: RuntimeConfiguration

    def __post_init__(self) -> None:
        if not isinstance(self.reference, LifecycleConfigurationReference):
            raise TypeError("reference must be a LifecycleConfigurationReference")


@dataclass(frozen=True, slots=True)
class RuntimeConfigurationSet:
    """A command-bound typed set; executable kinds are singular."""

    items: tuple[LoadedRuntimeConfiguration, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple) or any(
            not isinstance(item, LoadedRuntimeConfiguration) for item in self.items
        ):
            raise TypeError("items must contain LoadedRuntimeConfiguration values")
        expected = tuple(
            sorted(
                self.items,
                key=lambda item: item.reference.sort_key,
            )
        )
        if self.items != expected:
            raise RuntimeConfigurationError(
                "runtime configurations must follow reference order"
            )
        executable = tuple(
            item.reference.configuration_kind
            for item in self.items
            if item.reference.configuration_kind is not LifecycleConfigurationKind.GENERIC
        )
        if len(executable) != len(set(executable)):
            raise RuntimeConfigurationError(
                "each executable configuration kind must be unique"
            )

    def get(
        self, kind: LifecycleConfigurationKind
    ) -> RuntimeConfiguration | None:
        if not isinstance(kind, LifecycleConfigurationKind):
            raise TypeError("kind must be a LifecycleConfigurationKind")
        matches = tuple(
            item.configuration
            for item in self.items
            if item.reference.configuration_kind is kind
        )
        if not matches:
            return None
        if len(matches) != 1:
            raise RuntimeConfigurationError(
                f"configuration kind {kind.value} is not singular"
            )
        return matches[0]


class RuntimeConfigurationReader:
    """Read exact typed configuration JSON and reject every binding mismatch."""

    def read(
        self, reference: LifecycleConfigurationReference
    ) -> LoadedRuntimeConfiguration:
        if not isinstance(reference, LifecycleConfigurationReference):
            raise TypeError("reference must be a LifecycleConfigurationReference")
        payload = self._read_json(Path(reference.locator))
        try:
            configuration = self._restore(reference.configuration_kind, payload)
            identity, version, content_hash = _configuration_binding(configuration)
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeConfigurationError(
                f"cannot restore {reference.configuration_kind.value} configuration"
            ) from exc
        if (
            identity != reference.configuration_id
            or version != reference.configuration_version
            or content_hash != reference.content_hash
        ):
            raise RuntimeConfigurationError(
                "runtime configuration reference identity, version or hash mismatch"
            )
        return LoadedRuntimeConfiguration(
            reference=reference,
            configuration=configuration,
        )

    def read_all(
        self, references: tuple[LifecycleConfigurationReference, ...]
    ) -> RuntimeConfigurationSet:
        if not isinstance(references, tuple) or any(
            not isinstance(item, LifecycleConfigurationReference)
            for item in references
        ):
            raise TypeError(
                "references must contain LifecycleConfigurationReference values"
            )
        loaded = tuple(self.read(reference) for reference in references)
        return RuntimeConfigurationSet(loaded)

    @staticmethod
    def _read_json(path: Path) -> Mapping[str, Any]:
        try:
            raw = path.resolve().read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeConfigurationError(
                f"cannot read runtime configuration: {path}"
            ) from exc
        try:
            payload = json.loads(
                raw,
                object_pairs_hook=_reject_duplicate_json_keys,
                parse_constant=_reject_non_json_number,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            raise RuntimeConfigurationError(
                "runtime configuration is not strict JSON"
            ) from exc
        if not isinstance(payload, Mapping):
            raise RuntimeConfigurationError(
                "runtime configuration root must be an object"
            )
        return payload

    @staticmethod
    def _restore(
        kind: LifecycleConfigurationKind,
        payload: Mapping[str, Any],
    ) -> RuntimeConfiguration:
        if kind is LifecycleConfigurationKind.RESEARCH_PIPELINE:
            return ResearchPipelineConfig.from_canonical_dict(payload)
        if kind is LifecycleConfigurationKind.SIGNAL_MODEL:
            return SignalModelConfig.from_canonical_dict(dict(payload))
        if kind is LifecycleConfigurationKind.PATH_FORECAST:
            return PathForecastConfig.from_canonical_dict(dict(payload))
        if kind is LifecycleConfigurationKind.COMPLETE_ACCOUNT_RISK:
            return CompleteAccountRiskConfiguration.from_canonical_dict(payload)
        if kind is LifecycleConfigurationKind.RISK_REDUCING_GATE:
            return RiskReducingGateConfiguration.from_canonical_dict(payload)
        if kind is LifecycleConfigurationKind.RISK_REDUCTION_CONFIRMATION_POLICY:
            return RiskReductionConfirmationPolicy.from_canonical_dict(payload)
        if kind is LifecycleConfigurationKind.GENERIC:
            raise RuntimeConfigurationError(
                "GENERIC configuration has no executable typed Reader"
            )
        raise RuntimeConfigurationError(f"unsupported configuration kind: {kind}")


def _configuration_binding(
    configuration: RuntimeConfiguration,
) -> tuple[ArtifactId, str, str]:
    if isinstance(configuration, ResearchPipelineConfig):
        return (
            configuration.configuration_id,
            ResearchPipelineConfig.SCHEMA_VERSION,
            configuration.configuration_hash,
        )
    if isinstance(configuration, SignalModelConfig):
        return (
            configuration.configuration_id,
            configuration.schema_version,
            configuration.configuration_hash,
        )
    if isinstance(configuration, PathForecastConfig):
        return (
            configuration.configuration_id,
            configuration.schema_version,
            configuration.configuration_hash,
        )
    if isinstance(configuration, CompleteAccountRiskConfiguration):
        return (
            configuration.configuration_id,
            configuration.schema_version,
            configuration.configuration_hash,
        )
    if isinstance(configuration, RiskReducingGateConfiguration):
        return (
            configuration.configuration_id,
            configuration.schema_version,
            configuration.configuration_hash,
        )
    if isinstance(configuration, RiskReductionConfirmationPolicy):
        return (
            configuration.policy_id,
            configuration.schema_version,
            configuration.policy_hash,
        )
    raise TypeError("unsupported runtime configuration")


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeConfigurationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_non_json_number(value: str) -> None:
    raise RuntimeConfigurationError(f"non-JSON numeric value: {value}")
