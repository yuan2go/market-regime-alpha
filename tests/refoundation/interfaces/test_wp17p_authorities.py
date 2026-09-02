from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest

from market_regime_alpha.interfaces.wp17p_authorities import (
    build_wp17p_authority_catalog,
)
from market_regime_alpha.market.ports import ArchiveTradingSession
from market_regime_alpha.research_qualification.domain import ArtifactBinding
from market_regime_alpha.research_qualification.domain.exploratory_backtest import (
    BacktestArmKind,
    BacktestSessionRole,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    EvaluationSliceKind,
    PartitionPurpose,
)
from market_regime_alpha.shared.identity import TradingSessionId


def _sessions(exchange: str = "XSHG") -> tuple[ArchiveTradingSession, ...]:
    result = []
    for ordinal in range(8):
        session_date = date(2026, 1, 5) + timedelta(days=ordinal)
        opened = datetime(2026, 1, 5 + ordinal, 1, 30, tzinfo=UTC)
        result.append(
            ArchiveTradingSession(
                TradingSessionId(UUID(int=100 + ordinal)),
                exchange,
                session_date,
                opened,
                opened + timedelta(hours=2),
                opened + timedelta(hours=3, minutes=30),
                opened + timedelta(hours=5, minutes=30),
            )
        )
    return tuple(result)


def _catalog():
    artifact = ArtifactBinding(UUID(int=1), "1" * 64, 1)
    return build_wp17p_authority_catalog(
        provider_product_id=UUID(int=2),
        market_archive_id=UUID(int=3),
        market_archive_seal_id=UUID(int=4),
        sessions=_sessions(),
        code_artifact=artifact,
        config_artifact=artifact,
        provenance_sha256="2" * 64,
    )


def test_catalog_freezes_one_hypothesis_two_arms_and_chronological_folds() -> None:
    catalog = _catalog()

    assert tuple(item.kind for item in catalog.backtest.arms) == (
        BacktestArmKind.RULE_BASELINE,
        BacktestArmKind.MODEL_CHALLENGER,
    )
    assert tuple(item.purpose for item in catalog.backtest.folds) == (
        PartitionPurpose.FIT,
        PartitionPurpose.VALIDATION,
    )
    assert all(
        tuple(item.role for item in fold.sessions)
        == (
            BacktestSessionRole.FIT_INPUT,
            BacktestSessionRole.PURGE,
            BacktestSessionRole.EVALUATION,
            BacktestSessionRole.EMBARGO,
        )
        for fold in catalog.backtest.folds
    )
    assert catalog.candidate_policy.requested_top_k == 5
    assert len(catalog.validation_evaluation_protocol.metrics) == 22
    assert all(item.slice_kind is EvaluationSliceKind.EXPLORATORY_BACKTEST_ARM for item in catalog.validation_evaluation_protocol.metrics)


def test_catalog_rejects_joint_or_ambiguous_calendar_roster() -> None:
    artifact = ArtifactBinding(UUID(int=1), "1" * 64, 1)
    with pytest.raises(ValueError, match="XSHG"):
        build_wp17p_authority_catalog(
            provider_product_id=UUID(int=2),
            market_archive_id=UUID(int=3),
            market_archive_seal_id=UUID(int=4),
            sessions=_sessions("XSHE"),
            code_artifact=artifact,
            config_artifact=artifact,
            provenance_sha256="2" * 64,
        )
