"""PostgreSQL-native repository for immutable PortfolioDecision and independent RiskDecision."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any, cast

from market_regime_alpha.core.identity import PortfolioDecisionId, RiskDecisionId
from market_regime_alpha.portfolio.lifecycle import PortfolioDecision, RiskDecision
from market_regime_alpha.portfolio.serialization import (
    portfolio_decision_from_dict,
    risk_decision_from_dict,
)
from market_regime_alpha.portfolio.services import IndependentRiskService
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.native_repository import (
    NativePostgresRepository,
    PostgresConnection,
    acquire_scope_lock,
)


class PostgresPortfolioDecisionRepository(NativePostgresRepository):
    """Native PostgreSQL PortfolioDecision and RiskDecision authority."""

    def __init__(self, factory: PostgresConnectionFactory) -> None:
        super().__init__(factory)

    def save_portfolio(
        self,
        decision: PortfolioDecision,
        *,
        idempotency_key: str,
        command_hash: str,
    ) -> PortfolioDecision:
        return cast(PortfolioDecision, self._save(
            result_type="PORTFOLIO",
            result_id=str(decision.decision_id),
            payload=decision.to_canonical_dict(),
            idempotency_key=idempotency_key,
            command_hash=command_hash,
            portfolio=decision,
            risk=None,
        ))

    def save_risk(
        self,
        decision: RiskDecision,
        *,
        idempotency_key: str,
        command_hash: str,
    ) -> RiskDecision:
        portfolio = self.get_portfolio(decision.portfolio_decision_id)
        expected = IndependentRiskService().assess(
            portfolio,
            actor=decision.actor,
            reason=decision.reason,
            started_at=decision.started_at,
            completed_at=decision.completed_at,
        )
        if expected != decision:
            raise ValueError("RiskDecision cannot bypass independent risk validation")
        return cast(RiskDecision, self._save(
            result_type="RISK",
            result_id=str(decision.risk_decision_id),
            payload=decision.to_canonical_dict(),
            idempotency_key=idempotency_key,
            command_hash=command_hash,
            portfolio=None,
            risk=decision,
        ))

    def _save(
        self,
        *,
        result_type: str,
        result_id: str,
        payload: dict[str, Any],
        idempotency_key: str,
        command_hash: str,
        portfolio: PortfolioDecision | None,
        risk: RiskDecision | None,
    ) -> PortfolioDecision | RiskDecision:
        _key(idempotency_key)
        with self._connect() as connection:
            acquire_scope_lock(
                connection,
                namespace="portfolio-risk-command",
                identity=idempotency_key,
            )
            try:
                command = connection.execute(
                    "SELECT * FROM portfolio_risk_commands WHERE idempotency_key = %s",
                    (idempotency_key,),
                ).fetchone()
                if command is not None:
                    if (
                        command["command_hash"] != command_hash
                        or command["result_type"] != result_type
                        or command["result_id"] != result_id
                    ):
                        raise ValueError("idempotency key reused for different portfolio command")
                    result = (
                        _load_portfolio(connection, PortfolioDecisionId(result_id))
                        if result_type == "PORTFOLIO"
                        else _load_risk(connection, RiskDecisionId(result_id))
                    )
                    connection.commit()
                    return result
                if portfolio is not None:
                    existing = connection.execute(
                        "SELECT decision_json FROM portfolio_decisions WHERE portfolio_decision_id = %s",
                        (result_id,),
                    ).fetchone()
                    if existing is None:
                        connection.execute(
                            """
                            INSERT INTO portfolio_decisions(
                                portfolio_decision_id, version, mode, state,
                                risk_budget_id, risk_budget_hash, decision_json, created_at
                            ) VALUES (%s, 0, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                result_id,
                                portfolio.mode.value,
                                portfolio.state.value,
                                str(portfolio.risk_budget_id),
                                portfolio.risk_budget_hash,
                                _json(payload),
                                portfolio.created_at.isoformat(),
                            ),
                        )
                    elif portfolio_decision_from_dict(
                        _object_json(str(existing["decision_json"]))
                    ) != portfolio:
                        raise ValueError("PortfolioDecision identity conflict")
                else:
                    assert risk is not None
                    existing = connection.execute(
                        "SELECT decision_json FROM risk_decisions WHERE portfolio_decision_id = %s",
                        (str(risk.portfolio_decision_id),),
                    ).fetchone()
                    if existing is None:
                        connection.execute(
                            """
                            INSERT INTO risk_decisions(
                                risk_decision_id, portfolio_decision_id,
                                portfolio_decision_version, version, state,
                                decision_json, created_at
                            ) VALUES (%s, %s, 0, 0, %s, %s, %s)
                            """,
                            (
                                result_id,
                                str(risk.portfolio_decision_id),
                                risk.state.value,
                                _json(payload),
                                risk.completed_at.isoformat(),
                            ),
                        )
                    elif risk_decision_from_dict(
                        _object_json(str(existing["decision_json"]))
                    ) != risk:
                        raise ValueError("PortfolioDecision already has a different RiskDecision")
                connection.execute(
                    """
                    INSERT INTO portfolio_risk_commands(
                        idempotency_key, command_hash, result_type, result_id, created_at
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        idempotency_key,
                        command_hash,
                        result_type,
                        result_id,
                        datetime.now(UTC).isoformat(),
                    ),
                )
                stored_result = portfolio if portfolio is not None else risk
                if stored_result is None:
                    raise RuntimeError("portfolio repository result is missing")
                connection.commit()
                return stored_result
            except Exception:
                connection.rollback()
                raise

    def get_portfolio(self, decision_id: PortfolioDecisionId) -> PortfolioDecision:
        with self._connect() as connection:
            return _load_portfolio(connection, decision_id)

    def get_risk(self, risk_decision_id: RiskDecisionId) -> RiskDecision:
        with self._connect() as connection:
            return _load_risk(connection, risk_decision_id)


def _load_portfolio(
    connection: PostgresConnection, decision_id: PortfolioDecisionId
) -> PortfolioDecision:
    row = connection.execute(
        "SELECT * FROM portfolio_decisions WHERE portfolio_decision_id = %s",
        (str(decision_id),),
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown PortfolioDecision: {decision_id}")
    decision = portfolio_decision_from_dict(_object_json(str(row["decision_json"])))
    if (
        row["version"] != decision.version
        or row["mode"] != decision.mode.value
        or row["state"] != decision.state.value
        or row["risk_budget_hash"] != decision.risk_budget_hash
    ):
        raise ValueError("PortfolioDecision projection is not reconstructible")
    return decision


def _load_risk(
    connection: PostgresConnection, decision_id: RiskDecisionId
) -> RiskDecision:
    row = connection.execute(
        "SELECT * FROM risk_decisions WHERE risk_decision_id = %s",
        (str(decision_id),),
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown RiskDecision: {decision_id}")
    decision = risk_decision_from_dict(_object_json(str(row["decision_json"])))
    if row["version"] != decision.version or row["state"] != decision.state.value:
        raise ValueError("RiskDecision projection is not reconstructible")
    return decision


def _key(value: str) -> None:
    if not value or value != value.strip():
        raise ValueError("idempotency key must be a non-empty trimmed string")


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _object_json(value: str) -> dict[str, Any]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("portfolio repository JSON must be an object")
    return payload


__all__ = ["PostgresPortfolioDecisionRepository"]
