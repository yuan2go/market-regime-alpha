from datetime import UTC, datetime
from dataclasses import replace
from uuid import UUID

import pytest

from market_regime_alpha.research_qualification.domain.daily_prediction import DailyPredictionPlan
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.interfaces.daily_research import prediction_steps
from market_regime_alpha.interfaces.daily_research import DailyResearchOperations
from market_regime_alpha.interfaces.daily_research import encode_daily_plan, decode_daily_plan
from market_regime_alpha.runtime.domain import validate_step_dag


def plan():
    artifact = ArtifactBinding(UUID(int=1), "a" * 64, 1)
    return DailyPredictionPlan(
        UUID(int=2),
        UUID(int=3),
        UUID(int=4),
        UUID(int=5),
        UUID(int=6),
        artifact,
        "INDEX",
        "CSI300",
        (UUID(int=7), UUID(int=8)),
        UUID(int=9),
        UUID(int=10),
        UUID(int=11),
        UUID(int=12),
        UUID(int=13),
        UUID(int=14),
        UUID(int=15),
        UUID(int=16),
        datetime(2026, 9, 7, 9, tzinfo=UTC),
        datetime(2026, 9, 7, 10, tzinfo=UTC),
        "b" * 64,
        artifact,
        artifact,
        "c" * 40,
        UUID(int=17),
    )


def test_daily_runtime_uses_complete_canonical_chain_without_retrospective_identity():
    frozen = plan()
    steps, dependencies = prediction_steps(frozen)
    validate_step_dag(steps, dependencies)
    assert [step.step_kind for step in steps] == [
        "FREEZE_UNIVERSE",
        "ASSESS_ELIGIBILITY",
        "REGISTER_DATASET",
        "BUILD_CANDIDATE_SET",
        "OPEN_DECISION_RUN",
        "ASSESS_CONTEXT",
        "SIGNAL_AND_FORECAST",
        "SIGNAL_AND_FORECAST",
        "RECORD_EVIDENCE",
    ]
    assert len({step.request_hash for step in steps}) == 9
    assert all(step.retry_policy.deadline is None for step in steps)
    assert prediction_steps(frozen) == prediction_steps(frozen)


def test_daily_request_rejects_duplicate_members_and_future_input():
    frozen = plan()
    with pytest.raises(ValueError, match="population"):
        replace(frozen, instrument_ids=(UUID(int=7), UUID(int=7)))
    with pytest.raises(ValueError, match="cutoff"):
        replace(frozen, input_cutoff=datetime(2026, 9, 8, tzinfo=UTC))


def test_daily_plan_json_preserves_typed_artifact_and_time_identities():
    frozen = plan()
    assert decode_daily_plan(encode_daily_plan(frozen)) == frozen
    with pytest.raises(ValueError, match="schema"):
        decode_daily_plan(b'{"schema":"retrospective-plan","plan":{}}')


def test_unmature_target_stays_pending_without_outcome_evaluation_or_publication_writes():
    from types import SimpleNamespace

    frozen = plan()
    reads = SimpleNamespace(
        ready=lambda _: SimpleNamespace(target_window_end=datetime(2026, 9, 8, 7, tzinfo=UTC)),
        now=lambda: datetime(2026, 9, 8, 6, tzinfo=UTC),
    )
    # An app with no methods: touching any writer is a test failure.
    result = DailyResearchOperations(SimpleNamespace(), reads).settle_and_evaluate(frozen, worker_id="daily-test")
    assert result == {
        "prediction_id": frozen.prediction_id,
        "state": "PENDING",
        "due_at": datetime(2026, 9, 8, 7, tzinfo=UTC),
        "business_writes": 0,
    }


def test_collection_freezes_round_and_never_blindly_retries_unknown_provider_effect():
    from market_regime_alpha.interfaces.daily_collection import DailyCollectionPlan, collection_steps
    from market_regime_alpha.runtime.domain import ExternalEffectClass

    frozen = plan()
    collection = DailyCollectionPlan(frozen, "input", 1, frozen.decision_time)
    assert DailyCollectionPlan.decode(collection.content) == collection
    steps, dependencies = collection_steps(collection)
    validate_step_dag(steps, dependencies)
    assert len(steps) == 4
    assert steps[0].external_effect_class is ExternalEffectClass.CONTENT_PUT
    assert steps[0].retry_policy.max_attempts == 1
    assert steps[1].retry_policy.max_attempts == 3
    assert collection.run_id != DailyCollectionPlan(frozen, "input", 2, frozen.decision_time).run_id
    with pytest.raises(ValueError, match="bounded"):
        DailyCollectionPlan(frozen, "input", 17, frozen.decision_time)
def test_market_observation_schedule_does_not_collide_with_outcome_evaluation():
    from market_regime_alpha.interfaces.daily_collection import DailyCollectionPlan
    frozen = plan()
    observation = DailyCollectionPlan(frozen, "outcome", 1, frozen.decision_time)
    assert observation.schedule_code != "daily-outcome-" + frozen.experimental_model_use_id.hex
    assert observation.schedule_code == "daily-outcome-collection-" + frozen.experimental_model_use_id.hex
