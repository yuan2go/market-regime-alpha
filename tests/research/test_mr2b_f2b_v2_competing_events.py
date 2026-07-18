from market_regime_alpha.research.mr2b_f2b_competing_events import COMPETING_EVENT_TARGET_ID
from market_regime_alpha.research.mr2b_f2b_v2_competing_events import (
    build_competing_event_diagnostics_v2,
)


def test_competing_event_missing_counts_are_bound_to_each_scope() -> None:
    symbols = tuple("ABCDEFGH")
    targets = tuple(
        {
            "decision_date": "2026-01-01",
            "symbol": symbol,
            "target_id": COMPETING_EVENT_TARGET_ID,
            "status": "AVAILABLE" if index < 5 else "UNAVAILABLE",
            "outcome": "UP_FIRST" if index < 5 else None,
        }
        for index, symbol in enumerate(symbols)
    )
    rankings = tuple(
        {
            "decision_date": "2026-01-01",
            "symbol": symbol,
            "model_id": "prr-mvp-1-b1-e-v1",
            "target_id": "target-r5-decision-reference-to-next-session-close-return-v1",
            "eligible_for_ranking": True,
            "rank": rank,
        }
        for rank, symbol in enumerate(symbols, start=1)
    )
    selections = tuple(
        {
            "decision_date": "2026-01-01",
            "model_id": "prr-mvp-1-b1-e-v1",
            "seed": seed,
            "slot_index": slot,
            "symbol": symbol,
        }
        for seed in (0, 1)
        for slot, symbol in enumerate(symbols[:5], start=1)
    )
    result = build_competing_event_diagnostics_v2(
        target_rows=targets,
        ranking_rows=rankings,
        multiseed_selection_rows=selections,
        primary_model_id="prr-mvp-1-b1-e-v1",
        top_k=5,
    )
    assert result.coverage.top5_coverage == 1.0
    assert result.coverage.top5_missing_target_count == 0
    assert result.coverage.population_missing_target_count == 3
    assert result.coverage.global_unavailable_target_count == 3
