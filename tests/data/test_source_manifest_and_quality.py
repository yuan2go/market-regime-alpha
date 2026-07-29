from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.identity import ArtifactId, ProviderId
from market_regime_alpha.core.time import (
    AvailabilityTime,
    DecisionTime,
    RetrievedAt,
)
from market_regime_alpha.data.contracts import (
    DataEligibility,
    SourceArtifactReference,
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
SOURCE = SourceArtifactReference(
    artifact_id=ArtifactId("source-artifact-tencent"),
    provider_id=ProviderId("provider-tencent-public"),
    retrieved_at=RETRIEVED,
    content_hash="sha256:" + "1" * 64,
    locator="https://qt.gtimg.cn/q=sz000001",
)


def _field(
    fact: CriticalSourceFact | None,
    *,
    symbol: str | None = "000001.SZ",
    field_id: str | None = None,
    available_time: AvailabilityTime | None = AVAILABLE,
    quality: SourceFieldQualityStatus = SourceFieldQualityStatus.COMPLETE,
) -> SourceManifestField:
    return SourceManifestField(
        field_id=field_id or (fact.value.lower() if fact is not None else "optional-note"),
        symbol=symbol,
        critical_fact=fact,
        provider_id=SOURCE.provider_id,
        source_artifact_id=SOURCE.artifact_id,
        event_time=datetime(2025, 1, 6, 14, 54, tzinfo=SHANGHAI),
        available_time=available_time,
        retrieved_time=RETRIEVED,
        decision_time=DECISION,
        unit="CNY" if fact is CriticalSourceFact.PRICE else "DECLARATION",
        adjustment_basis="NONE",
        finality=SourceFieldFinality.FINAL,
        data_eligibility=DataEligibility.EXPLORATORY,
        quality_status=quality,
        reason_codes=(),
    )


def _complete_manifest(
    *,
    fields: tuple[SourceManifestField, ...] | None = None,
) -> SourceManifest:
    required = (
        _field(CriticalSourceFact.DECISION_TIME, symbol=None),
        _field(CriticalSourceFact.PRICE),
        _field(CriticalSourceFact.TRADING_STATUS),
        _field(CriticalSourceFact.HISTORY_WINDOW),
        _field(CriticalSourceFact.UNIVERSE_MEMBERSHIP),
        _field(CriticalSourceFact.ELIGIBILITY),
    )
    return SourceManifest(
        provider_profile_id="public-composite-replay-v1",
        decision_time=DECISION,
        source_artifacts=(SOURCE,),
        fields=fields if fields is not None else required,
        source_conflicts=(),
        limitations=("PUBLIC_DATA_EXPLORATORY_ONLY",),
        data_eligibility=DataEligibility.EXPLORATORY,
    )


def test_source_manifest_identity_is_deterministic_and_binds_raw_hashes() -> None:
    first = _complete_manifest()
    second = _complete_manifest()

    assert first.source_manifest_id == second.source_manifest_id
    assert first.content_hash == second.content_hash
    assert first.source_hashes == (SOURCE.content_hash,)
    assert first.to_canonical_dict()["fields"][0]["available_time"] == AVAILABLE.isoformat()


def test_quality_gate_is_complete_only_when_every_critical_fact_is_usable() -> None:
    report = evaluate_daily_data_quality(
        manifest=_complete_manifest(),
        required_symbols=("000001.SZ",),
    )

    assert report.status is DailyDataQualityStatus.COMPLETE
    assert report.blocked_reason_codes == ()
    assert report.data_eligibility is DataEligibility.EXPLORATORY


def test_missing_critical_fact_is_data_blocked_not_failed() -> None:
    manifest = _complete_manifest()
    fields = tuple(
        field
        for field in manifest.fields
        if field.critical_fact is not CriticalSourceFact.TRADING_STATUS
    )

    report = evaluate_daily_data_quality(
        manifest=_complete_manifest(fields=fields),
        required_symbols=("000001.SZ",),
    )

    assert report.status is DailyDataQualityStatus.DATA_BLOCKED
    assert report.blocked_reason_codes == ("TRADING_STATUS_MISSING:000001.SZ",)


def test_missing_or_post_decision_availability_is_data_blocked() -> None:
    missing = _complete_manifest()
    missing_fields = tuple(
        _field(
            field.critical_fact,
            symbol=field.symbol,
            field_id=field.field_id,
            available_time=None,
        )
        if field.critical_fact is CriticalSourceFact.PRICE
        else field
        for field in missing.fields
    )
    late = _complete_manifest()
    late_fields = tuple(
        _field(
            field.critical_fact,
            symbol=field.symbol,
            field_id=field.field_id,
            available_time=AvailabilityTime(DECISION.value + timedelta(seconds=1)),
        )
        if field.critical_fact is CriticalSourceFact.PRICE
        else field
        for field in late.fields
    )

    missing_report = evaluate_daily_data_quality(
        manifest=_complete_manifest(fields=missing_fields),
        required_symbols=("000001.SZ",),
    )
    late_report = evaluate_daily_data_quality(
        manifest=_complete_manifest(fields=late_fields),
        required_symbols=("000001.SZ",),
    )

    assert missing_report.status is DailyDataQualityStatus.DATA_BLOCKED
    assert missing_report.blocked_reason_codes == (
        "AVAILABLE_TIME_MISSING:000001.SZ:price",
    )
    assert late_report.status is DailyDataQualityStatus.DATA_BLOCKED
    assert late_report.blocked_reason_codes == (
        "AVAILABLE_AFTER_DECISION:000001.SZ:price",
    )


def test_noncritical_degradation_remains_explicit() -> None:
    manifest = _complete_manifest()
    fields = (
        *manifest.fields,
        _field(
            None,
            field_id="optional-market-name",
            quality=SourceFieldQualityStatus.DEGRADED,
        ),
    )

    report = evaluate_daily_data_quality(
        manifest=_complete_manifest(fields=fields),
        required_symbols=("000001.SZ",),
    )

    assert report.status is DailyDataQualityStatus.DEGRADED
    assert report.blocked_reason_codes == ()


def test_v1_source_manifest_round_trip_identity_is_unchanged_by_v2_support() -> None:
    manifest = _complete_manifest()
    restored = SourceManifest.from_canonical_dict(manifest.to_canonical_dict())

    assert manifest.schema_version == "phase-d-source-manifest-v1"
    assert restored == manifest
    assert all(
        field.authority_kind is SourceAuthorityKind.PROVIDER
        and field.value is None
        for field in restored.fields
    )


def test_reader_rejects_tampered_policy_membership() -> None:
    membership = SourceManifestField(
        field_id="universe_membership",
        symbol="000001.SZ",
        critical_fact=CriticalSourceFact.UNIVERSE_MEMBERSHIP,
        provider_id=SOURCE.provider_id,
        source_artifact_id=SOURCE.artifact_id,
        event_time=DECISION.value,
        available_time=AvailabilityTime(DECISION.value),
        retrieved_time=RETRIEVED,
        decision_time=DECISION,
        unit="BOOLEAN",
        adjustment_basis="NONE",
        finality=SourceFieldFinality.FINAL,
        data_eligibility=DataEligibility.EXPLORATORY,
        quality_status=SourceFieldQualityStatus.COMPLETE,
        reason_codes=(),
        schema_version="phase-d-source-manifest-field-v2",
        authority_kind=SourceAuthorityKind.UNIVERSE_POLICY,
        value=True,
    )
    fields = tuple(
        membership
        if field.critical_fact is CriticalSourceFact.UNIVERSE_MEMBERSHIP
        else replace(
            field,
            schema_version="phase-d-source-manifest-field-v2",
        )
        for field in _complete_manifest().fields
    )
    manifest = SourceManifest(
        provider_profile_id="public-composite-replay-v1",
        decision_time=DECISION,
        source_artifacts=(SOURCE,),
        fields=fields,
        source_conflicts=(),
        limitations=("PUBLIC_DATA_EXPLORATORY_ONLY",),
        data_eligibility=DataEligibility.EXPLORATORY,
        schema_version="phase-d-source-manifest-v2",
    )
    payload = manifest.to_canonical_dict()
    membership_payload = next(
        item
        for item in payload["fields"]
        if item["critical_fact"] == "UNIVERSE_MEMBERSHIP"
    )
    membership_payload["value"] = False

    with pytest.raises(ValueError, match="identity mismatch"):
        SourceManifest.from_canonical_dict(payload)
