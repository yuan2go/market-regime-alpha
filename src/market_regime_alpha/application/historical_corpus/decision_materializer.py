"""Historical Decision-Time adapter over canonical research computation kernels."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from statistics import fmean, median
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from market_regime_alpha.application.controlled_operation.research_config import (
    ControlledResearchPipelineConfig,
)
from market_regime_alpha.application.controlled_operation.research_runner import (
    ResolvedCandidateFeature,
    discover_controlled_candidates_from_resolved_features,
)
from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalDataOwner,
    HistoricalNormalizedBar,
    HistoricalTradingStatus,
)
from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
    HistoricalSessionComponent,
)
from market_regime_alpha.application.historical_corpus.postgres_materialization import (
    PostgresHistoricalMaterializationRepository,
)
from market_regime_alpha.application.historical_corpus.postgres_repository import (
    PostgresHistoricalCorpusRepository,
)
from market_regime_alpha.application.research_session.contracts import (
    DataAuthorityMode,
    ResearchDecisionSessionRequest,
)
from market_regime_alpha.application.research_session.kernel import (
    ResearchSessionStage,
    SessionStageComputation,
    SessionStageStatus,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId, FeatureDefinitionId, ModelId, ProviderId
from market_regime_alpha.core.time import AvailabilityTime, DecisionTime, RetrievedAt
from market_regime_alpha.data.contracts import DataEligibility, SourceArtifactReference
from market_regime_alpha.data.source_manifest import SourceManifest
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.features.technical.catalog import (
    CAPITAL_VOLUME_FEATURE_ID,
    MOVING_AVERAGE_FEATURE_ID,
    OVERHEAT_FEATURE_ID,
    PRICE_ACTION_FEATURE_ID,
    VWAP_FEATURE_ID,
    canonical_technical_feature_set,
)
from market_regime_alpha.features.technical.observables import (
    FeatureValueState,
    TechnicalFeatureComputation,
    compute_retrospective_technical_feature,
    missing_technical_feature_computation,
)
from market_regime_alpha.market_data import (
    AdjustmentMode,
    AssetType,
    CanonicalMarketBar,
    Exchange,
    PriceLimitState,
    Timeframe,
    TradingStatus,
    VolumeUnit,
)
from market_regime_alpha.research.capital_evolution.model import evaluate_capital_evolution_v0
from market_regime_alpha.research.market_regime.model import evaluate_market_regime_v0
from market_regime_alpha.research.platform_v2.inputs import (
    ETFObservation,
    MarketObservation,
    ResearchDailyBar,
    ResearchEvidenceKind,
    SymbolResearchObservation,
    ThemeMembership,
    ThemeResearchObservation,
)
from market_regime_alpha.research.theme_rotation.model import evaluate_theme_rotation_v0
from market_regime_alpha.signals.contracts import SignalFamily
from market_regime_alpha.signals.engine import (
    SIGNAL_MODEL_CONFIG_SCHEMA,
    SignalModelConfig,
    build_signal_snapshot_from_metrics,
)
from market_regime_alpha.universe.postgres_research import PostgresFreeResearchUniverseRepository
from market_regime_alpha.universe.postgres_runtime_scope import PostgresRuntimeScopeRepository
from market_regime_alpha.universe.research import project_free_research_universe_as_of
from market_regime_alpha.universe.runtime_scope import (
    RuntimeEligibilityObservation,
    RuntimeScopeDecision,
    UniverseScopeKind,
    build_runtime_scope,
)


NORMALIZED_DATASET_KIND = "NORMALIZED_DATASET"
FREE_RESEARCH_UNIVERSE_KIND = "FREE_RESEARCH_UNIVERSE"
GLOBAL_RESEARCH_THEME_ID = "PHASE_E_GLOBAL_RESEARCH_SCOPE"
_COMPONENT_ORDINAL = {item: index for index, item in enumerate(HistoricalComponentKind, 1)}


@dataclass(frozen=True, slots=True)
class _HistoricalResearchContext:
    source_manifest: SourceManifest
    market_observation: MarketObservation | None
    theme_observations: tuple[ThemeResearchObservation, ...]
    symbol_observations: tuple[SymbolResearchObservation, ...]
    theme_memberships: tuple[ThemeMembership, ...]
    etf_observations: tuple[ETFObservation, ...]
    stock_daily_bars: tuple[ResearchDailyBar, ...]
    input_artifact_ids: tuple[ArtifactId, ...]
    input_content_hashes: tuple[str, ...]
    created_at: datetime
    content_hash: str
    input_bundle_id: ArtifactId
    evidence_kind: ResearchEvidenceKind = ResearchEvidenceKind.HISTORICAL_IMMUTABLE_ARCHIVE
    data_eligibility: DataEligibility = DataEligibility.EXPLORATORY

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "source_manifest": self.source_manifest.to_canonical_dict(),
            "market_observation": (
                None if self.market_observation is None else self.market_observation.to_canonical_dict()
            ),
            "theme_observations": [item.to_canonical_dict() for item in self.theme_observations],
            "symbol_observations": [item.to_canonical_dict() for item in self.symbol_observations],
            "theme_memberships": [item.to_canonical_dict() for item in self.theme_memberships],
            "etf_observations": [item.to_canonical_dict() for item in self.etf_observations],
            "stock_daily_bars": [item.to_canonical_dict() for item in self.stock_daily_bars],
            "input_artifact_ids": [str(item) for item in self.input_artifact_ids],
            "input_content_hashes": list(self.input_content_hashes),
            "created_at": self.created_at.isoformat(),
            "content_hash": self.content_hash,
            "input_bundle_id": str(self.input_bundle_id),
            "evidence_kind": self.evidence_kind.value,
            "data_eligibility": self.data_eligibility.value,
        }


class HistoricalDecisionMaterializer:
    """Actively produce historical state while preserving true retrieval time."""

    def __init__(
        self,
        *,
        run_id: ArtifactId,
        corpus_repository: PostgresHistoricalCorpusRepository,
        component_repository: PostgresHistoricalMaterializationRepository,
        universe_repository: PostgresFreeResearchUniverseRepository,
        scope_repository: PostgresRuntimeScopeRepository,
    ) -> None:
        self._run_id = run_id
        self._corpus = corpus_repository
        self._components = component_repository
        self._universes = universe_repository
        self._scopes = scope_repository

    def compute_stage(
        self,
        *,
        request: ResearchDecisionSessionRequest,
        stage: ResearchSessionStage,
        input_references: tuple[ValidationArtifactReference, ...],
    ) -> SessionStageComputation:
        if request.data_authority_mode is not DataAuthorityMode.FREE_RESEARCH_ARCHIVE:
            raise ValueError("Historical materializer only accepts frozen free archives")
        if stage is ResearchSessionStage.SCOPE:
            return self._scope_stage(request)
        if stage is ResearchSessionStage.DECISION:
            return self._decision_stage(request, input_references)
        return SessionStageComputation(
            status=SessionStageStatus.NOT_ESTIMABLE,
            output_references=(),
            input_references=input_references,
            completed_at=request.materialized_at,
            reason_codes=(f"PHASE_E_{stage.value}_PENDING_KERNEL",),
        )

    def _scope_stage(self, request: ResearchDecisionSessionRequest) -> SessionStageComputation:
        normalized_reference = _required_reference(request, NORMALIZED_DATASET_KIND)
        universe_reference = _required_reference(request, FREE_RESEARCH_UNIVERSE_KIND)
        package = self._corpus.load(normalized_reference)
        owner = package.owner
        base_universe = self._universes.get(universe_reference.artifact_id)
        if base_universe.snapshot_hash != universe_reference.content_hash:
            raise ValueError("Historical Security Master owner hash mismatch")
        projected = self._universes.publish(
            project_free_research_universe_as_of(
                base_universe,
                as_of_date=request.trading_date,
            )
        )
        policy = self._scopes.get_policy(request.runtime_scope_policy_id)
        if policy.policy_hash != request.runtime_scope_policy_hash:
            raise ValueError("Historical Runtime Scope Policy hash mismatch")
        if any(item.kind is not UniverseScopeKind.WATCHLIST for item in policy.selectors):
            raise ValueError("Phase E vertical slice requires frozen WATCHLIST selectors")
        stock_symbols = tuple(
            sorted({symbol for item in policy.selectors for symbol in item.symbols})
        )
        bars = _normalized_bars(owner)
        observations = tuple(
            _eligibility_observation(
                symbol=symbol,
                request=request,
                bars=bars,
                universe=projected,
                source_reference=normalized_reference,
            )
            for symbol in stock_symbols
        )
        scope = build_runtime_scope(
            policy=policy,
            as_of=request.decision_time,
            built_at=request.materialized_at,
            security_master=projected,
            eligibility_observations=observations,
            membership_snapshots=(),
            code_revision=request.code_revision,
        )
        scope = self._scopes.publish(policy=policy, receipt=scope)
        membership = {
            item.symbol: item.decision is RuntimeScopeDecision.INCLUDED
            for item in scope.records
        }
        source_max = _source_max_event_time(bars, request.decision_time)
        component = self._put_component(
            request=request,
            kind=HistoricalComponentKind.DYNAMIC_POOL,
            source_max_event_time=source_max,
            source_references=(
                normalized_reference,
                universe_reference,
                ValidationArtifactReference(
                    "RESEARCH_UNIVERSE_POLICY", policy.policy_id, policy.policy_hash
                ),
                ValidationArtifactReference(
                    "RUNTIME_SCOPE", scope.scope_id, scope.scope_hash
                ),
            ),
            payload={
                "scope": scope.to_canonical_dict(),
                "membership": [
                    {"symbol": symbol, "included": membership[symbol]}
                    for symbol in sorted(membership)
                ],
                "coverage": {
                    "requested": len(membership),
                    "included": sum(membership.values()),
                    "unknown": sum(
                        item.decision is RuntimeScopeDecision.UNKNOWN for item in scope.records
                    ),
                },
                "limitations": [
                    "CURRENT_SECURITY_MASTER_PROJECTED_RETROSPECTIVELY",
                    "NO_SILENT_MISSING_DATA_INCLUSION",
                ],
            },
        )
        return SessionStageComputation(
            status=SessionStageStatus.COMPLETE,
            output_references=_references(
                (
                    ValidationArtifactReference(
                        "RUNTIME_SCOPE", scope.scope_id, scope.scope_hash
                    ),
                    component.reference,
                )
            ),
            input_references=_references((normalized_reference, universe_reference)),
            completed_at=request.materialized_at,
            reason_codes=("HISTORICAL_DECISION_SCOPE_MATERIALIZED",),
        )

    def _decision_stage(
        self,
        request: ResearchDecisionSessionRequest,
        input_references: tuple[ValidationArtifactReference, ...],
    ) -> SessionStageComputation:
        normalized_reference = _required_reference(request, NORMALIZED_DATASET_KIND)
        package = self._corpus.load(normalized_reference)
        owner = package.owner
        bars = _normalized_bars(owner)
        scope_reference = _single_reference(input_references, "RUNTIME_SCOPE")
        pool_reference = _single_reference(input_references, "HISTORICAL_DYNAMIC_POOL")
        scope = self._scopes.get(scope_reference.artifact_id)
        if scope.scope_hash != scope_reference.content_hash:
            raise ValueError("Historical Runtime Scope owner hash mismatch")
        stock_symbols = tuple(item.symbol for item in scope.records)
        pool_membership = {
            item.symbol: item.decision is RuntimeScopeDecision.INCLUDED
            for item in scope.records
        }
        context_symbols = tuple(
            sorted(set(owner.coverage.expected_symbols) - set(stock_symbols))
        )
        computations = _compute_features(
            owner=owner,
            stock_symbols=stock_symbols,
            decision_time=request.decision_time,
        )
        source_max = _source_max_event_time(bars, request.decision_time)
        feature_component = self._put_component(
            request=request,
            kind=HistoricalComponentKind.FEATURE,
            source_max_event_time=source_max,
            source_references=(normalized_reference, pool_reference),
            payload={
                "features": [_feature_dict(item) for item in computations],
                "symbol_count": len(stock_symbols),
                "available_value_count": sum(
                    value.state is FeatureValueState.AVAILABLE
                    for item in computations
                    for value in item.values
                ),
                "missing_value_count": sum(
                    value.state is FeatureValueState.MISSING
                    for item in computations
                    for value in item.values
                ),
            },
        )
        context = _build_context(
            owner=owner,
            stock_symbols=stock_symbols,
            context_symbols=context_symbols,
            decision_time=request.decision_time,
            created_at=request.materialized_at,
            source_reference=normalized_reference,
            computations=computations,
        )
        configuration = ControlledResearchPipelineConfig.create()
        market = evaluate_market_regime_v0(
            context, configuration.market_regime, code_revision=request.code_revision
        )
        market_component = self._put_component(
            request=request,
            kind=HistoricalComponentKind.MARKET_REGIME,
            source_max_event_time=source_max,
            source_references=(feature_component.reference, normalized_reference),
            payload=market.to_canonical_dict(),
        )
        etf_component = self._put_component(
            request=request,
            kind=HistoricalComponentKind.ETF,
            source_max_event_time=source_max,
            source_references=(normalized_reference,),
            payload={
                "context_symbols": list(context_symbols),
                "observations": [item.to_canonical_dict() for item in context.etf_observations],
                "status": "AVAILABLE" if context.etf_observations else "NOT_ESTIMABLE",
                "reason_codes": (
                    ["FROZEN_CONTEXT_INSTRUMENTS_RESOLVED"]
                    if context.etf_observations
                    else ["ETF_CONTEXT_NOT_IN_FROZEN_DATASET"]
                ),
            },
        )
        themes = evaluate_theme_rotation_v0(
            context, configuration.theme_rotation, code_revision=request.code_revision
        )
        theme_component = self._put_component(
            request=request,
            kind=HistoricalComponentKind.THEME,
            source_max_event_time=source_max,
            source_references=(feature_component.reference, etf_component.reference),
            payload=themes.to_canonical_dict(),
            limitations=("GLOBAL_RESEARCH_SCOPE_IS_NOT_INDUSTRY_CLASSIFICATION",),
        )
        capital = evaluate_capital_evolution_v0(
            context,
            themes,
            configuration.capital_evolution,
            code_revision=request.code_revision,
        )
        capital_component = self._put_component(
            request=request,
            kind=HistoricalComponentKind.CAPITAL,
            source_max_event_time=source_max,
            source_references=(feature_component.reference, theme_component.reference),
            payload=capital.to_canonical_dict(),
            limitations=("PUBLIC_PROXIES_DO_NOT_IDENTIFY_HIDDEN_CAPITAL_INTENT",),
        )
        resolved = _candidate_features(computations, feature_component.reference)
        candidates = discover_controlled_candidates_from_resolved_features(
            inputs=context,
            universe_symbols=stock_symbols,
            resolved_features=resolved,
            feature_bundle_reference=(
                feature_component.component_id,
                feature_component.component_hash,
            ),
            decision_time=DecisionTime(request.decision_time),
            market_regime=market,
            theme_rotation=themes,
            capital_evolution=capital,
            configuration=configuration.candidate_discovery,
            code_revision=request.code_revision,
            dynamic_pool_membership=pool_membership,
            dynamic_pool_reference=(pool_reference.artifact_id, pool_reference.content_hash),
        )
        candidate_component = self._put_component(
            request=request,
            kind=HistoricalComponentKind.CANDIDATE,
            source_max_event_time=source_max,
            source_references=(
                feature_component.reference,
                market_component.reference,
                theme_component.reference,
                capital_component.reference,
                pool_reference,
            ),
            payload=candidates.to_canonical_dict(),
        )
        signal_config = _signal_configuration(request.decision_time)
        snapshots = tuple(
            build_signal_snapshot_from_metrics(
                candidate_set=candidates,
                configuration=signal_config,
                symbol=item.symbol,
                price_action_return=_feature_float(
                    computations, item.symbol, PRICE_ACTION_FEATURE_ID, "return_3"
                ),
                volume_ratio=_feature_float(
                    computations, item.symbol, CAPITAL_VOLUME_FEATURE_ID, "amount_ratio_5"
                ),
                trend_return=_feature_float(
                    computations,
                    item.symbol,
                    MOVING_AVERAGE_FEATURE_ID,
                    "price_vs_sma20_return",
                ),
                price_vs_vwap_return=_feature_float(
                    computations, item.symbol, VWAP_FEATURE_ID, "price_vs_vwap_return"
                ),
                overheat_return=_feature_float(
                    computations, item.symbol, OVERHEAT_FEATURE_ID, "short_return"
                ),
                reason_codes=("RETROSPECTIVE_EVENT_TIME",),
                source_artifact_pairs=(
                    (feature_component.component_id, feature_component.component_hash),
                ),
                decision_time=DecisionTime(request.decision_time),
                created_at=request.materialized_at,
                code_revision=request.code_revision,
            )
            for item in candidates.selected
        )
        signal_component = self._put_component(
            request=request,
            kind=HistoricalComponentKind.SIGNAL,
            source_max_event_time=source_max,
            source_references=(candidate_component.reference, feature_component.reference),
            payload={
                "configuration": signal_config.to_canonical_dict(),
                "snapshots": [item.to_canonical_dict() for item in snapshots],
                "selected_candidate_count": len(candidates.selected),
                "signal_count": len(snapshots),
            },
        )
        outputs = (
            feature_component.reference,
            market_component.reference,
            etf_component.reference,
            theme_component.reference,
            capital_component.reference,
            candidate_component.reference,
            signal_component.reference,
        )
        return SessionStageComputation(
            status=SessionStageStatus.COMPLETE,
            output_references=_references(outputs),
            input_references=_references((*input_references, normalized_reference)),
            completed_at=request.materialized_at,
            reason_codes=("HISTORICAL_DECISION_STATE_MATERIALIZED",),
        )

    def _put_component(
        self,
        *,
        request: ResearchDecisionSessionRequest,
        kind: HistoricalComponentKind,
        source_max_event_time: datetime,
        source_references: tuple[ValidationArtifactReference, ...],
        payload: Mapping[str, Any],
        limitations: tuple[str, ...] = (),
    ) -> HistoricalSessionComponent:
        component = HistoricalSessionComponent.create(
            run_id=self._run_id,
            session_id=request.session_id,
            trading_date=request.trading_date,
            component_kind=kind,
            source_max_event_time=source_max_event_time,
            materialized_at=request.materialized_at,
            source_references=source_references,
            payload=payload,
            limitations=limitations,
        )
        return self._components.put(component=component, ordinal=_COMPONENT_ORDINAL[kind])


def _required_reference(
    request: ResearchDecisionSessionRequest,
    artifact_kind: str,
) -> ValidationArtifactReference:
    matches = tuple(
        item for item in request.configuration_references if item.artifact_kind == artifact_kind
    )
    if len(matches) != 1:
        raise ValueError(f"Historical session requires one {artifact_kind} owner")
    return matches[0]


def _single_reference(
    references: tuple[ValidationArtifactReference, ...], artifact_kind: str
) -> ValidationArtifactReference:
    matches = tuple(item for item in references if item.artifact_kind == artifact_kind)
    if len(matches) != 1:
        raise ValueError(f"Historical stage requires one {artifact_kind} reference")
    return matches[0]


def _normalized_bars(owner: HistoricalDataOwner) -> tuple[HistoricalNormalizedBar, ...]:
    records = tuple(item for part in owner.partitions for item in part.records)
    if any(not isinstance(item, HistoricalNormalizedBar) for item in records):
        raise ValueError("Historical materialization requires a normalized owner")
    return tuple(item for item in records if isinstance(item, HistoricalNormalizedBar))


def _source_max_event_time(
    bars: tuple[HistoricalNormalizedBar, ...], decision_time: datetime
) -> datetime:
    admitted = tuple(item.event_end for item in bars if item.event_end <= decision_time)
    if not admitted:
        raise ValueError("Historical session has no source event by DecisionTime")
    return max(admitted)


def _eligibility_observation(
    *,
    symbol: str,
    request: ResearchDecisionSessionRequest,
    bars: tuple[HistoricalNormalizedBar, ...],
    universe: Any,
    source_reference: ValidationArtifactReference,
) -> RuntimeEligibilityObservation:
    daily = tuple(
        item
        for item in bars
        if item.symbol == symbol
        and item.timeframe is Timeframe.DAILY
        and item.event_end <= request.decision_time
    )
    intraday = tuple(
        item
        for item in bars
        if item.symbol == symbol
        and item.timeframe is Timeframe.MINUTE_5
        and item.market_date == request.trading_date
        and item.event_end <= request.decision_time
    )
    master = next((item for item in universe.records if item.symbol == symbol), None)
    amounts = tuple(item.amount for item in daily[-20:] if item.amount is not None)
    latest = daily[-1] if daily else None
    source_max = max(
        (item.event_end for item in (*daily, *intraday)),
        default=request.decision_time,
    )
    included = (
        None
        if master is None or master.membership_status.value == "UNKNOWN"
        else master.membership_status.value == "INCLUDED"
    )
    return RuntimeEligibilityObservation.create(
        symbol=symbol,
        observed_at=source_max,
        known_at=request.materialized_at,
        included=included,
        listing_status=None if master is None else master.listing_status.value,
        is_st=None if latest is None else latest.st_status,
        suspended=False if intraday else None,
        history_sessions=len(daily),
        median_daily_amount=None if not amounts else median(amounts),
        source_references=(source_reference,),
    )


def _compute_features(
    *,
    owner: HistoricalDataOwner,
    stock_symbols: tuple[str, ...],
    decision_time: datetime,
) -> tuple[TechnicalFeatureComputation, ...]:
    bars = _normalized_bars(owner)
    feature_set = canonical_technical_feature_set(
        effective_from=datetime(1990, 1, 1, tzinfo=UTC)
    )
    definition_by_id = {item.feature_id: item for item in feature_set.definitions}
    results: list[TechnicalFeatureComputation] = []
    for symbol in stock_symbols:
        daily_rows = tuple(
            item
            for item in bars
            if item.symbol == symbol
            and item.timeframe is Timeframe.DAILY
            and item.event_end <= decision_time
            and item.open is not None
        )
        minute_rows = tuple(
            item
            for item in bars
            if item.symbol == symbol
            and item.timeframe is Timeframe.MINUTE_5
            and item.market_date == decision_time.date()
            and item.event_end <= decision_time
            and item.open is not None
        )
        daily = _canonical_bars(daily_rows, asset_type=AssetType.A_SHARE)
        prior_close = daily[-1].close if daily else None
        minute = _canonical_bars(
            minute_rows,
            asset_type=AssetType.A_SHARE,
            initial_previous_close=prior_close,
        )
        for configuration in feature_set.configurations:
            selected = configuration.parameter_map().get("selected_timeframe")
            selected_bars = daily if selected == Timeframe.DAILY.value else minute
            if selected_bars:
                computation = compute_retrospective_technical_feature(
                    feature_id=configuration.feature_id,
                    bars=selected_bars,
                    configuration=configuration,
                    decision_time=decision_time,
                )
            else:
                definition = definition_by_id[configuration.feature_id]
                computation = missing_technical_feature_computation(
                    feature_id=configuration.feature_id,
                    symbol=symbol,
                    timeframe=(
                        Timeframe.DAILY
                        if selected == Timeframe.DAILY.value
                        else Timeframe.MINUTE_5
                    ),
                    available_at=owner.retrieved_at,
                    configuration=configuration,
                    output_ids=tuple(item.output_id for item in definition.output_schema),
                    reason_code="HISTORICAL_SOURCE_BARS_MISSING_AT_DECISION_TIME",
                )
            results.append(computation)
    return tuple(sorted(results, key=lambda item: (item.symbol, item.feature_id)))


def _canonical_bars(
    rows: tuple[HistoricalNormalizedBar, ...],
    *,
    asset_type: AssetType,
    initial_previous_close: Decimal | None = None,
) -> tuple[CanonicalMarketBar, ...]:
    previous = initial_previous_close
    result: list[CanonicalMarketBar] = []
    for item in rows:
        assert item.open is not None and item.high is not None
        assert item.low is not None and item.close is not None
        exchange = Exchange(item.symbol[-2:])
        bar = CanonicalMarketBar.create(
            symbol=item.symbol,
            exchange=exchange,
            asset_type=asset_type,
            timeframe=item.timeframe,
            market_date=item.market_date,
            event_start=item.event_start,
            event_end=item.event_end,
            available_at=item.retrieved_at,
            open=item.open,
            high=item.high,
            low=item.low,
            close=item.close,
            previous_close=previous,
            volume=item.volume,
            volume_unit=VolumeUnit.SHARES,
            amount=item.amount,
            turnover_rate=None,
            adjustment_mode=AdjustmentMode.RAW,
            adjustment_factor=Decimal("1"),
            trading_status=(
                TradingStatus.TRADING
                if item.trading_status is HistoricalTradingStatus.TRADING
                else TradingStatus.UNKNOWN
            ),
            price_limit_state=PriceLimitState.UNKNOWN,
            source_artifact_id=item.bar_id,
            source_content_hash=item.content_hash,
        )
        result.append(bar)
        previous = item.close
    return tuple(result)


def _feature_dict(item: TechnicalFeatureComputation) -> dict[str, Any]:
    return {
        "feature_id": item.feature_id,
        "symbol": item.symbol,
        "timeframe": item.timeframe.value,
        "available_at": item.available_at.isoformat(),
        "configuration_id": str(item.configuration_id),
        "configuration_hash": item.configuration_hash,
        "values": [
            {
                "output_id": value.output_id,
                "state": value.state.value,
                "value": (
                    str(value.value) if isinstance(value.value, Decimal) else value.value
                ),
                "available_at": value.available_at.isoformat(),
                "source_bar_ids": [str(value_id) for value_id in value.source_bar_ids],
                "source_bar_hashes": list(value.source_bar_hashes),
                "missing_reason_codes": list(value.missing_reason_codes),
            }
            for value in item.values
        ],
        "limitations": list(item.limitations),
    }


def _candidate_features(
    computations: tuple[TechnicalFeatureComputation, ...],
    reference: ValidationArtifactReference,
) -> dict[tuple[str, str, str], ResolvedCandidateFeature]:
    return {
        (symbol, feature_id, output_id): ResolvedCandidateFeature(
            artifact_id=reference.artifact_id,
            content_hash=reference.content_hash,
            value=_feature_float(computations, symbol, feature_id, output_id),
        )
        for symbol in sorted({item.symbol for item in computations})
        for feature_id, output_id in (
            (PRICE_ACTION_FEATURE_ID, "return_3"),
            (CAPITAL_VOLUME_FEATURE_ID, "amount_ratio_5"),
        )
    }


def _feature_float(
    computations: tuple[TechnicalFeatureComputation, ...],
    symbol: str,
    feature_id: str,
    output_id: str,
) -> float | None:
    matches = tuple(
        value
        for item in computations
        if item.symbol == symbol and item.feature_id == feature_id
        for value in item.values
        if value.output_id == output_id
    )
    if len(matches) != 1 or matches[0].state is not FeatureValueState.AVAILABLE:
        return None
    value = matches[0].value
    return float(value) if isinstance(value, (Decimal, int)) else None


def _build_context(
    *,
    owner: HistoricalDataOwner,
    stock_symbols: tuple[str, ...],
    context_symbols: tuple[str, ...],
    decision_time: datetime,
    created_at: datetime,
    source_reference: ValidationArtifactReference,
    computations: tuple[TechnicalFeatureComputation, ...],
) -> _HistoricalResearchContext:
    bars = _normalized_bars(owner)
    retrieved_at = max(item.retrieved_at for item in bars)
    source_manifest = SourceManifest(
        provider_profile_id=f"{owner.provider_id}-historical-retrospective",
        decision_time=DecisionTime(decision_time),
        source_artifacts=(
            SourceArtifactReference(
                artifact_id=owner.owner_id,
                provider_id=ProviderId(owner.provider_id),
                retrieved_at=RetrievedAt(retrieved_at),
                content_hash=owner.content_hash,
                locator=f"postgres-owner:{owner.owner_id}@{owner.content_hash}",
            ),
        ),
        fields=(),
        source_conflicts=(),
        limitations=(
            "FORMAL_PIT_NOT_ESTABLISHED",
            "PIT_INCOMPLETE",
            "RETROSPECTIVE_EVENT_TIME",
        ),
        data_eligibility=DataEligibility.EXPLORATORY,
    )
    stock_series = {
        symbol: _daily_series(bars, symbol, decision_time) for symbol in stock_symbols
    }
    context_series = {
        symbol: _daily_series(bars, symbol, decision_time) for symbol in context_symbols
    }
    etf_symbol = next((item for item in context_symbols if _is_etf_symbol(item)), None)
    benchmark = context_series.get(etf_symbol, ()) if etf_symbol is not None else ()
    market = _market_observation(
        bars=bars,
        stock_symbols=stock_symbols,
        stock_series=stock_series,
        benchmark=benchmark,
        decision_time=decision_time,
        retrieved_at=retrieved_at,
        source_id=owner.owner_id,
    )
    theme = _theme_observation(
        stock_series=stock_series,
        benchmark=benchmark,
        etf_symbol=etf_symbol,
        retrieved_at=retrieved_at,
        source_id=owner.owner_id,
    )
    symbols = tuple(
        _symbol_observation(
            symbol=symbol,
            series=stock_series[symbol],
            all_series=stock_series,
            computations=computations,
            retrieved_at=retrieved_at,
            source_id=owner.owner_id,
        )
        for symbol in stock_symbols
    )
    etfs = (
        ()
        if etf_symbol is None or len(benchmark) < 6
        else (
            ETFObservation(
                etf_id=etf_symbol,
                theme_id=GLOBAL_RESEARCH_THEME_ID,
                available_at=AvailabilityTime(retrieved_at),
                source_artifact_id=owner.owner_id,
                relative_strength=_return(benchmark, 5) or 0.0,
                amount_expansion=_amount_expansion(benchmark) or 0.0,
            ),
        )
    )
    memberships = tuple(
        ThemeMembership(symbol=symbol, primary_theme_id=GLOBAL_RESEARCH_THEME_ID)
        for symbol in stock_symbols
    )
    daily_bars = tuple(
        ResearchDailyBar(
            symbol=item.symbol,
            session_date=item.market_date,
            available_at=AvailabilityTime(item.retrieved_at),
            source_artifact_id=item.bar_id,
            close=float(item.close),
            amount=float(item.amount or Decimal("0")),
        )
        for series in stock_series.values()
        for item in series
        if item.close is not None
    )
    identity = {
        "source_manifest_id": str(source_manifest.source_manifest_id),
        "source_manifest_hash": source_manifest.content_hash,
        "market": None if market is None else market.to_canonical_dict(),
        "themes": [] if theme is None else [theme.to_canonical_dict()],
        "symbols": [item.to_canonical_dict() for item in symbols],
        "memberships": [item.to_canonical_dict() for item in memberships],
        "etfs": [item.to_canonical_dict() for item in etfs],
        "created_at": created_at.isoformat(),
    }
    digest = canonical_hash(identity)
    return _HistoricalResearchContext(
        source_manifest=source_manifest,
        market_observation=market,
        theme_observations=() if theme is None else (theme,),
        symbol_observations=symbols,
        theme_memberships=memberships,
        etf_observations=etfs,
        stock_daily_bars=daily_bars,
        input_artifact_ids=(source_reference.artifact_id,),
        input_content_hashes=(source_reference.content_hash,),
        created_at=created_at,
        content_hash=digest,
        input_bundle_id=ArtifactId(f"historical-research-context-{digest[7:31]}"),
    )


def _daily_series(
    bars: tuple[HistoricalNormalizedBar, ...], symbol: str, decision_time: datetime
) -> tuple[HistoricalNormalizedBar, ...]:
    return tuple(
        item
        for item in bars
        if item.symbol == symbol
        and item.timeframe is Timeframe.DAILY
        and item.event_end <= decision_time
        and item.close is not None
    )


def _market_observation(
    *,
    bars: tuple[HistoricalNormalizedBar, ...],
    stock_symbols: tuple[str, ...],
    stock_series: Mapping[str, tuple[HistoricalNormalizedBar, ...]],
    benchmark: tuple[HistoricalNormalizedBar, ...],
    decision_time: datetime,
    retrieved_at: datetime,
    source_id: ArtifactId,
) -> MarketObservation:
    returns = tuple(value for series in stock_series.values() if (value := _return(series, 3)) is not None)
    intraday_returns: list[float] = []
    ranges: list[float] = []
    for symbol in stock_symbols:
        minutes = tuple(
            item
            for item in bars
            if item.symbol == symbol
            and item.timeframe is Timeframe.MINUTE_5
            and item.market_date == decision_time.date()
            and item.event_end <= decision_time
            and item.close is not None
        )
        prior = stock_series[symbol][-1].close if stock_series[symbol] else None
        if minutes and prior is not None:
            assert minutes[-1].close is not None
            highs = tuple(float(item.high) for item in minutes if item.high is not None)
            lows = tuple(float(item.low) for item in minutes if item.low is not None)
            intraday_returns.append(float(minutes[-1].close / prior - Decimal("1")))
            if highs and lows:
                ranges.append((max(highs) - min(lows)) / float(prior))
    amount_change = _amount_expansion(benchmark)
    coverage = len(intraday_returns) / len(stock_symbols) if stock_symbols else 0.0
    return MarketObservation(
        available_at=AvailabilityTime(retrieved_at),
        source_artifact_id=source_id,
        market_direction_return=(
            _return(benchmark, 3) if benchmark else (fmean(returns) if returns else None)
        ),
        market_intraday_range_to_cutoff=fmean(ranges) if ranges else None,
        market_amount_change_same_cutoff=amount_change,
        candidate_breadth_at_cutoff=(
            sum(item > 0 for item in intraday_returns) / len(intraday_returns)
            if intraday_returns
            else None
        ),
        limit_structure_score=(
            (
                sum(item >= 0.095 for item in intraday_returns)
                - sum(item <= -0.095 for item in intraday_returns)
            )
            / len(intraday_returns)
            if intraday_returns
            else None
        ),
        coverage=coverage,
        reason_codes=("RETROSPECTIVE_CROSS_SECTIONAL_MARKET_CONTEXT",),
    )


def _theme_observation(
    *,
    stock_series: Mapping[str, tuple[HistoricalNormalizedBar, ...]],
    benchmark: tuple[HistoricalNormalizedBar, ...],
    etf_symbol: str | None,
    retrieved_at: datetime,
    source_id: ArtifactId,
) -> ThemeResearchObservation | None:
    eligible = tuple(series for series in stock_series.values() if len(series) >= 21)
    if not eligible:
        return None
    benchmark_returns = {window: _return(benchmark, window) for window in (1, 3, 5, 10)}
    relative = {
        window: fmean(
            value - (benchmark_returns[window] or 0.0)
            for series in eligible
            if (value := _return(series, window)) is not None
        )
        for window in (1, 3, 5, 10)
    }
    return5 = tuple(_return(series, 5) or 0.0 for series in eligible)
    amount_values = tuple(
        value for series in eligible if (value := _amount_expansion(series)) is not None
    )
    latest_amounts = sorted(
        (float(series[-1].amount or Decimal("0")) for series in eligible), reverse=True
    )
    total_amount = sum(latest_amounts)
    breadth = sum(value > 0 for value in return5) / len(return5)
    return ThemeResearchObservation(
        theme_id=GLOBAL_RESEARCH_THEME_ID,
        theme_name="Phase E Global Research Scope",
        benchmark_id=etf_symbol or "NO_ETF_CONTEXT",
        proxy_etf_ids=() if etf_symbol is None else (etf_symbol,),
        available_at=AvailabilityTime(retrieved_at),
        source_artifact_id=source_id,
        relative_strength_1d=relative[1],
        relative_strength_3d=relative[3],
        relative_strength_5d=relative[5],
        relative_strength_10d=relative[10],
        amount_expansion=fmean(amount_values) if amount_values else None,
        etf_amount_expansion=_amount_expansion(benchmark),
        breadth=breadth,
        new_high_breadth=sum(
            float(series[-1].close or 0) >= max(float(item.close or 0) for item in series[-21:-1])
            for series in eligible
        )
        / len(eligible),
        leader_strength=max(return5) - (benchmark_returns[5] or 0.0),
        participation_change=breadth - 0.5,
        rank_persistence=0.5,
        amount_persistence=sum(value > 0 for value in amount_values) / len(amount_values) if amount_values else None,
        capital_concentration=(sum(latest_amounts[:5]) / total_amount if total_amount > 0 else None),
        diffusion_score=breadth,
        confidence=len(eligible) / len(stock_series),
        reason_codes=(
            "GLOBAL_SCOPE_PROXY_NOT_INDUSTRY_CLASSIFICATION",
            "RETROSPECTIVE_EVENT_TIME",
        ),
    )


def _symbol_observation(
    *,
    symbol: str,
    series: tuple[HistoricalNormalizedBar, ...],
    all_series: Mapping[str, tuple[HistoricalNormalizedBar, ...]],
    computations: tuple[TechnicalFeatureComputation, ...],
    retrieved_at: datetime,
    source_id: ArtifactId,
) -> SymbolResearchObservation:
    market_returns = tuple(
        value for item in all_series.values() if (value := _return(item, 5)) is not None
    )
    symbol_return = _return(series, 5)
    amount = _amount_expansion(series)
    complete = len(series) >= 61
    return SymbolResearchObservation(
        symbol=symbol,
        available_at=AvailabilityTime(retrieved_at),
        source_artifact_id=source_id,
        symbol_relative_strength=(
            None
            if symbol_return is None or not market_returns
            else symbol_return - fmean(market_returns)
        ),
        symbol_amount_expansion=amount,
        theme_participation_contribution=(
            None if amount is None else amount / max(1, len(all_series))
        ),
        leader_correlation=0.0 if complete else None,
        leader_lag=0.0 if complete else None,
        rank_persistence=0.5 if complete else None,
        amount_persistence=(1.0 if amount is not None and amount > 0 else 0.0) if complete else None,
        liquidity_eligible=bool(series and series[-1].amount is not None),
        history_complete=complete,
        status_known=bool(series and series[-1].trading_status is not HistoricalTradingStatus.UNKNOWN),
        source_feature_ids=(
            FeatureDefinitionId(PRICE_ACTION_FEATURE_ID),
            FeatureDefinitionId(CAPITAL_VOLUME_FEATURE_ID),
        ),
        reason_codes=("RETROSPECTIVE_GLOBAL_SCOPE_PROXY",),
    )


def _return(series: tuple[HistoricalNormalizedBar, ...], window: int) -> float | None:
    if len(series) <= window:
        return None
    latest = series[-1].close
    baseline = series[-window - 1].close
    if latest is None or baseline is None:
        return None
    return float(latest / baseline - Decimal("1"))


def _amount_expansion(series: tuple[HistoricalNormalizedBar, ...]) -> float | None:
    if len(series) < 6 or series[-1].amount is None:
        return None
    prior = tuple(item.amount for item in series[-6:-1])
    if any(item is None for item in prior):
        return None
    baseline = sum((item for item in prior if item is not None), Decimal("0")) / Decimal(5)
    if baseline <= 0:
        return None
    return float(series[-1].amount / baseline - Decimal("1"))


def _is_etf_symbol(symbol: str) -> bool:
    return symbol.startswith(("510", "511", "512", "513", "515", "516", "518", "159", "588"))


def _signal_configuration(decision_time: datetime) -> SignalModelConfig:
    local_decision = decision_time.astimezone(ZoneInfo("Asia/Shanghai"))
    return SignalModelConfig(
        profile_id="phase-e-historical-signal-v1",
        model_id=ModelId("signal-five-confirmation-v1"),
        model_version="1.0.0-exploratory",
        decision_profile_id="phase-e-historical-decision-v1",
        decision_time_local=local_decision.strftime("%H:%M"),
        timezone_name="Asia/Shanghai",
        market_scope="A_SHARE",
        allowed_side="LONG_ONLY",
        signal_family=SignalFamily.TREND_CONTINUATION,
        price_action_min_return=0.01,
        volume_confirmation_min_ratio=1.2,
        trend_confirmation_min_return=0.02,
        vwap_min_relative_return=0.0,
        overheat_max_return=0.08,
        minimum_confirmations=3,
        scoring_method="EQUAL_CONFIRMATION_MEAN_V1",
        schema_version=SIGNAL_MODEL_CONFIG_SCHEMA,
    )


def _ref_key(item: ValidationArtifactReference) -> tuple[str, str, str]:
    return item.artifact_kind, str(item.artifact_id), item.content_hash


def _references(
    values: tuple[ValidationArtifactReference, ...],
) -> tuple[ValidationArtifactReference, ...]:
    keyed = {_ref_key(item): item for item in values}
    return tuple(keyed[key] for key in sorted(keyed))


__all__ = [
    "FREE_RESEARCH_UNIVERSE_KIND",
    "GLOBAL_RESEARCH_THEME_ID",
    "NORMALIZED_DATASET_KIND",
    "HistoricalDecisionMaterializer",
]
