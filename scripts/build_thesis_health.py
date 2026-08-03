#!/usr/bin/env python3
"""Build and persist one artifact-derived ThesisHealthObservationV2 only."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from market_regime_alpha.application.trading_lifecycle import (
    ThesisHealthApplicationService,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.daily_decision import DecisionPriceSnapshot
from market_regime_alpha.decision import TradingOpportunity, TradingThesis
from market_regime_alpha.forecasting import PathForecast
from market_regime_alpha.forecasting.artifact import (
    load_verified_path_forecast,
)
from market_regime_alpha.position import (
    ManualInvalidationEvidence,
    ThesisHealthRuleConfiguration,
    ThesisInvalidationRuleSet,
)
from market_regime_alpha.position.sqlite_thesis_health import (
    SQLiteThesisHealthRepository,
)
from market_regime_alpha.research.platform_v2.reader import (
    load_verified_research_layer_artifact,
)
from market_regime_alpha.research.candidate_discovery import CandidateSet
from market_regime_alpha.research.capital_evolution import CapitalEvolutionSnapshot
from market_regime_alpha.research.market_regime import MarketRegimeSnapshot
from market_regime_alpha.research.theme_rotation import ThemeRotationSnapshot
from market_regime_alpha.signals import SignalSnapshot
from market_regime_alpha.signals.artifact import load_verified_signal_run


_REQUEST_FIELDS = {
    "thesis_path",
    "opportunity_path",
    "research_package_path",
    "signal_package_path",
    "path_forecast_package_path",
    "price_snapshot_path",
    "configuration_path",
    "rule_set_path",
    "manual_evidence_paths",
    "prior_observation_id",
    "prior_observation_hash",
    "assessed_at",
    "actor",
    "reason",
    "idempotency_key",
}


@dataclass(frozen=True, slots=True)
class _LoadedInputs:
    thesis: TradingThesis
    opportunity: TradingOpportunity
    market_regime: MarketRegimeSnapshot
    theme_rotation: ThemeRotationSnapshot
    capital_evolution: CapitalEvolutionSnapshot
    candidate_set: CandidateSet
    signal_snapshot: SignalSnapshot
    path_forecast: PathForecast
    price_snapshot: DecisionPriceSnapshot
    configuration: ThesisHealthRuleConfiguration
    rule_set: ThesisInvalidationRuleSet
    manual_evidence: tuple[ManualInvalidationEvidence, ...]
    expected_prior_observation_id: ArtifactId | None
    expected_prior_observation_hash: str | None
    assessed_at: datetime
    actor: str
    reason: str


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


def _optional_string(value: object, *, name: str) -> str | None:
    if value is None:
        return None
    return _string(value, name=name)


def _document(path: Path, *, name: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid {name} document: {path}") from exc
    return _object(value, name=name)


def _request_path(
    request: dict[str, Any],
    field: str,
    *,
    base: Path,
) -> Path:
    value = Path(_string(request[field], name=field))
    return value if value.is_absolute() else base / value


def _manual_paths(value: object, *, base: Path) -> tuple[Path, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("manual_evidence_paths must be an array of strings")
    paths = tuple(Path(item) if Path(item).is_absolute() else base / item for item in value)
    if paths != tuple(sorted(paths, key=str)) or len(paths) != len(set(paths)):
        raise ValueError("manual_evidence_paths must be sorted and unique")
    return paths


def _load_inputs(
    request: dict[str, Any],
    *,
    base: Path,
) -> _LoadedInputs:
    thesis = TradingThesis.from_canonical_dict(
        _document(_request_path(request, "thesis_path", base=base), name="Thesis")
    )
    opportunity = TradingOpportunity.from_canonical_dict(
        _document(
            _request_path(request, "opportunity_path", base=base),
            name="Opportunity",
        )
    )
    research = load_verified_research_layer_artifact(
        _request_path(request, "research_package_path", base=base)
    ).artifact
    signal_run = load_verified_signal_run(
        _request_path(request, "signal_package_path", base=base)
    ).artifact
    if signal_run.candidate_set != research.candidate_set:
        raise ValueError("Signal package does not bind current Research CandidateSet")
    matching_signals = tuple(
        item for item in signal_run.snapshots if item.symbol == thesis.symbol
    )
    if len(matching_signals) != 1:
        raise ValueError("Signal package must contain exactly one Thesis-symbol snapshot")
    path_run = load_verified_path_forecast(
        _request_path(request, "path_forecast_package_path", base=base)
    ).artifact
    if path_run.forecast.symbol != thesis.symbol:
        raise ValueError("PathForecast package does not match Thesis symbol")
    if path_run.signal_snapshot != matching_signals[0]:
        raise ValueError("PathForecast package does not bind current SignalSnapshot")
    price = DecisionPriceSnapshot.from_canonical_dict(
        _document(
            _request_path(request, "price_snapshot_path", base=base),
            name="DecisionPriceSnapshot",
        )
    )
    configuration = ThesisHealthRuleConfiguration.from_canonical_dict(
        _document(
            _request_path(request, "configuration_path", base=base),
            name="ThesisHealthRuleConfiguration",
        )
    )
    rule_set = ThesisInvalidationRuleSet.from_canonical_dict(
        _document(
            _request_path(request, "rule_set_path", base=base),
            name="ThesisInvalidationRuleSet",
        )
    )
    manual_evidence = tuple(
        ManualInvalidationEvidence.from_canonical_dict(
            _document(path, name="ManualInvalidationEvidence")
        )
        for path in _manual_paths(request["manual_evidence_paths"], base=base)
    )
    prior_id = _optional_string(
        request["prior_observation_id"], name="prior_observation_id"
    )
    prior_hash = _optional_string(
        request["prior_observation_hash"], name="prior_observation_hash"
    )
    if (prior_id is None) != (prior_hash is None):
        raise ValueError("prior Observation ID and hash must be supplied together")
    return _LoadedInputs(
        thesis=thesis,
        opportunity=opportunity,
        market_regime=research.market_regime,
        theme_rotation=research.theme_rotation,
        capital_evolution=research.capital_evolution,
        candidate_set=research.candidate_set,
        signal_snapshot=matching_signals[0],
        path_forecast=path_run.forecast,
        price_snapshot=price,
        configuration=configuration,
        rule_set=rule_set,
        manual_evidence=manual_evidence,
        expected_prior_observation_id=(
            ArtifactId(prior_id) if prior_id is not None else None
        ),
        expected_prior_observation_hash=prior_hash,
        assessed_at=datetime.fromisoformat(
            _string(request["assessed_at"], name="assessed_at")
        ),
        actor=_string(request["actor"], name="actor"),
        reason=_string(request["reason"], name="reason"),
    )


def _assess(
    database: Path,
    request: dict[str, Any],
    *,
    base: Path,
) -> dict[str, object]:
    repository = SQLiteThesisHealthRepository(database)
    inputs = _load_inputs(request, base=base)
    observation = ThesisHealthApplicationService(
        repository
    ).assess(
        thesis=inputs.thesis,
        opportunity=inputs.opportunity,
        market_regime=inputs.market_regime,
        theme_rotation=inputs.theme_rotation,
        capital_evolution=inputs.capital_evolution,
        candidate_set=inputs.candidate_set,
        signal_snapshot=inputs.signal_snapshot,
        path_forecast=inputs.path_forecast,
        price_snapshot=inputs.price_snapshot,
        configuration=inputs.configuration,
        rule_set=inputs.rule_set,
        manual_evidence=inputs.manual_evidence,
        expected_prior_observation_id=inputs.expected_prior_observation_id,
        expected_prior_observation_hash=inputs.expected_prior_observation_hash,
        assessed_at=inputs.assessed_at,
        actor=inputs.actor,
        reason=inputs.reason,
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
        "prior_observation": {
            "observation_id": (
                str(observation.prior_observation_id)
                if observation.prior_observation_id is not None
                else None
            ),
            "content_hash": observation.prior_observation_hash,
            "observed_health_state": (
                observation.prior_observed_health_state.value
                if observation.prior_observed_health_state is not None
                else None
            ),
            "effective_health_state": (
                observation.prior_effective_health_state.value
                if observation.prior_effective_health_state is not None
                else "NOT_ESTABLISHED"
            ),
        },
        "price_observation": {
            "artifact_id": str(observation.price_observation_id),
            "content_hash": observation.price_observation_hash,
        },
        "manual_evidence_authentication": (
            observation.manual_evidence_authentication
        ),
        "formal_oos_alpha": observation.formal_oos_alpha,
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
    result = _assess(
        args.database,
        _read_request(args.request),
        base=args.request.resolve().parent,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
