from __future__ import annotations

import json

import pytest

from market_regime_alpha.cli.prepare_controlled_operation import main as prepare_main
from market_regime_alpha.cli.replay_controlled_operation import main as replay_main
from market_regime_alpha.cli.report_controlled_operation import main as report_main
from market_regime_alpha.cli.resume_controlled_operation import main as resume_main
from market_regime_alpha.cli.run_decision_window import main as run_main
from market_regime_alpha.cli.settle_controlled_operation import main as settle_main


@pytest.mark.parametrize(
    "entrypoint",
    (prepare_main, run_main, resume_main, settle_main, replay_main, report_main),
)
def test_controlled_cli_argument_errors_are_structured_and_fail_closed(entrypoint, capsys: pytest.CaptureFixture[str]) -> None:
    assert entrypoint([]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "FAILED"
    assert payload["NO_ORDER_CREATED"] is True
    assert payload["BROKER_NOT_INVOKED"] is True
    assert payload["NO_FILL_CREATED"] is True
    assert payload["ENTRY_MODEL_EMPIRICALLY_VALIDATED_FALSE"] is True
    assert payload["FORMAL_OOS_ALPHA_NOT_ESTABLISHED"] is True
