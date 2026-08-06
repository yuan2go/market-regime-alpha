"""PostgreSQL-only CLI for manual account and research decision support."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any, Mapping, NoReturn, Sequence

from market_regime_alpha.application.continuous_research.journal import (
    ClaimedRuntimeTick,
    RuntimeArtifactReference,
)
from market_regime_alpha.application.continuous_research.ports import (
    ChildExecutionRequest,
)
from market_regime_alpha.application.decision_system.contracts import (
    DecisionLineage,
    DecisionRiskConfiguration,
    FillDerivedPositionReference,
    ManualAccountObservation,
    ManualPositionObservation,
    ReconciliationTolerance,
    SummaryCandidate,
)
from market_regime_alpha.application.decision_system.reconciliation import (
    reconcile_account,
)
from market_regime_alpha.application.decision_system.runtime import (
    DecisionRuntimeInputs,
    DecisionSystemRuntimeService,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionUnavailable,
)
from market_regime_alpha.persistence.repository_factory import (
    RepositoryFactory,
    add_database_arguments,
    settings_from_namespace,
)


SUCCESS = 0
VALIDATION_ERROR = 2
DATABASE_ERROR = 3


class _CLIError(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _CLIError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    add_database_arguments(parser)
    commands = parser.add_subparsers(dest="operation", required=True)
    for name in ("record-manual-account", "import-manual-account"):
        command = commands.add_parser(name)
        command.add_argument("--input", type=Path, required=True)
    inspect_account = commands.add_parser("inspect-manual-account")
    inspect_account.add_argument("--observation-id", required=True)
    reconcile = commands.add_parser("reconcile-account")
    reconcile.add_argument("--input", type=Path, required=True)
    inspect_reconciliation = commands.add_parser("inspect-reconciliation")
    inspect_reconciliation.add_argument("--reconciliation-id", required=True)
    for name in ("preview-daily-decision", "finalize-daily-decision"):
        command = commands.add_parser(name)
        command.add_argument("--input", type=Path, required=True)
    inspect_summary = commands.add_parser("inspect-daily-decision")
    inspect_summary.add_argument("--summary-id", required=True)
    inspect_proposal = commands.add_parser("inspect-portfolio-proposal")
    inspect_proposal.add_argument("--proposal-id", required=True)
    inspect_risk = commands.add_parser("inspect-risk-decision")
    inspect_risk.add_argument("--risk-decision-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if not args.database_url:
            raise _CLIError("explicit --database-url is required")
        with RepositoryFactory(settings_from_namespace(args, dotenv_path=Path("/nonexistent"))) as repositories:
            output = _dispatch(args, repositories)
        _emit({**output, **_authority_ceiling()})
        return SUCCESS
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        _emit_error("DECISION_COMMAND_VALIDATION_FAILED", exc)
        return VALIDATION_ERROR
    except PostgresConnectionUnavailable as exc:
        _emit_error("DATABASE_UNAVAILABLE", exc)
        return DATABASE_ERROR
    except Exception as exc:
        _emit_error("POSTGRESQL_OPERATION_FAILED", exc)
        return DATABASE_ERROR


def _dispatch(args: argparse.Namespace, repositories: RepositoryFactory) -> dict[str, Any]:
    repository = repositories.decision_system()
    operation = args.operation
    if operation == "record-manual-account":
        observation = _manual_observation(_object(_read_json(args.input)))
        return {
            "operation": "RECORD_MANUAL_ACCOUNT",
            "status": "RECORDED",
            "observation": repository.record_manual_observation(observation).to_canonical_dict(),
        }
    if operation == "import-manual-account":
        observation = _manual_observation(_csv_account(args.input))
        return {
            "operation": "IMPORT_MANUAL_ACCOUNT",
            "status": "RECORDED",
            "observation": repository.record_manual_observation(observation).to_canonical_dict(),
        }
    if operation == "inspect-manual-account":
        return {
            "operation": "INSPECT_MANUAL_ACCOUNT",
            "status": "FOUND",
            "observation": repository.get_manual_observation(ArtifactId(args.observation_id)).to_canonical_dict(),
        }
    if operation == "reconcile-account":
        payload = _object(_read_json(args.input))
        account = repository.get_manual_observation(ArtifactId(_text(payload, "manual_observation_id")))
        report = reconcile_account(
            observation=account,
            positions=tuple(_fill_position(_object(item)) for item in _array(payload, "positions")),
            fill_ledger_head=_text(payload, "fill_ledger_head"),
            fill_ledger_complete=_boolean(payload, "fill_ledger_complete"),
            tolerance=_tolerance(_object(payload["tolerance"])),
            authoritative_total_equity=_optional_decimal(payload.get("authoritative_total_equity")),
            authoritative_available_cash=_optional_decimal(payload.get("authoritative_available_cash")),
            authoritative_frozen_cash=_optional_decimal(payload.get("authoritative_frozen_cash")),
            as_of_time=_instant(payload["as_of_time"]),
            revision=_integer(payload, "revision"),
            previous_reconciliation_id=_optional_artifact(payload.get("previous_reconciliation_id")),
            idempotency_key=_text(payload, "idempotency_key"),
            created_at=_instant(payload["created_at"]),
        )
        recorded = repository.save_reconciliation(
            report,
            claim=_claim(_object(payload["claim"])),
        )
        return {
            "operation": "RECONCILE_ACCOUNT",
            "status": recorded.status.value,
            "reconciliation": recorded.to_canonical_dict(),
        }
    if operation == "inspect-reconciliation":
        return {
            "operation": "INSPECT_RECONCILIATION",
            "status": "FOUND",
            "reconciliation": repository.get_reconciliation(ArtifactId(args.reconciliation_id)).to_canonical_dict(),
        }
    if operation in {"preview-daily-decision", "finalize-daily-decision"}:
        payload = _object(_read_json(args.input))
        request = _runtime_request(_object(payload["request"]))
        inputs = _runtime_inputs(
            _object(payload["inputs"]),
            finalize=operation == "finalize-daily-decision",
        )
        receipt = DecisionSystemRuntimeService(repository).execute(
            request=request,
            inputs=inputs,
        )
        return {
            "operation": ("PREVIEW_DAILY_DECISION" if not inputs.finalize else "FINALIZE_DAILY_DECISION"),
            "status": receipt.status,
            "receipt": receipt.to_canonical_dict(),
        }
    if operation == "inspect-daily-decision":
        return {
            "operation": "INSPECT_DAILY_DECISION",
            "status": "FOUND",
            "summary": repository.get_summary(ArtifactId(args.summary_id)).to_canonical_dict(),
        }
    if operation == "inspect-portfolio-proposal":
        return {
            "operation": "INSPECT_PORTFOLIO_PROPOSAL",
            "status": "FOUND",
            "proposal": repository.get_proposal(ArtifactId(args.proposal_id)).to_canonical_dict(),
        }
    if operation == "inspect-risk-decision":
        return {
            "operation": "INSPECT_RISK_DECISION",
            "status": "FOUND",
            "risk_decision": repository.get_risk_decision(ArtifactId(args.risk_decision_id)).to_canonical_dict(),
        }
    raise _CLIError("unsupported Decision System operation")


def _manual_observation(payload: Mapping[str, Any]) -> ManualAccountObservation:
    return ManualAccountObservation.create(
        account_id=_text(payload, "account_id"),
        trading_date=date.fromisoformat(_text(payload, "trading_date")),
        as_of_time=_instant(payload["as_of_time"]),
        total_equity=_decimal(payload["total_equity"]),
        available_cash=_decimal(payload["available_cash"]),
        frozen_cash=_decimal(payload["frozen_cash"]),
        source=_text(payload, "source"),
        actor=_text(payload, "actor"),
        reason=_text(payload, "reason"),
        notes=str(payload.get("notes", "")),
        idempotency_key=_text(payload, "idempotency_key"),
        revision=_integer(payload, "revision"),
        previous_observation_id=_optional_artifact(payload.get("previous_observation_id")),
        positions=tuple(_manual_position(_object(item)) for item in _array(payload, "positions")),
        created_at=_instant(payload["created_at"]),
    )


def _manual_position(payload: Mapping[str, Any]) -> ManualPositionObservation:
    return ManualPositionObservation(
        symbol=_text(payload, "symbol"),
        total_quantity=_integer(payload, "total_quantity"),
        available_quantity=_integer(payload, "available_quantity"),
        frozen_quantity=_integer(payload, "frozen_quantity"),
        average_cost=_optional_decimal(payload.get("average_cost")),
        observed_market_value=_decimal(payload["observed_market_value"]),
        notes=str(payload.get("notes", "")),
    )


def _fill_position(payload: Mapping[str, Any]) -> FillDerivedPositionReference:
    return FillDerivedPositionReference(
        snapshot_id=ArtifactId(_text(payload, "snapshot_id")),
        snapshot_hash=_text(payload, "snapshot_hash"),
        account_id=_text(payload, "account_id"),
        symbol=_text(payload, "symbol"),
        as_of_time=_instant(payload["as_of_time"]),
        total_quantity=_integer(payload, "total_quantity"),
        available_quantity=_optional_integer(payload.get("available_quantity")),
        frozen_quantity=_optional_integer(payload.get("frozen_quantity")),
        average_cost=_optional_decimal(payload.get("average_cost")),
        source_fill_ids=tuple(str(item) for item in _array(payload, "source_fill_ids")),
        complete=_boolean(payload, "complete"),
    )


def _tolerance(payload: Mapping[str, Any]) -> ReconciliationTolerance:
    return ReconciliationTolerance(
        configuration_id=ArtifactId(_text(payload, "configuration_id")),
        configuration_hash=_text(payload, "configuration_hash"),
        equity_tolerance=_decimal(payload["equity_tolerance"]),
        cash_tolerance=_decimal(payload["cash_tolerance"]),
        average_cost_tolerance=_decimal(payload["average_cost_tolerance"]),
    )


def _risk_configuration(payload: Mapping[str, Any]) -> DecisionRiskConfiguration:
    return DecisionRiskConfiguration(
        configuration_id=ArtifactId(_text(payload, "configuration_id")),
        configuration_hash=_text(payload, "configuration_hash"),
        maximum_observation_age_seconds=_integer(payload, "maximum_observation_age_seconds"),
        maximum_data_age_seconds=_integer(payload, "maximum_data_age_seconds"),
        maximum_single_symbol_weight=_decimal(payload["maximum_single_symbol_weight"]),
        maximum_theme_weight=_decimal(payload["maximum_theme_weight"]),
        minimum_liquidity=_decimal(payload["minimum_liquidity"]),
        daily_loss_limit=_optional_decimal(payload.get("daily_loss_limit")),
    )


def _runtime_inputs(payload: Mapping[str, Any], *, finalize: bool) -> DecisionRuntimeInputs:
    return DecisionRuntimeInputs(
        manual_observation_id=ArtifactId(_text(payload, "manual_observation_id")),
        positions=tuple(_fill_position(_object(item)) for item in _array(payload, "positions")),
        fill_ledger_head=_text(payload, "fill_ledger_head"),
        fill_ledger_complete=_boolean(payload, "fill_ledger_complete"),
        authoritative_total_equity=_optional_decimal(payload.get("authoritative_total_equity")),
        authoritative_available_cash=_optional_decimal(payload.get("authoritative_available_cash")),
        authoritative_frozen_cash=_optional_decimal(payload.get("authoritative_frozen_cash")),
        reconciliation_tolerance=_tolerance(_object(payload["reconciliation_tolerance"])),
        reconciliation_revision=_integer(payload, "reconciliation_revision"),
        previous_reconciliation_id=_optional_artifact(payload.get("previous_reconciliation_id")),
        strategy_configuration_id=ArtifactId(_text(payload, "strategy_configuration_id")),
        strategy_configuration_hash=_text(payload, "strategy_configuration_hash"),
        lineage=DecisionLineage.from_canonical_dict(_object(payload["lineage"])),
        candidates=tuple(SummaryCandidate.from_canonical_dict(_object(item)) for item in _array(payload, "candidates")),
        summary_revision=_integer(payload, "summary_revision"),
        previous_summary_id=_optional_artifact(payload.get("previous_summary_id")),
        correction_of_summary_id=_optional_artifact(payload.get("correction_of_summary_id")),
        risk_configuration=_risk_configuration(_object(payload["risk_configuration"])),
        finalize=finalize,
        uses_complete_close_bar=_optional_boolean(payload.get("uses_complete_close_bar"), default=False),
        daily_loss=_optional_decimal(payload.get("daily_loss")),
    )


def _runtime_request(payload: Mapping[str, Any]) -> ChildExecutionRequest:
    return ChildExecutionRequest(
        trading_date=date.fromisoformat(_text(payload, "trading_date")),
        as_of_time=_instant(payload["as_of_time"]),
        run_id=ArtifactId(_text(payload, "run_id")),
        tick_id=ArtifactId(_text(payload, "tick_id")),
        tick_sequence=_integer(payload, "tick_sequence"),
        claim_id=_text(payload, "claim_id"),
        fencing_token=_integer(payload, "fencing_token"),
        tick_version=_integer(payload, "tick_version"),
        lease_expires_at=_instant(payload["lease_expires_at"]),
        provider_attempt_id=_integer(payload, "provider_attempt_id"),
        source_manifest_id=ArtifactId(_text(payload, "source_manifest_id")),
        source_manifest_hash=_text(payload, "source_manifest_hash"),
        evidence_commit_id=ArtifactId(_text(payload, "evidence_commit_id")),
        evidence_commit_hash=_text(payload, "evidence_commit_hash"),
        decision_id=ArtifactId(_text(payload, "decision_id")),
        decision_hash=_text(payload, "decision_hash"),
        input_references=tuple(_reference(_object(item)) for item in _array(payload, "input_references")),
        configuration_references=tuple(_reference(_object(item)) for item in _array(payload, "configuration_references")),
    )


def _reference(payload: Mapping[str, Any]) -> RuntimeArtifactReference:
    return RuntimeArtifactReference.from_canonical_dict(payload)


def _claim(payload: Mapping[str, Any]) -> ClaimedRuntimeTick:
    return ClaimedRuntimeTick(
        run_id=ArtifactId(_text(payload, "run_id")),
        tick_id=ArtifactId(_text(payload, "tick_id")),
        tick_sequence=_integer(payload, "tick_sequence"),
        claim_id=_text(payload, "claim_id"),
        fencing_token=_integer(payload, "fencing_token"),
        tick_version=_integer(payload, "tick_version"),
        lease_acquired_at=_instant(payload["lease_acquired_at"]),
        lease_expires_at=_instant(payload["lease_expires_at"]),
        heartbeat_at=_instant(payload["heartbeat_at"]),
    )


def _csv_account(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise _CLIError("manual account CSV is empty")
    account_fields = (
        "account_id",
        "trading_date",
        "as_of_time",
        "total_equity",
        "available_cash",
        "frozen_cash",
        "source",
        "actor",
        "reason",
        "notes",
        "idempotency_key",
        "revision",
        "previous_observation_id",
        "created_at",
    )
    first = rows[0]
    for row in rows[1:]:
        if any(row.get(field, "") != first.get(field, "") for field in account_fields):
            raise _CLIError("CSV rows contain different account observation headers")
    positions = []
    for row in rows:
        positions.append(
            {
                "symbol": row.get("symbol"),
                "total_quantity": row.get("total_quantity"),
                "available_quantity": row.get("available_quantity"),
                "frozen_quantity": row.get("frozen_quantity"),
                "average_cost": row.get("average_cost") or None,
                "observed_market_value": row.get("observed_market_value"),
                "notes": row.get("position_notes", ""),
            }
        )
    payload = {field: first.get(field) for field in account_fields}
    payload["previous_observation_id"] = payload["previous_observation_id"] or None
    payload["positions"] = positions
    return payload


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _object(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _CLIError("expected JSON object")
    return value


def _array(payload: Mapping[str, Any], name: str) -> tuple[object, ...]:
    value = payload.get(name)
    if not isinstance(value, list):
        raise _CLIError(f"{name} must be a JSON array")
    return tuple(value)


def _text(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise _CLIError(f"{name} must be non-empty text")
    return value


def _integer(payload: Mapping[str, Any], name: str) -> int:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise _CLIError(f"{name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise _CLIError(f"{name} must be an integer") from exc
    return parsed


def _optional_integer(value: object) -> int | None:
    if value is None:
        return None
    return _integer({"value": value}, "value")


def _decimal(value: object) -> Decimal:
    if isinstance(value, float) or isinstance(value, bool):
        raise _CLIError("Decimal values must be encoded as strings or integers")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise _CLIError("invalid Decimal value") from exc
    if not parsed.is_finite():
        raise _CLIError("Decimal value must be finite")
    return parsed


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None or value == "" else _decimal(value)


def _boolean(payload: Mapping[str, Any], name: str) -> bool:
    value = payload.get(name)
    if not isinstance(value, bool):
        raise _CLIError(f"{name} must be a boolean")
    return value


def _optional_boolean(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise _CLIError("optional boolean has invalid type")
    return value


def _optional_artifact(value: object) -> ArtifactId | None:
    return None if value is None or value == "" else ArtifactId(str(value))


def _instant(value: object) -> datetime:
    instant = datetime.fromisoformat(str(value))
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise _CLIError("timestamp must be timezone-aware")
    return instant


def _authority_ceiling() -> dict[str, bool | str]:
    return {
        "authority": "RESEARCH_MANUAL_DECISION_SUPPORT",
        "entry_authority_granted": False,
        "order_created": False,
        "fill_created": False,
        "position_mutated": False,
        "broker_called": False,
    }


def _emit(payload: Mapping[str, Any]) -> None:
    print(json.dumps(dict(payload), ensure_ascii=True, sort_keys=True, separators=(",", ":")))


def _emit_error(reason_code: str, exc: BaseException) -> None:
    _emit(
        {
            "status": "FAILED",
            "reason_code": reason_code,
            "error_type": type(exc).__name__,
            "message": "Decision System command failed closed",
            **_authority_ceiling(),
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
