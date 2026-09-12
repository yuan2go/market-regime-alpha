"""Finite holdout operations over Backtest/Artifact owners, not a new executor."""

from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from uuid import UUID, uuid5, NAMESPACE_URL

from market_regime_alpha.research_qualification.domain.backtest_holdout import BacktestHoldoutReservation
from market_regime_alpha.research_qualification.domain.historical_matrix import HistoricalTimeSplit
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.runtime.application import CommandContext, ActorType


def add_holdout_parsers(commands) -> None:
    for name in ("holdout-reserve", "holdout-select", "holdout-open", "holdout-inspect"):
        parser = commands.add_parser(name)
        parser.add_argument("--expected-database-name", required=True)
        parser.add_argument("--expected-database-oid", required=True, type=int)
        if name == "holdout-reserve":
            parser.add_argument("--development-run-id", required=True, type=UUID)
            parser.add_argument("--protocol", required=True, type=Path)
        else:
            parser.add_argument("--reservation-id", required=True, type=UUID)
        if name in {"holdout-reserve", "holdout-open"}:
            parser.add_argument("--actor-id", required=True)
            parser.add_argument("--idempotency-key", required=True)
        if name == "holdout-select":
            parser.add_argument("--output-plan", required=True, type=Path)


def _closed_json(content: bytes):
    if len(content) > 1024 * 1024:
        raise ValueError("holdout boundary exceeds the one MiB declaration budget")
    def closed(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate holdout protocol field")
            result[key] = value
        return result
    return json.loads(content, object_pairs_hook=closed)


def execute_holdout(app, arguments):
    owner = app.backtest_holdouts
    if arguments.research_command == "holdout-inspect":
        return owner.queries.inspect(arguments.reservation_id)
    if arguments.research_command == "holdout-select":
        from market_regime_alpha.interfaces.historical_study import _exact, _json
        reservation = owner.queries.reservation(arguments.reservation_id)
        selected = owner.select(arguments.reservation_id)
        # owner.select already verifies the exact physical protocol. Read the
        # same object through the Artifact adapter, retaining its original bytes.
        protocol = owner.frozen_protocol(arguments.reservation_id)
        plan = protocol["development_plan"]
        plan["baseline"].update(protocol["holdout_time_split"])
        plan["baseline"]["study_code"] = reservation.future_study_code
        plan["additional_splits"] = []
        plan["ridge_candidates"] = [c for c in plan["ridge_candidates"] if c["name"] == selected["selected_arm_code"]]
        content = _json(plan)
        _exact(arguments.output_plan, content)
        return {"reservation_id": arguments.reservation_id, "selected_arm_id": selected["selected_arm_id"],
            "selected_arm_code": selected["selected_arm_code"], "selected_validation_mae": selected["selected_mae"],
            "development_projection_sha256": selected["development_projection"]["projection_sha256"],
            "plan_sha256": sha256(content).hexdigest(), "reuse_contracts_from": reservation.development_run_id,
            "next_entry": "mra research prepare-historical --reuse-contracts-from " + str(reservation.development_run_id),
            "holdout_state": "RESERVED_NOT_EXECUTED"}
    context = CommandContext(arguments.idempotency_key, ActorType.OPERATOR, arguments.actor_id, "EXPLORATORY_HOLDOUT")
    if arguments.research_command == "holdout-open":
        reservation = owner.queries.reservation(arguments.reservation_id)
        return owner.open(arguments.reservation_id, reservation.future_run_id, context)
    if arguments.protocol.stat().st_size > 1024 * 1024:
        raise ValueError("holdout boundary exceeds the one MiB declaration budget")
    with arguments.protocol.open("rb") as stream:
        content = stream.read(1024 * 1024 + 1)
    protocol = _closed_json(content)
    if not isinstance(protocol, dict) or protocol.get("schema") != "mra-historical-campaign-boundary-v1":
        raise ValueError("unsupported holdout boundary schema")
    spec = app.backtest_specifications.load_specification(arguments.development_run_id)
    future_code = protocol["future_holdout_study_code"]
    future_id = uuid5(uuid5(NAMESPACE_URL, "mra:historical-study:" + future_code), "backtest")
    artifact = app.artifacts.publish(content, media_type="application/json", context=context)
    request = BacktestHoldoutReservation(uuid5(arguments.development_run_id, "exploratory-holdout-v1"),
        arguments.development_run_id, str(spec.content_sha256), future_id, future_code,
        HistoricalTimeSplit(**{name: tuple(date.fromisoformat(day) for day in dates)
            for name, dates in protocol["holdout_time_split"].items()}),
        tuple(protocol["selection"]["eligible_candidates"]),
        ArtifactBinding(artifact.artifact_id, artifact.content_sha256, artifact.size_bytes))
    return owner.reserve(request, context)
