"""Canonical Runtime/Decision execution for the WP-17P pilot.

This is orchestration only.  Each state change is owned by the existing
Runtime, Selection, Decision Support, Portfolio, or Risk Application command.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from uuid import UUID, uuid5

from market_regime_alpha.bootstrap import TargetApplication
from market_regime_alpha.decision_support.domain import (
    ExploratoryRetrospectiveDecisionScope,
    OpenDecisionRunRequest,
    RequestedDecisionTarget,
    ResearchPurpose,
)
from market_regime_alpha.interfaces.wp17p_authorities import Wp17pAuthorityCatalog
from market_regime_alpha.interfaces.wp17p_operations import Wp17pDatasetAuthority
from market_regime_alpha.research_qualification.domain.exploratory_backtest import (
    BacktestSessionRole,
)
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
from market_regime_alpha.runtime.ports import AttemptClaim
from market_regime_alpha.shared.hashing import canonical_json_sha256


@dataclass(frozen=True, slots=True)
class Wp17pDecisionExecution:
    dataset_id: UUID
    candidate_set_id: UUID
    decision_run_id: UUID
    runtime_run_id: UUID
    commitment_ids: tuple[UUID, ...]
    opportunity_set_id: UUID | None
    portfolio_proposal_id: UUID | None
    risk_decision_id: UUID | None
    model_version_id: UUID | None


class Wp17pDecisionOperations:
    """Drive one predeclared arm/session through canonical commands."""

    def __init__(self, application: TargetApplication, *, code_sha: str) -> None:
        if re.fullmatch(r"[0-9a-f]{40}([0-9a-f]{24})?", code_sha) is None:
            raise ValueError("code_sha must be an exact Git SHA")
        self._application = application
        self._code_sha = code_sha

    def execute(
        self,
        *,
        catalog: Wp17pAuthorityCatalog,
        dataset: Wp17pDatasetAuthority,
        complete_decision_support: bool,
        model_version_id: UUID | None = None,
    ) -> Wp17pDecisionExecution:
        arm = _one(
            tuple(
                item
                for item in catalog.backtest.arms
                if item.exploratory_backtest_arm_id
                == dataset.backtest_scope.exploratory_backtest_arm_id
            ),
            "Dataset arm",
        )
        fold = _one(
            tuple(
                item
                for item in catalog.backtest.folds
                if item.exploratory_backtest_fold_id
                == dataset.backtest_scope.exploratory_backtest_fold_id
            ),
            "Dataset fold",
        )
        session = _one(
            tuple(
                item
                for item in fold.sessions
                if item.exploratory_backtest_fold_session_id
                == dataset.backtest_scope.exploratory_backtest_fold_session_id
            ),
            "Dataset fold session",
        )
        if complete_decision_support != (
            session.role is BacktestSessionRole.EVALUATION
        ):
            raise ValueError(
                "only EVALUATION sessions execute the complete Decision Support chain"
            )
        if not complete_decision_support and session.role is not BacktestSessionRole.FIT_INPUT:
            raise ValueError("training input Decision must use a FIT_INPUT session")
        if model_version_id is not None and (
            not arm.uses_model or not complete_decision_support
        ):
            raise ValueError("ModelVersion is allowed only on the challenger Evaluation arm")
        if (
            complete_decision_support
            and arm.uses_model
            and model_version_id is None
        ):
            raise ValueError("challenger Evaluation requires an exact ModelVersion")
        if not arm.uses_model and model_version_id is not None:
            raise ValueError("rule baseline cannot bind a ModelVersion")
        strategy = catalog.strategy
        if arm.strategy_version_id is not None:
            matches = tuple(
                item
                for item in (catalog.strategy_roster or (catalog.strategy,))
                if item.strategy_version_id == arm.strategy_version_id
                and str(item.content_sha256) == str(arm.strategy_version_sha256)
            )
            strategy = _one(matches, "arm StrategyVersion")

        app = self._application
        runtime_run_id = uuid5(
            catalog.backtest.exploratory_backtest_run_id,
            f"runtime:{arm.exploratory_backtest_arm_id}:{session.exploratory_backtest_fold_session_id}",
        )
        _schedule_runtime(
            app,
            catalog=catalog,
            runtime_run_id=runtime_run_id,
            decision_time=dataset.retrospective_scope.simulated_event_cutoff,
            requested_at=dataset.retrospective_scope.knowledge_cutoff,
            complete_decision_support=complete_decision_support,
            code_sha=self._code_sha,
        )
        candidate_claim = _claim(app, runtime_run_id, "build-candidate-set")
        candidate = app.candidates.build_candidate_set(
            catalog.candidate_policy.candidate_policy_id,
            dataset.dataset_id,
            _context(f"candidate-{dataset.dataset_id}"),
            runtime_claim=candidate_claim,
        )
        candidate_set_id = UUID(candidate.aggregate_id)
        decision_claim = _claim(app, runtime_run_id, "open-decision-run")
        retrospective_scope = ExploratoryRetrospectiveDecisionScope(
            dataset.dataset_id,
            dataset.backtest_scope.exploratory_backtest_run_id,
            dataset.backtest_scope.exploratory_backtest_arm_id,
            dataset.backtest_scope.exploratory_backtest_fold_id,
            dataset.backtest_scope.exploratory_backtest_fold_session_id,
            dataset.retrospective_scope.market_archive_id,
            dataset.retrospective_scope.market_archive_seal_id,
            dataset.retrospective_scope.knowledge_cutoff,
            dataset.retrospective_scope.simulated_event_cutoff,
        )
        decision = app.decision_support.open_exploratory_retrospective_decision_run(
            OpenDecisionRunRequest(
                candidate_set_id=candidate_set_id,
                targets=(
                    RequestedDecisionTarget(
                        catalog.target.target_definition_id,
                        catalog.eligibility_policy.market_provider_product_id,
                    ),
                ),
                research_purpose=(
                    ResearchPurpose.VALIDATION
                    if complete_decision_support
                    else ResearchPurpose.DISCOVERY
                ),
                research_qualifications=(),
            ),
            retrospective_scope,
            _context(f"decision-{dataset.dataset_id}"),
            runtime_claim=decision_claim,
        )
        context_claim = _claim(app, runtime_run_id, "assess-context")
        app.decision_contexts.assess_exploratory_retrospective_context(
            decision.decision_run_id,
            catalog.context_policy.context_policy_id,
            retrospective_scope,
            _context(f"context-{dataset.dataset_id}"),
            runtime_claim=context_claim,
        )

        opportunity_set_id: UUID | None = None
        portfolio_proposal_id: UUID | None = None
        risk_decision_id: UUID | None = None
        if complete_decision_support:
            inference_claim = _claim(app, runtime_run_id, "signal-and-forecast")
            if model_version_id is None:
                app.decision_inference.produce(
                    decision.decision_run_id,
                    strategy.strategy_version_id,
                    _context(f"inference-{dataset.dataset_id}"),
                    runtime_claim=inference_claim,
                )
            else:
                app.decision_model_forecasts.produce(
                    decision.decision_run_id,
                    strategy.strategy_version_id,
                    model_version_id,
                    _context(f"model-inference-{dataset.dataset_id}"),
                    runtime_claim=inference_claim,
                )
            decide_claim = _claim(app, runtime_run_id, "decide-and-risk")
            opportunities = app.decision_opportunities.create_opportunities(
                decision.decision_run_id,
                strategy.strategy_version_id,
                _context(f"opportunities-{dataset.dataset_id}"),
                runtime_claim=decide_claim,
            )
            opportunity_set_id = opportunities.aggregate_id
            proposal = app.decision_portfolios.propose(
                opportunity_set_id,
                catalog.portfolio_policy.portfolio_policy_id,
                _context(f"portfolio-{dataset.dataset_id}"),
                runtime_claim=decide_claim,
            )
            portfolio_proposal_id = proposal.aggregate_id
            risk = app.decision_risk.assess(
                portfolio_proposal_id,
                catalog.risk_policy.risk_policy_id,
                _context(f"risk-{dataset.dataset_id}"),
                runtime_claim=decide_claim,
            )
            risk_decision_id = risk.aggregate_id

        snapshot = app.decision_runs.load(decision.decision_run_id)
        commitment_ids = tuple(
            item.commitment_id for item in snapshot.authority.commitments
        )
        if len(commitment_ids) != decision.commitment_count:
            raise ValueError("Decision commitment roster did not reconcile")
        verification = app.decision_support_verifier.verify(decision.decision_run_id)
        if not verification.matched or verification.mismatch_count:
            raise ValueError("Decision Support Authority did not reconcile")
        return Wp17pDecisionExecution(
            dataset.dataset_id,
            candidate_set_id,
            decision.decision_run_id,
            runtime_run_id,
            commitment_ids,
            opportunity_set_id,
            portfolio_proposal_id,
            risk_decision_id,
            model_version_id,
        )


def _schedule_runtime(
    application: TargetApplication,
    *,
    catalog: Wp17pAuthorityCatalog,
    runtime_run_id: UUID,
    decision_time: datetime,
    requested_at: datetime,
    complete_decision_support: bool,
    code_sha: str,
) -> None:
    step_kinds = [
        ("build-candidate-set", "BUILD_CANDIDATE_SET"),
        ("open-decision-run", "OPEN_DECISION_RUN"),
        ("assess-context", "ASSESS_CONTEXT"),
    ]
    profile = "decision"
    if complete_decision_support:
        profile = "full"
        step_kinds.extend(
            (
                ("signal-and-forecast", "SIGNAL_AND_FORECAST"),
                ("decide-and-risk", "DECIDE_AND_RISK"),
            )
        )
    schedule_id = uuid5(
        catalog.backtest.exploratory_backtest_run_id,
        f"runtime-schedule:{profile}",
    )
    schedule_code = f"wp17p-{profile}-{str(schedule_id)[:8]}"
    steps = tuple(
        StepSpec(
            step_key=key,
            step_kind=kind,
            implementation=f"market_regime_alpha.interfaces.wp17p_decisions:{kind}",
            implementation_version="1",
            ordinal=ordinal,
            required=True,
            request_hash=canonical_json_sha256(
                {"backtest": catalog.backtest.exploratory_backtest_run_id, "kind": kind}
            ),
            input_evidence_hash=str(catalog.backtest.content_sha256),
            retry_policy=RetryPolicy(3, (), frozenset()),
            external_effect_class=ExternalEffectClass.PURE_READ,
        )
        for ordinal, (key, kind) in enumerate(step_kinds, start=1)
    )
    dependencies = tuple(
        StepDependency(left.step_key, right.step_key)
        for left, right in zip(steps, steps[1:], strict=False)
    )
    application.runtime.create_schedule(
        ScheduleSpec(
            schedule_id,
            schedule_code,
            1,
            RuntimeMode.HISTORICAL,
            None,
            "Asia/Shanghai",
            canonical_json_sha256(tuple((item.step_key, item.step_kind) for item in steps)),
            True,
        ),
        _context(f"runtime-schedule-{profile}"),
    )
    application.runtime.schedule_run(
        RunSpec(
            runtime_run_id,
            schedule_id,
            f"wp17p-{runtime_run_id}",
            RuntimeMode.HISTORICAL,
            requested_at,
            decision_time,
            code_sha,
            catalog.backtest.config_artifact.artifact_id,
            str(catalog.backtest.config_artifact.content_sha256),
        ),
        steps,
        dependencies,
        _context(f"runtime-plan-{runtime_run_id}"),
    )
    application.runtime.start_run(
        runtime_run_id,
        _context(f"runtime-start-{runtime_run_id}"),
    )


def _claim(
    application: TargetApplication,
    runtime_run_id: UUID,
    expected_step_key: str,
) -> AttemptClaim:
    claim = application.runtime.claim_next(
        worker_id="wp17p-pilot-worker",
        lease_duration=timedelta(minutes=5),
        context=_context(f"claim-{runtime_run_id}-{expected_step_key}"),
    )
    if (
        claim is None
        or claim.run_id != runtime_run_id
        or claim.step_key != expected_step_key
    ):
        raise ValueError("Runtime ready queue returned an unexpected WP-17P Step")
    application.runtime.start_attempt(
        claim,
        _context(f"attempt-{claim.attempt_id}"),
    )
    return claim


def _one(items: tuple[object, ...], label: str):
    if len(items) != 1:
        raise ValueError(f"{label} is absent or ambiguous")
    return items[0]


def _context(suffix: str) -> CommandContext:
    return CommandContext(
        idempotency_key=f"wp17p:{suffix}",
        actor_type=ActorType.OPERATOR,
        actor_id="wp17p-pilot-operator",
        reason_code="WP17P_EXPLORATORY_PILOT",
    )


__all__ = ["Wp17pDecisionExecution", "Wp17pDecisionOperations"]
