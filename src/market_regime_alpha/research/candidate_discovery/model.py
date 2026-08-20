"""Candidate Discovery V2 with mandatory Market/Theme/Capital gates."""

from __future__ import annotations

from dataclasses import replace
from statistics import mean

from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.envelope import (
    ArtifactEnvelope,
    EvidenceAuthority,
)
from market_regime_alpha.research.candidate_discovery.contracts import (
    CandidateRecord,
    CandidateSelectionStatus,
    CandidateSet,
)
from market_regime_alpha.research.candidate_discovery.legacy_adapter import (
    LegacyCandidateFactors,
    adapt_b0_b1_candidate_factors,
)
from market_regime_alpha.research.capital_evolution.contracts import (
    CapitalEvolutionSnapshot,
    CapitalEvolutionState,
    SymbolCapitalEvolution,
)
from market_regime_alpha.research.market_regime.contracts import (
    MarketRegimeSnapshot,
    TradePermission,
)
from market_regime_alpha.research.platform_v2.configs import (
    CandidateDiscoveryModelConfig,
)
from market_regime_alpha.research.platform_v2.inputs import (
    ResearchInputView,
    SymbolResearchObservation,
    ThemeMembership,
)
from market_regime_alpha.research.cross_sectional_ranking import competition_ranks
from market_regime_alpha.research.theme_rotation.contracts import (
    RotationState,
    ThemeRotationItem,
    ThemeRotationSnapshot,
)
from market_regime_alpha.universe.contracts import TradingEligibilityStatus


_QUALIFIED_ROTATION = {
    RotationState.STARTING,
    RotationState.STRENGTHENING,
    RotationState.LEADING,
}
_QUALIFIED_CAPITAL = {
    CapitalEvolutionState.ACCUMULATION,
    CapitalEvolutionState.IGNITION,
    CapitalEvolutionState.DIFFUSION,
    CapitalEvolutionState.ACCELERATION,
}


def discover_candidates_v2(
    inputs: ResearchInputView,
    market_regime: MarketRegimeSnapshot,
    theme_rotation: ThemeRotationSnapshot,
    capital_evolution: CapitalEvolutionSnapshot,
    config: CandidateDiscoveryModelConfig,
    *,
    code_revision: str,
) -> CandidateSet:
    factors = adapt_b0_b1_candidate_factors(inputs.prediction_runs)
    theme_by_id = {item.theme_id: item for item in theme_rotation.themes}
    capital_by_symbol = {
        item.symbol: item for item in capital_evolution.symbols
    }
    memberships = {item.symbol: item for item in inputs.theme_memberships}
    observations = {item.symbol: item for item in inputs.symbol_observations}
    records = tuple(
        _reconcile(
            symbol,
            inputs,
            market_regime,
            theme_by_id,
            capital_by_symbol,
            memberships,
            observations,
            factors,
            config,
        )
        for symbol in inputs.universe_snapshot.member_symbols
    )
    viable_by_symbol = {
        item.symbol: item
        for item in records
        if item.selection_status is CandidateSelectionStatus.WATCHLIST
        and item.candidate_discovery_score is not None
    }
    viable_scores = {
        symbol: item.candidate_discovery_score
        for symbol, item in viable_by_symbol.items()
        if item.candidate_discovery_score is not None
    }
    ranks = competition_ranks(viable_scores, higher_is_better=True)
    viable = sorted(
        viable_by_symbol.values(),
        key=lambda item: (
            ranks[item.symbol],
            item.symbol,
        ),
    )
    insufficient_population = len(viable) < config.minimum_candidate_population
    ranked_by_symbol: dict[str, CandidateRecord] = {}
    selected_count = sum(
        1 for item in viable if ranks[item.symbol] <= config.top_n
    )
    boundary_tie_expanded = selected_count > min(config.top_n, len(viable))
    for item in viable:
        rank = ranks[item.symbol]
        selected = (
            not insufficient_population and rank <= config.top_n
        )
        ranked_by_symbol[item.symbol] = replace(
            item,
            rank=rank,
            selection_status=(
                CandidateSelectionStatus.SELECTED
                if selected
                else CandidateSelectionStatus.WATCHLIST
            ),
            reason_codes=tuple(
                dict.fromkeys(
                    (
                        *item.reason_codes,
                        (
                            "CANDIDATE_SELECTED"
                            if selected
                            else "CANDIDATE_POPULATION_INSUFFICIENT"
                            if insufficient_population
                            else "CANDIDATE_WATCHLIST"
                        ),
                    )
                )
            ),
        )
    finalized = tuple(
        ranked_by_symbol.get(item.symbol, item)
        for item in sorted(records, key=lambda value: value.symbol)
    )
    reasons = tuple(
        dict.fromkeys(
            (
                *(
                    ("MARKET_REGIME_PROHIBITS_RISK",)
                    if market_regime.trade_permission
                    is TradePermission.PROHIBIT
                    else ()
                ),
                *(
                    ("CANDIDATE_POPULATION_INSUFFICIENT",)
                    if insufficient_population
                    else ()
                ),
                *(
                    ("CANDIDATE_BOUNDARY_TIE_EXPANDED",)
                    if boundary_tie_expanded and not insufficient_population
                    else ()
                ),
                "CANDIDATE_SET_IS_NOT_RECOMMENDATION",
            )
        )
    )
    payload = {
        "records": [item.to_canonical_dict() for item in finalized],
        "minimum_candidate_population": config.minimum_candidate_population,
        "reason_codes": list(reasons),
    }
    stage_inputs = (
        *inputs.input_artifact_ids,
        inputs.input_bundle_id,
        market_regime.envelope.artifact_id,
        theme_rotation.envelope.artifact_id,
        capital_evolution.envelope.artifact_id,
        *(run.prediction_run_id for run in inputs.prediction_runs),
    )
    stage_hashes = (
        *inputs.input_content_hashes,
        inputs.content_hash,
        market_regime.envelope.content_hash,
        theme_rotation.envelope.content_hash,
        capital_evolution.envelope.content_hash,
        *(run.content_hash for run in inputs.prediction_runs),
    )
    envelope = ArtifactEnvelope.create(
        artifact_type="CANDIDATE_SET",
        artifact_payload=payload,
        decision_date=inputs.source_manifest.decision_time.value.date(),
        decision_time=inputs.source_manifest.decision_time,
        created_at=inputs.created_at,
        code_revision=code_revision,
        configuration_id=config.configuration_id,
        configuration_hash=config.configuration_hash,
        source_manifest_id=inputs.source_manifest.source_manifest_id,
        source_manifest_hash=inputs.source_manifest.content_hash,
        input_artifact_ids=stage_inputs,
        input_content_hashes=stage_hashes,
        model_id=config.model_id,
        model_version=config.model_version,
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status=(
            "RESEARCH_BLOCKED"
            if market_regime.trade_permission is TradePermission.PROHIBIT
            or insufficient_population
            else "RESEARCH_READY"
        ),
        reason_codes=reasons,
        limitations=config.assumptions,
    )
    return CandidateSet(
        envelope=envelope,
        records=finalized,
        minimum_candidate_population=config.minimum_candidate_population,
        reason_codes=reasons,
    )


def _reconcile(
    symbol: str,
    inputs: ResearchInputView,
    market_regime: MarketRegimeSnapshot,
    theme_by_id: dict[str, ThemeRotationItem],
    capital_by_symbol: dict[str, SymbolCapitalEvolution],
    memberships: dict[str, ThemeMembership],
    observations: dict[str, SymbolResearchObservation],
    factors: dict[str, LegacyCandidateFactors],
    config: CandidateDiscoveryModelConfig,
) -> CandidateRecord:
    membership = memberships.get(symbol)
    observation = observations.get(symbol)
    factor = factors.get(symbol)
    primary_theme = membership.primary_theme_id if membership is not None else None
    supporting = membership.supporting_theme_ids if membership is not None else ()
    theme = theme_by_id.get(primary_theme or "")
    capital = capital_by_symbol.get(symbol)
    rotation_state = (
        theme.rotation_state
        if theme is not None
        else RotationState.DATA_INSUFFICIENT
    )
    capital_state = (
        capital.capital_evolution_state
        if capital is not None
        else CapitalEvolutionState.DATA_INSUFFICIENT
    )
    base = CandidateRecord(
        symbol=symbol,
        primary_theme_id=primary_theme,
        supporting_theme_ids=supporting,
        market_regime_status=market_regime.market_state,
        theme_rotation_state=rotation_state,
        capital_evolution_state=capital_state,
        market_regime_score=_market_score(market_regime),
        theme_score=theme.rotation_score if theme is not None else None,
        capital_evolution_score=(
            capital.capital_evolution_score if capital is not None else None
        ),
        candidate_discovery_score=None,
        rank=None,
        source_feature_ids=(
            factor.source_feature_ids if factor is not None else ()
        ),
        input_artifact_ids=(
            factor.prediction_run_ids if factor is not None else ()
        ),
        selection_status=CandidateSelectionStatus.DATA_INSUFFICIENT,
        reason_codes=("CANDIDATE_NOT_YET_RECONCILED",),
    )
    if market_regime.trade_permission is TradePermission.PROHIBIT:
        return replace(
            base,
            selection_status=CandidateSelectionStatus.REJECTED,
            reason_codes=("MARKET_REGIME_PROHIBITS_RISK",),
        )
    eligibility = inputs.eligibility_snapshot.status_for(symbol)
    if eligibility is not TradingEligibilityStatus.ELIGIBLE:
        return replace(
            base,
            selection_status=CandidateSelectionStatus.REJECTED,
            reason_codes=(f"ELIGIBILITY_{eligibility.value}",),
        )
    if membership is None:
        return replace(
            base,
            selection_status=CandidateSelectionStatus.DATA_INSUFFICIENT,
            reason_codes=("THEME_MEMBERSHIP_MISSING",),
        )
    if observation is None:
        return replace(
            base,
            selection_status=CandidateSelectionStatus.DATA_INSUFFICIENT,
            reason_codes=("SYMBOL_RESEARCH_OBSERVATION_MISSING",),
        )
    gate_reasons: list[str] = []
    if not observation.liquidity_eligible:
        gate_reasons.append("INSUFFICIENT_LIQUIDITY")
    if not observation.history_complete:
        gate_reasons.append("INSUFFICIENT_HISTORY")
    if not observation.status_known:
        gate_reasons.append("TRADING_STATUS_UNKNOWN")
    if gate_reasons:
        return replace(
            base,
            source_feature_ids=observation.source_feature_ids,
            selection_status=CandidateSelectionStatus.REJECTED,
            reason_codes=tuple(gate_reasons),
        )
    if rotation_state not in _QUALIFIED_ROTATION:
        return replace(
            base,
            source_feature_ids=observation.source_feature_ids,
            selection_status=CandidateSelectionStatus.REJECTED,
            reason_codes=("THEME_ROTATION_NOT_QUALIFIED",),
        )
    if capital_state not in _QUALIFIED_CAPITAL:
        return replace(
            base,
            source_feature_ids=observation.source_feature_ids,
            selection_status=CandidateSelectionStatus.REJECTED,
            reason_codes=("CAPITAL_EVOLUTION_NOT_QUALIFIED",),
        )
    if (
        factor is None
        or factor.b0_momentum_percentile is None
        or factor.b1_balanced_percentile is None
        or base.market_regime_score is None
        or base.theme_score is None
        or base.capital_evolution_score is None
    ):
        return replace(
            base,
            source_feature_ids=observation.source_feature_ids,
            selection_status=CandidateSelectionStatus.DATA_INSUFFICIENT,
            reason_codes=("LEGACY_CANDIDATE_FACTORS_INCOMPLETE",),
        )
    score = (
        _unit(base.market_regime_score)
        * config.market_regime_weight
        + _unit(base.theme_score) * config.theme_rotation_weight
        + _unit(base.capital_evolution_score)
        * config.capital_evolution_weight
        + factor.b0_momentum_percentile * config.b0_momentum_weight
        + factor.b1_balanced_percentile * config.b1_balanced_weight
    )
    return replace(
        base,
        source_feature_ids=tuple(
            dict.fromkeys(
                (*observation.source_feature_ids, *factor.source_feature_ids)
            )
        ),
        candidate_discovery_score=score,
        selection_status=CandidateSelectionStatus.WATCHLIST,
        reason_codes=(
            "CANDIDATE_GATES_PASSED",
            "B0_B1_ARE_BASELINE_FACTORS_NOT_PROBABILITIES",
        ),
    )


def _market_score(snapshot: MarketRegimeSnapshot) -> float | None:
    values = tuple(
        value
        for value in (
            snapshot.direction_score,
            snapshot.breadth_score,
            snapshot.liquidity_score,
            snapshot.volatility_score,
            snapshot.limit_structure_score,
        )
        if value is not None
    )
    return mean(values) if values else None


def _unit(value: float) -> float:
    return max(0.0, min(1.0, (value + 1.0) / 2.0))
