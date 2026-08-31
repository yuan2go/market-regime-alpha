from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from market_regime_alpha.research_qualification.domain.partition import ResearchPartitionPlan
from market_regime_alpha.research_qualification.ports.evaluation_uow import EvaluationUnitOfWork
from market_regime_alpha.research_qualification.ports.experiment_uow import ExperimentUnitOfWork
from market_regime_alpha.research_qualification.ports.partition_uow import PartitionUnitOfWork


ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "src/market_regime_alpha/research_qualification"


def test_wp11_remains_inside_existing_research_qualification_authority() -> None:
    package_names = {item.name for item in PACKAGE.iterdir() if item.is_dir()}
    assert "research_validity" not in package_names
    assert {"domain", "application", "ports"} <= package_names


def test_three_uows_have_narrow_non_overlapping_business_ownership() -> None:
    partition_source = (PACKAGE / "ports/partition_uow.py").read_text()
    experiment_source = (PACKAGE / "ports/experiment_uow.py").read_text()
    evaluation_source = (PACKAGE / "ports/evaluation_uow.py").read_text()
    assert "ResearchPartitionRepository" in partition_source
    assert "ExperimentRepository" not in partition_source
    assert "EvaluationRepository" not in partition_source
    assert "ExperimentRepository" in experiment_source
    assert "EvaluationRepository" not in experiment_source
    assert "def create_evaluation" not in experiment_source
    assert "EvaluationRepository" in evaluation_source
    assert "TransactionalOutcomeAcquisition" in evaluation_source
    assert PartitionUnitOfWork is not ExperimentUnitOfWork
    assert ExperimentUnitOfWork is not EvaluationUnitOfWork


def test_partition_command_contract_cannot_accept_selected_member_roster() -> None:
    field_names = {item.name for item in fields(ResearchPartitionPlan)}
    assert not field_names & {"members", "member_ids", "commitment_ids", "roster"}
    partition_application = (PACKAGE / "application/partitions.py").read_text()
    assert "derive_complete_roster" in partition_application
    assert "Outcome" not in partition_application


def test_prospective_uses_runtime_clock_facts_not_a_live_mode_allowlist() -> None:
    query_source = (
        ROOT
        / "src/market_regime_alpha/infrastructure/postgres/queries/research_partition_inputs.py"
    ).read_text()
    assert "runtime_mode NOT IN ('HISTORICAL', 'REPLAY')" in query_source
    assert "requested_at <= decision_time" in query_source
    assert "created_at <= decision_time" in query_source
    assert '"SHADOW"' not in query_source


def test_evaluation_never_imports_market_provider_or_outcome_current_port() -> None:
    source_files = (
        PACKAGE / "application/evaluations.py",
        PACKAGE / "domain/evaluation.py",
        PACKAGE / "ports/evaluation_inputs.py",
        ROOT
        / "src/market_regime_alpha/infrastructure/postgres/queries/research_evaluation_inputs.py",
        ROOT
        / "src/market_regime_alpha/infrastructure/postgres/repositories/research_evaluations.py",
    )
    source = "\n".join(item.read_text() for item in source_files)
    assert "current_for_commitment" not in source
    assert "market_regime_alpha.market" not in source
    assert "market_regime_alpha.provider" not in source
    assert "market_bar_revision" not in source


def test_no_out_of_scope_authority_placeholders_were_added() -> None:
    sql = (
        ROOT
        / "src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql"
    ).read_text()
    wp11_sql = sql.split("-- WP-11:", maxsplit=1)[1]
    for forbidden in (
        "create table mra.evidence_item",
        "create table mra.research_assessment",
        "create table mra.research_qualification",
        "create table mra.model",
        "create table mra.model_version",
        "create table mra.forecast",
        "create table mra.portfolio",
        "create table mra.position",
        "create table mra.execution",
        "create table mra.attribution",
        " jsonb",
    ):
        assert forbidden not in wp11_sql.lower()
