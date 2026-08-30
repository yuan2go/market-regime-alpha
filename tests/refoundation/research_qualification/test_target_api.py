from __future__ import annotations

from inspect import signature
from pathlib import Path

from market_regime_alpha.research_qualification.application.service import (
    ResearchQualificationApplication,
)
from market_regime_alpha.research_qualification.application.target_definitions import (
    TargetDefinitionCommands,
    TargetRegistrationResult,
)
from market_regime_alpha.research_qualification.ports.target_artifacts import (
    TargetArtifactRepository,
)
from market_regime_alpha.research_qualification.ports.target_repository import (
    TargetDefinitionRecord,
    TargetDefinitionRepository,
    TargetRegistrationReconciliation,
)
from market_regime_alpha.research_qualification.ports.target_uow import (
    TargetUnitOfWork,
    TargetUnitOfWorkProvider,
)


PACKAGE = Path(__file__).resolve().parents[3] / "src" / "market_regime_alpha"


def test_target_registration_has_an_independent_public_command_and_uow_seam() -> None:
    assert TargetDefinitionCommands.__module__.startswith(
        "market_regime_alpha.research_qualification"
    )
    assert TargetRegistrationResult.__module__.startswith(
        "market_regime_alpha.research_qualification"
    )
    assert TargetDefinitionRepository.__module__.startswith(
        "market_regime_alpha.research_qualification"
    )
    assert TargetDefinitionRecord.__module__.startswith(
        "market_regime_alpha.research_qualification"
    )
    assert TargetRegistrationReconciliation.__module__.startswith(
        "market_regime_alpha.research_qualification"
    )
    assert TargetArtifactRepository.__module__.startswith(
        "market_regime_alpha.research_qualification"
    )
    assert TargetUnitOfWork.__module__.startswith(
        "market_regime_alpha.research_qualification"
    )
    assert TargetUnitOfWorkProvider.__module__.startswith(
        "market_regime_alpha.research_qualification"
    )

    surface = set(dir(TargetUnitOfWork))
    assert {
        "target_definitions",
        "target_artifacts",
        "receipts",
        "audit",
        "runtime_finalization",
    } <= surface
    assert "research_definitions" not in surface
    assert "source_queries" not in surface
    assert "candidates" not in surface
    assert "market_queries" not in surface


def test_research_facade_exposes_target_registration_without_owning_transaction() -> None:
    method = signature(ResearchQualificationApplication.register_target_definition)
    assert tuple(method.parameters) == (
        "self",
        "definition",
        "context",
        "runtime_claim",
    )
    source = (
        PACKAGE / "research_qualification/application/service.py"
    ).read_text(encoding="utf-8")
    assert "with self._target_uow_provider()" not in source
    assert len(source.splitlines()) <= 130


def test_target_postgres_uow_is_separate_from_research_definition_uow() -> None:
    target_uow = (
        PACKAGE / "infrastructure/postgres/target_uow.py"
    ).read_text(encoding="utf-8")
    research_uow = (
        PACKAGE / "infrastructure/postgres/research_uow.py"
    ).read_text(encoding="utf-8")
    bootstrap = (PACKAGE / "bootstrap.py").read_text(encoding="utf-8")
    assert "def target_definitions(" in target_uow
    assert "def research_definitions(" not in target_uow
    assert "def target_definitions(" not in research_uow
    assert "PostgresTargetUnitOfWorkProvider(pool)" in bootstrap
