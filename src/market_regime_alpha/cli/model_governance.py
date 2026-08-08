"""PostgreSQL Model Registry, governance and Runtime-selection CLI."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.platform.contracts import (
    EvidenceLevel,
    ModelLifecycleStatus,
)
from market_regime_alpha.platform.durable_governance import PersistentModelRegistry
from market_regime_alpha.platform.governance_serialization import (
    model_definition_from_dict,
)
from market_regime_alpha.platform.runtime_governance import (
    AssignmentLane,
    AssignmentStatus,
    ModelGovernancePolicy,
    ModelQualificationEvidence,
    ModelVersionLineage,
    RuntimePurpose,
)
from market_regime_alpha.persistence.repository_factory import (
    RepositoryFactory,
    add_database_arguments,
    settings_from_namespace,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    add_database_arguments(parser)
    commands = parser.add_subparsers(dest="operation", required=True)
    commands.add_parser("list-models")
    inspect_model = commands.add_parser("inspect-model")
    inspect_model.add_argument("--model-id", required=True)
    inspect_policy = commands.add_parser("inspect-policy")
    inspect_policy.add_argument("--policy-id", required=True)
    inspect_evidence = commands.add_parser("inspect-evidence")
    inspect_evidence.add_argument("--evidence-id", required=True)
    inspect_selection = commands.add_parser("inspect-selection")
    inspect_selection.add_argument("--receipt-id", required=True)
    replay_selection = commands.add_parser("replay-selection")
    replay_selection.add_argument("--receipt-id", required=True)
    assignments = commands.add_parser("inspect-assignments")
    assignments.add_argument("--runtime-scope", required=True)
    assignments.add_argument("--model-slot", required=True)
    assignments.add_argument(
        "--purpose",
        choices=tuple(item.value for item in RuntimePurpose),
        required=True,
    )
    assignments.add_argument("--revision", type=int)
    for name in (
        "register-model",
        "transition-model",
        "record-lineage",
        "record-evidence",
        "record-policy",
        "qualify",
        "assign",
        "transition-assignment",
        "replace-champion",
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
        governance = repositories.model_governance()
        operation = args.operation
        if operation == "list-models":
            result: Any = {
                "governance_revision": governance.current_revision(),
                "models": governance.list_models(),
            }
        elif operation == "inspect-model":
            result = governance.inspect_model(ModelId(args.model_id))
        elif operation == "inspect-policy":
            result = governance.inspect_policy(ArtifactId(args.policy_id))
        elif operation == "inspect-evidence":
            result = governance.inspect_evidence(ArtifactId(args.evidence_id))
        elif operation in {"inspect-selection", "replay-selection"}:
            receipt_id = ArtifactId(args.receipt_id)
            receipt = (
                governance.get_selection_receipt(receipt_id)
                if operation == "inspect-selection"
                else governance.replay_selection(receipt_id)
            )
            result = receipt.to_canonical_dict()
        elif operation == "inspect-assignments":
            result = {
                "governance_revision": governance.current_revision(),
                "assignments": [
                    item.to_canonical_dict()
                    for item in governance.list_assignments(
                        runtime_scope=args.runtime_scope,
                        model_slot=args.model_slot,
                        purpose=RuntimePurpose(args.purpose),
                        revision=args.revision,
                    )
                ],
            }
        else:
            payload = _object(json.loads(args.input.read_text(encoding="utf-8")))
            result = _write(operation, payload, governance)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def _write(operation: str, payload: Mapping[str, Any], governance: Any) -> Any:
    if operation == "register-model":
        result = PersistentModelRegistry(governance).register(
            model_definition_from_dict(_object(payload["definition"])),
            idempotency_key=_text(payload, "idempotency_key"),
        )
        return {
            "registration": governance.inspect_model(
                result.registration.definition.model_id
            ),
        }
    if operation == "transition-model":
        result = PersistentModelRegistry(governance).transition(
            ModelId(_text(payload, "model_id")),
            expected_version=_integer(payload, "expected_version"),
            idempotency_key=_text(payload, "idempotency_key"),
            to_status=ModelLifecycleStatus(_text(payload, "to_status")),
            changed_at=_instant(payload["changed_at"]),
            reason=_text(payload, "reason"),
            evidence_refs=tuple(str(item) for item in payload.get("evidence_refs", [])),
            evidence_level=(
                None
                if payload.get("evidence_level") is None
                else EvidenceLevel(str(payload["evidence_level"]))
            ),
            approval_ref=(
                None
                if payload.get("approval_ref") is None
                else str(payload["approval_ref"])
            ),
        )
        return governance.inspect_model(result.registration.definition.model_id)
    if operation == "record-lineage":
        item = governance.record_version_lineage(
            ModelVersionLineage.from_canonical_dict(_object(payload["lineage"])),
            actor=_text(payload, "actor"),
            reason=_text(payload, "reason"),
            idempotency_key=_text(payload, "idempotency_key"),
        )
    elif operation == "record-evidence":
        item = governance.record_evidence(
            ModelQualificationEvidence.from_canonical_dict(
                _object(payload["evidence"])
            ),
            idempotency_key=_text(payload, "idempotency_key"),
        )
    elif operation == "record-policy":
        item = governance.record_policy(
            ModelGovernancePolicy.from_canonical_dict(_object(payload["policy"])),
            actor=_text(payload, "actor"),
            reason=_text(payload, "reason"),
            created_at=_instant(payload["created_at"]),
            idempotency_key=_text(payload, "idempotency_key"),
        )
    elif operation == "qualify":
        item = governance.qualify(
            model_id=ModelId(_text(payload, "model_id")),
            policy_id=ArtifactId(_text(payload, "policy_id")),
            actor=_text(payload, "actor"),
            reason=_text(payload, "reason"),
            approval_ref=_optional_text(payload.get("approval_ref")),
            decided_at=_instant(payload["decided_at"]),
            expected_registry_version=_integer(
                payload, "expected_registry_version"
            ),
            idempotency_key=_text(payload, "idempotency_key"),
        )
    elif operation == "assign":
        item = governance.assign(
            runtime_scope=_text(payload, "runtime_scope"),
            model_slot=_text(payload, "model_slot"),
            purpose=RuntimePurpose(_text(payload, "purpose")),
            lane=AssignmentLane(_text(payload, "lane")),
            model_id=ModelId(_text(payload, "model_id")),
            policy_id=ArtifactId(_text(payload, "policy_id")),
            expected_governance_revision=_integer(
                payload, "expected_governance_revision"
            ),
            effective_at=_instant(payload["effective_at"]),
            actor=_text(payload, "actor"),
            reason=_text(payload, "reason"),
            approval_ref=_text(payload, "approval_ref"),
            idempotency_key=_text(payload, "idempotency_key"),
        )
    elif operation == "transition-assignment":
        item = governance.transition_assignment(
            ArtifactId(_text(payload, "assignment_id")),
            expected_version=_integer(payload, "expected_version"),
            status=AssignmentStatus(_text(payload, "status")),
            effective_at=_instant(payload["effective_at"]),
            actor=_text(payload, "actor"),
            reason=_text(payload, "reason"),
            approval_ref=_text(payload, "approval_ref"),
            idempotency_key=_text(payload, "idempotency_key"),
        )
    elif operation == "replace-champion":
        item = governance.replace_champion(
            ArtifactId(_text(payload, "current_assignment_id")),
            new_model_id=ModelId(_text(payload, "new_model_id")),
            policy_id=ArtifactId(_text(payload, "policy_id")),
            expected_version=_integer(payload, "expected_version"),
            expected_governance_revision=_integer(
                payload,
                "expected_governance_revision",
            ),
            effective_at=_instant(payload["effective_at"]),
            actor=_text(payload, "actor"),
            reason=_text(payload, "reason"),
            approval_ref=_text(payload, "approval_ref"),
            idempotency_key=_text(payload, "idempotency_key"),
        )
    else:
        raise ValueError(f"unsupported Model Governance operation: {operation}")
    return item.to_canonical_dict()


def _object(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected JSON object")
    return value


def _text(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _integer(payload: Mapping[str, Any], name: str) -> int:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
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
