"""Fail-closed builder for a small, real-data-ready MACD rehearsal dataset.

It deliberately accepts only ``REHEARSAL`` inputs.  It is a data-contract
validator and manifest producer, not a source-specific compatibility layer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from .macd import PriceAdjustmentMode
from .macd_experiments import canonical_json
from .macd_oos import DatasetClassification, DatasetManifest, build_dataset_manifest


FORMAL_DATASET_BUILDER_VERSION = "formal-dataset-builder-mvp-v1"


class FormalDatasetBuildError(ValueError):
    """A blocking formal-data contract failure; never silently repaired."""


@dataclass(frozen=True)
class FormalDatasetSidecars:
    trading_calendar_path: Path
    universe_path: Path
    corporate_actions_path: Path
    suspensions_path: Path
    eligibility_path: Path
    market_context_path: Path


@dataclass(frozen=True)
class FormalDatasetBuildRequest:
    bar_paths: tuple[Path, ...]
    data_source: str
    price_adjustment_mode: PriceAdjustmentMode
    pit_adjustment_complete: bool
    trading_calendar_version: str
    sidecars: FormalDatasetSidecars


@dataclass(frozen=True)
class FormalDatasetQualityReport:
    builder_version: str
    symbol_count: int
    calendar_span_days: int
    finalized_bar_count: int
    blocking_reasons: tuple[str, ...]


@dataclass(frozen=True)
class FormalDatasetBuildResult:
    manifest: DatasetManifest
    quality: FormalDatasetQualityReport


def build_rehearsal_dataset(request: FormalDatasetBuildRequest) -> FormalDatasetBuildResult:
    """Validate a 5–10 symbol, 3–6 month, finalized/PIT rehearsal input.

    All evidence must be explicit in the provided files.  This function does
    not fetch data, infer Tencent labels, manufacture VWAP, or upgrade a CSV.
    """

    import pandas as pd

    if not request.bar_paths:
        raise FormalDatasetBuildError("BAR_PATHS_REQUIRED")
    if not isinstance(request.price_adjustment_mode, PriceAdjustmentMode):
        raise FormalDatasetBuildError("PRICE_ADJUSTMENT_MODE_REQUIRED")
    if request.price_adjustment_mode is not PriceAdjustmentMode.POINT_IN_TIME_ADJUSTED or not request.pit_adjustment_complete:
        raise FormalDatasetBuildError("PIT_ADJUSTMENT_REQUIRED")
    for path in (*request.bar_paths, *asdict(request.sidecars).values()):
        if not Path(path).is_file():
            raise FormalDatasetBuildError(f"INPUT_FILE_MISSING:{path}")

    frames = [_read_bars(Path(path)) for path in request.bar_paths]
    data = pd.concat(frames, ignore_index=True)
    _validate_bar_columns(data)
    symbols = tuple(sorted(data["symbol"].astype(str).unique()))
    if not 5 <= len(symbols) <= 10:
        raise FormalDatasetBuildError("MVP_SYMBOL_COUNT_MUST_BE_5_TO_10")
    calendar = _load_object(request.sidecars.trading_calendar_path, "TRADING_CALENDAR_INVALID")
    dates = _calendar_dates_with_session_close(calendar)
    span = (pd.Timestamp(max(dates)) - pd.Timestamp(min(dates))).days
    if not 90 <= span <= 184:
        raise FormalDatasetBuildError("MVP_CALENDAR_SPAN_MUST_BE_3_TO_6_MONTHS")
    _validate_sidecar_coverage(data, symbols, dates, request.sidecars)

    manifest = build_dataset_manifest(
        request.bar_paths,
        data_source=request.data_source,
        price_adjustment_mode=request.price_adjustment_mode,
        pit_adjustment_complete=request.pit_adjustment_complete,
        trading_calendar_version=request.trading_calendar_version,
        trading_calendar_path=request.sidecars.trading_calendar_path,
        universe_path=request.sidecars.universe_path,
        corporate_actions_path=request.sidecars.corporate_actions_path,
        suspensions_path=request.sidecars.suspensions_path,
        classification=DatasetClassification.REHEARSAL,
    )
    if manifest.quality.missing_expected_bar_count or manifest.quality.unexpected_timestamp_count or manifest.quality.duplicate_timestamp_count:
        raise FormalDatasetBuildError("BAR_CALENDAR_QUALITY_GATE_FAILED")
    quality = FormalDatasetQualityReport(
        builder_version=FORMAL_DATASET_BUILDER_VERSION,
        symbol_count=len(symbols),
        calendar_span_days=span,
        finalized_bar_count=manifest.quality.finalized_bar_count,
        blocking_reasons=(),
    )
    return FormalDatasetBuildResult(manifest=manifest, quality=quality)


def write_rehearsal_dataset_artifact(result: FormalDatasetBuildResult, directory: Path) -> Path:
    """Atomically write a non-overwritable rehearsal manifest/quality artifact."""

    if directory.exists():
        raise FileExistsError(directory)
    directory.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{directory.name}.tmp-", dir=directory.parent))
    try:
        (stage / "manifest.json").write_text(canonical_json(asdict(result.manifest)) + "\n", encoding="utf-8")
        (stage / "quality.json").write_text(canonical_json(asdict(result.quality)) + "\n", encoding="utf-8")
        (stage / "REHEARSAL_ONLY").write_text("sealed_test_accessed=false\n", encoding="utf-8")
        stage.replace(directory)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return directory


def _read_bars(path: Path) -> Any:
    import pandas as pd

    return pd.read_parquet(path) if path.suffix.lower() == ".parquet" else pd.read_csv(path)


def _validate_bar_columns(data: Any) -> None:
    import pandas as pd

    required = {"symbol", "timestamp", "open", "high", "low", "close", "volume", "amount", "vwap", "bar_final", "source_freq"}
    missing = sorted(required - set(data.columns))
    if missing:
        if "bar_final" in missing:
            raise FormalDatasetBuildError("BAR_FINAL_REQUIRED")
        raise FormalDatasetBuildError(f"BAR_COLUMNS_REQUIRED:{','.join(missing)}")
    if data["bar_final"].isna().any() or not pd.api.types.is_bool_dtype(data["bar_final"].dtype) or not data["bar_final"].all():
        raise FormalDatasetBuildError("BAR_FINAL_REQUIRED")
    if set(data["source_freq"].astype(str)) != {"5min"}:
        raise FormalDatasetBuildError("FIVE_MINUTE_BARS_REQUIRED")
    timestamps = pd.to_datetime(data["timestamp"], errors="coerce")
    if timestamps.isna().any() or data.duplicated(subset=["symbol", "timestamp"]).any():
        raise FormalDatasetBuildError("BAR_TIMESTAMP_CONTRACT_INVALID")
    for column in ("open", "high", "low", "close", "volume", "amount", "vwap"):
        values = pd.to_numeric(data[column], errors="coerce")
        if values.isna().any() or not (values > 0).all():
            raise FormalDatasetBuildError(f"BAR_{column.upper()}_INVALID")
    vwap_error = (pd.to_numeric(data["amount"]) / pd.to_numeric(data["volume"]) - pd.to_numeric(data["vwap"])).abs()
    if (vwap_error > 1e-6).any():
        raise FormalDatasetBuildError("VWAP_PROVENANCE_OR_VALUE_INVALID")


def _load_object(path: Path, error: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FormalDatasetBuildError(error) from exc
    if not isinstance(data, dict):
        raise FormalDatasetBuildError(error)
    return data


def _calendar_dates_with_session_close(calendar: dict[str, Any]) -> tuple[str, ...]:
    dates = calendar.get("trading_dates")
    sessions = calendar.get("sessions")
    if not isinstance(dates, list) or not isinstance(sessions, list) or not dates:
        raise FormalDatasetBuildError("TRADING_CALENDAR_SESSION_CLOSE_REQUIRED")
    session_dates = {item.get("trade_date") for item in sessions if isinstance(item, dict) and item.get("session_close")}
    if set(dates) != session_dates or not all(isinstance(date, str) for date in dates):
        raise FormalDatasetBuildError("TRADING_CALENDAR_SESSION_CLOSE_REQUIRED")
    return tuple(sorted(dates))


def _validate_sidecar_coverage(data: Any, symbols: tuple[str, ...], dates: tuple[str, ...], sidecars: FormalDatasetSidecars) -> None:
    universe = _load_object(sidecars.universe_path, "PIT_UNIVERSE_REQUIRED")
    eligibility = _load_object(sidecars.eligibility_path, "ELIGIBILITY_SIDECAR_REQUIRED")
    market = _load_object(sidecars.market_context_path, "MARKET_SIDECAR_REQUIRED")
    universe_keys = {(str(row.get("as_of_date")), str(row.get("symbol"))) for row in universe.get("records", []) if isinstance(row, dict) and row.get("eligible") is True}
    if any((date, symbol) not in universe_keys for date in dates for symbol in symbols):
        raise FormalDatasetBuildError("PIT_UNIVERSE_COVERAGE_REQUIRED")
    bar_keys = {(str(row.symbol), str(row.timestamp)) for row in data[["symbol", "timestamp"]].itertuples(index=False)}
    eligibility_keys = {(str(row.get("symbol")), str(row.get("timestamp"))) for row in eligibility.get("records", []) if isinstance(row, dict)}
    required_eligibility = {"is_suspended", "is_st", "prev_close", "limit_up_price", "limit_down_price", "limit_regime"}
    if not bar_keys <= eligibility_keys or any(not required_eligibility <= set(row) for row in eligibility.get("records", []) if isinstance(row, dict)):
        raise FormalDatasetBuildError("ELIGIBILITY_SIDECAR_COVERAGE_REQUIRED")
    market_times = {str(row.get("timestamp")) for row in market.get("records", []) if isinstance(row, dict)}
    required_market = {"timestamp", "index_symbol", "index_close", "industry_id", "industry_close", "theme_state", "market_regime"}
    actual_times = {str(value) for value in data["timestamp"]}
    if not actual_times <= market_times or any(not required_market <= set(row) for row in market.get("records", []) if isinstance(row, dict)):
        raise FormalDatasetBuildError("MARKET_SIDECAR_COVERAGE_REQUIRED")
