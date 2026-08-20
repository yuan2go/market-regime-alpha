from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal, localcontext

import pytest

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId, FillId, ManualTradeId, ModelId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.evidence.envelope import ArtifactEnvelope, EvidenceAuthority
from market_regime_alpha.execution.manual import FILL_SCHEMA, Fill, FillKind, TradeSide
from market_regime_alpha.research.candidate_discovery.contracts import (
    CandidateSelectionStatus,
    CandidateSet,
)
from market_regime_alpha.strategies.defaults import (
    canonical_exploratory_strategy_registry,
)
from market_regime_alpha.strategies.portfolio import (
    CrossStrategyPortfolioPolicy,
    build_cross_strategy_portfolio,
)
from market_regime_alpha.strategies.runtime import MultiStrategyRuntime
from market_regime_alpha.strategies.sleeves import (
    allocate_observed_fill,
    project_strategy_sleeves,
)
from tests.strategies.test_multi_strategy_runtime import (
    NOW,
    _candidate,
    _registry,
    _runtime_input,
)


def _fill(
    name: str,
    *,
    side: TradeSide,
    quantity: int,
    price: float,
    minute: int,
    correction_of: FillId | None = None,
) -> Fill:
    return Fill(
        schema_version=FILL_SCHEMA,
        fill_id=FillId(f"fill-{name}"),
        manual_trade_id=ManualTradeId("manual-trade-multi-strategy"),
        account_id="account-a",
        symbol="000001.SZ",
        side=side,
        quantity=quantity,
        price=price,
        fees=0.0,
        occurred_at=NOW + timedelta(minutes=minute),
        recorded_at=NOW + timedelta(minutes=minute, seconds=1),
        actor="human-trader-a",
        reason="observed manual fill",
        external_fill_id=f"external-{name}",
        fill_kind=(FillKind.CORRECTION if correction_of is not None else FillKind.EXECUTION),
        correction_of_fill_id=correction_of,
    )


def _portfolio():
    registry = _registry()
    cycle = MultiStrategyRuntime(registry).execute(_runtime_input(registry.active_versions))
    decision = build_cross_strategy_portfolio(
        cycle=cycle,
        policy=CrossStrategyPortfolioPolicy(
            maximum_gross_weight=Decimal("0.50"),
            maximum_symbol_weight=Decimal("0.20"),
        ),
    )
    return registry, cycle, decision


def test_cross_strategy_portfolio_caps_symbol_and_prioritizes_reduction() -> None:
    registry, cycle, decision = _portfolio()

    proposal_count = sum(len(run.proposals) for run in cycle.runs)
    assert len(decision.lines) == proposal_count == 4
    assert {line.strategy_version_reference.artifact_id for line in decision.lines} == set(registry.active_version_ids)
    symbol_one = tuple(line for line in decision.lines if line.symbol == "000001.SZ")
    assert sum((line.accepted_weight for line in symbol_one), Decimal("0")) == Decimal("0.20")
    symbol_two = tuple(line for line in decision.lines if line.symbol == "000002.SZ")
    reduction = next(line for line in symbol_two if line.requested_weight < 0)
    addition = next(line for line in symbol_two if line.requested_weight > 0)
    assert reduction.accepted_weight == reduction.requested_weight
    assert addition.accepted_weight == 0
    assert "OPPOSING_REDUCTION_PRIORITY" in addition.reason_codes
    assert decision.production_authorized is False


def test_portfolio_gross_is_the_exact_sum_of_accepted_fractional_lines() -> None:
    registry = canonical_exploratory_strategy_registry()
    symbols = (
        "001872.SZ",
        "001965.SZ",
        "002714.SZ",
        "600018.SH",
        "600028.SH",
        "600036.SH",
        "600050.SH",
        "600377.SH",
        "600886.SH",
        "600900.SH",
        "600941.SH",
        "601006.SH",
        "601088.SH",
        "601225.SH",
        "601288.SH",
        "601398.SH",
        "601728.SH",
        "601857.SH",
        "601919.SH",
        "601939.SH",
    )
    records = tuple(
        _candidate(
            symbol,
            CandidateSelectionStatus.SELECTED,
            score=0.90,
            rank=1,
        )
        for symbol in sorted(symbols)
    )
    payload = {
        "records": [item.to_canonical_dict() for item in records],
        "minimum_candidate_population": 2,
        "reason_codes": ["COMPLETE_RECONCILIATION"],
    }
    envelope = ArtifactEnvelope.create(
        artifact_type="CANDIDATE_SET",
        artifact_payload=payload,
        decision_date=NOW.date(),
        decision_time=DecisionTime(NOW),
        created_at=NOW,
        code_revision="test-code",
        configuration_id=ArtifactId("candidate-config-test"),
        configuration_hash=canonical_hash({"candidate": "config"}),
        source_manifest_id=ArtifactId("candidate-source-test"),
        source_manifest_hash=canonical_hash({"candidate": "source"}),
        input_artifact_ids=(),
        input_content_hashes=(),
        model_id=ModelId("candidate-model-test"),
        model_version="1.0.0",
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status="RESEARCH_READY",
        reason_codes=("COMPLETE_RECONCILIATION",),
        limitations=("PIT_INCOMPLETE",),
    )
    candidates = CandidateSet(
        envelope=envelope,
        records=records,
        minimum_candidate_population=2,
        reason_codes=("COMPLETE_RECONCILIATION",),
    )
    runtime_input = replace(
        _runtime_input(registry.active_versions),
        candidate_set=candidates,
        positions=(),
    )
    cycle = MultiStrategyRuntime(registry).execute(runtime_input)

    decision = build_cross_strategy_portfolio(
        cycle=cycle,
        policy=CrossStrategyPortfolioPolicy(
            maximum_gross_weight=Decimal("0.50"),
            maximum_symbol_weight=Decimal("0.20"),
        ),
    )

    with localcontext() as context:
        context.prec = 64
        accepted_sum = sum(
            (
                max(Decimal("0"), line.accepted_weight)
                for line in decision.lines
            ),
            Decimal("0"),
        )
    assert decision.gross_accepted_weight == accepted_sum
    assert decision.gross_accepted_weight == Decimal("0.50")


def test_portfolio_identity_does_not_depend_on_process_decimal_context() -> None:
    registry = canonical_exploratory_strategy_registry()
    cycle = MultiStrategyRuntime(registry).execute(
        replace(_runtime_input(registry.active_versions), positions=())
    )
    policy = CrossStrategyPortfolioPolicy(
        maximum_gross_weight=Decimal("0.50"),
        maximum_symbol_weight=Decimal("0.20"),
    )

    with localcontext() as context:
        context.prec = 8
        low_precision = build_cross_strategy_portfolio(cycle=cycle, policy=policy)
    with localcontext() as context:
        context.prec = 50
        high_precision = build_cross_strategy_portfolio(cycle=cycle, policy=policy)

    assert low_precision == high_precision


def test_strategy_sleeves_can_only_be_projected_from_fully_allocated_observed_fill() -> None:
    _, _, decision = _portfolio()
    entry_lines = tuple(line for line in decision.lines if line.symbol == "000001.SZ")
    fill = _fill("buy-1", side=TradeSide.BUY, quantity=100, price=10.0, minute=1)
    batch = allocate_observed_fill(
        fill=fill,
        allocations=(
            (
                entry_lines[0].strategy_version_reference,
                entry_lines[0].proposal_reference,
                60,
            ),
            (
                entry_lines[1].strategy_version_reference,
                entry_lines[1].proposal_reference,
                40,
            ),
        ),
    )

    sleeves = project_strategy_sleeves((batch,))

    assert tuple(sorted(item.quantity for item in sleeves)) == (40, 60)
    assert sum(item.quantity for item in sleeves) == fill.quantity
    assert all(item.average_cost == Decimal("10.0") for item in sleeves)
    assert all(item.source_fill_ids == (fill.fill_id,) for item in sleeves)
    assert project_strategy_sleeves(()) == ()

    with pytest.raises(ValueError, match="fully allocated"):
        allocate_observed_fill(
            fill=fill,
            allocations=(
                (
                    entry_lines[0].strategy_version_reference,
                    entry_lines[0].proposal_reference,
                    60,
                ),
            ),
        )


def test_fill_correction_replaces_original_sleeve_allocation_during_replay() -> None:
    _, _, decision = _portfolio()
    entry_lines = tuple(line for line in decision.lines if line.symbol == "000001.SZ")

    def allocation_rows(first: int, second: int) -> tuple[tuple[RuntimeArtifactReference, RuntimeArtifactReference, int], ...]:
        return (
            (
                entry_lines[0].strategy_version_reference,
                entry_lines[0].proposal_reference,
                first,
            ),
            (
                entry_lines[1].strategy_version_reference,
                entry_lines[1].proposal_reference,
                second,
            ),
        )

    original = _fill("buy-original", side=TradeSide.BUY, quantity=100, price=10.0, minute=1)
    correction = _fill(
        "buy-correction",
        side=TradeSide.BUY,
        quantity=80,
        price=10.0,
        minute=2,
        correction_of=original.fill_id,
    )
    sell = _fill("sell-1", side=TradeSide.SELL, quantity=20, price=11.0, minute=3)
    batches = (
        allocate_observed_fill(fill=original, allocations=allocation_rows(60, 40)),
        allocate_observed_fill(fill=correction, allocations=allocation_rows(50, 30)),
        allocate_observed_fill(fill=sell, allocations=allocation_rows(10, 10)),
    )

    replayed = project_strategy_sleeves(tuple(reversed(batches)))

    assert tuple(sorted(item.quantity for item in replayed)) == (20, 40)
    assert all(original.fill_id not in item.source_fill_ids for item in replayed)
    assert all(correction.fill_id in item.source_fill_ids for item in replayed)
