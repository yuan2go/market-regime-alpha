from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from market_regime_alpha.research_qualification.domain.exploratory_backtest import (
    BacktestArmKind,
    BacktestArmPlan,
    BacktestCostAssumption,
    BacktestCostKind,
    BacktestFoldPlan,
    BacktestFoldSessionPlan,
    BacktestSessionRole,
    ExploratoryBacktestDatasetScope,
    ExploratoryBacktestRunPlan,
)
from market_regime_alpha.research_qualification.domain.exploratory import (
    ExploratoryRetrospectiveDatasetScope,
)
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionPurpose,
)


def _id(value: int) -> UUID:
    return UUID(int=value)


def _artifact(value: int) -> ArtifactBinding:
    return ArtifactBinding(_id(value), f"{value:064x}", value)


def _fold(
    fold_id: int,
    ordinal: int,
    purpose: PartitionPurpose,
    first_day: int,
) -> BacktestFoldPlan:
    roles = (
        BacktestSessionRole.FIT_INPUT,
        BacktestSessionRole.PURGE,
        BacktestSessionRole.EVALUATION,
        BacktestSessionRole.EMBARGO,
    )
    sessions = tuple(
        BacktestFoldSessionPlan(
            exploratory_backtest_fold_session_id=_id(fold_id * 100 + index),
            ordinal=index,
            trading_session_id=_id(fold_id * 1000 + index),
            session_date=date(2026, 1, first_day + index - 1),
            role=role,
        )
        for index, role in enumerate(roles, start=1)
    )
    return BacktestFoldPlan(
        exploratory_backtest_fold_id=_id(fold_id),
        ordinal=ordinal,
        purpose=purpose,
        exchange_code="XSHG",
        purge_sessions=1,
        embargo_sessions=1,
        evaluation_protocol_id=_id(fold_id + 20),
        evaluation_protocol_sha256=f"{fold_id + 20:064x}",
        sessions=sessions,
    )


def _plan() -> ExploratoryBacktestRunPlan:
    return ExploratoryBacktestRunPlan(
        exploratory_backtest_run_id=_id(1),
        run_code="wp17p-pilot",
        generation=1,
        market_archive_id=_id(2),
        market_archive_seal_id=_id(3),
        hypothesis="Transparent rank baseline versus one deterministic ridge model.",
        target_definition_id=_id(4),
        target_version=1,
        target_definition_sha256="4" * 64,
        feature_definitions=((_id(5), "5" * 64),),
        candidate_policy_id=_id(6),
        candidate_policy_sha256="6" * 64,
        context_policy_id=_id(7),
        context_policy_sha256="7" * 64,
        strategy_version_id=_id(8),
        strategy_version_sha256="8" * 64,
        portfolio_policy_id=_id(9),
        portfolio_policy_sha256="9" * 64,
        risk_policy_id=_id(10),
        risk_policy_sha256="a" * 64,
        arms=(
            BacktestArmPlan(_id(11), 1, BacktestArmKind.RULE_BASELINE),
            BacktestArmPlan(_id(12), 2, BacktestArmKind.MODEL_CHALLENGER),
        ),
        folds=(
            _fold(13, 1, PartitionPurpose.FIT, 2),
            _fold(14, 2, PartitionPurpose.VALIDATION, 7),
        ),
        cost_assumptions=(
            BacktestCostAssumption(_id(15), 1, BacktestCostKind.COMMISSION_BPS, Decimal("3")),
            BacktestCostAssumption(_id(16), 2, BacktestCostKind.SLIPPAGE_BPS, Decimal("5")),
        ),
        random_seed=1729,
        code_artifact=_artifact(17),
        config_artifact=_artifact(18),
        provenance_sha256="b" * 64,
    )


def test_exploratory_backtest_freezes_two_arms_and_chronological_folds() -> None:
    plan = _plan()

    assert tuple(arm.kind for arm in plan.arms) == (
        BacktestArmKind.RULE_BASELINE,
        BacktestArmKind.MODEL_CHALLENGER,
    )
    assert plan.evidence_lane == "EXPLORATORY_RETROSPECTIVE"
    assert plan.arm_roster_sha256
    assert plan.fold_roster_sha256
    assert plan.session_count == 8
    assert plan.content_sha256


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda plan: replace(plan, arms=plan.arms[:1]), "exactly two"),
        (
            lambda plan: replace(
                plan,
                arms=(plan.arms[1], plan.arms[0]),
            ),
            "arm roster",
        ),
        (
            lambda plan: replace(
                plan,
                folds=(plan.folds[1], plan.folds[0]),
            ),
            "fold ordinals",
        ),
        (
            lambda plan: replace(
                plan,
                folds=(
                    replace(plan.folds[0], purpose=PartitionPurpose.LOCKED_OOS),
                    plan.folds[1],
                ),
            ),
            "exploratory fold purpose",
        ),
    ),
)
def test_exploratory_backtest_rejects_mutable_or_formal_shapes(mutation, message) -> None:
    with pytest.raises(ValueError, match=message):
        mutation(_plan())


def test_fold_requires_relational_purge_and_embargo_rosters() -> None:
    fold = _fold(30, 1, PartitionPurpose.FIT, 12)

    with pytest.raises(ValueError, match="purge roster"):
        replace(fold, purge_sessions=2)
    with pytest.raises(ValueError, match="chronological"):
        replace(
            fold,
            sessions=(
                replace(fold.sessions[0], session_date=fold.sessions[1].session_date),
                replace(fold.sessions[1], session_date=fold.sessions[0].session_date),
                *fold.sessions[2:],
            ),
        )


def test_backtest_dataset_scope_freezes_archive_and_exact_member_identity() -> None:
    retrospective = ExploratoryRetrospectiveDatasetScope(
        market_archive_id=_id(80),
        market_archive_seal_id=_id(81),
        knowledge_cutoff=datetime(2026, 9, 3, tzinfo=timezone.utc),
        simulated_event_cutoff=datetime(2026, 1, 8, tzinfo=timezone.utc),
    )
    scope = ExploratoryBacktestDatasetScope(
        retrospective=retrospective,
        exploratory_backtest_run_id=_id(82),
        exploratory_backtest_arm_id=_id(83),
        exploratory_backtest_fold_id=_id(84),
        exploratory_backtest_fold_session_id=_id(85),
    )

    assert scope.content_sha256
