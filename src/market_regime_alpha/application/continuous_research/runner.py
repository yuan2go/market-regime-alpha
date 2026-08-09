"""Bounded one-tick Continuous Research orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from market_regime_alpha.application.continuous_research.change_detection import (
    ChangeDecision,
)
from market_regime_alpha.application.continuous_research.children import (
    ContinuousChildReference,
)
from market_regime_alpha.application.continuous_research.contracts import (
    ContinuousResearchCommand,
    RuntimeTickCommand,
)
from market_regime_alpha.application.continuous_research.evidence import (
    EvidenceCommit,
    ProviderAttemptOutcome,
)
from market_regime_alpha.application.continuous_research.journal import (
    ChildReferenceDisposition,
    ClaimedRuntimeTick,
    ChangeDecisionType,
    ContinuousChildKind,
    ContinuousTickSnapshot,
    ContinuousTickStatus,
    ProviderAttemptStatus,
    RuntimeArtifactReference,
    RuntimeTickReceipt,
)
from market_regime_alpha.application.continuous_research.policy import (
    ContinuousDecisionWindowPolicy,
    ContinuousRunState,
    ContinuousSessionPhase,
)
from market_regime_alpha.application.continuous_research.ports import (
    ChildExecutionRequest,
    ChildExecutionResult,
    ContinuousResearchChildPort,
    ProviderAcquisitionPort,
    ProviderAcquisitionRequest,
)
from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.market_data.contracts import require_utc_second


Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


@dataclass(frozen=True, slots=True)
class ContinuousTickExecutionResult:
    tick: ContinuousTickSnapshot
    run_state: ContinuousRunState
    evidence: EvidenceCommit | None
    decision: ChangeDecision | None
    child_references: tuple[ContinuousChildReference, ...]
    reason_codes: tuple[str, ...]

    @property
    def entry_authority_granted(self) -> bool:
        return False


class _ChildExecutionFailed(RuntimeError):
    def __init__(self, tick: ContinuousTickSnapshot, reason_code: str) -> None:
        self.tick = tick
        self.reason_code = reason_code
        super().__init__(reason_code)


class ContinuousResearchTickRunner:
    """The unique all-day owner; computation remains behind existing child ports."""

    def __init__(
        self,
        *,
        journal: PostgresContinuousResearchJournal,
        provider: ProviderAcquisitionPort,
        children: ContinuousResearchChildPort,
        policy: ContinuousDecisionWindowPolicy,
        clock: Clock = _utc_now,
    ) -> None:
        if not isinstance(journal, PostgresContinuousResearchJournal):
            raise TypeError("journal must be PostgresContinuousResearchJournal")
        if not callable(clock):
            raise TypeError("clock must be callable")
        if not isinstance(policy, ContinuousDecisionWindowPolicy):
            raise TypeError("policy must be a ContinuousDecisionWindowPolicy")
        self._journal = journal
        self._provider = provider
        self._children = children
        self._policy = policy
        self._clock = clock

    def execute(
        self,
        *,
        run_command: ContinuousResearchCommand,
        tick_command: RuntimeTickCommand,
        provider_request: ProviderAcquisitionRequest,
    ) -> ContinuousTickExecutionResult:
        if tick_command.run_id != run_command.run_id:
            raise ValueError("tick command does not belong to run command")
        if (
            run_command.policy_id != self._policy.policy_id
            or run_command.policy_hash != self._policy.content_hash
        ):
            raise ValueError("run command does not bind the selected Runtime policy")
        assessment = self._policy.assess(
            trading_date=run_command.trading_date,
            observed_at=tick_command.observed_at,
        )
        session_phase = assessment.session_phase
        self._journal.create_or_get(run_command)
        admitted = self._journal.admit_tick(
            tick_command, session_phase=session_phase
        )
        if admitted.status is ContinuousTickStatus.COMPLETED:
            return self._completed_result(run_command, admitted)
        self._journal.resume(run_command.run_id)
        claim = self._journal.claim_tick(
            run_id=run_command.run_id, tick_id=tick_command.tick_id
        )
        active_claim = claim
        tick_state = self._journal.get_tick(claim.run_id, claim.tick_id)
        evidence: EvidenceCommit
        if tick_state.evidence_commit_id is not None:
            evidence = self._journal.get_evidence_commit(
                tick_state.evidence_commit_id
            )
        else:
            previous_current = None
            started = self._journal.start_provider_attempt(
                claim=claim,
                provider_id=provider_request.provider_id,
                product=provider_request.product,
                request_hash=provider_request.request_hash,
                provider_revision=provider_request.provider_revision,
            )
            active_claim = started.claim

            # External acquisition is deliberately outside every Journal transaction.
            try:
                acquired = self._provider.acquire(provider_request)
            except Exception as exc:
                return self._record_provider_exception(
                    run_command=run_command,
                    claim=active_claim,
                    attempt_id=started.attempt.attempt_id,
                    error=exc,
                )
            if acquired.evidence is not None:
                try:
                    _validate_evidence_time(
                        acquired.evidence,
                        tick_command=tick_command,
                        session_phase=session_phase,
                    )
                except (TypeError, ValueError) as exc:
                    return self._record_invalid_evidence(
                        run_command=run_command,
                        claim=active_claim,
                        attempt_id=started.attempt.attempt_id,
                        raw_response_hash=acquired.raw_response_hash,
                        error=exc,
                    )
            attempt = self._journal.complete_provider_attempt(
                claim=active_claim,
                attempt_id=started.attempt.attempt_id,
                outcome=acquired.to_outcome(),
            )
            if acquired.evidence is None:
                error = acquired.error_message or acquired.status.value
                tick = self._journal.fail_tick(
                    claim=active_claim,
                    error=error,
                    retryable=(
                        acquired.retry_at is not None
                        and acquired.status.value
                        in {"FAILED", "TIMED_OUT", "RATE_LIMITED"}
                    ),
                    retry_at=acquired.retry_at,
                )
                run = self._journal.get_run(run_command.run_id)
                return ContinuousTickExecutionResult(
                    tick=tick,
                    run_state=run.status,
                    evidence=None,
                    decision=None,
                    child_references=(),
                    reason_codes=tuple(
                        sorted({"ENTRY_BLOCKED", *acquired.reason_codes})
                    ),
                )
            previous_current = self._journal.get_current_evidence(
                run_command.run_id, acquired.evidence.evidence_scope
            )
            evidence = acquired.build_evidence(
                attempt=attempt,
                trading_date=run_command.trading_date,
                request_scope_hash=run_command.request_scope_hash,
                provider_configuration_id=run_command.provider_configuration_id,
                provider_configuration_hash=(
                    run_command.provider_configuration_hash
                ),
            )
            committed = self._journal.commit_evidence(
                claim=active_claim,
                attempt=attempt,
                evidence=evidence,
            )
            evidence = committed.evidence
            active_claim = committed.claim
            if previous_current is not None:
                previous_evidence = self._journal.get_evidence_commit(
                    previous_current.evidence_commit_id
                )
            else:
                previous_evidence = None
        if tick_state.evidence_commit_id is not None:
            previous_evidence = self._journal.get_prior_evidence_commit(
                run_id=run_command.run_id,
                tick_id=tick_command.tick_id,
                evidence_scope=evidence.evidence_scope,
            )

        tick_state = self._journal.get_tick(claim.run_id, claim.tick_id)
        if tick_state.change_decision_id is not None:
            decision = self._journal.get_change_decision(
                tick_state.change_decision_id
            )
        else:
            decision = ChangeDecision.create(
                evidence=evidence,
                previous_evidence=previous_evidence,
                downstream_contract_satisfied=_downstream_contract_satisfied(
                    evidence
                ),
                created_at=self._now(),
            )
            recorded = self._journal.record_change_decision(
                claim=active_claim, decision=decision
            )
            decision = recorded.decision
            active_claim = recorded.claim
        try:
            child_references, active_claim = self._resolve_children(
                run_command=run_command,
                claim=active_claim,
                evidence=evidence,
                decision=decision,
            )
        except _ChildExecutionFailed as exc:
            return ContinuousTickExecutionResult(
                tick=exc.tick,
                run_state=self._journal.get_run(run_command.run_id).status,
                evidence=evidence,
                decision=decision,
                child_references=(),
                reason_codes=("ENTRY_BLOCKED", exc.reason_code),
            )
        receipt = RuntimeTickReceipt.create(
            claim=active_claim,
            input_references=_tick_input_references(evidence, decision),
            output_references=_tick_output_references(child_references),
            reason_codes=tuple(
                sorted({"ENTRY_BLOCKED", *decision.reason_codes})
            ),
            created_at=self._now(),
        )
        final_state = _completed_run_state(session_phase)
        tick = self._journal.complete_tick(
            claim=active_claim,
            receipt=receipt,
            run_state=final_state,
        )
        return ContinuousTickExecutionResult(
            tick=tick,
            run_state=final_state,
            evidence=evidence,
            decision=decision,
            child_references=child_references,
            reason_codes=receipt.reason_codes,
        )

    def _record_provider_exception(
        self,
        *,
        run_command: ContinuousResearchCommand,
        claim: ClaimedRuntimeTick,
        attempt_id: int,
        error: Exception,
    ) -> ContinuousTickExecutionResult:
        reason = f"PROVIDER_EXCEPTION_{type(error).__name__.upper()}"
        self._journal.complete_provider_attempt(
            claim=claim,
            attempt_id=attempt_id,
            outcome=ProviderAttemptOutcome.create(
                status=ProviderAttemptStatus.FAILED,
                completed_at=self._now(),
                raw_response_hash=None,
                source_manifest_id=None,
                source_manifest_hash=None,
                error_code="PROVIDER_EXCEPTION",
                error_message=type(error).__name__,
                reason_codes=(reason,),
                retry_at=None,
            ),
        )
        tick = self._journal.fail_tick(
            claim=claim,
            error=reason,
            retryable=False,
            retry_at=None,
        )
        return ContinuousTickExecutionResult(
            tick=tick,
            run_state=self._journal.get_run(run_command.run_id).status,
            evidence=None,
            decision=None,
            child_references=(),
            reason_codes=("ENTRY_BLOCKED", reason),
        )

    def _record_invalid_evidence(
        self,
        *,
        run_command: ContinuousResearchCommand,
        claim: ClaimedRuntimeTick,
        attempt_id: int,
        raw_response_hash: str | None,
        error: Exception,
    ) -> ContinuousTickExecutionResult:
        reason = "INVALID_EVIDENCE_TIME"
        self._journal.complete_provider_attempt(
            claim=claim,
            attempt_id=attempt_id,
            outcome=ProviderAttemptOutcome.create(
                status=ProviderAttemptStatus.INVALID_RESPONSE,
                completed_at=self._now(),
                raw_response_hash=raw_response_hash,
                source_manifest_id=None,
                source_manifest_hash=None,
                error_code=reason,
                error_message=type(error).__name__,
                reason_codes=(reason,),
                retry_at=None,
            ),
        )
        tick = self._journal.fail_tick(
            claim=claim,
            error=reason,
            retryable=False,
            retry_at=None,
        )
        return ContinuousTickExecutionResult(
            tick=tick,
            run_state=self._journal.get_run(run_command.run_id).status,
            evidence=None,
            decision=None,
            child_references=(),
            reason_codes=("ENTRY_BLOCKED", reason),
        )

    def _resolve_children(
        self,
        *,
        run_command: ContinuousResearchCommand,
        claim: ClaimedRuntimeTick,
        evidence: EvidenceCommit,
        decision: ChangeDecision,
    ) -> tuple[tuple[ContinuousChildReference, ...], ClaimedRuntimeTick]:
        existing = self._journal.get_child_references(claim.run_id, claim.tick_id)
        if len(existing) == len(ContinuousChildKind):
            return existing, claim
        if decision.decision_type in {
            ChangeDecisionType.NO_MATERIAL_CHANGE,
            ChangeDecisionType.DATA_INSUFFICIENT,
        }:
            if decision.decision_type is ChangeDecisionType.DATA_INSUFFICIENT:
                return (), claim
            prior = self._journal.get_latest_child_references(
                run_id=run_command.run_id,
                before_tick_sequence=claim.tick_sequence,
            )
            references = tuple(
                _child_reference(
                    run_command=run_command,
                    claim=claim,
                    evidence=evidence,
                    decision=decision,
                    result=ChildExecutionResult(
                        child_kind=item.child_kind,
                        child_run_id=item.child_run_id,
                        child_receipt_id=item.child_receipt_id,
                        child_receipt_hash=item.child_receipt_hash,
                        child_artifact_id=item.child_artifact_id,
                        child_artifact_hash=item.child_artifact_hash,
                        input_references=item.input_references,
                        configuration_references=item.configuration_references,
                    ),
                    disposition=ChildReferenceDisposition.REUSED,
                    created_at=self._now(),
                )
                for item in prior
            )
        else:
            claim = self._journal.heartbeat(claim)
            request = _child_request(
                run_command=run_command,
                claim=claim,
                evidence=evidence,
                decision=decision,
            )
            try:
                results = self._children.lookup_children(request)
                disposition = ChildReferenceDisposition.REUSED
                if results is None:
                    # Existing services execute outside the CRR Journal transaction and
                    # remain responsible for their own idempotent receipts.
                    results = self._children.execute_children(request)
                    disposition = ChildReferenceDisposition.CREATED
            except Exception as exc:
                reason = _child_failure_reason(exc)
                tick = self._journal.fail_tick(
                    claim=claim,
                    error=reason,
                    retryable=False,
                    retry_at=None,
                )
                raise _ChildExecutionFailed(tick, reason) from exc
            claim = self._journal.heartbeat(claim)
            _require_complete_child_set(results)
            references = tuple(
                _child_reference(
                    run_command=run_command,
                    claim=claim,
                    evidence=evidence,
                    decision=decision,
                    result=result,
                    disposition=disposition,
                    created_at=self._now(),
                )
                for result in sorted(results, key=lambda item: item.child_kind.value)
            )
        existing_kinds = {item.child_kind for item in existing}
        for reference in references:
            if reference.child_kind in existing_kinds:
                continue
            self._journal.record_child_reference(
                claim=claim, reference=reference
            )
        return self._journal.get_child_references(claim.run_id, claim.tick_id), claim

    def _completed_result(
        self,
        run_command: ContinuousResearchCommand,
        tick: ContinuousTickSnapshot,
    ) -> ContinuousTickExecutionResult:
        evidence = (
            None
            if tick.evidence_commit_id is None
            else self._journal.get_evidence_commit(tick.evidence_commit_id)
        )
        decision = (
            None
            if tick.change_decision_id is None
            else self._journal.get_change_decision(tick.change_decision_id)
        )
        return ContinuousTickExecutionResult(
            tick=tick,
            run_state=self._journal.get_run(run_command.run_id).status,
            evidence=evidence,
            decision=decision,
            child_references=self._journal.get_child_references(
                run_command.run_id, tick.command.tick_id
            ),
            reason_codes=(
                ("ENTRY_BLOCKED",)
                if tick.receipt is None
                else tick.receipt.reason_codes
            ),
        )

    def _now(self) -> datetime:
        value = self._clock()
        require_utc_second("clock", value)
        return value


def _child_request(
    *,
    run_command: ContinuousResearchCommand,
    claim: ClaimedRuntimeTick,
    evidence: EvidenceCommit,
    decision: ChangeDecision,
) -> ChildExecutionRequest:
    return ChildExecutionRequest(
        trading_date=run_command.trading_date,
        as_of_time=evidence.as_of_time,
        run_id=claim.run_id,
        tick_id=claim.tick_id,
        tick_sequence=claim.tick_sequence,
        claim_id=claim.claim_id,
        fencing_token=claim.fencing_token,
        tick_version=claim.tick_version,
        lease_acquired_at=claim.lease_acquired_at,
        lease_expires_at=claim.lease_expires_at,
        heartbeat_at=claim.heartbeat_at,
        provider_attempt_id=evidence.attempt_id,
        source_manifest_id=evidence.source_manifest_id,
        source_manifest_hash=evidence.source_manifest_hash,
        evidence_commit_id=evidence.evidence_commit_id,
        evidence_commit_hash=evidence.commit_hash,
        decision_id=decision.decision_id,
        decision_hash=decision.decision_hash,
        input_references=tuple(
            sorted(
                (
                    RuntimeArtifactReference(
                        "EVIDENCE_ARTIFACT",
                        evidence.evidence_artifact_id,
                        evidence.evidence_artifact_hash,
                    ),
                    RuntimeArtifactReference(
                        "SOURCE_MANIFEST",
                        evidence.source_manifest_id,
                        evidence.source_manifest_hash,
                    ),
                ),
                key=_reference_key,
            )
        ),
        configuration_references=tuple(
            sorted(
                (
                    RuntimeArtifactReference(
                        "PROVIDER_CONFIGURATION",
                        run_command.provider_configuration_id,
                        run_command.provider_configuration_hash,
                    ),
                    RuntimeArtifactReference(
                        "RESEARCH_CONFIGURATION",
                        run_command.research_configuration_id,
                        run_command.research_configuration_hash,
                    ),
                ),
                key=_reference_key,
            )
        ),
        authority_mode=run_command.authority_mode,
    )


def _child_reference(
    *,
    run_command: ContinuousResearchCommand,
    claim: ClaimedRuntimeTick,
    evidence: EvidenceCommit,
    decision: ChangeDecision,
    result: ChildExecutionResult,
    disposition: ChildReferenceDisposition,
    created_at: datetime,
) -> ContinuousChildReference:
    return ContinuousChildReference.create(
        trading_date=run_command.trading_date,
        run_id=claim.run_id,
        tick_id=claim.tick_id,
        tick_sequence=claim.tick_sequence,
        provider_attempt_id=evidence.attempt_id,
        source_manifest_id=evidence.source_manifest_id,
        source_manifest_hash=evidence.source_manifest_hash,
        evidence_commit_id=evidence.evidence_commit_id,
        evidence_commit_hash=evidence.commit_hash,
        decision_id=decision.decision_id,
        decision_hash=decision.decision_hash,
        child_kind=result.child_kind,
        reference_disposition=disposition,
        child_run_id=result.child_run_id,
        child_receipt_id=result.child_receipt_id,
        child_receipt_hash=result.child_receipt_hash,
        child_artifact_id=result.child_artifact_id,
        child_artifact_hash=result.child_artifact_hash,
        input_references=result.input_references,
        configuration_references=result.configuration_references,
        created_at=created_at,
    )


def _require_complete_child_set(results: tuple[ChildExecutionResult, ...]) -> None:
    kinds = tuple(result.child_kind for result in results)
    required = set(ContinuousChildKind) - {
        # A stage-level DATA_INSUFFICIENT or MODEL_NOT_QUALIFIED outcome can
        # legitimately stop before Canonical Lifecycle admission.  The Daily
        # Summary remains the terminal Decision owner; absent work must never
        # be represented by a synthetic Canonical receipt.
        ContinuousChildKind.CANONICAL_LIFECYCLE,
    }
    if (
        len(kinds) != len(set(kinds))
        or not required.issubset(kinds)
        or not set(kinds).issubset(set(ContinuousChildKind))
    ):
        raise ValueError("child port must return each executed research owner exactly once")


def _tick_input_references(
    evidence: EvidenceCommit, decision: ChangeDecision
) -> tuple[RuntimeArtifactReference, ...]:
    return tuple(
        sorted(
            (
                RuntimeArtifactReference(
                    "CHANGE_DECISION", decision.decision_id, decision.decision_hash
                ),
                RuntimeArtifactReference(
                    "EVIDENCE_COMMIT",
                    evidence.evidence_commit_id,
                    evidence.commit_hash,
                ),
            ),
            key=_reference_key,
        )
    )


def _tick_output_references(
    references: tuple[ContinuousChildReference, ...],
) -> tuple[RuntimeArtifactReference, ...]:
    outputs: list[RuntimeArtifactReference] = []
    for reference in references:
        outputs.append(
            RuntimeArtifactReference(
                f"{reference.child_kind.value}_RECEIPT",
                reference.child_receipt_id,
                reference.child_receipt_hash,
            )
        )
        if reference.child_artifact_id is not None:
            assert reference.child_artifact_hash is not None
            outputs.append(
                RuntimeArtifactReference(
                    f"{reference.child_kind.value}_ARTIFACT",
                    reference.child_artifact_id,
                    reference.child_artifact_hash,
                )
            )
    return tuple(sorted(outputs, key=_reference_key))


def _reference_key(reference: RuntimeArtifactReference) -> tuple[str, str, str]:
    return (
        reference.reference_kind,
        str(reference.artifact_id),
        reference.content_hash,
    )


def _completed_run_state(phase: ContinuousSessionPhase) -> ContinuousRunState:
    if phase is ContinuousSessionPhase.DECISION_WINDOW:
        return ContinuousRunState.DECISION_WINDOW_OPEN
    if phase is ContinuousSessionPhase.MARKET_CLOSED:
        return ContinuousRunState.MARKET_CLOSED
    return ContinuousRunState.WAITING_FOR_NEW_DATA


def _downstream_contract_satisfied(evidence: EvidenceCommit) -> bool:
    satisfied = "DOWNSTREAM_CONTRACT_SATISFIED" in evidence.limitations
    blocked = "DOWNSTREAM_CONTRACT_NOT_SATISFIED" in evidence.limitations
    if satisfied == blocked:
        raise ValueError(
            "Runner Evidence must persist exactly one downstream contract marker"
        )
    return satisfied


def _validate_evidence_time(
    evidence: object,
    *,
    tick_command: RuntimeTickCommand,
    session_phase: ContinuousSessionPhase,
) -> None:
    from market_regime_alpha.application.continuous_research.ports import (
        ValidatedEvidencePayload,
    )

    if not isinstance(evidence, ValidatedEvidencePayload):
        raise TypeError("provider Evidence must be a ValidatedEvidencePayload")
    if evidence.as_of_time > tick_command.observed_at:
        raise ValueError("Evidence AsOfTime cannot exceed Runtime Tick observed_at")
    if evidence.available_at > tick_command.observed_at:
        raise ValueError("future Evidence is not consumable by the Runtime Tick")
    if (
        session_phase is ContinuousSessionPhase.DECISION_WINDOW
        and "COMPLETE_DAILY_BAR" in evidence.limitations
    ):
        raise ValueError("Decision Window cannot consume a complete daily bar")


def _child_failure_reason(exc: Exception) -> str:
    if str(exc) == "FREE_DATA_PRODUCTION_AUTHORITY_DENIED":
        return "FREE_DATA_PRODUCTION_AUTHORITY_DENIED"
    # Runtime reason codes are typed control-plane facts.  Arbitrary Provider
    # or database exception text belongs in logs and must not become lineage.
    return f"CHILD_EXECUTION_{type(exc).__name__.upper()}"


__all__ = ["ContinuousResearchTickRunner", "ContinuousTickExecutionResult"]
