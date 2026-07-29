"""Deterministic Capital Evolution V0 scoring, gate and state machine."""

from __future__ import annotations

from statistics import mean
from typing import cast

from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.envelope import (
    ArtifactEnvelope,
    EvidenceAuthority,
)
from market_regime_alpha.research.capital_evolution.contracts import (
    CapitalEvolutionSnapshot,
    CapitalEvolutionState,
    SymbolCapitalEvolution,
    ThemeCapitalEvolution,
)
from market_regime_alpha.research.platform_v2.configs import (
    CapitalEvolutionModelConfig,
)
from market_regime_alpha.research.platform_v2.inputs import (
    ResearchInputBundle,
    SymbolResearchObservation,
    ThemeResearchObservation,
)
from market_regime_alpha.research.theme_rotation.contracts import (
    RotationState,
    ThemeRotationSnapshot,
)


def evaluate_capital_evolution_v0(
    inputs: ResearchInputBundle,
    theme_rotation: ThemeRotationSnapshot,
    config: CapitalEvolutionModelConfig,
    *,
    code_revision: str,
) -> CapitalEvolutionSnapshot:
    rotation_by_theme = {
        item.theme_id: item for item in theme_rotation.themes
    }
    themes = tuple(
        _theme_state(item, rotation_by_theme.get(item.theme_id), config)
        for item in sorted(inputs.theme_observations, key=lambda value: value.theme_id)
    )
    membership_by_symbol = {
        item.symbol: item for item in inputs.theme_memberships
    }
    theme_by_id = {item.theme_id: item for item in themes}
    symbols = tuple(
        _symbol_state(
            item,
            (
                membership_by_symbol[item.symbol].primary_theme_id
                if item.symbol in membership_by_symbol
                else None
            ),
            theme_by_id,
            config,
        )
        for item in sorted(inputs.symbol_observations, key=lambda value: value.symbol)
    )
    reasons = (
        ("CAPITAL_EVOLUTION_DATA_INSUFFICIENT",)
        if not themes
        or all(
            item.capital_evolution_state
            is CapitalEvolutionState.DATA_INSUFFICIENT
            for item in themes
        )
        else (
            "CAPITAL_EVOLUTION_IS_MODEL_INFERENCE",
            "CAPITAL_EVOLUTION_V0_MODEL_ASSUMPTION",
        )
    )
    payload = {
        "themes": [item.to_canonical_dict() for item in themes],
        "symbols": [item.to_canonical_dict() for item in symbols],
        "reason_codes": list(reasons),
    }
    input_ids = (
        *inputs.input_artifact_ids,
        inputs.input_bundle_id,
        theme_rotation.envelope.artifact_id,
    )
    input_hashes = (
        *inputs.input_content_hashes,
        inputs.content_hash,
        theme_rotation.envelope.content_hash,
    )
    envelope = ArtifactEnvelope.create(
        artifact_type="CAPITAL_EVOLUTION_SNAPSHOT",
        artifact_payload=payload,
        decision_date=inputs.source_manifest.decision_time.value.date(),
        decision_time=inputs.source_manifest.decision_time,
        created_at=inputs.created_at,
        code_revision=code_revision,
        configuration_id=config.configuration_id,
        configuration_hash=config.configuration_hash,
        source_manifest_id=inputs.source_manifest.source_manifest_id,
        source_manifest_hash=inputs.source_manifest.content_hash,
        input_artifact_ids=input_ids,
        input_content_hashes=input_hashes,
        model_id=config.model_id,
        model_version=config.model_version,
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status=(
            "DATA_INSUFFICIENT"
            if reasons == ("CAPITAL_EVOLUTION_DATA_INSUFFICIENT",)
            else "RESEARCH_READY"
        ),
        reason_codes=reasons,
        limitations=(
            *config.assumptions,
            "INFERRED_FROM_OBSERVABLE_PROXIES_NOT_HIDDEN_ACTOR_INTENT",
        ),
    )
    return CapitalEvolutionSnapshot(
        envelope=envelope,
        themes=themes,
        symbols=symbols,
        reason_codes=reasons,
    )


def _theme_state(
    item: ThemeResearchObservation,
    rotation: object,
    config: CapitalEvolutionModelConfig,
) -> ThemeCapitalEvolution:
    rotation_state = (
        rotation.rotation_state
        if hasattr(rotation, "rotation_state")
        else RotationState.DATA_INSUFFICIENT
    )
    required = (
        item.relative_strength_1d,
        item.relative_strength_3d,
        item.relative_strength_5d,
        item.relative_strength_10d,
        item.etf_amount_expansion,
        item.amount_expansion,
        item.breadth,
        item.new_high_breadth,
        item.leader_strength,
        item.participation_change,
        item.capital_concentration,
        item.rank_persistence,
        item.amount_persistence,
        item.diffusion_score,
    )
    if (
        rotation_state is RotationState.DATA_INSUFFICIENT
        or item.confidence < config.minimum_theme_confidence
        or any(value is None for value in required)
    ):
        return _theme_result(
            item,
            None,
            CapitalEvolutionState.DATA_INSUFFICIENT,
            ("CAPITAL_EVOLUTION_DATA_INSUFFICIENT",),
        )
    values = tuple(float(value) for value in required if value is not None)
    rs = _clip(mean(values[:4]) / config.return_scale)
    score = _clip(
        rs * config.relative_strength_weight
        + _clip(values[4] / config.amount_scale) * config.etf_amount_weight
        + _clip(values[5] / config.amount_scale) * config.theme_amount_weight
        + _unit(values[6]) * config.breadth_weight
        + _unit(values[7]) * config.new_high_breadth_weight
        + _clip(values[8] / config.return_scale)
        * config.leader_strength_weight
        + _clip(values[9] / config.participation_scale)
        * config.participation_weight
        + _clip(1.0 - 2.0 * values[10]) * config.concentration_weight
        + _unit(values[11]) * config.rank_persistence_weight
        + _unit(values[12]) * config.amount_persistence_weight
        + _unit(values[13]) * config.diffusion_weight
    )
    if score >= config.ignition_threshold and (
        values[10] >= config.divergence_concentration_threshold
        or values[9] <= config.divergence_participation_threshold
    ):
        state, reason = (
            CapitalEvolutionState.DIVERGENCE,
            "CAPITAL_DIVERGENCE_GATE",
        )
    else:
        state = _score_state(score, config)
        reason = f"CAPITAL_STATE_{state.value}"
    return _theme_result(item, score, state, (reason,))


def _symbol_state(
    item: SymbolResearchObservation,
    theme_id: str | None,
    themes: dict[str, ThemeCapitalEvolution],
    config: CapitalEvolutionModelConfig,
) -> SymbolCapitalEvolution:
    required = (
        item.symbol_relative_strength,
        item.symbol_amount_expansion,
        item.theme_participation_contribution,
        item.leader_correlation,
        item.leader_lag,
        item.rank_persistence,
        item.amount_persistence,
    )
    if (
        theme_id is None
        or theme_id not in themes
        or themes[theme_id].capital_evolution_state
        is CapitalEvolutionState.DATA_INSUFFICIENT
        or any(value is None for value in required)
    ):
        return _symbol_result(
            item,
            theme_id or "UNASSIGNED",
            None,
            CapitalEvolutionState.DATA_INSUFFICIENT,
            ("CAPITAL_EVOLUTION_DATA_INSUFFICIENT",),
        )
    values = tuple(float(value) for value in required if value is not None)
    score = _clip(
        _clip(values[0] / config.return_scale)
        * config.symbol_relative_strength_weight
        + _clip(values[1] / config.amount_scale)
        * config.symbol_amount_expansion_weight
        + _clip(values[2] / config.participation_scale)
        * config.symbol_participation_weight
        + _clip(values[3]) * config.symbol_leader_correlation_weight
        + _clip(-values[4] / config.leader_lag_scale)
        * config.symbol_leader_lag_weight
        + _unit(values[5]) * config.symbol_rank_persistence_weight
        + _unit(values[6]) * config.symbol_amount_persistence_weight
    )
    return _symbol_result(
        item,
        theme_id,
        score,
        _score_state(score, config),
        (f"CAPITAL_STATE_{_score_state(score, config).value}",),
    )


def _score_state(
    score: float, config: CapitalEvolutionModelConfig
) -> CapitalEvolutionState:
    if score <= config.collapse_threshold:
        return CapitalEvolutionState.COLLAPSE
    if score <= config.exhaustion_threshold:
        return CapitalEvolutionState.EXHAUSTION
    if score < config.accumulation_threshold:
        return CapitalEvolutionState.DORMANT
    if score < config.ignition_threshold:
        return CapitalEvolutionState.ACCUMULATION
    if score < config.diffusion_threshold:
        return CapitalEvolutionState.IGNITION
    if score < config.acceleration_threshold:
        return CapitalEvolutionState.DIFFUSION
    return CapitalEvolutionState.ACCELERATION


def _theme_result(
    item: ThemeResearchObservation,
    score: float | None,
    state: CapitalEvolutionState,
    reasons: tuple[str, ...],
) -> ThemeCapitalEvolution:
    return ThemeCapitalEvolution(
        theme_id=item.theme_id,
        capital_evolution_score=score,
        capital_evolution_state=state,
        confidence=item.confidence,
        theme_relative_strength=(
            mean(
                (
                    cast(float, item.relative_strength_1d),
                    cast(float, item.relative_strength_3d),
                    cast(float, item.relative_strength_5d),
                    cast(float, item.relative_strength_10d),
                )
            )
            if all(
                value is not None
                for value in (
                    item.relative_strength_1d,
                    item.relative_strength_3d,
                    item.relative_strength_5d,
                    item.relative_strength_10d,
                )
            )
            else None
        ),
        etf_amount_expansion=item.etf_amount_expansion,
        theme_amount_expansion=item.amount_expansion,
        breadth=item.breadth,
        new_high_breadth=item.new_high_breadth,
        leader_strength=item.leader_strength,
        participation_expansion=item.participation_change,
        capital_concentration=item.capital_concentration,
        rank_persistence=item.rank_persistence,
        amount_persistence=item.amount_persistence,
        diffusion_score=item.diffusion_score,
        reason_codes=tuple(dict.fromkeys((*item.reason_codes, *reasons))),
    )


def _symbol_result(
    item: SymbolResearchObservation,
    theme_id: str,
    score: float | None,
    state: CapitalEvolutionState,
    reasons: tuple[str, ...],
) -> SymbolCapitalEvolution:
    return SymbolCapitalEvolution(
        symbol=item.symbol,
        theme_id=theme_id,
        symbol_relative_strength=item.symbol_relative_strength,
        symbol_amount_expansion=item.symbol_amount_expansion,
        theme_participation_contribution=item.theme_participation_contribution,
        leader_correlation=item.leader_correlation,
        leader_lag=item.leader_lag,
        rank_persistence=item.rank_persistence,
        amount_persistence=item.amount_persistence,
        capital_evolution_score=score,
        capital_evolution_state=state,
        confidence=1.0 if score is not None else 0.0,
        reason_codes=tuple(dict.fromkeys((*item.reason_codes, *reasons))),
    )


def _clip(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _unit(value: float) -> float:
    return _clip(2.0 * value - 1.0)
