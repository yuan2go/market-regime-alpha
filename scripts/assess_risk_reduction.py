#!/usr/bin/env python3
"""Persist one reducing-risk decision without creating an order or trade record."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from market_regime_alpha.portfolio import (
    ReducingExecutionObservation,
    RiskChangeKind,
    RiskReducingDecisionState,
    RiskReducingGateConfiguration,
    RiskRouteApplicationService,
)
from market_regime_alpha.persistence.repository_factory import (
    RepositoryFactory,
    add_database_arguments,
    settings_from_namespace,
)
from market_regime_alpha.position import PositionSnapshot


_REQUEST_FIELDS = {
    "action",
    "position_snapshot",
    "target_quantity",
    "order_quantity",
    "execution_observation",
    "configuration",
    "actor",
    "reason",
    "assessed_at",
    "idempotency_key",
}


def _object(value: object, *, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _read_request(path: Path) -> dict[str, Any]:
    payload = _object(
        json.loads(path.read_text(encoding="utf-8")),
        name="risk reduction request",
    )
    if set(payload) != _REQUEST_FIELDS:
        missing = sorted(_REQUEST_FIELDS - set(payload))
        extra = sorted(set(payload) - _REQUEST_FIELDS)
        raise ValueError(
            f"risk reduction request fields mismatch; missing={missing}, extra={extra}"
        )
    return payload


def _integer(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _string(value: object, *, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _assess(repository: Any, request: dict[str, Any]) -> dict[str, object]:
    position = PositionSnapshot.from_canonical_dict(
        _object(request["position_snapshot"], name="position_snapshot")
    )
    observation = ReducingExecutionObservation.from_canonical_dict(
        _object(request["execution_observation"], name="execution_observation")
    )
    configuration = RiskReducingGateConfiguration.from_canonical_dict(
        _object(request["configuration"], name="configuration")
    )
    decision = RiskRouteApplicationService(
        repository
    ).assess_reducing(
        action=RiskChangeKind(_string(request["action"], name="action")),
        position=position,
        target_quantity=_integer(
            request["target_quantity"], name="target_quantity"
        ),
        order_quantity=_integer(request["order_quantity"], name="order_quantity"),
        execution_observation=observation,
        configuration=configuration,
        actor=_string(request["actor"], name="actor"),
        reason=_string(request["reason"], name="reason"),
        assessed_at=datetime.fromisoformat(
            _string(request["assessed_at"], name="assessed_at")
        ),
        idempotency_key=_string(
            request["idempotency_key"], name="idempotency_key"
        ),
    )
    return {
        "mode": "DECISION_ONLY",
        "decision_id": str(decision.decision_id),
        "decision_content_hash": decision.content_hash,
        "state": decision.state.value,
        "reason_codes": list(decision.reason_codes),
        "position_snapshot_id": str(decision.position_snapshot_id),
        "position_snapshot_hash": decision.position_snapshot_hash,
        "execution_observation_id": str(decision.observation_id),
        "execution_observation_hash": decision.observation_hash,
        "configuration_id": str(decision.configuration_id),
        "configuration_hash": decision.configuration_hash,
        "manual_confirmation_required": decision.state
        is RiskReducingDecisionState.PERMITTED_FOR_MANUAL_CONFIRMATION,
        "order_created": False,
        "execution_boundary": "NO_ORDER_CREATED",
        "trading_authority": "TRADING_AUTHORITY_NOT_GRANTED",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assess and persist one reducing-risk decision only"
    )
    add_database_arguments(parser)
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args(argv)
    with RepositoryFactory(settings_from_namespace(args)) as repositories:
        result = _assess(repositories.risk_route(), _read_request(args.request))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
