import json
from pathlib import Path

from market_regime_alpha.research.prr_artifact_schemas import canonical_identity_hash
from market_regime_alpha.research.xuntou_pit_v4_preflight import (
    XuntouPITV4PreflightStatus,
    preflight_xuntou_pit_v4,
)


def test_missing_bundle_is_explicit_external_blocker() -> None:
    result = preflight_xuntou_pit_v4(None)
    assert result.status is XuntouPITV4PreflightStatus.BLOCKED_EXTERNAL_PROVIDER_INPUT
    assert result.tencent_fallback_used is False


def test_v3_bundle_cannot_masquerade_as_v4(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.json"
    bundle.write_text('{"schema_version":"xuntou-p0-native-bundle-v3"}', encoding="utf-8")
    result = preflight_xuntou_pit_v4(bundle)
    assert result.status is XuntouPITV4PreflightStatus.INVALID_PIT_EVIDENCE
    assert "V3_REHEARSAL_BUNDLE_CANNOT_BE_PROMOTED" in result.reasons


def test_test_only_fixture_is_not_formal_research_input(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        '{"schema_version":"xuntou-pit-validation-bundle-v4",'
        '"evidence_classification":"TEST_ONLY_NOT_RESEARCH_EVIDENCE"}',
        encoding="utf-8",
    )
    result = preflight_xuntou_pit_v4(bundle)
    assert result.status is XuntouPITV4PreflightStatus.INVALID_PIT_EVIDENCE
    assert "TEST_FIXTURE_NOT_RESEARCH_EVIDENCE" in result.reasons


def test_source_byte_change_changes_preflight_identity(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.json"
    bundle.write_text('{"schema_version":"bad-v1"}', encoding="utf-8")
    first = preflight_xuntou_pit_v4(bundle)
    bundle.write_text('{"schema_version":"bad-v2"}', encoding="utf-8")
    second = preflight_xuntou_pit_v4(bundle)
    assert first.bundle_content_hash != second.bundle_content_hash


def test_boolean_qualification_summary_cannot_unlock_v4_availability(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        '{"schema_version":"xuntou-pit-validation-bundle-v4",'
        '"qualification_inputs":{'
        '"historical_membership_complete":true,'
        '"security_master_complete":true,'
        '"st_history_complete":true,'
        '"suspension_history_complete":true,'
        '"orderability_complete":true,'
        '"liquidity_unit_verified":true,'
        '"bar_finality_verified":true,'
        '"availability_verified":true,'
        '"evaluation_path_complete":true}}',
        encoding="utf-8",
    )
    result = preflight_xuntou_pit_v4(bundle)
    assert result.status is not XuntouPITV4PreflightStatus.AVAILABLE
    assert "SOURCE_ARTIFACT_EVIDENCE_MISSING" in result.reasons


def test_complete_content_addressed_evidence_can_reach_available(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(_qualified_bundle()), encoding="utf-8")
    result = preflight_xuntou_pit_v4(bundle)
    assert result.status is XuntouPITV4PreflightStatus.AVAILABLE
    assert result.qualification is not None
    assert result.qualification.pit_correct_for_scope is True
    assert result.provider_artifact_id is not None
    assert result.provider_artifact_id.startswith("sha256:")


def test_checksum_stale_evidence_section_cannot_reach_available(tmp_path: Path) -> None:
    payload = _qualified_bundle()
    sections = payload["evidence_sections"]
    assert isinstance(sections, dict)
    membership = sections["historical_membership"]
    assert isinstance(membership, dict)
    records = membership["records"]
    assert isinstance(records, list)
    records[0]["is_member"] = False
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    result = preflight_xuntou_pit_v4(bundle)
    assert result.status is XuntouPITV4PreflightStatus.INVALID_PIT_EVIDENCE
    assert "HISTORICAL_MEMBERSHIP_CONTENT_HASH_MISMATCH" in result.reasons


def test_current_membership_records_cannot_reach_available(tmp_path: Path) -> None:
    payload = _qualified_bundle()
    sections = payload["evidence_sections"]
    assert isinstance(sections, dict)
    membership = sections["historical_membership"]
    assert isinstance(membership, dict)
    records = membership["records"]
    assert isinstance(records, list)
    records[0]["membership_source"] = "CURRENT_MEMBERSHIP_BACKFILL"
    membership["content_hash"] = canonical_identity_hash({"records": records})
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    result = preflight_xuntou_pit_v4(bundle)
    assert result.status is XuntouPITV4PreflightStatus.INSUFFICIENT_PROVIDER_CAPABILITY
    assert result.qualification is not None
    assert "CURRENT_MEMBERSHIP_BACKFILL_REJECTED" in result.qualification.reasons


def test_incomplete_0930_1030_path_cannot_reach_available(tmp_path: Path) -> None:
    payload = _qualified_bundle()
    sections = payload["evidence_sections"]
    assert isinstance(sections, dict)
    bars = sections["bar_finality"]
    assert isinstance(bars, dict)
    records = bars["records"]
    assert isinstance(records, list)
    records[:] = [
        row
        for row in records
        if row["observed_at"] != "2026-07-20T10:00:00+08:00"
    ]
    bars["content_hash"] = canonical_identity_hash({"records": records})
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    result = preflight_xuntou_pit_v4(bundle)
    assert result.status is XuntouPITV4PreflightStatus.INSUFFICIENT_PROVIDER_CAPABILITY
    assert result.qualification is not None
    assert "NEXT_SESSION_1030_EVIDENCE_INCOMPLETE" in result.qualification.reasons


def _qualified_bundle() -> dict[str, object]:
    decision_time = "2026-07-17T14:55:00+08:00"
    symbol = "000001.SZ"
    raw_hashes = {"raw/provider-response.json": "sha256:" + "1" * 64}
    source_hash = canonical_identity_hash({"raw_source_hashes": raw_hashes})
    sections = {
        "historical_membership": _section(
            [
                {
                    "as_of_date": "2026-07-17",
                    "symbol": symbol,
                    "is_member": True,
                    "membership_source": "XUNTOU_HISTORICAL_MEMBERSHIP",
                    "available_at": "2026-07-17T09:00:00+08:00",
                    "lookup_complete": True,
                    "source_artifact_id": source_hash,
                }
            ]
        ),
        "security_master": _section(
            [
                {
                    "symbol": symbol,
                    "effective_from": "2020-01-01T00:00:00+08:00",
                    "effective_to": None,
                    "available_at": "2026-07-17T09:00:00+08:00",
                    "lookup_complete": True,
                    "source_reference": "raw/security-master.json",
                }
            ]
        ),
        "st_history": _section(
            [
                {
                    "symbol": symbol,
                    "lookup_complete": True,
                    "available_at": "2026-07-17T09:00:00+08:00",
                    "source_reference": "raw/st-history.json",
                }
            ]
        ),
        "suspension_history": _section(
            [
                {
                    "decision_time": decision_time,
                    "symbol": symbol,
                    "trading_status": "TRADING",
                    "suspension_status": "NOT_SUSPENDED",
                    "available_at": decision_time,
                    "lookup_complete": True,
                    "source_reference": "raw/trading-status.json",
                }
            ]
        ),
        "orderability": _section(
            [
                {
                    "decision_time": decision_time,
                    "symbol": symbol,
                    "reference_price": 10.0,
                    "best_ask_price": 10.01,
                    "best_ask_volume": 1000.0,
                    "best_bid_price": 10.0,
                    "best_bid_volume": 1000.0,
                    "limit_up_price": 11.0,
                    "limit_down_price": 9.0,
                    "trading_status": "TRADING",
                    "suspension_status": "NOT_SUSPENDED",
                    "quote_observed_at": decision_time,
                    "available_at": decision_time,
                    "snapshot_finalized": True,
                    "orderability_status": "RESEARCH_ORDERABLE",
                    "orderability_reason": "DECISION_TIME_NORMAL_BUY_INTENT_ALLOWED",
                    "source_reference": "raw/decision-quote.json",
                }
            ]
        ),
        "liquidity_unit": _section(
            [
                {
                    "currency": "CNY",
                    "unit": "YUAN",
                    "scale": 1.0,
                    "aggregation": "SUM_NATIVE_PERIOD_AMOUNT",
                    "adjustment_basis": "NONE",
                    "provider_field": "amount",
                    "evidence_source": "XUNTOU_OFFICIAL_FIELD_EVIDENCE",
                }
            ]
        ),
        "bar_finality": _section(_finalized_minute_bars(symbol, decision_time)),
        "availability": _section(
            [
                {
                    "decision_time": decision_time,
                    "symbol": symbol,
                    "available_at": decision_time,
                    "source_reference": "raw/availability.json",
                }
            ]
        ),
        "evaluation_path": _section(
            [
                {
                    "decision_date": "2026-07-17",
                    "next_session_date": "2026-07-20",
                    "symbol": symbol,
                    "evaluation_time": "2026-07-20T10:30:00+08:00",
                    "evaluation_mark_id": "next-session-1030-minute-close-v1",
                    "evaluation_price": 10.05,
                    "price_rule_id": "exact-completed-1030-minute-close-v1",
                    "minute_path_complete_to_1030": True,
                    "available_at": "2026-07-20T10:31:00+08:00",
                    "finalized_at": "2026-07-20T10:31:00+08:00",
                    "missing_reason": None,
                }
            ]
        ),
    }
    return {
        "schema_version": "xuntou-pit-validation-bundle-v4",
        "mapping_contract_id": "xuntou-pit-validation-field-mapping-v4",
        "conventions": {
            "decision_bar_convention_id": "completed-1m-end-label-at-1455-v1",
            "decision_bar_label": "END_TIME",
            "decision_bar_freshness_seconds": 60,
            "availability_cutoff": "DECISION_TIME",
            "finality_required": True,
            "evaluation_mark_id": "next-session-1030-minute-close-v1",
            "evaluation_time": "10:30",
            "evaluation_price_rule_id": "exact-completed-1030-minute-close-v1",
            "missing_evaluation_policy": "MISSING_AS_CASH",
            "path_evidence_rule_id": "complete-1m-0930-through-1030-v1",
        },
        "source_artifact": {
            "provider": "XUNTOU",
            "product": "XTQUANT",
            "contract_version": "xuntou-pit-validation-bundle-v4",
            "retrieved_at": "2026-07-21T15:00:00+08:00",
            "export_started_at": "2026-07-21T14:00:00+08:00",
            "export_completed_at": "2026-07-21T14:30:00+08:00",
            "content_hash": source_hash,
            "locator_role": "EXTERNAL_IMMUTABLE_INPUT",
            "entitlement_class": "REDACTED_RESEARCH",
            "runtime_version": "authorized-runtime",
            "xtquant_version": "authorized-version",
            "timezone": "Asia/Shanghai",
            "evidence_classification": "PROVIDER_EXPORT",
        },
        "raw_source_hashes": raw_hashes,
        "evidence_scope": {"decision_times": [decision_time], "symbols": [symbol]},
        "evidence_sections": sections,
    }


def _section(records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "content_hash": canonical_identity_hash({"records": records}),
        "records": records,
    }


def _finalized_minute_bars(
    symbol: str, decision_time: str
) -> list[dict[str, object]]:
    decision_bar = _minute_bar(symbol, decision_time, "2026-07-17")
    path = [
        _minute_bar(
            symbol,
            f"2026-07-20T{total_minutes // 60:02d}:{total_minutes % 60:02d}:00+08:00",
            "2026-07-20",
        )
        for total_minutes in range(9 * 60 + 30, 10 * 60 + 31)
    ]
    return [decision_bar, *path]


def _minute_bar(
    symbol: str, observed_at: str, session_date: str
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "interval": "1m",
        "observed_at": observed_at,
        "session_date": session_date,
        "open": 10.0,
        "high": 10.1,
        "low": 9.9,
        "close": 10.05,
        "volume": 1000.0,
        "amount": 10050.0,
        "available_at": observed_at,
        "finalized_at": observed_at,
        "revision_id": "provider-final-v1",
        "revision_status": "FINAL",
        "adjustment_basis": "NONE",
        "source_reference": "raw/minute-bars.json",
    }
