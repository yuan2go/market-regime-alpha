from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
import json
from pathlib import Path
import signal
import time

import pytest

import market_regime_alpha.application.historical_corpus.baostock_archive as archive_module

from market_regime_alpha.application.historical_corpus.baostock_archive import (
    BAOSTOCK_HISTORICAL_PROVIDER_ID,
    BaoStockHistoricalArchiveClient,
)
from market_regime_alpha.application.historical_corpus.artifacts import (
    load_verified_historical_package,
)
from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalArtifactKind,
    HistoricalDataPartition,
    HISTORICAL_PARTITION_SCHEMA_V1,
    HISTORICAL_PARTITION_SCHEMA_V2,
    HistoricalRawRequest,
    HistoricalTradingStatus,
    build_partitions,
)
from market_regime_alpha.application.historical_corpus.normalization import (
    HistoricalNormalizationError,
    normalize_baostock_archive,
    normalize_historical_package,
)
from market_regime_alpha.data_sources.a_share_bars import AShareDataError
from market_regime_alpha.evidence.canonical import canonical_hash, canonical_json
from market_regime_alpha.market_data.contracts import Timeframe
from tests.application.historical_corpus.support import raw_owner, raw_request


@dataclass
class _Response:
    fields: list[str]
    rows: list[list[str]]
    error_code: str = "0"
    error_msg: str = ""
    index: int = -1

    def next(self) -> bool:
        self.index += 1
        return self.index < len(self.rows)

    def get_row_data(self) -> list[str]:
        return self.rows[self.index]


class _FakeBaoStock:
    def __init__(self) -> None:
        self.queries: list[dict[str, str]] = []

    def login(self, **_: str) -> _Response:
        return _Response([], [])

    def logout(self) -> _Response:
        return _Response([], [])

    def query_history_k_data_plus(
        self,
        code: str,
        fields: str,
        **parameters: str,
    ) -> _Response:
        self.queries.append({"code": code, "fields": fields, **parameters})
        names = fields.split(",")
        if parameters["frequency"] == "d":
            values = {
                "date": f"{parameters['start_date'][:4]}-01-03",
                "code": code,
                "open": "10",
                "high": "10.5",
                "low": "9.8",
                "close": "10.2",
                "volume": "100000",
                "amount": "1020000",
                "adjustflag": "3",
                "tradestatus": "1",
                "isST": "0",
            }
        else:
            values = {
                "date": f"{parameters['start_date'][:4]}-01-03",
                "time": f"{parameters['start_date'][:4]}0103093500000",
                "code": code,
                "open": "10",
                "high": "10.2",
                "low": "9.9",
                "close": "10.1",
                "volume": "1000",
                "amount": "10100",
                "adjustflag": "3",
            }
        return _Response(names, [[values[name] for name in names]])


class _IncompletePagedBaoStock(_FakeBaoStock):
    def query_history_k_data_plus(
        self,
        code: str,
        fields: str,
        **parameters: str,
    ) -> _Response:
        response = super().query_history_k_data_plus(
            code,
            fields,
            **parameters,
        )
        response.data = [["partial"]] * 2_000  # type: ignore[attr-defined]
        response.per_page_count = 2_000  # type: ignore[attr-defined]
        response.cur_row_num = 2_000  # type: ignore[attr-defined]
        response.rows = []
        return response


class _FailOnceBaoStock(_FakeBaoStock):
    def __init__(self, fail_at: int) -> None:
        super().__init__()
        self._fail_at = fail_at

    def query_history_k_data_plus(
        self,
        code: str,
        fields: str,
        **parameters: str,
    ) -> _Response:
        if len(self.queries) + 1 == self._fail_at:
            self.queries.append({"code": code, "fields": fields, **parameters})
            return _Response([], [], error_code="10002007", error_msg="transport")
        return super().query_history_k_data_plus(code, fields, **parameters)


class _HangingLoginBaoStock(_FakeBaoStock):
    def login(self, **_: str) -> _Response:
        time.sleep(1)
        return _Response([], [])


class _FailingLoginBaoStock(_FakeBaoStock):
    def login(self, **_: str) -> _Response:
        raise AssertionError("complete checkpoint recovery must not log in")


class _AuthenticationExpiresOnceBaoStock(_FakeBaoStock):
    def __init__(self) -> None:
        super().__init__()
        self.login_count = 0
        self.expired = False

    def login(self, **_: str) -> _Response:
        self.login_count += 1
        return _Response([], [])

    def query_history_k_data_plus(
        self,
        code: str,
        fields: str,
        **parameters: str,
    ) -> _Response:
        if not self.expired:
            self.expired = True
            return _Response([], [], error_code="10001001", error_msg="用户未登录")
        return super().query_history_k_data_plus(code, fields, **parameters)


def test_package_acquisition_resumes_without_network_and_normalizes_by_partition(
    tmp_path: Path,
) -> None:
    retrieved_at = datetime(2026, 8, 12, 3, 0, tzinfo=UTC)
    values = {
        "symbols": ("600000.SH",),
        "start_date": date(2025, 1, 1),
        "end_date": date(2025, 1, 31),
        "artifact_root": tmp_path / "artifacts",
        "checkpoint_root": tmp_path / "checkpoints",
        "acquisition_id": "bounded-package-v1",
        "bucket_count": 4,
    }
    provider = _FakeBaoStock()
    first = BaoStockHistoricalArchiveClient(
        clock=lambda: retrieved_at,
        baostock_module=provider,
    ).acquire_to_package(**values)
    query_count = len(provider.queries)

    replayed = BaoStockHistoricalArchiveClient(
        clock=lambda: retrieved_at,
        baostock_module=_FailingLoginBaoStock(),
    ).acquire_to_package(**values)
    normalized = normalize_historical_package(
        raw=first,
        artifact_root=tmp_path / "artifacts",
    )

    assert len(provider.queries) == query_count
    assert replayed.reference == first.reference
    assert replayed.physical_hash == first.physical_hash
    assert normalized.parent_reference == first.reference
    raw_owner_value = load_verified_historical_package(first.root).owner
    expected_normalized = normalize_baostock_archive(raw_owner_value)
    assert normalized.reference == expected_normalized.reference
    assert load_verified_historical_package(normalized.root).owner == expected_normalized


def test_acquisition_splits_requests_by_year_and_preserves_true_retrieval() -> None:
    provider = _FakeBaoStock()
    retrieved_at = datetime(2026, 8, 12, 3, 0, tzinfo=UTC)
    owner = BaoStockHistoricalArchiveClient(
        clock=lambda: retrieved_at,
        baostock_module=provider,
    ).acquire(
        symbols=("600000.SH",),
        start_date=date(2023, 1, 1),
        end_date=date(2024, 12, 31),
        timeframes=(Timeframe.DAILY, Timeframe.MINUTE_5),
        bucket_count=4,
    )

    assert owner.artifact_kind is HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE
    assert owner.provider_id == BAOSTOCK_HISTORICAL_PROVIDER_ID
    assert owner.retrieved_at == retrieved_at
    assert owner.coverage.expected_request_count == 26
    assert owner.coverage.source_row_count == 26
    assert owner.first_market_date == date(2023, 1, 1)
    assert owner.last_market_date == date(2024, 12, 31)
    assert all(
        partition.first_market_date == date(partition.first_market_date.year, 1, 1)
        and partition.last_market_date
        == date(partition.first_market_date.year, 12, 31)
        for partition in owner.partitions
        if partition.timeframe is Timeframe.DAILY
    )
    assert all(
        partition.first_market_date.day == 1
        and partition.last_market_date.month
        == partition.first_market_date.month
        for partition in owner.partitions
        if partition.timeframe is Timeframe.MINUTE_5
    )
    assert len(provider.queries) == 26
    requests = tuple(
        record for partition in owner.partitions for record in partition.records
    )
    assert all(isinstance(item, HistoricalRawRequest) for item in requests)
    assert all(item.retrieved_at == retrieved_at for item in requests)
    assert all(
        "BAOSTOCK_LIBRARY_RESULT_REENCODED_NOT_TRANSPORT_BYTES"
        in item.limitations
        for item in requests
        if isinstance(item, HistoricalRawRequest)
    )


def test_acquisition_uses_exact_per_timeframe_windows() -> None:
    provider = _FakeBaoStock()
    retrieved_at = datetime(2026, 8, 12, 3, 0, tzinfo=UTC)

    owner = BaoStockHistoricalArchiveClient(
        clock=lambda: retrieved_at,
        baostock_module=provider,
    ).acquire(
        symbols=("600000.SH",),
        start_date=date(2025, 1, 1),
        end_date=date(2026, 7, 14),
        timeframes=(Timeframe.DAILY, Timeframe.MINUTE_5),
        timeframe_ranges={
            Timeframe.DAILY: (date(2025, 1, 1), date(2026, 7, 14)),
            Timeframe.MINUTE_5: (date(2026, 6, 14), date(2026, 7, 14)),
        },
        bucket_count=4,
    )

    assert owner.coverage.expected_request_count == 4
    minute_queries = [
        item for item in provider.queries if item["frequency"] == "5"
    ]
    assert minute_queries == [
        {
            "code": "sh.600000",
            "fields": "date,time,code,open,high,low,close,volume,amount,adjustflag",
            "start_date": "2026-06-14",
            "end_date": "2026-06-30",
            "frequency": "5",
            "adjustflag": "3",
        },
        {
            "code": "sh.600000",
            "fields": "date,time,code,open,high,low,close,volume,amount,adjustflag",
            "start_date": "2026-07-01",
            "end_date": "2026-07-14",
            "frequency": "5",
            "adjustflag": "3",
        },
    ]
    assert len(provider.queries) == 4
    requests = tuple(
        record for partition in owner.partitions for record in partition.records
    )
    assert all(isinstance(item, HistoricalRawRequest) for item in requests)
    assert all(item.retrieved_at == retrieved_at for item in requests)
    assert all(
        "BAOSTOCK_LIBRARY_RESULT_REENCODED_NOT_TRANSPORT_BYTES"
        in item.limitations
        for item in requests
        if isinstance(item, HistoricalRawRequest)
    )


def test_acquisition_fails_closed_on_incomplete_provider_pagination() -> None:
    with pytest.raises(AShareDataError, match="partial corpus is not publishable"):
        BaoStockHistoricalArchiveClient(
            clock=lambda: datetime(2026, 8, 12, 3, 0, tzinfo=UTC),
            baostock_module=_IncompletePagedBaoStock(),
        ).acquire(
            symbols=("600000.SH",),
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            bucket_count=4,
        )


def test_acquisition_checkpoints_completed_requests_for_exact_resume(
    tmp_path,
) -> None:
    provider = _FakeBaoStock()
    client = BaoStockHistoricalArchiveClient(
        clock=lambda: datetime(2026, 8, 12, 3, 0, tzinfo=UTC),
        baostock_module=provider,
    )
    values = {
        "symbols": ("600000.SH",),
        "start_date": date(2025, 1, 1),
        "end_date": date(2025, 1, 31),
        "bucket_count": 4,
        "checkpoint_root": tmp_path / "checkpoints",
        "acquisition_id": "checkpoint-repeat-v1",
    }

    first = client.acquire(**values)
    query_count = len(provider.queries)
    repeated = client.acquire(**values)

    assert repeated == first
    assert len(provider.queries) == query_count
    checkpoints = tuple(
        path
        for path in (tmp_path / "checkpoints").glob("*/*.json")
        if path.name != "acquisition-manifest.json"
    )
    assert len(checkpoints) == 2
    checkpoints[0].write_text("{}\n", encoding="utf-8")
    with pytest.raises(AShareDataError, match="identity drift"):
        client.acquire(**values)


def test_complete_checkpoint_recovery_does_not_require_provider_login(
    tmp_path,
) -> None:
    retrieved_at = datetime(2026, 8, 12, 3, 0, tzinfo=UTC)
    values = {
        "symbols": ("600000.SH",),
        "start_date": date(2025, 1, 1),
        "end_date": date(2025, 1, 31),
        "bucket_count": 4,
        "checkpoint_root": tmp_path,
        "acquisition_id": "offline-owner-publication-v1",
    }
    expected = BaoStockHistoricalArchiveClient(
        clock=lambda: retrieved_at,
        baostock_module=_FakeBaoStock(),
    ).acquire(**values)

    recovered = BaoStockHistoricalArchiveClient(
        clock=lambda: retrieved_at,
        baostock_module=_FailingLoginBaoStock(),
    ).acquire(**values)

    assert recovered == expected


def test_acquisition_resumes_after_transport_interruption_with_exact_owner(
    tmp_path,
) -> None:
    retrieved_at = datetime(2026, 8, 12, 3, 0, tzinfo=UTC)
    interrupted_provider = _FailOnceBaoStock(fail_at=2)
    values = {
        "symbols": ("600000.SH",),
        "start_date": date(2025, 1, 1),
        "end_date": date(2025, 2, 28),
        "bucket_count": 4,
    }
    with pytest.raises(AShareDataError, match="partial corpus is not publishable"):
        BaoStockHistoricalArchiveClient(
            clock=lambda: retrieved_at,
            baostock_module=interrupted_provider,
        ).acquire(
            **values,
            checkpoint_root=tmp_path / "resumed",
            acquisition_id="interrupted-resume-v1",
        )

    resumed_provider = _FakeBaoStock()
    resumed = BaoStockHistoricalArchiveClient(
        clock=lambda: retrieved_at,
        baostock_module=resumed_provider,
    ).acquire(
        **values,
        checkpoint_root=tmp_path / "resumed",
        acquisition_id="interrupted-resume-v1",
    )
    uninterrupted = BaoStockHistoricalArchiveClient(
        clock=lambda: retrieved_at,
        baostock_module=_FakeBaoStock(),
    ).acquire(
        **values,
        checkpoint_root=tmp_path / "uninterrupted",
        acquisition_id="uninterrupted-v1",
    )

    assert resumed == uninterrupted
    assert len(resumed_provider.queries) == 2


def test_concurrent_checkpoint_accepts_valid_winner_with_different_clock(
    tmp_path,
    monkeypatch,
) -> None:
    provider = _FakeBaoStock()
    loser_client = BaoStockHistoricalArchiveClient(
        clock=lambda: datetime(2026, 8, 12, 3, 0, tzinfo=UTC),
        baostock_module=provider,
    )
    winner = BaoStockHistoricalArchiveClient(
        clock=lambda: datetime(2026, 8, 12, 3, 1, tzinfo=UTC),
        baostock_module=provider,
    )._timed_acquire_one(  # noqa: SLF001
        bs=provider,
        symbol="600000.SH",
        timeframe=Timeframe.DAILY,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )

    def concurrent_link(source: str, destination: str) -> None:
        loser_payload = json.loads(open(source, encoding="utf-8").read())  # noqa: PTH123, SIM115
        envelope = {
            "schema_version": loser_payload["schema_version"],
            "request_identity": loser_payload["request_identity"],
            "response": winner.to_canonical_dict(),
        }
        with open(destination, "w", encoding="utf-8") as handle:  # noqa: PTH123
            handle.write(
                canonical_json(
                    {**envelope, "checkpoint_hash": canonical_hash(envelope)}
                )
            )
            handle.write("\n")
        raise FileExistsError

    monkeypatch.setattr(archive_module.os, "link", concurrent_link)
    actual = loser_client._checkpointed_acquire_one(  # noqa: SLF001
        checkpoint_root=tmp_path,
        bs=provider,
        symbol="600000.SH",
        timeframe=Timeframe.DAILY,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )

    assert actual == winner
    assert actual.retrieved_at != datetime(2026, 8, 12, 3, 0, tzinfo=UTC)


def test_acquisition_enforces_request_and_row_ceilings() -> None:
    with pytest.raises(ValueError, match="request ceiling"):
        BaoStockHistoricalArchiveClient(
            baostock_module=_FakeBaoStock(),
            maximum_source_requests=1,
        ).acquire(
            symbols=("600000.SH",),
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
    with pytest.raises(AShareDataError, match="row ceiling"):
        BaoStockHistoricalArchiveClient(
            baostock_module=_FakeBaoStock(),
            maximum_source_rows=1,
        ).acquire(
            symbols=("600000.SH",),
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )


@pytest.mark.skipif(not hasattr(signal, "setitimer"), reason="requires SIGALRM")
def test_acquisition_bounds_login_wall_clock() -> None:
    with pytest.raises(AShareDataError, match="login timed out"):
        BaoStockHistoricalArchiveClient(
            baostock_module=_HangingLoginBaoStock(),
            timeout_seconds=0.01,
        ).acquire(
            symbols=("600000.SH",),
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )


def test_acquisition_reauthenticates_once_without_archiving_auth_failure(
    tmp_path,
) -> None:
    provider = _AuthenticationExpiresOnceBaoStock()
    owner = BaoStockHistoricalArchiveClient(
        baostock_module=provider,
    ).acquire(
        symbols=("600000.SH",),
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        checkpoint_root=tmp_path,
        acquisition_id="reauthentication-v1",
    )

    assert provider.login_count == 2
    assert owner.coverage.successful_request_count == 2
    assert all(
        item.provider_error_code != "10001001"
        for partition in owner.partitions
        for item in partition.records
        if isinstance(item, HistoricalRawRequest)
    )


def test_checkpoint_scope_isolated_by_explicit_acquisition_id(tmp_path) -> None:
    provider = _FakeBaoStock()
    client = BaoStockHistoricalArchiveClient(baostock_module=provider)
    values = {
        "symbols": ("600000.SH",),
        "start_date": date(2025, 1, 1),
        "end_date": date(2025, 1, 31),
        "checkpoint_root": tmp_path,
    }

    client.acquire(**values, acquisition_id="experiment-a")
    first_query_count = len(provider.queries)
    client.acquire(**values, acquisition_id="experiment-b")

    assert len(provider.queries) == first_query_count * 2
    assert len(tuple(tmp_path.glob("*/acquisition-manifest.json"))) == 2


def test_normalization_preserves_retrieval_clock_and_missingness() -> None:
    provider = _FakeBaoStock()
    retrieved_at = datetime(2026, 8, 12, 3, 0, tzinfo=UTC)
    raw = BaoStockHistoricalArchiveClient(
        clock=lambda: retrieved_at,
        baostock_module=provider,
    ).acquire(
        symbols=("600000.SH",),
        start_date=date(2023, 1, 1),
        end_date=date(2023, 12, 31),
        bucket_count=4,
    )

    normalized = normalize_baostock_archive(raw)
    bars = tuple(
        record for partition in normalized.partitions for record in partition.records
    )

    assert normalized.parent_reference == raw.reference
    assert normalized.created_at == raw.created_at
    assert normalized.coverage.normalized_row_count == 2
    assert all(item.retrieved_at == retrieved_at for item in bars)
    daily = next(item for item in bars if item.timeframe is Timeframe.DAILY)
    minute = next(item for item in bars if item.timeframe is Timeframe.MINUTE_5)
    assert daily.event_end == datetime(2023, 1, 3, 7, 0, tzinfo=UTC)
    assert minute.event_end == datetime(2023, 1, 3, 1, 35, tzinfo=UTC)
    assert daily.trading_status is HistoricalTradingStatus.TRADING
    assert daily.st_status is False
    assert minute.st_status is None
    assert ("ST_STATUS", 1) in normalized.coverage.missing_field_counts
    assert ("LISTING_STATUS", 2) in normalized.coverage.missing_field_counts


def test_legacy_raw_partition_replays_start_date_projection() -> None:
    request = raw_request()
    legacy = HistoricalDataPartition.create(
        artifact_kind=HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE,
        timeframe=request.timeframe,
        symbol_bucket=build_partitions(
            artifact_kind=HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE,
            records=(request,),
            bucket_count=4,
        )[0].symbol_bucket,
        bucket_count=4,
        records=(request,),
        schema_version=HISTORICAL_PARTITION_SCHEMA_V1,
    )

    assert legacy.first_market_date == request.start_date
    assert legacy.last_market_date == request.start_date
    assert "schema_version" not in legacy.reference_dict()
    assert (
        HistoricalDataPartition.from_reference_dict(
            legacy.reference_dict(),
            records=(request,),
        )
        == legacy
    )


def test_pre_e3_raw_intraday_partition_path_remains_replayable() -> None:
    request = raw_request(timeframe=Timeframe.MINUTE_5)
    bucket = build_partitions(
        artifact_kind=HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE,
        records=(request,),
        bucket_count=4,
    )[0].symbol_bucket
    legacy = HistoricalDataPartition.create(
        artifact_kind=HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE,
        timeframe=request.timeframe,
        symbol_bucket=bucket,
        bucket_count=4,
        records=(request,),
        schema_version=HISTORICAL_PARTITION_SCHEMA_V2,
    )

    assert "/month=" not in legacy.relative_path
    assert (
        HistoricalDataPartition.from_reference_dict(
            legacy.reference_dict(),
            records=(request,),
        )
        == legacy
    )

def test_suspension_is_not_silently_price_filled() -> None:
    request = HistoricalRawRequest.create(
        provider_id=BAOSTOCK_HISTORICAL_PROVIDER_ID,
        product="query_history_k_data_plus:d:adjustflag=3",
        symbol="600000.SH",
        timeframe=Timeframe.DAILY,
        start_date=date(2023, 1, 1),
        end_date=date(2023, 12, 31),
        request_parameters=(("frequency", "d"),),
        requested_at=datetime(2026, 8, 12, 2, 0, tzinfo=UTC),
        retrieved_at=datetime(2026, 8, 12, 2, 0, tzinfo=UTC),
        fields=(
            "date", "code", "open", "high", "low", "close", "volume",
            "amount", "adjustflag", "tradestatus", "isST",
        ),
        rows=((
            "2023-01-03", "sh.600000", "", "", "", "", "0", "0",
            "3", "0", "0",
        ),),
    )
    raw = raw_owner(request=request)
    # Test support uses a legacy provider id; bind the same immutable payload to
    # the BaoStock product identity required by the normalizer.
    raw = type(raw).create(
        artifact_kind=raw.artifact_kind,
        provider_id=BAOSTOCK_HISTORICAL_PROVIDER_ID,
        normalization_version=None,
        parent_reference=None,
        created_at=raw.created_at,
        retrieved_at=raw.retrieved_at,
        first_market_date=raw.first_market_date,
        last_market_date=raw.last_market_date,
        bucket_count=raw.bucket_count,
        partitions=raw.partitions,
        coverage=raw.coverage,
        limitations=raw.limitations,
    )

    normalized = normalize_baostock_archive(raw)
    bar = normalized.partitions[0].records[0]

    assert bar.trading_status is HistoricalTradingStatus.SUSPENDED
    assert (bar.open, bar.high, bar.low, bar.close) == (None, None, None, None)
    assert "OHLC" in bar.missing_fields


def test_duplicate_event_facts_fail_normalization() -> None:
    first = raw_request()
    duplicate = HistoricalRawRequest.create(
        provider_id=first.provider_id,
        product=first.product,
        symbol=first.symbol,
        timeframe=first.timeframe,
        start_date=first.start_date,
        end_date=first.end_date,
        request_parameters=(*first.request_parameters, ("retry", "1")),
        requested_at=first.requested_at,
        retrieved_at=first.retrieved_at,
        fields=first.fields,
        rows=first.rows,
        limitations=first.limitations,
    )
    partitions = build_partitions(
        artifact_kind=HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE,
        records=(first, duplicate),
        bucket_count=4,
    )
    template = raw_owner(request=first)
    raw = type(template).create(
        artifact_kind=template.artifact_kind,
        provider_id=BAOSTOCK_HISTORICAL_PROVIDER_ID,
        normalization_version=None,
        parent_reference=None,
        created_at=template.created_at,
        retrieved_at=template.retrieved_at,
        first_market_date=partitions[0].first_market_date,
        last_market_date=partitions[-1].last_market_date,
        bucket_count=4,
        partitions=partitions,
        coverage=template.coverage,
        limitations=template.limitations,
    )

    with pytest.raises(HistoricalNormalizationError, match="duplicate"):
        normalize_baostock_archive(raw)
