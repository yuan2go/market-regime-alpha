"""Deterministic DTO projection for replaying an explicit retrospective subset."""

from __future__ import annotations

from uuid import NAMESPACE_URL, UUID, uuid5

from market_regime_alpha.market.application.archive import (
    ArchiveSlicePlan,
    StartMarketArchiveRequest,
)
from market_regime_alpha.market.application.archive_manifest import (
    ArchiveManifestSlice,
    ArchiveOperatorManifest,
)
from market_regime_alpha.market.domain import ArchiveLane
from market_regime_alpha.market.ports import CaptureRequest
from market_regime_alpha.shared.hashing import canonical_json_sha256


def relabel_retrospective_manifest(
    *,
    source: ArchiveOperatorManifest,
    selected: tuple[ArchiveManifestSlice, ...],
    identity_key: str,
    archive_code: str,
    code_artifact_id: UUID,
    config_artifact_id: UUID,
    instrument_scope: str,
    instrument_scope_sha256: str,
    provenance_sha256: str,
    reserved_free_bytes: int,
    maximum_archive_bytes: int,
) -> ArchiveOperatorManifest:
    """Relabel selected requests without changing their Provider resources.

    The result remains an operator DTO. ``ArchiveCommands.start`` freezes the
    authoritative roster in PostgreSQL before any capture executes.
    """

    if source.start_request.lane is not ArchiveLane.RETROSPECTIVE_BACKFILL:
        raise ValueError("source manifest must be retrospective")
    if not identity_key:
        raise ValueError("replay identity_key is required")
    if not selected:
        raise ValueError("replay subset must be non-empty")
    source_by_id = {
        item.plan.market_archive_slice_id: item for item in source.slices
    }
    selected_ids = tuple(item.plan.market_archive_slice_id for item in selected)
    if len(set(selected_ids)) != len(selected_ids) or any(
        source_by_id.get(item.plan.market_archive_slice_id) != item
        for item in selected
    ):
        raise ValueError("replay subset contains a duplicate or foreign slice")
    if reserved_free_bytes < 0 or maximum_archive_bytes < 1:
        raise ValueError("replay resource limits are invalid")

    prefix = f"mra:retrospective-archive-replay:{identity_key}"
    relabeled: list[ArchiveManifestSlice] = []
    for ordinal, item in enumerate(selected, start=1):
        capture = CaptureRequest(
            provider_product_id=item.capture_request.provider_product_id,
            capture_key=f"{archive_code}/{ordinal:04d}",
            resource=item.capture_request.resource,
            request_headers_hash=item.capture_request.request_headers_hash,
        )
        plan = ArchiveSlicePlan(
            market_archive_slice_id=uuid5(NAMESPACE_URL, f"{prefix}:slice:{ordinal}"),
            ordinal=ordinal,
            scope_key=item.plan.scope_key,
            event_window_start=item.plan.event_window_start,
            event_window_end=item.plan.event_window_end,
            request_sha256=canonical_json_sha256(capture),
            expected_fact_kind=item.plan.expected_fact_kind,
        )
        relabeled.append(
            ArchiveManifestSlice(
                plan=plan,
                capture_request=capture,
                schedule_slot=item.schedule_slot,
            )
        )
    source_request = source.start_request
    request = StartMarketArchiveRequest(
        market_archive_id=uuid5(NAMESPACE_URL, f"{prefix}:archive"),
        archive_code=archive_code,
        lane=ArchiveLane.RETROSPECTIVE_BACKFILL,
        provider_product_id=source_request.provider_product_id,
        exchange_code=source_request.exchange_code,
        timeframe=source_request.timeframe,
        price_basis=source_request.price_basis,
        instrument_scope=instrument_scope,
        instrument_scope_sha256=instrument_scope_sha256,
        event_window_start=source_request.event_window_start,
        event_window_end=source_request.event_window_end,
        reserved_free_bytes=reserved_free_bytes,
        maximum_archive_bytes=maximum_archive_bytes,
        maximum_slice_bytes=source_request.maximum_slice_bytes,
        code_artifact_id=code_artifact_id,
        config_artifact_id=config_artifact_id,
        provenance_sha256=provenance_sha256,
        slices=tuple(item.plan for item in relabeled),
    )
    return ArchiveOperatorManifest(request, tuple(relabeled))


__all__ = ["relabel_retrospective_manifest"]
