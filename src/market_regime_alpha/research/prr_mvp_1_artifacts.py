"""Immutable raw, Dataset, and run artifacts for PRR-MVP-1."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
import shutil
from typing import Any, Mapping

import pandas as pd

from market_regime_alpha.core.identity import StableId
from market_regime_alpha.core.identity import ProviderId
from market_regime_alpha.core.time import RetrievedAt, SemanticTime
from market_regime_alpha.research.prr_mvp_1 import (
    ExploratoryExecutionCostConfig,
    PRRCandidateData,
    PRRReplayResult,
    PRR_MVP_1_EXECUTION_ASSUMPTION,
    PRR_MVP_1_SCHEMA_VERSION,
)
from market_regime_alpha.research.prr_artifact_schemas import PRR_DATASET_SCHEMA
from market_regime_alpha.research.tencent_composite_execution import (
    TencentCompositeResearchExecution,
)
from market_regime_alpha.research.tencent_composite_contracts import (
    CompositeAcquisitionResult,
    CompositeBar,
    CompositeSourceAttempt,
    CompositeSourceKind,
    CompositeSourcePartition,
)


RAW_FILENAMES = frozenset(
    {
        "request.json",
        "source_attempts.json",
        "source_conflicts.json",
        "source_partitions.json",
        "normalized_provider_response.json",
        "raw_manifest.json",
        "limitations.json",
        "SHA256SUMS.json",
    }
)
RUN_FILENAMES = frozenset(
    {
        "manifest.json",
        "config.snapshot.json",
        "dataset_manifest.json",
        "provider_selection.json",
        "source_artifacts.json",
        "data_quality.json",
        "candidate_panel_summary.json",
        "model_evaluation.json",
        "execution_assumptions.json",
        "orders.parquet",
        "fills.parquet",
        "trades.parquet",
        "daily_equity.parquet",
        "monthly_metrics.csv",
        "metrics.json",
        "stability.json",
        "acceptance_accounting.json",
        "selection_slot_outcomes.parquet",
        "limitations.json",
        "report.md",
        "SHA256SUMS.json",
    }
)
FAILURE_FILENAMES = frozenset({"manifest.json", "failure.json", "logs.jsonl", "SHA256SUMS.json"})


def raw_acquisition_id(execution: TencentCompositeResearchExecution) -> str:
    return _identity(
        "prr-raw",
        {
            "schema_version": "prr-mvp-1-raw-v1",
            "retrieved_at": execution.acquisition.retrieved_at.isoformat(),
            "partitions": [
                partition.content_hash
                for partition in (*execution.acquisition.partitions, execution.acquisition.quote_partition)
            ],
            "mode": execution.acquisition_mode,
        },
    )


def write_prr_raw_evidence(
    *,
    root: str | Path,
    execution: TencentCompositeResearchExecution,
    request: Mapping[str, Any],
) -> tuple[str, Path]:
    """Publish retained normalized provider responses without claiming raw bytes."""

    acquisition_id = raw_acquisition_id(execution)
    final, stage = _reserve(Path(root), acquisition_id)
    stage.mkdir(parents=True)
    try:
        partitions = (*execution.acquisition.partitions, execution.acquisition.quote_partition)
        _write_json(stage / "request.json", request)
        _write_json(stage / "source_attempts.json", execution.acquisition.attempts)
        _write_json(stage / "source_conflicts.json", execution.merged.conflicts)
        _write_json(
            stage / "source_partitions.json",
            [
                {
                    **_json_value(partition),
                    "source_partition_id": _identity(
                        "prr-source-partition",
                        {
                            "provider_id": str(partition.provider_id),
                            "locator": partition.locator,
                            "content_hash": partition.content_hash,
                        },
                    ),
                    "mode": execution.acquisition_mode,
                    "date_range": _bar_date_range(execution, partition.requested_symbols),
                    "frequency": "5min" if partition.product != "latest-quote" else "quote",
                    "raw_provider_bytes_status": "RAW_PROVIDER_BYTES_NOT_RETAINED",
                    "retained_response_status": "NORMALIZED_PROVIDER_RESPONSE_RETAINED",
                }
                for partition in partitions
            ],
        )
        _write_json(
            stage / "normalized_provider_response.json",
            {
                "bars": execution.acquisition.bars,
                "quotes": execution.acquisition.quotes,
                "retrieved_at": execution.acquisition.retrieved_at,
            },
        )
        limitations = (
            *execution.limitations,
            "RAW_PROVIDER_BYTES_NOT_RETAINED",
            "NORMALIZED_PROVIDER_RESPONSE_RETAINED",
            "RETRIEVED_AT_IS_NOT_HISTORICAL_AVAILABILITY",
            "CURRENT_WATCHLIST_IS_NOT_HISTORICAL_PIT_UNIVERSE",
        )
        _write_json(stage / "limitations.json", tuple(dict.fromkeys(limitations)))
        _write_json(
            stage / "raw_manifest.json",
            {
                "schema_version": "prr-mvp-1-raw-v1",
                "acquisition_id": acquisition_id,
                "data_eligibility": "EXPLORATORY",
                "acquisition_mode": execution.acquisition_mode,
                "retrieved_at": execution.acquisition.retrieved_at,
                "raw_provider_bytes": "RAW_PROVIDER_BYTES_NOT_RETAINED",
                "normalized_response": "NORMALIZED_PROVIDER_RESPONSE_RETAINED",
                "source_partition_count": len(partitions),
                "source_attempt_count": len(execution.acquisition.attempts),
                "source_conflict_count": len(execution.merged.conflicts),
            },
        )
        _write_checksums(stage)
        _validate_exact_set(stage, RAW_FILENAMES)
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return acquisition_id, final


def load_prr_cached_acquisition(path: str | Path) -> CompositeAcquisitionResult:
    """Load retained normalized input without opening a provider or network connection."""

    root = Path(path)
    manifest = json.loads((root / "raw_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("data_eligibility") != "EXPLORATORY":
        raise ValueError("cached PRR acquisition must remain EXPLORATORY")
    partitions_raw = json.loads((root / "source_partitions.json").read_text(encoding="utf-8"))
    response = json.loads((root / "normalized_provider_response.json").read_text(encoding="utf-8"))
    partitions = tuple(
        CompositeSourcePartition(
            source=CompositeSourceKind(item["source"]),
            provider_id=ProviderId(item["provider_id"]),
            product=item["product"],
            retrieved_at=RetrievedAt(datetime.fromisoformat(item["retrieved_at"])),
            locator=item["locator"],
            content_hash=item["content_hash"],
            requested_symbols=tuple(item["requested_symbols"]),
            raw_row_count=int(item["raw_row_count"]),
            normalized_row_count=int(item["normalized_row_count"]),
            limitations=tuple(item.get("limitations", ())),
        )
        for item in partitions_raw
        if item["product"] != "latest-quote"
    )
    quote_raw = next(item for item in partitions_raw if item["product"] == "latest-quote")
    quote_partition = CompositeSourcePartition(
        source=CompositeSourceKind(quote_raw["source"]),
        provider_id=ProviderId(quote_raw["provider_id"]),
        product=quote_raw["product"],
        retrieved_at=RetrievedAt(datetime.fromisoformat(quote_raw["retrieved_at"])),
        locator=quote_raw["locator"],
        content_hash=quote_raw["content_hash"],
        requested_symbols=tuple(quote_raw["requested_symbols"]),
        raw_row_count=int(quote_raw["raw_row_count"]),
        normalized_row_count=int(quote_raw["normalized_row_count"]),
        limitations=tuple(quote_raw.get("limitations", ())),
    )
    bars = tuple(
        sorted(
            (
                CompositeBar(
                    symbol=item["symbol"],
                    timestamp=datetime.fromisoformat(item["timestamp"]),
                    open=float(item["open"]),
                    high=float(item["high"]),
                    low=float(item["low"]),
                    close=float(item["close"]),
                    volume=float(item["volume"]),
                    amount=float(item["amount"]),
                    source=CompositeSourceKind(item["source"]),
                )
                for item in response["bars"]
            ),
            key=lambda item: (item.timestamp, item.symbol, item.source.value),
        )
    )
    attempts: tuple[CompositeSourceAttempt, ...] = ()
    return CompositeAcquisitionResult(
        partitions=partitions,
        quote_partition=quote_partition,
        attempts=attempts,
        bars=bars,
        quotes=response.get("quotes", {}),
        retrieved_at=RetrievedAt(datetime.fromisoformat(response["retrieved_at"])),
    )


def dataset_id(
    *,
    execution: TencentCompositeResearchExecution,
    candidate_data: PRRCandidateData,
    acquisition_id: str,
    code_revision: str,
    config_hash: str,
) -> str:
    return _identity(
        "prr-dataset",
        {
            "schema_version": PRR_DATASET_SCHEMA.schema_version,
            "acquisition_id": acquisition_id,
            "source_dataset_id": str(execution.dataset_contract.dataset_id),
            "ranking_content_hash": _canonical_hash(candidate_data.ranking_rows),
            "prepared_content_hash": _canonical_hash(execution.prepared.sessions),
            "code_revision": code_revision,
            "config_hash": config_hash,
        },
    )


def write_prr_dataset(
    *,
    root: str | Path,
    execution: TencentCompositeResearchExecution,
    candidate_data: PRRCandidateData,
    acquisition_id: str,
    raw_path: Path,
    code_revision: str,
    config_hash: str,
) -> tuple[str, Path, dict[str, Any]]:
    """Publish a content-identified normalized Dataset with complete rankings."""

    identifier = dataset_id(
        execution=execution,
        candidate_data=candidate_data,
        acquisition_id=acquisition_id,
        code_revision=code_revision,
        config_hash=config_hash,
    )
    final, stage = _reserve(Path(root), identifier)
    stage.mkdir(parents=True)
    try:
        bars = [
            {
                "symbol": bar.symbol,
                "timestamp": bar.timestamp,
                "session_date": bar.timestamp.date(),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "amount": bar.amount,
                "source": bar.source.value,
                "provider_id": _provider_for_source(bar.source.value),
                "source_partition_id": None,
                "retrieved_at": execution.acquisition.retrieved_at.value,
            }
            for bar in execution.merged.bars
        ]
        prepared = [
            {
                "symbol": session.symbol,
                "session_date": session.session_date,
                "open": session.open,
                "high": session.high,
                "low": session.low,
                "close": session.close,
                "amount": session.amount,
                "reference_price": session.reference_price,
                "reference_timestamp": session.reference_timestamp,
                "source_kinds": ",".join(item.value for item in session.source_kinds),
            }
            for session in execution.prepared.sessions
        ]
        snapshots = [
            {
                "decision_date": session.session_date,
                "decision_time": datetime.combine(
                    session.session_date,
                    datetime.min.time(),
                    tzinfo=session.reference_timestamp.tzinfo,
                ).replace(hour=14, minute=55),
                "symbol": session.symbol,
                "reference_price": session.reference_price,
                "reference_timestamp": session.reference_timestamp,
                "candidate_population_member": session.session_date in candidate_data.decision_dates,
                "feature_input_available": session.session_date in candidate_data.decision_dates,
            }
            for session in execution.prepared.sessions
            if session.session_date in candidate_data.decision_dates
        ]
        _write_parquet(stage / "bars.parquet", bars)
        _write_parquet(stage / "prepared_sessions.parquet", prepared)
        _write_parquet(stage / "decision_snapshots.parquet", snapshots)
        _write_parquet(stage / "candidate_rankings.parquet", candidate_data.ranking_rows)
        quality = {
            "disposition": "PASS" if execution.prepared.quality.success else "FAIL",
            "quality_gate": execution.prepared.quality,
            "after_hours_rows_excluded_by_acquisition": True,
            "reference_timestamp_convention": "<=14:50 source bar; declared 14:55 Decision Time",
            "candidate_decision_date_coverage": len(candidate_data.decision_dates),
            "source_attempt_retention": len(execution.acquisition.attempts),
            "source_conflict_retention": len(execution.merged.conflicts),
            "dataset_row_counts": {
                "bars": len(bars),
                "prepared_sessions": len(prepared),
                "decision_snapshots": len(snapshots),
                "candidate_rankings": len(candidate_data.ranking_rows),
            },
        }
        limitations = tuple(
            dict.fromkeys(
                (
                    *execution.limitations,
                    "HISTORICAL_PIT_NOT_VERIFIED",
                    "HISTORICAL_BUYABILITY_NOT_VERIFIED",
                    "BAR_FINALITY_NOT_VERIFIED",
                    "PRICE_ADJUSTMENT_LIMITATIONS_UNVERIFIED",
                    "AUXILIARY_DATA_ONLY",
                )
            )
        )
        _write_json(stage / "data_quality.json", quality)
        _write_json(stage / "limitations.json", limitations)
        checksums = _payload_checksums(stage)
        manifest = {
            "schema_version": "prr-mvp-1-dataset-v1",
            "dataset_id": identifier,
            "data_eligibility": "EXPLORATORY",
            "acquisition_id": acquisition_id,
            "raw_path": str(raw_path),
            "source_dataset_id": str(execution.dataset_contract.dataset_id),
            "provider_references": execution.dataset_contract.provider_references,
            "source_artifact_ids": [str(item.artifact_id) for item in execution.source_artifacts],
            "source_partition_hashes": [
                item.content_hash
                for item in (*execution.acquisition.partitions, execution.acquisition.quote_partition)
            ],
            "code_revision": code_revision,
            "config_hash": config_hash,
            "retrieved_at": execution.acquisition.retrieved_at,
            "acquisition_mode": execution.acquisition_mode,
            "symbol_count": 20,
            "accepted_symbol_count": len(execution.prepared.accepted_symbols),
            "session_count": len(execution.prepared.common_session_dates),
            "decision_count": len(candidate_data.decision_dates),
            "row_counts": quality["dataset_row_counts"],
            "date_range": {
                "start": execution.prepared.common_session_dates[0],
                "end": execution.prepared.common_session_dates[-1],
            },
            "frequency": "5min composite / prepared daily session",
            "price_basis": "SOURCE_ADJUSTMENT_SEMANTICS_UNVERIFIED",
            "decision_convention": "14:55 Asia/Shanghai; <=14:50 completed source reference",
            "availability_limitations": "RETRIEVED_AT_NOT_HISTORICAL_AVAILABILITY",
            "pit_limitations": "CURRENT_WATCHLIST_BACKFILL_BIAS",
            "buyability_limitations": "HISTORICAL_BUYABILITY_NOT_VERIFIED",
            "bar_finality_limitations": "SOURCE_FINALITY_NOT_PROVEN",
            "adjustment_limitations": "PRICE_ADJUSTMENT_REVISION_HISTORY_UNVERIFIED",
            "quality_disposition": quality["disposition"],
            "artifact_hashes": checksums,
        }
        _write_json(stage / "dataset_manifest.json", manifest)
        _write_checksums(stage)
        _validate_exact_set(stage, PRR_DATASET_SCHEMA.required_files)
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return identifier, final, manifest


def write_prr_run(
    *,
    root: str | Path,
    run_id: str,
    dataset_identifier: str,
    dataset_path: Path,
    dataset_manifest: Mapping[str, Any],
    execution: TencentCompositeResearchExecution,
    candidate_data: PRRCandidateData,
    replay: PRRReplayResult,
    acceptance: Mapping[str, Any],
    cost_config: ExploratoryExecutionCostConfig,
    config_snapshot: Mapping[str, Any],
) -> Path:
    """Publish the exact successful PRR run artifact through an atomic rename."""

    final, stage = _reserve(Path(root), run_id)
    stage.mkdir(parents=True)
    try:
        _write_json(stage / "config.snapshot.json", config_snapshot)
        _write_json(stage / "dataset_manifest.json", dataset_manifest)
        _write_json(
            stage / "provider_selection.json",
            {
                "source": "TENCENT_COMPOSITE",
                "data_eligibility": "EXPLORATORY",
                "acquisition_mode": execution.acquisition_mode,
                "canonical_provider_authority": "XUNTOU_PRIMARY_UNCHANGED",
            },
        )
        _write_json(stage / "source_artifacts.json", execution.source_artifacts)
        _write_json(stage / "data_quality.json", execution.prepared.quality)
        _write_json(stage / "candidate_panel_summary.json", execution.candidate_experiment.panel_summary())
        _write_json(stage / "model_evaluation.json", execution.candidate_experiment.evaluation_summary())
        _write_json(
            stage / "execution_assumptions.json",
            {
                "schema_version": PRR_MVP_1_SCHEMA_VERSION,
                "assumption_id": PRR_MVP_1_EXECUTION_ASSUMPTION,
                "cost_config": cost_config,
                "fee_notice": "RESEARCH ASSUMPTION — REQUIRES CURRENT EXTERNAL VERIFICATION",
                "reference_mark_notice": "14:55 reference price is not proof of a historical executable fill.",
            },
        )
        _write_parquet(stage / "orders.parquet", replay.orders)
        _write_parquet(stage / "fills.parquet", replay.fills)
        _write_parquet(stage / "trades.parquet", replay.trades)
        _write_parquet(stage / "daily_equity.parquet", replay.daily_equity)
        _write_parquet(stage / "selection_slot_outcomes.parquet", replay.selection_slot_outcomes)
        _write_monthly_metrics(stage / "monthly_metrics.csv", replay.daily_equity)
        _write_json(stage / "metrics.json", replay.metrics)
        _write_json(stage / "stability.json", _stability(replay.daily_equity))
        _write_json(stage / "acceptance_accounting.json", acceptance)
        limitations = tuple(dict.fromkeys((*execution.limitations, *replay.limitations)))
        _write_json(stage / "limitations.json", limitations)
        _write_report(
            stage / "report.md",
            run_id=run_id,
            dataset_identifier=dataset_identifier,
            dataset_path=dataset_path,
            execution=execution,
            replay=replay,
        )
        artifact_hashes = _payload_checksums(stage)
        _write_json(
            stage / "manifest.json",
            {
                "schema_version": "prr-mvp-1-run-v1",
                "run_id": run_id,
                "dataset_id": dataset_identifier,
                "dataset_path": str(dataset_path),
                "dataset_manifest_hash": _content_hash(dataset_path / "dataset_manifest.json"),
                "dataset_checksums_hash": _content_hash(dataset_path / "SHA256SUMS.json"),
                "data_eligibility": "EXPLORATORY",
                "acquisition_mode": execution.acquisition_mode,
                "decision_count": len(candidate_data.decision_dates),
                "model_count": len(replay.metrics["models"]),
                "artifact_hashes": artifact_hashes,
            },
        )
        _write_checksums(stage)
        _validate_exact_set(stage, RUN_FILENAMES)
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def write_prr_failure(
    *,
    root: str | Path,
    run_id: str,
    config_snapshot: Mapping[str, Any],
    error: Exception,
) -> Path:
    """Retain a failed acquisition/replay attempt without success-only artifacts."""

    final, stage = _reserve(Path(root), run_id)
    stage.mkdir(parents=True)
    try:
        _write_json(
            stage / "failure.json",
            {"error_type": type(error).__name__, "message": str(error), "config": config_snapshot},
        )
        (stage / "logs.jsonl").write_text(
            json.dumps({"event": "FAILED", "error_type": type(error).__name__, "message": str(error)}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _write_json(
            stage / "manifest.json",
            {"schema_version": "prr-mvp-1-run-v1", "run_id": run_id, "terminal_state": "FAILED", "data_eligibility": "EXPLORATORY"},
        )
        _write_checksums(stage)
        _validate_exact_set(stage, FAILURE_FILENAMES)
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def _reserve(root: Path, identifier: str) -> tuple[Path, Path]:
    if not identifier or Path(identifier).name != identifier:
        raise ValueError("artifact identifier must be a safe non-empty path name")
    final = root / identifier
    stage = root / f".{identifier}.staging"
    if final.exists() or stage.exists():
        raise FileExistsError(f"PRR artifact path already exists: {final}")
    return final, stage


def _validate_exact_set(stage: Path, expected: frozenset[str]) -> None:
    actual = {path.name for path in stage.iterdir()}
    if actual != expected:
        raise RuntimeError(f"incomplete PRR artifact: expected {sorted(expected)}, got {sorted(actual)}")


def _write_parquet(path: Path, rows: Any) -> None:
    pd.DataFrame(list(rows)).to_parquet(path, index=False)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(
            _json_value(value),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_monthly_metrics(path: Path, rows: tuple[dict[str, Any], ...]) -> None:
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        frame.to_csv(path, index=False)
        return
    frame["month"] = pd.to_datetime(frame["session_date"]).dt.to_period("M").astype(str)
    frame.groupby(["model_id", "month"], as_index=False).agg(
        gross_return=("gross_return", "sum"),
        net_return=("net_return", "sum"),
        transaction_cost=("transaction_cost", "sum"),
    ).to_csv(path, index=False)


def _stability(rows: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        return {"monthly": []}
    frame["month"] = pd.to_datetime(frame["session_date"]).dt.to_period("M").astype(str)
    return {
        "monthly": frame.groupby(["model_id", "month"], as_index=False)["net_return"].sum().to_dict(orient="records"),
        "descriptive_only": True,
    }


def _write_report(
    path: Path,
    *,
    run_id: str,
    dataset_identifier: str,
    dataset_path: Path,
    execution: TencentCompositeResearchExecution,
    replay: PRRReplayResult,
) -> None:
    lines = [
        "# PRR-MVP-1 Candidate Backtest",
        "",
        f"- Run ID: `{run_id}`",
        f"- Dataset ID: `{dataset_identifier}`",
        f"- Dataset path: `{dataset_path}`",
        "- Data eligibility: `EXPLORATORY`",
        f"- Acquisition mode: `{execution.acquisition_mode}`",
        "- Model policy: fixed B0 controls and B1-A through B1-E; DESCRIPTIVE ONLY — NO MODEL SELECTION.",
        "",
        "## Execution limitation",
        "",
        "The 14:55 reference price is a research mark. It is not proof that an order could have been filled at that price. No order-book, queue, Level-2, partial-fill, or market-impact evidence is available.",
        "",
        "## Metrics",
        "",
    ]
    for model_id, metrics in replay.metrics["models"].items():
        lines.append(f"- `{model_id}`: net cumulative return `{metrics['net_cumulative_return']}`; maximum drawdown `{metrics['maximum_drawdown']}`; trades `{metrics['trade_count']}`")
    lines.extend(["", "## Limitations", "", *[f"- `{item}`" for item in replay.limitations]])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_checksums(stage: Path) -> None:
    _write_json(stage / "SHA256SUMS.json", _payload_checksums(stage))


def _payload_checksums(stage: Path) -> dict[str, str]:
    return {
        path.name: _content_hash(path)
        for path in sorted(stage.iterdir(), key=lambda value: value.name)
        if path.name != "SHA256SUMS.json"
    }


def _content_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _canonical_hash(value: Any) -> str:
    canonical = json.dumps(_json_value(value), ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"


def _identity(prefix: str, payload: Mapping[str, Any]) -> str:
    return f"{prefix}-{_canonical_hash(payload).removeprefix('sha256:')[:24]}"


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, StableId):
        return str(value)
    if isinstance(value, SemanticTime):
        return value.isoformat()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_value(item) for item in value]
    return value


def _bar_date_range(execution: TencentCompositeResearchExecution, symbols: tuple[str, ...]) -> dict[str, str | None]:
    dates = [bar.timestamp.date() for bar in execution.acquisition.bars if bar.symbol in symbols]
    return {"start": min(dates).isoformat() if dates else None, "end": max(dates).isoformat() if dates else None}


def _provider_for_source(source: str) -> str:
    return {"TENCENT": "provider-tencent-public", "LOCAL": "provider-local-cache", "BAOSTOCK": "provider-baostock"}[source]
