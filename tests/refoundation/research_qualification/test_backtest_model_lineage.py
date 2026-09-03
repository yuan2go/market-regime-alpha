from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import pytest

from market_regime_alpha.research_qualification.domain.backtest_execution import (
    BacktestModelLineage,
)


def _id(value: int) -> UUID:
    return UUID(int=value)


def _lineage() -> BacktestModelLineage:
    return BacktestModelLineage(
        backtest_model_lineage_id=_id(1),
        exploratory_backtest_run_id=_id(2),
        specification_sha256="a" * 64,
        model_training_requirement_id=_id(3),
        backtest_evaluation_execution_id=_id(4),
        fit_evaluation_run_id=_id(5),
        model_id=_id(6),
        model_training_run_id=_id(7),
        model_training_run_sha256="b" * 64,
        model_training_reproducibility_sha256="c" * 64,
        model_version_id=_id(8),
        model_version_sha256="d" * 64,
    )


def test_backtest_model_lineage_binds_exact_fit_evaluation_training_and_version() -> None:
    lineage = _lineage()

    assert len(str(lineage.content_sha256)) == 64
    assert lineage.model_training_requirement_id == _id(3)


def test_backtest_model_lineage_rejects_non_hash_bindings() -> None:
    with pytest.raises(ValueError):
        replace(_lineage(), model_version_sha256="not-a-hash")
