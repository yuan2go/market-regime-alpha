"""Verified, network-free readers for immutable PRR Dataset and MR-1 artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeVar, cast

import pandas as pd

from market_regime_alpha.research.tencent_composite_contracts import (
    CompositeBar,
    CompositeDispositionCode,
    CompositeQualityReport,
    CompositeSourceKind,
    CompositeSymbolDisposition,
    PreparedCompositeData,
    PreparedCompositeSession,
)


PRR_DATASET_SCHEMA_VERSION = "prr-mvp-1-dataset-v1"
MR1_RUN_SCHEMA_VERSION = "mr-1-run-v2"
MR1_DAILY_CANDIDATE_BASELINE_SCHEMA_VERSION = "mr-1-candidate-daily-baseline-v1"

PRR_DATASET_FILENAMES = frozenset(
    {
        "bars.parquet",
        "prepared_sessions.parquet",
        "decision_snapshots.parquet",
        "candidate_rankings.parquet",
        "dataset_manifest.json",
        "data_quality.json",
        "limitations.json",
        "SHA256SUMS.json",
    }
)
MR1_RUN_FILENAMES = frozenset(
    {
        "manifest.json",
        "limitations.json",
        "morning_targets.parquet",
        "orders.parquet",
        "fills.parquet",
        "trades.parquet",
        "daily_equity.parquet",
        "candidate_daily_baseline.parquet",
        "chronological_model_metrics.parquet",
        "model_target_matrix.csv",
        "exit_time_comparison.json",
        "metrics.json",
        "report.md",
        "SHA256SUMS.json",
    }
)


@dataclass(frozen=True, slots=True)
class VerifiedPRRDataset:
    """Fully checked, in-memory view of one immutable exploratory Dataset."""

    root: Path
    dataset_id: str
    manifest: Mapping[str, Any]
    prepared: PreparedCompositeData
    bars: tuple[CompositeBar, ...]
    ranking_rows: tuple[Mapping[str, Any], ...]
    decision_dates: tuple[date, ...]
    checksums_hash: str


@dataclass(frozen=True, slots=True)
class VerifiedMR1Run:
    """Fully checked, in-memory view of one immutable MR-1 run."""

    root: Path
    run_id: str
    dataset_id: str
    manifest: Mapping[str, Any]
    morning_targets: tuple[Mapping[str, Any], ...]
    daily_equity: tuple[Mapping[str, Any], ...]
    metrics: tuple[Mapping[str, Any], ...]
    candidate_daily_baseline: tuple[Mapping[str, Any], ...]
    checksums_hash: str


def load_verified_prr_dataset(path: Path) -> VerifiedPRRDataset:
    """Load a complete PRR Dataset after exact-set and SHA-256 verification."""

    root = path.resolve()
    _verify_artifact(root, PRR_DATASET_FILENAMES)
    manifest = _read_mapping(root / "dataset_manifest.json", "Dataset manifest")
    _require_schema(manifest, PRR_DATASET_SCHEMA_VERSION, "Dataset manifest")
    _require_exploratory(manifest, "Dataset manifest")
    dataset_id = _required_text(manifest, "dataset_id", "Dataset manifest")

    prepared_frame = _read_parquet(root / "prepared_sessions.parquet")
    bars_frame = _read_parquet(root / "bars.parquet")
    rankings_frame = _read_parquet(root / "candidate_rankings.parquet")
    snapshots_frame = _read_parquet(root / "decision_snapshots.parquet")
    prepared = _prepared_data(prepared_frame)
    bars = _bars(bars_frame)
    ranking_rows = _frozen_records(rankings_frame)
    decision_dates = _decision_dates(snapshots_frame)

    return VerifiedPRRDataset(
        root=root,
        dataset_id=dataset_id,
        manifest=_freeze_mapping(manifest),
        prepared=prepared,
        bars=bars,
        ranking_rows=ranking_rows,
        decision_dates=decision_dates,
        checksums_hash=_content_hash(root / "SHA256SUMS.json"),
    )


def load_verified_mr1_run(
    path: Path,
    *,
    expected_dataset_id: str | None = None,
) -> VerifiedMR1Run:
    """Load a complete MR-1 v2 run without mutating it or accessing providers."""

    root = path.resolve()
    _verify_artifact(root, MR1_RUN_FILENAMES)
    manifest = _read_mapping(root / "manifest.json", "MR-1 manifest")
    _require_schema(manifest, MR1_RUN_SCHEMA_VERSION, "MR-1 manifest")
    _require_exploratory(manifest, "MR-1 manifest")
    run_id = _required_text(manifest, "run_id", "MR-1 manifest")
    dataset_id = _required_text(manifest, "dataset_id", "MR-1 manifest")
    if run_id != root.name:
        raise ValueError("MR-1 run_id must match its immutable directory name")
    if expected_dataset_id is not None and dataset_id != expected_dataset_id:
        raise ValueError("MR-1 Dataset ID does not match the verified Dataset")

    baseline_rows = _frozen_records(_read_parquet(root / "candidate_daily_baseline.parquet"))
    if any(
        row.get("schema_version") != MR1_DAILY_CANDIDATE_BASELINE_SCHEMA_VERSION
        for row in baseline_rows
    ):
        raise ValueError("MR-1 Candidate daily baseline schema is invalid")
    if any(row.get("data_eligibility") != "EXPLORATORY" for row in baseline_rows):
        raise ValueError("MR-1 Candidate daily baseline must remain EXPLORATORY")

    return VerifiedMR1Run(
        root=root,
        run_id=run_id,
        dataset_id=dataset_id,
        manifest=_freeze_mapping(manifest),
        morning_targets=_frozen_records(_read_parquet(root / "morning_targets.parquet")),
        daily_equity=_frozen_records(_read_parquet(root / "daily_equity.parquet")),
        metrics=_frozen_records(_read_parquet(root / "chronological_model_metrics.parquet")),
        candidate_daily_baseline=baseline_rows,
        checksums_hash=_content_hash(root / "SHA256SUMS.json"),
    )


def _verify_artifact(root: Path, required_filenames: frozenset[str]) -> None:
    if not root.is_dir():
        raise ValueError("artifact directory is missing")
    filenames = frozenset(item.name for item in root.iterdir() if item.is_file())
    if filenames != required_filenames:
        raise ValueError("artifact file set does not match its declared schema")
    checksums = _read_mapping(root / "SHA256SUMS.json", "checksum manifest")
    payload_filenames = required_filenames - {"SHA256SUMS.json"}
    if frozenset(checksums) != payload_filenames:
        raise ValueError("checksum manifest must cover every payload exactly once")
    for filename in sorted(payload_filenames):
        expected = checksums.get(filename)
        if not isinstance(expected, str) or expected != _content_hash(root / filename):
            raise ValueError(f"artifact checksum mismatch: {filename}")


def _prepared_data(frame: pd.DataFrame) -> PreparedCompositeData:
    sessions = tuple(
        PreparedCompositeSession(
            symbol=str(row.symbol),
            session_date=_parse_date(row.session_date),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            amount=float(row.amount),
            reference_price=float(row.reference_price),
            reference_timestamp=_parse_datetime(row.reference_timestamp),
            source_kinds=_source_kinds(row.source_kinds),
        )
        for row in frame.itertuples(index=False)
    )
    if not sessions:
        raise ValueError("Dataset prepared sessions must not be empty")
    symbols = tuple(sorted({session.symbol for session in sessions}))
    session_dates = tuple(sorted({session.session_date for session in sessions}))
    quality = CompositeQualityReport(
        requested_symbols=symbols,
        accepted_symbols=symbols,
        dispositions=tuple(
            CompositeSymbolDisposition(
                symbol=symbol,
                code=CompositeDispositionCode.ACCEPTED,
                complete_session_count=len(session_dates),
                findings=(),
            )
            for symbol in symbols
        ),
        common_session_dates=session_dates,
        required_session_count=1,
        minimum_accepted_symbols=1,
    )
    return PreparedCompositeData(
        accepted_symbols=symbols,
        common_session_dates=session_dates,
        sessions=sessions,
        quality=quality,
        limitations=("AUXILIARY_DATA_ONLY",),
    )


def _bars(frame: pd.DataFrame) -> tuple[CompositeBar, ...]:
    bars = tuple(
        CompositeBar(
            symbol=str(row.symbol),
            timestamp=_parse_datetime(row.timestamp),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume),
            amount=float(row.amount),
            source=CompositeSourceKind(str(row.source)),
        )
        for row in frame.itertuples(index=False)
    )
    if not bars:
        raise ValueError("Dataset bars must not be empty")
    return bars


def _decision_dates(frame: pd.DataFrame) -> tuple[date, ...]:
    if "decision_date" not in frame:
        raise ValueError("decision snapshots must include decision_date")
    ordered_unique = tuple(dict.fromkeys(_parse_date(value) for value in frame["decision_date"]))
    if not ordered_unique or ordered_unique != tuple(sorted(ordered_unique)):
        raise ValueError("Dataset Decision Dates must be non-empty, ordered, and unique")
    return ordered_unique


def _source_kinds(value: object) -> tuple[CompositeSourceKind, ...]:
    kinds = tuple(CompositeSourceKind(item) for item in str(value).split(",") if item)
    if not kinds or len(kinds) != len(set(kinds)):
        raise ValueError("prepared session source kinds must be non-empty and unique")
    return kinds


def _read_parquet(path: Path) -> pd.DataFrame:
    try:
        return pd.read_parquet(path)
    except Exception as exc:  # pragma: no cover - pandas backend error wording varies.
        raise ValueError(f"artifact Parquet is unreadable: {path.name}") from exc


def _read_mapping(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _require_schema(manifest: Mapping[str, Any], expected: str, label: str) -> None:
    if manifest.get("schema_version") != expected:
        raise ValueError(f"{label} schema is unsupported")


def _require_exploratory(manifest: Mapping[str, Any], label: str) -> None:
    if manifest.get("data_eligibility") != "EXPLORATORY":
        raise ValueError(f"{label} must remain EXPLORATORY")


def _required_text(manifest: Mapping[str, Any], key: str, label: str) -> str:
    value = manifest.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} {key} must be a non-empty string")
    return value


def _parse_date(value: object) -> date:
    return date.fromisoformat(str(value))


def _parse_datetime(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("artifact timestamp must be timezone-aware")
    return parsed


def _content_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


T = TypeVar("T")


def _freeze(value: T) -> T:
    if isinstance(value, dict):
        return cast(T, MappingProxyType({key: _freeze(item) for key, item in value.items()}))
    if isinstance(value, list):
        return cast(T, tuple(_freeze(item) for item in value))
    return value


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], _freeze(dict(value)))


def _frozen_records(frame: pd.DataFrame) -> tuple[Mapping[str, Any], ...]:
    return tuple(_freeze_mapping(row) for row in frame.to_dict(orient="records"))
