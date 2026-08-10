"""Operate the PostgreSQL-backed Research Shadow lifecycle without SQL."""

from __future__ import annotations

import argparse
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.controlled_operation.outcome_evidence import (
    load_trade_horizon_outcome_evidence,
)
from market_regime_alpha.application.controlled_operation.outcome_source_archive import (
    load_outcome_settlement_source_archive,
)
from market_regime_alpha.application.controlled_operation.prospective_outcome import (
    SettlementSessionStatus,
)
from market_regime_alpha.application.research_evaluation.targets import (
    engineering_multi_horizon_protocol,
)
from market_regime_alpha.application.research_validation.factor_extraction import (
    CanonicalStateFactorSource,
    FactorFamily,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.shadow_research.attestation import (
    ClockMode,
    RuntimeOrigin,
)
from market_regime_alpha.application.shadow_research.contracts import (
    ShadowSessionCommand,
)
from market_regime_alpha.application.shadow_research.operations import (
    ResearchShadowOperations,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.features.materialization_v2 import (
    load_verified_feature_bundle_v2,
)
from market_regime_alpha.forecasting.contracts import PathForecast
from market_regime_alpha.market_data.artifacts import load_verified_market_data_dataset
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.persistence.settings import DatabaseSettings
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.research.state_system.pool import DynamicStockPoolVersion
from market_regime_alpha.signals.v3 import load_verified_signal_run_v3


SUCCESS = 0
ARGUMENT_ERROR = 2
DATABASE_ERROR = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--application-schema", default="market_regime_alpha")
    commands = parser.add_subparsers(dest="operation", required=True)

    schedule = commands.add_parser("schedule")
    schedule.add_argument("--run-id", required=True)
    schedule.add_argument("--trading-date", required=True)
    schedule.add_argument("--scheduled-at", required=True)
    schedule.add_argument("--idempotency-key", required=True)
    schedule.add_argument("--operator-observation")

    for name in ("run", "outcome-pending", "resume"):
        command = commands.add_parser(name)
        command.add_argument("--session-id", required=True)
        command.add_argument("--expected-version", type=int, required=True)

    for name in ("freeze", "attach-summary"):
        command = commands.add_parser(name)
        command.add_argument("--session-id", required=True)
        command.add_argument("--summary-id", required=True)
        command.add_argument("--frozen-at", required=True)
        command.add_argument("--expected-version", type=int, required=True)

    settle = commands.add_parser("settle")
    settle.add_argument("--decision-id", required=True)
    settle.add_argument("--source-archive", type=Path, required=True)
    settle.add_argument("--settlement-dataset", type=Path, required=True)
    settle.add_argument("--factual-evidence", type=Path, required=True)
    settle.add_argument("--next-session-date", required=True)
    settle.add_argument(
        "--session-status",
        choices=[item.value for item in SettlementSessionStatus],
        required=True,
    )

    evaluations = {
        name: commands.add_parser(name)
        for name in ("build-evaluation", "build-enriched-evaluation")
    }
    for evaluation in evaluations.values():
        evaluation.add_argument("--decision-id", required=True)
        evaluation.add_argument("--targeted-outcome-id", required=True)
        evaluation.add_argument("--target-protocol-id", required=True)
        evaluation.add_argument("--dynamic-pool", type=Path, required=True)
        evaluation.add_argument("--candidate-set", type=Path, required=True)
        evaluation.add_argument("--state-policy-references", type=Path, required=True)
        evaluation.add_argument("--artifact-root", type=Path, required=True)
        evaluation.add_argument("--created-at", required=True)
    enriched = evaluations["build-enriched-evaluation"]
    enriched.add_argument("--dataset", type=Path, required=True)
    enriched.add_argument("--feature-bundle", type=Path, required=True)
    enriched.add_argument("--feature-artifact-root", type=Path, required=True)
    enriched.add_argument("--signal-run", type=Path)
    enriched.add_argument("--forecasts", type=Path, required=True)
    enriched.add_argument("--state-sources", type=Path, required=True)
    settle.add_argument("--expected-version", type=int, required=True)
    settle.add_argument("--created-at", required=True)
    settle.add_argument("--code-revision", required=True)
    settle.add_argument("--clock-mode", choices=[item.value for item in ClockMode], required=True)
    settle.add_argument(
        "--runtime-origin",
        choices=[item.value for item in RuntimeOrigin],
        required=True,
    )

    invalidate = commands.add_parser("invalidate")
    invalidate.add_argument("--session-id", required=True)
    invalidate.add_argument("--expected-version", type=int, required=True)
    invalidate.add_argument("--reason-code", action="append", required=True)

    report = commands.add_parser("report")
    report.add_argument("--session-id", required=True)
    replay = commands.add_parser("replay")
    replay.add_argument("--decision-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    factory: PostgresConnectionFactory | None = None
    try:
        args = build_parser().parse_args(argv)
        settings = DatabaseSettings.from_sources(database_url=args.database_url, environ={})
        factory = PostgresConnectionFactory(settings, application_schema=args.application_schema)
        operations = ResearchShadowOperations(factory)
        output = _dispatch(args, operations)
        _emit(output)
        return SUCCESS
    except (ValueError, TypeError, KeyError, OSError, json.JSONDecodeError) as exc:
        _emit_error("ARGUMENT_OR_IDENTITY_INVALID", exc)
        return ARGUMENT_ERROR
    except Exception as exc:
        _emit_error("POSTGRESQL_OPERATION_FAILED", exc)
        return DATABASE_ERROR
    finally:
        if factory is not None:
            factory.close()


def _dispatch(args: argparse.Namespace, operations: ResearchShadowOperations) -> Mapping[str, Any]:
    if args.operation == "schedule":
        snapshot = operations.schedule(
            ShadowSessionCommand.create(
                idempotency_key=args.idempotency_key,
                run_id=ArtifactId(args.run_id),
                trading_date=date.fromisoformat(args.trading_date),
                runtime_mode=RuntimeAuthorityMode.SHADOW,
                scheduled_at=_instant(args.scheduled_at),
                operator_observation=args.operator_observation,
            )
        )
        return {"operation": "SCHEDULE", **_snapshot(snapshot)}
    if args.operation == "run":
        return {
            "operation": "RUN_ATTACH",
            **_snapshot(operations.run_or_attach(ArtifactId(args.session_id), expected_version=args.expected_version)),
        }
    if args.operation in {"freeze", "attach-summary"}:
        decision = operations.freeze(
            ArtifactId(args.session_id),
            summary_id=ArtifactId(args.summary_id),
            decision_frozen_at=_instant(args.frozen_at),
            expected_version=args.expected_version,
        )
        return {"operation": "FREEZE", **decision.to_canonical_dict()}
    if args.operation == "outcome-pending":
        return {
            "operation": "OUTCOME_PENDING",
            **_snapshot(operations.outcome_pending(ArtifactId(args.session_id), expected_version=args.expected_version)),
        }
    if args.operation == "settle":
        result = operations.settle(
            decision_id=ArtifactId(args.decision_id),
            source_archive=load_outcome_settlement_source_archive(args.source_archive),
            settlement_dataset=load_verified_market_data_dataset(args.settlement_dataset),
            factual_evidence=load_trade_horizon_outcome_evidence(args.factual_evidence),
            next_session_date=date.fromisoformat(args.next_session_date),
            session_status=SettlementSessionStatus(args.session_status),
            target_protocol=engineering_multi_horizon_protocol(),
            expected_shadow_version=args.expected_version,
            created_at=_instant(args.created_at),
            code_revision=args.code_revision,
            clock_mode=ClockMode(args.clock_mode),
            runtime_origin=RuntimeOrigin(args.runtime_origin),
        )
        return {
            "operation": "SETTLE",
            "session": _snapshot(result.session),
            "factual_outcome_v1": result.factual_outcome_v1.to_canonical_dict(),
            "targeted_outcome_v2": result.targeted_outcome_v2.to_canonical_dict(),
            "attestation": result.attestation.to_canonical_dict(),
        }
    if args.operation in {"build-evaluation", "build-enriched-evaluation"}:
        pool_payload = _json_object(args.dynamic_pool)
        candidate_payload = _json_object(args.candidate_set)
        references = _runtime_references(args.state_policy_references)
        common = {
            "decision_id": ArtifactId(args.decision_id),
            "targeted_outcome_id": ArtifactId(args.targeted_outcome_id),
            "target_protocol_id": ArtifactId(args.target_protocol_id),
            "dynamic_pool": DynamicStockPoolVersion.from_canonical_dict(pool_payload),
            "candidate_set": CandidateSet.from_canonical_dict(candidate_payload),
            "state_policy_references": references,
            "artifact_root": args.artifact_root,
            "created_at": _instant(args.created_at),
        }
        if args.operation == "build-enriched-evaluation":
            forecasts = _forecasts(args.forecasts)
            state_sources = _state_sources(args.state_sources)
            signal = None if args.signal_run is None else load_verified_signal_run_v3(args.signal_run).artifact
            panel, enrichment, panel_path, enrichment_path = operations.build_enriched_evaluation(
                **common,
                dataset=load_verified_market_data_dataset(args.dataset),
                feature_bundle=load_verified_feature_bundle_v2(
                    args.feature_bundle,
                    artifact_root=args.feature_artifact_root,
                ),
                signal_run=signal,
                forecasts=forecasts,
                state_sources=state_sources,
            )
            return {
                "operation": "BUILD_ENRICHED_EVALUATION",
                "panel_id": str(panel.panel_id),
                "panel_hash": panel.panel_hash,
                "row_count": panel.row_count,
                "enrichment_id": str(enrichment.enrichment_id),
                "enrichment_hash": enrichment.enrichment_hash,
                "exposure_count": len(enrichment.exposures),
                "panel_artifact_path": str(panel_path),
                "enrichment_artifact_path": str(enrichment_path),
                **_authority(),
            }
        panel, path = operations.build_evaluation(
            **common,
        )
        return {
            "operation": "BUILD_EVALUATION",
            "panel_id": str(panel.panel_id),
            "panel_hash": panel.panel_hash,
            "row_count": panel.row_count,
            "artifact_path": str(path),
            **_authority(),
        }
    if args.operation == "resume":
        return {
            "operation": "RESUME",
            **_snapshot(operations.resume(ArtifactId(args.session_id), expected_version=args.expected_version)),
        }
    if args.operation == "invalidate":
        return {
            "operation": "INVALIDATE",
            **_snapshot(
                operations.invalidate(
                    ArtifactId(args.session_id),
                    expected_version=args.expected_version,
                    reason_codes=tuple(sorted(set(args.reason_code))),
                )
            ),
        }
    if args.operation == "report":
        return operations.report(ArtifactId(args.session_id))
    if args.operation == "replay":
        return {
            "operation": "REPLAY",
            "decision": operations.replay(ArtifactId(args.decision_id)).to_canonical_dict(),
            **_authority(),
        }
    raise ValueError("unsupported Research Shadow operation")


def _snapshot(value: Any) -> dict[str, Any]:
    return {
        "session_id": str(value.command.session_id),
        "run_id": str(value.command.run_id),
        "trading_date": value.command.trading_date.isoformat(),
        "status": value.status.value,
        "outcome_status": value.outcome_status.value,
        "decision_id": None if value.decision_id is None else str(value.decision_id),
        "version": value.version,
        "reason_codes": list(value.reason_codes),
        **_authority(),
    }


def _authority() -> dict[str, bool]:
    return {
        "prospective_proven": False,
        "alpha_proven": False,
        "order_authority": False,
        "broker_authority": False,
        "position_mutation": False,
    }


def _instant(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return result


def _json_value(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_object(path: Path) -> dict[str, Any]:
    value = _json_value(path)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _runtime_references(path: Path) -> tuple[RuntimeArtifactReference, ...]:
    values = _json_value(path)
    if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
        raise ValueError("State Policy references must be an array of objects")
    return tuple(
        RuntimeArtifactReference(
            reference_kind=str(item["reference_kind"]),
            artifact_id=ArtifactId(str(item["artifact_id"])),
            content_hash=str(item["content_hash"]),
        )
        for item in values
    )


def _forecasts(path: Path) -> tuple[PathForecast, ...]:
    values = _json_value(path)
    if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
        raise ValueError("Forecasts must be an array of canonical Path Forecast objects")
    return tuple(PathForecast.from_canonical_dict(item) for item in values)


def _state_sources(path: Path) -> tuple[CanonicalStateFactorSource, ...]:
    values = _json_value(path)
    if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
        raise ValueError("State sources must be an array of canonical source objects")
    result: list[CanonicalStateFactorSource] = []
    for item in values:
        reference = item.get("reference")
        source_values = item.get("values")
        missingness = item.get("missingness", [])
        if not isinstance(reference, dict) or not isinstance(source_values, dict):
            raise ValueError("State source reference and values must be objects")
        if not isinstance(missingness, list):
            raise ValueError("State source missingness must be an array")
        available = item.get("available_at")
        result.append(
            CanonicalStateFactorSource(
                family=FactorFamily(str(item["family"])),
                reference=ValidationArtifactReference.from_canonical_dict(reference),
                values={str(name): _state_value(value) for name, value in source_values.items()},
                symbol=None if item.get("symbol") is None else str(item["symbol"]),
                available_at=None if available is None else _instant(str(available)),
                gate_result=None if item.get("gate_result") is None else str(item["gate_result"]),
                missingness=tuple(sorted({str(value) for value in missingness})),
            )
        )
    return tuple(result)


def _state_value(value: object) -> Decimal | int | str | bool | None:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    raise ValueError("State source values must be scalar JSON values")


def _emit(payload: Mapping[str, Any]) -> None:
    print(json.dumps(dict(payload), ensure_ascii=True, sort_keys=True, separators=(",", ":")))


def _emit_error(reason: str, error: Exception) -> None:
    _emit(
        {
            "status": "FAILED",
            "reason_code": reason,
            "error_type": type(error).__name__,
            "message": str(error),
            **_authority(),
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
