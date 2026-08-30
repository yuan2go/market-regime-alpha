"""Candidate Policy registration and deterministic CandidateSet assembly."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
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
    CandidatePopulationCell,
    CandidatePopulationRow,
)
from market_regime_alpha.selection.domain.candidate_policy import (
    CandidateFeatureValueType,
    CandidatePolicy,
)
from market_regime_alpha.selection.domain.candidate_ranking import (
    build_candidate_set as rank_candidate_set,
)
from market_regime_alpha.selection.domain.candidate_results import (
    CandidateRankingPlan,
    CandidateScoreComponentRecord,
)
from market_regime_alpha.selection.ports.candidate_repository import (
    CandidatePersistenceReconciliation,
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
class _CandidateReplayLoad:
    receipt: ReceiptRecord
    policy: CandidatePolicy
    snapshot: CandidateResearchDependencySnapshot
    persisted_plan: CandidateRankingPlan | None


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
        runtime_claim: AttemptClaim | None = None,
    ) -> CandidateMutationResult:
        """Prepare and rank outside PostgreSQL, then bind in one short UoW."""

        identity_request_hash = canonical_json_sha256(
            {
                "candidate_policy_id": candidate_policy_id,
                "dataset_id": dataset_id,
            }
        )
        operation = "BUILD_CANDIDATE_SET"
        scope_id = f"{candidate_policy_id}:{dataset_id}"
        request_hash_holder = {"value": identity_request_hash}
        replay_load: _CandidateReplayLoad | None = None
        with candidate_failure_boundary(
            self._failure_recorder,
            operation=operation,
            scope_id=scope_id,
            request_hash=lambda: request_hash_holder["value"],
            context=context,
            runtime_claim=runtime_claim,
        ):
            replay_load, policy, preflight_snapshot, request_hash = (
                self._preflight_build(
                    candidate_policy_id=candidate_policy_id,
                    dataset_id=dataset_id,
                    context=context,
                    request_hash_holder=request_hash_holder,
                    runtime_claim=runtime_claim,
                )
            )
            request_hash_holder["value"] = request_hash
            if replay_load is None:
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
        assert replay_load is not None
        return self._complete_candidate_replay(
            replay_load,
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
        runtime_claim: AttemptClaim | None,
    ) -> tuple[
        _CandidateReplayLoad | None,
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
                persisted_plan = uow.candidates.persisted_candidate_set(
                    candidate_policy_id=candidate_policy_id,
                    dataset_id=dataset_id,
                    lock=False,
                )
                return (
                    _CandidateReplayLoad(
                        receipt=receipt,
                        policy=policy,
                        snapshot=snapshot,
                        persisted_plan=persisted_plan,
                    ),
                    None,
                    None,
                    request_hash,
                )
            return None, policy, snapshot, request_hash

    def _complete_candidate_replay(
        self,
        replay: _CandidateReplayLoad,
        *,
        candidate_policy_id: UUID,
        dataset_id: UUID,
        context: CommandContext,
        request_hash: str,
        runtime_claim: AttemptClaim | None,
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
        replay: _CandidateReplayLoad,
        *,
        candidate_policy_id: UUID,
        dataset_id: UUID,
        context: CommandContext,
        request_hash: str,
        runtime_claim: AttemptClaim | None,
    ) -> CandidateMutationResult:
        verified_plan = _rebuild_persisted_candidate_set(
            replay.policy,
            replay.persisted_plan,
        )
        result = _candidate_set_result_from_receipt(
            replay.receipt,
            verified_plan,
        )
        if runtime_claim is None:
            return result
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
            persisted_plan = uow.candidates.persisted_candidate_set(
                candidate_policy_id=candidate_policy_id,
                dataset_id=dataset_id,
                lock=True,
            )
            _validate_persisted_candidate_set(persisted_plan, verified_plan)
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
        runtime_claim: AttemptClaim | None,
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
        runtime_claim: AttemptClaim | None,
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
                if runtime_claim is not None:
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


def _rebuild_persisted_candidate_set(
    policy: CandidatePolicy,
    persisted: CandidateRankingPlan | None,
) -> CandidateRankingPlan:
    if persisted is None:
        raise ArtifactIntegrityError(
            "CandidateSet receipt has no persisted Candidate Authority"
        )
    try:
        population = _population_from_persisted_candidate_set(persisted)
        rebuilt = rank_candidate_set(policy=policy, dataset=population)
    except (ArithmeticError, KeyError, TypeError, ValueError) as exception:
        raise ArtifactIntegrityError(
            "persisted Candidate raw matrix cannot rebuild ranking"
        ) from exception
    _validate_persisted_candidate_set(persisted, rebuilt)
    return rebuilt


def _population_from_persisted_candidate_set(
    persisted: CandidateRankingPlan,
) -> CandidateDatasetPopulation:
    scores_by_candidate: dict[UUID, list[CandidateScoreComponentRecord]] = {
        candidate.candidate_id: [] for candidate in persisted.candidates
    }
    for score in persisted.score_components:
        try:
            scores_by_candidate[score.candidate_id].append(score)
        except KeyError as exception:
            raise ArtifactIntegrityError(
                "persisted Candidate score has no Candidate parent"
            ) from exception
    rows = tuple(
        CandidatePopulationRow(
            instrument_id=candidate.instrument_id,
            dataset_population_source_id=(
                candidate.dataset_population_source_id
            ),
            cells=tuple(
                CandidatePopulationCell(
                    feature_definition_id=score.feature_definition_id,
                    status=score.raw_status,
                    value=_persisted_raw_value(score),
                    reason_code=score.raw_reason_code,
                    cell_source_lineage_hash=score.cell_source_lineage_hash,
                )
                for score in scores_by_candidate[candidate.candidate_id]
            ),
        )
        for candidate in persisted.candidates
    )
    candidate_set = persisted.candidate_set
    return CandidateDatasetPopulation(
        dataset_id=candidate_set.dataset_id,
        dataset_content_sha256=candidate_set.dataset_content_sha256,
        decision_time=candidate_set.decision_time,
        universe_revision_id=candidate_set.universe_revision_id,
        eligibility_policy_id=candidate_set.eligibility_policy_id,
        rows=rows,
        dependency_sha256=candidate_set.dependency_sha256,
    )


def _persisted_raw_value(
    score: CandidateScoreComponentRecord,
) -> Decimal | int | None:
    if score.raw_status is not CandidateCellStatus.AVAILABLE:
        return None
    if score.feature_value_type is CandidateFeatureValueType.DECIMAL:
        return score.raw_decimal_value
    return score.raw_integer_value


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
