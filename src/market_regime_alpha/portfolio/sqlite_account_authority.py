"""SQLite adapter for atomic complete-account Portfolio/Risk assessments."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from market_regime_alpha.core.identity import (
    ArtifactId,
    PortfolioDecisionId,
    RiskDecisionId,
)
from market_regime_alpha.portfolio.account_authority import (
    AuthoritativeAccountPortfolioSnapshot,
    CompleteAccountPortfolioDecision,
    CompleteAccountRiskDecision,
    CompleteAccountRiskService,
)


_MIGRATION_ROOT = Path(__file__).resolve().parent / "migrations"
COMPLETE_ACCOUNT_RISK_UP_MIGRATION = (
    _MIGRATION_ROOT / "005_complete_account_portfolio_risk_up.sql"
)
COMPLETE_ACCOUNT_RISK_DOWN_MIGRATION = (
    _MIGRATION_ROOT / "005_complete_account_portfolio_risk_down.sql"
)


class SQLiteCompleteAccountPortfolioRiskRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                COMPLETE_ACCOUNT_RISK_UP_MIGRATION.read_text(encoding="utf-8")
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
        finally:
            connection.close()

    def save_assessment(
        self,
        account_snapshot: AuthoritativeAccountPortfolioSnapshot,
        portfolio: CompleteAccountPortfolioDecision,
        risk: CompleteAccountRiskDecision,
        *,
        idempotency_key: str,
        command_hash: str,
    ) -> tuple[CompleteAccountPortfolioDecision, CompleteAccountRiskDecision]:
        _key(idempotency_key)
        if portfolio.account_snapshot != account_snapshot:
            raise ValueError("PortfolioDecision account snapshot mismatch")
        expected_risk = CompleteAccountRiskService().assess(
            portfolio,
            actor=risk.actor,
            reason=risk.reason,
            started_at=risk.started_at,
            completed_at=risk.completed_at,
        )
        if expected_risk != risk:
            raise ValueError("complete-account Risk cannot bypass validation")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                command = connection.execute(
                    """
                    SELECT * FROM complete_account_risk_commands
                    WHERE idempotency_key = ?
                    """,
                    (idempotency_key,),
                ).fetchone()
                if command is not None:
                    if (
                        command["command_hash"] != command_hash
                        or command["account_snapshot_id"]
                        != str(account_snapshot.snapshot_id)
                        or command["portfolio_decision_id"]
                        != str(portfolio.decision_id)
                        or command["risk_decision_id"]
                        != str(risk.risk_decision_id)
                    ):
                        raise ValueError(
                            "idempotency key reused for different complete-account command"
                        )
                    stored_portfolio = _load_portfolio(
                        connection, portfolio.decision_id
                    )
                    stored_risk = _load_risk(connection, risk.risk_decision_id)
                    connection.commit()
                    return stored_portfolio, stored_risk
                _insert_snapshot(connection, account_snapshot)
                _insert_portfolio(connection, portfolio)
                _insert_risk(connection, risk)
                connection.execute(
                    """
                    INSERT INTO complete_account_risk_commands(
                        idempotency_key, command_hash, account_snapshot_id,
                        portfolio_decision_id, risk_decision_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        idempotency_key,
                        command_hash,
                        str(account_snapshot.snapshot_id),
                        str(portfolio.decision_id),
                        str(risk.risk_decision_id),
                        datetime.now(UTC).isoformat(),
                    ),
                )
                connection.commit()
                return portfolio, risk
            except Exception:
                connection.rollback()
                raise

    def get_account_snapshot(
        self, snapshot_id: str
    ) -> AuthoritativeAccountPortfolioSnapshot:
        with self._connect() as connection:
            return _load_snapshot(connection, ArtifactId(snapshot_id))

    def get_complete_account_portfolio(
        self, decision_id: PortfolioDecisionId
    ) -> CompleteAccountPortfolioDecision:
        with self._connect() as connection:
            return _load_portfolio(connection, decision_id)

    def get_complete_account_risk(
        self, risk_decision_id: RiskDecisionId
    ) -> CompleteAccountRiskDecision:
        with self._connect() as connection:
            return _load_risk(connection, risk_decision_id)


def _insert_snapshot(
    connection: sqlite3.Connection,
    snapshot: AuthoritativeAccountPortfolioSnapshot,
) -> None:
    existing = connection.execute(
        """
        SELECT snapshot_json FROM authoritative_account_portfolio_snapshots
        WHERE account_snapshot_id = ?
        """,
        (str(snapshot.snapshot_id),),
    ).fetchone()
    if existing is not None:
        stored = AuthoritativeAccountPortfolioSnapshot.from_canonical_dict(
            _object_json(str(existing["snapshot_json"]))
        )
        if stored != snapshot:
            raise ValueError("account Portfolio snapshot identity conflict")
        return
    connection.execute(
        """
        INSERT INTO authoritative_account_portfolio_snapshots(
            account_snapshot_id, account_id, as_of, source_reference,
            completeness, reconciliation_state, version, content_hash,
            snapshot_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(snapshot.snapshot_id),
            snapshot.account_id,
            snapshot.as_of.isoformat(),
            snapshot.source_reference,
            snapshot.completeness.value,
            snapshot.reconciliation_state.value,
            snapshot.version,
            snapshot.content_hash,
            _json(snapshot.to_canonical_dict()),
        ),
    )


def _insert_portfolio(
    connection: sqlite3.Connection,
    portfolio: CompleteAccountPortfolioDecision,
) -> None:
    existing = connection.execute(
        """
        SELECT decision_json FROM complete_account_portfolio_decisions
        WHERE portfolio_decision_id = ?
        """,
        (str(portfolio.decision_id),),
    ).fetchone()
    if existing is not None:
        stored = CompleteAccountPortfolioDecision.from_canonical_dict(
            _object_json(str(existing["decision_json"]))
        )
        if stored != portfolio:
            raise ValueError("complete-account PortfolioDecision identity conflict")
        return
    connection.execute(
        """
        INSERT INTO complete_account_portfolio_decisions(
            portfolio_decision_id, account_snapshot_id,
            post_trade_snapshot_id, post_trade_content_hash,
            configuration_id, configuration_hash, mode, version,
            decision_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (
            str(portfolio.decision_id),
            str(portfolio.account_snapshot.snapshot_id),
            str(portfolio.post_trade.snapshot_id),
            portfolio.post_trade.content_hash,
            str(portfolio.configuration.configuration_id),
            portfolio.configuration.configuration_hash,
            portfolio.mode.value,
            _json(portfolio.to_canonical_dict()),
            portfolio.created_at.isoformat(),
        ),
    )


def _insert_risk(
    connection: sqlite3.Connection, risk: CompleteAccountRiskDecision
) -> None:
    existing = connection.execute(
        """
        SELECT decision_json FROM complete_account_risk_decisions
        WHERE risk_decision_id = ? OR portfolio_decision_id = ?
        """,
        (str(risk.risk_decision_id), str(risk.portfolio_decision_id)),
    ).fetchone()
    if existing is not None:
        stored = CompleteAccountRiskDecision.from_canonical_dict(
            _object_json(str(existing["decision_json"]))
        )
        if stored != risk:
            raise ValueError("complete-account RiskDecision identity conflict")
        return
    connection.execute(
        """
        INSERT INTO complete_account_risk_decisions(
            risk_decision_id, portfolio_decision_id,
            post_trade_snapshot_id, state, version, decision_json, created_at
        ) VALUES (?, ?, ?, ?, 0, ?, ?)
        """,
        (
            str(risk.risk_decision_id),
            str(risk.portfolio_decision_id),
            str(risk.post_trade_snapshot_id),
            risk.state.value,
            _json(risk.to_canonical_dict()),
            risk.completed_at.isoformat(),
        ),
    )


def _load_snapshot(
    connection: sqlite3.Connection, snapshot_id: ArtifactId
) -> AuthoritativeAccountPortfolioSnapshot:
    row = connection.execute(
        """
        SELECT * FROM authoritative_account_portfolio_snapshots
        WHERE account_snapshot_id = ?
        """,
        (str(snapshot_id),),
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown account Portfolio snapshot: {snapshot_id}")
    snapshot = AuthoritativeAccountPortfolioSnapshot.from_canonical_dict(
        _object_json(str(row["snapshot_json"]))
    )
    if (
        row["content_hash"] != snapshot.content_hash
        or row["version"] != snapshot.version
        or row["completeness"] != snapshot.completeness.value
        or row["reconciliation_state"] != snapshot.reconciliation_state.value
    ):
        raise ValueError("account Portfolio snapshot projection is invalid")
    return snapshot


def _load_portfolio(
    connection: sqlite3.Connection, decision_id: PortfolioDecisionId
) -> CompleteAccountPortfolioDecision:
    row = connection.execute(
        """
        SELECT * FROM complete_account_portfolio_decisions
        WHERE portfolio_decision_id = ?
        """,
        (str(decision_id),),
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown complete-account PortfolioDecision: {decision_id}")
    portfolio = CompleteAccountPortfolioDecision.from_canonical_dict(
        _object_json(str(row["decision_json"]))
    )
    if (
        row["version"] != portfolio.version
        or row["post_trade_content_hash"] != portfolio.post_trade.content_hash
        or row["configuration_hash"]
        != portfolio.configuration.configuration_hash
    ):
        raise ValueError("complete-account Portfolio projection is invalid")
    snapshot = _load_snapshot(connection, portfolio.account_snapshot.snapshot_id)
    if snapshot != portfolio.account_snapshot:
        raise ValueError("complete-account Portfolio source snapshot is invalid")
    return portfolio


def _load_risk(
    connection: sqlite3.Connection, risk_id: RiskDecisionId
) -> CompleteAccountRiskDecision:
    row = connection.execute(
        """
        SELECT * FROM complete_account_risk_decisions
        WHERE risk_decision_id = ?
        """,
        (str(risk_id),),
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown complete-account RiskDecision: {risk_id}")
    risk = CompleteAccountRiskDecision.from_canonical_dict(
        _object_json(str(row["decision_json"]))
    )
    if row["version"] != risk.version or row["state"] != risk.state.value:
        raise ValueError("complete-account Risk projection is invalid")
    portfolio = _load_portfolio(connection, risk.portfolio_decision_id)
    expected = CompleteAccountRiskService().assess(
        portfolio,
        actor=risk.actor,
        reason=risk.reason,
        started_at=risk.started_at,
        completed_at=risk.completed_at,
    )
    if expected != risk:
        raise ValueError("complete-account Risk history is not reconstructible")
    return risk


def _key(value: str) -> None:
    if not value or value != value.strip():
        raise ValueError("idempotency key must be a non-empty trimmed string")


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _object_json(value: str) -> dict[str, Any]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("complete-account repository JSON must be an object")
    return payload
