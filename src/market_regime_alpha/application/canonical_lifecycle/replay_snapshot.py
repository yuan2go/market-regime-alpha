"""Immutable source-journal snapshots for recoverable durable replay."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from market_regime_alpha.application.canonical_lifecycle._immutable_io import (
    publish_immutable_text,
)
from market_regime_alpha.application.canonical_lifecycle.commands import (
    CanonicalLifecycleCommand,
)
from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleAttempt,
    LifecycleEvent,
    LifecycleRun,
    LifecycleStage,
    StageReceipt,
)
from market_regime_alpha.application.canonical_lifecycle.repositories import (
    LifecycleHistory,
    LifecycleJournalIntegrityError,
    LifecycleRunRepository,
)
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    canonical_json,
    require_sha256,
)


def lifecycle_history_hash(history: LifecycleHistory) -> str:
    """Bind one exact, internally consistent view of a lifecycle journal."""

    if not isinstance(history, LifecycleHistory):
        raise TypeError("history must be a LifecycleHistory")
    return canonical_hash(_history_payload(history))


def publish_source_history_snapshot(
    *,
    root: Path,
    source_command: CanonicalLifecycleCommand,
    source_history: LifecycleHistory,
) -> Path:
    """Publish the source view before the replay journal may mutate."""

    source_history_hash = lifecycle_history_hash(source_history)
    path = _source_snapshot_path(root, source_history_hash)
    payload = canonical_json(
        {
            "schema_version": "canonical-lifecycle-source-snapshot-v1",
            "source_command": source_command.to_canonical_dict(),
            "source_history_hash": source_history_hash,
            "history": _history_payload(source_history),
        }
    ) + "\n"
    try:
        publish_immutable_text(
            path=path,
            payload=payload,
            collision_message="source history snapshot identity collision",
        )
    except ValueError as exc:
        raise LifecycleJournalIntegrityError(str(exc)) from exc
    return path


def load_or_recover_source_snapshot(
    *,
    repository: LifecycleRunRepository,
    replay_command: CanonicalLifecycleCommand,
) -> tuple[CanonicalLifecycleCommand, LifecycleHistory]:
    """Load a captured view, or forward-repair an old run only if unchanged."""

    assert replay_command.source_run_id is not None
    assert replay_command.source_history_hash is not None
    path = _source_snapshot_path(
        replay_command.output_directory,
        replay_command.source_history_hash,
    )
    if not path.is_file():
        source_command = repository.get_command(replay_command.source_run_id)
        source_history = repository.history(replay_command.source_run_id)
        if (
            source_command.command_hash != replay_command.source_command_hash
            or lifecycle_history_hash(source_history)
            != replay_command.source_history_hash
        ):
            raise LifecycleJournalIntegrityError(
                "replay source snapshot is missing and the source has advanced"
            )
        publish_source_history_snapshot(
            root=replay_command.output_directory,
            source_command=source_command,
            source_history=source_history,
        )
    return _load_source_history_snapshot(path)


def _source_snapshot_path(root: Path, source_history_hash: str) -> Path:
    require_sha256("source_history_hash", source_history_hash)
    return (
        root.resolve()
        / "source-history-snapshots"
        / source_history_hash.split(":", 1)[1]
        / "history.json"
    )


def _load_source_history_snapshot(
    path: Path,
) -> tuple[CanonicalLifecycleCommand, LifecycleHistory]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LifecycleJournalIntegrityError(
            "source history snapshot is unavailable or invalid"
        ) from exc
    if not isinstance(raw, Mapping) or set(raw) != {
        "schema_version",
        "source_command",
        "source_history_hash",
        "history",
    }:
        raise LifecycleJournalIntegrityError("source history snapshot fields mismatch")
    if raw["schema_version"] != "canonical-lifecycle-source-snapshot-v1":
        raise LifecycleJournalIntegrityError(
            "unsupported source history snapshot schema"
        )
    command_payload = raw["source_command"]
    history_payload = raw["history"]
    source_history_hash = raw["source_history_hash"]
    if (
        not isinstance(command_payload, Mapping)
        or not isinstance(history_payload, Mapping)
        or not isinstance(source_history_hash, str)
    ):
        raise LifecycleJournalIntegrityError(
            "source history snapshot payload types mismatch"
        )
    try:
        source_command = CanonicalLifecycleCommand.from_canonical_dict(
            command_payload
        )
        source_history = _history_from_payload(history_payload)
        require_sha256("source_history_hash", source_history_hash)
    except (KeyError, TypeError, ValueError) as exc:
        raise LifecycleJournalIntegrityError(
            "source history snapshot semantic validation failed"
        ) from exc
    if (
        lifecycle_history_hash(source_history) != source_history_hash
        or path.parent.name != source_history_hash.split(":", 1)[1]
    ):
        raise LifecycleJournalIntegrityError(
            "source history snapshot content address mismatch"
        )
    return source_command, source_history


def _history_payload(history: LifecycleHistory) -> dict[str, Any]:
    return {
        "schema_version": "canonical-lifecycle-replay-journal-v1",
        "run": history.run.to_canonical_dict(),
        "stages": [item.to_canonical_dict() for item in history.stages],
        "attempts": [item.to_canonical_dict() for item in history.attempts],
        "receipts": [item.to_canonical_dict() for item in history.receipts],
        "events": [item.to_canonical_dict() for item in history.events],
        "event_payloads": list(history.event_payloads),
    }


def _history_from_payload(payload: Mapping[str, Any]) -> LifecycleHistory:
    expected = {
        "schema_version",
        "run",
        "stages",
        "attempts",
        "receipts",
        "events",
        "event_payloads",
    }
    if set(payload) != expected:
        raise ValueError("source LifecycleHistory fields mismatch")
    if payload["schema_version"] != "canonical-lifecycle-replay-journal-v1":
        raise ValueError("unsupported source LifecycleHistory schema")
    run = _mapping(payload["run"], "run")
    stages = _mapping_list(payload["stages"], "stages")
    attempts = _mapping_list(payload["attempts"], "attempts")
    receipts = _mapping_list(payload["receipts"], "receipts")
    events = _mapping_list(payload["events"], "events")
    event_payloads = payload["event_payloads"]
    if not isinstance(event_payloads, list) or any(
        not isinstance(item, str) for item in event_payloads
    ):
        raise ValueError("event_payloads must contain strings")
    return LifecycleHistory(
        run=LifecycleRun.from_canonical_dict(run),
        stages=tuple(LifecycleStage.from_canonical_dict(item) for item in stages),
        attempts=tuple(
            LifecycleAttempt.from_canonical_dict(item) for item in attempts
        ),
        receipts=tuple(StageReceipt.from_canonical_dict(item) for item in receipts),
        events=tuple(LifecycleEvent.from_canonical_dict(item) for item in events),
        event_payloads=tuple(event_payloads),
    )


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _mapping_list(value: Any, label: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, Mapping) for item in value
    ):
        raise ValueError(f"{label} must contain objects")
    return tuple(value)
