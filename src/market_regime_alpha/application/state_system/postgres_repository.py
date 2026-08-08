"""PostgreSQL-default fenced/CAS writer for state artifacts and Dynamic Pool."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Mapping

import psycopg
from psycopg import sql

from market_regime_alpha.application.continuous_research.journal import ClaimedRuntimeTick
from market_regime_alpha.application.continuous_research.journal import (
    ContinuousChildKind,
    RuntimeArtifactReference,
)
from market_regime_alpha.application.continuous_research.ports import (
    ChildExecutionRequest,
    ChildExecutionResult,
)
from market_regime_alpha.application.state_system.repository import (
    StateArtifactWrite,
    StateDomain,
    StateSystemConflict,
    StateSystemIntegrityError,
    decode_and_verify_pool,
)
from market_regime_alpha.application.state_system.bundles import (
    state_research_pipeline_identity,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, canonical_json
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.research.state_system.pool import DynamicStockPoolVersion

if TYPE_CHECKING:
    from market_regime_alpha.application.state_system.runtime import (
        StateResearchStageArtifact,
    )


Clock = Callable[[], datetime]

_DOMAIN_TABLES = {
    StateDomain.MARKET_REGIME: (
        "market_regime_state_observation",
        "market_regime_state",
        "market_regime_state_transition",
    ),
    StateDomain.ETF_ROTATION: (
        "etf_rotation_state_observation",
        "etf_rotation_state",
        "etf_rotation_state_transition",
    ),
    StateDomain.THEME_ROTATION: (
        "theme_rotation_state_observation",
        "theme_rotation_state",
        "theme_rotation_state_transition",
    ),
    StateDomain.CAPITAL_STATE: (
        "capital_state_observation",
        "capital_state",
        "capital_state_transition",
    ),
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class PostgresStateSystemRepository:
    """Every final write validates the active Continuous Tick in one transaction."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        clock: Clock = _now,
        apply_migrations: bool = True,
    ) -> None:
        if not isinstance(factory, PostgresConnectionFactory):
            raise TypeError("factory must be PostgresConnectionFactory")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._factory = factory
        self._clock = clock
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    @property
    def runtime_authority(self) -> bool:
        return True

    def append_state(
        self,
        write: StateArtifactWrite,
        *,
        claim: ClaimedRuntimeTick,
        expected_previous_state_id: ArtifactId | None,
    ) -> ArtifactId:
        if not isinstance(write, StateArtifactWrite):
            raise TypeError("write must be StateArtifactWrite")
        if write.previous_state_id != expected_previous_state_id:
            raise StateSystemConflict("State predecessor does not match CAS expectation")
        if write.lineage.continuous_operation_id != claim.run_id or write.lineage.runtime_tick_id != claim.tick_id:
            raise StateSystemConflict("State lineage does not match active claim")
        observation_table, state_table, transition_table = _DOMAIN_TABLES[write.domain]

        def operation(connection: psycopg.Connection[Any]) -> ArtifactId:
            self._assert_claim(connection, claim)
            connection.execute(
                sql.SQL(
                    """
                    INSERT INTO {}(
                        observation_id, observation_hash, run_id, tick_id,
                        as_of_time, available_at, artifact_json, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (observation_id) DO NOTHING
                    """
                ).format(sql.Identifier(observation_table)),
                (
                    str(write.observation_id),
                    write.observation_hash,
                    str(claim.run_id),
                    str(claim.tick_id),
                    write.lineage.as_of_time,
                    write.lineage.available_at,
                    canonical_json(write.observation_payload),
                    write.lineage.created_at,
                ),
            )
            connection.execute(
                sql.SQL(
                    """
                    INSERT INTO {}(
                        state_id, state_hash, observation_id, previous_state_id,
                        scope_key, effective_state, artifact_json, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (state_id) DO NOTHING
                    """
                ).format(sql.Identifier(state_table)),
                (
                    str(write.state_id),
                    write.state_hash,
                    str(write.observation_id),
                    None if write.previous_state_id is None else str(write.previous_state_id),
                    write.scope_key,
                    write.effective_state,
                    canonical_json(write.state_payload),
                    write.lineage.created_at,
                ),
            )
            connection.execute(
                sql.SQL(
                    """
                    INSERT INTO {}(
                        transition_id, transition_hash, state_id,
                        artifact_json, created_at
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (transition_id) DO NOTHING
                    """
                ).format(sql.Identifier(transition_table)),
                (
                    str(write.transition_id),
                    write.transition_hash,
                    str(write.state_id),
                    canonical_json(write.transition_payload),
                    write.lineage.created_at,
                ),
            )
            stored = connection.execute(
                sql.SQL(
                    "SELECT state_hash FROM {} WHERE state_id = %s FOR UPDATE"
                ).format(sql.Identifier(state_table)),
                (str(write.state_id),),
            ).fetchone()
            if stored is None or str(stored[0]) != write.state_hash:
                raise StateSystemConflict("State identity resolved to different content")
            self._advance_state_pointer(
                connection,
                write=write,
                claim=claim,
                expected_previous_state_id=expected_previous_state_id,
            )
            return write.state_id

        try:
            result = self._factory.run_transaction(operation)
        except psycopg.errors.UniqueViolation as exc:
            raise StateSystemConflict("State idempotency/CAS conflict") from exc
        if not isinstance(result, ArtifactId):
            raise StateSystemIntegrityError("State write returned invalid identity")
        return result

    def lookup_runtime_child(
        self, request: ChildExecutionRequest
    ) -> ChildExecutionResult | None:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT receipt_json
                FROM state_runtime_receipt
                WHERE run_id = %s AND tick_id = %s
                """,
                (str(request.run_id), str(request.tick_id)),
            ).fetchone()
            if row is None:
                return None
            result, receipt_payload = _decode_child_result(str(row[0]))
            self._validate_runtime_receipt_composition(
                connection,
                request=request,
                result=result,
                receipt_payload=receipt_payload,
            )
            return result

    def record_runtime_child(
        self,
        request: ChildExecutionRequest,
        result: ChildExecutionResult,
        *,
        stage_authorities: tuple[StateResearchStageArtifact, ...],
        receipt_payload: Mapping[str, Any],
    ) -> ChildExecutionResult:
        if result.child_kind is not ContinuousChildKind.STATE_SYSTEM:
            raise ValueError("State Runtime receipt requires STATE_SYSTEM child kind")
        if canonical_hash(dict(receipt_payload)) != result.child_receipt_hash:
            raise ValueError("State Runtime receipt payload/hash mismatch")
        payload = _encode_child_result(result, receipt_payload=receipt_payload)
        serialized = canonical_json(payload)

        def operation(connection: psycopg.Connection[Any]) -> ChildExecutionResult:
            self._assert_claim(connection, request)
            created_at = self._clock()
            connection.execute(
                """
                INSERT INTO state_runtime_receipt(
                    receipt_id, receipt_hash, run_id, tick_id,
                    pool_id, status, receipt_json, created_at
                ) VALUES (%s, %s, %s, %s, NULL, 'COMPLETED', %s, %s)
                ON CONFLICT (tick_id) DO NOTHING
                """,
                (
                    str(result.child_receipt_id),
                    result.child_receipt_hash,
                    str(request.run_id),
                    str(request.tick_id),
                    serialized,
                    created_at,
                ),
            )
            row = connection.execute(
                """
                SELECT receipt_hash, receipt_json
                FROM state_runtime_receipt
                WHERE run_id = %s AND tick_id = %s
                FOR UPDATE
                """,
                (str(request.run_id), str(request.tick_id)),
            ).fetchone()
            if row is None or str(row[0]) != result.child_receipt_hash:
                raise StateSystemConflict("State Runtime receipt identity conflict")
            for authority in stage_authorities:
                connection.execute(
                    """
                    INSERT INTO state_research_stage_authority(
                        run_id, tick_id, state_receipt_id, stage,
                        artifact_id, artifact_hash, data_eligibility,
                        available_at, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (run_id, tick_id, stage) DO NOTHING
                    """,
                    (
                        str(request.run_id),
                        str(request.tick_id),
                        str(result.child_receipt_id),
                        authority.stage.value,
                        str(authority.artifact_id),
                        authority.artifact_hash,
                        authority.data_eligibility.value,
                        authority.available_at,
                        created_at,
                    ),
                )
                stored = connection.execute(
                    """
                    SELECT state_receipt_id, artifact_id, artifact_hash,
                           data_eligibility, available_at
                    FROM state_research_stage_authority
                    WHERE run_id = %s AND tick_id = %s AND stage = %s
                    """,
                    (str(request.run_id), str(request.tick_id), authority.stage.value),
                ).fetchone()
                if stored is None or (
                    str(stored[0]) != str(result.child_receipt_id)
                    or str(stored[1]) != str(authority.artifact_id)
                    or str(stored[2]) != authority.artifact_hash
                    or str(stored[3]) != authority.data_eligibility.value
                    or stored[4] != authority.available_at
                ):
                    raise StateSystemConflict(
                        "State stage authority identity conflict"
                    )
            recorded, stored_receipt_payload = _decode_child_result(str(row[1]))
            self._validate_runtime_receipt_composition(
                connection,
                request=request,
                result=recorded,
                receipt_payload=stored_receipt_payload,
            )
            return recorded

        recorded = self._factory.run_transaction(operation)
        if not isinstance(recorded, ChildExecutionResult):
            raise StateSystemIntegrityError("State Runtime receipt decode failed")
        return recorded

    def _validate_runtime_receipt_composition(
        self,
        connection: psycopg.Connection[Any],
        *,
        request: ChildExecutionRequest,
        result: ChildExecutionResult,
        receipt_payload: dict[str, Any] | None,
    ) -> None:
        if receipt_payload is None:
            raise StateSystemIntegrityError(
                "legacy State Runtime receipt has no recomputable composition"
            )
        rows = connection.execute(
            """
            SELECT stage, artifact_id, artifact_hash, data_eligibility, available_at
            FROM state_research_stage_authority
            WHERE run_id = %s AND tick_id = %s
            """,
            (str(request.run_id), str(request.tick_id)),
        ).fetchall()
        order = {
            name: index
            for index, name in enumerate(
                (
                    "OBSERVATION", "MARKET_REGIME", "ETF_ROTATION",
                    "THEME_ROTATION", "CAPITAL_STATE", "DYNAMIC_POOL",
                    "CANDIDATE", "SIGNAL", "FORECAST",
                )
            )
        }
        if len(rows) != len(order) or any(str(row[0]) not in order for row in rows):
            raise StateSystemIntegrityError(
                "State Runtime receipt stage authority set is incomplete"
            )
        ordered = tuple(sorted(rows, key=lambda row: order[str(row[0])]))
        pipeline_id, pipeline_hash = state_research_pipeline_identity(
            run_id=request.run_id,
            tick_id=request.tick_id,
            as_of_time=request.as_of_time,
            stages=tuple(
                (
                    str(row[0]),
                    ArtifactId(str(row[1])),
                    str(row[2]),
                    row[4],
                )
                for row in ordered
            ),
        )
        receipt_schema = receipt_payload.get("schema")
        if receipt_schema == "state_system_runtime_receipt/v2":
            if any(row[3] is None for row in ordered):
                raise StateSystemIntegrityError(
                    "State Runtime v2 receipt lacks DataEligibility authority"
                )
            expected_references = [
                {
                    **RuntimeArtifactReference(
                        reference_kind=f"STATE_RESEARCH_{row[0]}",
                        artifact_id=ArtifactId(str(row[1])),
                        content_hash=str(row[2]),
                    ).to_canonical_dict(),
                    "data_eligibility": str(row[3]),
                }
                for row in ordered
            ]
        elif receipt_schema == "state_system_runtime_receipt/v1":
            if any(row[3] is not None for row in ordered):
                raise StateSystemIntegrityError(
                    "legacy State Runtime receipt eligibility was rewritten"
                )
            expected_references = [
                RuntimeArtifactReference(
                    reference_kind=f"STATE_RESEARCH_{row[0]}",
                    artifact_id=ArtifactId(str(row[1])),
                    content_hash=str(row[2]),
                ).to_canonical_dict()
                for row in ordered
            ]
        else:
            raise StateSystemIntegrityError(
                "unsupported State Runtime receipt schema"
            )
        expected_receipt_id = ArtifactId(
            f"state-system-receipt:{result.child_receipt_hash[7:]}"
        )
        expected_child_run_id = ArtifactId(
            "state-system-run:"
            f"{request.idempotency_key.removeprefix('continuous-children-')}"
        )
        if (
            result.child_kind is not ContinuousChildKind.STATE_SYSTEM
            or result.child_run_id != expected_child_run_id
            or result.child_receipt_id != expected_receipt_id
            or result.child_artifact_id != pipeline_id
            or result.child_artifact_hash != pipeline_hash
            or receipt_payload.get("request_idempotency_key")
            != request.idempotency_key
            or receipt_payload.get("pipeline_artifact_id") != str(pipeline_id)
            or receipt_payload.get("pipeline_artifact_hash") != pipeline_hash
            or receipt_payload.get("stage_references") != expected_references
            or receipt_payload.get("reason_codes")
            != ["ENTRY_BLOCKED", "STATE_RESEARCH_CHAIN_COMPLETED"]
            or canonical_hash(receipt_payload) != result.child_receipt_hash
        ):
            raise StateSystemIntegrityError(
                "State Runtime receipt composition cannot be reproduced"
            )

    def append_pool(
        self,
        pool: DynamicStockPoolVersion,
        *,
        claim: ClaimedRuntimeTick,
        expected_previous_pool_id: ArtifactId | None,
    ) -> dict[str, Any]:
        if not isinstance(pool, DynamicStockPoolVersion):
            raise TypeError("pool must be DynamicStockPoolVersion")
        if not isinstance(claim, ClaimedRuntimeTick):
            raise TypeError("claim must be ClaimedRuntimeTick")
        if pool.lineage.continuous_operation_id != claim.run_id or pool.runtime_tick_id != claim.tick_id:
            raise StateSystemConflict("Dynamic Pool lineage does not match active claim")
        if pool.previous_pool_id != expected_previous_pool_id:
            raise StateSystemConflict("Dynamic Pool previous identity does not match CAS expectation")
        serialized = canonical_json(pool.to_canonical_dict())

        def operation(connection: psycopg.Connection[Any]) -> dict[str, Any]:
            self._assert_claim(connection, claim)
            try:
                connection.execute(
                    """
                    INSERT INTO dynamic_stock_pool(
                        pool_id, pool_hash, previous_pool_id, pool_version,
                        run_id, tick_id, claim_id, fencing_token, tick_version,
                        effective_at, available_at, decision_time,
                        material_state_hash, configuration_id, configuration_hash,
                        pool_json, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (pool_id) DO NOTHING
                    """,
                    (
                        str(pool.pool_id),
                        pool.pool_hash,
                        None if pool.previous_pool_id is None else str(pool.previous_pool_id),
                        pool.pool_version,
                        str(claim.run_id),
                        str(claim.tick_id),
                        claim.claim_id,
                        claim.fencing_token,
                        claim.tick_version,
                        pool.effective_at,
                        pool.available_at,
                        pool.decision_time,
                        pool.material_state_hash,
                        str(pool.lineage.configuration_id),
                        pool.configuration_hash,
                        serialized,
                        pool.lineage.created_at,
                    ),
                )
            except psycopg.errors.UniqueViolation as exc:
                raise StateSystemConflict("Dynamic Pool idempotency/CAS conflict") from exc
            stored = connection.execute(
                "SELECT pool_hash, pool_json FROM dynamic_stock_pool WHERE pool_id = %s FOR UPDATE",
                (str(pool.pool_id),),
            ).fetchone()
            if stored is None or str(stored[0]) != pool.pool_hash:
                raise StateSystemConflict("Dynamic Pool identity resolved to different content")
            for member in pool.members:
                connection.execute(
                    """
                    INSERT INTO dynamic_stock_pool_member(
                        pool_id, symbol, included, rank, member_json
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (pool_id, symbol) DO NOTHING
                    """,
                    (
                        str(pool.pool_id),
                        member.symbol,
                        member.included,
                        member.rank,
                        canonical_json(member.to_canonical_dict()),
                    ),
                )
            for symbol, change_type in (
                *((symbol, "ADDED") for symbol in pool.added_symbols),
                *((symbol, "REMOVED") for symbol in pool.removed_symbols),
            ):
                connection.execute(
                    """
                    INSERT INTO dynamic_stock_pool_change(
                        pool_id, symbol, change_type, change_json
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (pool_id, symbol, change_type) DO NOTHING
                    """,
                    (
                        str(pool.pool_id),
                        symbol,
                        change_type,
                        canonical_json({"symbol": symbol, "change_type": change_type}),
                    ),
                )
            self._advance_pointer(
                connection,
                pool=pool,
                claim=claim,
                expected_previous_pool_id=expected_previous_pool_id,
            )
            return decode_and_verify_pool(str(stored[1]))

        try:
            result = self._factory.run_transaction(operation)
        except psycopg.errors.UniqueViolation as exc:
            raise StateSystemConflict("Dynamic Pool concurrent write conflict") from exc
        if not isinstance(result, dict):
            raise StateSystemIntegrityError("Dynamic Pool write did not return validated content")
        return result

    def read_pool(self, pool_id: ArtifactId) -> dict[str, Any]:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT pool_json FROM dynamic_stock_pool WHERE pool_id = %s",
                (str(pool_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(pool_id))
        return decode_and_verify_pool(str(row[0]))

    def latest_pool_id(self, continuous_operation_id: ArtifactId) -> ArtifactId | None:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT current_artifact_id
                FROM state_current_pointer
                WHERE domain = 'DYNAMIC_POOL' AND scope_key = %s
                """,
                (str(continuous_operation_id),),
            ).fetchone()
        return None if row is None else ArtifactId(str(row[0]))

    def _assert_claim(
        self,
        connection: psycopg.Connection[Any],
        claim: ClaimedRuntimeTick | ChildExecutionRequest,
    ) -> None:
        row = connection.execute(
            """
            SELECT status, claim_id, fencing_token, version, lease_expires_at
            FROM continuous_runtime_tick
            WHERE run_id = %s AND tick_id = %s
            FOR UPDATE
            """,
            (str(claim.run_id), str(claim.tick_id)),
        ).fetchone()
        now = self._clock()
        if (
            row is None
            or str(row[0]) != "IN_PROGRESS"
            or str(row[1]) != claim.claim_id
            or int(row[2]) != claim.fencing_token
            or int(row[3]) != claim.tick_version
            or row[4] is None
            or row[4] <= now
        ):
            raise StateSystemConflict("stale Continuous Tick claim/fence cannot write State")

    def _advance_pointer(
        self,
        connection: psycopg.Connection[Any],
        *,
        pool: DynamicStockPoolVersion,
        claim: ClaimedRuntimeTick,
        expected_previous_pool_id: ArtifactId | None,
    ) -> None:
        scope = str(pool.lineage.continuous_operation_id)
        row = connection.execute(
            """
            SELECT current_artifact_id, current_artifact_hash, version, last_fencing_token
            FROM state_current_pointer
            WHERE domain = 'DYNAMIC_POOL' AND scope_key = %s
            FOR UPDATE
            """,
            (scope,),
        ).fetchone()
        if row is None:
            if expected_previous_pool_id is not None:
                raise StateSystemConflict("Dynamic Pool CAS expected a missing predecessor")
            connection.execute(
                """
                INSERT INTO state_current_pointer(
                    domain, scope_key, current_artifact_id,
                    current_artifact_hash, version, last_fencing_token, updated_at
                ) VALUES ('DYNAMIC_POOL', %s, %s, %s, 1, %s, %s)
                """,
                (scope, str(pool.pool_id), pool.pool_hash, claim.fencing_token, self._clock()),
            )
            return
        if str(row[0]) == str(pool.pool_id):
            if str(row[1]) != pool.pool_hash:
                raise StateSystemConflict("Dynamic Pool pointer hash conflict")
            return
        if expected_previous_pool_id is None or str(row[0]) != str(expected_previous_pool_id):
            raise StateSystemConflict("Dynamic Pool CAS predecessor mismatch")
        if claim.fencing_token < int(row[3]):
            raise StateSystemConflict("Dynamic Pool fencing token regressed")
        updated = connection.execute(
            """
            UPDATE state_current_pointer
            SET current_artifact_id = %s, current_artifact_hash = %s,
                version = version + 1, last_fencing_token = %s, updated_at = %s
            WHERE domain = 'DYNAMIC_POOL' AND scope_key = %s
              AND version = %s AND current_artifact_id = %s
            """,
            (
                str(pool.pool_id),
                pool.pool_hash,
                claim.fencing_token,
                self._clock(),
                scope,
                int(row[2]),
                str(expected_previous_pool_id),
            ),
        ).rowcount
        if updated != 1:
            raise StateSystemConflict("Dynamic Pool CAS update lost a concurrent race")

    def _advance_state_pointer(
        self,
        connection: psycopg.Connection[Any],
        *,
        write: StateArtifactWrite,
        claim: ClaimedRuntimeTick,
        expected_previous_state_id: ArtifactId | None,
    ) -> None:
        row = connection.execute(
            """
            SELECT current_artifact_id, current_artifact_hash, version, last_fencing_token
            FROM state_current_pointer
            WHERE domain = %s AND scope_key = %s
            FOR UPDATE
            """,
            (write.domain.value, write.scope_key),
        ).fetchone()
        if row is None:
            if expected_previous_state_id is not None:
                raise StateSystemConflict("State CAS expected a missing predecessor")
            connection.execute(
                """
                INSERT INTO state_current_pointer(
                    domain, scope_key, current_artifact_id,
                    current_artifact_hash, version, last_fencing_token, updated_at
                ) VALUES (%s, %s, %s, %s, 1, %s, %s)
                """,
                (
                    write.domain.value,
                    write.scope_key,
                    str(write.state_id),
                    write.state_hash,
                    claim.fencing_token,
                    self._clock(),
                ),
            )
            return
        if str(row[0]) == str(write.state_id):
            if str(row[1]) != write.state_hash:
                raise StateSystemConflict("State pointer hash conflict")
            return
        if expected_previous_state_id is None or str(row[0]) != str(expected_previous_state_id):
            raise StateSystemConflict("State CAS predecessor mismatch")
        if claim.fencing_token < int(row[3]):
            raise StateSystemConflict("State fencing token regressed")
        updated = connection.execute(
            """
            UPDATE state_current_pointer
            SET current_artifact_id = %s, current_artifact_hash = %s,
                version = version + 1, last_fencing_token = %s, updated_at = %s
            WHERE domain = %s AND scope_key = %s
              AND version = %s AND current_artifact_id = %s
            """,
            (
                str(write.state_id),
                write.state_hash,
                claim.fencing_token,
                self._clock(),
                write.domain.value,
                write.scope_key,
                int(row[2]),
                str(expected_previous_state_id),
            ),
        ).rowcount
        if updated != 1:
            raise StateSystemConflict("State CAS update lost a concurrent race")


def _encode_child_result(
    result: ChildExecutionResult,
    *,
    receipt_payload: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "state_runtime_child_receipt/v2",
        "child_kind": result.child_kind.value,
        "child_run_id": str(result.child_run_id),
        "child_receipt_id": str(result.child_receipt_id),
        "child_receipt_hash": result.child_receipt_hash,
        "child_artifact_id": None if result.child_artifact_id is None else str(result.child_artifact_id),
        "child_artifact_hash": result.child_artifact_hash,
        "input_references": [value.to_canonical_dict() for value in result.input_references],
        "configuration_references": [
            value.to_canonical_dict() for value in result.configuration_references
        ],
        "receipt_payload": dict(receipt_payload),
    }


def _decode_child_result(
    serialized: str,
) -> tuple[ChildExecutionResult, dict[str, Any] | None]:
    import json

    try:
        payload = json.loads(serialized)
    except json.JSONDecodeError as exc:
        raise StateSystemIntegrityError("State Runtime receipt JSON is invalid") from exc
    if not isinstance(payload, dict) or payload.get("schema") not in {
        "state_runtime_child_receipt/v1",
        "state_runtime_child_receipt/v2",
    }:
        raise StateSystemIntegrityError("State Runtime receipt schema is invalid")
    inputs = payload.get("input_references")
    configurations = payload.get("configuration_references")
    if not isinstance(inputs, list) or not isinstance(configurations, list):
        raise StateSystemIntegrityError("State Runtime receipt references are invalid")
    artifact_id = payload.get("child_artifact_id")
    artifact_hash = payload.get("child_artifact_hash")
    result = ChildExecutionResult(
        child_kind=ContinuousChildKind(str(payload["child_kind"])),
        child_run_id=ArtifactId(str(payload["child_run_id"])),
        child_receipt_id=ArtifactId(str(payload["child_receipt_id"])),
        child_receipt_hash=str(payload["child_receipt_hash"]),
        child_artifact_id=None if artifact_id is None else ArtifactId(str(artifact_id)),
        child_artifact_hash=None if artifact_hash is None else str(artifact_hash),
        input_references=tuple(
            RuntimeArtifactReference.from_canonical_dict(value)
            for value in inputs
            if isinstance(value, dict)
        ),
        configuration_references=tuple(
            RuntimeArtifactReference.from_canonical_dict(value)
            for value in configurations
            if isinstance(value, dict)
        ),
    )
    raw_receipt_payload = payload.get("receipt_payload")
    receipt_payload = (
        raw_receipt_payload if isinstance(raw_receipt_payload, dict) else None
    )
    if payload["schema"] == "state_runtime_child_receipt/v2" and (
        receipt_payload is None
        or canonical_hash(receipt_payload) != result.child_receipt_hash
    ):
        raise StateSystemIntegrityError(
            "State Runtime receipt payload failed hash verification"
        )
    return result, receipt_payload
