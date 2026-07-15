"""Multi-decision-time Candidate research panel assembly.

A panel preserves each cross-sectional slice as an identified research artifact. It does
not flatten changing PIT universes into one timeless universe and does not silently alter
the target or feature schema across Decision Times.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from market_regime_alpha.candidates.dataset import CandidateResearchDataset
from market_regime_alpha.core.identity import DatasetId, FeatureDefinitionId, TargetId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.contracts import DataEligibility


_DATA_ELIGIBILITY_ORDER = {
    DataEligibility.UNQUALIFIED: 0,
    DataEligibility.EXPLORATORY: 1,
    DataEligibility.REHEARSAL: 2,
    DataEligibility.FORMAL_RESEARCH: 3,
}


@dataclass(frozen=True, slots=True)
class CandidateResearchPanel:
    """Versioned collection of Candidate cross-sections across multiple Decision Times."""

    dataset_id: DatasetId
    slice_dataset_ids: tuple[DatasetId, ...]
    data_eligibility: DataEligibility
    target_id: TargetId
    feature_definition_ids: tuple[FeatureDefinitionId, ...]
    decision_times: tuple[DecisionTime, ...]
    slices: tuple[CandidateResearchDataset, ...]
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.data_eligibility, DataEligibility):
            raise TypeError("data_eligibility must be a DataEligibility")
        if not self.slices:
            raise ValueError("Candidate research panel requires at least one slice")
        if len(self.slice_dataset_ids) != len(set(self.slice_dataset_ids)):
            raise ValueError("slice_dataset_ids must be unique")
        if len(self.decision_times) != len(set(self.decision_times)):
            raise ValueError("decision_times must be unique")
        if tuple(sorted(self.decision_times, key=lambda value: value.value)) != self.decision_times:
            raise ValueError("decision_times must be sorted")
        if tuple(slice_.dataset_id for slice_ in self.slices) != self.slice_dataset_ids:
            raise ValueError("slice_dataset_ids must match slices")
        if tuple(slice_.decision_time for slice_ in self.slices) != self.decision_times:
            raise ValueError("decision_times must match slices")
        for slice_ in self.slices:
            if slice_.target_id != self.target_id:
                raise ValueError("all Candidate panel slices must share one Target Identity")
            if slice_.feature_definition_ids != self.feature_definition_ids:
                raise ValueError("all Candidate panel slices must share one Feature schema")

    @property
    def slice_count(self) -> int:
        return len(self.slices)

    @property
    def row_count(self) -> int:
        return sum(slice_.row_count for slice_ in self.slices)


def assemble_candidate_research_panel(
    slices: tuple[CandidateResearchDataset, ...],
    *,
    limitations: tuple[str, ...] = (),
) -> CandidateResearchPanel:
    """Assemble identified Candidate slices into a chronologically ordered research panel."""

    if not slices:
        raise ValueError("Candidate research panel requires at least one slice")
    ordered = tuple(sorted(slices, key=lambda slice_: slice_.decision_time.value))
    decision_times = tuple(slice_.decision_time for slice_ in ordered)
    if len(decision_times) != len(set(decision_times)):
        raise ValueError("Candidate research panel cannot contain duplicate Decision Times")

    first = ordered[0]
    for slice_ in ordered[1:]:
        if slice_.target_id != first.target_id:
            raise ValueError("Candidate research panel cannot mix Target identities")
        if slice_.feature_definition_ids != first.feature_definition_ids:
            raise ValueError("Candidate research panel cannot mix Feature schemas")

    data_eligibility = min(
        (slice_.data_eligibility for slice_ in ordered),
        key=_DATA_ELIGIBILITY_ORDER.__getitem__,
    )
    slice_dataset_ids = tuple(slice_.dataset_id for slice_ in ordered)
    dataset_id = _panel_dataset_id(
        slice_dataset_ids=slice_dataset_ids,
        target_id=first.target_id,
        feature_definition_ids=first.feature_definition_ids,
    )
    return CandidateResearchPanel(
        dataset_id=dataset_id,
        slice_dataset_ids=slice_dataset_ids,
        data_eligibility=data_eligibility,
        target_id=first.target_id,
        feature_definition_ids=first.feature_definition_ids,
        decision_times=decision_times,
        slices=ordered,
        limitations=limitations,
    )


def _panel_dataset_id(
    *,
    slice_dataset_ids: tuple[DatasetId, ...],
    target_id: TargetId,
    feature_definition_ids: tuple[FeatureDefinitionId, ...],
) -> DatasetId:
    payload = {
        "schema_version": "candidate-research-panel-v1",
        "slice_dataset_ids": [str(value) for value in slice_dataset_ids],
        "target_id": str(target_id),
        "feature_definition_ids": [str(value) for value in feature_definition_ids],
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    return DatasetId(f"candidate-panel-{digest[:24]}")
