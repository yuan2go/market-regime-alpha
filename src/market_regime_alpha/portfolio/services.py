"""Portfolio proposal and independent fail-closed risk assessment services."""

from __future__ import annotations

from datetime import datetime

from market_regime_alpha.core.identity import PortfolioDecisionId, RiskDecisionId
from market_regime_alpha.decision.thesis import ThesisState, TradingThesis
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.portfolio.lifecycle import (
    PORTFOLIO_DECISION_SCHEMA,
    RISK_DECISION_SCHEMA,
    CurrentPositionInput,
    PortfolioAccountSnapshot,
    PortfolioConstraint,
    PortfolioConstraintType,
    PortfolioDecision,
    PortfolioDecisionState,
    PortfolioOutputMode,
    RiskBudget,
    RiskDecision,
    RiskDecisionState,
    TargetPosition,
    ThesisAllocationRequest,
)


class PortfolioConstructionService:
    """Constructs a proposal; it has no authority to approve hard risk."""

    def construct(
        self,
        *,
        theses: tuple[TradingThesis, ...],
        allocations: tuple[ThesisAllocationRequest, ...],
        current_positions: tuple[CurrentPositionInput, ...],
        account_snapshot: PortfolioAccountSnapshot,
        risk_budget: RiskBudget,
        mode: PortfolioOutputMode,
        actor: str,
        reason: str,
        created_at: datetime,
    ) -> PortfolioDecision:
        thesis_by_id = {item.thesis_id: item for item in theses}
        allocation_by_thesis = {item.thesis_id: item for item in allocations}
        if len(thesis_by_id) != len(theses) or len(allocation_by_thesis) != len(allocations):
            raise ValueError("Portfolio inputs require unique Thesis identities")
        if set(thesis_by_id) != set(allocation_by_thesis):
            raise ValueError("every Thesis requires exactly one allocation request")
        for thesis in theses:
            if thesis.state is not ThesisState.APPROVED:
                raise ValueError("only APPROVED Thesis can enter Portfolio construction")
            if created_at >= thesis.time_invalidation:
                raise ValueError("time-invalidated Thesis cannot enter Portfolio construction")
            request = allocation_by_thesis[thesis.thesis_id]
            if thesis.symbol != request.symbol:
                raise ValueError("Thesis and allocation symbol mismatch")
        positions = {item.symbol: item for item in current_positions}
        allocation_symbols = {item.symbol for item in allocations}
        if len(positions) != len(current_positions) or set(positions) != allocation_symbols:
            raise ValueError("current position inputs must exactly cover allocation symbols")
        symbols = tuple(item.symbol for item in allocations)
        conflict_symbols = tuple(
            sorted(symbol for symbol in set(symbols) if symbols.count(symbol) > 1)
        )
        thesis_ids = tuple(sorted(thesis_by_id, key=str))
        if conflict_symbols:
            state = PortfolioDecisionState.CONFLICTED
            targets: tuple[TargetPosition, ...] = ()
            reason_codes = ("CONFLICTING_THESES_FOR_SYMBOL",)
        else:
            state = PortfolioDecisionState.PROPOSED_FOR_RISK
            targets = tuple(
                sorted(
                    (
                        TargetPosition(
                            thesis_id=request.thesis_id,
                            symbol=request.symbol,
                            theme_id=request.theme_id,
                            current_quantity=positions[request.symbol].total_quantity,
                            available_quantity=positions[request.symbol].available_quantity,
                            target_quantity=request.target_quantity,
                            trade_quantity=(
                                request.target_quantity
                                - positions[request.symbol].total_quantity
                            ),
                            reference_price=request.reference_price,
                            average_daily_trade_value=request.average_daily_trade_value,
                            loss_per_share=request.loss_per_share,
                        )
                        for request in allocations
                    ),
                    key=lambda item: item.symbol,
                )
            )
            reason_codes = ("PORTFOLIO_PROPOSED_FOR_INDEPENDENT_RISK",)
        semantic = {
            "mode": mode.value,
            "state": state.value,
            "risk_budget_id": str(risk_budget.configuration_id),
            "risk_budget_hash": risk_budget.configuration_hash,
            "account_snapshot": account_snapshot.to_canonical_dict(),
            "target_positions": [item.to_canonical_dict() for item in targets],
            "thesis_ids": [str(item) for item in thesis_ids],
            "actor": actor,
            "reason": reason,
            "created_at": created_at.isoformat(),
            "reason_codes": list(reason_codes),
        }
        digest = canonical_hash(semantic).split(":", 1)[1]
        return PortfolioDecision(
            schema_version=PORTFOLIO_DECISION_SCHEMA,
            decision_id=PortfolioDecisionId(f"portfolio-decision-{digest[:24]}"),
            mode=mode,
            state=state,
            risk_budget_id=risk_budget.configuration_id,
            risk_budget_hash=risk_budget.configuration_hash,
            risk_budget=risk_budget,
            account_snapshot=account_snapshot,
            target_positions=targets,
            thesis_ids=thesis_ids,
            version=0,
            actor=actor,
            reason=reason,
            created_at=created_at,
            reason_codes=reason_codes,
        )


class IndependentRiskService:
    """Hard-risk authority; callers cannot replace or override its decision."""

    def assess(
        self,
        portfolio: PortfolioDecision,
        *,
        actor: str,
        reason: str,
        started_at: datetime,
        completed_at: datetime,
    ) -> RiskDecision:
        budget = portfolio.risk_budget
        elapsed = (completed_at - started_at).total_seconds()
        reason_codes: tuple[str, ...]
        if elapsed > budget.risk_service_timeout_seconds:
            state = RiskDecisionState.TIMEOUT
            constraints: tuple[PortfolioConstraint, ...] = ()
            reason_codes = ("RISK_SERVICE_TIMEOUT_FAIL_CLOSED",)
        elif portfolio.account_snapshot.observed_at > started_at:
            state = RiskDecisionState.DATA_INSUFFICIENT
            constraints = ()
            reason_codes = ("ACCOUNT_SNAPSHOT_NOT_AVAILABLE_AT_RISK_TIME",)
        elif portfolio.state is PortfolioDecisionState.CONFLICTED:
            state = RiskDecisionState.REJECTED
            constraints = ()
            reason_codes = ("CONFLICTING_THESES_FOR_SYMBOL",)
        else:
            constraints = _constraints(portfolio)
            failed = tuple(item for item in constraints if not item.passed)
            state = (
                RiskDecisionState.APPROVED
                if not failed
                else RiskDecisionState.REJECTED
            )
            reason_codes = (
                ("ALL_HARD_RISK_CONSTRAINTS_PASSED",)
                if not failed
                else tuple(sorted({item.reason_code for item in failed}))
            )
        semantic = {
            "portfolio_decision_id": str(portfolio.decision_id),
            "portfolio_decision_version": portfolio.version,
            "risk_budget_id": str(budget.configuration_id),
            "risk_budget_hash": budget.configuration_hash,
            "mode": portfolio.mode.value,
            "state": state.value,
            "constraints": [item.to_canonical_dict() for item in constraints],
            "actor": actor,
            "reason": reason,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "reason_codes": list(reason_codes),
        }
        digest = canonical_hash(semantic).split(":", 1)[1]
        return RiskDecision(
            schema_version=RISK_DECISION_SCHEMA,
            risk_decision_id=RiskDecisionId(f"risk-decision-{digest[:24]}"),
            portfolio_decision_id=portfolio.decision_id,
            portfolio_decision_version=portfolio.version,
            risk_budget_id=budget.configuration_id,
            risk_budget_hash=budget.configuration_hash,
            risk_budget=budget,
            mode=portfolio.mode,
            state=state,
            constraints=constraints,
            version=0,
            actor=actor,
            reason=reason,
            started_at=started_at,
            completed_at=completed_at,
            reason_codes=reason_codes,
        )


def _constraints(portfolio: PortfolioDecision) -> tuple[PortfolioConstraint, ...]:
    budget = portfolio.risk_budget
    nav = portfolio.account_snapshot.net_asset_value
    targets = portfolio.target_positions
    constraints: list[PortfolioConstraint] = []
    gross = sum(item.target_value for item in targets) / nav
    constraints.append(
        _constraint(
            PortfolioConstraintType.MAXIMUM_GROSS_EXPOSURE,
            gross,
            budget.maximum_gross_exposure,
            "MAXIMUM_GROSS_EXPOSURE_EXCEEDED",
            tuple(item.symbol for item in targets),
        )
    )
    maximum_symbol = max((item.target_value / nav for item in targets), default=0.0)
    constraints.append(
        _constraint(
            PortfolioConstraintType.SINGLE_SYMBOL_LIMIT,
            maximum_symbol,
            budget.single_symbol_limit,
            "SINGLE_SYMBOL_LIMIT_EXCEEDED",
            tuple(item.symbol for item in targets if item.target_value / nav > budget.single_symbol_limit),
        )
    )
    theme_values: dict[str, float] = {}
    for item in targets:
        theme_values[item.theme_id] = theme_values.get(item.theme_id, 0.0) + item.target_value
    maximum_theme = max((value / nav for value in theme_values.values()), default=0.0)
    constraints.append(
        _constraint(
            PortfolioConstraintType.THEME_LIMIT,
            maximum_theme,
            budget.theme_limit,
            "THEME_LIMIT_EXCEEDED",
            tuple(sorted(item.symbol for item in targets if theme_values[item.theme_id] / nav > budget.theme_limit)),
        )
    )
    liquidity = max(
        (abs(item.trade_value) / item.average_daily_trade_value for item in targets),
        default=0.0,
    )
    constraints.append(
        _constraint(
            PortfolioConstraintType.LIQUIDITY_LIMIT,
            liquidity,
            budget.liquidity_max_participation,
            "LIQUIDITY_LIMIT_EXCEEDED",
            tuple(
                item.symbol
                for item in targets
                if abs(item.trade_value) / item.average_daily_trade_value
                > budget.liquidity_max_participation
            ),
        )
    )
    required_cash = sum(max(0.0, item.trade_value) for item in targets)
    usable_cash = max(
        0.0,
        portfolio.account_snapshot.available_cash
        - nav * budget.minimum_cash_reserve,
    )
    constraints.append(
        _constraint(
            PortfolioConstraintType.AVAILABLE_CASH,
            required_cash,
            usable_cash,
            "AVAILABLE_CASH_INSUFFICIENT",
            tuple(item.symbol for item in targets if item.trade_quantity > 0),
        )
    )
    invalid_position = max(
        (float(-item.target_quantity) for item in targets if item.target_quantity < 0),
        default=0.0,
    )
    constraints.append(
        _constraint(
            PortfolioConstraintType.CURRENT_POSITION,
            invalid_position,
            0.0,
            "LONG_ONLY_POSITION_CONSTRAINT_FAILED",
            tuple(item.symbol for item in targets if item.target_quantity < 0),
        )
    )
    unavailable_sell = max(
        (
            float(max(0, -item.trade_quantity - item.available_quantity))
            for item in targets
        ),
        default=0.0,
    )
    t1_limit = 0.0 if budget.t_plus_one_enforced else unavailable_sell
    constraints.append(
        _constraint(
            PortfolioConstraintType.T_PLUS_ONE,
            unavailable_sell,
            t1_limit,
            "T_PLUS_ONE_AVAILABLE_QUANTITY_EXCEEDED",
            tuple(
                item.symbol
                for item in targets
                if -item.trade_quantity > item.available_quantity
            ),
        )
    )
    maximum_loss = sum(
        item.target_quantity * item.loss_per_share for item in targets
    ) / nav
    constraints.append(
        _constraint(
            PortfolioConstraintType.MAXIMUM_LOSS_BUDGET,
            maximum_loss,
            budget.maximum_loss_budget,
            "MAXIMUM_LOSS_BUDGET_EXCEEDED",
            tuple(item.symbol for item in targets),
        )
    )
    return tuple(constraints)


def _constraint(
    kind: PortfolioConstraintType,
    observed: float,
    limit: float,
    failed_reason: str,
    symbols: tuple[str, ...],
) -> PortfolioConstraint:
    passed = observed <= limit
    return PortfolioConstraint(
        constraint_type=kind,
        passed=passed,
        observed_value=observed,
        limit_value=limit,
        reason_code="CONSTRAINT_PASSED" if passed else failed_reason,
        symbols=tuple(sorted(set(symbols))),
    )
