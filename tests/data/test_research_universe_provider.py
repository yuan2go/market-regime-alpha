from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.providers.public_composite.research_universe import (
    BaoStockResearchUniverseClient,
    _normalize_security_master_rows,
)
from market_regime_alpha.data_sources.a_share_bars import AShareDataError
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.universe.research import (
    FreeDataEvidenceOrigin,
    ResearchUniverseMembershipStatus,
    build_free_research_universe_snapshot,
)


def test_malformed_security_master_row_with_code_is_retained_as_unknown() -> None:
    rows = _normalize_security_master_rows(
        fields=("code", "code_name", "ipoDate", "outDate", "type", "status"),
        rows=(("sz.000001", "平安银行", "1991-04-03", "", "1"),),
    )
    snapshot = build_free_research_universe_snapshot(
        as_of_date=date(2026, 8, 10),
        known_at=datetime(2026, 8, 10, 8, tzinfo=UTC),
        provider_id="provider-baostock-public",
        provider_contract="baostock-query-stock-basic-all/v1",
        source_manifest_reference=ValidationArtifactReference(
            "SOURCE_MANIFEST",
            ArtifactId("malformed-universe-manifest"),
            canonical_hash({"manifest": "malformed"}),
        ),
        raw_archive_id="malformed-universe-archive",
        evidence_origin=FreeDataEvidenceOrigin.ENGINEERING_FIXTURE,
        rows=rows,
    )

    record = snapshot.records[0]
    assert record.symbol == "000001.SZ"
    assert record.membership_status is ResearchUniverseMembershipStatus.UNKNOWN
    assert "PROVIDER_ROW_FIELD_COUNT_MISMATCH" in record.reason_codes


def test_malformed_security_master_row_without_code_fails_closed() -> None:
    with pytest.raises(AShareDataError, match="has no security code"):
        _normalize_security_master_rows(
            fields=("code", "code_name", "ipoDate"),
            rows=(("", "unknown", ""),),
        )


class _Result:
    def __init__(self, fields: tuple[str, ...], rows: tuple[tuple[str, ...], ...]):
        self.error_code = "0"
        self.error_msg = "success"
        self.fields = list(fields)
        self._rows = rows
        self._index = -1

    def next(self) -> bool:
        self._index += 1
        return self._index < len(self._rows)

    def get_row_data(self) -> list[str]:
        return list(self._rows[self._index])


def test_constituent_history_scans_sessions_and_deduplicates_effective_cohorts(
    monkeypatch,
) -> None:
    calendar = _Result(
        ("calendar_date", "is_trading_day"),
        (
            ("2025-06-13", "1"),
            ("2025-06-14", "0"),
            ("2025-06-16", "1"),
            ("2025-06-17", "1"),
        ),
    )
    responses = {
        "2025-06-13": (("2024-12-30", "sh.600000", "浦发银行"),),
        "2025-06-16": (("2025-06-16", "sz.000001", "平安银行"),),
        "2025-06-17": (("2025-06-16", "sz.000001", "平安银行"),),
    }
    security_master = _Result(
        ("code", "code_name", "ipoDate", "outDate", "type", "status"),
        (
            ("sh.600000", "浦发银行", "1999-11-10", "", "1", "1"),
            ("sz.000001", "平安银行", "1991-04-03", "", "1", "1"),
        ),
    )

    def hs300(value: str) -> _Result:
        return _Result(("updateDate", "code", "code_name"), responses[value])

    fake = SimpleNamespace(
        login=lambda **_kwargs: SimpleNamespace(error_code="0", error_msg="success"),
        logout=lambda: None,
        query_trade_dates=lambda **_kwargs: calendar,
        query_hs300_stocks=hs300,
        query_stock_basic=lambda: security_master,
    )
    monkeypatch.setitem(__import__("sys").modules, "baostock", fake)
    monkeypatch.setattr(
        "market_regime_alpha.data.providers.public_composite.research_universe.baostock_credentials",
        lambda: ("anonymous", "123456"),
    )
    current = datetime(2026, 8, 13, tzinfo=UTC)

    def clock() -> datetime:
        nonlocal current
        current += timedelta(seconds=1)
        return current

    history = BaoStockResearchUniverseClient(clock=clock).acquire_historical_constituent_history(
        start_date=date(2025, 6, 13),
        end_date=date(2025, 6, 17),
    )

    assert history.queried_trading_dates == (
        date(2025, 6, 13),
        date(2025, 6, 16),
        date(2025, 6, 17),
    )
    assert tuple(item.snapshot.constituent_effective_date for item in history.acquisitions) == (date(2024, 12, 30), date(2025, 6, 16))
    assert tuple(tuple(record.symbol for record in item.snapshot.records) for item in history.acquisitions) == (
        ("600000.SH",),
        ("000001.SZ",),
    )
    assert all(len(item.provider_result.raw_payloads) == 3 for item in history.acquisitions)
    assert len(history.scan_provider_result.raw_payloads) == 5
    assert sum(item.product == "query_hs300_stocks:session-history:v1" for item in history.scan_provider_result.raw_payloads) == 3
    constituent_sources = tuple(
        item
        for item in history.scan_provider_result.raw_payloads
        if item.product == "query_hs300_stocks:session-history:v1"
    )
    assert len({item.retrieved_time.value for item in constituent_sources}) == 3
    assert all(
        item.request_metadata.requested_at <= item.retrieved_time.value
        for item in constituent_sources
    )
    assert history.start_date == date(2025, 6, 13)
    assert history.end_date == date(2025, 6, 17)
