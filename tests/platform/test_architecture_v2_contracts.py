from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.decision.contracts import TradeDecisionState
from market_regime_alpha.forecasting.contracts import (
    CalibrationStatus,
    NextSessionForecast,
)
from market_regime_alpha.platform.architecture_v2 import (
    PLATFORM_V2_BOUNDARIES,
    PlatformLayer,
)


def test_all_six_platform_layers_have_exclusive_boundaries() -> None:
    assert tuple(item.layer for item in PLATFORM_V2_BOUNDARIES) == tuple(
        PlatformLayer
    )
    assert all(
        not (set(item.owned_outputs) & set(item.forbidden_outputs))
        for item in PLATFORM_V2_BOUNDARIES
    )


def test_production_lifecycle_outputs_remain_in_existing_six_layers() -> None:
    by_layer = {item.layer: item for item in PLATFORM_V2_BOUNDARIES}
    assert {
        "TradingOpportunity",
        "TradingThesis",
        "PortfolioDecision",
        "RiskDecision",
    }.issubset(by_layer[PlatformLayer.TRADE_DECISION_RISK].owned_outputs)
    assert {
        "ManualTradeRecord",
        "Fill",
        "PositionSnapshot",
        "HoldingAssessment",
        "ExitAssessment",
    }.issubset(
        by_layer[PlatformLayer.POSITION_LIFECYCLE_EXECUTION].owned_outputs
    )
    assert {
        "TradeOutcome",
        "AttributionRecord",
        "RollingScorecard",
    }.issubset(by_layer[PlatformLayer.OUTCOME_EVALUATION_LEARNING].owned_outputs)


def test_trade_decision_vocabulary_has_no_live_actions() -> None:
    assert {item.value for item in TradeDecisionState} == {
        "REJECT",
        "WATCH",
        "WAIT_CONFIRMATION",
        "ENTER_SIMULATION",
    }
    assert "BUY" not in TradeDecisionState.__members__
    assert "SELL" not in TradeDecisionState.__members__


def test_uncalibrated_forecast_cannot_carry_probability() -> None:
    from market_regime_alpha.core.identity import ArtifactId, ModelId, TargetId
    from market_regime_alpha.core.time import DecisionTime
    from market_regime_alpha.data.contracts import DataEligibility
    from market_regime_alpha.evidence.envelope import (
        ArtifactEnvelope,
        EvidenceAuthority,
    )

    payload = {
        "symbol": "600001.SH",
        "forecast_horizon": "NEXT_SESSION",
        "target_id": "target",
        "probability_positive_return": None,
        "expected_return": None,
        "return_quantiles": [],
        "expected_adverse_excursion": None,
        "expected_favorable_excursion": None,
        "confidence": 0.0,
        "calibration_status": "NOT_CALIBRATED",
        "reason_codes": ["FORECAST_MODEL_NOT_IMPLEMENTED"],
    }
    decision_time = DecisionTime(
        datetime(2026, 7, 29, 14, 55, tzinfo=ZoneInfo("Asia/Shanghai"))
    )
    envelope = ArtifactEnvelope.create(
        artifact_type="NEXT_SESSION_FORECAST",
        artifact_payload=payload,
        decision_date=date(2026, 7, 29),
        decision_time=decision_time,
        created_at=datetime(
            2026, 7, 29, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")
        ),
        code_revision="test",
        configuration_id=ArtifactId("forecast-contract-config"),
        configuration_hash="sha256:" + "1" * 64,
        source_manifest_id=ArtifactId("source-manifest-contract"),
        source_manifest_hash="sha256:" + "2" * 64,
        input_artifact_ids=(ArtifactId("candidate-set-contract"),),
        input_content_hashes=("sha256:" + "3" * 64,),
        model_id=ModelId("forecast-contract-only"),
        model_version="0.0.0",
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status="DATA_INSUFFICIENT",
        reason_codes=("FORECAST_MODEL_NOT_IMPLEMENTED",),
        limitations=("CONTRACT_ONLY",),
    )
    forecast = NextSessionForecast(
        envelope=envelope,
        symbol="600001.SH",
        forecast_horizon="NEXT_SESSION",
        target_id=TargetId("target"),
        probability_positive_return=None,
        expected_return=None,
        return_quantiles=(),
        expected_adverse_excursion=None,
        expected_favorable_excursion=None,
        confidence=0.0,
        calibration_status=CalibrationStatus.NOT_CALIBRATED,
        reason_codes=("FORECAST_MODEL_NOT_IMPLEMENTED",),
    )
    with pytest.raises(ValueError, match="calibration"):
        replace(forecast, probability_positive_return=0.60)
