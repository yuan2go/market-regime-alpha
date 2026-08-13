"""Historical Decision-Time adapter over canonical research computation kernels."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from math import sqrt
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
    HistoricalNormalizedBar,
    HistoricalTradingStatus,
)
from market_regime_alpha.application.historical_corpus.historical_window import (
    HistoricalWindowReader,
)
from market_regime_alpha.application.historical_corpus.artifacts import (
    HistoricalPackageIndex,
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
from market_regime_alpha.application.historical_corpus.selective_read import HistoricalReadMetrics
from market_regime_alpha.application.controlled_operation.prospective_outcome import (
    OutcomeAvailabilityStatus,
    OutcomeMarketCondition,
)
from market_regime_alpha.application.research_evaluation.postgres_target_repository import (
    PostgresTargetOutcomeRepository,
)
from market_regime_alpha.application.research_evaluation.targeted_outcome import (
    TargetOutcomeLabel,
    build_target_outcome_label_from_bars,
)
from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeCheckpoint,
    OutcomeTargetProtocol,
    TargetDefinition,
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
from market_regime_alpha.application.research_validation.liquidity_capacity import (
    CapacityParameter,
    CapacityValueProvenance,
    LiquidityCapacityAssessment,
    LiquidityCapacityProtocol,
)
from market_regime_alpha.application.strategy_shadow.economics import (
    StrategyEconomicsPolicy,
    StrategyEconomicsResult,
    StrategyEntryKind,
    StrategyExecutionObservation,
    StrategyExecutionPhase,
    StrategyExitKind,
    evaluate_strategy_economics,
)
from market_regime_alpha.application.strategy_shadow.portfolio import (
    ShadowParameterProvenance,
)
from market_regime_alpha.core.identity import (
    ArtifactId,
    FeatureDefinitionId,
    ModelId,
    ProviderId,
    TargetId,
)
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
from market_regime_alpha.forecasting.path import (
    PATH_FORECAST_CONFIG_SCHEMA,
    PATH_FORECAST_SAMPLE_SCHEMA,
    PathForecastConfig,
    PathForecastSample,
    build_retrospective_path_forecast,
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
from market_regime_alpha.universe.postgres_historical_facts import (
    HistoricalSecurityFactProjection,
    PostgresHistoricalSecurityFactsRepository,
)
from market_regime_alpha.universe.historical_facts import (
    HistoricalSecurityFact,
    HistoricalSecurityFactCoverageGap,
)
from market_regime_alpha.universe.postgres_runtime_scope import PostgresRuntimeScopeRepository
from market_regime_alpha.universe.research import (
    FreeResearchUniverseSnapshot,
    ResearchUniverseMembershipStatus,
    ResearchUniverseSelectionBasis,
    project_free_research_universe_as_of,
)
from market_regime_alpha.universe.runtime_scope import (
    RuntimeEligibilityObservation,
    RuntimeScopeMembershipSnapshot,
    RuntimeScopeDecision,
    UniversePolicySelector,
    UniverseScopeKind,
    build_runtime_scope,
)
from market_regime_alpha.strategies.entry.contracts import (
    EntryBarrierSpec,
    EntryPathObservationStatus,
    EntryPathReasonCode,
    build_entry_path_target_contract,
)

NORMALIZED_DATASET_KIND = "NORMALIZED_DATASET"
FREE_RESEARCH_UNIVERSE_KIND = "FREE_RESEARCH_UNIVERSE"
HISTORICAL_SECURITY_FACTS_KIND = "HISTORICAL_SECURITY_FACTS"
HISTORICAL_CONSTITUENT_TIMELINE_KIND = "HISTORICAL_CONSTITUENT_TIMELINE"
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
            "market_observation": (None if self.market_observation is None else self.market_observation.to_canonical_dict()),
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


@dataclass(frozen=True, slots=True)
class _HistoricalFeatureValue:
    output_id: str
    state: FeatureValueState
    value: Decimal | int | str | None
    available_at: datetime
    source_bar_count: int
    source_bar_lineage_hash: str
    missing_reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _HistoricalFeatureComputation:
    feature_id: str
    symbol: str
    timeframe: Timeframe
    available_at: datetime
    configuration_id: ArtifactId
    configuration_hash: str
    values: tuple[_HistoricalFeatureValue, ...]
    limitations: tuple[str, ...]


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
        target_repository: PostgresTargetOutcomeRepository,
        historical_facts_repository: PostgresHistoricalSecurityFactsRepository | None = None,
        maximum_daily_rows: int = 1_000_000,
        maximum_minute_session_rows: int = 250_000,
        minute_session_cache_size: int = 4,
        maximum_prior_forecast_sessions: int = 756,
    ) -> None:
        if maximum_prior_forecast_sessions < 20:
            raise ValueError("Historical Forecast window cannot lower the frozen sample floor")
        self._run_id = run_id
        self._corpus = corpus_repository
        self._components = component_repository
        self._universes = universe_repository
        self._scopes = scope_repository
        self._targets = target_repository
        self._historical_facts = historical_facts_repository
        self._maximum_prior_forecast_sessions = maximum_prior_forecast_sessions
        self._windows = HistoricalWindowReader(
            corpus_repository,
            maximum_daily_rows=maximum_daily_rows,
            maximum_minute_session_rows=maximum_minute_session_rows,
            minute_session_cache_size=minute_session_cache_size,
        )
        self._universe_cache: dict[
            tuple[ValidationArtifactReference, ...],
            tuple[tuple[date, FreeResearchUniverseSnapshot, ValidationArtifactReference], ...],
        ] = {}

    def selective_read_metrics(self) -> tuple[HistoricalReadMetrics, ...]:
        return self._windows.metrics()

    def window_cache_metrics(self) -> Mapping[str, int]:
        return self._windows.cache_metrics()

    def compute_stage(
        self,
        *,
        request: ResearchDecisionSessionRequest,
        stage: ResearchSessionStage,
        input_references: tuple[ValidationArtifactReference, ...],
    ) -> SessionStageComputation:
        self._windows.begin_stage()
        if request.data_authority_mode is not DataAuthorityMode.FREE_RESEARCH_ARCHIVE:
            raise ValueError("Historical materializer only accepts frozen free archives")
        if stage is ResearchSessionStage.SCOPE:
            return self._scope_stage(request)
        if stage is ResearchSessionStage.DECISION:
            return self._decision_stage(request, input_references)
        if stage is ResearchSessionStage.STRATEGY:
            return self._strategy_stage(request, input_references)
        if stage is ResearchSessionStage.PORTFOLIO:
            return self._portfolio_stage(request, input_references)
        if stage is ResearchSessionStage.OUTCOME:
            return self._outcome_stage(request, input_references)
        if stage is ResearchSessionStage.PERFORMANCE:
            return self._performance_stage(request, input_references)
        raise AssertionError(f"unhandled Historical stage {stage.value}")

    def _scope_stage(self, request: ResearchDecisionSessionRequest) -> SessionStageComputation:
        normalized_reference = _required_reference(request, NORMALIZED_DATASET_KIND)
        base_universe, universe_reference = self._active_universe(
            request.configuration_references,
            request.trading_date,
        )
        policy = self._scopes.get_policy(request.runtime_scope_policy_id)
        if policy.policy_hash != request.runtime_scope_policy_hash:
            raise ValueError("Historical Runtime Scope Policy hash mismatch")
        supported_selectors = {UniverseScopeKind.WATCHLIST, UniverseScopeKind.INDEX}
        if any(item.kind not in supported_selectors for item in policy.selectors):
            raise ValueError("Historical materialization supports frozen WATCHLIST or INDEX scope")
        has_index = any(item.kind is UniverseScopeKind.INDEX for item in policy.selectors)
        if has_index:
            if base_universe.selection_basis is not ResearchUniverseSelectionBasis.HISTORICAL_CONSTITUENT_SNAPSHOT:
                raise ValueError("Historical INDEX requires a frozen historical constituent owner")
            stock_symbols = tuple(
                item.symbol for item in base_universe.records if item.membership_status is ResearchUniverseMembershipStatus.INCLUDED
            )
        else:
            stock_symbols = tuple(sorted({symbol for item in policy.selectors for symbol in item.symbols}))
        projected = self._universes.publish(
            project_free_research_universe_as_of(
                base_universe,
                as_of_date=request.trading_date,
                symbols=stock_symbols,
            )
        )
        bars = self._windows.decision_bars(
            normalized_reference,
            request.decision_time,
            symbols=stock_symbols,
        )
        observations = tuple(
            _eligibility_observation(
                symbol=symbol,
                request=request,
                bars=bars,
                universe=projected,
                source_references=(normalized_reference, universe_reference),
            )
            for symbol in stock_symbols
        )
        facts_reference = _optional_reference(
            request.configuration_references,
            HISTORICAL_SECURITY_FACTS_KIND,
        )
        if facts_reference is not None and self._historical_facts is None:
            raise ValueError("Historical Security Facts owner is bound but repository is absent")
        if facts_reference is None:
            fact_projection = None
        else:
            facts_repository = self._historical_facts
            assert facts_repository is not None
            fact_projection = facts_repository.resolve_as_of(
                facts_reference,
                symbols=tuple(sorted(stock_symbols)),
                decision_date=request.trading_date,
            )
        business_facts = _historical_business_fact_rows(
            symbols=tuple(sorted(stock_symbols)),
            bars=bars,
            decision_time=request.decision_time,
            fact_projection=fact_projection,
        )
        scope = build_runtime_scope(
            policy=policy,
            as_of=request.decision_time,
            built_at=request.materialized_at,
            security_master=projected,
            eligibility_observations=observations,
            membership_snapshots=(
                _historical_index_membership_snapshot(
                    selector=next(item for item in policy.selectors if item.kind is UniverseScopeKind.INDEX),
                    universe=projected,
                    decision_time=request.decision_time,
                    source_reference=universe_reference,
                ),
            )
            if has_index
            else (),
            code_revision=request.code_revision,
        )
        scope = self._scopes.publish(policy=policy, receipt=scope)
        membership = {item.symbol: item.decision is RuntimeScopeDecision.INCLUDED for item in scope.records}
        source_max = _source_max_event_time(bars, request.decision_time)
        component = self._put_component(
            request=request,
            kind=HistoricalComponentKind.DYNAMIC_POOL,
            source_max_event_time=source_max,
            source_references=(
                normalized_reference,
                universe_reference,
                ValidationArtifactReference("RESEARCH_UNIVERSE_POLICY", policy.policy_id, policy.policy_hash),
                ValidationArtifactReference("RUNTIME_SCOPE", scope.scope_id, scope.scope_hash),
                *((facts_reference,) if facts_reference is not None else ()),
            ),
            payload={
                "scope": scope.to_canonical_dict(),
                "membership": [{"symbol": symbol, "included": membership[symbol]} for symbol in sorted(membership)],
                "coverage": {
                    "requested": len(membership),
                    "included": sum(membership.values()),
                    "unknown": sum(item.decision is RuntimeScopeDecision.UNKNOWN for item in scope.records),
                },
                "historical_security_fact_coverage": _security_fact_coverage(
                    universe=projected,
                    observations=observations,
                    decision_date=request.trading_date,
                    business_facts=business_facts,
                    facts_owner_bound=facts_reference is not None,
                ),
                "historical_business_facts": list(business_facts),
                "selective_reads": self._windows.stage_lineage_payload(),
                "universe_selection_basis": projected.selection_basis.value,
                "limitations": sorted(
                    {
                        "NO_SILENT_MISSING_DATA_INCLUSION",
                        *(
                            {
                                "FROZEN_HISTORICAL_CONSTITUENT_SNAPSHOT",
                                "CURRENT_CLASSIFICATION_NOT_BACKFILLED",
                            }
                            if projected.selection_basis is ResearchUniverseSelectionBasis.HISTORICAL_CONSTITUENT_SNAPSHOT
                            else {"CURRENT_SECURITY_MASTER_PROJECTED_RETROSPECTIVELY"}
                        ),
                        *(() if facts_reference is not None else {"HISTORICAL_BUSINESS_FACT_OWNER_NOT_BOUND"}),
                    }
                ),
            },
        )
        return SessionStageComputation(
            status=SessionStageStatus.COMPLETE,
            output_references=_references(
                (
                    ValidationArtifactReference("RUNTIME_SCOPE", scope.scope_id, scope.scope_hash),
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
        owner = self._windows.index(normalized_reference).package
        scope_reference = _single_reference(input_references, "RUNTIME_SCOPE")
        pool_reference = _single_reference(input_references, "HISTORICAL_DYNAMIC_POOL")
        scope = self._scopes.get(scope_reference.artifact_id)
        if scope.scope_hash != scope_reference.content_hash:
            raise ValueError("Historical Runtime Scope owner hash mismatch")
        stock_symbols = tuple(item.symbol for item in scope.records)
        pool_membership = {item.symbol: item.decision is RuntimeScopeDecision.INCLUDED for item in scope.records}
        context_symbols = tuple(sorted(set(owner.coverage.expected_symbols) - set(stock_symbols)))
        bars = self._windows.decision_bars(
            normalized_reference,
            request.decision_time,
            symbols=tuple(sorted((*stock_symbols, *context_symbols))),
        )
        computations = _compute_features(
            owner=owner,
            bars=bars,
            stock_symbols=stock_symbols,
            decision_time=request.decision_time,
        )
        source_max = _source_max_event_time(bars, request.decision_time)
        feature_component = self._build_component(
            request=request,
            kind=HistoricalComponentKind.FEATURE,
            source_max_event_time=source_max,
            source_references=(normalized_reference, pool_reference),
            payload={
                "features": [_feature_dict(item) for item in computations],
                "symbol_count": len(stock_symbols),
                "available_value_count": sum(value.state is FeatureValueState.AVAILABLE for item in computations for value in item.values),
                "missing_value_count": sum(value.state is FeatureValueState.MISSING for item in computations for value in item.values),
                "selective_reads": self._windows.stage_lineage_payload(),
            },
        )
        context = _build_context(
            owner=owner,
            bars=bars,
            stock_symbols=stock_symbols,
            context_symbols=context_symbols,
            decision_time=request.decision_time,
            created_at=request.materialized_at,
            source_reference=normalized_reference,
            computations=computations,
        )
        configuration = ControlledResearchPipelineConfig.create()
        market = evaluate_market_regime_v0(context, configuration.market_regime, code_revision=request.code_revision)
        market_component = self._build_component(
            request=request,
            kind=HistoricalComponentKind.MARKET_REGIME,
            source_max_event_time=source_max,
            source_references=(feature_component.reference, normalized_reference),
            payload=market.to_canonical_dict(),
        )
        etf_component = self._build_component(
            request=request,
            kind=HistoricalComponentKind.ETF,
            source_max_event_time=source_max,
            source_references=(normalized_reference,),
            payload={
                "context_symbols": list(context_symbols),
                "benchmark_usage": {
                    "market_regime": next(
                        (item for item in context_symbols if not _is_etf_symbol(item)),
                        next(
                            (item for item in context_symbols if _is_etf_symbol(item)),
                            None,
                        ),
                    ),
                    "theme": next(
                        (item for item in context_symbols if _is_etf_symbol(item)),
                        next(
                            (item for item in context_symbols if not _is_etf_symbol(item)),
                            None,
                        ),
                    ),
                },
                "observations": [item.to_canonical_dict() for item in context.etf_observations],
                "instrument_coverage": _context_instrument_coverage(
                    bars=bars,
                    context_symbols=context_symbols,
                    decision_time=request.decision_time,
                ),
                "status": "AVAILABLE" if context.etf_observations else "NOT_ESTIMABLE",
                "reason_codes": (
                    ["FROZEN_CONTEXT_INSTRUMENTS_RESOLVED"] if context.etf_observations else ["ETF_CONTEXT_NOT_IN_FROZEN_DATASET"]
                ),
            },
        )
        themes = evaluate_theme_rotation_v0(context, configuration.theme_rotation, code_revision=request.code_revision)
        theme_component = self._build_component(
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
        capital_component = self._build_component(
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
        candidate_component = self._build_component(
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
                price_action_return=_feature_float(computations, item.symbol, PRICE_ACTION_FEATURE_ID, "return_3"),
                volume_ratio=_feature_float(computations, item.symbol, CAPITAL_VOLUME_FEATURE_ID, "amount_ratio_5"),
                trend_return=_feature_float(
                    computations,
                    item.symbol,
                    MOVING_AVERAGE_FEATURE_ID,
                    "price_vs_sma20_return",
                ),
                price_vs_vwap_return=_feature_float(computations, item.symbol, VWAP_FEATURE_ID, "price_vs_vwap_return"),
                overheat_return=_feature_float(computations, item.symbol, OVERHEAT_FEATURE_ID, "short_return"),
                reason_codes=("RETROSPECTIVE_EVENT_TIME",),
                source_artifact_pairs=((feature_component.component_id, feature_component.component_hash),),
                decision_time=DecisionTime(request.decision_time),
                created_at=request.materialized_at,
                code_revision=request.code_revision,
            )
            for item in candidates.selected
        )
        signal_component = self._build_component(
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
        forecast_config = _forecast_configuration(request.decision_time)
        target_protocol = self._load_target_protocol(request)
        forecast_target = next(item for item in target_protocol.targets if item.checkpoint is OutcomeCheckpoint.TIME_1030)
        forecasts = []
        used_prior_references: set[ValidationArtifactReference] = set()
        for snapshot in snapshots:
            samples, event_ends, source_references = _prior_forecast_samples(
                prior_labels=self._components.list_outcome_labels_before(
                    run_id=self._run_id,
                    before=request.trading_date,
                    symbol=snapshot.symbol,
                    target_id=forecast_target.target_id,
                    maximum_labels=self._maximum_prior_forecast_sessions,
                ),
                symbol=snapshot.symbol,
                configuration=forecast_config,
            )
            forecasts.append(
                build_retrospective_path_forecast(
                    signal_snapshot=snapshot,
                    configuration=forecast_config,
                    samples=samples,
                    sample_event_ends=event_ends,
                    decision_time=DecisionTime(request.decision_time),
                    created_at=request.materialized_at,
                    code_revision=request.code_revision,
                )
            )
            used_prior_references.update(source_references)
        forecast_component = self._build_component(
            request=request,
            kind=HistoricalComponentKind.FORECAST,
            source_max_event_time=source_max,
            source_references=(
                signal_component.reference,
                *tuple(sorted(used_prior_references, key=_ref_key)),
            ),
            payload={
                "configuration": forecast_config.to_canonical_dict(),
                "forecasts": [item.to_canonical_dict() for item in forecasts],
                "forecast_count": len(forecasts),
                "available_for_research_count": sum(item.forecast.forecast_status.value == "AVAILABLE_FOR_RESEARCH" for item in forecasts),
                "calibrated": False,
                "formal_oos": False,
                "formal_model_qualified": False,
            },
            limitations=("CALIBRATED_FALSE", "FORMAL_MODEL_QUALIFIED_FALSE"),
        )
        outputs = (
            feature_component.reference,
            market_component.reference,
            etf_component.reference,
            theme_component.reference,
            capital_component.reference,
            candidate_component.reference,
            signal_component.reference,
            forecast_component.reference,
        )
        decision_components = (
            feature_component,
            market_component,
            etf_component,
            theme_component,
            capital_component,
            candidate_component,
            signal_component,
            forecast_component,
        )
        self._components.put_many(tuple((item, _COMPONENT_ORDINAL[item.component_kind]) for item in decision_components))
        return SessionStageComputation(
            status=SessionStageStatus.COMPLETE,
            output_references=_references(outputs),
            input_references=_references((*input_references, normalized_reference)),
            completed_at=request.materialized_at,
            reason_codes=("HISTORICAL_DECISION_STATE_MATERIALIZED",),
        )

    def _active_universe(
        self,
        references: tuple[ValidationArtifactReference, ...],
        trading_date: date,
    ) -> tuple[FreeResearchUniverseSnapshot, ValidationArtifactReference]:
        universe_references = tuple(item for item in references if item.artifact_kind == FREE_RESEARCH_UNIVERSE_KIND)
        if not universe_references:
            raise ValueError("Historical session requires constituent owners")
        timeline_references = tuple(item for item in references if item.artifact_kind == HISTORICAL_CONSTITUENT_TIMELINE_KIND)
        if len(timeline_references) != 1:
            raise ValueError("Every Historical session requires one exact cohort timeline")
        timeline_owner = self._universes.get_timeline(timeline_references[0].artifact_id)
        if (
            timeline_owner.timeline_hash != timeline_references[0].content_hash
            or tuple(
                sorted(
                    (cohort.snapshot_reference for cohort in timeline_owner.cohorts),
                    key=lambda item: (
                        item.artifact_kind,
                        str(item.artifact_id),
                        item.content_hash,
                    ),
                )
            )
            != universe_references
            or not timeline_owner.start_date <= trading_date <= timeline_owner.end_date
        ):
            raise ValueError("Historical constituent timeline range/cohort lineage mismatch")
        query_mapping = dict(timeline_owner.query_effective_dates)
        expected_effective_date = query_mapping.get(trading_date)
        if expected_effective_date is None:
            raise ValueError("Decision session is absent from Historical constituent scan")
        timeline = self._universe_cache.get(universe_references)
        if timeline is None:
            resolved: list[tuple[date, FreeResearchUniverseSnapshot, ValidationArtifactReference]] = []
            seen_dates: set[date] = set()
            for reference in universe_references:
                snapshot = self._universes.get(reference.artifact_id)
                if snapshot.snapshot_hash != reference.content_hash:
                    raise ValueError("Historical Security Master owner hash mismatch")
                if (
                    snapshot.selection_basis is not ResearchUniverseSelectionBasis.HISTORICAL_CONSTITUENT_SNAPSHOT
                    or snapshot.constituent_effective_date is None
                ):
                    raise ValueError("Historical INDEX requires effective-dated constituent owners")
                if snapshot.constituent_effective_date in seen_dates:
                    raise ValueError("Historical constituent timeline has duplicate effective dates")
                seen_dates.add(snapshot.constituent_effective_date)
                resolved.append((snapshot.constituent_effective_date, snapshot, reference))
            timeline = tuple(sorted(resolved, key=lambda item: item[0]))
            self._universe_cache[universe_references] = timeline
        active = tuple(item for item in timeline if item[0] <= trading_date)
        if not active:
            raise ValueError("Historical constituent timeline starts after Decision session")
        effective_date, snapshot, reference = active[-1]
        if effective_date != expected_effective_date:
            raise ValueError("Historical constituent timeline selected cohort does not match scan")
        return snapshot, reference

    def _strategy_stage(
        self,
        request: ResearchDecisionSessionRequest,
        input_references: tuple[ValidationArtifactReference, ...],
    ) -> SessionStageComputation:
        protocol = self._load_target_protocol(request)
        signal = self._components.get(_single_reference(input_references, "HISTORICAL_SIGNAL"))
        forecast = self._components.get(_single_reference(input_references, "HISTORICAL_FORECAST"))
        policies = tuple(_strategy_policy(target, request.materialized_at) for target in protocol.targets)
        source_max = max(signal.source_max_event_time, forecast.source_max_event_time)
        component = self._put_component(
            request=request,
            kind=HistoricalComponentKind.STRATEGY,
            source_max_event_time=source_max,
            source_references=(signal.reference, forecast.reference),
            payload={
                "entry": "FROZEN_DECISION_REFERENCE",
                "holding": "T_PLUS_ONE",
                "policies": [
                    item.identity_payload()
                    | {
                        "policy_id": str(item.policy_id),
                        "policy_hash": item.policy_hash,
                    }
                    for item in policies
                ],
                "candidate_symbols": [str(item["symbol"]) for item in _objects(signal.payload.get("snapshots"), "snapshots")],
                "cost_assumptions": {
                    "commission_bps_each_side": "3",
                    "stamp_duty_bps_sell": "5",
                    "spread_slippage_bps_each_side": "5",
                    "impact_coefficient_bps": "8",
                    "participation_rate": "0.1",
                },
            },
            limitations=("COST_AND_FILLABILITY_ENGINEERING_ASSUMPTIONS",),
        )
        return _complete_stage(
            request=request,
            inputs=input_references,
            output=component.reference,
            reason="HISTORICAL_STRATEGY_POLICY_FROZEN",
        )

    def _portfolio_stage(
        self,
        request: ResearchDecisionSessionRequest,
        input_references: tuple[ValidationArtifactReference, ...],
    ) -> SessionStageComputation:
        candidate = self._components.get(_single_reference(input_references, "HISTORICAL_CANDIDATE"))
        strategy = self._components.get(_single_reference(input_references, "HISTORICAL_STRATEGY"))
        records = _objects(candidate.payload.get("records"), "candidate records")
        selected = tuple(item for item in records if item.get("selection_status") == "SELECTED")
        positions = tuple(
            {
                "symbol": str(item["symbol"]),
                "rank": int(item["rank"]),
                "target_weight": (None if not selected else str(Decimal("1") / Decimal(len(selected)))),
                "requested_notional": "100000",
            }
            for item in sorted(selected, key=lambda value: int(value["rank"]))
        )
        component = self._put_component(
            request=request,
            kind=HistoricalComponentKind.PORTFOLIO,
            source_max_event_time=max(candidate.source_max_event_time, strategy.source_max_event_time),
            source_references=(candidate.reference, strategy.reference),
            payload={
                "construction": "EQUAL_WEIGHT_SELECTED_CANDIDATES_V1",
                "positions": list(positions),
                "selected_count": len(positions),
                "lot_size": 100,
                "requested_notional_per_symbol": "100000",
                "actual_position_authority": False,
            },
            limitations=("RESEARCH_PORTFOLIO_NOT_ACTUAL_POSITION",),
        )
        return _complete_stage(
            request=request,
            inputs=input_references,
            output=component.reference,
            reason="HISTORICAL_RESEARCH_PORTFOLIO_FROZEN",
        )

    def _outcome_stage(
        self,
        request: ResearchDecisionSessionRequest,
        input_references: tuple[ValidationArtifactReference, ...],
    ) -> SessionStageComputation:
        normalized_reference = _required_reference(request, NORMALIZED_DATASET_KIND)
        owner = self._windows.index(normalized_reference).package
        protocol = self._load_target_protocol(request)
        signal = self._components.get(_single_reference(input_references, "HISTORICAL_SIGNAL"))
        candidate = self._components.get(_single_reference(input_references, "HISTORICAL_CANDIDATE"))
        portfolio = self._components.get(_single_reference(input_references, "HISTORICAL_PORTFOLIO"))
        next_session = self._windows.next_session(normalized_reference, request.trading_date)
        if next_session is None:
            return SessionStageComputation(
                status=SessionStageStatus.NOT_ESTIMABLE,
                output_references=(),
                input_references=_references((*input_references, normalized_reference)),
                completed_at=request.materialized_at,
                reason_codes=("T_PLUS_ONE_SESSION_NOT_IN_FROZEN_DATASET",),
            )
        symbols = tuple(str(item["symbol"]) for item in _objects(candidate.payload.get("records"), "candidate records"))
        bars = self._windows.outcome_bars(
            normalized_reference,
            decision_time=request.decision_time,
            next_session=next_session,
            symbols=tuple(sorted(set(symbols))),
        )
        canonical = tuple(_canonical_outcome_bars(bars, next_session))
        facts_reference = _optional_reference(
            request.configuration_references,
            HISTORICAL_SECURITY_FACTS_KIND,
        )
        if facts_reference is not None and self._historical_facts is None:
            raise ValueError("Historical Security Facts owner is bound but repository is absent")
        if facts_reference is None:
            actions_by_symbol: Mapping[str, tuple[HistoricalSecurityFact, ...]] = {}
            action_gaps_by_symbol: Mapping[
                str,
                tuple[HistoricalSecurityFactCoverageGap, ...],
            ] = {}
        else:
            facts_repository = self._historical_facts
            assert facts_repository is not None
            actions_by_symbol = facts_repository.corporate_actions_for_symbols(
                facts_reference,
                symbols=tuple(sorted(set(symbols))),
                after=request.trading_date,
                through=next_session,
            )
            action_gaps_by_symbol = facts_repository.corporate_action_gaps_for_symbols(
                facts_reference,
                symbols=tuple(sorted(set(symbols))),
                after=request.trading_date,
                through=next_session,
            )
        corporate_action_excluded_symbols = set(actions_by_symbol) | set(
            action_gaps_by_symbol
        )
        labels: list[TargetOutcomeLabel] = []
        economics: list[StrategyEconomicsResult] = []
        capacity_protocol = _capacity_protocol(request.materialized_at)
        requested_notional = Decimal("100000")
        for symbol in symbols:
            if symbol in corporate_action_excluded_symbols:
                continue
            reference_price = _decision_reference_price(bars, symbol, request.trading_date, request.decision_time)
            if reference_price is None:
                continue
            initial_conditions = _market_conditions(bars, symbol, next_session)
            fallback_open = next(
                (
                    item.open
                    for item in bars
                    if item.symbol == symbol and item.market_date == next_session and item.timeframe is Timeframe.DAILY
                ),
                None,
            )
            symbol_labels = tuple(
                build_target_outcome_label_from_bars(
                    symbol=symbol,
                    decision_frozen_at=request.decision_time,
                    decision_reference_price=reference_price,
                    target=target,
                    protocol=protocol,
                    bars=canonical,
                    fallback_available_at=owner.retrieved_at,
                    next_session_date=next_session,
                    initial_market_conditions=initial_conditions,
                    fallback_open=fallback_open,
                )
                for target in protocol.targets
            )
            labels.extend(symbol_labels)
            historical_daily = _canonical_bars(
                tuple(
                    item
                    for item in bars
                    if item.symbol == symbol
                    and item.timeframe is Timeframe.DAILY
                    and item.event_end <= request.decision_time
                    and item.open is not None
                ),
                asset_type=AssetType.A_SHARE,
                assume_normal_price_limit=True,
            )
            liquidity = LiquidityCapacityAssessment.create(
                symbol=symbol,
                as_of_date=request.trading_date,
                market_data_reference=normalized_reference,
                bars=historical_daily,
                requested_position=requested_notional,
                requested_order=requested_notional,
                protocol=capacity_protocol,
                created_at=request.materialized_at,
            )
            for label in symbol_labels:
                target = next(item for item in protocol.targets if item.target_id == label.target.artifact_id)
                policy = _strategy_policy(target, request.materialized_at)
                entry = _execution_observation(
                    phase=StrategyExecutionPhase.ENTRY,
                    symbol=symbol,
                    price=reference_price,
                    market_conditions=(OutcomeMarketCondition.TRADING,),
                    effective_at=request.decision_time,
                    available_at=request.materialized_at,
                    source_reference=candidate.reference,
                )
                exit_conditions = label.market_conditions
                exit_at = label.label_interval_end
                exit_execution = _execution_observation(
                    phase=StrategyExecutionPhase.EXIT,
                    symbol=symbol,
                    price=label.checkpoint_price,
                    market_conditions=exit_conditions,
                    effective_at=exit_at,
                    available_at=max(owner.retrieved_at, exit_at),
                    source_reference=normalized_reference,
                )
                economics.append(
                    evaluate_strategy_economics(
                        policy=policy,
                        label=label,
                        liquidity=liquidity,
                        entry_execution=entry,
                        exit_execution=exit_execution,
                        requested_notional=requested_notional,
                        evaluated_at=max(
                            request.materialized_at,
                            owner.retrieved_at,
                            label.outcome_available_at,
                        ),
                    )
                )
        outcome_max = max(
            (item.event_end for item in bars if item.market_date == next_session),
            default=request.decision_time,
        )
        component = self._put_component(
            request=request,
            kind=HistoricalComponentKind.OUTCOME,
            source_max_event_time=outcome_max,
            source_references=(
                normalized_reference,
                candidate.reference,
                signal.reference,
                portfolio.reference,
                request.target_protocol_reference,
                *((facts_reference,) if facts_reference is not None else ()),
            ),
            payload={
                "next_session_date": next_session.isoformat(),
                "target_protocol": protocol.to_canonical_dict(),
                "labels": [item.to_canonical_dict() for item in labels],
                "strategy_economics": [
                    item.identity_payload()
                    | {
                        "result_id": str(item.result_id),
                        "result_hash": item.result_hash,
                    }
                    for item in economics
                ],
                "available_label_count": sum(item.availability_status is OutcomeAvailabilityStatus.COMPLETE for item in labels),
                "not_estimated_label_count": sum(item.availability_status is not OutcomeAvailabilityStatus.COMPLETE for item in labels),
                "corporate_action_exclusions": [
                    {
                        "symbol": symbol,
                        "action_references": [
                            {
                                "artifact_kind": "HISTORICAL_SECURITY_FACT",
                                "artifact_id": str(item.fact_id),
                                "content_hash": item.fact_hash,
                            }
                            for item in actions_by_symbol.get(symbol, ())
                        ],
                        "coverage_gap_references": [
                            {
                                "artifact_kind": "HISTORICAL_SECURITY_FACT_COVERAGE_GAP",
                                "artifact_id": str(item.gap_id),
                                "content_hash": item.gap_hash,
                            }
                            for item in action_gaps_by_symbol.get(symbol, ())
                        ],
                        "excluded_target_count": len(protocol.targets),
                        "reason_code": (
                            "CORPORATE_ACTION_COVERAGE_GAP_RAW_RETURN_NOT_ESTIMABLE"
                            if symbol in action_gaps_by_symbol
                            else "RAW_UNADJUSTED_RETURN_CROSSES_CORPORATE_ACTION"
                        ),
                    }
                    for symbol in sorted(corporate_action_excluded_symbols)
                ],
                "corporate_action_coverage": {
                    "facts_owner_bound": facts_reference is not None,
                    "affected_symbol_count": len(corporate_action_excluded_symbols),
                    "action_fact_count": sum(len(items) for items in actions_by_symbol.values()),
                    "coverage_gap_count": sum(
                        len(items) for items in action_gaps_by_symbol.values()
                    ),
                    "incomplete_symbol_count": len(action_gaps_by_symbol),
                    "excluded_target_count": len(corporate_action_excluded_symbols)
                    * len(protocol.targets),
                    "price_adjustment_basis": "RAW_UNADJUSTED_TRADABLE_PRICE_V1",
                },
                "engineering_assumptions": [
                    "COMMISSION_3_BPS_EACH_SIDE",
                    "STAMP_DUTY_5_BPS_SELL",
                    "SPREAD_SLIPPAGE_5_BPS_EACH_SIDE",
                    "IMPACT_COEFFICIENT_8_BPS",
                    "PARTICIPATION_RATE_10_PERCENT",
                    *([] if facts_reference is not None else ["CORPORATE_ACTION_COVERAGE_INCOMPLETE_RAW_ONLY"]),
                ],
                "selective_reads": self._windows.stage_lineage_payload(),
            },
            limitations=tuple(
                sorted(
                    {
                        "COST_AND_FILLABILITY_ENGINEERING_ASSUMPTIONS",
                        *(() if facts_reference is not None else {"CORPORATE_ACTION_COVERAGE_INCOMPLETE"}),
                    }
                )
            ),
        )
        self._remember_outcome(component)
        return _complete_stage(
            request=request,
            inputs=_references((*input_references, normalized_reference)),
            output=component.reference,
            reason="HISTORICAL_T_PLUS_ONE_OUTCOME_MATERIALIZED",
        )

    def _performance_stage(
        self,
        request: ResearchDecisionSessionRequest,
        input_references: tuple[ValidationArtifactReference, ...],
    ) -> SessionStageComputation:
        candidate = self._components.get(_single_reference(input_references, "HISTORICAL_CANDIDATE"))
        feature = self._components.get(_single_reference(input_references, "HISTORICAL_FEATURE"))
        market = self._components.get(_single_reference(input_references, "HISTORICAL_MARKET_REGIME"))
        etf = self._components.get(_single_reference(input_references, "HISTORICAL_ETF"))
        theme = self._components.get(_single_reference(input_references, "HISTORICAL_THEME"))
        capital = self._components.get(_single_reference(input_references, "HISTORICAL_CAPITAL"))
        signal = self._components.get(_single_reference(input_references, "HISTORICAL_SIGNAL"))
        forecast = self._components.get(_single_reference(input_references, "HISTORICAL_FORECAST"))
        outcome = self._components.get(_single_reference(input_references, "HISTORICAL_OUTCOME"))
        pool = self._components.get(_single_reference(input_references, "HISTORICAL_DYNAMIC_POOL"))
        rows = _research_panel_rows(
            trading_date=request.trading_date,
            feature=feature,
            market=market,
            etf=etf,
            theme=theme,
            capital=capital,
            pool=pool,
            candidate=candidate,
            signal=signal,
            forecast=forecast,
            outcome=outcome,
        )
        component = self._put_component(
            request=request,
            kind=HistoricalComponentKind.RESEARCH_PANEL,
            source_max_event_time=outcome.source_max_event_time,
            source_references=(
                feature.reference,
                market.reference,
                etf.reference,
                theme.reference,
                capital.reference,
                pool.reference,
                candidate.reference,
                signal.reference,
                forecast.reference,
                outcome.reference,
            ),
            payload={
                "rows": list(rows),
                "row_count": len(rows),
                "missing_target_count": sum(item["target_return"] is None for item in rows),
                "gross_return": _mean_decimal_text(item["gross_return"] for item in rows),
                "cost_return": _mean_decimal_text(item["cost_return"] for item in rows),
                "net_return": _mean_decimal_text(item["net_return"] for item in rows),
            },
        )
        return _complete_stage(
            request=request,
            inputs=input_references,
            output=component.reference,
            reason="HISTORICAL_RESEARCH_PANEL_MATERIALIZED",
        )

    def _load_target_protocol(self, request: ResearchDecisionSessionRequest) -> OutcomeTargetProtocol:
        protocol = self._targets.get_protocol(request.target_protocol_reference.artifact_id)
        if protocol.protocol_hash != request.target_protocol_reference.content_hash:
            raise ValueError("Historical Target Protocol owner hash mismatch")
        return protocol

    def _remember_outcome(self, component: HistoricalSessionComponent) -> None:
        if component.component_kind is not HistoricalComponentKind.OUTCOME:
            raise ValueError("Historical Outcome cache only accepts Outcome owners")

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
        component = self._build_component(
            request=request,
            kind=kind,
            source_max_event_time=source_max_event_time,
            source_references=source_references,
            payload=payload,
            limitations=limitations,
        )
        return self._components.put(component=component, ordinal=_COMPONENT_ORDINAL[kind])

    def _build_component(
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
        return component


def _required_reference(
    request: ResearchDecisionSessionRequest,
    artifact_kind: str,
) -> ValidationArtifactReference:
    matches = tuple(item for item in request.configuration_references if item.artifact_kind == artifact_kind)
    if len(matches) != 1:
        raise ValueError(f"Historical session requires one {artifact_kind} owner")
    return matches[0]


def _optional_reference(
    references: tuple[ValidationArtifactReference, ...],
    artifact_kind: str,
) -> ValidationArtifactReference | None:
    matches = tuple(item for item in references if item.artifact_kind == artifact_kind)
    if len(matches) > 1:
        raise ValueError(f"Historical session accepts at most one {artifact_kind} owner")
    return None if not matches else matches[0]


def _single_reference(references: tuple[ValidationArtifactReference, ...], artifact_kind: str) -> ValidationArtifactReference:
    matches = tuple(item for item in references if item.artifact_kind == artifact_kind)
    if len(matches) != 1:
        raise ValueError(f"Historical stage requires one {artifact_kind} reference")
    return matches[0]


def _historical_index_membership_snapshot(
    *,
    selector: UniversePolicySelector,
    universe: Any,
    decision_time: datetime,
    source_reference: ValidationArtifactReference,
) -> RuntimeScopeMembershipSnapshot:
    effective_date = universe.constituent_effective_date
    if effective_date is None:
        raise ValueError("Historical INDEX membership lacks an effective date")
    return RuntimeScopeMembershipSnapshot(
        selector=selector,
        effective_at=datetime.combine(effective_date, datetime.min.time(), tzinfo=UTC),
        known_at=universe.known_at,
        decisions=tuple(
            (
                item.symbol,
                RuntimeScopeDecision(item.membership_status.value),
            )
            for item in universe.records
        ),
        source_reference=(universe.constituent_source_reference or source_reference),
    )


def _historical_bar_key(
    item: HistoricalNormalizedBar,
) -> tuple[str, str, datetime, str]:
    return (item.symbol, item.timeframe.value, item.event_end, str(item.bar_id))


def _source_max_event_time(bars: tuple[HistoricalNormalizedBar, ...], decision_time: datetime) -> datetime:
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
    source_references: tuple[ValidationArtifactReference, ...],
) -> RuntimeEligibilityObservation:
    daily = tuple(
        item for item in bars if item.symbol == symbol and item.timeframe is Timeframe.DAILY and item.event_end <= request.decision_time
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
    included = None if master is None or master.membership_status.value == "UNKNOWN" else master.membership_status.value == "INCLUDED"
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
        source_references=source_references,
    )


def _security_fact_coverage(
    *,
    universe: Any,
    observations: tuple[RuntimeEligibilityObservation, ...],
    decision_date: date,
    business_facts: tuple[Mapping[str, Any], ...],
    facts_owner_bound: bool,
) -> dict[str, Any]:
    """Persist exact fact coverage without inventing unavailable classifications."""

    records = tuple(universe.records)
    listing_dates = tuple(item for item in records if item.listing_date is not None)
    return {
        "symbol_count": len(records),
        "listing_date_available_count": len(listing_dates),
        "delisting_date_available_count": sum(item.delisting_date is not None for item in records),
        "listing_age_available_count": sum(item.listing_date is not None and item.listing_date <= decision_date for item in records),
        "listing_status_known_count": sum(item.listing_status.value != "UNKNOWN" for item in records),
        "st_status_known_count": sum(item.is_st is not None for item in observations),
        "suspension_status_known_count": sum(item.suspended is not None for item in observations),
        "market_cap_available_count": sum(item.get("market_cap") is not None for item in business_facts),
        "market_cap_status": (
            "PARTIAL_OR_AVAILABLE" if any(item.get("market_cap") is not None for item in business_facts) else "NOT_ESTIMABLE"
        ),
        "industry_available_count": sum(item.get("industry") is not None for item in business_facts),
        "industry_status": ("PARTIAL_OR_AVAILABLE" if any(item.get("industry") is not None for item in business_facts) else "UNKNOWN"),
        "facts_owner_bound": facts_owner_bound,
        "reason_codes": sorted(
            {
                "CURRENT_CLASSIFICATION_NOT_BACKFILLED",
                "HISTORICAL_SUSPENSION_UNKNOWN_WITHOUT_POSITIVE_OBSERVATION",
                "LISTING_AGE_DERIVED_ONLY_FROM_OWNER_RESOLVED_LISTING_DATE",
                *(() if facts_owner_bound else {"HISTORICAL_BUSINESS_FACT_OWNER_NOT_BOUND"}),
            }
        ),
    }


def _historical_business_fact_rows(
    *,
    symbols: tuple[str, ...],
    bars: tuple[HistoricalNormalizedBar, ...],
    decision_time: datetime,
    fact_projection: HistoricalSecurityFactProjection | None,
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        industry = None if fact_projection is None else fact_projection.industries.get(symbol)
        shares = None if fact_projection is None else fact_projection.share_capital.get(symbol)
        share_values = {} if shares is None else dict(shares.values)
        raw_total_shares = share_values.get("total_shares")
        total_shares = None if raw_total_shares in {None, ""} else Decimal(str(raw_total_shares))
        price = _decision_reference_price(
            bars,
            symbol,
            decision_time.astimezone(ZoneInfo("Asia/Shanghai")).date(),
            decision_time,
        )
        market_cap = None if total_shares is None or price is None else total_shares * price
        rows.append(
            {
                "symbol": symbol,
                "industry": (None if industry is None else dict(industry.values)["industry"]),
                "industry_fact_reference": (
                    None
                    if industry is None
                    else {
                        "artifact_kind": "HISTORICAL_SECURITY_FACT",
                        "artifact_id": str(industry.fact_id),
                        "content_hash": industry.fact_hash,
                    }
                ),
                "share_fact_reference": (
                    None
                    if shares is None
                    else {
                        "artifact_kind": "HISTORICAL_SECURITY_FACT",
                        "artifact_id": str(shares.fact_id),
                        "content_hash": shares.fact_hash,
                    }
                ),
                "share_effective_date": (None if shares is None else shares.effective_date.isoformat()),
                "share_published_date": (None if shares is None or shares.published_date is None else shares.published_date.isoformat()),
                "total_shares": (None if total_shares is None else str(total_shares)),
                "liquid_shares": share_values.get("liquid_shares") or None,
                "decision_reference_price": (None if price is None else str(price)),
                "market_cap": None if market_cap is None else str(market_cap),
                "market_cap_method": (None if market_cap is None else "PUBLISHED_TOTAL_SHARES_X_RAW_DECISION_PRICE_V1"),
            }
        )
    return tuple(rows)


def _compute_features(
    *,
    owner: HistoricalPackageIndex,
    bars: tuple[HistoricalNormalizedBar, ...],
    stock_symbols: tuple[str, ...],
    decision_time: datetime,
) -> tuple[_HistoricalFeatureComputation, ...]:
    feature_set = canonical_technical_feature_set(effective_from=datetime(1990, 1, 1, tzinfo=UTC))
    bars_by_symbol = _bars_by_symbol(bars)
    definition_by_id = {item.feature_id: item for item in feature_set.definitions}
    results: list[_HistoricalFeatureComputation] = []
    for symbol in stock_symbols:
        symbol_bars = bars_by_symbol.get(symbol, ())
        daily_rows = tuple(
            item for item in symbol_bars if item.timeframe is Timeframe.DAILY and item.event_end <= decision_time and item.open is not None
        )
        minute_rows = tuple(
            item
            for item in symbol_bars
            if item.timeframe is Timeframe.MINUTE_5
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
                    timeframe=(Timeframe.DAILY if selected == Timeframe.DAILY.value else Timeframe.MINUTE_5),
                    available_at=owner.retrieved_at,
                    configuration=configuration,
                    output_ids=tuple(item.output_id for item in definition.output_schema),
                    reason_code="HISTORICAL_SOURCE_BARS_MISSING_AT_DECISION_TIME",
                )
            results.append(_compact_feature_computation(computation))
    return tuple(sorted(results, key=lambda item: (item.symbol, item.feature_id)))


def _compact_feature_computation(
    item: TechnicalFeatureComputation,
) -> _HistoricalFeatureComputation:
    values = tuple(
        _HistoricalFeatureValue(
            output_id=value.output_id,
            state=value.state,
            value=value.value,
            available_at=value.available_at,
            source_bar_count=len(value.source_bar_ids),
            source_bar_lineage_hash=canonical_hash(
                {
                    "source_bars": [
                        {"bar_id": str(bar_id), "bar_hash": bar_hash}
                        for bar_id, bar_hash in zip(
                            value.source_bar_ids,
                            value.source_bar_hashes,
                            strict=True,
                        )
                    ]
                }
            ),
            missing_reason_codes=value.missing_reason_codes,
        )
        for value in item.values
    )
    return _HistoricalFeatureComputation(
        feature_id=item.feature_id,
        symbol=item.symbol,
        timeframe=item.timeframe,
        available_at=item.available_at,
        configuration_id=item.configuration_id,
        configuration_hash=item.configuration_hash,
        values=values,
        limitations=item.limitations,
    )


def _canonical_bars(
    rows: tuple[HistoricalNormalizedBar, ...],
    *,
    asset_type: AssetType,
    initial_previous_close: Decimal | None = None,
    assume_normal_price_limit: bool = False,
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
                else TradingStatus.SUSPENDED
                if item.trading_status is HistoricalTradingStatus.SUSPENDED
                else TradingStatus.UNKNOWN
            ),
            price_limit_state=(
                PriceLimitState.NORMAL
                if assume_normal_price_limit and item.trading_status is HistoricalTradingStatus.TRADING
                else PriceLimitState.UNKNOWN
            ),
            source_artifact_id=item.bar_id,
            source_content_hash=item.content_hash,
        )
        result.append(bar)
        previous = item.close
    return tuple(result)


def _feature_dict(item: _HistoricalFeatureComputation) -> dict[str, Any]:
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
                "value": (str(value.value) if isinstance(value.value, Decimal) else value.value),
                "available_at": value.available_at.isoformat(),
                "source_bar_count": value.source_bar_count,
                "source_bar_lineage_hash": value.source_bar_lineage_hash,
                "missing_reason_codes": list(value.missing_reason_codes),
            }
            for value in item.values
        ],
        "limitations": list(item.limitations),
    }


def _candidate_features(
    computations: tuple[_HistoricalFeatureComputation, ...],
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
    computations: tuple[_HistoricalFeatureComputation, ...],
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
    owner: HistoricalPackageIndex,
    bars: tuple[HistoricalNormalizedBar, ...],
    stock_symbols: tuple[str, ...],
    context_symbols: tuple[str, ...],
    decision_time: datetime,
    created_at: datetime,
    source_reference: ValidationArtifactReference,
    computations: tuple[_HistoricalFeatureComputation, ...],
) -> _HistoricalResearchContext:
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
    bars_by_symbol = _bars_by_symbol(bars)
    stock_series = {symbol: _daily_series(bars_by_symbol.get(symbol, ()), decision_time) for symbol in stock_symbols}
    context_series = {symbol: _daily_series(bars_by_symbol.get(symbol, ()), decision_time) for symbol in context_symbols}
    etf_symbol = next((item for item in context_symbols if _is_etf_symbol(item)), None)
    index_symbol = next((item for item in context_symbols if not _is_etf_symbol(item)), None)
    market_benchmark = context_series.get(index_symbol, ()) if index_symbol is not None else ()
    theme_benchmark = context_series.get(etf_symbol, ()) if etf_symbol is not None else ()
    if not market_benchmark:
        market_benchmark = theme_benchmark
    if not theme_benchmark:
        theme_benchmark = market_benchmark
    market = _market_observation(
        bars_by_symbol=bars_by_symbol,
        stock_symbols=stock_symbols,
        stock_series=stock_series,
        benchmark=market_benchmark,
        benchmark_id=index_symbol or etf_symbol,
        decision_time=decision_time,
        retrieved_at=retrieved_at,
        source_id=owner.owner_id,
    )
    theme = _theme_observation(
        bars_by_symbol=bars_by_symbol,
        stock_series=stock_series,
        benchmark=theme_benchmark,
        etf_symbol=etf_symbol,
        decision_time=decision_time,
        retrieved_at=retrieved_at,
        source_id=owner.owner_id,
    )
    market_returns = tuple(value for item in stock_series.values() if (value := _return(item, 5)) is not None)
    leader_series = max(
        stock_series.values(),
        key=lambda item: _return(item, 5) or float("-inf"),
        default=(),
    )
    leader_returns = _daily_returns(leader_series, 21)
    current_ranks = _cross_sectional_percentile_ranks(stock_series, offset=0)
    previous_ranks = _cross_sectional_percentile_ranks(stock_series, offset=1)
    symbols = tuple(
        _symbol_observation(
            symbol=symbol,
            series=stock_series[symbol],
            all_series=stock_series,
            bars=bars_by_symbol.get(symbol, ()),
            decision_time=decision_time,
            computations=computations,
            market_returns=market_returns,
            leader_returns=leader_returns,
            current_ranks=current_ranks,
            previous_ranks=previous_ranks,
            retrieved_at=retrieved_at,
            source_id=owner.owner_id,
        )
        for symbol in stock_symbols
    )
    etf_amount_expansion = (
        None if etf_symbol is None else _symbol_same_cutoff_amount_change(bars_by_symbol.get(etf_symbol, ()), decision_time)
    )
    etfs = (
        ()
        if etf_symbol is None or len(theme_benchmark) < 6 or etf_amount_expansion is None
        else (
            ETFObservation(
                etf_id=etf_symbol,
                theme_id=GLOBAL_RESEARCH_THEME_ID,
                available_at=AvailabilityTime(retrieved_at),
                source_artifact_id=owner.owner_id,
                relative_strength=_return(theme_benchmark, 5) or 0.0,
                amount_expansion=etf_amount_expansion,
            ),
        )
    )
    memberships = tuple(ThemeMembership(symbol=symbol, primary_theme_id=GLOBAL_RESEARCH_THEME_ID) for symbol in stock_symbols)
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
        "market_benchmark_id": index_symbol or etf_symbol,
        "theme_benchmark_id": etf_symbol or index_symbol,
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


def _daily_series(bars: tuple[HistoricalNormalizedBar, ...], decision_time: datetime) -> tuple[HistoricalNormalizedBar, ...]:
    return tuple(item for item in bars if item.timeframe is Timeframe.DAILY and item.event_end <= decision_time and item.close is not None)


def _bars_by_symbol(
    bars: tuple[HistoricalNormalizedBar, ...],
) -> Mapping[str, tuple[HistoricalNormalizedBar, ...]]:
    grouped: dict[str, list[HistoricalNormalizedBar]] = {}
    for item in bars:
        grouped.setdefault(item.symbol, []).append(item)
    return {symbol: tuple(sorted(values, key=_historical_bar_key)) for symbol, values in grouped.items()}


def _market_observation(
    *,
    bars_by_symbol: Mapping[str, tuple[HistoricalNormalizedBar, ...]],
    stock_symbols: tuple[str, ...],
    stock_series: Mapping[str, tuple[HistoricalNormalizedBar, ...]],
    benchmark: tuple[HistoricalNormalizedBar, ...],
    benchmark_id: str | None,
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
            for item in bars_by_symbol.get(symbol, ())
            if item.timeframe is Timeframe.MINUTE_5
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
    amount_change = _same_cutoff_amount_change(bars_by_symbol, stock_symbols, decision_time)
    coverage = len(intraday_returns) / len(stock_symbols) if stock_symbols else 0.0
    return MarketObservation(
        available_at=AvailabilityTime(retrieved_at),
        source_artifact_id=source_id,
        market_direction_return=(_return(benchmark, 3) if benchmark else (fmean(returns) if returns else None)),
        market_intraday_range_to_cutoff=fmean(ranges) if ranges else None,
        market_amount_change_same_cutoff=amount_change,
        candidate_breadth_at_cutoff=(sum(item > 0 for item in intraday_returns) / len(intraday_returns) if intraday_returns else None),
        limit_structure_score=(
            (sum(item >= 0.095 for item in intraday_returns) - sum(item <= -0.095 for item in intraday_returns)) / len(intraday_returns)
            if intraday_returns
            else None
        ),
        coverage=coverage,
        reason_codes=tuple(
            sorted(
                {
                    "RETROSPECTIVE_CROSS_SECTIONAL_MARKET_CONTEXT",
                    (
                        "REAL_INDEX_BENCHMARK"
                        if benchmark_id is not None and not _is_etf_symbol(benchmark_id)
                        else "ETF_OR_CROSS_SECTIONAL_MARKET_BENCHMARK"
                    ),
                    ("SAME_CUTOFF_MINUTE_AMOUNT_AVAILABLE" if amount_change is not None else "SAME_CUTOFF_MINUTE_AMOUNT_NOT_ESTIMABLE"),
                }
            )
        ),
    )


def _theme_observation(
    *,
    bars_by_symbol: Mapping[str, tuple[HistoricalNormalizedBar, ...]],
    stock_series: Mapping[str, tuple[HistoricalNormalizedBar, ...]],
    benchmark: tuple[HistoricalNormalizedBar, ...],
    etf_symbol: str | None,
    decision_time: datetime,
    retrieved_at: datetime,
    source_id: ArtifactId,
) -> ThemeResearchObservation | None:
    eligible = tuple(series for series in stock_series.values() if len(series) >= 21)
    if not eligible:
        return None
    benchmark_returns = {window: _return(benchmark, window) for window in (1, 3, 5, 10)}
    relative = {
        window: fmean(value - (benchmark_returns[window] or 0.0) for series in eligible if (value := _return(series, window)) is not None)
        for window in (1, 3, 5, 10)
    }
    return5 = tuple(_return(series, 5) or 0.0 for series in eligible)
    amount_values = tuple(
        value
        for symbol in stock_series
        if (value := _symbol_same_cutoff_amount_change(bars_by_symbol.get(symbol, ()), decision_time)) is not None
    )
    latest_amounts = sorted((float(series[-1].amount or Decimal("0")) for series in eligible), reverse=True)
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
        etf_amount_expansion=(
            None if etf_symbol is None else _symbol_same_cutoff_amount_change(bars_by_symbol.get(etf_symbol, ()), decision_time)
        ),
        breadth=breadth,
        new_high_breadth=sum(float(series[-1].close or 0) >= max(float(item.close or 0) for item in series[-21:-1]) for series in eligible)
        / len(eligible),
        leader_strength=max(return5) - (benchmark_returns[5] or 0.0),
        participation_change=(breadth - sum((_return(series[:-1], 5) or 0.0) > 0 for series in eligible) / len(eligible)),
        rank_persistence=_cross_sectional_rank_persistence(eligible, 5),
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
    bars: tuple[HistoricalNormalizedBar, ...],
    decision_time: datetime,
    computations: tuple[_HistoricalFeatureComputation, ...],
    market_returns: tuple[float, ...],
    leader_returns: tuple[float, ...],
    current_ranks: Mapping[str, float],
    previous_ranks: Mapping[str, float],
    retrieved_at: datetime,
    source_id: ArtifactId,
) -> SymbolResearchObservation:
    symbol_return = _return(series, 5)
    amount = _symbol_same_cutoff_amount_change(bars, decision_time)
    complete = len(series) >= 61
    symbol_returns = _daily_returns(series, 21)
    amount_history = tuple(
        value for end in range(max(6, len(series) - 4), len(series) + 1) if (value := _amount_expansion(series[:end])) is not None
    )
    return SymbolResearchObservation(
        symbol=symbol,
        available_at=AvailabilityTime(retrieved_at),
        source_artifact_id=source_id,
        symbol_relative_strength=(None if symbol_return is None or not market_returns else symbol_return - fmean(market_returns)),
        symbol_amount_expansion=amount,
        theme_participation_contribution=(None if amount is None else amount / max(1, len(all_series))),
        leader_correlation=(_correlation(symbol_returns, leader_returns) if complete else None),
        leader_lag=(_correlation(symbol_returns[1:], leader_returns[:-1]) if complete else None),
        rank_persistence=(
            None
            if not complete or symbol not in current_ranks or symbol not in previous_ranks
            else 1.0 - abs(current_ranks[symbol] - previous_ranks[symbol])
        ),
        amount_persistence=(None if not complete or not amount_history else sum(item > 0 for item in amount_history) / len(amount_history)),
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


def _symbol_same_cutoff_amount_change(
    bars: tuple[HistoricalNormalizedBar, ...],
    decision_time: datetime,
) -> float | None:
    amounts = _same_cutoff_amount_pair(bars, decision_time)
    if amounts is None or amounts[1] <= 0:
        return None
    return float(amounts[0] / amounts[1] - Decimal("1"))


def _same_cutoff_amount_change(
    bars_by_symbol: Mapping[str, tuple[HistoricalNormalizedBar, ...]],
    symbols: tuple[str, ...],
    decision_time: datetime,
) -> float | None:
    pairs = tuple(
        pair for symbol in symbols if (pair := _same_cutoff_amount_pair(bars_by_symbol.get(symbol, ()), decision_time)) is not None
    )
    if not pairs:
        return None
    current = sum((item[0] for item in pairs), Decimal("0"))
    previous = sum((item[1] for item in pairs), Decimal("0"))
    return None if previous <= 0 else float(current / previous - Decimal("1"))


def _same_cutoff_amount_pair(
    bars: tuple[HistoricalNormalizedBar, ...],
    decision_time: datetime,
) -> tuple[Decimal, Decimal] | None:
    zone = ZoneInfo("Asia/Shanghai")
    market_date = decision_time.astimezone(zone).date()
    cutoff = decision_time.astimezone(zone).time().replace(tzinfo=None)
    dates = sorted({item.market_date for item in bars if item.timeframe is Timeframe.MINUTE_5 and item.market_date <= market_date})
    if market_date not in dates:
        return None
    prior_dates = tuple(item for item in dates if item < market_date)
    if not prior_dates:
        return None
    previous_date = prior_dates[-1]

    def amount_for(target_date: date) -> Decimal | None:
        values = tuple(
            item.amount
            for item in bars
            if item.timeframe is Timeframe.MINUTE_5
            and item.market_date == target_date
            and item.event_end.astimezone(zone).time().replace(tzinfo=None) <= cutoff
            and item.amount is not None
        )
        return None if not values else sum(values, Decimal("0"))

    current = amount_for(market_date)
    previous = amount_for(previous_date)
    return None if current is None or previous is None else (current, previous)


def _daily_returns(series: tuple[HistoricalNormalizedBar, ...], maximum: int) -> tuple[float, ...]:
    values = tuple(item.close for item in series if item.close is not None)
    return tuple(
        float(current / previous - Decimal("1"))
        for previous, current in zip(values[-maximum - 1 : -1], values[-maximum:], strict=False)
        if previous > 0
    )


def _cross_sectional_percentile_ranks(
    series_by_symbol: Mapping[str, tuple[HistoricalNormalizedBar, ...]],
    *,
    offset: int,
    window: int = 5,
) -> dict[str, float]:
    values = {
        symbol: value
        for symbol, series in series_by_symbol.items()
        if len(series) > offset and (value := _return(series[:-offset] if offset else series, window)) is not None
    }
    ordered = sorted(values, key=lambda symbol: (values[symbol], symbol))
    denominator = max(1, len(ordered) - 1)
    return {symbol: index / denominator for index, symbol in enumerate(ordered)}


def _cross_sectional_rank_persistence(series: tuple[tuple[HistoricalNormalizedBar, ...], ...], window: int) -> float | None:
    by_symbol = {item[-1].symbol: item for item in series if item}
    current = _cross_sectional_percentile_ranks(by_symbol, offset=0, window=window)
    previous = _cross_sectional_percentile_ranks(by_symbol, offset=1, window=window)
    symbols = tuple(sorted(set(current) & set(previous)))
    if len(symbols) < 2:
        return None
    return _correlation(
        tuple(current[symbol] for symbol in symbols),
        tuple(previous[symbol] for symbol in symbols),
    )


def _context_instrument_coverage(
    *,
    bars: tuple[HistoricalNormalizedBar, ...],
    context_symbols: tuple[str, ...],
    decision_time: datetime,
) -> dict[str, Any]:
    by_symbol = _bars_by_symbol(bars)
    instruments = []
    for symbol in context_symbols:
        daily = _daily_series(by_symbol.get(symbol, ()), decision_time)
        instrument_kind = "ETF" if _is_etf_symbol(symbol) else "INDEX"
        instruments.append(
            {
                "symbol": symbol,
                "instrument_kind": instrument_kind,
                "daily_observation_count": len(daily),
                "status": "AVAILABLE" if daily else "NOT_ESTIMABLE",
            }
        )
    return {
        "instruments": instruments,
        "etf_available_count": sum(item["instrument_kind"] == "ETF" and item["status"] == "AVAILABLE" for item in instruments),
        "index_available_count": sum(item["instrument_kind"] == "INDEX" and item["status"] == "AVAILABLE" for item in instruments),
    }


def _correlation(left: tuple[float, ...], right: tuple[float, ...]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_mean = fmean(left)
    right_mean = fmean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    denominator = sqrt(sum((item - left_mean) ** 2 for item in left) * sum((item - right_mean) ** 2 for item in right))
    return None if denominator == 0 else numerator / denominator


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


def _forecast_configuration(decision_time: datetime) -> PathForecastConfig:
    target = build_entry_path_target_contract(
        EntryBarrierSpec(
            upper_return=0.02,
            lower_return=-0.01,
            horizon_sessions=1,
            price_adjustment_basis="RAW_UNADJUSTED_TRADABLE_PRICE_V1",
        )
    )
    return PathForecastConfig(
        profile_id="phase-e-retrospective-path-forecast-v1",
        model_id=ModelId("empirical-path-forecast-v1"),
        model_version="1.0.0-exploratory-pit-incomplete",
        decision_profile_id="phase-e-historical-decision-v1",
        decision_time_local=decision_time.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%H:%M"),
        timezone_name="Asia/Shanghai",
        market_scope="A_SHARE",
        allowed_side="LONG_ONLY",
        target_contract=target,
        horizon_label="T_PLUS_ONE_TO_1030",
        return_quantile_levels=(0.25, 0.5, 0.75),
        minimum_usable_samples=20,
        aggregation_method="EMPIRICAL_LINEAR_QUANTILE_MEAN_EXCURSION_V1",
        schema_version=PATH_FORECAST_CONFIG_SCHEMA,
    )


def _prior_forecast_samples(
    *,
    prior_labels: tuple[tuple[ValidationArtifactReference, TargetOutcomeLabel], ...],
    symbol: str,
    configuration: PathForecastConfig,
) -> tuple[
    tuple[PathForecastSample, ...],
    dict[ArtifactId, datetime],
    tuple[ValidationArtifactReference, ...],
]:
    samples: list[PathForecastSample] = []
    event_ends: dict[ArtifactId, datetime] = {}
    sources: list[ValidationArtifactReference] = []
    for component_reference, label in prior_labels:
        if label.symbol != symbol:
            raise ValueError("Historical Outcome label symbol projection drift")
        usable = all(item is not None for item in (label.checkpoint_return, label.mfe, label.mae))
        sample_identity = canonical_hash(
            {
                "outcome_component_id": str(component_reference.artifact_id),
                "outcome_component_hash": component_reference.content_hash,
                "label_id": str(label.label_id),
                "forecast_target_id": str(configuration.target_contract.target_id),
            }
        )
        sample = PathForecastSample(
            sample_id=ArtifactId(f"historical-path-sample-{sample_identity[7:31]}"),
            source_artifact_id=component_reference.artifact_id,
            source_content_hash=component_reference.content_hash,
            symbol=symbol,
            target_id=TargetId(str(configuration.target_contract.target_id)),
            sample_decision_time=DecisionTime(label.label_interval_start),
            available_at=AvailabilityTime(label.outcome_available_at),
            observation_status=(EntryPathObservationStatus.AVAILABLE if usable else EntryPathObservationStatus.NOT_YET_OBSERVED),
            observation_reason_code=(
                EntryPathReasonCode.OUTCOME_RESOLVED if usable else EntryPathReasonCode.EVIDENCE_COVERAGE_NOT_COMPLETE
            ),
            realized_mfe=(None if label.mfe is None else max(0.0, float(label.mfe))),
            realized_mae=(None if label.mae is None else min(0.0, float(label.mae))),
            realized_return=(None if label.checkpoint_return is None else float(label.checkpoint_return)),
            schema_version=PATH_FORECAST_SAMPLE_SCHEMA,
        )
        samples.append(sample)
        event_ends[sample.sample_id] = label.label_interval_end
        sources.append(component_reference)
    ordered = tuple(
        sorted(
            samples,
            key=lambda item: (item.sample_decision_time.value, str(item.sample_id)),
        )
    )
    return ordered, event_ends, _references(tuple(sources))


def _strategy_policy(target: TargetDefinition, created_at: datetime) -> StrategyEconomicsPolicy:
    return StrategyEconomicsPolicy.create(
        policy_version=f"phase-e-{target.checkpoint.value}-engineering-cost-v1",
        prediction_target=target,
        entry_kind=StrategyEntryKind.FROZEN_DECISION_REFERENCE,
        exit_kind=StrategyExitKind.FIXED_TIME,
        fixed_exit_checkpoint=target.checkpoint,
        barrier_id=None,
        forecast_raw_score_threshold=None,
        lot_size=100,
        t_plus_one=True,
        parameters={
            "commission_bps": (
                Decimal("3"),
                ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
            ),
            "stamp_duty_bps": (
                Decimal("5"),
                ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
            ),
            "spread_slippage_bps": (
                Decimal("5"),
                ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
            ),
        },
        created_at=created_at,
    )


def _capacity_protocol(created_at: datetime) -> LiquidityCapacityProtocol:
    return LiquidityCapacityProtocol.create(
        protocol_version="phase-e-capacity-engineering-v1",
        parameters=tuple(
            CapacityParameter(
                name,
                value,
                CapacityValueProvenance.ENGINEERING_ASSUMPTION,
            )
            for name, value in (
                ("impact_coefficient_bps", Decimal("8")),
                ("participation_rate", Decimal("0.1")),
                ("slippage_bps", Decimal("5")),
            )
        ),
        created_at=created_at,
    )


def _canonical_outcome_bars(bars: tuple[HistoricalNormalizedBar, ...], next_session: date) -> tuple[CanonicalMarketBar, ...]:
    result: list[CanonicalMarketBar] = []
    symbols = sorted({item.symbol for item in bars if item.market_date == next_session})
    for symbol in symbols:
        rows = tuple(
            sorted(
                (item for item in bars if item.symbol == symbol and item.market_date == next_session and item.open is not None),
                key=lambda item: (item.timeframe.value, item.event_start),
            )
        )
        result.extend(
            _canonical_bars(
                rows,
                asset_type=(AssetType.ETF if _is_etf_symbol(symbol) else AssetType.A_SHARE),
            )
        )
    return tuple(sorted(result, key=lambda item: (item.symbol, item.event_start)))


def _decision_reference_price(
    bars: tuple[HistoricalNormalizedBar, ...],
    symbol: str,
    trading_date: date,
    decision_time: datetime,
) -> Decimal | None:
    intraday = tuple(
        item
        for item in bars
        if item.symbol == symbol
        and item.market_date == trading_date
        and item.timeframe is Timeframe.MINUTE_5
        and item.event_end <= decision_time
        and item.close is not None
    )
    if intraday:
        return intraday[-1].close
    daily = tuple(
        item
        for item in bars
        if item.symbol == symbol and item.timeframe is Timeframe.DAILY and item.event_end <= decision_time and item.close is not None
    )
    return None if not daily else daily[-1].close


def _market_conditions(bars: tuple[HistoricalNormalizedBar, ...], symbol: str, market_date: date) -> tuple[OutcomeMarketCondition, ...]:
    selected = tuple(item for item in bars if item.symbol == symbol and item.market_date == market_date)
    if not selected:
        return (OutcomeMarketCondition.MISSING_QUOTE,)
    if any(item.trading_status is HistoricalTradingStatus.SUSPENDED for item in selected):
        return (OutcomeMarketCondition.SUSPENDED,)
    conditions = {OutcomeMarketCondition.TRADING}
    daily = next((item for item in selected if item.timeframe is Timeframe.DAILY), None)
    prior = tuple(
        item
        for item in bars
        if item.symbol == symbol and item.timeframe is Timeframe.DAILY and item.market_date < market_date and item.close is not None
    )
    if daily is not None and daily.open is not None and prior:
        previous_close = prior[-1].close
        assert previous_close is not None
        threshold = (
            Decimal("0.05")
            if daily.st_status
            else Decimal("0.20")
            if symbol.startswith(("300", "301", "688"))
            else Decimal("0.30")
            if symbol.startswith(("4", "8"))
            else Decimal("0.10")
        )
        tolerance = Decimal("0.001")
        change = daily.open / previous_close - Decimal("1")
        if change >= threshold - tolerance:
            conditions.add(OutcomeMarketCondition.LIMIT_UP)
        if change <= -threshold + tolerance:
            conditions.add(OutcomeMarketCondition.LIMIT_DOWN)
    return tuple(sorted(conditions, key=lambda item: item.value))


def _execution_observation(
    *,
    phase: StrategyExecutionPhase,
    symbol: str,
    price: Decimal | None,
    market_conditions: tuple[OutcomeMarketCondition, ...],
    effective_at: datetime,
    available_at: datetime,
    source_reference: ValidationArtifactReference,
) -> StrategyExecutionObservation:
    return StrategyExecutionObservation(
        phase=phase,
        symbol=symbol,
        price=price,
        market_conditions=tuple(sorted(set(market_conditions), key=lambda item: item.value)),
        effective_at=effective_at,
        available_at=available_at,
        source_reference=source_reference,
    )


def _complete_stage(
    *,
    request: ResearchDecisionSessionRequest,
    inputs: tuple[ValidationArtifactReference, ...],
    output: ValidationArtifactReference,
    reason: str,
) -> SessionStageComputation:
    return SessionStageComputation(
        status=SessionStageStatus.COMPLETE,
        output_references=(output,),
        input_references=_references(inputs),
        completed_at=request.materialized_at,
        reason_codes=(reason,),
    )


def _research_panel_rows(
    *,
    trading_date: date,
    feature: HistoricalSessionComponent,
    market: HistoricalSessionComponent,
    etf: HistoricalSessionComponent,
    theme: HistoricalSessionComponent,
    capital: HistoricalSessionComponent,
    pool: HistoricalSessionComponent,
    candidate: HistoricalSessionComponent,
    signal: HistoricalSessionComponent,
    forecast: HistoricalSessionComponent,
    outcome: HistoricalSessionComponent,
) -> tuple[dict[str, Any], ...]:
    feature_values = _panel_feature_values(feature)
    signal_by_symbol = {str(item["symbol"]): item for item in _objects(signal.payload.get("snapshots"), "signal snapshots")}
    forecast_by_symbol = {
        str(_mapping(item.get("forecast"), "forecast")["symbol"]): _mapping(item.get("forecast"), "forecast")
        for item in _objects(forecast.payload.get("forecasts"), "forecasts")
    }
    protocol = OutcomeTargetProtocol.from_canonical_dict(_mapping(outcome.payload.get("target_protocol"), "target protocol"))
    target = next(item for item in protocol.targets if item.checkpoint is OutcomeCheckpoint.TIME_1030)
    labels = {
        label.symbol: label
        for label in (TargetOutcomeLabel.from_canonical_dict(item) for item in _objects(outcome.payload.get("labels"), "outcome labels"))
        if label.target.artifact_id == target.target_id
    }
    economics = {
        str(item["symbol"]): item
        for item in _objects(outcome.payload.get("strategy_economics"), "strategy economics")
        if isinstance(item.get("target_label_reference"), Mapping)
        and str(item["target_label_reference"].get("artifact_id")) in {str(label.label_id) for label in labels.values()}
    }
    market_state = str(market.payload.get("market_state", "DATA_INSUFFICIENT"))
    volatility = str(market.payload.get("market_volatility", "UNKNOWN"))
    etf_observations = _objects(etf.payload.get("observations"), "ETF observations")
    etf_score = (
        None
        if not etf_observations
        else (Decimal(str(etf_observations[0].get("relative_strength", 0))) + Decimal(str(etf_observations[0].get("amount_expansion", 0))))
        / Decimal("2")
    )
    pool_membership = {str(item["symbol"]): bool(item["included"]) for item in _objects(pool.payload.get("membership"), "pool membership")}
    business_facts = {
        str(item["symbol"]): item
        for item in _objects(
            pool.payload.get("historical_business_facts", []),
            "historical business facts",
        )
    }
    action_exclusions = {
        str(item["symbol"])
        for item in _objects(
            outcome.payload.get("corporate_action_exclusions", []),
            "corporate action exclusions",
        )
    }
    records = _objects(candidate.payload.get("records"), "candidate records")
    rows: list[dict[str, Any]] = []
    for record in records:
        symbol = str(record["symbol"])
        label = labels.get(symbol)
        result = economics.get(symbol)
        values = feature_values.get(symbol, {})
        forecast_payload = forecast_by_symbol.get(symbol)
        median_forecast = _forecast_median(forecast_payload)
        signal_payload = signal_by_symbol.get(symbol)
        capacity = None if result is None else _optional_decimal(result.get("capacity_ceiling"))
        business = business_facts.get(symbol, {})
        market_cap = _optional_decimal(business.get("market_cap"))
        rows.append(
            {
                "session_key": trading_date.isoformat(),
                "trading_date": trading_date.isoformat(),
                "symbol": symbol,
                "selected": record.get("selection_status") == "SELECTED",
                "candidate_rank": record.get("rank"),
                "score": _decimal_string(record.get("candidate_discovery_score")),
                "factor_values": {
                    "price": _decimal_string(values.get("return_3")),
                    "volume": _decimal_string(values.get("amount_ratio_5")),
                    "market_regime": _decimal_string(record.get("market_regime_score")),
                    "etf": _decimal_string(etf_score),
                    "theme": _decimal_string(record.get("theme_score")),
                    "capital": _decimal_string(record.get("capital_evolution_score")),
                    "dynamic_pool": ("1" if pool_membership.get(symbol, False) else "0"),
                    "candidate": _decimal_string(record.get("candidate_discovery_score")),
                    "signal": _decimal_string(None if signal_payload is None else signal_payload.get("signal_score")),
                    "forecast": _decimal_string(median_forecast),
                },
                "signal_diagnostic": (
                    {
                        "state": "NOT_EMITTED_NOT_SELECTED",
                        "confirmation_states": {},
                        "reason_codes": ["CANDIDATE_NOT_SELECTED"],
                    }
                    if signal_payload is None
                    else {
                        "state": str(signal_payload["signal_state"]),
                        "confirmation_states": {
                            name: str(signal_payload[name])
                            for name in (
                                "price_action_state",
                                "volume_confirmation_state",
                                "trend_confirmation_state",
                                "vwap_state",
                                "overheat_state",
                            )
                        },
                        "reason_codes": list(signal_payload["reason_codes"]),
                    }
                ),
                "forecast_diagnostic": (
                    {
                        "status": "NOT_EMITTED_NO_SIGNAL",
                        "usable_sample_count": 0,
                        "excluded_sample_count": 0,
                        "reason_codes": ["SIGNAL_NOT_EMITTED"],
                    }
                    if forecast_payload is None
                    else {
                        "status": str(forecast_payload["forecast_status"]),
                        "usable_sample_count": int(forecast_payload["usable_sample_count"]),
                        "excluded_sample_count": int(forecast_payload["excluded_sample_count"]),
                        "reason_codes": list(forecast_payload["reason_codes"]),
                    }
                ),
                "target_return": (None if label is None else _decimal_string(label.checkpoint_return)),
                "target_status": (
                    "CORPORATE_ACTION_EXCLUDED"
                    if symbol in action_exclusions
                    else "NOT_ESTIMABLE"
                    if label is None
                    else label.availability_status.value
                ),
                "mfe": None if label is None else _decimal_string(label.mfe),
                "mae": None if label is None else _decimal_string(label.mae),
                "gross_return": (None if result is None else result.get("gross_return")),
                "cost_return": (None if result is None else result.get("cost_return")),
                "net_return": (None if result is None else result.get("net_return")),
                "economics_status": ("NOT_ESTIMABLE" if result is None else str(result["status"])),
                "capacity_ceiling": (None if capacity is None else str(capacity)),
                "market_regime": market_state,
                "liquidity_bucket": _liquidity_bucket(capacity),
                "market_cap_bucket": _market_cap_bucket(market_cap),
                "volatility_bucket": volatility,
                "theme": str(record.get("primary_theme_id") or "NOT_ESTIMABLE"),
                "industry": str(business.get("industry") or "NOT_ESTIMABLE"),
                "evidence_ceiling": "EXPLORATORY_PIT_INCOMPLETE",
                "theme_owner_status": str(theme.payload.get("rotation_state", "UNKNOWN")),
                "capital_owner_status": str(capital.payload.get("capital_state", "UNKNOWN")),
            }
        )
    return tuple(rows)


def _panel_feature_values(
    feature: HistoricalSessionComponent,
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for computation in _objects(feature.payload.get("features"), "features"):
        symbol_values = result.setdefault(str(computation["symbol"]), {})
        for value in _objects(computation.get("values"), "feature values"):
            if value.get("state") == "AVAILABLE":
                symbol_values[str(value["output_id"])] = value.get("value")
    return result


def _forecast_median(payload: Mapping[str, Any] | None) -> object:
    if payload is None:
        return None
    quantiles = _objects(payload.get("return_quantiles"), "return quantiles")
    return next(
        (item.get("return_value") for item in quantiles if float(item.get("probability", -1)) == 0.5),
        None,
    )


def _liquidity_bucket(capacity: Decimal | None) -> str:
    if capacity is None:
        return "NOT_ESTIMABLE"
    if capacity < Decimal("100000"):
        return "LOW"
    if capacity < Decimal("1000000"):
        return "MEDIUM"
    return "HIGH"


def _market_cap_bucket(market_cap: Decimal | None) -> str:
    if market_cap is None:
        return "NOT_ESTIMABLE"
    if market_cap < Decimal("10000000000"):
        return "SMALL_LT_CNY_10B"
    if market_cap < Decimal("50000000000"):
        return "MID_CNY_10B_TO_50B"
    return "LARGE_GTE_CNY_50B"


def _mean_decimal_text(values: Any) -> str | None:
    numbers = tuple(Decimal(str(item)) for item in values if item is not None)
    return None if not numbers else str(sum(numbers, Decimal("0")) / len(numbers))


def _decimal_string(value: object) -> str | None:
    if value is None:
        return None
    return str(Decimal(str(value)))


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"Historical {label} must be an object")
    return value


def _objects(value: object, label: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"Historical {label} must be an object array")
    return tuple(value)


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
    "HISTORICAL_SECURITY_FACTS_KIND",
    "NORMALIZED_DATASET_KIND",
    "HistoricalDecisionMaterializer",
]
