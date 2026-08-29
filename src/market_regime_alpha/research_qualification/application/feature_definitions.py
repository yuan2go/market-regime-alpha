"""FeatureDefinition registration over the narrow Research UoW."""

from __future__ import annotations

from typing import Callable
from uuid import UUID

from market_regime_alpha.research_qualification.application._command_support import (
    finalize_runtime,
    finish_success,
    replay_concurrent_success,
    terminal_failure_boundary,
)
from market_regime_alpha.research_qualification.application._results import (
    ResearchMutationResult,
    replayed_mutation_result,
)
from market_regime_alpha.research_qualification.domain import FeatureDefinition
from market_regime_alpha.research_qualification.ports import (
    ResearchUnitOfWorkProvider,
)
from market_regime_alpha.runtime.application import (
    CommandContext,
    RuntimeCommandFailureRecorder,
)
from market_regime_alpha.runtime.ports import AttemptClaim
from market_regime_alpha.shared.hashing import canonical_json_sha256


class FeatureDefinitionCommands:
    """Own the one immutable FeatureDefinition registration command."""

    def __init__(
        self,
        uow_provider: ResearchUnitOfWorkProvider,
        *,
        id_factory: Callable[[], UUID],
    ) -> None:
        self._uow_provider = uow_provider
        self._id_factory = id_factory
        self._failure_recorder = RuntimeCommandFailureRecorder(
            uow_provider,
            id_factory=id_factory,
        )

    @replay_concurrent_success
    def register(
        self,
        definition: FeatureDefinition,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> ResearchMutationResult:
        request_hash = canonical_json_sha256(definition)
        result_hash = canonical_json_sha256(
            {
                "content_sha256": definition.content_sha256,
                "feature_definition_id": definition.feature_definition_id,
                "version": definition.version,
            }
        )
        with (
            terminal_failure_boundary(
                self._failure_recorder,
                operation="REGISTER_FEATURE_DEFINITION",
                scope_id=definition.feature_code,
                request_hash=request_hash,
                error_class="COMMAND",
                error_code="REGISTER_FEATURE_DEFINITION_REJECTED",
                context=context,
                runtime_claim=runtime_claim,
            ),
            self._uow_provider() as uow,
        ):
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="REGISTER_FEATURE_DEFINITION",
                scope_id=definition.feature_code,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                replay = replayed_mutation_result(receipt)
                finalize_runtime(
                    uow,
                    runtime_claim,
                    receipt_id=receipt.receipt_id,
                    result_hash=replay.result_hash,
                )
                if runtime_claim is not None:
                    uow.commit()
                return replay
            uow.research_artifacts.require_exact(
                definition.code_artifact,
                lock=True,
            )
            uow.research_artifacts.require_exact(
                definition.config_artifact,
                lock=True,
            )
            version = uow.research_definitions.insert_feature_definition(
                definition
            )
            finish_success(
                uow,
                id_factory=self._id_factory,
                receipt_id=receipt.receipt_id,
                aggregate_kind="FEATURE_DEFINITION",
                aggregate_id=str(definition.feature_definition_id),
                aggregate_version=version,
                result_hash=result_hash,
                action="REGISTER_FEATURE_DEFINITION",
                context=context,
                runtime_claim=runtime_claim,
            )
            finalize_runtime(
                uow,
                runtime_claim,
                receipt_id=receipt.receipt_id,
                result_hash=result_hash,
            )
            uow.commit()
            return ResearchMutationResult(
                aggregate_kind="FEATURE_DEFINITION",
                aggregate_id=str(definition.feature_definition_id),
                aggregate_version=version,
                result_hash=result_hash,
                receipt_id=receipt.receipt_id,
                replayed=False,
            )


__all__ = ["FeatureDefinitionCommands"]
