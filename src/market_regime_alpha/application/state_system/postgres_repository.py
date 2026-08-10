"""PostgreSQL-default fenced/CAS writer for state artifacts and Dynamic Pool."""

from __future__ import annotations

from datetime import datetime, timezone
import json
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
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import canonical_hash, canonical_json
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.research.state_system.pool import DynamicStockPoolVersion
from market_regime_alpha.research.state_system.authority import (
    DynamicPoolPolicy,
    StateSeries,
    StateTransitionPolicy,
)
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet

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
                sql.SQL("SELECT state_hash FROM {} WHERE state_id = %s FOR UPDATE").format(sql.Identifier(state_table)),
                (str(write.state_id),),
            ).fetchone()
            if stored is None or str(stored[0]) != write.state_hash:
                raise StateSystemConflict("State identity resolved to different content")
            if write.state_series is None or write.state_policy is None:
                self._advance_state_pointer(
                    connection,
                    write=write,
                    claim=claim,
                    expected_previous_state_id=expected_previous_state_id,
                )
            else:
                self._register_state_authority(
                    connection,
                    series=write.state_series,
                    policy=write.state_policy,
                    created_at=write.lineage.created_at,
                )
                self._advance_series_head(
                    connection,
                    series=write.state_series,
                    policy=write.state_policy,
                    artifact_id=write.state_id,
                    artifact_hash=write.state_hash,
                    expected_previous_artifact_id=expected_previous_state_id,
                    claim=claim,
                    as_of_time=write.lineage.as_of_time,
                    available_at=write.lineage.available_at,
                    created_at=write.lineage.created_at,
                )
            return write.state_id

        try:
            result = self._factory.run_transaction(operation)
        except psycopg.errors.UniqueViolation as exc:
            raise StateSystemConflict("State idempotency/CAS conflict") from exc
        if not isinstance(result, ArtifactId):
            raise StateSystemIntegrityError("State write returned invalid identity")
        return result

    def lookup_runtime_child(self, request: ChildExecutionRequest) -> ChildExecutionResult | None:
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
                        stage_status, available_at, reason_codes_json, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
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
                        authority.status.value,
                        authority.available_at,
                        json.dumps(list(authority.reason_codes), separators=(",", ":")),
                        created_at,
                    ),
                )
                stored = connection.execute(
                    """
                    SELECT state_receipt_id, artifact_id, artifact_hash,
                           data_eligibility, stage_status, available_at,
                           reason_codes_json
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
                    or str(stored[4]) != authority.status.value
                    or stored[5] != authority.available_at
                    or stored[6] != list(authority.reason_codes)
                ):
                    raise StateSystemConflict("State stage authority identity conflict")
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

    def append_runtime_candidate(
        self,
        *,
        request: ChildExecutionRequest,
        candidate_set: CandidateSet,
        candidate_stage: StateResearchStageArtifact,
    ) -> None:
        """Stage the State-owned final CandidateSet for crash-safe continuation."""

        from market_regime_alpha.application.state_system.runtime import (
            StateResearchStage,
        )

        if candidate_stage.stage is not StateResearchStage.CANDIDATE:
            raise ValueError("State Candidate authority requires CANDIDATE stage")
        if candidate_stage.available_at > request.as_of_time:
            raise ValueError("State Candidate authority cannot contain future data")
        candidate_set.envelope.verify_payload(candidate_set.artifact_payload())
        payload = candidate_set.to_canonical_dict()

        def operation(connection: psycopg.Connection[Any]) -> None:
            self._assert_claim(connection, request)
            connection.execute(
                """
                INSERT INTO state_runtime_candidate_artifact(
                    run_id, tick_id, candidate_id, candidate_hash,
                    stage_artifact_id, stage_artifact_hash, payload_json,
                    created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                ON CONFLICT (run_id, tick_id) DO NOTHING
                """,
                (
                    str(request.run_id),
                    str(request.tick_id),
                    str(candidate_set.envelope.artifact_id),
                    candidate_set.envelope.content_hash,
                    str(candidate_stage.artifact_id),
                    candidate_stage.artifact_hash,
                    canonical_json(payload),
                    self._clock(),
                ),
            )
            stored = connection.execute(
                """
                SELECT candidate_id, candidate_hash, stage_artifact_id,
                       stage_artifact_hash, payload_json
                FROM state_runtime_candidate_artifact
                WHERE run_id = %s AND tick_id = %s
                """,
                (str(request.run_id), str(request.tick_id)),
            ).fetchone()
            if stored is None or (
                str(stored[0]) != str(candidate_set.envelope.artifact_id)
                or str(stored[1]) != candidate_set.envelope.content_hash
                or str(stored[2]) != str(candidate_stage.artifact_id)
                or str(stored[3]) != candidate_stage.artifact_hash
                or stored[4] != payload
            ):
                raise StateSystemConflict("State Candidate staging conflict")

        self._factory.run_transaction(operation)

    def read_runtime_candidate(self, request: ChildExecutionRequest) -> CandidateSet:
        return self.get_runtime_candidate(
            run_id=request.run_id,
            tick_id=request.tick_id,
        )

    def get_runtime_candidate(
        self,
        *,
        run_id: ArtifactId,
        tick_id: ArtifactId,
    ) -> CandidateSet:
        """Owner Reader for operator/replay flows that do not hold a live lease."""

        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT candidate_id, candidate_hash, stage_artifact_id,
                       stage_artifact_hash, payload_json
                FROM state_runtime_candidate_artifact
                WHERE run_id = %s AND tick_id = %s
                """,
                (str(run_id), str(tick_id)),
            ).fetchone()
            stage = connection.execute(
                """
                SELECT artifact_id, artifact_hash
                FROM state_research_stage_authority
                WHERE run_id = %s AND tick_id = %s AND stage = 'CANDIDATE'
                """,
                (str(run_id), str(tick_id)),
            ).fetchone()
            if row is None or stage is None:
                raise StateSystemIntegrityError("State Candidate recovery authority is missing")
            payload = row[4]
            if not isinstance(payload, dict):
                raise StateSystemIntegrityError("State Candidate payload is invalid")
            try:
                candidate = CandidateSet.from_canonical_dict(payload)
            except (KeyError, TypeError, ValueError) as exc:
                raise StateSystemIntegrityError("State Candidate payload failed canonical verification") from exc
            if (
                str(row[0]) != str(candidate.envelope.artifact_id)
                or str(row[1]) != candidate.envelope.content_hash
                or str(row[2]) != str(stage[0])
                or str(row[3]) != str(stage[1])
            ):
                raise StateSystemIntegrityError("State Candidate owner lineage mismatch")
            return candidate

    def read_runtime_stages(
        self, request: ChildExecutionRequest
    ) -> tuple[
        tuple[StateResearchStageArtifact, ...],
        dict[Any, datetime],
    ]:
        from market_regime_alpha.application.state_system.runtime import (
            STATE_SYSTEM_STAGE_ORDER,
            StateResearchStage,
            StateResearchStageArtifact,
            StateResearchStageStatus,
        )

        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT stage, artifact_id, artifact_hash, data_eligibility,
                       stage_status, available_at, reason_codes_json, created_at
                FROM state_research_stage_authority
                WHERE run_id = %s AND tick_id = %s
                """,
                (str(request.run_id), str(request.tick_id)),
            ).fetchall()
        by_stage = {StateResearchStage(str(row[0])): row for row in rows}
        if set(by_stage) != set(STATE_SYSTEM_STAGE_ORDER):
            raise StateSystemIntegrityError("State Stage recovery set is incomplete")
        artifacts = tuple(
            StateResearchStageArtifact(
                stage=stage,
                artifact_id=ArtifactId(str(by_stage[stage][1])),
                artifact_hash=str(by_stage[stage][2]),
                data_eligibility=DataEligibility(str(by_stage[stage][3])),
                status=StateResearchStageStatus(str(by_stage[stage][4])),
                available_at=by_stage[stage][5],
                reason_codes=tuple(str(item) for item in by_stage[stage][6]),
            )
            for stage in STATE_SYSTEM_STAGE_ORDER
        )
        completed_at = {stage: by_stage[stage][7] for stage in STATE_SYSTEM_STAGE_ORDER}
        return artifacts, completed_at

    def _validate_runtime_receipt_composition(
        self,
        connection: psycopg.Connection[Any],
        *,
        request: ChildExecutionRequest,
        result: ChildExecutionResult,
        receipt_payload: dict[str, Any] | None,
    ) -> None:
        if receipt_payload is None:
            raise StateSystemIntegrityError("legacy State Runtime receipt has no recomputable composition")
        rows = connection.execute(
            """
            SELECT stage, artifact_id, artifact_hash, data_eligibility,
                   stage_status, available_at
            FROM state_research_stage_authority
            WHERE run_id = %s AND tick_id = %s
            """,
            (str(request.run_id), str(request.tick_id)),
        ).fetchall()
        all_order = (
            "OBSERVATION",
            "MARKET_REGIME",
            "ETF_ROTATION",
            "THEME_ROTATION",
            "CAPITAL_STATE",
            "DYNAMIC_POOL",
            "CANDIDATE",
            "SIGNAL",
            "FORECAST",
        )
        receipt_schema = receipt_payload.get("schema")
        expected_order = all_order[:7] if receipt_schema == "state_system_runtime_receipt/v3" else all_order
        order = {name: index for index, name in enumerate(expected_order)}
        if len(rows) != len(order) or any(str(row[0]) not in order for row in rows):
            raise StateSystemIntegrityError("State Runtime receipt stage authority set is incomplete")
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
                    row[5],
                )
                for row in ordered
            ),
        )
        if receipt_schema == "state_system_runtime_receipt/v3":
            if any(row[3] is None or row[4] is None for row in ordered):
                raise StateSystemIntegrityError("State Runtime v3 receipt lacks typed Stage authority")
            expected_references = [
                {
                    **RuntimeArtifactReference(
                        reference_kind=f"STATE_RESEARCH_{row[0]}",
                        artifact_id=ArtifactId(str(row[1])),
                        content_hash=str(row[2]),
                    ).to_canonical_dict(),
                    "data_eligibility": str(row[3]),
                    "stage_status": str(row[4]),
                }
                for row in ordered
            ]
        elif receipt_schema == "state_system_runtime_receipt/v2":
            if any(row[3] is None for row in ordered):
                raise StateSystemIntegrityError("State Runtime v2 receipt lacks DataEligibility authority")
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
                raise StateSystemIntegrityError("legacy State Runtime receipt eligibility was rewritten")
            expected_references = [
                RuntimeArtifactReference(
                    reference_kind=f"STATE_RESEARCH_{row[0]}",
                    artifact_id=ArtifactId(str(row[1])),
                    content_hash=str(row[2]),
                ).to_canonical_dict()
                for row in ordered
            ]
        else:
            raise StateSystemIntegrityError("unsupported State Runtime receipt schema")
        expected_receipt_id = ArtifactId(f"state-system-receipt:{result.child_receipt_hash[7:]}")
        expected_child_run_id = ArtifactId(f"state-system-run:{request.idempotency_key.removeprefix('continuous-children-')}")
        if (
            result.child_kind is not ContinuousChildKind.STATE_SYSTEM
            or result.child_run_id != expected_child_run_id
            or result.child_receipt_id != expected_receipt_id
            or result.child_artifact_id != pipeline_id
            or result.child_artifact_hash != pipeline_hash
            or receipt_payload.get("request_idempotency_key") != request.idempotency_key
            or receipt_payload.get("pipeline_artifact_id") != str(pipeline_id)
            or receipt_payload.get("pipeline_artifact_hash") != pipeline_hash
            or receipt_payload.get("stage_references") != expected_references
            or receipt_payload.get("reason_codes") != ["ENTRY_BLOCKED", "STATE_RESEARCH_CHAIN_COMPLETED"]
            or canonical_hash(receipt_payload) != result.child_receipt_hash
        ):
            raise StateSystemIntegrityError("State Runtime receipt composition cannot be reproduced")

    def append_pool(
        self,
        pool: DynamicStockPoolVersion,
        *,
        claim: ClaimedRuntimeTick,
        expected_previous_pool_id: ArtifactId | None,
        state_series: StateSeries | None = None,
        state_policy: DynamicPoolPolicy | None = None,
    ) -> dict[str, Any]:
        if not isinstance(pool, DynamicStockPoolVersion):
            raise TypeError("pool must be DynamicStockPoolVersion")
        if not isinstance(claim, ClaimedRuntimeTick):
            raise TypeError("claim must be ClaimedRuntimeTick")
        if pool.lineage.continuous_operation_id != claim.run_id or pool.runtime_tick_id != claim.tick_id:
            raise StateSystemConflict("Dynamic Pool lineage does not match active claim")
        if pool.previous_pool_id != expected_previous_pool_id:
            raise StateSystemConflict("Dynamic Pool previous identity does not match CAS expectation")
        if (state_series is None) != (state_policy is None):
            raise ValueError("Dynamic Pool State Series and Policy must be bound together")
        if (
            state_series is not None
            and state_policy is not None
            and (
                state_series.domain.value != "DYNAMIC_POOL"
                or state_series.state_policy_id != state_policy.policy_id
                or state_series.state_policy_version != state_policy.policy_version
                or state_series.state_policy_hash != state_policy.policy_hash
                or pool.lineage.state_series_id != state_series.series_id
                or pool.lineage.state_series_hash != state_series.series_hash
                or pool.lineage.state_policy_id != state_policy.policy_id
                or pool.lineage.state_policy_version != state_policy.policy_version
                or pool.lineage.state_policy_hash != state_policy.policy_hash
            )
        ):
            raise ValueError("Dynamic Pool V2 authority binding mismatch")
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
            if state_series is None or state_policy is None:
                self._advance_pointer(
                    connection,
                    pool=pool,
                    claim=claim,
                    expected_previous_pool_id=expected_previous_pool_id,
                )
            else:
                self._register_state_authority(
                    connection,
                    series=state_series,
                    policy=state_policy,
                    created_at=pool.lineage.created_at,
                )
                self._advance_series_head(
                    connection,
                    series=state_series,
                    policy=state_policy,
                    artifact_id=pool.pool_id,
                    artifact_hash=pool.pool_hash,
                    expected_previous_artifact_id=expected_previous_pool_id,
                    claim=claim,
                    as_of_time=pool.decision_time,
                    available_at=pool.available_at,
                    created_at=pool.lineage.created_at,
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

    def read_current_state(
        self,
        domain: StateDomain,
        scope_key: str,
    ) -> tuple[ArtifactId, str, dict[str, Any], datetime] | None:
        """Reload the exact State owner Artifact selected by the CAS pointer."""

        if domain not in _DOMAIN_TABLES:
            raise ValueError("unsupported State domain")
        _observation_table, state_table, _transition_table = _DOMAIN_TABLES[domain]
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                sql.SQL(
                    """
                    SELECT state.state_id, state.state_hash,
                           state.artifact_json, state.created_at,
                           pointer.current_artifact_hash
                    FROM state_current_pointer AS pointer
                    JOIN {} AS state
                      ON state.state_id = pointer.current_artifact_id
                    WHERE pointer.domain = %s AND pointer.scope_key = %s
                    """
                ).format(sql.Identifier(state_table)),
                (domain.value, scope_key),
            ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(str(row[2]))
        except (TypeError, json.JSONDecodeError) as exc:
            raise StateSystemIntegrityError("State Artifact JSON is invalid") from exc
        if not isinstance(payload, dict):
            raise StateSystemIntegrityError("State Artifact payload is not an object")
        digest = canonical_hash(payload)
        if digest != str(row[1]) or digest != str(row[4]):
            raise StateSystemIntegrityError("State Artifact/pointer hash mismatch")
        created_at = row[3]
        if not isinstance(created_at, datetime):
            raise StateSystemIntegrityError("State Artifact CreatedAt is invalid")
        return ArtifactId(str(row[0])), digest, payload, created_at

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

    def read_current_series_state(
        self,
        domain: StateDomain,
        series_id: ArtifactId,
    ) -> tuple[ArtifactId, str, dict[str, Any], datetime] | None:
        """Read the latest effective Artifact from a stable cross-session series."""

        if domain not in _DOMAIN_TABLES:
            raise ValueError("unsupported State domain")
        _observation_table, state_table, _transition_table = _DOMAIN_TABLES[domain]
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                sql.SQL(
                    """
                    SELECT state.state_id, state.state_hash, state.artifact_json,
                           state.created_at, head.current_artifact_hash
                    FROM state_series_head AS head
                    JOIN state_series AS series ON series.series_id = head.series_id
                    JOIN {} AS state ON state.state_id = head.current_artifact_id
                    WHERE head.series_id = %s AND series.domain = %s
                    """
                ).format(sql.Identifier(state_table)),
                (str(series_id), domain.value),
            ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(str(row[2]))
        except (TypeError, json.JSONDecodeError) as exc:
            raise StateSystemIntegrityError("State Series Artifact JSON is invalid") from exc
        if not isinstance(payload, dict):
            raise StateSystemIntegrityError("State Series Artifact payload is not an object")
        digest = canonical_hash(payload)
        if digest != str(row[1]) or digest != str(row[4]):
            raise StateSystemIntegrityError("State Series Artifact/head hash mismatch")
        if not isinstance(row[3], datetime):
            raise StateSystemIntegrityError("State Series CreatedAt is invalid")
        return ArtifactId(str(row[0])), digest, payload, row[3]

    def latest_pool_id_for_series(self, series_id: ArtifactId) -> ArtifactId | None:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT head.current_artifact_id
                FROM state_series_head AS head
                JOIN state_series AS series ON series.series_id = head.series_id
                WHERE head.series_id = %s AND series.domain = 'DYNAMIC_POOL'
                """,
                (str(series_id),),
            ).fetchone()
        return None if row is None else ArtifactId(str(row[0]))

    def read_series_chain(self, series_id: ArtifactId) -> tuple[tuple[ArtifactId, ArtifactId | None, ArtifactId, datetime], ...]:
        """Return immutable lineage in effective-time order for replay verification."""

        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT artifact_id, previous_artifact_id, run_id, as_of_time
                FROM state_series_link
                WHERE series_id = %s
                ORDER BY as_of_time, link_id
                """,
                (str(series_id),),
            ).fetchall()
        return tuple(
            (
                ArtifactId(str(row[0])),
                None if row[1] is None else ArtifactId(str(row[1])),
                ArtifactId(str(row[2])),
                row[3],
            )
            for row in rows
        )

    def _register_state_authority(
        self,
        connection: psycopg.Connection[Any],
        *,
        series: StateSeries,
        policy: StateTransitionPolicy | DynamicPoolPolicy,
        created_at: datetime,
    ) -> None:
        policy_payload = policy.to_canonical_dict()
        policy_domain = policy.domain.value if isinstance(policy, StateTransitionPolicy) else "DYNAMIC_POOL"
        connection.execute(
            """
            INSERT INTO state_policy_authority(
                policy_id, policy_hash, policy_version, domain, policy_json, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (policy_id) DO NOTHING
            """,
            (
                str(policy.policy_id),
                policy.policy_hash,
                policy.policy_version,
                policy_domain,
                canonical_json(policy_payload),
                created_at,
            ),
        )
        stored_policy = connection.execute(
            "SELECT policy_hash FROM state_policy_authority WHERE policy_id = %s",
            (str(policy.policy_id),),
        ).fetchone()
        if stored_policy is None or str(stored_policy[0]) != policy.policy_hash:
            raise StateSystemConflict("State Policy identity conflict")
        connection.execute(
            """
            INSERT INTO state_series(
                series_id, series_hash, domain, logical_scope, research_family,
                authority_mode, universe_policy_id, universe_policy_hash,
                model_id, model_version, configuration_id, configuration_hash,
                state_policy_id, state_policy_version, state_policy_hash,
                series_json, created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) ON CONFLICT (series_id) DO NOTHING
            """,
            (
                str(series.series_id),
                series.series_hash,
                series.domain.value,
                series.logical_scope,
                series.research_family,
                series.authority_mode,
                str(series.universe_policy_id),
                series.universe_policy_hash,
                str(series.model_id),
                series.model_version,
                str(series.configuration_id),
                series.configuration_hash,
                str(series.state_policy_id),
                series.state_policy_version,
                series.state_policy_hash,
                canonical_json(series.to_canonical_dict()),
                created_at,
            ),
        )
        stored_series = connection.execute(
            "SELECT series_hash FROM state_series WHERE series_id = %s",
            (str(series.series_id),),
        ).fetchone()
        if stored_series is None or str(stored_series[0]) != series.series_hash:
            raise StateSystemConflict("State Series identity conflict")

    def _advance_series_head(
        self,
        connection: psycopg.Connection[Any],
        *,
        series: StateSeries,
        policy: StateTransitionPolicy | DynamicPoolPolicy,
        artifact_id: ArtifactId,
        artifact_hash: str,
        expected_previous_artifact_id: ArtifactId | None,
        claim: ClaimedRuntimeTick,
        as_of_time: datetime,
        available_at: datetime,
        created_at: datetime,
    ) -> None:
        del policy
        head = connection.execute(
            """
            SELECT current_link_id, current_artifact_id, current_artifact_hash,
                   current_run_id, current_tick_sequence, current_as_of_time,
                   version, last_fencing_token
            FROM state_series_head WHERE series_id = %s FOR UPDATE
            """,
            (str(series.series_id),),
        ).fetchone()
        if head is None:
            if expected_previous_artifact_id is not None:
                raise StateSystemConflict("State Series CAS expected a missing predecessor")
            previous_link_id = None
        else:
            if str(head[1]) == str(artifact_id):
                if str(head[2]) != artifact_hash:
                    raise StateSystemConflict("State Series head hash conflict")
                return
            if expected_previous_artifact_id is None or str(head[1]) != str(expected_previous_artifact_id):
                raise StateSystemConflict("State Series CAS predecessor mismatch")
            if as_of_time <= head[5]:
                raise StateSystemConflict("State Series stale AsOfTime cannot advance head")
            if str(head[3]) == str(claim.run_id) and (claim.tick_sequence <= int(head[4]) or claim.fencing_token < int(head[7])):
                raise StateSystemConflict("State Series stale Tick/fence cannot advance head")
            previous_link_id = str(head[0])
        trading_date = connection.execute(
            "SELECT trading_date FROM continuous_research_run WHERE run_id = %s",
            (str(claim.run_id),),
        ).fetchone()
        if trading_date is None:
            raise StateSystemConflict("State Series Runtime parent is missing")
        foreign_ids: dict[str, str | None] = {
            "MARKET_REGIME": None,
            "ETF_ROTATION": None,
            "THEME_ROTATION": None,
            "CAPITAL_STATE": None,
            "DYNAMIC_POOL": None,
        }
        foreign_ids[series.domain.value] = str(artifact_id)
        link_payload = {
            "schema": "state_series_link/v1",
            "series_id": str(series.series_id),
            "previous_artifact_id": (None if expected_previous_artifact_id is None else str(expected_previous_artifact_id)),
            "artifact_id": str(artifact_id),
            "artifact_hash": artifact_hash,
            "run_id": str(claim.run_id),
            "tick_id": str(claim.tick_id),
            "trading_date": trading_date[0].isoformat(),
            "tick_sequence": claim.tick_sequence,
            "fencing_token": claim.fencing_token,
            "as_of_time": as_of_time.isoformat().replace("+00:00", "Z"),
            "available_at": available_at.isoformat().replace("+00:00", "Z"),
        }
        link_hash = canonical_hash(link_payload)
        link_id = ArtifactId(f"state-series-link:{link_hash[7:]}")
        connection.execute(
            """
            INSERT INTO state_series_link(
                link_id, link_hash, series_id, previous_link_id,
                previous_artifact_id, artifact_id, artifact_hash,
                market_regime_state_id, etf_rotation_state_id,
                theme_rotation_state_id, capital_state_id, dynamic_pool_id,
                run_id, tick_id, trading_date, tick_sequence, fencing_token,
                as_of_time, available_at, link_json, created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            ) ON CONFLICT (link_id) DO NOTHING
            """,
            (
                str(link_id),
                link_hash,
                str(series.series_id),
                previous_link_id,
                None if expected_previous_artifact_id is None else str(expected_previous_artifact_id),
                str(artifact_id),
                artifact_hash,
                foreign_ids["MARKET_REGIME"],
                foreign_ids["ETF_ROTATION"],
                foreign_ids["THEME_ROTATION"],
                foreign_ids["CAPITAL_STATE"],
                foreign_ids["DYNAMIC_POOL"],
                str(claim.run_id),
                str(claim.tick_id),
                trading_date[0],
                claim.tick_sequence,
                claim.fencing_token,
                as_of_time,
                available_at,
                canonical_json(link_payload),
                created_at,
            ),
        )
        if head is None:
            connection.execute(
                """
                INSERT INTO state_series_head(
                    series_id, current_link_id, current_artifact_id,
                    current_artifact_hash, current_run_id, current_tick_id,
                    current_tick_sequence, current_as_of_time, version,
                    last_fencing_token, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s)
                """,
                (
                    str(series.series_id),
                    str(link_id),
                    str(artifact_id),
                    artifact_hash,
                    str(claim.run_id),
                    str(claim.tick_id),
                    claim.tick_sequence,
                    as_of_time,
                    claim.fencing_token,
                    self._clock(),
                ),
            )
            return
        updated = connection.execute(
            """
            UPDATE state_series_head
            SET current_link_id = %s, current_artifact_id = %s,
                current_artifact_hash = %s, current_run_id = %s,
                current_tick_id = %s, current_tick_sequence = %s,
                current_as_of_time = %s, version = version + 1,
                last_fencing_token = %s, updated_at = %s
            WHERE series_id = %s AND version = %s
              AND current_artifact_id = %s AND current_link_id = %s
            """,
            (
                str(link_id),
                str(artifact_id),
                artifact_hash,
                str(claim.run_id),
                str(claim.tick_id),
                claim.tick_sequence,
                as_of_time,
                claim.fencing_token,
                self._clock(),
                str(series.series_id),
                int(head[6]),
                str(expected_previous_artifact_id),
                str(head[0]),
            ),
        ).rowcount
        if updated != 1:
            raise StateSystemConflict("State Series CAS update lost a concurrent race")

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
        "configuration_references": [value.to_canonical_dict() for value in result.configuration_references],
        "receipt_payload": dict(receipt_payload),
    }


def _decode_child_result(
    serialized: str,
) -> tuple[ChildExecutionResult, dict[str, Any] | None]:
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
        input_references=tuple(RuntimeArtifactReference.from_canonical_dict(value) for value in inputs if isinstance(value, dict)),
        configuration_references=tuple(
            RuntimeArtifactReference.from_canonical_dict(value) for value in configurations if isinstance(value, dict)
        ),
    )
    raw_receipt_payload = payload.get("receipt_payload")
    receipt_payload = raw_receipt_payload if isinstance(raw_receipt_payload, dict) else None
    if payload["schema"] == "state_runtime_child_receipt/v2" and (
        receipt_payload is None or canonical_hash(receipt_payload) != result.child_receipt_hash
    ):
        raise StateSystemIntegrityError("State Runtime receipt payload failed hash verification")
    return result, receipt_payload
