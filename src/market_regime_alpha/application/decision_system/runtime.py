"""The single Continuous Runtime Decision System child and its stage receipts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Mapping
import unicodedata

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
    DecisionModelQualification,
    DecisionLineage,
    DecisionRiskConfiguration,
    DecisionWindowState,
    IndependentRiskResult,
    ReconciliationTolerance,
    SummaryCandidate,
)
from market_regime_alpha.application.decision_system.authority import (
    PositionSettlementEvidence,
)
from market_regime_alpha.application.decision_system.portfolio import (
    build_research_portfolio_proposal,
)
from market_regime_alpha.application.decision_system.postgres_repository import (
    DecisionSystemConflict,
    DecisionSystemIntegrityError,
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
from market_regime_alpha.core.identity import ArtifactId, UniverseId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
)
from market_regime_alpha.platform.postgres_runtime_governance import (
    PostgresModelGovernanceRepository,
)
from market_regime_alpha.platform.runtime_governance import (
    ArtifactLineageReference,
    ModelSelectionRequest,
    RuntimeAuthorityMode,
    RuntimeModelLineage,
    SelectionStatus,
)


DECISION_RUNTIME_RECEIPT_SCHEMA = "decision_runtime_receipt/v2"


class DecisionRuntimeStage(str, Enum):
    ACCOUNT_OBSERVATION_LOOKUP = "ACCOUNT_OBSERVATION_LOOKUP"
    MODEL_GOVERNANCE = "MODEL_GOVERNANCE"
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
        if self.artifact_id is not None:
            _string(str(self.artifact_id))
        for reason in self.reason_codes:
            _string(reason)
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
        if set(payload) != {
            "stage", "status", "artifact_id", "artifact_hash", "reason_codes"
        }:
            raise ValueError("DecisionStageReceipt fields mismatch")
        artifact_id = payload["artifact_id"]
        return cls(
            stage=DecisionRuntimeStage(_string(payload["stage"])),
            status=_string(payload["status"]),
            artifact_id=None if artifact_id is None else ArtifactId(_string(artifact_id)),
            artifact_hash=(None if payload["artifact_hash"] is None else _string(payload["artifact_hash"])),
            reason_codes=tuple(_string(item) for item in _sequence(payload["reason_codes"])),
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
    lease_expires_at: datetime
    state_receipt_id: ArtifactId
    state_receipt_hash: str
    reconciliation_id: ArtifactId | None
    summary_id: ArtifactId | None
    proposal_id: ArtifactId | None
    risk_decision_id: ArtifactId | None
    status: str
    stage_receipts: tuple[DecisionStageReceipt, ...]
    created_at: datetime
    schema_version: str = DECISION_RUNTIME_RECEIPT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != DECISION_RUNTIME_RECEIPT_SCHEMA:
            raise ValueError("unsupported Decision Runtime receipt schema")
        if self.status not in {"COMPLETED", "BLOCKED"}:
            raise ValueError("invalid Decision Runtime status")
        for text_value in (
            str(self.receipt_id), str(self.run_id), str(self.tick_id),
            self.claim_id, str(self.state_receipt_id),
        ):
            _string(text_value)
        for artifact_value in (
            self.reconciliation_id, self.summary_id, self.proposal_id,
            self.risk_decision_id,
        ):
            if artifact_value is not None:
                _string(str(artifact_value))
        for label, integer_value in (
            ("fencing_token", self.fencing_token),
            ("tick_version", self.tick_version),
        ):
            if (
                isinstance(integer_value, bool)
                or not isinstance(integer_value, int)
                or integer_value < 1
            ):
                raise ValueError(f"Decision Runtime {label} must be a positive integer")
        require_sha256("Decision state receipt hash", self.state_receipt_hash)
        require_sha256("Decision Runtime receipt hash", self.receipt_hash)
        if self.created_at.tzinfo is None:
            raise ValueError("Decision Runtime created_at must be aware")
        if self.lease_expires_at.tzinfo is None:
            raise ValueError("Decision Runtime lease_expires_at must be aware")
        if self.lease_expires_at <= self.created_at:
            raise ValueError("Decision Runtime receipt requires active bound Lease")
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
            lease_expires_at=self.lease_expires_at,
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
        expected = {
            "schema_version", "receipt_id", "receipt_hash", "run_id", "tick_id",
            "claim_id", "fencing_token", "tick_version", "lease_expires_at",
            "state_receipt_id", "state_receipt_hash", "reconciliation_id",
            "summary_id", "proposal_id", "risk_decision_id", "status",
            "stage_receipts", "created_at",
        }
        if set(payload) != expected:
            raise ValueError("DecisionRuntimeReceipt fields mismatch")
        if payload["schema_version"] != DECISION_RUNTIME_RECEIPT_SCHEMA:
            raise ValueError("unsupported Decision Runtime receipt schema")
        return cls(
            receipt_id=ArtifactId(_string(payload["receipt_id"])),
            receipt_hash=_string(payload["receipt_hash"]),
            run_id=ArtifactId(_string(payload["run_id"])),
            tick_id=ArtifactId(_string(payload["tick_id"])),
            claim_id=_string(payload["claim_id"]),
            fencing_token=_integer(payload["fencing_token"]),
            tick_version=_integer(payload["tick_version"]),
            lease_expires_at=_instant(payload["lease_expires_at"]),
            state_receipt_id=ArtifactId(_string(payload["state_receipt_id"])),
            state_receipt_hash=_string(payload["state_receipt_hash"]),
            reconciliation_id=_optional_id(payload["reconciliation_id"]),
            summary_id=_optional_id(payload["summary_id"]),
            proposal_id=_optional_id(payload["proposal_id"]),
            risk_decision_id=_optional_id(payload["risk_decision_id"]),
            status=_string(payload["status"]),
            stage_receipts=tuple(DecisionStageReceipt.from_canonical_dict(_mapping(item)) for item in _sequence(payload["stage_receipts"])),
            created_at=_instant(payload["created_at"]),
        )


@dataclass(frozen=True, slots=True)
class DecisionRuntimeInputs:
    manual_observation_id: ArtifactId
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
    model_runtime_lineages: tuple[RuntimeModelLineage, ...]
    finalize: bool
    uses_complete_close_bar: bool = False
    position_settlement_evidence: PositionSettlementEvidence | None = None


DecisionRuntimeInputLoader = Callable[[ChildExecutionRequest], DecisionRuntimeInputs]


class DecisionSystemRuntimeService:
    def __init__(
        self,
        repository: PostgresDecisionSystemRepository,
        *,
        policy: DailyDecisionWindowPolicy | None = None,
        model_selector: PostgresModelGovernanceRepository | None = None,
    ) -> None:
        self._repository = repository
        self._policy = policy or DailyDecisionWindowPolicy()
        self._model_selector = model_selector

    def execute(
        self,
        *,
        request: ChildExecutionRequest,
        inputs: DecisionRuntimeInputs,
    ) -> DecisionRuntimeReceipt:
        if request.authority_mode is not RuntimeAuthorityMode.PRODUCTION:
            raise ValueError(
                "Research/Shadow must use the account-neutral Summary Runtime"
            )
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
        if observation.trading_date != request.trading_date:
            raise ValueError("Manual Account TradingDate lineage mismatch")
        if observation.as_of_time > request.as_of_time:
            raise ValueError("Manual Account is later than Decision AsOfTime")
        stages.append(_stage(DecisionRuntimeStage.ACCOUNT_OBSERVATION_LOOKUP, observation.observation_id, observation.content_hash))

        governed_inputs, governance_stage = self._apply_model_governance(
            request=request,
            inputs=inputs,
        )
        stages.append(governance_stage)
        if governed_inputs is None:
            blocked = DecisionRuntimeReceipt.create(
                run_id=request.run_id,
                tick_id=request.tick_id,
                claim_id=request.claim_id,
                fencing_token=request.fencing_token,
                tick_version=request.tick_version,
                lease_expires_at=request.lease_expires_at,
                state_receipt_id=state_reference.artifact_id,
                state_receipt_hash=state_reference.content_hash,
                reconciliation_id=None,
                summary_id=None,
                proposal_id=None,
                risk_decision_id=None,
                status="BLOCKED",
                stage_receipts=tuple(stages),
                created_at=request.as_of_time,
            )
            return self._repository.save_runtime_receipt(blocked, claim=claim)
        inputs = governed_inputs

        tolerance = self._repository.record_reconciliation_tolerance(
            inputs.reconciliation_tolerance,
            claim=claim,
        )
        risk_configuration = self._repository.record_risk_configuration(
            inputs.risk_configuration,
            claim=claim,
        )
        if (
            tolerance != inputs.reconciliation_tolerance
            or risk_configuration != inputs.risk_configuration
        ):
            raise ValueError("Decision Configuration authority mismatch")
        settlement_evidence = inputs.position_settlement_evidence
        if settlement_evidence is not None:
            if (
                settlement_evidence.account_id != observation.account_id
                or settlement_evidence.as_of_time != request.as_of_time
            ):
                raise ValueError("Position settlement evidence lineage mismatch")
            settlement_evidence = (
                self._repository.record_position_settlement_evidence(
                    settlement_evidence,
                    claim=claim,
                )
            )
        fill_authority = self._repository.load_fill_derived_account_authority(
            account_id=observation.account_id,
            as_of_time=request.as_of_time,
            settlement_evidence=settlement_evidence,
        )
        fill_authority = self._repository.record_fill_derived_account_authority(
            fill_authority,
            claim=claim,
        )
        self._validate_authority_inputs(inputs, fill_authority.positions)

        reconciliation = reconcile_account(
            observation=observation,
            positions=fill_authority.positions,
            fill_ledger_head=fill_authority.fill_ledger_head,
            fill_ledger_complete=fill_authority.fill_ledger_complete,
            tolerance=tolerance,
            # Manual observation cannot independently corroborate itself.
            # No separate cash/equity authority exists in this work package.
            authoritative_total_equity=None,
            authoritative_available_cash=None,
            authoritative_frozen_cash=None,
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
        self._repository.validate_summary_authority(preview)
        preview = self._repository.save_summary(preview, claim=claim)
        stages.append(_stage(DecisionRuntimeStage.SUMMARY_PREVIEW, preview.summary_id, preview.content_hash))

        proposal = build_research_portfolio_proposal(
            summary=preview,
            observation=observation,
            reconciliation=reconciliation,
            positions=fill_authority.positions,
            configuration=risk_configuration,
            idempotency_key=f"{request.idempotency_key}:portfolio",
        )
        proposal = self._repository.save_proposal(proposal, claim=claim)
        stages.append(_stage(DecisionRuntimeStage.PORTFOLIO_PROPOSAL, proposal.proposal_id, proposal.content_hash))

        risk = IndependentRiskService(self._repository).decide(
            proposal_id=proposal.proposal_id,
            as_of_time=request.as_of_time,
            idempotency_key=f"{request.idempotency_key}:risk",
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
                    else (
                        DecisionWindowState.FINALIZED
                        if risk.result in {
                            IndependentRiskResult.RESEARCH_APPROVED,
                            IndependentRiskResult.RESEARCH_REDUCED,
                        }
                        else DecisionWindowState.BLOCKED
                    )
                ),
                outcome=_risk_outcome(risk.result, preview.outcome),
                manual_observation_id=preview.manual_observation_id,
                reconciliation_id=preview.reconciliation_id,
                lineage=preview.lineage,
                candidates=tuple(
                    replace(item, risk_result=risk.result)
                    for item in preview.candidates
                ),
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
                    lease_expires_at=request.lease_expires_at,
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
            lease_expires_at=request.lease_expires_at,
            state_receipt_id=state_reference.artifact_id,
            state_receipt_hash=state_reference.content_hash,
            reconciliation_id=reconciliation.reconciliation_id,
            summary_id=output_summary.summary_id,
            proposal_id=proposal.proposal_id,
            risk_decision_id=risk.risk_decision_id,
            status=(
                "BLOCKED"
                if output_summary.lifecycle_state is DecisionWindowState.BLOCKED
                else "COMPLETED"
            ),
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
            lease_expires_at=request.lease_expires_at,
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
        required_configurations = {
            inputs.strategy_configuration_id,
            inputs.reconciliation_tolerance.configuration_id,
            inputs.risk_configuration.configuration_id,
        }
        if not required_configurations.issubset(set(lineage.configuration_ids)):
            raise ValueError("Decision Runtime Configuration lineage mismatch")
        configuration_references = {
            item.artifact_id: item.content_hash
            for item in request.configuration_references
        }
        if configuration_references.get(inputs.strategy_configuration_id) != (
            inputs.strategy_configuration_hash
        ):
            raise ValueError(
                "Decision Runtime Strategy Configuration authority mismatch"
            )
        if not inputs.candidates and (lineage.signal_ids or lineage.forecast_ids):
            raise ValueError("Decision Runtime empty Candidate lineage mismatch")

    @staticmethod
    def _validate_authority_inputs(
        inputs: DecisionRuntimeInputs,
        positions: tuple[Any, ...],
    ) -> None:
        position_ids = tuple(sorted((item.snapshot_id for item in positions), key=str))
        if position_ids != inputs.lineage.position_snapshot_ids:
            raise ValueError("Decision Runtime Fill Position lineage mismatch")
        by_symbol = {item.symbol: item for item in positions}
        if any(
            candidate.current_quantity
            != (
                0
                if candidate.symbol not in by_symbol
                else by_symbol[candidate.symbol].total_quantity
            )
            for candidate in inputs.candidates
        ):
            raise ValueError("Decision Candidate current Position mismatch")

    def _apply_model_governance(
        self,
        *,
        request: ChildExecutionRequest,
        inputs: DecisionRuntimeInputs,
    ) -> tuple[DecisionRuntimeInputs | None, DecisionStageReceipt]:
        referenced_model_ids = tuple(
            sorted(
                {
                    str(model_id)
                    for candidate in inputs.candidates
                    for model_id in (
                        candidate.signal_model_id,
                        candidate.forecast_model_id,
                    )
                }
            )
        )
        lineage_by_model = {
            str(item.model_id): item for item in inputs.model_runtime_lineages
        }
        if not referenced_model_ids:
            return None, DecisionStageReceipt(
                DecisionRuntimeStage.MODEL_GOVERNANCE,
                "BLOCKED",
                None,
                None,
                ("MODEL_SELECTION_REQUIRED",),
            )
        if (
            self._model_selector is None
            or len(lineage_by_model) != len(inputs.model_runtime_lineages)
            or set(lineage_by_model) != set(referenced_model_ids)
        ):
            return None, DecisionStageReceipt(
                DecisionRuntimeStage.MODEL_GOVERNANCE,
                "BLOCKED",
                None,
                None,
                ("MODEL_GOVERNANCE_AUTHORITY_UNAVAILABLE",),
            )
        requests: list[ModelSelectionRequest] = []
        for model_id in referenced_model_ids:
            roles = {
                role
                for candidate in inputs.candidates
                for role, candidate_model_id in (
                    ("STATE_SIGNAL", candidate.signal_model_id),
                    ("STATE_FORECAST", candidate.forecast_model_id),
                )
                if str(candidate_model_id) == model_id
            }
            if len(roles) != 1:
                return None, DecisionStageReceipt(
                    DecisionRuntimeStage.MODEL_GOVERNANCE,
                    "BLOCKED",
                    None,
                    None,
                    ("MODEL_SLOT_AMBIGUOUS",),
                )
            slot = next(iter(roles))
            runtime_lineage = lineage_by_model[model_id]
            authority_rejections = (
                ()
                if _decision_runtime_lineage_is_authoritative(
                    runtime_lineage,
                    model_slot=slot,
                    inputs=inputs,
                )
                else ("RUNTIME_LINEAGE_AUTHORITY_MISMATCH",)
            )
            requests.append(
                ModelSelectionRequest.create(
                    runtime_scope="DECISION_SYSTEM",
                    model_slot=slot,
                    purpose=request.authority_mode.runtime_purpose,
                    runtime_lineage=runtime_lineage,
                    selected_at=request.as_of_time,
                    idempotency_key=(
                        f"{request.run_id}:{request.tick_id}:"
                        f"model-selection:{request.authority_mode.value}:"
                        f"{slot}:{model_id}"
                    ),
                    preselection_rejection_codes=authority_rejections,
                )
            )
        receipts = tuple(
            self._model_selector.select(selection_request)
            for selection_request in requests
        )
        rejection_reasons = tuple(
            sorted(
                {
                    reason
                    for receipt in receipts
                    if receipt.status is SelectionStatus.REJECTED
                    for reason in receipt.reason_codes
                }
            )
        )
        production_authorization_missing = (
            request.authority_mode.requires_production_authorization
            and any(not receipt.production_authorized for receipt in receipts)
        )
        if rejection_reasons or production_authorization_missing:
            return None, _model_governance_stage(
                receipts,
                status="BLOCKED",
                reason_codes=(
                    rejection_reasons
                    or ("PRODUCTION_MODEL_AUTHORIZATION_MISSING",)
                ),
            )
        authorized = replace(
            inputs,
            candidates=tuple(
                replace(
                    candidate,
                    model_qualification=DecisionModelQualification.QUALIFIED,
                )
                for candidate in inputs.candidates
            ),
        )
        return authorized, _model_governance_stage(
            receipts,
            status="COMPLETED",
            reason_codes=(
                "PRODUCTION_MODELS_AUTHORIZED"
                if request.authority_mode is RuntimeAuthorityMode.PRODUCTION
                else f"{request.authority_mode.value}_MODELS_SELECTED",
            ),
        )


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
        except KeyError:
            reason = "REQUIRED_DECISION_AUTHORITY_UNAVAILABLE"
            receipt = self._service.blocked(request=request, reason=reason)
        except DecisionWindowBlocked as exc:
            reason = str(exc).strip("'") or "DECISION_WINDOW_BLOCKED"
            receipt = self._service.blocked(request=request, reason=reason)
        except DecisionSystemIntegrityError:
            receipt = self._service.blocked(
                request=request,
                reason="POSTGRESQL_AUTHORITY_INTEGRITY_BLOCKED",
            )
        except DecisionSystemConflict:
            receipt = self._service.blocked(
                request=request,
                reason="DECISION_AUTHORITY_CONFLICT",
            )
        except ValueError:
            reason = "DECISION_INPUT_LINEAGE_BLOCKED"
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


def _model_governance_stage(
    receipts: tuple[Any, ...],
    *,
    status: str,
    reason_codes: tuple[str, ...],
) -> DecisionStageReceipt:
    payload = {
        "schema_version": "decision-model-governance-binding/v1",
        "selection_receipts": [
            {
                "receipt_id": str(item.receipt_id),
                "receipt_hash": item.receipt_hash,
                "status": item.status.value,
                "production_authorized": item.production_authorized,
            }
            for item in sorted(receipts, key=lambda value: str(value.receipt_id))
        ],
    }
    digest = canonical_hash(payload)
    return DecisionStageReceipt(
        DecisionRuntimeStage.MODEL_GOVERNANCE,
        status,
        ArtifactId(
            f"decision-model-governance:{digest.split(':', 1)[1][:24]}"
        ),
        digest,
        tuple(
            sorted(
                set(reason_codes)
                | {
                    f"MODEL_SELECTION_RECEIPT:{item.receipt_id}"
                    for item in receipts
                }
            )
        ),
    )


def _decision_runtime_lineage_is_authoritative(
    runtime_lineage: RuntimeModelLineage,
    *,
    model_slot: str,
    inputs: DecisionRuntimeInputs,
) -> bool:
    if model_slot == "STATE_SIGNAL":
        reference = ArtifactLineageReference(
            "DECISION_SIGNAL_BUNDLE",
            inputs.lineage.signal_bundle_id,
            inputs.lineage.signal_bundle_hash,
        )
    elif model_slot == "STATE_FORECAST":
        reference = ArtifactLineageReference(
            "DECISION_FORECAST_BUNDLE",
            inputs.lineage.forecast_bundle_id,
            inputs.lineage.forecast_bundle_hash,
        )
    else:
        return False
    return (
        runtime_lineage.dataset == reference
        and runtime_lineage.feature_materializations == (reference,)
        and runtime_lineage.universe_id
        == UniverseId(str(inputs.lineage.dynamic_pool_id))
        and runtime_lineage.data_eligibility is inputs.lineage.data_eligibility
    )


def _preview_outcome(inputs: DecisionRuntimeInputs, reconciliation_status: str) -> DailyDecisionOutcome:
    if reconciliation_status != "RECONCILED":
        return DailyDecisionOutcome.RECONCILIATION_REQUIRED
    if any(
        item.model_qualification is not DecisionModelQualification.QUALIFIED
        for item in inputs.candidates
    ):
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
        "schema_version": DECISION_RUNTIME_RECEIPT_SCHEMA,
        "run_id": str(values["run_id"]),
        "tick_id": str(values["tick_id"]),
        "claim_id": values["claim_id"],
        "fencing_token": values["fencing_token"],
        "tick_version": values["tick_version"],
        "lease_expires_at": canonical_datetime(values["lease_expires_at"]),
        "state_receipt_id": str(values["state_receipt_id"]),
        "state_receipt_hash": values["state_receipt_hash"],
        "reconciliation_id": _id_text(values["reconciliation_id"]),
        "summary_id": _id_text(values["summary_id"]),
        "proposal_id": _id_text(values["proposal_id"]),
        "risk_decision_id": _id_text(values["risk_decision_id"]),
        "status": values["status"],
        "stage_receipts": [item.to_canonical_dict() for item in values["stage_receipts"]],
        "created_at": canonical_datetime(values["created_at"]),
    }


def _id_text(value: ArtifactId | None) -> str | None:
    return None if value is None else str(value)


def _optional_id(value: object) -> ArtifactId | None:
    return None if value is None else ArtifactId(_string(value))


def _sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, list):
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


def _string(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("expected non-empty string")
    if value != unicodedata.normalize("NFC", value):
        raise ValueError("string is not Unicode NFC")
    return value


def _instant(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("expected canonical datetime string")
    parsed = datetime.fromisoformat(value)
    if canonical_datetime(parsed) != value:
        raise ValueError("expected canonical UTC-second datetime")
    return parsed


__all__ = [
    "DECISION_RUNTIME_STAGE_ORDER",
    "DecisionRuntimeInputs",
    "DecisionRuntimeReceipt",
    "DecisionRuntimeStage",
    "DecisionStageReceipt",
    "DecisionSystemDelegate",
    "DecisionSystemRuntimeService",
]
