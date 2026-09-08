from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from market_regime_alpha.market.application import (
    ArchiveManifestSlice,
    ArchiveOperatorManifest,
    ArchiveSlicePlan,
    StartMarketArchiveRequest,
)
from market_regime_alpha.market.application.archive_replay import (
    relabel_retrospective_manifest,
)
from market_regime_alpha.market.domain import ArchiveLane, BarTimeframe, PriceBasis
from market_regime_alpha.market.ports import CaptureRequest
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


def _source_manifest() -> ArchiveOperatorManifest:
    provider_product_id = uuid4()
    slices: list[ArchiveManifestSlice] = []
    for ordinal in range(1, 4):
        capture = CaptureRequest(
            provider_product_id=provider_product_id,
            capture_key=f"source/{ordinal:04d}",
            resource=f'{{"kind":"FIXTURE","ordinal":{ordinal}}}',
            request_headers_hash=ContentHash(sha256(b"").hexdigest()),
        )
        plan = ArchiveSlicePlan(
            market_archive_slice_id=uuid4(),
            ordinal=ordinal,
            scope_key=f"fixture:{ordinal}",
            event_window_start=datetime(2026, 1, ordinal, tzinfo=UTC),
            event_window_end=datetime(2026, 1, ordinal, 8, tzinfo=UTC),
            request_sha256=canonical_json_sha256(capture),
            expected_fact_kind="FIXTURE",
        )
        slices.append(ArchiveManifestSlice(plan, capture, "BACKFILL_FIXTURE"))
    request = StartMarketArchiveRequest(
        market_archive_id=uuid4(),
        archive_code="source_archive",
        lane=ArchiveLane.RETROSPECTIVE_BACKFILL,
        provider_product_id=provider_product_id,
        exchange_code="XSHG",
        timeframe=BarTimeframe.MINUTE_5,
        price_basis=PriceBasis.RAW_UNADJUSTED,
        instrument_scope="SOURCE_SCOPE",
        instrument_scope_sha256=sha256(b"source").hexdigest(),
        event_window_start=datetime(2026, 1, 1, tzinfo=UTC),
        event_window_end=datetime(2026, 1, 31, tzinfo=UTC),
        reserved_free_bytes=2_000_000_000,
        maximum_archive_bytes=2_500_000_000,
        maximum_slice_bytes=50_000_000,
        code_artifact_id=uuid4(),
        config_artifact_id=uuid4(),
        provenance_sha256=sha256(b"source-provenance").hexdigest(),
        slices=tuple(item.plan for item in slices),
    )
    return ArchiveOperatorManifest(request, tuple(slices))


def test_relabels_an_explicit_ordered_subset_deterministically() -> None:
    source = _source_manifest()
    selected = (source.slices[2], source.slices[0])
    kwargs = dict(
        source=source,
        selected=selected,
        identity_key="generic-platform-qualification-20260904-v1",
        archive_code="generic_platform_qualification_20260904",
        code_artifact_id=uuid4(),
        config_artifact_id=uuid4(),
        instrument_scope="DETERMINISTIC_32_SYMBOL_QUALIFICATION",
        instrument_scope_sha256=sha256(b"32-symbols").hexdigest(),
        provenance_sha256=sha256(b"qualification-provenance").hexdigest(),
        reserved_free_bytes=256_000_000,
        maximum_archive_bytes=500_000_000,
    )

    first = relabel_retrospective_manifest(**kwargs)
    second = relabel_retrospective_manifest(**kwargs)

    assert first.to_bytes() == second.to_bytes()
    assert first.start_request.market_archive_id == UUID(
        "94a00500-c867-5ede-bf7d-886fbbd5fcaf"
    )
    assert tuple(item.plan.ordinal for item in first.slices) == (1, 2)
    assert tuple(item.plan.scope_key for item in first.slices) == (
        "fixture:3",
        "fixture:1",
    )
    assert tuple(item.capture_request.capture_key for item in first.slices) == (
        "generic_platform_qualification_20260904/0001",
        "generic_platform_qualification_20260904/0002",
    )
    assert tuple(item.capture_request.resource for item in first.slices) == tuple(
        item.capture_request.resource for item in selected
    )
    assert first.start_request.lane is ArchiveLane.RETROSPECTIVE_BACKFILL
    assert first.start_request.reserved_free_bytes == 256_000_000
    assert first.start_request.maximum_slice_bytes == source.start_request.maximum_slice_bytes
