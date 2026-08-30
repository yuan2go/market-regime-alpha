"""Candidate Policy registration and deterministic CandidateSet assembly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from uuid import UUID, uuid4

from market_regime_alpha.runtime.application import (
    CommandContext,
    CommandFailureDescriptor,
    RuntimeCommandFailureRecorder,
)
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    CommandInProgressError,
    CommandPreviouslyFailedError,
    IdempotencyKeyReusedError,
    RuntimeNotFoundError,
    RuntimeStateConflictError,
)
from market_regime_alpha.runtime.ports import AttemptClaim, ReceiptRecord
from market_regime_alpha.selection.application._candidate_command_support import (
    candidate_failure_boundary,
    replay_concurrent_success,
)
from market_regime_alpha.selection.domain.candidate_inputs import (
    CandidateCellStatus,
    CandidateDatasetPopulation,
)
from market_regime_alpha.selection.domain.candidate_policy import CandidatePolicy
from market_regime_alpha.selection.domain.candidate_ranking import (
    build_candidate_set as rank_candidate_set,
)
from market_regime_alpha.selection.domain.candidate_results import (
    CandidateDisposition,
    CandidateRankingPlan,
    CandidateRankingStatus,
    CandidateScoreComponentRecord,
    candidate_result_content_sha256,
)
from market_regime_alpha.selection.ports.candidate_repository import (
    CandidatePersistenceReconciliation,
    CandidateSetBinding,
)
from market_regime_alpha.selection.ports.candidate_uow import (
    CandidateUnitOfWork,
    CandidateUnitOfWorkProvider,
)
from market_regime_alpha.selection.ports.research_inputs import (
    CandidateFeatureDependency,
    CandidatePreparedResearchInput,
    CandidateResearchDependencySnapshot,
    CandidateResearchInputLoader,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


@dataclass(frozen=True, slots=True)
class CandidateMutationResult:
    aggregate_kind: str
    aggregate_id: str
    aggregate_version: int
    result_hash: str
    receipt_id: UUID
    replayed: bool


@dataclass(frozen=True, slots=True)
class _CandidateReplayProbe:
    receipt: ReceiptRecord
    policy: CandidatePolicy
    snapshot: CandidateResearchDependencySnapshot
    binding: CandidateSetBinding | None


class CandidateApplication:
    """Independent Selection application boundary for Candidate Authority."""

    def __init__(
        self,
        research_input_loader: CandidateResearchInputLoader,
        uow_provider: CandidateUnitOfWorkProvider,
        *,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._research_input_loader = research_input_loader
        self._uow_provider = uow_provider
        self._id_factory = id_factory
        self._failure_recorder = RuntimeCommandFailureRecorder(
            uow_provider,
            id_factory=id_factory,
        )

    @replay_concurrent_success
    def register_candidate_policy(
        self,
        policy: CandidatePolicy,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> CandidateMutationResult:
        """Register one immutable policy without binding it to a Dataset."""

        request_hash = canonical_json_sha256(policy)
        operation = "REGISTER_CANDIDATE_POLICY"
        scope_id = str(policy.candidate_policy_id)
        with (
            candidate_failure_boundary(
                self._failure_recorder,
                operation=operation,
                scope_id=scope_id,
                request_hash=request_hash,
                context=context,
                runtime_claim=runtime_claim,
            ),
            self._uow_provider() as uow,
        ):
            _lock_live(uow, runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind=operation,
                scope_id=scope_id,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                result = self._replayed_policy_result(uow, receipt, policy)
                _finalize_runtime(
                    uow,
                    runtime_claim,
                    receipt_id=receipt.receipt_id,
                    result_hash=result.result_hash,
                )
                if runtime_claim is not None:
                    uow.commit()
                return result

            uow.candidate_artifacts.require_exact(policy.code_artifact, lock=True)
            uow.candidate_artifacts.require_exact(policy.config_artifact, lock=True)
            required_features = _policy_feature_dependencies(policy)
            actual_features = uow.research_dependencies.feature_dependencies(
                required_features,
                lock=True,
            )
            if actual_features != required_features:
                raise RuntimeStateConflictError(
                    "CandidatePolicy FeatureDefinition dependencies changed"
                )
            uow.candidates.insert_policy(policy)
            persisted = uow.candidates.policy(
                policy.candidate_policy_id,
                lock=False,
            )
            if persisted != policy:
                raise ArtifactIntegrityError(
                    "persisted CandidatePolicy does not reconcile"
                )
            result_hash = _policy_result_hash(policy)
            _finish_success(
                uow,
                id_factory=self._id_factory,
                receipt_id=receipt.receipt_id,
                aggregate_kind="CANDIDATE_POLICY",
                aggregate_id=str(policy.candidate_policy_id),
                aggregate_version=policy.version,
                result_hash=result_hash,
                action=operation,
                context=context,
                runtime_claim=runtime_claim,
            )
            _finalize_runtime(
                uow,
                runtime_claim,
                receipt_id=receipt.receipt_id,
                result_hash=result_hash,
            )
            uow.commit()
            return CandidateMutationResult(
                aggregate_kind="CANDIDATE_POLICY",
                aggregate_id=str(policy.candidate_policy_id),
                aggregate_version=policy.version,
                result_hash=result_hash,
                receipt_id=receipt.receipt_id,
                replayed=False,
            )

    @replay_concurrent_success
    def build_candidate_set(
        self,
        candidate_policy_id: UUID,
        dataset_id: UUID,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim,
    ) -> CandidateMutationResult:
        """Prepare and rank outside PostgreSQL, then bind in one short UoW."""

        if runtime_claim is None:
            raise TypeError("BUILD_CANDIDATE_SET requires a runtime_claim")

        identity_request_hash = canonical_json_sha256(
            {
                "candidate_policy_id": candidate_policy_id,
                "dataset_id": dataset_id,
            }
        )
        operation = "BUILD_CANDIDATE_SET"
        scope_id = f"{candidate_policy_id}:{dataset_id}"
        request_hash_holder = {"value": identity_request_hash}
        replay_probe: _CandidateReplayProbe | None = None
        with candidate_failure_boundary(
            self._failure_recorder,
            operation=operation,
            scope_id=scope_id,
            request_hash=lambda: request_hash_holder["value"],
            context=context,
            runtime_claim=runtime_claim,
        ):
            replay_probe, policy, preflight_snapshot, request_hash = (
                self._preflight_build(
                    candidate_policy_id=candidate_policy_id,
                    dataset_id=dataset_id,
                    context=context,
                    request_hash_holder=request_hash_holder,
                    runtime_claim=runtime_claim,
                )
            )
            request_hash_holder["value"] = request_hash
            if replay_probe is None:
                assert policy is not None
                assert preflight_snapshot is not None
                required_features = _policy_feature_dependencies(policy)
                prepared = self._research_input_loader.prepare(
                    dataset_id=dataset_id,
                    required_features=required_features,
                )
                if _prepared_snapshot(prepared) != preflight_snapshot:
                    raise RuntimeStateConflictError(
                        "Dataset dependencies changed during Candidate input "
                        "preparation"
                    )
                _validate_prepared_input(
                    prepared,
                    dataset_id=dataset_id,
                    required_features=required_features,
                )
                population = CandidateDatasetPopulation(
                    dataset_id=dataset_id,
                    dataset_content_sha256=prepared.dataset.content_sha256,
                    decision_time=prepared.dataset.decision_time,
                    universe_revision_id=prepared.dataset.universe_revision_id,
                    eligibility_policy_id=prepared.dataset.eligibility_policy_id,
                    rows=prepared.rows,
                    dependency_sha256=prepared.dependency_sha256,
                )
                plan = rank_candidate_set(policy=policy, dataset=population)
                return self._bind_candidate_set(
                    policy=policy,
                    prepared=prepared,
                    preflight_snapshot=preflight_snapshot,
                    plan=plan,
                    context=context,
                    request_hash=request_hash,
                    runtime_claim=runtime_claim,
                )
        assert replay_probe is not None
        return self._complete_candidate_replay(
            replay_probe,
            candidate_policy_id=candidate_policy_id,
            dataset_id=dataset_id,
            context=context,
            request_hash=request_hash_holder["value"],
            runtime_claim=runtime_claim,
        )

    def _preflight_build(
        self,
        *,
        candidate_policy_id: UUID,
        dataset_id: UUID,
        context: CommandContext,
        request_hash_holder: dict[str, str],
        runtime_claim: AttemptClaim,
    ) -> tuple[
        _CandidateReplayProbe | None,
        CandidatePolicy | None,
        CandidateResearchDependencySnapshot | None,
        str,
    ]:
        with self._uow_provider() as uow:
            _lock_live(uow, runtime_claim)
            policy = uow.candidates.policy(candidate_policy_id, lock=False)
            required_features = _policy_feature_dependencies(policy)
            snapshot = uow.research_dependencies.snapshot(
                dataset_id=dataset_id,
                required_features=required_features,
                lock=False,
            )
            request_hash = _build_request_hash(
                policy=policy,
                snapshot=snapshot,
            )
            request_hash_holder["value"] = request_hash
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="BUILD_CANDIDATE_SET",
                scope_id=f"{candidate_policy_id}:{dataset_id}",
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                binding = uow.candidates.candidate_set_binding(
                    candidate_policy_id=candidate_policy_id,
                    dataset_id=dataset_id,
                    lock=False,
                )
                return (
                    _CandidateReplayProbe(
                        receipt=receipt,
                        policy=policy,
                        snapshot=snapshot,
                        binding=binding,
                    ),
                    None,
                    None,
                    request_hash,
                )
            return None, policy, snapshot, request_hash

    def _complete_candidate_replay(
        self,
        replay: _CandidateReplayProbe,
        *,
        candidate_policy_id: UUID,
        dataset_id: UUID,
        context: CommandContext,
        request_hash: str,
        runtime_claim: AttemptClaim,
    ) -> CandidateMutationResult:
        try:
            return self._complete_candidate_replay_unchecked(
                replay,
                candidate_policy_id=candidate_policy_id,
                dataset_id=dataset_id,
                context=context,
                request_hash=request_hash,
                runtime_claim=runtime_claim,
            )
        except (CommandInProgressError, IdempotencyKeyReusedError) as exception:
            self._record_candidate_replay_rejection(
                scope_id=f"{candidate_policy_id}:{dataset_id}",
                request_hash=request_hash,
                rejection_code=exception.code,
                context=context,
                runtime_claim=runtime_claim,
            )
            raise
        except (
            ArithmeticError,
            ArtifactIntegrityError,
            CommandPreviouslyFailedError,
            RuntimeNotFoundError,
            RuntimeStateConflictError,
            ValueError,
        ):
            self._record_candidate_replay_rejection(
                scope_id=f"{candidate_policy_id}:{dataset_id}",
                request_hash=request_hash,
                rejection_code="CANDIDATE_REPLAY_INTEGRITY_REJECTED",
                context=context,
                runtime_claim=runtime_claim,
            )
            raise

    def _complete_candidate_replay_unchecked(
        self,
        replay: _CandidateReplayProbe,
        *,
        candidate_policy_id: UUID,
        dataset_id: UUID,
        context: CommandContext,
        request_hash: str,
        runtime_claim: AttemptClaim,
    ) -> CandidateMutationResult:
        with self._uow_provider(read_only=True) as read_uow:
            persisted_plan = read_uow.candidates.persisted_candidate_set(
                candidate_policy_id=candidate_policy_id,
                dataset_id=dataset_id,
                lock=False,
            )
            reconciliation = (
                None
                if replay.binding is None
                else read_uow.candidates.reconciliation(
                    replay.binding.candidate_set_id
                )
            )
        verified_plan = _verify_persisted_candidate_result(
            replay,
            persisted_plan,
            reconciliation,
        )
        scope_id = f"{candidate_policy_id}:{dataset_id}"
        with self._uow_provider() as uow:
            _lock_live(uow, runtime_claim)
            persisted_policy = uow.candidates.policy(
                candidate_policy_id,
                lock=True,
            )
            if persisted_policy != replay.policy:
                raise RuntimeStateConflictError(
                    "CandidatePolicy changed during Candidate replay"
                )
            uow.candidate_artifacts.require_exact(
                replay.policy.code_artifact,
                lock=True,
            )
            uow.candidate_artifacts.require_exact(
                replay.policy.config_artifact,
                lock=True,
            )
            required_features = _policy_feature_dependencies(replay.policy)
            actual_snapshot = uow.research_dependencies.snapshot(
                dataset_id=dataset_id,
                required_features=required_features,
                lock=True,
            )
            if actual_snapshot != replay.snapshot:
                raise RuntimeStateConflictError(
                    "Dataset dependencies changed during Candidate replay"
                )
            uow.candidate_artifacts.require_exact(
                replay.snapshot.dataset.manifest_artifact,
                lock=True,
            )
            uow.candidate_artifacts.require_exact(
                replay.snapshot.dataset.code_artifact,
                lock=True,
            )
            uow.candidate_artifacts.require_exact(
                replay.snapshot.dataset.config_artifact,
                lock=True,
            )
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="BUILD_CANDIDATE_SET",
                scope_id=scope_id,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if receipt != replay.receipt:
                raise ArtifactIntegrityError(
                    "Candidate replay receipt changed before Runtime finalization"
                )
            locked_binding = uow.candidates.candidate_set_binding(
                candidate_policy_id=candidate_policy_id,
                dataset_id=dataset_id,
                lock=True,
            )
            if (
                locked_binding != replay.binding
                or locked_binding != _candidate_set_binding(verified_plan)
            ):
                raise ArtifactIntegrityError(
                    "CandidateSet binding changed before Runtime finalization"
                )
            persisted_plan = uow.candidates.persisted_candidate_set(
                candidate_policy_id=candidate_policy_id,
                dataset_id=dataset_id,
                lock=True,
            )
            _validate_persisted_candidate_set(persisted_plan, verified_plan)
            reconciliation = uow.candidates.reconciliation(
                verified_plan.candidate_set_id
            )
            _validate_reconciliation(reconciliation, verified_plan)
            result = _candidate_set_result_from_receipt(receipt, verified_plan)
            _finalize_runtime(
                uow,
                runtime_claim,
                receipt_id=result.receipt_id,
                result_hash=result.result_hash,
            )
            uow.commit()
            return result

    def _record_candidate_replay_rejection(
        self,
        *,
        scope_id: str,
        request_hash: str,
        rejection_code: str,
        context: CommandContext,
        runtime_claim: AttemptClaim,
    ) -> None:
        self._failure_recorder.record_idempotency_rejection(
            _candidate_replay_failure_descriptor(
                scope_id=scope_id,
                request_hash=request_hash,
            ),
            rejection_code=rejection_code,
            context=context,
            runtime_claim=runtime_claim,
        )

    def _bind_candidate_set(
        self,
        *,
        policy: CandidatePolicy,
        prepared: CandidatePreparedResearchInput,
        preflight_snapshot: CandidateResearchDependencySnapshot,
        plan: CandidateRankingPlan,
        context: CommandContext,
        request_hash: str,
        runtime_claim: AttemptClaim,
    ) -> CandidateMutationResult:
        dataset_id = prepared.dataset.dataset_id
        scope_id = f"{policy.candidate_policy_id}:{dataset_id}"
        required_features = _policy_feature_dependencies(policy)
        with self._uow_provider() as uow:
            _lock_live(uow, runtime_claim)
            uow.candidates.lock_candidate_set_identity(plan.candidate_set_id)
            persisted_policy = uow.candidates.policy(
                policy.candidate_policy_id,
                lock=True,
            )
            if persisted_policy != policy:
                raise RuntimeStateConflictError(
                    "CandidatePolicy changed during CandidateSet preparation"
                )
            uow.candidate_artifacts.require_exact(policy.code_artifact, lock=True)
            uow.candidate_artifacts.require_exact(policy.config_artifact, lock=True)
            actual_snapshot = uow.research_dependencies.snapshot(
                dataset_id=dataset_id,
                required_features=required_features,
                lock=True,
            )
            if (
                actual_snapshot != preflight_snapshot
                or actual_snapshot != _prepared_snapshot(prepared)
            ):
                raise RuntimeStateConflictError(
                    "Dataset dependencies changed during CandidateSet preparation"
                )
            manifest_artifact = uow.candidate_artifacts.require_exact(
                prepared.dataset.manifest_artifact,
                lock=True,
            )
            uow.candidate_artifacts.require_exact(
                prepared.dataset.code_artifact,
                lock=True,
            )
            uow.candidate_artifacts.require_exact(
                prepared.dataset.config_artifact,
                lock=True,
            )
            uow.candidates.insert_candidate_set(plan)
            persisted_plan = uow.candidates.persisted_candidate_set(
                candidate_policy_id=policy.candidate_policy_id,
                dataset_id=dataset_id,
                lock=False,
            )
            _validate_persisted_candidate_set(persisted_plan, plan)
            reconciliation = uow.candidates.reconciliation(plan.candidate_set_id)
            _validate_reconciliation(reconciliation, plan)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="BUILD_CANDIDATE_SET",
                scope_id=scope_id,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                replay = _candidate_set_result_from_receipt(receipt, plan)
                _finalize_runtime(
                    uow,
                    runtime_claim,
                    receipt_id=receipt.receipt_id,
                    result_hash=replay.result_hash,
                )
                uow.commit()
                return replay
            uow.candidate_artifacts.record_verification(
                verification_id=self._id_factory(),
                receipt_id=receipt.receipt_id,
                artifact=manifest_artifact,
                verifier_id="selection-candidate-dataset-manifest-parser",
                policy="CANDIDATE_DATASET_MANIFEST_READ",
                verification=prepared.manifest_verification,
            )
            result_hash = str(plan.result_sha256)
            _finish_success(
                uow,
                id_factory=self._id_factory,
                receipt_id=receipt.receipt_id,
                aggregate_kind="CANDIDATE_SET",
                aggregate_id=str(plan.candidate_set_id),
                aggregate_version=1,
                result_hash=result_hash,
                action="BUILD_CANDIDATE_SET",
                context=context,
                runtime_claim=runtime_claim,
            )
            _finalize_runtime(
                uow,
                runtime_claim,
                receipt_id=receipt.receipt_id,
                result_hash=result_hash,
            )
            uow.commit()
            return CandidateMutationResult(
                aggregate_kind="CANDIDATE_SET",
                aggregate_id=str(plan.candidate_set_id),
                aggregate_version=1,
                result_hash=result_hash,
                receipt_id=receipt.receipt_id,
                replayed=False,
            )

    def _replayed_policy_result(
        self,
        uow: CandidateUnitOfWork,
        receipt: ReceiptRecord,
        requested: CandidatePolicy,
    ) -> CandidateMutationResult:
        _ensure_successful_receipt(receipt, aggregate_kind="CANDIDATE_POLICY")
        persisted = uow.candidates.policy(
            requested.candidate_policy_id,
            lock=False,
        )
        expected_hash = _policy_result_hash(persisted)
        if (
            persisted != requested
            or receipt.result_aggregate_id != str(requested.candidate_policy_id)
            or receipt.result_aggregate_version != requested.version
            or receipt.result_hash != expected_hash
        ):
            raise ArtifactIntegrityError(
                "CandidatePolicy receipt and Authority do not reconcile"
            )
        return CandidateMutationResult(
            aggregate_kind="CANDIDATE_POLICY",
            aggregate_id=str(requested.candidate_policy_id),
            aggregate_version=requested.version,
            result_hash=expected_hash,
            receipt_id=receipt.receipt_id,
            replayed=True,
        )


def _policy_feature_dependencies(
    policy: CandidatePolicy,
) -> tuple[CandidateFeatureDependency, ...]:
    return tuple(
        CandidateFeatureDependency(
            feature_definition_id=component.feature_definition_id,
            content_sha256=str(component.feature_definition_content_sha256),
            value_type=component.feature_value_type.value,
        )
        for component in policy.components
    )


def _policy_result_hash(policy: CandidatePolicy) -> str:
    return canonical_json_sha256(
        {
            "candidate_policy_id": policy.candidate_policy_id,
            "content_sha256": policy.content_sha256,
            "version": policy.version,
        }
    )


def _build_request_hash(
    *,
    policy: CandidatePolicy,
    snapshot: CandidateResearchDependencySnapshot,
) -> str:
    return canonical_json_sha256(
        {
            "algorithm_contract": {
                "missing_policy": policy.missing_policy,
                "normalization_method": policy.normalization_method,
                "projection_method": policy.projection_method,
                "projection_version": policy.projection_version,
                "rank_method": policy.rank_method,
                "score_semantics": policy.score_semantics,
                "selection_method": policy.selection_method,
                "tie_policy": policy.tie_policy,
            },
            "candidate_policy_content_sha256": policy.content_sha256,
            "candidate_policy_id": policy.candidate_policy_id,
            "dataset_dependency_sha256": snapshot.dependency_sha256,
            "dataset_id": snapshot.dataset.dataset_id,
        }
    )


def _candidate_replay_failure_descriptor(
    *,
    scope_id: str,
    request_hash: str,
) -> CommandFailureDescriptor:
    return CommandFailureDescriptor(
        command_kind="BUILD_CANDIDATE_SET",
        scope_id=scope_id,
        request_hash=request_hash,
        error_class="COMMAND",
        error_code="BUILD_CANDIDATE_SET_REJECTED",
        aggregate_kind="CANDIDATE_COMMAND",
        failure_action="CANDIDATE_COMMAND_FAILED",
        rejection_command_kind="CANDIDATE_COMMAND_REJECTION",
        rejection_action="CANDIDATE_COMMAND_REJECTED",
        rejection_key_prefix="candidate-command-rejection",
    )


def _validate_prepared_input(
    prepared: CandidatePreparedResearchInput,
    *,
    dataset_id: UUID,
    required_features: tuple[CandidateFeatureDependency, ...],
) -> None:
    if prepared.dataset.dataset_id != dataset_id:
        raise RuntimeStateConflictError(
            "Candidate Research input returned a different Dataset"
        )
    if prepared.features != required_features:
        raise RuntimeStateConflictError(
            "Candidate Research input FeatureDefinition bindings diverged"
        )
    if prepared.manifest_verification.result != "VERIFIED":
        raise ArtifactIntegrityError(
            "Candidate Dataset manifest bytes were not exactly verified"
        )
    row_population = tuple(
        (row.population_source_id, row.instrument_id) for row in prepared.rows
    )
    dependency_population = tuple(
        (item.population_dataset_source_id, item.instrument_id)
        for item in prepared.population
    )
    if (
        len(prepared.rows) != prepared.dataset.row_count
        or row_population != dependency_population
    ):
        raise RuntimeStateConflictError(
            "Candidate Dataset population and prepared rows diverged"
        )


def _prepared_snapshot(
    prepared: CandidatePreparedResearchInput,
) -> CandidateResearchDependencySnapshot:
    return CandidateResearchDependencySnapshot(
        dataset=prepared.dataset,
        features=prepared.features,
        population=prepared.population,
        dependency_sha256=prepared.dependency_sha256,
    )


def _validate_persisted_candidate_set(
    persisted: CandidateRankingPlan | None,
    expected: CandidateRankingPlan,
) -> None:
    if persisted != expected:
        raise ArtifactIntegrityError(
            "persisted Candidate Authority does not reconcile"
        )


def _verify_persisted_candidate_result(
    replay: _CandidateReplayProbe,
    persisted: CandidateRankingPlan | None,
    reconciliation: CandidatePersistenceReconciliation | None,
) -> CandidateRankingPlan:
    if replay.binding is None or persisted is None or reconciliation is None:
        raise ArtifactIntegrityError(
            "CandidateSet receipt has no persisted Candidate Authority"
        )
    candidate_set = persisted.candidate_set
    expected_binding = _candidate_set_binding(persisted)
    if replay.binding != expected_binding:
        raise ArtifactIntegrityError(
            "CandidateSet probe binding and persisted Authority diverged"
        )
    policy = replay.policy
    snapshot = replay.snapshot
    if (
        candidate_set.candidate_policy_id != policy.candidate_policy_id
        or str(candidate_set.candidate_policy_content_sha256)
        != str(policy.content_sha256)
        or candidate_set.dataset_id != snapshot.dataset.dataset_id
        or str(candidate_set.dataset_content_sha256)
        != str(snapshot.dataset.content_sha256)
        or str(candidate_set.dependency_sha256)
        != str(snapshot.dependency_sha256)
        or candidate_set.universe_revision_id
        != snapshot.dataset.universe_revision_id
        or candidate_set.eligibility_policy_id
        != snapshot.dataset.eligibility_policy_id
        or candidate_set.decision_time != snapshot.dataset.decision_time
        or candidate_set.requested_top_k != policy.requested_top_k
        or candidate_set.component_count != policy.component_count
        or candidate_set.population_count != snapshot.dataset.row_count
    ):
        raise ArtifactIntegrityError(
            "CandidateSet dependencies and persisted Authority diverged"
        )
    _validate_persisted_candidate_counts(persisted, policy)
    _validate_reconciliation(reconciliation, persisted)
    recomputed_hash = candidate_result_content_sha256(
        policy=policy,
        candidate_set_id=candidate_set.candidate_set_id,
        dataset_id=candidate_set.dataset_id,
        dataset_content_sha256=candidate_set.dataset_content_sha256,
        dependency_sha256=candidate_set.dependency_sha256,
        projection_precision=candidate_set.decimal_projection_precision,
        candidates=persisted.candidates,
        score_components=persisted.score_components,
        component_diagnostics=persisted.component_diagnostics,
    )
    if recomputed_hash != candidate_set.result_sha256:
        raise ArtifactIntegrityError(
            "persisted Candidate result content hash does not reconcile"
        )
    _candidate_set_result_from_receipt(replay.receipt, persisted)
    return persisted


def _candidate_set_binding(plan: CandidateRankingPlan) -> CandidateSetBinding:
    candidate_set = plan.candidate_set
    return CandidateSetBinding(
        candidate_set_id=candidate_set.candidate_set_id,
        candidate_policy_id=candidate_set.candidate_policy_id,
        candidate_policy_content_sha256=str(
            candidate_set.candidate_policy_content_sha256
        ),
        dataset_id=candidate_set.dataset_id,
        dataset_content_sha256=str(candidate_set.dataset_content_sha256),
        dependency_sha256=str(candidate_set.dependency_sha256),
        result_sha256=str(candidate_set.result_sha256),
    )


def _validate_persisted_candidate_counts(
    plan: CandidateRankingPlan,
    policy: CandidatePolicy,
) -> None:
    candidate_set = plan.candidate_set
    component_identities = tuple(
        (
            item.candidate_policy_component_id,
            item.feature_definition_id,
        )
        for item in plan.component_diagnostics
    )
    expected_component_identities = tuple(
        (
            item.candidate_policy_component_id,
            item.feature_definition_id,
        )
        for item in policy.components
    )
    if component_identities != expected_component_identities:
        raise ArtifactIntegrityError(
            "persisted Candidate diagnostics and Policy components diverged"
        )
    candidates_by_id = {item.candidate_id: item for item in plan.candidates}
    if len(candidates_by_id) != len(plan.candidates):
        raise ArtifactIntegrityError("persisted Candidate identities are not unique")
    if (
        len({item.instrument_id for item in plan.candidates})
        != len(plan.candidates)
        or len(
            {item.dataset_population_source_id for item in plan.candidates}
        )
        != len(plan.candidates)
    ):
        raise ArtifactIntegrityError(
            "persisted Candidate population identities are not unique"
        )
    for candidate in plan.candidates:
        if (
            candidate.candidate_set_id != candidate_set.candidate_set_id
            or candidate.candidate_policy_id
            != candidate_set.candidate_policy_id
            or candidate.dataset_id != candidate_set.dataset_id
            or candidate.dataset_source_role != "POPULATION"
        ):
            raise ArtifactIntegrityError(
                "persisted Candidate parent bindings do not reconcile"
            )
    policy_components = {
        item.candidate_policy_component_id: item for item in policy.components
    }
    scores_by_candidate: dict[
        UUID, dict[UUID, CandidateScoreComponentRecord]
    ] = {
        item.candidate_id: {} for item in plan.candidates
    }
    score_ids: set[UUID] = set()
    for score in plan.score_components:
        candidate = candidates_by_id.get(score.candidate_id)
        component = policy_components.get(
            score.candidate_policy_component_id
        )
        if (
            candidate is None
            or component is None
            or score.candidate_set_id != candidate_set.candidate_set_id
            or score.candidate_policy_id
            != candidate_set.candidate_policy_id
            or score.dataset_id != candidate_set.dataset_id
            or score.instrument_id != candidate.instrument_id
            or score.candidate_disposition != candidate.disposition
            or score.feature_definition_id
            != component.feature_definition_id
            or str(score.feature_content_sha256)
            != str(component.feature_content_sha256)
            or score.feature_value_type != component.feature_value_type
        ):
            raise ArtifactIntegrityError(
                "persisted Candidate score bindings do not reconcile"
            )
        if score.candidate_score_component_id in score_ids:
            raise ArtifactIntegrityError(
                "persisted Candidate score identities are not unique"
            )
        score_ids.add(score.candidate_score_component_id)
        candidate_scores = scores_by_candidate[score.candidate_id]
        if score.candidate_policy_component_id in candidate_scores:
            raise ArtifactIntegrityError(
                "persisted Candidate score matrix has duplicate cells"
            )
        candidate_scores[score.candidate_policy_component_id] = score

    expected_component_ids = set(policy_components)
    if any(
        set(candidate_scores) != expected_component_ids
        for candidate_scores in scores_by_candidate.values()
    ):
        raise ArtifactIntegrityError(
            "persisted Candidate score matrix is incomplete"
        )

    rankable_candidates = []
    unrankable_candidates = []
    for candidate in plan.candidates:
        candidate_scores = scores_by_candidate[candidate.candidate_id]
        fact_rankable = all(
            score.raw_status is CandidateCellStatus.AVAILABLE
            for score in candidate_scores.values()
        )
        if fact_rankable:
            if (
                candidate.disposition is CandidateDisposition.UNRANKABLE
                or candidate.composite_score is None
                or candidate.competition_rank is None
                or any(
                    score.percentile is None or score.contribution is None
                    for score in candidate_scores.values()
                )
            ):
                raise ArtifactIntegrityError(
                    "persisted rankable Candidate facts do not reconcile"
                )
            rankable_candidates.append(candidate)
        else:
            if (
                candidate.disposition is not CandidateDisposition.UNRANKABLE
                or candidate.composite_score is not None
                or candidate.competition_rank is not None
                or any(
                    score.percentile is not None
                    or score.contribution is not None
                    for score in candidate_scores.values()
                )
            ):
                raise ArtifactIntegrityError(
                    "persisted STRICT_COMPLETE_CASE facts do not reconcile"
                )
            unrankable_candidates.append(candidate)

    expected_diagnostics = []
    for component in policy.components:
        component_scores = tuple(
            scores_by_candidate[candidate.candidate_id][
                component.candidate_policy_component_id
            ]
            for candidate in plan.candidates
        )
        observed_scores = tuple(
            scores_by_candidate[candidate.candidate_id][
                component.candidate_policy_component_id
            ]
            for candidate in rankable_candidates
        )
        distinct_count = len(
            {
                (score.raw_decimal_value, score.raw_integer_value)
                for score in observed_scores
            }
        )
        raw_status_counts = {
            status: sum(score.raw_status is status for score in component_scores)
            for status in CandidateCellStatus
        }
        if not rankable_candidates:
            information_status = CandidateRankingStatus.NOT_ESTIMABLE
        elif distinct_count == 1:
            information_status = CandidateRankingStatus.CONSTANT
        else:
            information_status = CandidateRankingStatus.AVAILABLE
        expected_diagnostics.append(
            (
                component.candidate_policy_component_id,
                component.feature_definition_id,
                len(rankable_candidates),
                distinct_count,
                raw_status_counts[CandidateCellStatus.AVAILABLE],
                raw_status_counts[CandidateCellStatus.AVAILABLE]
                - len(rankable_candidates),
                raw_status_counts[CandidateCellStatus.MISSING],
                raw_status_counts[CandidateCellStatus.UNKNOWN],
                raw_status_counts[CandidateCellStatus.STALE],
                raw_status_counts[CandidateCellStatus.CONFLICT],
                information_status,
            )
        )
    actual_diagnostics = [
        (
            item.candidate_policy_component_id,
            item.feature_definition_id,
            item.observed_count,
            item.distinct_count,
            item.raw_available_count,
            item.available_but_not_observed_count,
            item.missing_count,
            item.unknown_count,
            item.stale_count,
            item.conflict_count,
            item.ranking_status,
        )
        for item in plan.component_diagnostics
    ]
    if actual_diagnostics != expected_diagnostics:
        raise ArtifactIntegrityError(
            "persisted Candidate component diagnostics do not reconcile"
        )

    rankable_scores = {
        item.candidate_id: item.composite_score for item in rankable_candidates
    }
    if any(value is None for value in rankable_scores.values()):
        raise ArtifactIntegrityError(
            "persisted rankable Candidate scores do not reconcile"
        )
    concrete_scores = {
        identity: value
        for identity, value in rankable_scores.items()
        if value is not None
    }
    if concrete_scores:
        ordered_scores = sorted(concrete_scores.values(), reverse=True)
        boundary_score = ordered_scores[
            min(candidate_set.requested_top_k, len(ordered_scores)) - 1
        ]
        expected_selected_ids = {
            identity
            for identity, score in concrete_scores.items()
            if score >= boundary_score
        }
        strictly_above_boundary_count = sum(
            score > boundary_score for score in concrete_scores.values()
        )
        boundary_group_count = sum(
            score == boundary_score for score in concrete_scores.values()
        )
        boundary_rank = strictly_above_boundary_count + 1
    else:
        boundary_score = None
        expected_selected_ids = set()
        strictly_above_boundary_count = 0
        boundary_group_count = 0
        boundary_rank = None
    selected_candidates = tuple(
        item
        for item in rankable_candidates
        if item.disposition is CandidateDisposition.SELECTED
    )
    ranked_not_selected_candidates = tuple(
        item
        for item in rankable_candidates
        if item.disposition is CandidateDisposition.RANKED_NOT_SELECTED
    )
    actual_selected_ids = {item.candidate_id for item in selected_candidates}
    if actual_selected_ids != expected_selected_ids:
        raise ArtifactIntegrityError(
            "persisted Candidate boundary dispositions do not reconcile"
        )
    for candidate in rankable_candidates:
        assert candidate.composite_score is not None
        expected_rank = 1 + sum(
            other > candidate.composite_score
            for other in concrete_scores.values()
        )
        if candidate.competition_rank != expected_rank:
            raise ArtifactIntegrityError(
                "persisted Candidate competition ranks do not reconcile"
            )

    selected_count = len(selected_candidates)
    ranked_not_selected_count = len(ranked_not_selected_candidates)
    unrankable_count = len(unrankable_candidates)
    diagnostic_status_counts = {
        status: sum(
            item.ranking_status is status for item in plan.component_diagnostics
        )
        for status in CandidateRankingStatus
    }
    if all(
        item.ranking_status is CandidateRankingStatus.NOT_ESTIMABLE
        for item in plan.component_diagnostics
    ):
        ranking_status = CandidateRankingStatus.NOT_ESTIMABLE
    elif any(
        item.ranking_status is CandidateRankingStatus.AVAILABLE
        for item in plan.component_diagnostics
    ):
        ranking_status = CandidateRankingStatus.AVAILABLE
    else:
        ranking_status = CandidateRankingStatus.CONSTANT
    composite_distinct_count = len(set(concrete_scores.values()))
    expected_summary = (
        len(plan.candidates),
        len(rankable_candidates),
        unrankable_count,
        selected_count,
        ranked_not_selected_count,
        len(plan.score_components),
        diagnostic_status_counts[CandidateRankingStatus.AVAILABLE],
        diagnostic_status_counts[CandidateRankingStatus.CONSTANT],
        diagnostic_status_counts[CandidateRankingStatus.NOT_ESTIMABLE],
        ranking_status,
        composite_distinct_count,
        boundary_score,
        boundary_rank,
        strictly_above_boundary_count,
        boundary_group_count,
        max(0, selected_count - candidate_set.requested_top_k),
        boundary_group_count > 1,
        selected_count > candidate_set.requested_top_k,
    )
    actual_summary = (
        candidate_set.population_count,
        candidate_set.rankable_count,
        candidate_set.unrankable_count,
        candidate_set.selected_count,
        candidate_set.ranked_not_selected_count,
        candidate_set.score_component_count,
        candidate_set.available_component_count,
        candidate_set.constant_component_count,
        candidate_set.not_estimable_component_count,
        candidate_set.ranking_status,
        candidate_set.composite_distinct_count,
        candidate_set.boundary_score,
        candidate_set.boundary_rank,
        candidate_set.strictly_above_boundary_count,
        candidate_set.boundary_group_count,
        candidate_set.selected_overflow_count,
        candidate_set.boundary_has_tie,
        candidate_set.boundary_tie_expanded,
    )
    if actual_summary != expected_summary:
        raise ArtifactIntegrityError(
            "persisted CandidateSet summary facts do not reconcile"
        )

    all_rankable_selected = (
        selected_count == len(rankable_candidates)
        and candidate_set.requested_top_k >= len(rankable_candidates)
    )
    boundary_tie_expanded = selected_count > candidate_set.requested_top_k
    for candidate in plan.candidates:
        if candidate.disposition is CandidateDisposition.UNRANKABLE:
            expected_reason = "STRICT_COMPLETE_CASE_REQUIRED_FEATURE_UNAVAILABLE"
        elif candidate.disposition is CandidateDisposition.RANKED_NOT_SELECTED:
            expected_reason = "BELOW_BOUNDARY"
        elif all_rankable_selected:
            expected_reason = "ALL_RANKABLE_SELECTED"
        elif candidate.composite_score is not None and (
            boundary_score is not None
            and candidate.composite_score > boundary_score
        ):
            expected_reason = "ABOVE_BOUNDARY"
        elif boundary_tie_expanded:
            expected_reason = "BOUNDARY_TIE_INCLUDED"
        else:
            expected_reason = "AT_BOUNDARY"
        if candidate.reason_code != expected_reason:
            raise ArtifactIntegrityError(
                "persisted Candidate disposition reasons do not reconcile"
            )


def _validate_reconciliation(
    actual: CandidatePersistenceReconciliation,
    plan: CandidateRankingPlan,
) -> None:
    expected = plan.candidate_set
    if (
        actual.population_count != expected.population_count
        or actual.selected_count != expected.selected_count
        or actual.ranked_not_selected_count
        != expected.ranked_not_selected_count
        or actual.unrankable_count != expected.unrankable_count
        or actual.score_component_count != expected.score_component_count
        or not actual.population_reconciled
        or not actual.rankable_reconciled
        or not actual.component_matrix_reconciled
        or not actual.ranking_reconciled
    ):
        raise ArtifactIntegrityError(
            "CandidateSet persistence reconciliation failed"
        )


def _candidate_set_result_from_receipt(
    receipt: ReceiptRecord,
    plan: CandidateRankingPlan,
) -> CandidateMutationResult:
    _ensure_successful_receipt(receipt, aggregate_kind="CANDIDATE_SET")
    if (
        receipt.result_aggregate_id != str(plan.candidate_set_id)
        or receipt.result_aggregate_version != 1
        or receipt.result_hash != str(plan.result_sha256)
    ):
        raise ArtifactIntegrityError(
            "CandidateSet receipt and Authority do not reconcile"
        )
    return CandidateMutationResult(
        aggregate_kind="CANDIDATE_SET",
        aggregate_id=str(plan.candidate_set_id),
        aggregate_version=1,
        result_hash=str(plan.result_sha256),
        receipt_id=receipt.receipt_id,
        replayed=True,
    )


def _ensure_successful_receipt(
    receipt: ReceiptRecord,
    *,
    aggregate_kind: str,
) -> None:
    if receipt.status in {"FAILED", "BLOCKED"}:
        raise CommandPreviouslyFailedError(
            receipt.error_code or "CANDIDATE_COMMAND_FAILED_WITHOUT_ERROR_CODE"
        )
    if (
        receipt.status != "SUCCEEDED"
        or receipt.result_aggregate_kind != aggregate_kind
        or receipt.result_aggregate_id is None
        or receipt.result_aggregate_version is None
        or receipt.result_hash is None
    ):
        raise RuntimeStateConflictError(
            "Candidate command receipt is not a complete terminal success"
        )


def _lock_live(
    uow: CandidateUnitOfWork,
    claim: AttemptClaim | None,
) -> None:
    if claim is not None:
        uow.runtime_finalization.lock_live(claim)


def _finish_success(
    uow: CandidateUnitOfWork,
    *,
    id_factory: Callable[[], UUID],
    receipt_id: UUID,
    aggregate_kind: str,
    aggregate_id: str,
    aggregate_version: int,
    result_hash: str,
    action: str,
    context: CommandContext,
    runtime_claim: AttemptClaim | None,
) -> None:
    uow.receipts.succeed(
        receipt_id=receipt_id,
        aggregate_kind=aggregate_kind,
        aggregate_id=aggregate_id,
        aggregate_version=aggregate_version,
        result_hash=result_hash,
        runtime_claim=runtime_claim,
    )
    uow.audit.append(
        audit_event_id=id_factory(),
        receipt_id=receipt_id,
        actor_type=context.actor_type.value,
        actor_id=context.actor_id,
        aggregate_kind=aggregate_kind,
        aggregate_id=aggregate_id,
        action=action,
        reason_code=context.reason_code,
        before_version=None,
        after_version=aggregate_version,
        runtime_claim=runtime_claim,
    )


def _finalize_runtime(
    uow: CandidateUnitOfWork,
    claim: AttemptClaim | None,
    *,
    receipt_id: UUID,
    result_hash: str,
) -> None:
    if claim is not None:
        uow.runtime_finalization.succeed(
            claim,
            receipt_id=receipt_id,
            result_hash=result_hash,
        )


__all__ = [
    "CandidateApplication",
    "CandidateMutationResult",
    "replay_concurrent_success",
]
