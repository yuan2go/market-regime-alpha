"""Thin operator orchestration for the BaoStock exploratory Research Universe."""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from market_regime_alpha.application.controlled_operation.input_artifacts import (
    publish_controlled_trading_calendar,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId, DatasetId
from market_regime_alpha.data.pit_artifact_authority import (
    CanonicalPITArtifactAuthorityResolver,
    PITArtifactKind,
    PITArtifactReference,
)
from market_regime_alpha.data.postgres_pit_authority import PostgresPITAuthority
from market_regime_alpha.data.postgres_trading_calendar import (
    PostgresPITTradingCalendarSnapshotRepository,
)
from market_regime_alpha.data.providers.public_composite.replay_archive import (
    SourceReplayArchiveReader,
    publish_source_archive,
)
from market_regime_alpha.data.providers.public_composite.research_universe import (
    BaoStockResearchUniverseClient,
    FreeResearchUniverseAcquisition,
    FreeResearchUniverseHistoryAcquisition,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.data.trading_calendar import (
    TradingCalendarArtifact,
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.universe.postgres_research import (
    PostgresFreeResearchUniverseRepository,
)
from market_regime_alpha.universe.research import FreeDataEvidenceOrigin
from market_regime_alpha.universe.research import (
    HistoricalConstituentCohort,
    HistoricalConstituentTimeline,
)


class FreeResearchUniverseAcquirer(Protocol):
    def acquire(self, *, as_of_date: date) -> FreeResearchUniverseAcquisition: ...

    def acquire_historical_constituents(self, *, effective_date: date) -> FreeResearchUniverseAcquisition: ...

    def acquire_historical_constituent_history(self, *, start_date: date, end_date: date) -> FreeResearchUniverseHistoryAcquisition: ...


def build_historical_trading_calendar(
    timeline: HistoricalConstituentTimeline,
) -> TradingCalendarArtifact:
    """Project the exact Provider scan sessions into the canonical Calendar."""

    timezone = ZoneInfo("Asia/Shanghai")
    return build_trading_calendar_artifact(
        source_dataset_id=DatasetId(str(timeline.timeline_id)),
        market="CN_A_SHARE",
        calendar_version="BAOSTOCK_HISTORY_SCAN_V1",
        timezone_name="Asia/Shanghai",
        sessions=tuple(
            TradingSession(
                trade_date=session_date,
                session_close=datetime.combine(
                    session_date,
                    time(hour=15),
                    tzinfo=timezone,
                ),
            )
            for session_date in timeline.queried_trading_dates
        ),
    )


class FreeResearchUniverseOperator:
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        acquisition: FreeResearchUniverseAcquirer | None = None,
    ) -> None:
        self._factory = factory
        self._repository = PostgresFreeResearchUniverseRepository(factory)
        self._acquisition = acquisition or BaoStockResearchUniverseClient()

    def sync(self, *, as_of_date: date, artifact_root: Path) -> dict[str, object]:
        acquired = self._acquisition.acquire(as_of_date=as_of_date)
        return self._publish(acquired, artifact_root=artifact_root, historical=False)

    def sync_historical_constituents(
        self,
        *,
        effective_date: date,
        artifact_root: Path,
    ) -> dict[str, object]:
        acquired = self._acquisition.acquire_historical_constituents(effective_date=effective_date)
        return self._publish(acquired, artifact_root=artifact_root, historical=True)

    def sync_historical_constituent_history(
        self,
        *,
        start_date: date,
        end_date: date,
        artifact_root: Path,
    ) -> dict[str, object]:
        acquired = self._acquisition.acquire_historical_constituent_history(
            start_date=start_date,
            end_date=end_date,
        )
        scan_archive_root = artifact_root / "free-data-research-universe" / "history-scan-raw-archives"
        scan_archive_path = scan_archive_root / acquired.scan_raw_archive_id
        if scan_archive_path.exists():
            scan_replay = SourceReplayArchiveReader().read(scan_archive_path)
            if (
                scan_replay.source_manifest.source_manifest_id != acquired.scan_source_manifest.source_manifest_id
                or scan_replay.provider_result.content_hash != acquired.scan_provider_result.content_hash
            ):
                raise ValueError("Research Universe history scan archive conflict")
        else:
            scan_archive_path = publish_source_archive(
                root=scan_archive_root,
                provider_result=acquired.scan_provider_result,
                source_manifest=acquired.scan_source_manifest,
            )
        published = tuple(self._publish(item, artifact_root=artifact_root, historical=True) for item in acquired.acquisitions)
        snapshots = tuple(self._repository.get(ArtifactId(str(item["snapshot_id"]))) for item in published)
        by_id = {snapshot.snapshot_id: snapshot for snapshot in snapshots}
        timeline = self._repository.publish_timeline(
            HistoricalConstituentTimeline.create(
                start_date=acquired.start_date,
                end_date=acquired.end_date,
                queried_trading_dates=acquired.queried_trading_dates,
                query_effective_dates=acquired.query_effective_dates,
                cohorts=tuple(
                    HistoricalConstituentCohort(
                        effective_date=snapshot.constituent_effective_date,
                        snapshot_reference=ValidationArtifactReference(
                            "FREE_RESEARCH_UNIVERSE",
                            snapshot.snapshot_id,
                            snapshot.snapshot_hash,
                        ),
                    )
                    for snapshot in sorted(
                        by_id.values(),
                        key=lambda item: item.constituent_effective_date or date.min,
                    )
                    if snapshot.constituent_effective_date is not None
                ),
                scan_source_manifest_reference=ValidationArtifactReference(
                    "SOURCE_MANIFEST",
                    acquired.scan_source_manifest.source_manifest_id,
                    acquired.scan_source_manifest.content_hash,
                ),
                raw_archive_id=acquired.scan_raw_archive_id,
                known_at=acquired.retrieved_at,
            )
        )
        symbols = {record.symbol for snapshot in snapshots for record in snapshot.records if record.membership_status.value == "INCLUDED"}
        return {
            "operation": "HISTORICAL_RESEARCH_UNIVERSE_HISTORY_SYNC",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "queried_trading_session_count": len(acquired.queried_trading_dates),
            "cohort_count": len(snapshots),
            "timeline_id": str(timeline.timeline_id),
            "timeline_hash": timeline.timeline_hash,
            "scan_raw_archive": str(scan_archive_path),
            "union_symbol_count": len(symbols),
            "cohorts": list(published),
            "data_eligibility": "EXPLORATORY",
            "evidence_ceiling": "PIT_INCOMPLETE",
            "formal_pit": False,
            "formal_oos": False,
            "production_authorized": False,
        }

    def freeze_historical_trading_calendar(
        self,
        *,
        timeline_id: ArtifactId,
        artifact_root: Path,
    ) -> dict[str, object]:
        """Publish and record the Calendar projected from one exact timeline."""

        timeline = self._repository.get_timeline(timeline_id)
        calendar = build_historical_trading_calendar(timeline)
        calendar_root = artifact_root / "historical-trading-calendar"
        package_path = publish_controlled_trading_calendar(
            root=calendar_root,
            artifact=calendar,
        )
        reference = PITArtifactReference(
            PITArtifactKind.TRADING_CALENDAR.value,
            calendar.artifact_id,
            calendar.content_hash,
        )
        resolution = PostgresPITAuthority(
            self._factory,
            artifact_resolver=CanonicalPITArtifactAuthorityResolver(
                artifact_roots={
                    PITArtifactKind.TRADING_CALENDAR: calendar_root,
                }
            ),
        ).resolve_artifact(
            reference,
            actor="HISTORICAL_RESEARCH",
            reason="resolve exact provider-scanned Historical Trading Calendar",
            idempotency_key=(
                f"historical-calendar:{timeline.timeline_id}:"
                f"{timeline.timeline_hash}"
            ),
        )
        recorded = PostgresPITTradingCalendarSnapshotRepository(
            self._factory,
            apply_migrations=False,
        ).record(calendar)
        if recorded != calendar:
            raise ValueError("Historical Trading Calendar owner identity drifted")
        return {
            "operation": "HISTORICAL_TRADING_CALENDAR_FREEZE",
            "calendar_reference": ValidationArtifactReference(
                "TRADING_CALENDAR",
                calendar.artifact_id,
                calendar.content_hash,
            ).to_canonical_dict(),
            "timeline_reference": timeline.reference.to_canonical_dict(),
            "session_count": len(calendar.sessions),
            "package_path": str(package_path),
            "authority_resolution": resolution.to_canonical_dict(),
            "data_eligibility": "EXPLORATORY",
            "evidence_ceiling": "PIT_INCOMPLETE",
            "formal_pit": False,
            "formal_oos": False,
        }

    def _publish(
        self,
        acquired: FreeResearchUniverseAcquisition,
        *,
        artifact_root: Path,
        historical: bool,
    ) -> dict[str, object]:
        archive_root = artifact_root / "free-data-research-universe" / "raw-archives"
        archive_path = archive_root / acquired.snapshot.raw_archive_id
        if archive_path.exists():
            replay = SourceReplayArchiveReader().read(archive_path)
            if (
                replay.source_manifest.source_manifest_id != acquired.source_manifest.source_manifest_id
                or replay.provider_result.content_hash != acquired.provider_result.content_hash
            ):
                raise ValueError("Research Universe raw archive identity conflict")
        else:
            archive_path = publish_source_archive(
                root=archive_root,
                provider_result=acquired.provider_result,
                source_manifest=acquired.source_manifest,
            )
        snapshot = self._repository.publish(acquired.snapshot)
        result = _result(snapshot, archive_path=str(archive_path), replayed=False)
        if historical:
            result["operation"] = "HISTORICAL_RESEARCH_UNIVERSE_SYNC"
        return result

    def replay(
        self,
        snapshot_id: ArtifactId,
        *,
        artifact_root: Path,
    ) -> dict[str, object]:
        snapshot = self._repository.get(snapshot_id)
        archive_path = artifact_root / "free-data-research-universe" / "raw-archives" / snapshot.raw_archive_id
        replay = SourceReplayArchiveReader().read(archive_path)
        if (
            replay.archive_id != snapshot.raw_archive_id
            or replay.source_manifest.source_manifest_id != snapshot.source_manifest_reference.artifact_id
            or replay.source_manifest.content_hash != snapshot.source_manifest_reference.content_hash
        ):
            raise ValueError("Research Universe replay archive lineage mismatch")
        return _result(
            snapshot,
            archive_path=str(archive_path),
            replayed=True,
        )


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
        "selection_basis": snapshot.selection_basis.value,
        "constituent_effective_date": (
            None if snapshot.constituent_effective_date is None else snapshot.constituent_effective_date.isoformat()
        ),
        "runtime_evidence_origin": (FreeDataEvidenceOrigin.ARCHIVED_REPLAY.value if replayed else snapshot.evidence_origin.value),
        "data_eligibility": snapshot.data_eligibility.value,
        "evidence_ceiling": snapshot.evidence_ceiling.value,
        "raw_archive": archive_path,
        "formal_pit": False,
        "formal_oos": False,
        "production_authorized": False,
    }


__all__ = [
    "FreeResearchUniverseOperator",
    "build_historical_trading_calendar",
]
