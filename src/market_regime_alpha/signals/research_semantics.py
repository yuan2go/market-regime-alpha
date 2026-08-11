"""Unambiguous research measures projected from immutable Signal artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.signals.decimal_model import CanonicalSignalSnapshotV3


class CalibratedProbabilityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    NOT_ESTIMABLE_UNCALIBRATED = "NOT_ESTIMABLE_UNCALIBRATED"


@dataclass(frozen=True, slots=True)
class SignalResearchMeasures:
    source_signal_id: ArtifactId
    source_signal_hash: str
    data_completeness: Decimal
    signal_strength: Decimal | None
    calibrated_probability: Decimal | None
    calibrated_probability_status: CalibratedProbabilityStatus
    limitations: tuple[str, ...]


def project_signal_research_measures(
    snapshot: CanonicalSignalSnapshotV3,
) -> SignalResearchMeasures:
    """Interpret legacy V3 ``confidence`` by its actual coverage semantics.

    V3 identities remain immutable for replay.  Research consumers use this
    projection so coverage is never presented as predictive confidence or a
    calibrated probability.
    """

    return SignalResearchMeasures(
        source_signal_id=snapshot.artifact_id,
        source_signal_hash=snapshot.envelope.content_hash,
        data_completeness=snapshot.confidence,
        signal_strength=snapshot.signal_score,
        calibrated_probability=None,
        calibrated_probability_status=(
            CalibratedProbabilityStatus.NOT_ESTIMABLE_UNCALIBRATED
        ),
        limitations=(
            "LEGACY_V3_CONFIDENCE_MEANS_DATA_COMPLETENESS",
            "NO_CALIBRATED_PROBABILITY",
            "RESEARCH_SIGNAL_NOT_ENTRY",
        ),
    )


__all__ = [
    "CalibratedProbabilityStatus",
    "SignalResearchMeasures",
    "project_signal_research_measures",
]
