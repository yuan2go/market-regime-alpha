"""Commands for immutable formal campaign predeclaration and exact bindings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, cast
from uuid import UUID

from market_regime_alpha.research_qualification.application._command_support import (
    replay_concurrent_success,
    retry_transient_transaction,
    terminal_failure_boundary,
)
from market_regime_alpha.research_qualification.application._results import (
    ensure_replay_succeeded,
)
from market_regime_alpha.research_qualification.domain.formal_campaign import (
    FormalResearchCampaignDefinition,
)
from market_regime_alpha.research_qualification.ports.formal_campaign_uow import (
    FormalCampaignBindingRecord,
    FormalCampaignRepository,
    FormalCampaignUnitOfWork,
    FormalCampaignUnitOfWorkProvider,
)
from market_regime_alpha.runtime.application import (
    CommandContext,
    RuntimeCommandFailureRecorder,
)
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.runtime.ports import (
    AttemptClaim,
    CommandFailureUnitOfWorkProvider,
    ReceiptRecord,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


@dataclass(frozen=True, slots=True)
class FormalCampaignMutationResult:
    aggregate_kind: str
    aggregate_id: UUID
    receipt_id: UUID
    result_hash: str
    replayed: bool


class FormalCampaignCommands:
    def __init__(
        self,
        uow_provider: FormalCampaignUnitOfWorkProvider,
        *,
        id_factory: Callable[[], UUID],
    ) -> None:
        self._uow_provider = uow_provider
        self._id_factory = id_factory
        self._failure_recorder = RuntimeCommandFailureRecorder(
            cast(CommandFailureUnitOfWorkProvider, uow_provider),
            id_factory=id_factory,
        )

    @retry_transient_transaction
    @replay_concurrent_success
    def predeclare(
        self,
        definition: FormalResearchCampaignDefinition,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> FormalCampaignMutationResult:
        request_hash = canonical_json_sha256(definition)
        with terminal_failure_boundary(
            self._failure_recorder,
            operation="PREDECLARE_FORMAL_RESEARCH_CAMPAIGN",
            scope_id=definition.campaign_code,
            request_hash=request_hash,
            error_class="COMMAND",
            error_code="FORMAL_CAMPAIGN_PREDECLARATION_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            with self._uow_provider() as uow:
                if runtime_claim is not None:
                    uow.runtime_finalization.lock_live(runtime_claim)
                receipt = uow.receipts.start(
                    receipt_id=self._id_factory(),
                    command_kind="PREDECLARE_FORMAL_RESEARCH_CAMPAIGN",
                    scope_id=definition.campaign_code,
                    idempotency_key=context.idempotency_key,
                    request_hash=request_hash,
                )
                if not receipt.is_new:
                    return self._replay_campaign(uow, receipt, runtime_claim)
                uow.campaigns.lock_identity(definition.campaign_code)
                uow.artifacts.require_exact(definition.code_artifact, lock=True)
                uow.artifacts.require_exact(definition.config_artifact, lock=True)
                for plan in definition.partition_plans:
                    uow.artifacts.require_exact(plan.code_artifact, lock=True)
                    uow.artifacts.require_exact(plan.config_artifact, lock=True)
                record = uow.campaigns.predeclare(
                    definition,
                    request_identity=context.idempotency_key,
                    request_sha256=request_hash,
                )
                if not uow.campaigns.reconcile(record.formal_research_campaign_id):
                    raise ArtifactIntegrityError(
                        "FormalResearchCampaign does not reconcile"
                    )
                result_hash = canonical_json_sha256(record)
                self._finish(
                    uow,
                    receipt.receipt_id,
                    "FORMAL_RESEARCH_CAMPAIGN",
                    record.formal_research_campaign_id,
                    record.revision,
                    result_hash,
                    "PREDECLARE_FORMAL_RESEARCH_CAMPAIGN",
                    context,
                    runtime_claim,
                )
                uow.commit()
                return FormalCampaignMutationResult(
                    "FORMAL_RESEARCH_CAMPAIGN",
                    record.formal_research_campaign_id,
                    receipt.receipt_id,
                    result_hash,
                    False,
                )

    @retry_transient_transaction
    @replay_concurrent_success
    def bind_provider_decision(
        self,
        formal_research_campaign_id: UUID,
        provider_qualification_decision_id: UUID,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> FormalCampaignMutationResult:
        return self._binding_command(
            operation="BIND_FORMAL_CAMPAIGN_PROVIDER_DECISION",
            campaign_id=formal_research_campaign_id,
            request={
                "provider_qualification_decision_id": provider_qualification_decision_id
            },
            binding_kind="PROVIDER_DECISION",
            context=context,
            runtime_claim=runtime_claim,
            mutation=lambda repository: repository.bind_provider_decision(
                formal_research_campaign_id, provider_qualification_decision_id
            ),
        )

    @retry_transient_transaction
    @replay_concurrent_success
    def bind_partition_roster(
        self,
        formal_research_campaign_id: UUID,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> FormalCampaignMutationResult:
        return self._binding_command(
            operation="BIND_FORMAL_CAMPAIGN_PARTITION_ROSTER",
            campaign_id=formal_research_campaign_id,
            request={},
            binding_kind="PARTITION_ROSTER",
            context=context,
            runtime_claim=runtime_claim,
            mutation=lambda repository: repository.bind_partition_roster(
                formal_research_campaign_id
            ),
        )

    @retry_transient_transaction
    @replay_concurrent_success
    def bind_experiment(
        self,
        formal_research_campaign_id: UUID,
        experiment_id: UUID,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> FormalCampaignMutationResult:
        return self._binding_command(
            operation="BIND_FORMAL_CAMPAIGN_EXPERIMENT",
            campaign_id=formal_research_campaign_id,
            request={"experiment_id": experiment_id},
            binding_kind="EXPERIMENT",
            context=context,
            runtime_claim=runtime_claim,
            mutation=lambda repository: repository.bind_experiment(
                formal_research_campaign_id, experiment_id
            ),
        )

    @retry_transient_transaction
    @replay_concurrent_success
    def open_protected(
        self,
        formal_research_campaign_id: UUID,
        *,
        purpose: str,
        experiment_run_id: UUID,
        evaluation_run_id: UUID,
        context: CommandContext,
        runtime_claim: AttemptClaim | None = None,
    ) -> FormalCampaignMutationResult:
        return self._binding_command(
            operation="OPEN_FORMAL_CAMPAIGN_PROTECTED",
            campaign_id=formal_research_campaign_id,
            request={
                "evaluation_run_id": evaluation_run_id,
                "experiment_run_id": experiment_run_id,
                "purpose": purpose,
            },
            binding_kind="PROTECTED_OPEN",
            context=context,
            runtime_claim=runtime_claim,
            mutation=lambda repository: repository.open_protected(
                formal_research_campaign_id,
                purpose=purpose,
                experiment_run_id=experiment_run_id,
                evaluation_run_id=evaluation_run_id,
            ),
        )

    @retry_transient_transaction
    @replay_concurrent_success
    def bind_runtime_run(
        self,
        formal_research_campaign_id: UUID,
        *,
        runtime_profile: str,
        runtime_run_id: UUID,
        context: CommandContext,
        runtime_claim: AttemptClaim | None = None,
    ) -> FormalCampaignMutationResult:
        return self._binding_command(
            operation="BIND_FORMAL_CAMPAIGN_RUNTIME_RUN",
            campaign_id=formal_research_campaign_id,
            request={
                "runtime_profile": runtime_profile,
                "runtime_run_id": runtime_run_id,
            },
            binding_kind="RUNTIME_RUN",
            context=context,
            runtime_claim=runtime_claim,
            mutation=lambda repository: repository.bind_runtime_run(
                formal_research_campaign_id,
                runtime_profile=runtime_profile,
                runtime_run_id=runtime_run_id,
            ),
        )

    def _binding_command(
        self,
        *,
        operation: str,
        campaign_id: UUID,
        request: dict[str, object],
        binding_kind: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
        mutation: Callable[[FormalCampaignRepository], FormalCampaignBindingRecord],
    ) -> FormalCampaignMutationResult:
        request_hash = canonical_json_sha256(
            {"formal_research_campaign_id": campaign_id, **request}
        )
        with terminal_failure_boundary(
            self._failure_recorder,
            operation=operation,
            scope_id=str(campaign_id),
            request_hash=request_hash,
            error_class="COMMAND",
            error_code=f"{operation}_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            with self._uow_provider() as uow:
                if runtime_claim is not None:
                    uow.runtime_finalization.lock_live(runtime_claim)
                receipt = uow.receipts.start(
                    receipt_id=self._id_factory(),
                    command_kind=operation,
                    scope_id=str(campaign_id),
                    idempotency_key=context.idempotency_key,
                    request_hash=request_hash,
                )
                if not receipt.is_new:
                    return self._replay_binding(
                        uow, receipt, campaign_id, binding_kind, runtime_claim
                    )
                record = mutation(uow.campaigns)
                result_hash = record.content_sha256
                self._finish(
                    uow,
                    receipt.receipt_id,
                    binding_kind,
                    record.aggregate_id,
                    record.binding_count,
                    result_hash,
                    operation,
                    context,
                    runtime_claim,
                )
                uow.commit()
                return FormalCampaignMutationResult(
                    binding_kind,
                    record.aggregate_id,
                    receipt.receipt_id,
                    result_hash,
                    False,
                )

    def _replay_campaign(
        self,
        uow: FormalCampaignUnitOfWork,
        receipt: ReceiptRecord,
        runtime_claim: AttemptClaim | None,
    ) -> FormalCampaignMutationResult:
        ensure_replay_succeeded(receipt)
        if receipt.result_aggregate_id is None or receipt.result_hash is None:
            raise ArtifactIntegrityError("Formal campaign receipt is incomplete")
        campaign_id = UUID(receipt.result_aggregate_id)
        record = uow.campaigns.record(campaign_id, lock=False)
        if canonical_json_sha256(record) != receipt.result_hash:
            raise ArtifactIntegrityError("Formal campaign receipt differs from Authority")
        self._finish_replay(uow, receipt, runtime_claim)
        return FormalCampaignMutationResult(
            "FORMAL_RESEARCH_CAMPAIGN",
            campaign_id,
            receipt.receipt_id,
            receipt.result_hash,
            True,
        )

    def _replay_binding(
        self,
        uow: FormalCampaignUnitOfWork,
        receipt: ReceiptRecord,
        campaign_id: UUID,
        binding_kind: str,
        runtime_claim: AttemptClaim | None,
    ) -> FormalCampaignMutationResult:
        ensure_replay_succeeded(receipt)
        if receipt.result_aggregate_id is None or receipt.result_hash is None:
            raise ArtifactIntegrityError("Formal campaign binding receipt is incomplete")
        aggregate_id = UUID(receipt.result_aggregate_id)
        if not uow.campaigns.binding_matches(
            campaign_id,
            binding_kind=binding_kind,
            aggregate_id=aggregate_id,
            content_sha256=receipt.result_hash,
        ):
            raise ArtifactIntegrityError("Formal campaign binding receipt differs")
        self._finish_replay(uow, receipt, runtime_claim)
        return FormalCampaignMutationResult(
            binding_kind,
            aggregate_id,
            receipt.receipt_id,
            receipt.result_hash,
            True,
        )

    def _finish_replay(
        self,
        uow: FormalCampaignUnitOfWork,
        receipt: ReceiptRecord,
        runtime_claim: AttemptClaim | None,
    ) -> None:
        if runtime_claim is not None:
            assert receipt.result_hash is not None
            uow.runtime_finalization.succeed(
                runtime_claim,
                receipt_id=receipt.receipt_id,
                result_hash=receipt.result_hash,
            )
            uow.commit()

    def _finish(
        self,
        uow: FormalCampaignUnitOfWork,
        receipt_id: UUID,
        aggregate_kind: str,
        aggregate_id: UUID,
        aggregate_version: int,
        result_hash: str,
        action: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
    ) -> None:
        uow.receipts.succeed(
            receipt_id=receipt_id,
            aggregate_kind=aggregate_kind,
            aggregate_id=str(aggregate_id),
            aggregate_version=aggregate_version,
            result_hash=result_hash,
            runtime_claim=runtime_claim,
        )
        uow.audit.append(
            audit_event_id=self._id_factory(),
            receipt_id=receipt_id,
            actor_type=context.actor_type.value,
            actor_id=context.actor_id,
            aggregate_kind=aggregate_kind,
            aggregate_id=str(aggregate_id),
            action=action,
            reason_code=context.reason_code,
            before_version=None,
            after_version=aggregate_version,
            runtime_claim=runtime_claim,
        )
        if runtime_claim is not None:
            uow.runtime_finalization.succeed(
                runtime_claim, receipt_id=receipt_id, result_hash=result_hash
            )


__all__ = ["FormalCampaignCommands", "FormalCampaignMutationResult"]
