from __future__ import annotations

from pathlib import Path


BASELINE = Path(__file__).resolve().parents[3] / "src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql"


def test_model_training_reproducibility_is_a_root_owned_typed_closure() -> None:
    sql = BASELINE.read_text(encoding="utf-8")

    assert "CREATE TABLE mra.model_training_reproducibility" in sql
    assert "CREATE TABLE mra.model_training_dependency" in sql
    assert "CREATE TABLE mra.model_training_hyperparameter" in sql
    assert "model_training_run_id uuid PRIMARY KEY" in sql
    assert "training_knowledge_cutoff timestamptz NOT NULL" in sql
    assert "uv_lock_sha256 text NOT NULL" in sql
    assert "value_type text NOT NULL" in sql
    assert "CREATE FUNCTION mra.validate_model_training_reproducibility()" in sql
    assert "outcome.knowledge_cutoff > reproducibility.training_knowledge_cutoff" in sql
    assert "current Backtest ModelTrainingRun requires reproducibility closure" in sql


def test_model_reproducibility_closure_is_append_only() -> None:
    sql = BASELINE.read_text(encoding="utf-8")

    for table in (
        "model_training_reproducibility",
        "model_training_dependency",
        "model_training_hyperparameter",
    ):
        assert f"CREATE TRIGGER {table}_append_only" in sql
