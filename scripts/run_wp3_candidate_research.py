#!/usr/bin/env python3
"""Run source-aware WP-3 Candidate research without live-trading side effects."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, Sequence
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.time import RetrievedAt
from market_regime_alpha.data import DataEligibility, SourceArtifactReference
from market_regime_alpha.data_sources.a_share_bars import (
    BaoStockADataProvider,
    TencentMinuteProvider,
    fetch_tencent_latest_quotes,
    read_local_5min_cache,
)
from market_regime_alpha.dividend_t.storage import DEFAULT_WATCHLIST_PATH, load_watchlist
from market_regime_alpha.dividend_t.trend_snapshot import DEFAULT_LOCAL_TIMING_CACHE_DIR
from market_regime_alpha.research.provider_routing import (
    CandidateDataSource,
    CandidateRunSourceMode,
    ProviderAvailabilityStatus,
    ProviderCapabilityReport,
)
from market_regime_alpha.research.tencent_composite_acquisition import (
    TencentCompositeAcquirer,
    merge_acquisition,
)
from market_regime_alpha.research.tencent_composite_contracts import (
    TENCENT_COMPOSITE_DECISION_CONVENTION,
    CompositeAcquisitionResult,
    build_tencent_composite_dataset_contract,
)
from market_regime_alpha.research.tencent_composite_quality import (
    TencentCompositeQualityGateError,
    prepare_composite_data,
)
from market_regime_alpha.research.tencent_composite_runner import (
    run_tencent_composite_candidate_experiment,
)
from market_regime_alpha.research.wp3_orchestrator import (
    WP3BackendExecutionError,
    WP3BackendResult,
    WP3ExecutionErrorCode,
    WP3RunRequest,
    execute_wp3_candidate_run,
)


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "processed" / "r5_candidate_runs"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run source-aware Xuntou/Tencent WP-3 Candidate research"
    )
    parser.add_argument("--source", choices=("auto", "xuntou", "tencent"), default="auto")
    parser.add_argument(
        "--minimum-eligibility",
        choices=("exploratory", "rehearsal"),
        default="exploratory",
    )
    parser.add_argument("--xuntou-bundle", type=Path)
    parser.add_argument("--minimum-liquidity-value", type=float)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--watchlist", type=Path, default=DEFAULT_WATCHLIST_PATH)
    parser.add_argument("--local-cache-dir", type=Path, default=DEFAULT_LOCAL_TIMING_CACHE_DIR)
    parser.add_argument("--decision-count", type=int, default=60)
    parser.add_argument("--warmup-sessions", type=int, default=21)
    parser.add_argument("--minimum-accepted-symbols", type=int, default=16)
    parser.add_argument("--history-calendar-days", type=int, default=180)
    parser.add_argument("--timeout-seconds", type=float, default=8.0)
    parser.add_argument("--retry-count", type=int, default=2)
    parser.add_argument("--retrieved-at")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    orchestrator: Callable[..., Path] = execute_wp3_candidate_run,
    tencent_backend_factory: Callable[[argparse.Namespace, datetime], Any] | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.source == "xuntou" and args.xuntou_bundle is None:
        parser.error("--source xuntou requires --xuntou-bundle")
    if args.xuntou_bundle is not None and args.minimum_liquidity_value is None:
        parser.error("--xuntou-bundle requires --minimum-liquidity-value")
    if args.minimum_liquidity_value is not None and args.minimum_liquidity_value <= 0.0:
        parser.error("--minimum-liquidity-value must be positive")

    retrieved_at = parse_retrieved_at(args.retrieved_at)
    code_revision = current_git_revision()
    run_config_hash = config_hash(args)
    run_id = run_identity(retrieved_at, run_config_hash)
    request = WP3RunRequest(
        run_id=run_id,
        source_mode={
            "auto": CandidateRunSourceMode.AUTO,
            "xuntou": CandidateRunSourceMode.XUNTOU,
            "tencent": CandidateRunSourceMode.TENCENT,
        }[args.source],
        minimum_eligibility={
            "exploratory": DataEligibility.EXPLORATORY,
            "rehearsal": DataEligibility.REHEARSAL,
        }[args.minimum_eligibility],
        output_root=args.output_root,
        xuntou_bundle=args.xuntou_bundle,
        decision_count=args.decision_count,
        code_revision=code_revision,
        config_hash=run_config_hash,
        minimum_liquidity_value=args.minimum_liquidity_value,
    )
    factory = tencent_backend_factory or build_tencent_backend
    backend = factory(args, retrieved_at)
    output = orchestrator(request, tencent_backend=backend)
    if (output / "failure.json").exists():
        print(f"WP-3 failed with retained evidence: {output}", file=sys.stderr)
        return 2
    print(f"WP-3 completed: {output}")
    return 0


class TencentCompositeWP3Backend:
    """Temporary Tencent/local/BaoStock EXPLORATORY Candidate backend."""

    def __init__(
        self,
        *,
        args: argparse.Namespace,
        retrieved_at: datetime,
        acquirer: TencentCompositeAcquirer,
    ) -> None:
        self.args = args
        self.retrieved_at = RetrievedAt(retrieved_at)
        self.acquirer = acquirer

    def capability_report(self) -> ProviderCapabilityReport:
        watchlist_items = load_watchlist(self.args.watchlist)[:20]
        if not self.args.watchlist.is_file() or len(watchlist_items) != 20:
            return ProviderCapabilityReport(
                source=CandidateDataSource.TENCENT_COMPOSITE,
                availability_status=ProviderAvailabilityStatus.INVALID,
                maximum_data_eligibility=DataEligibility.EXPLORATORY,
                supported_evidence=("TEMPORARY_EXPLORATORY_OHLCV",),
                unsupported_evidence=(
                    "HISTORICAL_PIT",
                    "HISTORICAL_BUYABILITY",
                    "REHEARSAL",
                    "FORMAL_RESEARCH",
                ),
                limitations=("TENCENT_WATCHLIST_CONFIGURATION_INVALID",),
                input_identity=f"tencent-watchlist:{self.args.watchlist}",
            )
        watchlist_hash = file_hash(self.args.watchlist)
        return ProviderCapabilityReport(
            source=CandidateDataSource.TENCENT_COMPOSITE,
            availability_status=ProviderAvailabilityStatus.AVAILABLE,
            maximum_data_eligibility=DataEligibility.EXPLORATORY,
            supported_evidence=("TEMPORARY_EXPLORATORY_OHLCV", "FIXED_B0_B1_INPUT"),
            unsupported_evidence=(
                "HISTORICAL_PIT",
                "HISTORICAL_BUYABILITY",
                "REHEARSAL",
                "FORMAL_RESEARCH",
            ),
            limitations=(
                "CURRENT_WATCHLIST_BACKFILL_BIAS",
                "TENCENT_TEMPORARY_TRAINING_ROUTE",
            ),
            input_identity=f"tencent-watchlist:{watchlist_hash}",
        )

    def execute(self, request: WP3RunRequest) -> WP3BackendResult:
        if request.decision_count != 60:
            raise WP3BackendExecutionError(
                WP3ExecutionErrorCode.CANDIDATE_MATERIALIZATION_FAILED,
                "current Tencent composite Candidate contract requires decision_count=60",
            )
        items = load_watchlist(self.args.watchlist)[:20]
        if len(items) != 20:
            raise WP3BackendExecutionError(
                WP3ExecutionErrorCode.TENCENT_QUALITY_GATE_FAILED,
                "Tencent composite route requires exactly 20 configured watchlist symbols",
            )
        watchlist = tuple(item.symbol for item in items)
        acquisition = self.acquirer.acquire(
            symbols=watchlist,
            start_date=(
                self.retrieved_at.value.date()
                - timedelta(days=self.args.history_calendar_days)
            ).isoformat(),
            end_date=self.retrieved_at.value.date().isoformat(),
            retrieved_at=self.retrieved_at.value,
        )
        merged = merge_acquisition(acquisition)
        contract = _tencent_dataset_contract(
            acquisition,
            watchlist_hash=file_hash(self.args.watchlist),
            code_revision=request.code_revision,
            config_hash=request.config_hash,
        )
        try:
            prepared = prepare_composite_data(
                merged,
                requested_symbols=watchlist,
                decision_count=request.decision_count,
                warmup_sessions=self.args.warmup_sessions,
                minimum_accepted_symbols=self.args.minimum_accepted_symbols,
            )
        except TencentCompositeQualityGateError as exc:
            raise WP3BackendExecutionError(
                WP3ExecutionErrorCode.TENCENT_QUALITY_GATE_FAILED,
                str(exc),
                evidence={
                    "quality": exc.quality,
                    "source_attempts": acquisition.attempts,
                    "source_conflicts": merged.conflicts,
                },
            ) from exc
        candidate = run_tencent_composite_candidate_experiment(
            prepared=prepared,
            dataset_contract=contract,
            retrieved_at=self.retrieved_at,
            code_revision=request.code_revision,
            config_hash=request.config_hash,
        )
        source_artifacts = _source_artifacts(acquisition)
        return WP3BackendResult(
            source=CandidateDataSource.TENCENT_COMPOSITE,
            data_eligibility=DataEligibility.EXPLORATORY,
            dataset_id=contract.dataset_id,
            provider_references=contract.provider_references,
            source_artifacts=source_artifacts,
            quality={
                "quality_gate": prepared.quality,
                "source_attempts": acquisition.attempts,
                "source_conflicts": merged.conflicts,
            },
            candidate_panel_summary=candidate.panel_summary(),
            b0_b1_evaluation=candidate.evaluation_summary(),
            limitations=candidate.limitations,
            manifest_details={
                "retrieved_at": acquisition.retrieved_at.isoformat(),
                "watchlist": list(watchlist),
                "watchlist_hash": file_hash(self.args.watchlist),
                "decision_convention": TENCENT_COMPOSITE_DECISION_CONVENTION,
                "source_conflict_count": len(merged.conflicts),
                "canonical_provider_authority": "XUNTOU_PRIMARY_UNCHANGED",
                "feature_definition_ids": [
                    str(value)
                    for value in candidate.target_runs[0].panel.feature_definition_ids
                ],
                "target_ids": [str(item.target_id) for item in candidate.target_runs],
            },
        )


def build_tencent_backend(
    args: argparse.Namespace,
    retrieved_at: datetime,
) -> TencentCompositeWP3Backend:
    acquirer = TencentCompositeAcquirer(
        tencent=TencentMinuteProvider(timeout_seconds=args.timeout_seconds),
        baostock=BaoStockADataProvider(),
        local_reader=partial(read_local_5min_cache, cache_dir=args.local_cache_dir),
        quote_fetcher=partial(
            fetch_tencent_latest_quotes,
            timeout_seconds=args.timeout_seconds,
        ),
        retry_count=args.retry_count,
    )
    return TencentCompositeWP3Backend(
        args=args,
        retrieved_at=retrieved_at,
        acquirer=acquirer,
    )


def config_hash(args: argparse.Namespace) -> str:
    payload = {
        "schema_version": "wp3-provider-candidate-config-v1",
        "source": args.source,
        "minimum_eligibility": args.minimum_eligibility,
        "xuntou_bundle_hash": optional_file_hash(args.xuntou_bundle),
        "minimum_liquidity_value": args.minimum_liquidity_value,
        "watchlist_hash": optional_file_hash(args.watchlist),
        "decision_count": args.decision_count,
        "warmup_sessions": args.warmup_sessions,
        "minimum_accepted_symbols": args.minimum_accepted_symbols,
        "history_calendar_days": args.history_calendar_days,
        "timeout_seconds": args.timeout_seconds,
        "retry_count": args.retry_count,
        "decision_time_convention": "14:55:00 Asia/Shanghai",
    }
    return f"sha256:{canonical_digest(payload)}"


def parse_retrieved_at(raw: str | None) -> datetime:
    if raw is None:
        return datetime.now(SHANGHAI_TZ)
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--retrieved-at must be timezone-aware ISO-8601")
    return parsed.astimezone(SHANGHAI_TZ)


def current_git_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def run_identity(retrieved_at: datetime, run_config_hash: str) -> str:
    timestamp = retrieved_at.strftime("%Y%m%dT%H%M%S%z")
    suffix = canonical_digest({"config_hash": run_config_hash})[:10]
    return f"wp3-candidate-{timestamp}-{suffix}"


def file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def optional_file_hash(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    return file_hash(path)


def canonical_digest(payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


def _tencent_dataset_contract(
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


def _source_artifacts(
    acquisition: CompositeAcquisitionResult,
) -> tuple[SourceArtifactReference, ...]:
    partitions = (*acquisition.partitions, acquisition.quote_partition)
    return tuple(_source_artifact(partition) for partition in partitions)


def _source_artifact(partition: Any) -> SourceArtifactReference:
    payload = {
        "provider_id": str(partition.provider_id),
        "product": partition.product,
        "retrieved_at": partition.retrieved_at.isoformat(),
        "content_hash": partition.content_hash,
        "locator": partition.locator,
    }
    digest = canonical_digest(payload)
    return SourceArtifactReference(
        artifact_id=ArtifactId(f"source-wp3-tencent-{digest[:24]}"),
        provider_id=partition.provider_id,
        retrieved_at=partition.retrieved_at,
        content_hash=partition.content_hash,
        locator=partition.locator,
    )


if __name__ == "__main__":
    raise SystemExit(main())
