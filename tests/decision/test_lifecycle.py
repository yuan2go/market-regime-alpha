from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.application.trading_lifecycle import DecisionLifecycleService
from market_regime_alpha.core.identity import ArtifactId, ModelId, ThesisId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.decision import (
    DecisionEvidenceReference,
    DecisionVersionConflictError,
    InvalidationCondition,
    InvalidationKind,
    OpportunityState,
    ThesisState,
    TradingThesis,
)
from market_regime_alpha.decision.opportunity import transition_opportunity
from market_regime_alpha.decision.thesis import TRADING_THESIS_SCHEMA
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.evidence.envelope import ArtifactEnvelope, EvidenceAuthority
from market_regime_alpha.forecasting.contracts import (
    CalibrationStatus,
    PathForecast,
    PathForecastStatus,
    ReturnQuantile,
)
from market_regime_alpha.research.candidate_discovery.contracts import (
    CandidateRecord,
    CandidateSelectionStatus,
    CandidateSet,
)
from market_regime_alpha.research.capital_evolution.contracts import CapitalEvolutionState
from market_regime_alpha.research.market_regime.contracts import MarketState
from market_regime_alpha.research.theme_rotation.contracts import RotationState
from market_regime_alpha.signals.contracts import (
    ConfirmationState,
    SignalFamily,
    SignalSnapshot,
    SignalState,
)
from tests.postgres_path_repositories import (
    PostgresDecisionLifecycleRepository,
    postgres_cli_arguments,
    postgres_connection,
)
from market_regime_alpha.strategies.entry import EntryBarrierSpec, build_entry_path_target_contract


TZ = ZoneInfo("Asia/Shanghai")
DECISION = DecisionTime(datetime(2026, 7, 20, 14, 55, tzinfo=TZ))
CREATED = datetime(2026, 7, 20, 15, 0, tzinfo=TZ)
VALID_UNTIL = datetime(2026, 7, 21, 10, 0, tzinfo=TZ)


def _envelope(
    *,
    artifact_type: str,
    payload: dict[str, object],
    status: str,
    configuration: str,
    model: str,
    inputs: tuple[tuple[ArtifactId, str], ...] = (),
) -> ArtifactEnvelope:
    return ArtifactEnvelope.create(
        artifact_type=artifact_type,
        artifact_payload=payload,
        decision_date=DECISION.value.date(),
        decision_time=DECISION,
        created_at=CREATED,
        code_revision="test-revision",
        configuration_id=ArtifactId(configuration),
        configuration_hash=canonical_hash({"configuration": configuration}),
        source_manifest_id=ArtifactId("source-manifest-test"),
        source_manifest_hash="sha256:" + "1" * 64,
        input_artifact_ids=tuple(item[0] for item in inputs),
        input_content_hashes=tuple(item[1] for item in inputs),
        model_id=ModelId(model),
        model_version="test-v1",
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status=status,
        reason_codes=("SYNTHETIC_DECISION_FIXTURE",),
        limitations=("TEST_ONLY", "NO_TRADING_AUTHORITY"),
    )


def _candidate_set(status: str = "RESEARCH_READY") -> CandidateSet:
    record = CandidateRecord(
        symbol="000001.SZ",
        primary_theme_id="theme-bank",
        supporting_theme_ids=(),
        market_regime_status=MarketState.RISK_ON,
        theme_rotation_state=RotationState.STRENGTHENING,
        capital_evolution_state=CapitalEvolutionState.IGNITION,
        market_regime_score=0.5,
        theme_score=0.4,
        capital_evolution_score=0.3,
        candidate_discovery_score=0.6,
        rank=1,
        selection_status=CandidateSelectionStatus.SELECTED,
        reason_codes=("SYNTHETIC_SELECTED",),
        source_feature_ids=(),
        input_artifact_ids=(),
    )
    payload: dict[str, object] = {
        "records": [record.to_canonical_dict()],
        "minimum_candidate_population": 1,
        "reason_codes": ["SYNTHETIC_FIXTURE"],
    }
    return CandidateSet(
        envelope=_envelope(
            artifact_type="CANDIDATE_SET",
            payload=payload,
            status=status,
            configuration="candidate-config-test",
            model="candidate-model-test",
        ),
        records=(record,),
        minimum_candidate_population=1,
        reason_codes=("SYNTHETIC_FIXTURE",),
    )


def _signal(candidate: CandidateSet) -> SignalSnapshot:
    payload: dict[str, object] = {
        "symbol": "000001.SZ",
        "signal_family": SignalFamily.TREND_CONTINUATION.value,
        "signal_state": SignalState.CONFIRMED_FOR_RESEARCH.value,
        "price_action_state": ConfirmationState.CONFIRMED.value,
        "volume_confirmation_state": ConfirmationState.CONFIRMED.value,
        "trend_confirmation_state": ConfirmationState.CONFIRMED.value,
        "vwap_state": ConfirmationState.CONFIRMED.value,
        "overheat_state": ConfirmationState.CONFIRMED.value,
        "signal_score": 1.0,
        "confidence": 1.0,
        "reason_codes": ["SYNTHETIC_SIGNAL"],
    }
    envelope = _envelope(
        artifact_type="SIGNAL_SNAPSHOT",
        payload=payload,
        status=SignalState.CONFIRMED_FOR_RESEARCH.value,
        configuration="signal-config-test",
        model="signal-model-test",
        inputs=((candidate.envelope.artifact_id, candidate.envelope.content_hash),),
    )
    return SignalSnapshot(
        envelope=envelope,
        symbol="000001.SZ",
        signal_family=SignalFamily.TREND_CONTINUATION,
        signal_state=SignalState.CONFIRMED_FOR_RESEARCH,
        price_action_state=ConfirmationState.CONFIRMED,
        volume_confirmation_state=ConfirmationState.CONFIRMED,
        trend_confirmation_state=ConfirmationState.CONFIRMED,
        vwap_state=ConfirmationState.CONFIRMED,
        overheat_state=ConfirmationState.CONFIRMED,
        signal_score=1.0,
        confidence=1.0,
        reason_codes=("SYNTHETIC_SIGNAL",),
    )


def _forecast(signal: SignalSnapshot) -> PathForecast:
    target = build_entry_path_target_contract(
        EntryBarrierSpec(
            upper_return=0.03,
            lower_return=-0.02,
            horizon_sessions=5,
            price_adjustment_basis="RAW_UNADJUSTED_TRADABLE_PRICE_V1",
        )
    )
    quantiles = (ReturnQuantile(0.25, -0.01), ReturnQuantile(0.75, 0.03))
    payload: dict[str, object] = {
        "symbol": "000001.SZ",
        "target_id": str(target.target_id),
        "forecast_horizon": "5_TRADING_SESSIONS",
        "upper_barrier_return": 0.03,
        "lower_barrier_return": -0.02,
        "expected_mfe": 0.04,
        "expected_mae": -0.015,
        "return_quantiles": [
            {"probability": item.probability, "return_value": item.return_value}
            for item in quantiles
        ],
        "calibration_status": CalibrationStatus.NOT_CALIBRATED.value,
        "forecast_status": PathForecastStatus.AVAILABLE_FOR_RESEARCH.value,
        "usable_sample_count": 10,
        "excluded_sample_count": 1,
        "reason_codes": ["SYNTHETIC_PATH"],
    }
    envelope = _envelope(
        artifact_type="PATH_FORECAST",
        payload=payload,
        status=PathForecastStatus.AVAILABLE_FOR_RESEARCH.value,
        configuration="path-config-test",
        model="path-model-test",
        inputs=((signal.envelope.artifact_id, signal.envelope.content_hash),),
    )
    return PathForecast(
        envelope=envelope,
        symbol="000001.SZ",
        target_id=target.target_id,
        forecast_horizon="5_TRADING_SESSIONS",
        upper_barrier_return=0.03,
        lower_barrier_return=-0.02,
        expected_mfe=0.04,
        expected_mae=-0.015,
        return_quantiles=quantiles,
        calibration_status=CalibrationStatus.NOT_CALIBRATED,
        forecast_status=PathForecastStatus.AVAILABLE_FOR_RESEARCH,
        usable_sample_count=10,
        excluded_sample_count=1,
        reason_codes=("SYNTHETIC_PATH",),
    )


def _service(tmp_path):
    repository = PostgresDecisionLifecycleRepository(tmp_path / "decision.postgres-scope")
    return DecisionLifecycleService(repository), repository


def _create(service: DecisionLifecycleService):
    candidate = _candidate_set()
    signal = _signal(candidate)
    forecast = _forecast(signal)
    opportunity = service.create_opportunity(
        candidate_set=candidate,
        signal_snapshot=signal,
        path_forecast=forecast,
        valid_until=VALID_UNTIL,
        actor="researcher-a",
        reason="manual review requested",
        created_at=CREATED,
        idempotency_key="create-opportunity-1",
    )
    return opportunity, candidate, signal, forecast


def _evidence(candidate, signal, forecast):
    return tuple(
        sorted(
            (
                DecisionEvidenceReference(
                    item.artifact_type,
                    item.artifact_id,
                    item.content_hash,
                    item.status,
                )
                for item in (
                    candidate.envelope,
                    signal.envelope,
                    forecast.envelope,
                )
            ),
            key=lambda item: str(item.artifact_id),
        )
    )


def _conditions():
    return (
        InvalidationCondition(
            condition_id="price-invalid-v1",
            kind=InvalidationKind.PRICE,
            description="Operator-verified price invalidation from explicit profile",
            reason_code="PRICE_INVALIDATION_REACHED",
        ),
    )


def test_opportunity_to_thesis_is_atomic_versioned_and_restorable(tmp_path) -> None:
    service, repository = _service(tmp_path)
    opportunity, candidate, signal, forecast = _create(service)

    thesis = service.confirm_opportunity(
        opportunity.opportunity_id,
        expected_version=0,
        supporting_evidence=_evidence(candidate, signal, forecast),
        invalidation_conditions=_conditions(),
        time_invalidation=CREATED + timedelta(days=5),
        actor="approver-a",
        reason="approved for manual consideration",
        confirmed_at=CREATED + timedelta(minutes=5),
        idempotency_key="confirm-opportunity-1",
    )

    restored_repository = PostgresDecisionLifecycleRepository(repository.path)
    restored_opportunity = restored_repository.get_opportunity(opportunity.opportunity_id)
    assert restored_opportunity.state is OpportunityState.CONFIRMED_TO_THESIS
    assert restored_opportunity.version == 1
    assert restored_repository.get_thesis(thesis.thesis_id) == thesis
    assert thesis.state is ThesisState.APPROVED
    assert thesis.source_opportunity_version == 0
    completed = subprocess.run(
        [
                sys.executable,
                "scripts/run_decision_lifecycle.py",
                *postgres_cli_arguments(repository.path),
            "show-thesis",
            "--thesis-id",
            str(thesis.thesis_id),
        ],
        cwd=Path(__file__).parents[2],
        check=True,
        capture_output=True,
        text=True,
    )
    assert str(thesis.thesis_id) in completed.stdout


def test_expired_opportunity_cannot_become_thesis(tmp_path) -> None:
    service, _ = _service(tmp_path)
    opportunity, candidate, signal, forecast = _create(service)

    with pytest.raises(ValueError, match="expired Opportunity"):
        service.confirm_opportunity(
            opportunity.opportunity_id,
            expected_version=0,
            supporting_evidence=_evidence(candidate, signal, forecast),
            invalidation_conditions=_conditions(),
            time_invalidation=VALID_UNTIL + timedelta(days=1),
            actor="approver-a",
            reason="late approval",
            confirmed_at=VALID_UNTIL + timedelta(seconds=1),
            idempotency_key="late-confirm",
        )


def test_non_ready_candidate_artifact_fails_closed(tmp_path) -> None:
    service, _ = _service(tmp_path)
    candidate = _candidate_set(status="RESEARCH_BLOCKED")
    signal = _signal(candidate)
    forecast = _forecast(signal)

    with pytest.raises(ValueError, match="RESEARCH_READY"):
        service.create_opportunity(
            candidate_set=candidate,
            signal_snapshot=signal,
            path_forecast=forecast,
            valid_until=VALID_UNTIL,
            actor="researcher-a",
            reason="should fail",
            created_at=CREATED,
            idempotency_key="blocked-create",
        )


def test_duplicate_confirmation_is_idempotent_and_conflicting_key_rejected(tmp_path) -> None:
    service, _ = _service(tmp_path)
    opportunity, candidate, signal, forecast = _create(service)
    kwargs = {
        "expected_version": 0,
        "supporting_evidence": _evidence(candidate, signal, forecast),
        "invalidation_conditions": _conditions(),
        "time_invalidation": CREATED + timedelta(days=5),
        "actor": "approver-a",
        "reason": "approved once",
        "confirmed_at": CREATED + timedelta(minutes=5),
        "idempotency_key": "confirm-idempotent",
    }

    first = service.confirm_opportunity(opportunity.opportunity_id, **kwargs)
    second = service.confirm_opportunity(opportunity.opportunity_id, **kwargs)
    assert first == second

    with pytest.raises(ValueError, match="idempotency key reused"):
        service.confirm_opportunity(
            opportunity.opportunity_id,
            **{**kwargs, "reason": "different command"},
        )


def test_concurrent_stale_confirmation_has_one_winner(tmp_path) -> None:
    service_a, repository = _service(tmp_path)
    opportunity, candidate, signal, forecast = _create(service_a)
    service_b = DecisionLifecycleService(
        PostgresDecisionLifecycleRepository(repository.path)
    )

    service_a.reject_opportunity(
        opportunity.opportunity_id,
        expected_version=0,
        actor="approver-a",
        reason="rejected first",
        rejected_at=CREATED + timedelta(minutes=1),
        idempotency_key="reject-first",
    )
    with pytest.raises(DecisionVersionConflictError, match="stale Opportunity"):
        service_b.confirm_opportunity(
            opportunity.opportunity_id,
            expected_version=0,
            supporting_evidence=_evidence(candidate, signal, forecast),
            invalidation_conditions=_conditions(),
            time_invalidation=CREATED + timedelta(days=5),
            actor="approver-b",
            reason="stale approval",
            confirmed_at=CREATED + timedelta(minutes=2),
            idempotency_key="stale-confirm",
        )


def test_thesis_invalidation_is_append_only_and_recoverable(tmp_path) -> None:
    service, repository = _service(tmp_path)
    opportunity, candidate, signal, forecast = _create(service)
    thesis = service.confirm_opportunity(
        opportunity.opportunity_id,
        expected_version=0,
        supporting_evidence=_evidence(candidate, signal, forecast),
        invalidation_conditions=_conditions(),
        time_invalidation=CREATED + timedelta(days=5),
        actor="approver-a",
        reason="approved",
        confirmed_at=CREATED + timedelta(minutes=5),
        idempotency_key="confirm-before-invalidate",
    )
    invalidated = service.invalidate_thesis(
        thesis.thesis_id,
        expected_version=0,
        actor="reviewer-a",
        reason="price condition met",
        invalidated_at=CREATED + timedelta(hours=1),
        idempotency_key="invalidate-thesis-1",
    )

    assert invalidated.state is ThesisState.INVALIDATED
    assert invalidated.version == 1
    assert repository.get_thesis(thesis.thesis_id) == invalidated
    with postgres_connection(repository.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM thesis_events").fetchone()[0] == 2


def test_repository_rejects_forged_confirmation_that_bypasses_service(tmp_path) -> None:
    service, repository = _service(tmp_path)
    opportunity, _, signal, _ = _create(service)
    confirmed_at = CREATED + timedelta(minutes=5)
    updated = transition_opportunity(
        opportunity,
        to_state=OpportunityState.CONFIRMED_TO_THESIS,
        actor="forger",
        reason="bypass attempt",
        changed_at=confirmed_at,
    )
    forged = TradingThesis(
        schema_version=TRADING_THESIS_SCHEMA,
        thesis_id=ThesisId("thesis-forged-test"),
        opportunity_id=opportunity.opportunity_id,
        source_opportunity_version=0,
        symbol=opportunity.symbol,
        supporting_evidence=(
            DecisionEvidenceReference(
                signal.envelope.artifact_type,
                signal.envelope.artifact_id,
                signal.envelope.content_hash,
                signal.envelope.status,
            ),
        ),
        invalidation_conditions=_conditions(),
        time_invalidation=CREATED + timedelta(days=5),
        state=ThesisState.APPROVED,
        version=0,
        approved_by="forger",
        approval_reason="bypass attempt",
        created_at=confirmed_at,
        updated_at=confirmed_at,
        last_actor="forger",
        last_reason="bypass attempt",
    )

    with pytest.raises(ValueError, match="omits required Opportunity evidence"):
        repository.confirm_opportunity(
            updated,
            forged,
            expected_version=0,
            idempotency_key="forged-confirmation",
            command_hash=canonical_hash({"forged": True}),
        )
