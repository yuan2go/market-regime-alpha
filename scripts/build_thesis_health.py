#!/usr/bin/env python3
"""Build and persist one artifact-derived ThesisHealthObservationV2 only."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
from typing import Any

from market_regime_alpha.application.trading_lifecycle import (
    ThesisHealthApplicationService,
)
from market_regime_alpha.position import ThesisHealthInputBundle
from market_regime_alpha.position.sqlite_thesis_health import (
    SQLiteThesisHealthRepository,
)


_REQUEST_FIELDS = {"input_bundle", "idempotency_key"}


def _object(value: object, *, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _read_request(path: Path) -> dict[str, Any]:
    payload = _object(
        json.loads(path.read_text(encoding="utf-8")),
        name="Thesis health request",
    )
    if set(payload) != _REQUEST_FIELDS:
        missing = sorted(_REQUEST_FIELDS - set(payload))
        extra = sorted(set(payload) - _REQUEST_FIELDS)
        raise ValueError(
            f"Thesis health request fields mismatch; missing={missing}, extra={extra}"
        )
    return payload


def _string(value: object, *, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _assess(database: Path, request: dict[str, Any]) -> dict[str, object]:
    bundle = ThesisHealthInputBundle.from_canonical_dict(
        _object(request["input_bundle"], name="input_bundle")
    )
    observation = ThesisHealthApplicationService(
        SQLiteThesisHealthRepository(database)
    ).assess(
        input_bundle=bundle,
        idempotency_key=_string(
            request["idempotency_key"], name="idempotency_key"
        ),
    )
    source_artifacts = {
        "price_snapshot": {
            "artifact_id": str(observation.price_snapshot_id),
            "content_hash": observation.price_snapshot_hash,
        },
        "market_regime": {
            "artifact_id": str(observation.market_regime_id),
            "content_hash": observation.market_regime_hash,
        },
        "candidate_set": {
            "artifact_id": str(observation.candidate_set_id),
            "content_hash": observation.candidate_set_hash,
        },
        "signal_snapshot": {
            "artifact_id": str(observation.signal_snapshot_id),
            "content_hash": observation.signal_snapshot_hash,
        },
        "path_forecast": {
            "artifact_id": str(observation.path_forecast_id),
            "content_hash": observation.path_forecast_hash,
        },
        "theme_rotation": {
            "artifact_id": str(observation.theme_rotation_id),
            "content_hash": observation.theme_rotation_hash,
        },
        "capital_evolution": {
            "artifact_id": str(observation.capital_evolution_id),
            "content_hash": observation.capital_evolution_hash,
        },
    }
    return {
        "mode": "OBSERVATION_ONLY",
        "schema_version": observation.schema_version,
        "observation_id": str(observation.observation_id),
        "content_hash": observation.content_hash,
        "thesis_id": str(observation.thesis_id),
        "thesis_version": observation.thesis_version,
        "observed_health_state": observation.observed_health_state.value,
        "effective_health_state": (
            observation.effective_health_state.value
            if observation.effective_health_state is not None
            else "NOT_ESTABLISHED"
        ),
        "component_states": {
            "market": observation.market_support_state.value,
            "signal": observation.signal_support_state.value,
            "path": observation.path_support_state.value,
            "theme": observation.theme_support_state.value,
            "capital": observation.capital_support_state.value,
        },
        "triggered_condition_ids": list(observation.triggered_condition_ids),
        "missing_reason_codes": list(observation.missing_reason_codes),
        "reason_codes": list(observation.reason_codes),
        "source_artifacts": source_artifacts,
        "configuration": {
            "configuration_id": str(observation.configuration_id),
            "configuration_hash": observation.configuration_hash,
        },
        "rule_set": {
            "rule_set_id": str(observation.rule_set_id),
            "rule_set_hash": observation.rule_set_hash,
        },
        "execution_boundary": "NO_TRADE_ACTION_CREATED",
        "trading_authority": "TRADING_AUTHORITY_NOT_GRANTED",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build and persist one Thesis Health V2 Observation only"
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args(argv)
    result = _assess(args.database, _read_request(args.request))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
