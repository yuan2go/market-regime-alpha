from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.application.trading_lifecycle import (
    LifecycleReviewApplicationService,
    publish_lifecycle_review,
    replay_lifecycle_review,
)
from market_regime_alpha.core.identity import (
    ArtifactId,
    FillId,
    ManualTradeId,
    OpportunityId,
    ThesisId,
)
from market_regime_alpha.decision import (
    DecisionEvidenceReference,
    InvalidationCondition,
    InvalidationKind,
    ThesisState,
    TradingThesis,
)
from market_regime_alpha.decision.thesis import TRADING_THESIS_SCHEMA
from market_regime_alpha.evaluation import (
    TRADE_EVALUATION_CONFIG_SCHEMA,
    TradeEvaluationConfig,
    TradePathObservation,
)
from market_regime_alpha.execution import ExecutionDeviation, Fill, FillKind, TradeSide
from market_regime_alpha.execution.manual import FILL_SCHEMA
from market_regime_alpha.position import (
    POSITION_LIFECYCLE_CONFIG_SCHEMA,
    PositionLifecycleAction,
    PositionLifecycleConfig,
    ThesisHealthObservation,
)


TZ = ZoneInfo("Asia/Shanghai")
ENTRY = datetime(2026, 7, 20, 14, 55, tzinfo=TZ)
ASSESS = datetime(2026, 7, 22, 14, 55, tzinfo=TZ)
EXIT = datetime(2026, 7, 23, 14, 55, tzinfo=TZ)
EVALUATED = EXIT + timedelta(minutes=10)
SYMBOL = "000001.SZ"


def _reference(name: str, artifact_type: str) -> DecisionEvidenceReference:
    return DecisionEvidenceReference(
        artifact_type=artifact_type,
        artifact_id=ArtifactId(name),
        content_hash="sha256:" + "9" * 64,
        status="VERIFIED_EXPLORATORY",
    )


def _thesis() -> TradingThesis:
    return TradingThesis(
        schema_version=TRADING_THESIS_SCHEMA,
        thesis_id=ThesisId("thesis-full-lifecycle-replay"),
        opportunity_id=OpportunityId("opportunity-full-lifecycle-replay"),
        source_opportunity_version=0,
        symbol=SYMBOL,
        supporting_evidence=(
            _reference("candidate-full-replay", "CANDIDATE_SET"),
            _reference("path-full-replay", "PATH_FORECAST"),
            _reference("signal-full-replay", "SIGNAL_SNAPSHOT"),
        ),
        invalidation_conditions=(
            InvalidationCondition(
                condition_id="theme-support-lost",
                kind=InvalidationKind.THEME,
                description="synthetic invalidation for replay",
                reason_code="SYNTHETIC_THEME_INVALIDATION",
            ),
        ),
        time_invalidation=EXIT + timedelta(days=1),
        state=ThesisState.APPROVED,
        version=0,
        approved_by="approver-a",
        approval_reason="synthetic full lifecycle fixture",
        created_at=ENTRY - timedelta(minutes=5),
        updated_at=ENTRY - timedelta(minutes=5),
        last_actor="approver-a",
        last_reason="synthetic full lifecycle fixture",
    )


def _fill(
    fill_id: str,
    trade_id: str,
    side: TradeSide,
    quantity: int,
    price: float,
    occurred_at: datetime,
) -> Fill:
    return Fill(
        schema_version=FILL_SCHEMA,
        fill_id=FillId(fill_id),
        manual_trade_id=ManualTradeId(trade_id),
        account_id="account-a",
        symbol=SYMBOL,
        side=side,
        quantity=quantity,
        price=price,
        fees=0.0,
        occurred_at=occurred_at,
        recorded_at=occurred_at + timedelta(seconds=1),
        actor="human-a",
        reason="synthetic manual lifecycle record",
        external_fill_id=f"external-{fill_id}",
        fill_kind=FillKind.EXECUTION,
        correction_of_fill_id=None,
    )


def _review():
    entry = _fill("fill-full-entry", "trade-full-entry", TradeSide.BUY, 100, 10.0, ENTRY)
    exit_fill = _fill("fill-full-exit", "trade-full-exit", TradeSide.SELL, 100, 10.8, EXIT)
    assessment_config = PositionLifecycleConfig.create(
        profile_id="synthetic_holding_exit_profile_v1",
        add_minimum_return=0.05,
        weakening_return_threshold=-0.03,
        exit_return_threshold=-0.08,
        enable_add_assessment=True,
        market_scope="A_SHARE",
        allowed_side="LONG_ONLY",
        schema_version=POSITION_LIFECYCLE_CONFIG_SCHEMA,
    )
    evaluation_config = TradeEvaluationConfig.create(
        profile_id="synthetic_trade_evaluation_v1",
        rolling_window_size=20,
        minimum_sample_count=1,
        capture_denominator_floor=0.001,
        schema_version=TRADE_EVALUATION_CONFIG_SCHEMA,
    )
    health = ThesisHealthObservation(
        symbol=SYMBOL,
        market_price=10.5,
        observed_at=ASSESS - timedelta(seconds=2),
        availability_time=ASSESS - timedelta(seconds=1),
        signal_support=True,
        theme_support=False,
        capital_support=True,
        triggered_condition_ids=("theme-support-lost",),
        evidence=_reference("health-full-replay", "THESIS_HEALTH_EVIDENCE"),
        missing_reason_codes=(),
    )
    path = TradePathObservation(
        symbol=SYMBOL,
        path_started_at=ENTRY,
        path_ended_at=EXIT,
        availability_time=EXIT + timedelta(minutes=5),
        maximum_price=11.2,
        minimum_price=9.6,
        entry_reference_price=10.0,
        entry_fill_ids=(entry.fill_id,),
        evidence=_reference("trade-path-full-replay", "TRADE_PATH_OBSERVATION"),
    )
    deviations = (
        ExecutionDeviation(
            manual_trade_id=entry.manual_trade_id,
            intended_quantity=100,
            effective_filled_quantity=100,
            quantity_deviation=0,
            volume_weighted_price=10.0,
            expected_mid_price=10.0,
            price_deviation=0.0,
        ),
        ExecutionDeviation(
            manual_trade_id=exit_fill.manual_trade_id,
            intended_quantity=100,
            effective_filled_quantity=100,
            quantity_deviation=0,
            volume_weighted_price=10.8,
            expected_mid_price=10.8,
            price_deviation=0.0,
        ),
    )
    return LifecycleReviewApplicationService().run(
        thesis=_thesis(),
        assessment_configuration=assessment_config,
        health_observation=health,
        assessed_at=ASSESS,
        evaluation_configuration=evaluation_config,
        path_observation=path,
        fills=(entry, exit_fill),
        execution_deviations=deviations,
        prior_outcomes=(),
        actor="reviewer-a",
        reason="synthetic complete lifecycle replay",
        evaluated_at=EVALUATED,
        code_revision="synthetic-test-revision",
    )


def test_complete_manual_trade_lifecycle_publishes_idempotently_and_replays(tmp_path) -> None:
    review = _review()
    assert review.assessment_position.total_quantity == 100
    assert review.holding_assessment.action is PositionLifecycleAction.WAIT
    assert review.exit_assessment.action is PositionLifecycleAction.EXIT
    assert review.final_position.total_quantity == 0
    assert review.trade_outcome.realized_pnl == pytest.approx(80.0)

    path = publish_lifecycle_review(root=tmp_path / "artifacts", review=review)
    assert publish_lifecycle_review(root=tmp_path / "artifacts", review=review) == path
    assert replay_lifecycle_review(path).review == review

    completed = subprocess.run(
        [sys.executable, "scripts/replay_lifecycle_review.py", str(path)],
        cwd=Path(__file__).parents[2],
        check=True,
        capture_output=True,
        text=True,
    )
    assert str(review.artifact_id) in completed.stdout

    input_path = tmp_path / "review-input.json"
    input_path.write_text(
        json.dumps(review.input_payload(), ensure_ascii=False), encoding="utf-8"
    )
    run_completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_lifecycle_review.py",
            "--input",
            str(input_path),
            "--artifact-root",
            str(tmp_path / "cli-artifacts"),
        ],
        cwd=Path(__file__).parents[2],
        check=True,
        capture_output=True,
        text=True,
    )
    assert str(review.artifact_id) in run_completed.stdout


def test_lifecycle_review_detects_artifact_tampering(tmp_path) -> None:
    review = _review()
    path = publish_lifecycle_review(root=tmp_path / "artifacts", review=review)
    artifact_path = path / "artifact.json"
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    payload["actor"] = "tampered-actor"
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        replay_lifecycle_review(path)
