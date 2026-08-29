"""Decision-input Dataset registration and short-transaction binding."""

from __future__ import annotations

from typing import Callable
from uuid import UUID

from market_regime_alpha.research_qualification.application._command_support import (
    ResearchFailureAlreadyRecorded,
    failure_descriptor,
    finalize_runtime,
    finish_success,
    replay_concurrent_success,
    terminal_failure_boundary,
)
from market_regime_alpha.research_qualification.application._dataset_validation import (
    validate_market_lineage,
    validate_population,
)
from market_regime_alpha.research_qualification.application._results import (
    DatasetRegistrationResult,
    dataset_result,
    dataset_result_hash,
    replayed_dataset_result,
)
from market_regime_alpha.research_qualification.domain import (
    DecisionInputDatasetDefinition,
    DecisionInputDatasetManifest,
    FeatureDefinition,
    parse_decision_input_dataset_manifest,
)
from market_regime_alpha.research_qualification.ports import (
    ResearchArtifactByteStore,
    ResearchUnitOfWorkProvider,
)
from market_regime_alpha.runtime.application import (
    CommandContext,
    ConcurrentCommandSucceeded,
    RuntimeCommandFailureRecorder,
)
from market_regime_alpha.runtime.errors import (
    ArtifactByteStoreError,
    ArtifactIntegrityError,
    RuntimeStateConflictError,
)
from market_regime_alpha.runtime.ports import AttemptClaim, ByteVerification
from market_regime_alpha.shared.hashing import canonical_json_sha256


class DatasetCommands:
    """Own strict Decision-input Dataset verification and registration."""

    def __init__(
        self,
        byte_store: ResearchArtifactByteStore,
        uow_provider: ResearchUnitOfWorkProvider,
        *,
        id_factory: Callable[[], UUID],
    ) -> None:
        self._byte_store = byte_store
        self._uow_provider = uow_provider
        self._id_factory = id_factory
        self._failure_recorder = RuntimeCommandFailureRecorder(
            uow_provider,
            id_factory=id_factory,
        )

    @replay_concurrent_success
    def register(
        self,
        definition: DecisionInputDatasetDefinition,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> DatasetRegistrationResult:
        request_hash = canonical_json_sha256(definition)
        with terminal_failure_boundary(
            self._failure_recorder,
            operation="REGISTER_DATASET",
            scope_id=definition.dataset_code,
            request_hash=request_hash,
            error_class="COMMAND",
            error_code="REGISTER_DATASET_REJECTED",
            context=context,
            runtime_claim=runtime_claim,
        ):
            replay, preflight_features = self._preflight(
                definition,
                context=context,
                request_hash=request_hash,
                runtime_claim=runtime_claim,
            )
            if replay is not None:
                return replay
            verification = self._byte_store.verify(
                str(definition.manifest_artifact.content_sha256),
                expected_size=definition.manifest_artifact.size_bytes,
            )
            if verification.result != "VERIFIED":
                self._record_manifest_failure(
                    definition,
                    verification=verification,
                    context=context,
                    request_hash=request_hash,
                    runtime_claim=runtime_claim,
                )
                raise ResearchFailureAlreadyRecorded(
                    "Decision-input Dataset manifest bytes failed exact verification"
                )
            try:
                content = self._byte_store.read_bytes(
                    str(definition.manifest_artifact.content_sha256),
                    expected_size=definition.manifest_artifact.size_bytes,
                )
            except ArtifactByteStoreError as exc:
                failed_observation = self._manifest_read_failure_observation(
                    definition,
                    prior_verification=verification,
                )
                self._record_manifest_failure(
                    definition,
                    verification=failed_observation,
                    context=context,
                    request_hash=request_hash,
                    runtime_claim=runtime_claim,
                )
                raise ResearchFailureAlreadyRecorded(
                    "Decision-input Dataset manifest bytes changed during read"
                ) from exc
            manifest = parse_decision_input_dataset_manifest(
                content,
                dataset=definition,
                feature_definitions=preflight_features,
            )
            if manifest.content_sha256 != definition.manifest_artifact.content_sha256:
                raise ArtifactIntegrityError(
                    "Decision-input Dataset manifest hash does not match its binding"
                )
            return self._bind(
                definition,
                manifest,
                preflight_features=preflight_features,
                verification=verification,
                context=context,
                request_hash=request_hash,
                runtime_claim=runtime_claim,
            )

    def _manifest_read_failure_observation(
        self,
        definition: DecisionInputDatasetDefinition,
        *,
        prior_verification: ByteVerification,
    ) -> ByteVerification:
        try:
            observation = self._byte_store.verify(
                str(definition.manifest_artifact.content_sha256),
                expected_size=definition.manifest_artifact.size_bytes,
            )
        except ArtifactByteStoreError:
            return ByteVerification(
                result="INTEGRITY_ERROR",
                observed_exists=False,
                observed_size_bytes=None,
                observed_sha256=None,
            )
        if observation.result != "VERIFIED":
            return observation
        return ByteVerification(
            result="INTEGRITY_ERROR",
            observed_exists=prior_verification.observed_exists,
            observed_size_bytes=prior_verification.observed_size_bytes,
            observed_sha256=prior_verification.observed_sha256,
        )

    def _record_manifest_failure(
        self,
        definition: DecisionInputDatasetDefinition,
        *,
        verification: ByteVerification,
        context: CommandContext,
        request_hash: str,
        runtime_claim: AttemptClaim | None,
    ) -> None:
        descriptor = failure_descriptor(
            operation="REGISTER_DATASET",
            scope_id=definition.dataset_code,
            request_hash=request_hash,
            error_class="DATA_INTEGRITY",
            error_code="REGISTER_DATASET_REJECTED",
        )
        with self._uow_provider() as uow:
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            artifact = uow.research_artifacts.lock_exact_identity(
                definition.manifest_artifact
            )
            receipt = self._failure_recorder.append_failure(
                uow,
                descriptor=descriptor,
                context=context,
                runtime_claim=runtime_claim,
            )
            if receipt.status == "SUCCEEDED":
                raise ConcurrentCommandSucceeded(
                    runtime_finalized=runtime_claim is not None
                )
            uow.research_artifacts.record_verification(
                verification_id=self._id_factory(),
                receipt_id=receipt.receipt_id,
                artifact=artifact,
                verifier_id="research-dataset-manifest-parser",
                policy="RESEARCH_DATASET_MANIFEST_READ",
                verification=verification,
            )
            uow.commit()

    def _preflight(
        self,
        definition: DecisionInputDatasetDefinition,
        *,
        context: CommandContext,
        request_hash: str,
        runtime_claim: AttemptClaim | None,
    ) -> tuple[DatasetRegistrationResult | None, tuple[FeatureDefinition, ...]]:
        with self._uow_provider() as uow:
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="REGISTER_DATASET",
                scope_id=definition.dataset_code,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                replay = replayed_dataset_result(uow, receipt)
                finalize_runtime(
                    uow,
                    runtime_claim,
                    receipt_id=receipt.receipt_id,
                    result_hash=replay.result_hash,
                )
                if runtime_claim is not None:
                    uow.commit()
                return replay, ()
            features = uow.research_definitions.feature_definitions(
                definition.feature_definition_ids,
                lock=False,
            )
            uow.research_artifacts.require_exact(
                definition.manifest_artifact,
                lock=False,
            )
            uow.research_artifacts.require_exact(
                definition.code_artifact,
                lock=False,
            )
            uow.research_artifacts.require_exact(
                definition.config_artifact,
                lock=False,
            )
            return None, features

    def _bind(
        self,
        definition: DecisionInputDatasetDefinition,
        manifest: DecisionInputDatasetManifest,
        *,
        preflight_features: tuple[FeatureDefinition, ...],
        verification: ByteVerification,
        context: CommandContext,
        request_hash: str,
        runtime_claim: AttemptClaim | None,
    ) -> DatasetRegistrationResult:
        with self._uow_provider() as uow:
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="REGISTER_DATASET",
                scope_id=definition.dataset_code,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                replay = replayed_dataset_result(uow, receipt)
                finalize_runtime(
                    uow,
                    runtime_claim,
                    receipt_id=receipt.receipt_id,
                    result_hash=replay.result_hash,
                )
                if runtime_claim is not None:
                    uow.commit()
                return replay
            features = uow.research_definitions.feature_definitions(
                definition.feature_definition_ids,
                lock=True,
            )
            if features != preflight_features:
                raise RuntimeStateConflictError(
                    "FeatureDefinition bindings changed during Dataset assembly"
                )
            manifest_artifact = uow.research_artifacts.require_exact(
                definition.manifest_artifact,
                lock=True,
            )
            uow.research_artifacts.require_exact(
                definition.code_artifact,
                lock=True,
            )
            uow.research_artifacts.require_exact(
                definition.config_artifact,
                lock=True,
            )
            expected_population = uow.source_queries.expected_population(
                universe_revision_id=definition.universe_revision_id,
                eligibility_policy_id=definition.eligibility_policy_id,
                decision_time=definition.decision_time,
                lock=True,
            )
            validate_population(manifest, expected_population)
            observations = uow.source_queries.market_source_observations(
                manifest.sources,
                lock=True,
            )
            validate_market_lineage(
                manifest,
                features=features,
                observations=observations,
            )
            uow.research_artifacts.record_verification(
                verification_id=self._id_factory(),
                receipt_id=receipt.receipt_id,
                artifact=manifest_artifact,
                verifier_id="research-dataset-manifest-parser",
                policy="RESEARCH_DATASET_MANIFEST_READ",
                verification=verification,
            )
            version = uow.research_definitions.insert_dataset(
                definition,
                manifest,
            )
            persisted = uow.research_definitions.dataset_record(
                definition.dataset_id,
                lock=False,
            )
            if persisted.content_sha256 != str(definition.content_sha256):
                raise ArtifactIntegrityError(
                    "persisted Dataset content identity does not reconcile"
                )
            persisted_sources = uow.research_definitions.dataset_sources(
                definition.dataset_id,
                lock=False,
            )
            if persisted_sources != manifest.sources:
                raise ArtifactIntegrityError(
                    "Dataset manifest and PostgreSQL source lineage diverged"
                )
            result_hash = dataset_result_hash(persisted)
            finish_success(
                uow,
                id_factory=self._id_factory,
                receipt_id=receipt.receipt_id,
                aggregate_kind="DATASET",
                aggregate_id=str(definition.dataset_id),
                aggregate_version=version,
                result_hash=result_hash,
                action="REGISTER_DATASET",
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
            return dataset_result(
                persisted,
                receipt_id=receipt.receipt_id,
                result_hash=result_hash,
                replayed=False,
            )


__all__ = ["DatasetCommands"]
