"""Read-only deterministic replay verification for an existing lifecycle run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import NoReturn, Sequence

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleRunId,
)
from market_regime_alpha.application.canonical_lifecycle.replay import (
    LifecycleReplayStatus,
    verify_lifecycle_replay,
)
from market_regime_alpha.application.canonical_lifecycle.sqlite_repository import (
    SQLiteLifecycleRunRepository,
)


EXIT_STABLE = 0
EXIT_NOT_COMPARABLE = 1
EXIT_REPLAY_FAILED = 2
EXIT_VALIDATION_ERROR = 3


class _CLIValidationError(ValueError):
    pass


class _StructuredArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _CLIValidationError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _StructuredArgumentParser(
        description=(
            "Verify one existing lifecycle journal and replay only registered pure "
            "Artifacts. The Runner and all execution services remain disabled."
        )
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if not args.database.is_file():
            raise _CLIValidationError(
                "replay requires an existing lifecycle database"
            )
        repository = SQLiteLifecycleRunRepository(args.database)
        run_id = LifecycleRunId(args.run_id)
        first = verify_lifecycle_replay(repository=repository, run_id=run_id)
        second = verify_lifecycle_replay(repository=repository, run_id=run_id)
        hash_stable = (
            first.report_hash == second.report_hash
            and first.to_canonical_dict() == second.to_canonical_dict()
        )
        if not hash_stable:
            raise ValueError("read-only replay report changed between identical reads")
    except (OSError, TypeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "run_id": None,
                    "replay_status": "REJECTED",
                    "report_hash": None,
                    "REPORT_HASH_STABLE": False,
                    "error": str(exc),
                    "reason_codes": ["REPLAY_VALIDATION_FAILED"],
                    **_safety_declarations(),
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return EXIT_VALIDATION_ERROR

    payload = {
        **first.to_canonical_dict(),
        "replay_status": first.status.value,
        "REPORT_HASH_STABLE": hash_stable,
        **_safety_declarations(),
    }
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
    return {
        LifecycleReplayStatus.STABLE: EXIT_STABLE,
        LifecycleReplayStatus.NOT_COMPARABLE: EXIT_NOT_COMPARABLE,
        LifecycleReplayStatus.FAILED: EXIT_REPLAY_FAILED,
    }[first.status]


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
