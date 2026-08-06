"""Create or resume a durable deterministic verification run for a source run."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
from typing import NoReturn, Sequence

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleRunId,
)
from market_regime_alpha.application.canonical_lifecycle.durable_replay import (
    run_durable_lifecycle_replay,
)
from market_regime_alpha.application.canonical_lifecycle.repositories import (
    LifecycleIdempotencyConflict,
    LifecycleRepositoryError,
    LifecycleRunNotFound,
)
from market_regime_alpha.application.canonical_lifecycle.replay import (
    LifecycleReplayStatus,
)
from market_regime_alpha.persistence.repository_factory import (
    DatabaseBindingError,
    RepositoryFactory,
    add_database_arguments,
    settings_from_namespace,
)


EXIT_STABLE = 0
EXIT_VALIDATION_ERROR = 2
EXIT_IDEMPOTENCY_CONFLICT = 3
EXIT_SOURCE_NOT_FOUND = 4
EXIT_REPLAY_FAILED = 5
EXIT_REPOSITORY_ERROR = 6


class _CLIValidationError(ValueError):
    pass


class _StructuredArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _CLIValidationError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _StructuredArgumentParser(
        description=(
            "Create or resume a source-bound REPLAY journal, recompute registered "
            "pure Artifacts, and verify read-only domain references. The canonical "
            "Runner and all execution services remain disabled."
        )
    )
    add_database_arguments(parser)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--idempotency-key")
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        repositories = RepositoryFactory(settings_from_namespace(args))
        repository = repositories.lifecycle()
        source_run_id = LifecycleRunId(args.run_id)
        source_history = repository.history(source_run_id)
        repositories.assert_runtime_binding(
            "CANONICAL_LIFECYCLE",
            str(source_run_id),
        )
        clock = _DeterministicReplayClock(
            source_history.run.updated_at + timedelta(seconds=1)
        )
        idempotency_key = (
            args.idempotency_key
            if args.idempotency_key is not None
            else f"canonical-replay:{source_run_id}"
        )
        first = run_durable_lifecycle_replay(
            repository=repository,
            source_run_id=source_run_id,
            idempotency_key=idempotency_key,
            clock=clock,
            output_directory=args.output_dir,
        )
        repositories.bind_runtime(
            "CANONICAL_LIFECYCLE",
            str(first.replay_run.run_id),
        )
        second = run_durable_lifecycle_replay(
            repository=repository,
            source_run_id=source_run_id,
            idempotency_key=idempotency_key,
            clock=clock,
            output_directory=args.output_dir,
        )
        hash_stable = (
            first.replay_run.run_id == second.replay_run.run_id
            and first.report.report_hash == second.report.report_hash
            and first.report.to_canonical_dict()
            == second.report.to_canonical_dict()
        )
        if not hash_stable:
            raise ValueError("durable replay report changed between identical reads")
    except LifecycleIdempotencyConflict as exc:
        return _print_error(
            exit_code=EXIT_IDEMPOTENCY_CONFLICT,
            reason_code="REPLAY_IDEMPOTENCY_CONFLICT",
            exc=exc,
        )
    except LifecycleRunNotFound as exc:
        return _print_error(
            exit_code=EXIT_SOURCE_NOT_FOUND,
            reason_code="REPLAY_SOURCE_NOT_FOUND",
            exc=exc,
        )
    except (LifecycleRepositoryError, DatabaseBindingError) as exc:
        return _print_error(
            exit_code=EXIT_REPOSITORY_ERROR,
            reason_code="REPLAY_REPOSITORY_ERROR",
            exc=exc,
        )
    except (OSError, TypeError, ValueError) as exc:
        return _print_error(
            exit_code=EXIT_VALIDATION_ERROR,
            reason_code="REPLAY_VALIDATION_FAILED",
            exc=exc,
        )

    payload = {
        **first.report.to_canonical_dict(),
        "source_run_id": str(first.source_run_id),
        "replay_run_id": str(first.replay_run.run_id),
        "replay_run_type": first.replay_run.run_type.value,
        "replay_run_status": first.replay_run.status.value,
        "replay_report_path": str(first.report_path),
        "replay_status": first.report.status.value,
        "REPORT_HASH_STABLE": hash_stable,
        **_safety_declarations(),
    }
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
    return (
        EXIT_REPLAY_FAILED
        if first.report.status is LifecycleReplayStatus.FAILED
        else EXIT_STABLE
    )


def _print_error(*, exit_code: int, reason_code: str, exc: Exception) -> int:
    print(
        json.dumps(
            {
                "run_id": None,
                "replay_status": "REJECTED",
                "report_hash": None,
                "REPORT_HASH_STABLE": False,
                "error": str(exc),
                "reason_codes": [reason_code],
                **_safety_declarations(),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return exit_code


class _DeterministicReplayClock:
    def __init__(self, start: datetime) -> None:
        self._current = start

    def __call__(self) -> datetime:
        value = self._current
        self._current += timedelta(seconds=1)
        return value


def _safety_declarations() -> dict[str, bool]:
    return {
        "RUNNER_INVOKED": False,
        "MANUAL_TRADE_CREATED": False,
        "NO_ORDER_CREATED": True,
        "BROKER_NOT_INVOKED": True,
        "NO_FILL_CREATED": True,
        "automatic_order_execution": False,
        "broker_integration_proven": False,
        "entry_model_empirically_validated": False,
        "production_ready": False,
    }


if __name__ == "__main__":
    sys.exit(main())
