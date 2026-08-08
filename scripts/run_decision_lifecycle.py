#!/usr/bin/env python3
"""CLI for durable research-backed Opportunity and Thesis commands."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from market_regime_alpha.application.trading_lifecycle import DecisionLifecycleService
from market_regime_alpha.core.identity import OpportunityId, ThesisId
from market_regime_alpha.decision import (
    DecisionEvidenceReference,
    InvalidationCondition,
)
from market_regime_alpha.persistence.repository_factory import (
    RepositoryFactory,
    add_database_arguments,
    settings_from_namespace,
)
from market_regime_alpha.forecasting.contracts import PathForecast
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.signals.contracts import SignalSnapshot


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return _object(value, "request")


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _array(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _service(repository: Any) -> DecisionLifecycleService:
    return DecisionLifecycleService(repository)


def _create(repository: Any, payload: dict[str, Any]):
    return _service(repository).create_opportunity(
        candidate_set=CandidateSet.from_canonical_dict(
            _object(payload["candidate_set"], "candidate_set")
        ),
        signal_snapshot=SignalSnapshot.from_canonical_dict(
            _object(payload["signal_snapshot"], "signal_snapshot")
        ),
        path_forecast=PathForecast.from_canonical_dict(
            _object(payload["path_forecast"], "path_forecast")
        ),
        valid_until=datetime.fromisoformat(str(payload["valid_until"])),
        actor=str(payload["actor"]),
        reason=str(payload["reason"]),
        created_at=datetime.fromisoformat(str(payload["created_at"])),
        idempotency_key=str(payload["idempotency_key"]),
    )


def _confirm(repository: Any, payload: dict[str, Any]):
    return _service(repository).confirm_opportunity(
        OpportunityId(str(payload["opportunity_id"])),
        expected_version=int(payload["expected_version"]),
        supporting_evidence=tuple(
            DecisionEvidenceReference.from_canonical_dict(_object(item, "evidence"))
            for item in _array(payload["supporting_evidence"], "supporting_evidence")
        ),
        invalidation_conditions=tuple(
            InvalidationCondition.from_canonical_dict(_object(item, "condition"))
            for item in _array(
                payload["invalidation_conditions"], "invalidation_conditions"
            )
        ),
        time_invalidation=datetime.fromisoformat(str(payload["time_invalidation"])),
        actor=str(payload["actor"]),
        reason=str(payload["reason"]),
        confirmed_at=datetime.fromisoformat(str(payload["confirmed_at"])),
        idempotency_key=str(payload["idempotency_key"]),
    )


def _transition_opportunity(
    repository: Any, payload: dict[str, Any], *, expire: bool
):
    service = _service(repository)
    common = {
        "expected_version": int(payload["expected_version"]),
        "actor": str(payload["actor"]),
        "reason": str(payload["reason"]),
        "idempotency_key": str(payload["idempotency_key"]),
    }
    opportunity_id = OpportunityId(str(payload["opportunity_id"]))
    if expire:
        return service.expire_opportunity(
            opportunity_id,
            expired_at=datetime.fromisoformat(str(payload["changed_at"])),
            **common,
        )
    return service.reject_opportunity(
        opportunity_id,
        rejected_at=datetime.fromisoformat(str(payload["changed_at"])),
        **common,
    )


def _invalidate_thesis(repository: Any, payload: dict[str, Any]):
    return _service(repository).invalidate_thesis(
        ThesisId(str(payload["thesis_id"])),
        expected_version=int(payload["expected_version"]),
        actor=str(payload["actor"]),
        reason=str(payload["reason"]),
        invalidated_at=datetime.fromisoformat(str(payload["changed_at"])),
        idempotency_key=str(payload["idempotency_key"]),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Production decision lifecycle CLI")
    add_database_arguments(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in (
        "create-opportunity",
        "confirm-opportunity",
        "reject-opportunity",
        "expire-opportunity",
        "invalidate-thesis",
    ):
        child = subparsers.add_parser(command)
        child.add_argument("--request", type=Path, required=True)
    show_opportunity = subparsers.add_parser("show-opportunity")
    show_opportunity.add_argument("--opportunity-id", required=True)
    show_thesis = subparsers.add_parser("show-thesis")
    show_thesis.add_argument("--thesis-id", required=True)
    args = parser.parse_args()
    with RepositoryFactory(settings_from_namespace(args)) as repositories:
        repository = repositories.decision()
        if args.command == "create-opportunity":
            result = _create(repository, _read(args.request)).to_canonical_dict()
        elif args.command == "confirm-opportunity":
            result = _confirm(repository, _read(args.request)).to_canonical_dict()
        elif args.command == "reject-opportunity":
            result = _transition_opportunity(
                repository, _read(args.request), expire=False
            ).to_canonical_dict()
        elif args.command == "expire-opportunity":
            result = _transition_opportunity(
                repository, _read(args.request), expire=True
            ).to_canonical_dict()
        elif args.command == "invalidate-thesis":
            result = _invalidate_thesis(
                repository, _read(args.request)
            ).to_canonical_dict()
        elif args.command == "show-opportunity":
            result = repository.get_opportunity(
                OpportunityId(args.opportunity_id)
            ).to_canonical_dict()
        else:
            result = repository.get_thesis(
                ThesisId(args.thesis_id)
            ).to_canonical_dict()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
