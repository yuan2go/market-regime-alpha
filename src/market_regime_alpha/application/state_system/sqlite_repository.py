"""Explicit SQLite compatibility/replay adapter for Dynamic Pool history."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Any

from market_regime_alpha.application.state_system.repository import (
    StateArtifactWrite,
    StateSystemConflict,
    decode_and_verify_pool,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_json
from market_regime_alpha.research.state_system.pool import DynamicStockPoolVersion


class SQLiteStateSystemRepository:
    """Replay compatibility only; never the Continuous Runtime write authority."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise TypeError("path must be Path")
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE IF NOT EXISTS dynamic_stock_pool (
                    pool_id TEXT PRIMARY KEY,
                    pool_hash TEXT NOT NULL UNIQUE,
                    previous_pool_id TEXT REFERENCES dynamic_stock_pool(pool_id),
                    operation_id TEXT NOT NULL,
                    pool_version INTEGER NOT NULL,
                    pool_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dynamic_stock_pool_member (
                    pool_id TEXT NOT NULL REFERENCES dynamic_stock_pool(pool_id),
                    symbol TEXT NOT NULL,
                    member_json TEXT NOT NULL,
                    PRIMARY KEY(pool_id, symbol)
                );
                CREATE TABLE IF NOT EXISTS dynamic_pool_current (
                    operation_id TEXT PRIMARY KEY,
                    pool_id TEXT NOT NULL REFERENCES dynamic_stock_pool(pool_id),
                    pool_hash TEXT NOT NULL,
                    version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS state_artifact (
                    domain TEXT NOT NULL,
                    scope_key TEXT NOT NULL,
                    observation_id TEXT NOT NULL UNIQUE,
                    observation_hash TEXT NOT NULL UNIQUE,
                    observation_json TEXT NOT NULL,
                    state_id TEXT PRIMARY KEY,
                    state_hash TEXT NOT NULL UNIQUE,
                    previous_state_id TEXT REFERENCES state_artifact(state_id),
                    effective_state TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    transition_id TEXT NOT NULL UNIQUE,
                    transition_hash TEXT NOT NULL UNIQUE,
                    transition_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS state_current_pointer (
                    domain TEXT NOT NULL,
                    scope_key TEXT NOT NULL,
                    state_id TEXT NOT NULL REFERENCES state_artifact(state_id),
                    state_hash TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    PRIMARY KEY(domain, scope_key)
                );
                """
            )

    @property
    def runtime_authority(self) -> bool:
        return False

    def append_state(
        self,
        write: StateArtifactWrite,
        *,
        expected_previous_state_id: ArtifactId | None,
    ) -> ArtifactId:
        if write.previous_state_id != expected_previous_state_id:
            raise StateSystemConflict("SQLite State predecessor mismatch")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO state_artifact(
                        domain, scope_key, observation_id, observation_hash,
                        observation_json, state_id, state_hash, previous_state_id,
                        effective_state, state_json, transition_id,
                        transition_hash, transition_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        write.domain.value,
                        write.scope_key,
                        str(write.observation_id),
                        write.observation_hash,
                        canonical_json(write.observation_payload),
                        str(write.state_id),
                        write.state_hash,
                        None if write.previous_state_id is None else str(write.previous_state_id),
                        write.effective_state,
                        canonical_json(write.state_payload),
                        str(write.transition_id),
                        write.transition_hash,
                        canonical_json(write.transition_payload),
                    ),
                )
                stored = connection.execute(
                    "SELECT state_hash FROM state_artifact WHERE state_id = ?",
                    (str(write.state_id),),
                ).fetchone()
                if stored is None or str(stored[0]) != write.state_hash:
                    raise StateSystemConflict("SQLite State identity conflict")
                pointer = connection.execute(
                    """
                    SELECT state_id, state_hash, version
                    FROM state_current_pointer
                    WHERE domain = ? AND scope_key = ?
                    """,
                    (write.domain.value, write.scope_key),
                ).fetchone()
                if pointer is None:
                    if expected_previous_state_id is not None:
                        raise StateSystemConflict("SQLite State CAS missing predecessor")
                    connection.execute(
                        "INSERT INTO state_current_pointer VALUES (?, ?, ?, ?, 1)",
                        (write.domain.value, write.scope_key, str(write.state_id), write.state_hash),
                    )
                elif str(pointer[0]) != str(write.state_id):
                    if expected_previous_state_id is None or str(pointer[0]) != str(expected_previous_state_id):
                        raise StateSystemConflict("SQLite State CAS predecessor mismatch")
                    updated = connection.execute(
                        """
                        UPDATE state_current_pointer
                        SET state_id = ?, state_hash = ?, version = version + 1
                        WHERE domain = ? AND scope_key = ?
                          AND state_id = ? AND version = ?
                        """,
                        (
                            str(write.state_id),
                            write.state_hash,
                            write.domain.value,
                            write.scope_key,
                            str(expected_previous_state_id),
                            int(pointer[2]),
                        ),
                    ).rowcount
                    if updated != 1:
                        raise StateSystemConflict("SQLite State CAS race")
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return write.state_id

    def append_pool(
        self,
        pool: DynamicStockPoolVersion,
        *,
        expected_previous_pool_id: ArtifactId | None,
    ) -> dict[str, Any]:
        if pool.previous_pool_id != expected_previous_pool_id:
            raise StateSystemConflict("SQLite Dynamic Pool predecessor mismatch")
        operation_id = str(pool.lineage.continuous_operation_id)
        serialized = canonical_json(pool.to_canonical_dict())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO dynamic_stock_pool(
                        pool_id, pool_hash, previous_pool_id,
                        operation_id, pool_version, pool_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(pool.pool_id),
                        pool.pool_hash,
                        None if pool.previous_pool_id is None else str(pool.previous_pool_id),
                        operation_id,
                        pool.pool_version,
                        serialized,
                    ),
                )
                stored = connection.execute(
                    "SELECT pool_hash, pool_json FROM dynamic_stock_pool WHERE pool_id = ?",
                    (str(pool.pool_id),),
                ).fetchone()
                if stored is None or str(stored[0]) != pool.pool_hash:
                    raise StateSystemConflict("SQLite Dynamic Pool identity conflict")
                for member in pool.members:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO dynamic_stock_pool_member(
                            pool_id, symbol, member_json
                        ) VALUES (?, ?, ?)
                        """,
                        (str(pool.pool_id), member.symbol, canonical_json(member.to_canonical_dict())),
                    )
                pointer = connection.execute(
                    "SELECT pool_id, pool_hash, version FROM dynamic_pool_current WHERE operation_id = ?",
                    (operation_id,),
                ).fetchone()
                if pointer is None:
                    if expected_previous_pool_id is not None:
                        raise StateSystemConflict("SQLite Dynamic Pool CAS missing predecessor")
                    connection.execute(
                        "INSERT INTO dynamic_pool_current VALUES (?, ?, ?, 1)",
                        (operation_id, str(pool.pool_id), pool.pool_hash),
                    )
                elif str(pointer[0]) != str(pool.pool_id):
                    if expected_previous_pool_id is None or str(pointer[0]) != str(expected_previous_pool_id):
                        raise StateSystemConflict("SQLite Dynamic Pool CAS predecessor mismatch")
                    updated = connection.execute(
                        """
                        UPDATE dynamic_pool_current
                        SET pool_id = ?, pool_hash = ?, version = version + 1
                        WHERE operation_id = ? AND pool_id = ? AND version = ?
                        """,
                        (
                            str(pool.pool_id),
                            pool.pool_hash,
                            operation_id,
                            str(expected_previous_pool_id),
                            int(pointer[2]),
                        ),
                    ).rowcount
                    if updated != 1:
                        raise StateSystemConflict("SQLite Dynamic Pool CAS race")
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return decode_and_verify_pool(str(stored[1]))

    def read_pool(self, pool_id: ArtifactId) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT pool_json FROM dynamic_stock_pool WHERE pool_id = ?",
                (str(pool_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(pool_id))
        return decode_and_verify_pool(str(row[0]))

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()
