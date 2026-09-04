"""Controlled archive operator surface over the sole target composition root."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import re
from uuid import UUID

from market_regime_alpha.bootstrap import (
    TargetApplication,
    TargetSettings,
    database_identity,
)
from market_regime_alpha.infrastructure.providers.baostock_archive import (
    BaoStockArchiveProvider,
    BaoStockArchiveQuery,
    BaoStockSdk,
    BaoStockSession,
)
from market_regime_alpha.infrastructure.providers.baostock_archive_normalizer import (
    BaoStockArchiveNormalizer,
)
from market_regime_alpha.market.application import (
    ArchiveManifestSlice,
    ArchiveOperatorManifest,
    ArchiveSliceExecutionRequest,
)
from market_regime_alpha.market.domain import (
    ArchiveLane,
)
from market_regime_alpha.runtime.application import ActorType, CommandContext


_NON_OPERATIONAL_DATABASE = re.compile(
    r"(^|[_-])(test(?:ing)?\d*|dev(?:elopment)?\d*|qual(?:ification)?\d*|fixture\d*|tmp\d*|temp\d*)([_-]|$)",
    re.IGNORECASE,
)


def require_isolated_operational_target(
    settings: TargetSettings,
    *,
    expected_database_name: str,
) -> None:
    identity = database_identity(settings)
    validate_operational_target(
        database_name=identity.database_name,
        artifact_root=settings.artifact_root,
        expected_database_name=expected_database_name,
    )


def validate_operational_target(
    *,
    database_name: str,
    artifact_root: Path,
    expected_database_name: str,
) -> None:
    if database_name != expected_database_name:
        raise ValueError("operational archive database identity differs from operator intent")
    if database_name in {"postgres", "template0", "template1"} or _NON_OPERATIONAL_DATABASE.search(database_name):
        raise ValueError("archive operations reject system/disposable database identities")
    lowered_parts = {part.lower() for part in artifact_root.parts}
    if lowered_parts.intersection({"tmp", "temp", "test", "tests", "fixtures"}):
        raise ValueError("archive operations reject disposable Artifact roots")


def start_archive(
    application: TargetApplication,
    manifest: ArchiveOperatorManifest,
    *,
    actor_id: str,
) -> object:
    return application.market_archives.start(
        manifest.start_request,
        _context(manifest, actor_id, "start"),
    )


def resume_archive(
    application: TargetApplication,
    manifest: ArchiveOperatorManifest,
    *,
    sdk: BaoStockSdk,
    actor_id: str,
    operation_key: str,
    slice_ids: tuple[UUID, ...] | None = None,
) -> tuple[object, ...]:
    results: list[object] = []
    selected = set(slice_ids or ())
    if slice_ids is not None and (
        not slice_ids
        or len(selected) != len(slice_ids)
        or not selected.issubset(
            {item.plan.market_archive_slice_id for item in manifest.slices}
        )
    ):
        raise ValueError("selected archive slice roster is empty, duplicate, or unknown")
    if manifest.start_request.lane is ArchiveLane.PROSPECTIVE_CONTEMPORANEOUS:
        application.market_archives.finalize_overdue(
            market_archive_id=manifest.start_request.market_archive_id,
            context=_context(
                manifest,
                actor_id,
                f"{operation_key}-finalize-overdue",
            ),
        )
        if manifest.start_request.prospective_generation is not None:
            report = application.archive_inspection.inspect(
                manifest.start_request.market_archive_id
            )
            due = {
                item.market_archive_slice_id
                for item in report.slices
                if item.status == "DUE"
            }
            if slice_ids is not None and not selected.issubset(due):
                raise ValueError(
                    "prospective execution roster contains a non-DUE slice"
                )
            selected = due if slice_ids is None else selected
            slice_ids = tuple(sorted(selected, key=str))
            if not slice_ids:
                return ()
    with BaoStockSession(sdk) as session:
        provider = BaoStockArchiveProvider(session)
        for item in manifest.slices:
            if slice_ids is not None and item.plan.market_archive_slice_id not in selected:
                continue
            query = BaoStockArchiveQuery.from_resource(item.capture_request.resource)
            normalizer = BaoStockArchiveNormalizer(
                expected_query=query,
                revision_lineage=application.market_revision_lineage,
                trading_sessions=application.archive_trading_sessions,
            )
            results.append(
                application.archive_operations.execute_slice(
                    ArchiveSliceExecutionRequest(
                        market_archive_id=manifest.start_request.market_archive_id,
                        market_archive_slice_id=item.plan.market_archive_slice_id,
                        capture_request=item.capture_request,
                        schedule_slot=item.schedule_slot,
                    ),
                    provider=provider,
                    normalizer=normalizer,
                    context=_context(manifest, actor_id, f"{operation_key}-{item.plan.ordinal}"),
                )
            )
    return tuple(results)


def archive_report(application: TargetApplication, archive_id: UUID, kind: str) -> object:
    report = application.archive_inspection.inspect(archive_id)
    if kind == "inspect" or kind == "daily-health":
        return report
    if kind == "gap-report":
        return {
            "market_archive_id": archive_id,
            "gaps": tuple(
                item for item in report.slices if item.gap_id is not None
            ),
            "resource_stops": tuple(
                item
                for item in report.slices
                if item.status in {"RESOURCE_LIMIT", "RESOURCE_STOP"}
            ),
            "missed": tuple(
                item for item in report.slices if item.status == "MISSED"
            ),
        }
    if kind == "revision-report":
        return {
            "market_archive_id": archive_id,
            "changed_observation_count": report.changed_observation_count,
            "market_revision_successor_count": report.market_revision_successor_count,
            "slices": tuple(
                item for item in report.slices if item.observation_count > 0
            ),
        }
    raise ValueError("archive report kind is unsupported")


def run_due_archive(
    application: TargetApplication,
    manifest: ArchiveOperatorManifest,
    *,
    sdk: BaoStockSdk,
    actor_id: str,
    operation_key: str,
) -> tuple[object, ...]:
    """Close overdue windows, then execute the currently due manifest roster."""

    return resume_archive(
        application,
        manifest,
        sdk=sdk,
        actor_id=actor_id,
        operation_key=operation_key,
    )


def predeclare_prospective_runtime(
    application: TargetApplication,
    manifest: ArchiveOperatorManifest,
    *,
    code_sha: str,
    actor_id: str,
    lease_duration: timedelta,
) -> object:
    """Register exact prospective work through Runtime Schedule/Run/Attempt."""

    return application.prospective_archives.predeclare(
        manifest,
        code_sha=code_sha,
        actor_id=actor_id,
        lease_duration=lease_duration,
    )


def run_due_prospective_runtime(
    application: TargetApplication,
    manifest: ArchiveOperatorManifest,
    *,
    sdk: BaoStockSdk,
    code_sha: str,
    actor_id: str,
    worker_id: str,
    lease_duration: timedelta,
) -> object:
    """Execute only PostgreSQL-clock-due slices under exact Runtime fences."""

    with BaoStockSession(sdk) as session:
        provider = BaoStockArchiveProvider(session)

        def normalizer_for(item: ArchiveManifestSlice) -> BaoStockArchiveNormalizer:
            return BaoStockArchiveNormalizer(
                expected_query=BaoStockArchiveQuery.from_resource(
                    item.capture_request.resource
                ),
                revision_lineage=application.market_revision_lineage,
                trading_sessions=application.archive_trading_sessions,
            )

        return application.prospective_archives.run_due(
            manifest,
            code_sha=code_sha,
            actor_id=actor_id,
            worker_id=worker_id,
            lease_duration=lease_duration,
            provider=provider,
            normalizer_for=normalizer_for,
        )


def load_archive_manifest(path: Path) -> ArchiveOperatorManifest:
    return ArchiveOperatorManifest.from_json(path.read_text(encoding="utf-8"))


def _context(
    manifest: ArchiveOperatorManifest,
    actor_id: str,
    suffix: str,
) -> CommandContext:
    return CommandContext(
        idempotency_key=(
            f"archive:{manifest.start_request.market_archive_id}:{suffix}"
        ),
        actor_type=ActorType.OPERATOR,
        actor_id=actor_id,
        reason_code="WP17P_ARCHIVE_OPERATION",
    )


__all__ = [
    "ArchiveManifestSlice",
    "ArchiveOperatorManifest",
    "archive_report",
    "load_archive_manifest",
    "predeclare_prospective_runtime",
    "require_isolated_operational_target",
    "resume_archive",
    "run_due_archive",
    "run_due_prospective_runtime",
    "start_archive",
    "validate_operational_target",
]
