from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from market_regime_alpha.application.historical_corpus.golden_loop import (
    GoldenLoopScoringContract,
    GoldenLoopSessionEvaluation,
    evaluate_golden_loop_session,
)
from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
    HistoricalSessionComponent,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId


AT = datetime(2026, 8, 20, 7, 0, tzinfo=UTC)


def test_golden_loop_v2_scoring_contract_is_content_addressed_and_frozen() -> None:
    contract = GoldenLoopScoringContract.create_v2()

    assert contract.scoring_contract == (
        "WITHIN_SESSION_TIE_AWARE_FACTOR_PERCENTILE_MEAN_V2"
    )
    assert contract.selection_policy == "FRACTIONAL_BOUNDARY_WEIGHT_V1"
    assert contract.missing_policy == "FIXED_DENOMINATOR_NEUTRAL_0_5_V1"
    assert contract.tie_policy == "ARITHMETIC_MIDRANK_V1"
    assert contract.constant_policy == "NEUTRAL_0_5_NO_RANKING_INFORMATION_V1"
    assert contract.top_k == 10
    assert GoldenLoopScoringContract.from_canonical_dict(
        contract.to_canonical_dict()
    ) == contract
    assert contract.reference.artifact_kind == "GOLDEN_LOOP_SCORING_CONTRACT"


def test_session_evaluation_freezes_canonical_sources_and_not_estimable_layers() -> None:
    panel, outcome = _components()

    evaluation = _evaluate(panel, outcome)

    assert {item.artifact_kind for item in evaluation.source_references} >= {
        "HISTORICAL_RESEARCH_PANEL",
        "HISTORICAL_OUTCOME",
        "MULTI_STRATEGY_CYCLE",
        "CROSS_STRATEGY_PORTFOLIO",
        "RESEARCH_EXPERIMENT_DEFINITION",
        "GOLDEN_LOOP_SCORING_CONTRACT",
    }
    assert evaluation.portfolio_status == "NO_ACTION"
    assert evaluation.portfolio_line_count == 0
    assert evaluation.layer_diagnostics["theme"]["status"] == "CONSTANT"
    assert evaluation.layer_diagnostics["candidate"]["status"] == "NOT_ESTIMABLE"
    assert evaluation.layer_diagnostics["signal"]["observed_count"] == 0
    assert evaluation.layer_diagnostics["forecast"]["observed_count"] == 0
    assert GoldenLoopSessionEvaluation.from_canonical_dict(
        evaluation.to_canonical_dict()
    ).to_canonical_dict() == evaluation.to_canonical_dict()


def test_constant_factor_has_zero_selection_increment() -> None:
    panel, outcome = _components()
    evaluation = _evaluate(panel, outcome)
    by_variant = {str(item["variant_id"]): item for item in evaluation.variants}

    without_theme = _weights(
        by_variant["price_volume_market_regime_etf"]
    )
    with_theme = _weights(
        by_variant["price_volume_market_regime_etf_theme"]
    )

    assert without_theme == with_theme
    assert sum(with_theme.values(), Decimal("0")) == Decimal("10")


def test_evaluation_is_invariant_to_row_permutation_and_symbol_renaming() -> None:
    panel, outcome = _components()
    renamed_panel, renamed_outcome = _components(
        rename=True,
        reverse=True,
    )

    original = _evaluate(panel, outcome)
    renamed = _evaluate(renamed_panel, renamed_outcome)
    original_rows = _rows_by_price(original.variants[0])
    renamed_rows = _rows_by_price(renamed.variants[0])

    assert original_rows == renamed_rows


def test_evaluation_rejects_a_noncanonical_cycle_reference() -> None:
    panel, outcome = _components()

    with pytest.raises(ValueError, match="MULTI_STRATEGY_CYCLE"):
        evaluate_golden_loop_session(
            panel=panel,
            outcome=outcome,
            experiment_reference=_reference("RESEARCH_EXPERIMENT_DEFINITION", "exp"),
            cycle_reference=_reference("STRATEGY_RUN", "cycle"),
            portfolio_reference=_reference("CROSS_STRATEGY_PORTFOLIO", "portfolio"),
            portfolio_status="NO_ACTION",
            portfolio_line_count=0,
        )


def _evaluate(
    panel: HistoricalSessionComponent,
    outcome: HistoricalSessionComponent,
) -> GoldenLoopSessionEvaluation:
    return evaluate_golden_loop_session(
        panel=panel,
        outcome=outcome,
        experiment_reference=_reference("RESEARCH_EXPERIMENT_DEFINITION", "exp"),
        cycle_reference=_reference("MULTI_STRATEGY_CYCLE", "cycle"),
        portfolio_reference=_reference("CROSS_STRATEGY_PORTFOLIO", "portfolio"),
        portfolio_status="NO_ACTION",
        portfolio_line_count=0,
    )


def _components(
    *,
    rename: bool = False,
    reverse: bool = False,
) -> tuple[HistoricalSessionComponent, HistoricalSessionComponent]:
    rows = [
        {
            "symbol": f"{'RENAMED' if rename else 'SYMBOL'}-{index:02d}",
            "target_return": str(Decimal(index - 6) / Decimal("1000")),
            "cost_return": "0.0021",
            "mfe": "0.01",
            "mae": "-0.01",
            "selected": index >= 10,
            "factor_values": {
                "price": None if index == 6 else str(index),
                "volume": str(index % 3),
                "theme": "1",
            },
        }
        for index in range(12)
    ]
    if reverse:
        rows.reverse()
    common = {
        "run_id": ArtifactId("historical-run-golden-loop-test"),
        "session_id": ArtifactId("historical-session-golden-loop-test"),
        "trading_date": date(2026, 8, 19),
        "source_max_event_time": AT,
        "materialized_at": AT,
        "source_references": (_reference("TEST_OWNER", "source"),),
    }
    panel = HistoricalSessionComponent.create(
        **common,
        component_kind=HistoricalComponentKind.RESEARCH_PANEL,
        payload={"rows": rows},
    )
    outcome = HistoricalSessionComponent.create(
        **common,
        component_kind=HistoricalComponentKind.OUTCOME,
        payload={"status": "SETTLED"},
    )
    return panel, outcome


def _reference(kind: str, identity: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(f"{kind.lower()}-{identity}"),
        f"sha256:{identity.encode().hex().ljust(64, '0')[:64]}",
    )


def _weights(variant: object) -> dict[str, Decimal]:
    assert isinstance(variant, dict) or hasattr(variant, "get")
    rows = variant["rows"]  # type: ignore[index]
    return {str(row["symbol"]): Decimal(str(row["top_weight"])) for row in rows}


def _rows_by_price(variant: object) -> dict[str, tuple[str, str]]:
    assert isinstance(variant, dict) or hasattr(variant, "get")
    rows = variant["rows"]  # type: ignore[index]
    return {
        str(index): (str(row["score"]), str(row["top_weight"]))
        for index, row in enumerate(
            sorted(rows, key=lambda item: Decimal(str(item["realized_return"])))
        )
    }
