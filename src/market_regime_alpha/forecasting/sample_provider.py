"""Authority boundary for historical PathForecast samples.

The default implementation is intentionally unavailable: a current Signal is not
historical outcome evidence and must never be converted into invented samples.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.evidence.canonical import require_unique_text
from market_regime_alpha.forecasting.path import PathForecastConfig, PathForecastSample
from market_regime_alpha.signals.contracts import SignalSnapshot


@dataclass(frozen=True, slots=True)
class PathForecastSampleBatch:
    samples: tuple[PathForecastSample, ...]
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        identities = tuple(str(item.sample_id) for item in self.samples)
        if len(identities) != len(set(identities)):
            raise ValueError("PathForecast sample provider returned duplicate samples")
        require_unique_text("reason_code", self.reason_codes)
        require_unique_text("limitation", self.limitations)
        if self.reason_codes != tuple(sorted(self.reason_codes)):
            raise ValueError("PathForecast sample reason codes must be sorted")
        if self.limitations != tuple(sorted(self.limitations)):
            raise ValueError("PathForecast sample limitations must be sorted")
        if not self.samples and not self.reason_codes:
            raise ValueError("empty PathForecast sample batch requires a reason")


class PathForecastSampleProvider(Protocol):
    """Read-only provider of already-observed, available historical samples."""

    def load_samples(
        self,
        *,
        signal_snapshot: SignalSnapshot,
        configuration: PathForecastConfig,
        decision_time: DecisionTime,
    ) -> PathForecastSampleBatch: ...


class UnavailablePathForecastSampleProvider:
    """Fail-closed default until H9 supplies qualified sample authority."""

    def load_samples(
        self,
        *,
        signal_snapshot: SignalSnapshot,
        configuration: PathForecastConfig,
        decision_time: DecisionTime,
    ) -> PathForecastSampleBatch:
        del signal_snapshot, configuration, decision_time
        return PathForecastSampleBatch(
            samples=(),
            reason_codes=("FORMAL_PATH_SAMPLE_PROVIDER_NOT_CONFIGURED",),
            limitations=(
                "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
                "H9_SAMPLE_AUTHORITY_NOT_IMPLEMENTED",
                "NO_SAMPLES_FABRICATED_FROM_CURRENT_SIGNAL",
            ),
        )


__all__ = [
    "PathForecastSampleBatch",
    "PathForecastSampleProvider",
    "UnavailablePathForecastSampleProvider",
]
