"""Create an H4.5 manual SELL record without order, Broker or Fill authority."""

from __future__ import annotations

import argparse
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from math import isfinite
from pathlib import Path
import sys
from typing import Any, NoReturn, Sequence

from market_regime_alpha.application.trading_lifecycle.risk_reduction_confirmation import (
    RiskReductionConfirmationApplicationService,
    RiskReductionConfirmationIdempotencyConflict,
)
from market_regime_alpha.application.trading_lifecycle.sqlite_risk_reduction import (
    SQLiteRiskReductionManualIntentRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.execution.risk_reduction import (
    RiskReductionConfirmationPolicy,
    RiskReductionConfirmationResult,
)
from market_regime_alpha.portfolio.risk_routes import (
    ReducingExecutionObservation,
)
from market_regime_alpha.position.authority import SymbolTradingSessionStatus


EXIT_SUCCESS = 0
EXIT_DOMAIN_REJECTION = 1
EXIT_VALIDATION_ERROR = 2
EXIT_IDEMPOTENCY_CONFLICT = 3


class _CLIValidationError(ValueError):
    pass


class _StructuredArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _CLIValidationError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _StructuredArgumentParser(
        description=(
            "Create an H4.5 manual SELL intent; never create Fill or broker order."
        )
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
    parser.add_argument(
        "--expected-price-lower", type=_positive_decimal, required=True
    )
    parser.add_argument(
        "--expected-price-upper", type=_positive_decimal, required=True
    )
    parser.add_argument("--confirmed-at", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--idempotency-key", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except _CLIValidationError as error:
        _print_rejection(
            error=error,
            reason_code="COMMAND_VALIDATION_FAILED",
            args=None,
            observation=None,
        )
        return EXIT_VALIDATION_ERROR

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
            expected_price_lower=_h4_5_compatible_price_float(
                args.expected_price_lower
            ),
            expected_price_upper=_h4_5_compatible_price_float(
                args.expected_price_upper
            ),
            confirmed_at=datetime.fromisoformat(args.confirmed_at),
            actor=args.actor,
            reason=args.reason,
            idempotency_key=args.idempotency_key,
        )
    except RiskReductionConfirmationIdempotencyConflict as error:
        _print_rejection(
            error=error,
            reason_code="IDEMPOTENCY_KEY_CONFLICT",
            args=args,
            observation=observation,
        )
        return EXIT_IDEMPOTENCY_CONFLICT
    except KeyError as error:
        _print_rejection(
            error=error,
            reason_code="AUTHORITY_REFERENCE_NOT_RESOLVED",
            args=args,
            observation=observation,
        )
        return EXIT_VALIDATION_ERROR
    except (OSError, TypeError, ValueError) as error:
        _print_rejection(
            error=error,
            reason_code="COMMAND_VALIDATION_FAILED",
            args=args,
            observation=observation,
        )
        return EXIT_VALIDATION_ERROR

    print(
        json.dumps(
            _result_payload(result),
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return (
        EXIT_SUCCESS
        if result.manual_trade is not None
        else EXIT_DOMAIN_REJECTION
    )


def _result_payload(
    result: RiskReductionConfirmationResult,
) -> dict[str, Any]:
    attempt = result.attempt
    return {
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
        **_safety_declarations(),
    }


def _print_rejection(
    *,
    error: Exception,
    reason_code: str,
    args: argparse.Namespace | None,
    observation: ReducingExecutionObservation | None,
) -> None:
    print(
        json.dumps(
            {
                "attempt_id": None,
                "state": "DATA_INSUFFICIENT",
                "error": str(error),
                "reason_codes": [reason_code],
                "risk_reducing_decision_id": (
                    getattr(args, "risk_reducing_decision_id", None)
                    if args is not None
                    else None
                ),
                "risk_reducing_decision_hash": (
                    getattr(args, "risk_reducing_decision_hash", None)
                    if args is not None
                    else None
                ),
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
                **_safety_declarations(),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )


def _safety_declarations() -> dict[str, bool]:
    return {
        "MANUAL_CONFIRMATION_REQUIRED": True,
        "NO_ORDER_CREATED": True,
        "BROKER_NOT_INVOKED": True,
        "NO_FILL_CREATED": True,
        "NO_BROKER_ORDER_CREATED": True,
        "TRADING_AUTHORITY_NOT_GRANTED": True,
        "OPERATOR_AUTHENTICATION_NOT_ESTABLISHED": True,
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _positive_decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise argparse.ArgumentTypeError(
            "expected price must be a finite positive decimal"
        ) from error
    if not parsed.is_finite() or parsed <= 0:
        raise argparse.ArgumentTypeError(
            "expected price must be a finite positive decimal"
        )
    return parsed


def _h4_5_compatible_price_float(value: Decimal) -> float:
    """Bridge Decimal CLI input to the merged H4.5 float command contract only."""

    converted = float(value)
    if not isfinite(converted) or converted <= 0.0:
        raise ValueError("expected price is outside the H4.5 compatibility range")
    return converted


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


if __name__ == "__main__":
    sys.exit(main())
