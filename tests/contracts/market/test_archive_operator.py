from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

import pytest

from market_regime_alpha.interfaces.archive import (
    ArchiveOperatorManifest,
    resume_archive,
    validate_operational_target,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


def _manifest() -> dict[str, object]:
    archive_id = uuid4()
    product_id = uuid4()
    capture = {
        "provider_product_id": str(product_id),
        "capture_key": "wp17p:sh.600000:2026-01-05",
        "resource": json.dumps(
            {
                "code": "sh.600000",
                "end_date": "2026-01-05",
                "kind": "HISTORY_5M_RAW",
                "start_date": "2026-01-05",
                "version": 1,
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
        "request_headers_hash": "0" * 64,
    }
    return {
        "version": 1,
        "market_archive_id": str(archive_id),
        "archive_code": "wp17p_pilot",
        "lane": "RETROSPECTIVE_BACKFILL",
        "provider_product_id": str(product_id),
        "exchange_code": "XSHG",
        "timeframe": "MINUTE_5",
        "price_basis": "RAW_UNADJUSTED",
        "instrument_scope": "WP17P_DETERMINISTIC_32",
        "instrument_scope_sha256": "1" * 64,
        "event_window_start": "2026-01-05T01:30:00Z",
        "event_window_end": "2026-01-05T07:00:00Z",
        "reserved_free_bytes": 1_000_000,
        "maximum_archive_bytes": 2_000_000,
        "maximum_slice_bytes": 100_000,
        "code_artifact_id": str(uuid4()),
        "config_artifact_id": str(uuid4()),
        "provenance_sha256": "2" * 64,
        "slices": [
            {
                "market_archive_slice_id": str(uuid4()),
                "ordinal": 1,
                "scope_key": "sh.600000:2026-01-05",
                "event_window_start": "2026-01-05T01:30:00Z",
                "event_window_end": "2026-01-05T07:00:00Z",
                "expected_fact_kind": "MARKET_BAR",
                "schedule_slot": "RETROSPECTIVE_BATCH",
                "capture_request": capture,
            }
        ],
    }


def test_manifest_freezes_exact_capture_hash_and_complete_slice_roster() -> None:
    parsed = ArchiveOperatorManifest.from_json(json.dumps(_manifest()))

    assert parsed.start_request.slices == tuple(item.plan for item in parsed.slices)
    assert parsed.slices[0].plan.request_sha256 == canonical_json_sha256(
        parsed.slices[0].capture_request
    )
    assert parsed.start_request.event_window_start == datetime(
        2026, 1, 5, 1, 30, tzinfo=UTC
    )


def test_manifest_rejects_mixed_product_and_naive_time() -> None:
    mixed = _manifest()
    mixed["slices"][0]["capture_request"]["provider_product_id"] = str(uuid4())  # type: ignore[index]
    with pytest.raises(ValueError, match="manifest is invalid"):
        ArchiveOperatorManifest.from_json(json.dumps(mixed))

    naive = _manifest()
    naive["event_window_start"] = "2026-01-05T01:30:00"
    with pytest.raises(ValueError, match="manifest is invalid"):
        ArchiveOperatorManifest.from_json(json.dumps(naive))


def test_operational_guard_rejects_disposable_or_mismatched_targets() -> None:
    validate_operational_target(
        database_name="mra_archive_operational_20260903",
        expected_database_name="mra_archive_operational_20260903",
        artifact_root=Path("/srv/mra/archive-wp17p"),
    )
    with pytest.raises(ValueError, match="disposable database"):
        validate_operational_target(
            database_name="mra_wp17p_dev32",
            expected_database_name="mra_wp17p_dev32",
            artifact_root=Path("/srv/mra/archive-wp17p"),
        )
    with pytest.raises(ValueError, match="differs from operator intent"):
        validate_operational_target(
            database_name="mra_archive_operational_20260903",
            expected_database_name="other",
            artifact_root=Path("/srv/mra/archive-wp17p"),
        )
    with pytest.raises(ValueError, match="Artifact roots"):
        validate_operational_target(
            database_name="mra_archive_operational_20260903",
            expected_database_name="mra_archive_operational_20260903",
            artifact_root=Path("/tmp/archive"),
        )


def test_resume_rejects_an_unknown_or_empty_selected_slice_roster() -> None:
    manifest = ArchiveOperatorManifest.from_json(json.dumps(_manifest()))
    with pytest.raises(ValueError, match="slice roster"):
        resume_archive(
            object(),  # type: ignore[arg-type]
            manifest,
            sdk=object(),  # type: ignore[arg-type]
            actor_id="operator",
            operation_key="selected",
            slice_ids=(),
        )
    with pytest.raises(ValueError, match="slice roster"):
        resume_archive(
            object(),  # type: ignore[arg-type]
            manifest,
            sdk=object(),  # type: ignore[arg-type]
            actor_id="operator",
            operation_key="selected",
            slice_ids=(uuid4(),),
        )
