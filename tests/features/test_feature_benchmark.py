from __future__ import annotations

import json

from scripts.benchmark_feature_materialization import main
from tests.postgres_path_repositories import postgres_cli_arguments


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
                *postgres_cli_arguments(tmp_path / "benchmark.postgres-scope"),
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


def test_research_scale_v2_only_benchmark_is_measurement_not_absolute_gate(
    tmp_path, capsys
) -> None:
    assert (
        main(
            [
                "--symbols",
                "3",
                "--candidate-count",
                "2",
                "--daily-sessions",
                "65",
                "--minute-bars-per-symbol",
                "2",
                "--columnar-v2-only",
                "--output-dir",
                str(tmp_path),
                *postgres_cli_arguments(tmp_path / "benchmark.postgres-scope"),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "MEASURED"
    assert payload["candidate_count"] == 2
    assert payload["static_symbol_count"] == 3
    assert payload["intraday_symbol_count"] == 2
    assert payload["minute_bars"] == 4
    assert payload["market_bar_count"] == 199
    assert payload["feature_artifact_count"] == 19
    assert payload["absolute_ci_gate_applied"] is False
    assert payload["deterministic_cached_receipt"] is True
