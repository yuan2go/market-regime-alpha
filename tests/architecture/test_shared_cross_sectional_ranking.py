from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ACTIVE_CONSUMERS = (
    ROOT / "src/market_regime_alpha/candidates/baselines.py",
    ROOT / "src/market_regime_alpha/candidates/composite_baseline.py",
    ROOT / "src/market_regime_alpha/candidates/evaluation.py",
    ROOT / "src/market_regime_alpha/platform/prediction_run.py",
    ROOT / "src/market_regime_alpha/research/candidate_discovery/contracts.py",
    ROOT / "src/market_regime_alpha/research/candidate_discovery/model.py",
    ROOT / "src/market_regime_alpha/research/pit_replication_success_v2_features.py",
    ROOT / "src/market_regime_alpha/application/research_validation/ablation.py",
)
FORBIDDEN_PRIVATE_IMPLEMENTATIONS = {
    "_directional_rank_percentiles",
    "_within_session_percentile_scores",
}
EVIDENCE_PRODUCER = (
    ROOT
    / "src/market_regime_alpha/application/historical_corpus/evidence_producer.py"
)


def test_active_ranking_consumers_use_one_public_kernel() -> None:
    for path in ACTIVE_CONSUMERS:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        definitions = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        assert "market_regime_alpha.research.cross_sectional_ranking" in imports, path
        assert definitions.isdisjoint(FORBIDDEN_PRIVATE_IMPLEMENTATIONS), path


def test_historical_evidence_producer_does_not_rank_or_build_portfolios() -> None:
    text = EVIDENCE_PRODUCER.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }

    assert imported_names.isdisjoint(
        {
            "build_cross_strategy_portfolio",
            "composite_percentile_scores",
            "fractional_boundary_weights",
            "rank_percentiles",
            "run_incremental_alpha_ablation_suite",
        }
    )
    assert "RESEARCH_EVALUATION" in text
    assert "run_precomputed_alpha_ablation_suite" in imported_names
