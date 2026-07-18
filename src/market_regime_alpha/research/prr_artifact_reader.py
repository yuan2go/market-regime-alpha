"""Verified, network-free readers for immutable PRR Dataset and MR-1 artifacts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeVar, cast

import pandas as pd

from market_regime_alpha.research.prr_artifact_schemas import (
    ArtifactSchema,
    BAR_PRIMARY_KEY,
    CANDIDATE_RANKING_PRIMARY_KEY,
    CandidateBaselineId,
    DECISION_SNAPSHOT_PRIMARY_KEY,
    MR1_BASELINE_PRIMARY_SEED,
    MR1_CANDIDATE_BASELINE_PRIMARY_KEY,
    MR1_CANDIDATE_BASELINE_SCHEMA_VERSION,
    MR1_CASH_LOCK_POLICY_ID,
    MR1_COST_SCENARIOS,
    MR1_DAILY_EQUITY_PRIMARY_KEY,
    MR1_EXIT_TIMES,
    MR1_MISSING_WEIGHT_POLICY_ID,
    MR1_RUN_SCHEMA,
    MR1_SOURCE_RANKING_PRIMARY_KEY,
    PREPARED_SESSION_PRIMARY_KEY,
    PRR_DATASET_SCHEMA,
)
from market_regime_alpha.research.tencent_composite_contracts import (
    CompositeBar,
    CompositeDispositionCode,
    CompositeQualityFinding,
    CompositeQualityReport,
    CompositeSourceKind,
    CompositeSymbolDisposition,
    PreparedCompositeData,
    PreparedCompositeSession,
)


_CLOSE_RETURN_TARGET_ID = "target-r5-decision-reference-to-next-session-close-return-v1"


@dataclass(frozen=True, slots=True)
class VerifiedPRRDataset:
    """Fully checked, in-memory view of one immutable exploratory Dataset."""

    root: Path
    dataset_id: str
    manifest: Mapping[str, Any]
    quality: Mapping[str, Any]
    prepared: PreparedCompositeData
    bars: tuple[CompositeBar, ...]
    ranking_rows: tuple[Mapping[str, Any], ...]
    decision_dates: tuple[date, ...]
    checksums_hash: str


@dataclass(frozen=True, slots=True)
class VerifiedMR1Run:
    """Fully checked, in-memory view of one immutable MR-1 v3 run."""

    root: Path
    run_id: str
    dataset_id: str
    manifest: Mapping[str, Any]
    morning_targets: tuple[Mapping[str, Any], ...]
    daily_equity: tuple[Mapping[str, Any], ...]
    metrics: tuple[Mapping[str, Any], ...]
    candidate_daily_baselines: tuple[Mapping[str, Any], ...]
    checksums_hash: str


def load_verified_prr_dataset(path: Path) -> VerifiedPRRDataset:
    """Load a PRR Dataset after exact-set, checksum, and cross-table validation."""

    root = path.resolve()
    _verify_artifact(root, PRR_DATASET_SCHEMA.required_files)
    manifest = _read_mapping(root / "dataset_manifest.json", "Dataset manifest")
    _verify_manifest(manifest, PRR_DATASET_SCHEMA, "Dataset manifest")
    _require_exploratory(manifest, "Dataset manifest")
    dataset_id = _required_text(manifest, "dataset_id", "Dataset manifest")
    quality_payload = _read_mapping(root / "data_quality.json", "Dataset quality")
    limitations = _read_string_sequence(root / "limitations.json", "Dataset limitations")

    prepared_frame = _read_parquet(root / "prepared_sessions.parquet")
    bars_frame = _read_parquet(root / "bars.parquet")
    rankings_frame = _read_parquet(root / "candidate_rankings.parquet")
    snapshots_frame = _read_parquet(root / "decision_snapshots.parquet")
    _validate_dataset_frames(
        manifest=manifest,
        quality_payload=quality_payload,
        prepared_frame=prepared_frame,
        bars_frame=bars_frame,
        rankings_frame=rankings_frame,
        snapshots_frame=snapshots_frame,
    )
    quality = _quality_report(quality_payload)
    prepared = _prepared_data(prepared_frame, quality=quality, limitations=limitations)
    bars = _bars(bars_frame)
    ranking_rows = _frozen_records(rankings_frame)
    decision_dates = _ordered_decision_dates(snapshots_frame)

    return VerifiedPRRDataset(
        root=root,
        dataset_id=dataset_id,
        manifest=_freeze_mapping(manifest),
        quality=_freeze_mapping(quality_payload),
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
    """Load one MR-1 v3 run after table cardinality and parity validation."""

    root = path.resolve()
    _verify_artifact(root, MR1_RUN_SCHEMA.required_files)
    manifest = _read_mapping(root / "manifest.json", "MR-1 manifest")
    _verify_manifest(manifest, MR1_RUN_SCHEMA, "MR-1 manifest")
    _require_exploratory(manifest, "MR-1 manifest")
    run_id = _required_text(manifest, "run_id", "MR-1 manifest")
    dataset_id = _required_text(manifest, "dataset_id", "MR-1 manifest")
    if run_id != root.name:
        raise ValueError("MR-1 run_id must match its immutable directory name")
    if expected_dataset_id is not None and dataset_id != expected_dataset_id:
        raise ValueError("MR-1 Dataset ID does not match the verified Dataset")
    if frozenset(_required_string_sequence(manifest, "required_artifacts", "MR-1 manifest")) != MR1_RUN_SCHEMA.required_files:
        raise ValueError("MR-1 manifest required_artifacts must match the schema contract")
    if manifest.get("candidate_daily_baseline_schema_version") != MR1_CANDIDATE_BASELINE_SCHEMA_VERSION:
        raise ValueError("MR-1 Candidate baseline schema does not match the schema contract")
    if tuple(manifest.get("exit_times", ())) != MR1_EXIT_TIMES:
        raise ValueError("MR-1 exit times do not match the schema contract")
    if tuple(manifest.get("cost_scenarios", ())) != MR1_COST_SCENARIOS:
        raise ValueError("MR-1 cost scenarios do not match the schema contract")

    targets_frame = _read_parquet(root / "morning_targets.parquet")
    equity_frame = _read_parquet(root / "daily_equity.parquet")
    metrics_frame = _read_parquet(root / "chronological_model_metrics.parquet")
    baselines_frame = _read_parquet(root / "candidate_daily_baselines.parquet")
    _validate_mr1_frames(
        manifest=manifest,
        targets_frame=targets_frame,
        equity_frame=equity_frame,
        baselines_frame=baselines_frame,
    )
    baseline_rows = _frozen_records(baselines_frame)
    return VerifiedMR1Run(
        root=root,
        run_id=run_id,
        dataset_id=dataset_id,
        manifest=_freeze_mapping(manifest),
        morning_targets=_frozen_records(targets_frame),
        daily_equity=_frozen_records(equity_frame),
        metrics=_frozen_records(metrics_frame),
        candidate_daily_baselines=baseline_rows,
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


def _validate_dataset_frames(
    *,
    manifest: Mapping[str, Any],
    quality_payload: Mapping[str, Any],
    prepared_frame: pd.DataFrame,
    bars_frame: pd.DataFrame,
    rankings_frame: pd.DataFrame,
    snapshots_frame: pd.DataFrame,
) -> None:
    _require_unique_frame_keys(prepared_frame, PREPARED_SESSION_PRIMARY_KEY, "prepared sessions")
    _require_unique_frame_keys(bars_frame, BAR_PRIMARY_KEY, "bars")
    _require_unique_frame_keys(snapshots_frame, DECISION_SNAPSHOT_PRIMARY_KEY, "decision snapshots")
    _require_unique_frame_keys(rankings_frame, CANDIDATE_RANKING_PRIMARY_KEY, "Candidate rankings")
    close_rankings = rankings_frame[rankings_frame["target_id"] == _CLOSE_RETURN_TARGET_ID]
    _require_unique_frame_keys(close_rankings, MR1_SOURCE_RANKING_PRIMARY_KEY, "MR-1 source rankings")

    quality = _quality_report(quality_payload)
    accepted = set(quality.accepted_symbols)
    prepared_symbols = set(str(value) for value in prepared_frame["symbol"])
    if prepared_symbols != accepted:
        raise ValueError("prepared symbols must equal quality accepted symbols")
    for label, frame in (
        ("ranking", rankings_frame),
        ("snapshot", snapshots_frame),
        ("bar", bars_frame),
    ):
        if not set(str(value) for value in frame["symbol"]).issubset(accepted):
            raise ValueError(f"{label} symbols must belong to prepared accepted symbols")

    prepared_dates = tuple(sorted({_parse_date(value) for value in prepared_frame["session_date"]}))
    prepared_keys = {
        (str(row.symbol), _parse_date(row.session_date))
        for row in prepared_frame.itertuples(index=False)
    }
    expected_prepared_keys = {
        (symbol, session_date)
        for symbol in accepted
        for session_date in quality.common_session_dates
    }
    if prepared_keys != expected_prepared_keys:
        raise ValueError("prepared sessions must exactly cover accepted symbols and quality dates")
    if prepared_dates != quality.common_session_dates:
        raise ValueError("prepared session dates must equal retained quality evidence")
    snapshot_dates = _ordered_decision_dates(snapshots_frame)
    ranking_dates = tuple(sorted({_parse_date(value) for value in rankings_frame["decision_date"]}))
    if ranking_dates != snapshot_dates:
        raise ValueError("Candidate ranking dates must equal Decision Dates")
    if len(prepared_dates) <= len(snapshot_dates):
        raise ValueError("prepared sessions must include one Target session after Decision Dates")
    expected_decisions = prepared_dates[-(len(snapshot_dates) + 1) : -1]
    if snapshot_dates != expected_decisions:
        raise ValueError("Decision Dates must be the contiguous prepared slice before the Target session")

    date_range = manifest.get("date_range")
    if not isinstance(date_range, Mapping):
        raise ValueError("Dataset manifest date_range must be an object")
    if _parse_date(date_range.get("start")) != prepared_dates[0] or _parse_date(date_range.get("end")) != prepared_dates[-1]:
        raise ValueError("Dataset manifest date range must equal prepared session range")
    row_counts = manifest.get("row_counts")
    expected_counts = {
        "bars": len(bars_frame),
        "prepared_sessions": len(prepared_frame),
        "decision_snapshots": len(snapshots_frame),
        "candidate_rankings": len(rankings_frame),
    }
    if not isinstance(row_counts, Mapping) or dict(row_counts) != expected_counts:
        raise ValueError("Dataset manifest row counts must match physical tables")
    if manifest.get("decision_count") != len(snapshot_dates) or manifest.get("session_count") != len(prepared_dates):
        raise ValueError("Dataset manifest date cardinalities must match physical tables")
    if manifest.get("symbol_count") != len(quality.requested_symbols) or manifest.get("accepted_symbol_count") != len(accepted):
        raise ValueError("Dataset manifest symbol cardinalities must match quality evidence")
    if manifest.get("quality_disposition") != quality_payload.get("disposition"):
        raise ValueError("Dataset manifest quality disposition must match quality evidence")
    retrieved_at = _parse_datetime(manifest.get("retrieved_at"))
    if any(_parse_datetime(value) > retrieved_at for value in bars_frame["timestamp"]):
        raise ValueError("bar timestamps must not be later than Dataset retrieval evidence")


def _validate_mr1_frames(
    *,
    manifest: Mapping[str, Any],
    targets_frame: pd.DataFrame,
    equity_frame: pd.DataFrame,
    baselines_frame: pd.DataFrame,
) -> None:
    _require_unique_frame_keys(equity_frame, MR1_DAILY_EQUITY_PRIMARY_KEY, "MR-1 daily equity")
    _require_unique_frame_keys(
        baselines_frame,
        MR1_CANDIDATE_BASELINE_PRIMARY_KEY,
        "MR-1 Candidate daily baselines",
    )
    if baselines_frame.empty or equity_frame.empty or targets_frame.empty:
        raise ValueError("MR-1 semantic tables must not be empty")
    if set(str(value) for value in baselines_frame["schema_version"]) != {MR1_CANDIDATE_BASELINE_SCHEMA_VERSION}:
        raise ValueError("MR-1 Candidate baseline row schema is invalid")
    if set(str(value) for value in baselines_frame["data_eligibility"]) != {"EXPLORATORY"}:
        raise ValueError("MR-1 Candidate baselines must remain EXPLORATORY")
    baseline_ids = set(str(value) for value in baselines_frame["baseline_id"])
    if baseline_ids != {item.value for item in CandidateBaselineId}:
        raise ValueError("MR-1 Candidate baseline family is incomplete")
    if set(int(value) for value in baselines_frame["baseline_seed"]) != {MR1_BASELINE_PRIMARY_SEED}:
        raise ValueError("MR-1 Candidate baseline seed does not match the contract")
    if set(int(value) for value in baselines_frame["top_k"]) != {int(manifest["top_k"])}:
        raise ValueError("MR-1 Candidate baseline Top-K must match the manifest")
    if set(str(value) for value in baselines_frame["cash_lock_policy_id"]) != {
        MR1_CASH_LOCK_POLICY_ID
    }:
        raise ValueError("MR-1 Candidate baseline cash-lock policy is invalid")
    if set(str(value) for value in baselines_frame["missing_weight_policy_id"]) != {
        MR1_MISSING_WEIGHT_POLICY_ID
    }:
        raise ValueError("MR-1 Candidate baseline missing-weight policy is invalid")
    if any(not str(value).strip() for value in baselines_frame["cost_policy_id"]):
        raise ValueError("MR-1 Candidate baseline cost policy must be identified")
    if any(not str(value).strip() for value in baselines_frame["baseline_selection_id"]):
        raise ValueError("MR-1 Candidate baseline selection must be identified")
    for row in baselines_frame.itertuples(index=False):
        observed = _finite_number(row.observed_weight, "observed_weight")
        missing = _finite_number(row.missing_weight, "missing_weight")
        locked = _finite_number(row.cash_locked_weight, "cash_locked_weight")
        if min(observed, missing, locked) < 0.0 or abs(observed + missing + locked - 1.0) > 1e-12:
            raise ValueError("MR-1 Candidate baseline weights must reconcile to one")
        _finite_number(row.gross_return, "gross_return")
        _finite_number(row.net_return, "net_return")
        if row.baseline_slot_status not in {"EXECUTED", "CASH_LOCKED"}:
            raise ValueError("MR-1 Candidate baseline slot status is invalid")
        all_candidate = CandidateBaselineId(str(row.baseline_id)) in {
            CandidateBaselineId.ALL_CANDIDATE_GROSS_V1,
            CandidateBaselineId.ALL_CANDIDATE_NET_DIAGNOSTIC_V1,
        }
        expected_selected = (
            int(row.candidate_symbol_count)
            if all_candidate
            else min(int(row.top_k), int(row.candidate_symbol_count))
        )
        if row.baseline_slot_status == "EXECUTED" and int(row.selected_symbol_count) != expected_selected:
            raise ValueError("MR-1 Candidate baseline selected cardinality is invalid")
        if row.baseline_slot_status == "CASH_LOCKED" and (
            int(row.selected_symbol_count) != 0
            or not math.isclose(locked, 1.0, abs_tol=1e-12)
        ):
            raise ValueError("MR-1 cash-locked baseline must execute no selection")
    _validate_baseline_family_parity(baselines_frame)

    baseline_dates = tuple(sorted({_parse_date(value) for value in baselines_frame["decision_date"]}))
    equity_dates = tuple(sorted({_parse_date(value) for value in equity_frame["session_date"]}))
    target_dates = tuple(sorted({_parse_date(value) for value in targets_frame["decision_date"]}))
    if baseline_dates != equity_dates or baseline_dates != target_dates:
        raise ValueError("MR-1 daily equity, baseline, and Target dates must match")
    if set(str(value) for value in baselines_frame["exit_time"]) != set(MR1_EXIT_TIMES):
        raise ValueError("MR-1 Candidate baseline exit times are incomplete")
    if set(str(value) for value in baselines_frame["cost_scenario"]) != set(MR1_COST_SCENARIOS):
        raise ValueError("MR-1 Candidate baseline cost scenarios are incomplete")
    if set(str(value) for value in equity_frame["exit_time"]) != set(MR1_EXIT_TIMES):
        raise ValueError("MR-1 daily equity exit times must align with baselines")
    if set(str(value) for value in equity_frame["cost_scenario"]) != set(MR1_COST_SCENARIOS):
        raise ValueError("MR-1 daily equity cost scenarios must align with baselines")
    expected_baselines = len(baseline_dates) * len(MR1_EXIT_TIMES) * len(MR1_COST_SCENARIOS) * len(CandidateBaselineId)
    if len(baselines_frame) != expected_baselines:
        raise ValueError("MR-1 Candidate baseline cardinality is incomplete")
    model_ids = set(str(value) for value in equity_frame["model_id"])
    expected_equity = len(baseline_dates) * len(MR1_EXIT_TIMES) * len(MR1_COST_SCENARIOS) * len(model_ids)
    if len(equity_frame) != expected_equity:
        raise ValueError("MR-1 daily equity cardinality is incomplete")
    for row in equity_frame.itertuples(index=False):
        _finite_number(row.gross_return, "daily equity gross_return")
        _finite_number(row.net_return, "daily equity net_return")
        cash_ratio = _finite_number(row.cash_ratio, "daily equity cash_ratio")
        if cash_ratio < 0.0 or cash_ratio > 1.0:
            raise ValueError("MR-1 daily equity cash ratio must be within zero and one")
    _validate_close_cash_lock_parity(baselines_frame, equity_frame)


def _validate_baseline_family_parity(frame: pd.DataFrame) -> None:
    group_fields = ["decision_date", "exit_time", "cost_scenario", "baseline_seed"]
    for _, group in frame.groupby(group_fields, sort=False, dropna=False):
        indexed = {CandidateBaselineId(str(row.baseline_id)): row for row in group.itertuples(index=False)}
        if set(indexed) != set(CandidateBaselineId):
            raise ValueError("MR-1 Candidate baseline family is incomplete for a daily comparison")
        all_gross = indexed[CandidateBaselineId.ALL_CANDIDATE_GROSS_V1]
        all_net = indexed[CandidateBaselineId.ALL_CANDIDATE_NET_DIAGNOSTIC_V1]
        matched_gross = indexed[CandidateBaselineId.MATCHED_K_HASH_GROSS_V1]
        matched_net = indexed[CandidateBaselineId.MATCHED_K_HASH_NET_V1]
        if not math.isclose(float(all_gross.net_return), float(all_gross.gross_return), abs_tol=1e-12):
            raise ValueError("all-Candidate gross baseline must not contain costs")
        if not math.isclose(float(matched_gross.net_return), float(matched_gross.gross_return), abs_tol=1e-12):
            raise ValueError("matched-K gross baseline must not contain costs")
        for left, right, label in (
            (all_gross, all_net, "all-Candidate"),
            (matched_gross, matched_net, "matched-K"),
        ):
            parity_fields = (
                "gross_return",
                "selected_symbol_count",
                "observed_weight",
                "missing_weight",
                "cash_locked_weight",
                "baseline_slot_status",
                "baseline_selection_id",
            )
            if any(getattr(left, field) != getattr(right, field) for field in parity_fields):
                raise ValueError(f"{label} gross and net baselines must share selection semantics")


def _validate_close_cash_lock_parity(baselines: pd.DataFrame, equity: pd.DataFrame) -> None:
    close_baselines = baselines[baselines["exit_time"] == "CLOSE"]
    for (decision_date, scenario), group in close_baselines.groupby(
        ["decision_date", "cost_scenario"], sort=False, dropna=False
    ):
        statuses = set(str(value) for value in group["baseline_slot_status"])
        if len(statuses) != 1:
            raise ValueError("CLOSE baseline family must share one sleeve state")
        if statuses != {"CASH_LOCKED"}:
            continue
        model_rows = equity[
            (equity["session_date"].astype(str) == str(decision_date))
            & (equity["exit_time"] == "CLOSE")
            & (equity["cost_scenario"] == scenario)
        ]
        if model_rows.empty:
            raise ValueError("CLOSE cash-lock baseline must align with model daily equity")
        for row in model_rows.itertuples(index=False):
            if (
                not math.isclose(float(row.gross_return), 0.0, abs_tol=1e-12)
                or not math.isclose(float(row.net_return), 0.0, abs_tol=1e-12)
                or not math.isclose(float(row.cash_ratio), 1.0, abs_tol=1e-12)
            ):
                raise ValueError("CLOSE model and matched baselines must share cash-lock semantics")


def _quality_report(payload: Mapping[str, Any]) -> CompositeQualityReport:
    gate = payload.get("quality_gate")
    if not isinstance(gate, Mapping):
        raise ValueError("Dataset quality must retain quality_gate evidence")
    requested = _mapping_string_sequence(gate, "requested_symbols", "quality_gate")
    accepted = _mapping_string_sequence(gate, "accepted_symbols", "quality_gate")
    common_dates = tuple(_parse_date(value) for value in _mapping_sequence(gate, "common_session_dates", "quality_gate"))
    raw_dispositions = _mapping_sequence(gate, "dispositions", "quality_gate")
    dispositions: list[CompositeSymbolDisposition] = []
    for raw in raw_dispositions:
        if not isinstance(raw, Mapping):
            raise ValueError("quality disposition must be an object")
        raw_findings = raw.get("findings")
        if not isinstance(raw_findings, Sequence) or isinstance(raw_findings, (str, bytes)):
            raise ValueError("quality findings must be an array")
        findings = tuple(
            CompositeQualityFinding(
                code=_required_text(item, "code", "quality finding"),
                message=_required_text(item, "message", "quality finding"),
                critical=bool(item.get("critical")),
            )
            for item in raw_findings
            if isinstance(item, Mapping)
        )
        if len(findings) != len(raw_findings):
            raise ValueError("quality findings must contain only objects")
        dispositions.append(
            CompositeSymbolDisposition(
                symbol=_required_text(raw, "symbol", "quality disposition"),
                code=CompositeDispositionCode(_required_text(raw, "code", "quality disposition")),
                complete_session_count=_required_int(raw, "complete_session_count", "quality disposition"),
                findings=findings,
            )
        )
    return CompositeQualityReport(
        requested_symbols=requested,
        accepted_symbols=accepted,
        dispositions=tuple(dispositions),
        common_session_dates=common_dates,
        required_session_count=_required_int(gate, "required_session_count", "quality_gate"),
        minimum_accepted_symbols=_required_int(gate, "minimum_accepted_symbols", "quality_gate"),
    )


def _prepared_data(
    frame: pd.DataFrame,
    *,
    quality: CompositeQualityReport,
    limitations: tuple[str, ...],
) -> PreparedCompositeData:
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
    return PreparedCompositeData(
        accepted_symbols=quality.accepted_symbols,
        common_session_dates=quality.common_session_dates,
        sessions=sessions,
        quality=quality,
        limitations=limitations,
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


def _ordered_decision_dates(frame: pd.DataFrame) -> tuple[date, ...]:
    if "decision_date" not in frame:
        raise ValueError("decision snapshots must include decision_date")
    ordered_unique = tuple(dict.fromkeys(_parse_date(value) for value in frame["decision_date"]))
    if not ordered_unique or ordered_unique != tuple(sorted(ordered_unique)):
        raise ValueError("Dataset Decision Dates must be non-empty and chronological")
    return ordered_unique


def _require_unique_frame_keys(frame: pd.DataFrame, fields: tuple[str, ...], label: str) -> None:
    missing = set(fields) - set(frame.columns)
    if missing:
        raise ValueError(f"{label} missing primary key fields: {sorted(missing)}")
    if frame[list(fields)].isnull().any(axis=None) or frame.duplicated(list(fields)).any():
        raise ValueError(f"{label} primary keys must be present and unique")


def _source_kinds(value: object) -> tuple[CompositeSourceKind, ...]:
    kinds = tuple(CompositeSourceKind(item) for item in str(value).split(",") if item)
    if not kinds or len(kinds) != len(set(kinds)):
        raise ValueError("prepared session source kinds must be non-empty and unique")
    return kinds


def _read_parquet(path: Path) -> pd.DataFrame:
    try:
        return pd.read_parquet(path)
    except Exception as exc:  # pragma: no cover - backend wording varies.
        raise ValueError(f"artifact Parquet is unreadable: {path.name}") from exc


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc


def _read_mapping(path: Path, label: str) -> dict[str, Any]:
    value = _read_json(path, label)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _read_string_sequence(path: Path, label: str) -> tuple[str, ...]:
    value = _read_json(path, label)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a JSON string array")
    return tuple(value)


def _verify_manifest(manifest: Mapping[str, Any], schema: ArtifactSchema, label: str) -> None:
    if manifest.get("schema_version") != schema.schema_version:
        raise ValueError(f"{label} schema is unsupported")
    missing = schema.required_manifest_keys - set(manifest)
    if missing:
        raise ValueError(f"{label} missing required fields: {sorted(missing)}")


def _require_exploratory(manifest: Mapping[str, Any], label: str) -> None:
    if manifest.get("data_eligibility") != "EXPLORATORY":
        raise ValueError(f"{label} must remain EXPLORATORY")


def _required_text(manifest: Mapping[str, Any], key: str, label: str) -> str:
    value = manifest.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} {key} must be a non-empty string")
    return value


def _required_int(manifest: Mapping[str, Any], key: str, label: str) -> int:
    value = manifest.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} {key} must be a non-negative int")
    return value


def _required_string_sequence(manifest: Mapping[str, Any], key: str, label: str) -> tuple[str, ...]:
    value = manifest.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} {key} must be a string array")
    return tuple(value)


def _mapping_sequence(manifest: Mapping[str, Any], key: str, label: str) -> tuple[Any, ...]:
    value = manifest.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} {key} must be an array")
    return tuple(value)


def _mapping_string_sequence(manifest: Mapping[str, Any], key: str, label: str) -> tuple[str, ...]:
    values = _mapping_sequence(manifest, key, label)
    if any(not isinstance(value, str) for value in values):
        raise ValueError(f"{label} {key} must contain strings")
    return cast(tuple[str, ...], values)


def _parse_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, pd.Timestamp):
        parsed = value.to_pydatetime()
    elif isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("artifact timestamp must be timezone-aware")
    return parsed


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite numeric")
    return result


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
