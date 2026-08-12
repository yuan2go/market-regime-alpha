"""Multi-period metrics and attribution over Portfolio Shadow owner facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from math import sqrt
from typing import Any, Mapping

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.strategy_shadow.portfolio import (
    ShadowPortfolio,
    ShadowPortfolioDayState,
    ShadowTradeSide,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    normalize_canonical_datetime,
    require_sha256,
    require_text,
)


PERFORMANCE_REPORT_SCHEMA = "shadow-portfolio-performance/v1"


class EstimationStatus(str, Enum):
    ESTIMATED = "ESTIMATED"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


@dataclass(frozen=True, slots=True)
class PerformancePolicy:
    policy_id: ArtifactId
    policy_hash: str
    policy_version: str
    annual_sessions: int
    annual_risk_free_rate: Decimal
    minimum_return_samples: int
    reconciliation_tolerance: Decimal
    benchmark_reference: ValidationArtifactReference | None
    schema_version: str = "shadow-performance-policy/v1"

    def __post_init__(self) -> None:
        require_sha256("policy_hash", self.policy_hash)
        require_text("policy_version", self.policy_version)
        if self.annual_sessions <= 0 or self.minimum_return_samples < 2:
            raise ValueError("Performance Policy session/sample counts are invalid")
        if self.annual_risk_free_rate <= Decimal("-1"):
            raise ValueError("annual_risk_free_rate must exceed -100 percent")
        if self.reconciliation_tolerance < 0:
            raise ValueError("reconciliation_tolerance cannot be negative")
        digest = canonical_hash(self.identity_payload())
        if digest != self.policy_hash:
            raise ValueError("Performance Policy hash mismatch")
        if str(self.policy_id) != f"shadow-performance-policy-{digest[7:31]}":
            raise ValueError("Performance Policy identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        policy_version: str,
        annual_sessions: int,
        annual_risk_free_rate: Decimal,
        minimum_return_samples: int,
        reconciliation_tolerance: Decimal,
        benchmark_reference: ValidationArtifactReference | None,
    ) -> PerformancePolicy:
        values = _policy_payload(
            policy_version=policy_version,
            annual_sessions=annual_sessions,
            annual_risk_free_rate=annual_risk_free_rate,
            minimum_return_samples=minimum_return_samples,
            reconciliation_tolerance=reconciliation_tolerance,
            benchmark_reference=benchmark_reference,
        )
        digest = canonical_hash(values)
        return cls(
            ArtifactId(f"shadow-performance-policy-{digest[7:31]}"),
            digest,
            policy_version,
            annual_sessions,
            annual_risk_free_rate,
            minimum_return_samples,
            reconciliation_tolerance,
            benchmark_reference,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _policy_payload(
            policy_version=self.policy_version,
            annual_sessions=self.annual_sessions,
            annual_risk_free_rate=self.annual_risk_free_rate,
            minimum_return_samples=self.minimum_return_samples,
            reconciliation_tolerance=self.reconciliation_tolerance,
            benchmark_reference=self.benchmark_reference,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "policy_id": str(self.policy_id),
            "policy_hash": self.policy_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> PerformancePolicy:
        benchmark = value["benchmark_reference"]
        return cls(
            policy_id=ArtifactId(str(value["policy_id"])),
            policy_hash=str(value["policy_hash"]),
            policy_version=str(value["policy_version"]),
            annual_sessions=int(value["annual_sessions"]),
            annual_risk_free_rate=Decimal(str(value["annual_risk_free_rate"])),
            minimum_return_samples=int(value["minimum_return_samples"]),
            reconciliation_tolerance=Decimal(
                str(value["reconciliation_tolerance"])
            ),
            benchmark_reference=(
                None
                if benchmark is None
                else ValidationArtifactReference.from_canonical_dict(benchmark)
            ),
            schema_version=str(value["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class PerformanceMetric:
    name: str
    status: EstimationStatus
    value: Decimal | None
    unit: str
    sample_count: int
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text("metric name", self.name)
        require_text("metric unit", self.unit)
        if self.sample_count < 0:
            raise ValueError("metric sample_count cannot be negative")
        if (self.status is EstimationStatus.ESTIMATED) != (self.value is not None):
            raise ValueError("metric estimation status must match value availability")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("metric reasons must be unique and sorted")
        if self.status is EstimationStatus.NOT_ESTIMABLE and not self.reason_codes:
            raise ValueError("NOT_ESTIMABLE metric requires a reason")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "value": None if self.value is None else str(self.value),
            "unit": self.unit,
            "sample_count": self.sample_count,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> PerformanceMetric:
        metric_value = value["value"]
        return cls(
            name=str(value["name"]),
            status=EstimationStatus(str(value["status"])),
            value=None if metric_value is None else Decimal(str(metric_value)),
            unit=str(value["unit"]),
            sample_count=int(value["sample_count"]),
            reason_codes=tuple(str(item) for item in value["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class PeriodReturn:
    period: str
    value: Decimal
    session_count: int

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "period": self.period,
            "value": str(self.value),
            "session_count": self.session_count,
        }

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> PeriodReturn:
        return cls(
            period=str(value["period"]),
            value=Decimal(str(value["value"])),
            session_count=int(value["session_count"]),
        )


@dataclass(frozen=True, slots=True)
class PerformanceAttribution:
    dimension: str
    key: str
    status: EstimationStatus
    contribution: Decimal | None
    source_references: tuple[ValidationArtifactReference, ...]
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text("attribution dimension", self.dimension)
        require_text("attribution key", self.key)
        if (self.status is EstimationStatus.ESTIMATED) != (
            self.contribution is not None
        ):
            raise ValueError("attribution status must match contribution availability")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("attribution reasons must be unique and sorted")
        if self.status is EstimationStatus.NOT_ESTIMABLE and not self.reason_codes:
            raise ValueError("NOT_ESTIMABLE attribution requires a reason")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "key": self.key,
            "status": self.status.value,
            "contribution": (
                None if self.contribution is None else str(self.contribution)
            ),
            "source_references": [
                item.to_canonical_dict() for item in self.source_references
            ],
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> PerformanceAttribution:
        contribution = value["contribution"]
        return cls(
            dimension=str(value["dimension"]),
            key=str(value["key"]),
            status=EstimationStatus(str(value["status"])),
            contribution=(
                None if contribution is None else Decimal(str(contribution))
            ),
            source_references=tuple(
                ValidationArtifactReference.from_canonical_dict(item)
                for item in value["source_references"]
            ),
            reason_codes=tuple(str(item) for item in value["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class PortfolioPerformanceReport:
    report_id: ArtifactId
    report_hash: str
    portfolio_reference: ValidationArtifactReference
    policy_reference: ValidationArtifactReference
    start_date: date
    end_date: date
    generated_at: datetime
    equity_curve: tuple[tuple[date, Decimal], ...]
    metrics: tuple[PerformanceMetric, ...]
    monthly_returns: tuple[PeriodReturn, ...]
    yearly_returns: tuple[PeriodReturn, ...]
    attribution: tuple[PerformanceAttribution, ...]
    input_state_references: tuple[ValidationArtifactReference, ...]
    reconciliation_difference: Decimal
    negative_results_preserved: bool
    limitations: tuple[str, ...]
    schema_version: str = PERFORMANCE_REPORT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != PERFORMANCE_REPORT_SCHEMA:
            raise ValueError("unsupported performance report schema")
        require_sha256("report_hash", self.report_hash)
        normalize_canonical_datetime(self.generated_at)
        dates = tuple(item[0] for item in self.equity_curve)
        if not dates or dates != tuple(sorted(set(dates))):
            raise ValueError("equity curve must be non-empty, unique and sorted")
        names = tuple(item.name for item in self.metrics)
        if names != tuple(sorted(set(names))):
            raise ValueError("performance metrics must be unique and sorted")
        if not self.negative_results_preserved:
            raise ValueError("performance reports must preserve negative results")
        digest = canonical_hash(self.identity_payload())
        if digest != self.report_hash:
            raise ValueError("performance report hash mismatch")
        if str(self.report_id) != f"shadow-performance-{digest[7:31]}":
            raise ValueError("performance report identity mismatch")

    def metric(self, name: str) -> PerformanceMetric:
        for item in self.metrics:
            if item.name == name:
                return item
        raise KeyError(name)

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "portfolio_reference": self.portfolio_reference.to_canonical_dict(),
            "policy_reference": self.policy_reference.to_canonical_dict(),
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "generated_at": canonical_datetime(self.generated_at),
            "equity_curve": [
                {"date": item_date.isoformat(), "nav": str(nav)}
                for item_date, nav in self.equity_curve
            ],
            "metrics": [item.to_canonical_dict() for item in self.metrics],
            "monthly_returns": [
                item.to_canonical_dict() for item in self.monthly_returns
            ],
            "yearly_returns": [
                item.to_canonical_dict() for item in self.yearly_returns
            ],
            "attribution": [item.to_canonical_dict() for item in self.attribution],
            "input_state_references": [
                item.to_canonical_dict() for item in self.input_state_references
            ],
            "reconciliation_difference": str(self.reconciliation_difference),
            "negative_results_preserved": self.negative_results_preserved,
            "limitations": list(self.limitations),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "report_id": str(self.report_id),
            "report_hash": self.report_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, value: Mapping[str, Any]
    ) -> PortfolioPerformanceReport:
        return cls(
            report_id=ArtifactId(str(value["report_id"])),
            report_hash=str(value["report_hash"]),
            portfolio_reference=ValidationArtifactReference.from_canonical_dict(
                value["portfolio_reference"]
            ),
            policy_reference=ValidationArtifactReference.from_canonical_dict(
                value["policy_reference"]
            ),
            start_date=date.fromisoformat(str(value["start_date"])),
            end_date=date.fromisoformat(str(value["end_date"])),
            generated_at=datetime.fromisoformat(
                str(value["generated_at"]).replace("Z", "+00:00")
            ),
            equity_curve=tuple(
                (date.fromisoformat(str(item["date"])), Decimal(str(item["nav"])))
                for item in value["equity_curve"]
            ),
            metrics=tuple(
                PerformanceMetric.from_canonical_dict(item)
                for item in value["metrics"]
            ),
            monthly_returns=tuple(
                PeriodReturn.from_canonical_dict(item)
                for item in value["monthly_returns"]
            ),
            yearly_returns=tuple(
                PeriodReturn.from_canonical_dict(item)
                for item in value["yearly_returns"]
            ),
            attribution=tuple(
                PerformanceAttribution.from_canonical_dict(item)
                for item in value["attribution"]
            ),
            input_state_references=tuple(
                ValidationArtifactReference.from_canonical_dict(item)
                for item in value["input_state_references"]
            ),
            reconciliation_difference=Decimal(
                str(value["reconciliation_difference"])
            ),
            negative_results_preserved=bool(value["negative_results_preserved"]),
            limitations=tuple(str(item) for item in value["limitations"]),
            schema_version=str(value["schema_version"]),
        )


def build_portfolio_performance_report(
    *,
    portfolio: ShadowPortfolio,
    states: tuple[ShadowPortfolioDayState, ...],
    policy: PerformancePolicy,
    generated_at: datetime,
) -> PortfolioPerformanceReport:
    if not states:
        raise ValueError("performance report requires Portfolio Shadow states")
    states = tuple(
        sorted(
            states,
            key=lambda item: (item.trading_date, item.sequence, str(item.state_id)),
        )
    )
    if len({item.trading_date for item in states}) != len(states):
        raise ValueError("Portfolio Shadow state dates must be unique")
    if tuple(item.sequence for item in states) != tuple(range(1, len(states) + 1)):
        raise ValueError("Portfolio Shadow state sequence is not contiguous")
    if any(
        item.portfolio_reference.artifact_id != portfolio.portfolio_id
        or item.portfolio_reference.content_hash != portfolio.portfolio_hash
        for item in states
    ):
        raise ValueError("performance input belongs to another Portfolio")
    previous: ShadowPortfolioDayState | None = None
    for state in states:
        expected_previous = (
            None
            if previous is None
            else ValidationArtifactReference(
                "SHADOW_PORTFOLIO_DAY_STATE",
                previous.state_id,
                previous.state_hash,
            )
        )
        if state.previous_state_reference != expected_previous:
            raise ValueError("Portfolio Shadow state predecessor identity diverged")
        if previous is not None and state.recorded_at < previous.recorded_at:
            raise ValueError("Portfolio Shadow state recorded time is not monotonic")
        previous = state
    generated_at = normalize_canonical_datetime(generated_at)
    if generated_at < max(portfolio.created_at, *(item.recorded_at for item in states)):
        raise ValueError("Performance generated_at predates required input availability")
    returns = _returns(portfolio.initial_cash, states)
    metrics = _metrics(portfolio, states, returns, policy)
    state_references = tuple(
        ValidationArtifactReference(
            "SHADOW_PORTFOLIO_DAY_STATE", item.state_id, item.state_hash
        )
        for item in states
    )
    attribution = _attribution(states, state_references)
    symbol_pnl = sum(
        (
            item.contribution
            for item in attribution
            if item.dimension == "SYMBOL" and item.contribution is not None
        ),
        Decimal("0"),
    )
    reconciliation = states[-1].nav - portfolio.initial_cash - symbol_pnl
    if reconciliation.copy_abs() > policy.reconciliation_tolerance:
        raise ValueError("Portfolio performance attribution does not reconcile")
    portfolio_reference = ValidationArtifactReference(
        "SHADOW_PORTFOLIO", portfolio.portfolio_id, portfolio.portfolio_hash
    )
    policy_reference = ValidationArtifactReference(
        "SHADOW_PERFORMANCE_POLICY", policy.policy_id, policy.policy_hash
    )
    values = {
        "schema_version": PERFORMANCE_REPORT_SCHEMA,
        "portfolio_reference": portfolio_reference.to_canonical_dict(),
        "policy_reference": policy_reference.to_canonical_dict(),
        "start_date": states[0].trading_date.isoformat(),
        "end_date": states[-1].trading_date.isoformat(),
        "generated_at": canonical_datetime(generated_at),
        "equity_curve": [
            {"date": item.trading_date.isoformat(), "nav": str(item.nav)}
            for item in states
        ],
        "metrics": [item.to_canonical_dict() for item in metrics],
        "monthly_returns": [
            item.to_canonical_dict()
            for item in _period_returns(states, returns, yearly=False)
        ],
        "yearly_returns": [
            item.to_canonical_dict()
            for item in _period_returns(states, returns, yearly=True)
        ],
        "attribution": [item.to_canonical_dict() for item in attribution],
        "input_state_references": [
            item.to_canonical_dict() for item in state_references
        ],
        "reconciliation_difference": str(reconciliation),
        "negative_results_preserved": True,
        "limitations": [
            "ENGINEERING_EVIDENCE_ONLY",
            "FORMAL_OOS_FALSE",
            "NO_TRADING_AUTHORITY",
            "SHADOW_PORTFOLIO_ONLY",
        ],
    }
    digest = canonical_hash(values)
    monthly = _period_returns(states, returns, yearly=False)
    yearly = _period_returns(states, returns, yearly=True)
    return PortfolioPerformanceReport(
        report_id=ArtifactId(f"shadow-performance-{digest[7:31]}"),
        report_hash=digest,
        portfolio_reference=portfolio_reference,
        policy_reference=policy_reference,
        start_date=states[0].trading_date,
        end_date=states[-1].trading_date,
        generated_at=generated_at,
        equity_curve=tuple((item.trading_date, item.nav) for item in states),
        metrics=metrics,
        monthly_returns=monthly,
        yearly_returns=yearly,
        attribution=attribution,
        input_state_references=state_references,
        reconciliation_difference=reconciliation,
        negative_results_preserved=True,
        limitations=(
            "ENGINEERING_EVIDENCE_ONLY",
            "FORMAL_OOS_FALSE",
            "NO_TRADING_AUTHORITY",
            "SHADOW_PORTFOLIO_ONLY",
        ),
    )


def _metrics(
    portfolio: ShadowPortfolio,
    states: tuple[ShadowPortfolioDayState, ...],
    returns: tuple[Decimal, ...],
    policy: PerformancePolicy,
) -> tuple[PerformanceMetric, ...]:
    count = len(returns)
    cumulative = states[-1].nav / portfolio.initial_cash - Decimal("1")
    maximum_drawdown = _maximum_drawdown(portfolio.initial_cash, states)
    estimated: dict[str, tuple[Decimal, str]] = {
        "cumulative_return": (cumulative, "RATIO"),
        "maximum_drawdown": (maximum_drawdown, "RATIO"),
        "hit_rate": (
            Decimal(sum(item > 0 for item in returns)) / Decimal(count),
            "RATIO",
        ),
        "turnover": (
            sum((item.turnover for item in states), Decimal("0")),
            "RATIO",
        ),
        "cost_drag": (
            sum((item.total_cost for item in states), Decimal("0"))
            / portfolio.initial_cash,
            "RATIO",
        ),
        "average_exposure": (
            sum((item.gross_exposure for item in states), Decimal("0"))
            / Decimal(len(states)),
            "RATIO",
        ),
        "maximum_exposure": (
            max(item.gross_exposure for item in states),
            "RATIO",
        ),
    }
    if count >= policy.minimum_return_samples:
        annualized = _annualized_return(cumulative, count, policy.annual_sessions)
        volatility = _volatility(returns, policy.annual_sessions)
        estimated["annualized_return"] = (annualized, "RATIO")
        estimated["volatility"] = (volatility, "RATIO")
        if volatility > 0:
            daily_excess = (
                sum(returns, Decimal("0")) / Decimal(count)
                - policy.annual_risk_free_rate / Decimal(policy.annual_sessions)
            )
            estimated["sharpe"] = (
                _decimal_float(
                    float(daily_excess)
                    / (float(volatility) / sqrt(policy.annual_sessions))
                    * sqrt(policy.annual_sessions)
                ),
                "RATIO",
            )
        downside = tuple(item for item in returns if item < 0)
        if downside:
            downside_deviation = sqrt(
                sum(float(item) ** 2 for item in downside) / len(downside)
            )
            if downside_deviation > 0:
                estimated["sortino"] = (
                    _decimal_float(
                        float(sum(returns, Decimal("0")) / Decimal(count))
                        / downside_deviation
                        * sqrt(policy.annual_sessions)
                    ),
                    "RATIO",
                )
        if maximum_drawdown > 0:
            estimated["calmar"] = (annualized / maximum_drawdown, "RATIO")
    wins = tuple(item for item in returns if item > 0)
    losses = tuple(item for item in returns if item < 0)
    if wins and losses:
        estimated["win_loss_ratio"] = (
            (sum(wins, Decimal("0")) / Decimal(len(wins)))
            / -(sum(losses, Decimal("0")) / Decimal(len(losses))),
            "RATIO",
        )
    requested = sum(
        (
            intent.requested_quantity
            for state in states
            for intent in state.order_intents
        ),
        Decimal("0"),
    )
    if requested > 0:
        filled = sum(
            (fill.filled_quantity for state in states for fill in state.fills),
            Decimal("0"),
        )
        estimated["capacity_fill_ratio"] = (filled / requested, "RATIO")
    holding_counts: dict[str, int] = {}
    for state in states:
        for position in state.positions:
            holding_counts[position.symbol] = holding_counts.get(position.symbol, 0) + 1
    if holding_counts:
        estimated["average_holding_period"] = (
            Decimal(sum(holding_counts.values())) / Decimal(len(holding_counts)),
            "SESSIONS",
        )
    required = {
        "annualized_return": "INSUFFICIENT_RETURN_SAMPLES",
        "volatility": "INSUFFICIENT_RETURN_SAMPLES",
        "sharpe": "ZERO_OR_UNAVAILABLE_VOLATILITY",
        "sortino": "NO_DOWNSIDE_RETURN_SAMPLE",
        "calmar": "ZERO_OR_UNAVAILABLE_DRAWDOWN",
        "win_loss_ratio": "WIN_OR_LOSS_SAMPLE_MISSING",
        "capacity_fill_ratio": "NO_SHADOW_ORDER_REQUEST",
        "average_holding_period": "NO_SHADOW_POSITION_SAMPLE",
        "mfe": "MFE_NOT_OWNED_BY_PORTFOLIO_STATE",
        "mae": "MAE_NOT_OWNED_BY_PORTFOLIO_STATE",
    }
    names = {
        *estimated,
        *required,
    }
    return tuple(
        (
            PerformanceMetric(
                name,
                EstimationStatus.ESTIMATED,
                estimated[name][0],
                estimated[name][1],
                count,
                (),
            )
            if name in estimated
            else PerformanceMetric(
                name,
                EstimationStatus.NOT_ESTIMABLE,
                None,
                "RATIO" if name not in {"average_holding_period"} else "SESSIONS",
                count,
                (required[name],),
            )
        )
        for name in sorted(names)
    )


def _attribution(
    states: tuple[ShadowPortfolioDayState, ...],
    state_references: tuple[ValidationArtifactReference, ...],
) -> tuple[PerformanceAttribution, ...]:
    realized: dict[str, Decimal] = {}
    costs: dict[str, Decimal] = {}
    for state in states:
        for item in state.attribution:
            realized[item.symbol] = realized.get(item.symbol, Decimal("0")) + (
                item.realized_pnl
            )
            costs[item.symbol] = costs.get(item.symbol, Decimal("0")) + item.cost
    unrealized = {
        item.symbol: item.unrealized_pnl for item in states[-1].attribution
    }
    symbols = tuple(sorted(set(realized) | set(unrealized)))
    rows: list[PerformanceAttribution] = [
        PerformanceAttribution(
            "SYMBOL",
            symbol,
            EstimationStatus.ESTIMATED,
            realized.get(symbol, Decimal("0"))
            + unrealized.get(symbol, Decimal("0")),
            state_references,
            (),
        )
        for symbol in symbols
    ]
    rows.append(
        PerformanceAttribution(
            "COST",
            "TOTAL_COST_DRAG",
            EstimationStatus.ESTIMATED,
            -sum(costs.values(), Decimal("0")),
            state_references,
            ("INFORMATIONAL_NON_ADDITIVE_DIMENSION",),
        )
    )
    sides = {
        side: sum(
            (
                fill.total_cost
                for state in states
                for fill in state.fills
                if next(
                    intent.side
                    for intent in state.order_intents
                    if intent.intent_id == fill.intent_id
                )
                is side
            ),
            Decimal("0"),
        )
        for side in ShadowTradeSide
    }
    for side in ShadowTradeSide:
        rows.append(
            PerformanceAttribution(
                "ENTRY_EXIT",
                side.value,
                EstimationStatus.ESTIMATED,
                -sides[side],
                state_references,
                ("COST_ONLY_NON_ADDITIVE_DIMENSION",),
            )
        )
    for dimension in ("REGIME", "THEME", "FACTOR", "SIGNAL", "CANDIDATE_RANK"):
        rows.append(
            PerformanceAttribution(
                dimension,
                "NOT_AVAILABLE",
                EstimationStatus.NOT_ESTIMABLE,
                None,
                (),
                (f"{dimension}_EFFECTIVE_TIME_FACT_MISSING",),
            )
        )
    return tuple(sorted(rows, key=lambda item: (item.dimension, item.key)))


def _returns(
    initial_cash: Decimal,
    states: tuple[ShadowPortfolioDayState, ...],
) -> tuple[Decimal, ...]:
    previous = initial_cash
    result: list[Decimal] = []
    for state in states:
        if previous <= 0:
            raise ValueError("performance return denominator must be positive")
        result.append(state.nav / previous - Decimal("1"))
        previous = state.nav
    return tuple(result)


def _period_returns(
    states: tuple[ShadowPortfolioDayState, ...],
    returns: tuple[Decimal, ...],
    *,
    yearly: bool,
) -> tuple[PeriodReturn, ...]:
    grouped: dict[str, list[Decimal]] = {}
    for state, value in zip(states, returns, strict=True):
        key = (
            f"{state.trading_date.year:04d}"
            if yearly
            else f"{state.trading_date.year:04d}-{state.trading_date.month:02d}"
        )
        grouped.setdefault(key, []).append(value)
    return tuple(
        PeriodReturn(
            period=key,
            value=_compound(tuple(values)),
            session_count=len(values),
        )
        for key, values in sorted(grouped.items())
    )


def _compound(values: tuple[Decimal, ...]) -> Decimal:
    result = Decimal("1")
    for value in values:
        result *= Decimal("1") + value
    return result - Decimal("1")


def _maximum_drawdown(
    initial_cash: Decimal, states: tuple[ShadowPortfolioDayState, ...]
) -> Decimal:
    peak = initial_cash
    maximum = Decimal("0")
    for state in states:
        peak = max(peak, state.nav)
        drawdown = Decimal("0") if peak == 0 else (peak - state.nav) / peak
        maximum = max(maximum, drawdown)
    return maximum


def _annualized_return(
    cumulative: Decimal, count: int, annual_sessions: int
) -> Decimal:
    base = Decimal("1") + cumulative
    if base <= 0:
        return Decimal("-1")
    return _decimal_float(float(base) ** (annual_sessions / count) - 1.0)


def _volatility(returns: tuple[Decimal, ...], annual_sessions: int) -> Decimal:
    mean = sum(returns, Decimal("0")) / Decimal(len(returns))
    variance = sum(
        ((item - mean) ** 2 for item in returns), Decimal("0")
    ) / Decimal(len(returns) - 1)
    return _decimal_float(sqrt(float(variance)) * sqrt(annual_sessions))


def _decimal_float(value: float) -> Decimal:
    return Decimal(format(value, ".15g"))


def _policy_payload(
    *,
    policy_version: str,
    annual_sessions: int,
    annual_risk_free_rate: Decimal,
    minimum_return_samples: int,
    reconciliation_tolerance: Decimal,
    benchmark_reference: ValidationArtifactReference | None,
) -> dict[str, Any]:
    return {
        "schema_version": "shadow-performance-policy/v1",
        "policy_version": policy_version,
        "annual_sessions": annual_sessions,
        "annual_risk_free_rate": str(annual_risk_free_rate),
        "minimum_return_samples": minimum_return_samples,
        "reconciliation_tolerance": str(reconciliation_tolerance),
        "benchmark_reference": (
            None
            if benchmark_reference is None
            else benchmark_reference.to_canonical_dict()
        ),
    }


__all__ = [
    "EstimationStatus",
    "PERFORMANCE_REPORT_SCHEMA",
    "PerformanceAttribution",
    "PerformanceMetric",
    "PerformancePolicy",
    "PeriodReturn",
    "PortfolioPerformanceReport",
    "build_portfolio_performance_report",
]
