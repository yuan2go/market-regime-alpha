#!/usr/bin/env python3
"""Acquire, finalize, replay, settle, or report the Phase D daily loop."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time
import json
from pathlib import Path
import subprocess
import sys
from typing import Sequence
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from market_regime_alpha.application.daily_loop import (
    DAILY_B0_B1_MODEL_SET_ID,
    DailyLoopRunResult,
    DailyLoopRunner,
    DailyRunCommand,
    DailyRunId,
    RunMode,
    SQLiteDailyRunRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.providers.public_composite import (
    PUBLIC_COMPOSITE_LIVE_PROFILE_ID,
    PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
    BaoStockHistoryClient,
    BaoStockSecurityStatusClient,
    PublicCompositeLiveProfile,
    SourceReplayArchiveReader,
    TencentCurrentQuoteClient,
)
from market_regime_alpha.universe.daily_exploratory import smoke_pool_policy_v1


SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_OUTPUT_ROOT = (
    PROJECT_ROOT / "data" / "processed" / "exploratory_daily_loop"
)
DEFAULT_CONFIGURATION_ID = ArtifactId(
    "exploratory-daily-loop-cli-configuration-v1"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--journal", type=Path)
    commands = parser.add_subparsers(dest="operation", required=True)

    run = commands.add_parser("run", help="run one LIVE or archive-backed day")
    _add_daily_arguments(run, allow_replay=True)
    run.add_argument("--source-archive", type=Path)

    prepare_history = commands.add_parser(
        "prepare-history",
        help="freeze BaoStock prior-session daily history",
    )
    _add_daily_arguments(prepare_history, allow_replay=False)

    freeze_status = commands.add_parser(
        "freeze-security-status",
        help="freeze exact decision-session BaoStock status evidence",
    )
    _add_daily_arguments(freeze_status, allow_replay=False)

    freeze_quote = commands.add_parser(
        "freeze-decision-quote",
        help="freeze Tencent quotes inside the decision window",
    )
    _add_daily_arguments(freeze_quote, allow_replay=False)

    finalize = commands.add_parser(
        "finalize-run",
        help="finalize from three verified frozen LIVE stages without network",
    )
    _add_daily_arguments(finalize, allow_replay=False)

    replay = commands.add_parser(
        "replay",
        help="verify and reconstruct an existing Daily Decision Artifact",
    )
    replay.add_argument("--run-id", type=DailyRunId, required=True)

    settle = commands.add_parser(
        "settle",
        help="append MR1 10:30 outcomes from an immutable archive",
    )
    settle.add_argument("--run-id", type=DailyRunId, required=True)
    settle.add_argument("--settlement-archive", type=Path)

    report = commands.add_parser(
        "report",
        help="reconstruct the latest Markdown report",
    )
    report.add_argument("--run-id", type=DailyRunId, required=True)
    return parser


def _add_daily_arguments(
    parser: argparse.ArgumentParser,
    *,
    allow_replay: bool,
) -> None:
    parser.add_argument("--decision-date", type=date.fromisoformat, required=True)
    choices = (
        (
            PUBLIC_COMPOSITE_LIVE_PROFILE_ID,
            PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
        )
        if allow_replay
        else (PUBLIC_COMPOSITE_LIVE_PROFILE_ID,)
    )
    parser.add_argument(
        "--provider-profile",
        choices=choices,
        default=PUBLIC_COMPOSITE_LIVE_PROFILE_ID,
    )
    parser.add_argument(
        "--configuration-identity",
        type=ArtifactId,
        default=DEFAULT_CONFIGURATION_ID,
    )
    parser.add_argument("--timeout-seconds", type=float, default=8.0)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_root = args.output_root.resolve()
    journal = (
        args.journal.resolve()
        if args.journal is not None
        else output_root / "runtime-journal.sqlite3"
    )
    repository = SQLiteDailyRunRepository(journal)
    live_profile = None
    if args.operation in {
        "run",
        "prepare-history",
        "freeze-security-status",
        "freeze-decision-quote",
    } and (
        args.provider_profile == PUBLIC_COMPOSITE_LIVE_PROFILE_ID
    ):
        live_profile = PublicCompositeLiveProfile(
            history_client=BaoStockHistoryClient(),
            security_status_client=BaoStockSecurityStatusClient(
                timeout_seconds=args.timeout_seconds
            ),
            current_client=TencentCurrentQuoteClient(
                timeout_seconds=args.timeout_seconds
            ),
        )
    runner = DailyLoopRunner(
        repository=repository,
        code_revision=_current_git_revision(),
        live_profile=live_profile,
    )
    if args.operation == "run":
        return _run(args, runner, output_root)
    if args.operation in {
        "prepare-history",
        "freeze-security-status",
        "freeze-decision-quote",
    }:
        command = _build_command(args, output_root=output_root)
        operation = {
            "prepare-history": runner.prepare_history,
            "freeze-security-status": runner.freeze_security_status,
            "freeze-decision-quote": runner.freeze_decision_quote,
        }[args.operation]
        receipt = operation(command)
        _print_json(
            {
                "run_request_id": str(receipt.run_request_id),
                "stage": receipt.stage.value,
                "artifact_id": str(receipt.artifact_id),
                "content_hash": receipt.content_hash,
                "status": "SOURCE_ACQUIRING",
            }
        )
        return 0
    if args.operation == "finalize-run":
        completed = runner.finalize_run(
            _build_command(args, output_root=output_root)
        )
        _print_completed(completed)
        return 0
    if args.operation == "replay":
        verified = runner.replay_daily_run(args.run_id)
        _print_json(
            {
                "daily_run_id": str(args.run_id),
                "artifact_id": verified.artifact_id,
                "status": verified.bundle.status.value,
                "replay_hash": verified.checksums_hash,
            }
        )
        return 0
    if args.operation == "settle":
        if args.settlement_archive is None:
            record = repository.get_by_daily_run_id(args.run_id)
            _print_json(
                {
                    "daily_run_id": str(args.run_id),
                    "status": record.status.value,
                    "settlement": "OUTCOME_ARCHIVE_REQUIRED",
                }
            )
            return 0
        settled = runner.settle_daily_run(
            args.run_id,
            settlement_archive_path=args.settlement_archive.resolve(),
        )
        _print_json(
            {
                "daily_run_id": str(args.run_id),
                "status": settled.record.status.value,
                "artifact_id": settled.review_artifact.artifact_id,
                "replay_hash": settled.review_artifact.checksums_hash,
                "outcome_coverage": (
                    settled.review_artifact.settlement.review.outcome_coverage
                ),
            }
        )
        return 0
    if args.operation == "report":
        sys.stdout.write(runner.report_daily_run(args.run_id))
        return 0
    raise AssertionError(f"unsupported operation: {args.operation}")


def _run(
    args: argparse.Namespace,
    runner: DailyLoopRunner,
    output_root: Path,
) -> int:
    run_mode = (
        RunMode.LIVE
        if args.provider_profile == PUBLIC_COMPOSITE_LIVE_PROFILE_ID
        else RunMode.REPLAY
    )
    replay_source_manifest_id = None
    source_archive = args.source_archive
    if run_mode is RunMode.REPLAY:
        if source_archive is None:
            raise ValueError(
                "public-composite-replay-v1 requires --source-archive"
            )
        acquired = SourceReplayArchiveReader().read(source_archive.resolve())
        replay_source_manifest_id = (
            acquired.source_manifest.source_manifest_id
        )
    elif source_archive is not None:
        raise ValueError("LIVE does not accept --source-archive")
    command = _build_command(
        args,
        output_root=output_root,
        replay_source_manifest_id=replay_source_manifest_id,
    )
    completed = runner.run(
        command,
        replay_archive_path=(
            source_archive.resolve() if source_archive is not None else None
        ),
    )
    _print_completed(completed)
    return 0


def _build_command(
    args: argparse.Namespace,
    *,
    output_root: Path,
    replay_source_manifest_id: ArtifactId | None = None,
) -> DailyRunCommand:
    policy = smoke_pool_policy_v1()
    run_mode = (
        RunMode.REPLAY
        if args.provider_profile == PUBLIC_COMPOSITE_REPLAY_PROFILE_ID
        else RunMode.LIVE
    )
    decision_time = DecisionTime(
        datetime.combine(args.decision_date, time(14, 55), tzinfo=SHANGHAI)
    )
    return DailyRunCommand(
        decision_date=args.decision_date,
        decision_time=decision_time,
        run_mode=run_mode,
        provider_profile_id=args.provider_profile,
        universe_policy_id=str(policy.policy_id),
        model_set_id=DAILY_B0_B1_MODEL_SET_ID,
        configuration_identity=args.configuration_identity,
        output_root=output_root,
        replay_source_manifest_id=replay_source_manifest_id,
    )


def _print_completed(completed: DailyLoopRunResult) -> None:
    _print_json(
        {
            "run_request_id": str(completed.record.run_request_id),
            "daily_run_id": str(completed.record.daily_run_id),
            "status": completed.record.status.value,
            "source_archive_id": completed.source_archive_path.name,
            "artifact_id": completed.decision_artifact.artifact_id,
            "replay_hash": completed.decision_artifact.checksums_hash,
            "blocked_reasons": list(
                completed.decision_artifact.bundle.data_quality_report.blocked_reason_codes
            ),
            "data_eligibility": (
                completed.decision_artifact.bundle.source_manifest.data_eligibility.value
            ),
            "delivery_authority": "EXPLORATORY_DAILY_LOOP_OPERATIONAL",
            "formal_oos_authority": "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "trading_authority": "TRADING_AUTHORITY_NOT_GRANTED",
        }
    )


def _current_git_revision() -> str:
    result = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _print_json(payload: dict[str, object]) -> None:
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
