"""The single Continuous Runtime Decision System child and its stage receipts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Mapping

from market_regime_alpha.application.continuous_research.journal import (
    ClaimedRuntimeTick,
    ContinuousChildKind,
    RuntimeArtifactReference,
)
from market_regime_alpha.application.continuous_research.ports import (
    ChildExecutionRequest,
    ChildExecutionResult,
)
from market_regime_alpha.application.decision_system.contracts import (
    DailyDecisionOutcome,
    DailyDecisionWindowSummary,
    DecisionLineage,
    DecisionRiskConfiguration,
    DecisionWindowState,
    FillDerivedPositionReference,
    IndependentRiskResult,
    ReconciliationTolerance,
    SummaryCandidate,
)
from market_regime_alpha.application.decision_system.portfolio import (
    build_research_portfolio_proposal,
)
from market_regime_alpha.application.decision_system.postgres_repository import (
    DecisionSystemConflict,
    PostgresDecisionSystemRepository,
)
from market_regime_alpha.application.decision_system.reconciliation import (
    reconcile_account,
)
from market_regime_alpha.application.decision_system.risk import IndependentRiskService
from market_regime_alpha.application.decision_system.window import (
    DailyDecisionWindowPolicy,
    DecisionWindowBlocked,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256


class DecisionRuntimeStage(str, Enum):
    ACCOUNT_OBSERVATION_LOOKUP = "ACCOUNT_OBSERVATION_LOOKUP"
    RECONCILIATION = "RECONCILIATION"
    SUMMARY_PREVIEW = "SUMMARY_PREVIEW"
    PORTFOLIO_PROPOSAL = "PORTFOLIO_PROPOSAL"
    RISK_DECISION = "RISK_DECISION"
    SUMMARY_FINALIZE = "SUMMARY_FINALIZE"


DECISION_RUNTIME_STAGE_ORDER = tuple(DecisionRuntimeStage)


@dataclass(frozen=True, slots=True)
class DecisionStageReceipt:
    stage: DecisionRuntimeStage
    status: str
    artifact_id: ArtifactId | None
    artifact_hash: str | None
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.status not in {"COMPLETED", "BLOCKED", "NOT_REQUESTED"}:
            raise ValueError("invalid Decision stage status")
        if (self.artifact_id is None) != (self.artifact_hash is None):
            raise ValueError("Decision stage Artifact identity must be paired")
        if self.artifact_hash is not None:
            require_sha256("Decision stage artifact_hash", self.artifact_hash)
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Decision stage reasons must be sorted and unique")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "status": self.status,
            "artifact_id": None if self.artifact_id is None else str(self.artifact_id),
            "artifact_hash": self.artifact_hash,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> DecisionStageReceipt:
        artifact_id = payload["artifact_id"]
        return cls(
            stage=DecisionRuntimeStage(str(payload["stage"])),
            status=str(payload["status"]),
            artifact_id=None if artifact_id is None else ArtifactId(str(artifact_id)),
            artifact_hash=(None if payload["artifact_hash"] is None else str(payload["artifact_hash"])),
            reason_codes=tuple(str(item) for item in _sequence(payload["reason_codes"])),
        )


@dataclass(frozen=True, slots=True)
class DecisionRuntimeReceipt:
    receipt_id: ArtifactId
    receipt_hash: str
    run_id: ArtifactId
    tick_id: ArtifactId
    claim_id: str
    fencing_token: int
    tick_version: int
    state_receipt_id: ArtifactId
    state_receipt_hash: str
    reconciliation_id: ArtifactId | None
    summary_id: ArtifactId | None
    proposal_id: ArtifactId | None
    risk_decision_id: ArtifactId | None
    status: str
    stage_receipts: tuple[DecisionStageReceipt, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        if self.status not in {"COMPLETED", "BLOCKED"}:
            raise ValueError("invalid Decision Runtime status")
        require_sha256("Decision state receipt hash", self.state_receipt_hash)
        require_sha256("Decision Runtime receipt hash", self.receipt_hash)
        if self.created_at.tzinfo is None:
            raise ValueError("Decision Runtime created_at must be aware")
        stages = tuple(item.stage for item in self.stage_receipts)
        if stages != DECISION_RUNTIME_STAGE_ORDER[: len(stages)]:
            raise ValueError("Decision Runtime stages are not an ordered prefix")
        if canonical_hash(self.semantic_payload()) != self.receipt_hash:
            raise ValueError("Decision Runtime receipt hash mismatch")
        if self.receipt_id != _runtime_receipt_id(self.receipt_hash):
            raise ValueError("Decision Runtime receipt identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> DecisionRuntimeReceipt:
        digest = canonical_hash(_runtime_payload(**values))
        return cls(
            receipt_id=_runtime_receipt_id(digest),
            receipt_hash=digest,
            **values,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _runtime_payload(
            run_id=self.run_id,
            tick_id=self.tick_id,
            claim_id=self.claim_id,
            fencing_token=self.fencing_token,
            tick_version=self.tick_version,
            state_receipt_id=self.state_receipt_id,
            state_receipt_hash=self.state_receipt_hash,
            reconciliation_id=self.reconciliation_id,
            summary_id=self.summary_id,
            proposal_id=self.proposal_id,
            risk_decision_id=self.risk_decision_id,
            status=self.status,
            stage_receipts=self.stage_receipts,
            created_at=self.created_at,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": str(self.receipt_id),
            "receipt_hash": self.receipt_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> DecisionRuntimeReceipt:
        return cls(
            receipt_id=ArtifactId(str(payload["receipt_id"])),
            receipt_hash=str(payload["receipt_hash"]),
            run_id=ArtifactId(str(payload["run_id"])),
            tick_id=ArtifactId(str(payload["tick_id"])),
            claim_id=str(payload["claim_id"]),
            fencing_token=_integer(payload["fencing_token"]),
            tick_version=_integer(payload["tick_version"]),
            state_receipt_id=ArtifactId(str(payload["state_receipt_id"])),
            state_receipt_hash=str(payload["state_receipt_hash"]),
            reconciliation_id=_optional_id(payload["reconciliation_id"]),
            summary_id=_optional_id(payload["summary_id"]),
            proposal_id=_optional_id(payload["proposal_id"]),
            risk_decision_id=_optional_id(payload["risk_decision_id"]),
            status=str(payload["status"]),
            stage_receipts=tuple(DecisionStageReceipt.from_canonical_dict(_mapping(item)) for item in _sequence(payload["stage_receipts"])),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
        )


@dataclass(frozen=True, slots=True)
class DecisionRuntimeInputs:
    manual_observation_id: ArtifactId
    positions: tuple[FillDerivedPositionReference, ...]
    fill_ledger_head: str
    fill_ledger_complete: bool
    authoritative_total_equity: Decimal | None
    authoritative_available_cash: Decimal | None
    authoritative_frozen_cash: Decimal | None
    reconciliation_tolerance: ReconciliationTolerance
    reconciliation_revision: int
    previous_reconciliation_id: ArtifactId | None
    strategy_configuration_id: ArtifactId
    strategy_configuration_hash: str
    lineage: DecisionLineage
    candidates: tuple[SummaryCandidate, ...]
    summary_revision: int
    previous_summary_id: ArtifactId | None
    correction_of_summary_id: ArtifactId | None
    risk_configuration: DecisionRiskConfiguration
    finalize: bool
    uses_complete_close_bar: bool = False
    daily_loss: Decimal | None = None


DecisionRuntimeInputLoader = Callable[[ChildExecutionRequest], DecisionRuntimeInputs]


class DecisionSystemRuntimeService:
    def __init__(
        self,
        repository: PostgresDecisionSystemRepository,
        *,
        policy: DailyDecisionWindowPolicy | None = None,
    ) -> None:
        self._repository = repository
        self._policy = policy or DailyDecisionWindowPolicy()

    def execute(
        self,
        *,
        request: ChildExecutionRequest,
        inputs: DecisionRuntimeInputs,
    ) -> DecisionRuntimeReceipt:
        claim = _claim(request)
        state_reference = _state_reference(request)
        if (
            self._policy.state_at(
                trading_date=request.trading_date,
                observed_at=request.as_of_time,
            )
            is DecisionWindowState.WINDOW_NOT_OPEN
        ):
            raise DecisionWindowBlocked("WINDOW_NOT_OPEN")
        self._policy.require_preview(
            trading_date=request.trading_date,
            as_of_time=request.as_of_time,
        )
        self._validate_inputs(request, inputs, state_reference)
        stages: list[DecisionStageReceipt] = []
        observation = self._repository.get_manual_observation(inputs.manual_observation_id)
        if observation.account_id != inputs.positions[0].account_id if inputs.positions else False:
            raise ValueError("Manual Account/Position lineage mismatch")
        if observation.trading_date != request.trading_date:
            raise ValueError("Manual Account TradingDate lineage mismatch")
        if observation.as_of_time > request.as_of_time:
            raise ValueError("Manual Account is later than Decision AsOfTime")
        stages.append(_stage(DecisionRuntimeStage.ACCOUNT_OBSERVATION_LOOKUP, observation.observation_id, observation.content_hash))

        reconciliation = reconcile_account(
            observation=observation,
            positions=inputs.positions,
            fill_ledger_head=inputs.fill_ledger_head,
            fill_ledger_complete=inputs.fill_ledger_complete,
            tolerance=inputs.reconciliation_tolerance,
            authoritative_total_equity=inputs.authoritative_total_equity,
            authoritative_available_cash=inputs.authoritative_available_cash,
            authoritative_frozen_cash=inputs.authoritative_frozen_cash,
            as_of_time=request.as_of_time,
            revision=inputs.reconciliation_revision,
            previous_reconciliation_id=inputs.previous_reconciliation_id,
            idempotency_key=f"{request.idempotency_key}:reconciliation",
            created_at=request.as_of_time,
        )
        reconciliation = self._repository.save_reconciliation(reconciliation, claim=claim)
        stages.append(_stage(DecisionRuntimeStage.RECONCILIATION, reconciliation.reconciliation_id, reconciliation.content_hash))

        preview = DailyDecisionWindowSummary.create(
            account_id=observation.account_id,
            trading_date=request.trading_date,
            strategy_configuration_id=inputs.strategy_configuration_id,
            strategy_configuration_hash=inputs.strategy_configuration_hash,
            as_of_time=request.as_of_time,
            available_at=inputs.lineage.available_at,
            lifecycle_state=DecisionWindowState.PREVIEW_AVAILABLE,
            outcome=_preview_outcome(inputs, reconciliation.status.value),
            manual_observation_id=observation.observation_id,
            reconciliation_id=reconciliation.reconciliation_id,
            lineage=inputs.lineage,
            candidates=inputs.candidates,
            revision=inputs.summary_revision,
            previous_summary_id=inputs.previous_summary_id,
            correction_of_summary_id=None,
            idempotency_key=f"{request.idempotency_key}:summary-preview",
            created_at=request.as_of_time,
        )
        preview = self._repository.save_summary(preview, claim=claim)
        stages.append(_stage(DecisionRuntimeStage.SUMMARY_PREVIEW, preview.summary_id, preview.content_hash))

        proposal = build_research_portfolio_proposal(
            summary=preview,
            observation=observation,
            reconciliation=reconciliation,
            configuration=inputs.risk_configuration,
            idempotency_key=f"{request.idempotency_key}:portfolio",
        )
        proposal = self._repository.save_proposal(proposal, claim=claim)
        stages.append(_stage(DecisionRuntimeStage.PORTFOLIO_PROPOSAL, proposal.proposal_id, proposal.content_hash))

        risk = IndependentRiskService(self._repository).decide(
            proposal_id=proposal.proposal_id,
            configuration=inputs.risk_configuration,
            as_of_time=request.as_of_time,
            idempotency_key=f"{request.idempotency_key}:risk",
            daily_loss=inputs.daily_loss,
        )
        risk = self._repository.save_risk_decision(risk, claim=claim)
        stages.append(_stage(DecisionRuntimeStage.RISK_DECISION, risk.risk_decision_id, risk.content_hash))

        output_summary = preview
        if inputs.finalize:
            self._policy.require_finalize(
                trading_date=request.trading_date,
                as_of_time=request.as_of_time,
                latest_available_at=inputs.lineage.available_at,
                uses_complete_close_bar=inputs.uses_complete_close_bar,
            )
            output_summary = DailyDecisionWindowSummary.create(
                account_id=preview.account_id,
                trading_date=preview.trading_date,
                strategy_configuration_id=preview.strategy_configuration_id,
                strategy_configuration_hash=preview.strategy_configuration_hash,
                as_of_time=preview.as_of_time,
                available_at=preview.available_at,
                lifecycle_state=(
                    DecisionWindowState.CORRECTED
                    if inputs.correction_of_summary_id is not None
                    else DecisionWindowState.FINALIZED
                ),
                outcome=_risk_outcome(risk.result, preview.outcome),
                manual_observation_id=preview.manual_observation_id,
                reconciliation_id=preview.reconciliation_id,
                lineage=preview.lineage,
                candidates=tuple(replace(item, risk_result=risk.result.value) for item in preview.candidates),
                revision=preview.revision + 1,
                previous_summary_id=preview.summary_id,
                correction_of_summary_id=inputs.correction_of_summary_id,
                idempotency_key=f"{request.idempotency_key}:summary-final",
                created_at=request.as_of_time,
            )
            try:
                output_summary = self._repository.save_summary(
                    output_summary,
                    claim=claim,
                )
            except DecisionSystemConflict:
                stages.append(
                    DecisionStageReceipt(
                        DecisionRuntimeStage.SUMMARY_FINALIZE,
                        "BLOCKED",
                        None,
                        None,
                        ("FINAL_ALREADY_EXISTS_OR_SUMMARY_CAS_REJECTED",),
                    )
                )
                blocked = DecisionRuntimeReceipt.create(
                    run_id=request.run_id,
                    tick_id=request.tick_id,
                    claim_id=request.claim_id,
                    fencing_token=request.fencing_token,
                    tick_version=request.tick_version,
                    state_receipt_id=state_reference.artifact_id,
                    state_receipt_hash=state_reference.content_hash,
                    reconciliation_id=reconciliation.reconciliation_id,
                    summary_id=preview.summary_id,
                    proposal_id=proposal.proposal_id,
                    risk_decision_id=risk.risk_decision_id,
                    status="BLOCKED",
                    stage_receipts=tuple(stages),
                    created_at=request.as_of_time,
                )
                return self._repository.save_runtime_receipt(
                    blocked,
                    claim=claim,
                )
            stages.append(
                _stage(
                    DecisionRuntimeStage.SUMMARY_FINALIZE,
                    output_summary.summary_id,
                    output_summary.content_hash,
                )
            )
        else:
            stages.append(
                DecisionStageReceipt(
                    DecisionRuntimeStage.SUMMARY_FINALIZE,
                    "NOT_REQUESTED",
                    None,
                    None,
                    ("PREVIEW_ONLY",),
                )
            )
        receipt = DecisionRuntimeReceipt.create(
            run_id=request.run_id,
            tick_id=request.tick_id,
            claim_id=request.claim_id,
            fencing_token=request.fencing_token,
            tick_version=request.tick_version,
            state_receipt_id=state_reference.artifact_id,
            state_receipt_hash=state_reference.content_hash,
            reconciliation_id=reconciliation.reconciliation_id,
            summary_id=output_summary.summary_id,
            proposal_id=proposal.proposal_id,
            risk_decision_id=risk.risk_decision_id,
            status="COMPLETED",
            stage_receipts=tuple(stages),
            created_at=request.as_of_time,
        )
        return self._repository.save_runtime_receipt(receipt, claim=claim)

    def blocked(
        self,
        *,
        request: ChildExecutionRequest,
        reason: str,
    ) -> DecisionRuntimeReceipt:
        state_reference = _state_reference(request)
        receipt = DecisionRuntimeReceipt.create(
            run_id=request.run_id,
            tick_id=request.tick_id,
            claim_id=request.claim_id,
            fencing_token=request.fencing_token,
            tick_version=request.tick_version,
            state_receipt_id=state_reference.artifact_id,
            state_receipt_hash=state_reference.content_hash,
            reconciliation_id=None,
            summary_id=None,
            proposal_id=None,
            risk_decision_id=None,
            status="BLOCKED",
            stage_receipts=(
                DecisionStageReceipt(
                    DecisionRuntimeStage.ACCOUNT_OBSERVATION_LOOKUP,
                    "BLOCKED",
                    None,
                    None,
                    (reason,),
                ),
            ),
            created_at=request.as_of_time,
        )
        return self._repository.save_runtime_receipt(receipt, claim=_claim(request))

    @staticmethod
    def _validate_inputs(
        request: ChildExecutionRequest,
        inputs: DecisionRuntimeInputs,
        state_reference: RuntimeArtifactReference,
    ) -> None:
        lineage = inputs.lineage
        if lineage.continuous_operation_id != request.run_id or lineage.runtime_tick_id != request.tick_id:
            raise ValueError("Decision Runtime operation/tick lineage mismatch")
        if lineage.as_of_time != request.as_of_time:
            raise ValueError("Decision Runtime AsOfTime lineage mismatch")
        if lineage.state_receipt_id != state_reference.artifact_id or lineage.state_receipt_hash != state_reference.content_hash:
            raise ValueError("Decision Runtime State receipt lineage mismatch")


class DecisionSystemDelegate:
    child_kind = ContinuousChildKind.DECISION_SYSTEM

    def __init__(
        self,
        service: DecisionSystemRuntimeService,
        *,
        input_loader: DecisionRuntimeInputLoader,
    ) -> None:
        self._service = service
        self._input_loader = input_loader

    def lookup(self, request: ChildExecutionRequest) -> ChildExecutionResult | None:
        try:
            receipt = self._service._repository.get_runtime_receipt(
                run_id=request.run_id,
                tick_id=request.tick_id,
            )
        except KeyError:
            return None
        return _child_result(request, receipt)

    def execute(self, request: ChildExecutionRequest) -> ChildExecutionResult:
        try:
            inputs = self._input_loader(request)
            receipt = self._service.execute(request=request, inputs=inputs)
        except (KeyError, DecisionWindowBlocked) as exc:
            reason = str(exc).strip("'") or "REQUIRED_DECISION_AUTHORITY_UNAVAILABLE"
            receipt = self._service.blocked(request=request, reason=reason)
        return _child_result(request, receipt)


def _child_result(
    request: ChildExecutionRequest,
    receipt: DecisionRuntimeReceipt,
) -> ChildExecutionResult:
    artifact_id = receipt.summary_id or receipt.risk_decision_id
    artifact_hash = None
    if artifact_id is not None:
        for stage in reversed(receipt.stage_receipts):
            if stage.artifact_id == artifact_id:
                artifact_hash = stage.artifact_hash
                break
    return ChildExecutionResult(
        child_kind=ContinuousChildKind.DECISION_SYSTEM,
        child_run_id=receipt.run_id,
        child_receipt_id=receipt.receipt_id,
        child_receipt_hash=receipt.receipt_hash,
        child_artifact_id=artifact_id,
        child_artifact_hash=artifact_hash,
        input_references=request.input_references,
        configuration_references=request.configuration_references,
    )


def _claim(request: ChildExecutionRequest) -> ClaimedRuntimeTick:
    return ClaimedRuntimeTick(
        run_id=request.run_id,
        tick_id=request.tick_id,
        tick_sequence=request.tick_sequence,
        claim_id=request.claim_id,
        fencing_token=request.fencing_token,
        tick_version=request.tick_version,
        lease_acquired_at=request.as_of_time,
        lease_expires_at=request.lease_expires_at,
        heartbeat_at=request.as_of_time,
    )


def _state_reference(request: ChildExecutionRequest) -> RuntimeArtifactReference:
    matches = tuple(item for item in request.input_references if item.reference_kind == "STATE_SYSTEM_OUTPUT")
    if len(matches) != 1:
        raise ValueError("Decision System requires exactly one State receipt")
    return matches[0]


def _stage(
    stage: DecisionRuntimeStage,
    artifact_id: ArtifactId,
    artifact_hash: str,
) -> DecisionStageReceipt:
    return DecisionStageReceipt(
        stage,
        "COMPLETED",
        artifact_id,
        artifact_hash,
        (f"{stage.value}_COMPLETED",),
    )


def _preview_outcome(inputs: DecisionRuntimeInputs, reconciliation_status: str) -> DailyDecisionOutcome:
    if reconciliation_status != "RECONCILED":
        return DailyDecisionOutcome.RECONCILIATION_REQUIRED
    if any(item.model_qualification != "QUALIFIED" for item in inputs.candidates):
        return DailyDecisionOutcome.MODEL_NOT_QUALIFIED
    if not inputs.candidates:
        return DailyDecisionOutcome.NO_ACTION
    return DailyDecisionOutcome.RESEARCH_BUY_CANDIDATE


def _risk_outcome(
    result: IndependentRiskResult,
    preview: DailyDecisionOutcome,
) -> DailyDecisionOutcome:
    return {
        IndependentRiskResult.RESEARCH_APPROVED: preview,
        IndependentRiskResult.RESEARCH_REDUCED: preview,
        IndependentRiskResult.RISK_BLOCKED: DailyDecisionOutcome.RISK_BLOCKED,
        IndependentRiskResult.DATA_INSUFFICIENT: DailyDecisionOutcome.DATA_INSUFFICIENT,
        IndependentRiskResult.ACCOUNT_NOT_CALIBRATED: DailyDecisionOutcome.ACCOUNT_NOT_CALIBRATED,
        IndependentRiskResult.RECONCILIATION_REQUIRED: DailyDecisionOutcome.RECONCILIATION_REQUIRED,
        IndependentRiskResult.MODEL_NOT_QUALIFIED: DailyDecisionOutcome.MODEL_NOT_QUALIFIED,
        IndependentRiskResult.ORDERABILITY_UNKNOWN: DailyDecisionOutcome.RISK_BLOCKED,
    }[result]


def _runtime_receipt_id(digest: str) -> ArtifactId:
    return ArtifactId(f"decision-runtime-receipt-{digest.split(':', 1)[1][:24]}")


def _runtime_payload(**values: Any) -> dict[str, Any]:
    return {
        "run_id": str(values["run_id"]),
        "tick_id": str(values["tick_id"]),
        "claim_id": values["claim_id"],
        "fencing_token": values["fencing_token"],
        "tick_version": values["tick_version"],
        "state_receipt_id": str(values["state_receipt_id"]),
        "state_receipt_hash": values["state_receipt_hash"],
        "reconciliation_id": _id_text(values["reconciliation_id"]),
        "summary_id": _id_text(values["summary_id"]),
        "proposal_id": _id_text(values["proposal_id"]),
        "risk_decision_id": _id_text(values["risk_decision_id"]),
        "status": values["status"],
        "stage_receipts": [item.to_canonical_dict() for item in values["stage_receipts"]],
        "created_at": values["created_at"].isoformat(),
    }


def _id_text(value: ArtifactId | None) -> str | None:
    return None if value is None else str(value)


def _optional_id(value: object) -> ArtifactId | None:
    return None if value is None else ArtifactId(str(value))


def _sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("expected sequence")
    return tuple(value)


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected object")
    return value


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("expected integer")
    return value


__all__ = [
    "DECISION_RUNTIME_STAGE_ORDER",
    "DecisionRuntimeInputs",
    "DecisionRuntimeReceipt",
    "DecisionRuntimeStage",
    "DecisionStageReceipt",
    "DecisionSystemDelegate",
    "DecisionSystemRuntimeService",
]
