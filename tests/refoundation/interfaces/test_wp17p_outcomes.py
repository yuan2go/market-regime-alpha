from __future__ import annotations

from datetime import UTC, date, datetime, time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from market_regime_alpha.interfaces.wp17p_outcomes import (
    Wp17pOutcomeOperations,
    outcome_observation_cutoff,
)
from market_regime_alpha.research_qualification.domain.target_vocabulary import (
    TargetCheckpointRole,
)


def _catalog():
    first_id = uuid4()
    second_id = uuid4()
    session_id = uuid4()
    return SimpleNamespace(
        target=SimpleNamespace(
            checkpoints=(
                SimpleNamespace(
                    role=TargetCheckpointRole.DECISION_REFERENCE,
                    session_offset=0,
                    local_time=time(14, 55),
                    timezone_name="Asia/Shanghai",
                ),
                SimpleNamespace(
                    role=TargetCheckpointRole.OUTCOME_OBSERVATION,
                    session_offset=1,
                    local_time=time(10, 30),
                    timezone_name="Asia/Shanghai",
                ),
            )
        ),
        backtest=SimpleNamespace(
            exploratory_backtest_run_id=uuid4(),
            folds=(
                SimpleNamespace(
                    sessions=(
                        SimpleNamespace(
                            exploratory_backtest_fold_session_id=session_id,
                            trading_session_id=first_id,
                            session_date=date(2026, 1, 5),
                        ),
                        SimpleNamespace(
                            exploratory_backtest_fold_session_id=uuid4(),
                            trading_session_id=second_id,
                            session_date=date(2026, 1, 6),
                        ),
                    )
                ),
            ),
        ),
    ), session_id


def test_outcome_cutoff_uses_declared_next_trading_session() -> None:
    catalog, fold_session_id = _catalog()

    cutoff = outcome_observation_cutoff(catalog, fold_session_id)

    assert cutoff == datetime(2026, 1, 6, 2, 30, tzinfo=UTC)


def test_outcome_cutoff_rejects_incomplete_horizon() -> None:
    catalog, fold_session_id = _catalog()
    catalog.backtest = SimpleNamespace(
        exploratory_backtest_run_id=catalog.backtest.exploratory_backtest_run_id,
        folds=(
            SimpleNamespace(sessions=(catalog.backtest.folds[0].sessions[0],)),
        ),
    )

    with pytest.raises(ValueError, match="horizon"):
        outcome_observation_cutoff(catalog, fold_session_id)


def test_outcome_operations_reject_noncanonical_code_sha() -> None:
    with pytest.raises(ValueError, match="exact Git SHA"):
        Wp17pOutcomeOperations(SimpleNamespace(), code_sha="g" * 40)
