from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "market_regime_alpha"


def test_wp12_is_composed_in_sole_target_root_with_three_narrow_uows() -> None:
    bootstrap = (SRC / "bootstrap.py").read_text()
    assert "research_evidence: EvidenceCommands" in bootstrap
    assert "research_assessments: AssessmentCommands" in bootstrap
    assert "research_qualifications: QualificationCommands" in bootstrap
    assert "PostgresEvidenceUnitOfWorkProvider" in bootstrap
    assert "PostgresAssessmentUnitOfWorkProvider" in bootstrap
    assert "PostgresQualificationUnitOfWorkProvider" in bootstrap
    assert "research_qualification_admissions" in bootstrap

    uows = {
        name: (SRC / "research_qualification" / "ports" / name).read_text()
        for name in (
            "evidence_uow.py",
            "assessment_uow.py",
            "qualification_uow.py",
        )
    }
    assert "ResearchAssessment" not in uows["evidence_uow.py"]
    assert "EvidenceRepository" not in uows["assessment_uow.py"]
    assert "AssessmentRepository" not in uows["qualification_uow.py"]


def test_wp12_has_no_runtime_dispatch_cli_cutover_or_later_authority() -> None:
    runtime = "\n".join(
        path.read_text()
        for path in (SRC / "runtime").rglob("*.py")
    ).lower()
    cli = "\n".join(
        path.read_text()
        for path in (SRC / "interfaces" / "cli").rglob("*.py")
    ).lower()
    for command in (
        "record_research_evidence",
        "assess_research_experiment",
        "decide_research_qualification",
    ):
        assert command not in runtime
        assert command not in cli

    baseline = (
        SRC / "infrastructure" / "postgres" / "migrations" / "001_baseline.sql"
    ).read_text()
    for table in (
        "calibration",
        "trade_outcome",
    ):
        assert f"CREATE TABLE mra.{table} (" not in baseline


def test_qualification_read_port_is_exact_id_and_generation_safe() -> None:
    port = (
        SRC
        / "infrastructure"
        / "postgres"
        / "queries"
        / "research_qualification.py"
    ).read_text()
    assert "research_qualification_decision_id = %s" in port
    assert "requested_knowledge_cutoff" in port
    assert "consumer_generation_time" in port
    assert "source_generation_max_decision_time < %s" in port
    assert "ORDER BY" not in port
    assert "current" not in port.lower()
    assert "latest" not in port.lower()
