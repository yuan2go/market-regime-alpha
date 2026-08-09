"""PostgreSQL Formal PIT fact, validation, replay and governance CLI."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.pit_artifact_authority import (
    CanonicalPITArtifactAuthorityResolver,
)
from market_regime_alpha.data.pit_authority import (
    FormalPITValidationRequest,
    PITAsOfQuery,
    PITArtifactKind,
    PITArtifactReference,
    PITFactRevision,
    PITRequiredFact,
    PITSourceQualification,
)
from market_regime_alpha.data.pit_governance import (
    record_formal_pit_qualification_evidence,
)
from market_regime_alpha.persistence.repository_factory import (
    RepositoryFactory,
    add_database_arguments,
    settings_from_namespace,
)
from market_regime_alpha.platform.runtime_governance import ModelVersionLineage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    add_database_arguments(parser)
    for option in (
        "source-manifest",
        "market-data-dataset",
        "trading-calendar",
        "universe",
        "feature-materialization",
        "configuration",
    ):
        parser.add_argument(f"--pit-{option}-root", type=Path)
    parser.add_argument("--pit-feature-artifact-root", type=Path)
    commands = parser.add_subparsers(dest="operation", required=True)
    commands.add_parser("revision")
    for name in (
        "inspect-source-qualification",
        "inspect-fact",
        "inspect-evidence",
        "replay-evidence",
    ):
        command = commands.add_parser(name)
        command.add_argument(
            (
                "--source-qualification-id"
                if name == "inspect-source-qualification"
                else "--fact-id" if name == "inspect-fact" else "--evidence-id"
            ),
            required=True,
        )
    for name in (
        "record-source-qualification",
        "resolve-artifact",
        "record-fact",
        "as-of",
        "validate",
        "consume-governance",
    ):
        command = commands.add_parser(name)
        command.add_argument("--input", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.database_url:
        raise ValueError("explicit --database-url is required")
    with RepositoryFactory(
        settings_from_namespace(args, dotenv_path=Path("/nonexistent"))
    ) as repositories:
        pit = repositories.pit_authority(
            artifact_resolver=_artifact_resolver(args)
        )
        operation = args.operation
        if operation == "revision":
            result: Any = {"authority_revision": pit.current_revision()}
        elif operation == "inspect-source-qualification":
            result = pit.get_source_qualification(
                ArtifactId(args.source_qualification_id)
            ).to_canonical_dict()
        elif operation == "inspect-fact":
            result = pit.get_fact(ArtifactId(args.fact_id)).to_canonical_dict()
        elif operation in {"inspect-evidence", "replay-evidence"}:
            evidence_id = ArtifactId(args.evidence_id)
            evidence = (
                pit.get_evidence(evidence_id)
                if operation == "inspect-evidence"
                else pit.replay_evidence(evidence_id)
            )
            result = evidence.to_canonical_dict()
        else:
            payload = _object(json.loads(args.input.read_text(encoding="utf-8")))
            result = _write(operation, payload, pit, repositories)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def _write(operation: str, payload: Mapping[str, Any], pit: Any, repositories: Any) -> Any:
    if operation == "resolve-artifact":
        resolution = pit.resolve_artifact(
            PITArtifactReference.from_canonical_dict(
                _object(payload["reference"])
            ),
            actor=_text(payload, "actor"),
            reason=_text(payload, "reason"),
            idempotency_key=_text(payload, "idempotency_key"),
        )
        return resolution.to_canonical_dict()
    if operation == "record-source-qualification":
        qualification = pit.record_source_qualification(
            PITSourceQualification.from_canonical_dict(
                _object(payload["qualification"])
            ),
            idempotency_key=_text(payload, "idempotency_key"),
        )
        return qualification.to_canonical_dict()
    if operation == "record-fact":
        recorded = pit.record_fact(
            PITFactRevision.from_canonical_dict(_object(payload["fact"])),
            actor=_text(payload, "actor"),
            reason=_text(payload, "reason"),
            idempotency_key=_text(payload, "idempotency_key"),
        )
        return recorded.to_canonical_dict()
    if operation == "as-of":
        snapshot = pit.as_of(
            PITAsOfQuery.create(
                scope_id=_text(payload, "scope_id"),
                decision_time=_instant(payload["decision_time"]),
                required_facts=tuple(
                    PITRequiredFact.from_canonical_dict(_object(item))
                    for item in _sequence(payload["required_facts"])
                ),
            )
        )
        return snapshot.to_canonical_dict()
    if operation == "validate":
        evidence = pit.validate(
            FormalPITValidationRequest.from_canonical_dict(
                _object(payload["request"])
            )
        )
        return evidence.to_canonical_dict()
    if operation == "consume-governance":
        evidence = record_formal_pit_qualification_evidence(
            pit_authority=pit,
            model_governance=repositories.model_governance(),
            pit_evidence_id=ArtifactId(_text(payload, "pit_evidence_id")),
            model_lineage=ModelVersionLineage.from_canonical_dict(
                _object(payload["model_lineage"])
            ),
            actor=_text(payload, "actor"),
            reason=_text(payload, "reason"),
            idempotency_key=_text(payload, "idempotency_key"),
        )
        return evidence.to_canonical_dict()
    raise ValueError(f"unsupported PIT Authority operation: {operation}")


def _artifact_resolver(args: argparse.Namespace) -> CanonicalPITArtifactAuthorityResolver:
    values = {
        PITArtifactKind.SOURCE_MANIFEST: args.pit_source_manifest_root,
        PITArtifactKind.MARKET_DATA_DATASET: args.pit_market_data_dataset_root,
        PITArtifactKind.TRADING_CALENDAR: args.pit_trading_calendar_root,
        PITArtifactKind.UNIVERSE: args.pit_universe_root,
        PITArtifactKind.FEATURE_MATERIALIZATION: args.pit_feature_materialization_root,
        PITArtifactKind.CONFIGURATION: args.pit_configuration_root,
    }
    return CanonicalPITArtifactAuthorityResolver(
        artifact_roots={kind: path for kind, path in values.items() if path is not None},
        feature_artifact_root=args.pit_feature_artifact_root,
    )


def _object(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected JSON object")
    return value


def _sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("expected JSON array")
    return tuple(value)


def _text(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _instant(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be ISO-8601 text")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
