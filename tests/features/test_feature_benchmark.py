from __future__ import annotations

import json

from scripts.benchmark_feature_materialization import main


def test_offline_feature_benchmark_reports_real_measurements(
    tmp_path, capsys
) -> None:
    assert (
        main(
            [
                "--symbols",
                "2",
                "--daily-sessions",
                "65",
                "--minute-bars-per-symbol",
                "2",
                "--max-workers",
                "2",
                "--output-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["symbols"] == 2
    assert payload["market_bar_count"] == 134
    assert payload["feature_family_count"] == 7
    assert payload["feature_artifact_count"] == 14
    assert payload["cold_run_seconds"] >= 0
    assert payload["cached_run_seconds"] >= 0
    assert payload["peak_memory_bytes"] > 0
    assert payload["output_bytes"] > 0
    assert payload["deterministic_cached_receipt"] is True
    assert payload["network_used"] is False
