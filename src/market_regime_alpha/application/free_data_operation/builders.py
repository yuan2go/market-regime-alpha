"""Materialize honest Controlled inputs from verified free-data evidence."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Iterable
from zoneinfo import ZoneInfo

from market_regime_alpha.application.controlled_operation.input_artifacts import (
    load_controlled_runtime_configuration,
    publish_controlled_runtime_configuration,
    publish_controlled_source_manifest,
    publish_controlled_trading_calendar,
)
from market_regime_alpha.application.controlled_operation.runtime_configuration import (
    ControlledOperationRuntimeConfiguration,
)
from market_regime_alpha.application.free_data_operation.contracts import (
    FreeDataPreparationRequest,
    FreeDataPreparedInputs,
    FreeDataPreparedManifest,
    FreeDataPreparedPaths,
    PreparedArtifactReference,
    publish_free_data_prepared_manifest,
)
from market_regime_alpha.application.operational_research.contracts import (
    MissingEvidence,
    SupplementalResearchEvidenceBundle,
)
from market_regime_alpha.application.operational_research.supplemental_artifact import (
    load_verified_supplemental_research_evidence,
    publish_supplemental_research_evidence,
)
from market_regime_alpha.core.identity import ArtifactId, ProviderId
from market_regime_alpha.core.time import AvailabilityTime, RetrievedAt
from market_regime_alpha.data.contracts import (
    DataEligibility,
    SourceArtifactReference,
)
from market_regime_alpha.data.providers.public_composite import PublicCompositeProviderResult
from market_regime_alpha.data.providers.public_composite.contracts import (
    ListingStatus as PublicListingStatus,
)
from market_regime_alpha.data.providers.public_composite.contracts import (
    STStatus as PublicSTStatus,
)
from market_regime_alpha.data.providers.public_composite.contracts import (
    TradingStatus as PublicTradingStatus,
)
from market_regime_alpha.data.providers.public_composite.stage_artifact import (
    PublicSourceAcquisitionStage,
    VerifiedPublicSourceStageArtifact,
)
from market_regime_alpha.data.source_manifest import (
    CriticalSourceFact,
    SourceManifest,
    SourceManifestField,
)
from market_regime_alpha.data.trading_calendar import (
    TradingCalendarArtifact,
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.evidence.canonical import normalize_canonical_datetime
from market_regime_alpha.market_data import (
    CanonicalMarketBar,
    FormalPitStatus,
    MarketDataDatasetArtifact,
    Timeframe,
    normalize_public_history_stage,
    publish_market_data_dataset,
)
from market_regime_alpha.research.platform_v2.inputs import (
    MarketObservation,
    ResearchDailyBar,
    SymbolResearchObservation,
)
from market_regime_alpha.signals import canonical_signal_freshness_policy
from market_regime_alpha.universe import (
    ListingStatus,
    OperationalLiquidityEvidence,
    OperationalUniverseArtifact,
    OperationalUniverseRecord,
    STStatus,
    SuspensionStatus,
    publish_operational_universe,
)


_SHANGHAI = ZoneInfo("Asia/Shanghai")


def prepare_free_data_inputs(
    *,
    request: FreeDataPreparationRequest,
    history_source: VerifiedPublicSourceStageArtifact,
    provider_result: PublicCompositeProviderResult,
    full_source_manifest: SourceManifest,
    output_root: Path,
    runtime_configuration_path: Path | None = None,
    supplemental_evidence_path: Path | None = None,
) -> FreeDataPreparedInputs:
    """Publish deterministic inputs; mutable lifecycle state stays in PostgreSQL."""

    root = output_root.resolve()
    _validate_source_bindings(
        request=request,
        history_source=history_source,
        provider_result=provider_result,
        full_source_manifest=full_source_manifest,
        output_root=root,
    )
    created_at = normalize_canonical_datetime(request.created_at)
    decision_time = normalize_canonical_datetime(request.decision_time.value)
    history_manifest = SourceManifest(
        provider_profile_id=request.provider_profile_id,
        decision_time=request.decision_time,
        source_artifacts=tuple(
            item.reference for item in history_source.batch.raw_payloads
        ),
        fields=(),
        source_conflicts=history_source.batch.source_conflicts,
        limitations=tuple(
            dict.fromkeys(
                (
                    *history_source.batch.limitations,
                    "FORMAL_PIT_NOT_ESTABLISHED",
                    "HISTORY_SOURCE_STAGE_ONLY",
                    "PUBLIC_DATA_EXPLORATORY_ONLY",
                )
            )
        ),
        data_eligibility=DataEligibility.EXPLORATORY,
        schema_version=SourceManifest.SCHEMA_V2,
    )
    history_manifest_path = publish_controlled_source_manifest(
        root=root / "daily_source_manifests",
        artifact=history_manifest,
    )
    full_manifest_path = publish_controlled_source_manifest(
        root=root / "full_source_manifests",
        artifact=full_source_manifest,
    )
    daily_dataset = normalize_public_history_stage(
        verified=history_source,
        decision_time=decision_time,
        created_at=created_at,
        expected_symbols=request.symbols,
        source_manifest=history_manifest,
        asset_types=request.asset_types,
    )
    daily_dataset_path = publish_market_data_dataset(
        root=root / "daily_market_data",
        artifact=daily_dataset,
    )
    calendar = _build_calendar(
        dataset=daily_dataset,
        request=request,
        provider_result=provider_result,
        source_manifest=full_source_manifest,
    )
    calendar_path = publish_controlled_trading_calendar(
        root=root / "trading_calendars",
        artifact=calendar,
    )
    universe = _build_universe(
        request=request,
        dataset=daily_dataset,
        full_source_manifest=full_source_manifest,
    )
    universe_path = publish_operational_universe(
        root=root / "operational_universes",
        artifact=universe,
    )
    supplemental = (
        _load_explicit_supplemental(
            path=supplemental_evidence_path,
            request=request,
            universe=universe,
        )
        if supplemental_evidence_path is not None
        else _build_supplemental(
            request=request,
            dataset=daily_dataset,
            universe=universe,
            full_source_manifest=full_source_manifest,
        )
    )
    supplemental_path = publish_supplemental_research_evidence(
        root=root / "supplemental_research_evidence",
        bundle=supplemental,
    )
    active_configuration_path: Path | None = None
    active_configuration = None
    if runtime_configuration_path is not None:
        template = load_controlled_runtime_configuration(
            runtime_configuration_path.resolve()
        )
        active_configuration = ControlledOperationRuntimeConfiguration.create(
            static_feature_set=template.static_feature_set,
            intraday_feature_set=template.intraday_feature_set,
            research=template.research,
            signal_model=template.signal_model,
            signal_mapping=template.signal_mapping,
            signal_requirement=template.signal_requirement,
            signal_freshness=canonical_signal_freshness_policy(
                trading_calendar=calendar
            ),
            path_forecast=template.path_forecast,
            feature_max_workers=template.feature_max_workers,
            minute_concurrency_limit=template.minute_concurrency_limit,
            minute_per_request_timeout_seconds=(
                template.minute_per_request_timeout_seconds
            ),
            minute_max_attempts=template.minute_max_attempts,
            minute_retry_backoff_seconds=template.minute_retry_backoff_seconds,
            provider_profile_id=template.provider_profile_id,
            limitations=template.limitations,
        )
        active_configuration_path = publish_controlled_runtime_configuration(
            root=root / "runtime_configurations",
            artifact=active_configuration,
        )
    paths = FreeDataPreparedPaths(
        history_source_stage=history_source.root,
        daily_source_manifest=history_manifest_path,
        full_source_manifest=full_manifest_path,
        daily_market_data=daily_dataset_path,
        trading_calendar=calendar_path,
        operational_universe=universe_path,
        supplemental_research_evidence=supplemental_path,
        runtime_configuration=active_configuration_path,
    )
    configuration_reference: tuple[PreparedArtifactReference, ...] = ()
    if active_configuration is not None and active_configuration_path is not None:
        configuration_reference = (
            _reference(
                "RUNTIME_CONFIGURATION",
                active_configuration.configuration_id,
                active_configuration.configuration_hash,
                active_configuration_path,
                root,
            ),
        )
    prepared_manifest = FreeDataPreparedManifest.create(
        request=request,
        artifacts=(
            _reference(
                "DAILY_SOURCE_STAGE",
                history_source.artifact_id,
                history_source.content_hash,
                history_source.root,
                root,
            ),
            _reference(
                "DAILY_SOURCE_MANIFEST",
                history_manifest.source_manifest_id,
                history_manifest.content_hash,
                history_manifest_path,
                root,
            ),
            _reference(
                "FULL_SOURCE_MANIFEST",
                full_source_manifest.source_manifest_id,
                full_source_manifest.content_hash,
                full_manifest_path,
                root,
            ),
            _reference(
                "MARKET_DATA_DATASET",
                ArtifactId(str(daily_dataset.dataset_id)),
                daily_dataset.content_hash,
                daily_dataset_path,
                root,
            ),
            _reference(
                "OPERATIONAL_UNIVERSE",
                ArtifactId(str(universe.universe_id)),
                universe.content_hash,
                universe_path,
                root,
            ),
            _reference(
                "SUPPLEMENTAL_RESEARCH_EVIDENCE",
                supplemental.bundle_id,
                supplemental.content_hash,
                supplemental_path,
                root,
            ),
            _reference(
                "TRADING_CALENDAR",
                calendar.artifact_id,
                calendar.content_hash,
                calendar_path,
                root,
            ),
            *configuration_reference,
        ),
        limitations=(
            "EXPLORATORY",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "NO_CALIBRATED_PROBABILITY",
            "TRADING_AUTHORITY_NOT_GRANTED",
        ),
    )
    manifest_path = publish_free_data_prepared_manifest(
        root=root / "prepared_free_data_inputs",
        manifest=prepared_manifest,
    )
    return FreeDataPreparedInputs(
        manifest=prepared_manifest,
        manifest_path=manifest_path,
        paths=paths,
        calendar=calendar,
    )


def _load_explicit_supplemental(
    *,
    path: Path,
    request: FreeDataPreparationRequest,
    universe: OperationalUniverseArtifact,
) -> SupplementalResearchEvidenceBundle:
    """Verify an explicitly configured bundle; never discover or substitute one."""

    bundle = load_verified_supplemental_research_evidence(path.resolve()).bundle
    if bundle.decision_time.value != request.decision_time.value:
        raise ValueError("supplemental evidence DecisionTime mismatch")
    if bundle.source_manifest.decision_time.value != request.decision_time.value:
        raise ValueError("supplemental SourceManifest DecisionTime mismatch")
    if any(
        item.retrieved_at.value > request.decision_time.value
        for item in bundle.source_manifest.source_artifacts
    ):
        raise ValueError("supplemental evidence is available after DecisionTime")
    universe_symbols = set(universe.symbols)
    if any(
        item.symbol not in universe_symbols
        for item in bundle.theme_memberships
    ):
        raise ValueError("supplemental theme membership exceeds Operational Universe")
    if bundle.data_eligibility is not DataEligibility.EXPLORATORY:
        raise ValueError("free supplemental evidence must remain EXPLORATORY")
    return bundle


def _validate_source_bindings(
    *,
    request: FreeDataPreparationRequest,
    history_source: VerifiedPublicSourceStageArtifact,
    provider_result: PublicCompositeProviderResult,
    full_source_manifest: SourceManifest,
    output_root: Path,
) -> None:
    if history_source.stage is not PublicSourceAcquisitionStage.HISTORY_SOURCE_FROZEN:
        raise ValueError("free-data preparation requires verified frozen history")
    if not history_source.root.resolve().is_relative_to(output_root):
        raise ValueError("history source stage must be under the operation root")
    if provider_result.profile_id != request.provider_profile_id:
        raise ValueError("ProviderResult profile does not match free-data request")
    if provider_result.decision_time != request.decision_time:
        raise ValueError("ProviderResult Decision Time mismatch")
    if full_source_manifest.provider_profile_id != request.provider_profile_id:
        raise ValueError("SourceManifest profile does not match free-data request")
    if (
        full_source_manifest.decision_time != request.decision_time
        or full_source_manifest.source_artifacts
        != provider_result.source_artifact_references
    ):
        raise ValueError("full SourceManifest does not bind ProviderResult")
    observed = {item.symbol for item in provider_result.bars}
    if not observed.issubset(request.symbols):
        raise ValueError("provider bars exceed requested instrument scope")
    history_ids = {item.source_artifact_id for item in history_source.batch.raw_payloads}
    if any(item.source_artifact_id not in history_ids for item in history_source.batch.bars):
        raise ValueError("history bars are not bound to frozen source bytes")


def _build_calendar(
    *,
    dataset: MarketDataDatasetArtifact,
    request: FreeDataPreparationRequest,
    provider_result: PublicCompositeProviderResult,
    source_manifest: SourceManifest,
) -> TradingCalendarArtifact:
    by_date: dict[date, datetime] = {}
    for bar in dataset.iter_bars():
        existing = by_date.get(bar.market_date)
        if existing is None or bar.event_end > existing:
            by_date[bar.market_date] = bar.event_end
    decision_date = request.decision_time.value.astimezone(_SHANGHAI).date()
    has_decision_quote = any(
        item.symbol in request.symbols
        and item.event_time is not None
        and item.event_time.astimezone(_SHANGHAI).date() == decision_date
        and item.available_time is not None
        and item.available_time.value <= request.decision_time.value
        for item in provider_result.quotes
    )
    has_trading_status = any(
        item.symbol in request.symbols
        and item.critical_fact is CriticalSourceFact.TRADING_STATUS
        and item.value == PublicTradingStatus.TRADING.value
        and item.available_time is not None
        and item.available_time.value <= request.decision_time.value
        for item in source_manifest.fields
    )
    if has_decision_quote and has_trading_status:
        by_date[decision_date] = datetime.combine(
            decision_date,
            datetime.min.time().replace(hour=15),
            tzinfo=_SHANGHAI,
        )
    sessions = tuple(
        TradingSession(
            trade_date=trade_date,
            session_close=event_end.astimezone(_SHANGHAI),
        )
        for trade_date, event_end in sorted(by_date.items())
    )
    return build_trading_calendar_artifact(
        source_dataset_id=dataset.dataset_id,
        market="A_SHARE",
        calendar_version="FREE_DATA_ARCHIVED_SESSIONS_V1",
        timezone_name="Asia/Shanghai",
        sessions=sessions,
    )


def _build_universe(
    *,
    request: FreeDataPreparationRequest,
    dataset: MarketDataDatasetArtifact,
    full_source_manifest: SourceManifest,
) -> OperationalUniverseArtifact:
    bars_by_symbol = {
        symbol: tuple(
            sorted(
                (
                    item
                    for item in dataset.iter_bars()
                    if item.symbol == symbol and item.timeframe is Timeframe.DAILY
                ),
                key=lambda item: item.event_end,
            )
        )
        for symbol in request.symbols
    }
    source_hash_by_id = {
        item.artifact_id: item.content_hash
        for item in full_source_manifest.source_artifacts
    }
    statuses = _current_statuses(
        full_source_manifest,
        decision_time=request.decision_time.value,
    )
    records: list[OperationalUniverseRecord] = []
    for instrument in request.instruments:
        symbol = instrument.symbol
        bars = bars_by_symbol[symbol]
        scoped = bars[-request.liquidity_lookback_sessions :]
        amounts = tuple(item.amount for item in scoped if item.amount is not None)
        status = statuses.get(symbol, {})
        listing = _listing_status(status.get(CriticalSourceFact.LISTING_STATUS))
        st_status = _st_status(status.get(CriticalSourceFact.ST_STATUS))
        suspension = _suspension_status(status.get(CriticalSourceFact.TRADING_STATUS))
        exclusions: list[str] = []
        if listing is not ListingStatus.LISTED:
            exclusions.append(f"LISTING_STATUS_{listing.value}")
        if st_status is not STStatus.NOT_ST:
            exclusions.append(f"ST_STATUS_{st_status.value}")
        if suspension is not SuspensionStatus.NOT_SUSPENDED:
            exclusions.append(f"SUSPENSION_STATUS_{suspension.value}")
        if len(bars) < request.minimum_history_sessions:
            exclusions.append("HISTORY_INSUFFICIENT")
        median_amount = Decimal(median(amounts)) if amounts else None
        if (
            median_amount is None
            or median_amount < request.minimum_median_daily_amount
        ):
            exclusions.append("LIQUIDITY_BELOW_MINIMUM")
        refs = {
            (item.source_artifact_id, item.source_content_hash) for item in bars
        }
        refs.update(
            (field.source_artifact_id, source_hash_by_id[field.source_artifact_id])
            for field in status.values()
            if field.source_artifact_id in source_hash_by_id
        )
        if not refs:
            raise ValueError("Universe record lacks source lineage")
        available_at = max(item.available_at for item in bars)
        source_artifact_id = bars[-1].source_artifact_id
        source_content_hash = bars[-1].source_content_hash
        included = not exclusions
        records.append(
            OperationalUniverseRecord(
                symbol=symbol,
                asset_type=instrument.asset_type,
                exchange=bars[-1].exchange,
                membership_source=request.membership_source,
                listing_status=listing,
                st_status=st_status,
                suspension_status=suspension,
                liquidity_evidence=OperationalLiquidityEvidence(
                    lookback_sessions=request.liquidity_lookback_sessions,
                    observed_sessions=len(scoped),
                    median_daily_amount=median_amount,
                    minimum_daily_amount=min(amounts) if amounts else None,
                    available_at=available_at,
                    source_artifact_id=source_artifact_id,
                    source_content_hash=source_content_hash,
                ),
                history_sessions_observed=len(bars),
                history_sessions_required=request.minimum_history_sessions,
                included=included,
                inclusion_reasons=("FREE_DATA_OPERATIONAL_ELIGIBLE",) if included else (),
                exclusion_reasons=tuple(sorted(exclusions)),
                source_artifact_references=tuple(
                    sorted(refs, key=lambda item: (str(item[0]), item[1]))
                ),
                data_eligibility=DataEligibility.EXPLORATORY,
            )
        )
    all_refs = tuple(
        sorted(
            {
                item
                for record in records
                for item in record.source_artifact_references
            },
            key=lambda item: (str(item[0]), item[1]),
        )
    )
    effective_at = normalize_canonical_datetime(
        request.decision_time.value.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
    )
    status_availability = tuple(
        field.available_time.value
        for fields in statuses.values()
        for field in fields.values()
        if field.available_time is not None
    )
    available_at = normalize_canonical_datetime(
        max(
            *(item.liquidity_evidence.available_at for item in records),
            *status_availability,
        )
    )
    return OperationalUniverseArtifact.create(
        decision_date=request.decision_time.value.astimezone(_SHANGHAI).date(),
        effective_at=effective_at,
        available_at=available_at,
        records=tuple(records),
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        data_eligibility=DataEligibility.EXPLORATORY,
        source_artifact_references=all_refs,
        limitations=(
            "EXPLORATORY",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "FREE_DATA_OPERATIONAL_UNIVERSE",
            "MEMBERSHIP_NOT_FORMAL_PIT",
        ),
    )


def _current_statuses(
    source_manifest: SourceManifest,
    *,
    decision_time: datetime,
) -> dict[str, dict[CriticalSourceFact, SourceManifestField]]:
    result: dict[str, dict[CriticalSourceFact, SourceManifestField]] = {}
    for item in source_manifest.fields:
        if (
            item.symbol is None
            or item.available_time is None
            or item.available_time.value > decision_time
            or item.critical_fact not in {
            CriticalSourceFact.LISTING_STATUS,
            CriticalSourceFact.ST_STATUS,
            CriticalSourceFact.TRADING_STATUS,
            }
        ):
            continue
        result.setdefault(item.symbol, {})[item.critical_fact] = item
    return result


def _listing_status(observation: SourceManifestField | None) -> ListingStatus:
    if observation is None or observation.value == PublicListingStatus.UNKNOWN.value:
        return ListingStatus.UNKNOWN
    if observation.value == PublicListingStatus.LISTED.value:
        return ListingStatus.LISTED
    if observation.value == PublicListingStatus.DELISTED.value:
        return ListingStatus.DELISTED
    return ListingStatus.UNKNOWN


def _st_status(observation: SourceManifestField | None) -> STStatus:
    if observation is None or observation.value == PublicSTStatus.UNKNOWN.value:
        return STStatus.UNKNOWN
    if observation.value == PublicSTStatus.NOT_ST.value:
        return STStatus.NOT_ST
    if observation.value == PublicSTStatus.ST.value:
        return STStatus.ST
    return STStatus.UNKNOWN


def _suspension_status(observation: SourceManifestField | None) -> SuspensionStatus:
    if observation is None or observation.value == PublicTradingStatus.UNKNOWN.value:
        return SuspensionStatus.UNKNOWN
    if observation.value == PublicTradingStatus.TRADING.value:
        return SuspensionStatus.NOT_SUSPENDED
    if observation.value == PublicTradingStatus.SUSPENDED.value:
        return SuspensionStatus.SUSPENDED
    return SuspensionStatus.UNKNOWN


def _build_supplemental(
    *,
    request: FreeDataPreparationRequest,
    dataset: MarketDataDatasetArtifact,
    universe: OperationalUniverseArtifact,
    full_source_manifest: SourceManifest,
) -> SupplementalResearchEvidenceBundle:
    dataset_id = ArtifactId(str(dataset.dataset_id))
    dataset_reference = SourceArtifactReference(
        artifact_id=dataset_id,
        provider_id=ProviderId("authority-canonical-market-data"),
        retrieved_at=RetrievedAt(request.created_at),
        content_hash=dataset.content_hash,
        locator=f"artifact://canonical-market-data/{dataset.dataset_id}",
    )
    supplemental_manifest = SourceManifest(
        provider_profile_id=request.provider_profile_id,
        decision_time=request.decision_time,
        source_artifacts=(*full_source_manifest.source_artifacts, dataset_reference),
        fields=full_source_manifest.fields,
        source_conflicts=full_source_manifest.source_conflicts,
        limitations=tuple(
            dict.fromkeys(
                (
                    *full_source_manifest.limitations,
                    "CANONICAL_MARKET_DATA_DERIVATION_BOUND",
                    "FORMAL_PIT_NOT_ESTABLISHED",
                )
            )
        ),
        data_eligibility=DataEligibility.EXPLORATORY,
        schema_version=full_source_manifest.schema_version,
    )
    included = set(universe.symbols)
    bars_by_symbol = {
        symbol: tuple(
            item
            for item in dataset.iter_bars()
            if item.symbol == symbol and item.timeframe is Timeframe.DAILY
        )
        for symbol in universe.symbols
    }
    latest_returns: list[float] = []
    amount_changes: list[float] = []
    symbol_observations: list[SymbolResearchObservation] = []
    universe_by_symbol = {item.symbol: item for item in universe.records}
    for symbol in universe.symbols:
        bars = bars_by_symbol[symbol]
        latest_return = _latest_return(bars)
        amount_change = _latest_amount_change(bars)
        if latest_return is not None:
            latest_returns.append(latest_return)
        if amount_change is not None:
            amount_changes.append(amount_change)
        record = universe_by_symbol[symbol]
        symbol_observations.append(
            SymbolResearchObservation(
                symbol=symbol,
                available_at=AvailabilityTime(dataset.available_at),
                source_artifact_id=dataset_id,
                symbol_relative_strength=latest_return,
                symbol_amount_expansion=amount_change,
                theme_participation_contribution=None,
                leader_correlation=None,
                leader_lag=None,
                rank_persistence=None,
                amount_persistence=None,
                liquidity_eligible=record.included,
                history_complete=(
                    record.history_sessions_observed
                    >= record.history_sessions_required
                ),
                status_known=(
                    record.listing_status is not ListingStatus.UNKNOWN
                    and record.st_status is not STStatus.UNKNOWN
                    and record.suspension_status is not SuspensionStatus.UNKNOWN
                ),
                source_feature_ids=(),
                reason_codes=(
                    "FREE_DATA_SYMBOL_OBSERVABLE_PROXY",
                    "THEME_AND_LEADER_EVIDENCE_MISSING",
                ),
            )
        )
    market_direction = _mean(latest_returns)
    amount_change = _mean(amount_changes)
    breadth = (
        sum(1 for item in latest_returns if item > 0) / len(latest_returns)
        if latest_returns
        else None
    )
    market_observation = MarketObservation(
        available_at=AvailabilityTime(dataset.available_at),
        source_artifact_id=dataset_id,
        market_direction_return=market_direction,
        market_intraday_range_to_cutoff=None,
        market_amount_change_same_cutoff=amount_change,
        candidate_breadth_at_cutoff=breadth,
        limit_structure_score=None,
        coverage=(len(latest_returns) / len(included) if included else 0.0),
        reason_codes=(
            "EQUAL_WEIGHTED_OPERATIONAL_UNIVERSE_PROXY",
            "INDEX_PROXY_NOT_PROVIDED",
            "INTRADAY_MARKET_EVIDENCE_MISSING",
            "LIMIT_STRUCTURE_EVIDENCE_MISSING",
        ),
    )
    stock_daily_bars = tuple(
        ResearchDailyBar(
            symbol=bar.symbol,
            session_date=bar.market_date,
            available_at=AvailabilityTime(bar.available_at),
            source_artifact_id=dataset_id,
            close=float(bar.close),
            amount=float(bar.amount),
        )
        for bar in dataset.iter_bars()
        if (
            bar.symbol in included
            and bar.timeframe is Timeframe.DAILY
            and bar.amount is not None
        )
    )
    missing = tuple(
        sorted(
            (
                *(
                    MissingEvidence(
                        evidence_kind="THEME_MEMBERSHIP",
                        key=symbol,
                        reason_codes=(
                            "FREE_DATA_THEME_MEMBERSHIP_NOT_PROVIDED",
                            "FORMAL_THEME_PIT_NOT_ESTABLISHED",
                        ),
                    )
                    for symbol in universe.symbols
                ),
                MissingEvidence(
                    evidence_kind="CAPITAL_OBSERVATION",
                    key="ALL_THEMES",
                    reason_codes=("OBSERVABLE_THEME_CAPITAL_PROXY_NOT_PROVIDED",),
                ),
                MissingEvidence(
                    evidence_kind="ETF_THEME_MAPPING",
                    key="ALL_THEMES",
                    reason_codes=("ETF_THEME_MAPPING_NOT_PROVIDED",),
                ),
                MissingEvidence(
                    evidence_kind="THEME_OBSERVATION",
                    key="ALL_THEMES",
                    reason_codes=("THEME_COMPONENT_EVIDENCE_NOT_PROVIDED",),
                ),
            ),
            key=lambda item: (item.evidence_kind, item.key),
        )
    )
    return SupplementalResearchEvidenceBundle(
        source_manifest=supplemental_manifest,
        decision_time=request.decision_time,
        market_observation=market_observation,
        theme_observations=(),
        capital_observations=(),
        symbol_observations=tuple(symbol_observations),
        theme_memberships=(),
        etf_theme_mappings=(),
        etf_observations=(),
        stock_daily_bars=stock_daily_bars,
        missing_evidence=missing,
        reason_codes=(
            "EXPLORATORY",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "SUPPLEMENTAL_EVIDENCE_INCOMPLETE",
            "TRADING_AUTHORITY_NOT_GRANTED",
        ),
        created_at=request.created_at,
        data_eligibility=DataEligibility.EXPLORATORY,
    )


def _latest_return(bars: tuple[CanonicalMarketBar, ...]) -> float | None:
    if len(bars) < 2 or bars[-2].close == 0:
        return None
    return float(bars[-1].close / bars[-2].close - Decimal("1"))


def _latest_amount_change(bars: tuple[CanonicalMarketBar, ...]) -> float | None:
    if len(bars) < 2 or bars[-2].amount in {None, Decimal("0")}:
        return None
    if bars[-1].amount is None:
        return None
    return float(bars[-1].amount / bars[-2].amount - Decimal("1"))


def _mean(values: Iterable[float]) -> float | None:
    materialized = tuple(values)
    return sum(materialized) / len(materialized) if materialized else None


def _reference(
    kind: str,
    artifact_id: ArtifactId,
    content_hash: str,
    path: Path,
    root: Path,
) -> PreparedArtifactReference:
    relative = path.resolve().relative_to(root).as_posix()
    return PreparedArtifactReference(
        kind=kind,
        artifact_id=artifact_id,
        content_hash=content_hash,
        relative_locator=relative,
    )


__all__ = ["prepare_free_data_inputs"]
