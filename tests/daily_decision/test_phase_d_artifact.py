from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from market_regime_alpha.application.daily_loop.commands import (
    DailyRunIdentity,
    RunRequestId,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.daily_quality import (
    DailyDataQualityStatus,
    DataQualityFinding,
)
from market_regime_alpha.daily_decision.artifact import (
    PHASE_D_DAILY_DECISION_FILES,
    DailyDecisionArtifactStatus,
    PhaseDDailyDecisionBundle,
    publish_phase_d_daily_decision_artifact,
)
from market_regime_alpha.daily_decision.entry import assess_entry_plumbing
from market_regime_alpha.daily_decision.reader_registry import (
    load_verified_daily_decision_artifact,
)
from market_regime_alpha.daily_decision.recommendation import (
    project_candidate_recommendations,
)
from tests.daily_decision.conftest import DailyDecisionFixture


def _run_identity(fixture: DailyDecisionFixture) -> DailyRunIdentity:
    return DailyRunIdentity(
        run_request_id=RunRequestId("run-request-phase-d-test"),
        run_request_hash="sha256:" + "3" * 64,
        code_revision="772ecfb09410588b5a406ad900d793a5850e60d5",
        configuration_hash="sha256:" + "4" * 64,
        source_manifest_id=fixture.source_manifest.source_manifest_id,
        source_manifest_content_hash=fixture.source_manifest.content_hash,
        source_content_hashes=tuple(
            sorted(set(fixture.source_manifest.source_hashes))
        ),
    )


def _published_bundle(
    fixture: DailyDecisionFixture,
) -> PhaseDDailyDecisionBundle:
    recommendations = project_candidate_recommendations(
        prediction_runs=fixture.prediction_runs,
        decision_snapshot=fixture.decision_snapshot,
        data_quality_report=fixture.quality_report,
    )
    entries = assess_entry_plumbing(
        recommendations=recommendations,
        prediction_runs=fixture.prediction_runs,
        decision_snapshot=fixture.decision_snapshot,
        source_manifest=fixture.source_manifest,
        data_quality_report=fixture.quality_report,
        eligibility_snapshot=fixture.reconciliation.eligibility_snapshot,
    )
    return PhaseDDailyDecisionBundle(
        status=DailyDecisionArtifactStatus.DECISION_PUBLISHED,
        run_identity=_run_identity(fixture),
        source_archive_id=ArtifactId("source-replay-fixture"),
        source_manifest=fixture.source_manifest,
        data_quality_report=fixture.quality_report,
        universe_snapshot=fixture.reconciliation.universe_snapshot,
        eligibility_snapshot=fixture.reconciliation.eligibility_snapshot,
        decision_price_snapshot=fixture.decision_snapshot,
        feature_definitions=fixture.feature_definitions,
        feature_materializations=fixture.feature_materializations,
        prediction_runs=fixture.prediction_runs,
        recommendations=recommendations,
        entry_assessments=entries,
    )


def test_phase_d_artifact_has_exact_files_and_semantically_replays(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    bundle = _published_bundle(daily_decision_fixture)
    path = publish_phase_d_daily_decision_artifact(root=tmp_path, bundle=bundle)

    assert {item.name for item in path.iterdir()} == set(
        PHASE_D_DAILY_DECISION_FILES
    )
    verified = load_verified_daily_decision_artifact(path)
    replayed = load_verified_daily_decision_artifact(path)

    assert verified.bundle == bundle
    assert verified.artifact_id == str(bundle.artifact_id)
    assert verified.checksums_hash == replayed.checksums_hash
    assert verified.bundle.prediction_runs == bundle.prediction_runs
    assert verified.bundle.recommendations == bundle.recommendations
    assert verified.bundle.entry_assessments == bundle.entry_assessments
    assert "TRADING_AUTHORITY_NOT_GRANTED" in (
        path / "report.md"
    ).read_text(encoding="utf-8")

    with pytest.raises(FileExistsError):
        publish_phase_d_daily_decision_artifact(root=tmp_path, bundle=bundle)


def test_artifact_tamper_is_rejected_before_semantic_use(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    path = publish_phase_d_daily_decision_artifact(
        root=tmp_path,
        bundle=_published_bundle(daily_decision_fixture),
    )
    target = path / "candidate_recommendations.json"
    target.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="checksum mismatch"):
        load_verified_daily_decision_artifact(path)


def test_report_is_reconstructed_even_if_attacker_rewrites_checksum(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    path = publish_phase_d_daily_decision_artifact(
        root=tmp_path,
        bundle=_published_bundle(daily_decision_fixture),
    )
    report = path / "report.md"
    report.write_text("# forged\n", encoding="utf-8")
    checksums_path = path / "SHA256SUMS.json"
    checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    checksums["report.md"] = f"sha256:{sha256(report.read_bytes()).hexdigest()}"
    checksums_path.write_text(
        json.dumps(checksums, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="report is not reconstructible"):
        load_verified_daily_decision_artifact(path)


def test_data_blocked_is_a_verified_artifact_with_empty_downstream_sets(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    fixture = daily_decision_fixture
    blocked_report = replace(
        fixture.quality_report,
        status=DailyDataQualityStatus.DATA_BLOCKED,
        findings=(
            DataQualityFinding(
                symbol=fixture.reconciliation.policy.symbols[0],
                field_id="price",
                critical_fact=None,
                reason_code="PRICE_UNAVAILABLE",
                blocking=True,
            ),
        ),
    )
    bundle = PhaseDDailyDecisionBundle(
        status=DailyDecisionArtifactStatus.DATA_BLOCKED,
        run_identity=_run_identity(fixture),
        source_archive_id=ArtifactId("source-replay-blocked-fixture"),
        source_manifest=fixture.source_manifest,
        data_quality_report=blocked_report,
        universe_snapshot=None,
        eligibility_snapshot=None,
        decision_price_snapshot=fixture.decision_snapshot,
        feature_definitions=(),
        feature_materializations=(),
        prediction_runs=(),
        recommendations=(),
        entry_assessments=(),
    )

    path = publish_phase_d_daily_decision_artifact(root=tmp_path, bundle=bundle)
    verified = load_verified_daily_decision_artifact(path)

    assert verified.bundle.status is DailyDecisionArtifactStatus.DATA_BLOCKED
    assert verified.bundle.prediction_runs == ()
    assert verified.bundle.recommendations == ()
    assert verified.bundle.entry_assessments == ()
    assert "PRICE_UNAVAILABLE" in (path / "report.md").read_text(encoding="utf-8")


def test_versioned_reader_registry_does_not_treat_v1_as_phase_d(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "historical-v1"
    artifact.mkdir()
    (artifact / "manifest.json").write_text(
        json.dumps({"schema_version": "daily-quant-decision-artifact-v1"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported daily decision Artifact schema"):
        load_verified_daily_decision_artifact(artifact)
