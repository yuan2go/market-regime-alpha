import pytest

from market_regime_alpha.research.pit_replication_runner import validate_replication_tables


def test_unknown_buyability_never_enters_candidate_population() -> None:
    universe = ({"decision_date": "2026-01-01", "symbol": "000001.SZ", "is_member": True, "membership_source": "HISTORICAL_PIT"},)
    eligibility = ({"decision_date": "2026-01-01", "symbol": "000001.SZ", "status": "UNKNOWN", "buyability": "UNKNOWN"},)
    population = ({"decision_date": "2026-01-01", "symbol": "000001.SZ"},)
    with pytest.raises(ValueError, match="ELIGIBLE"):
        validate_replication_tables(universe, eligibility, population, (), ())


def test_matched_k_must_use_same_population() -> None:
    universe = ({"decision_date": "2026-01-01", "symbol": "000001.SZ", "is_member": True, "membership_source": "HISTORICAL_PIT"},)
    eligibility = ({"decision_date": "2026-01-01", "symbol": "000001.SZ", "status": "ELIGIBLE", "buyability": "BUYABLE"},)
    population = ({"decision_date": "2026-01-01", "symbol": "000001.SZ"},)
    rankings = ({"decision_date": "2026-01-01", "symbol": "000001.SZ", "model_id": "prr-mvp-1-b1-e-v1", "rank": 1},)
    selections = ({"decision_date": "2026-01-01", "symbol": "000002.SZ", "seed": 0, "slot_index": 1},)
    with pytest.raises(ValueError, match="population"):
        validate_replication_tables(universe, eligibility, population, rankings, selections)


def test_current_membership_backfill_is_rejected() -> None:
    universe = ({"decision_date": "2026-01-01", "symbol": "000001.SZ", "is_member": True, "membership_source": "CURRENT_WATCHLIST_BACKFILL"},)
    with pytest.raises(ValueError, match="current-watchlist"):
        validate_replication_tables(universe, (), (), (), ())


def test_duplicate_population_and_non_contiguous_rank_fail_closed() -> None:
    universe = (
        {"decision_date": "2026-01-01", "symbol": "000001.SZ", "is_member": True, "membership_source": "HISTORICAL_PIT"},
        {"decision_date": "2026-01-01", "symbol": "000002.SZ", "is_member": True, "membership_source": "HISTORICAL_PIT"},
    )
    eligibility = tuple(
        {"decision_date": "2026-01-01", "symbol": symbol, "status": "ELIGIBLE", "buyability": "BUYABLE"}
        for symbol in ("000001.SZ", "000002.SZ")
    )
    duplicate_population = (
        {"decision_date": "2026-01-01", "symbol": "000001.SZ"},
        {"decision_date": "2026-01-01", "symbol": "000001.SZ"},
    )
    with pytest.raises(ValueError, match="duplicate Candidate population"):
        validate_replication_tables(universe, eligibility, duplicate_population, (), ())

    population = tuple(
        {"decision_date": "2026-01-01", "symbol": symbol}
        for symbol in ("000001.SZ", "000002.SZ")
    )
    rankings = (
        {"decision_date": "2026-01-01", "symbol": "000001.SZ", "model_id": "prr-mvp-1-b1-e-v1", "rank": 1},
        {"decision_date": "2026-01-01", "symbol": "000002.SZ", "model_id": "prr-mvp-1-b1-e-v1", "rank": 3},
    )
    with pytest.raises(ValueError, match="continuous"):
        validate_replication_tables(universe, eligibility, population, rankings, ())
