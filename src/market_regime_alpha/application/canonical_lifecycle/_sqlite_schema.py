"""Authoritative migration-011 schema introspection for the SQLite adapter."""

from __future__ import annotations

import sqlite3

from market_regime_alpha.application.canonical_lifecycle.repositories import (
    LifecycleJournalIntegrityError,
)


def verify_lifecycle_schema(connection: sqlite3.Connection) -> None:
    marker = connection.execute(
        "SELECT 1 FROM pdl_schema_migrations WHERE version = 11"
    ).fetchone()
    if marker is None:
        raise LifecycleJournalIntegrityError("lifecycle migration 011 is not applied")
    expected_tables = {
        "lifecycle_runs",
        "lifecycle_stages",
        "lifecycle_attempts",
        "lifecycle_stage_receipts",
        "lifecycle_events",
    }
    present_tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    missing = expected_tables - present_tables
    if missing:
        raise LifecycleJournalIntegrityError(
            f"migration 011 is missing tables: {sorted(missing)}"
        )
    expected_triggers = {
        "lifecycle_attempts_no_delete",
        "lifecycle_attempts_terminal_immutable",
        "lifecycle_attempts_completion_only",
        "lifecycle_stage_receipts_no_update",
        "lifecycle_stage_receipts_no_delete",
        "lifecycle_events_no_update",
        "lifecycle_events_no_delete",
        "lifecycle_terminal_stages_immutable",
        "lifecycle_stages_no_delete",
        "lifecycle_runs_no_delete",
        "lifecycle_runs_identity_immutable",
    }
    present_triggers = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
        )
    }
    if expected_triggers - present_triggers:
        raise LifecycleJournalIntegrityError("migration 011 trigger set is incomplete")
    expected_columns = {
        "lifecycle_runs": {
            "run_id", "idempotency_key", "command_hash", "command_json",
            "run_type", "decision_date", "as_of_time", "status",
            "current_stage", "input_manifest_id", "input_content_hash",
            "run_json", "version", "claim_token", "created_at",
            "updated_at", "completed_at",
        },
        "lifecycle_stages": {
            "run_id", "stage_name", "stage_status", "attempt_count",
            "stage_json", "version",
        },
        "lifecycle_attempts": {
            "attempt_id", "run_id", "stage_name", "attempt_number",
            "result", "attempt_json", "claim_token", "started_at",
            "completed_at", "exception_type", "exception_message",
        },
        "lifecycle_stage_receipts": {
            "receipt_id", "run_id", "stage_name", "attempt_number",
            "receipt_hash", "receipt_json", "stage_result", "created_at",
        },
        "lifecycle_events": {
            "event_id", "run_id", "sequence_number", "event_type",
            "stage_name", "attempt_id", "receipt_id", "event_json",
            "payload_json", "payload_hash", "created_at", "claim_token",
        },
    }
    for table, expected in expected_columns.items():
        actual = {
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info({table})")
        }
        if actual != expected:
            raise LifecycleJournalIntegrityError(
                f"migration 011 {table} columns are not authoritative"
            )
    table_fragments = {
        "lifecycle_runs": (
            "idempotency_key text not null unique",
            "check (json_valid(command_json))",
            "check (json_valid(run_json))",
            "check (version > 0)",
            "check (claim_token >= 0)",
            "length(command_hash) = 71",
        ),
        "lifecycle_stages": (
            "primary key (run_id, stage_name)",
            "check (attempt_count >= 0)",
            "check (version > 0)",
        ),
        "lifecycle_attempts": (
            "check (attempt_number > 0)",
            "check (claim_token > 0)",
            "check ((exception_type is null) = (exception_message is null))",
            "check ((result = 'failed') = (exception_type is not null))",
        ),
        "lifecycle_stage_receipts": (
            "check (attempt_number > 0)",
            "length(receipt_hash) = 71",
        ),
        "lifecycle_events": (
            "check (sequence_number > 0)",
            "check (claim_token >= 0)",
            "length(payload_hash) = 71",
        ),
    }
    for table, fragments in table_fragments.items():
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        sql = " ".join(str(row[0]).lower().split()) if row is not None else ""
        if any(fragment not in sql for fragment in fragments):
            raise LifecycleJournalIntegrityError(
                f"migration 011 table {table} constraints are not authoritative"
            )
    required_unique_signatures: dict[str, set[tuple[str, ...]]] = {
        "lifecycle_runs": {("idempotency_key",)},
        "lifecycle_stages": {("run_id", "stage_name")},
        "lifecycle_attempts": {
            ("run_id", "stage_name", "attempt_number"),
            ("attempt_id", "run_id", "stage_name"),
        },
        "lifecycle_stage_receipts": {
            ("run_id", "stage_name", "receipt_hash"),
            ("receipt_id", "run_id", "stage_name"),
        },
        "lifecycle_events": {("run_id", "sequence_number")},
    }
    for table, required_unique in required_unique_signatures.items():
        if not required_unique <= _unique_index_signatures(connection, table):
            raise LifecycleJournalIntegrityError(
                f"migration 011 {table} unique constraints are incomplete"
            )
    required_index_signatures: dict[str, set[tuple[str, ...]]] = {
        "lifecycle_runs": {("status", "decision_date", "run_id")},
        "lifecycle_stages": {("stage_status", "stage_name", "run_id")},
        "lifecycle_attempts": {("run_id", "stage_name", "attempt_number")},
        "lifecycle_stage_receipts": {("run_id", "created_at", "receipt_id")},
        "lifecycle_events": {("run_id", "sequence_number")},
    }
    for table, required_indexes in required_index_signatures.items():
        if not required_indexes <= _index_signatures(connection, table):
            raise LifecycleJournalIntegrityError(
                f"migration 011 {table} query indexes are incomplete"
            )
    required_foreign_keys: dict[
        str,
        set[tuple[str, tuple[str, ...], tuple[str, ...]]],
    ] = {
        "lifecycle_stages": {
            ("lifecycle_runs", ("run_id",), ("run_id",)),
        },
        "lifecycle_attempts": {
            (
                "lifecycle_stages",
                ("run_id", "stage_name"),
                ("run_id", "stage_name"),
            ),
        },
        "lifecycle_stage_receipts": {
            (
                "lifecycle_attempts",
                ("run_id", "stage_name", "attempt_number"),
                ("run_id", "stage_name", "attempt_number"),
            ),
        },
        "lifecycle_events": {
            ("lifecycle_runs", ("run_id",), ("run_id",)),
            (
                "lifecycle_stages",
                ("run_id", "stage_name"),
                ("run_id", "stage_name"),
            ),
            (
                "lifecycle_attempts",
                ("attempt_id", "run_id", "stage_name"),
                ("attempt_id", "run_id", "stage_name"),
            ),
            (
                "lifecycle_stage_receipts",
                ("receipt_id", "run_id", "stage_name"),
                ("receipt_id", "run_id", "stage_name"),
            ),
        },
    }
    for table, required_foreign in required_foreign_keys.items():
        if not required_foreign <= _foreign_key_signatures(connection, table):
            raise LifecycleJournalIntegrityError(
                f"migration 011 {table} foreign keys are incomplete"
            )
    trigger_fragments = {
        "lifecycle_attempts_no_delete": ("before delete on lifecycle_attempts",),
        "lifecycle_attempts_terminal_immutable": (
            "before update on lifecycle_attempts", "old.result != 'running'",
        ),
        "lifecycle_attempts_completion_only": (
            "before update on lifecycle_attempts", "new.result = 'running'",
        ),
        "lifecycle_stage_receipts_no_update": (
            "before update on lifecycle_stage_receipts",
        ),
        "lifecycle_stage_receipts_no_delete": (
            "before delete on lifecycle_stage_receipts",
        ),
        "lifecycle_events_no_update": ("before update on lifecycle_events",),
        "lifecycle_events_no_delete": ("before delete on lifecycle_events",),
        "lifecycle_terminal_stages_immutable": (
            "before update on lifecycle_stages", "old.stage_status in",
        ),
        "lifecycle_stages_no_delete": ("before delete on lifecycle_stages",),
        "lifecycle_runs_no_delete": ("before delete on lifecycle_runs",),
        "lifecycle_runs_identity_immutable": (
            "before update on lifecycle_runs", "new.command_json is not old.command_json",
        ),
    }
    for name, fragments in trigger_fragments.items():
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
            (name,),
        ).fetchone()
        sql = " ".join(str(row[0]).lower().split()) if row is not None else ""
        if any(fragment not in sql for fragment in fragments):
            raise LifecycleJournalIntegrityError(
                f"migration 011 trigger {name} is not authoritative"
            )


def _unique_index_signatures(
    connection: sqlite3.Connection,
    table: str,
) -> set[tuple[str, ...]]:
    signatures: set[tuple[str, ...]] = set()
    for row in connection.execute(f"PRAGMA index_list({table})"):
        if int(row[2]) != 1:
            continue
        name = str(row[1]).replace("'", "''")
        columns = tuple(
            str(item[2])
            for item in connection.execute(f"PRAGMA index_info('{name}')")
        )
        signatures.add(columns)
    return signatures


def _index_signatures(
    connection: sqlite3.Connection,
    table: str,
) -> set[tuple[str, ...]]:
    signatures: set[tuple[str, ...]] = set()
    for row in connection.execute(f"PRAGMA index_list({table})"):
        name = str(row[1]).replace("'", "''")
        signatures.add(
            tuple(
                str(item[2])
                for item in connection.execute(f"PRAGMA index_info('{name}')")
            )
        )
    return signatures


def _foreign_key_signatures(
    connection: sqlite3.Connection,
    table: str,
) -> set[tuple[str, tuple[str, ...], tuple[str, ...]]]:
    groups: dict[int, list[sqlite3.Row]] = {}
    for row in connection.execute(f"PRAGMA foreign_key_list({table})"):
        groups.setdefault(int(row[0]), []).append(row)
    signatures: set[tuple[str, tuple[str, ...], tuple[str, ...]]] = set()
    for rows in groups.values():
        ordered = sorted(rows, key=lambda item: int(item[1]))
        signatures.add(
            (
                str(ordered[0][2]),
                tuple(str(item[3]) for item in ordered),
                tuple(str(item[4]) for item in ordered),
            )
        )
    return signatures
