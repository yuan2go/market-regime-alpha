from datetime import datetime

import pytest

from market_regime_alpha.research.xuntou_pit_v4_contract import XuntouPITSourceArtifact
from market_regime_alpha.research.xuntou_pit_v4_qualification import (
    build_qualified_pit_market_artifact,
    derive_pit_qualification,
)


def test_input_self_declaration_cannot_override_missing_membership() -> None:
    qualification = derive_pit_qualification(
        historical_membership_complete=False,
        security_master_complete=True,
        st_history_complete=True,
        suspension_history_complete=True,
        orderability_complete=True,
        liquidity_unit_verified=True,
        bar_finality_verified=True,
        availability_verified=True,
        evaluation_path_complete=True,
        input_declared_pit_correct=True,
    )
    assert qualification.pit_correct_for_scope is False
    assert "HISTORICAL_MEMBERSHIP_INCOMPLETE" in qualification.reasons


def test_current_membership_backfill_never_qualifies() -> None:
    qualification = derive_pit_qualification(
        historical_membership_complete=True,
        security_master_complete=True,
        st_history_complete=True,
        suspension_history_complete=True,
        orderability_complete=True,
        liquidity_unit_verified=True,
        bar_finality_verified=True,
        availability_verified=True,
        evaluation_path_complete=True,
        membership_sources=("CURRENT_MEMBERSHIP_BACKFILL",),
    )
    assert qualification.pit_correct_for_scope is False
    assert "CURRENT_MEMBERSHIP_BACKFILL_REJECTED" in qualification.reasons


def test_test_fixture_cannot_create_qualified_market_artifact() -> None:
    source = XuntouPITSourceArtifact(
        "XUNTOU",
        "XTQUANT",
        "xuntou-pit-validation-bundle-v4",
        datetime.fromisoformat("2026-07-18T15:00:00+08:00"),
        datetime.fromisoformat("2026-07-18T14:00:00+08:00"),
        datetime.fromisoformat("2026-07-18T14:30:00+08:00"),
        "sha256:" + "0" * 64,
        "EXTERNAL_IMMUTABLE_INPUT",
        "TEST",
        "test",
        "test",
        "Asia/Shanghai",
        "TEST_ONLY_NOT_RESEARCH_EVIDENCE",
    )
    qualification = derive_pit_qualification(
        historical_membership_complete=True,
        security_master_complete=True,
        st_history_complete=True,
        suspension_history_complete=True,
        orderability_complete=True,
        liquidity_unit_verified=True,
        bar_finality_verified=True,
        availability_verified=True,
        evaluation_path_complete=True,
    )
    with pytest.raises(ValueError, match="test-only"):
        build_qualified_pit_market_artifact(source=source, qualification=qualification)
