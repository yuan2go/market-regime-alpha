from __future__ import annotations

import pytest

from market_regime_alpha.application.research_validation.formal_execution import (
    FormalExecutionAssessment,
    FormalExecutionStage,
    FormalExecutionStageAssessment,
    FormalExecutionStatus,
)
from tests.application.research_validation.test_formal_execution import NOW, _ref


def test_calibration_flag_cannot_exist_before_formal_oos() -> None:
    with pytest.raises(ValueError, match="Calibration cannot precede Formal OOS"):
        FormalExecutionAssessment.create(
            request_reference=_ref("FORMAL_EXECUTION_REQUEST", "a"),
            status=FormalExecutionStatus.SATISFIED,
            terminal_stage=FormalExecutionStage.COMPLETE,
            stages=(
                FormalExecutionStageAssessment(
                    FormalExecutionStage.COMPLETE,
                    FormalExecutionStatus.SATISFIED,
                    (),
                    (),
                ),
            ),
            source_references=(),
            formal_model_qualified=True,
            formal_oos_alpha_established=False,
            calibrated=True,
            production_authorized=False,
            assessed_at=NOW,
            reason_codes=(),
        )
