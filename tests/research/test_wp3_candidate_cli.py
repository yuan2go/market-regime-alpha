from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.data import DataEligibility
from market_regime_alpha.research.provider_routing import CandidateRunSourceMode


def _cli_module():
    from scripts import run_wp3_candidate_research

    return run_wp3_candidate_research


def test_parser_defaults_to_auto_exploratory() -> None:
    module = _cli_module()

    args = module.build_parser().parse_args([])

    assert args.source == "auto"
    assert args.minimum_eligibility == "exploratory"
    assert args.decision_count == 60
    assert not hasattr(args, "snapshot_output")


def test_explicit_xuntou_requires_bundle() -> None:
    module = _cli_module()

    with pytest.raises(SystemExit):
        module.main(["--source", "xuntou"])


def test_supplied_xuntou_bundle_requires_explicit_liquidity_threshold(
    tmp_path,
) -> None:
    module = _cli_module()
    bundle = tmp_path / "bundle.json"
    bundle.write_text("{}", encoding="utf-8")

    with pytest.raises(SystemExit):
        module.main(["--source", "xuntou", "--xuntou-bundle", str(bundle)])


def test_main_injects_orchestration_without_network_or_snapshot_side_effects(
    tmp_path,
) -> None:
    module = _cli_module()
    captured = {}

    class FakeTencentBackend:
        pass

    def backend_factory(args, retrieved_at):
        captured["backend_args"] = args
        captured["retrieved_at"] = retrieved_at
        return FakeTencentBackend()

    def orchestrator(request, *, tencent_backend):
        captured["request"] = request
        captured["backend"] = tencent_backend
        output = request.output_root / request.run_id
        output.mkdir(parents=True)
        return output

    exit_code = module.main(
        [
            "--source",
            "auto",
            "--output-root",
            str(tmp_path),
            "--retrieved-at",
            "2026-07-16T18:00:00+08:00",
        ],
        orchestrator=orchestrator,
        tencent_backend_factory=backend_factory,
    )

    request = captured["request"]
    assert exit_code == 0
    assert request.source_mode is CandidateRunSourceMode.AUTO
    assert request.minimum_eligibility is DataEligibility.EXPLORATORY
    assert request.output_root == tmp_path
    assert captured["retrieved_at"] == datetime(
        2026, 7, 16, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")
    )


def test_failure_artifact_returns_nonzero_exit_code(tmp_path) -> None:
    module = _cli_module()

    def orchestrator(request, *, tencent_backend):
        output = request.output_root / request.run_id
        output.mkdir(parents=True)
        (output / "failure.json").write_text("{}\n", encoding="utf-8")
        return output

    exit_code = module.main(
        [
            "--output-root",
            str(tmp_path),
            "--retrieved-at",
            "2026-07-16T18:00:00+08:00",
        ],
        orchestrator=orchestrator,
        tencent_backend_factory=lambda args, retrieved_at: object(),
    )

    assert exit_code == 2


def test_config_hash_changes_with_result_affecting_source_mode(tmp_path) -> None:
    module = _cli_module()
    parser = module.build_parser()
    common = [
        "--output-root",
        str(tmp_path),
        "--retrieved-at",
        "2026-07-16T18:00:00+08:00",
    ]
    auto = parser.parse_args([*common, "--source", "auto"])
    tencent = parser.parse_args([*common, "--source", "tencent"])

    auto_hash = module.config_hash(auto)
    tencent_hash = module.config_hash(tencent)

    assert auto_hash.startswith("sha256:")
    assert auto_hash != tencent_hash
