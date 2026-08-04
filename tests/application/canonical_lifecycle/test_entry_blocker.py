from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from market_regime_alpha.application.canonical_lifecycle.input_manifest import (
    LifecycleAuthorityCeiling,
)
from market_regime_alpha.application.canonical_lifecycle.stages.signal_forecast import (
    EntryAssessmentStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LifecycleRunStatus,
    LifecycleStageName,
    LifecycleStageStatus,
)
from tests.application.canonical_lifecycle.test_research_stages import (
    _context,
    _execute_through_forecast,
)


def test_entry_blocks_on_actual_validation_ceiling_and_insufficient_inputs(
    tmp_path: Path,
) -> None:
    fixture, results = _execute_through_forecast(tmp_path, ranked_percentiles=True)
    handler = EntryAssessmentStageHandler(authority_ceiling=LifecycleAuthorityCeiling())

    result = handler.execute(_context(fixture, LifecycleStageName.ENTRY_ASSESSMENT, results))

    assert result.stage_status is LifecycleStageStatus.BLOCKED
    assert result.run_status is LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION
    assert result.output_references == ()
    assert "ENTRY_MODEL_EMPIRICALLY_VALIDATED_FALSE" in result.reason_codes
    assert "SIGNAL_DATA_INSUFFICIENT" in result.reason_codes
    assert "PATH_FORECAST_DATA_INSUFFICIENT" in result.reason_codes
    assert "PATH_FORECAST_NOT_CALIBRATED" in result.reason_codes
    assert result.blocker_reason is not None


def test_entry_recovery_is_read_only_and_stable(tmp_path: Path) -> None:
    fixture, results = _execute_through_forecast(tmp_path)
    handler = EntryAssessmentStageHandler(authority_ceiling=LifecycleAuthorityCeiling())
    context = _context(fixture, LifecycleStageName.ENTRY_ASSESSMENT, results)

    assert handler.recover(context) == handler.execute(context)


def test_entry_rejects_incomplete_signal_forecast_lineage(tmp_path: Path) -> None:
    fixture, results = _execute_through_forecast(tmp_path, ranked_percentiles=True)
    assert len(results[3].output_references) >= 2
    incomplete_forecasts = replace(results[3], output_references=results[3].output_references[:-1])
    handler = EntryAssessmentStageHandler(authority_ceiling=LifecycleAuthorityCeiling())

    with pytest.raises(ValueError, match="one PathForecast per Signal snapshot"):
        handler.execute(
            _context(
                fixture,
                LifecycleStageName.ENTRY_ASSESSMENT,
                (*results[:3], incomplete_forecasts),
            )
        )
