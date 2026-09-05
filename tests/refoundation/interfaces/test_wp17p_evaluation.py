from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from market_regime_alpha.interfaces.wp17p_evaluation import wp17p_partition_plan
from market_regime_alpha.research_qualification.domain import ArtifactBinding
from market_regime_alpha.research_qualification.domain.exploratory_backtest import (
    BacktestFoldSessionPlan,
    BacktestSessionRole,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionOverlapPolicy,
    PartitionPurpose,
)


def _binding() -> ArtifactBinding:
    return ArtifactBinding(uuid4(), "a" * 64, 7)


def _inputs():
    fold_id = uuid4()
    fold_session_id = uuid4()
    trading_session_id = uuid4()
    artifact = _binding()
    catalog = SimpleNamespace(
        target=SimpleNamespace(
            target_definition_id=uuid4(),
            version=1,
            content_sha256="b" * 64,
        ),
        backtest=SimpleNamespace(
            generation=1,
            exploratory_backtest_run_id=uuid4(),
            code_artifact=artifact,
            config_artifact=artifact,
            provenance_sha256="c" * 64,
            folds=(
                SimpleNamespace(
                    exploratory_backtest_fold_id=fold_id,
                    ordinal=2,
                    purpose=PartitionPurpose.VALIDATION,
                    exchange_code="XSHG",
                    purge_sessions=1,
                    embargo_sessions=1,
                    sessions=(
                        BacktestFoldSessionPlan(
                            exploratory_backtest_fold_session_id=fold_session_id,
                            ordinal=1,
                            trading_session_id=trading_session_id,
                            session_date=date(2026, 1, 14),
                            role=BacktestSessionRole.EVALUATION,
                        ),
                    ),
                ),
            ),
        ),
    )
    dataset = SimpleNamespace(
        backtest_scope=SimpleNamespace(
            exploratory_backtest_fold_id=fold_id,
            exploratory_backtest_fold_session_id=fold_session_id,
        )
    )
    return catalog, dataset, trading_session_id


@pytest.mark.parametrize(
    ("generation", "expected_code"),
    [(1, "wp17p_validation_partition"), (2, "wp18_validation_02_partition")],
)
def test_partition_plan_freezes_fold_calendar_and_protection(
    generation: int, expected_code: str
) -> None:
    catalog, dataset, trading_session_id = _inputs()
    catalog.backtest.generation = generation

    plan = wp17p_partition_plan(catalog, (dataset,))

    assert plan.partition_code == expected_code
    assert plan.purpose is PartitionPurpose.VALIDATION
    assert plan.overlap_policy is PartitionOverlapPolicy.PURGED_WALK_FORWARD
    assert plan.exchange_code == "XSHG"
    assert plan.decision_start_session_id == trading_session_id
    assert plan.decision_end_session_id == trading_session_id
    assert plan.purge_before_sessions == 1
    assert plan.embargo_sessions == 1


def test_partition_plan_rejects_undeclared_dataset_session() -> None:
    catalog, dataset, _ = _inputs()
    dataset.backtest_scope = SimpleNamespace(
        exploratory_backtest_fold_id=uuid4(),
        exploratory_backtest_fold_session_id=uuid4(),
    )

    with pytest.raises(ValueError, match="absent or ambiguous"):
        wp17p_partition_plan(catalog, (dataset,))
