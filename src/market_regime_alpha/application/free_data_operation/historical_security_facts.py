"""Owner orchestration for exploratory historical Security Facts."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Protocol

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.providers.public_composite.historical_security_facts import (
    BaoStockHistoricalSecurityFactsClient,
    HistoricalSecurityFactsAcquisition,
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
        checkpoint_root: Path | None = None,
    ) -> HistoricalSecurityFactsAcquisition: ...


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
        start_date: date,
        end_date: date,
        artifact_root: Path,
    ) -> dict[str, object]:
        if not universe_snapshot_ids or universe_snapshot_ids != tuple(sorted(set(universe_snapshot_ids), key=str)):
            raise ValueError("Historical fact Universe owners must be ordered")
        universes = tuple(self._universes.get(snapshot_id) for snapshot_id in universe_snapshot_ids)
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


__all__ = ["HistoricalSecurityFactsOperator"]
