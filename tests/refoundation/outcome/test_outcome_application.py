from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from market_regime_alpha.outcome.application import (
    OutcomeApplication,
    OutcomeNotDueResult,
    SettleMarketTargetOutcomeRequest,
)
from market_regime_alpha.outcome.domain import (
    OutcomeCommitmentSnapshot,
    OutcomeRuntimeSnapshot,
    PreparedOutcomeInputs,
)
from market_regime_alpha.outcome.errors import (
    OutcomeAuthorityIntegrityError,
    OutcomeCommitResultUnknownError,
    OutcomeRetryableTransactionError,
)
from market_regime_alpha.outcome.ports import OutcomeReconciliation, OutcomeSnapshot
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.runtime.ports import AttemptClaim, ReceiptRecord
from market_regime_alpha.runtime.errors import StaleFenceError
from tests.refoundation.outcome.test_outcome_kernel import (
    CHECKPOINT_A,
    HASH_A,
    HASH_B,
    INSTRUMENT_ID,
    PRODUCT_ID,
    REFERENCE_ID,
    TARGET_ID,
    _bar,
    _checkpoint,
    _dependency,
    _instant,
    _metric,
    _reference,
    _session,
    _target,
)
from market_regime_alpha.outcome.domain import (
    OutcomeDependencyRole,
    OutcomeMetricKind,
)


def _prepared(*, due: bool) -> PreparedOutcomeInputs:
    checkpoint = _checkpoint(CHECKPOINT_A, ordinal=1, local_time=datetime.min.time().replace(hour=10, minute=30))
    metric = _metric(3101, ordinal=1, kind=OutcomeMetricKind.SIMPLE_RETURN)
    target = _target(
        checkpoints=(checkpoint,),
        metrics=(metric,),
        dependencies=(
            _dependency(
                3201,
                ordinal=1,
                metric=metric,
                checkpoint_id=REFERENCE_ID,
                role=OutcomeDependencyRole.REFERENCE,
            ),
            _dependency(
                3202,
                ordinal=2,
                metric=metric,
                checkpoint_id=CHECKPOINT_A,
                role=OutcomeDependencyRole.OBSERVATION,
            ),
        ),
    )
    reference = _reference()
    commitment = OutcomeCommitmentSnapshot(
        commitment_id=UUID("00000000-0000-4000-8000-000000003301"),
        decision_run_id=UUID("00000000-0000-4000-8000-000000003302"),
        decision_run_target_id=UUID("00000000-0000-4000-8000-000000003303"),
        candidate_set_id=UUID("00000000-0000-4000-8000-000000003304"),
        candidate_id=UUID("00000000-0000-4000-8000-000000003305"),
        instrument_id=INSTRUMENT_ID,
        target_definition_id=TARGET_ID,
        target_version=1,
        target_definition_sha256=HASH_A,
        target_checkpoint_id=REFERENCE_ID,
        reference_provider_product_id=PRODUCT_ID,
        reference_capture_id=UUID("00000000-0000-4000-8000-000000003306"),
        reference_session_id=UUID("00000000-0000-4000-8000-000000001005"),
        reference_source_kind="BAR_REVISION",
        reference_fact_id=UUID("00000000-0000-4000-8000-000000003307"),
        reference_known_at=_instant(9),
        decision_time=_instant(9),
        runtime_mode="HISTORICAL",
        commitment_recorded_at=_instant(9, 1),
        reference=reference,
    )
    runtime = OutcomeRuntimeSnapshot(
        run_id=UUID("00000000-0000-4000-8000-000000003311"),
        step_id=UUID("00000000-0000-4000-8000-000000003312"),
        attempt_id=UUID("00000000-0000-4000-8000-000000003313"),
        fence_token=3,
        step_key="settle-outcome",
        step_kind="SETTLE_OUTCOME",
        runtime_mode="HISTORICAL",
        decision_time=_instant(9),
        code_sha="c" * 40,
        config_artifact_id=UUID("00000000-0000-4000-8000-000000003314"),
        config_hash=HASH_B,
    )
    return PreparedOutcomeInputs(
        commitment=commitment,
        target=target,
        runtime=runtime,
        observation_cutoff=(
            _instant(10, 30) if due else _instant(10, 29)
        ),
        knowledge_cutoff=_instant(10, 31),
        due_at=_instant(10, 30),
        sessions=(_session(),),
        sources=(
            _bar(
                checkpoint,
                ordinal=1,
                event_end=_instant(10, 30),
                open_value="100",
                high_value="106",
                low_value="99",
                close_value="105",
            ),
        )
        if due
        else (),
        is_due=due,
    )


class _Preparation:
    def __init__(self, value: PreparedOutcomeInputs) -> None:
        self.value = value
        self.calls = 0

    def prepare(self, request, runtime_claim):
        self.calls += 1
        return self.value


class _Query:
    snapshot: OutcomeSnapshot | None = None

    def load(self, revision_id):
        assert self.snapshot is not None
        assert self.snapshot.authority.revision.market_target_outcome_revision_id == revision_id
        return self.snapshot

    def find_by_request(self, commitment_id, request_identity):
        if self.snapshot is None:
            return None
        revision = self.snapshot.authority.revision
        if (
            self.snapshot.authority.commitment.commitment_id == commitment_id
            and revision.request_identity == request_identity
        ):
            return self.snapshot
        return None

    def current_for_commitment(self, commitment_id):
        if (
            self.snapshot is not None
            and self.snapshot.authority.commitment.commitment_id == commitment_id
        ):
            return self.snapshot
        return None


class _Dependencies:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state

    def lock_and_revalidate(self, prepared):
        self.state.setdefault("locks", []).append(("dependencies", prepared))
        if self.state.pop("fail_dependencies", False):
            raise OutcomeAuthorityIntegrityError("injected dependency drift")


class _Outcomes:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state

    def lock_scope_and_head(self, commitment_id):
        self.state.setdefault("locks", []).append(("outcome", commitment_id))
        return None

    def authoritative_settled_at(self):
        return _instant(10, 32)

    def insert(self, authority, *, create_root):
        self.state["authority"] = authority
        self.state["create_root"] = create_root

    def reconcile(self, revision_id, *, lock):
        revision = self.state["authority"].revision
        return OutcomeReconciliation.from_revision(revision, matched=True)


class _Receipts:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state

    def start(self, *, receipt_id, command_kind, scope_id, idempotency_key, request_hash):
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


class _Finalization:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state

    def lock_live(self, claim):
        self.lock_live_for_step(claim, expected_step_kind="SETTLE_OUTCOME")

    def lock_live_for_step(self, claim, *, expected_step_kind):
        self.state.setdefault("locks", []).append(("fence", expected_step_kind))
        if self.state.get("stale_fence"):
            raise StaleFenceError("injected stale Outcome fence")

    def succeed(self, claim, *, receipt_id, result_hash):
        self.state["runtime_success"] = result_hash
        return 2, 2

    def fail(self, claim, *, receipt_id, error_class, error_code):
        self.state["runtime_failure"] = error_code
        return "FAILED_TERMINAL", 2, 2


class _Uow:
    def __init__(self, state: dict[str, Any], query: _Query) -> None:
        self.state = state
        self.query = query
        self.dependencies = _Dependencies(state)
        self.outcomes = _Outcomes(state)
        self.receipts = _Receipts(state)
        self.audit = _Audit(state)
        self.runtime_finalization = _Finalization(state)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def commit(self):
        self.state["commits"] = self.state.get("commits", 0) + 1
        if "authority" in self.state:
            success = self.state["receipt_success"]
            self.query.snapshot = OutcomeSnapshot(
                authority=self.state["authority"],
                receipt_id=success["receipt_id"],
                result_hash=success["result_hash"],
            )
        retryable_failures = self.state.get("retryable_failures", 0)
        if retryable_failures:
            self.state["retryable_failures"] = retryable_failures - 1
            self.query.snapshot = None
            raise OutcomeRetryableTransactionError("40001")
        if self.state.pop("unknown_commit", False):
            raise OutcomeCommitResultUnknownError("injected unknown commit result")


class _UowProvider:
    def __init__(self, state: dict[str, Any], query: _Query) -> None:
        self.state = state
        self.query = query
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return _Uow(self.state, self.query)


def _context() -> CommandContext:
    return CommandContext(
        idempotency_key="settle-outcome-1",
        actor_type=ActorType.WORKER,
        actor_id="outcome-worker",
        reason_code="SETTLE_DUE_OUTCOME",
    )


def _claim(prepared: PreparedOutcomeInputs) -> AttemptClaim:
    runtime = prepared.runtime
    return AttemptClaim(
        attempt_id=runtime.attempt_id,
        run_id=runtime.run_id,
        step_id=runtime.step_id,
        step_key=runtime.step_key,
        attempt_no=1,
        fence_token=runtime.fence_token,
        lease_owner="outcome-worker",
        lease_until=datetime(2026, 8, 31, 11, tzinfo=UTC),
    )


def _request(
    prepared: PreparedOutcomeInputs,
    *,
    observation_cutoff: datetime | None = None,
) -> SettleMarketTargetOutcomeRequest:
    return SettleMarketTargetOutcomeRequest(
        commitment_id=prepared.commitment.commitment_id,
        observation_cutoff=observation_cutoff or _instant(10, 30),
        knowledge_cutoff=_instant(10, 31),
        expected_current_revision_id=None,
    )


def test_not_due_returns_zero_write_result_before_uow() -> None:
    prepared = _prepared(due=False)
    query = _Query()
    state: dict[str, Any] = {}
    uows = _UowProvider(state, query)
    result = OutcomeApplication(
        _Preparation(prepared), uows, query
    ).settle_market_target_outcome(
        _request(prepared, observation_cutoff=_instant(10, 29)),
        _context(),
        runtime_claim=_claim(prepared),
    )

    assert isinstance(result, OutcomeNotDueResult)
    assert result.database_writes == 0
    assert uows.calls == 0
    assert state == {}


def test_observation_and_knowledge_cutoffs_are_independent_boundaries() -> None:
    prepared = _prepared(due=True)
    request = SettleMarketTargetOutcomeRequest(
        commitment_id=prepared.commitment.commitment_id,
        observation_cutoff=_instant(11),
        knowledge_cutoff=_instant(10, 31),
        expected_current_revision_id=None,
    )

    assert request.observation_cutoff == _instant(11)
    assert request.knowledge_cutoff == _instant(10, 31)


def test_due_settlement_is_atomic_and_exact_retry_skips_preparation() -> None:
    prepared = _prepared(due=True)
    preparation = _Preparation(prepared)
    query = _Query()
    state: dict[str, Any] = {}
    identities = iter(
        UUID(f"00000000-0000-4000-8000-{value:012d}")
        for value in range(3401, 3500)
    )
    application = OutcomeApplication(
        preparation,
        _UowProvider(state, query),
        query,
        id_factory=identities.__next__,
        clock=lambda: _instant(10, 31),
    )

    first = application.settle_market_target_outcome(
        _request(prepared), _context(), runtime_claim=_claim(prepared)
    )
    replay = application.settle_market_target_outcome(
        _request(prepared), _context(), runtime_claim=_claim(prepared)
    )

    assert first.replayed is False
    assert replay == first.as_replay()
    assert preparation.calls == 1
    assert state["commits"] == 1
    assert state["locks"][0] == ("fence", "SETTLE_OUTCOME")
    assert state["create_root"] is True
    assert state["audits"][0]["action"] == "SETTLE_MARKET_TARGET_OUTCOME"


def test_retryable_transaction_retries_whole_write_with_stable_identities() -> None:
    prepared = _prepared(due=True)
    query = _Query()
    state: dict[str, Any] = {"retryable_failures": 2}
    identities = iter(
        UUID(f"00000000-0000-4000-8000-{value:012d}")
        for value in range(3501, 3600)
    )
    uows = _UowProvider(state, query)
    result = OutcomeApplication(
        _Preparation(prepared),
        uows,
        query,
        id_factory=identities.__next__,
        clock=lambda: _instant(10, 31),
    ).settle_market_target_outcome(
        _request(prepared),
        _context(),
        runtime_claim=_claim(prepared),
    )

    assert result.replayed is False
    assert uows.calls == 3
    assert state["commits"] == 3
    assert state["retryable_failures"] == 0


def test_unknown_commit_result_resolves_by_exact_read_only_replay() -> None:
    prepared = _prepared(due=True)
    query = _Query()
    state: dict[str, Any] = {"unknown_commit": True}
    identities = iter(
        UUID(f"00000000-0000-4000-8000-{value:012d}")
        for value in range(3601, 3700)
    )
    result = OutcomeApplication(
        _Preparation(prepared),
        _UowProvider(state, query),
        query,
        id_factory=identities.__next__,
        clock=lambda: _instant(10, 31),
    ).settle_market_target_outcome(
        _request(prepared),
        _context(),
        runtime_claim=_claim(prepared),
    )

    assert result.replayed is True
    assert query.snapshot is not None
    assert result.market_target_outcome_revision_id == (
        query.snapshot.authority.revision.market_target_outcome_revision_id
    )


def test_stale_fence_has_zero_business_and_failure_writes() -> None:
    prepared = _prepared(due=True)
    query = _Query()
    state: dict[str, Any] = {"stale_fence": True}
    with pytest.raises(StaleFenceError):
        OutcomeApplication(
            _Preparation(prepared),
            _UowProvider(state, query),
            query,
        ).settle_market_target_outcome(
            _request(prepared),
            _context(),
            runtime_claim=_claim(prepared),
        )

    assert "authority" not in state
    assert "receipt_failure" not in state
    assert "audits" not in state
    assert state.get("commits", 0) == 0


def test_deterministic_failure_rolls_back_business_and_records_fenced_failure() -> None:
    prepared = _prepared(due=True)
    query = _Query()
    state: dict[str, Any] = {"fail_dependencies": True}
    with pytest.raises(OutcomeAuthorityIntegrityError, match="dependency drift"):
        OutcomeApplication(
            _Preparation(prepared),
            _UowProvider(state, query),
            query,
        ).settle_market_target_outcome(
            _request(prepared),
            _context(),
            runtime_claim=_claim(prepared),
        )

    assert "authority" not in state
    assert state["receipt_failure"]["error_code"] == (
        "OUTCOME_AUTHORITY_INTEGRITY_FAILED"
    )
    assert state["runtime_failure"] == "OUTCOME_AUTHORITY_INTEGRITY_FAILED"
    assert state["audits"][-1]["action"] == "SETTLE_MARKET_TARGET_OUTCOME_FAILED"
