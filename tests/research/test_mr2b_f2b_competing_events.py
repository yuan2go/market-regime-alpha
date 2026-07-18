from market_regime_alpha.research.mr2b_f2b_competing_events import (
    COMPETING_EVENT_TARGET_ID,
    build_competing_event_diagnostics,
)


def test_competing_events_keep_ambiguous_separate_and_do_not_assess_primary() -> None:
    targets = tuple(
        {
            "decision_date": "2026-01-01",
            "symbol": symbol,
            "target_id": COMPETING_EVENT_TARGET_ID,
            "status": "AVAILABLE",
            "outcome": outcome,
        }
        for symbol, outcome in zip(
            ("A", "B", "C", "D"),
            ("UP_FIRST", "DOWN_FIRST", "TIMEOUT", "AMBIGUOUS"),
            strict=True,
        )
    )
    result = build_competing_event_diagnostics(
        target_rows=targets,
        ranking_rows=(),
        multiseed_selection_rows=(),
        primary_model_id="prr-mvp-1-b1-e-v1",
        top_k=5,
    )
    assert result.status == "COMPETING_EVENT_EVIDENCE_UNAVAILABLE"
    assert result.target_contract_id == COMPETING_EVENT_TARGET_ID


def test_competing_event_rates_keep_all_four_outcomes_and_explicit_denominators() -> None:
    outcomes = {"A": "UP_FIRST", "B": "DOWN_FIRST", "C": "TIMEOUT", "D": "AMBIGUOUS"}
    targets = tuple(
        {
            "decision_date": "2026-01-01", "symbol": symbol,
            "target_id": COMPETING_EVENT_TARGET_ID, "status": "AVAILABLE", "outcome": outcome,
        }
        for symbol, outcome in outcomes.items()
    )
    rankings = tuple(
        {
            "decision_date": "2026-01-01", "symbol": symbol,
            "model_id": "prr-mvp-1-b1-e-v1",
            "target_id": "target-r5-decision-reference-to-next-session-close-return-v1",
            "eligible_for_ranking": True, "rank": rank,
        }
        for rank, symbol in enumerate(outcomes, start=1)
    )
    selections = tuple(
        {"decision_date": "2026-01-01", "model_id": "prr-mvp-1-b1-e-v1", "seed": seed, "slot_index": slot, "symbol": symbol}
        for seed, symbols in ((0, ("A", "B")), (1, ("C", "D")))
        for slot, symbol in enumerate(symbols, start=1)
    )
    result = build_competing_event_diagnostics(
        target_rows=targets, ranking_rows=rankings, multiseed_selection_rows=selections,
        primary_model_id="prr-mvp-1-b1-e-v1", top_k=2,
    )
    assert result.status == "AVAILABLE"
    model = next(row for row in result.rows if row["scope"] == "B1_E_TOP5")
    assert model["observed_count"] == 2
    assert model["UP_FIRST_rate"] == 0.5
    assert model["DOWN_FIRST_rate"] == 0.5
    assert model["AMBIGUOUS_rate"] == 0.0
