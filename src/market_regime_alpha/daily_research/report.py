"""Deterministic presentation derived solely from verified decision records."""

from __future__ import annotations

from market_regime_alpha.daily_research.contracts import (
    CandidateRecommendation,
    DailyResearchSnapshot,
    EntryAssessment,
)
from market_regime_alpha.daily_research.policy import evidence_authority


def render_daily_quant_decision_report(
    snapshot: DailyResearchSnapshot,
    recommendations: tuple[CandidateRecommendation, ...],
    entry_assessments: tuple[EntryAssessment, ...],
) -> str:
    """Render the human-readable report solely from structured evidence."""

    entries = {entry.recommendation_id: entry for entry in entry_assessments}
    lines = [
        "# Daily Quant Decision Report", "", "## Evidence identity", "",
        f"- Snapshot: `{snapshot.snapshot_id}`",
        f"- Decision Time: `{snapshot.decision_time.isoformat()}`",
        f"- Data Authority: `{snapshot.data_authority.value}`",
        f"- Evidence Authority: `{evidence_authority(snapshot.data_authority)}`",
        "- No Alpha or trading authority is established by this report.",
        "- Source Artifacts: "
        + ", ".join(
            f"`{source.artifact_id}` ({source.provider_id}, {source.data_authority.value})"
            for source in snapshot.source_artifacts
        ),
        "", "## Candidate Recommendations and Entry Assessments", "",
    ]
    if not recommendations:
        lines.extend([
            "- No Candidate Recommendation was produced. This valid empty result was not backfilled.",
            "",
        ])
    for recommendation in recommendations:
        entry = entries[recommendation.recommendation_id]
        lines.extend(_recommendation_lines(recommendation, entry))
    lines.extend([
        "## Boundaries", "",
        "- Candidate ranking and Entry timing are separate records.",
        "- This Artifact contains no manual trade, broker fill, Portfolio Decision, or order.",
        "- Auxiliary or exploratory evidence cannot substitute for formal Xuntou PIT validation.",
        "",
    ])
    return "\n".join(lines)


def _recommendation_lines(
    recommendation: CandidateRecommendation,
    entry: EntryAssessment,
) -> list[str]:
    zone = (
        f"{entry.preferred_price_zone.lower}..{entry.preferred_price_zone.upper}"
        if entry.preferred_price_zone is not None
        else "UNAVAILABLE"
    )
    return [
        f"### {recommendation.candidate_rank}. {recommendation.symbol} ({recommendation.instrument_type.value})",
        "",
        f"- Candidate score: `{recommendation.candidate_score}`",
        "- Score components: " + ", ".join(
            f"{item.component_identity}={item.value}" for item in recommendation.score_components
        ),
        f"- Candidate model: `{recommendation.model_identity}`",
        f"- Target: `{recommendation.target_definition}`",
        f"- Expected horizon: `{recommendation.expected_horizon}`",
        f"- Industry: `{recommendation.industry or 'UNAVAILABLE'}`",
        f"- Themes: {', '.join(recommendation.themes) or 'UNAVAILABLE'}",
        f"- Related ETFs: {', '.join(recommendation.related_etfs) or 'UNAVAILABLE'}",
        f"- Data quality: `{recommendation.data_quality.value}`",
        f"- Selection reasons: {', '.join(recommendation.selection_reasons)}",
        f"- Risk reasons: {', '.join(recommendation.risk_reasons) or 'NONE_DECLARED'}",
        f"- Invalidation conditions: {', '.join(recommendation.invalidation_conditions)}",
        f"- Entry state: `{entry.entry_state.value}`",
        f"- Entry score: `{entry.entry_score}`",
        f"- Reference price: `{entry.reference_price}`",
        f"- Preferred price zone: `{zone}`",
        f"- Maximum acceptable price: `{entry.maximum_acceptable_price}`",
        f"- Invalidation price: `{entry.invalidation_price}`",
        f"- Expected MFE / MAE: `{entry.expected_mfe}` / `{entry.expected_mae}`",
        f"- Risk/reward estimate: `{entry.risk_reward_estimate}`",
        f"- Uncertainty: `{entry.uncertainty}`",
        f"- Entry reasons: {', '.join(entry.entry_reasons) or 'NONE_DECLARED'}",
        f"- Blocking reasons: {', '.join(entry.blocking_reasons) or 'NONE'}",
        "",
    ]
