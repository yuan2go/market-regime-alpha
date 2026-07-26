"""Cross-record application policy for one daily decision package."""

from __future__ import annotations

from market_regime_alpha.daily_research.contracts import (
    CandidateRecommendation,
    DailyDataAuthority,
    DailyResearchSnapshot,
    DecisionDataQuality,
    EntryAssessment,
    EntryState,
    InstrumentType,
)


def validate_daily_decision_aggregate(
    *,
    snapshot: DailyResearchSnapshot,
    recommendations: tuple[CandidateRecommendation, ...],
    entry_assessments: tuple[EntryAssessment, ...],
) -> tuple[tuple[CandidateRecommendation, ...], tuple[EntryAssessment, ...]]:
    """Validate references, score-derived ranks, coverage, and canonical ordering."""

    if not isinstance(snapshot, DailyResearchSnapshot):
        raise TypeError("snapshot must be a DailyResearchSnapshot")
    if any(not isinstance(item, CandidateRecommendation) for item in recommendations):
        raise TypeError("recommendations must contain CandidateRecommendation values")
    if any(not isinstance(item, EntryAssessment) for item in entry_assessments):
        raise TypeError("entry_assessments must contain EntryAssessment values")
    ordered_recommendations = tuple(
        sorted(
            recommendations,
            key=lambda item: (item.instrument_type.value, item.candidate_rank, item.symbol),
        )
    )
    recommendation_ids = tuple(str(item.recommendation_id) for item in ordered_recommendations)
    if len(recommendation_ids) != len(set(recommendation_ids)):
        raise ValueError("Candidate Recommendation IDs must be unique")
    symbol_keys = tuple((item.instrument_type, item.symbol) for item in ordered_recommendations)
    if len(symbol_keys) != len(set(symbol_keys)):
        raise ValueError("Candidate Recommendation instrument/symbol keys must be unique")
    _validate_rank_reconstruction(ordered_recommendations)
    source_ids = {str(item.artifact_id) for item in snapshot.source_artifacts}
    registered_component_ids = {str(item) for item in snapshot.registered_component_identities}
    for recommendation in ordered_recommendations:
        if recommendation.decision_snapshot_id != snapshot.snapshot_id:
            raise ValueError("Candidate Recommendation references a different snapshot")
        if recommendation.data_authority is not snapshot.data_authority:
            raise ValueError("Candidate Recommendation authority mismatch")
        if recommendation.model_identity != snapshot.model_identity:
            raise ValueError("Candidate Recommendation model identity mismatch")
        component_ids = {str(item.component_identity) for item in recommendation.score_components}
        if not component_ids <= registered_component_ids:
            raise ValueError("Candidate Recommendation uses an unregistered component identity")
        if str(recommendation.target_definition) not in source_ids:
            raise ValueError("Candidate Recommendation Target identity lacks source Artifact lineage")

    ordered_entries = tuple(sorted(entry_assessments, key=lambda item: str(item.recommendation_id)))
    entry_recommendation_ids = tuple(str(item.recommendation_id) for item in ordered_entries)
    if len(entry_recommendation_ids) != len(set(entry_recommendation_ids)):
        raise ValueError("one Entry Assessment per recommendation is required")
    if set(entry_recommendation_ids) != set(recommendation_ids):
        raise ValueError("Entry Assessment coverage must exactly match recommendations")
    recommendations_by_id = {item.recommendation_id: item for item in ordered_recommendations}
    for entry in ordered_entries:
        if entry.decision_snapshot_id != snapshot.snapshot_id:
            raise ValueError("Entry Assessment references a different snapshot")
        if entry.data_authority is not snapshot.data_authority:
            raise ValueError("Entry Assessment authority mismatch")
        if str(entry.model_identity) not in source_ids:
            raise ValueError("Entry model identity lacks source Artifact lineage")
        if str(entry.configuration_identity) not in source_ids:
            raise ValueError("Entry configuration identity lacks source Artifact lineage")
        if (
            recommendations_by_id[entry.recommendation_id].data_quality
            is DecisionDataQuality.INSUFFICIENT
            and entry.entry_state is not EntryState.REJECT
        ):
            raise ValueError("an INSUFFICIENT Candidate must be REJECT at Entry")
    return ordered_recommendations, ordered_entries


def _validate_rank_reconstruction(
    recommendations: tuple[CandidateRecommendation, ...],
) -> None:
    for instrument_type in InstrumentType:
        instrument_recommendations = tuple(
            item for item in recommendations if item.instrument_type is instrument_type
        )
        ranks = tuple(item.candidate_rank for item in instrument_recommendations)
        if ranks != tuple(range(1, len(ranks) + 1)):
            raise ValueError(f"{instrument_type.value} Candidate ranks must be contiguous from one")
        score_order = tuple(
            sorted(instrument_recommendations, key=lambda item: (-item.candidate_score, item.symbol))
        )
        if any(item.candidate_rank != expected for expected, item in enumerate(score_order, start=1)):
            raise ValueError(
                f"{instrument_type.value} Candidate ranks must match descending score order"
            )


def evidence_authority(data_authority: DailyDataAuthority) -> str:
    """Return the package evidence ceiling without inflating test fixtures."""

    if data_authority is DailyDataAuthority.TEST_ONLY_NOT_RESEARCH_EVIDENCE:
        return DailyDataAuthority.TEST_ONLY_NOT_RESEARCH_EVIDENCE.value
    return "NOT_FORMAL_OOS"
