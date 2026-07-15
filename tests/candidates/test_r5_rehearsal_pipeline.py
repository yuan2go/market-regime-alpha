from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.candidates.baselines import rank_candidates_by_feature
from market_regime_alpha.candidates.contracts import CandidatePopulation
from market_regime_alpha.candidates.dataset import build_candidate_research_dataset
from market_regime_alpha.candidates.evaluation import evaluate_candidate_ranking_panel
from market_regime_alpha.candidates.panel import assemble_candidate_research_panel
from market_regime_alpha.candidates.rehearsal_targets import (
    materialize_r5_next_session_return_target,
    r5_next_session_return_target_contract,
)
from market_regime_alpha.core.identity import ArtifactId, DatasetId, ModelId, ProviderId, UniverseId
from market_regime_alpha.core.time import AsOfTime, AvailabilityTime, DecisionTime
from market_regime_alpha.data.contracts import DataEligibility, DatasetContract, ProviderReference
from market_regime_alpha.data.rehearsal import (
    RehearsalDailyBar,
    RehearsalDecisionSnapshot,
    RehearsalNextSessionClose,
)
from market_regime_alpha.features.rehearsal_baselines import (
    MOMENTUM_5S_ID,
    materialize_r5_baseline_features,
    r5_baseline_feature_definitions,
)


TZ = ZoneInfo("Asia/Shanghai")
MODEL_ID = ModelId("candidate-r5-single-momentum-rank-v1")
SYMBOLS = ("000001.SZ", "000002.SZ", "000003.SZ")


def _dataset_contract(dataset_id: DatasetId) -> DatasetContract:
    return DatasetContract(
        dataset_id=dataset_id,
        schema_version="r5-rehearsal-source-v1",
        eligibility=DataEligibility.REHEARSAL,
        manifest_artifact_id=ArtifactId(f"manifest-{dataset_id}"),
        provider_references=(
            ProviderReference(
                provider_id=ProviderId("provider-controlled-r5-fixture"),
                product="r5-rehearsal-bars",
                contract_version="v1",
            ),
        ),
        pit_correct_for_scope=True,
        scope="controlled R5 Candidate rehearsal fixture",
        limitations=("controlled fixture; not formal Alpha evidence",),
    )


def _history(symbol: str, decision_date: date, *, base_close: float) -> tuple[RehearsalDailyBar, ...]:
    start = decision_date - timedelta(days=35)
    bars = []
    for index in range(25):
        session_date = start + timedelta(days=index)
        bars.append(
            RehearsalDailyBar(
                symbol=symbol,
                session_date=session_date,
                close=base_close + index * 0.1,
                amount=1_000_000.0 + index * 5_000.0,
                available_at=AvailabilityTime(datetime(session_date.year, session_date.month, session_date.day, 15, 5, tzinfo=TZ)),
            )
        )
    return tuple(bars)


def _build_slice(
    *,
    decision_date: date,
    source_dataset_id: DatasetId,
    universe_id: UniverseId,
    price_a: float,
    price_b: float,
    future_a: float,
    future_b: float,
):
    decision_at = datetime(decision_date.year, decision_date.month, decision_date.day, 14, 55, tzinfo=TZ)
    decision_time = DecisionTime(decision_at)
    population = CandidatePopulation(
        universe_id=universe_id,
        decision_time=decision_time,
        symbols=SYMBOLS,
        source_dataset_ids=(source_dataset_id,),
    )
    bars = (
        *_history("000001.SZ", decision_date, base_close=100.0),
        *_history("000002.SZ", decision_date, base_close=100.0),
        *_history("000003.SZ", decision_date, base_close=100.0),
    )
    snapshots = (
        RehearsalDecisionSnapshot("000001.SZ", decision_time, price_a, AvailabilityTime(decision_at)),
        RehearsalDecisionSnapshot("000002.SZ", decision_time, price_b, AvailabilityTime(decision_at)),
    )
    feature_definitions = r5_baseline_feature_definitions()
    feature_materializations = materialize_r5_baseline_features(
        population=population,
        source_dataset_id=source_dataset_id,
        daily_bars=bars,
        decision_snapshots=snapshots,
        code_revision="abc123",
        config_hash="r5-baseline-features-v1",
    )

    next_date = decision_date + timedelta(days=1)
    next_close_available = AvailabilityTime(
        datetime(next_date.year, next_date.month, next_date.day, 15, 5, tzinfo=TZ)
    )
    target_materialized_at = AsOfTime(
        datetime(next_date.year, next_date.month, next_date.day, 15, 30, tzinfo=TZ)
    )
    target_materialization = materialize_r5_next_session_return_target(
        population=population,
        source_dataset_id=source_dataset_id,
        decision_snapshots=snapshots,
        next_session_closes=(
            RehearsalNextSessionClose("000001.SZ", next_date, future_a, next_close_available),
            RehearsalNextSessionClose("000002.SZ", next_date, future_b, next_close_available),
            RehearsalNextSessionClose("000003.SZ", next_date, 100.0, next_close_available),
        ),
        materialized_at=target_materialized_at,
        code_revision="abc123",
        config_hash="r5-next-session-target-v1",
    )
    source_contract = _dataset_contract(source_dataset_id)
    candidate_dataset = build_candidate_research_dataset(
        population=population,
        dataset_contracts=(source_contract,),
        feature_definitions=feature_definitions,
        feature_materializations=feature_materializations,
        target_contract=r5_next_session_return_target_contract(),
        target_materialization=target_materialization,
        limitations=("R5 controlled rehearsal slice",),
    )
    ranking = rank_candidates_by_feature(
        candidate_dataset,
        feature_id=MOMENTUM_5S_ID,
        model_id=MODEL_ID,
        code_revision="abc123",
        config_hash="single-momentum-rank-v1",
    )
    return candidate_dataset, ranking


def test_two_date_r5_rehearsal_pipeline_produces_panel_rankings_and_evaluation() -> None:
    first_dataset, first_ranking = _build_slice(
        decision_date=date(2026, 7, 13),
        source_dataset_id=DatasetId("dataset-r5-20260713"),
        universe_id=UniverseId("universe-r5-20260713"),
        price_a=112.0,
        price_b=106.0,
        future_a=114.0,
        future_b=104.0,
    )
    second_dataset, second_ranking = _build_slice(
        decision_date=date(2026, 7, 15),
        source_dataset_id=DatasetId("dataset-r5-20260715"),
        universe_id=UniverseId("universe-r5-20260715"),
        price_a=105.0,
        price_b=113.0,
        future_a=103.0,
        future_b=116.0,
    )

    panel = assemble_candidate_research_panel((second_dataset, first_dataset))
    evaluation = evaluate_candidate_ranking_panel(
        panel,
        (second_ranking, first_ranking),
        top_k=1,
    )

    assert panel.slice_count == 2
    assert panel.row_count == 6
    assert first_ranking.candidate_population_size == 3
    assert first_ranking.ranked_population_size == 2
    assert len(first_ranking.rejections) == 1
    assert first_ranking.rejections[0].symbol == "000003.SZ"
    assert first_ranking.rejections[0].reason_code == "FEATURE_MISSING"

    assert tuple(item.symbol for item in first_ranking.predictions) == ("000001.SZ", "000002.SZ")
    assert tuple(item.symbol for item in second_ranking.predictions) == ("000002.SZ", "000001.SZ")

    assert evaluation.slice_count == 2
    assert evaluation.candidate_population_size == 6
    assert evaluation.ranked_population_size == 4
    assert evaluation.evaluated_prediction_count == 4
    assert evaluation.ranking_coverage == pytest.approx(4 / 6)
    assert evaluation.evaluated_prediction_coverage == pytest.approx(4 / 6)
    assert evaluation.mean_slice_rank_ic == pytest.approx(1.0)
    assert evaluation.mean_slice_top_k_target is not None
    assert evaluation.mean_slice_top_k_target > 0.0
