from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from market_regime_alpha.application.continuous_research.daily_alpha import (
    DailyAlphaActivationStatus,
    DailyAlphaEvidenceGate,
    DailyAlphaPredictionSnapshot,
    DailyAlphaSymbolProjection,
    EVIDENCE_DEPENDENCY_NOT_SATISFIED,
    assess_daily_alpha_evidence_gate,
)
from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalEvidenceKind,
    HistoricalResearchEvidence,
    ResearchFinding,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash


NOW = datetime(2026, 8, 21, 6, 55, tzinfo=UTC)


def _reference(kind: str, name: str) -> RuntimeArtifactReference:
    return RuntimeArtifactReference(
        kind,
        ArtifactId(name),
        canonical_hash({"kind": kind, "name": name}),
    )


def _validation_reference(kind: str, name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(name),
        canonical_hash({"kind": kind, "name": name}),
    )


def _historical(
    kind: HistoricalEvidenceKind,
    payload: dict[str, str],
) -> HistoricalResearchEvidence:
    return HistoricalResearchEvidence.create(
        run_id=ArtifactId("historical-run"),
        command_hash=canonical_hash({"command": "frozen"}),
        experiment_reference=_validation_reference(
            "RESEARCH_EXPERIMENT_DEFINITION", "experiment"
        ),
        evidence_kind=kind,
        research_question=kind.value,
        classification=ResearchFinding.POSITIVE,
        rationale="frozen result",
        source_references=(_validation_reference("SOURCE", kind.value),),
        metrics=(),
        payload=payload,
        created_at=NOW,
    )


def _symbol() -> DailyAlphaSymbolProjection:
    return DailyAlphaSymbolProjection(
        symbol="600000.SH",
        selection_status="SELECTED",
        candidate_rank=1,
        factor_score="0.75",
        factor_values=(("price_vs_vwap_return:value", "0.01"),),
        factor_contributions=(("price_vs_vwap_return", "0.75"),),
        context=(("market_regime", "RISK_ON"),),
        signal_reference=_reference("SIGNAL_SNAPSHOT", "signal"),
        signal_state="ACTIVE",
        signal_score="0.8",
        forecast_reference=_reference("PATH_FORECAST", "forecast"),
        forecast_expected_return=None,
        forecast_uncertainty=None,
        calibration_status="NOT_CALIBRATED",
        strategy_diagnostic_reference=_reference(
            "MULTI_STRATEGY_CYCLE", "strategy-cycle"
        ),
        reason_codes=("PATH_FORECAST_EXPECTED_RETURN_NOT_IMPLEMENTED",),
    )


def _snapshot(gate: DailyAlphaEvidenceGate) -> DailyAlphaPredictionSnapshot:
    return DailyAlphaPredictionSnapshot.create(
        run_reference=_reference("CONTINUOUS_RESEARCH_RUN", "run"),
        tick_reference=_reference("CONTINUOUS_RUNTIME_TICK", "tick"),
        code_reference=_reference("CONTINUOUS_RUN_CODE_IDENTITY", "code"),
        configuration_references=(_reference("RESEARCH_CONFIGURATION", "config"),),
        provider_evidence_reference=_reference("EVIDENCE_COMMIT", "evidence"),
        dataset_reference=_reference("MARKET_DATA_DATASET", "dataset"),
        universe_reference=_reference("OPERATIONAL_UNIVERSE", "universe"),
        feature_references=(_reference("FEATURE_BUNDLE_V2", "features"),),
        context_references=(
            _reference("RESEARCH_DAILY_SUMMARY", "research-summary"),
        ),
        candidate_reference=_reference("CANDIDATE_SET", "candidates"),
        signal_reference=_reference("STATE_STAGE_SIGNAL", "signal-stage"),
        forecast_references=(_reference("STATE_STAGE_FORECAST", "forecast-stage"),),
        strategy_diagnostic_reference=_reference(
            "MULTI_STRATEGY_CYCLE", "strategy-cycle"
        ),
        evidence_gate=gate,
        trading_date=date(2026, 8, 21),
        decision_time=NOW,
        available_at=NOW,
        symbols=(_symbol(),),
        reason_codes=("DAILY_PREDICTION_FROZEN_BEFORE_OUTCOME",),
    )


def test_daily_snapshot_is_content_addressed_and_replay_stable() -> None:
    first = _snapshot(DailyAlphaEvidenceGate.inactive())
    second = _snapshot(DailyAlphaEvidenceGate.inactive())

    assert first == second
    assert first.snapshot_id == second.snapshot_id
    assert DailyAlphaPredictionSnapshot.from_canonical_dict(
        first.to_canonical_dict()
    ) == first
    assert EVIDENCE_DEPENDENCY_NOT_SATISFIED in first.reason_codes


def test_inactive_gate_cannot_silently_look_successful() -> None:
    with pytest.raises(ValueError, match="dependency reason"):
        DailyAlphaEvidenceGate(
            DailyAlphaActivationStatus.VALIDATED_CHALLENGER_INACTIVE,
            None,
            None,
            None,
            ("ENGINEERING_RUN_COMPLETED",),
        )


def test_gate_requires_explicitly_supported_full_chain() -> None:
    correctness = _historical(
        HistoricalEvidenceKind.ALPHA_CORRECTNESS,
        {"status": "CORRECTNESS_SUPPORTED"},
    )
    external = _historical(
        HistoricalEvidenceKind.EXTERNAL_VALIDATION,
        {"qualification_status": "SUPPORTED"},
    )
    dormant = _historical(
        HistoricalEvidenceKind.CANDIDATE_POLICY,
        {"activation_status": "CHALLENGER_DORMANT", "stability": "STABLE"},
    )
    blocked = assess_daily_alpha_evidence_gate((correctness, external, dormant))
    assert blocked.status is DailyAlphaActivationStatus.VALIDATED_CHALLENGER_INACTIVE
    assert "CANDIDATE_CHALLENGER_NOT_ACTIVE" in blocked.reason_codes

    active = _historical(
        HistoricalEvidenceKind.CANDIDATE_POLICY,
        {"activation_status": "CHALLENGER_ACTIVE", "stability": "STABLE"},
    )
    admitted = assess_daily_alpha_evidence_gate((correctness, external, active))
    assert admitted.status is DailyAlphaActivationStatus.VALIDATED_CHALLENGER_ACTIVE
    assert EVIDENCE_DEPENDENCY_NOT_SATISFIED not in admitted.reason_codes


def test_snapshot_rejects_future_availability() -> None:
    value = _snapshot(DailyAlphaEvidenceGate.inactive())
    payload = value.to_canonical_dict()
    payload["available_at"] = "2026-08-21T06:54:59Z"
    with pytest.raises(ValueError, match="predate DecisionTime"):
        DailyAlphaPredictionSnapshot.from_canonical_dict(payload)
