from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg
import pytest

from market_regime_alpha.decision_support.application import (
    DecisionSupportApplication,
)
from market_regime_alpha.decision_support.domain import (
    ExploratoryRetrospectiveDecisionScope,
    OpenDecisionRunRequest,
    PreparedDecisionInputs,
    QualificationInputRole,
    ResearchPurpose,
    RequestedDecisionTarget,
    RequestedResearchQualification,
)
from market_regime_alpha.decision_support.ports import DecisionRunReconciliation
from market_regime_alpha.decision_support.errors import (
    DecisionCommitOutcomeUnknownError,
    DecisionRetryableTransactionError,
    DecisionTransactionRetryExhaustedError,
)
from market_regime_alpha.infrastructure.postgres.decision_uow import (
    PostgresDecisionSupportUnitOfWork,
)
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.runtime.ports import AttemptClaim, ReceiptRecord
from tests.refoundation.decision_support.test_decision_domain import (
    _candidate_snapshot,
    _references,
    _runtime,
    _target_snapshot,
    _uuid,
)
from tests.refoundation.decision_support.test_wp13_qualification_roster_domain import (
    _prepared as _prepared_qualification,
)


class _Preparation:
    def __init__(self, prepared: PreparedDecisionInputs) -> None:
        self.prepared = prepared
        self.calls = 0

    def prepare(self, request, runtime_claim):
        self.calls += 1
        return self.prepared

    def prepare_exploratory_retrospective(self, request, runtime_claim, scope):
        assert self.prepared.exploratory_retrospective_scope == scope
        self.calls += 1
        return self.prepared


class _Query:
    snapshot = None

    def load(self, decision_run_id):
        assert self.snapshot is not None
        assert self.snapshot.authority.decision_run_id == decision_run_id
        return self.snapshot

    def find_by_candidate_set(self, candidate_set_id):
        if (
            self.snapshot is not None
            and self.snapshot.authority.candidate_set.candidate_set_id
            == candidate_set_id
        ):
            return self.snapshot
        return None


class _DecisionRuns:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state

    def lock_candidate_set_identity(self, candidate_set_id):
        self.state["candidate_lock"] = candidate_set_id

    def authoritative_recorded_at(self):
        return datetime(2026, 8, 28, 6, 57, tzinfo=UTC)

    def insert(self, authority):
        self.state["authority"] = authority

    def bind_exploratory_retrospective(self, authority, scope):
        assert authority == self.state["authority"]
        self.state["retrospective_scope"] = scope
        return str(scope.content_sha256)

    def reconcile(self, decision_run_id, *, lock):
        authority = self.state["authority"]
        return DecisionRunReconciliation(
            decision_run_id=decision_run_id,
            actual_target_count=authority.target_count,
            actual_commitment_count=authority.commitment_count,
            actual_reference_count=authority.reference_count,
            actual_research_qualification_count=(
                authority.research_qualification_count
            ),
            missing_commitment_count=0,
            extra_commitment_count=0,
            candidate_roster_sha256=authority.candidate_roster_sha256,
            target_roster_sha256=authority.target_roster_sha256,
            commitment_roster_sha256=authority.commitment_roster_sha256,
            research_qualification_roster_sha256=(
                authority.research_qualification_roster_sha256
            ),
            matched=True,
        )


class _Dependencies:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state

    def lock_and_revalidate(self, prepared):
        self.state["dependencies"] = prepared


class _Receipts:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state

    def start(self, *, receipt_id, command_kind, scope_id, idempotency_key, request_hash):
        self.state["receipt_id"] = receipt_id
        self.state["request_hash"] = request_hash
        return ReceiptRecord(
            receipt_id=receipt_id,
            status="PENDING",
            request_hash=request_hash,
            result_aggregate_kind=None,
            result_aggregate_id=None,
            result_aggregate_version=None,
            result_hash=None,
            error_code=None,
            is_new=True,
        )

    def succeed(self, **kwargs):
        self.state["receipt_success"] = kwargs

    def fail(self, **kwargs):
        self.state["receipt_failure"] = kwargs


class _Audit:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state

    def append(self, **kwargs):
        self.state.setdefault("audits", []).append(kwargs)


class _RuntimeFinalization:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state

    def lock_live(self, claim):
        self.state.setdefault("locks", []).append(("fence", claim.attempt_id))

    def lock_live_for_step(self, claim, *, expected_step_kind):
        self.state.setdefault("locks", []).append(
            ("fence", claim.attempt_id, expected_step_kind)
        )

    def succeed(self, claim, *, receipt_id, result_hash):
        self.state["runtime_success"] = (claim, receipt_id, result_hash)
        return 2, 2

    def fail(self, claim, *, receipt_id, error_class, error_code):
        self.state["runtime_failure"] = (claim, receipt_id, error_class, error_code)
        return "FAILED_TERMINAL", 2, 2


class _Uow:
    def __init__(self, state, query):
        self.state = state
        self.query = query
        self.decision_runs = _DecisionRuns(state)
        self.dependencies = _Dependencies(state)
        self.receipts = _Receipts(state)
        self.audit = _Audit(state)
        self.runtime_finalization = _RuntimeFinalization(state)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def commit(self):
        from market_regime_alpha.decision_support.ports import DecisionRunSnapshot

        self.state["commits"] = self.state.get("commits", 0) + 1
        receipt = self.state.get("receipt_success")
        if "authority" in self.state and receipt is not None:
            self.query.snapshot = DecisionRunSnapshot(
                authority=self.state["authority"],
                receipt_id=receipt["receipt_id"],
                result_hash=receipt["result_hash"],
                exploratory_retrospective_scope=self.state.get(
                    "retrospective_scope"
                ),
            )


class _UowProvider:
    def __init__(self, state, query):
        self.state = state
        self.query = query

    def __call__(self):
        return _Uow(self.state, self.query)


class _RetryBeforeTransaction:
    def __enter__(self):
        raise DecisionRetryableTransactionError("40001")

    def __exit__(self, *args):
        return None


class _RetryingUowProvider:
    def __init__(self, state, query, *, failures: int) -> None:
        self.state = state
        self.query = query
        self.failures = failures
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.calls <= self.failures:
            return _RetryBeforeTransaction()
        return _Uow(self.state, self.query)


class _UnknownCommitUow(_Uow):
    def commit(self):
        super().commit()
        raise DecisionCommitOutcomeUnknownError("simulated lost COMMIT response")


class _UnknownCommitUowProvider:
    def __init__(self, state, query) -> None:
        self.state = state
        self.query = query
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return _UnknownCommitUow(self.state, self.query)


class _FailingCommitConnection:
    def __init__(self, error: psycopg.Error) -> None:
        self._error = error

    def commit(self) -> None:
        raise self._error


def _context() -> CommandContext:
    return CommandContext(
        idempotency_key="open-decision-run-1",
        actor_type=ActorType.WORKER,
        actor_id="decision-worker",
        reason_code="OPEN_DECISION_RUN",
    )


def _claim() -> AttemptClaim:
    runtime = _runtime()
    return AttemptClaim(
        attempt_id=runtime.attempt_id,
        run_id=runtime.run_id,
        step_id=runtime.step_id,
        step_key=runtime.step_key,
        attempt_no=1,
        fence_token=runtime.fence_token,
        lease_owner="decision-worker",
        lease_until=datetime(2026, 8, 28, 7, 5, tzinfo=UTC),
    )


def test_open_decision_run_uses_one_transaction_and_exact_replay_skips_preparation() -> None:
    prepared = PreparedDecisionInputs(
        candidate_set=_candidate_snapshot(),
        targets=(_target_snapshot(),),
        references=_references(),
        runtime=_runtime(),
        research_qualifications=(),
    )
    preparation = _Preparation(prepared)
    query = _Query()
    state: dict[str, Any] = {}
    next_identity = 1000

    def id_factory() -> UUID:
        nonlocal next_identity
        next_identity += 1
        return _uuid(next_identity)

    application = DecisionSupportApplication(
        preparation,
        _UowProvider(state, query),
        query,
        id_factory=id_factory,
        clock=lambda: datetime(2026, 8, 28, 6, 56, tzinfo=UTC),
    )
    request = OpenDecisionRunRequest(
        candidate_set_id=prepared.candidate_set.candidate_set_id,
        targets=(
            RequestedDecisionTarget(
                target_definition_id=prepared.targets[0].target_definition_id,
                reference_provider_product_id=(
                    prepared.targets[0].reference_provider_product.provider_product_id
                ),
            ),
        ),
        research_purpose=ResearchPurpose.DISCOVERY,
        research_qualifications=(),
    )

    first = application.open_decision_run(request, _context(), runtime_claim=_claim())
    replay = application.open_decision_run(request, _context(), runtime_claim=_claim())

    assert first.replayed is False
    assert replay == first.as_replay()
    assert first.decision_run_id == state["authority"].decision_run_id
    assert first.commitment_count == 3
    assert first.reference_count == 3
    assert preparation.calls == 1
    assert state["commits"] == 1
    assert state["locks"][0][2] == "OPEN_DECISION_RUN"
    assert state["audits"][0]["action"] == "OPEN_DECISION_RUN"


def test_typed_retrospective_open_binds_scope_in_same_transaction_and_replays() -> None:
    scope = ExploratoryRetrospectiveDecisionScope(
        dataset_id=_candidate_snapshot().dataset_id,
        exploratory_backtest_run_id=_uuid(1800),
        exploratory_backtest_arm_id=_uuid(1801),
        exploratory_backtest_fold_id=_uuid(1802),
        exploratory_backtest_fold_session_id=_uuid(1803),
        market_archive_id=_uuid(1804),
        market_archive_seal_id=_uuid(1805),
        knowledge_cutoff=datetime(2026, 8, 28, 7, 0, tzinfo=UTC),
        simulated_event_cutoff=_runtime().decision_time,
    )
    late = replace(
        _references()[0],
        recorded_at=datetime(2026, 8, 28, 6, 55, 30, tzinfo=UTC),
        known_at=datetime(2026, 8, 28, 6, 56, tzinfo=UTC),
    )
    prepared = PreparedDecisionInputs(
        candidate_set=_candidate_snapshot(),
        targets=(_target_snapshot(),),
        references=(late, *_references()[1:]),
        runtime=_runtime(),
        research_qualifications=(),
        exploratory_retrospective_scope=scope,
    )
    preparation = _Preparation(prepared)
    query = _Query()
    state: dict[str, Any] = {}
    identities = iter(range(1810, 1900))
    application = DecisionSupportApplication(
        preparation,
        _UowProvider(state, query),
        query,
        exploratory_preparation=preparation,
        id_factory=lambda: _uuid(next(identities)),
        clock=lambda: datetime(2026, 8, 28, 6, 56, tzinfo=UTC),
    )
    request = OpenDecisionRunRequest(
        candidate_set_id=prepared.candidate_set.candidate_set_id,
        targets=(
            RequestedDecisionTarget(
                target_definition_id=prepared.targets[0].target_definition_id,
                reference_provider_product_id=(
                    prepared.targets[0].reference_provider_product.provider_product_id
                ),
            ),
        ),
        research_purpose=ResearchPurpose.DISCOVERY,
        research_qualifications=(),
    )

    first = application.open_exploratory_retrospective_decision_run(
        request,
        scope,
        _context(),
        runtime_claim=_claim(),
    )
    replay = application.open_exploratory_retrospective_decision_run(
        request,
        scope,
        _context(),
        runtime_claim=_claim(),
    )

    assert first.replayed is False
    assert replay == first.as_replay()
    assert state["retrospective_scope"] == scope
    assert state["commits"] == 1
    assert preparation.calls == 1


def test_open_decision_run_freezes_exact_qualification_and_replay_never_reresolves() -> None:
    qualification = _prepared_qualification()
    prepared = PreparedDecisionInputs(
        candidate_set=_candidate_snapshot(),
        targets=(_target_snapshot(),),
        references=_references(),
        runtime=_runtime(),
        research_qualifications=(qualification,),
    )
    preparation = _Preparation(prepared)
    query = _Query()
    state: dict[str, Any] = {}
    identities = iter(range(2200, 2300))
    application = DecisionSupportApplication(
        preparation,
        _UowProvider(state, query),
        query,
        id_factory=lambda: _uuid(next(identities)),
        clock=lambda: datetime(2026, 8, 28, 6, 56, tzinfo=UTC),
    )
    request = OpenDecisionRunRequest(
        candidate_set_id=prepared.candidate_set.candidate_set_id,
        targets=(
            RequestedDecisionTarget(
                target_definition_id=prepared.targets[0].target_definition_id,
                reference_provider_product_id=(
                    prepared.targets[0].reference_provider_product.provider_product_id
                ),
            ),
        ),
        research_purpose=ResearchPurpose.DISCOVERY,
        research_qualifications=(
            RequestedResearchQualification(
                research_qualification_decision_id=(
                    qualification.research_qualification_decision_id
                ),
                role=QualificationInputRole.PRIMARY,
            ),
        ),
    )

    first = application.open_decision_run(request, _context(), runtime_claim=_claim())
    replay = application.open_decision_run(request, _context(), runtime_claim=_claim())

    assert first.research_purpose == "DISCOVERY"
    assert first.research_qualification_count == 1
    assert replay == first.as_replay()
    assert preparation.calls == 1
    assert state["authority"].research_qualification_roster.members[0].source == qualification


@pytest.mark.parametrize(
    "database_error, expected_error",
    (
        (
            psycopg.errors.SerializationFailure("serialization fixture"),
            DecisionRetryableTransactionError,
        ),
        (
            psycopg.errors.DeadlockDetected("deadlock fixture"),
            DecisionRetryableTransactionError,
        ),
        (
            psycopg.OperationalError("connection-loss fixture"),
            DecisionCommitOutcomeUnknownError,
        ),
    ),
)
def test_postgres_commit_classifies_retryable_and_unknown_outcomes(
    database_error: psycopg.Error,
    expected_error: type[Exception],
) -> None:
    uow = PostgresDecisionSupportUnitOfWork(object())  # type: ignore[arg-type]
    uow._connection = _FailingCommitConnection(database_error)  # type: ignore[assignment]

    with pytest.raises(expected_error):
        uow.commit()


def test_open_decision_run_rejects_empty_target_roster_before_preparation() -> None:
    prepared = PreparedDecisionInputs(
        candidate_set=_candidate_snapshot(),
        targets=(_target_snapshot(),),
        references=_references(),
        runtime=_runtime(),
        research_qualifications=(),
    )
    preparation = _Preparation(prepared)
    query = _Query()
    application = DecisionSupportApplication(
        preparation,
        _UowProvider({}, query),
        query,
        id_factory=lambda: _uuid(2000),
        clock=lambda: datetime(2026, 8, 28, 6, 56, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="non-empty"):
        application.open_decision_run(
            OpenDecisionRunRequest(
                candidate_set_id=prepared.candidate_set.candidate_set_id,
                targets=(),
                research_purpose=ResearchPurpose.DISCOVERY,
                research_qualifications=(),
            ),
            _context(),
            runtime_claim=_claim(),
        )
    assert preparation.calls == 0


def test_open_decision_run_retries_whole_transaction_with_frozen_inputs() -> None:
    prepared = PreparedDecisionInputs(
        candidate_set=_candidate_snapshot(),
        targets=(_target_snapshot(),),
        references=_references(),
        runtime=_runtime(),
        research_qualifications=(),
    )
    request = OpenDecisionRunRequest(
        candidate_set_id=prepared.candidate_set.candidate_set_id,
        targets=(
            RequestedDecisionTarget(
                target_definition_id=prepared.targets[0].target_definition_id,
                reference_provider_product_id=(
                    prepared.targets[0].reference_provider_product.provider_product_id
                ),
            ),
        ),
        research_purpose=ResearchPurpose.DISCOVERY,
        research_qualifications=(),
    )
    preparation = _Preparation(prepared)
    query = _Query()
    state: dict[str, Any] = {}
    provider = _RetryingUowProvider(state, query, failures=2)
    identities = iter(range(3000, 3100))

    result = DecisionSupportApplication(
        preparation,
        provider,
        query,
        id_factory=lambda: _uuid(next(identities)),
        clock=lambda: datetime(2026, 8, 28, 6, 56, tzinfo=UTC),
    ).open_decision_run(request, _context(), runtime_claim=_claim())

    assert result.replayed is False
    assert provider.calls == 3
    assert preparation.calls == 1
    assert state["commits"] == 1


def test_retry_exhaustion_records_one_terminal_failure_after_business_rollbacks() -> None:
    prepared = PreparedDecisionInputs(
        candidate_set=_candidate_snapshot(),
        targets=(_target_snapshot(),),
        references=_references(),
        runtime=_runtime(),
        research_qualifications=(),
    )
    request = OpenDecisionRunRequest(
        candidate_set_id=prepared.candidate_set.candidate_set_id,
        targets=(
            RequestedDecisionTarget(
                target_definition_id=prepared.targets[0].target_definition_id,
                reference_provider_product_id=(
                    prepared.targets[0].reference_provider_product.provider_product_id
                ),
            ),
        ),
        research_purpose=ResearchPurpose.DISCOVERY,
        research_qualifications=(),
    )
    preparation = _Preparation(prepared)
    query = _Query()
    state: dict[str, Any] = {}
    provider = _RetryingUowProvider(state, query, failures=3)
    identities = iter(range(3500, 3600))

    with pytest.raises(DecisionTransactionRetryExhaustedError):
        DecisionSupportApplication(
            preparation,
            provider,
            query,
            id_factory=lambda: _uuid(next(identities)),
            clock=lambda: datetime(2026, 8, 28, 6, 56, tzinfo=UTC),
        ).open_decision_run(request, _context(), runtime_claim=_claim())

    assert provider.calls == 4
    assert preparation.calls == 1
    assert "authority" not in state
    assert state["commits"] == 1
    assert state["receipt_failure"]["error_code"] == (
        "DECISION_TRANSACTION_RETRY_EXHAUSTED"
    )
    assert state["audits"][0]["action"] == "OPEN_DECISION_RUN_FAILED"
    assert state["runtime_failure"][3] == "DECISION_TRANSACTION_RETRY_EXHAUSTED"


def test_unknown_commit_outcome_is_resolved_by_exact_authority_replay() -> None:
    prepared = PreparedDecisionInputs(
        candidate_set=_candidate_snapshot(),
        targets=(_target_snapshot(),),
        references=_references(),
        runtime=_runtime(),
        research_qualifications=(),
    )
    request = OpenDecisionRunRequest(
        candidate_set_id=prepared.candidate_set.candidate_set_id,
        targets=(
            RequestedDecisionTarget(
                target_definition_id=prepared.targets[0].target_definition_id,
                reference_provider_product_id=(
                    prepared.targets[0].reference_provider_product.provider_product_id
                ),
            ),
        ),
        research_purpose=ResearchPurpose.DISCOVERY,
        research_qualifications=(),
    )
    preparation = _Preparation(prepared)
    query = _Query()
    state: dict[str, Any] = {}
    provider = _UnknownCommitUowProvider(state, query)
    identities = iter(range(4000, 4100))

    result = DecisionSupportApplication(
        preparation,
        provider,
        query,
        id_factory=lambda: _uuid(next(identities)),
        clock=lambda: datetime(2026, 8, 28, 6, 56, tzinfo=UTC),
    ).open_decision_run(request, _context(), runtime_claim=_claim())

    assert result.replayed is True
    assert provider.calls == 1
    assert preparation.calls == 1
    assert state["commits"] == 1
    assert query.snapshot is not None
    assert result.decision_run_id == query.snapshot.authority.decision_run_id
