from __future__ import annotations

import subprocess
import sys


def test_canonical_lifecycle_can_import_before_controlled_runner() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from market_regime_alpha.application.canonical_lifecycle.stages."
                "signal_forecast import EntryAssessmentStageHandler; "
                "from market_regime_alpha.application.controlled_operation import "
                "ControlledDecisionTimeOperationRunner"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
