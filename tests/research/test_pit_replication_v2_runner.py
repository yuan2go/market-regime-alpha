from dataclasses import replace
import json
from pathlib import Path

from market_regime_alpha.research.pit_replication_success_v2_runner import (
    run_pit_replication_success_v2,
)
from tests.research.pit_replication_v2_fixtures import build_test_success_inputs


def test_available_test_input_executes_success_path_without_placeholder(tmp_path: Path) -> None:
    final = run_pit_replication_success_v2(
        xuntou_bundle=None,
        output_root=tmp_path,
        success_inputs=build_test_success_inputs(),
    )
    manifest = json.loads((final / "manifest.json").read_text(encoding="utf-8"))
    assert final.name.startswith("test-only-pit-replication-v2-")
    assert manifest["data_eligibility"] == "TEST_ONLY_NOT_RESEARCH_EVIDENCE"
    assert manifest["authority"] == "TEST_ONLY_NOT_RESEARCH_EVIDENCE"


def test_unknown_orderability_never_enters_population(tmp_path: Path) -> None:
    inputs = build_test_success_inputs()
    unknown = {**inputs.orderability_rows[0], "orderability_status": "UNKNOWN"}
    broken = replace(inputs, orderability_rows=(unknown, *inputs.orderability_rows[1:]))
    try:
        run_pit_replication_success_v2(
            xuntou_bundle=None, output_root=tmp_path, success_inputs=broken
        )
    except ValueError as exc:
        assert "RESEARCH_ORDERABLE" in str(exc)
    else:
        raise AssertionError("UNKNOWN orderability entered the Candidate population")


def test_missing_real_bundle_publishes_v4_bound_blocker(tmp_path: Path) -> None:
    final = run_pit_replication_success_v2(
        xuntou_bundle=None, output_root=tmp_path
    )
    blocker = json.loads((final / "blocker.json").read_text(encoding="utf-8"))
    assert blocker["required_bundle_schema"] == "xuntou-pit-validation-bundle-v4"
    assert blocker["tencent_fallback_used"] is False
