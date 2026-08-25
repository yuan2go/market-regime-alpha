"""Owner orchestration for exploratory historical Security Facts."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Protocol

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.data.providers.public_composite.historical_security_facts import (
    BaoStockHistoricalSecurityFactsClient,
    HistoricalSecurityFactsAcquisition,
    HistoricalSecurityFactsPrefetch,
)
from market_regime_alpha.data.providers.public_composite.replay_archive import (
    SourceReplayArchiveReader,
    publish_source_archive,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.universe.postgres_historical_facts import (
    PostgresHistoricalSecurityFactsRepository,
)
from market_regime_alpha.universe.postgres_research import (
    PostgresFreeResearchUniverseRepository,
)
from market_regime_alpha.universe.research import (
    ResearchUniverseMembershipStatus,
)


class HistoricalSecurityFactsAcquirer(Protocol):
    def acquire(
        self,
        *,
        symbols: tuple[str, ...],
        cohort_dates: tuple[date, ...],
        start_date: date,
        end_date: date,
        universe_scope_references: tuple[ValidationArtifactReference, ...],
        checkpoint_root: Path | None = None,
    ) -> HistoricalSecurityFactsAcquisition: ...

    def prefetch(
        self,
        *,
        symbols: tuple[str, ...],
        cohort_dates: tuple[date, ...],
        start_date: date,
        end_date: date,
        checkpoint_root: Path,
        worker_index: int,
        worker_count: int,
    ) -> HistoricalSecurityFactsPrefetch: ...


class HistoricalSecurityFactsOperator:
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        acquisition: HistoricalSecurityFactsAcquirer | None = None,
    ) -> None:
        self._universes = PostgresFreeResearchUniverseRepository(factory)
        self._facts = PostgresHistoricalSecurityFactsRepository(factory, apply_migrations=False)
        self._acquisition = acquisition or BaoStockHistoricalSecurityFactsClient()

    def sync(
        self,
        *,
        universe_snapshot_ids: tuple[ArtifactId, ...],
        universe_timeline_reference: ValidationArtifactReference | None = None,
        start_date: date,
        end_date: date,
        artifact_root: Path,
    ) -> dict[str, object]:
        if not universe_snapshot_ids or universe_snapshot_ids != tuple(sorted(set(universe_snapshot_ids), key=str)):
            raise ValueError("Historical fact Universe owners must be ordered")
        universes = tuple(self._universes.get(snapshot_id) for snapshot_id in universe_snapshot_ids)
        scope_references = tuple(
            sorted(
                (
                    *(
                        ValidationArtifactReference(
                            "FREE_RESEARCH_UNIVERSE",
                            universe.snapshot_id,
                            universe.snapshot_hash,
                        )
                        for universe in universes
                    ),
                    *((universe_timeline_reference,) if universe_timeline_reference is not None else ()),
                ),
                key=lambda item: (
                    item.artifact_kind,
                    str(item.artifact_id),
                    item.content_hash,
                ),
            )
        )
        raw_cohort_dates = tuple(item.constituent_effective_date for item in universes)
        if any(item is None for item in raw_cohort_dates):
            raise ValueError("Historical fact Universe cohort dates are invalid")
        cohort_dates = tuple(sorted({item for item in raw_cohort_dates if item is not None}))
        if len(cohort_dates) != len(universes):
            raise ValueError("Historical fact Universe cohort dates are not unique")
        symbols = tuple(
            sorted(
                {
                    record.symbol
                    for universe in universes
                    for record in universe.records
                    if record.membership_status is ResearchUniverseMembershipStatus.INCLUDED
                }
            )
        )
        acquired = self._acquisition.acquire(
            symbols=symbols,
            cohort_dates=cohort_dates,
            start_date=start_date,
            end_date=end_date,
            universe_scope_references=scope_references,
            checkpoint_root=(artifact_root / "free-data-historical-security-facts" / "query-checkpoints"),
        )
        archive_root = artifact_root / "free-data-historical-security-facts" / "raw-archives"
        archive_path = archive_root / acquired.owner.raw_archive_id
        if archive_path.exists():
            replay = SourceReplayArchiveReader().read(archive_path)
            if (
                replay.source_manifest.content_hash != acquired.source_manifest.content_hash
                or replay.provider_result.content_hash != acquired.provider_result.content_hash
            ):
                raise ValueError("Historical Security Facts archive conflict")
        else:
            archive_path = publish_source_archive(
                root=archive_root,
                provider_result=acquired.provider_result,
                source_manifest=acquired.source_manifest,
            )
        owner = self._facts.publish(acquired.owner)
        coverage = {kind: count for kind, count in acquired.fact_counts}
        return {
            "operation": "HISTORICAL_SECURITY_FACTS_SYNC",
            "owner_reference": owner.reference.to_canonical_dict(),
            "universe_snapshot_ids": [str(item) for item in universe_snapshot_ids],
            "cohort_dates": [item.isoformat() for item in cohort_dates],
            "symbol_count": len(symbols),
            "query_count": acquired.query_count,
            "empty_query_count": acquired.empty_query_count,
            "rejected_row_count": acquired.rejected_row_count,
            "coverage_gap_count": acquired.coverage_gap_count,
            "fact_counts": coverage,
            "raw_archive": str(archive_path),
            "data_eligibility": owner.data_eligibility.value,
            "evidence_ceiling": owner.evidence_ceiling.value,
            "formal_pit": False,
            "formal_oos": False,
            "production_authorized": False,
        }

    def prefetch(
        self,
        *,
        universe_snapshot_ids: tuple[ArtifactId, ...],
        start_date: date,
        end_date: date,
        artifact_root: Path,
        worker_index: int,
        worker_count: int,
    ) -> dict[str, object]:
        """Populate deterministic request checkpoints without publishing facts."""

        if not universe_snapshot_ids or universe_snapshot_ids != tuple(
            sorted(set(universe_snapshot_ids), key=str)
        ):
            raise ValueError("Historical fact Universe owners must be ordered")
        universes = tuple(
            self._universes.get(snapshot_id) for snapshot_id in universe_snapshot_ids
        )
        raw_cohort_dates = tuple(
            item.constituent_effective_date for item in universes
        )
        if any(item is None for item in raw_cohort_dates):
            raise ValueError("Historical fact Universe cohort dates are invalid")
        cohort_dates = tuple(
            sorted({item for item in raw_cohort_dates if item is not None})
        )
        if len(cohort_dates) != len(universes):
            raise ValueError("Historical fact Universe cohort dates are not unique")
        symbols = tuple(
            sorted(
                {
                    record.symbol
                    for universe in universes
                    for record in universe.records
                    if record.membership_status
                    is ResearchUniverseMembershipStatus.INCLUDED
                }
            )
        )
        result = self._acquisition.prefetch(
            symbols=symbols,
            cohort_dates=cohort_dates,
            start_date=start_date,
            end_date=end_date,
            checkpoint_root=(
                artifact_root
                / "free-data-historical-security-facts"
                / "query-checkpoints"
            ),
            worker_index=worker_index,
            worker_count=worker_count,
        )
        return {
            "operation": "HISTORICAL_SECURITY_FACTS_PREFETCH",
            "worker_index": result.worker_index,
            "worker_count": result.worker_count,
            "expected_query_count": result.expected_query_count,
            "assigned_query_count": result.assigned_query_count,
            "symbol_count": len(symbols),
            "cohort_count": len(cohort_dates),
            "owner_published": False,
            "formal_pit": False,
            "formal_oos": False,
            "production_authorized": False,
        }


__all__ = ["HistoricalSecurityFactsOperator"]
