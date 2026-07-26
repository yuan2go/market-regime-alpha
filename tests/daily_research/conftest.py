from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    ModelId,
    ProviderId,
    TargetId,
    UniverseId,
)
from market_regime_alpha.core.time import AsOfTime, AvailabilityTime, DecisionTime
from market_regime_alpha.daily_research.artifacts import publish_daily_quant_decision_artifact
from market_regime_alpha.daily_research.contracts import (
    CandidateRecommendation,
    DailyDataAuthority,
    DailyResearchSnapshot,
    DecisionDataQuality,
    DecisionSourceArtifact,
    EntryAssessment,
    EntryState,
    InstrumentType,
    PriceZone,
    ScoreComponent,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
DECISION = datetime(2026, 7, 23, 14, 55, tzinfo=SHANGHAI)


def make_snapshot(
    *,
    created_at: datetime | None = None,
    source_observed_at: datetime | None = None,
    source_available_at: datetime | None = None,
    source_artifacts: tuple[DecisionSourceArtifact, ...] | None = None,
    authority: DailyDataAuthority = DailyDataAuthority.AUXILIARY,
) -> DailyResearchSnapshot:
    observed_at = source_observed_at or DECISION - timedelta(minutes=1)
    available_at = source_available_at or max(DECISION, observed_at)
    identities = (
        "auxiliary-market-data-example-v1",
        "candidate-model-example-v1",
        "daily-config-example-v1",
        "daily-stock-universe-example-v1",
        "entry-config-example-v1",
        "entry-path-short-v1",
        "entry-policy-example-v1",
        "etf-snapshot-unavailable-v1",
        "feature-individual-strength-example-v1",
        "feature-registry-example-v1",
        "feature-risk-penalty-example-v1",
        "manual-holdings-empty-v1",
        "market-context-unavailable-v1",
        "theme-snapshot-unavailable-v1",
    )
    sources = source_artifacts or tuple(
        DecisionSourceArtifact(
            artifact_id=ArtifactId(identity),
            provider_id=ProviderId("AUXILIARY_EXAMPLE"),
            content_hash="sha256:" + f"{index:x}" * 64,
            observed_at=AsOfTime(observed_at),
            available_at=AvailabilityTime(available_at),
            data_authority=authority,
        )
        for index, identity in enumerate(identities, start=1)
    )
    return DailyResearchSnapshot(
        decision_date=date(2026, 7, 23),
        decision_time=DecisionTime(DECISION),
        timezone="Asia/Shanghai",
        universe_identity=UniverseId("daily-stock-universe-example-v1"),
        market_data_identity=DatasetId("auxiliary-market-data-example-v1"),
        feature_registry_identity=ArtifactId("feature-registry-example-v1"),
        registered_component_identities=(
            ArtifactId("feature-individual-strength-example-v1"),
            ArtifactId("feature-risk-penalty-example-v1"),
        ),
        model_identity=ModelId("candidate-model-example-v1"),
        configuration_identity=ArtifactId("daily-config-example-v1"),
        market_context_identity=ArtifactId("market-context-unavailable-v1"),
        etf_snapshot_identity=ArtifactId("etf-snapshot-unavailable-v1"),
        theme_snapshot_identity=ArtifactId("theme-snapshot-unavailable-v1"),
        holdings_identity=ArtifactId("manual-holdings-empty-v1"),
        source_artifacts=sources,
        data_authority=authority,
        created_at=AsOfTime(created_at or DECISION + timedelta(minutes=1)),
    )


def make_recommendation(
    snapshot: DailyResearchSnapshot,
    *,
    symbol: str = "600000.SH",
    rank: int = 1,
    score: float = 0.75,
) -> CandidateRecommendation:
    return CandidateRecommendation(
        decision_snapshot_id=snapshot.snapshot_id,
        instrument_type=InstrumentType.A_SHARE_STOCK,
        symbol=symbol,
        candidate_rank=rank,
        candidate_score=score,
        score_components=(
            ScoreComponent(ArtifactId("feature-individual-strength-example-v1"), score + 0.05),
            ScoreComponent(ArtifactId("feature-risk-penalty-example-v1"), -0.05),
        ),
        industry="bank-v1",
        themes=("large-cap-bank-v1",),
        related_etfs=("512800.SH",),
        selection_reasons=("B1_BASELINE_RANK",),
        risk_reasons=("AUXILIARY_SOURCE_LIMITATION",),
        expected_horizon="1_TO_3_TRADING_SESSIONS_V1",
        target_definition=TargetId("entry-path-short-v1"),
        invalidation_conditions=("STRUCTURE_INVALIDATED",),
        data_quality=DecisionDataQuality.DEGRADED,
        model_identity=snapshot.model_identity,
        data_authority=snapshot.data_authority,
    )


def make_entry(
    snapshot: DailyResearchSnapshot,
    recommendation: CandidateRecommendation,
    *,
    state: EntryState = EntryState.ENTER,
) -> EntryAssessment:
    kwargs: dict[str, object] = {
        "decision_snapshot_id": snapshot.snapshot_id,
        "recommendation_id": recommendation.recommendation_id,
        "entry_state": state,
        "entry_score": 0.68,
        "entry_reasons": ("PRICE_STRUCTURE_VALID",),
        "blocking_reasons": (),
        "reference_price": 10.0,
        "preferred_price_zone": PriceZone(9.8, 10.1),
        "maximum_acceptable_price": 10.2,
        "invalidation_price": 9.4,
        "expected_mfe": 0.03,
        "expected_mae": -0.02,
        "risk_reward_estimate": 1.5,
        "uncertainty": 0.2,
        "model_identity": ModelId("entry-policy-example-v1"),
        "configuration_identity": ArtifactId("entry-config-example-v1"),
        "data_authority": snapshot.data_authority,
    }
    if state is EntryState.REJECT:
        kwargs["entry_reasons"] = ()
        kwargs["blocking_reasons"] = ("DATA_INCOMPLETE",)
        kwargs["preferred_price_zone"] = None
        kwargs["maximum_acceptable_price"] = None
    return EntryAssessment(**kwargs)  # type: ignore[arg-type]


@pytest.fixture
def published_artifact(tmp_path: Path) -> Path:
    snapshot = make_snapshot()
    recommendation = make_recommendation(snapshot)
    entry = make_entry(snapshot, recommendation)
    return publish_daily_quant_decision_artifact(
        root=tmp_path,
        snapshot=snapshot,
        recommendations=(recommendation,),
        entry_assessments=(entry,),
    )
