#!/usr/bin/env python3
"""Run the bounded Tencent/local/BaoStock EXPLORATORY research workflow."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.time import RetrievedAt
from market_regime_alpha.data.contracts import DataEligibility, SourceArtifactReference
from market_regime_alpha.data_sources.a_share_bars import (
    BaoStockADataProvider,
    TencentMinuteProvider,
    fetch_tencent_latest_quotes,
    read_local_5min_cache,
)
from market_regime_alpha.dividend_t.storage import DEFAULT_WATCHLIST_PATH, load_watchlist
from market_regime_alpha.dividend_t.trend_snapshot import (
    DEFAULT_LOCAL_TIMING_CACHE_DIR,
    DEFAULT_TREND_OUTPUT,
    write_dividend_trend_snapshot,
)
from market_regime_alpha.research.tencent_composite_acquisition import (
    TencentCompositeAcquirer,
    frames_for_accepted_symbols,
    merge_acquisition,
)
from market_regime_alpha.research.tencent_composite_artifacts import (
    write_tencent_composite_quality_failure,
    write_tencent_composite_run,
)
from market_regime_alpha.research.tencent_composite_contracts import (
    TENCENT_COMPOSITE_DECISION_CONVENTION,
    CompositeAcquisitionResult,
    build_tencent_composite_dataset_contract,
)
from market_regime_alpha.research.tencent_composite_dividend_t import (
    refresh_dividend_t_from_composite,
)
from market_regime_alpha.research.tencent_composite_quality import (
    TencentCompositeQualityGateError,
    prepare_composite_data,
)
from market_regime_alpha.research.tencent_composite_runner import (
    run_tencent_composite_candidate_experiment,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "processed" / "tencent_composite_exploratory"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Tencent composite EXPLORATORY Candidate research"
    )
    parser.add_argument("--watchlist", type=Path, default=DEFAULT_WATCHLIST_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--snapshot-output", type=Path, default=DEFAULT_TREND_OUTPUT)
    parser.add_argument("--local-cache-dir", type=Path, default=DEFAULT_LOCAL_TIMING_CACHE_DIR)
    parser.add_argument("--decision-count", type=int, default=60)
    parser.add_argument("--warmup-sessions", type=int, default=21)
    parser.add_argument("--minimum-accepted-symbols", type=int, default=16)
    parser.add_argument("--history-calendar-days", type=int, default=180)
    parser.add_argument("--timeout-seconds", type=float, default=8.0)
    parser.add_argument("--retry-count", type=int, default=2)
    parser.add_argument("--retrieved-at")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    retrieved_at = _retrieved_at(args.retrieved_at)
    items = load_watchlist(args.watchlist)[:20]
    if len(items) != 20:
        raise ValueError("Tencent composite run requires the first 20 watchlist symbols")
    watchlist = tuple(item.symbol for item in items)
    code_revision = current_git_revision()
    watchlist_hash = _file_hash(args.watchlist)
    config_hash = _config_hash(args, watchlist)
    run_id = _run_id(retrieved_at, config_hash, watchlist_hash)
    for reserved in (args.output_root / run_id, args.output_root / f"{run_id}-failed"):
        if reserved.exists():
            raise FileExistsError(f"run output already exists: {reserved}")
    acquirer = build_default_acquirer(
        timeout_seconds=args.timeout_seconds,
        retry_count=args.retry_count,
        local_cache_dir=args.local_cache_dir,
    )
    acquisition = acquirer.acquire(
        symbols=watchlist,
        start_date=(retrieved_at.value.date() - timedelta(days=args.history_calendar_days)).isoformat(),
        end_date=retrieved_at.value.date().isoformat(),
        retrieved_at=retrieved_at.value,
    )
    merged = merge_acquisition(acquisition)
    contract = build_contract_from_acquisition(
        acquisition,
        watchlist_hash=watchlist_hash,
        code_revision=code_revision,
        config_hash=config_hash,
    )
    base_manifest = build_manifest(
        run_id=run_id,
        acquisition=acquisition,
        contract=contract,
        watchlist=watchlist,
        watchlist_hash=watchlist_hash,
        code_revision=code_revision,
        config_hash=config_hash,
        source_conflict_count=len(merged.conflicts),
    )
    try:
        prepared = prepare_composite_data(
            merged,
            requested_symbols=watchlist,
            decision_count=args.decision_count,
            warmup_sessions=args.warmup_sessions,
            minimum_accepted_symbols=args.minimum_accepted_symbols,
        )
    except TencentCompositeQualityGateError as exc:
        failed = write_tencent_composite_quality_failure(
            root=args.output_root,
            run_id=f"{run_id}-failed",
            manifest={
                **base_manifest,
                "run_id": f"{run_id}-failed",
                "failure": "COMPOSITE_QUALITY_GATE_FAILED",
            },
            quality=exc.quality,
        )
        print(f"quality gate failed: {failed}", file=sys.stderr)
        return 2

    candidate = run_tencent_composite_candidate_experiment(
        prepared=prepared,
        dataset_contract=contract,
        retrieved_at=retrieved_at,
        code_revision=code_revision,
        config_hash=config_hash,
    )
    before = read_snapshot_if_present(args.snapshot_output)
    dividend = refresh_dividend_t_from_composite(
        watchlist_path=args.watchlist,
        frames=frames_for_accepted_symbols(merged, prepared.accepted_symbols),
        quotes=acquisition.quotes,
        before_snapshot=before,
        generated_at=retrieved_at.value,
    )
    write_dividend_trend_snapshot(dividend.snapshot, output_path=args.snapshot_output)
    manifest = {
        **base_manifest,
        "accepted_symbols": list(prepared.accepted_symbols),
        "common_session_count": len(prepared.common_session_dates),
        "decision_date_count": candidate.decision_date_count,
    }
    output = write_tencent_composite_run(
        root=args.output_root,
        run_id=run_id,
        manifest=manifest,
        quality=prepared.quality,
        conflicts=merged.conflicts,
        candidate_run=candidate,
        dividend_refresh=dividend,
    )
    print(
        f"completed {output}: accepted={len(prepared.accepted_symbols)} "
        f"sessions={len(prepared.common_session_dates)} decisions={candidate.decision_date_count}"
    )
    return 0


def build_default_acquirer(
    *,
    timeout_seconds: float,
    retry_count: int,
    local_cache_dir: Path,
) -> TencentCompositeAcquirer:
    """Compose current public adapters without hiding their identities."""

    return TencentCompositeAcquirer(
        tencent=TencentMinuteProvider(timeout_seconds=timeout_seconds),
        baostock=BaoStockADataProvider(),
        local_reader=partial(read_local_5min_cache, cache_dir=local_cache_dir),
        quote_fetcher=partial(fetch_tencent_latest_quotes, timeout_seconds=timeout_seconds),
        retry_count=retry_count,
    )


def build_contract_from_acquisition(
    acquisition: CompositeAcquisitionResult,
    *,
    watchlist_hash: str,
    code_revision: str,
    config_hash: str,
):
    hashes = tuple(
        partition.content_hash
        for partition in (*acquisition.partitions, acquisition.quote_partition)
    )
    return build_tencent_composite_dataset_contract(
        watchlist_hash=watchlist_hash,
        source_content_hashes=hashes,
        code_revision=code_revision,
        config_hash=config_hash,
    )


def build_manifest(
    *,
    run_id: str,
    acquisition: CompositeAcquisitionResult,
    contract: Any,
    watchlist: tuple[str, ...],
    watchlist_hash: str,
    code_revision: str,
    config_hash: str,
    source_conflict_count: int,
) -> dict[str, Any]:
    partitions = list(acquisition.partitions)
    if acquisition.quote_partition is not None:
        partitions.append(acquisition.quote_partition)
    source_artifacts = tuple(_source_artifact(partition) for partition in partitions)
    return {
        "run_id": run_id,
        "schema_version": "tencent-composite-exploratory-run-v1",
        "data_eligibility": DataEligibility.EXPLORATORY.value,
        "dataset_id": str(contract.dataset_id),
        "retrieved_at": acquisition.retrieved_at.isoformat(),
        "watchlist": list(watchlist),
        "watchlist_hash": watchlist_hash,
        "code_revision": code_revision,
        "config_hash": config_hash,
        "decision_convention": TENCENT_COMPOSITE_DECISION_CONVENTION,
        "canonical_provider_authority": "XUNTOU_PRIMARY_UNCHANGED",
        "source_partitions": partitions,
        "source_artifacts": source_artifacts,
        "source_attempts": acquisition.attempts,
        "source_conflict_count": source_conflict_count,
        "limitations": list(contract.limitations),
    }


def current_git_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def read_snapshot_if_present(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("existing dividend snapshot must contain a JSON object")
    return value


def _source_artifact(partition: Any) -> SourceArtifactReference:
    payload = {
        "provider_id": str(partition.provider_id),
        "product": partition.product,
        "retrieved_at": partition.retrieved_at.isoformat(),
        "content_hash": partition.content_hash,
        "locator": partition.locator,
    }
    digest = _canonical_digest(payload)
    return SourceArtifactReference(
        artifact_id=ArtifactId(f"source-tencent-composite-{digest[:24]}"),
        provider_id=partition.provider_id,
        retrieved_at=partition.retrieved_at,
        content_hash=partition.content_hash,
        locator=partition.locator,
    )


def _retrieved_at(raw: str | None) -> RetrievedAt:
    if raw is None:
        return RetrievedAt(datetime.now(SHANGHAI_TZ))
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--retrieved-at must be timezone-aware ISO-8601")
    return RetrievedAt(parsed.astimezone(SHANGHAI_TZ))


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _config_hash(args: argparse.Namespace, watchlist: tuple[str, ...]) -> str:
    payload = {
        "schema_version": "tencent-composite-exploratory-config-v1",
        "watchlist": list(watchlist),
        "decision_count": args.decision_count,
        "warmup_sessions": args.warmup_sessions,
        "minimum_accepted_symbols": args.minimum_accepted_symbols,
        "history_calendar_days": args.history_calendar_days,
        "retry_count": args.retry_count,
        "decision_convention": TENCENT_COMPOSITE_DECISION_CONVENTION,
    }
    return f"sha256:{_canonical_digest(payload)}"


def _run_id(retrieved_at: RetrievedAt, config_hash: str, watchlist_hash: str) -> str:
    timestamp = retrieved_at.value.strftime("%Y%m%dT%H%M%S%z")
    suffix = _canonical_digest({"config_hash": config_hash, "watchlist_hash": watchlist_hash})[:10]
    return f"tencent-composite-{timestamp}-{suffix}"


def _canonical_digest(payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
