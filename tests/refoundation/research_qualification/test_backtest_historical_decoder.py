from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest

from market_regime_alpha.interfaces.wp17p_authorities import (
    build_wp17p_authority_catalog,
    build_wp18_authority_catalog,
)
from market_regime_alpha.market.ports import ArchiveTradingSession
from market_regime_alpha.research_qualification.domain import ArtifactBinding
from market_regime_alpha.research_qualification.domain.backtest import (
    AuthorityBinding,
    BacktestComparisonRole,
    BacktestExecutionKind,
    FrozenBacktestEvidence,
    FrozenBacktestSource,
)
from market_regime_alpha.research_qualification.domain.backtest_compatibility import (
    HistoricalBacktestCompatibilityError,
    decode_exact_historical_backtest,
)
from market_regime_alpha.shared.identity import TradingSessionId


def _wp17p_completed_plan():
    identities_and_dates = (
        ("f22ad4c8-26a3-51ad-a317-25e844b1d797", "2026-01-06"),
        ("15c37e3f-852b-5ba9-b389-9dc873027a0b", "2026-01-07"),
        ("4ed96093-fc5d-563b-ae60-be934d70283f", "2026-01-08"),
        ("5ae53357-1b1b-5016-bdf2-5c8e6bf55906", "2026-01-09"),
        ("75fcc28c-63ba-57af-9f57-8a55cdc86741", "2026-01-13"),
        ("9307afff-c94c-5689-bc45-176db342bfcb", "2026-01-14"),
        ("1c36fe80-bdc4-5f8b-8b43-6b98c600a708", "2026-01-15"),
        ("044d6ab9-160a-5f90-b06b-8598c3ae2529", "2026-01-16"),
    )
    sessions = tuple(
        ArchiveTradingSession(
            TradingSessionId(UUID(identity)),
            "XSHG",
            date.fromisoformat(session_date),
            datetime.fromisoformat(f"{session_date}T09:30:00+08:00"),
            datetime.fromisoformat(f"{session_date}T11:30:00+08:00"),
            datetime.fromisoformat(f"{session_date}T13:00:00+08:00"),
            datetime.fromisoformat(f"{session_date}T15:00:00+08:00"),
        )
        for identity, session_date in identities_and_dates
    )
    return build_wp17p_authority_catalog(
        provider_product_id=UUID("922614a5-d37d-5682-8ef9-9d4c9a303d76"),
        market_archive_id=UUID("5b138e9b-232c-59bb-9307-490dd2b21c4e"),
        market_archive_seal_id=UUID("cf8eb599-bf3a-4095-af80-dd638613b5b9"),
        sessions=sessions,
        code_artifact=ArtifactBinding(
            UUID("8b34fc91-f7c0-467c-89b7-742b7fe14129"),
            "7008a6c774f1d5d75aecd620f201eacf53e302ede4666df1834179fe4bc3a17b",
            283,
        ),
        config_artifact=ArtifactBinding(
            UUID("d21e237f-d199-4fc8-9138-58b7204ccf97"),
            "91df1f824dab3cde80eddb348f9a7d3c8b2cd058efffbf7fca686d7f5ad654c2",
            898,
        ),
        provenance_sha256=(
            "3814e484acb2590970f38ec94ea716902e604dfc50c6aea2bd8585ebf1559b8e"
        ),
    ).backtest


def _wp18_definition_plan():
    artifact = ArtifactBinding(UUID(int=1), "1" * 64, 1)
    sessions = tuple(
        ArchiveTradingSession(
            TradingSessionId(UUID(int=1000 + ordinal)),
            "XSHG",
            date(2026, 1, 5) + timedelta(days=ordinal),
            datetime(2026, 1, 5, 1, 30, tzinfo=UTC) + timedelta(days=ordinal),
            datetime(2026, 1, 5, 3, 30, tzinfo=UTC) + timedelta(days=ordinal),
            datetime(2026, 1, 5, 5, 0, tzinfo=UTC) + timedelta(days=ordinal),
            datetime(2026, 1, 5, 7, 0, tzinfo=UTC) + timedelta(days=ordinal),
        )
        for ordinal in range(40)
    )
    return build_wp18_authority_catalog(
        provider_product_id=UUID(int=2),
        market_archive_id=UUID(int=3),
        market_archive_seal_id=UUID(int=4),
        sessions=sessions,
        code_artifact=artifact,
        config_artifact=artifact,
        provenance_sha256="2" * 64,
    ).backtest


def test_exact_completed_wp17p_decodes_to_generic_contract_without_hash_change() -> None:
    plan = _wp17p_completed_plan()
    model_arm_id = plan.arms[1].exploratory_backtest_arm_id

    frozen = decode_exact_historical_backtest(
        plan,
        model_definitions={
            model_arm_id: AuthorityBinding(
                UUID("00c60f93-08d9-555e-af94-6a7853a0bb26"),
                "92aea54f0b2f9f2201e8c651e8a35e30d1536b7c42aad80b78612e6778e35b73",
            )
        },
    )

    assert frozen.source is FrozenBacktestSource.HISTORICAL_EXACT
    assert frozen.evidence is FrozenBacktestEvidence.COMPLETED_ZERO_WRITE
    assert frozen.definition_sha256 == plan.content_sha256
    assert tuple(arm.execution_kind for arm in frozen.arms) == (
        BacktestExecutionKind.RULE,
        BacktestExecutionKind.MODEL,
    )
    assert tuple(arm.comparison_role for arm in frozen.arms) == (
        BacktestComparisonRole.BASELINE,
        BacktestComparisonRole.CHALLENGER,
    )
    assert len(frozen.fold_dependencies) == 1
    assert len(frozen.arm_folds) == 3
    assert frozen.distinct_trading_session_count == 8
    assert frozen.fold_session_binding_count == 8


def test_missing_current_specification_is_not_a_legacy_fallback() -> None:
    plan = _wp17p_completed_plan()
    unknown = replace(plan, exploratory_backtest_run_id=UUID(int=999))

    with pytest.raises(
        HistoricalBacktestCompatibilityError,
        match="not in the exact historical allowlist",
    ):
        decode_exact_historical_backtest(
            unknown,
            model_definitions={
                unknown.arms[1].exploratory_backtest_arm_id: AuthorityBinding(
                    UUID(int=998), "e" * 64
                )
            },
        )


def test_wp18_fixture_proves_definition_equivalence_only() -> None:
    plan = _wp18_definition_plan()
    models = {
        arm.exploratory_backtest_arm_id: AuthorityBinding(UUID(int=900), "9" * 64)
        for arm in plan.arms
        if arm.uses_model
    }

    frozen = decode_exact_historical_backtest(plan, model_definitions=models)

    assert frozen.source is FrozenBacktestSource.HISTORICAL_EXACT
    assert frozen.evidence is FrozenBacktestEvidence.DEFINITION_ONLY
    assert frozen.definition_sha256 == plan.content_sha256
    assert len(frozen.arms) == 4
    assert len(frozen.folds) == 10
    assert len(frozen.fold_dependencies) == 5
    assert frozen.distinct_trading_session_count == 40
    assert frozen.fold_session_binding_count == 40
