"""Read-only inspection commands for the Continuous Runtime state child."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from market_regime_alpha.application.state_system.repository import (
    StateSystemIntegrityError,
    decode_and_verify_pool,
)
from market_regime_alpha.application.state_system.runtime import (
    STATE_RESEARCH_STAGE_ORDER,
)


SUCCESS = 0
ARGUMENT_OR_INTEGRITY_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    subparsers.add_parser("describe")
    verify = subparsers.add_parser("verify-pool")
    verify.add_argument("--artifact", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.operation == "describe":
            output: Mapping[str, Any] = {
                "runtime_owner": "CONTINUOUS_RESEARCH",
                "child_kind": "STATE_SYSTEM",
                "stage_order": [stage.value for stage in STATE_RESEARCH_STAGE_ORDER],
                "entry_authority_granted": False,
                "broker_authority_granted": False,
                "daily_decision_window_summary_delivered": False,
            }
        elif args.operation == "verify-pool":
            artifact = decode_and_verify_pool(
                args.artifact.read_text(encoding="utf-8")
            )
            output = {
                "status": "VERIFIED",
                "pool_id": artifact["pool_id"],
                "pool_hash": artifact["pool_hash"],
                "entry_authority_granted": False,
                "broker_authority_granted": False,
            }
        else:
            raise ValueError("unsupported state-system operation")
        _emit(output)
        return SUCCESS
    except (OSError, ValueError, TypeError, json.JSONDecodeError, StateSystemIntegrityError) as exc:
        _emit(
            {
                "status": "FAILED",
                "reason_code": "STATE_SYSTEM_ARTIFACT_INVALID",
                "error_type": type(exc).__name__,
                "message": "State System inspection failed",
                "entry_authority_granted": False,
                "broker_authority_granted": False,
            }
        )
        return ARGUMENT_OR_INTEGRITY_ERROR


def _emit(payload: Mapping[str, Any]) -> None:
    print(
        json.dumps(
            dict(payload),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
