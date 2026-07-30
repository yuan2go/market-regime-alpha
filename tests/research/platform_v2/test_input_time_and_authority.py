from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from market_regime_alpha.core.time import AvailabilityTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.research.platform_v2.inputs import (
    ResearchEvidenceKind,
    ResearchInputBundle,
)

from .conftest import DECISION_AT
from .test_candidate_discovery import _qualified


@pytest.mark.parametrize("input_kind", ("market", "theme", "symbol"))
def test_research_input_rejects_observations_available_after_decision_time(
    research_input_bundle: ResearchInputBundle,
    input_kind: str,
) -> None:
    inputs = _qualified(research_input_bundle)
    late = AvailabilityTime(DECISION_AT + timedelta(seconds=1))

    with pytest.raises(ValueError, match="available by Decision Time"):
        if input_kind == "market":
            replace(
                inputs,
                market_observation=replace(
                    inputs.market_observation, available_at=late
                ),
            )
        elif input_kind == "theme":
            replace(
                inputs,
                theme_observations=(
                    replace(
                        inputs.theme_observations[0], available_at=late
                    ),
                ),
            )
        else:
            replace(
                inputs,
                symbol_observations=(
                    replace(
                        inputs.symbol_observations[0], available_at=late
                    ),
                    *inputs.symbol_observations[1:],
                ),
            )


def test_research_evidence_kind_has_no_live_fixture_alias() -> None:
    assert {item.value for item in ResearchEvidenceKind} == {
        "SYNTHETIC_FIXTURE",
        "HISTORICAL_IMMUTABLE_ARCHIVE",
    }


def test_research_input_cannot_inflate_data_eligibility(
    research_input_bundle: ResearchInputBundle,
) -> None:
    with pytest.raises(ValueError, match="EXPLORATORY"):
        replace(
            research_input_bundle,
            data_eligibility=DataEligibility.FORMAL_RESEARCH,
        )
