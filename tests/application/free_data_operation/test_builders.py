from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from market_regime_alpha.application.free_data_operation import (
    FreeDataInstrument,
    FreeDataOperationScale,
    FreeDataPreparationRequest,
    load_free_data_prepared_manifest,
    prepare_free_data_inputs,
)
from market_regime_alpha.application.operational_research.supplemental_artifact import (
    load_verified_supplemental_research_evidence,
)
from market_regime_alpha.core.time import AvailabilityTime, DecisionTime, RetrievedAt
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.providers.public_composite import (
    BAOSTOCK_PUBLIC_PROVIDER_ID,
    TENCENT_FREE_OPERATIONAL_PROFILE_ID,
    TENCENT_PUBLIC_PROVIDER_ID,
    AcquiredSourcePayload,
    PublicBar,
    PublicCompositeBatch,
    PublicCompositeProviderResult,
    PublicQuote,
    PublicSourceAcquisitionStage,
    PublicSourceStageScope,
    STStatus,
    ListingStatus,
    TradingStatus,
    load_verified_public_source_stage_artifact,
    publish_public_source_stage_artifact,
)
from market_regime_alpha.data.source_manifest import (
    CriticalSourceFact,
    SourceAuthorityKind,
    SourceFieldFinality,
    SourceFieldQualityStatus,
    SourceManifest,
    SourceManifestField,
)
from market_regime_alpha.market_data import (
    AssetType,
    Timeframe,
    VolumeUnit,
    load_verified_market_data_dataset,
    replay_market_data_dataset,
)
from market_regime_alpha.universe import load_operational_universe


SHANGHAI = ZoneInfo("Asia/Shanghai")
UTC = timezone.utc
DECISION = DecisionTime(datetime(2026, 8, 5, 14, 55, tzinfo=SHANGHAI))


def _symbols(count: int) -> tuple[str, ...]:
    return tuple(f"{600000 + index:06d}.SH" for index in range(count))


def _source_inputs(
    tmp_path: Path,
    *,
    count: int = 20,
    missing_session: date | None = None,
) -> tuple[Path, PublicCompositeProviderResult, SourceManifest]:
    symbols = _symbols(count)
    retrieved = RetrievedAt(DECISION.value - timedelta(minutes=10))
    history = AcquiredSourcePayload(
        provider_id=BAOSTOCK_PUBLIC_PROVIDER_ID,
        product="recorded-baostock-history",
        locator="recorded://baostock/history",
        raw_payload=f"recorded-history:{count}".encode(),
        retrieved_time=retrieved,
        limitations=("RECORDED_ARCHIVE_TEST",),
    )
    status = AcquiredSourcePayload(
        provider_id=BAOSTOCK_PUBLIC_PROVIDER_ID,
        product="recorded-baostock-status",
        locator="recorded://baostock/status",
        raw_payload=f"recorded-status:{count}".encode(),
        retrieved_time=retrieved,
        limitations=("RECORDED_ARCHIVE_TEST",),
    )
    quote = AcquiredSourcePayload(
        provider_id=TENCENT_PUBLIC_PROVIDER_ID,
        product="recorded-tencent-quote",
        locator="recorded://tencent/quote",
        raw_payload=f"recorded-quote:{count}".encode(),
        retrieved_time=retrieved,
        limitations=("RECORDED_ARCHIVE_TEST",),
    )
    sessions: tuple[date, ...] = (
        date(2026, 7, 30),
        date(2026, 7, 31),
        date(2026, 8, 3),
        date(2026, 8, 4),
    )
    sessions = tuple(item for item in sessions if item != missing_session)
    bars = tuple(
        PublicBar(
            symbol=symbol,
            event_time=datetime.combine(session, time(15), tzinfo=SHANGHAI),
            available_time=None,
            source_artifact_id=history.source_artifact_id,
            open=10.0 + day_index / 10,
            high=10.3 + day_index / 10,
            low=9.8 + day_index / 10,
            close=10.1 + day_index / 10,
            volume=1_000_000 + symbol_index * 1000,
            amount=20_000_000 + symbol_index * 10_000,
            unit="CNY",
            adjustment_basis="BAOSTOCK_ADJUSTFLAG_3",
            finality=SourceFieldFinality.UNKNOWN,
        )
        for symbol_index, symbol in enumerate(symbols)
        for day_index, session in enumerate(sessions)
    )
    quotes = tuple(
        PublicQuote(
            symbol=symbol,
            event_time=DECISION.value - timedelta(minutes=1),
            available_time=AvailabilityTime(retrieved.value),
            source_artifact_id=quote.source_artifact_id,
            price=10.5,
            trading_status=TradingStatus.UNKNOWN,
            unit="CNY",
            finality=SourceFieldFinality.PRELIMINARY,
        )
        for symbol in symbols
    )
    stage_path = publish_public_source_stage_artifact(
        root=tmp_path / "source_stages",
        stage=PublicSourceAcquisitionStage.HISTORY_SOURCE_FROZEN,
        batch=PublicCompositeBatch(
            raw_payloads=(history,),
            bars=bars,
            quotes=(),
            source_conflicts=(),
            limitations=("RECORDED_ARCHIVE_TEST",),
        ),
        scope=PublicSourceStageScope(
            run_request_id="free-data-recorded-request",
            decision_date=DECISION.value.date(),
            decision_time=DECISION,
            provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
            universe_policy_id=f"free-data-{count}",
            acquisition_stage=PublicSourceAcquisitionStage.HISTORY_SOURCE_FROZEN,
        ),
    )
    result = PublicCompositeProviderResult(
        profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        decision_time=DECISION,
        raw_payloads=(history, status, quote),
        bars=bars,
        quotes=quotes,
        source_conflicts=(),
        limitations=("RECORDED_ARCHIVE_TEST",),
    )
    manifest = SourceManifest(
        provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        decision_time=DECISION,
        source_artifacts=result.source_artifact_references,
        fields=tuple(
            SourceManifestField(
                field_id=fact.value.lower(),
                symbol=symbol,
                critical_fact=fact,
                provider_id=status.provider_id,
                source_artifact_id=status.source_artifact_id,
                event_time=None,
                available_time=AvailabilityTime(retrieved.value),
                retrieved_time=retrieved,
                decision_time=DECISION,
                unit="DECLARATION",
                adjustment_basis="NONE",
                finality=SourceFieldFinality.PRELIMINARY,
                data_eligibility=DataEligibility.EXPLORATORY,
                quality_status=SourceFieldQualityStatus.COMPLETE,
                reason_codes=(),
                schema_version=SourceManifestField.SCHEMA_V2,
                authority_kind=SourceAuthorityKind.PROVIDER,
                value=value,
            )
            for symbol in symbols
            for fact, value in (
                (CriticalSourceFact.TRADING_STATUS, TradingStatus.TRADING.value),
                (CriticalSourceFact.ST_STATUS, STStatus.NOT_ST.value),
                (CriticalSourceFact.LISTING_STATUS, ListingStatus.LISTED.value),
            )
        ),
        source_conflicts=(),
        limitations=("RECORDED_ARCHIVE_TEST", "FORMAL_PIT_NOT_ESTABLISHED"),
        data_eligibility=DataEligibility.EXPLORATORY,
        schema_version=SourceManifest.SCHEMA_V2,
    )
    return stage_path, result, manifest


def _request(count: int = 20) -> FreeDataPreparationRequest:
    return FreeDataPreparationRequest(
        scale=FreeDataOperationScale.from_symbol_count(count),
        provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        decision_time=DECISION,
        created_at=(DECISION.value + timedelta(minutes=5)).astimezone(UTC),
        instruments=tuple(
            FreeDataInstrument(symbol=symbol, asset_type=AssetType.A_SHARE)
            for symbol in _symbols(count)
        ),
        membership_source=f"OPERATOR_APPROVED_FREE_DATA_{count}",
        minimum_history_sessions=3,
        liquidity_lookback_sessions=4,
        minimum_median_daily_amount=Decimal("1000000"),
        configuration_hash="sha256:" + "c" * 64,
    )


def test_recorded_free_data_builds_replayable_canonical_inputs(tmp_path: Path) -> None:
    stage_path, result, manifest = _source_inputs(tmp_path)

    prepared = prepare_free_data_inputs(
        request=_request(),
        history_source=load_verified_public_source_stage_artifact(stage_path),
        provider_result=result,
        full_source_manifest=manifest,
        output_root=tmp_path,
    )

    universe = load_operational_universe(prepared.paths.operational_universe)
    dataset = load_verified_market_data_dataset(prepared.paths.daily_market_data)
    supplemental = load_verified_supplemental_research_evidence(
        prepared.paths.supplemental_research_evidence
    )
    restored = load_free_data_prepared_manifest(prepared.manifest_path)
    assert len(universe.records) == 20
    assert len(universe.symbols) == 20
    assert dataset.artifact.coverage.expected_symbols == _symbols(20)
    assert dataset.artifact.coverage.expected_timeframes == (Timeframe.DAILY,)
    assert all(bar.volume_unit is VolumeUnit.SHARES for bar in dataset.bars)
    assert replay_market_data_dataset(prepared.paths.daily_market_data).artifact == dataset.artifact
    assert len(supplemental.bundle.symbol_observations) == 20
    assert supplemental.bundle.theme_memberships == ()
    assert any(
        item.evidence_kind == "THEME_MEMBERSHIP"
        for item in supplemental.bundle.missing_evidence
    )
    assert "FORMAL_PIT_NOT_ESTABLISHED" in supplemental.bundle.reason_codes
    assert restored == prepared.manifest

    repeated = prepare_free_data_inputs(
        request=_request(),
        history_source=load_verified_public_source_stage_artifact(stage_path),
        provider_result=result,
        full_source_manifest=manifest,
        output_root=tmp_path,
    )
    assert repeated.manifest == prepared.manifest
    assert repeated.manifest_path == prepared.manifest_path


def test_calendar_contains_only_sessions_observed_in_archived_bars(
    tmp_path: Path,
) -> None:
    missing = date(2026, 7, 31)
    stage_path, result, manifest = _source_inputs(
        tmp_path,
        missing_session=missing,
    )

    prepared = prepare_free_data_inputs(
        request=_request(),
        history_source=load_verified_public_source_stage_artifact(stage_path),
        provider_result=result,
        full_source_manifest=manifest,
        output_root=tmp_path,
    )

    assert missing not in prepared.calendar.trading_dates
    assert prepared.calendar.trading_dates == (
        date(2026, 7, 30),
        date(2026, 8, 3),
        date(2026, 8, 4),
        date(2026, 8, 5),
    )


def test_scale_contracts_are_exact() -> None:
    assert FreeDataOperationScale.from_symbol_count(20) is FreeDataOperationScale.SMOKE
    assert FreeDataOperationScale.from_symbol_count(100) is FreeDataOperationScale.STANDARD
    assert FreeDataOperationScale.from_symbol_count(300) is FreeDataOperationScale.STRESS


def test_request_identity_excludes_nonsemantic_invocation_timestamp() -> None:
    first = _request()
    second = replace(first, created_at=first.created_at + timedelta(minutes=1))

    assert second.command_hash == first.command_hash


def test_status_retrieved_after_decision_cannot_enter_operational_universe(
    tmp_path: Path,
) -> None:
    stage_path, result, manifest = _source_inputs(tmp_path)
    late = DECISION.value + timedelta(minutes=1)
    late_manifest = replace(
        manifest,
        fields=tuple(
            replace(
                item,
                available_time=AvailabilityTime(late),
                retrieved_time=RetrievedAt(late),
            )
            for item in manifest.fields
        ),
    )

    prepared = prepare_free_data_inputs(
        request=_request(),
        history_source=load_verified_public_source_stage_artifact(stage_path),
        provider_result=result,
        full_source_manifest=late_manifest,
        output_root=tmp_path,
    )

    universe = load_operational_universe(prepared.paths.operational_universe)
    assert universe.symbols == ()
    assert all(
        {
            "LISTING_STATUS_UNKNOWN",
            "ST_STATUS_UNKNOWN",
            "SUSPENSION_STATUS_UNKNOWN",
        }.issubset(record.exclusion_reasons)
        for record in universe.records
    )
