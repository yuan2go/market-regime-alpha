"""Application service composing verified research into Opportunity and Thesis."""

from __future__ import annotations

from datetime import datetime

from market_regime_alpha.core.identity import (
    OpportunityId,
    ThesisId,
)
from market_regime_alpha.decision.opportunity import (
    TRADING_OPPORTUNITY_SCHEMA,
    DecisionEvidenceReference,
    DecisionModelReference,
    OpportunityState,
    TradingOpportunity,
    transition_opportunity,
)
from market_regime_alpha.decision.repositories import (
    DecisionLifecycleRepository,
    DecisionVersionConflictError,
)
from market_regime_alpha.decision.thesis import (
    TRADING_THESIS_SCHEMA,
    InvalidationCondition,
    ThesisState,
    TradingThesis,
    transition_thesis,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.forecasting.contracts import PathForecast, PathForecastStatus
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.signals.contracts import SignalSnapshot, SignalState


class DecisionLifecycleService:
    def __init__(self, repository: DecisionLifecycleRepository) -> None:
        self._repository = repository

    def create_opportunity(
        self,
        *,
        candidate_set: CandidateSet,
        signal_snapshot: SignalSnapshot,
        path_forecast: PathForecast,
        valid_until: datetime,
        actor: str,
        reason: str,
        created_at: datetime,
        idempotency_key: str,
    ) -> TradingOpportunity:
        _verify_evidence(candidate_set, signal_snapshot, path_forecast)
        if created_at > valid_until:
            raise ValueError("expired evidence cannot create an Opportunity")
        request = {
            "command": "CREATE_OPPORTUNITY",
            "candidate_set_id": str(candidate_set.envelope.artifact_id),
            "candidate_set_hash": candidate_set.envelope.content_hash,
            "signal_snapshot_id": str(signal_snapshot.envelope.artifact_id),
            "signal_snapshot_hash": signal_snapshot.envelope.content_hash,
            "path_forecast_id": str(path_forecast.envelope.artifact_id),
            "path_forecast_hash": path_forecast.envelope.content_hash,
            "valid_until": valid_until.isoformat(),
            "actor": actor,
            "reason": reason,
            "created_at": created_at.isoformat(),
        }
        command_hash = canonical_hash(request)
        resolved = self._repository.resolve_command(
            idempotency_key=idempotency_key, command_hash=command_hash
        )
        if resolved is not None:
            if resolved.opportunity is None:
                raise ValueError("Opportunity command has no Opportunity result")
            return resolved.opportunity
        identity_hash = canonical_hash(
            {
                "candidate_set": request["candidate_set_id"],
                "signal_snapshot": request["signal_snapshot_id"],
                "path_forecast": request["path_forecast_id"],
                "valid_until": request["valid_until"],
            }
        )
        opportunity = TradingOpportunity(
            schema_version=TRADING_OPPORTUNITY_SCHEMA,
            opportunity_id=OpportunityId(
                f"opportunity-{identity_hash.split(':', 1)[1][:24]}"
            ),
            symbol=signal_snapshot.symbol,
            candidate_set=_evidence_reference(candidate_set.envelope),
            signal_snapshot=_evidence_reference(signal_snapshot.envelope),
            path_forecast=_evidence_reference(path_forecast.envelope),
            decision_time=signal_snapshot.envelope.decision_time,
            signal_model=_model_reference(signal_snapshot.envelope),
            forecast_model=_model_reference(path_forecast.envelope),
            valid_until=valid_until,
            state=OpportunityState.OPEN,
            version=0,
            created_at=created_at,
            created_by=actor,
            creation_reason=reason,
            updated_at=created_at,
            last_actor=actor,
            last_reason=reason,
            reason_codes=("VERIFIED_RESEARCH_EVIDENCE_BOUND",),
        )
        result = self._repository.create_opportunity(
            opportunity,
            idempotency_key=idempotency_key,
            command_hash=command_hash,
        )
        assert result.opportunity is not None
        return result.opportunity

    def confirm_opportunity(
        self,
        opportunity_id: OpportunityId,
        *,
        expected_version: int,
        supporting_evidence: tuple[DecisionEvidenceReference, ...],
        invalidation_conditions: tuple[InvalidationCondition, ...],
        time_invalidation: datetime,
        actor: str,
        reason: str,
        confirmed_at: datetime,
        idempotency_key: str,
    ) -> TradingThesis:
        ordered_evidence = tuple(
            sorted(supporting_evidence, key=lambda item: str(item.artifact_id))
        )
        ordered_conditions = tuple(
            sorted(invalidation_conditions, key=lambda item: item.condition_id)
        )
        request = {
            "command": "CONFIRM_OPPORTUNITY",
            "opportunity_id": str(opportunity_id),
            "expected_version": expected_version,
            "supporting_evidence": [
                item.to_canonical_dict() for item in ordered_evidence
            ],
            "invalidation_conditions": [
                item.to_canonical_dict() for item in ordered_conditions
            ],
            "time_invalidation": time_invalidation.isoformat(),
            "actor": actor,
            "reason": reason,
            "confirmed_at": confirmed_at.isoformat(),
        }
        command_hash = canonical_hash(request)
        resolved = self._repository.resolve_command(
            idempotency_key=idempotency_key, command_hash=command_hash
        )
        if resolved is not None:
            if resolved.thesis is None:
                raise ValueError("confirmation command has no Thesis result")
            return resolved.thesis
        opportunity = self._repository.get_opportunity(opportunity_id)
        if opportunity.version != expected_version:
            raise DecisionVersionConflictError("stale Opportunity version")
        if confirmed_at > opportunity.valid_until:
            raise ValueError("expired Opportunity cannot become a Thesis")
        if opportunity.state is not OpportunityState.OPEN:
            raise ValueError("only OPEN Opportunity can become a Thesis")
        required = {
            (opportunity.candidate_set.artifact_id, opportunity.candidate_set.content_hash),
            (opportunity.signal_snapshot.artifact_id, opportunity.signal_snapshot.content_hash),
            (opportunity.path_forecast.artifact_id, opportunity.path_forecast.content_hash),
        }
        provided = {(item.artifact_id, item.content_hash) for item in ordered_evidence}
        if not required.issubset(provided):
            raise ValueError("Thesis omits required Opportunity evidence")
        thesis_hash = canonical_hash(
            {
                "opportunity_id": str(opportunity_id),
                "source_opportunity_version": opportunity.version,
                "supporting_evidence": request["supporting_evidence"],
                "invalidation_conditions": request["invalidation_conditions"],
                "time_invalidation": request["time_invalidation"],
                "actor": actor,
                "reason": reason,
            }
        )
        thesis = TradingThesis(
            schema_version=TRADING_THESIS_SCHEMA,
            thesis_id=ThesisId(f"thesis-{thesis_hash.split(':', 1)[1][:24]}"),
            opportunity_id=opportunity.opportunity_id,
            source_opportunity_version=opportunity.version,
            symbol=opportunity.symbol,
            supporting_evidence=ordered_evidence,
            invalidation_conditions=ordered_conditions,
            time_invalidation=time_invalidation,
            state=ThesisState.APPROVED,
            version=0,
            approved_by=actor,
            approval_reason=reason,
            created_at=confirmed_at,
            updated_at=confirmed_at,
            last_actor=actor,
            last_reason=reason,
        )
        updated = transition_opportunity(
            opportunity,
            to_state=OpportunityState.CONFIRMED_TO_THESIS,
            actor=actor,
            reason=reason,
            changed_at=confirmed_at,
        )
        result = self._repository.confirm_opportunity(
            updated,
            thesis,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            command_hash=command_hash,
        )
        assert result.thesis is not None
        return result.thesis

    def expire_opportunity(
        self,
        opportunity_id: OpportunityId,
        *,
        expected_version: int,
        actor: str,
        reason: str,
        expired_at: datetime,
        idempotency_key: str,
    ) -> TradingOpportunity:
        return self._transition_opportunity(
            opportunity_id,
            expected_version=expected_version,
            to_state=OpportunityState.EXPIRED,
            actor=actor,
            reason=reason,
            changed_at=expired_at,
            idempotency_key=idempotency_key,
        )

    def reject_opportunity(
        self,
        opportunity_id: OpportunityId,
        *,
        expected_version: int,
        actor: str,
        reason: str,
        rejected_at: datetime,
        idempotency_key: str,
    ) -> TradingOpportunity:
        return self._transition_opportunity(
            opportunity_id,
            expected_version=expected_version,
            to_state=OpportunityState.REJECTED,
            actor=actor,
            reason=reason,
            changed_at=rejected_at,
            idempotency_key=idempotency_key,
        )

    def invalidate_thesis(
        self,
        thesis_id: ThesisId,
        *,
        expected_version: int,
        actor: str,
        reason: str,
        invalidated_at: datetime,
        idempotency_key: str,
    ) -> TradingThesis:
        request = {
            "command": "INVALIDATE_THESIS",
            "thesis_id": str(thesis_id),
            "expected_version": expected_version,
            "actor": actor,
            "reason": reason,
            "invalidated_at": invalidated_at.isoformat(),
        }
        command_hash = canonical_hash(request)
        resolved = self._repository.resolve_command(
            idempotency_key=idempotency_key, command_hash=command_hash
        )
        if resolved is not None:
            assert resolved.thesis is not None
            return resolved.thesis
        current = self._repository.get_thesis(thesis_id)
        if current.version != expected_version:
            raise DecisionVersionConflictError("stale Thesis version")
        updated = transition_thesis(
            current,
            to_state=ThesisState.INVALIDATED,
            actor=actor,
            reason=reason,
            changed_at=invalidated_at,
        )
        result = self._repository.transition_thesis(
            updated,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            command_hash=command_hash,
        )
        assert result.thesis is not None
        return result.thesis

    def _transition_opportunity(
        self,
        opportunity_id: OpportunityId,
        *,
        expected_version: int,
        to_state: OpportunityState,
        actor: str,
        reason: str,
        changed_at: datetime,
        idempotency_key: str,
    ) -> TradingOpportunity:
        request = {
            "command": to_state.value,
            "opportunity_id": str(opportunity_id),
            "expected_version": expected_version,
            "actor": actor,
            "reason": reason,
            "changed_at": changed_at.isoformat(),
        }
        command_hash = canonical_hash(request)
        resolved = self._repository.resolve_command(
            idempotency_key=idempotency_key, command_hash=command_hash
        )
        if resolved is not None:
            assert resolved.opportunity is not None
            return resolved.opportunity
        current = self._repository.get_opportunity(opportunity_id)
        if current.version != expected_version:
            raise DecisionVersionConflictError("stale Opportunity version")
        updated = transition_opportunity(
            current,
            to_state=to_state,
            actor=actor,
            reason=reason,
            changed_at=changed_at,
        )
        result = self._repository.transition_opportunity(
            updated,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            command_hash=command_hash,
        )
        assert result.opportunity is not None
        return result.opportunity


def _verify_evidence(
    candidate_set: CandidateSet,
    signal_snapshot: SignalSnapshot,
    path_forecast: PathForecast,
) -> None:
    candidate_set.envelope.verify_payload(candidate_set.artifact_payload())
    signal_snapshot.envelope.verify_payload(signal_snapshot.artifact_payload())
    path_forecast.envelope.verify_payload(path_forecast.artifact_payload())
    if candidate_set.envelope.status != "RESEARCH_READY":
        raise ValueError("Opportunity requires verified RESEARCH_READY CandidateSet")
    if signal_snapshot.signal_state is not SignalState.CONFIRMED_FOR_RESEARCH:
        raise ValueError("Opportunity requires research-confirmed Signal")
    if path_forecast.forecast_status is not PathForecastStatus.AVAILABLE_FOR_RESEARCH:
        raise ValueError("Opportunity requires available PathForecast")
    if signal_snapshot.symbol != path_forecast.symbol:
        raise ValueError("Signal and PathForecast symbol mismatch")
    selected = {item.symbol for item in candidate_set.selected}
    if signal_snapshot.symbol not in selected:
        raise ValueError("Signal symbol is not a selected Candidate")
    if candidate_set.envelope.artifact_id not in signal_snapshot.envelope.input_artifact_ids:
        raise ValueError("SignalSnapshot does not bind CandidateSet")
    if signal_snapshot.envelope.artifact_id not in path_forecast.envelope.input_artifact_ids:
        raise ValueError("PathForecast does not bind SignalSnapshot")
    decision_times = {
        candidate_set.envelope.decision_time,
        signal_snapshot.envelope.decision_time,
        path_forecast.envelope.decision_time,
    }
    if len(decision_times) != 1:
        raise ValueError("Opportunity evidence DecisionTime mismatch")


def _evidence_reference(envelope: object) -> DecisionEvidenceReference:
    from market_regime_alpha.evidence.envelope import ArtifactEnvelope

    if not isinstance(envelope, ArtifactEnvelope):
        raise TypeError("decision evidence requires ArtifactEnvelope")
    return DecisionEvidenceReference(
        artifact_type=envelope.artifact_type,
        artifact_id=envelope.artifact_id,
        content_hash=envelope.content_hash,
        status=envelope.status,
    )


def _model_reference(envelope: object) -> DecisionModelReference:
    from market_regime_alpha.evidence.envelope import ArtifactEnvelope

    if not isinstance(envelope, ArtifactEnvelope):
        raise TypeError("decision model reference requires ArtifactEnvelope")
    if envelope.model_id is None or envelope.model_version is None:
        raise ValueError("Opportunity evidence requires identified model")
    return DecisionModelReference(
        model_id=envelope.model_id,
        model_version=envelope.model_version,
        configuration_id=envelope.configuration_id,
        configuration_hash=envelope.configuration_hash,
    )
