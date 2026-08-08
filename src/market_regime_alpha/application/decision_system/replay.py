"""Deterministic Decision System export, PostgreSQL import, and re-execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
import unicodedata

from market_regime_alpha.application.decision_system.authority import (
    DecisionStateAuthorityContext,
    FillDerivedAccountAuthority,
    PositionSettlementEvidence,
)
from market_regime_alpha.application.decision_system.contracts import (
    AccountReconciliationReport,
    DailyDecisionWindowSummary,
    DecisionRiskConfiguration,
    DecisionWindowState,
    IndependentRiskDecision,
    IndependentRiskResult,
    ManualAccountObservation,
    ReconciliationTolerance,
    ResearchPortfolioProposal,
)
from market_regime_alpha.application.decision_system.portfolio import (
    build_research_portfolio_proposal,
)
from market_regime_alpha.application.decision_system.postgres_repository import (
    PostgresDecisionSystemRepository,
)
from market_regime_alpha.application.decision_system.reconciliation import (
    reconcile_account,
)
from market_regime_alpha.application.decision_system.risk import (
    IndependentRiskService,
)
from market_regime_alpha.application.decision_system.runtime import (
    DecisionRuntimeReceipt,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
)
from market_regime_alpha.platform.postgres_runtime_governance import (
    PostgresModelGovernanceRepository,
)


_REPLAY_SCHEMA = "decision-system-replay/v2"
_RUNTIME_INPUT_SCHEMA = "decision-replay-runtime-input/v1"


@dataclass(frozen=True, slots=True)
class DecisionSystemReplayResult:
    run_id: ArtifactId
    tick_id: ArtifactId
    receipt_id: ArtifactId
    receipt_hash: str
    replay_session_id: ArtifactId
    replay_hash: str
    verified_authority_count: int
    reexecuted_authority_count: int
    postgres_import_verified: bool
    entry_authority_granted: bool = False
    broker_authority_granted: bool = False

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": _REPLAY_SCHEMA,
            "run_id": str(self.run_id),
            "tick_id": str(self.tick_id),
            "receipt_id": str(self.receipt_id),
            "receipt_hash": self.receipt_hash,
            "replay_session_id": str(self.replay_session_id),
            "replay_hash": self.replay_hash,
            "verified_authority_count": self.verified_authority_count,
            "reexecuted_authority_count": self.reexecuted_authority_count,
            "postgres_import_verified": self.postgres_import_verified,
            "entry_authority_granted": False,
            "broker_authority_granted": False,
        }


def replay_decision_system(
    repository: PostgresDecisionSystemRepository,
    *,
    run_id: ArtifactId,
    tick_id: ArtifactId,
    replay_repository: PostgresDecisionSystemRepository,
) -> DecisionSystemReplayResult:
    """Export authority, import it into a PG replay schema, and re-execute."""

    source_factory = repository._postgres_factory
    replay_factory = replay_repository._postgres_factory
    if source_factory is replay_factory or (
        source_factory._database_url == replay_factory._database_url
        and source_factory.application_schema == replay_factory.application_schema
    ):
        raise ValueError("Decision Replay requires an isolated PostgreSQL schema")
    artifacts = _export_artifacts(repository, run_id=run_id, tick_id=tick_id)
    session_hash = canonical_hash(
        {
            "schema_version": _REPLAY_SCHEMA,
            "run_id": str(run_id),
            "tick_id": str(tick_id),
            "artifacts": list(artifacts),
        }
    )
    replay_session_id = ArtifactId(
        f"decision-replay-session-{session_hash[7:31]}"
    )
    governance_bundle = next(
        item["payload"]
        for item in artifacts
        if item["artifact_kind"] == "MODEL_GOVERNANCE"
    )
    if not isinstance(governance_bundle, dict):
        raise TypeError("Decision Replay governance bundle must be an object")
    PostgresModelGovernanceRepository(
        replay_factory
    ).import_replay_bundle(governance_bundle)
    imported = replay_repository.import_replay_artifacts(
        replay_session_id=replay_session_id,
        artifacts=artifacts,
    )
    restored = _restore_artifacts(imported)
    reexecuted = _reexecute(
        restored,
        replay_repository=replay_repository,
        replay_session_id=replay_session_id,
    )
    receipt = restored.receipt
    replay_hash = canonical_hash(
        {
            "schema_version": _REPLAY_SCHEMA,
            "replay_session_id": str(replay_session_id),
            "imported_artifacts": list(imported),
            "reexecuted": reexecuted,
        }
    )
    return DecisionSystemReplayResult(
        run_id=run_id,
        tick_id=tick_id,
        receipt_id=receipt.receipt_id,
        receipt_hash=receipt.receipt_hash,
        replay_session_id=replay_session_id,
        replay_hash=replay_hash,
        verified_authority_count=len(imported),
        reexecuted_authority_count=len(reexecuted),
        postgres_import_verified=imported == artifacts,
    )


@dataclass(frozen=True, slots=True)
class _RestoredReplay:
    receipt: DecisionRuntimeReceipt
    observation: ManualAccountObservation
    fill_authority: FillDerivedAccountAuthority
    settlement_evidence: PositionSettlementEvidence | None
    tolerance: ReconciliationTolerance
    reconciliation: AccountReconciliationReport
    preview: DailyDecisionWindowSummary
    proposal: ResearchPortfolioProposal
    risk_configuration: DecisionRiskConfiguration
    risk: IndependentRiskDecision
    terminal: DailyDecisionWindowSummary
    runtime_input: dict[str, Any]
    governance_bundle: dict[str, Any]


def _export_artifacts(
    repository: PostgresDecisionSystemRepository,
    *,
    run_id: ArtifactId,
    tick_id: ArtifactId,
) -> tuple[dict[str, Any], ...]:
    receipt = repository.get_runtime_receipt(run_id=run_id, tick_id=tick_id)
    reconciliation_id = receipt.reconciliation_id
    terminal_summary_id = receipt.summary_id
    proposal_id = receipt.proposal_id
    risk_decision_id = receipt.risk_decision_id
    if (
        reconciliation_id is None
        or terminal_summary_id is None
        or proposal_id is None
        or risk_decision_id is None
    ):
        raise ValueError("Decision Replay requires a complete Decision Runtime receipt")
    reconciliation = repository.get_reconciliation(reconciliation_id)
    terminal = repository.get_summary(terminal_summary_id)
    proposal = repository.get_proposal(proposal_id)
    preview = repository.get_summary(proposal.summary_id)
    risk = repository.get_risk_decision(risk_decision_id)
    observation = repository.get_manual_observation(proposal.manual_observation_id)
    tolerance = repository.get_reconciliation_tolerance(
        reconciliation.tolerance_configuration_id
    )
    risk_configuration = repository.get_risk_configuration(
        proposal.risk_configuration_id
    )
    fill_authority = repository.get_recorded_fill_derived_account_authority(
        account_id=proposal.account_id,
        as_of_time=risk.as_of_time,
    )
    settlement_evidence = (
        None
        if fill_authority.settlement_evidence_id is None
        else repository.get_position_settlement_evidence(
            fill_authority.settlement_evidence_id
        )
    )
    if settlement_evidence is not None and (
        settlement_evidence.content_hash != fill_authority.settlement_evidence_hash
    ):
        raise ValueError("Decision Replay settlement evidence mismatch")
    repository.validate_summary_authority(preview)
    state_context = repository.get_decision_state_context(preview)
    runtime_input = {
        "schema_version": _RUNTIME_INPUT_SCHEMA,
        "run_id": str(run_id),
        "tick_id": str(tick_id),
        "state_receipt_id": str(preview.lineage.state_receipt_id),
        "state_receipt_hash": preview.lineage.state_receipt_hash,
        "state_stages": list(
            repository.get_state_stage_authority(run_id=run_id, tick_id=tick_id)
        ),
        "state_context": {
            "market_state_id": str(preview.lineage.market_state_id),
            "market_state": state_context.market_state,
            "etf_state_ids": [str(item) for item in preview.lineage.etf_state_ids],
            "etf_states": [list(item) for item in state_context.etf_states],
            "theme_state_ids": [str(item) for item in preview.lineage.theme_state_ids],
            "theme_states": [list(item) for item in state_context.theme_states],
            "capital_state_id": str(preview.lineage.capital_state_id),
            "capital_state": state_context.capital_state,
            "oldest_available_at": canonical_datetime(
                state_context.oldest_available_at
            ),
        },
        "daily_loss": None,
    }
    selection_receipt_ids = _selection_receipt_ids(receipt)
    governance_repository = PostgresModelGovernanceRepository(
        repository._postgres_factory
    )
    for selection_receipt_id in selection_receipt_ids:
        governance_repository.replay_selection(selection_receipt_id)
    governance_bundle = governance_repository.export_replay_bundle(
        selection_receipt_ids
    )
    artifacts = [
        _artifact(
            "MODEL_GOVERNANCE",
            f"model-governance:{tick_id}",
            canonical_hash(governance_bundle),
            governance_bundle,
        ),
        _artifact("RUNTIME_INPUT", f"runtime-input:{tick_id}", canonical_hash(runtime_input), runtime_input),
        _artifact("MANUAL_OBSERVATION", observation.observation_id, observation.content_hash, observation.to_canonical_dict()),
        _artifact("FILL_AUTHORITY", fill_authority.authority_id, fill_authority.content_hash, fill_authority.to_canonical_dict()),
        _artifact("RECONCILIATION_TOLERANCE", tolerance.configuration_id, tolerance.configuration_hash, tolerance.to_canonical_dict()),
        _artifact("RECONCILIATION", reconciliation.reconciliation_id, reconciliation.content_hash, reconciliation.to_canonical_dict()),
        _artifact("PREVIEW_SUMMARY", preview.summary_id, preview.content_hash, preview.to_canonical_dict()),
        _artifact("RISK_CONFIGURATION", risk_configuration.configuration_id, risk_configuration.configuration_hash, risk_configuration.to_canonical_dict()),
        _artifact("PORTFOLIO_PROPOSAL", proposal.proposal_id, proposal.content_hash, proposal.to_canonical_dict()),
        _artifact("RISK_DECISION", risk.risk_decision_id, risk.content_hash, risk.to_canonical_dict()),
        _artifact("TERMINAL_SUMMARY", terminal.summary_id, terminal.content_hash, terminal.to_canonical_dict()),
        _artifact("RUNTIME_RECEIPT", receipt.receipt_id, receipt.receipt_hash, receipt.to_canonical_dict()),
    ]
    if settlement_evidence is not None:
        artifacts.append(
            _artifact(
                "SETTLEMENT_EVIDENCE",
                settlement_evidence.evidence_id,
                settlement_evidence.content_hash,
                settlement_evidence.to_canonical_dict(),
            )
        )
    return tuple(
        sorted(artifacts, key=lambda item: (item["artifact_kind"], item["artifact_id"]))
    )


def _artifact(
    kind: str,
    identity: object,
    content_hash: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "artifact_kind": kind,
        "artifact_id": str(identity),
        "content_hash": content_hash,
        "payload": payload,
    }


def _restore_artifacts(artifacts: tuple[dict[str, Any], ...]) -> _RestoredReplay:
    by_kind: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        kind = str(artifact["artifact_kind"])
        if kind in by_kind:
            raise ValueError("Decision Replay contains duplicate Artifact kind")
        payload = artifact["payload"]
        if not isinstance(payload, dict):
            raise TypeError("Decision Replay Artifact payload must be an object")
        if _content_hash(kind, payload) != artifact["content_hash"]:
            raise ValueError("Decision Replay Artifact hash mismatch")
        by_kind[kind] = payload
    expected = {
        "RUNTIME_INPUT", "MANUAL_OBSERVATION", "FILL_AUTHORITY",
        "RECONCILIATION_TOLERANCE", "RECONCILIATION", "PREVIEW_SUMMARY",
        "RISK_CONFIGURATION", "PORTFOLIO_PROPOSAL", "RISK_DECISION",
        "TERMINAL_SUMMARY", "RUNTIME_RECEIPT", "MODEL_GOVERNANCE",
    }
    allowed = expected | {"SETTLEMENT_EVIDENCE"}
    if frozenset(by_kind) not in {frozenset(expected), frozenset(allowed)}:
        raise ValueError("Decision Replay Artifact set mismatch")
    _validate_runtime_input(by_kind["RUNTIME_INPUT"])
    restored = _RestoredReplay(
        receipt=DecisionRuntimeReceipt.from_canonical_dict(by_kind["RUNTIME_RECEIPT"]),
        observation=ManualAccountObservation.from_canonical_dict(by_kind["MANUAL_OBSERVATION"]),
        fill_authority=_fill_authority(by_kind["FILL_AUTHORITY"]),
        settlement_evidence=(
            None
            if "SETTLEMENT_EVIDENCE" not in by_kind
            else PositionSettlementEvidence.from_canonical_dict(
                by_kind["SETTLEMENT_EVIDENCE"]
            )
        ),
        tolerance=ReconciliationTolerance.from_canonical_dict(by_kind["RECONCILIATION_TOLERANCE"]),
        reconciliation=AccountReconciliationReport.from_canonical_dict(by_kind["RECONCILIATION"]),
        preview=DailyDecisionWindowSummary.from_canonical_dict(by_kind["PREVIEW_SUMMARY"]),
        proposal=ResearchPortfolioProposal.from_canonical_dict(by_kind["PORTFOLIO_PROPOSAL"]),
        risk_configuration=DecisionRiskConfiguration.from_canonical_dict(by_kind["RISK_CONFIGURATION"]),
        risk=IndependentRiskDecision.from_canonical_dict(by_kind["RISK_DECISION"]),
        terminal=DailyDecisionWindowSummary.from_canonical_dict(by_kind["TERMINAL_SUMMARY"]),
        runtime_input=by_kind["RUNTIME_INPUT"],
        governance_bundle=by_kind["MODEL_GOVERNANCE"],
    )
    if (
        (restored.settlement_evidence is None)
        != (restored.fill_authority.settlement_evidence_id is None)
        or (
            restored.settlement_evidence is not None
            and (
                restored.settlement_evidence.evidence_id
                != restored.fill_authority.settlement_evidence_id
                or restored.settlement_evidence.content_hash
                != restored.fill_authority.settlement_evidence_hash
            )
        )
    ):
        raise ValueError("Decision Replay settlement evidence linkage mismatch")
    return restored


def _reexecute(
    restored: _RestoredReplay,
    *,
    replay_repository: PostgresDecisionSystemRepository,
    replay_session_id: ArtifactId,
) -> tuple[dict[str, str], ...]:
    report = restored.reconciliation
    recomputed_reconciliation = reconcile_account(
        observation=restored.observation,
        positions=restored.fill_authority.positions,
        fill_ledger_head=restored.fill_authority.fill_ledger_head,
        fill_ledger_complete=restored.fill_authority.fill_ledger_complete,
        tolerance=restored.tolerance,
        authoritative_total_equity=None,
        authoritative_available_cash=None,
        authoritative_frozen_cash=None,
        as_of_time=report.as_of_time,
        revision=report.revision,
        previous_reconciliation_id=report.previous_reconciliation_id,
        idempotency_key=report.idempotency_key,
        created_at=report.created_at,
    )
    if recomputed_reconciliation != report:
        raise ValueError("Decision Replay Reconciliation re-execution mismatch")
    recomputed_proposal = build_research_portfolio_proposal(
        summary=restored.preview,
        observation=restored.observation,
        reconciliation=report,
        positions=restored.fill_authority.positions,
        configuration=restored.risk_configuration,
        idempotency_key=restored.proposal.idempotency_key,
    )
    if recomputed_proposal != restored.proposal:
        raise ValueError("Decision Replay Proposal re-execution mismatch")
    reader = _PostgresReplayAuthorityReader(
        replay_repository,
        replay_session_id=replay_session_id,
    )
    recomputed_risk = IndependentRiskService(reader).decide(
        proposal_id=restored.proposal.proposal_id,
        as_of_time=restored.risk.as_of_time,
        idempotency_key=restored.risk.idempotency_key,
    )
    if recomputed_risk != restored.risk:
        raise ValueError("Decision Replay Risk re-execution mismatch")
    _validate_terminal(restored)
    governance_repository = PostgresModelGovernanceRepository(
        replay_repository._postgres_factory
    )
    selection_replays = tuple(
        {
            "kind": "MODEL_SELECTION",
            "content_hash": governance_repository.replay_selection(
                receipt_id
            ).receipt_hash,
        }
        for receipt_id in _selection_receipt_ids(restored.receipt)
    )
    return (
        {"kind": "RECONCILIATION", "content_hash": report.content_hash},
        {"kind": "PORTFOLIO_PROPOSAL", "content_hash": restored.proposal.content_hash},
        {"kind": "RISK_DECISION", "content_hash": restored.risk.content_hash},
        {"kind": "TERMINAL_SUMMARY", "content_hash": restored.terminal.content_hash},
        *selection_replays,
    )


class _PostgresReplayAuthorityReader:
    """Strict authority Reader that reloads each input from replay PostgreSQL."""

    def __init__(
        self,
        repository: PostgresDecisionSystemRepository,
        *,
        replay_session_id: ArtifactId,
    ) -> None:
        self._repository = repository
        self._replay_session_id = replay_session_id

    def _payload(self, kind: str) -> dict[str, Any]:
        matches = tuple(
            item
            for item in self._repository.get_replay_artifacts(
                self._replay_session_id
            )
            if item["artifact_kind"] == kind
        )
        if len(matches) != 1:
            raise ValueError(f"Decision Replay {kind} authority cardinality mismatch")
        payload = matches[0]["payload"]
        if not isinstance(payload, dict):
            raise TypeError(f"Decision Replay {kind} payload must be an object")
        return payload

    def get_proposal(self, proposal_id: ArtifactId) -> ResearchPortfolioProposal:
        proposal = ResearchPortfolioProposal.from_canonical_dict(
            self._payload("PORTFOLIO_PROPOSAL")
        )
        if proposal_id != proposal.proposal_id:
            raise KeyError(str(proposal_id))
        return proposal

    def get_summary(self, summary_id: ArtifactId) -> DailyDecisionWindowSummary:
        summary = DailyDecisionWindowSummary.from_canonical_dict(
            self._payload("PREVIEW_SUMMARY")
        )
        if summary_id != summary.summary_id:
            raise KeyError(str(summary_id))
        return summary

    def get_manual_observation(self, observation_id: ArtifactId) -> ManualAccountObservation:
        observation = ManualAccountObservation.from_canonical_dict(
            self._payload("MANUAL_OBSERVATION")
        )
        if observation_id != observation.observation_id:
            raise KeyError(str(observation_id))
        return observation

    def get_reconciliation(self, reconciliation_id: ArtifactId) -> AccountReconciliationReport:
        reconciliation = AccountReconciliationReport.from_canonical_dict(
            self._payload("RECONCILIATION")
        )
        if reconciliation_id != reconciliation.reconciliation_id:
            raise KeyError(str(reconciliation_id))
        return reconciliation

    def get_risk_configuration(self, configuration_id: ArtifactId) -> DecisionRiskConfiguration:
        configuration = DecisionRiskConfiguration.from_canonical_dict(
            self._payload("RISK_CONFIGURATION")
        )
        if configuration_id != configuration.configuration_id:
            raise KeyError(str(configuration_id))
        return configuration

    def validate_summary_authority(self, summary: DailyDecisionWindowSummary) -> None:
        runtime_input = self._payload("RUNTIME_INPUT")
        if (
            runtime_input.get("schema_version") != _RUNTIME_INPUT_SCHEMA
            or runtime_input.get("state_receipt_id") != str(summary.lineage.state_receipt_id)
            or runtime_input.get("state_receipt_hash") != summary.lineage.state_receipt_hash
        ):
            raise ValueError("Decision Replay State receipt mismatch")
        stages = {
            str(item["stage"]): item
            for item in runtime_input.get("state_stages", [])
            if isinstance(item, dict)
        }
        expected = {
            "MARKET_REGIME": (summary.lineage.market_state_id, None),
            "DYNAMIC_POOL": (summary.lineage.dynamic_pool_id, None),
            "CANDIDATE": (
                summary.lineage.candidate_binding_id,
                summary.lineage.candidate_binding_hash,
            ),
            "SIGNAL": (
                summary.lineage.signal_bundle_id,
                summary.lineage.signal_bundle_hash,
            ),
            "FORECAST": (
                summary.lineage.forecast_bundle_id,
                summary.lineage.forecast_bundle_hash,
            ),
        }
        for stage, (artifact_id, artifact_hash) in expected.items():
            item = stages.get(stage)
            if item is None or item.get("artifact_id") != str(artifact_id):
                raise ValueError(f"Decision Replay {stage} identity mismatch")
            if artifact_hash is not None and item.get("artifact_hash") != artifact_hash:
                raise ValueError(f"Decision Replay {stage} hash mismatch")
        for stage in ("SIGNAL", "FORECAST"):
            eligibility = stages[stage].get("data_eligibility")
            if (
                eligibility is None
                and summary.lineage.data_eligibility.value != "UNQUALIFIED"
            ) or (
                eligibility is not None
                and eligibility != summary.lineage.data_eligibility.value
            ):
                raise ValueError(
                    f"Decision Replay {stage} DataEligibility mismatch"
                )

        state_context = _state_context_payload(runtime_input)
        if (
            state_context["market_state_id"]
            != str(summary.lineage.market_state_id)
            or tuple(state_context["etf_state_ids"])
            != tuple(str(item) for item in summary.lineage.etf_state_ids)
            or tuple(state_context["theme_state_ids"])
            != tuple(str(item) for item in summary.lineage.theme_state_ids)
            or state_context["capital_state_id"]
            != str(summary.lineage.capital_state_id)
        ):
            raise ValueError("Decision Replay scoped State lineage mismatch")
        for stage in ("ETF_ROTATION", "THEME_ROTATION", "CAPITAL_STATE"):
            if stage not in stages:
                raise ValueError(f"Decision Replay {stage} stage is missing")

    def load_fill_derived_account_authority(
        self, *, account_id: str, as_of_time: datetime,
        settlement_evidence: PositionSettlementEvidence | None = None,
    ) -> FillDerivedAccountAuthority:
        fill_authority = _fill_authority(self._payload("FILL_AUTHORITY"))
        if (
            account_id != fill_authority.account_id
            or as_of_time != fill_authority.as_of_time
        ):
            raise ValueError("Decision Replay Fill authority scope mismatch")
        expected_settlement = (
            None
            if fill_authority.settlement_evidence_id is None
            else self.get_position_settlement_evidence(
                fill_authority.settlement_evidence_id
            )
        )
        if settlement_evidence != expected_settlement:
            raise ValueError("Decision Replay settlement evidence mismatch")
        return fill_authority

    def get_position_settlement_evidence(
        self,
        evidence_id: ArtifactId,
    ) -> PositionSettlementEvidence:
        try:
            evidence = PositionSettlementEvidence.from_canonical_dict(
                self._payload("SETTLEMENT_EVIDENCE")
            )
        except ValueError as exc:
            raise KeyError(str(evidence_id)) from exc
        if evidence.evidence_id != evidence_id:
            raise KeyError(str(evidence_id))
        return evidence

    def get_recorded_fill_derived_account_authority(
        self, *, account_id: str, as_of_time: datetime
    ) -> FillDerivedAccountAuthority:
        fill_authority = _fill_authority(self._payload("FILL_AUTHORITY"))
        return self.load_fill_derived_account_authority(
            account_id=account_id,
            as_of_time=as_of_time,
            settlement_evidence=(
                None
                if fill_authority.settlement_evidence_id is None
                else self.get_position_settlement_evidence(
                    fill_authority.settlement_evidence_id
                )
            ),
        )

    def get_decision_state_context(
        self,
        summary: DailyDecisionWindowSummary,
    ) -> DecisionStateAuthorityContext:
        self.validate_summary_authority(summary)
        payload = _state_context_payload(self._payload("RUNTIME_INPUT"))
        return DecisionStateAuthorityContext(
            market_state=_strict_string(payload["market_state"]),
            etf_states=_scoped_states(payload["etf_states"]),
            theme_states=_scoped_states(payload["theme_states"]),
            capital_state=_strict_string(payload["capital_state"]),
            oldest_available_at=_canonical_instant(
                payload["oldest_available_at"]
            ),
        )

    def get_daily_loss(self, **_: object) -> Decimal | None:
        value = self._payload("RUNTIME_INPUT").get("daily_loss")
        return None if value is None else Decimal(str(value))


def _validate_terminal(restored: _RestoredReplay) -> None:
    terminal = restored.terminal
    if terminal.previous_summary_id != restored.preview.summary_id:
        raise ValueError("Decision Replay terminal Summary lineage mismatch")
    if any(item.risk_result is not restored.risk.result for item in terminal.candidates):
        raise ValueError("Decision Replay terminal Risk result mismatch")
    approved = restored.risk.result in {
        IndependentRiskResult.RESEARCH_APPROVED,
        IndependentRiskResult.RESEARCH_REDUCED,
    }
    if terminal.lifecycle_state is DecisionWindowState.FINALIZED and not approved:
        raise ValueError("Decision Replay Finalized Summary was not Risk-approved")
    if terminal.lifecycle_state is DecisionWindowState.BLOCKED and approved:
        raise ValueError("Decision Replay Blocked Summary conflicts with Risk result")
    if restored.receipt.summary_id != terminal.summary_id:
        raise ValueError("Decision Replay receipt/Summary lineage mismatch")


def _content_hash(kind: str, payload: dict[str, Any]) -> str:
    if kind in {"RUNTIME_INPUT", "MODEL_GOVERNANCE"}:
        return canonical_hash(payload)
    for field in ("content_hash", "configuration_hash", "receipt_hash"):
        value = payload.get(field)
        if isinstance(value, str):
            return value
    raise ValueError(f"Decision Replay {kind} does not expose a content hash")


def _fill_authority(payload: dict[str, Any]) -> FillDerivedAccountAuthority:
    return FillDerivedAccountAuthority.from_canonical_dict(payload)


def _validate_runtime_input(payload: dict[str, Any]) -> None:
    expected = {
        "schema_version", "run_id", "tick_id", "state_receipt_id",
        "state_receipt_hash", "state_stages", "state_context", "daily_loss",
    }
    if set(payload) != expected or payload["schema_version"] != _RUNTIME_INPUT_SCHEMA:
        raise ValueError("Decision Replay Runtime input fields mismatch")
    for name in (
        "run_id", "tick_id", "state_receipt_id", "state_receipt_hash",
    ):
        _strict_string(payload[name])
    require_sha256("Decision Replay state_receipt_hash", payload["state_receipt_hash"])
    stages = payload["state_stages"]
    if not isinstance(stages, list):
        raise TypeError("Decision Replay State stages must be an array")
    for item in stages:
        stage = _strict_object(item)
        if frozenset(stage) not in {
            frozenset(
                {"stage", "artifact_id", "artifact_hash", "available_at"}
            ),
            frozenset(
                {
                    "stage",
                    "artifact_id",
                    "artifact_hash",
                    "data_eligibility",
                    "available_at",
                }
            ),
        }:
            raise ValueError("Decision Replay State stage fields mismatch")
        _strict_string(stage["stage"])
        _strict_string(stage["artifact_id"])
        require_sha256(
            "Decision Replay State stage artifact_hash",
            _strict_string(stage["artifact_hash"]),
        )
        _canonical_instant(stage["available_at"])
        if "data_eligibility" in stage:
            value = stage["data_eligibility"]
            if value is not None:
                _strict_string(value)
    _validate_state_context(payload["state_context"])
    daily_loss = payload["daily_loss"]
    if daily_loss is not None and not isinstance(daily_loss, str):
        raise TypeError("Decision Replay Daily Loss must be canonical text")


def _strict_string(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError("Decision Replay value must be non-empty text")
    if value != unicodedata.normalize("NFC", value):
        raise ValueError("Decision Replay text is not Unicode NFC")
    return value


def _selection_receipt_ids(
    receipt: DecisionRuntimeReceipt,
) -> tuple[ArtifactId, ...]:
    prefix = "MODEL_SELECTION_RECEIPT:"
    result = tuple(
        sorted(
            {
                ArtifactId(reason.removeprefix(prefix))
                for stage in receipt.stage_receipts
                for reason in stage.reason_codes
                if reason.startswith(prefix)
            },
            key=str,
        )
    )
    if not result:
        raise ValueError(
            "Decision Replay receipt lacks Model Selection authority"
        )
    return result


def _canonical_instant(value: object) -> datetime:
    raw = _strict_string(value)
    parsed = datetime.fromisoformat(raw)
    if canonical_datetime(parsed) != raw:
        raise ValueError("Decision Replay instant is not canonical UTC-second text")
    return parsed


def _state_context_payload(runtime_input: dict[str, Any]) -> dict[str, Any]:
    return _strict_object(runtime_input["state_context"])


def _validate_state_context(value: object) -> None:
    payload = _strict_object(value)
    expected = {
        "market_state_id", "market_state", "etf_state_ids", "etf_states",
        "theme_state_ids", "theme_states", "capital_state_id",
        "capital_state", "oldest_available_at",
    }
    if set(payload) != expected:
        raise ValueError("Decision Replay State context fields mismatch")
    for field in (
        "market_state_id", "market_state", "capital_state_id", "capital_state",
    ):
        _strict_string(payload[field])
    for field in ("etf_state_ids", "theme_state_ids"):
        values = payload[field]
        if not isinstance(values, list) or not values:
            raise TypeError("Decision Replay State IDs must be a non-empty array")
        texts = tuple(_strict_string(item) for item in values)
        if texts != tuple(sorted(set(texts))):
            raise ValueError("Decision Replay State IDs must be sorted and unique")
    _scoped_states(payload["etf_states"])
    _scoped_states(payload["theme_states"])
    _canonical_instant(payload["oldest_available_at"])


def _scoped_states(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list) or not value:
        raise TypeError("Decision Replay scoped States must be a non-empty array")
    result: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, list) or len(item) != 2:
            raise TypeError("Decision Replay scoped State must be a pair")
        result.append((_strict_string(item[0]), _strict_string(item[1])))
    restored = tuple(result)
    if restored != tuple(sorted(set(restored))):
        raise ValueError("Decision Replay scoped States must be sorted and unique")
    return restored


def _strict_object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("Decision Replay value must be an object")
    return value


__all__ = ["DecisionSystemReplayResult", "replay_decision_system"]
