"""Native PostgreSQL authority for the research/manual decision closure."""

from __future__ import annotations

from datetime import datetime, timezone
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
    IndependentRiskDecision,
    ManualAccountObservation,
    ResearchPortfolioProposal,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.native_repository import (
    NativePostgresRepository,
    PostgresConnection,
    acquire_scope_lock,
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
            if (
                summary.account_id != proposal.account_id
                or observation.account_id != proposal.account_id
                or report.account_id != proposal.account_id
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
            if proposal.account_id != decision.account_id or proposal.trading_date != decision.trading_date:
                raise DecisionSystemConflict("Independent Risk Proposal lineage mismatch")
            if (
                proposal.risk_configuration_id != decision.risk_configuration_id
                or proposal.risk_configuration_hash != decision.risk_configuration_hash
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
                    fencing_token, tick_version, state_receipt_id,
                    state_receipt_hash, reconciliation_id, summary_id,
                    proposal_id, risk_decision_id, status,
                    stage_receipts_json, payload_json, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
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
