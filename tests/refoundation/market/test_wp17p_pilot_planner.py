from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

import pytest

from market_regime_alpha.interfaces.wp17p_pilot import (
    build_prospective_manifest,
    build_retrospective_manifest,
    select_deterministic_pilot,
)
from market_regime_alpha.market.domain import ArchiveLane


PRODUCT_ID = UUID("10000000-0000-0000-0000-000000000001")
CODE_ARTIFACT_ID = UUID("20000000-0000-0000-0000-000000000001")
CONFIG_ARTIFACT_ID = UUID("30000000-0000-0000-0000-000000000001")


def _codes(count: int = 40) -> tuple[str, ...]:
    return tuple(f"sh.{600000 + item:06d}" for item in range(count))


def test_pilot_roster_is_order_independent_exact_and_never_return_selected() -> None:
    expected = select_deterministic_pilot(_codes())

    assert len(expected) == 32
    assert expected == select_deterministic_pilot(tuple(reversed(_codes())))
    assert expected == tuple(sorted(expected))
    with pytest.raises(ValueError, match="at least 32"):
        select_deterministic_pilot(_codes(31))
    with pytest.raises(ValueError, match="BaoStock A-share"):
        select_deterministic_pilot((*_codes(39), "bj.430001"))


def test_retrospective_manifest_freezes_monthly_real_request_roster() -> None:
    pilot = select_deterministic_pilot(_codes())
    manifest = build_retrospective_manifest(
        provider_product_id=PRODUCT_ID,
        code_artifact_id=CODE_ARTIFACT_ID,
        config_artifact_id=CONFIG_ARTIFACT_ID,
        execution_date=date(2026, 3, 10),
        membership_dates=(date(2026, 1, 5), date(2026, 3, 9)),
        security_master_codes=_codes(),
        pilot_codes=pilot,
        provenance_sha256="a" * 64,
    )

    assert manifest.start_request.lane is ArchiveLane.RETROSPECTIVE_BACKFILL
    assert manifest.start_request.instrument_scope == "CSI300_STABLE_HASH_32_ENGINEERING_PILOT"
    assert len(manifest.slices) == 1 + 40 + 2 + (32 * 3 * 2)
    assert tuple(item.plan.ordinal for item in manifest.slices) == tuple(
        range(1, len(manifest.slices) + 1)
    )
    kinds = {item.plan.expected_fact_kind for item in manifest.slices}
    assert kinds == {
        "TRADING_SESSION",
        "INSTRUMENT",
        "CLASSIFICATION_MEMBERSHIP",
        "MARKET_BAR_DAILY",
        "MARKET_BAR_5M",
    }
    assert all("2025" not in item.capture_request.resource for item in manifest.slices)
    assert manifest == type(manifest).from_json(manifest.to_json())


def test_archive_generation_creates_a_new_identity_without_changing_scope() -> None:
    pilot = select_deterministic_pilot(_codes())
    common = {
        "provider_product_id": PRODUCT_ID,
        "code_artifact_id": CODE_ARTIFACT_ID,
        "config_artifact_id": CONFIG_ARTIFACT_ID,
        "execution_date": date(2026, 3, 10),
        "membership_dates": (date(2026, 1, 5), date(2026, 3, 9)),
        "security_master_codes": _codes(),
        "pilot_codes": pilot,
        "provenance_sha256": "a" * 64,
    }

    generation_one = build_retrospective_manifest(**common, archive_generation=1)
    generation_two = build_retrospective_manifest(**common, archive_generation=2)

    assert generation_one.start_request.market_archive_id != (
        generation_two.start_request.market_archive_id
    )
    assert generation_one.start_request.archive_code.endswith("_g001")
    assert generation_two.start_request.archive_code.endswith("_g002")
    assert generation_one.start_request.instrument_scope_sha256 == (
        generation_two.start_request.instrument_scope_sha256
    )
    assert tuple(item.plan.scope_key for item in generation_one.slices) == tuple(
        item.plan.scope_key for item in generation_two.slices
    )
    with pytest.raises(ValueError, match="archive_generation must be positive"):
        build_retrospective_manifest(**common, archive_generation=0)


def test_prospective_manifest_contains_only_post_start_scheduled_windows() -> None:
    planned_after = datetime(2026, 9, 3, 8, 0, tzinfo=UTC)
    manifest = build_prospective_manifest(
        provider_product_id=PRODUCT_ID,
        code_artifact_id=CODE_ARTIFACT_ID,
        config_artifact_id=CONFIG_ARTIFACT_ID,
        archive_not_before=planned_after,
        next_session_date=date(2026, 9, 4),
        pilot_codes=select_deterministic_pilot(_codes()),
        provenance_sha256="b" * 64,
        archive_generation=3,
    )

    assert manifest.start_request.lane is ArchiveLane.PROSPECTIVE_CONTEMPORANEOUS
    assert manifest.start_request.archive_code.endswith("_g003")
    assert all(
        item.plan.event_window_start >= planned_after for item in manifest.slices
    )
    assert manifest.slices[0].schedule_slot == "ARCHIVE_START_SMOKE"
    assert {item.schedule_slot for item in manifest.slices[1:]} == {
        "DECISION_NEAR",
        "POST_CLOSE",
        "EVENING",
        "NEXT_PREOPEN",
        "NEXT_POSTCLOSE",
        "LATER_VERIFICATION",
    }
    assert manifest == type(manifest).from_json(manifest.to_json())
