"""Selection Core commands over one narrow transaction."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
from typing import Callable, Iterator, ParamSpec, TypeVar
from uuid import UUID, uuid4

from market_regime_alpha.market.domain import MembershipStatus
from market_regime_alpha.runtime.application import (
    CommandContext,
    CommandFailureDescriptor,
    ConcurrentCommandSucceeded,
    RuntimeCommandFailureRecorder,
)
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    CommandInProgressError,
    CommandPreviouslyFailedError,
    IdempotencyKeyReusedError,
    RuntimeNotFoundError,
    RuntimeStateConflictError,
    StaleFenceError,
)
from market_regime_alpha.runtime.ports import AttemptClaim, ReceiptRecord
from market_regime_alpha.selection.domain import (
    CriterionEvidence,
    CriterionOperator,
    CriterionResult,
    CriterionValueKind,
    EligibilityAssessmentDecision,
    EligibilityBatch,
    EligibilityPolicy,
    EligibilityReasonDecision,
    EligibilityRule,
    EligibilityRuleKind,
    EligibilityStatus,
    FrozenUniverse,
    MarketEvidenceStatus,
    UniverseDefinition,
    UniverseMemberDecision,
    UniverseMembershipStatus,
    UniverseScopeSpecification,
)
from market_regime_alpha.selection.ports import (
    SelectionUnitOfWork,
    SelectionUnitOfWorkProvider,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.time import DecisionTime


_P = ParamSpec("_P")
_R = TypeVar("_R")


def _replay_concurrent_success(
    command: Callable[_P, _R],
) -> Callable[_P, _R]:
    @wraps(command)
    def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        try:
            return command(*args, **kwargs)
        except ConcurrentCommandSucceeded:
            return command(*args, **kwargs)

    return wrapped


@dataclass(frozen=True, slots=True)
class SelectionMutationResult:
    aggregate_kind: str
    aggregate_id: str
    aggregate_version: int
    result_hash: str
    receipt_id: UUID
    replayed: bool


class SelectionApplication:
    """Own Universe/Eligibility semantics; consume Market only through its port."""

    def __init__(
        self,
        uow_provider: SelectionUnitOfWorkProvider,
        *,
        id_factory=uuid4,
    ) -> None:
        self._uow_provider = uow_provider
        self._id_factory = id_factory
        self._failure_recorder = RuntimeCommandFailureRecorder(
            uow_provider,
            id_factory=id_factory,
        )

    @_replay_concurrent_success
    def register_universe(
        self,
        definition: UniverseDefinition,
        context: CommandContext,
    ) -> SelectionMutationResult:
        request_hash = canonical_json_sha256(definition)
        result_hash = canonical_json_sha256({"universe_id": definition.universe_id, "version": 1})
        with (
            self._terminal_failure_boundary(
                operation="REGISTER_UNIVERSE",
                scope_id=definition.universe_code,
                request_hash=request_hash,
                error_class="COMMAND",
                error_code="REGISTER_UNIVERSE_REJECTED",
                context=context,
                runtime_claim=None,
            ),
            self._uow_provider() as uow,
        ):
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="REGISTER_UNIVERSE",
                scope_id=definition.universe_code,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return _replayed_mutation(receipt)
            version = uow.selection.register_universe(definition)
            self._finish(
                uow,
                receipt_id=receipt.receipt_id,
                aggregate_kind="UNIVERSE",
                aggregate_id=str(definition.universe_id),
                aggregate_version=version,
                result_hash=result_hash,
                action="REGISTER_UNIVERSE",
                context=context,
            )
            uow.commit()
            return SelectionMutationResult(
                aggregate_kind="UNIVERSE",
                aggregate_id=str(definition.universe_id),
                aggregate_version=version,
                result_hash=result_hash,
                receipt_id=receipt.receipt_id,
                replayed=False,
            )

    @_replay_concurrent_success
    def register_eligibility_policy(
        self,
        policy: EligibilityPolicy,
        context: CommandContext,
    ) -> SelectionMutationResult:
        request_hash = canonical_json_sha256(policy)
        result_hash = canonical_json_sha256(
            {
                "eligibility_policy_id": policy.eligibility_policy_id,
                "content_sha256": policy.content_sha256,
                "version": policy.version,
            }
        )
        with (
            self._terminal_failure_boundary(
                operation="REGISTER_ELIGIBILITY_POLICY",
                scope_id=policy.policy_code,
                request_hash=request_hash,
                error_class="COMMAND",
                error_code="REGISTER_ELIGIBILITY_POLICY_REJECTED",
                context=context,
                runtime_claim=None,
            ),
            self._uow_provider() as uow,
        ):
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="REGISTER_ELIGIBILITY_POLICY",
                scope_id=policy.policy_code,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return _replayed_mutation(receipt)
            version = uow.selection.register_eligibility_policy(policy)
            self._finish(
                uow,
                receipt_id=receipt.receipt_id,
                aggregate_kind="ELIGIBILITY_POLICY",
                aggregate_id=str(policy.eligibility_policy_id),
                aggregate_version=version,
                result_hash=result_hash,
                action="REGISTER_ELIGIBILITY_POLICY",
                context=context,
            )
            uow.commit()
            return SelectionMutationResult(
                aggregate_kind="ELIGIBILITY_POLICY",
                aggregate_id=str(policy.eligibility_policy_id),
                aggregate_version=version,
                result_hash=result_hash,
                receipt_id=receipt.receipt_id,
                replayed=False,
            )

    @_replay_concurrent_success
    def freeze_universe(
        self,
        *,
        universe_id: UUID,
        scope: UniverseScopeSpecification,
        decision_time: DecisionTime,
        context: CommandContext,
        runtime_claim: AttemptClaim | None = None,
    ) -> FrozenUniverse:
        decision_time = decision_time if isinstance(decision_time, DecisionTime) else DecisionTime(decision_time)
        request_hash = canonical_json_sha256(
            {
                "decision_time": decision_time,
                "scope": scope,
                "universe_id": universe_id,
            }
        )
        with (
            self._terminal_failure_boundary(
                operation="FREEZE_UNIVERSE",
                scope_id=str(universe_id),
                request_hash=request_hash,
                error_class="COMMAND",
                error_code="FREEZE_UNIVERSE_REJECTED",
                context=context,
                runtime_claim=runtime_claim,
            ),
            self._uow_provider() as uow,
        ):
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="FREEZE_UNIVERSE",
                scope_id=str(universe_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                result_hash = _required_result_hash(receipt)
                frozen = uow.selection.load_frozen_universe(
                    UUID(_required_aggregate_id(receipt)),
                    result_hash=result_hash,
                    receipt_id=receipt.receipt_id,
                    replayed=True,
                )
                self._finalize_runtime(
                    uow,
                    runtime_claim,
                    receipt_id=receipt.receipt_id,
                    result_hash=result_hash,
                )
                uow.commit()
                return frozen
            revision = uow.selection.validate_and_lock_scope(
                universe_id=universe_id,
                scope=scope,
            )
            members = tuple(
                self._classify_member(
                    instrument_id=instrument_id,
                    evidence=uow.market_queries.membership_as_of(
                        scope=scope,
                        instrument_id=instrument_id,
                        decision_time=decision_time,
                    ),
                    scope=scope,
                )
                for instrument_id in scope.instrument_ids
            )
            included = sum(item.membership_status is UniverseMembershipStatus.INCLUDED for item in members)
            excluded = sum(item.membership_status is UniverseMembershipStatus.EXCLUDED for item in members)
            unknown = sum(item.membership_status is UniverseMembershipStatus.UNKNOWN for item in members)
            if len(members) != included + excluded + unknown:
                raise AssertionError("Universe member counts do not reconcile")
            universe_revision_id = self._id_factory()
            result_hash = canonical_json_sha256(
                {
                    "decision_time": decision_time,
                    "members": members,
                    "revision": revision,
                    "scope_content_sha256": scope.content_sha256,
                    "universe_id": universe_id,
                    "universe_revision_id": universe_revision_id,
                }
            )
            uow.selection.insert_frozen_universe(
                universe_revision_id=universe_revision_id,
                universe_id=universe_id,
                revision=revision,
                decision_time=decision_time,
                scope=scope,
                members=members,
            )
            self._finish(
                uow,
                receipt_id=receipt.receipt_id,
                aggregate_kind="UNIVERSE_REVISION",
                aggregate_id=str(universe_revision_id),
                aggregate_version=revision,
                result_hash=result_hash,
                action="FREEZE_UNIVERSE",
                context=context,
                runtime_claim=runtime_claim,
            )
            self._finalize_runtime(
                uow,
                runtime_claim,
                receipt_id=receipt.receipt_id,
                result_hash=result_hash,
            )
            uow.commit()
            return FrozenUniverse(
                universe_revision_id=universe_revision_id,
                universe_id=universe_id,
                revision=revision,
                decision_time=decision_time,
                members=members,
                total_count=len(members),
                included_count=included,
                excluded_count=excluded,
                unknown_count=unknown,
                result_hash=result_hash,
                receipt_id=receipt.receipt_id,
                replayed=False,
            )

    @_replay_concurrent_success
    def assess_eligibility(
        self,
        *,
        universe_revision_id: UUID,
        eligibility_policy_id: UUID,
        decision_time: DecisionTime,
        context: CommandContext,
        runtime_claim: AttemptClaim | None = None,
    ) -> EligibilityBatch:
        decision_time = decision_time if isinstance(decision_time, DecisionTime) else DecisionTime(decision_time)
        request_hash = canonical_json_sha256(
            {
                "decision_time": decision_time,
                "eligibility_policy_id": eligibility_policy_id,
                "universe_revision_id": universe_revision_id,
            }
        )
        scope_id = f"{universe_revision_id}:{eligibility_policy_id}"
        with (
            self._terminal_failure_boundary(
                operation="ASSESS_ELIGIBILITY",
                scope_id=scope_id,
                request_hash=request_hash,
                error_class="COMMAND",
                error_code="ASSESS_ELIGIBILITY_REJECTED",
                context=context,
                runtime_claim=runtime_claim,
            ),
            self._uow_provider() as uow,
        ):
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="ASSESS_ELIGIBILITY",
                scope_id=scope_id,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                result_hash = _required_result_hash(receipt)
                batch = uow.selection.load_eligibility_batch(
                    universe_revision_id=universe_revision_id,
                    eligibility_policy_id=eligibility_policy_id,
                    decision_time=decision_time,
                    result_hash=result_hash,
                    receipt_id=receipt.receipt_id,
                    replayed=True,
                )
                self._finalize_runtime(
                    uow,
                    runtime_claim,
                    receipt_id=receipt.receipt_id,
                    result_hash=result_hash,
                )
                uow.commit()
                return batch
            universe = uow.selection.lock_frozen_universe(universe_revision_id)
            if universe.decision_time != decision_time:
                raise ValueError("Eligibility DecisionTime must equal Universe DecisionTime")
            policy = uow.selection.load_eligibility_policy(eligibility_policy_id)
            assessments = tuple(
                self._assess_member(
                    uow=uow,
                    member=member,
                    policy=policy,
                    decision_time=decision_time,
                )
                for member in universe.members
            )
            eligible = sum(item.result is EligibilityStatus.ELIGIBLE for item in assessments)
            ineligible = sum(item.result is EligibilityStatus.INELIGIBLE for item in assessments)
            unknown = sum(item.result is EligibilityStatus.UNKNOWN for item in assessments)
            if len(assessments) != eligible + ineligible + unknown:
                raise AssertionError("Eligibility counts do not reconcile")
            result_hash = canonical_json_sha256(
                {
                    "assessments": assessments,
                    "decision_time": decision_time,
                    "eligibility_policy_id": eligibility_policy_id,
                    "universe_revision_id": universe_revision_id,
                }
            )
            uow.selection.insert_eligibility_assessments(
                universe=universe,
                policy=policy,
                decision_time=decision_time,
                assessments=assessments,
            )
            self._finish(
                uow,
                receipt_id=receipt.receipt_id,
                aggregate_kind="ELIGIBILITY_BATCH",
                aggregate_id=scope_id,
                aggregate_version=1,
                result_hash=result_hash,
                action="ASSESS_ELIGIBILITY",
                context=context,
                runtime_claim=runtime_claim,
            )
            self._finalize_runtime(
                uow,
                runtime_claim,
                receipt_id=receipt.receipt_id,
                result_hash=result_hash,
            )
            uow.commit()
            return EligibilityBatch(
                universe_revision_id=universe_revision_id,
                eligibility_policy_id=eligibility_policy_id,
                decision_time=decision_time,
                assessments=assessments,
                total_count=len(assessments),
                eligible_count=eligible,
                ineligible_count=ineligible,
                unknown_count=unknown,
                result_hash=result_hash,
                receipt_id=receipt.receipt_id,
                replayed=False,
            )

    @contextmanager
    def _terminal_failure_boundary(
        self,
        *,
        operation: str,
        scope_id: str,
        request_hash: str,
        error_class: str,
        error_code: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None,
    ) -> Iterator[None]:
        """Select deterministic Selection errors; persistence is shared."""
        descriptor = self._failure_descriptor(
            operation=operation,
            scope_id=scope_id,
            request_hash=request_hash,
            error_class=error_class,
            error_code=error_code,
        )
        try:
            yield
        except StaleFenceError:
            raise
        except (CommandInProgressError, IdempotencyKeyReusedError) as exc:
            self._failure_recorder.record_idempotency_rejection(
                descriptor,
                rejection_code=exc.code,
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
            self._failure_recorder.record(
                descriptor,
                context=context,
                runtime_claim=runtime_claim,
            )
            raise

    @staticmethod
    def _failure_descriptor(
        *,
        operation: str,
        scope_id: str,
        request_hash: str,
        error_class: str,
        error_code: str,
    ) -> CommandFailureDescriptor:
        return CommandFailureDescriptor(
            command_kind=operation,
            scope_id=scope_id,
            request_hash=request_hash,
            error_class=error_class,
            error_code=error_code,
            aggregate_kind="SELECTION_COMMAND",
            failure_action="SELECTION_COMMAND_FAILED",
            rejection_command_kind="SELECTION_COMMAND_REJECTION",
            rejection_action="SELECTION_COMMAND_REJECTED",
            rejection_key_prefix="selection-command-rejection",
        )

    def _classify_member(
        self,
        *,
        instrument_id,
        evidence,
        scope,
    ) -> UniverseMemberDecision:
        if evidence.status is MarketEvidenceStatus.AVAILABLE:
            included = evidence.membership_status is MembershipStatus.MEMBER
            status = UniverseMembershipStatus.INCLUDED if included else UniverseMembershipStatus.EXCLUDED
            reason = "CLASSIFICATION_MEMBER" if included else "CLASSIFICATION_NOT_MEMBER"
        else:
            status = UniverseMembershipStatus.UNKNOWN
            reason = {
                MarketEvidenceStatus.MISSING: "MARKET_EVIDENCE_MISSING",
                MarketEvidenceStatus.STALE: "MARKET_EVIDENCE_STALE",
                MarketEvidenceStatus.GAP: "MARKET_EVIDENCE_GAP",
                MarketEvidenceStatus.CONFLICT: "MARKET_EVIDENCE_CONFLICT",
            }[evidence.status]
        lineage_hash = canonical_json_sha256(
            {
                "classification_code": scope.classification_code,
                "classification_scheme": scope.classification_scheme,
                "evidence": evidence,
                "instrument_id": instrument_id,
            }
        )
        return UniverseMemberDecision(
            universe_member_id=self._id_factory(),
            instrument_id=instrument_id,
            membership_status=status,
            evidence_status=evidence.status,
            observed_membership_status=(evidence.membership_status.value if evidence.membership_status is not None else None),
            classification_id=evidence.classification_id,
            membership_revision_id=evidence.membership_revision_id,
            source_gap_id=evidence.gap_id,
            market_capture_id=evidence.capture_id,
            market_decision_visible_at=evidence.decision_visible_at,
            reason_code=reason,
            lineage_hash=lineage_hash,
        )

    def _assess_member(
        self,
        *,
        uow: SelectionUnitOfWork,
        member: UniverseMemberDecision,
        policy: EligibilityPolicy,
        decision_time: DecisionTime,
    ) -> EligibilityAssessmentDecision:
        reasons = tuple(
            self._evaluate_rule(
                rule,
                uow.market_queries.criterion_evidence_as_of(
                    market_provider_product_id=policy.market_provider_product_id,
                    rule=rule,
                    instrument_id=member.instrument_id,
                    decision_time=decision_time,
                ),
            )
            for rule in policy.rules
        )
        fail_count = sum(item.criterion_result is CriterionResult.FAIL for item in reasons)
        unknown_count = sum(item.criterion_result is CriterionResult.UNKNOWN for item in reasons)
        result = EligibilityStatus.INELIGIBLE if fail_count else EligibilityStatus.UNKNOWN if unknown_count else EligibilityStatus.ELIGIBLE
        return EligibilityAssessmentDecision(
            eligibility_assessment_id=self._id_factory(),
            universe_member_id=member.universe_member_id,
            instrument_id=member.instrument_id,
            result=result,
            reasons=reasons,
        )

    def _evaluate_rule(
        self,
        rule: EligibilityRule,
        evidence: CriterionEvidence,
    ) -> EligibilityReasonDecision:
        observed_kind = _observed_kind(evidence)
        if evidence.status is not MarketEvidenceStatus.AVAILABLE:
            result = CriterionResult.UNKNOWN
            reason = {
                MarketEvidenceStatus.MISSING: "EVIDENCE_MISSING",
                MarketEvidenceStatus.STALE: "EVIDENCE_STALE",
                MarketEvidenceStatus.GAP: "EVIDENCE_GAP",
                MarketEvidenceStatus.CONFLICT: "EVIDENCE_CONFLICT",
            }[evidence.status]
        elif evidence.observed_status == "UNKNOWN":
            result = CriterionResult.UNKNOWN
            reason = "EVIDENCE_UNKNOWN_STATUS"
        elif rule.rule_kind is EligibilityRuleKind.MIN_LISTING_AGE and evidence.observed_status in {"PRE_LISTING", "DELISTED"}:
            result = CriterionResult.FAIL
            reason = "EXPLICIT_CRITERION_FAILED"
        else:
            passed = _compare(rule, evidence)
            result = CriterionResult.PASS if passed else CriterionResult.FAIL
            reason = "CRITERION_PASSED" if passed else "EXPLICIT_CRITERION_FAILED"
        return EligibilityReasonDecision(
            eligibility_reason_id=self._id_factory(),
            rule=rule,
            criterion_result=result,
            observed_value_kind=observed_kind,
            observed_decimal=evidence.observed_decimal,
            observed_status=evidence.observed_status,
            observed_count=evidence.observed_count,
            reason_code=reason,
            lineage=evidence.lineage,
        )

    def _finish(
        self,
        uow: SelectionUnitOfWork,
        *,
        receipt_id: UUID,
        aggregate_kind: str,
        aggregate_id: str,
        aggregate_version: int,
        result_hash: str,
        action: str,
        context: CommandContext,
        runtime_claim: AttemptClaim | None = None,
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
            audit_event_id=self._id_factory(),
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

    @staticmethod
    def _finalize_runtime(
        uow: SelectionUnitOfWork,
        claim: AttemptClaim | None,
        *,
        receipt_id: UUID,
        result_hash: str,
    ) -> None:
        if claim is None:
            return
        uow.runtime_finalization.succeed(
            claim,
            receipt_id=receipt_id,
            result_hash=result_hash,
        )


def _observed_kind(evidence: CriterionEvidence) -> CriterionValueKind:
    if evidence.observed_status is not None:
        return CriterionValueKind.STATUS
    if evidence.observed_decimal is not None:
        return CriterionValueKind.DECIMAL
    if evidence.observed_count is not None:
        return CriterionValueKind.COUNT
    return CriterionValueKind.MISSING


def _compare(rule: EligibilityRule, evidence: CriterionEvidence) -> bool:
    if rule.operator is CriterionOperator.EQ:
        return evidence.observed_status == rule.threshold_status
    if rule.value_kind is CriterionValueKind.DECIMAL:
        if evidence.observed_decimal is None or rule.threshold_decimal is None:
            raise AssertionError("decimal rule lost its typed values")
        return evidence.observed_decimal >= rule.threshold_decimal
    if rule.value_kind is CriterionValueKind.COUNT:
        if evidence.observed_count is None or rule.threshold_count is None:
            raise AssertionError("count rule lost its typed values")
        return evidence.observed_count >= rule.threshold_count
    raise AssertionError("unsupported explicit Eligibility comparison")


def _replayed_mutation(receipt: ReceiptRecord) -> SelectionMutationResult:
    _ensure_replay_succeeded(receipt)
    if (
        receipt.result_aggregate_kind is None
        or receipt.result_aggregate_id is None
        or receipt.result_aggregate_version is None
        or receipt.result_hash is None
    ):
        raise ArtifactIntegrityError("terminal receipt has no complete result")
    return SelectionMutationResult(
        aggregate_kind=receipt.result_aggregate_kind,
        aggregate_id=receipt.result_aggregate_id,
        aggregate_version=receipt.result_aggregate_version,
        result_hash=receipt.result_hash,
        receipt_id=receipt.receipt_id,
        replayed=True,
    )


def _required_result_hash(receipt: ReceiptRecord) -> str:
    _ensure_replay_succeeded(receipt)
    if receipt.result_hash is None:
        raise ArtifactIntegrityError("terminal receipt has no result hash")
    return receipt.result_hash


def _required_aggregate_id(receipt: ReceiptRecord) -> str:
    if receipt.result_aggregate_id is None:
        raise ArtifactIntegrityError("terminal receipt has no aggregate identity")
    return receipt.result_aggregate_id


def _ensure_replay_succeeded(receipt: ReceiptRecord) -> None:
    if receipt.status in {"FAILED", "BLOCKED"}:
        raise CommandPreviouslyFailedError(receipt.error_code or "COMMAND_FAILED_WITHOUT_ERROR_CODE")
    if receipt.status != "SUCCEEDED":
        raise RuntimeStateConflictError(f"receipt {receipt.receipt_id} is not a replayable terminal result")


__all__ = ["SelectionApplication", "SelectionMutationResult"]
