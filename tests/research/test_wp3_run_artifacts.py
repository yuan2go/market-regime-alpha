from __future__ import annotations

from hashlib import sha256
import json

import pytest

from market_regime_alpha.research.wp3_run_artifacts import (
    WP3FailureArtifactPayload,
    WP3RunArtifactAlreadyExistsError,
    WP3RunArtifactErrorCode,
    WP3RunArtifactPayload,
    write_wp3_candidate_failure,
    write_wp3_candidate_run,
)


SUCCESS_FILES = {
    "manifest.json",
    "provider_selection.json",
    "source_artifacts.json",
    "quality.json",
    "candidate_panel_summary.json",
    "b0_b1_evaluation.json",
    "limitations.json",
    "report.md",
    "SHA256SUMS.json",
}


def _payload(*, empty: bool = False) -> WP3RunArtifactPayload:
    return WP3RunArtifactPayload(
        manifest={
            "run_id": "run-001",
            "code_revision": "abc123",
            "config_hash": "sha256:config",
            "data_eligibility": "REHEARSAL",
        },
        provider_selection={"selected_source": "XUNTOU"},
        source_artifacts=[{"content_hash": "sha256:source"}],
        quality={"status": "ACCEPTED"},
        candidate_panel_summary={"outcome": "EVALUATED"},
        b0_b1_evaluation=(
            {
                "status": "NOT_PRODUCED",
                "reason": "NO_CANDIDATES_AFTER_ELIGIBILITY",
                "targets": [],
            }
            if empty
            else {"status": "PRODUCED", "targets": []}
        ),
        limitations={"items": ["REHEARSAL_ONLY"]},
        report="# WP-3 Candidate Run\n\nNo Alpha claim.\n",
    )


def test_success_writer_is_complete_hashed_and_non_overwriting(tmp_path) -> None:
    output = write_wp3_candidate_run(
        root=tmp_path,
        run_id="run-001",
        payload=_payload(),
    )

    assert {path.name for path in output.iterdir()} == SUCCESS_FILES
    checksums = json.loads((output / "SHA256SUMS.json").read_text())
    assert set(checksums) == SUCCESS_FILES - {"SHA256SUMS.json"}
    for filename, declared in checksums.items():
        content = (output / filename).read_bytes()
        assert declared == f"sha256:{sha256(content).hexdigest()}"
    manifest = json.loads((output / "manifest.json").read_text())
    assert set(manifest["artifacts"]) == SUCCESS_FILES - {
        "manifest.json",
        "SHA256SUMS.json",
    }
    assert manifest["checksum_file"] == "SHA256SUMS.json"

    with pytest.raises(WP3RunArtifactAlreadyExistsError) as exc_info:
        write_wp3_candidate_run(
            root=tmp_path,
            run_id="run-001",
            payload=_payload(),
        )
    assert exc_info.value.code is WP3RunArtifactErrorCode.ALREADY_EXISTS


def test_empty_candidate_run_retains_explicit_no_evaluation_reason(tmp_path) -> None:
    output = write_wp3_candidate_run(
        root=tmp_path,
        run_id="run-001",
        payload=_payload(empty=True),
    )

    evaluation = json.loads((output / "b0_b1_evaluation.json").read_text())
    assert evaluation == {
        "reason": "NO_CANDIDATES_AFTER_ELIGIBILITY",
        "status": "NOT_PRODUCED",
        "targets": [],
    }


def test_failed_serialization_removes_only_owned_staging_directory(tmp_path) -> None:
    payload = _payload()
    invalid = WP3RunArtifactPayload(
        manifest=payload.manifest,
        provider_selection=payload.provider_selection,
        source_artifacts=payload.source_artifacts,
        quality={"not_json": object()},
        candidate_panel_summary=payload.candidate_panel_summary,
        b0_b1_evaluation=payload.b0_b1_evaluation,
        limitations=payload.limitations,
        report=payload.report,
    )

    with pytest.raises(TypeError):
        write_wp3_candidate_run(root=tmp_path, run_id="run-001", payload=invalid)

    assert not (tmp_path / ".run-001.staging").exists()
    assert not (tmp_path / "run-001").exists()


def test_failure_writer_contains_no_candidate_evaluation(tmp_path) -> None:
    output = write_wp3_candidate_failure(
        root=tmp_path,
        run_id="run-failed",
        payload=WP3FailureArtifactPayload(
            manifest={
                "run_id": "run-failed",
                "code_revision": "abc123",
                "config_hash": "sha256:config",
                "data_eligibility": "UNQUALIFIED",
            },
            failure={
                "code": "WP3_XUNTOU_PREFLIGHT_FAILED",
                "message": "bundle invalid",
            },
        ),
    )

    assert {path.name for path in output.iterdir()} == {
        "manifest.json",
        "failure.json",
        "SHA256SUMS.json",
    }
    assert not (output / "b0_b1_evaluation.json").exists()
