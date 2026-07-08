"""Portfolio and execution risk checks for dividend T-trading."""

from __future__ import annotations

from dataclasses import dataclass

from market_regime_alpha.dividend_t.models import OrderIntent, PositionState


@dataclass(frozen=True)
class RiskLimits:
    single_stock_limit_pct: float = 1.00
    cycle_stock_limit_pct: float = 1.00
    max_single_t_trade_pct: float = 1.00
    min_cash_pct: float = 0.00


@dataclass(frozen=True)
class RiskCheckResult:
    allowed: bool
    final_notional_pct: float
    violations: tuple[str, ...]
    warnings: tuple[str, ...]


class RiskEngine:
    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()

    def validate_order(
        self,
        intent: OrderIntent | None,
        *,
        position: PositionState,
        base_position_limit_pct: float,
    ) -> RiskCheckResult:
        if intent is None:
            return RiskCheckResult(False, 0.0, ("没有订单意图。",), ())

        requested = max(0.0, intent.notional_pct)
        warnings: list[str] = []
        violations: list[str] = []

        if intent.side == "BUY":
            requested = min(requested, self.limits.max_single_t_trade_pct)
            position_limit = min(base_position_limit_pct, self.limits.single_stock_limit_pct)
            if position.is_cycle_stock:
                position_limit = min(position_limit, self.limits.cycle_stock_limit_pct)

            room_by_position = max(0.0, position_limit - position.symbol_position_pct)
            room_by_cash = max(0.0, position.available_cash_pct - self.limits.min_cash_pct)
            final_pct = min(requested, room_by_position, room_by_cash)

            if final_pct < intent.notional_pct:
                warnings.append("买入比例被总仓位、现金或单次主动买入上限压缩。")
            if final_pct <= 0:
                violations.append("没有可用仓位或现金空间。")

        elif intent.side == "SELL":
            final_pct = min(requested, position.available_sell_pct, position.symbol_position_pct)
            if position.available_sell_pct <= 0:
                violations.append("没有可卖仓位，可能受 T+1 或持仓不足限制。")
            if final_pct < intent.notional_pct:
                warnings.append("卖出比例被可卖仓位限制压缩。")
        else:
            return RiskCheckResult(False, 0.0, (f"未知订单方向：{intent.side}",), ())

        return RiskCheckResult(
            allowed=not violations and final_pct > 0,
            final_notional_pct=round(final_pct, 4),
            violations=tuple(violations),
            warnings=tuple(warnings),
        )
