"""Thin operator orchestration for the BaoStock exploratory Research Universe."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Protocol

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.providers.public_composite.replay_archive import (
    SourceReplayArchiveReader,
    publish_source_archive,
)
from market_regime_alpha.data.providers.public_composite.research_universe import (
    BaoStockResearchUniverseClient,
    FreeResearchUniverseAcquisition,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.universe.postgres_research import (
    PostgresFreeResearchUniverseRepository,
)


class FreeResearchUniverseAcquirer(Protocol):
    def acquire(self, *, as_of_date: date) -> FreeResearchUniverseAcquisition: ...


class FreeResearchUniverseOperator:
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        acquisition: FreeResearchUniverseAcquirer | None = None,
    ) -> None:
        self._repository = PostgresFreeResearchUniverseRepository(factory)
        self._acquisition = acquisition or BaoStockResearchUniverseClient()

    def sync(self, *, as_of_date: date, artifact_root: Path) -> dict[str, object]:
        acquired = self._acquisition.acquire(as_of_date=as_of_date)
        archive_root = artifact_root / "free-data-research-universe" / "raw-archives"
        archive_path = archive_root / acquired.snapshot.raw_archive_id
        if archive_path.exists():
            replay = SourceReplayArchiveReader().read(archive_path)
            if (
                replay.source_manifest.source_manifest_id
                != acquired.source_manifest.source_manifest_id
                or replay.provider_result.content_hash
                != acquired.provider_result.content_hash
            ):
                raise ValueError("Research Universe raw archive identity conflict")
        else:
            archive_path = publish_source_archive(
                root=archive_root,
                provider_result=acquired.provider_result,
                source_manifest=acquired.source_manifest,
            )
        snapshot = self._repository.publish(acquired.snapshot)
        return _result(snapshot, archive_path=str(archive_path), replayed=False)

    def replay(self, snapshot_id: ArtifactId) -> dict[str, object]:
        return _result(self._repository.get(snapshot_id), archive_path=None, replayed=True)


def _result(snapshot, *, archive_path: str | None, replayed: bool) -> dict[str, object]:
    return {
        "operation": "RESEARCH_UNIVERSE_REPLAY" if replayed else "RESEARCH_UNIVERSE_SYNC",
        "snapshot_id": str(snapshot.snapshot_id),
        "snapshot_hash": snapshot.snapshot_hash,
        "as_of_date": snapshot.as_of_date.isoformat(),
        "known_at": snapshot.known_at.isoformat(),
        "security_master_count": snapshot.security_master_count,
        "included_count": snapshot.included_count,
        "unknown_count": snapshot.unknown_count,
        "evidence_origin": snapshot.evidence_origin.value,
        "data_eligibility": snapshot.data_eligibility.value,
        "evidence_ceiling": snapshot.evidence_ceiling.value,
        "raw_archive": archive_path,
        "formal_pit": False,
        "formal_oos": False,
        "production_authorized": False,
    }


__all__ = ["FreeResearchUniverseOperator"]
