"""Independent research Risk service that reloads PostgreSQL authority inputs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol

from market_regime_alpha.application.decision_system.contracts import (
    AccountReconciliationReport,
    DailyDecisionWindowSummary,
    DecisionRiskConfiguration,
    IndependentRiskDecision,
    IndependentRiskResult,
    ManualAccountObservation,
    ProposalStatus,
    ReconciliationStatus,
    ResearchPortfolioProposal,
)
from market_regime_alpha.application.decision_system.authority import (
    DecisionStateAuthorityContext,
    FillDerivedAccountAuthority,
    PositionSettlementEvidence,
)
from market_regime_alpha.application.decision_system.portfolio import (
    build_research_portfolio_proposal,
)
from market_regime_alpha.core.identity import ArtifactId


class IndependentRiskAuthorityReader(Protocol):
    def get_proposal(self, proposal_id: ArtifactId) -> ResearchPortfolioProposal: ...
    def get_summary(self, summary_id: ArtifactId) -> DailyDecisionWindowSummary: ...
    def get_manual_observation(self, observation_id: ArtifactId) -> ManualAccountObservation: ...
    def get_reconciliation(self, reconciliation_id: ArtifactId) -> AccountReconciliationReport: ...
    def get_risk_configuration(self, configuration_id: ArtifactId) -> DecisionRiskConfiguration: ...
    def validate_summary_authority(self, summary: DailyDecisionWindowSummary) -> None: ...
    def load_fill_derived_account_authority(
        self, *, account_id: str, as_of_time: datetime,
        settlement_evidence: PositionSettlementEvidence | None = None,
    ) -> FillDerivedAccountAuthority: ...
    def get_position_settlement_evidence(
        self, evidence_id: ArtifactId
    ) -> PositionSettlementEvidence: ...
    def get_recorded_fill_derived_account_authority(
        self, *, account_id: str, as_of_time: datetime
    ) -> FillDerivedAccountAuthority: ...
    def get_decision_state_context(
        self, summary: DailyDecisionWindowSummary
    ) -> DecisionStateAuthorityContext: ...
    def get_daily_loss(
        self, *, account_id: str, trading_date: object, as_of_time: datetime
    ) -> Decimal | None: ...


class IndependentRiskService:
    """Trust only a Proposal ID; all proposal inputs are reloaded and rechecked."""

    def __init__(self, reader: IndependentRiskAuthorityReader) -> None:
        self._reader = reader

    def decide(
        self,
        *,
        proposal_id: ArtifactId,
        as_of_time: datetime,
        idempotency_key: str,
    ) -> IndependentRiskDecision:
        proposal = self._reader.get_proposal(proposal_id)
        summary = self._reader.get_summary(proposal.summary_id)
        observation = self._reader.get_manual_observation(
            proposal.manual_observation_id
        )
        reconciliation = self._reader.get_reconciliation(
            proposal.reconciliation_id
        )
        configuration = self._reader.get_risk_configuration(
            proposal.risk_configuration_id
        )
        self._reader.validate_summary_authority(summary)
        fill_authority = self._reader.get_recorded_fill_derived_account_authority(
            account_id=proposal.account_id,
            as_of_time=as_of_time,
        )
        settlement_evidence = (
            None
            if fill_authority.settlement_evidence_id is None
            else self._reader.get_position_settlement_evidence(
                fill_authority.settlement_evidence_id
            )
        )
        if settlement_evidence is not None and (
            settlement_evidence.content_hash
            != fill_authority.settlement_evidence_hash
        ):
            raise ValueError("Independent Risk settlement evidence mismatch")
        live_fill_authority = self._reader.load_fill_derived_account_authority(
            account_id=proposal.account_id,
            as_of_time=as_of_time,
            settlement_evidence=settlement_evidence,
        )
        if live_fill_authority != fill_authority:
            raise ValueError("Independent Risk frozen/live Fill authority mismatch")
        state_context = self._reader.get_decision_state_context(summary)
        daily_loss = self._reader.get_daily_loss(
            account_id=proposal.account_id,
            trading_date=proposal.trading_date,
            as_of_time=as_of_time,
        )
        reasons: set[str] = set()
        result = IndependentRiskResult.RESEARCH_APPROVED
        _same_authority(proposal, summary, observation, reconciliation, configuration)
        fill_position_ids = tuple(
            sorted(
                (item.snapshot_id for item in fill_authority.positions),
                key=str,
            )
        )
        if (
            reconciliation.position_snapshot_ids != fill_position_ids
            or summary.lineage.position_snapshot_ids != fill_position_ids
        ):
            raise ValueError("Independent Risk Fill Position lineage mismatch")
        if (
            reconciliation.fill_ledger_head != fill_authority.fill_ledger_head
            or reconciliation.fill_ledger_complete
            != fill_authority.fill_ledger_complete
        ):
            raise ValueError("Independent Risk Fill Ledger lineage mismatch")
        recomputed = build_research_portfolio_proposal(
            summary=summary,
            observation=observation,
            reconciliation=reconciliation,
            positions=fill_authority.positions,
            configuration=configuration,
            idempotency_key=proposal.idempotency_key,
        )
        if recomputed != proposal:
            raise ValueError("Independent Risk Proposal recomputation mismatch")
        observation_age = (as_of_time - observation.as_of_time).total_seconds()
        data_age = (
            as_of_time - state_context.oldest_available_at
        ).total_seconds()
        scoped_states = tuple(
            value
            for _, value in state_context.etf_states + state_context.theme_states
        ) + (state_context.capital_state,)
        if observation_age < 0 or observation_age > configuration.maximum_observation_age_seconds:
            result = IndependentRiskResult.ACCOUNT_NOT_CALIBRATED
            reasons.add("ACCOUNT_OBSERVATION_STALE")
        elif data_age < 0 or data_age > configuration.maximum_data_age_seconds:
            result = IndependentRiskResult.DATA_INSUFFICIENT
            reasons.add("DECISION_DATA_STALE")
        elif reconciliation.status is not ReconciliationStatus.RECONCILED:
            result = IndependentRiskResult.RECONCILIATION_REQUIRED
            reasons.add("RECONCILIATION_NOT_RESOLVED")
        elif state_context.market_state == "DATA_INSUFFICIENT" or any(
            value == "DATA_INSUFFICIENT" for value in scoped_states
        ):
            result = IndependentRiskResult.DATA_INSUFFICIENT
            reasons.add("STATE_CONTEXT_DATA_INSUFFICIENT")
        elif state_context.market_state == "RISK_OFF":
            result = IndependentRiskResult.RISK_BLOCKED
            reasons.add("MARKET_REGIME_RISK_OFF")
        elif proposal.status is ProposalStatus.MODEL_NOT_QUALIFIED or any(
            item.model_qualification.value != "QUALIFIED" for item in recomputed.lines
        ):
            result = IndependentRiskResult.MODEL_NOT_QUALIFIED
            reasons.add("MODEL_NOT_QUALIFIED")
        elif proposal.status is ProposalStatus.ORDERABILITY_UNKNOWN or any(
            item.orderability.value != "ORDERABLE" for item in recomputed.lines
        ):
            result = IndependentRiskResult.ORDERABILITY_UNKNOWN
            reasons.add("ORDERABILITY_UNKNOWN")
        elif proposal.status not in {ProposalStatus.PROPOSED, ProposalStatus.NO_ACTION}:
            result = IndependentRiskResult.RISK_BLOCKED
            reasons.add(f"PROPOSAL_STATUS_{proposal.status.value}")
        elif not reconciliation.fill_ledger_complete or reconciliation.differences:
            result = IndependentRiskResult.RECONCILIATION_REQUIRED
            reasons.add("FILL_POSITION_AUTHORITY_NOT_RECONCILED")
        elif configuration.daily_loss_limit is not None and daily_loss is None:
            result = IndependentRiskResult.DATA_INSUFFICIENT
            reasons.add("DAILY_LOSS_AUTHORITY_UNAVAILABLE")
        elif daily_loss is not None and configuration.daily_loss_limit is not None and daily_loss > configuration.daily_loss_limit:
            result = IndependentRiskResult.RISK_BLOCKED
            reasons.add("DAILY_LOSS_LIMIT_EXCEEDED")
        else:
            concentration = any(
                item.proposed_research_weight > configuration.maximum_single_symbol_weight
                or item.theme_exposure > configuration.maximum_theme_weight
                or item.single_symbol_exposure > configuration.maximum_single_symbol_weight
                for item in recomputed.lines
            )
            liquidity = any(
                item.liquidity_constraint != "SATISFIED" for item in recomputed.lines
            )
            correlated_groups = _correlated_groups(summary)
            market_reduction = state_context.market_state in {
                "DEFENSIVE", "OVERHEATED"
            }
            if concentration or liquidity or correlated_groups or market_reduction:
                result = IndependentRiskResult.RESEARCH_REDUCED
                if concentration:
                    reasons.add("CONCENTRATION_REDUCED")
                if liquidity:
                    reasons.add("LIQUIDITY_REDUCED")
                if correlated_groups:
                    reasons.add("ETF_THEME_CORRELATION_REDUCED")
                if market_reduction:
                    reasons.add("MARKET_REGIME_RESEARCH_REDUCED")
            else:
                reasons.add("INDEPENDENT_RESEARCH_RISK_CHECKS_PASSED")
        approved = (
            sum((item.proposed_research_weight for item in recomputed.lines), Decimal("0"))
            if result in {
                IndependentRiskResult.RESEARCH_APPROVED,
                IndependentRiskResult.RESEARCH_REDUCED,
            }
            else Decimal("0")
        )
        if approved > Decimal("1"):
            result = IndependentRiskResult.RISK_BLOCKED
            approved = Decimal("0")
            reasons = {"PORTFOLIO_EXPOSURE_EXCEEDS_ONE"}
        return IndependentRiskDecision.create(
            proposal_id=proposal.proposal_id,
            account_id=proposal.account_id,
            trading_date=proposal.trading_date,
            as_of_time=as_of_time,
            result=result,
            approved_research_weight=approved,
            reason_codes=tuple(sorted(reasons)),
            risk_configuration_id=configuration.configuration_id,
            risk_configuration_hash=configuration.configuration_hash,
            idempotency_key=idempotency_key,
            created_at=as_of_time,
        )


def _same_authority(
    proposal: ResearchPortfolioProposal,
    summary: DailyDecisionWindowSummary,
    observation: ManualAccountObservation,
    reconciliation: AccountReconciliationReport,
    configuration: DecisionRiskConfiguration,
) -> None:
    if proposal.risk_configuration_id != configuration.configuration_id or proposal.risk_configuration_hash != configuration.configuration_hash:
        raise ValueError("Risk Configuration lineage mismatch")
    if proposal.account_id != summary.account_id or proposal.account_id != observation.account_id or proposal.account_id != reconciliation.account_id:
        raise ValueError("Independent Risk Account lineage mismatch")
    if proposal.trading_date != summary.trading_date or proposal.trading_date != observation.trading_date or proposal.trading_date != reconciliation.trading_date:
        raise ValueError("Independent Risk TradingDate lineage mismatch")
    if proposal.manual_observation_id != observation.observation_id or proposal.reconciliation_id != reconciliation.reconciliation_id:
        raise ValueError("Independent Risk input identity mismatch")
    if summary.manual_observation_id != observation.observation_id or summary.reconciliation_id != reconciliation.reconciliation_id:
        raise ValueError("Summary authority identity mismatch")
    if reconciliation.manual_observation_id != observation.observation_id:
        raise ValueError("Reconciliation authority identity mismatch")
    if tuple(item.symbol for item in proposal.lines) != tuple(
        item.symbol for item in summary.candidates
    ):
        raise ValueError("Proposal/Summary Candidate lineage mismatch")


def _correlated_groups(summary: DailyDecisionWindowSummary) -> bool:
    etfs = tuple(item.etf for item in summary.candidates if item.etf is not None)
    themes = tuple(item.theme for item in summary.candidates if item.theme is not None)
    return len(etfs) != len(set(etfs)) or len(themes) != len(set(themes))


__all__ = [
    "IndependentRiskAuthorityReader",
    "IndependentRiskService",
]
