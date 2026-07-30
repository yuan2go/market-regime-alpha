from __future__ import annotations

import json
from pathlib import Path

from market_regime_alpha.research.platform_v2.inputs import ResearchInputBundle
from scripts.run_research_layer import main

from .test_candidate_discovery import _qualified


def test_research_layer_cli_run_replay_and_report(
    research_input_bundle: ResearchInputBundle,
    tmp_path: Path,
    capsys,
) -> None:
    inputs = _qualified(research_input_bundle)
    input_path = tmp_path / "input.json"
    input_path.write_text(
        json.dumps(inputs.to_canonical_dict(), sort_keys=True),
        encoding="utf-8",
    )
    output = tmp_path / "artifacts"
    assert (
        main(
            (
                "run-research-v2",
                "--input-bundle",
                str(input_path),
                "--output-root",
                str(output),
                "--code-revision",
                "cli-test-revision",
            )
        )
        == 0
    )
    run_payload = json.loads(capsys.readouterr().out)
    artifact = output / run_payload["artifact_id"]
    assert run_payload["selected_candidate_count"] == 5
    assert run_payload["data_eligibility"] == "EXPLORATORY"

    assert main(("replay-research-v2", "--artifact", str(artifact))) == 0
    replay_payload = json.loads(capsys.readouterr().out)
    assert replay_payload["artifact_id"] == run_payload["artifact_id"]
    assert replay_payload["content_hash"] == run_payload["content_hash"]

    assert main(("report-research-v2", "--artifact", str(artifact))) == 0
    report = capsys.readouterr().out
    assert "# Platform V2 Research Layer Report" in report
    assert (
        "CandidateSet is research opportunity discovery, not a buy list."
        in report
    )
