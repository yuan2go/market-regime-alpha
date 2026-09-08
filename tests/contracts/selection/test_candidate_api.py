from __future__ import annotations

from dataclasses import fields

from market_regime_alpha.selection.ports.candidate_artifacts import (
    CandidateArtifactByteStore,
    CandidateArtifactRepository,
)
from market_regime_alpha.selection.ports.candidate_queries import (
    CandidateQueryProvider,
)
from market_regime_alpha.selection.ports.candidate_repository import (
    CandidatePersistenceReconciliation,
    CandidateRepository,
)
from market_regime_alpha.selection.ports.candidate_uow import (
    CandidateUnitOfWork,
    CandidateUnitOfWorkProvider,
)
from market_regime_alpha.selection.ports.research_inputs import (
    CandidateDatasetDependency,
    CandidateFeatureDependency,
    CandidatePopulationDependency,
    CandidatePreparedResearchInput,
    CandidateResearchDependencyQueries,
    CandidateResearchInputLoader,
)


def test_candidate_ports_are_narrow_and_selection_owned() -> None:
    assert CandidateRepository.__module__.startswith("market_regime_alpha.selection")
    assert CandidatePersistenceReconciliation.__module__.startswith(
        "market_regime_alpha.selection"
    )
    assert CandidateUnitOfWork.__module__.startswith("market_regime_alpha.selection")
    assert CandidateResearchInputLoader.__module__.startswith(
        "market_regime_alpha.selection"
    )
    assert CandidateResearchDependencyQueries.__module__.startswith(
        "market_regime_alpha.selection"
    )
    assert CandidateArtifactByteStore.__module__.startswith(
        "market_regime_alpha.selection"
    )
    assert CandidateArtifactRepository.__module__.startswith(
        "market_regime_alpha.selection"
    )
    assert CandidateQueryProvider.__module__.startswith("market_regime_alpha.selection")
    assert CandidateUnitOfWorkProvider.__module__.startswith(
        "market_regime_alpha.selection"
    )


def test_research_input_dtos_expose_only_candidate_dependencies() -> None:
    dto_types = (
        CandidateDatasetDependency,
        CandidateFeatureDependency,
        CandidatePopulationDependency,
        CandidatePreparedResearchInput,
    )
    field_names = {field.name for dto_type in dto_types for field in fields(dto_type)}
    forbidden = {
        "model_id",
        "model_version_id",
        "target_id",
        "outcome_id",
        "evidence_id",
        "qualification_id",
        "context_id",
        "decision_run_id",
        "dataset_source_ids",
        "source_ids",
    }
    assert field_names.isdisjoint(forbidden)
    assert {
        "dataset_id",
        "feature_definition_id",
        "population_dataset_source_id",
        "dependency_sha256",
    } <= field_names


def test_candidate_uow_is_not_a_research_or_selection_core_mega_uow() -> None:
    surface = set(dir(CandidateUnitOfWork))
    assert {
        "candidates",
        "research_dependencies",
        "candidate_artifacts",
        "receipts",
        "audit",
        "runtime_finalization",
    } <= surface
    assert "selection" not in surface
    assert "market_queries" not in surface
    assert "research_definitions" not in surface
    assert "source_queries" not in surface
