#!/usr/bin/env python3
"""Append a manual Fill/correction or rebuild Position from the Fill ledger."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from market_regime_alpha.application.trading_lifecycle import (
    ManualExecutionApplicationService,
)
from market_regime_alpha.core.identity import FillId, ManualTradeId
from market_regime_alpha.persistence.repository_factory import (
    RepositoryFactory,
    add_database_arguments,
    settings_from_namespace,
)


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("manual Fill request must be an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Append manual Fill and rebuild Position")
    add_database_arguments(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)
    record = subparsers.add_parser("record")
    record.add_argument("--request", type=Path, required=True)
    position = subparsers.add_parser("position")
    position.add_argument("--account-id", required=True)
    position.add_argument("--symbol", required=True)
    position.add_argument("--as-of", required=True)
    args = parser.parse_args()
    with RepositoryFactory(settings_from_namespace(args)) as repositories:
        service = ManualExecutionApplicationService(
            repositories.manual_execution()
        )
        if args.command == "record":
            request = _object(json.loads(args.request.read_text(encoding="utf-8")))
            correction = request.get("correction_of_fill_id")
            trade, fill = service.record_fill(
                ManualTradeId(str(request["manual_trade_id"])),
                external_fill_id=str(request["external_fill_id"]),
                quantity=int(request["quantity"]),
                price=float(request["price"]),
                fees=float(request["fees"]),
                occurred_at=datetime.fromisoformat(str(request["occurred_at"])),
                recorded_at=datetime.fromisoformat(str(request["recorded_at"])),
                actor=str(request["actor"]),
                reason=str(request["reason"]),
                idempotency_key=str(request["idempotency_key"]),
                correction_of_fill_id=(
                    FillId(str(correction)) if correction is not None else None
                ),
            )
            result = {
                "manual_trade": trade.to_canonical_dict(),
                "fill": fill.to_canonical_dict(),
            }
        else:
            result = service.rebuild_position(
                account_id=args.account_id,
                symbol=args.symbol,
                as_of=datetime.fromisoformat(args.as_of),
            ).to_canonical_dict()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
