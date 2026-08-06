#!/usr/bin/env python3
"""Record one human trade intent backed by an approved RiskDecision."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from market_regime_alpha.application.trading_lifecycle import (
    ManualExecutionApplicationService,
)
from market_regime_alpha.persistence.repository_factory import (
    RepositoryFactory,
    add_database_arguments,
    settings_from_namespace,
)
from market_regime_alpha.portfolio.serialization import (
    portfolio_decision_from_dict,
    risk_decision_from_dict,
    target_position_from_dict,
)


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("manual trade request must be an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Record manual trade intent only")
    add_database_arguments(parser)
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    request = _object(json.loads(args.request.read_text(encoding="utf-8")))
    with RepositoryFactory(settings_from_namespace(args)) as repositories:
        service = ManualExecutionApplicationService(
            repositories.manual_execution()
        )
        record = service.create_trade(
            risk_decision=risk_decision_from_dict(_object(request["risk_decision"])),
            portfolio_decision=portfolio_decision_from_dict(
                _object(request["portfolio_decision"])
            ),
            target_position=target_position_from_dict(
                _object(request["target_position"])
            ),
            account_id=str(request["account_id"]),
            expected_price_lower=float(request["expected_price_lower"]),
            expected_price_upper=float(request["expected_price_upper"]),
            actor=str(request["actor"]),
            reason=str(request["reason"]),
            created_at=datetime.fromisoformat(str(request["created_at"])),
            idempotency_key=str(request["idempotency_key"]),
        )
    print(json.dumps(record.to_canonical_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
