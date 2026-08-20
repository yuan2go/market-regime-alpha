from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import ArtifactId, ProviderId, TargetId
from market_regime_alpha.core.time import (
    AvailabilityTime,
    DecisionTime,
    RetrievedAt,
)
from market_regime_alpha.data.providers.public_composite import (
    PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
    AcquiredSourcePayload,
    PublicBar,
    PublicCompositeProviderResult,
)
from market_regime_alpha.data.source_manifest import SourceFieldFinality
from market_regime_alpha.daily_decision.artifact import (
    publish_phase_d_daily_decision_artifact,
)
from market_regime_alpha.daily_decision.outcome import (
    OutcomeStatus,
    settle_mr1_1030_outcomes,
)
from market_regime_alpha.daily_decision.outcome_artifact import (
    DAILY_REVIEW_ARTIFACT_FILES,
    load_verified_daily_review_artifact,
    publish_daily_review_artifact,
)
from market_regime_alpha.daily_decision.target_adapter import (
    mr1_next_session_1030_target_protocol,
)
from market_regime_alpha.platform.target_evaluation import PriceMark
from market_regime_alpha.research.mr1_morning_pop import MR1TargetId
from tests.daily_decision.conftest import DailyDecisionFixture
from tests.daily_decision.test_phase_d_artifact import _published_bundle


SHANGHAI = ZoneInfo("Asia/Shanghai")
NEXT_SESSION = date(2025, 2, 4)


def _settlement_result(
    fixture: DailyDecisionFixture,
    *,
    omit_symbol: str | None,
) -> PublicCompositeProviderResult:
    source = AcquiredSourcePayload(
        provider_id=ProviderId("provider-tencent-public"),
        product="fixture-next-session-1030",
        locator="archive://fixture/next-session-1030",
        raw_payload=f"next-session:{omit_symbol}".encode(),
        retrieved_time=RetrievedAt(
            datetime(2025, 2, 4, 10, 31, tzinfo=SHANGHAI)
        ),
        limitations=("FIXTURE_REPLAY_ONLY",),
    )
    reference_by_symbol = {
        item.symbol: item.price
        for item in fixture.decision_snapshot.observations
        if item.price is not None
    }
    bars = tuple(
        PublicBar(
            symbol=symbol,
            event_time=datetime(2025, 2, 4, 10, 30, tzinfo=SHANGHAI),
            available_time=AvailabilityTime(
                datetime(2025, 2, 4, 10, 31, tzinfo=SHANGHAI)
            ),
            source_artifact_id=source.source_artifact_id,
            open=float(reference) * 1.005,
            high=float(reference) * 1.02,
            low=float(reference) * 0.99,
            close=float(reference) * (1.01 + index / 10_000),
            volume=1_000_000.0,
            amount=20_000_000.0,
            unit="CNY",
            adjustment_basis="NONE",
            finality=SourceFieldFinality.PRELIMINARY,
        )
        for index, (symbol, reference) in enumerate(
            sorted(reference_by_symbol.items())
        )
        if symbol != omit_symbol
    )
    return PublicCompositeProviderResult(
        profile_id=PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
        decision_time=DecisionTime(
            datetime(2025, 2, 4, 14, 55, tzinfo=SHANGHAI)
        ),
        raw_payloads=(source,),
        bars=bars,
        quotes=(),
        source_conflicts=(),
        limitations=("FIXTURE_REPLAY_ONLY",),
    )


def test_target_protocol_is_an_adapter_over_the_unique_mr1_identity(
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    protocol = mr1_next_session_1030_target_protocol(
        daily_decision_fixture.reconciliation.population.universe_id
    )

    assert protocol.target_id == TargetId(
        MR1TargetId.NEXT_SESSION_1030_RETURN.value
    )
    assert protocol.end_mark is PriceMark.NEXT_1030
    assert protocol.path_required is False


def test_outcome_append_preserves_t_artifact_and_reconstructs_review(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    daily_bundle = _published_bundle(daily_decision_fixture)
    daily_path = publish_phase_d_daily_decision_artifact(
        root=tmp_path / "daily",
        bundle=daily_bundle,
    )
    before = {
        item.name: f"sha256:{sha256(item.read_bytes()).hexdigest()}"
        for item in daily_path.iterdir()
    }
    omit = daily_bundle.recommendations[0].symbol
    settlement = settle_mr1_1030_outcomes(
        daily_decision_bundle=daily_bundle,
        daily_decision_artifact_id=daily_bundle.artifact_id,
        settlement_provider_result=_settlement_result(
            daily_decision_fixture,
            omit_symbol=omit,
        ),
        settlement_source_archive_id=ArtifactId(
            "source-replay-next-session-fixture"
        ),
        next_session_date=NEXT_SESSION,
    )

    assert settlement.target_protocol.target_id == TargetId(
        MR1TargetId.NEXT_SESSION_1030_RETURN.value
    )
    assert len(settlement.recommendation_outcomes) == len(
        daily_bundle.recommendations
    )
    assert len(settlement.population_outcomes) == len(
        daily_bundle.prediction_runs[0].predictions
    )
    assert any(
        item.status is OutcomeStatus.UNRESOLVED
        for item in settlement.recommendation_outcomes
    )
    assert settlement.review.recommendation_count == len(
        daily_bundle.recommendations
    )
    assert settlement.review.unresolved_outcome_count >= 1
    assert 0.0 <= settlement.review.outcome_coverage < 1.0
    assert settlement.review.b0_b1_top_k_overlap_count >= 0
    assert settlement.review.data_eligibility.value == "EXPLORATORY"

    review_path = publish_daily_review_artifact(
        root=tmp_path / "reviews",
        settlement=settlement,
    )
    assert {item.name for item in review_path.iterdir()} == set(
        DAILY_REVIEW_ARTIFACT_FILES
    )
    verified = load_verified_daily_review_artifact(review_path)
    assert verified.settlement == settlement
    assert "FORMAL_OOS_ALPHA_NOT_ESTABLISHED" in (
        review_path / "report.md"
    ).read_text(encoding="utf-8")
    after = {
        item.name: f"sha256:{sha256(item.read_bytes()).hexdigest()}"
        for item in daily_path.iterdir()
    }
    assert after == before


def test_outcome_arrival_creates_new_evidence_without_mutating_prior_review(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    daily_bundle = _published_bundle(daily_decision_fixture)
    omit = daily_bundle.recommendations[0].symbol
    unresolved = settle_mr1_1030_outcomes(
        daily_decision_bundle=daily_bundle,
        daily_decision_artifact_id=daily_bundle.artifact_id,
        settlement_provider_result=_settlement_result(
            daily_decision_fixture,
            omit_symbol=omit,
        ),
        settlement_source_archive_id=ArtifactId("source-next-partial"),
        next_session_date=NEXT_SESSION,
    )
    resolved = settle_mr1_1030_outcomes(
        daily_decision_bundle=daily_bundle,
        daily_decision_artifact_id=daily_bundle.artifact_id,
        settlement_provider_result=_settlement_result(
            daily_decision_fixture,
            omit_symbol=None,
        ),
        settlement_source_archive_id=ArtifactId("source-next-complete"),
        next_session_date=NEXT_SESSION,
    )
    unresolved_path = publish_daily_review_artifact(
        root=tmp_path,
        settlement=unresolved,
    )
    resolved_path = publish_daily_review_artifact(
        root=tmp_path,
        settlement=resolved,
    )

    assert unresolved_path != resolved_path
    assert unresolved.review.unresolved_outcome_count >= 1
    assert resolved.review.unresolved_outcome_count == 0
    assert resolved.review.outcome_coverage == 1.0
    assert load_verified_daily_review_artifact(
        unresolved_path
    ).settlement == unresolved
