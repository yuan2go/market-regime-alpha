"""Free-data T+1 settlement and evaluation on the existing Research Shadow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Protocol
from zoneinfo import ZoneInfo

from market_regime_alpha.application.controlled_operation.evidence_package import (
    ControlledOperationalEvidencePackage,
    load_controlled_operation_package,
)
from market_regime_alpha.application.controlled_operation.longitudinal_index import (
    resolve_artifact_root_locator,
)
from market_regime_alpha.application.controlled_operation.outcome_evidence import (
    TradeHorizonDefinition,
    build_trade_horizon_outcome_evidence,
    load_trade_horizon_outcome_evidence,
    publish_trade_horizon_outcome_evidence,
)
from market_regime_alpha.application.controlled_operation.outcome_source_archive import (
    RECORDED_OUTCOME_BARS_SOURCE_KIND,
    OutcomeRawSourcePayload,
    OutcomeSettlementSourceArchive,
    encode_recorded_outcome_bars,
    load_outcome_settlement_source_archive,
    publish_outcome_settlement_source_archive,
)
from market_regime_alpha.application.controlled_operation.postgres_prospective_outcome import (
    PostgresProspectiveOutcomeRepository,
)
from market_regime_alpha.application.controlled_operation.postgres_longitudinal_index import (
    PostgresLongitudinalOperationalIndex,
)
from market_regime_alpha.application.controlled_operation.prospective_outcome import (
    SettlementSessionStatus,
)
from market_regime_alpha.application.continuous_research.postgres_daily_alpha import (
    PostgresDailyAlphaOwnerResolver,
    PostgresDailyAlphaPredictionAuthority,
)
from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.research_evaluation.targets import (
    engineering_multi_horizon_protocol,
)
from market_regime_alpha.application.research_validation.factor_research import (
    analyze_factor_deduplication,
    build_factor_research_catalog,
    publish_factor_research_artifact,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.application.research_validation.path_calibration import (
    PostgresPathForecastCalibrationOperator,
)
from market_regime_alpha.application.shadow_research.attestation import (
    ClockMode,
    RuntimeOrigin,
)
from market_regime_alpha.application.shadow_research.operations import (
    ResearchShadowOperations,
)
from market_regime_alpha.application.shadow_research.postgres_repository import (
    PostgresShadowResearchRepository,
)
from market_regime_alpha.application.state_system.postgres_repository import (
    PostgresStateSystemRepository,
)
from market_regime_alpha.core.identity import ArtifactId, ProviderId
from market_regime_alpha.core.time import (
    AvailabilityTime,
    DecisionTime,
    RetrievedAt,
)
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.source_manifest import (
    CriticalSourceFact,
    SourceArtifactReference,
    SourceAuthorityKind,
    SourceFieldFinality,
    SourceFieldQualityStatus,
    SourceManifest,
    SourceManifestField,
)
from market_regime_alpha.data_sources.a_share_bars import (
    AShareBarProvider,
    AShareDataError,
    BaoStockADataProvider,
)
from market_regime_alpha.features.materialization_v2 import (
    load_verified_feature_bundle_v2,
)
from market_regime_alpha.features.postgres_materialization_run import (
    PostgresFeatureMaterializationRunRepository,
)
from market_regime_alpha.features.v2_contracts import FeatureMaterializationReceipt
from market_regime_alpha.features.operational_overlay import (
    load_static_universe_feature_bundle,
)
from market_regime_alpha.forecasting.artifact import (
    load_verified_path_forecast,
)
from market_regime_alpha.market_data.adjustment import PriceAdjustmentPolicy
from market_regime_alpha.market_data.artifacts import (
    VerifiedMarketDataDataset,
    load_verified_market_data_dataset,
    publish_market_data_dataset,
)
from market_regime_alpha.market_data.contracts import (
    AdjustmentMode,
    AssetType,
    CanonicalMarketBar,
    Exchange,
    PriceLimitState,
    Timeframe,
    TradingStatus,
    VolumeUnit,
)
from market_regime_alpha.market_data.dataset import (
    FormalPitStatus,
    MarketDataDatasetArtifact,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.research.state_system.pool import DynamicStockPoolVersion
from market_regime_alpha.signals.v3 import load_verified_signal_run_v3


_SHANGHAI = ZoneInfo("Asia/Shanghai")
_PLACEHOLDER_HASH = "sha256:" + "0" * 64


@dataclass(frozen=True, slots=True)
class FreeOutcomeAcquisition:
    dataset: VerifiedMarketDataDataset
    source_archive: OutcomeSettlementSourceArchive
    source_archive_path: Path
    dataset_path: Path
    provider_id: str
    minute_timeframe: Timeframe
    retrieved_at: datetime


class FreeOutcomeDatasetBuilder:
    """Acquire post-close BaoStock 5m OHLC evidence for current or missed days."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime],
        historical_provider: AShareBarProvider | None = None,
    ) -> None:
        self._clock = clock
        self._historical = historical_provider or BaoStockADataProvider()

    def acquire(
        self,
        *,
        symbols: tuple[str, ...],
        next_session_date: date,
        output_root: Path,
    ) -> FreeOutcomeAcquisition:
        retrieved_at = self._clock().astimezone(UTC).replace(microsecond=0)
        if not symbols or symbols != tuple(sorted(set(symbols))):
            raise ValueError("Free Outcome symbols must be non-empty, unique and sorted")
        local_retrieved_at = retrieved_at.astimezone(_SHANGHAI)
        is_same_session = local_retrieved_at.date() == next_session_date
        if is_same_session and local_retrieved_at.time() < time(15):
            raise ValueError(
                "Current-session Free Outcome acquisition requires the 15:00 close"
            )
        provider = self._historical
        timeframe = Timeframe.MINUTE_5
        frames = []
        missing_symbols: set[str] = set()
        for symbol in symbols:
            try:
                frame = provider.minute_bars(
                    symbol,
                    freq="5min",
                    start_date=next_session_date.isoformat(),
                    end_date=next_session_date.isoformat(),
                )
            except AShareDataError as exc:
                if not _is_explicit_no_data_error(exc):
                    raise
                missing_symbols.add(symbol)
                continue
            scoped = frame[
                frame["timestamp"].map(
                    lambda value: _timestamp(value).astimezone(_SHANGHAI).date()
                    == next_session_date
                )
            ]
            if scoped.empty:
                missing_symbols.add(symbol)
                continue
            frames.append((symbol, scoped))
        if not frames:
            raise ValueError(
                "Free Outcome provider returned no bars for any requested symbol"
            )

        source_id = ArtifactId(
            f"free-outcome-source-{next_session_date.isoformat()}-"
            f"{sha256('|'.join(symbols).encode()).hexdigest()[:16]}-"
            f"{sha256(retrieved_at.isoformat().encode()).hexdigest()[:16]}"
        )
        provisional = _canonical_bars(
            frames=tuple(frames),
            market_date=next_session_date,
            timeframe=timeframe,
            retrieved_at=retrieved_at,
            source_id=source_id,
            source_hash=_PLACEHOLDER_HASH,
            timestamp_is_interval_end=True,
        )
        raw_payload = encode_recorded_outcome_bars(provisional)
        source_hash = "sha256:" + sha256(raw_payload).hexdigest()
        bars = _canonical_bars(
            frames=tuple(frames),
            market_date=next_session_date,
            timeframe=timeframe,
            retrieved_at=retrieved_at,
            source_id=source_id,
            source_hash=source_hash,
            timestamp_is_interval_end=True,
        )
        if encode_recorded_outcome_bars(bars) != raw_payload:
            raise ValueError("Free Outcome recorded payload is not hash-stable")
        provider_id = "BAOSTOCK_HISTORICAL_5MIN_FREE_EXPLORATORY"
        provider_reference_id = ProviderId(provider_id.lower())
        manifest_fields = tuple(
            SourceManifestField(
                field_id="outcome_bars.MINUTE_5",
                symbol=symbol,
                critical_fact=CriticalSourceFact.PRICE,
                provider_id=provider_reference_id,
                source_artifact_id=source_id,
                event_time=datetime.combine(
                    next_session_date,
                    time(15),
                    tzinfo=_SHANGHAI,
                ).astimezone(UTC),
                available_time=(
                    None
                    if symbol in missing_symbols
                    else AvailabilityTime(retrieved_at)
                ),
                retrieved_time=RetrievedAt(retrieved_at),
                decision_time=DecisionTime(retrieved_at),
                unit="OHLCV_5MIN",
                adjustment_basis="RAW_UNADJUSTED",
                finality=SourceFieldFinality.UNKNOWN,
                data_eligibility=DataEligibility.EXPLORATORY,
                quality_status=(
                    SourceFieldQualityStatus.INSUFFICIENT
                    if symbol in missing_symbols
                    else SourceFieldQualityStatus.COMPLETE
                ),
                reason_codes=(
                    ("AVAILABILITY_UNKNOWN", "OUTCOME_BARS_MISSING")
                    if symbol in missing_symbols
                    else ()
                ),
                schema_version=SourceManifestField.SCHEMA_V2,
                authority_kind=SourceAuthorityKind.PROVIDER,
                value=("MISSING" if symbol in missing_symbols else "OBSERVED"),
            )
            for symbol in symbols
        )
        manifest = SourceManifest(
            provider_profile_id=provider_id,
            decision_time=DecisionTime(retrieved_at),
            source_artifacts=(
                SourceArtifactReference(
                    artifact_id=source_id,
                    provider_id=provider_reference_id,
                    retrieved_at=RetrievedAt(retrieved_at),
                    content_hash=source_hash,
                    locator=f"free-data://outcome/{next_session_date.isoformat()}",
                ),
            ),
            fields=manifest_fields,
            source_conflicts=(),
            limitations=tuple(
                sorted(
                    {
                        "BACKFILL_NOT_POINT_IN_TIME",
                        "FREE_DATA_EXPLORATORY",
                        "PROVIDER_NOT_QUALIFIED",
                        "SOURCE_TRANSPORT_REENCODED_AS_CANONICAL_BARS",
                        *(
                            ("PARTIAL_SYMBOL_COVERAGE_EXPLICIT",)
                            if missing_symbols
                            else ()
                        ),
                    }
                )
            ),
            data_eligibility=DataEligibility.EXPLORATORY,
            schema_version=SourceManifest.SCHEMA_V2,
        )
        adjustment = PriceAdjustmentPolicy.create(
            policy_version="free-outcome-raw-unadjusted-v1",
            mode=AdjustmentMode.RAW,
            factors=(),
            limitations=("FREE_DATA_FACTOR_NOT_USED",),
        )
        artifact = MarketDataDatasetArtifact.create(
            decision_time=retrieved_at,
            created_at=retrieved_at,
            bars=bars,
            expected_symbols=symbols,
            expected_timeframes=(Timeframe.DAILY, timeframe),
            adjustment_policy=adjustment,
            source_manifest_references=(
                (manifest.source_manifest_id, manifest.content_hash),
            ),
            data_eligibility=DataEligibility.EXPLORATORY,
            formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
            limitations=tuple(
                sorted(
                    {
                        "ALPHA_VALIDATED_FALSE",
                        "FORMAL_OOS_FALSE",
                        "FORMAL_PIT_FALSE",
                        "FREE_DATA_EXPLORATORY",
                        "PRODUCTION_AUTHORIZED_FALSE",
                        *(
                            ("PARTIAL_SYMBOL_COVERAGE_EXPLICIT",)
                            if missing_symbols
                            else ()
                        ),
                    }
                )
            ),
        )
        dataset_path = publish_market_data_dataset(
            root=output_root / "outcome-datasets",
            artifact=artifact,
        )
        raw = OutcomeRawSourcePayload(
            source_artifact_id=source_id,
            source_kind=RECORDED_OUTCOME_BARS_SOURCE_KIND,
            media_type="application/json",
            payload=raw_payload,
        )
        archive = OutcomeSettlementSourceArchive.create(
            source_manifest=manifest,
            next_session_date=next_session_date,
            raw_payloads=(raw,),
            created_at=retrieved_at,
            limitations=(
                "FACTUAL_OUTCOME_SOURCE_ONLY",
                "FREE_DATA_EXPLORATORY",
                "PROVIDER_NOT_QUALIFIED",
            ),
        )
        archive_path = publish_outcome_settlement_source_archive(
            root=output_root / "outcome-source-archives",
            artifact=archive,
            raw_payloads=(raw,),
        )
        return FreeOutcomeAcquisition(
            dataset=load_verified_market_data_dataset(dataset_path),
            source_archive=archive,
            source_archive_path=archive_path,
            dataset_path=dataset_path,
            provider_id=provider_id,
            minute_timeframe=timeframe,
            retrieved_at=retrieved_at,
        )


class FreeDataSettlementOperator:
    """Resolve PostgreSQL identities, acquire Outcome data, settle and enrich."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        clock: Callable[[], datetime],
        acquisition: FreeOutcomeDatasetBuilder | None = None,
    ) -> None:
        self._factory = factory
        self._clock = clock
        self._shadow = PostgresShadowResearchRepository(factory)
        self._state = PostgresStateSystemRepository(factory, apply_migrations=False)
        self._operations = ResearchShadowOperations(factory)
        self._outcomes = PostgresProspectiveOutcomeRepository(
            factory,
            apply_migrations=False,
        )
        self._validation = PostgresResearchValidationRepository(
            factory,
            apply_migrations=False,
        )
        self._longitudinal = PostgresLongitudinalOperationalIndex(factory)
        self._feature_runs = PostgresFeatureMaterializationRunRepository(factory)
        self._acquisition = acquisition or FreeOutcomeDatasetBuilder(clock=clock)

    def settle_day(
        self,
        *,
        trading_date: date,
        next_session_date: date,
        artifact_root: Path,
        decision_id: ArtifactId | None = None,
        prediction_snapshot_reference: RuntimeArtifactReference | None = None,
    ) -> dict[str, Any]:
        session, decision = self._pending_decision(
            trading_date,
            decision_id=decision_id,
        )
        package, run_root = _resolve_operation_package(
            artifact_root,
            decision.controlled_operation.artifact_id,
            locator=self._longitudinal,
        )
        candidate_set = self._state.get_runtime_candidate(
            run_id=decision.run_id,
            tick_id=decision.tick_id,
        )
        symbols = tuple(sorted(item.symbol for item in candidate_set.selected))
        if not symbols:
            raise ValueError("settle-day requires selected Candidates")
        settlement_root = artifact_root / "free-data-settlement"
        try:
            existing_factual = self._outcomes.get_for_decision(decision.decision_id)
        except KeyError:
            existing_factual = None
        recovered = existing_factual is not None
        prediction_snapshot = (
            None
            if existing_factual is not None
            and existing_factual.schema_version == "prospective-shadow-outcome/v1"
            else PostgresDailyAlphaPredictionAuthority(
                self._factory,
                resolver=PostgresDailyAlphaOwnerResolver(
                    self._factory,
                    artifact_root=artifact_root,
                ),
            ).get_for_tick(run_id=decision.run_id, tick_id=decision.tick_id)
        )
        if prediction_snapshot is not None:
            if (
                prediction_snapshot.target_session_date != next_session_date
                or prediction_snapshot.trading_date != trading_date
                or (
                    prediction_snapshot_reference is not None
                    and prediction_snapshot.reference
                    != prediction_snapshot_reference
                )
            ):
                raise ValueError("settle-day Daily prediction target lineage drifted")
        if existing_factual is None:
            acquisition = self._acquisition.acquire(
                symbols=symbols,
                next_session_date=next_session_date,
                output_root=settlement_root,
            )
            factual_evidence = None
            evidence_path = None
        else:
            if existing_factual.next_session_date != next_session_date:
                raise ValueError("settle-day next session conflicts with durable Outcome")
            acquisition, factual_evidence, evidence_path = _recover_acquisition(
                settlement_root=settlement_root,
                factual=existing_factual,
            )
        decision_dataset = load_verified_market_data_dataset(
            _reference_path(package, run_root, "DAILY_DATASET")
        )
        signal = load_verified_signal_run_v3(
            _reference_path(package, run_root, "SIGNAL_V3")
        )
        forecasts = tuple(
            load_verified_path_forecast(run_root / reference.locator)
            for reference in package.evidence_references
            if reference.reference_type == "PATH_FORECAST"
        )
        if factual_evidence is None:
            factual_evidence = build_trade_horizon_outcome_evidence(
                operation_package=package,
                candidate_set=candidate_set,
                signal=signal,
                forecasts=forecasts,
                decision_dataset=decision_dataset,
                settlement_dataset=acquisition.dataset,
                next_session_date=next_session_date,
                horizon=TradeHorizonDefinition.create(include_session_close=True),
                created_at=acquisition.retrieved_at,
            )
            evidence_path = publish_trade_horizon_outcome_evidence(
                root=settlement_root / "outcome-evidence",
                artifact=factual_evidence,
            )
        assert evidence_path is not None
        target_protocol = engineering_multi_horizon_protocol()
        settled = self._operations.settle(
            decision_id=decision.decision_id,
            prediction_snapshot=prediction_snapshot,
            source_archive=acquisition.source_archive,
            settlement_dataset=acquisition.dataset,
            factual_evidence=factual_evidence,
            next_session_date=next_session_date,
            session_status=SettlementSessionStatus.TRADING_DAY,
            target_protocol=target_protocol,
            expected_shadow_version=session.version,
            created_at=acquisition.retrieved_at,
            code_revision=package.code_revision,
            clock_mode=ClockMode.UNKNOWN,
            runtime_origin=RuntimeOrigin.UNKNOWN,
        )
        pool_payload = self._state.read_pool(decision.dynamic_pool.artifact_id) if decision.dynamic_pool is not None else None
        if pool_payload is None:
            raise ValueError("settle-day requires frozen Dynamic Pool")
        pool = DynamicStockPoolVersion.from_canonical_dict(pool_payload)
        static = load_static_universe_feature_bundle(
            _reference_path(package, run_root, "STATIC_FEATURE_BUNDLE")
        )
        feature_path = _feature_bundle_path(
            run_root / "static-features",
            bundle_id=static.feature_bundle_id,
            bundle_hash=static.feature_bundle_hash,
            receipt_id=static.run_receipt_id,
            receipt_hash=static.run_receipt_hash,
            receipts=self._feature_runs.receipts(),
        )
        feature_bundle = load_verified_feature_bundle_v2(
            feature_path,
            artifact_root=run_root / "static-features" / "feature-artifacts",
        )
        panel, enrichment, panel_path, enrichment_path = self._operations.build_enriched_evaluation(
            decision_id=decision.decision_id,
            targeted_outcome_id=settled.targeted_outcome_v2.settlement_id,
            target_protocol_id=settled.targeted_outcome_v2.target_protocol_id,
            dynamic_pool=pool,
            candidate_set=candidate_set,
            state_policy_references=decision.state_policy_references,
            dataset=decision_dataset,
            feature_bundle=feature_bundle,
            feature_wrapper=static,
            signal_run=signal.artifact,
            forecasts=tuple(item.artifact.forecast for item in forecasts),
            state_sources=(),
            artifact_root=artifact_root / "free-data-settlement" / "research-evaluation",
            created_at=acquisition.retrieved_at,
        )
        catalog = build_factor_research_catalog(
            enrichment=enrichment,
            created_at=acquisition.retrieved_at,
        )
        deduplication = analyze_factor_deduplication(
            enrichment=enrichment,
            catalog=catalog,
            analyzed_at=acquisition.retrieved_at,
        )
        factor_root = (
            artifact_root
            / "free-data-settlement"
            / "research-evaluation"
            / "factor-research"
        )
        catalog_path = publish_factor_research_artifact(
            root=factor_root,
            artifact=catalog,
        )
        deduplication_path = publish_factor_research_artifact(
            root=factor_root,
            artifact=deduplication,
        )
        self._validation.record_factor_catalog(catalog)
        self._validation.record(
            artifact_id=deduplication.report_id,
            artifact_hash=deduplication.report_hash,
            artifact_kind="FACTOR_DEDUPLICATION_REPORT",
            evidence_authority="EXPLORATORY",
            payload=deduplication.identity_payload(),
            created_at=deduplication.analyzed_at,
        )
        calibration_engineering = PostgresPathForecastCalibrationOperator(
            self._factory,
            repository=self._validation,
        ).run(
            target_protocol=target_protocol,
            through_date=trading_date,
            created_at=acquisition.retrieved_at,
        )
        return {
            "operation": "SETTLE_DAY",
            "status": settled.session.status.value,
            "research_shadow_session_id": str(settled.session.command.session_id),
            "research_shadow_decision_id": str(decision.decision_id),
            "prediction_snapshot_id": (
                None
                if settled.factual_outcome_v1.prediction_snapshot is None
                else str(
                    settled.factual_outcome_v1.prediction_snapshot.artifact_id
                )
            ),
            "prediction_snapshot_hash": (
                None
                if settled.factual_outcome_v1.prediction_snapshot is None
                else settled.factual_outcome_v1.prediction_snapshot.content_hash
            ),
            "factual_outcome_id": str(settled.factual_outcome_v1.settlement_id),
            "targeted_outcome_id": str(settled.targeted_outcome_v2.settlement_id),
            "target_protocol_id": str(settled.targeted_outcome_v2.target_protocol_id),
            "panel_id": str(panel.panel_id),
            "panel_enrichment_id": str(enrichment.enrichment_id),
            "factor_catalog_id": str(catalog.catalog_id),
            "factor_deduplication_report_id": str(deduplication.report_id),
            "calibration_engineering": calibration_engineering,
            "outcome_source_archive": str(acquisition.source_archive_path),
            "outcome_dataset": str(acquisition.dataset_path),
            "outcome_evidence": str(evidence_path),
            "panel_artifact": str(panel_path),
            "panel_enrichment_artifact": str(enrichment_path),
            "factor_catalog_artifact": str(catalog_path),
            "factor_deduplication_artifact": str(deduplication_path),
            "outcome_provider": acquisition.provider_id,
            "outcome_minute_timeframe": acquisition.minute_timeframe.value,
            "missing_outcome_symbol_timeframes": list(
                acquisition.dataset.artifact.coverage.missing_symbol_timeframes
            ),
            "recovered_from_postgres_authority": recovered,
            "formal_pit": False,
            "formal_oos": False,
            "prospective_proven": False,
            "production_authorized": False,
            "broker_invoked": False,
            "order_created": False,
            "real_fill_created": False,
        }

    def _pending_decision(
        self,
        trading_date: date,
        *,
        decision_id: ArtifactId | None,
    ) -> tuple[Any, Any]:
        with self._factory.connection(read_only=True) as connection:
            if decision_id is None:
                rows = connection.execute(
                    """
                    SELECT session_id, decision_id
                    FROM shadow_research_session
                    WHERE trading_date = %s
                      AND status IN ('OUTCOME_PENDING', 'SETTLED')
                    ORDER BY created_at DESC, session_id DESC
                    """,
                    (trading_date,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT session_id, decision_id
                    FROM shadow_research_session
                    WHERE trading_date = %s AND decision_id = %s
                      AND status IN ('OUTCOME_PENDING', 'SETTLED')
                    """,
                    (trading_date, str(decision_id)),
                ).fetchall()
        if len(rows) != 1 or rows[0][1] is None:
            raise ValueError("settle-day requires exactly one pending/settled Research Shadow Decision")
        return (
            self._shadow.get_session(ArtifactId(str(rows[0][0]))),
            self._shadow.get_decision(ArtifactId(str(rows[0][1]))),
        )


def _canonical_bars(
    *,
    frames: tuple[tuple[str, Any], ...],
    market_date: date,
    timeframe: Timeframe,
    retrieved_at: datetime,
    source_id: ArtifactId,
    source_hash: str,
    timestamp_is_interval_end: bool,
) -> tuple[CanonicalMarketBar, ...]:
    minute_bars = []
    daily_bars = []
    duration = timeframe.duration
    assert duration is not None
    for symbol, frame in frames:
        rows = [
            row
            for row in frame.sort_values("timestamp").to_dict(orient="records")
            if _is_continuous_session_stamp(
                _timestamp(row["timestamp"]).astimezone(_SHANGHAI).time(),
                timestamp_is_interval_end=timestamp_is_interval_end,
            )
        ]
        if not rows:
            raise ValueError(f"Free Outcome provider returned no continuous-session bars for {symbol}")
        for row in rows:
            observed = _timestamp(row["timestamp"]).astimezone(_SHANGHAI)
            event_start = observed - duration if timestamp_is_interval_end else observed
            event_end = observed if timestamp_is_interval_end else observed + duration
            minute_bars.append(
                _bar(
                    symbol=symbol,
                    timeframe=timeframe,
                    market_date=market_date,
                    event_start=event_start,
                    event_end=event_end,
                    available_at=retrieved_at,
                    open_price=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row.get("volume", 0),
                    amount=row.get("amount"),
                    source_id=source_id,
                    source_hash=source_hash,
                )
            )
        daily_bars.append(
            _bar(
                symbol=symbol,
                timeframe=Timeframe.DAILY,
                market_date=market_date,
                event_start=datetime.combine(market_date, time(9, 30), tzinfo=_SHANGHAI),
                event_end=datetime.combine(market_date, time(15), tzinfo=_SHANGHAI),
                available_at=retrieved_at,
                open_price=rows[0]["open"],
                high=max(Decimal(str(item["high"])) for item in rows),
                low=min(Decimal(str(item["low"])) for item in rows),
                close=rows[-1]["close"],
                volume=sum((Decimal(str(item.get("volume", 0))) for item in rows), Decimal("0")),
                amount=sum((Decimal(str(item.get("amount", 0) or 0)) for item in rows), Decimal("0")),
                source_id=source_id,
                source_hash=source_hash,
            )
        )
    return tuple(sorted((*minute_bars, *daily_bars), key=lambda item: (item.symbol, item.timeframe.value, item.event_start)))


def _is_explicit_no_data_error(error: AShareDataError) -> bool:
    return str(error) in {
        "data source returned no rows",
        "normalized minute bars are empty",
    }


def _is_continuous_session_stamp(
    observed_time: time,
    *,
    timestamp_is_interval_end: bool,
) -> bool:
    if timestamp_is_interval_end:
        return time(9, 30) < observed_time <= time(11, 30) or time(13) < observed_time <= time(15)
    return time(9, 30) <= observed_time < time(11, 30) or time(13) <= observed_time < time(15)


def _bar(**values: Any) -> CanonicalMarketBar:
    symbol = str(values["symbol"])
    return CanonicalMarketBar.create(
        symbol=symbol,
        exchange=Exchange(symbol[-2:]),
        asset_type=AssetType.A_SHARE,
        timeframe=values["timeframe"],
        market_date=values["market_date"],
        event_start=values["event_start"].astimezone(UTC),
        event_end=values["event_end"].astimezone(UTC),
        available_at=values["available_at"],
        open=Decimal(str(values["open_price"])),
        high=Decimal(str(values["high"])),
        low=Decimal(str(values["low"])),
        close=Decimal(str(values["close"])),
        previous_close=None,
        volume=Decimal(str(values["volume"])),
        volume_unit=VolumeUnit.SHARES,
        amount=None if values["amount"] is None else Decimal(str(values["amount"])),
        turnover_rate=None,
        adjustment_mode=AdjustmentMode.RAW,
        adjustment_factor=Decimal("1"),
        trading_status=TradingStatus.TRADING,
        price_limit_state=PriceLimitState.UNKNOWN,
        source_artifact_id=values["source_id"],
        source_content_hash=values["source_hash"],
    )


class _PackageLocator(Protocol):
    def get_package_locator(self, package_id: ArtifactId) -> Any: ...


def _resolve_operation_package(
    artifact_root: Path,
    controlled_operation_id: ArtifactId,
    *,
    locator: _PackageLocator,
) -> tuple[ControlledOperationalEvidencePackage, Path]:
    try:
        record = locator.get_package_locator(controlled_operation_id)
    except KeyError as exc:
        raise ValueError(
            "settle-day PostgreSQL locator has no Controlled package"
        ) from exc
    package_path = resolve_artifact_root_locator(
        artifact_root=artifact_root,
        locator=str(record.package_locator),
    )
    package = load_controlled_operation_package(package_path)
    if (
        package.package_id != controlled_operation_id
        or package.content_hash != record.package_hash
        or package.command.run_id != record.operation_run_id
    ):
        raise ValueError("PostgreSQL locator does not bind Controlled package identity")
    return package, package_path.parent.parent


def _feature_bundle_path(
    root: Path,
    *,
    bundle_id: ArtifactId,
    bundle_hash: str,
    receipt_id: ArtifactId,
    receipt_hash: str,
    receipts: tuple[FeatureMaterializationReceipt, ...],
) -> Path:
    matches = tuple(
        item
        for item in receipts
        if item.receipt_id == receipt_id
        and item.content_hash == receipt_hash
        and item.bundle_id == bundle_id
        and item.bundle_hash == bundle_hash
    )
    if len(matches) != 1:
        raise ValueError("PostgreSQL Feature receipt locator is missing or ambiguous")
    authority_root = root.resolve()
    path = (authority_root / matches[0].bundle_locator).resolve()
    if authority_root not in path.parents:
        raise ValueError("Feature receipt locator escapes its Artifact root")
    return path


def _recover_acquisition(
    *,
    settlement_root: Path,
    factual: Any,
) -> tuple[FreeOutcomeAcquisition, Any, Path]:
    archive_path = settlement_root / "outcome-source-archives" / str(
        factual.source_archive.artifact_id
    )
    dataset_path = settlement_root / "outcome-datasets" / str(
        factual.source_dataset.artifact_id
    )
    evidence_path = settlement_root / "outcome-evidence" / str(
        factual.factual_evidence.artifact_id
    )
    archive = load_outcome_settlement_source_archive(archive_path)
    dataset = load_verified_market_data_dataset(dataset_path)
    evidence = load_trade_horizon_outcome_evidence(evidence_path)
    stored = (
        (archive.artifact_id, archive.content_hash),
        (ArtifactId(str(dataset.artifact.dataset_id)), dataset.artifact.content_hash),
        (evidence.artifact_id, evidence.content_hash),
    )
    expected = (
        (factual.source_archive.artifact_id, factual.source_archive.content_hash),
        (factual.source_dataset.artifact_id, factual.source_dataset.content_hash),
        (factual.factual_evidence.artifact_id, factual.factual_evidence.content_hash),
    )
    if stored != expected:
        raise ValueError("durable Outcome Artifact lineage differs from PostgreSQL Authority")
    minute_timeframes = {
        item.timeframe for item in dataset.bars if item.timeframe is not Timeframe.DAILY
    }
    if minute_timeframes != {Timeframe.MINUTE_5}:
        raise ValueError("durable free Outcome Dataset is not BaoStock five-minute OHLC")
    return (
        FreeOutcomeAcquisition(
            dataset=dataset,
            source_archive=archive,
            source_archive_path=archive_path,
            dataset_path=dataset_path,
            provider_id="BAOSTOCK_HISTORICAL_5MIN_FREE_EXPLORATORY",
            minute_timeframe=Timeframe.MINUTE_5,
            retrieved_at=factual.created_at,
        ),
        evidence,
        evidence_path,
    )


def _reference_path(
    package: ControlledOperationalEvidencePackage,
    run_root: Path,
    reference_type: str,
) -> Path:
    matches = tuple(
        item for item in package.evidence_references if item.reference_type == reference_type
    )
    if len(matches) != 1:
        raise ValueError(f"Controlled package requires one {reference_type} reference")
    path = (run_root / matches[0].locator).resolve()
    if not path.is_relative_to(run_root.resolve()) or not path.exists():
        raise ValueError(f"Controlled package {reference_type} locator is invalid")
    return path


def _timestamp(value: object) -> datetime:
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if result.tzinfo is None or result.utcoffset() is None:
        result = result.replace(tzinfo=_SHANGHAI)
    return result


__all__ = [
    "FreeDataSettlementOperator",
    "FreeOutcomeAcquisition",
    "FreeOutcomeDatasetBuilder",
]
