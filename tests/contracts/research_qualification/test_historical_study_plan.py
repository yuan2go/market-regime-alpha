from dataclasses import replace
from datetime import date
from uuid import UUID

import pytest

from market_regime_alpha.research_qualification.domain.historical_study import HistoricalStudyPlan


def plan():
    return HistoricalStudyPlan("small_real_baseline", UUID(int=1), "a" * 64, UUID(int=2), "b" * 64, UUID(int=3), "c" * 64,
        (date(2026, 1, 6),), (date(2026, 1, 7),), (date(2026, 1, 8),), (date(2026, 1, 9),), (UUID(int=4),))


@pytest.mark.parametrize("changes", [
    {"seed": True}, {"purge_dates": ()}, {"embargo_dates": ()}, {"validation_dates": ()},
    {"validation_dates": (date(2026, 1, 6),)}, {"candidates": ("ridge_v2", "ridge_v2")},
    {"instrument_ids": (UUID(int=5), UUID(int=4))}, {"universe_limitation": "PIT"},
])
def test_study_rejects_ambiguous_time_rosters_budget_and_authority(changes):
    with pytest.raises(ValueError):
        replace(plan(), **changes)


def test_study_parser_rejects_duplicate_fields_before_constructing_owner_commands():
    with pytest.raises(ValueError, match="duplicate study field"):
        HistoricalStudyPlan.from_bytes(b'{"schema":"mra-historical-study-v1","schema":"mra-historical-study-v1"}')


def test_study_rejects_wrapped_or_text_identities_before_sql_adaptation():
    from market_regime_alpha.shared.identity import InstrumentId
    with pytest.raises(TypeError,match="UUID values"):
        replace(plan(),instrument_ids=(InstrumentId(UUID(int=4)),))
