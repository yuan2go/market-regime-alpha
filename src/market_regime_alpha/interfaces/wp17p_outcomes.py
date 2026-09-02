"""Canonical Outcome settlement for the WP-17P retrospective pilot.

The operator resolves only the predeclared trading-session horizon.  Realized
values remain owned by ``OutcomeApplication`` and are reconstructed from exact
Market revisions visible at the sealed archive knowledge cutoff.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import re
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from market_regime_alpha.bootstrap import TargetApplication
from market_regime_alpha.interfaces.wp17p_authorities import Wp17pAuthorityCatalog
from market_regime_alpha.interfaces.wp17p_decisions import Wp17pDecisionExecution
from market_regime_alpha.interfaces.wp17p_operations import Wp17pDatasetAuthority
from market_regime_alpha.outcome.application import (
    OutcomeNotDueResult,
    SettleMarketTargetOutcomeRequest,
)
from market_regime_alpha.outcome.domain import OutcomeStatus
from market_regime_alpha.research_qualification.domain.target_vocabulary import (
    TargetCheckpointRole,
)
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.runtime.domain import (
    ExternalEffectClass,
    RetryPolicy,
    RunSpec,
    RuntimeMode,
    ScheduleSpec,
    StepSpec,
)
from market_regime_alpha.runtime.ports import AttemptClaim
from market_regime_alpha.shared.hashing import canonical_json_sha256


@dataclass(frozen=True, slots=True)
class Wp17pSettledOutcome:
    commitment_id: UUID
    outcome_revision_id: UUID
    status: OutcomeStatus
    result_hash: str
    settled_at: datetime


@dataclass(frozen=True, slots=True)
class Wp17pOutcomeExecution:
    decision_run_id: UUID
    observation_cutoff: datetime
    knowledge_cutoff: datetime
    outcomes: tuple[Wp17pSettledOutcome, ...]


class Wp17pOutcomeOperations:
    """Settle one complete Decision commitment roster without latest reads."""

    def __init__(self, application: TargetApplication, *, code_sha: str) -> None:
        if re.fullmatch(r"[0-9a-f]{40}([0-9a-f]{24})?", code_sha) is None:
            raise ValueError("code_sha must be an exact Git SHA")
        self._application = application
        self._code_sha = code_sha

    def settle(
        self,
        *,
        catalog: Wp17pAuthorityCatalog,
        dataset: Wp17pDatasetAuthority,
        decision: Wp17pDecisionExecution,
    ) -> Wp17pOutcomeExecution:
        if decision.dataset_id != dataset.dataset_id:
            raise ValueError("Outcome Decision and Dataset differ")
        commitment_ids = tuple(sorted(decision.commitment_ids, key=str))
        if not commitment_ids or len(set(commitment_ids)) != len(commitment_ids):
            raise ValueError("Outcome settlement requires a complete unique roster")
        observation_cutoff = outcome_observation_cutoff(
            catalog,
            dataset.backtest_scope.exploratory_backtest_fold_session_id,
        )
        knowledge_cutoff = dataset.retrospective_scope.knowledge_cutoff
        if observation_cutoff >= knowledge_cutoff:
            raise ValueError("retrospective Outcome must predate archive knowledge")

        outcomes = tuple(
            self._settle_one(
                catalog=catalog,
                commitment_id=commitment_id,
                observation_cutoff=observation_cutoff,
                knowledge_cutoff=knowledge_cutoff,
            )
            for commitment_id in commitment_ids
        )
        if tuple(item.commitment_id for item in outcomes) != commitment_ids:
            raise ValueError("Outcome settlement roster did not reconcile")
        return Wp17pOutcomeExecution(
            decision.decision_run_id,
            observation_cutoff,
            knowledge_cutoff,
            outcomes,
        )

    def _settle_one(
        self,
        *,
        catalog: Wp17pAuthorityCatalog,
        commitment_id: UUID,
        observation_cutoff: datetime,
        knowledge_cutoff: datetime,
    ) -> Wp17pSettledOutcome:
        context = _context(f"outcome-{commitment_id}")
        existing = self._application.outcome_queries.find_by_request(
            commitment_id,
            context.idempotency_key,
        )
        if existing is not None:
            revision = existing.authority.revision
            if (
                revision.draft.observation_cutoff != observation_cutoff
                or revision.draft.knowledge_cutoff != knowledge_cutoff
                or revision.supersedes_revision_id is not None
                or existing.authority.commitment.target_definition_id != catalog.target.target_definition_id
            ):
                raise ValueError("persisted Outcome replay differs from frozen request")
            return self._verified(existing)

        runtime_run_id = uuid5(
            catalog.backtest.exploratory_backtest_run_id,
            f"outcome-runtime:{commitment_id}",
        )
        _schedule_outcome_runtime(
            self._application,
            catalog=catalog,
            runtime_run_id=runtime_run_id,
            commitment_id=commitment_id,
            observation_cutoff=observation_cutoff,
            requested_at=knowledge_cutoff,
            code_sha=self._code_sha,
        )
        claim = _claim(self._application, runtime_run_id)
        result = self._application.outcomes.settle_exploratory_retrospective_market_target_outcome(
            SettleMarketTargetOutcomeRequest(
                commitment_id,
                observation_cutoff,
                knowledge_cutoff,
                None,
            ),
            context,
            runtime_claim=claim,
        )
        if isinstance(result, OutcomeNotDueResult):
            raise ValueError("predeclared retrospective Outcome is unexpectedly NOT_DUE")
        snapshot = self._application.outcome_queries.load(result.market_target_outcome_revision_id)
        return self._verified(snapshot)

    def _verified(self, snapshot) -> Wp17pSettledOutcome:
        revision_id = snapshot.authority.revision.market_target_outcome_revision_id
        report = self._application.outcome_verifier.verify(revision_id)
        if not report.matched or report.mismatch_count:
            raise ValueError("Outcome Authority did not reconcile")
        return Wp17pSettledOutcome(
            snapshot.authority.commitment.commitment_id,
            revision_id,
            snapshot.authority.revision.draft.status,
            snapshot.result_hash,
            snapshot.authority.revision.settled_at,
        )


def outcome_observation_cutoff(
    catalog: Wp17pAuthorityCatalog,
    fold_session_id: UUID,
) -> datetime:
    """Resolve the Target horizon on the frozen exchange-session roster."""

    sessions = tuple(
        sorted(
            (item for fold in catalog.backtest.folds for item in fold.sessions),
            key=lambda item: (item.session_date, str(item.trading_session_id)),
        )
    )
    if len({item.trading_session_id for item in sessions}) != len(sessions):
        raise ValueError("backtest trading-session roster contains duplicates")
    indexes = {item.exploratory_backtest_fold_session_id: index for index, item in enumerate(sessions)}
    if fold_session_id not in indexes:
        raise ValueError("fold session is not declared by the backtest")
    reference_index = indexes[fold_session_id]
    observations = tuple(item for item in catalog.target.checkpoints if item.role is TargetCheckpointRole.OUTCOME_OBSERVATION)
    if not observations:
        raise ValueError("Target has no Outcome observation checkpoint")
    cutoffs: list[datetime] = []
    for checkpoint in observations:
        target_index = reference_index + checkpoint.session_offset
        if target_index >= len(sessions):
            raise ValueError("backtest roster does not cover the Target horizon")
        cutoffs.append(
            datetime.combine(
                sessions[target_index].session_date,
                checkpoint.local_time,
                ZoneInfo(checkpoint.timezone_name),
            ).astimezone(UTC)
        )
    return max(cutoffs)


def _schedule_outcome_runtime(
    application: TargetApplication,
    *,
    catalog: Wp17pAuthorityCatalog,
    runtime_run_id: UUID,
    commitment_id: UUID,
    observation_cutoff: datetime,
    requested_at: datetime,
    code_sha: str,
) -> None:
    schedule_id = uuid5(
        catalog.backtest.exploratory_backtest_run_id,
        "runtime-schedule:outcome",
    )
    step = StepSpec(
        step_key="settle-outcome",
        step_kind="SETTLE_OUTCOME",
        implementation=("market_regime_alpha.interfaces.wp17p_outcomes:SETTLE_OUTCOME"),
        implementation_version="1",
        ordinal=1,
        required=True,
        request_hash=canonical_json_sha256(
            {
                "commitment_id": commitment_id,
                "knowledge_cutoff": requested_at,
                "observation_cutoff": observation_cutoff,
            }
        ),
        input_evidence_hash=str(catalog.backtest.content_sha256),
        retry_policy=RetryPolicy(3, (), frozenset()),
        external_effect_class=ExternalEffectClass.NONE,
    )
    application.runtime.create_schedule(
        ScheduleSpec(
            schedule_id,
            f"wp17p-outcome-{str(schedule_id)[:8]}",
            1,
            RuntimeMode.HISTORICAL,
            None,
            "Asia/Shanghai",
            canonical_json_sha256((step.step_key, step.step_kind)),
            True,
        ),
        _context("outcome-runtime-schedule"),
    )
    application.runtime.schedule_run(
        RunSpec(
            runtime_run_id,
            schedule_id,
            f"wp17p-outcome-{commitment_id}",
            RuntimeMode.HISTORICAL,
            requested_at,
            observation_cutoff,
            code_sha,
            catalog.backtest.config_artifact.artifact_id,
            str(catalog.backtest.config_artifact.content_sha256),
        ),
        (step,),
        (),
        _context(f"outcome-runtime-plan-{commitment_id}"),
    )
    application.runtime.start_run(
        runtime_run_id,
        _context(f"outcome-runtime-start-{commitment_id}"),
    )


def _claim(application: TargetApplication, runtime_run_id: UUID) -> AttemptClaim:
    claim = application.runtime.claim_next(
        worker_id="wp17p-pilot-worker",
        lease_duration=timedelta(minutes=5),
        context=_context(f"outcome-claim-{runtime_run_id}"),
    )
    if claim is None or claim.run_id != runtime_run_id or claim.step_key != "settle-outcome":
        raise ValueError("Runtime ready queue returned an unexpected Outcome Step")
    application.runtime.start_attempt(
        claim,
        _context(f"outcome-attempt-{claim.attempt_id}"),
    )
    return claim


def _context(suffix: str) -> CommandContext:
    return CommandContext(
        idempotency_key=f"wp17p:{suffix}",
        actor_type=ActorType.OPERATOR,
        actor_id="wp17p-pilot-operator",
        reason_code="WP17P_EXPLORATORY_PILOT",
    )


__all__ = [
    "Wp17pOutcomeExecution",
    "Wp17pOutcomeOperations",
    "Wp17pSettledOutcome",
    "outcome_observation_cutoff",
]
