"""Daily prediction composition on the sole Runtime and canonical owners."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass, fields
from datetime import datetime, timedelta
from decimal import Decimal
import json
import re
from typing import Any, TYPE_CHECKING, Callable
from uuid import UUID, uuid5

from market_regime_alpha.decision_support.domain import OpenDecisionRunRequest, RequestedDecisionTarget, ResearchPurpose
from market_regime_alpha.research_qualification.domain.backtest_dataset import (
    BacktestDatasetFeatureCell,
    BacktestDatasetMember,
    BacktestFeatureLineageKind,
    materialize_backtest_dataset,
)
from market_regime_alpha.research_qualification.domain.daily_inputs import DailyInputState, session_open_close_move
from market_regime_alpha.research_qualification.domain.daily_prediction import DailyPredictionPlan
from market_regime_alpha.research_qualification.domain.daily_protocol import daily_evaluation_protocol
from market_regime_alpha.research_qualification.domain.evaluation import EvaluationRunPlan
from market_regime_alpha.research_qualification.domain.experiment import ExperimentDefinition, ExperimentPartitionBinding, ExperimentRunPlan
from market_regime_alpha.research_qualification.domain.partition import (
    DecisionPartitionSource,
    ResearchPartitionPlan,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionPurpose,
    PartitionPopulationScope,
    PartitionOverlapPolicy,
)
from market_regime_alpha.outcome.application import SettleMarketTargetOutcomeRequest, OutcomeNotDueResult
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.vocabulary import FeatureCellStatus
from market_regime_alpha.research_qualification.ports.daily_prediction import DailyPredictionReads
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.runtime.domain import (
    ExternalEffectClass,
    RetryPolicy,
    RunSpec,
    RuntimeMode,
    ScheduleSpec,
    StepDependency,
    StepSpec,
)
from market_regime_alpha.runtime.errors import ArtifactIntegrityError, RuntimeStateConflictError
from market_regime_alpha.runtime.ports import ArtifactRecord, AttemptClaim, RunTrace
from market_regime_alpha.selection.domain import UniverseScopeSpecification
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import InstrumentId
from market_regime_alpha.shared.time import DecisionTime

if TYPE_CHECKING:
    from market_regime_alpha.bootstrap import TargetApplication


_MODEL_USE_UNAVAILABLE = "MODEL_USE_UNAVAILABLE_FOR_NEW_PREDICTION"
_ABSTENTION_LEASE_DURATION = timedelta(minutes=2)
_ABSTENTION_REASONS = frozenset(
    {
        "MISSED_PUBLICATION_CUTOFF",
        "DATA_READINESS_BUDGET_EXHAUSTED",
        "NO_FEATURE_READY_MEMBERS",
        "POPULATION_EVIDENCE_UNAVAILABLE",
        "MODEL_USE_UNAVAILABLE",
        "PROCESS_DOWNTIME_MISSED_PUBLICATION",
    }
)


def prediction_steps(plan: DailyPredictionPlan) -> tuple[tuple[StepSpec, ...], tuple[StepDependency, ...]]:
    roster = (
        ("freeze-universe", "FREEZE_UNIVERSE"),
        ("assess-eligibility", "ASSESS_ELIGIBILITY"),
        ("register-dataset", "REGISTER_DATASET"),
        ("build-candidate-set", "BUILD_CANDIDATE_SET"),
        ("open-decision-run", "OPEN_DECISION_RUN"),
        ("assess-context", "ASSESS_CONTEXT"),
        ("rule-forecast", "SIGNAL_AND_FORECAST"),
        ("model-forecast", "SIGNAL_AND_FORECAST"),
        ("report", "RECORD_EVIDENCE"),
    )
    steps = tuple(
        StepSpec(
            key,
            kind,
            "research.daily_prediction." + key,
            "1",
            ordinal,
            True,
            canonical_json_sha256({"plan_sha256": plan.content_sha256, "step_key": key}),
            plan.input_content_sha256,
            RetryPolicy(3, (), frozenset()),
            ExternalEffectClass.CONTENT_PUT
            if kind in {"FREEZE_UNIVERSE", "REGISTER_DATASET", "RECORD_EVIDENCE"}
            else ExternalEffectClass.NONE,
        )
        for ordinal, (key, kind) in enumerate(roster, 1)
    )
    return steps, tuple(StepDependency(first.step_key, second.step_key) for first, second in zip(steps, steps[1:]))


class DailyResearchOperations:
    """Bounded step execution; the Runtime owns claims, fences and progress."""

    def __init__(self, app: TargetApplication, reads: DailyPredictionReads, *, before_action: Callable[[], None] = lambda: None) -> None:
        self._app = app
        self._reads = reads
        self._before_action = before_action

    def execute(self, plan: DailyPredictionPlan, *, worker_id: str, maximum_steps: int = 9) -> RunTrace:
        if not worker_id or not 1 <= maximum_steps <= 9:
            raise ValueError("daily execution requires a worker and a bounded step budget")
        self._before_action()
        frozen_content = self._reads.run_plan_content(plan.runtime_run_id)
        if frozen_content is None:
            if not self._reads.model_use_available(plan):
                raise RuntimeStateConflictError(_MODEL_USE_UNAVAILABLE)
        elif frozen_content != encode_daily_plan(plan):
            raise ArtifactIntegrityError("daily Runtime contains another frozen plan")
        ready = self._reads.ready(plan)
        if ready.state not in {"READY", "PARTIAL"}:
            raise RuntimeStateConflictError("daily DataReady refuses prediction: " + ready.state)
        steps, dependencies = prediction_steps(plan)
        schedule_id = uuid5(plan.experimental_model_use_id, "daily-prediction-schedule")
        schedule = ScheduleSpec(
            schedule_id,
            "daily-model-" + plan.experimental_model_use_id.hex,
            1,
            RuntimeMode.SHADOW,
            None,
            "Asia/Shanghai",
            canonical_json_sha256(tuple((item.step_key, item.step_kind, item.implementation) for item in steps)),
            True,
        )
        self._app.runtime.create_schedule(
            schedule,
            CommandContext(
                "daily-schedule:" + str(plan.experimental_model_use_id),
                ActorType.WORKER,
                "daily-model-research",
                "EXPERIMENTAL_DAILY_RESEARCH",
            ),
        )
        config = self._app.artifacts.publish(encode_daily_plan(plan), media_type="application/json", context=_context(plan, "frozen-plan"))
        self._app.runtime.schedule_run(
            RunSpec(
                plan.runtime_run_id,
                schedule_id,
                "daily:" + str(plan.prediction_id),
                RuntimeMode.SHADOW,
                plan.decision_time,
                plan.decision_time,
                plan.code_sha,
                config.artifact_id,
                config.content_sha256,
            ),
            steps,
            dependencies,
            _context(plan, "schedule-run"),
        )
        trace = self._app.runtime.inspect_run(plan.runtime_run_id)
        if trace.run_state == "QUEUED":
            self._app.runtime.start_run(plan.runtime_run_id, _context(plan, "start-run"))
        elif trace.run_state not in {"RUNNING", "SUCCEEDED"}:
            raise RuntimeStateConflictError("daily Run requires explicit recovery: " + trace.run_state)
        self._app.runtime.recover_expired(actor_id=worker_id, reason_code="DAILY_RESTART", run_id=plan.runtime_run_id)
        for _ in range(maximum_steps):
            self._before_action()
            trace = self._app.runtime.inspect_run(plan.runtime_run_id)
            model_step = next(
                item for item in trace.steps if item.step_key == "model-forecast"
            )
            if (
                model_step.state != "SUCCEEDED"
                and not self._reads.model_use_available(plan)
            ):
                return self._stop_unavailable_model_run(
                    plan,
                    trace,
                    worker_id=worker_id,
                )
            pending = next((item for item in trace.steps if item.state == "READY"), None)
            if pending is None:
                break
            claim = self._app.runtime.claim_next(
                run_id=plan.runtime_run_id,
                step_id=pending.step_id,
                worker_id=worker_id,
                lease_duration=timedelta(minutes=5),
                context=_context(plan, "claim:" + pending.step_key + ":" + str(pending.current_fence + 1)),
            )
            if claim is None:
                break
            self._app.runtime.start_attempt(claim, _context(plan, "start:" + str(claim.attempt_id)))
            if pending.step_key != "report" and self._reads.now() >= ready.target_window_start:
                self._app.runtime.fail_attempt(
                    claim,
                    error_class="RESEARCH",
                    error_code="MISSED_PUBLICATION_CUTOFF",
                    context=_context(plan, "missed:" + pending.step_key),
                )
                break
            try:
                self.execute_step(plan, claim)
            except RuntimeStateConflictError as exc:
                unavailable = _MODEL_USE_UNAVAILABLE in str(exc)
                self._fail_live_claim(
                    plan,
                    claim,
                    error_code=(
                        _MODEL_USE_UNAVAILABLE
                        if unavailable
                        else "DAILY_PREDICTION_STEP_FAILED"
                    ),
                )
                if unavailable:
                    break
                raise
            except Exception:
                self._fail_live_claim(
                    plan,
                    claim,
                    error_code="DAILY_PREDICTION_STEP_FAILED",
                )
                raise
        return self._app.runtime.inspect_run(plan.runtime_run_id)

    def _stop_unavailable_model_run(
        self,
        plan: DailyPredictionPlan,
        trace: RunTrace,
        *,
        worker_id: str,
    ) -> RunTrace:
        """Make a revoked/expired pre-publication Run terminal and visible."""

        pending = next((item for item in trace.steps if item.state == "READY"), None)
        if pending is None:
            # A live owner keeps its lease; an already terminal state remains
            # immutable. Expired attempts were recovered before this check.
            return trace
        claim = self._app.runtime.claim_next(
            run_id=plan.runtime_run_id,
            step_id=pending.step_id,
            worker_id=worker_id,
            lease_duration=timedelta(minutes=5),
            context=_context(
                plan,
                "claim-model-unavailable:"
                + pending.step_key
                + ":"
                + str(pending.current_fence + 1),
            ),
        )
        if claim is None:
            return self._app.runtime.inspect_run(plan.runtime_run_id)
        self._app.runtime.start_attempt(
            claim,
            _context(plan, "start-model-unavailable:" + str(claim.attempt_id)),
        )
        self._before_action()
        self._app.runtime.fail_attempt(
            claim,
            error_class="RESEARCH",
            error_code=_MODEL_USE_UNAVAILABLE,
            context=_context(plan, "model-unavailable:" + str(claim.attempt_id)),
        )
        return self._app.runtime.inspect_run(plan.runtime_run_id)

    def _fail_live_claim(
        self,
        plan: DailyPredictionPlan,
        claim: AttemptClaim,
        *,
        error_code: str,
    ) -> None:
        """Terminalize ordinary failures; process termination remains lease recovery."""

        try:
            self._before_action()
            trace = self._app.runtime.inspect_run(claim.run_id)
            step = next(item for item in trace.steps if item.step_id == claim.step_id)
            if (
                step.current_attempt_id == claim.attempt_id
                and step.state in {"CLAIMED", "RUNNING"}
            ):
                self._app.runtime.fail_attempt(
                    claim,
                    error_class="RESEARCH",
                    error_code=error_code,
                    context=_context(plan, "fail:" + str(claim.attempt_id)),
                )
        except (RuntimeError, ValueError, StopIteration):
            # A lost supervisor/fence deliberately leaves recovery to the lease
            # owner. Never replace the original business exception.
            return

    def execute_step(self, plan: DailyPredictionPlan, claim: AttemptClaim) -> None:
        self._before_action()
        if claim.run_id != plan.runtime_run_id:
            raise RuntimeStateConflictError("daily claim belongs to another exact request")
        context = _context(plan, claim.step_key)
        app = self._app
        if claim.step_key == "freeze-universe":
            app.selection.freeze_universe(
                universe_id=plan.universe_id,
                scope=UniverseScopeSpecification(
                    plan.universe_scope.artifact_id,
                    str(plan.universe_scope.content_sha256),
                    plan.universe_scope.size_bytes,
                    plan.provider_product_id,
                    plan.classification_scheme,
                    plan.classification_code,
                    tuple(InstrumentId(item) for item in plan.instrument_ids),
                ),
                decision_time=DecisionTime(plan.decision_time),
                context=context,
                runtime_claim=claim,
            )
        elif claim.step_key == "assess-eligibility":
            app.selection.assess_eligibility(
                universe_revision_id=self._reads.universe_revision(plan),
                eligibility_policy_id=plan.eligibility_policy_id,
                decision_time=DecisionTime(plan.decision_time),
                context=context,
                runtime_claim=claim,
            )
        elif claim.step_key == "register-dataset":
            self._register_dataset(plan, claim)
        elif claim.step_key == "build-candidate-set":
            app.candidates.build_candidate_set(plan.candidate_policy_id, plan.dataset_id, context, runtime_claim=claim)
        elif claim.step_key == "open-decision-run":
            app.decision_support.open_decision_run(
                OpenDecisionRunRequest(
                    self._reads.candidate_set(plan),
                    (RequestedDecisionTarget(plan.target_definition_id, plan.provider_product_id),),
                    ResearchPurpose.DISCOVERY,
                    (),
                ),
                context,
                runtime_claim=claim,
            )
        elif claim.step_key == "assess-context":
            app.decision_contexts.assess_context(self._reads.decision_run(plan), plan.context_policy_id, context, runtime_claim=claim)
        elif claim.step_key == "model-forecast":
            # This read is an early rejection; the Model Forecast repository
            # repeats it while holding the ExperimentalModelUse row lock in the
            # forecast commit transaction, fencing a concurrent revocation.
            if not self._reads.model_use_available(plan):
                raise RuntimeStateConflictError(_MODEL_USE_UNAVAILABLE)
            if not any(member.eligible for member in self._reads.population(plan)):
                # Close the canonical empty Signal/Forecast roster. No model is
                # invoked and no forecast estimate/binding is created.
                app.decision_inference.produce(self._reads.decision_run(plan), plan.strategy_version_id, context, runtime_claim=claim)
            else:
                app.decision_model_forecasts.produce(
                    self._reads.decision_run(plan),
                    plan.strategy_version_id,
                    plan.model_version_id,
                    context,
                    runtime_claim=claim,
                    experimental_model_use_id=plan.experimental_model_use_id,
                )
        elif claim.step_key == "rule-forecast":
            app.decision_inference.produce(self._reads.decision_run(plan), plan.baseline_strategy_version_id, context, runtime_claim=claim)
        elif claim.step_key == "report":
            report = self.report(plan)
            self.schedule_outcomes(plan)
            app.runtime.succeed_attempt(claim, result_hash=canonical_json_sha256(report), context=context)
        else:
            raise ValueError("unknown daily prediction step")

    def _register_dataset(self, plan: DailyPredictionPlan, claim: AttemptClaim) -> None:
        ready = self._reads.ready(plan)
        population = self._reads.population(plan)
        inputs = {item.instrument_id: item for item in ready.members}
        members = []
        for item in population:
            if not item.eligible:
                continue
            source = inputs[item.instrument_id]
            if source.state is DailyInputState.AVAILABLE:
                assert source.bar_revision_id is not None and source.open_value is not None and source.close_value is not None
                cell = BacktestDatasetFeatureCell(
                    plan.feature_definition_id,
                    FeatureCellStatus.AVAILABLE,
                    source.reason_code,
                    BacktestFeatureLineageKind.BAR_REVISION,
                    source.bar_revision_id,
                    session_open_close_move(source.open_value, source.close_value),
                )
            elif source.source_gap_id is not None:
                cell = BacktestDatasetFeatureCell(
                    plan.feature_definition_id,
                    FeatureCellStatus.MISSING,
                    source.reason_code,
                    BacktestFeatureLineageKind.SOURCE_GAP,
                    source.source_gap_id,
                    None,
                )
            else:
                raise RuntimeStateConflictError("daily unavailable member requires canonical SourceGap: " + str(item.instrument_id))
            assert item.eligibility_assessment_id is not None
            members.append(BacktestDatasetMember(item.instrument_id, item.universe_member_id, item.eligibility_assessment_id, (cell,)))
        materialized = materialize_backtest_dataset(
            dataset_id=plan.dataset_id,
            dataset_code="daily_" + plan.dataset_id.hex,
            simulated_decision_time=plan.decision_time,
            universe_revision_id=self._reads.universe_revision(plan),
            eligibility_policy_id=plan.eligibility_policy_id,
            feature_definition_ids=(plan.feature_definition_id,),
            code_artifact=plan.code_artifact,
            config_artifact=plan.config_artifact,
            members=tuple(members),
        )
        manifest = self._app.artifacts.publish(
            materialized.manifest_content, media_type="application/json", context=_context(plan, "dataset-manifest")
        )
        self._before_action()
        self._app.research_definitions.register_dataset(
            materialized.definition(_binding(manifest)), _context(plan, "register-dataset"), runtime_claim=claim
        )

    def report(self, plan: DailyPredictionPlan) -> tuple[ArtifactBinding, ArtifactBinding]:
        verification = self._app.decision_support_verifier.verify(self._reads.decision_run(plan))
        if not verification.matched:
            raise ArtifactIntegrityError("daily report refuses unreconciled Decision Authority")
        projection = self._reads.forecast_projection(plan)
        self._before_action()
        content, markdown = render_daily_report(plan, projection)
        json_artifact = self._app.artifacts.publish(content, media_type="application/json", context=_context(plan, "report-json"))
        markdown_artifact = self._app.artifacts.publish(markdown, media_type="text/markdown", context=_context(plan, "report-markdown"))
        return _binding(json_artifact), _binding(markdown_artifact)

    def abstain(self, plan: DailyPredictionPlan, *, reason: str, worker_id: str) -> dict[str, Any]:
        if reason not in _ABSTENTION_REASONS:
            raise ValueError("daily abstention reason is unsupported")
        self._before_action()
        ready = self._reads.ready(plan)
        run_id = uuid5(plan.prediction_id, "abstention-runtime")
        schedule_id = uuid5(plan.experimental_model_use_id, "daily-abstention-schedule")
        payload = _abstention_payload(plan, ready, reason)
        config = self._app.artifacts.publish(
            encode_daily_plan(plan), media_type="application/json", context=_context(plan, "abstention-plan")
        )
        self._app.runtime.create_schedule(
            ScheduleSpec(
                schedule_id,
                "daily-abstention-" + plan.experimental_model_use_id.hex,
                1,
                RuntimeMode.SHADOW,
                None,
                "Asia/Shanghai",
                canonical_json_sha256("DAILY_ABSTENTION"),
                True,
            ),
            CommandContext(
                "daily-abstention-schedule:" + str(schedule_id), ActorType.WORKER, "daily-model-research", "EXPERIMENTAL_DAILY_RESEARCH"
            ),
        )
        step = StepSpec(
            "abstain",
            "RECORD_EVIDENCE",
            "research.daily_abstention.record",
            "1",
            1,
            True,
            canonical_json_sha256(payload),
            plan.input_content_sha256,
            RetryPolicy(3, (), frozenset()),
            ExternalEffectClass.CONTENT_PUT,
        )
        self._app.runtime.schedule_run(
            RunSpec(
                run_id,
                schedule_id,
                "daily-abstention:" + str(plan.prediction_id),
                RuntimeMode.SHADOW,
                plan.decision_time,
                plan.decision_time,
                plan.code_sha,
                config.artifact_id,
                config.content_sha256,
            ),
            (step,),
            (),
            _context(plan, "abstention-run"),
        )
        trace = self._app.runtime.inspect_run(run_id)
        if trace.run_state == "QUEUED":
            self._app.runtime.start_run(run_id, _context(plan, "abstention-start"))
        self._app.runtime.recover_expired(actor_id=worker_id, reason_code="DAILY_RESTART", run_id=run_id)
        trace = self._app.runtime.inspect_run(run_id)
        pending = trace.steps[0]
        if pending.state == "READY":
            claim = self._app.runtime.claim_next(
                run_id=run_id,
                worker_id=worker_id,
                lease_duration=_ABSTENTION_LEASE_DURATION,
                context=_context(plan, "abstention-claim:" + str(pending.current_fence + 1)),
            )
            if claim is not None:
                self._app.runtime.start_attempt(claim, _context(plan, "abstention-start:" + str(claim.attempt_id)))
                try:
                    self._before_action()
                    artifact = self._app.artifacts.publish(
                        _json(payload),
                        media_type="application/json",
                        context=_context(plan, "abstention-json"),
                    )
                    self._app.runtime.succeed_attempt(
                        claim,
                        result_hash=artifact.content_sha256,
                        context=_context(plan, "abstention-complete"),
                    )
                except Exception:
                    self._fail_live_claim(
                        plan,
                        claim,
                        error_code="DAILY_ABSTENTION_STEP_FAILED",
                    )
                    raise
        runtime = self._app.runtime.inspect_run(run_id)
        state = (
            "ABSTAINED"
            if runtime.run_state == "SUCCEEDED"
            else "ABSTENTION_RECOVERY_REQUIRED"
            if runtime.run_state in {"FAILED", "WAITING", "CANCELLED"}
            else "ABSTENTION_PROGRESS"
        )
        return {
            "state": state,
            "reason_code": reason,
            "prediction_id": plan.prediction_id,
            "runtime": runtime,
        }

    def frozen_abstention_reason(self, plan: DailyPredictionPlan) -> str:
        """Recover the exact reason from the immutable Step request identity."""

        run_id = uuid5(plan.prediction_id, "abstention-runtime")
        trace = self._app.runtime.inspect_run(run_id)
        if len(trace.steps) != 1 or trace.steps[0].step_key != "abstain":
            raise ArtifactIntegrityError("daily abstention Runtime shape changed")
        ready = self._reads.ready(plan)
        matches = tuple(
            reason
            for reason in sorted(_ABSTENTION_REASONS)
            if canonical_json_sha256(_abstention_payload(plan, ready, reason))
            == trace.steps[0].request_hash
        )
        if len(matches) != 1:
            raise ArtifactIntegrityError(
                "daily abstention reason cannot be recovered from frozen identity"
            )
        return matches[0]

    def replay(self, plan: DailyPredictionPlan) -> dict[str, Any]:
        decision = self._app.decision_support_verifier.verify(self._reads.decision_run(plan))
        if not decision.matched:
            raise ArtifactIntegrityError("daily replay refuses unreconciled Decision")
        projection = self._reads.forecast_projection(plan)
        content, markdown = render_daily_report(plan, projection)
        bindings = tuple(
            self._reads.published_report(plan, key, payload) for key, payload in (("report-json", content), ("report-markdown", markdown))
        )
        return {
            "prediction_id": plan.prediction_id,
            "matched": True,
            "mismatch_count": 0,
            "reports": bindings,
            "model_version_id": plan.model_version_id,
            "dataset_id": plan.dataset_id,
            "business_writes": 0,
        }

    def replay_completed_cycle(self, plan: DailyPredictionPlan) -> dict[str, Any]:
        """Verify published prediction and completed Evaluation without writes."""

        prediction = self.replay(plan)
        evaluation_id = uuid5(plan.prediction_id, "evaluation")
        verification = self._app.research_evaluation_verifier.verify_evaluation_run(
            evaluation_id
        )
        if not verification.matched:
            raise ArtifactIntegrityError(
                "daily cycle replay refuses unreconciled Evaluation"
            )
        projection = self._reads.forecast_projection(plan)
        evaluation = self._reads.evaluation_projection(evaluation_id)
        report = self._reads.published_report(
            plan,
            "evaluation-report-json",
            _evaluation_report_content(plan, projection, evaluation),
        )
        return {
            "prediction_id": plan.prediction_id,
            "matched": True,
            "mismatch_count": 0,
            "prediction_reports": prediction["reports"],
            "evaluation_id": evaluation_id,
            "evaluation_report": report,
            "research_dispositions": self._reads.research_dispositions(
                plan.prediction_id
            ),
            "model_version_id": plan.model_version_id,
            "experimental_model_use_id": plan.experimental_model_use_id,
            "business_writes": 0,
        }

    def record_research_disposition(
        self,
        plan: DailyPredictionPlan,
        *,
        review_id: UUID,
        reviewer_id: str,
        disposition: str,
        reason_code: str,
    ) -> ArtifactBinding:
        """Append one human research action without changing Model Governance."""

        if disposition not in {
            "CONTINUE_OBSERVATION",
            "INVESTIGATE",
            "STOP_FUTURE_USE",
            "NO_DECISION",
        }:
            raise ValueError("daily research disposition is unsupported")
        if not reviewer_id or len(reviewer_id) > 100:
            raise ValueError("daily research reviewer identity is invalid")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", reason_code):
            raise ValueError("daily research disposition reason is invalid")
        evaluation_id = uuid5(plan.prediction_id, "evaluation")
        verification = self._app.research_evaluation_verifier.verify_evaluation_run(
            evaluation_id
        )
        if not verification.matched:
            raise ArtifactIntegrityError(
                "daily research disposition refuses unreconciled Evaluation"
            )
        projection = self._reads.forecast_projection(plan)
        evaluation = self._reads.evaluation_projection(evaluation_id)
        report_content = _evaluation_report_content(plan, projection, evaluation)
        report = self._reads.published_report(
            plan, "evaluation-report-json", report_content
        )
        idempotency_key = (
            "daily:"
            + str(plan.prediction_id)
            + ":research-disposition:"
            + str(review_id)
        )
        expected_identity = {
            "schema": "daily-research-disposition-v1",
            "review_id": str(review_id),
            "prediction_id": str(plan.prediction_id),
            "experimental_model_use_id": str(plan.experimental_model_use_id),
            "model_version_id": str(plan.model_version_id),
            "target_definition_id": str(plan.target_definition_id),
            "evaluation_id": str(evaluation_id),
            "evaluation_report": {
                "artifact_id": str(report.artifact_id),
                "content_sha256": {"value": str(report.content_sha256)},
                "size_bytes": report.size_bytes,
            },
            "reviewer_id": reviewer_id,
            "disposition": disposition,
            "reason_code": reason_code,
            "automatic_model_change": False,
            "automatic_qualification_change": False,
        }
        existing = self._reads.published_artifact(idempotency_key)
        if existing is not None:
            binding, content = existing
            value = json.loads(content)
            if not isinstance(value, dict):
                raise ArtifactIntegrityError(
                    "daily research disposition content is not an object"
                )
            actual_identity = {
                key: value.get(key) for key in expected_identity
            }
            if actual_identity != expected_identity or not isinstance(
                value.get("reviewed_at"), str
            ):
                raise ArtifactIntegrityError(
                    "daily research disposition idempotency key was reused"
                )
            return binding
        reviewed_at = self._reads.now()
        payload = {
            "schema": "daily-research-disposition-v1",
            "review_id": review_id,
            "prediction_id": plan.prediction_id,
            "experimental_model_use_id": plan.experimental_model_use_id,
            "model_version_id": plan.model_version_id,
            "target_definition_id": plan.target_definition_id,
            "evaluation_id": evaluation_id,
            "evaluation_report": report,
            "reviewer_id": reviewer_id,
            "reviewed_at": reviewed_at,
            "disposition": disposition,
            "reason_code": reason_code,
            "automatic_model_change": False,
            "automatic_qualification_change": False,
        }
        self._before_action()
        record = self._app.artifacts.publish(
            _json(payload),
            media_type="application/json",
            context=CommandContext(
                idempotency_key,
                ActorType.OPERATOR,
                reviewer_id,
                "DAILY_RESEARCH_DISPOSITION",
            ),
        )
        return _binding(record)

    def schedule_outcomes(self, plan: DailyPredictionPlan) -> UUID | None:
        """Register a durable dependent Runtime Run at publication, not at maturity."""
        self._before_action()
        projection = self._reads.forecast_projection(plan)
        commitments = tuple(
            sorted({row["commitment_id"] for row in projection["predictions"] if row["commitment_id"] is not None}, key=str)
        )
        if not commitments:
            return None
        run_id = uuid5(plan.prediction_id, "outcome-evaluation-runtime")
        schedule_id = uuid5(plan.experimental_model_use_id, "daily-outcome-schedule")
        roster = tuple(("settle-" + item.hex, "SETTLE_OUTCOME") for item in commitments) + (
            ("freeze-partition", "FREEZE_PARTITION"),
            ("register-experiment", "REGISTER_EXPERIMENT"),
            ("open-experiment-run", "OPEN_EXPERIMENT_RUN"),
            ("open-evaluation", "OPEN_EVALUATION"),
            ("acquire-outcome-inputs", "ACQUIRE_OUTCOME_INPUTS"),
            ("evaluate", "EVALUATE"),
            ("evaluation-report", "RECORD_EVIDENCE"),
        )
        steps = tuple(
            StepSpec(
                key,
                kind,
                "research.daily_outcome." + key,
                "1",
                ordinal,
                True,
                canonical_json_sha256({"prediction": plan.content_sha256, "commitments": commitments, "step": key}),
                plan.input_content_sha256,
                RetryPolicy(3, (), frozenset()),
                ExternalEffectClass.NONE,
            )
            for ordinal, (key, kind) in enumerate(roster, 1)
        )
        # A constant catalog describes the step families, not daily roster size.
        schedule = ScheduleSpec(
            schedule_id,
            "daily-outcome-" + plan.experimental_model_use_id.hex,
            1,
            RuntimeMode.SHADOW,
            None,
            "Asia/Shanghai",
            canonical_json_sha256(
                (
                    "SETTLE_OUTCOME",
                    "FREEZE_PARTITION",
                    "REGISTER_EXPERIMENT",
                    "OPEN_EXPERIMENT_RUN",
                    "OPEN_EVALUATION",
                    "ACQUIRE_OUTCOME_INPUTS",
                    "EVALUATE",
                    "RECORD_EVIDENCE",
                )
            ),
            True,
        )
        self._app.runtime.create_schedule(
            schedule,
            CommandContext(
                "daily-outcome-schedule:" + str(plan.experimental_model_use_id),
                ActorType.WORKER,
                "daily-model-research",
                "EXPERIMENTAL_DAILY_RESEARCH",
            ),
        )
        config = self._app.artifacts.publish(encode_daily_plan(plan), media_type="application/json", context=_context(plan, "frozen-plan"))
        self._app.runtime.schedule_run(
            RunSpec(
                run_id,
                schedule_id,
                "daily-outcome:" + str(plan.prediction_id),
                RuntimeMode.SHADOW,
                projection["published_at"],
                plan.decision_time,
                plan.code_sha,
                config.artifact_id,
                config.content_sha256,
                parent_run_id=plan.runtime_run_id,
            ),
            steps,
            tuple(StepDependency(first.step_key, second.step_key) for first, second in zip(steps, steps[1:])),
            _context(plan, "schedule-outcomes"),
        )
        return run_id

    def settle_and_evaluate(self, plan: DailyPredictionPlan, *, worker_id: str, maximum_steps: int = 64) -> object:
        ready = self._reads.ready(plan)
        if self._reads.now() < ready.target_window_end:
            return {"prediction_id": plan.prediction_id, "state": "PENDING", "due_at": ready.target_window_end, "business_writes": 0}
        if not worker_id or not 1 <= maximum_steps <= 128:
            raise ValueError("daily settlement requires an explicit bounded worker")
        self._before_action()
        projection = self._reads.forecast_projection(plan)
        run_id = self.schedule_outcomes(plan)
        if run_id is None:
            return {"prediction_id": plan.prediction_id, "state": "NO_PREDICTIONS", "business_writes": 0}
        trace = self._app.runtime.inspect_run(run_id)
        if trace.run_state == "QUEUED":
            self._app.runtime.start_run(run_id, _context(plan, "start-outcomes"))
        elif trace.run_state not in {"RUNNING", "SUCCEEDED"}:
            raise RuntimeStateConflictError("daily Outcome Run requires explicit reconciliation: " + trace.run_state)
        target = self._reads.target_definition(plan)
        commitments = tuple(
            sorted({row["commitment_id"] for row in projection["predictions"] if row["commitment_id"] is not None}, key=str)
        )
        protocol = daily_evaluation_protocol(
            uuid5(plan.prediction_id, "evaluation-protocol"),
            target,
            plan.experimental_model_use_id,
            len(commitments),
            plan.code_artifact,
            plan.config_artifact,
        )
        self._app.research_evaluations.register_protocol(protocol, _context(plan, "register-evaluation-protocol"))
        partition_id = uuid5(plan.prediction_id, "evaluation-partition")
        experiment_id = uuid5(plan.prediction_id, "evaluation-experiment")
        partition_binding_id = uuid5(plan.prediction_id, "evaluation-experiment-partition")
        experiment_run_id = uuid5(plan.prediction_id, "evaluation-experiment-run")
        evaluation_id = uuid5(plan.prediction_id, "evaluation")
        self._app.runtime.recover_expired(actor_id=worker_id, reason_code="DAILY_RESTART", run_id=run_id)
        for _ in range(maximum_steps):
            self._before_action()
            trace = self._app.runtime.inspect_run(run_id)
            pending = next((item for item in trace.steps if item.state == "READY"), None)
            if pending is None:
                break
            key = pending.step_key
            if not key.startswith("settle-") and key != "freeze-partition":
                self._reads.require_partition_roster(partition_id, commitments)
            claim = self._app.runtime.claim_next(
                run_id=run_id,
                step_id=pending.step_id,
                worker_id=worker_id,
                lease_duration=timedelta(minutes=5),
                context=_context(plan, "outcome-claim:" + key + ":" + str(pending.current_fence + 1)),
            )
            if claim is None:
                break
            self._app.runtime.start_attempt(claim, _context(plan, "outcome-start:" + str(claim.attempt_id)))
            try:
                self._execute_outcome_step(
                    plan=plan,
                    claim=claim,
                    key=key,
                    ready=ready,
                    projection=projection,
                    commitments=commitments,
                    target=target,
                    protocol=protocol,
                    partition_id=partition_id,
                    experiment_id=experiment_id,
                    partition_binding_id=partition_binding_id,
                    experiment_run_id=experiment_run_id,
                    evaluation_id=evaluation_id,
                )
            except Exception:
                self._fail_live_claim(
                    plan,
                    claim,
                    error_code="DAILY_OUTCOME_STEP_FAILED",
                )
                raise
        return self._app.runtime.inspect_run(run_id)

    def _execute_outcome_step(
        self,
        *,
        plan: DailyPredictionPlan,
        claim: AttemptClaim,
        key: str,
        ready: Any,
        projection: dict[str, Any],
        commitments: tuple[UUID, ...],
        target: Any,
        protocol: Any,
        partition_id: UUID,
        experiment_id: UUID,
        partition_binding_id: UUID,
        experiment_run_id: UUID,
        evaluation_id: UUID,
    ) -> None:
        context = _context(plan, "outcome:" + key)
        if key.startswith("settle-"):
            commitment = next(
                item for item in commitments if "settle-" + item.hex == key
            )
            result = self._app.outcomes.settle_market_target_outcome(
                SettleMarketTargetOutcomeRequest(
                    commitment,
                    ready.target_window_end,
                    self._reads.first_attempt_at(claim.step_id),
                    None,
                ),
                context,
                runtime_claim=claim,
            )
            if isinstance(result, OutcomeNotDueResult):
                raise RuntimeStateConflictError(
                    "daily Outcome owner returned an inconsistent maturity window"
                )
        elif key == "freeze-partition":
            self._app.research_partitions.freeze(
                ResearchPartitionPlan(
                    partition_id,
                    "daily-" + plan.prediction_id.hex,
                    target.target_definition_id,
                    target.version,
                    target.content_sha256,
                    PartitionPurpose.DISCOVERY,
                    PartitionPopulationScope.ALL_COMMITMENTS,
                    PartitionOverlapPolicy.DIAGNOSTIC_REUSE,
                    "XSHG",
                    plan.input_session_id,
                    plan.input_session_id,
                    0,
                    0,
                    0,
                    "daily-" + plan.prediction_id.hex,
                    1,
                    plan.code_artifact,
                    plan.config_artifact,
                    plan.content_sha256,
                    decision_source=DecisionPartitionSource(
                        projection["decision_run_id"]
                    ),
                ),
                context,
                runtime_claim=claim,
            )
        elif key == "register-experiment":
            binding = ExperimentPartitionBinding(
                partition_binding_id,
                experiment_id,
                1,
                partition_id,
                target.target_definition_id,
                target.version,
                target.content_sha256,
                PartitionPurpose.DISCOVERY,
                self._reads.partition_hash(partition_id),
            )
            self._app.research_experiments.register(
                ExperimentDefinition(
                    experiment_id,
                    "daily-" + plan.prediction_id.hex,
                    "Describe the frozen next-session prediction population.",
                    "No fit, tuning or qualification change.",
                    "A frozen ModelVersion may or may not add predictive value.",
                    target.target_definition_id,
                    target.version,
                    target.content_sha256,
                    "evaluation-protocol:" + str(protocol.evaluation_protocol_id),
                    "Descriptive complete-population prediction evidence only.",
                    plan.code_artifact,
                    plan.config_artifact,
                    plan.content_sha256,
                ),
                (binding,),
                context,
                runtime_claim=claim,
            )
        elif key == "open-experiment-run":
            self._app.research_experiments.open_run(
                ExperimentRunPlan(
                    experiment_run_id,
                    experiment_id,
                    partition_binding_id,
                    "daily:" + str(plan.prediction_id),
                ),
                context,
                runtime_claim=claim,
            )
        elif key == "open-evaluation":
            self._app.research_evaluations.open_run(
                EvaluationRunPlan(
                    evaluation_id,
                    experiment_run_id,
                    protocol.evaluation_protocol_id,
                    self._reads.first_attempt_at(claim.step_id),
                    "daily:" + str(plan.prediction_id),
                    plan.code_artifact,
                    plan.config_artifact,
                    plan.content_sha256,
                ),
                context,
                runtime_claim=claim,
            )
        elif key == "acquire-outcome-inputs":
            self._app.research_evaluations.acquire_outcome_inputs(
                evaluation_id, context, runtime_claim=claim
            )
        elif key == "evaluate":
            self._app.research_evaluations.complete(
                evaluation_id, context, runtime_claim=claim
            )
        elif key == "evaluation-report":
            verification = (
                self._app.research_evaluation_verifier.verify_evaluation_run(
                    evaluation_id
                )
            )
            if not verification.matched:
                raise ArtifactIntegrityError(
                    "daily Evaluation report refuses unreconciled results"
                )
            evaluation = self._reads.evaluation_projection(evaluation_id)
            report = self._app.artifacts.publish(
                _evaluation_report_content(plan, projection, evaluation),
                media_type="application/json",
                context=_context(plan, "evaluation-report-json"),
            )
            self._app.runtime.succeed_attempt(
                claim, result_hash=report.content_sha256, context=context
            )
        else:
            raise ValueError("unknown daily Outcome step")


def _abstention_payload(
    plan: DailyPredictionPlan, ready: Any, reason: str
) -> dict[str, Any]:
    return {
        "schema": "daily-abstention-v1",
        "prediction_id": plan.prediction_id,
        "state": "ABSTAINED",
        "reason_code": reason,
        "plan_sha256": plan.content_sha256,
        "data_ready": ready,
        "model_version_id": plan.model_version_id,
        "forecast_published": False,
        "evidence_class": "EXPERIMENTAL_SHADOW",
        "trading_instruction": False,
    }


def _context(plan: DailyPredictionPlan, key: str) -> CommandContext:
    return CommandContext(
        "daily:" + str(plan.prediction_id) + ":" + key, ActorType.WORKER, "daily-model-research", "EXPERIMENTAL_DAILY_RESEARCH"
    )


def _binding(record: ArtifactRecord) -> ArtifactBinding:
    return ArtifactBinding(record.artifact_id, record.content_sha256, record.size_bytes)


def _json(value: object) -> bytes:
    def default(item: object) -> Any:
        if is_dataclass(item) and not isinstance(item, type):
            return asdict(item)
        if isinstance(item, datetime):
            return item.isoformat()
        if isinstance(item, (UUID, Decimal)):
            return str(item)
        raise TypeError("unsupported daily report value")

    return (json.dumps(value, default=default, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def _evaluation_denominators(
    projection: dict[str, Any], evaluation: dict[str, Any]
) -> dict[str, int]:
    prediction = projection["denominators"]
    metrics = evaluation["metrics"]

    def estimable(prefix: str) -> int:
        values = [
            int(metric["estimable_count"])
            for metric in metrics
            if str(metric["metric_code"]).startswith(prefix)
        ]
        return min(values) if values else 0

    model_estimable = estimable("model_")
    baseline_estimable = estimable("rule_baseline_")
    return {
        "sampled": int(prediction["sampled"]),
        "eligible": int(prediction["eligible"]),
        "feature_ready": int(prediction["feature_ready"]),
        "predicted": int(prediction["predicted"]),
        "mature": int(evaluation["evaluation"]["observation_count"]),
        "estimable": min(model_estimable, baseline_estimable),
        "model_estimable": model_estimable,
        "rule_baseline_estimable": baseline_estimable,
    }


def _evaluation_report_content(
    plan: DailyPredictionPlan,
    projection: dict[str, Any],
    evaluation: dict[str, Any],
) -> bytes:
    return _json(
        {
            "prediction": projection,
            "evaluation": evaluation,
            "denominators": _evaluation_denominators(projection, evaluation),
            "comparison": {
                "model_metric_prefix": "model_",
                "rule_baseline_metric_prefix": "rule_baseline_",
            },
            "research_disposition": "PENDING_HUMAN_REVIEW",
            "research_disposition_artifact_key_prefix": (
                "daily:"
                + str(plan.prediction_id)
                + ":research-disposition:"
            ),
            "automatic_model_change": False,
            "automatic_qualification_change": False,
        }
    )


def encode_daily_plan(plan: DailyPredictionPlan) -> bytes:
    payload = asdict(plan)
    for key in ("universe_scope", "code_artifact", "config_artifact"):
        artifact = getattr(plan, key)
        payload[key] = {
            "artifact_id": artifact.artifact_id,
            "content_sha256": str(artifact.content_sha256),
            "size_bytes": artifact.size_bytes,
        }
    return _json({"schema": "daily-model-prediction-plan-v1", "plan": payload})


def decode_daily_plan(content: bytes) -> DailyPredictionPlan:
    root = json.loads(content)
    if not isinstance(root, dict) or set(root) != {"schema", "plan"} or root["schema"] != "daily-model-prediction-plan-v1":
        raise ValueError("daily plan schema is unsupported")
    value = root["plan"]
    if not isinstance(value, dict) or set(value) != {field.name for field in fields(DailyPredictionPlan)}:
        raise ValueError("daily plan field roster differs")
    for key in tuple(value):
        if key.endswith("_id"):
            value[key] = UUID(value[key])
    value["instrument_ids"] = tuple(UUID(item) for item in value["instrument_ids"])
    for key in ("input_cutoff", "decision_time"):
        value[key] = datetime.fromisoformat(value[key])
    for key in ("universe_scope", "code_artifact", "config_artifact"):
        artifact = value[key]
        if not isinstance(artifact, dict) or set(artifact) != {"artifact_id", "content_sha256", "size_bytes"}:
            raise ValueError("daily plan Artifact roster differs")
        value[key] = ArtifactBinding(UUID(artifact["artifact_id"]), artifact["content_sha256"], artifact["size_bytes"])
    return DailyPredictionPlan(**value)


def render_daily_report(
    plan: DailyPredictionPlan, projection: dict[str, Any]
) -> tuple[bytes, bytes]:
    content = _json(projection)
    rows = projection["predictions"]
    markdown = "\n".join(
        [
            "# Experimental daily predictions",
            "",
            "Research predictions only; no trading instruction or qualified model claim.",
            "",
            f"ModelVersion: {plan.model_version_id}",
            f"DecisionTime: {plan.decision_time.isoformat()}",
            f"Published: {projection['published_at']}",
            f"Input snapshot: {plan.input_content_sha256}",
            "",
            "| Instrument | Model prediction | Baseline prediction | Model rank | Forecast state | Signal state |",
            "| --- | ---: | ---: | ---: | --- | --- |",
            *(
                f"| {row['instrument_id']} | {row['point_estimate'] if row['point_estimate'] is not None else 'UNAVAILABLE'} | {row['baseline_point_estimate'] if row['baseline_point_estimate'] is not None else 'UNAVAILABLE'} | {row['model_rank']} | {row['forecast_status']} | {row['signal_status']} |"
                for row in rows
            ),
            "",
        ]
    )
    return content, markdown.encode()
