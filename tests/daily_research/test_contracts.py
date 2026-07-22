from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.daily_research.contracts import (
    CandidateRecommendation,
    DailyDataAuthority,
    DecisionDataQuality,
    EntryAssessment,
    EntryState,
    ScoreComponent,
)

from .conftest import DECISION, make_entry, make_recommendation, make_snapshot


def test_snapshot_identity_is_deterministic_and_excludes_created_at() -> None:
    first = make_snapshot(created_at=DECISION + timedelta(minutes=1))
    second = make_snapshot(created_at=DECISION + timedelta(minutes=5))

    assert first.snapshot_id == second.snapshot_id
    assert first.content_hash == second.content_hash
    assert first.to_canonical_dict()["created_at"] != second.to_canonical_dict()["created_at"]


@pytest.mark.parametrize("field", ["source_observed_at", "source_available_at"])
def test_snapshot_rejects_source_evidence_after_decision_time(field: str) -> None:
    with pytest.raises(ValueError, match="Decision Time"):
        make_snapshot(**{field: DECISION + timedelta(seconds=1)})


def test_snapshot_rejects_wrong_local_decision_date() -> None:
    snapshot = make_snapshot()
    payload = snapshot.to_canonical_dict()
    payload["decision_date"] = "2026-07-22"

    with pytest.raises(ValueError, match="decision_date"):
        type(snapshot).from_canonical_dict(payload)


def test_snapshot_rejects_naive_decision_timestamp() -> None:
    snapshot = make_snapshot()
    payload = snapshot.to_canonical_dict()
    payload["decision_time"] = "2026-07-23T14:55:00"

    with pytest.raises(ValueError, match="timezone-aware"):
        type(snapshot).from_canonical_dict(payload)


def test_snapshot_rejects_wrong_timezone_contract() -> None:
    snapshot = make_snapshot()
    payload = snapshot.to_canonical_dict()
    payload["timezone"] = "UTC"

    with pytest.raises(ValueError, match="Asia/Shanghai"):
        type(snapshot).from_canonical_dict(payload)


def test_daily_contracts_are_immutable() -> None:
    snapshot = make_snapshot()
    recommendation = make_recommendation(snapshot)
    entry = make_entry(snapshot, recommendation)

    with pytest.raises(FrozenInstanceError):
        recommendation.candidate_rank = 2  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        entry.entry_state = EntryState.REJECT  # type: ignore[misc]


def test_candidate_recommendation_contains_no_entry_action() -> None:
    snapshot = make_snapshot()
    recommendation = make_recommendation(snapshot)

    assert "entry_state" not in recommendation.to_canonical_dict()
    assert not hasattr(recommendation, "entry_state")


def test_candidate_recommendation_rejects_duplicate_component_names() -> None:
    snapshot = make_snapshot()
    valid = make_recommendation(snapshot)
    payload = {
        **valid.semantic_payload(),
        "score_components": (
            ScoreComponent(ArtifactId("feature-same-v1"), 0.1),
            ScoreComponent(ArtifactId("feature-same-v1"), 0.2),
        ),
    }

    with pytest.raises(ValueError, match="score component"):
        CandidateRecommendation(**payload)


def test_entry_state_contracts_fail_closed() -> None:
    snapshot = make_snapshot()
    recommendation = make_recommendation(snapshot)
    valid = make_entry(snapshot, recommendation)
    payload = valid.semantic_payload()
    payload["blocking_reasons"] = ("LATE_DATA",)

    with pytest.raises(ValueError, match="ENTER"):
        EntryAssessment(**payload)

    reject_payload = valid.semantic_payload()
    reject_payload["entry_state"] = EntryState.REJECT
    reject_payload["entry_reasons"] = ()
    reject_payload["blocking_reasons"] = ()
    with pytest.raises(ValueError, match="REJECT"):
        EntryAssessment(**reject_payload)


def test_authority_enum_has_no_formal_research_value() -> None:
    assert {item.value for item in DailyDataAuthority} == {
        "EXPLORATORY",
        "AUXILIARY",
        "TEST_ONLY_NOT_RESEARCH_EVIDENCE",
    }
    with pytest.raises(ValueError):
        DailyDataAuthority("FORMAL_RESEARCH")


def test_score_is_not_renamed_probability() -> None:
    component = ScoreComponent(ArtifactId("rank-score-v1"), 0.8)
    assert component.value == 0.8
    assert not hasattr(component, "probability")


def test_identity_fields_cannot_be_caller_overridden() -> None:
    snapshot = make_snapshot()
    recommendation = make_recommendation(snapshot)
    with pytest.raises(TypeError):
        CandidateRecommendation(
            **recommendation.semantic_payload(),
            recommendation_id=ArtifactId("caller-selected"),  # type: ignore[call-arg]
        )


def test_snapshot_requires_temporal_lineage_for_every_upstream_identity() -> None:
    snapshot = make_snapshot()

    with pytest.raises(ValueError, match="upstream identities must have source Artifact lineage"):
        replace(snapshot, market_context_identity=ArtifactId("unlinked-market-context-v1"))


def test_candidate_requires_explicit_missing_mapping_quality_and_reasons() -> None:
    snapshot = make_snapshot()
    base = make_recommendation(snapshot)

    with pytest.raises(ValueError, match="missing industry mapping"):
        CandidateRecommendation(
            **{
                **base.semantic_payload(),
                "industry": None,
                "data_quality": DecisionDataQuality.COMPLETE,
                "risk_reasons": (),
            }
        )


def test_candidate_score_equals_identified_component_contributions() -> None:
    snapshot = make_snapshot()
    base = make_recommendation(snapshot)

    with pytest.raises(ValueError, match="component contributions"):
        CandidateRecommendation(**{**base.semantic_payload(), "candidate_score": 0.9})


def test_entry_integer_numerics_round_trip_canonically() -> None:
    snapshot = make_snapshot()
    recommendation = make_recommendation(snapshot)
    base = make_entry(snapshot, recommendation)
    assessment = EntryAssessment(
        **{
            **base.semantic_payload(),
            "reference_price": 10,
            "maximum_acceptable_price": 11,
            "invalidation_price": 9,
            "expected_mfe": 1,
            "expected_mae": -1,
            "risk_reward_estimate": 2,
            "uncertainty": 1,
        }
    )

    assert EntryAssessment.from_canonical_dict(assessment.to_canonical_dict()) == assessment


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"reference_price": 10.3}, "maximum acceptable"),
        ({"maximum_acceptable_price": 10.0}, "preferred zone"),
        ({"invalidation_price": 10.0}, "invalidation price"),
    ],
)
def test_enter_price_relationships_fail_closed(changes: dict[str, float], message: str) -> None:
    snapshot = make_snapshot()
    recommendation = make_recommendation(snapshot)
    base = make_entry(snapshot, recommendation)

    with pytest.raises(ValueError, match=message):
        EntryAssessment(**{**base.semantic_payload(), **changes})
