"""Thin operator facade for the PostgreSQL-owned Portfolio Shadow ledger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
    content_identity,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.application.shadow_research.postgres_repository import (
    PostgresShadowResearchRepository,
)
from market_regime_alpha.application.state_system.postgres_repository import (
    PostgresStateSystemRepository,
)
from market_regime_alpha.application.strategy_shadow.portfolio import (
    PortfolioWeightingMethod,
    ShadowParameterProvenance,
    ShadowPortfolio,
    ShadowPortfolioDayState,
    ShadowPortfolioMarketObservation,
    ShadowPortfolioPolicy,
    ShadowPortfolioTradeSession,
    _validate_market_value_provenance,
    build_shadow_portfolio,
    run_shadow_portfolio_day,
)
from market_regime_alpha.application.strategy_shadow.postgres_portfolio import (
    PostgresShadowPortfolioRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.market_data import PriceLimitState, TradingStatus
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)


@dataclass(frozen=True, slots=True)
class PortfolioMarketInput:
    symbol: str
    reference_price: Decimal | None
    mark_price: Decimal | None
    average_daily_amount: Decimal | None
    trading_status: TradingStatus
    price_limit_state: PriceLimitState
    trade_session: ShadowPortfolioTradeSession
    value_provenance: tuple[tuple[str, ShadowParameterProvenance], ...]
    risk_weight: Decimal | None
    risk_weight_provenance: ShadowParameterProvenance | None
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if (self.risk_weight is None) != (self.risk_weight_provenance is None):
            raise ValueError("Portfolio risk weight requires explicit provenance")
        if self.risk_weight is not None and self.risk_weight <= 0:
            raise ValueError("Portfolio risk weight must be positive")
        _validate_market_value_provenance(
            self.value_provenance,
            reference_price=self.reference_price,
            mark_price=self.mark_price,
            average_daily_amount=self.average_daily_amount,
        )
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Portfolio market reason codes must be sorted")

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> PortfolioMarketInput:
        risk_weight = _optional_decimal(value["risk_weight"])
        provenance_value = value["risk_weight_provenance"]
        return cls(
            symbol=str(value["symbol"]),
            reference_price=_optional_decimal(value["reference_price"]),
            mark_price=_optional_decimal(value["mark_price"]),
            average_daily_amount=_optional_decimal(value["average_daily_amount"]),
            trading_status=TradingStatus(str(value["trading_status"])),
            price_limit_state=PriceLimitState(str(value["price_limit_state"])),
            trade_session=ShadowPortfolioTradeSession(str(value["trade_session"])),
            value_provenance=tuple(
                sorted(
                    (
                        str(name),
                        ShadowParameterProvenance(str(provenance)),
                    )
                    for name, provenance in _mapping(
                        value["value_provenance"]
                    ).items()
                )
            ),
            risk_weight=risk_weight,
            risk_weight_provenance=(
                None
                if provenance_value is None
                else ShadowParameterProvenance(str(provenance_value))
            ),
            reason_codes=tuple(
                sorted({str(item) for item in _sequence(value["reason_codes"])})
            ),
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "reference_price": _decimal_text(self.reference_price),
            "mark_price": _decimal_text(self.mark_price),
            "average_daily_amount": _decimal_text(self.average_daily_amount),
            "trading_status": self.trading_status.value,
            "price_limit_state": self.price_limit_state.value,
            "trade_session": self.trade_session.value,
            "value_provenance": {
                name: provenance.value
                for name, provenance in self.value_provenance
            },
            "risk_weight": _decimal_text(self.risk_weight),
            "risk_weight_provenance": (
                None
                if self.risk_weight_provenance is None
                else self.risk_weight_provenance.value
            ),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class PortfolioShadowDayInput:
    research_trading_date: date
    trading_date: date
    observed_at: datetime
    portfolio_id: ArtifactId | None
    initial_cash: Decimal
    policy: ShadowPortfolioPolicy
    market_inputs: tuple[PortfolioMarketInput, ...]

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("Portfolio Shadow observed_at must be timezone-aware")
        if self.trading_date < self.research_trading_date:
            raise ValueError("Portfolio Shadow cannot precede its Research decision")
        symbols = tuple(item.symbol for item in self.market_inputs)
        if symbols != tuple(sorted(set(symbols))):
            raise ValueError("Portfolio Shadow market inputs must be sorted and unique")
        if self.initial_cash <= 0:
            raise ValueError("Portfolio Shadow initial cash must be positive")
        has_risk_weights = any(item.risk_weight is not None for item in self.market_inputs)
        if (
            self.policy.weighting_method is not PortfolioWeightingMethod.RISK_WEIGHT
            and has_risk_weights
        ):
            raise ValueError("risk_weight is only accepted by RISK_WEIGHT Policy")

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> PortfolioShadowDayInput:
        policy_value = _mapping(value["policy"])
        parameters = {
            str(name): (
                Decimal(str(_mapping(parameter)["value"])),
                ShadowParameterProvenance(
                    str(_mapping(parameter)["provenance"])
                ),
            )
            for name, parameter in _mapping(policy_value["parameters"]).items()
        }
        policy = ShadowPortfolioPolicy.create(
            policy_version=str(policy_value["policy_version"]),
            top_k=int(policy_value["top_k"]),
            weighting_method=PortfolioWeightingMethod(
                str(policy_value["weighting_method"])
            ),
            lot_size=int(policy_value["lot_size"]),
            t_plus_one=_required_boolean(policy_value["t_plus_one"]),
            parameters=parameters,
            created_at=datetime.fromisoformat(str(policy_value["effective_at"])),
        )
        market_inputs = tuple(
            sorted(
                (
                    PortfolioMarketInput.from_canonical_dict(_mapping(item))
                    for item in _sequence(value["market_observations"])
                ),
                key=lambda item: item.symbol,
            )
        )
        portfolio_id_value = value["portfolio_id"]
        return cls(
            research_trading_date=date.fromisoformat(
                str(value["research_trading_date"])
            ),
            trading_date=date.fromisoformat(str(value["trading_date"])),
            observed_at=datetime.fromisoformat(str(value["observed_at"])),
            portfolio_id=(
                None
                if portfolio_id_value is None
                else ArtifactId(str(portfolio_id_value))
            ),
            initial_cash=Decimal(str(value["initial_cash"])),
            policy=policy,
            market_inputs=market_inputs,
        )


class PortfolioShadowDayOperator:
    """Resolve owner Artifacts, then append or verify one Portfolio day."""

    def __init__(self, factory: PostgresConnectionFactory) -> None:
        self._factory = factory
        self._research = PostgresShadowResearchRepository(
            factory, apply_migrations=False
        )
        self._state = PostgresStateSystemRepository(factory, apply_migrations=False)
        self._validation = PostgresResearchValidationRepository(
            factory, apply_migrations=False
        )
        self._portfolio = PostgresShadowPortfolioRepository(
            factory, apply_migrations=False
        )

    def run(self, request: PortfolioShadowDayInput) -> dict[str, Any]:
        decision, panel_reference = self._resolve_research_lineage(
            request.research_trading_date
        )
        candidate_set = self._state.get_runtime_candidate(
            run_id=decision.run_id,
            tick_id=decision.tick_id,
        )
        candidate_reference = ValidationArtifactReference(
            "CANDIDATE_SET",
            candidate_set.envelope.artifact_id,
            candidate_set.envelope.content_hash,
        )
        portfolio = self._resolve_portfolio(
            request=request,
            panel_reference=panel_reference,
            candidate_reference=candidate_reference,
        )
        latest = self._portfolio.latest_state(portfolio.portfolio_id)
        if latest is not None and request.trading_date < latest.trading_date:
            raise ValueError("Portfolio Shadow cannot append before durable latest state")
        previous = latest
        if latest is not None and latest.trading_date == request.trading_date:
            previous = (
                None
                if latest.previous_state_reference is None
                else self._portfolio.get_state(
                    latest.previous_state_reference.artifact_id
                )
            )
        scores = {
            item.symbol: (
                None
                if item.candidate_discovery_score is None
                else Decimal(str(item.candidate_discovery_score))
            )
            for item in candidate_set.selected
        }
        inputs = {item.symbol: item for item in request.market_inputs}
        symbols = set(scores)
        if previous is not None:
            symbols.update(item.symbol for item in previous.positions)
        if not symbols:
            return _result(
                request=request,
                portfolio=portfolio,
                state=None,
                status="DATA_INSUFFICIENT",
                reason_codes=("NO_SELECTED_CANDIDATE_OR_OPEN_POSITION",),
            )
        unexpected_inputs = set(inputs) - symbols
        if unexpected_inputs:
            raise ValueError(
                "Portfolio Shadow market inputs contain symbols outside Candidate/Position Authority"
            )
        observations = tuple(
            self._observation(
                symbol=symbol,
                score=scores.get(symbol),
                market_input=inputs.get(symbol),
                observed_at=request.observed_at,
                candidate_reference=candidate_reference,
                panel_reference=panel_reference,
            )
            for symbol in sorted(symbols)
        )
        required_day_lineage = {panel_reference, candidate_reference}
        if any(
            not required_day_lineage.issubset(item.source_references)
            for item in observations
        ):
            raise ValueError(
                "Portfolio Shadow day omits current Panel/Candidate lineage"
            )
        if request.policy.weighting_method is PortfolioWeightingMethod.RISK_WEIGHT:
            missing_risk = tuple(
                item.symbol
                for item in observations
                if item.score is not None and item.risk_weight is None
            )
            if missing_risk:
                raise ValueError(
                    "RISK_WEIGHT requires explicit weights and provenance for all Candidates"
                )
        state = run_shadow_portfolio_day(
            portfolio=portfolio,
            policy=request.policy,
            trading_date=request.trading_date,
            observations=observations,
            previous=previous,
            recorded_at=request.observed_at,
        )
        expected_previous = None if previous is None else previous.state_id
        stored = self._portfolio.append_state(
            state,
            expected_previous_state_id=expected_previous,
        )
        return _result(
            request=request,
            portfolio=portfolio,
            state=stored,
            status="RECOVERED_IDEMPOTENT" if latest == stored else "RECORDED",
            reason_codes=("PORTFOLIO_SHADOW_DAY_RECORDED",),
        )

    def replay(self, portfolio_id: ArtifactId) -> dict[str, Any]:
        states = self._portfolio.replay(portfolio_id)
        _policy, portfolio = self._portfolio.get_portfolio(portfolio_id)
        return {
            "operation": "PORTFOLIO_SHADOW_REPLAY",
            "status": "VERIFIED",
            "portfolio_id": str(portfolio.portfolio_id),
            "state_ids": [str(item.state_id) for item in states],
            "state_count": len(states),
            "shadow_fill_is_real_fill": False,
            "shadow_position_is_real_position": False,
            **_authority_ceiling(),
        }

    def _resolve_portfolio(
        self,
        *,
        request: PortfolioShadowDayInput,
        panel_reference: ValidationArtifactReference,
        candidate_reference: ValidationArtifactReference,
    ) -> ShadowPortfolio:
        if request.portfolio_id is not None:
            stored_policy, portfolio = self._portfolio.get_portfolio(
                request.portfolio_id
            )
            if stored_policy != request.policy:
                raise ValueError("Portfolio Shadow request Policy conflicts with owner row")
            if portfolio.initial_cash != request.initial_cash:
                raise ValueError("Portfolio Shadow initial cash conflicts with owner row")
            return portfolio
        existing = self._portfolio.find_by_policy(request.policy.policy_id)
        if existing is not None:
            stored_policy, portfolio = existing
            if stored_policy != request.policy or portfolio.initial_cash != request.initial_cash:
                raise ValueError("Portfolio Shadow Policy owner identity conflict")
            return portfolio
        portfolio = build_shadow_portfolio(
            policy=request.policy,
            research_reference=panel_reference,
            candidate_reference=candidate_reference,
            initial_cash=request.initial_cash,
            created_at=request.policy.created_at,
        )
        return self._portfolio.save_portfolio(
            policy=request.policy,
            portfolio=portfolio,
        )

    def _observation(
        self,
        *,
        symbol: str,
        score: Decimal | None,
        market_input: PortfolioMarketInput | None,
        observed_at: datetime,
        candidate_reference: ValidationArtifactReference,
        panel_reference: ValidationArtifactReference,
    ) -> ShadowPortfolioMarketObservation:
        if market_input is None:
            market_input = PortfolioMarketInput(
                symbol=symbol,
                reference_price=None,
                mark_price=None,
                average_daily_amount=None,
                trading_status=TradingStatus.UNKNOWN,
                price_limit_state=PriceLimitState.UNKNOWN,
                trade_session=ShadowPortfolioTradeSession.UNKNOWN,
                value_provenance=(
                    (
                        "price_limit_state",
                        ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
                    ),
                    (
                        "trade_session",
                        ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
                    ),
                    (
                        "trading_status",
                        ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
                    ),
                ),
                risk_weight=None,
                risk_weight_provenance=None,
                reason_codes=("MARKET_OBSERVATION_MISSING",),
            )
        payload = {
            "schema_version": "portfolio-shadow-market-observation/v1",
            "observed_at": observed_at.isoformat(),
            "observation": market_input.to_canonical_dict(),
            "evidence_authority": "ENGINEERING_OPERATOR_OBSERVATION",
            "limitations": [
                "FREE_DATA_EXPLORATORY",
                "NOT_FORMAL_PIT",
                "NOT_REAL_FILL_EVIDENCE",
            ],
        }
        observation_id, observation_hash = content_identity(
            "portfolio-shadow-market-observation", payload
        )
        self._validation.record(
            artifact_id=observation_id,
            artifact_hash=observation_hash,
            artifact_kind="PORTFOLIO_SHADOW_MARKET_OBSERVATION",
            evidence_authority="ENGINEERING_ONLY",
            payload=payload,
            created_at=observed_at,
        )
        return ShadowPortfolioMarketObservation(
            symbol=symbol,
            score=score,
            risk_weight=market_input.risk_weight,
            risk_weight_provenance=market_input.risk_weight_provenance,
            reference_price=market_input.reference_price,
            mark_price=market_input.mark_price,
            average_daily_amount=market_input.average_daily_amount,
            trading_status=market_input.trading_status,
            price_limit_state=market_input.price_limit_state,
            trade_session=market_input.trade_session,
            value_provenance=market_input.value_provenance,
            observed_at=observed_at,
            source_references=tuple(
                sorted(
                    {
                        candidate_reference,
                        panel_reference,
                        ValidationArtifactReference(
                            "PORTFOLIO_SHADOW_MARKET_OBSERVATION",
                            observation_id,
                            observation_hash,
                        ),
                    },
                    key=lambda item: (
                        item.artifact_kind,
                        str(item.artifact_id),
                        item.content_hash,
                    ),
                )
            ),
            reason_codes=market_input.reason_codes,
        )

    def _resolve_research_lineage(
        self, trading_date: date
    ) -> tuple[Any, ValidationArtifactReference]:
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT decision.decision_id, panel.panel_id, panel.panel_hash
                FROM shadow_research_decision AS decision
                JOIN shadow_research_session AS shadow
                  ON shadow.session_id = decision.session_id
                JOIN research_evaluation_panel_slice_v2 AS slice
                  ON slice.shadow_decision_id = decision.decision_id
                JOIN research_evaluation_panel_v2 AS panel
                  ON panel.panel_id = slice.panel_id
                WHERE shadow.trading_date = %s
                  AND shadow.status = 'SETTLED'
                ORDER BY panel.created_at DESC, panel.panel_id DESC
                """,
                (trading_date,),
            ).fetchall()
        if len(rows) != 1:
            raise ValueError(
                "Portfolio Shadow requires exactly one settled Research Shadow Panel"
            )
        return (
            self._research.get_decision(ArtifactId(str(rows[0][0]))),
            ValidationArtifactReference(
                "RESEARCH_PANEL_V2",
                ArtifactId(str(rows[0][1])),
                str(rows[0][2]),
            ),
        )


def _result(
    *,
    request: PortfolioShadowDayInput,
    portfolio: ShadowPortfolio,
    state: ShadowPortfolioDayState | None,
    status: str,
    reason_codes: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "operation": "PORTFOLIO_SHADOW_DAY",
        "status": status,
        "trading_date": request.trading_date.isoformat(),
        "portfolio_id": str(portfolio.portfolio_id),
        "state_id": None if state is None else str(state.state_id),
        "state_hash": None if state is None else state.state_hash,
        "sequence": None if state is None else state.sequence,
        "cash": None if state is None else str(state.cash),
        "nav": None if state is None else str(state.nav),
        "gross_exposure": None if state is None else str(state.gross_exposure),
        "turnover": None if state is None else str(state.turnover),
        "drawdown": None if state is None else str(state.drawdown),
        "total_cost": None if state is None else str(state.total_cost),
        "position_count": None if state is None else len(state.positions),
        "reason_codes": list(reason_codes),
        "shadow_fill_is_real_fill": False,
        "shadow_position_is_real_position": False,
        **_authority_ceiling(),
    }


def _authority_ceiling() -> dict[str, bool]:
    return {
        "formal_pit": False,
        "formal_oos": False,
        "alpha_validated": False,
        "calibrated": False,
        "entry_qualified": False,
        "strategy_shadow_proven": False,
        "production_authorized": False,
        "live_broker_authorized": False,
    }


def _optional_decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Portfolio Shadow input must contain objects")
    return value


def _sequence(value: Any) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("Portfolio Shadow input must contain arrays")
    return tuple(value)


def _required_boolean(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError("Portfolio Shadow Policy boolean is invalid")
    return value


__all__ = ["PortfolioShadowDayInput", "PortfolioShadowDayOperator"]
