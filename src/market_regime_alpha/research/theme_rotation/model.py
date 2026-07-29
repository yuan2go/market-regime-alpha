"""Deterministic Theme Rotation V0 over decision-time observable proxies."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.envelope import (
    ArtifactEnvelope,
    EvidenceAuthority,
)
from market_regime_alpha.research.platform_v2.configs import (
    ThemeRotationModelConfig,
)
from market_regime_alpha.research.platform_v2.inputs import (
    ResearchInputBundle,
    ThemeResearchObservation,
)
from market_regime_alpha.research.theme_rotation.contracts import (
    RotationState,
    ThemeRotationItem,
    ThemeRotationSnapshot,
)


def evaluate_theme_rotation_v0(
    inputs: ResearchInputBundle,
    config: ThemeRotationModelConfig,
    *,
    code_revision: str,
) -> ThemeRotationSnapshot:
    unranked = tuple(_evaluate(item, config) for item in inputs.theme_observations)
    ordered = tuple(
        sorted(
            unranked,
            key=lambda item: (
                item.rotation_score is None,
                -(item.rotation_score or 0.0),
                item.theme_id,
            ),
        )
    )
    themes = tuple(
        replace(item, rank=index)
        for index, item in enumerate(ordered, start=1)
    )
    reasons = (
        ("THEME_ROTATION_DATA_INSUFFICIENT",)
        if not themes
        or all(
            item.rotation_state is RotationState.DATA_INSUFFICIENT
            for item in themes
        )
        else ("THEME_ROTATION_V0_MODEL_ASSUMPTION",)
    )
    payload = {
        "themes": [item.to_canonical_dict() for item in themes],
        "reason_codes": list(reasons),
    }
    envelope = ArtifactEnvelope.create(
        artifact_type="THEME_ROTATION_SNAPSHOT",
        artifact_payload=payload,
        decision_date=inputs.source_manifest.decision_time.value.date(),
        decision_time=inputs.source_manifest.decision_time,
        created_at=inputs.created_at,
        code_revision=code_revision,
        configuration_id=config.configuration_id,
        configuration_hash=config.configuration_hash,
        source_manifest_id=inputs.source_manifest.source_manifest_id,
        source_manifest_hash=inputs.source_manifest.content_hash,
        input_artifact_ids=inputs.input_artifact_ids,
        input_content_hashes=inputs.input_content_hashes,
        model_id=config.model_id,
        model_version=config.model_version,
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status=(
            "DATA_INSUFFICIENT"
            if reasons == ("THEME_ROTATION_DATA_INSUFFICIENT",)
            else "RESEARCH_READY"
        ),
        reason_codes=reasons,
        limitations=config.assumptions,
    )
    return ThemeRotationSnapshot(
        envelope=envelope, themes=themes, reason_codes=reasons
    )


def _evaluate(
    item: ThemeResearchObservation, config: ThemeRotationModelConfig
) -> ThemeRotationItem:
    required = (
        item.relative_strength_1d,
        item.relative_strength_3d,
        item.relative_strength_5d,
        item.relative_strength_10d,
        item.amount_expansion,
        item.breadth,
        item.new_high_breadth,
        item.leader_strength,
        item.participation_change,
        item.rank_persistence,
    )
    if item.confidence < config.minimum_confidence or any(
        value is None for value in required
    ):
        return _item(
            item,
            state=RotationState.DATA_INSUFFICIENT,
            score=None,
            reasons=tuple(
                dict.fromkeys(
                    (*item.reason_codes, "THEME_ROTATION_DATA_INSUFFICIENT")
                )
            ),
        )
    numeric = tuple(cast(float, value) for value in required)
    (
        rs1,
        rs3,
        rs5,
        rs10,
        amount,
        breadth,
        new_high,
        leader,
        participation,
        persistence,
    ) = numeric
    score = _clip(
        _clip(rs1 / config.return_scale)
        * config.relative_strength_1d_weight
        + _clip(rs3 / config.return_scale)
        * config.relative_strength_3d_weight
        + _clip(rs5 / config.return_scale)
        * config.relative_strength_5d_weight
        + _clip(rs10 / config.return_scale)
        * config.relative_strength_10d_weight
        + _clip(amount / config.amount_scale)
        * config.amount_expansion_weight
        + _unit_to_score(breadth) * config.breadth_weight
        + _unit_to_score(new_high) * config.new_high_breadth_weight
        + _clip(leader / config.return_scale)
        * config.leader_strength_weight
        + _clip(participation / config.participation_scale)
        * config.participation_change_weight
        + _unit_to_score(persistence) * config.persistence_weight
    )
    if score >= config.strengthening_threshold and (
        participation <= config.divergence_participation_threshold
        or breadth <= config.divergence_breadth_threshold
    ):
        state = RotationState.DIVERGING
        reason = "THEME_ROTATION_DIVERGENCE_GATE"
    elif score >= config.leading_threshold:
        state, reason = RotationState.LEADING, "THEME_ROTATION_LEADING"
    elif score >= config.strengthening_threshold:
        state, reason = (
            RotationState.STRENGTHENING,
            "THEME_ROTATION_STRENGTHENING",
        )
    elif score >= config.starting_threshold:
        state, reason = RotationState.STARTING, "THEME_ROTATION_STARTING"
    elif score >= config.weakening_threshold:
        state, reason = RotationState.WEAKENING, "THEME_ROTATION_WEAKENING"
    else:
        state, reason = RotationState.FAILED, "THEME_ROTATION_FAILED"
    return _item(
        item,
        state=state,
        score=score,
        reasons=tuple(dict.fromkeys((*item.reason_codes, reason))),
    )


def _item(
    item: ThemeResearchObservation,
    *,
    state: RotationState,
    score: float | None,
    reasons: tuple[str, ...],
) -> ThemeRotationItem:
    return ThemeRotationItem(
        theme_id=item.theme_id,
        theme_name=item.theme_name,
        benchmark_id=item.benchmark_id,
        proxy_etf_ids=item.proxy_etf_ids,
        rotation_state=state,
        rotation_score=score,
        rank=1,
        confidence=item.confidence,
        relative_strength_1d=item.relative_strength_1d,
        relative_strength_3d=item.relative_strength_3d,
        relative_strength_5d=item.relative_strength_5d,
        relative_strength_10d=item.relative_strength_10d,
        amount_expansion=item.amount_expansion,
        breadth=item.breadth,
        new_high_breadth=item.new_high_breadth,
        leader_strength=item.leader_strength,
        participation_change=item.participation_change,
        persistence=item.rank_persistence,
        reason_codes=reasons,
    )


def _clip(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _unit_to_score(value: float) -> float:
    return _clip(2.0 * value - 1.0)
