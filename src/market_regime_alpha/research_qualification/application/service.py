"""Stable Research Definition Application facade."""

from __future__ import annotations

from typing import Callable
from uuid import UUID, uuid4

from market_regime_alpha.research_qualification.application._results import DatasetRegistrationResult, ResearchMutationResult
from market_regime_alpha.research_qualification.application.datasets import DatasetCommands
from market_regime_alpha.research_qualification.application.feature_definitions import (
    FeatureDefinitionCommands,
)
from market_regime_alpha.research_qualification.application.target_definitions import (
    TargetDefinitionCommands,
    TargetRegistrationResult,
)
from market_regime_alpha.research_qualification.domain import (
    DecisionInputDatasetDefinition,
    FeatureDefinition,
    FormalDatasetScope,
)
from market_regime_alpha.research_qualification.domain.targets import TargetDefinition
from market_regime_alpha.research_qualification.ports import (
    ResearchArtifactByteStore,
    ResearchUnitOfWorkProvider,
)
from market_regime_alpha.research_qualification.ports.target_uow import TargetUnitOfWorkProvider
from market_regime_alpha.runtime.application import CommandContext
from market_regime_alpha.runtime.ports import AttemptClaim


class ResearchQualificationApplication:
    """Expose the commands owned by Research & Qualification definition authority."""

    def __init__(
        self,
        byte_store: ResearchArtifactByteStore,
        uow_provider: ResearchUnitOfWorkProvider,
        target_uow_provider: TargetUnitOfWorkProvider,
        *,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._feature_definitions = FeatureDefinitionCommands(
            uow_provider,
            id_factory=id_factory,
        )
        self._datasets = DatasetCommands(
            byte_store,
            uow_provider,
            id_factory=id_factory,
        )
        self._target_definitions = TargetDefinitionCommands(
            target_uow_provider,
            id_factory=id_factory,
        )

    def register_feature_definition(
        self,
        definition: FeatureDefinition,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> ResearchMutationResult:
        return self._feature_definitions.register(
            definition,
            context,
            runtime_claim=runtime_claim,
        )

    def register_dataset(
        self,
        definition: DecisionInputDatasetDefinition,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> DatasetRegistrationResult:
        return self._datasets.register(
            definition,
            context,
            runtime_claim=runtime_claim,
        )

    def register_formal_dataset(
        self,
        definition: DecisionInputDatasetDefinition,
        formal_scope: FormalDatasetScope,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> DatasetRegistrationResult:
        return self._datasets.register(
            definition,
            context,
            formal_scope=formal_scope,
            runtime_claim=runtime_claim,
        )

    def register_target_definition(
        self,
        definition: TargetDefinition,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> TargetRegistrationResult:
        return self._target_definitions.register(
            definition,
            context,
            runtime_claim=runtime_claim,
        )


__all__ = ["DatasetRegistrationResult", "ResearchMutationResult", "ResearchQualificationApplication", "TargetRegistrationResult"]
