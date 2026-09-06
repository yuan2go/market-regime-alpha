from __future__ import annotations

from decimal import Decimal
from importlib import import_module
from io import StringIO
import json
from uuid import UUID

import pytest

from market_regime_alpha.interfaces.cli import main
from market_regime_alpha.research_qualification.domain.backtest_report import BacktestMetricDelta


def test_comparison_cli_preserves_exact_decimal_values(monkeypatch):
    value = Decimal("0.1234567890123456789012345678901234")
    # Exercise the public CLI renderer using the actual typed comparison leaf.
    delta = BacktestMetricDelta(
        metric_code="metric", scope_key="arm:fold", left_value=value,
        right_value=value, delta=Decimal("0"), reason_code="MATCHED",
    )
    monkeypatch.setattr(import_module(main.__module__), "_dispatch", lambda *_: {"metric_deltas": (delta,)})
    output, errors = StringIO(), StringIO()
    code = main(["backtest", "compare", "--left-run-id", str(UUID(int=1)),
                 "--right-run-id", str(UUID(int=2))],
                environ={"MRA_DATABASE_URL": "postgresql://localhost/mra_comparison",
                         "MRA_ARTIFACT_ROOT": "/evidence/comparison"},
                stdout=output, stderr=errors)
    assert code == 0, errors.getvalue()
    row = json.loads(output.getvalue())["metric_deltas"][0]
    assert row["left_value"] == row["right_value"] == "0.1234567890123456789012345678901234"
    assert row["delta"] == "0"


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_cli_rejects_nonfinite_decimal_output(value):
    from market_regime_alpha.interfaces.cli.main import _json_value

    with pytest.raises(ValueError, match="finite"):
        _json_value(Decimal(value))
