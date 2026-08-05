"""Operate the PostgreSQL-backed Tencent free-data Canonical composition."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, time
from decimal import Decimal
import json
from pathlib import Path
import subprocess
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from market_regime_alpha.application.controlled_operation import (
    ChildRunReferenceKind,
)
from market_regime_alpha.application.controlled_operation.input_artifacts import (
    load_controlled_runtime_configuration,
)
from market_regime_alpha.application.free_data_operation.contracts import (
    FreeDataInstrument,
    FreeDataOperationScale,
    FreeDataPreparationRequest,
)
from market_regime_alpha.application.free_data_operation.blocked import (
    FreeDataOperationBlocked,
)
from market_regime_alpha.application.free_data_operation.service import (
    FreeDataOperationExecution,
    FreeDataOperationPreparation,
    FreeDataOperationService,
)
from market_regime_alpha.cli.replay_controlled_operation import (
    main as replay_controlled_main,
)
from market_regime_alpha.cli.report_controlled_operation import (
    main as report_controlled_main,
)
from market_regime_alpha.cli.resume_controlled_operation import (
    main as resume_controlled_main,
)
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.providers.public_composite import (
    BaoStockHistoryClient,
    BaoStockSecurityStatusClient,
    TENCENT_FREE_OPERATIONAL_PROFILE_ID,
    TencentCurrentQuoteClient,
    TencentFreeOperationalProfile,
)
from market_regime_alpha.market_data import AssetType
from market_regime_alpha.persistence.repository_factory import (
    RepositoryFactory,
    add_database_arguments,
    settings_from_namespace,
)
from market_regime_alpha.universe.daily_exploratory import SMOKE_POOL_SYMBOLS


_SHANGHAI = ZoneInfo("Asia/Shanghai")


def prepare_main(argv: Sequence[str] | None = None) -> int:
    return _execute(argv, run_decision=False)


def run_main(argv: Sequence[str] | None = None) -> int:
    return _execute(argv, run_decision=True)


def resume_main(argv: Sequence[str] | None = None) -> int:
    return resume_controlled_main(argv)


def replay_main(argv: Sequence[str] | None = None) -> int:
    return replay_controlled_main(argv)


def report_main(argv: Sequence[str] | None = None) -> int:
    return report_controlled_main(argv)


def inspect_main(argv: Sequence[str] | None = None) -> int:
    return report_controlled_main(argv)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--runtime-configuration", type=Path, required=True)
    parser.add_argument("--decision-date", required=True)
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--symbols-file", type=Path)
    parser.add_argument("--minimum-history-sessions", type=int, default=21)
    parser.add_argument("--liquidity-lookback-sessions", type=int, default=21)
    parser.add_argument(
        "--minimum-median-daily-amount",
        type=Decimal,
        default=Decimal("10000000"),
    )
    parser.add_argument("--provider-timeout-seconds", type=float, default=8.0)
    parser.add_argument("--code-revision", default=None)
    add_database_arguments(parser)
    return parser


def _execute(argv: Sequence[str] | None, *, run_decision: bool) -> int:
    args = build_parser().parse_args(argv)
    now = _utc_now()
    decision_date = datetime.strptime(args.decision_date, "%Y-%m-%d").date()
    decision = datetime.combine(
        decision_date,
        time(14, 55),
        tzinfo=_SHANGHAI,
    )
    if now < decision.astimezone(UTC):
        _emit_error("DECISION_TIME_NOT_REACHED", args.output_root)
        return 4
    repositories: RepositoryFactory | None = None
    try:
        symbols = _load_symbols(args.symbols_file)
        configuration = load_controlled_runtime_configuration(
            args.runtime_configuration.resolve()
        )
        request = FreeDataPreparationRequest(
            scale=FreeDataOperationScale.from_symbol_count(len(symbols)),
            provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
            decision_time=DecisionTime(decision),
            created_at=now,
            instruments=tuple(
                FreeDataInstrument(symbol=symbol, asset_type=AssetType.A_SHARE)
                for symbol in symbols
            ),
            membership_source=f"OPERATOR_APPROVED_FREE_DATA_{len(symbols)}",
            minimum_history_sessions=args.minimum_history_sessions,
            liquidity_lookback_sessions=args.liquidity_lookback_sessions,
            minimum_median_daily_amount=args.minimum_median_daily_amount,
            configuration_hash=configuration.configuration_hash,
        )
        repositories = RepositoryFactory(settings_from_namespace(args))
        profile = TencentFreeOperationalProfile(
            history_client=BaoStockHistoryClient(
                provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
            ),
            security_status_client=BaoStockSecurityStatusClient(
                timeout_seconds=args.provider_timeout_seconds,
                provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
            ),
            current_client=TencentCurrentQuoteClient(
                timeout_seconds=args.provider_timeout_seconds,
                provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
            ),
        )
        service = FreeDataOperationService(
            repositories=repositories,
            output_root=args.output_root,
            code_revision=args.code_revision or _git_revision(),
            clock=_utc_now,
            live_profile=profile,
        )
        result = (
            service.run(
                request=request,
                runtime_configuration_path=args.runtime_configuration,
                idempotency_key=args.idempotency_key,
            )
            if run_decision
            else service.prepare(
                request=request,
                runtime_configuration_path=args.runtime_configuration,
                idempotency_key=args.idempotency_key,
            )
        )
        payload = free_data_operation_payload(
            result,
            postgres_metrics=repositories.postgres_factory.runtime_metrics,
        )
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
        if isinstance(result, FreeDataOperationExecution) and result.blocked_reason:
            return 6
        return 0
    except FreeDataOperationBlocked as exc:
        print(
            json.dumps(
                {
                    "runtime_status": "DATA_BLOCKED",
                    "blocked_reason": exc.artifact.reason_code,
                    "blocked_artifact_id": str(exc.artifact.artifact_id),
                    "blocked_artifact": str(exc.path),
                    "source_manifest_id": str(exc.artifact.source_manifest_id),
                    "code_revision": exc.artifact.code_revision,
                    "artifact_root": str(args.output_root.resolve()),
                    **_safety_declarations(),
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 6
    except Exception as exc:
        print(
            json.dumps(
                {
                    "runtime_status": "FAILED_CLOSED",
                    "blocked_reason": f"{type(exc).__name__}:{exc}",
                    "artifact_root": str(args.output_root.resolve()),
                    **_safety_declarations(),
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 11
    finally:
        if repositories is not None:
            repositories.close()


def free_data_operation_payload(
    value: FreeDataOperationPreparation | FreeDataOperationExecution,
    *,
    postgres_metrics: object | None = None,
) -> dict[str, Any]:
    preparation = value.preparation if isinstance(value, FreeDataOperationExecution) else value
    prepared = preparation.prepared_inputs
    references = {item.kind: item for item in prepared.manifest.artifacts}
    decision = value.decision if isinstance(value, FreeDataOperationExecution) else None
    package = (
        value.terminal_package
        if isinstance(value, FreeDataOperationExecution)
        else None
    )
    canonical_run_id = None
    for stage in preparation.controlled_preparation.snapshot.stages:
        if stage.receipt is None:
            continue
        for child in stage.receipt.child_run_references:
            if child.reference_kind is ChildRunReferenceKind.CANONICAL_LIFECYCLE_RUN:
                canonical_run_id = child.child_run_id
    payload: dict[str, Any] = {
        "run_id": str(prepared.manifest.manifest_id),
        "parent_run_id": str(preparation.controlled_command.run_id),
        "canonical_run_id": canonical_run_id,
        "decision_date": preparation.controlled_command.decision_date.isoformat(),
        "decision_time": preparation.controlled_command.decision_time.isoformat(),
        "provider_profile": prepared.manifest.provider_profile_id,
        "source_manifest_id": _artifact_id(references, "FULL_SOURCE_MANIFEST"),
        "market_data_dataset_id": _artifact_id(references, "MARKET_DATA_DATASET"),
        "universe_id": _artifact_id(references, "OPERATIONAL_UNIVERSE"),
        "feature_bundle_id": (
            str(preparation.controlled_preparation.static_bundle.artifact_id)
        ),
        "research_artifact_id": (
            str(decision.research.artifact.artifact_id) if decision else None
        ),
        "candidate_set_id": (
            str(decision.candidate_set.envelope.artifact_id) if decision else None
        ),
        "signal_artifact_id": (
            str(decision.signal.artifact.artifact_id) if decision else None
        ),
        "path_forecast_status": (
            sorted(
                {
                    item.artifact.forecast.forecast_status.value
                    for item in decision.forecasts
                }
            )
            if decision
            else ["NOT_REACHED"]
        ),
        "entry_status": (
            value.entry_status
            if isinstance(value, FreeDataOperationExecution)
            else "NOT_REACHED"
        ),
        "runtime_status": (
            value.engineering_status
            if isinstance(value, FreeDataOperationExecution)
            else preparation.controlled_preparation.snapshot.status.value
        ),
        "blocked_reason": (
            value.blocked_reason
            if isinstance(value, FreeDataOperationExecution)
            else None
        ),
        "database_authority": preparation.database_authority,
        "artifact_root": str(prepared.manifest_path.parents[1]),
        "code_revision": preparation.controlled_command.code_revision,
        "configuration_hash": (
            preparation.controlled_command.configuration_manifest_hash
        ),
        "provider_request_count": len(
            preparation.source.acquired.provider_result.raw_payloads
        ),
        "archive_bytes": sum(
            len(item.raw_payload)
            for item in preparation.source.acquired.provider_result.raw_payloads
        ),
        "universe_count": len(preparation.controlled_preparation.universe.symbols),
        "candidate_count": package.candidate_count if package else 0,
        "signal_state_counts": dict(package.signal_state_counts) if package else {},
        "stage_latencies_ms": (
            {item.stage_name: item.elapsed_ms for item in package.stage_latencies}
            if package
            else {}
        ),
        **_safety_declarations(),
    }
    if postgres_metrics is not None:
        payload["postgres_transaction_attempts"] = getattr(
            postgres_metrics, "transaction_attempts", 0
        )
        payload["postgres_transaction_retries"] = getattr(
            postgres_metrics, "transaction_retries", 0
        )
        payload["postgres_lock_wait_seconds"] = getattr(
            postgres_metrics, "compatibility_lock_wait_seconds", 0.0
        )
    return payload


def _artifact_id(references: dict[str, Any], kind: str) -> str | None:
    reference = references.get(kind)
    return str(reference.artifact_id) if reference is not None else None


def _load_symbols(path: Path | None) -> tuple[str, ...]:
    if path is None:
        return SMOKE_POOL_SYMBOLS
    symbols = tuple(
        sorted(
            {
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            }
        )
    )
    FreeDataOperationScale.from_symbol_count(len(symbols))
    return symbols


def _safety_declarations() -> dict[str, bool]:
    return {
        "FORMAL_PIT_NOT_ESTABLISHED": True,
        "FORMAL_OOS_ALPHA_NOT_ESTABLISHED": True,
        "ENTRY_MODEL_VALIDATED": False,
        "TRADING_AUTHORITY_GRANTED": False,
        "BROKER_NOT_INVOKED": True,
        "NO_ORDER_CREATED": True,
        "NO_FILL_CREATED": True,
        "NO_POSITION_MUTATION": True,
    }


def _emit_error(reason: str, output_root: Path) -> None:
    print(
        json.dumps(
            {
                "runtime_status": "DATA_BLOCKED",
                "blocked_reason": reason,
                "artifact_root": str(output_root.resolve()),
                **_safety_declarations(),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )


def _git_revision() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


__all__ = [
    "free_data_operation_payload",
    "inspect_main",
    "prepare_main",
    "replay_main",
    "report_main",
    "resume_main",
    "run_main",
]
