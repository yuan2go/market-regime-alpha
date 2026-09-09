#!/usr/bin/env python3
"""Run or replay research-only Signal and PathForecast Artifact packages."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.forecasting import (
    PathForecastConfig,
    PathForecastSample,
    build_path_forecast,
    publish_path_forecast,
    replay_path_forecast,
)
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.signals import (
    SignalModelConfig,
    SignalObservation,
    SignalSnapshot,
    publish_signal_run,
    replay_signal_run,
    run_signal_model,
)


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _array(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _read_request(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return _object(value, "request")


def _run_signal(request: dict[str, Any], output_root: Path) -> Path:
    artifact = run_signal_model(
        candidate_set=CandidateSet.from_canonical_dict(
            _object(request["candidate_set"], "candidate_set")
        ),
        configuration=SignalModelConfig.from_canonical_dict(
            _object(request["configuration"], "configuration")
        ),
        observations=tuple(
            SignalObservation.from_canonical_dict(_object(item, "observation"))
            for item in _array(request["observations"], "observations")
        ),
        decision_time=DecisionTime(
            datetime.fromisoformat(str(request["decision_time"]))
        ),
        created_at=datetime.fromisoformat(str(request["created_at"])),
        code_revision=str(request["code_revision"]),
    )
    return publish_signal_run(root=output_root, artifact=artifact)


def _run_path(request: dict[str, Any], output_root: Path) -> Path:
    artifact = build_path_forecast(
        signal_snapshot=SignalSnapshot.from_canonical_dict(
            _object(request["signal_snapshot"], "signal_snapshot")
        ),
        configuration=PathForecastConfig.from_canonical_dict(
            _object(request["configuration"], "configuration")
        ),
        samples=tuple(
            PathForecastSample.from_canonical_dict(_object(item, "sample"))
            for item in _array(request["samples"], "samples")
        ),
        decision_time=DecisionTime(
            datetime.fromisoformat(str(request["decision_time"]))
        ),
        created_at=datetime.fromisoformat(str(request["created_at"])),
        code_revision=str(request["code_revision"]),
    )
    return publish_path_forecast(root=output_root, artifact=artifact)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Research-only Signal/PathForecast run and replay CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("run-signal", "run-path"):
        child = subparsers.add_parser(command)
        child.add_argument("--request", type=Path, required=True)
        child.add_argument("--output-root", type=Path, required=True)
    for command in ("replay-signal", "replay-path"):
        child = subparsers.add_parser(command)
        child.add_argument("--artifact", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "run-signal":
        result = _run_signal(_read_request(args.request), args.output_root)
    elif args.command == "run-path":
        result = _run_path(_read_request(args.request), args.output_root)
    elif args.command == "replay-signal":
        result = replay_signal_run(args.artifact).root
    else:
        result = replay_path_forecast(args.artifact).root
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
