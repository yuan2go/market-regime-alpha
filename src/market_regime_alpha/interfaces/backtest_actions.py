"""Permanent canonical step composition for generic Backtest execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from market_regime_alpha.decision_support.application import (
    ContextCommands,
    DecisionSupportApplication,
    InferenceCommands,
    ModelForecastCommands,
    OpportunityCommands,
    PortfolioCommands,
    RiskCommands,
)
from market_regime_alpha.decision_support.domain import (
    ExploratoryRetrospectiveDecisionScope,
    OpenDecisionRunRequest,
    RequestedDecisionTarget,
    ResearchPurpose,
)
from market_regime_alpha.research_qualification.application.service import (
    ResearchQualificationApplication,
)
from market_regime_alpha.research_qualification.application.backtests import (
    BacktestApplication,
)
from market_regime_alpha.research_qualification.application.evaluations import (
    EvaluationCommands,
)
from market_regime_alpha.research_qualification.application.experiments import (
    ExperimentCommands,
)
from market_regime_alpha.research_qualification.application.partitions import (
    ResearchPartitionCommands,
)
from market_regime_alpha.research_qualification.application.research_models import (
    RegisterModelVersionRequest,
    ResearchModelApplication,
)
from market_regime_alpha.research_qualification.domain.backtest import (
    BacktestArmSpecification,
    BacktestEvaluationRequirement,
    BacktestEvaluationScopeKind,
    BacktestExecutionKind,
    BacktestFoldSession,
    BacktestModelTrainingRequirement,
    BacktestSessionRole,
    BacktestSpecification,
)
from market_regime_alpha.research_qualification.domain.backtest_dataset import (
    BacktestDatasetMember,
    materialize_backtest_dataset,
)
from market_regime_alpha.research_qualification.domain.backtest_outcome import (
    BacktestOutcomeCheckpoint,
    BacktestSessionWindow,
    resolve_backtest_outcome_cutoff,
)
from market_regime_alpha.research_qualification.domain.backtest_execution import (
    BacktestActionKind,
    BacktestEvaluationExecution,
    BacktestExpectedAction,
    BacktestModelLineage,
)
from market_regime_alpha.research_qualification.domain.evaluation import (
    EvaluationRunPlan,
)
from market_regime_alpha.research_qualification.domain.experiment import (
    ExperimentDefinition,
    ExperimentPartitionBinding,
    ExperimentRunPlan,
)
from market_regime_alpha.research_qualification.domain.exploratory import (
    ExploratoryRetrospectiveDatasetScope,
)
from market_regime_alpha.research_qualification.domain.exploratory_backtest import (
    ExploratoryBacktestDatasetScope,
)
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.partition import (
    BacktestPartitionSource,
    ResearchPartitionPlan,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionOverlapPolicy,
    PartitionPopulationScope,
    PartitionPurpose,
)
from market_regime_alpha.research_qualification.ports.backtest_actions import (
    BacktestActionReadPort,
    BacktestFeatureMaterializer,
    BacktestFeatureRequest,
    BacktestModelAdapter,
    BacktestTradingSession,
)
from market_regime_alpha.research_qualification.ports.backtest_runtime import (
    BacktestRuntimeStep,
)
from market_regime_alpha.runtime.application import (
    ActorType,
    ArtifactApplication,
    CommandContext,
    RuntimeApplication,
)
from market_regime_alpha.runtime.domain import ExternalEffectClass
from market_regime_alpha.runtime.ports import ArtifactRecord, AttemptClaim
from market_regime_alpha.selection.application import SelectionApplication
from market_regime_alpha.selection.application import CandidateApplication
from market_regime_alpha.selection.domain import (
    ExploratoryRetrospectiveSelectionScope,
    UniverseScopeSpecification,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256, sha256_bytes
from market_regime_alpha.shared.identity import InstrumentId
from market_regime_alpha.outcome.application import (
    OutcomeApplication,
    OutcomeNotDueResult,
    SettleMarketTargetOutcomeRequest,
)


@dataclass(frozen=True, slots=True)
class _EvaluationIdentities:
    partition_id: UUID
    experiment_id: UUID
    experiment_partition_id: UUID
    experiment_run_id: UUID
    evaluation_run_id: UUID
    evaluation_binding_id: UUID


@dataclass(frozen=True, slots=True)
class _ModelIdentities:
    model_training_run_id: UUID
    model_version_id: UUID
    model_lineage_id: UUID


class BacktestCanonicalActionHandler:
    """Closed action/step dispatcher; every mutation stays with its owner."""

    def __init__(
        self,
        *,
        artifacts: ArtifactApplication,
        selection: SelectionApplication,
        research_definitions: ResearchQualificationApplication,
        reads: BacktestActionReadPort,
        feature_materializers: tuple[BacktestFeatureMaterializer, ...],
        worker_id: str,
        candidates: CandidateApplication | None = None,
        decision_support: DecisionSupportApplication | None = None,
        decision_contexts: ContextCommands | None = None,
        decision_inference: InferenceCommands | None = None,
        decision_model_forecasts: ModelForecastCommands | None = None,
        decision_opportunities: OpportunityCommands | None = None,
        decision_portfolios: PortfolioCommands | None = None,
        decision_risk: RiskCommands | None = None,
        outcomes: OutcomeApplication | None = None,
        research_partitions: ResearchPartitionCommands | None = None,
        research_experiments: ExperimentCommands | None = None,
        research_evaluations: EvaluationCommands | None = None,
        research_models: ResearchModelApplication | None = None,
        model_adapters: tuple[BacktestModelAdapter, ...] = (),
        backtests: BacktestApplication | None = None,
        runtime: RuntimeApplication | None = None,
    ) -> None:
        if not feature_materializers:
            raise ValueError("Backtest execution requires explicit Feature adapters")
        if not worker_id:
            raise ValueError("Backtest action worker_id is required")
        self._artifacts = artifacts
        self._selection = selection
        self._research_definitions = research_definitions
        self._reads = reads
        self._feature_materializers = feature_materializers
        self._worker_id = worker_id
        self._candidates = candidates
        self._decision_support = decision_support
        self._decision_contexts = decision_contexts
        self._decision_inference = decision_inference
        self._decision_model_forecasts = decision_model_forecasts
        self._decision_opportunities = decision_opportunities
        self._decision_portfolios = decision_portfolios
        self._decision_risk = decision_risk
        self._outcomes = outcomes
        self._research_partitions = research_partitions
        self._research_experiments = research_experiments
        self._research_evaluations = research_evaluations
        self._research_models = research_models
        self._model_adapters = model_adapters
        self._backtests = backtests
        self._runtime = runtime

    def requested_at(
        self,
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
    ) -> datetime:
        del action
        return self._reads.archive_seal(specification).knowledge_cutoff

    def decision_time(
        self,
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
    ) -> datetime | None:
        if action.fold_session_id is None:
            return None
        fold_session = self._fold_session(specification, action)
        session = self._reads.trading_session(specification, fold_session.trading_session_id)
        if session.session_date != fold_session.session_date:
            raise ValueError("Backtest Session date differs from specification")
        references = tuple(item for item in self._reads.target_checkpoints(specification) if item.role == "DECISION_REFERENCE")
        if len(references) != 1 or references[0].session_offset != 0:
            raise ValueError("Backtest Target requires one Decision reference")
        reference = references[0]
        cutoff = datetime.combine(
            session.session_date,
            reference.local_time,
            ZoneInfo(reference.timezone_name),
        ).astimezone(UTC)
        if not session.open_at < cutoff <= session.close_at:
            raise ValueError("Backtest DecisionTime is outside the frozen Session")
        return cutoff

    def steps(
        self,
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
    ) -> tuple[BacktestRuntimeStep, ...]:
        if action.kind is BacktestActionKind.MATERIALIZE_DATASET:
            return tuple(
                BacktestRuntimeStep(
                    key,
                    kind,
                    canonical_json_sha256(
                        {
                            "action_content_sha256": str(action.content_sha256),
                            "specification_sha256": str(specification.content_sha256),
                            "step_key": key,
                        }
                    ),
                    external_effect,
                )
                for key, kind, external_effect in (
                    (
                        "freeze-universe",
                        "FREEZE_UNIVERSE",
                        ExternalEffectClass.CONTENT_PUT,
                    ),
                    (
                        "assess-eligibility",
                        "ASSESS_ELIGIBILITY",
                        ExternalEffectClass.PURE_READ,
                    ),
                    (
                        "register-dataset",
                        "REGISTER_DATASET",
                        ExternalEffectClass.CONTENT_PUT,
                    ),
                )
            )
        if action.kind is BacktestActionKind.GENERATE_DECISION_SUPPORT:
            fold = self._fold(specification, action)
            step_roster = [
                ("build-candidate-set", "BUILD_CANDIDATE_SET"),
                ("open-decision-run", "OPEN_DECISION_RUN"),
                ("assess-context", "ASSESS_CONTEXT"),
            ]
            if fold.purpose is PartitionPurpose.VALIDATION:
                step_roster.extend(
                    (
                        ("signal-and-forecast", "SIGNAL_AND_FORECAST"),
                        ("decide-and-risk", "DECIDE_AND_RISK"),
                    )
                )
            return tuple(
                BacktestRuntimeStep(
                    key,
                    kind,
                    canonical_json_sha256(
                        {
                            "action_content_sha256": str(action.content_sha256),
                            "specification_sha256": str(specification.content_sha256),
                            "step_key": key,
                        }
                    ),
                    ExternalEffectClass.PURE_READ,
                )
                for key, kind in step_roster
            )
        if action.kind is BacktestActionKind.SETTLE_OUTCOME:
            commitment_ids = self._commitment_ids(specification, action)
            roster = (
                tuple((f"settle-{commitment_id.hex}", "SETTLE_OUTCOME") for commitment_id in commitment_ids)
                if commitment_ids
                else (("record-empty-outcome-roster", "RECORD_EVIDENCE"),)
            )
            return tuple(
                BacktestRuntimeStep(
                    key,
                    kind,
                    canonical_json_sha256(
                        {
                            "action_content_sha256": str(action.content_sha256),
                            "commitment_ids": commitment_ids,
                            "specification_sha256": str(specification.content_sha256),
                            "step_key": key,
                        }
                    ),
                    ExternalEffectClass.NONE,
                )
                for key, kind in roster
            )
        if action.kind is BacktestActionKind.TRAIN_MODEL:
            return tuple(
                BacktestRuntimeStep(
                    key,
                    kind,
                    canonical_json_sha256(
                        {
                            "action_content_sha256": str(action.content_sha256),
                            "specification_sha256": str(specification.content_sha256),
                            "step_key": key,
                        }
                    ),
                    external_effect,
                )
                for key, kind, external_effect in (
                    (
                        "open-model-training",
                        "OPEN_MODEL_TRAINING_RUN",
                        ExternalEffectClass.CONTENT_PUT,
                    ),
                    (
                        "register-model-version",
                        "REGISTER_MODEL_VERSION",
                        ExternalEffectClass.CONTENT_PUT,
                    ),
                    (
                        "bind-model-lineage",
                        "RECORD_EVIDENCE",
                        ExternalEffectClass.NONE,
                    ),
                )
            )
        if action.kind in {
            BacktestActionKind.COMPLETE_FOLD_EVALUATION,
            BacktestActionKind.COMPLETE_AGGREGATE_EVALUATION,
        }:
            return tuple(
                BacktestRuntimeStep(
                    key,
                    kind,
                    canonical_json_sha256(
                        {
                            "action_content_sha256": str(action.content_sha256),
                            "specification_sha256": str(specification.content_sha256),
                            "step_key": key,
                        }
                    ),
                    ExternalEffectClass.NONE,
                )
                for key, kind in (
                    ("freeze-partition", "FREEZE_PARTITION"),
                    ("register-experiment", "REGISTER_EXPERIMENT"),
                    ("open-experiment-run", "OPEN_EXPERIMENT_RUN"),
                    ("open-evaluation", "OPEN_EVALUATION"),
                    ("acquire-outcome-inputs", "ACQUIRE_OUTCOME_INPUTS"),
                    ("evaluate", "EVALUATE"),
                    ("bind-evaluation", "RECORD_EVIDENCE"),
                )
            )
        raise ValueError(f"Backtest action kind is not yet composed: {action.kind}")

    def execute_step(
        self,
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
        claim: AttemptClaim,
    ) -> None:
        if action.kind is BacktestActionKind.MATERIALIZE_DATASET:
            if claim.step_key == "freeze-universe":
                self._freeze_universe(specification, action, claim)
            elif claim.step_key == "assess-eligibility":
                self._assess_eligibility(specification, action, claim)
            elif claim.step_key == "register-dataset":
                self._register_dataset(specification, action, claim)
            else:
                raise ValueError(f"unsupported Dataset step {claim.step_key}")
        elif action.kind is BacktestActionKind.GENERATE_DECISION_SUPPORT:
            self._execute_decision_step(specification, action, claim)
        elif action.kind is BacktestActionKind.SETTLE_OUTCOME:
            self._execute_outcome_step(specification, action, claim)
        elif action.kind is BacktestActionKind.TRAIN_MODEL:
            self._execute_model_step(specification, action, claim)
        elif action.kind in {
            BacktestActionKind.COMPLETE_FOLD_EVALUATION,
            BacktestActionKind.COMPLETE_AGGREGATE_EVALUATION,
        }:
            self._execute_evaluation_step(specification, action, claim)
        else:
            raise ValueError(f"unsupported Backtest action {action.kind}")

    def _execute_model_step(
        self,
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
        claim: AttemptClaim,
    ) -> None:
        if self._research_models is None or self._backtests is None or not self._model_adapters:
            raise ValueError("Backtest Model owner Applications are not composed")
        requirement = self._model_training_requirement(specification, action)
        if requirement.recipe is None:  # pragma: no cover - domain invariant
            raise ValueError("current Backtest Model recipe is missing")
        adapters = tuple(item for item in self._model_adapters if item.supports(requirement.recipe))
        if len(adapters) != 1:
            raise ValueError("Backtest Model recipe requires exactly one concrete adapter")
        identities = _model_identities(action)
        fit_evaluation = self._reads.fit_evaluation_execution(
            exploratory_backtest_run_id=(specification.exploratory_backtest_run_id),
            specification_sha256=specification.content_sha256,
            model_training_requirement_id=requirement.requirement_id,
        )
        context = self._context(action, claim.step_key)
        if claim.step_key == "open-model-training":
            self._research_models.open_reproducible_training_run(
                adapters[0].training_request(
                    specification=specification,
                    requirement=requirement,
                    fit_evaluation=fit_evaluation,
                    model_training_run_id=identities.model_training_run_id,
                ),
                context,
                runtime_claim=claim,
            )
            return
        if requirement.planned_model_version is None:  # pragma: no cover
            raise ValueError("current Model requirement lacks planned version")
        if claim.step_key == "register-model-version":
            self._research_models.fit_and_register_reproducible_version(
                RegisterModelVersionRequest(
                    model_version_id=identities.model_version_id,
                    model_id=requirement.model_definition.authority_id,
                    version=requirement.planned_model_version,
                    model_training_run_id=identities.model_training_run_id,
                    provenance_sha256=str(specification.provenance_sha256),
                ),
                context,
                runtime_claim=claim,
            )
            return
        if claim.step_key == "bind-model-lineage":
            result = self._reads.model_execution_result(
                model_training_run_id=identities.model_training_run_id,
                model_version_id=identities.model_version_id,
            )
            if result.model_id != requirement.model_definition.authority_id:
                raise ValueError("Backtest trained Model differs from requirement")
            self._backtests.bind_model_lineage(
                BacktestModelLineage(
                    backtest_model_lineage_id=identities.model_lineage_id,
                    exploratory_backtest_run_id=(specification.exploratory_backtest_run_id),
                    specification_sha256=specification.content_sha256,
                    model_training_requirement_id=requirement.requirement_id,
                    backtest_evaluation_execution_id=(fit_evaluation.backtest_evaluation_execution_id),
                    fit_evaluation_run_id=fit_evaluation.evaluation_run_id,
                    model_id=result.model_id,
                    model_training_run_id=result.model_training_run_id,
                    model_training_run_sha256=(result.model_training_run_sha256),
                    model_training_reproducibility_sha256=(result.model_training_reproducibility_sha256),
                    model_version_id=result.model_version_id,
                    model_version_sha256=result.model_version_sha256,
                ),
                context,
                runtime_claim=claim,
            )
            return
        raise ValueError(f"unsupported Model step {claim.step_key}")

    @staticmethod
    def _model_training_requirement(
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
    ) -> BacktestModelTrainingRequirement:
        if action.model_training_requirement_id is None:
            raise ValueError("Backtest Model action lacks exact requirement")
        matches = tuple(
            item for item in specification.model_training_requirements if item.requirement_id == action.model_training_requirement_id
        )
        if len(matches) != 1:
            raise ValueError("Backtest Model requirement is absent or ambiguous")
        requirement = matches[0]
        if requirement.model_arm_id != action.arm_id or requirement.fit_fold_id != action.fold_id:
            raise ValueError("Backtest Model action scope differs")
        return requirement

    def _execute_evaluation_step(
        self,
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
        claim: AttemptClaim,
    ) -> None:
        self._require_evaluation_composition()
        requirement = self._evaluation_requirement(specification, action)
        identities = _evaluation_identities(action)
        context = self._context(action, claim.step_key)
        assert self._research_partitions is not None
        assert self._research_experiments is not None
        assert self._research_evaluations is not None
        assert self._backtests is not None
        if claim.step_key == "freeze-partition":
            self._research_partitions.freeze(
                self._partition_plan(
                    specification,
                    action,
                    requirement,
                    identities.partition_id,
                ),
                context,
                runtime_claim=claim,
            )
            return
        partition = self._reads.partition_execution(identities.partition_id)
        expected_purpose = self._evaluation_purpose(specification, requirement)
        if partition.purpose != expected_purpose.value:
            raise ValueError("Backtest Evaluation Partition purpose differs")
        binding = ExperimentPartitionBinding(
            experiment_partition_id=identities.experiment_partition_id,
            experiment_id=identities.experiment_id,
            binding_ordinal=1,
            research_partition_id=identities.partition_id,
            target_definition_id=specification.target.authority_id,
            target_version=specification.target.version,
            target_definition_sha256=specification.target.content_sha256,
            purpose=expected_purpose,
            partition_content_sha256=partition.content_sha256,
        )
        if claim.step_key == "register-experiment":
            self._research_experiments.register(
                ExperimentDefinition(
                    experiment_id=identities.experiment_id,
                    experiment_code=f"backtest-{action.action_id.hex}",
                    research_question=specification.hypothesis,
                    primary_change=(f"evaluate frozen arm {requirement.arm_id} at {requirement.scope_kind.value} scope"),
                    hypothesis=specification.hypothesis,
                    target_definition_id=specification.target.authority_id,
                    target_version=specification.target.version,
                    target_definition_sha256=specification.target.content_sha256,
                    protocol_identity=(f"evaluation-protocol:{requirement.evaluation_protocol.authority_id}"),
                    acceptance_semantics=("Frozen EvaluationProtocol metrics are the sole acceptance and NOT_ESTIMABLE Authority."),
                    code_artifact=specification.code_artifact,
                    config_artifact=specification.config_artifact,
                    provenance_sha256=specification.provenance_sha256,
                ),
                (binding,),
                context,
                runtime_claim=claim,
            )
            return
        if claim.step_key == "open-experiment-run":
            self._research_experiments.open_run(
                ExperimentRunPlan(
                    experiment_run_id=identities.experiment_run_id,
                    experiment_id=identities.experiment_id,
                    experiment_partition_id=identities.experiment_partition_id,
                    run_identity=f"backtest:{action.action_id}",
                ),
                context,
                runtime_claim=claim,
            )
            return
        if claim.step_key == "open-evaluation":
            self._research_evaluations.open_run(
                EvaluationRunPlan(
                    evaluation_run_id=identities.evaluation_run_id,
                    experiment_run_id=identities.experiment_run_id,
                    evaluation_protocol_id=(requirement.evaluation_protocol.authority_id),
                    requested_knowledge_cutoff=(self._reads.archive_seal(specification).knowledge_cutoff),
                    request_identity=f"backtest:{action.action_id}",
                    code_artifact=specification.code_artifact,
                    config_artifact=specification.config_artifact,
                    provenance_sha256=specification.provenance_sha256,
                ),
                context,
                runtime_claim=claim,
            )
            return
        if claim.step_key == "acquire-outcome-inputs":
            self._research_evaluations.acquire_outcome_inputs(
                identities.evaluation_run_id,
                context,
                runtime_claim=claim,
            )
            return
        if claim.step_key == "evaluate":
            self._research_evaluations.complete(
                identities.evaluation_run_id,
                context,
                runtime_claim=claim,
            )
            return
        if claim.step_key == "bind-evaluation":
            result = self._reads.evaluation_result(identities.evaluation_run_id)
            if result.evaluation_protocol_id != requirement.evaluation_protocol.authority_id:
                raise ValueError("Backtest Evaluation Protocol lineage differs")
            self._backtests.bind_evaluation(
                BacktestEvaluationExecution(
                    backtest_evaluation_execution_id=(identities.evaluation_binding_id),
                    exploratory_backtest_run_id=(specification.exploratory_backtest_run_id),
                    specification_sha256=specification.content_sha256,
                    backtest_evaluation_requirement_id=(requirement.requirement_id),
                    evaluation_run_id=result.evaluation_run_id,
                    evaluation_protocol_id=result.evaluation_protocol_id,
                    evaluation_metric_count=result.metric_count,
                    evaluation_metric_roster_sha256=(result.metric_roster_sha256),
                    canonical_completed_at=result.completed_at,
                ),
                context,
                runtime_claim=claim,
            )
            return
        raise ValueError(f"unsupported Evaluation step {claim.step_key}")

    def _partition_plan(
        self,
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
        requirement: BacktestEvaluationRequirement,
        partition_id: UUID,
    ) -> ResearchPartitionPlan:
        sessions = self._evaluation_sessions(specification, requirement)
        if not sessions:
            raise ValueError("Backtest Evaluation scope has no frozen Sessions")
        first = min(sessions, key=lambda item: item.session_date)
        last = max(sessions, key=lambda item: item.session_date)
        purpose = self._evaluation_purpose(specification, requirement)
        fold = (
            None
            if requirement.fold_id is None
            else next(item for item in specification.folds if item.exploratory_backtest_fold_id == requirement.fold_id)
        )
        return ResearchPartitionPlan(
            research_partition_id=partition_id,
            partition_code=f"backtest-{action.action_id.hex}",
            target_definition_id=specification.target.authority_id,
            target_version=specification.target.version,
            target_definition_sha256=specification.target.content_sha256,
            purpose=purpose,
            population_scope=PartitionPopulationScope.ALL_COMMITMENTS,
            overlap_policy=PartitionOverlapPolicy.PURGED_WALK_FORWARD,
            exchange_code=specification.exchange_code,
            decision_start_session_id=first.trading_session_id,
            decision_end_session_id=last.trading_session_id,
            purge_before_sessions=(0 if fold is None else fold.purge_sessions),
            purge_after_sessions=0,
            embargo_sessions=(0 if fold is None else fold.embargo_sessions),
            series_code=f"backtest-{action.action_id.hex}",
            fold_ordinal=(requirement.ordinal if fold is None else fold.ordinal),
            code_artifact=specification.code_artifact,
            config_artifact=specification.config_artifact,
            provenance_sha256=specification.provenance_sha256,
            backtest_source=BacktestPartitionSource(
                exploratory_backtest_run_id=(specification.exploratory_backtest_run_id),
                exploratory_backtest_arm_id=self._required_arm_id(requirement),
                exploratory_backtest_fold_id=requirement.fold_id,
            ),
        )

    @staticmethod
    def _required_arm_id(requirement: BacktestEvaluationRequirement) -> UUID:
        if requirement.arm_id is None:  # pragma: no cover - domain invariant
            raise ValueError("Backtest Evaluation requires an exact Arm")
        return requirement.arm_id

    @staticmethod
    def _evaluation_requirement(
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
    ) -> BacktestEvaluationRequirement:
        if action.evaluation_requirement_id is None:
            raise ValueError("current Backtest Evaluation action lacks requirement")
        matches = tuple(item for item in specification.evaluation_requirements if item.requirement_id == action.evaluation_requirement_id)
        if len(matches) != 1:
            raise ValueError("Backtest Evaluation requirement is absent or ambiguous")
        requirement = matches[0]
        if requirement.arm_id != action.arm_id or requirement.fold_id != action.fold_id:
            raise ValueError("Backtest Evaluation action scope differs")
        return requirement

    @staticmethod
    def _evaluation_purpose(
        specification: BacktestSpecification,
        requirement: BacktestEvaluationRequirement,
    ) -> PartitionPurpose:
        if requirement.fold_id is None:
            return PartitionPurpose.VALIDATION
        return next(item.purpose for item in specification.folds if item.exploratory_backtest_fold_id == requirement.fold_id)

    def _evaluation_sessions(
        self,
        specification: BacktestSpecification,
        requirement: BacktestEvaluationRequirement,
    ) -> tuple[BacktestFoldSession, ...]:
        participating_folds = {item.fold_id for item in specification.arm_folds if item.arm_id == requirement.arm_id}
        if requirement.fold_id is not None:
            folds = tuple(item for item in specification.folds if item.exploratory_backtest_fold_id == requirement.fold_id)
        else:
            folds = tuple(
                item
                for item in specification.folds
                if item.exploratory_backtest_fold_id in participating_folds and item.purpose is PartitionPurpose.VALIDATION
            )
        sessions = tuple(
            session
            for fold in folds
            for session in fold.sessions
            if session.role is (BacktestSessionRole.FIT_INPUT if fold.purpose is PartitionPurpose.FIT else BacktestSessionRole.EVALUATION)
        )
        if requirement.scope_kind is BacktestEvaluationScopeKind.MONTH:
            year, month = _parse_month(requirement.slice_key)
            sessions = tuple(item for item in sessions if (item.session_date.year, item.session_date.month) == (year, month))
        elif requirement.scope_kind is BacktestEvaluationScopeKind.QUARTER:
            year, quarter = _parse_quarter(requirement.slice_key)
            sessions = tuple(
                item for item in sessions if item.session_date.year == year and (item.session_date.month - 1) // 3 + 1 == quarter
            )
        return sessions

    def _require_evaluation_composition(self) -> None:
        if any(
            item is None
            for item in (
                self._research_partitions,
                self._research_experiments,
                self._research_evaluations,
                self._backtests,
            )
        ):
            raise ValueError("Backtest Evaluation owner Applications are not composed")

    def _execute_outcome_step(
        self,
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
        claim: AttemptClaim,
    ) -> None:
        commitment_ids = self._commitment_ids(specification, action)
        if not commitment_ids:
            if claim.step_key != "record-empty-outcome-roster":
                raise ValueError("Backtest empty Outcome roster Step differs")
            if self._runtime is None:
                raise ValueError("Backtest empty Outcome roster requires Runtime")
            self._runtime.succeed_attempt(
                claim,
                result_hash=canonical_json_sha256(
                    {
                        "action_id": action.action_id,
                        "commitment_ids": (),
                        "result": "EMPTY_CANONICAL_ROSTER",
                    }
                ),
                context=self._context(action, "empty-outcome-roster"),
            )
            return
        if self._outcomes is None:
            raise ValueError("Backtest Outcome owner Application is not composed")
        by_step = {f"settle-{commitment_id.hex}": commitment_id for commitment_id in commitment_ids}
        commitment_id = by_step.get(claim.step_key)
        if commitment_id is None:
            raise ValueError("Backtest Outcome Step is outside exact commitment roster")
        observation_cutoff = self._outcome_cutoff(specification, action)
        knowledge_cutoff = self._reads.archive_seal(specification).knowledge_cutoff
        if observation_cutoff >= knowledge_cutoff:
            raise ValueError("Backtest Outcome must predate Archive knowledge cutoff")
        result = self._outcomes.settle_exploratory_retrospective_market_target_outcome(
            SettleMarketTargetOutcomeRequest(
                commitment_id,
                observation_cutoff,
                knowledge_cutoff,
                None,
            ),
            self._context(action, f"outcome-{commitment_id}"),
            runtime_claim=claim,
        )
        if isinstance(result, OutcomeNotDueResult):
            raise ValueError("Backtest retrospective Outcome is unexpectedly NOT_DUE")

    def _commitment_ids(
        self,
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
    ) -> tuple[UUID, ...]:
        if action.arm_id is None or action.fold_id is None or action.fold_session_id is None:
            raise ValueError("Backtest Outcome action lacks exact scope")
        return self._reads.decision_commitment_ids(
            exploratory_backtest_run_id=specification.exploratory_backtest_run_id,
            arm_id=action.arm_id,
            fold_id=action.fold_id,
            fold_session_id=action.fold_session_id,
            target_definition_id=specification.target.authority_id,
        )

    def _outcome_cutoff(
        self,
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
    ) -> datetime:
        reference = self._fold_session(specification, action)
        bindings = tuple((session.trading_session_id, session.session_date) for fold in specification.folds for session in fold.sessions)
        distinct_ids = tuple(dict.fromkeys(session_id for session_id, _ in bindings))
        sessions = tuple(self._reads.trading_session(specification, session_id) for session_id in distinct_ids)
        checkpoints = tuple(
            BacktestOutcomeCheckpoint(
                checkpoint.session_offset,
                checkpoint.local_time,
                checkpoint.timezone_name,
            )
            for checkpoint in self._reads.target_checkpoints(specification)
            if checkpoint.role == "OUTCOME_OBSERVATION"
        )
        return resolve_backtest_outcome_cutoff(
            reference_session_id=reference.trading_session_id,
            fold_session_bindings=bindings,
            checkpoints=checkpoints,
            session_windows=tuple(
                BacktestSessionWindow(
                    session.trading_session_id,
                    session.session_date,
                    session.open_at,
                    session.close_at,
                )
                for session in sessions
            ),
        )

    def _execute_decision_step(
        self,
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
        claim: AttemptClaim,
    ) -> None:
        self._require_decision_composition()
        assert action.arm_id is not None and action.fold_id is not None and action.fold_session_id is not None
        arm = self._arm(specification, action)
        fold = self._fold(specification, action)
        dataset = self._reads.dataset_execution(
            exploratory_backtest_run_id=specification.exploratory_backtest_run_id,
            arm_id=action.arm_id,
            fold_session_id=action.fold_session_id,
        )
        context = self._context(action, claim.step_key)
        assert self._candidates is not None
        assert self._decision_support is not None
        assert self._decision_contexts is not None
        assert self._decision_inference is not None
        assert self._decision_model_forecasts is not None
        assert self._decision_opportunities is not None
        assert self._decision_portfolios is not None
        assert self._decision_risk is not None
        if claim.step_key == "build-candidate-set":
            self._candidates.build_candidate_set(
                arm.candidate.authority_id,
                dataset.dataset_id,
                context,
                runtime_claim=claim,
            )
            return
        candidate_set_id = self._reads.candidate_set_id(
            dataset_id=dataset.dataset_id,
            candidate_policy_id=arm.candidate.authority_id,
        )
        retrospective_scope = ExploratoryRetrospectiveDecisionScope(
            dataset.dataset_id,
            specification.exploratory_backtest_run_id,
            action.arm_id,
            action.fold_id,
            action.fold_session_id,
            dataset.retrospective_scope.market_archive_id,
            dataset.retrospective_scope.market_archive_seal_id,
            dataset.retrospective_scope.knowledge_cutoff,
            dataset.retrospective_scope.simulated_event_cutoff,
        )
        if claim.step_key == "open-decision-run":
            self._decision_support.open_exploratory_retrospective_decision_run(
                OpenDecisionRunRequest(
                    candidate_set_id=candidate_set_id,
                    targets=(
                        RequestedDecisionTarget(
                            specification.target.authority_id,
                            self._reads.universe_template(specification).market_provider_product_id,
                        ),
                    ),
                    research_purpose=(ResearchPurpose.DISCOVERY if fold.purpose is PartitionPurpose.FIT else ResearchPurpose.VALIDATION),
                    research_qualifications=(),
                ),
                retrospective_scope,
                context,
                runtime_claim=claim,
            )
            return
        decision_run_id = self._reads.decision_run_id(dataset_id=dataset.dataset_id)
        if claim.step_key == "assess-context":
            self._decision_contexts.assess_exploratory_retrospective_context(
                decision_run_id,
                arm.context.authority_id,
                retrospective_scope,
                context,
                runtime_claim=claim,
            )
            return
        if fold.purpose is not PartitionPurpose.VALIDATION:
            raise ValueError("FIT Decision does not have validation-only steps")
        model_version_id = self._validation_model_version(specification, action, arm)
        if claim.step_key == "signal-and-forecast":
            if model_version_id is None:
                self._decision_inference.produce(
                    decision_run_id,
                    arm.strategy.authority_id,
                    context,
                    runtime_claim=claim,
                )
            else:
                self._decision_model_forecasts.produce(
                    decision_run_id,
                    arm.strategy.authority_id,
                    model_version_id,
                    context,
                    runtime_claim=claim,
                )
            return
        if claim.step_key == "decide-and-risk":
            opportunities = self._decision_opportunities.create_opportunities(
                decision_run_id,
                arm.strategy.authority_id,
                self._context(action, "opportunities"),
                runtime_claim=claim,
            )
            proposal = self._decision_portfolios.propose(
                opportunities.aggregate_id,
                arm.portfolio.authority_id,
                self._context(action, "portfolio"),
                runtime_claim=claim,
            )
            self._decision_risk.assess(
                proposal.aggregate_id,
                arm.risk.authority_id,
                self._context(action, "risk"),
                runtime_claim=claim,
            )
            return
        raise ValueError(f"unsupported Decision step {claim.step_key}")

    def _validation_model_version(
        self,
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
        arm: BacktestArmSpecification,
    ) -> UUID | None:
        requirements = tuple(
            item
            for item in specification.model_training_requirements
            if item.model_arm_id == action.arm_id and item.validation_fold_id == action.fold_id
        )
        if arm.execution_kind is BacktestExecutionKind.RULE:
            if requirements:
                raise ValueError("RULE Backtest arm cannot have Model lineage")
            return None
        if len(requirements) != 1:
            raise ValueError("MODEL validation requires one exact training dependency")
        requirement = requirements[0]
        return self._reads.model_version_id(
            exploratory_backtest_run_id=specification.exploratory_backtest_run_id,
            model_training_requirement_id=requirement.requirement_id,
        )

    def _require_decision_composition(self) -> None:
        if any(
            item is None
            for item in (
                self._candidates,
                self._decision_support,
                self._decision_contexts,
                self._decision_inference,
                self._decision_model_forecasts,
                self._decision_opportunities,
                self._decision_portfolios,
                self._decision_risk,
            )
        ):
            raise ValueError("Backtest Decision owner Applications are not composed")

    @staticmethod
    def _arm(
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
    ) -> BacktestArmSpecification:
        matches = tuple(item for item in specification.arms if item.exploratory_backtest_arm_id == action.arm_id)
        if len(matches) != 1:
            raise ValueError("Backtest action Arm is absent or ambiguous")
        return matches[0]

    @staticmethod
    def _fold(specification: BacktestSpecification, action: BacktestExpectedAction):
        matches = tuple(item for item in specification.folds if item.exploratory_backtest_fold_id == action.fold_id)
        if len(matches) != 1:
            raise ValueError("Backtest action Fold is absent or ambiguous")
        return matches[0]

    def _freeze_universe(
        self,
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
        claim: AttemptClaim,
    ) -> None:
        template = self._reads.universe_template(specification)
        decision_time = self._required_decision_time(specification, action)
        scope_content = self._scope_content(specification, template)
        artifact = self._artifacts.publish(
            scope_content,
            media_type="application/json",
            context=self._context(action, "universe-scope"),
        )
        scope = UniverseScopeSpecification(
            artifact.artifact_id,
            artifact.content_sha256,
            artifact.size_bytes,
            template.market_provider_product_id,
            template.classification_scheme,
            template.classification_code,
            tuple(
                sorted(
                    (InstrumentId.parse(item.instrument_id) for item in specification.sample_members),
                    key=str,
                )
            ),
        )
        self._selection.freeze_exploratory_retrospective_universe(
            universe_id=template.universe_id,
            scope=scope,
            retrospective_scope=self._selection_scope(specification, decision_time),
            context=self._context(action, "freeze-universe"),
            runtime_claim=claim,
        )

    def _assess_eligibility(
        self,
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
        claim: AttemptClaim,
    ) -> None:
        decision_time = self._required_decision_time(specification, action)
        scope_hash = sha256_bytes(self._scope_content(specification, self._reads.universe_template(specification)))
        universe_revision_id = self._reads.retrospective_universe_id(
            specification=specification,
            decision_time=decision_time,
            scope_content_sha256=scope_hash,
        )
        self._selection.assess_exploratory_retrospective_eligibility(
            universe_revision_id=universe_revision_id,
            eligibility_policy_id=specification.eligibility_policy.authority_id,
            retrospective_scope=self._selection_scope(specification, decision_time),
            context=self._context(action, "assess-eligibility"),
            runtime_claim=claim,
        )

    def _register_dataset(
        self,
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
        claim: AttemptClaim,
    ) -> None:
        assert action.arm_id is not None and action.fold_session_id is not None
        decision_time = self._required_decision_time(specification, action)
        template = self._reads.universe_template(specification)
        universe_revision_id = self._reads.retrospective_universe_id(
            specification=specification,
            decision_time=decision_time,
            scope_content_sha256=sha256_bytes(self._scope_content(specification, template)),
        )
        population = self._reads.eligible_population(
            universe_revision_id=universe_revision_id,
            eligibility_policy_id=specification.eligibility_policy.authority_id,
        )
        session = self._session(specification, action)
        retrospective_scope = ExploratoryRetrospectiveDatasetScope(
            specification.market_archive.authority_id,
            specification.market_archive_seal.authority_id,
            self._reads.archive_seal(specification).knowledge_cutoff,
            decision_time,
        )
        feature_definitions = self._reads.feature_definitions(specification)
        members = tuple(
            BacktestDatasetMember(
                member.instrument_id.value,
                member.universe_member_id,
                member.eligibility_assessment_id,
                tuple(
                    self._feature_materializer(definition).materialize(
                        BacktestFeatureRequest(
                            definition,
                            retrospective_scope,
                            member.instrument_id,
                            session.session_date,
                            session.close_at,
                        )
                    )
                    for definition in feature_definitions
                ),
            )
            for member in population
        )
        dataset_id = uuid5(
            specification.exploratory_backtest_run_id,
            f"dataset:{action.arm_id}:{action.fold_session_id}",
        )
        materialized = materialize_backtest_dataset(
            dataset_id=dataset_id,
            dataset_code=(f"backtest_{str(action.arm_id)[:8]}_{session.session_date:%Y%m%d}"),
            simulated_decision_time=decision_time,
            universe_revision_id=universe_revision_id,
            eligibility_policy_id=specification.eligibility_policy.authority_id,
            feature_definition_ids=tuple(item.feature_definition_id for item in feature_definitions),
            code_artifact=specification.code_artifact,
            config_artifact=specification.config_artifact,
            members=members,
        )
        manifest = self._artifacts.publish(
            materialized.manifest_content,
            media_type="application/json",
            context=self._context(action, "dataset-manifest"),
        )
        assert action.fold_id is not None
        backtest_scope = ExploratoryBacktestDatasetScope(
            retrospective_scope,
            specification.exploratory_backtest_run_id,
            action.arm_id,
            action.fold_id,
            action.fold_session_id,
        )
        self._research_definitions.register_exploratory_backtest_dataset(
            materialized.definition(_artifact(manifest)),
            backtest_scope,
            self._context(action, "register-dataset"),
            runtime_claim=claim,
        )

    def _selection_scope(
        self,
        specification: BacktestSpecification,
        decision_time: datetime,
    ) -> ExploratoryRetrospectiveSelectionScope:
        return ExploratoryRetrospectiveSelectionScope(
            specification.market_archive.authority_id,
            specification.market_archive_seal.authority_id,
            self._reads.archive_seal(specification).knowledge_cutoff,
            decision_time,
        )

    @staticmethod
    def _scope_content(specification, template) -> bytes:
        return json.dumps(
            {
                "classification_code": template.classification_code,
                "classification_scheme": template.classification_scheme,
                "instrument_ids": [
                    str(item.instrument_id)
                    for item in sorted(
                        specification.sample_members,
                        key=lambda member: str(member.instrument_id),
                    )
                ],
                "market_provider_product_id": str(template.market_provider_product_id),
                "schema": "selection-universe-scope-v1",
            },
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    def _feature_materializer(self, definition):
        matches = tuple(item for item in self._feature_materializers if item.supports(definition))
        if len(matches) != 1:
            raise ValueError("FeatureDefinition requires exactly one concrete Backtest adapter")
        return matches[0]

    def _required_decision_time(self, specification, action) -> datetime:
        value = self.decision_time(specification, action)
        if value is None:
            raise ValueError("Backtest Dataset action requires a DecisionTime")
        return value

    def _session(
        self,
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
    ) -> BacktestTradingSession:
        member = self._fold_session(specification, action)
        return self._reads.trading_session(specification, member.trading_session_id)

    @staticmethod
    def _fold_session(
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
    ) -> BacktestFoldSession:
        if action.fold_id is None or action.fold_session_id is None:
            raise ValueError("Backtest action lacks exact Fold/Session")
        matches = tuple(
            member
            for fold in specification.folds
            if fold.exploratory_backtest_fold_id == action.fold_id
            for member in fold.sessions
            if member.exploratory_backtest_fold_session_id == action.fold_session_id
        )
        if len(matches) != 1 or matches[0].role not in {
            BacktestSessionRole.FIT_INPUT,
            BacktestSessionRole.EVALUATION,
        }:
            raise ValueError("Backtest action FoldSession is absent or non-executable")
        return matches[0]

    def _context(
        self,
        action: BacktestExpectedAction,
        suffix: str,
    ) -> CommandContext:
        return CommandContext(
            idempotency_key=f"backtest:{action.action_id}:{suffix}",
            actor_type=ActorType.WORKER,
            actor_id=self._worker_id,
            reason_code="BACKTEST_EXECUTION",
        )


def _artifact(record: ArtifactRecord) -> ArtifactBinding:
    return ArtifactBinding(
        record.artifact_id,
        record.content_sha256,
        record.size_bytes,
    )


def _evaluation_identities(
    action: BacktestExpectedAction,
) -> _EvaluationIdentities:
    return _EvaluationIdentities(
        partition_id=uuid5(action.action_id, "research-partition"),
        experiment_id=uuid5(action.action_id, "experiment"),
        experiment_partition_id=uuid5(action.action_id, "experiment-partition"),
        experiment_run_id=uuid5(action.action_id, "experiment-run"),
        evaluation_run_id=uuid5(action.action_id, "evaluation-run"),
        evaluation_binding_id=uuid5(action.action_id, "evaluation-binding"),
    )


def _model_identities(action: BacktestExpectedAction) -> _ModelIdentities:
    return _ModelIdentities(
        model_training_run_id=uuid5(action.action_id, "model-training-run"),
        model_version_id=uuid5(action.action_id, "model-version"),
        model_lineage_id=uuid5(action.action_id, "model-lineage"),
    )


def _parse_month(value: str | None) -> tuple[int, int]:
    if value is None:
        raise ValueError("MONTH Evaluation requires slice_key")
    try:
        year_text, month_text = value.split("-", maxsplit=1)
        year, month = int(year_text), int(month_text)
    except (TypeError, ValueError) as exc:
        raise ValueError("MONTH slice_key must be YYYY-MM") from exc
    if len(year_text) != 4 or len(month_text) != 2 or not 1 <= month <= 12:
        raise ValueError("MONTH slice_key must be YYYY-MM")
    return year, month


def _parse_quarter(value: str | None) -> tuple[int, int]:
    if value is None:
        raise ValueError("QUARTER Evaluation requires slice_key")
    try:
        year_text, quarter_text = value.split("-Q", maxsplit=1)
        year, quarter = int(year_text), int(quarter_text)
    except (TypeError, ValueError) as exc:
        raise ValueError("QUARTER slice_key must be YYYY-QN") from exc
    if len(year_text) != 4 or quarter not in {1, 2, 3, 4}:
        raise ValueError("QUARTER slice_key must be YYYY-QN")
    return year, quarter


__all__ = ["BacktestCanonicalActionHandler"]
