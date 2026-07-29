from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.identity import ArtifactId, ProviderId
from market_regime_alpha.core.time import (
    AvailabilityTime,
    DecisionTime,
    RetrievedAt,
)
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.providers.public_composite import (
    PUBLIC_COMPOSITE_LIVE_PROFILE_ID,
    PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
    AcquiredSourcePayload,
    BaoStockHistoryClient,
    PublicBar,
    PublicCompositeBatch,
    PublicCompositeLiveProfile,
    PublicCompositeProviderResult,
    PublicCompositeRequest,
    PublicCompositeReplayProfile,
    PublicQuote,
    PublicSecurityStatusObservation,
    STStatus,
    ListingStatus,
    SecurityStatusEvidenceScope,
    SecurityStatusFactType,
    SourceReplayArchiveReader,
    TradingStatus,
    HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1,
    build_public_source_manifest,
    build_daily_control_source_evidence,
    publish_source_replay_archive,
)
from market_regime_alpha.data.daily_quality import (
    DailyDataQualityStatus,
    evaluate_daily_data_quality,
)
from market_regime_alpha.data.source_manifest import (
    CriticalSourceFact,
    SourceAuthorityKind,
    SourceFieldFinality,
    SourceFieldQualityStatus,
    SourceManifest,
    SourceManifestField,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
DECISION = DecisionTime(datetime(2025, 1, 6, 14, 55, tzinfo=SHANGHAI))
RETRIEVED = RetrievedAt(datetime(2025, 1, 6, 14, 54, tzinfo=SHANGHAI))
AVAILABLE = AvailabilityTime(datetime(2025, 1, 6, 14, 54, tzinfo=SHANGHAI))


def _payload(provider: str, raw: bytes) -> AcquiredSourcePayload:
    return AcquiredSourcePayload(
        provider_id=ProviderId(provider),
        product="test-product",
        locator=f"https://example.invalid/{provider}",
        raw_payload=raw,
        retrieved_time=RETRIEVED,
        limitations=("PUBLIC_DATA_EXPLORATORY_ONLY",),
    )


def _history_batch() -> PublicCompositeBatch:
    payload = _payload("provider-baostock-public", b"date,time,close\n2025-01-03,145500,10.0\n")
    return PublicCompositeBatch(
        raw_payloads=(payload,),
        bars=(
            PublicBar(
                symbol="000001.SZ",
                event_time=datetime(2025, 1, 3, 14, 55, tzinfo=SHANGHAI),
                available_time=AvailabilityTime(
                    datetime(2025, 1, 3, 15, 1, tzinfo=SHANGHAI)
                ),
                source_artifact_id=payload.source_artifact_id,
                open=9.8,
                high=10.1,
                low=9.7,
                close=10.0,
                volume=1_000_000.0,
                amount=10_000_000.0,
                unit="CNY",
                adjustment_basis="BAOSTOCK_ADJUSTFLAG_3",
                finality=SourceFieldFinality.FINAL,
            ),
        ),
        quotes=(),
        source_conflicts=(),
        limitations=(),
    )


def _current_batch() -> PublicCompositeBatch:
    payload = _payload("provider-tencent-public", b'v_sz000001="51~name~000001~10.10";')
    return PublicCompositeBatch(
        raw_payloads=(payload,),
        bars=(),
        quotes=(
            PublicQuote(
                symbol="000001.SZ",
                event_time=datetime(2025, 1, 6, 14, 54, tzinfo=SHANGHAI),
                available_time=AVAILABLE,
                source_artifact_id=payload.source_artifact_id,
                price=10.1,
                trading_status=TradingStatus.TRADING,
                unit="CNY",
                finality=SourceFieldFinality.PRELIMINARY,
            ),
        ),
        source_conflicts=(),
        limitations=(),
    )


class _Client:
    def __init__(self, batch: PublicCompositeBatch) -> None:
        self.batch = batch
        self.calls = 0

    def acquire(self, request: PublicCompositeRequest) -> PublicCompositeBatch:
        self.calls += 1
        assert request.symbols == ("000001.SZ",)
        return self.batch


def _request() -> PublicCompositeRequest:
    return PublicCompositeRequest(
        symbols=("000001.SZ",),
        decision_time=DECISION,
        history_start=date(2024, 12, 1),
        minimum_history_sessions=1,
    )


def _replay_manifest(result: PublicCompositeProviderResult) -> SourceManifest:
    references = result.source_artifact_references
    quote = result.quotes[0]
    fields = tuple(
        SourceManifestField(
            field_id=fact.value.lower(),
            symbol=None if fact is CriticalSourceFact.DECISION_TIME else "000001.SZ",
            critical_fact=fact,
            provider_id=references[-1].provider_id,
            source_artifact_id=references[-1].artifact_id,
            event_time=quote.event_time,
            available_time=quote.available_time,
            retrieved_time=references[-1].retrieved_at,
            decision_time=DECISION,
            unit="CNY" if fact is CriticalSourceFact.PRICE else "DECLARATION",
            adjustment_basis="NONE",
            finality=SourceFieldFinality.FINAL,
            data_eligibility=DataEligibility.EXPLORATORY,
            quality_status=SourceFieldQualityStatus.COMPLETE,
            reason_codes=(),
        )
        for fact in CriticalSourceFact
        if fact is not CriticalSourceFact.AVAILABLE_TIME
    )
    return SourceManifest(
        provider_profile_id=PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
        decision_time=DECISION,
        source_artifacts=references,
        fields=fields,
        source_conflicts=(),
        limitations=("FIXTURE_REPLAY_ONLY",),
        data_eligibility=DataEligibility.EXPLORATORY,
    )


def test_live_profile_calls_only_declared_baostock_and_tencent_clients() -> None:
    history = _Client(_history_batch())
    current = _Client(_current_batch())
    profile = PublicCompositeLiveProfile(
        history_client=history,
        current_client=current,
    )

    result = profile.acquire(_request())

    assert profile.profile_id == PUBLIC_COMPOSITE_LIVE_PROFILE_ID
    assert history.calls == 1
    assert current.calls == 1
    assert tuple(item.provider_id.value for item in result.raw_payloads) == (
        "provider-baostock-public",
        "provider-tencent-public",
    )
    assert result.raw_payloads[0].raw_hash == (
        "sha256:f0e66a0d5301d5c1a421a4506e6f71c4e3a80ad4eff2c64"
        "b0a002e9134303dfe"
    )
    assert result.data_eligibility is DataEligibility.EXPLORATORY


def test_unreferenced_normalized_data_is_rejected() -> None:
    history = _history_batch()
    unknown = PublicQuote(
        symbol="000001.SZ",
        event_time=datetime(2025, 1, 6, 14, 54, tzinfo=SHANGHAI),
        available_time=AVAILABLE,
        source_artifact_id=ArtifactId("missing-source"),
        price=10.1,
        trading_status=TradingStatus.TRADING,
        unit="CNY",
        finality=SourceFieldFinality.PRELIMINARY,
    )

    with pytest.raises(ValueError, match="unarchived source payload"):
        PublicCompositeProviderResult(
            profile_id=PUBLIC_COMPOSITE_LIVE_PROFILE_ID,
            decision_time=DECISION,
            raw_payloads=history.raw_payloads,
            bars=history.bars,
            quotes=(unknown,),
            source_conflicts=(),
            limitations=(),
        )


def test_live_source_manifest_stays_blocked_when_membership_is_unproven() -> None:
    result = PublicCompositeLiveProfile(
        history_client=_Client(_history_batch()),
        current_client=_Client(_current_batch()),
    ).acquire(_request())

    manifest = build_public_source_manifest(result=result, request=_request())
    report = evaluate_daily_data_quality(
        manifest=manifest,
        required_symbols=("000001.SZ",),
    )

    assert report.status is DailyDataQualityStatus.DATA_BLOCKED
    assert report.blocked_reason_codes == (
        "UNIVERSE_MEMBERSHIP_MISSING:000001.SZ",
        "ELIGIBILITY_MISSING:000001.SZ",
    )
    assert all(
        field.data_eligibility is DataEligibility.EXPLORATORY
        for field in manifest.fields
    )


def test_unknown_trading_status_is_explicit() -> None:
    current = _current_batch()
    unknown_current = replace(
        current,
        quotes=tuple(
            replace(item, trading_status=TradingStatus.UNKNOWN)
            for item in current.quotes
        ),
    )
    result = PublicCompositeLiveProfile(
        history_client=_Client(_history_batch()),
        current_client=_Client(unknown_current),
    ).acquire(_request())
    evidence = build_daily_control_source_evidence(
        request=_request(),
        retrieved_time=RETRIEVED,
        policy_id=ArtifactId("universe-policy-smoke-v1"),
        policy_hash="sha256:" + "a" * 64,
        policy_version="a-share-smoke-pool@v1",
        instrument_scope="A_SHARE_STOCK",
        symbols=("000001.SZ",),
    )
    result = replace(
        result,
        raw_payloads=(*result.raw_payloads, *evidence.raw_payloads),
    )

    manifest = build_public_source_manifest(
        result=result,
        request=_request(),
        declared_fields=evidence.fields,
    )
    trading = next(
        field
        for field in manifest.fields
        if field.critical_fact is CriticalSourceFact.TRADING_STATUS
    )

    assert trading.value == "UNKNOWN"
    assert trading.quality_status is SourceFieldQualityStatus.INSUFFICIENT
    assert trading.reason_codes == ("TRADING_STATUS_UNKNOWN",)
    assert trading.authority_kind is SourceAuthorityKind.PROVIDER


def test_missing_membership_policy_blocks_run() -> None:
    result = PublicCompositeLiveProfile(
        history_client=_Client(_history_batch()),
        current_client=_Client(_current_batch()),
    ).acquire(_request())
    evidence = build_daily_control_source_evidence(
        request=_request(),
        retrieved_time=RETRIEVED,
        policy_id=ArtifactId("universe-policy-smoke-v1"),
        policy_hash="sha256:" + "a" * 64,
        policy_version="a-share-smoke-pool@v1",
        instrument_scope="A_SHARE_STOCK",
        symbols=("000001.SZ",),
    )
    result = replace(
        result,
        raw_payloads=(*result.raw_payloads, *evidence.raw_payloads),
    )
    protocol_only = tuple(
        field
        for field in evidence.fields
        if field.critical_fact is CriticalSourceFact.DECISION_TIME
    )
    manifest = build_public_source_manifest(
        result=result,
        request=_request(),
        declared_fields=protocol_only,
    )

    report = evaluate_daily_data_quality(
        manifest=manifest,
        required_symbols=("000001.SZ",),
    )

    assert report.status is DailyDataQualityStatus.DATA_BLOCKED
    assert "UNIVERSE_MEMBERSHIP_MISSING:000001.SZ" in (
        report.blocked_reason_codes
    )


def test_decision_time_is_protocol_fact() -> None:
    result = PublicCompositeLiveProfile(
        history_client=_Client(_history_batch()),
        current_client=_Client(_current_batch()),
    ).acquire(_request())
    late_retrieval = RetrievedAt(
        datetime(2025, 1, 6, 16, 0, tzinfo=SHANGHAI)
    )
    evidence = build_daily_control_source_evidence(
        request=_request(),
        retrieved_time=late_retrieval,
        policy_id=ArtifactId("universe-policy-smoke-v1"),
        policy_hash="sha256:" + "a" * 64,
        policy_version="a-share-smoke-pool@v1",
        instrument_scope="A_SHARE_STOCK",
        symbols=("000001.SZ",),
    )
    result = PublicCompositeProviderResult(
        profile_id=result.profile_id,
        decision_time=result.decision_time,
        raw_payloads=(*result.raw_payloads, *evidence.raw_payloads),
        bars=result.bars,
        quotes=result.quotes,
        source_conflicts=result.source_conflicts,
        limitations=result.limitations,
    )

    manifest = build_public_source_manifest(
        result=result,
        request=_request(),
        declared_fields=evidence.fields,
    )

    decision = next(
        field
        for field in manifest.fields
        if field.critical_fact is CriticalSourceFact.DECISION_TIME
    )
    assert manifest.schema_version == "phase-d-source-manifest-v2"
    assert decision.schema_version == "phase-d-source-manifest-field-v2"
    assert decision.authority_kind is SourceAuthorityKind.PROTOCOL
    assert decision.provider_id == ProviderId("provider-daily-run-protocol")
    assert decision.available_time == AvailabilityTime(DECISION.value)
    assert decision.retrieved_time == late_retrieval
    assert decision.value == DECISION.isoformat()


def test_decision_time_not_blocked_by_late_runtime_retrieval() -> None:
    result = PublicCompositeLiveProfile(
        history_client=_Client(_history_batch()),
        current_client=_Client(_current_batch()),
    ).acquire(_request())
    evidence = build_daily_control_source_evidence(
        request=_request(),
        retrieved_time=RetrievedAt(
            datetime(2025, 1, 6, 16, 0, tzinfo=SHANGHAI)
        ),
        policy_id=ArtifactId("universe-policy-smoke-v1"),
        policy_hash="sha256:" + "a" * 64,
        policy_version="a-share-smoke-pool@v1",
        instrument_scope="A_SHARE_STOCK",
        symbols=("000001.SZ",),
    )
    result = PublicCompositeProviderResult(
        profile_id=result.profile_id,
        decision_time=result.decision_time,
        raw_payloads=(*result.raw_payloads, *evidence.raw_payloads),
        bars=result.bars,
        quotes=result.quotes,
        source_conflicts=result.source_conflicts,
        limitations=result.limitations,
    )
    manifest = build_public_source_manifest(
        result=result,
        request=_request(),
        declared_fields=evidence.fields,
    )

    report = evaluate_daily_data_quality(
        manifest=manifest,
        required_symbols=("000001.SZ",),
    )

    assert not any(
        "GLOBAL:decision_time" in reason
        and reason.startswith("AVAILABLE_AFTER_DECISION")
        for reason in report.blocked_reason_codes
    )


def test_quote_after_decision_is_explicit_symbol_insufficiency() -> None:
    late_available = AvailabilityTime(
        datetime(2025, 1, 6, 16, 0, tzinfo=SHANGHAI)
    )
    current = _current_batch()
    late_current = replace(
        current,
        quotes=tuple(
            replace(item, available_time=late_available)
            for item in current.quotes
        ),
    )
    result = PublicCompositeLiveProfile(
        history_client=_Client(_history_batch()),
        current_client=_Client(late_current),
    ).acquire(_request())
    evidence = build_daily_control_source_evidence(
        request=_request(),
        retrieved_time=RetrievedAt(late_available.value),
        policy_id=ArtifactId("universe-policy-smoke-v1"),
        policy_hash="sha256:" + "a" * 64,
        policy_version="a-share-smoke-pool@v1",
        instrument_scope="A_SHARE_STOCK",
        symbols=("000001.SZ",),
    )
    result = replace(
        result,
        raw_payloads=(*result.raw_payloads, *evidence.raw_payloads),
    )
    manifest = build_public_source_manifest(
        result=result,
        request=_request(),
        declared_fields=evidence.fields,
    )

    price = next(
        field
        for field in manifest.fields
        if field.critical_fact is CriticalSourceFact.PRICE
    )
    trading = next(
        field
        for field in manifest.fields
        if field.critical_fact is CriticalSourceFact.TRADING_STATUS
    )

    assert price.quality_status is SourceFieldQualityStatus.INSUFFICIENT
    assert "QUOTE_AVAILABLE_AFTER_DECISION" in price.reason_codes
    assert trading.quality_status is SourceFieldQualityStatus.INSUFFICIENT
    assert "TRADING_STATUS_AVAILABLE_AFTER_DECISION" in trading.reason_codes


def test_smoke_pool_membership_has_policy_lineage() -> None:
    evidence = build_daily_control_source_evidence(
        request=_request(),
        retrieved_time=RETRIEVED,
        policy_id=ArtifactId("universe-policy-smoke-v1"),
        policy_hash="sha256:" + "a" * 64,
        policy_version="a-share-smoke-pool@v1",
        instrument_scope="A_SHARE_STOCK",
        symbols=("000001.SZ",),
    )

    membership = next(
        field
        for field in evidence.fields
        if field.critical_fact is CriticalSourceFact.UNIVERSE_MEMBERSHIP
    )
    policy_payload = next(
        payload
        for payload in evidence.raw_payloads
        if payload.product == "daily-universe-policy-evidence-v1"
    )
    assert membership.authority_kind is SourceAuthorityKind.UNIVERSE_POLICY
    assert membership.provider_id == ProviderId("authority-daily-universe-policy")
    assert membership.source_artifact_id == policy_payload.source_artifact_id
    assert membership.value is True
    assert policy_payload.locator == "policy://a-share-smoke-pool@v1"


def test_membership_does_not_claim_provider_authority() -> None:
    evidence = build_daily_control_source_evidence(
        request=_request(),
        retrieved_time=RETRIEVED,
        policy_id=ArtifactId("universe-policy-smoke-v1"),
        policy_hash="sha256:" + "a" * 64,
        policy_version="a-share-smoke-pool@v1",
        instrument_scope="A_SHARE_STOCK",
        symbols=("000001.SZ",),
    )

    membership = next(
        field
        for field in evidence.fields
        if field.critical_fact is CriticalSourceFact.UNIVERSE_MEMBERSHIP
    )
    assert membership.provider_id not in {
        ProviderId("provider-baostock-public"),
        ProviderId("provider-tencent-public"),
    }


def test_history_semantics_remain_exploratory() -> None:
    history = _history_batch()
    exploratory_bar = replace(
        history.bars[0],
        available_time=None,
        finality=SourceFieldFinality.UNKNOWN,
    )
    result = PublicCompositeProviderResult(
        profile_id=PUBLIC_COMPOSITE_LIVE_PROFILE_ID,
        decision_time=DECISION,
        raw_payloads=(*history.raw_payloads, *_current_batch().raw_payloads),
        bars=(exploratory_bar,),
        quotes=_current_batch().quotes,
        source_conflicts=(),
        limitations=(HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1,),
    )

    manifest = build_public_source_manifest(result=result, request=_request())
    history_field = next(
        field
        for field in manifest.fields
        if field.critical_fact is CriticalSourceFact.HISTORY_WINDOW
    )

    assert history_field.available_time is None
    assert history_field.finality is SourceFieldFinality.UNKNOWN
    assert (
        HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1
        in history_field.reason_codes
    )
    assert history_field.data_eligibility is DataEligibility.EXPLORATORY


def test_baostock_live_history_uses_prior_unadjusted_daily_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class Result:
        error_code = "0"
        error_msg = ""
        fields = (
            "date",
            "code",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "adjustflag",
            "tradestatus",
            "isST",
        )

        def __init__(self) -> None:
            self._rows = iter(
                (
                    [
                        "2025-01-03",
                        "sz.000001",
                        "9.8",
                        "10.1",
                        "9.7",
                        "10.0",
                        "1000000",
                        "10000000",
                        "3",
                        "1",
                        "0",
                    ],
                )
            )
            self._current: list[str] | None = None

        def next(self) -> bool:
            self._current = next(self._rows, None)
            return self._current is not None

        def get_row_data(self) -> list[str]:
            assert self._current is not None
            return self._current

    def query_history(code, fields, **kwargs):
        captured.update({"code": code, "fields": fields, **kwargs})
        return Result()

    fake = SimpleNamespace(
        login=lambda **kwargs: SimpleNamespace(
            error_code="0",
            error_msg="",
        ),
        logout=lambda: None,
        query_history_k_data_plus=query_history,
    )
    monkeypatch.setitem(sys.modules, "baostock", fake)
    client = BaoStockHistoryClient(
        clock=lambda: datetime(2025, 1, 6, 14, 50, tzinfo=SHANGHAI)
    )

    batch = client.acquire(_request())

    assert captured["frequency"] == "d"
    assert captured["adjustflag"] == "3"
    assert captured["end_date"] == "2025-01-05"
    assert "tradestatus" in str(captured["fields"])
    assert "isST" in str(captured["fields"])
    assert len(batch.bars) == 1
    assert batch.bars[0].available_time is None
    assert batch.bars[0].finality is SourceFieldFinality.UNKNOWN
    assert HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1 in batch.limitations
    assert tuple(
        (
            item.fact_type,
            item.value,
            item.scope,
            item.available_time,
            item.quality_status,
        )
        for item in batch.security_status_observations
    ) == (
        (
            SecurityStatusFactType.TRADING_STATUS,
            TradingStatus.TRADING,
            SecurityStatusEvidenceScope.PRIOR_SESSION_STATUS,
            None,
            SourceFieldQualityStatus.DEGRADED,
        ),
        (
            SecurityStatusFactType.ST_STATUS,
            STStatus.NOT_ST,
            SecurityStatusEvidenceScope.PRIOR_SESSION_STATUS,
            None,
            SourceFieldQualityStatus.DEGRADED,
        ),
    )
    assert all(
        item.reason_codes == ("PRIOR_SESSION_STATUS_NOT_CURRENT",)
        for item in batch.security_status_observations
    )


def test_security_status_fact_types_cannot_be_interchanged() -> None:
    payload = _payload("provider-baostock-public", b"status-evidence")

    with pytest.raises(TypeError, match="does not match fact_type"):
        PublicSecurityStatusObservation(
            symbol="000001.SZ",
            fact_type=SecurityStatusFactType.LISTING_STATUS,
            value=STStatus.NOT_ST,
            scope=SecurityStatusEvidenceScope.CURRENT_DECISION_SESSION,
            event_time=None,
            available_time=AVAILABLE,
            retrieved_time=RETRIEVED,
            decision_time=DECISION,
            policy_effective_time=None,
            provider_id=payload.provider_id,
            source_artifact_id=payload.source_artifact_id,
            authority_kind=SourceAuthorityKind.PROVIDER,
            quality_status=SourceFieldQualityStatus.COMPLETE,
            reason_codes=(),
            finality=SourceFieldFinality.PRELIMINARY,
            data_eligibility=DataEligibility.EXPLORATORY,
        )


def test_unknown_security_status_remains_explicit_and_incomplete() -> None:
    payload = _payload("provider-baostock-public", b"unknown-status-evidence")
    observation = PublicSecurityStatusObservation(
        symbol="000001.SZ",
        fact_type=SecurityStatusFactType.LISTING_STATUS,
        value=ListingStatus.UNKNOWN,
        scope=SecurityStatusEvidenceScope.CURRENT_DECISION_SESSION,
        event_time=None,
        available_time=AVAILABLE,
        retrieved_time=RETRIEVED,
        decision_time=DECISION,
        policy_effective_time=None,
        provider_id=payload.provider_id,
        source_artifact_id=payload.source_artifact_id,
        authority_kind=SourceAuthorityKind.PROVIDER,
        quality_status=SourceFieldQualityStatus.INSUFFICIENT,
        reason_codes=("LISTING_STATUS_UNKNOWN",),
        finality=SourceFieldFinality.UNKNOWN,
        data_eligibility=DataEligibility.EXPLORATORY,
    )

    restored = PublicSecurityStatusObservation.from_canonical_dict(
        observation.to_canonical_dict()
    )

    assert restored == observation
    assert restored.value is ListingStatus.UNKNOWN
    assert restored.available_time == AVAILABLE
    assert restored.retrieved_time == RETRIEVED
    assert restored.decision_time == DECISION
    assert restored.policy_effective_time is None


def test_replay_profile_reads_only_verified_manifest_and_immutable_archive(
    tmp_path: Path,
) -> None:
    live = PublicCompositeLiveProfile(
        history_client=_Client(_history_batch()),
        current_client=_Client(_current_batch()),
    ).acquire(_request())
    replay_result = PublicCompositeProviderResult(
        profile_id=PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
        decision_time=live.decision_time,
        raw_payloads=live.raw_payloads,
        bars=live.bars,
        quotes=live.quotes,
        source_conflicts=live.source_conflicts,
        limitations=("FIXTURE_REPLAY_ONLY",),
    )
    manifest = _replay_manifest(replay_result)
    archive = publish_source_replay_archive(
        root=tmp_path,
        provider_result=replay_result,
        source_manifest=manifest,
    )

    profile = PublicCompositeReplayProfile(
        archive_reader=SourceReplayArchiveReader()
    )
    acquired = profile.acquire(
        archive_path=archive,
        expected_source_manifest_id=manifest.source_manifest_id,
    )

    assert profile.profile_id == PUBLIC_COMPOSITE_REPLAY_PROFILE_ID
    assert acquired.source_manifest == manifest
    assert acquired.provider_result == replay_result
    assert acquired.provider_result.raw_payloads[1].raw_payload.startswith(b"v_")

    (archive / "provider_result.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        profile.acquire(
            archive_path=archive,
            expected_source_manifest_id=manifest.source_manifest_id,
        )


def test_replay_profile_rejects_a_different_manifest_identity(tmp_path: Path) -> None:
    live = PublicCompositeLiveProfile(
        history_client=_Client(_history_batch()),
        current_client=_Client(_current_batch()),
    ).acquire(_request())
    replay_result = PublicCompositeProviderResult(
        profile_id=PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
        decision_time=live.decision_time,
        raw_payloads=live.raw_payloads,
        bars=live.bars,
        quotes=live.quotes,
        source_conflicts=(),
        limitations=(),
    )
    manifest = _replay_manifest(replay_result)
    archive = publish_source_replay_archive(
        root=tmp_path,
        provider_result=replay_result,
        source_manifest=manifest,
    )

    with pytest.raises(ValueError, match="SourceManifest identity"):
        PublicCompositeReplayProfile().acquire(
            archive_path=archive,
            expected_source_manifest_id=ArtifactId("source-manifest-other"),
        )
