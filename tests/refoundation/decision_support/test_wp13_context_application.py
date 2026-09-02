from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from market_regime_alpha.decision_support.application import ContextCommands
from market_regime_alpha.decision_support.ports import (
    ContextAssessmentRecord,
    ContextPolicyRecord,
    ContextReconciliation,
)
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.runtime.errors import IdempotencyKeyReusedError
from market_regime_alpha.runtime.ports import AttemptClaim, ReceiptRecord
from tests.refoundation.decision_support.test_decision_domain import _uuid
from tests.refoundation.decision_support.test_wp13_context_domain import (
    DECISION_TIME,
    _policy,
    _source,
)
from market_regime_alpha.decision_support.domain import PreparedContextInputs


RECORDED_AT = datetime(2026, 9, 1, 7, 2, tzinfo=UTC)


def _prepared() -> PreparedContextInputs:
    policy = _policy()
    sources = tuple(
        source
        for metric in policy.metrics
        for source in (
            _source(
                metric,
                1,
                decimal_value=(
                    None if metric.value_type == "BOOLEAN" else metric.lower_threshold
                ),
                boolean_value=True if metric.value_type == "BOOLEAN" else None,
            ),
            _source(
                metric,
                2,
                decimal_value=(
                    None if metric.value_type == "BOOLEAN" else metric.lower_threshold
                ),
                boolean_value=False if metric.value_type == "BOOLEAN" else None,
            ),
        )
    )
    return PreparedContextInputs(
        decision_run_id=_uuid(1100),
        candidate_set_id=_uuid(1101),
        candidate_set_content_sha256="9" * 64,
        candidate_roster_sha256="d" * 64,
        decision_time=DECISION_TIME,
        candidate_count=2,
        policy=policy,
        sources=sources,
    )


def _context(key: str, reason: str) -> CommandContext:
    return CommandContext(
        idempotency_key=key,
        actor_type=ActorType.WORKER,
        actor_id="context-worker",
        reason_code=reason,
    )


def _claim() -> AttemptClaim:
    return AttemptClaim(
        attempt_id=_uuid(1200),
        run_id=_uuid(1201),
        step_id=_uuid(1202),
        step_key="assess_context",
        attempt_no=1,
        fence_token=1,
        lease_owner="context-worker",
        lease_until=datetime(2026, 9, 1, 7, 10, tzinfo=UTC),
    )


class _Preparation:
    def __init__(self, prepared: PreparedContextInputs) -> None:
        self.prepared = prepared
        self.calls = 0

    def prepare(self, decision_run_id, context_policy_id):
        self.calls += 1
        assert decision_run_id == self.prepared.decision_run_id
        assert context_policy_id == self.prepared.policy.context_policy_id
        return self.prepared


class _Query:
    def __init__(self) -> None:
        self.policies: dict[tuple[str, str], ContextPolicyRecord] = {}
        self.assessments: dict[tuple[UUID, UUID, str], ContextAssessmentRecord] = {}

    def authoritative_time(self):
        return RECORDED_AT

    def find_policy_request(self, policy_code, request_identity):
        return self.policies.get((policy_code, request_identity))

    def find_assessment_request(
        self,
        decision_run_id,
        context_policy_id,
        request_identity,
    ):
        return self.assessments.get(
            (decision_run_id, context_policy_id, request_identity)
        )


class _Contexts:
    def __init__(self, state: dict[str, Any], query: _Query) -> None:
        self.state = state
        self.query = query

    def lock_policy_identity(self, policy_code):
        self.state.setdefault("locks", []).append(("policy", policy_code))

    def lock_assessment_identity(self, decision_run_id, context_policy_id):
        self.state.setdefault("locks", []).append(
            ("assessment", decision_run_id, context_policy_id)
        )

    def authoritative_recorded_at(self):
        return RECORDED_AT

    def register_policy(self, plan, *, request_identity, request_sha256):
        record = ContextPolicyRecord(
            context_policy_id=plan.context_policy_id,
            policy_code=plan.policy_code,
            version=plan.version,
            metric_count=plan.metric_count,
            kind_count=plan.kind_count,
            content_sha256=plan.content_sha256,
            request_identity=request_identity,
            request_sha256=request_sha256,
            frozen_at=RECORDED_AT,
            receipt_id=self.state["receipt_id"],
        )
        self.query.policies[(plan.policy_code, request_identity)] = record
        return record

    def policy_record(self, context_policy_id, *, lock):
        del lock
        return next(
            record
            for record in self.query.policies.values()
            if record.context_policy_id == context_policy_id
        )

    def insert_assessment(self, authority):
        record = ContextAssessmentRecord(
            assessment_group_id=authority.assessment_group_id,
            decision_run_id=authority.decision_run_id,
            context_policy_id=authority.context_policy_id,
            assessment_count=authority.assessment_count,
            metric_count=authority.metric_count,
            source_count=authority.source_count,
            assessment_roster_sha256=authority.assessment_roster_sha256,
            content_sha256=authority.content_sha256,
            request_identity=authority.request_identity,
            request_sha256=authority.request_sha256,
            recorded_at=authority.recorded_at,
            receipt_id=self.state["receipt_id"],
        )
        self.query.assessments[
            (
                authority.decision_run_id,
                authority.context_policy_id,
                authority.request_identity,
            )
        ] = record
        self.state["authority"] = authority
        return record

    def assessment_record(self, assessment_group_id, *, lock):
        del lock
        return next(
            record
            for record in self.query.assessments.values()
            if record.assessment_group_id == assessment_group_id
        )

    def reconcile(self, assessment_group_id, *, lock):
        assert lock
        authority = self.state["authority"]
        return ContextReconciliation(
            assessment_group_id=assessment_group_id,
            actual_assessment_count=authority.assessment_count,
            actual_metric_count=authority.metric_count,
            actual_source_count=authority.source_count,
            assessment_roster_sha256=authority.assessment_roster_sha256,
            matched=True,
        )


class _Dependencies:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state

    def lock_and_revalidate(self, prepared):
        self.state["prepared"] = prepared


class _Artifacts:
    def require_exact(self, binding, *, lock):
        assert lock
        return binding


class _Receipts:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state

    def start(self, *, receipt_id, command_kind, scope_id, idempotency_key, request_hash):
        self.state["receipt_id"] = receipt_id
        self.state["command_kind"] = command_kind
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


class _Runtime:
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
    def __init__(self, state: dict[str, Any], query: _Query) -> None:
        self.state = state
        self.contexts = _Contexts(state, query)
        self.dependencies = _Dependencies(state)
        self.artifacts = _Artifacts()
        self.receipts = _Receipts(state)
        self.audit = _Audit(state)
        self.runtime_finalization = _Runtime(state)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def commit(self):
        self.state["commits"] = self.state.get("commits", 0) + 1


class _UowProvider:
    def __init__(self, state: dict[str, Any], query: _Query) -> None:
        self.state = state
        self.query = query

    def __call__(self):
        return _Uow(self.state, self.query)


def _commands(prepared: PreparedContextInputs):
    state: dict[str, Any] = {}
    query = _Query()
    identities = iter(range(1300, 1500))
    preparation = _Preparation(prepared)
    commands = ContextCommands(
        preparation,
        _UowProvider(state, query),
        query,
        id_factory=lambda: _uuid(next(identities)),
    )
    return commands, preparation, state


def test_register_context_policy_is_immutable_and_exactly_replayed() -> None:
    plan = _policy()
    commands, _, state = _commands(_prepared())
    context = _context("register-context-policy-1", "REGISTER_CONTEXT_POLICY")

    first = commands.register_policy(plan, context)
    replay = commands.register_policy(plan, context)

    assert replay == first.as_replay()
    assert state["commits"] == 1
    assert state["command_kind"] == "REGISTER_CONTEXT_POLICY"
    with pytest.raises(IdempotencyKeyReusedError):
        commands.register_policy(
            replace(plan, provenance_sha256="f" * 64),
            context,
        )


def test_assess_context_freezes_complete_roster_and_replay_skips_input_read() -> None:
    prepared = _prepared()
    commands, preparation, state = _commands(prepared)
    context = _context("assess-context-1", "ASSESS_CONTEXT")

    first = commands.assess_context(
        prepared.decision_run_id,
        prepared.policy.context_policy_id,
        context,
        runtime_claim=_claim(),
    )
    replay = commands.assess_context(
        prepared.decision_run_id,
        prepared.policy.context_policy_id,
        context,
        runtime_claim=_claim(),
    )

    assert replay == first.as_replay()
    assert first.child_count == prepared.policy.metric_count
    assert first.source_count == len(prepared.sources)
    assert preparation.calls == 1
    assert state["locks"][0][2] == "ASSESS_CONTEXT"
    assert state["audits"][0]["action"] == "CONTEXT_ASSESSED"
    assert state["commits"] == 1
