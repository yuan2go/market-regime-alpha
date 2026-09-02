"""Ex-ante Partition/Experiment and canonical Evaluation orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid5

from market_regime_alpha.bootstrap import TargetApplication
from market_regime_alpha.interfaces.wp17p_authorities import Wp17pAuthorityCatalog
from market_regime_alpha.interfaces.wp17p_decisions import Wp17pDecisionExecution
from market_regime_alpha.interfaces.wp17p_operations import Wp17pDatasetAuthority
from market_regime_alpha.interfaces.wp17p_outcomes import Wp17pOutcomeExecution
from market_regime_alpha.research_qualification.domain.evaluation import (
    EvaluationRunPlan,
)
from market_regime_alpha.research_qualification.domain.experiment import (
    ExperimentDefinition,
    ExperimentPartitionBinding,
    ExperimentRunPlan,
)
from market_regime_alpha.research_qualification.domain.partition import (
    ResearchPartitionPlan,
)
from market_regime_alpha.research_qualification.domain.exploratory_backtest import (
    BacktestArmKind,
    BacktestSessionRole,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionOverlapPolicy,
    PartitionPopulationScope,
    PartitionPurpose,
)
from market_regime_alpha.runtime.application import ActorType, CommandContext


@dataclass(frozen=True, slots=True)
class Wp17pOpenEvaluation:
    research_partition_id: UUID
    partition_member_count: int
    partition_content_sha256: str
    experiment_id: UUID
    experiment_partition_id: UUID
    experiment_run_id: UUID
    evaluation_protocol_id: UUID
    evaluation_run_id: UUID
    purpose: PartitionPurpose


@dataclass(frozen=True, slots=True)
class Wp17pCompletedEvaluation:
    evaluation_run_id: UUID
    observation_count: int
    metric_count: int
    input_roster_sha256: str
    metric_roster_sha256: str


class Wp17pEvaluationOperations:
    """Freeze pre-access authority, then acquire and evaluate exact Outcomes."""

    def __init__(self, application: TargetApplication) -> None:
        self._application = application

    def open(
        self,
        *,
        catalog: Wp17pAuthorityCatalog,
        datasets: tuple[Wp17pDatasetAuthority, ...],
        decisions: tuple[Wp17pDecisionExecution, ...],
    ) -> Wp17pOpenEvaluation:
        if not datasets or len(datasets) != len(decisions):
            raise ValueError("Evaluation requires matching Dataset and Decision rosters")
        dataset_by_id = {item.dataset_id: item for item in datasets}
        if (
            len(dataset_by_id) != len(datasets)
            or {item.dataset_id for item in decisions} != set(dataset_by_id)
        ):
            raise ValueError("Evaluation Decisions must bind the exact Dataset roster")
        dataset = datasets[0]
        fold_scope = (
            dataset.backtest_scope.exploratory_backtest_fold_id,
            dataset.backtest_scope.exploratory_backtest_fold_session_id,
            dataset.retrospective_scope.market_archive_id,
            dataset.retrospective_scope.market_archive_seal_id,
            dataset.retrospective_scope.knowledge_cutoff,
            dataset.retrospective_scope.simulated_event_cutoff,
        )
        if any(
            (
                item.backtest_scope.exploratory_backtest_fold_id,
                item.backtest_scope.exploratory_backtest_fold_session_id,
                item.retrospective_scope.market_archive_id,
                item.retrospective_scope.market_archive_seal_id,
                item.retrospective_scope.knowledge_cutoff,
                item.retrospective_scope.simulated_event_cutoff,
            )
            != fold_scope
            for item in datasets
        ):
            raise ValueError("Evaluation Dataset roster crosses a frozen fold/session")
        plan = wp17p_partition_plan(catalog, dataset)
        fold, session = _fold_and_session(catalog, dataset)
        arm_by_id = {
            item.exploratory_backtest_arm_id: item
            for item in catalog.backtest.arms
        }
        dataset_arm_ids = {
            item.backtest_scope.exploratory_backtest_arm_id for item in datasets
        }
        if not dataset_arm_ids.issubset(arm_by_id):
            raise ValueError("Evaluation Dataset arm is not declared")
        expected_arm_ids = (
            {
                item.exploratory_backtest_arm_id
                for item in catalog.backtest.arms
                if item.kind is BacktestArmKind.MODEL_CHALLENGER
            }
            if fold.purpose is PartitionPurpose.FIT
            else set(arm_by_id)
        )
        if dataset_arm_ids != expected_arm_ids:
            raise ValueError("Evaluation Dataset roster omits a predeclared arm")
        expected_role = (
            BacktestSessionRole.FIT_INPUT
            if fold.purpose is PartitionPurpose.FIT
            else BacktestSessionRole.EVALUATION
        )
        if session.role is not expected_role:
            raise ValueError("Evaluation Dataset uses the wrong fold session role")

        app = self._application
        frozen = app.research_partitions.freeze(
            plan,
            _context(f"partition-{fold.ordinal}"),
        )
        _require_matched(
            app.research_evaluation_verifier.verify_partition(
                frozen.research_partition_id
            ),
            "ResearchPartition",
        )
        experiment_id = uuid5(
            catalog.backtest.exploratory_backtest_run_id,
            f"experiment:{fold.exploratory_backtest_fold_id}",
        )
        definition = ExperimentDefinition(
            experiment_id,
            f"wp17p_{fold.purpose.value.lower()}_experiment",
            "Does the frozen WP-17P baseline produce reproducible Target outcomes?",
            "One predeclared rule baseline versus deterministic ridge challenger.",
            "The challenger may differ from the transparent baseline without formal admission.",
            catalog.target.target_definition_id,
            catalog.target.version,
            catalog.target.content_sha256,
            f"{fold.evaluation_protocol_id}:{fold.evaluation_protocol_sha256}",
            "Descriptive exploratory evidence only; negative and not-estimable states retained.",
            catalog.backtest.code_artifact,
            catalog.backtest.config_artifact,
            catalog.backtest.provenance_sha256,
        )
        experiment_partition_id = uuid5(experiment_id, "partition:1")
        binding = ExperimentPartitionBinding(
            experiment_partition_id,
            experiment_id,
            1,
            frozen.research_partition_id,
            catalog.target.target_definition_id,
            catalog.target.version,
            catalog.target.content_sha256,
            fold.purpose,
            frozen.content_sha256,
        )
        app.research_experiments.register(
            definition,
            (binding,),
            _context(f"experiment-{fold.ordinal}"),
        )
        _require_matched(
            app.research_evaluation_verifier.verify_experiment(experiment_id),
            "Experiment",
        )
        experiment_run_id = uuid5(experiment_id, "run:1")
        app.research_experiments.open_run(
            ExperimentRunPlan(
                experiment_run_id,
                experiment_id,
                experiment_partition_id,
                f"wp17p-{fold.purpose.value.lower()}-run-1",
            ),
            _context(f"experiment-run-{fold.ordinal}"),
        )
        protocol = (
            catalog.fit_evaluation_protocol
            if fold.purpose is PartitionPurpose.FIT
            else catalog.validation_evaluation_protocol
        )
        if (
            protocol.evaluation_protocol_id != fold.evaluation_protocol_id
            or protocol.content_sha256 != fold.evaluation_protocol_sha256
        ):
            raise ValueError("fold and EvaluationProtocol differ")
        evaluation_run_id = uuid5(experiment_run_id, "evaluation:1")
        app.research_evaluations.open_run(
            EvaluationRunPlan(
                evaluation_run_id,
                experiment_run_id,
                protocol.evaluation_protocol_id,
                dataset.retrospective_scope.knowledge_cutoff,
                f"wp17p-{fold.purpose.value.lower()}-evaluation-1",
                catalog.backtest.code_artifact,
                catalog.backtest.config_artifact,
                catalog.backtest.provenance_sha256,
            ),
            _context(f"evaluation-open-{fold.ordinal}"),
        )
        _require_matched(
            app.research_evaluation_verifier.verify_evaluation_run(
                evaluation_run_id
            ),
            "open EvaluationRun",
        )
        return Wp17pOpenEvaluation(
            frozen.research_partition_id,
            frozen.member_count,
            frozen.content_sha256,
            experiment_id,
            experiment_partition_id,
            experiment_run_id,
            protocol.evaluation_protocol_id,
            evaluation_run_id,
            fold.purpose,
        )

    def complete(
        self,
        *,
        opened: Wp17pOpenEvaluation,
        outcomes: tuple[Wp17pOutcomeExecution, ...],
    ) -> Wp17pCompletedEvaluation:
        commitment_ids = tuple(
            item.commitment_id
            for execution in outcomes
            for item in execution.outcomes
        )
        if (
            len(commitment_ids) != opened.partition_member_count
            or len(set(commitment_ids)) != len(commitment_ids)
        ):
            raise ValueError("settled Outcome roster differs from frozen Partition")
        acquired = self._application.research_evaluations.acquire_outcome_inputs(
            opened.evaluation_run_id,
            _context(f"evaluation-acquire-{opened.evaluation_run_id}"),
        )
        if acquired.count != opened.partition_member_count:
            raise ValueError("Evaluation observation roster is incomplete")
        completed = self._application.research_evaluations.complete(
            opened.evaluation_run_id,
            _context(f"evaluation-complete-{opened.evaluation_run_id}"),
        )
        _require_matched(
            self._application.research_evaluation_verifier.verify_evaluation_run(
                opened.evaluation_run_id
            ),
            "completed EvaluationRun",
        )
        return Wp17pCompletedEvaluation(
            opened.evaluation_run_id,
            acquired.count,
            completed.count,
            acquired.roster_sha256,
            completed.roster_sha256,
        )


def wp17p_partition_plan(
    catalog: Wp17pAuthorityCatalog,
    dataset: Wp17pDatasetAuthority,
) -> ResearchPartitionPlan:
    fold, session = _fold_and_session(catalog, dataset)
    if fold.purpose not in {PartitionPurpose.FIT, PartitionPurpose.VALIDATION}:
        raise ValueError("WP-17P v1 evaluates only FIT and VALIDATION folds")
    return ResearchPartitionPlan(
        uuid5(
            catalog.backtest.exploratory_backtest_run_id,
            f"partition:{fold.exploratory_backtest_fold_id}",
        ),
        f"wp17p_{fold.purpose.value.lower()}_partition",
        catalog.target.target_definition_id,
        catalog.target.version,
        catalog.target.content_sha256,
        fold.purpose,
        PartitionPopulationScope.ALL_COMMITMENTS,
        PartitionOverlapPolicy.PURGED_WALK_FORWARD,
        fold.exchange_code,
        session.trading_session_id,
        session.trading_session_id,
        fold.purge_sessions,
        0,
        fold.embargo_sessions,
        "wp17p_pilot",
        fold.ordinal,
        catalog.backtest.code_artifact,
        catalog.backtest.config_artifact,
        catalog.backtest.provenance_sha256,
    )


def _fold_and_session(catalog, dataset):
    matches = tuple(
        (fold, session)
        for fold in catalog.backtest.folds
        for session in fold.sessions
        if (
            fold.exploratory_backtest_fold_id
            == dataset.backtest_scope.exploratory_backtest_fold_id
            and session.exploratory_backtest_fold_session_id
            == dataset.backtest_scope.exploratory_backtest_fold_session_id
        )
    )
    if len(matches) != 1:
        raise ValueError("Dataset fold/session is absent or ambiguous")
    return matches[0]


def _require_matched(report, label: str) -> None:
    if not report.matched or report.mismatch_count:
        raise ValueError(f"{label} Authority did not reconcile")


def _context(suffix: str) -> CommandContext:
    return CommandContext(
        idempotency_key=f"wp17p:{suffix}",
        actor_type=ActorType.OPERATOR,
        actor_id="wp17p-pilot-operator",
        reason_code="WP17P_EXPLORATORY_PILOT",
    )


__all__ = [
    "Wp17pCompletedEvaluation",
    "Wp17pEvaluationOperations",
    "Wp17pOpenEvaluation",
    "wp17p_partition_plan",
]
