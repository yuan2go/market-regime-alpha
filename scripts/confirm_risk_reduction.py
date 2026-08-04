#!/usr/bin/env python3
"""Confirm one verified H4 reducing decision into a manual SELL intent only."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from market_regime_alpha.application.trading_lifecycle import (
    RiskReductionConfirmationApplicationService,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.execution.risk_reduction import (
    RiskReductionConfirmationPolicy,
)
from market_regime_alpha.application.trading_lifecycle.sqlite_risk_reduction import (
    SQLiteRiskReductionManualIntentRepository,
)
from market_regime_alpha.portfolio.risk_routes import (
    ReducingExecutionObservation,
)
from market_regime_alpha.position.authority import SymbolTradingSessionStatus


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create an H4.5 manual SELL intent; never create Fill or broker order."
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--risk-reducing-decision-id", required=True)
    parser.add_argument("--risk-reducing-decision-hash", required=True)
    parser.add_argument("--exit-directive-id", required=True)
    parser.add_argument("--exit-directive-hash", required=True)
    parser.add_argument("--thesis-health-observation-id", required=True)
    parser.add_argument("--thesis-health-observation-hash", required=True)
    parser.add_argument("--composite-manifest-id", required=True)
    parser.add_argument("--composite-manifest-hash", required=True)
    parser.add_argument("--trading-calendar", type=Path, required=True)
    parser.add_argument("--symbol-trading-status", type=Path, required=True)
    parser.add_argument("--execution-observation", type=Path, required=True)
    parser.add_argument("--confirmation-policy", type=Path, required=True)
    parser.add_argument("--expected-price-lower", type=float, required=True)
    parser.add_argument("--expected-price-upper", type=float, required=True)
    parser.add_argument("--confirmed-at", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--idempotency-key", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    observation: ReducingExecutionObservation | None = None
    try:
        calendar = TradingCalendarArtifact.from_canonical_dict(
            _object(_read_json(args.trading_calendar), "trading calendar")
        )
        statuses_payload = _read_json(args.symbol_trading_status)
        if isinstance(statuses_payload, dict):
            statuses_payload = statuses_payload.get("items")
        if not isinstance(statuses_payload, list):
            raise ValueError("symbol trading status file must contain an array")
        statuses = tuple(
            SymbolTradingSessionStatus.from_canonical_dict(
                _object(item, "symbol trading status")
            )
            for item in statuses_payload
        )
        observation = ReducingExecutionObservation.from_canonical_dict(
            _object(
                _read_json(args.execution_observation),
                "execution observation",
            )
        )
        policy = RiskReductionConfirmationPolicy.from_canonical_dict(
            _object(_read_json(args.confirmation_policy), "confirmation policy")
        )
        result = RiskReductionConfirmationApplicationService(
            SQLiteRiskReductionManualIntentRepository(args.database)
        ).confirm(
            risk_reducing_decision_id=ArtifactId(
                args.risk_reducing_decision_id
            ),
            risk_reducing_decision_hash=args.risk_reducing_decision_hash,
            exit_directive_id=ArtifactId(args.exit_directive_id),
            exit_directive_hash=args.exit_directive_hash,
            thesis_health_observation_id=ArtifactId(
                args.thesis_health_observation_id
            ),
            thesis_health_observation_hash=(
                args.thesis_health_observation_hash
            ),
            composite_manifest_id=ArtifactId(args.composite_manifest_id),
            composite_manifest_hash=args.composite_manifest_hash,
            trading_calendar=calendar,
            symbol_trading_statuses=statuses,
            execution_observation=observation,
            confirmation_policy=policy,
            expected_price_lower=args.expected_price_lower,
            expected_price_upper=args.expected_price_upper,
            confirmed_at=datetime.fromisoformat(args.confirmed_at),
            actor=args.actor,
            reason=args.reason,
            idempotency_key=args.idempotency_key,
        )
    except (KeyError, TypeError, ValueError) as error:
        print(
            json.dumps(
                {
                    "attempt_id": None,
                    "state": "DATA_INSUFFICIENT",
                    "error": str(error),
                    "reason_codes": ["AUTHORITY_REFERENCE_NOT_RESOLVED"],
                    "risk_reducing_decision_id": args.risk_reducing_decision_id,
                    "risk_reducing_decision_hash": args.risk_reducing_decision_hash,
                    "source_position_snapshot_id": None,
                    "source_position_snapshot_hash": None,
                    "current_position_snapshot_id": None,
                    "current_position_snapshot_hash": None,
                    "recheck_observation_id": (
                        str(observation.observation_id)
                        if observation is not None
                        else None
                    ),
                    "recheck_observation_hash": (
                        observation.content_hash
                        if observation is not None
                        else None
                    ),
                    "manual_trade_id": None,
                    "MANUAL_INTENT_CREATED": False,
                    "NO_FILL_CREATED": True,
                    "NO_BROKER_ORDER_CREATED": True,
                    "TRADING_AUTHORITY_NOT_GRANTED": True,
                    "OPERATOR_AUTHENTICATION_NOT_ESTABLISHED": True,
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 2

    attempt = result.attempt
    payload = {
        "attempt_id": str(attempt.attempt_id),
        "attempt_hash": attempt.content_hash,
        "state": attempt.state.value,
        "outcome": result.outcome,
        "reason_codes": list(attempt.reason_codes),
        "risk_reducing_decision_id": str(
            attempt.risk_reducing_decision_id
        ),
        "risk_reducing_decision_hash": attempt.risk_reducing_decision_hash,
        "source_position_snapshot_id": str(
            attempt.source_position_snapshot_id
        ),
        "source_position_snapshot_hash": (
            attempt.source_position_snapshot_hash
        ),
        "current_position_snapshot_id": str(
            attempt.current_position_snapshot_id
        ),
        "current_position_snapshot_hash": (
            attempt.current_position_snapshot_hash
        ),
        "recheck_observation_id": str(attempt.recheck_observation_id),
        "recheck_observation_hash": attempt.recheck_observation_hash,
        "manual_trade_id": (
            str(result.manual_trade.manual_trade_id)
            if result.manual_trade is not None
            else None
        ),
        "MANUAL_INTENT_CREATED": result.manual_trade is not None,
        "NO_FILL_CREATED": True,
        "NO_BROKER_ORDER_CREATED": True,
        "TRADING_AUTHORITY_NOT_GRANTED": True,
        "OPERATOR_AUTHENTICATION_NOT_ESTABLISHED": True,
    }
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
    return 0 if result.manual_trade is not None else 1


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


if __name__ == "__main__":
    sys.exit(main())
