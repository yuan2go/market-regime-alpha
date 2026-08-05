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
from market_regime_alpha.application.continuous_research.evidence import EvidenceCommit
from market_regime_alpha.application.continuous_research.journal import (
    ChildReferenceDisposition,
    ClaimedRuntimeTick,
    ChangeDecisionType,
    ContinuousChildKind,
    ContinuousTickSnapshot,
    ContinuousTickStatus,
    RuntimeArtifactReference,
    RuntimeTickReceipt,
)
from market_regime_alpha.application.continuous_research.policy import (
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


class ContinuousResearchTickRunner:
    """The unique all-day owner; computation remains behind existing child ports."""

    def __init__(
        self,
        *,
        journal: PostgresContinuousResearchJournal,
        provider: ProviderAcquisitionPort,
        children: ContinuousResearchChildPort,
        clock: Clock = _utc_now,
    ) -> None:
        if not isinstance(journal, PostgresContinuousResearchJournal):
            raise TypeError("journal must be PostgresContinuousResearchJournal")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._journal = journal
        self._provider = provider
        self._children = children
        self._clock = clock

    def execute(
        self,
        *,
        run_command: ContinuousResearchCommand,
        tick_command: RuntimeTickCommand,
        session_phase: ContinuousSessionPhase,
        provider_request: ProviderAcquisitionRequest,
    ) -> ContinuousTickExecutionResult:
        if tick_command.run_id != run_command.run_id:
            raise ValueError("tick command does not belong to run command")
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
            acquired = self._provider.acquire(provider_request)
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
        child_references = self._resolve_children(
            run_command=run_command,
            claim=active_claim,
            evidence=evidence,
            decision=decision,
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

    def _resolve_children(
        self,
        *,
        run_command: ContinuousResearchCommand,
        claim: ClaimedRuntimeTick,
        evidence: EvidenceCommit,
        decision: ChangeDecision,
    ) -> tuple[ContinuousChildReference, ...]:
        existing = self._journal.get_child_references(claim.run_id, claim.tick_id)
        if len(existing) == len(ContinuousChildKind):
            return existing
        if decision.decision_type in {
            ChangeDecisionType.NO_MATERIAL_CHANGE,
            ChangeDecisionType.DATA_INSUFFICIENT,
        }:
            if decision.decision_type is ChangeDecisionType.DATA_INSUFFICIENT:
                return ()
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
            request = _child_request(
                run_command=run_command,
                claim=claim,
                evidence=evidence,
                decision=decision,
            )
            results = self._children.lookup_children(request)
            disposition = ChildReferenceDisposition.REUSED
            if results is None:
                # Existing services execute outside the CRR Journal transaction and
                # remain responsible for their own idempotent receipts.
                results = self._children.execute_children(request)
                disposition = ChildReferenceDisposition.CREATED
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
        return self._journal.get_child_references(claim.run_id, claim.tick_id)

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
    expected = tuple(ContinuousChildKind)
    if len(kinds) != len(set(kinds)) or set(kinds) != set(expected):
        raise ValueError("child port must return each existing research service exactly once")


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


__all__ = ["ContinuousResearchTickRunner", "ContinuousTickExecutionResult"]
