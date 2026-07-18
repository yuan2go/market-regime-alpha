"""Shared Tencent/local/BaoStock execution seam for WP-3 and PRR research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
import json

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.time import RetrievedAt
from market_regime_alpha.data import DataEligibility, DatasetContract, SourceArtifactReference
from market_regime_alpha.research.tencent_composite_acquisition import (
    TencentCompositeAcquirer,
    merge_acquisition,
)
from market_regime_alpha.research.tencent_composite_contracts import (
    CompositeAcquisitionResult,
    CompositeMergeResult,
    PreparedCompositeData,
    build_tencent_composite_dataset_contract,
)
from market_regime_alpha.research.tencent_composite_quality import prepare_composite_data
from market_regime_alpha.research.tencent_composite_runner import (
    TencentCompositeCandidateRun,
    run_tencent_composite_candidate_experiment,
)


@dataclass(frozen=True, slots=True)
class TencentCompositeResearchExecution:
    """One shared EXPLORATORY Candidate-research input and fixed-model result."""

    acquisition: CompositeAcquisitionResult
    merged: CompositeMergeResult
    prepared: PreparedCompositeData
    dataset_contract: DatasetContract
    candidate_experiment: TencentCompositeCandidateRun
    source_artifacts: tuple[SourceArtifactReference, ...]
    acquisition_mode: str

    def __post_init__(self) -> None:
        if self.dataset_contract.eligibility is not DataEligibility.EXPLORATORY:
            raise ValueError("Tencent composite execution must remain EXPLORATORY")
        if self.candidate_experiment.data_eligibility is not DataEligibility.EXPLORATORY:
            raise ValueError("Candidate experiment must remain EXPLORATORY")
        if self.acquisition_mode not in {"LIVE", "CACHED", "MIXED"}:
            raise ValueError("acquisition_mode must be LIVE, CACHED, or MIXED")

    @property
    def limitations(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                (*self.dataset_contract.limitations, *self.candidate_experiment.limitations)
            )
        )


def execute_tencent_composite_research(
    *,
    acquirer: TencentCompositeAcquirer,
    watchlist: tuple[str, ...],
    watchlist_hash: str,
    retrieved_at: RetrievedAt,
    history_calendar_days: int,
    decision_count: int,
    warmup_sessions: int,
    minimum_accepted_symbols: int,
    code_revision: str,
    config_hash: str,
    acquisition_mode: str = "MIXED",
) -> TencentCompositeResearchExecution:
    """Run the existing composite preparation and fixed B0/B1 experiment once."""

    if decision_count != 60:
        raise ValueError("Tencent composite Candidate contract requires decision_count=60")
    if len(watchlist) != 20 or len(watchlist) != len(set(watchlist)):
        raise ValueError("Tencent composite route requires exactly 20 configured watchlist symbols")
    if history_calendar_days <= 0:
        raise ValueError("history_calendar_days must be positive")
    acquisition = acquirer.acquire(
        symbols=watchlist,
        start_date=(retrieved_at.value.date() - timedelta(days=history_calendar_days)).isoformat(),
        end_date=retrieved_at.value.date().isoformat(),
        retrieved_at=retrieved_at.value,
    )
    merged = merge_acquisition(acquisition)
    dataset_contract = build_tencent_composite_dataset_contract(
        watchlist_hash=watchlist_hash,
        source_content_hashes=tuple(
            partition.content_hash
            for partition in (*acquisition.partitions, acquisition.quote_partition)
        ),
        code_revision=code_revision,
        config_hash=config_hash,
    )
    prepared = prepare_composite_data(
        merged,
        requested_symbols=watchlist,
        decision_count=decision_count,
        warmup_sessions=warmup_sessions,
        minimum_accepted_symbols=minimum_accepted_symbols,
    )
    candidate_experiment = run_tencent_composite_candidate_experiment(
        prepared=prepared,
        dataset_contract=dataset_contract,
        retrieved_at=retrieved_at,
        code_revision=code_revision,
        config_hash=config_hash,
    )
    return TencentCompositeResearchExecution(
        acquisition=acquisition,
        merged=merged,
        prepared=prepared,
        dataset_contract=dataset_contract,
        candidate_experiment=candidate_experiment,
        source_artifacts=source_artifacts_from_acquisition(acquisition),
        acquisition_mode=acquisition_mode,
    )


def source_artifacts_from_acquisition(
    acquisition: CompositeAcquisitionResult,
) -> tuple[SourceArtifactReference, ...]:
    """Expose every composite partition as a stable source-artifact reference."""

    return tuple(
        _source_artifact(partition)
        for partition in (*acquisition.partitions, acquisition.quote_partition)
    )


def _source_artifact(partition: object) -> SourceArtifactReference:
    provider_id = getattr(partition, "provider_id")
    product = getattr(partition, "product")
    retrieved_at = getattr(partition, "retrieved_at")
    content_hash = getattr(partition, "content_hash")
    locator = getattr(partition, "locator")
    canonical = json.dumps(
        {
            "provider_id": str(provider_id),
            "product": product,
            "retrieved_at": retrieved_at.isoformat(),
            "content_hash": content_hash,
            "locator": locator,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    return SourceArtifactReference(
        artifact_id=ArtifactId(f"source-wp3-tencent-{digest[:24]}"),
        provider_id=provider_id,
        retrieved_at=retrieved_at,
        content_hash=content_hash,
        locator=locator,
    )
