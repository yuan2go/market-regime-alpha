"""Broker adapter contracts.

The default adapters are safe by design: paper trading works locally, while
QMT/PTrade raise explicit configuration errors until the real vendor runtime is
installed and wired on the trading machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import uuid4


class BrokerUnavailable(RuntimeError):
    """Raised when a live broker adapter is not configured."""


@dataclass(frozen=True)
class BrokerPosition:
    symbol: str
    shares: int
    available_shares: int
    market_value: float
    cost_basis: float | None = None


@dataclass(frozen=True)
class BrokerAccount:
    cash: float
    available_cash: float
    total_equity: float
    positions: tuple[BrokerPosition, ...] = ()


@dataclass(frozen=True)
class BrokerOrderRequest:
    symbol: str
    side: str
    shares: int
    price: float | None = None
    order_type: str = "LIMIT"
    remark: str = ""


@dataclass(frozen=True)
class BrokerOrderResult:
    order_id: str
    accepted: bool
    message: str
    created_at: datetime


class BrokerAdapter(Protocol):
    name: str

    def status(self) -> dict[str, object]:
        ...

    def account(self) -> BrokerAccount:
        ...

    def place_order(self, request: BrokerOrderRequest) -> BrokerOrderResult:
        ...


@dataclass
class PaperBrokerAdapter:
    cash: float = 1_000_000.0
    positions: dict[str, BrokerPosition] = field(default_factory=dict)
    name: str = "paper"

    def status(self) -> dict[str, object]:
        return {"name": self.name, "configured": True, "mode": "paper"}

    def account(self) -> BrokerAccount:
        total_position_value = sum(item.market_value for item in self.positions.values())
        return BrokerAccount(
            cash=self.cash,
            available_cash=self.cash,
            total_equity=self.cash + total_position_value,
            positions=tuple(self.positions.values()),
        )

    def place_order(self, request: BrokerOrderRequest) -> BrokerOrderResult:
        return BrokerOrderResult(
            order_id=f"paper-{uuid4().hex[:12]}",
            accepted=True,
            message="Paper order accepted. No real broker call was made.",
            created_at=datetime.now(),
        )


class QMTAdapter:
    name = "qmt"

    def __init__(self, *, account_id: str | None = None, enabled: bool = False) -> None:
        self.account_id = account_id
        self.enabled = enabled

    def status(self) -> dict[str, object]:
        return {
            "name": self.name,
            "configured": bool(self.enabled and self.account_id),
            "mode": "live-adapter-placeholder",
            "required_user_steps": [
                "在交易 Windows 机器安装并登录 QMT / xtquant。",
                "确认券商账户、资金账号、交易权限和委托测试环境。",
                "把 account_id 写入本地配置，不要提交到 Git。",
            ],
        }

    def account(self) -> BrokerAccount:
        raise BrokerUnavailable("QMTAdapter is not wired to xtquant in this local environment.")

    def place_order(self, request: BrokerOrderRequest) -> BrokerOrderResult:
        raise BrokerUnavailable("QMTAdapter refuses live orders until QMT runtime is configured.")


class PTradeAdapter:
    name = "ptrade"

    def __init__(self, *, account_id: str | None = None, enabled: bool = False) -> None:
        self.account_id = account_id
        self.enabled = enabled

    def status(self) -> dict[str, object]:
        return {
            "name": self.name,
            "configured": bool(self.enabled and self.account_id),
            "mode": "live-adapter-placeholder",
            "required_user_steps": [
                "在券商 PTrade 环境创建策略并确认 Python API 权限。",
                "确认回测、模拟、实盘三套环境的账户标识和交易权限。",
                "先用模拟盘验证委托、撤单、成交回报和持仓同步。",
            ],
        }

    def account(self) -> BrokerAccount:
        raise BrokerUnavailable("PTradeAdapter is not wired to the broker runtime in this local environment.")

    def place_order(self, request: BrokerOrderRequest) -> BrokerOrderResult:
        raise BrokerUnavailable("PTradeAdapter refuses live orders until PTrade runtime is configured.")
