from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from market_regime_alpha.application.continuous_research.policy import (
    ContinuousSessionPhase,
)
from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.application.decision_system.contracts import (
    DailyDecisionOutcome,
    DailyDecisionWindowSummary,
    DecisionLineage,
    DecisionRiskConfiguration,
    DecisionWindowState,
    FillDerivedPositionReference,
    ManualAccountObservation,
    ManualPositionObservation,
    ReconciliationTolerance,
    SummaryCandidate,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from tests.persistence.postgres.test_continuous_research_journal import (
    MutableClock,
    _command,
    _tick,
)


UTC = timezone.utc
TRADING_DATE = date(2026, 8, 6)
AS_OF = datetime(2026, 8, 6, 6, 45, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64


def active_claim(factory: PostgresConnectionFactory, clock: MutableClock):
    journal = PostgresContinuousResearchJournal(factory, clock=clock)
    command = _command()
    journal.create_or_get(command)
    tick = journal.admit_tick(_tick(command), session_phase=ContinuousSessionPhase.DECISION_WINDOW)
    return journal, journal.claim_tick(
        run_id=command.run_id,
        tick_id=tick.command.tick_id,
    )


def observation(
    *,
    revision: int = 1,
    previous: ArtifactId | None = None,
    idempotency_key: str = "manual-account-1",
    total_quantity: int = 100,
    available_quantity: int = 80,
    frozen_quantity: int = 20,
    total_equity: Decimal = Decimal("100000.120000"),
    available_cash: Decimal = Decimal("80000.120000"),
    positions: tuple[ManualPositionObservation, ...] | None = None,
) -> ManualAccountObservation:
    return ManualAccountObservation.create(
        account_id="manual-account-a",
        trading_date=TRADING_DATE,
        as_of_time=AS_OF,
        total_equity=total_equity,
        available_cash=available_cash,
        frozen_cash=Decimal("0"),
        source="MANUAL_BROKER_STATEMENT_OBSERVATION",
        actor="operator-a",
        reason="daily manual account calibration",
        notes="research/manual decision support only",
        idempotency_key=idempotency_key,
        revision=revision,
        previous_observation_id=previous,
        positions=(
            positions
            if positions is not None
            else (
                ManualPositionObservation(
                    symbol="600000.SH",
                    total_quantity=total_quantity,
                    available_quantity=available_quantity,
                    frozen_quantity=frozen_quantity,
                    average_cost=Decimal("10.123456") if total_quantity else None,
                    observed_market_value=Decimal("2000"),
                ),
            )
        ),
        created_at=AS_OF,
    )


def position(
    *,
    total_quantity: int = 100,
    available_quantity: int | None = 80,
    frozen_quantity: int | None = 20,
    average_cost: Decimal | None = Decimal("10.123456"),
    complete: bool = True,
) -> FillDerivedPositionReference:
    return FillDerivedPositionReference(
        snapshot_id=ArtifactId("fill-position-snapshot-a"),
        snapshot_hash=HASH_A,
        account_id="manual-account-a",
        symbol="600000.SH",
        as_of_time=AS_OF,
        total_quantity=total_quantity,
        available_quantity=available_quantity,
        frozen_quantity=frozen_quantity,
        average_cost=average_cost,
        source_fill_ids=("fill-a",),
        complete=complete,
    )


def tolerance() -> ReconciliationTolerance:
    return ReconciliationTolerance(
        configuration_id=ArtifactId("reconciliation-tolerance-v1"),
        configuration_hash=canonical_hash({"equity": "0.01", "cash": "0.01", "cost": "0.000001"}),
        equity_tolerance=Decimal("0.01"),
        cash_tolerance=Decimal("0.01"),
        average_cost_tolerance=Decimal("0.000001"),
    )


def risk_configuration() -> DecisionRiskConfiguration:
    payload = {
        "maximum_observation_age_seconds": 1800,
        "maximum_data_age_seconds": 1800,
        "maximum_single_symbol_weight": "0.10",
        "maximum_theme_weight": "0.20",
        "minimum_liquidity": "0.50",
        "daily_loss_limit": "1000",
    }
    return DecisionRiskConfiguration(
        configuration_id=ArtifactId("decision-risk-config-v1"),
        configuration_hash=canonical_hash(payload),
        maximum_observation_age_seconds=1800,
        maximum_data_age_seconds=1800,
        maximum_single_symbol_weight=Decimal("0.10"),
        maximum_theme_weight=Decimal("0.20"),
        minimum_liquidity=Decimal("0.50"),
        daily_loss_limit=Decimal("1000"),
    )


def lineage(claim) -> DecisionLineage:
    return DecisionLineage(
        continuous_operation_id=claim.run_id,
        runtime_tick_id=claim.tick_id,
        state_receipt_id=ArtifactId("state-receipt-a"),
        state_receipt_hash=HASH_B,
        market_state_id=ArtifactId("market-state-a"),
        etf_state_ids=(ArtifactId("etf-state-a"),),
        theme_state_ids=(ArtifactId("theme-state-a"),),
        capital_state_id=ArtifactId("capital-state-a"),
        dynamic_pool_id=ArtifactId("dynamic-pool-a"),
        candidate_set_id=ArtifactId("candidate-set-a"),
        signal_ids=(ArtifactId("signal-a"),),
        forecast_ids=(ArtifactId("forecast-a"),),
        position_snapshot_ids=(ArtifactId("fill-position-snapshot-a"),),
        model_ids=(ArtifactId("forecast-model-a"), ArtifactId("signal-model-a")),
        configuration_ids=(ArtifactId("state-config-a"),),
        as_of_time=AS_OF,
        available_at=AS_OF,
    )


def candidate(**overrides):
    values = {
        "symbol": "600000.SH",
        "dynamic_pool_membership": True,
        "etf": "510300.SH",
        "theme": "BANK",
        "candidate_rank": 1,
        "candidate_score": Decimal("0.8123456789"),
        "signal_id": ArtifactId("signal-a"),
        "signal_state": "CONFIRMED",
        "factor_coverage": Decimal("0.90"),
        "forecast_id": ArtifactId("forecast-a"),
        "forecast_bias": "POSITIVE_RESEARCH_BIAS",
        "empirical_mfe": Decimal("0.03"),
        "empirical_mae": Decimal("-0.01"),
        "sample_count": 120,
        "data_coverage": Decimal("0.95"),
        "main_evidence": ("STATE_SIGNAL_FORECAST_ALIGNED",),
        "counter_evidence": ("FORMAL_OOS_NOT_ESTABLISHED",),
        "risk_points": ("FREE_DATA_EXPLORATORY",),
        "invalidation_conditions": ("SIGNAL_INVALIDATED",),
        "valid_until": datetime(2026, 8, 7, 6, 45, tzinfo=UTC),
        "current_quantity": 100,
        "research_exposure_ceiling": Decimal("0.08"),
        "risk_result": "PENDING_INDEPENDENT_RISK",
        "model_qualification": "QUALIFIED",
        "liquidity": Decimal("0.80"),
        "orderability": "ORDERABLE",
    }
    values.update(overrides)
    return SummaryCandidate(**values)


def summary(*, claim, observation_id, reconciliation_id, **overrides):
    values = {
        "account_id": "manual-account-a",
        "trading_date": TRADING_DATE,
        "strategy_configuration_id": ArtifactId("strategy-config-a"),
        "strategy_configuration_hash": HASH_A,
        "as_of_time": AS_OF,
        "available_at": AS_OF,
        "lifecycle_state": DecisionWindowState.PREVIEW_AVAILABLE,
        "outcome": DailyDecisionOutcome.RESEARCH_BUY_CANDIDATE,
        "manual_observation_id": observation_id,
        "reconciliation_id": reconciliation_id,
        "lineage": lineage(claim),
        "candidates": (candidate(),),
        "revision": 1,
        "previous_summary_id": None,
        "correction_of_summary_id": None,
        "idempotency_key": "daily-summary-1",
        "created_at": AS_OF,
    }
    values.update(overrides)
    return DailyDecisionWindowSummary.create(**values)
