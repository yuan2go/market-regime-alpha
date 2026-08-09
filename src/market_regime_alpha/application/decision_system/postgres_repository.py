"""Native PostgreSQL authority for the research/manual decision closure."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
from typing import TYPE_CHECKING, Any, Callable, TypeVar, cast

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from market_regime_alpha.application.continuous_research.journal import (
    ClaimedRuntimeTick,
)
from market_regime_alpha.application.decision_system.contracts import (
    AccountReconciliationReport,
    DailyDecisionWindowSummary,
    DecisionRiskConfiguration,
    IndependentRiskDecision,
    ManualAccountObservation,
    ReconciliationTolerance,
    ResearchPortfolioProposal,
)
from market_regime_alpha.application.decision_system.authority import (
    DecisionStateAuthorityContext,
    FillDerivedAccountAuthority,
    PostgresFillDerivedAccountAuthorityReader,
    PositionSettlementEvidence,
)
from market_regime_alpha.application.decision_system.research_summary import (
    GOVERNED_RESEARCH_MODEL_SLOTS,
    ResearchDailySummary,
    ResearchStageStatus,
)
from market_regime_alpha.application.state_system.bundles import (
    scoped_state_stage_bundle_identity,
    state_research_pipeline_identity,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_datetime, canonical_hash
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.native_repository import (
    NativePostgresRepository,
    PostgresConnection,
    acquire_scope_lock,
    aware_datetime,
)
from market_regime_alpha.platform.runtime_governance import (
    ModelSelectionReceipt,
    ModelSelectionRequest,
    RuntimeAuthorityMode,
    SelectionStatus,
)

if TYPE_CHECKING:
    from market_regime_alpha.application.decision_system.runtime import (
        DecisionRuntimeReceipt,
    )


Clock = Callable[[], datetime]
_T = TypeVar("_T")


class DecisionSystemConflict(ValueError):
    """Idempotency, CAS, unique Final or active-fence conflict."""


class DecisionSystemIntegrityError(ValueError):
    """Stored decision authority fails canonical restoration."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class PostgresDecisionSystemRepository(NativePostgresRepository):
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        clock: Clock = _utc_now,
    ) -> None:
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._clock = clock
        super().__init__(factory)

    def record_reconciliation_tolerance(
        self,
        configuration: ReconciliationTolerance,
        *,
        claim: ClaimedRuntimeTick,
    ) -> ReconciliationTolerance:
        def operation(connection: PostgresConnection) -> ReconciliationTolerance:
            self._assert_claim(connection, claim)
            connection.execute(
                """
                INSERT INTO reconciliation_tolerance_configuration(
                    configuration_id, configuration_hash, payload_json, created_at
                ) VALUES (%s, %s, %s, %s)
                ON CONFLICT (configuration_id) DO NOTHING
                """,
                (
                    str(configuration.configuration_id),
                    configuration.configuration_hash,
                    Jsonb(configuration.to_canonical_dict()),
                    self._clock(),
                ),
            )
            return self._load_reconciliation_tolerance(
                connection,
                configuration.configuration_id,
            )

        return cast(ReconciliationTolerance, self._run(operation))

    def get_reconciliation_tolerance(
        self,
        configuration_id: ArtifactId,
    ) -> ReconciliationTolerance:
        with self._connect() as connection:
            return self._load_reconciliation_tolerance(
                connection,
                configuration_id,
            )

    def record_risk_configuration(
        self,
        configuration: DecisionRiskConfiguration,
        *,
        claim: ClaimedRuntimeTick,
    ) -> DecisionRiskConfiguration:
        def operation(connection: PostgresConnection) -> DecisionRiskConfiguration:
            self._assert_claim(connection, claim)
            connection.execute(
                """
                INSERT INTO decision_risk_configuration(
                    configuration_id, configuration_hash, payload_json, created_at
                ) VALUES (%s, %s, %s, %s)
                ON CONFLICT (configuration_id) DO NOTHING
                """,
                (
                    str(configuration.configuration_id),
                    configuration.configuration_hash,
                    Jsonb(configuration.to_canonical_dict()),
                    self._clock(),
                ),
            )
            return self._load_risk_configuration(
                connection,
                configuration.configuration_id,
            )

        return cast(DecisionRiskConfiguration, self._run(operation))

    def get_risk_configuration(
        self,
        configuration_id: ArtifactId,
    ) -> DecisionRiskConfiguration:
        with self._connect() as connection:
            return self._load_risk_configuration(connection, configuration_id)

    def load_fill_derived_account_authority(
        self,
        *,
        account_id: str,
        as_of_time: datetime,
        settlement_evidence: PositionSettlementEvidence | None = None,
    ) -> FillDerivedAccountAuthority:
        return PostgresFillDerivedAccountAuthorityReader(
            self._postgres_factory
        ).load(
            account_id=account_id,
            as_of_time=as_of_time,
            settlement_evidence=settlement_evidence,
        )

    def record_position_settlement_evidence(
        self,
        evidence: PositionSettlementEvidence,
        *,
        claim: ClaimedRuntimeTick,
    ) -> PositionSettlementEvidence:
        def operation(connection: PostgresConnection) -> PositionSettlementEvidence:
            self._assert_claim(connection, claim)
            acquire_scope_lock(
                connection,
                namespace="decision-position-settlement-evidence",
                identity=(
                    f"{evidence.account_id}:"
                    f"{canonical_datetime(evidence.as_of_time)}"
                ),
            )
            connection.execute(
                """
                INSERT INTO decision_position_settlement_evidence(
                    evidence_id, content_hash, account_id, as_of_time,
                    run_id, tick_id, claim_id, fencing_token, tick_version,
                    payload_json, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (evidence_id) DO NOTHING
                """,
                (
                    str(evidence.evidence_id), evidence.content_hash,
                    evidence.account_id, evidence.as_of_time,
                    str(claim.run_id), str(claim.tick_id), claim.claim_id,
                    claim.fencing_token, claim.tick_version,
                    Jsonb(evidence.to_canonical_dict()), self._clock(),
                ),
            )
            restored = self._load_position_settlement_evidence(
                connection,
                evidence.evidence_id,
            )
            if restored != evidence:
                raise DecisionSystemConflict(
                    "Position settlement evidence identity conflict"
                )
            return restored

        return cast(PositionSettlementEvidence, self._run(operation))

    def get_position_settlement_evidence(
        self,
        evidence_id: ArtifactId,
    ) -> PositionSettlementEvidence:
        with self._connect() as connection:
            return self._load_position_settlement_evidence(
                connection,
                evidence_id,
            )

    def record_fill_derived_account_authority(
        self,
        authority: FillDerivedAccountAuthority,
        *,
        claim: ClaimedRuntimeTick,
    ) -> FillDerivedAccountAuthority:
        """Freeze one Fill-derived account view for a Decision as-of scope."""

        def operation(connection: PostgresConnection) -> FillDerivedAccountAuthority:
            self._assert_claim(connection, claim)
            acquire_scope_lock(
                connection,
                namespace="decision-fill-account-authority",
                identity=f"{authority.account_id}:{canonical_datetime(authority.as_of_time)}",
            )
            connection.execute(
                """
                INSERT INTO decision_fill_account_authority(
                    authority_id, content_hash, account_id, as_of_time,
                    fill_ledger_head, fill_ledger_complete, run_id, tick_id,
                    claim_id, fencing_token, tick_version, payload_json, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (authority_id) DO NOTHING
                """,
                (
                    str(authority.authority_id), authority.content_hash,
                    authority.account_id, authority.as_of_time,
                    authority.fill_ledger_head, authority.fill_ledger_complete,
                    str(claim.run_id), str(claim.tick_id), claim.claim_id,
                    claim.fencing_token, claim.tick_version,
                    Jsonb(authority.to_canonical_dict()), self._clock(),
                ),
            )
            restored = self._load_recorded_fill_authority(
                connection,
                account_id=authority.account_id,
                as_of_time=authority.as_of_time,
            )
            if restored != authority:
                raise DecisionSystemConflict(
                    "Decision Fill authority as-of identity conflict"
                )
            return restored

        return cast(FillDerivedAccountAuthority, self._run(operation))

    def get_recorded_fill_derived_account_authority(
        self,
        *,
        account_id: str,
        as_of_time: datetime,
    ) -> FillDerivedAccountAuthority:
        with self._connect() as connection:
            return self._load_recorded_fill_authority(
                connection,
                account_id=account_id,
                as_of_time=as_of_time,
            )

    def get_decision_state_context(
        self,
        summary: DailyDecisionWindowSummary,
    ) -> DecisionStateAuthorityContext:
        self.validate_summary_authority(summary)
        lineage = summary.lineage
        with self._connect() as connection:
            market = connection.execute(
                "SELECT effective_state FROM market_regime_state WHERE state_id = %s",
                (str(lineage.market_state_id),),
            ).fetchone()
            capital = connection.execute(
                "SELECT effective_state FROM capital_state WHERE state_id = %s",
                (str(lineage.capital_state_id),),
            ).fetchone()
            etf_rows = connection.execute(
                """
                SELECT scope_key, effective_state
                FROM etf_rotation_state
                WHERE state_id = ANY(%s)
                ORDER BY scope_key, state_id
                """,
                ([str(item) for item in lineage.etf_state_ids],),
            ).fetchall()
            theme_rows = connection.execute(
                """
                SELECT scope_key, effective_state
                FROM theme_rotation_state
                WHERE state_id = ANY(%s)
                ORDER BY scope_key, state_id
                """,
                ([str(item) for item in lineage.theme_state_ids],),
            ).fetchall()
            availability_rows = connection.execute(
                """
                SELECT available_at
                FROM state_research_stage_authority
                WHERE run_id = %s AND tick_id = %s
                """,
                (str(lineage.continuous_operation_id), str(lineage.runtime_tick_id)),
            ).fetchall()
        if market is None or capital is None or not availability_rows:
            raise DecisionSystemIntegrityError(
                "PostgreSQL Decision State context is incomplete"
            )
        return DecisionStateAuthorityContext(
            market_state=str(market["effective_state"]),
            etf_states=tuple(
                (str(row["scope_key"]), str(row["effective_state"]))
                for row in etf_rows
            ),
            theme_states=tuple(
                (str(row["scope_key"]), str(row["effective_state"]))
                for row in theme_rows
            ),
            capital_state=str(capital["effective_state"]),
            oldest_available_at=min(
                aware_datetime(row["available_at"], label="stage available_at")
                for row in availability_rows
            ),
        )

    def get_market_state(self, state_id: ArtifactId) -> str:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state_hash, effective_state, artifact_json
                FROM market_regime_state
                WHERE state_id = %s
                """,
                (str(state_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(state_id))
        raw = row["artifact_json"]
        payload = raw if isinstance(raw, dict) else json.loads(str(raw))
        if not isinstance(payload, dict) or canonical_hash(payload) != str(
            row["state_hash"]
        ):
            raise DecisionSystemIntegrityError(
                "stored Market State failed canonical verification"
            )
        if str(payload.get("effective_state")) != str(row["effective_state"]):
            raise DecisionSystemIntegrityError(
                "stored Market State projection mismatch"
            )
        return str(row["effective_state"])

    def get_daily_loss(
        self,
        *,
        account_id: str,
        trading_date: object,
        as_of_time: datetime,
    ) -> Decimal | None:
        """No caller-authored PnL is accepted; no current PG daily-loss authority exists."""

        del account_id, trading_date, as_of_time
        return None

    def get_state_stage_authority(
        self,
        *,
        run_id: ArtifactId,
        tick_id: ArtifactId,
    ) -> tuple[dict[str, Any], ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT stage, artifact_id, artifact_hash, data_eligibility,
                       available_at
                FROM state_research_stage_authority
                WHERE run_id = %s AND tick_id = %s
                ORDER BY stage
                """,
                (str(run_id), str(tick_id)),
            ).fetchall()
        return tuple(
            {
                "stage": str(row["stage"]),
                "artifact_id": str(row["artifact_id"]),
                "artifact_hash": str(row["artifact_hash"]),
                "data_eligibility": (
                    None
                    if row["data_eligibility"] is None
                    else str(row["data_eligibility"])
                ),
                "available_at": canonical_datetime(
                    aware_datetime(row["available_at"], label="stage available_at")
                ),
            }
            for row in rows
        )

    def import_replay_artifacts(
        self,
        *,
        replay_session_id: ArtifactId,
        artifacts: tuple[dict[str, Any], ...],
    ) -> tuple[dict[str, Any], ...]:
        """Atomically import an immutable replay bundle into this PG schema."""

        def operation(connection: PostgresConnection) -> tuple[dict[str, Any], ...]:
            acquire_scope_lock(
                connection,
                namespace="decision-replay-import",
                identity=replay_session_id,
            )
            for artifact in artifacts:
                connection.execute(
                    """
                    INSERT INTO decision_replay_import(
                        replay_session_id, artifact_kind, artifact_id,
                        content_hash, payload_json, imported_at
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (replay_session_id, artifact_kind, artifact_id)
                    DO NOTHING
                    """,
                    (
                        str(replay_session_id), artifact["artifact_kind"],
                        artifact["artifact_id"], artifact["content_hash"],
                        Jsonb(artifact["payload"]), self._clock(),
                    ),
                )
            imported = self._load_replay_artifacts(connection, replay_session_id)
            if imported != artifacts:
                raise DecisionSystemConflict("Decision Replay import conflict")
            return imported

        return cast(tuple[dict[str, Any], ...], self._run(operation))

    def get_replay_artifacts(
        self,
        replay_session_id: ArtifactId,
    ) -> tuple[dict[str, Any], ...]:
        with self._connect() as connection:
            return self._load_replay_artifacts(connection, replay_session_id)

    def validate_summary_authority(
        self,
        summary: DailyDecisionWindowSummary,
    ) -> None:
        """Verify every State/Pool/Candidate bundle identity from PostgreSQL."""

        lineage = summary.lineage
        with self._connect() as connection:
            state_receipt = connection.execute(
                """
                SELECT receipt_hash, run_id, tick_id, receipt_json
                FROM state_runtime_receipt
                WHERE receipt_id = %s
                """,
                (str(lineage.state_receipt_id),),
            ).fetchone()
            if state_receipt is None or (
                str(state_receipt["receipt_hash"]) != lineage.state_receipt_hash
                or str(state_receipt["run_id"]) != str(lineage.continuous_operation_id)
                or str(state_receipt["tick_id"]) != str(lineage.runtime_tick_id)
            ):
                raise DecisionSystemIntegrityError(
                    "PostgreSQL State receipt authority mismatch"
                )
            rows = connection.execute(
                """
                SELECT stage, artifact_id, artifact_hash, data_eligibility,
                       available_at
                FROM state_research_stage_authority
                WHERE run_id = %s AND tick_id = %s
                """,
                (
                    str(lineage.continuous_operation_id),
                    str(lineage.runtime_tick_id),
                ),
            ).fetchall()
            by_stage = {str(row["stage"]): row for row in rows}
            stage_order = (
                "OBSERVATION", "MARKET_REGIME", "ETF_ROTATION",
                "THEME_ROTATION", "CAPITAL_STATE", "DYNAMIC_POOL",
                "CANDIDATE", "SIGNAL", "FORECAST",
            )
            if set(by_stage) != set(stage_order):
                raise DecisionSystemIntegrityError(
                    "PostgreSQL State stage authority set mismatch"
                )
            pipeline_id, pipeline_hash = state_research_pipeline_identity(
                run_id=lineage.continuous_operation_id,
                tick_id=lineage.runtime_tick_id,
                as_of_time=summary.as_of_time,
                stages=tuple(
                    (
                        stage,
                        ArtifactId(str(by_stage[stage]["artifact_id"])),
                        str(by_stage[stage]["artifact_hash"]),
                        aware_datetime(
                            by_stage[stage]["available_at"],
                            label=f"{stage} available_at",
                        ),
                    )
                    for stage in stage_order
                ),
            )
            raw_receipt_json = state_receipt["receipt_json"]
            stored_receipt = (
                raw_receipt_json
                if isinstance(raw_receipt_json, dict)
                else json.loads(str(raw_receipt_json))
            )
            receipt_payload = stored_receipt.get("receipt_payload")
            receipt_schema = (
                receipt_payload.get("schema")
                if isinstance(receipt_payload, dict)
                else None
            )
            if receipt_schema == "state_system_runtime_receipt/v2":
                if any(
                    by_stage[stage]["data_eligibility"] is None
                    for stage in stage_order
                ):
                    raise DecisionSystemIntegrityError(
                        "State Runtime v2 eligibility authority is incomplete"
                    )
                expected_stage_references = [
                    {
                        "reference_kind": f"STATE_RESEARCH_{stage}",
                        "artifact_id": str(by_stage[stage]["artifact_id"]),
                        "content_hash": str(by_stage[stage]["artifact_hash"]),
                        "data_eligibility": str(
                            by_stage[stage]["data_eligibility"]
                        ),
                    }
                    for stage in stage_order
                ]
            elif receipt_schema == "state_system_runtime_receipt/v1":
                if any(
                    by_stage[stage]["data_eligibility"] is not None
                    for stage in stage_order
                ) or lineage.data_eligibility.value != "UNQUALIFIED":
                    raise DecisionSystemIntegrityError(
                        "legacy State eligibility authority was inflated"
                    )
                expected_stage_references = [
                    {
                        "reference_kind": f"STATE_RESEARCH_{stage}",
                        "artifact_id": str(by_stage[stage]["artifact_id"]),
                        "content_hash": str(by_stage[stage]["artifact_hash"]),
                    }
                    for stage in stage_order
                ]
            else:
                raise DecisionSystemIntegrityError(
                    "unsupported State Runtime receipt schema"
                )
            if (
                stored_receipt.get("schema") != "state_runtime_child_receipt/v2"
                or not isinstance(receipt_payload, dict)
                or canonical_hash(receipt_payload) != lineage.state_receipt_hash
                or lineage.state_receipt_id
                != ArtifactId(
                    f"state-system-receipt:{lineage.state_receipt_hash[7:]}"
                )
                or stored_receipt.get("child_kind") != "STATE_SYSTEM"
                or stored_receipt.get("child_receipt_id")
                != str(lineage.state_receipt_id)
                or stored_receipt.get("child_receipt_hash")
                != lineage.state_receipt_hash
                or stored_receipt.get("child_artifact_id") != str(pipeline_id)
                or stored_receipt.get("child_artifact_hash") != pipeline_hash
                or receipt_payload.get("pipeline_artifact_id") != str(pipeline_id)
                or receipt_payload.get("pipeline_artifact_hash") != pipeline_hash
                or receipt_payload.get("stage_references")
                != expected_stage_references
                or receipt_payload.get("reason_codes")
                != ["ENTRY_BLOCKED", "STATE_RESEARCH_CHAIN_COMPLETED"]
            ):
                raise DecisionSystemIntegrityError(
                    "PostgreSQL State receipt composition mismatch"
                )
            market = connection.execute(
                "SELECT state_hash FROM market_regime_state WHERE state_id = %s",
                (str(lineage.market_state_id),),
            ).fetchone()
            if market is None:
                raise DecisionSystemIntegrityError(
                    "PostgreSQL Market State authority is missing"
                )
            expected_stage_artifacts = {
                "MARKET_REGIME": (
                    lineage.market_state_id,
                    str(market["state_hash"]),
                ),
                "CANDIDATE": (
                    lineage.candidate_binding_id,
                    lineage.candidate_binding_hash,
                ),
                "SIGNAL": (lineage.signal_bundle_id, lineage.signal_bundle_hash),
                "FORECAST": (
                    lineage.forecast_bundle_id,
                    lineage.forecast_bundle_hash,
                ),
            }
            if receipt_schema == "state_system_runtime_receipt/v2" and any(
                str(by_stage[stage]["data_eligibility"])
                != lineage.data_eligibility.value
                for stage in ("SIGNAL", "FORECAST")
            ):
                raise DecisionSystemIntegrityError(
                    "PostgreSQL Signal/Forecast DataEligibility authority mismatch"
                )
            for stage, (artifact_id, artifact_hash) in expected_stage_artifacts.items():
                row = by_stage.get(stage)
                if row is None or (
                    str(row["artifact_id"]) != str(artifact_id)
                    or str(row["artifact_hash"]) != artifact_hash
                    or aware_datetime(
                        row["available_at"], label=f"{stage} available_at"
                    ) > summary.as_of_time
                ):
                    raise DecisionSystemIntegrityError(
                        f"PostgreSQL {stage} authority mismatch"
                    )
            scoped_state_specs = (
                (
                    "ETF_ROTATION",
                    "etf_rotation_state",
                    "etf_rotation_state_observation",
                    lineage.etf_state_ids,
                ),
                (
                    "THEME_ROTATION",
                    "theme_rotation_state",
                    "theme_rotation_state_observation",
                    lineage.theme_state_ids,
                ),
                (
                    "CAPITAL_STATE",
                    "capital_state",
                    "capital_state_observation",
                    (lineage.capital_state_id,),
                ),
            )
            for stage, state_table, observation_table, expected_ids in scoped_state_specs:
                if not expected_ids:
                    raise DecisionSystemIntegrityError(
                        f"PostgreSQL {stage} lineage is empty"
                    )
                state_rows = connection.execute(  # noqa: S608 - fixed allowlist
                    f"""
                    SELECT state.state_id, state.state_hash, state.scope_key,
                           state.effective_state, state.artifact_json,
                           observation.run_id, observation.tick_id,
                           observation.available_at
                    FROM {state_table} AS state
                    JOIN {observation_table} AS observation
                      ON observation.observation_id = state.observation_id
                    WHERE state.state_id = ANY(%s)
                    """,
                    ([str(item) for item in expected_ids],),
                ).fetchall()
                if {str(row["state_id"]) for row in state_rows} != {
                    str(item) for item in expected_ids
                } or any(
                    str(row["run_id"]) != str(lineage.continuous_operation_id)
                    or str(row["tick_id"]) != str(lineage.runtime_tick_id)
                    or aware_datetime(
                        row["available_at"], label=f"{stage} available_at"
                    ) > summary.as_of_time
                    for row in state_rows
                ):
                    raise DecisionSystemIntegrityError(
                        f"PostgreSQL {stage} State authority mismatch"
                    )
                for state_row in state_rows:
                    raw_state = state_row["artifact_json"]
                    state_payload = (
                        raw_state
                        if isinstance(raw_state, dict)
                        else json.loads(str(raw_state))
                    )
                    if (
                        not isinstance(state_payload, dict)
                        or canonical_hash(state_payload)
                        != str(state_row["state_hash"])
                        or str(state_payload.get("effective_state"))
                        != str(state_row["effective_state"])
                    ):
                        raise DecisionSystemIntegrityError(
                            f"PostgreSQL {stage} canonical State mismatch"
                        )
                expected_scopes = (
                    {
                        item.etf
                        for item in summary.candidates
                        if item.etf is not None
                    }
                    if stage == "ETF_ROTATION"
                    else {
                        item.theme
                        for item in summary.candidates
                        if item.theme is not None
                    }
                    if stage == "THEME_ROTATION"
                    else None
                )
                if expected_scopes is not None and not expected_scopes.issubset(
                    {str(row["scope_key"]) for row in state_rows}
                ):
                    raise DecisionSystemIntegrityError(
                        f"PostgreSQL {stage} Candidate scope mismatch"
                    )
                stage_row = by_stage.get(stage)
                if stage_row is None or aware_datetime(
                    stage_row["available_at"], label=f"{stage} stage available_at"
                ) > summary.as_of_time:
                    raise DecisionSystemIntegrityError(
                        f"PostgreSQL {stage} stage authority mismatch"
                    )
                if len(state_rows) == 1:
                    expected_stage_id = ArtifactId(str(state_rows[0]["state_id"]))
                    expected_stage_hash = str(state_rows[0]["state_hash"])
                elif stage in {"ETF_ROTATION", "THEME_ROTATION"}:
                    expected_stage_id, expected_stage_hash = (
                        scoped_state_stage_bundle_identity(
                            stage=stage,
                            members=tuple(
                                (
                                    ArtifactId(str(item["state_id"])),
                                    str(item["state_hash"]),
                                    str(item["scope_key"]),
                                )
                                for item in state_rows
                            ),
                        )
                    )
                else:
                    raise DecisionSystemIntegrityError(
                        f"PostgreSQL {stage} returned multiple singleton States"
                    )
                if (
                    str(stage_row["artifact_id"]) != str(expected_stage_id)
                    or str(stage_row["artifact_hash"]) != expected_stage_hash
                ):
                    raise DecisionSystemIntegrityError(
                        f"PostgreSQL {stage} identity mismatch"
                    )
            pool = connection.execute(
                """
                SELECT pool_id, pool_hash, run_id, tick_id, available_at
                FROM dynamic_stock_pool
                WHERE pool_id = %s
                """,
                (str(lineage.dynamic_pool_id),),
            ).fetchone()
            if pool is None or (
                str(pool["run_id"]) != str(lineage.continuous_operation_id)
                or str(pool["tick_id"]) != str(lineage.runtime_tick_id)
                or aware_datetime(pool["available_at"], label="Pool available_at")
                > summary.as_of_time
            ):
                raise DecisionSystemIntegrityError(
                    "PostgreSQL Dynamic Pool authority mismatch"
                )
            dynamic_stage = by_stage.get("DYNAMIC_POOL")
            if dynamic_stage is None or (
                str(dynamic_stage["artifact_id"]) != str(lineage.dynamic_pool_id)
                or str(dynamic_stage["artifact_hash"]) != str(pool["pool_hash"])
            ):
                raise DecisionSystemIntegrityError(
                    "PostgreSQL Dynamic Pool stage authority mismatch"
                )
            members = connection.execute(
                """
                SELECT symbol, included
                FROM dynamic_stock_pool_member
                WHERE pool_id = %s
                """,
                (str(lineage.dynamic_pool_id),),
            ).fetchall()
            by_symbol = {str(row["symbol"]): row for row in members}
            for candidate in summary.candidates:
                member = by_symbol.get(candidate.symbol)
                if member is None or member["included"] is not True:
                    raise DecisionSystemIntegrityError(
                        "PostgreSQL Candidate/Pool membership mismatch"
                    )

    def record_manual_observation(self, observation: ManualAccountObservation) -> ManualAccountObservation:
        payload = observation.to_canonical_dict()

        def operation(connection: PostgresConnection) -> ManualAccountObservation:
            acquire_scope_lock(
                connection,
                namespace="manual-account-observation",
                identity=f"{observation.account_id}:{observation.trading_date.isoformat()}",
            )
            replay = _idempotent(
                connection,
                table="manual_account_observation",
                id_column="observation_id",
                key=observation.idempotency_key,
                command_hash=observation.content_hash,
            )
            if replay is not None:
                return self._load_observation(connection, ArtifactId(replay))
            previous = connection.execute(
                """
                SELECT observation_id, revision
                FROM manual_account_observation
                WHERE account_id = %s AND trading_date = %s
                ORDER BY revision DESC LIMIT 1 FOR UPDATE
                """,
                (observation.account_id, observation.trading_date),
            ).fetchone()
            expected_previous = None if previous is None else ArtifactId(str(previous["observation_id"]))
            expected_revision = 1 if previous is None else int(previous["revision"]) + 1
            if observation.previous_observation_id != expected_previous or observation.revision != expected_revision:
                raise DecisionSystemConflict("Manual Account revision CAS rejected")
            connection.execute(
                """
                INSERT INTO manual_account_observation(
                    observation_id, content_hash, account_id, trading_date,
                    as_of_time, total_equity, available_cash, frozen_cash,
                    source, actor, reason, notes, idempotency_key, command_hash,
                    revision, previous_observation_id, payload_json, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    str(observation.observation_id),
                    observation.content_hash,
                    observation.account_id,
                    observation.trading_date,
                    observation.as_of_time,
                    observation.total_equity,
                    observation.available_cash,
                    observation.frozen_cash,
                    observation.source,
                    observation.actor,
                    observation.reason,
                    observation.notes,
                    observation.idempotency_key,
                    observation.content_hash,
                    observation.revision,
                    _id_text(observation.previous_observation_id),
                    Jsonb(payload),
                    observation.created_at,
                ),
            )
            for position in observation.positions:
                connection.execute(
                    """
                    INSERT INTO manual_position_observation(
                        observation_id, symbol, total_quantity,
                        available_quantity, frozen_quantity, average_cost,
                        observed_market_value, notes, payload_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(observation.observation_id),
                        position.symbol,
                        position.total_quantity,
                        position.available_quantity,
                        position.frozen_quantity,
                        position.average_cost,
                        position.observed_market_value,
                        position.notes,
                        Jsonb(position.to_canonical_dict()),
                    ),
                )
            return self._load_observation(connection, observation.observation_id)

        return cast(ManualAccountObservation, self._run(operation))

    def get_manual_observation(self, observation_id: ArtifactId) -> ManualAccountObservation:
        with self._connect() as connection:
            return self._load_observation(connection, observation_id)

    def get_manual_observation_revision(self, *, account_id: str, trading_date: Any, revision: int) -> ManualAccountObservation:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT observation_id FROM manual_account_observation
                WHERE account_id = %s AND trading_date = %s AND revision = %s
                """,
                (account_id, trading_date, revision),
            ).fetchone()
            if row is None:
                raise KeyError(f"{account_id}:{trading_date}:{revision}")
            return self._load_observation(connection, ArtifactId(str(row["observation_id"])))

    def save_reconciliation(
        self,
        report: AccountReconciliationReport,
        *,
        claim: ClaimedRuntimeTick,
    ) -> AccountReconciliationReport:
        payload = report.to_canonical_dict()

        def operation(connection: PostgresConnection) -> AccountReconciliationReport:
            self._assert_claim(connection, claim)
            acquire_scope_lock(
                connection,
                namespace="account-reconciliation",
                identity=f"{report.account_id}:{report.trading_date.isoformat()}",
            )
            replay = _idempotent(
                connection,
                table="account_reconciliation",
                id_column="reconciliation_id",
                key=report.idempotency_key,
                command_hash=report.content_hash,
            )
            if replay is not None:
                return self._load_reconciliation(connection, ArtifactId(replay))
            observation = self._load_observation(connection, report.manual_observation_id)
            tolerance = self._load_reconciliation_tolerance(
                connection,
                report.tolerance_configuration_id,
            )
            if tolerance.configuration_hash != report.tolerance_configuration_hash:
                raise DecisionSystemConflict(
                    "Reconciliation Tolerance authority mismatch"
                )
            if observation.account_id != report.account_id or observation.trading_date != report.trading_date:
                raise DecisionSystemConflict("Reconciliation/Observation lineage mismatch")
            previous = connection.execute(
                """
                SELECT reconciliation_id, revision FROM account_reconciliation
                WHERE account_id = %s AND trading_date = %s
                ORDER BY revision DESC LIMIT 1 FOR UPDATE
                """,
                (report.account_id, report.trading_date),
            ).fetchone()
            expected_previous = None if previous is None else ArtifactId(str(previous["reconciliation_id"]))
            expected_revision = 1 if previous is None else int(previous["revision"]) + 1
            if report.previous_reconciliation_id != expected_previous or report.revision != expected_revision:
                raise DecisionSystemConflict("Reconciliation revision CAS rejected")
            connection.execute(
                """
                INSERT INTO account_reconciliation(
                    reconciliation_id, content_hash, account_id, trading_date,
                    as_of_time, manual_observation_id,
                    position_snapshot_ids_json, fill_ledger_head,
                    fill_ledger_complete, tolerance_configuration_id,
                    tolerance_configuration_hash, status, reason_codes_json,
                    revision, previous_reconciliation_id, idempotency_key,
                    command_hash, run_id, tick_id, claim_id, fencing_token,
                    tick_version, payload_json, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    str(report.reconciliation_id),
                    report.content_hash,
                    report.account_id,
                    report.trading_date,
                    report.as_of_time,
                    str(report.manual_observation_id),
                    Jsonb([str(item) for item in report.position_snapshot_ids]),
                    report.fill_ledger_head,
                    report.fill_ledger_complete,
                    str(report.tolerance_configuration_id),
                    report.tolerance_configuration_hash,
                    report.status.value,
                    Jsonb(list(report.reason_codes)),
                    report.revision,
                    _id_text(report.previous_reconciliation_id),
                    report.idempotency_key,
                    report.content_hash,
                    str(claim.run_id),
                    str(claim.tick_id),
                    claim.claim_id,
                    claim.fencing_token,
                    claim.tick_version,
                    Jsonb(payload),
                    report.created_at,
                ),
            )
            for index, difference in enumerate(report.differences, 1):
                connection.execute(
                    """
                    INSERT INTO reconciliation_difference(
                        reconciliation_id, difference_index, difference_type,
                        symbol, expected_value, observed_value,
                        absolute_difference, reason_code, payload_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(report.reconciliation_id),
                        index,
                        difference.difference_type.value,
                        difference.symbol,
                        difference.expected_value,
                        difference.observed_value,
                        difference.absolute_difference,
                        difference.reason_code,
                        Jsonb(difference.to_canonical_dict()),
                    ),
                )
            return self._load_reconciliation(connection, report.reconciliation_id)

        return cast(AccountReconciliationReport, self._run(operation))

    def get_reconciliation(self, reconciliation_id: ArtifactId) -> AccountReconciliationReport:
        with self._connect() as connection:
            return self._load_reconciliation(connection, reconciliation_id)

    def save_summary(
        self,
        summary: DailyDecisionWindowSummary,
        *,
        claim: ClaimedRuntimeTick,
    ) -> DailyDecisionWindowSummary:
        payload = summary.to_canonical_dict()

        def operation(connection: PostgresConnection) -> DailyDecisionWindowSummary:
            self._assert_claim(connection, claim)
            acquire_scope_lock(
                connection,
                namespace="daily-decision-summary",
                identity=(f"{summary.account_id}:{summary.trading_date.isoformat()}:{summary.strategy_configuration_id}"),
            )
            replay = _idempotent(
                connection,
                table="daily_decision_summary",
                id_column="summary_id",
                key=summary.idempotency_key,
                command_hash=summary.content_hash,
            )
            if replay is not None:
                return self._load_summary(connection, ArtifactId(replay))
            previous = connection.execute(
                """
                SELECT summary_id, revision FROM daily_decision_summary
                WHERE account_id = %s AND trading_date = %s
                  AND strategy_configuration_id = %s
                ORDER BY revision DESC LIMIT 1 FOR UPDATE
                """,
                (
                    summary.account_id,
                    summary.trading_date,
                    str(summary.strategy_configuration_id),
                ),
            ).fetchone()
            expected_previous = None if previous is None else ArtifactId(str(previous["summary_id"]))
            expected_revision = 1 if previous is None else int(previous["revision"]) + 1
            if summary.previous_summary_id != expected_previous or summary.revision != expected_revision:
                raise DecisionSystemConflict("Daily Summary revision CAS rejected")
            observation = self._load_observation(connection, summary.manual_observation_id)
            report = self._load_reconciliation(connection, summary.reconciliation_id)
            if observation.account_id != summary.account_id or report.account_id != summary.account_id:
                raise DecisionSystemConflict("Summary Account lineage mismatch")
            if report.manual_observation_id != observation.observation_id:
                raise DecisionSystemConflict("Summary Account/Reconciliation lineage mismatch")
            connection.execute(
                """
                INSERT INTO daily_decision_summary(
                    summary_id, content_hash, account_id, trading_date,
                    strategy_configuration_id, strategy_configuration_hash,
                    as_of_time, available_at, lifecycle_state, outcome,
                    manual_observation_id, reconciliation_id, revision,
                    previous_summary_id, correction_of_summary_id,
                    idempotency_key, command_hash, run_id, tick_id, claim_id,
                    fencing_token, tick_version, lineage_json, payload_json,
                    created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    str(summary.summary_id),
                    summary.content_hash,
                    summary.account_id,
                    summary.trading_date,
                    str(summary.strategy_configuration_id),
                    summary.strategy_configuration_hash,
                    summary.as_of_time,
                    summary.available_at,
                    summary.lifecycle_state.value,
                    summary.outcome.value,
                    str(summary.manual_observation_id),
                    str(summary.reconciliation_id),
                    summary.revision,
                    _id_text(summary.previous_summary_id),
                    _id_text(summary.correction_of_summary_id),
                    summary.idempotency_key,
                    summary.content_hash,
                    str(claim.run_id),
                    str(claim.tick_id),
                    claim.claim_id,
                    claim.fencing_token,
                    claim.tick_version,
                    Jsonb(summary.lineage.to_canonical_dict()),
                    Jsonb(payload),
                    summary.created_at,
                ),
            )
            for candidate in summary.candidates:
                connection.execute(
                    """
                    INSERT INTO daily_summary_candidate(
                        summary_id, symbol, candidate_rank, candidate_score,
                        current_quantity, research_exposure_ceiling, payload_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(summary.summary_id),
                        candidate.symbol,
                        candidate.candidate_rank,
                        candidate.candidate_score,
                        candidate.current_quantity,
                        candidate.research_exposure_ceiling,
                        Jsonb(candidate.to_canonical_dict()),
                    ),
                )
            return self._load_summary(connection, summary.summary_id)

        try:
            return cast(DailyDecisionWindowSummary, self._run(operation))
        except psycopg.errors.UniqueViolation as exc:
            raise DecisionSystemConflict("Daily Summary Final/identity uniqueness rejected") from exc

    def get_summary(self, summary_id: ArtifactId) -> DailyDecisionWindowSummary:
        with self._connect() as connection:
            return self._load_summary(connection, summary_id)

    def save_research_summary(
        self,
        summary: ResearchDailySummary,
        *,
        claim: ClaimedRuntimeTick,
    ) -> ResearchDailySummary:
        """Append one fenced Research/Shadow Summary revision."""

        payload = summary.to_canonical_dict()

        def operation(connection: PostgresConnection) -> ResearchDailySummary:
            self._assert_claim(connection, claim)
            if summary.run_id != claim.run_id or summary.tick_id != claim.tick_id:
                raise DecisionSystemConflict(
                    "Research Summary Continuous Tick lineage mismatch"
                )
            _verify_research_summary_model_receipts(connection, summary)
            acquire_scope_lock(
                connection,
                namespace="research-daily-summary",
                identity=(
                    f"{summary.run_id}:{summary.tick_id}:"
                    f"{summary.runtime_mode.value}"
                ),
            )
            replay = connection.execute(
                """
                SELECT summary_id, content_hash
                FROM research_daily_summary
                WHERE idempotency_key = %s
                FOR UPDATE
                """,
                (summary.idempotency_key,),
            ).fetchone()
            if replay is not None:
                if str(replay["content_hash"]) != summary.content_hash:
                    raise DecisionSystemConflict(
                        "Research Summary idempotency key conflict"
                    )
                return self._load_research_summary(
                    connection,
                    ArtifactId(str(replay["summary_id"])),
                )
            previous = connection.execute(
                """
                SELECT summary_id, revision, correction_of_summary_id
                FROM research_daily_summary
                WHERE run_id = %s AND tick_id = %s AND runtime_mode = %s
                ORDER BY revision DESC
                LIMIT 1
                FOR UPDATE
                """,
                (
                    str(summary.run_id),
                    str(summary.tick_id),
                    summary.runtime_mode.value,
                ),
            ).fetchone()
            expected_previous = (
                None
                if previous is None
                else ArtifactId(str(previous["summary_id"]))
            )
            expected_revision = 1 if previous is None else int(previous["revision"]) + 1
            if (
                summary.previous_summary_id != expected_previous
                or summary.revision != expected_revision
            ):
                raise DecisionSystemConflict(
                    "Research Summary revision CAS rejected"
                )
            if previous is not None:
                original = previous["correction_of_summary_id"] or previous["summary_id"]
                if summary.correction_of_summary_id != ArtifactId(str(original)):
                    raise DecisionSystemConflict(
                        "Research Summary correction lineage mismatch"
                    )
            connection.execute(
                """
                INSERT INTO research_daily_summary(
                    summary_id, content_hash, runtime_mode, run_id, tick_id,
                    trading_date, decision_time, provider_profile_id,
                    source_manifest_id, source_manifest_hash, dataset_id,
                    dataset_hash, feature_bundle_id, feature_bundle_hash,
                    data_eligibility, evidence_ceiling, outcome, revision,
                    previous_summary_id, correction_of_summary_id,
                    idempotency_key, run_claim_id, fencing_token, tick_version,
                    payload_json, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    str(summary.summary_id),
                    summary.content_hash,
                    summary.runtime_mode.value,
                    str(summary.run_id),
                    str(summary.tick_id),
                    summary.trading_date,
                    summary.decision_time,
                    summary.provider_profile_id,
                    str(summary.source_manifest.artifact_id),
                    summary.source_manifest.content_hash,
                    str(summary.dataset.artifact_id),
                    summary.dataset.content_hash,
                    str(summary.feature_bundle.artifact_id),
                    summary.feature_bundle.content_hash,
                    summary.data_eligibility.value,
                    summary.evidence_ceiling.value,
                    summary.outcome.value,
                    summary.revision,
                    _id_text(summary.previous_summary_id),
                    _id_text(summary.correction_of_summary_id),
                    summary.idempotency_key,
                    claim.claim_id,
                    claim.fencing_token,
                    claim.tick_version,
                    Jsonb(payload),
                    summary.created_at,
                ),
            )
            for index, stage in enumerate(summary.stages, start=1):
                output = stage.output_reference
                selection = stage.selection_receipt
                connection.execute(
                    """
                    INSERT INTO research_summary_stage(
                        summary_id, stage, stage_index, evidence_id,
                        evidence_hash, status, output_artifact_id,
                        output_artifact_hash, selection_receipt_id,
                        selection_receipt_hash, available_at,
                        stage_completed_at, result,
                        data_eligibility, evidence_ceiling, payload_json
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    """,
                    (
                        str(summary.summary_id),
                        stage.stage.value,
                        index,
                        str(stage.evidence_id),
                        stage.evidence_hash,
                        stage.status.value,
                        None if output is None else str(output.artifact_id),
                        None if output is None else output.content_hash,
                        None if selection is None else str(selection.artifact_id),
                        None if selection is None else selection.content_hash,
                        stage.evidence_available_at,
                        stage.stage_completed_at,
                        stage.result.value,
                        stage.data_eligibility.value,
                        stage.evidence_ceiling.value,
                        Jsonb(stage.to_canonical_dict()),
                    ),
                )
            return self._load_research_summary(connection, summary.summary_id)

        return cast(ResearchDailySummary, self._run(operation))

    def get_research_summary(
        self, summary_id: ArtifactId
    ) -> ResearchDailySummary:
        with self._connect() as connection:
            return self._load_research_summary(connection, summary_id)

    def get_research_summary_for_tick(
        self,
        *,
        run_id: ArtifactId,
        tick_id: ArtifactId,
        runtime_mode: RuntimeAuthorityMode,
    ) -> ResearchDailySummary:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT summary_id
                FROM research_daily_summary
                WHERE run_id = %s AND tick_id = %s AND runtime_mode = %s
                ORDER BY revision DESC
                LIMIT 1
                """,
                (str(run_id), str(tick_id), runtime_mode.value),
            ).fetchone()
            if row is None:
                raise KeyError(f"{run_id}:{tick_id}:{runtime_mode.value}")
            return self._load_research_summary(
                connection,
                ArtifactId(str(row["summary_id"])),
            )

    def save_proposal(
        self,
        proposal: ResearchPortfolioProposal,
        *,
        claim: ClaimedRuntimeTick,
    ) -> ResearchPortfolioProposal:
        payload = proposal.to_canonical_dict()

        def operation(connection: PostgresConnection) -> ResearchPortfolioProposal:
            self._assert_claim(connection, claim)
            replay = _idempotent(
                connection,
                table="research_portfolio_proposal",
                id_column="proposal_id",
                key=proposal.idempotency_key,
                command_hash=proposal.content_hash,
            )
            if replay is not None:
                return self._load_proposal(connection, ArtifactId(replay))
            summary = self._load_summary(connection, proposal.summary_id)
            observation = self._load_observation(connection, proposal.manual_observation_id)
            report = self._load_reconciliation(connection, proposal.reconciliation_id)
            configuration = self._load_risk_configuration(
                connection,
                proposal.risk_configuration_id,
            )
            if (
                summary.account_id != proposal.account_id
                or observation.account_id != proposal.account_id
                or report.account_id != proposal.account_id
                or configuration.configuration_hash
                != proposal.risk_configuration_hash
            ):
                raise DecisionSystemConflict("Proposal Account lineage mismatch")
            connection.execute(
                """
                INSERT INTO research_portfolio_proposal(
                    proposal_id, content_hash, account_id, trading_date,
                    as_of_time, summary_id, manual_observation_id,
                    reconciliation_id, risk_configuration_id,
                    risk_configuration_hash, status, reason_codes_json,
                    idempotency_key, command_hash, run_id, tick_id, claim_id,
                    fencing_token, tick_version, payload_json, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    str(proposal.proposal_id),
                    proposal.content_hash,
                    proposal.account_id,
                    proposal.trading_date,
                    proposal.as_of_time,
                    str(proposal.summary_id),
                    str(proposal.manual_observation_id),
                    str(proposal.reconciliation_id),
                    str(proposal.risk_configuration_id),
                    proposal.risk_configuration_hash,
                    proposal.status.value,
                    Jsonb(list(proposal.reason_codes)),
                    proposal.idempotency_key,
                    proposal.content_hash,
                    str(claim.run_id),
                    str(claim.tick_id),
                    claim.claim_id,
                    claim.fencing_token,
                    claim.tick_version,
                    Jsonb(payload),
                    proposal.created_at,
                ),
            )
            for line in proposal.lines:
                connection.execute(
                    """
                    INSERT INTO research_portfolio_line(
                        proposal_id, symbol, current_weight,
                        proposed_research_weight, weight_delta,
                        research_amount, payload_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(proposal.proposal_id),
                        line.symbol,
                        line.current_weight,
                        line.proposed_research_weight,
                        line.weight_delta,
                        line.research_amount,
                        Jsonb(line.to_canonical_dict()),
                    ),
                )
            return self._load_proposal(connection, proposal.proposal_id)

        return cast(ResearchPortfolioProposal, self._run(operation))

    def get_proposal(self, proposal_id: ArtifactId) -> ResearchPortfolioProposal:
        with self._connect() as connection:
            return self._load_proposal(connection, proposal_id)

    def save_risk_decision(
        self,
        decision: IndependentRiskDecision,
        *,
        claim: ClaimedRuntimeTick,
    ) -> IndependentRiskDecision:
        payload = decision.to_canonical_dict()

        def operation(connection: PostgresConnection) -> IndependentRiskDecision:
            self._assert_claim(connection, claim)
            replay = _idempotent(
                connection,
                table="independent_risk_decision",
                id_column="risk_decision_id",
                key=decision.idempotency_key,
                command_hash=decision.content_hash,
            )
            if replay is not None:
                return self._load_risk(connection, ArtifactId(replay))
            proposal = self._load_proposal(connection, decision.proposal_id)
            configuration = self._load_risk_configuration(
                connection,
                decision.risk_configuration_id,
            )
            if proposal.account_id != decision.account_id or proposal.trading_date != decision.trading_date:
                raise DecisionSystemConflict("Independent Risk Proposal lineage mismatch")
            if (
                proposal.risk_configuration_id != decision.risk_configuration_id
                or proposal.risk_configuration_hash != decision.risk_configuration_hash
                or configuration.configuration_hash
                != decision.risk_configuration_hash
            ):
                raise DecisionSystemConflict("Independent Risk Configuration lineage mismatch")
            connection.execute(
                """
                INSERT INTO independent_risk_decision(
                    risk_decision_id, content_hash, proposal_id, account_id,
                    trading_date, as_of_time, result,
                    approved_research_weight, reason_codes_json,
                    risk_configuration_id, risk_configuration_hash,
                    idempotency_key, command_hash, run_id, tick_id, claim_id,
                    fencing_token, tick_version, payload_json, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    str(decision.risk_decision_id),
                    decision.content_hash,
                    str(decision.proposal_id),
                    decision.account_id,
                    decision.trading_date,
                    decision.as_of_time,
                    decision.result.value,
                    decision.approved_research_weight,
                    Jsonb(list(decision.reason_codes)),
                    str(decision.risk_configuration_id),
                    decision.risk_configuration_hash,
                    decision.idempotency_key,
                    decision.content_hash,
                    str(claim.run_id),
                    str(claim.tick_id),
                    claim.claim_id,
                    claim.fencing_token,
                    claim.tick_version,
                    Jsonb(payload),
                    decision.created_at,
                ),
            )
            return self._load_risk(connection, decision.risk_decision_id)

        return cast(IndependentRiskDecision, self._run(operation))

    def get_risk_decision(self, risk_decision_id: ArtifactId) -> IndependentRiskDecision:
        with self._connect() as connection:
            return self._load_risk(connection, risk_decision_id)

    def save_runtime_receipt(
        self,
        receipt: DecisionRuntimeReceipt,
        *,
        claim: ClaimedRuntimeTick,
    ) -> DecisionRuntimeReceipt:
        payload = receipt.to_canonical_dict()

        def operation(connection: PostgresConnection) -> DecisionRuntimeReceipt:
            self._assert_claim(connection, claim)
            if (
                receipt.run_id != claim.run_id
                or receipt.tick_id != claim.tick_id
                or receipt.claim_id != claim.claim_id
                or receipt.fencing_token != claim.fencing_token
                or receipt.tick_version != claim.tick_version
                or receipt.lease_expires_at != claim.lease_expires_at
            ):
                raise DecisionSystemConflict("Decision receipt/fence lineage mismatch")
            prior = connection.execute(
                """
                SELECT receipt_id, receipt_hash FROM decision_runtime_receipt
                WHERE run_id = %s AND tick_id = %s FOR UPDATE
                """,
                (str(receipt.run_id), str(receipt.tick_id)),
            ).fetchone()
            if prior is not None:
                if str(prior["receipt_hash"]) != receipt.receipt_hash:
                    raise DecisionSystemConflict("Decision Runtime Tick identity conflict")
                return self._load_runtime_receipt(connection, ArtifactId(str(prior["receipt_id"])))
            connection.execute(
                """
                INSERT INTO decision_runtime_receipt(
                    receipt_id, receipt_hash, run_id, tick_id, claim_id,
                    fencing_token, tick_version, lease_expires_at, state_receipt_id,
                    state_receipt_hash, reconciliation_id, summary_id,
                    proposal_id, risk_decision_id, status,
                    stage_receipts_json, payload_json, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    str(receipt.receipt_id),
                    receipt.receipt_hash,
                    str(receipt.run_id),
                    str(receipt.tick_id),
                    receipt.claim_id,
                    receipt.fencing_token,
                    receipt.tick_version,
                    receipt.lease_expires_at,
                    str(receipt.state_receipt_id),
                    receipt.state_receipt_hash,
                    _id_text(receipt.reconciliation_id),
                    _id_text(receipt.summary_id),
                    _id_text(receipt.proposal_id),
                    _id_text(receipt.risk_decision_id),
                    receipt.status,
                    Jsonb([item.to_canonical_dict() for item in receipt.stage_receipts]),
                    Jsonb(payload),
                    receipt.created_at,
                ),
            )
            return self._load_runtime_receipt(connection, receipt.receipt_id)

        return cast("DecisionRuntimeReceipt", self._run(operation))

    def get_runtime_receipt(
        self,
        *,
        run_id: ArtifactId,
        tick_id: ArtifactId,
    ) -> DecisionRuntimeReceipt:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT receipt_id FROM decision_runtime_receipt
                WHERE run_id = %s AND tick_id = %s
                """,
                (str(run_id), str(tick_id)),
            ).fetchone()
            if row is None:
                raise KeyError(f"{run_id}:{tick_id}")
            return self._load_runtime_receipt(connection, ArtifactId(str(row["receipt_id"])))

    def authority_counts(self) -> dict[str, int]:
        tables = (
            "manual_account_observation",
            "manual_position_observation",
            "account_reconciliation",
            "reconciliation_difference",
            "daily_decision_summary",
            "daily_summary_candidate",
            "research_portfolio_proposal",
            "research_portfolio_line",
            "independent_risk_decision",
            "decision_runtime_receipt",
            "research_daily_summary",
            "research_summary_stage",
            "reconciliation_tolerance_configuration",
            "decision_risk_configuration",
            "decision_position_settlement_evidence",
            "decision_fill_account_authority",
        )
        with self._connect() as connection:
            counts: dict[str, int] = {}
            for table in tables:
                row = connection.execute(
                    f"SELECT count(*) AS row_count FROM {table}"  # noqa: S608 - fixed internal allowlist
                ).fetchone()
                if row is None:
                    raise DecisionSystemIntegrityError(f"count query returned no row for {table}")
                counts[table] = int(row["row_count"])
            return counts

    def _run(self, operation: Callable[[PostgresConnection], _T]) -> _T:
        def with_dict_rows(connection: Any) -> _T:
            previous = connection.row_factory
            connection.row_factory = dict_row
            try:
                return operation(cast(PostgresConnection, connection))
            finally:
                connection.row_factory = previous

        try:
            return cast(_T, self._postgres_factory.run_transaction(with_dict_rows))
        except psycopg.errors.UniqueViolation as exc:
            raise DecisionSystemConflict("Decision System uniqueness/CAS rejected") from exc

    def _assert_claim(self, connection: PostgresConnection, claim: ClaimedRuntimeTick) -> None:
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
            or str(row["status"]) != "IN_PROGRESS"
            or str(row["claim_id"]) != claim.claim_id
            or int(row["fencing_token"]) != claim.fencing_token
            or int(row["version"]) != claim.tick_version
            or row["lease_expires_at"] is None
            or row["lease_expires_at"] <= now
        ):
            raise DecisionSystemConflict("stale Continuous Tick claim/fence cannot write Decision System")

    def _load_reconciliation_tolerance(
        self,
        connection: PostgresConnection,
        configuration_id: ArtifactId,
    ) -> ReconciliationTolerance:
        row = connection.execute(
            """
            SELECT payload_json
            FROM reconciliation_tolerance_configuration
            WHERE configuration_id = %s
            """,
            (str(configuration_id),),
        ).fetchone()
        if row is None:
            raise KeyError(str(configuration_id))
        payload = row["payload_json"]
        if not isinstance(payload, dict):
            raise DecisionSystemIntegrityError(
                "stored Reconciliation Tolerance is not an object"
            )
        return ReconciliationTolerance.from_canonical_dict(payload)

    def _load_risk_configuration(
        self,
        connection: PostgresConnection,
        configuration_id: ArtifactId,
    ) -> DecisionRiskConfiguration:
        row = connection.execute(
            """
            SELECT payload_json
            FROM decision_risk_configuration
            WHERE configuration_id = %s
            """,
            (str(configuration_id),),
        ).fetchone()
        if row is None:
            raise KeyError(str(configuration_id))
        payload = row["payload_json"]
        if not isinstance(payload, dict):
            raise DecisionSystemIntegrityError(
                "stored Decision Risk Configuration is not an object"
            )
        return DecisionRiskConfiguration.from_canonical_dict(payload)

    def _load_recorded_fill_authority(
        self,
        connection: PostgresConnection,
        *,
        account_id: str,
        as_of_time: datetime,
    ) -> FillDerivedAccountAuthority:
        row = connection.execute(
            """
            SELECT payload_json
            FROM decision_fill_account_authority
            WHERE account_id = %s AND as_of_time = %s
            """,
            (account_id, as_of_time),
        ).fetchone()
        if row is None:
            raise KeyError(
                f"{account_id}:{canonical_datetime(as_of_time)}"
            )
        payload = row["payload_json"]
        if not isinstance(payload, dict):
            raise DecisionSystemIntegrityError(
                "stored Decision Fill authority is not an object"
            )
        try:
            return FillDerivedAccountAuthority.from_canonical_dict(payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise DecisionSystemIntegrityError(
                "stored Decision Fill authority failed canonical verification"
            ) from exc

    def _load_position_settlement_evidence(
        self,
        connection: PostgresConnection,
        evidence_id: ArtifactId,
    ) -> PositionSettlementEvidence:
        row = connection.execute(
            """
            SELECT payload_json
            FROM decision_position_settlement_evidence
            WHERE evidence_id = %s
            """,
            (str(evidence_id),),
        ).fetchone()
        if row is None:
            raise KeyError(str(evidence_id))
        payload = row["payload_json"]
        if not isinstance(payload, dict):
            raise DecisionSystemIntegrityError(
                "stored Position settlement evidence is not an object"
            )
        try:
            return PositionSettlementEvidence.from_canonical_dict(payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise DecisionSystemIntegrityError(
                "stored Position settlement evidence failed canonical verification"
            ) from exc

    def _load_replay_artifacts(
        self,
        connection: PostgresConnection,
        replay_session_id: ArtifactId,
    ) -> tuple[dict[str, Any], ...]:
        rows = connection.execute(
            """
            SELECT artifact_kind, artifact_id, content_hash, payload_json
            FROM decision_replay_import
            WHERE replay_session_id = %s
            ORDER BY artifact_kind, artifact_id
            """,
            (str(replay_session_id),),
        ).fetchall()
        artifacts: list[dict[str, Any]] = []
        for row in rows:
            payload = row["payload_json"]
            if not isinstance(payload, dict):
                raise DecisionSystemIntegrityError(
                    "stored Decision Replay payload is not an object"
                )
            artifacts.append(
                {
                    "artifact_kind": str(row["artifact_kind"]),
                    "artifact_id": str(row["artifact_id"]),
                    "content_hash": str(row["content_hash"]),
                    "payload": payload,
                }
            )
        return tuple(artifacts)

    def _load_observation(self, connection: PostgresConnection, observation_id: ArtifactId) -> ManualAccountObservation:
        return _load_payload(
            connection,
            "manual_account_observation",
            "observation_id",
            observation_id,
            ManualAccountObservation.from_canonical_dict,
        )

    def _load_reconciliation(self, connection: PostgresConnection, reconciliation_id: ArtifactId) -> AccountReconciliationReport:
        return _load_payload(
            connection,
            "account_reconciliation",
            "reconciliation_id",
            reconciliation_id,
            AccountReconciliationReport.from_canonical_dict,
        )

    def _load_summary(self, connection: PostgresConnection, summary_id: ArtifactId) -> DailyDecisionWindowSummary:
        return _load_payload(
            connection,
            "daily_decision_summary",
            "summary_id",
            summary_id,
            DailyDecisionWindowSummary.from_canonical_dict,
        )

    def _load_research_summary(
        self,
        connection: PostgresConnection,
        summary_id: ArtifactId,
    ) -> ResearchDailySummary:
        row = connection.execute(
            """
            SELECT payload_json
            FROM research_daily_summary
            WHERE summary_id = %s
            """,
            (str(summary_id),),
        ).fetchone()
        if row is None:
            raise KeyError(str(summary_id))
        payload = row["payload_json"]
        if not isinstance(payload, dict):
            raise DecisionSystemIntegrityError(
                "stored Research Summary is not an object"
            )
        try:
            return ResearchDailySummary.from_canonical_dict(payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise DecisionSystemIntegrityError(
                "stored Research Summary failed canonical verification"
            ) from exc

    def _load_proposal(self, connection: PostgresConnection, proposal_id: ArtifactId) -> ResearchPortfolioProposal:
        return _load_payload(
            connection,
            "research_portfolio_proposal",
            "proposal_id",
            proposal_id,
            ResearchPortfolioProposal.from_canonical_dict,
        )

    def _load_risk(self, connection: PostgresConnection, risk_id: ArtifactId) -> IndependentRiskDecision:
        return _load_payload(
            connection,
            "independent_risk_decision",
            "risk_decision_id",
            risk_id,
            IndependentRiskDecision.from_canonical_dict,
        )

    def _load_runtime_receipt(self, connection: PostgresConnection, receipt_id: ArtifactId) -> DecisionRuntimeReceipt:
        from market_regime_alpha.application.decision_system.runtime import (
            DecisionRuntimeReceipt,
        )

        row = connection.execute(
            "SELECT payload_json FROM decision_runtime_receipt WHERE receipt_id = %s",
            (str(receipt_id),),
        ).fetchone()
        if row is None:
            raise KeyError(str(receipt_id))
        raw = row["payload_json"]
        payload = raw if isinstance(raw, dict) else json.loads(str(raw))
        if not isinstance(payload, dict):
            raise DecisionSystemIntegrityError("Decision Runtime payload is not an object")
        try:
            return DecisionRuntimeReceipt.from_canonical_dict(payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise DecisionSystemIntegrityError("stored Decision Runtime receipt failed canonical verification") from exc


def _verify_research_summary_model_receipts(
    connection: PostgresConnection,
    summary: ResearchDailySummary,
) -> None:
    """Reload Governance authority instead of trusting caller references."""

    configurations = {
        (item.artifact_id, item.content_hash)
        for item in summary.configuration_references
    }
    for stage in summary.stages:
        reference = stage.selection_receipt
        if reference is None:
            continue
        if reference.reference_kind != "MODEL_SELECTION_RECEIPT":
            raise DecisionSystemConflict(
                "Research Summary Selection Receipt kind mismatch"
            )
        expected_slot = GOVERNED_RESEARCH_MODEL_SLOTS.get(stage.stage)
        if expected_slot is None:
            raise DecisionSystemConflict(
                "deterministic Research Stage cannot claim a Model Selection"
            )
        row = connection.execute(
            """
            SELECT receipt_hash, request_json, payload_json
            FROM model_selection_receipt
            WHERE receipt_id = %s
            """,
            (str(reference.artifact_id),),
        ).fetchone()
        if row is None:
            raise DecisionSystemConflict(
                "Research Summary Selection Receipt does not exist"
            )
        request_payload = row["request_json"]
        receipt_payload = row["payload_json"]
        if not isinstance(request_payload, dict) or not isinstance(
            receipt_payload, dict
        ):
            raise DecisionSystemIntegrityError(
                "stored Model Selection authority is not an object"
            )
        try:
            request = ModelSelectionRequest.from_canonical_dict(request_payload)
            receipt = ModelSelectionReceipt.from_canonical_dict(receipt_payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise DecisionSystemIntegrityError(
                "stored Model Selection authority failed canonical verification"
            ) from exc
        expected_status = (
            SelectionStatus.REJECTED
            if stage.status
            is ResearchStageStatus.MODEL_NOT_QUALIFIED_FOR_MODE
            else SelectionStatus.SELECTED
        )
        runtime_configuration = request.runtime_lineage.configuration
        if (
            str(row["receipt_hash"]) != reference.content_hash
            or receipt.receipt_id != reference.artifact_id
            or receipt.receipt_hash != reference.content_hash
            or receipt.request_hash != request.request_hash
            or receipt.purpose is not summary.runtime_mode.runtime_purpose
            or request.purpose is not summary.runtime_mode.runtime_purpose
            or receipt.model_slot != expected_slot
            or request.model_slot != expected_slot
            or receipt.status is not expected_status
            or receipt.runtime_lineage_hash
            != request.runtime_lineage.runtime_lineage_hash
            or request.runtime_lineage.dataset.artifact_id
            != summary.dataset.artifact_id
            or request.runtime_lineage.dataset.content_hash
            != summary.dataset.content_hash
            or (
                runtime_configuration.artifact_id,
                runtime_configuration.content_hash,
            )
            not in configurations
            or receipt.selected_at > summary.decision_time
        ):
            raise DecisionSystemConflict(
                "Research Summary Model Selection authority mismatch"
            )


def _idempotent(
    connection: PostgresConnection,
    *,
    table: str,
    id_column: str,
    key: str,
    command_hash: str,
) -> str | None:
    allowed = {
        ("manual_account_observation", "observation_id"),
        ("account_reconciliation", "reconciliation_id"),
        ("daily_decision_summary", "summary_id"),
        ("research_portfolio_proposal", "proposal_id"),
        ("independent_risk_decision", "risk_decision_id"),
    }
    if (table, id_column) not in allowed:
        raise AssertionError("unapproved Decision idempotency table")
    row = connection.execute(
        f"SELECT {id_column}, command_hash FROM {table} "  # noqa: S608 - fixed allowlist
        "WHERE idempotency_key = %s FOR UPDATE",
        (key,),
    ).fetchone()
    if row is None:
        return None
    if str(row["command_hash"]) != command_hash:
        raise DecisionSystemConflict("Decision idempotency key conflict")
    return str(row[id_column])


def _load_payload(
    connection: PostgresConnection,
    table: str,
    id_column: str,
    identity: ArtifactId,
    restore: Callable[[dict[str, Any]], _T],
) -> _T:
    allowed = {
        ("manual_account_observation", "observation_id"),
        ("account_reconciliation", "reconciliation_id"),
        ("daily_decision_summary", "summary_id"),
        ("research_portfolio_proposal", "proposal_id"),
        ("independent_risk_decision", "risk_decision_id"),
    }
    if (table, id_column) not in allowed:
        raise AssertionError("unapproved Decision payload table")
    row = connection.execute(
        f"SELECT payload_json FROM {table} WHERE {id_column} = %s",  # noqa: S608 - fixed allowlist
        (str(identity),),
    ).fetchone()
    if row is None:
        raise KeyError(str(identity))
    raw = row["payload_json"]
    payload = raw if isinstance(raw, dict) else json.loads(str(raw))
    if not isinstance(payload, dict):
        raise DecisionSystemIntegrityError("Decision payload is not an object")
    try:
        return restore(payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise DecisionSystemIntegrityError(f"stored {table} payload failed canonical verification") from exc


def _id_text(value: ArtifactId | None) -> str | None:
    return None if value is None else str(value)


__all__ = [
    "DecisionSystemConflict",
    "DecisionSystemIntegrityError",
    "PostgresDecisionSystemRepository",
]
