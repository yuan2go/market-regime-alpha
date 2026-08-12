from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from market_regime_alpha.application.shadow_research.free_data_settlement import (
    FreeOutcomeDatasetBuilder,
    _resolve_operation_package,
)
from market_regime_alpha.application.shadow_research.operations import (
    _feature_lineage_matches,
)
from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.data_sources.a_share_bars import AShareDataError
from market_regime_alpha.market_data.contracts import Timeframe


class _Provider:
    name = "fixture"
    data_source = "fixture"
    is_realtime = False

    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.calls: list[tuple[str, str]] = []

    def minute_bars(self, symbol: str, *, freq: str, start_date: str, end_date: str):
        del start_date, end_date
        self.calls.append((symbol, freq))
        result = self.frame.copy()
        result["symbol"] = symbol
        return result


class _PerSymbolProvider(_Provider):
    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self.frames = frames
        self.calls = []

    def minute_bars(self, symbol: str, *, freq: str, start_date: str, end_date: str):
        del start_date, end_date
        self.calls.append((symbol, freq))
        result = self.frames[symbol].copy()
        result["symbol"] = symbol
        return result


class _NoDataErrorProvider(_PerSymbolProvider):
    def minute_bars(self, symbol: str, *, freq: str, start_date: str, end_date: str):
        if symbol == "000002.SZ":
            raise AShareDataError("data source returned no rows")
        return super().minute_bars(
            symbol,
            freq=freq,
            start_date=start_date,
            end_date=end_date,
        )


def test_current_session_outcome_builds_post_close_baostock_five_minute_dataset(tmp_path) -> None:
    frame = _frame(("2026-08-10 09:35:00", "2026-08-10 10:30:00", "2026-08-10 15:00:00"))
    historical = _Provider(frame)
    builder = FreeOutcomeDatasetBuilder(
        clock=lambda: datetime(2026, 8, 10, 7, 5, tzinfo=UTC),
        historical_provider=historical,
    )

    result = builder.acquire(
        symbols=("000001.SZ",),
        next_session_date=date(2026, 8, 10),
        output_root=tmp_path,
    )
    replayed = builder.acquire(
        symbols=("000001.SZ",),
        next_session_date=date(2026, 8, 10),
        output_root=tmp_path,
    )

    assert result.minute_timeframe is Timeframe.MINUTE_5
    assert historical.calls == [("000001.SZ", "5min"), ("000001.SZ", "5min")]
    assert result.dataset.artifact == replayed.dataset.artifact
    assert result.source_archive == replayed.source_archive
    assert {item.timeframe for item in result.dataset.bars} == {Timeframe.MINUTE_5, Timeframe.DAILY}
    assert all(
        item.event_end <= datetime(2026, 8, 10, 7, 0, tzinfo=UTC)
        for item in result.dataset.bars
        if item.timeframe is Timeframe.MINUTE_5
    )
    assert result.dataset.artifact.formal_pit_status.value == "FORMAL_PIT_NOT_ESTABLISHED"
    assert "FREE_DATA_EXPLORATORY" in result.dataset.artifact.limitations


def test_missed_session_uses_baostock_five_minute_without_inventing_one_minute(tmp_path) -> None:
    frame = _frame(("2026-08-07 09:35:00", "2026-08-07 10:30:00", "2026-08-07 15:00:00"))
    historical = _Provider(frame)
    result = FreeOutcomeDatasetBuilder(
        clock=lambda: datetime(2026, 8, 10, 7, 5, tzinfo=UTC),
        historical_provider=historical,
    ).acquire(
        symbols=("000001.SZ",),
        next_session_date=date(2026, 8, 7),
        output_root=tmp_path,
    )

    assert result.minute_timeframe is Timeframe.MINUTE_5
    assert historical.calls == [("000001.SZ", "5min")]
    assert Timeframe.MINUTE_1 not in {item.timeframe for item in result.dataset.bars}


def test_outcome_acquisition_retains_missing_symbol_as_partial_coverage(
    tmp_path,
) -> None:
    available = _frame(
        (
            "2026-08-07 09:35:00",
            "2026-08-07 10:30:00",
            "2026-08-07 15:00:00",
        )
    )
    missing = available.iloc[0:0]
    provider = _PerSymbolProvider(
        {"000001.SZ": available, "000002.SZ": missing}
    )

    result = FreeOutcomeDatasetBuilder(
        clock=lambda: datetime(2026, 8, 10, 7, 5, tzinfo=UTC),
        historical_provider=provider,
    ).acquire(
        symbols=("000001.SZ", "000002.SZ"),
        next_session_date=date(2026, 8, 7),
        output_root=tmp_path,
    )

    assert result.dataset.artifact.coverage.state.value == "PARTIAL"
    assert result.dataset.artifact.coverage.missing_symbol_timeframes == (
        "000002.SZ|DAILY",
        "000002.SZ|MINUTE_5",
    )
    assert "PARTIAL_SYMBOL_COVERAGE_EXPLICIT" in (
        result.dataset.artifact.limitations
    )


def test_outcome_acquisition_classifies_baostock_no_rows_as_missing(
    tmp_path,
) -> None:
    available = _frame(
        (
            "2026-08-07 09:35:00",
            "2026-08-07 10:30:00",
            "2026-08-07 15:00:00",
        )
    )
    provider = _NoDataErrorProvider(
        {"000001.SZ": available, "000002.SZ": available}
    )

    result = FreeOutcomeDatasetBuilder(
        clock=lambda: datetime(2026, 8, 10, 7, 5, tzinfo=UTC),
        historical_provider=provider,
    ).acquire(
        symbols=("000001.SZ", "000002.SZ"),
        next_session_date=date(2026, 8, 7),
        output_root=tmp_path,
    )

    assert result.dataset.artifact.coverage.missing_symbol_timeframes == (
        "000002.SZ|DAILY",
        "000002.SZ|MINUTE_5",
    )


def test_outcome_acquisition_does_not_reclassify_provider_failure(
    tmp_path,
) -> None:
    class FailedProvider(_Provider):
        def minute_bars(
            self,
            symbol: str,
            *,
            freq: str,
            start_date: str,
            end_date: str,
        ):
            raise AShareDataError("BaoStock login failed: unavailable")

    builder = FreeOutcomeDatasetBuilder(
        clock=lambda: datetime(2026, 8, 10, 7, 5, tzinfo=UTC),
        historical_provider=FailedProvider(_frame(("2026-08-07 09:35:00",))),
    )

    with pytest.raises(AShareDataError, match="login failed"):
        builder.acquire(
            symbols=("000001.SZ",),
            next_session_date=date(2026, 8, 7),
            output_root=tmp_path,
        )


def test_current_session_outcome_fails_closed_before_market_close(tmp_path) -> None:
    frame = _frame(("2026-08-10 09:30:00", "2026-08-10 10:29:00"))
    builder = FreeOutcomeDatasetBuilder(
        clock=lambda: datetime(2026, 8, 10, 6, 59, tzinfo=UTC),
        historical_provider=_Provider(frame),
    )

    with pytest.raises(ValueError, match="requires the 15:00 close"):
        builder.acquire(
            symbols=("000001.SZ",),
            next_session_date=date(2026, 8, 10),
            output_root=tmp_path,
        )


def test_separate_acquisitions_never_reuse_a_mutable_source_identity(tmp_path) -> None:
    frame = _frame(("2026-08-07 09:35:00", "2026-08-07 15:00:00"))
    clock = [datetime(2026, 8, 10, 7, 5, tzinfo=UTC)]
    builder = FreeOutcomeDatasetBuilder(
        clock=lambda: clock[0],
        historical_provider=_Provider(frame),
    )
    first = builder.acquire(
        symbols=("000001.SZ",),
        next_session_date=date(2026, 8, 7),
        output_root=tmp_path,
    )
    clock[0] = datetime(2026, 8, 10, 7, 6, tzinfo=UTC)
    second = builder.acquire(
        symbols=("000001.SZ",),
        next_session_date=date(2026, 8, 7),
        output_root=tmp_path,
    )

    assert first.source_archive.entries[0].source_artifact_id != (
        second.source_archive.entries[0].source_artifact_id
    )


def test_controlled_package_resolution_uses_frozen_package_identity(
    tmp_path,
    monkeypatch,
) -> None:
    package_dir = tmp_path / "run" / "operation-packages" / "package"
    package_dir.mkdir(parents=True)
    package = SimpleNamespace(
        package_id=ArtifactId("controlled-package-id"),
        content_hash=canonical_hash({"package": 1}),
        created_at=datetime(2026, 8, 10, 7, tzinfo=UTC),
        command=SimpleNamespace(run_id=ArtifactId("controlled-run-id")),
    )
    monkeypatch.setattr(
        "market_regime_alpha.application.shadow_research.free_data_settlement.load_controlled_operation_package",
        lambda _path: package,
    )

    resolved, run_root = _resolve_operation_package(
        tmp_path,
        ArtifactId("controlled-package-id"),
        locator=SimpleNamespace(
            get_by_package_id=lambda _package_id: SimpleNamespace(
                package_locator=(
                    "artifact-root-v1/run/operation-packages/package"
                ),
                package_hash=package.content_hash,
                operation_run_id=package.command.run_id,
            )
        ),
    )

    assert resolved is package
    assert run_root == tmp_path / "run"


def test_feature_lineage_accepts_current_v2_and_verified_legacy_wrapper() -> None:
    bundle_hash = canonical_hash({"feature": "v2"})
    wrapper_hash = canonical_hash({"feature": "legacy-wrapper"})
    feature = SimpleNamespace(
        artifact=SimpleNamespace(
            bundle_id=ArtifactId("feature-bundle-v2"),
            content_hash=bundle_hash,
        )
    )
    wrapper = SimpleNamespace(
        artifact_id=ArtifactId("static-feature-wrapper"),
        content_hash=wrapper_hash,
        feature_bundle_id=ArtifactId("feature-bundle-v2"),
        feature_bundle_hash=bundle_hash,
    )

    assert _feature_lineage_matches(
        RuntimeArtifactReference(
            "FEATURE_BUNDLE_V2",
            ArtifactId("feature-bundle-v2"),
            bundle_hash,
        ),
        feature,
        None,
    )
    assert _feature_lineage_matches(
        RuntimeArtifactReference(
            "STATIC_FEATURE_BUNDLE",
            ArtifactId("static-feature-wrapper"),
            wrapper_hash,
        ),
        feature,
        wrapper,
    )


def _frame(timestamps: tuple[str, ...]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["000001.SZ"] * len(timestamps),
            "timestamp": pd.to_datetime(list(timestamps)),
            "open": [10.0] * len(timestamps),
            "high": [10.1] * len(timestamps),
            "low": [9.9] * len(timestamps),
            "close": [10.05] * len(timestamps),
            "volume": [1000.0] * len(timestamps),
            "amount": [10000.0] * len(timestamps),
            "source_freq": ["1min"] * len(timestamps),
        }
    )
