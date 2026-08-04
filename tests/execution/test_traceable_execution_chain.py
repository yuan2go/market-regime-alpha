from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.application.trading_lifecycle import (
    CompleteAccountPortfolioRiskApplicationService,
    PositionAuthoritativePortfolioRiskApplicationService,
    TraceableManualExecutionApplicationService,
)
from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    ManualTradeId,
    ModelId,
    OpportunityId,
    ThesisId,
)
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.decision import (
    DecisionEvidenceReference,
    DecisionModelReference,
    InvalidationCondition,
    InvalidationKind,
    OpportunityState,
    ThesisState,
    TradingOpportunity,
    TradingThesis,
)
from market_regime_alpha.decision.opportunity import TRADING_OPPORTUNITY_SCHEMA
from market_regime_alpha.decision.thesis import TRADING_THESIS_SCHEMA
from market_regime_alpha.data import TradingSession, build_trading_calendar_artifact
from market_regime_alpha.execution import (
    PositionBook,
    SQLiteTraceableManualExecutionRepository,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.evaluation import (
    TRADE_EVALUATION_CONFIG_SCHEMA,
    TradeEvaluationConfig,
    TradePathObservation,
    TraceableTradeOutcome,
    TraceableTradeOutcomeEvaluator,
)
from market_regime_alpha.execution.manual import (
    TRACEABLE_MANUAL_TRADE_SCHEMA,
    ManualOrderState,
    ManualTradeRecord,
    TradeSide,
)
from market_regime_alpha.execution.sqlite_repository import (
    insert_manual_trade_event,
    serialize_manual_execution_json,
)
from market_regime_alpha.execution.sqlite_traceability import (
    EXECUTION_TRACEABILITY_DOWN_MIGRATION,
)
from market_regime_alpha.portfolio import (
    RISK_BUDGET_SCHEMA,
    AccountPortfolioCompleteness,
    AccountPosition,
    AccountReconciliationState,
    AuthoritativeAccountPortfolioSnapshot,
    CompleteAccountRiskConfiguration,
    PortfolioOutputMode,
    PositionRiskValuationInput,
    RiskBudget,
    SQLiteCompleteAccountPortfolioRiskRepository,
    ThesisAllocationRequest,
)
from market_regime_alpha.position import (
    PositionProjector,
    PositionState,
    SymbolTradingSessionStatus,
    SymbolTradingState,
)


TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 7, 20, 14, 55, tzinfo=TZ)


def _sha(character: str) -> str:
    return "sha256:" + character * 64


def _evidence(label: str, character: str) -> DecisionEvidenceReference:
    return DecisionEvidenceReference(
        artifact_type=label,
        artifact_id=ArtifactId(f"artifact-{label.lower()}-{character}"),
        content_hash=_sha(character),
        status="VERIFIED_EXPLORATORY",
    )


def _opportunity(index: int, *, valid_until: datetime | None = None) -> TradingOpportunity:
    decision_time = DecisionTime(NOW - timedelta(minutes=5))
    model = DecisionModelReference(
        model_id=ModelId(f"model-trace-{index}"),
        model_version="synthetic-v1",
        configuration_id=ArtifactId(f"configuration-trace-{index}"),
        configuration_hash=_sha(format(index % 16, "x")),
    )
    return TradingOpportunity(
        schema_version=TRADING_OPPORTUNITY_SCHEMA,
        opportunity_id=OpportunityId(f"opportunity-trace-{index}"),
        symbol="000001.SZ",
        candidate_set=_evidence("CANDIDATE_SET", "a"),
        signal_snapshot=_evidence("SIGNAL_SNAPSHOT", "b"),
        path_forecast=_evidence("PATH_FORECAST", "c"),
        decision_time=decision_time,
        signal_model=model,
        forecast_model=model,
        valid_until=valid_until or NOW + timedelta(days=1),
        state=OpportunityState.CONFIRMED_TO_THESIS,
        version=1,
        created_at=NOW - timedelta(minutes=4),
        created_by="research-operator",
        creation_reason="synthetic trace fixture",
        updated_at=NOW - timedelta(minutes=3),
        last_actor="thesis-approver",
        last_reason="confirmed for synthetic fixture",
        reason_codes=("OPPORTUNITY_CONFIRMED_TO_THESIS",),
    )


def _thesis(index: int, *, opportunity: TradingOpportunity | None = None) -> TradingThesis:
    source = opportunity or _opportunity(index)
    evidence = _evidence("PATH_FORECAST", "d")
    return TradingThesis(
        schema_version=TRADING_THESIS_SCHEMA,
        thesis_id=ThesisId(f"thesis-trace-{index}"),
        opportunity_id=source.opportunity_id,
        source_opportunity_version=0,
        symbol=source.symbol,
        supporting_evidence=(evidence,),
        invalidation_conditions=(
            InvalidationCondition(
                condition_id=f"price-invalidation-{index}",
                kind=InvalidationKind.PRICE,
                description="synthetic price invalidation",
                reason_code="SYNTHETIC_PRICE_INVALIDATION",
            ),
        ),
        time_invalidation=NOW + timedelta(days=2),
        state=ThesisState.APPROVED,
        version=0,
        approved_by="thesis-approver",
        approval_reason="synthetic trace fixture",
        created_at=NOW - timedelta(minutes=2),
        updated_at=NOW - timedelta(minutes=2),
        last_actor="thesis-approver",
        last_reason="synthetic trace fixture",
    )


def _configuration() -> CompleteAccountRiskConfiguration:
    budget = RiskBudget.create(
        profile_id="test_risk_profile_v1",
        maximum_gross_exposure=1.0,
        single_symbol_limit=1.0,
        theme_limit=1.0,
        liquidity_max_participation=1.0,
        minimum_cash_reserve=0.0,
        maximum_loss_budget=1.0,
        t_plus_one_enforced=True,
        risk_service_timeout_seconds=2.0,
        market_scope="A_SHARE",
        allowed_side="LONG_ONLY",
        schema_version=RISK_BUDGET_SCHEMA,
    )
    return CompleteAccountRiskConfiguration.create(
        profile_id="test_complete_account_trace_v1",
        risk_budget=budget,
        maximum_account_snapshot_age_seconds=60.0,
        schema_version="complete-account-risk-configuration-v1",
    )


def _account(
    *,
    quantity: int = 0,
    available_quantity: int | None = None,
    position_id: ArtifactId | None = None,
    position_hash: str | None = None,
) -> AuthoritativeAccountPortfolioSnapshot:
    available = quantity if available_quantity is None else available_quantity
    positions = ()
    if quantity:
        positions = (
            AccountPosition(
                symbol="000001.SZ",
                theme_id="theme-bank",
                total_quantity=quantity,
                available_quantity=available,
                market_price=10.0,
                loss_per_share=1.0,
                source_position_snapshot_id=position_id or ArtifactId("position-fixture"),
                source_position_snapshot_hash=position_hash or _sha("e"),
            ),
        )
    return AuthoritativeAccountPortfolioSnapshot.create(
        account_id="account-a",
        as_of=NOW - timedelta(seconds=1),
        source_reference="synthetic-complete-account-trace",
        net_asset_value=100_000.0,
        available_cash=100_000.0 - quantity * 10.0,
        all_positions=positions,
        completeness=AccountPortfolioCompleteness.COMPLETE_ACCOUNT,
        reconciliation_state=AccountReconciliationState.RECONCILED,
        version=quantity,
    )


def _authority(
    tmp_path: Path,
    *,
    index: int = 1,
    quantity: int = 0,
    target: int = 100,
    opportunity: TradingOpportunity | None = None,
    thesis: TradingThesis | None = None,
):
    actual_opportunity = opportunity or _opportunity(index)
    actual_thesis = thesis or _thesis(index, opportunity=actual_opportunity)
    allocation = ThesisAllocationRequest(
        thesis_id=actual_thesis.thesis_id,
        symbol=actual_thesis.symbol,
        theme_id="theme-bank",
        target_quantity=target,
        reference_price=10.0,
        average_daily_trade_value=1_000_000.0,
        loss_per_share=1.0,
    )
    service = CompleteAccountPortfolioRiskApplicationService(
        SQLiteCompleteAccountPortfolioRiskRepository(
            tmp_path / f"risk-{index}-{quantity}-{target}.sqlite3"
        )
    )
    portfolio, risk = service.run_traceable(
        opportunities=(actual_opportunity,),
        theses=(actual_thesis,),
        allocations=(allocation,),
        account_snapshot=_account(quantity=quantity),
        configuration=_configuration(),
        mode=PortfolioOutputMode.MANUAL_CONFIRMATION,
        actor="risk-operator",
        reason="synthetic trace authority",
        portfolio_created_at=NOW,
        risk_started_at=NOW,
        risk_completed_at=NOW + timedelta(seconds=1),
        idempotency_key=f"risk-{index}-{quantity}-{target}",
    )
    return actual_opportunity, actual_thesis, portfolio, risk, allocation


def _create_trade(service: TraceableManualExecutionApplicationService, authority, key: str):
    opportunity, thesis, portfolio, risk, _ = authority
    delta = portfolio.post_trade.proposed_deltas[0]
    return service.create_trade(
        opportunity=opportunity,
        thesis=thesis,
        portfolio_decision=portfolio,
        risk_decision=risk,
        trade_delta=delta,
        account_id="account-a",
        expected_price_lower=9.8,
        expected_price_upper=10.2,
        actor="manual-operator",
        reason="synthetic traceable intent",
        created_at=NOW + timedelta(seconds=2),
        idempotency_key=key,
    )


def _insert_historical_v2_sell(
    repository: SQLiteTraceableManualExecutionRepository,
    book: PositionBook,
    authority,
) -> ManualTradeRecord:
    opportunity, thesis, portfolio, risk, _ = authority
    delta = portfolio.post_trade.proposed_deltas[0]
    record = ManualTradeRecord(
        schema_version=TRACEABLE_MANUAL_TRADE_SCHEMA,
        manual_trade_id=ManualTradeId("historical-v2-exit"),
        risk_decision_id=risk.risk_decision_id,
        risk_decision_hash=canonical_hash(risk.to_canonical_dict()),
        portfolio_decision_id=portfolio.decision_id,
        target_position_hash=canonical_hash(delta.to_canonical_dict()),
        account_id=book.account_id,
        symbol=book.symbol,
        side=TradeSide.SELL,
        intended_quantity=abs(delta.trade_quantity),
        expected_price_lower=10.8,
        expected_price_upper=11.2,
        state=ManualOrderState.RECORDED,
        filled_quantity=0,
        version=0,
        actor="historical-manual-operator",
        reason="pre-H4.5 V2 exit fixture",
        created_at=NOW + timedelta(seconds=2),
        updated_at=NOW + timedelta(seconds=2),
        last_actor="historical-manual-operator",
        last_reason="pre-H4.5 V2 exit fixture",
        position_book_id=book.position_book_id,
        thesis_id=thesis.thesis_id,
        opportunity_id=opportunity.opportunity_id,
        post_trade_snapshot_id=portfolio.post_trade.snapshot_id,
        post_trade_snapshot_hash=portfolio.post_trade.content_hash,
    )
    with sqlite3.connect(repository.path, isolation_level=None) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            INSERT INTO manual_trade_records(
                manual_trade_id, authority_route, risk_decision_id,
                risk_reducing_decision_id, risk_reduction_confirmation_id,
                account_id, symbol, side, state, filled_quantity,
                aggregate_json, version
            ) VALUES (?, 'INCREASING', ?, NULL, NULL, ?, ?, 'SELL',
                      'RECORDED', 0, ?, 0)
            """,
            (
                str(record.manual_trade_id),
                str(risk.risk_decision_id),
                book.account_id,
                book.symbol,
                serialize_manual_execution_json(record.to_canonical_dict()),
            ),
        )
        insert_manual_trade_event(connection, record, "historical-v2-exit")
        connection.execute(
            """
            INSERT INTO traceable_manual_trade_bindings(
                manual_trade_id, position_book_id, opportunity_id, thesis_id,
                portfolio_decision_id, risk_decision_id,
                post_trade_snapshot_id, post_trade_snapshot_hash,
                target_delta_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(record.manual_trade_id),
                str(book.position_book_id),
                str(opportunity.opportunity_id),
                str(thesis.thesis_id),
                str(portfolio.decision_id),
                str(risk.risk_decision_id),
                str(portfolio.post_trade.snapshot_id),
                portfolio.post_trade.content_hash,
                canonical_hash(delta.to_canonical_dict()),
                record.created_at.isoformat(),
            ),
        )
        connection.commit()
    return repository.get_trade(record.manual_trade_id)


def test_traceable_chain_restarts_and_rejects_cross_book_fill(tmp_path) -> None:
    path = tmp_path / "execution.sqlite3"
    repository = SQLiteTraceableManualExecutionRepository(path)
    service = TraceableManualExecutionApplicationService(repository)
    first_authority = _authority(tmp_path)
    book, trade = _create_trade(service, first_authority, "create-trace-1")
    assert _create_trade(service, first_authority, "create-trace-1") == (book, trade)
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE traceable_manual_trade_bindings SET thesis_id = 'forged'"
            )
    _, fill = service.record_fill(
        trade.manual_trade_id,
        external_fill_id="manual-fill-trace-1",
        quantity=100,
        price=10.0,
        fees=1.0,
        occurred_at=NOW + timedelta(minutes=1),
        recorded_at=NOW + timedelta(minutes=1, seconds=1),
        actor="manual-operator",
        reason="recorded manual fill",
        idempotency_key="fill-trace-1",
    )
    snapshot = service.rebuild_position(
        book.position_book_id, as_of=NOW + timedelta(minutes=2)
    )

    assert snapshot.position_book_id == book.position_book_id
    assert snapshot.thesis_id == book.thesis_id
    assert snapshot.source_manual_trade_ids == (trade.manual_trade_id,)
    assert snapshot.source_fill_ids == (fill.fill_id,)

    restarted = TraceableManualExecutionApplicationService(
        SQLiteTraceableManualExecutionRepository(path)
    )
    assert restarted.rebuild_position(
        book.position_book_id, as_of=NOW + timedelta(minutes=2)
    ) == snapshot

    _, correction = service.record_fill(
        trade.manual_trade_id,
        external_fill_id="manual-fill-trace-1-correction",
        quantity=80,
        price=10.1,
        fees=1.0,
        occurred_at=NOW + timedelta(minutes=1),
        recorded_at=NOW + timedelta(minutes=3),
        actor="manual-operator",
        reason="correct recorded manual fill",
        idempotency_key="fill-trace-1-correction",
        correction_of_fill_id=fill.fill_id,
    )
    corrected = service.rebuild_position(
        book.position_book_id, as_of=NOW + timedelta(minutes=4)
    )
    assert corrected.total_quantity == 80
    assert corrected.effective_fill_ids == (correction.fill_id,)
    assert corrected.source_manual_trade_ids == (trade.manual_trade_id,)
    assert TraceableManualExecutionApplicationService(
        SQLiteTraceableManualExecutionRepository(path)
    ).rebuild_position(
        book.position_book_id, as_of=NOW + timedelta(minutes=4)
    ) == corrected
    next_day = (NOW + timedelta(days=1)).date()
    calendar = build_trading_calendar_artifact(
        source_dataset_id=DatasetId("synthetic-restart-calendar"),
        market="CN_A_SHARE",
        calendar_version="synthetic-restart-v1",
        timezone_name="Asia/Shanghai",
        sessions=(
            TradingSession(trade_date=NOW.date(), session_close=NOW.replace(hour=15, minute=0)),
            TradingSession(
                trade_date=next_day,
                session_close=(NOW + timedelta(days=1)).replace(hour=15, minute=0),
            ),
        ),
    )
    status = SymbolTradingSessionStatus.create(
        symbol=book.symbol,
        session_date=NOW.date(),
        state=SymbolTradingState.TRADABLE,
        source_artifact_id=ArtifactId("synthetic-restart-status"),
        source_artifact_hash=_sha("6"),
        availability_time=NOW.replace(hour=9, minute=0),
        reason_code="SYNTHETIC_TRADABLE",
    )
    t_plus_one = service.rebuild_a_share_position(
        book.position_book_id,
        calendar=calendar,
        symbol_session_statuses=(status,),
        as_of=NOW + timedelta(minutes=4),
    )
    assert t_plus_one.available_quantity == 0
    assert TraceableManualExecutionApplicationService(
        SQLiteTraceableManualExecutionRepository(path)
    ).rebuild_a_share_position(
        book.position_book_id,
        calendar=calendar,
        symbol_session_statuses=(status,),
        as_of=NOW + timedelta(minutes=4),
    ) == t_plus_one
    hardened_risk = PositionAuthoritativePortfolioRiskApplicationService(
        execution_repository=repository,
        risk_repository=SQLiteCompleteAccountPortfolioRiskRepository(
            tmp_path / "position-authoritative-risk.sqlite3"
        ),
    )
    exit_allocation = ThesisAllocationRequest(
        thesis_id=first_authority[1].thesis_id,
        symbol=first_authority[1].symbol,
        theme_id="theme-bank",
        target_quantity=0,
        reference_price=10.0,
        average_daily_trade_value=1_000_000.0,
        loss_per_share=1.0,
    )
    account, positions, _, risk = hardened_risk.run(
        opportunities=(first_authority[0],),
        theses=(first_authority[1],),
        allocations=(exit_allocation,),
        account_id="account-a",
        account_as_of=NOW + timedelta(minutes=4),
        account_source_reference="synthetic-reconciled-manual-account",
        net_asset_value=100_000.0,
        available_cash=99_200.0,
        reconciliation_state=AccountReconciliationState.RECONCILED,
        account_version=1,
        valuations=(
            PositionRiskValuationInput(
                symbol=book.symbol,
                theme_id="theme-bank",
                market_price=10.0,
                loss_per_share=1.0,
                source_artifact_id=ArtifactId("synthetic-risk-valuation"),
                source_artifact_hash=_sha("5"),
            ),
        ),
        calendar=calendar,
        symbol_session_statuses={book.symbol: (status,)},
        configuration=_configuration(),
        mode=PortfolioOutputMode.MANUAL_CONFIRMATION,
        actor="risk-operator",
        reason="derive T+1 sellability from Position Authority",
        portfolio_created_at=NOW + timedelta(minutes=4),
        risk_started_at=NOW + timedelta(minutes=4),
        risk_completed_at=NOW + timedelta(minutes=4, seconds=1),
        idempotency_key="position-authoritative-risk",
    )
    assert account.all_positions[0].available_quantity == 0
    assert positions == (t_plus_one,)
    assert "T_PLUS_ONE_AVAILABLE_QUANTITY_EXCEEDED" in risk.reason_codes

    second_authority = _authority(tmp_path, index=2)
    second_book, second_trade = _create_trade(
        TraceableManualExecutionApplicationService(
            SQLiteTraceableManualExecutionRepository(tmp_path / "second.sqlite3")
        ),
        second_authority,
        "create-trace-2-independent",
    )
    assert second_book.position_book_id != book.position_book_id
    with pytest.raises(ValueError, match="does not belong"):
        PositionProjector().project_book(
            book=book,
            trades=repository.trades_for_book(book.position_book_id),
            fills=(replace(fill, manual_trade_id=second_trade.manual_trade_id),),
            as_of=NOW + timedelta(minutes=2),
        )


def test_one_open_thesis_per_account_symbol_and_mismatched_chain_rejected(tmp_path) -> None:
    repository = SQLiteTraceableManualExecutionRepository(tmp_path / "execution.sqlite3")
    service = TraceableManualExecutionApplicationService(repository)
    first_authority = _authority(tmp_path, index=1)
    _, first_trade = _create_trade(service, first_authority, "create-first-book")

    with pytest.raises(ValueError, match="ACTIVE Thesis"):
        _create_trade(service, _authority(tmp_path, index=2), "create-second-book")

    opportunity, thesis, portfolio, risk, _ = first_authority
    delta = portfolio.post_trade.proposed_deltas[0]
    with pytest.raises(ValueError, match="authority binding mismatch"):
        repository.create_traceable_trade(
            replace(first_trade, target_position_hash=_sha("9")),
            book=repository.get_position_book(first_trade.position_book_id),  # type: ignore[arg-type]
            opportunity=opportunity,
            thesis=thesis,
            risk_decision=risk,
            portfolio_decision=portfolio,
            trade_delta=delta,
            idempotency_key="mismatched-authority-chain",
            command_hash=_sha("8"),
        )


def test_expired_opportunity_cannot_create_traceable_risk(tmp_path) -> None:
    expired = _opportunity(9, valid_until=NOW - timedelta(seconds=1))
    thesis = _thesis(9, opportunity=expired)
    with pytest.raises(ValueError, match="expired or invalid Opportunity"):
        _authority(tmp_path, index=9, opportunity=expired, thesis=thesis)

    active = _opportunity(10)
    invalidated = replace(
        _thesis(10, opportunity=active),
        state=ThesisState.INVALIDATED,
        version=1,
    )
    with pytest.raises(ValueError, match="only APPROVED Thesis"):
        _authority(tmp_path, index=10, opportunity=active, thesis=invalidated)


def test_increasing_route_cannot_sell_or_close_position_book(tmp_path) -> None:
    repository = SQLiteTraceableManualExecutionRepository(tmp_path / "execution.sqlite3")
    service = TraceableManualExecutionApplicationService(repository)
    first_authority = _authority(tmp_path, index=1)
    book, buy = _create_trade(service, first_authority, "create-buy")
    service.record_fill(
        buy.manual_trade_id,
        external_fill_id="fill-buy",
        quantity=100,
        price=10.0,
        fees=0.0,
        occurred_at=NOW + timedelta(minutes=1),
        recorded_at=NOW + timedelta(minutes=1, seconds=1),
        actor="manual-operator",
        reason="entry",
        idempotency_key="fill-buy",
    )
    sell_authority = _authority(
        tmp_path,
        index=1,
        quantity=100,
        target=0,
        opportunity=first_authority[0],
        thesis=first_authority[1],
    )
    with pytest.raises(ValueError, match="INCREASING route requires positive OPEN/ADD"):
        _create_trade(service, sell_authority, "create-sell")

    assert repository.get_position_book(book.position_book_id).state.value == "OPEN"
    stored = repository.trades_for_book(book.position_book_id)
    assert len(stored) == 1
    assert stored[0].manual_trade_id == buy.manual_trade_id
    assert stored[0].side.value == "BUY"


def test_historical_v2_sell_path_remains_readable_and_evaluable(tmp_path) -> None:
    repository = SQLiteTraceableManualExecutionRepository(tmp_path / "execution.sqlite3")
    service = TraceableManualExecutionApplicationService(repository)
    first_authority = _authority(tmp_path, index=1)
    book, buy = _create_trade(service, first_authority, "create-buy-v2-history")
    service.record_fill(
        buy.manual_trade_id,
        external_fill_id="fill-buy-v2-history",
        quantity=100,
        price=10.0,
        fees=0.0,
        occurred_at=NOW + timedelta(minutes=1),
        recorded_at=NOW + timedelta(minutes=1, seconds=1),
        actor="manual-operator",
        reason="entry",
        idempotency_key="fill-buy-v2-history",
    )
    sell_authority = _authority(
        tmp_path,
        index=1,
        quantity=100,
        target=0,
        opportunity=first_authority[0],
        thesis=first_authority[1],
    )
    sell = _insert_historical_v2_sell(repository, book, sell_authority)
    assert sell.schema_version == TRACEABLE_MANUAL_TRADE_SCHEMA
    service.record_fill(
        sell.manual_trade_id,
        external_fill_id="fill-sell-v2-history",
        quantity=100,
        price=11.0,
        fees=0.0,
        occurred_at=NOW + timedelta(days=1),
        recorded_at=NOW + timedelta(days=1, seconds=1),
        actor="manual-operator",
        reason="historical V2 exit",
        idempotency_key="fill-sell-v2-history",
    )
    final_position = service.rebuild_position(
        book.position_book_id, as_of=NOW + timedelta(days=1, minutes=1)
    )
    assert final_position.state is PositionState.CLOSED
    closed = service.close_position_book(
        book.position_book_id,
        expected_version=0,
        final_position=final_position,
        actor="manual-operator",
        reason="authoritative historical V2 position closed",
        closed_at=NOW + timedelta(days=1, minutes=2),
        idempotency_key="close-v2-history-book",
    )
    assert closed.version == 1

    fills = repository.fills_for_book(book.position_book_id)
    trades = repository.trades_for_book(book.position_book_id)
    entry_fill = next(item for item in fills if item.side is TradeSide.BUY)
    path = TradePathObservation(
        symbol="000001.SZ",
        path_started_at=NOW,
        path_ended_at=NOW + timedelta(days=1, seconds=2),
        availability_time=NOW + timedelta(days=1, seconds=3),
        maximum_price=12.0,
        minimum_price=9.0,
        entry_reference_price=10.0,
        entry_fill_ids=(entry_fill.fill_id,),
        evidence=_evidence("TRADE_PATH", "7"),
    )
    configuration = TradeEvaluationConfig.create(
        profile_id="synthetic_trace_evaluation_v1",
        rolling_window_size=20,
        minimum_sample_count=5,
        capture_denominator_floor=0.001,
        schema_version=TRADE_EVALUATION_CONFIG_SCHEMA,
    )
    evaluator = TraceableTradeOutcomeEvaluator()
    outcome = evaluator.evaluate(
        opportunity=first_authority[0],
        thesis=first_authority[1],
        portfolio_decisions=(first_authority[2], sell_authority[2]),
        risk_decisions=(first_authority[3], sell_authority[3]),
        manual_trades=trades,
        final_position=final_position,
        fills=fills,
        path=path,
        execution_deviations=tuple(
            service.execution_deviation(item.manual_trade_id) for item in trades
        ),
        configuration=configuration,
        evaluated_at=NOW + timedelta(days=1, seconds=4),
    )
    assert (
        TraceableTradeOutcome.from_canonical_dict(outcome.to_canonical_dict())
        == outcome
    )
    with pytest.raises(ValueError, match="authority chain mismatch"):
        evaluator.evaluate(
            opportunity=first_authority[0],
            thesis=first_authority[1],
            portfolio_decisions=(first_authority[2], sell_authority[2]),
            risk_decisions=(first_authority[3], sell_authority[3]),
            manual_trades=(
                replace(trades[0], thesis_id=ThesisId("wrong-thesis")),
                *trades[1:],
            ),
            final_position=final_position,
            fills=fills,
            path=path,
            execution_deviations=tuple(
                service.execution_deviation(item.manual_trade_id)
                for item in trades
            ),
            configuration=configuration,
            evaluated_at=NOW + timedelta(days=1, seconds=4),
        )

    second, _ = _create_trade(
        service,
        _authority(tmp_path, index=2),
        "create-next-book-after-v2-history",
    )
    assert second.thesis_id == ThesisId("thesis-trace-2")


def test_traceability_migration_has_isolated_down_path(tmp_path) -> None:
    path = tmp_path / "migration.sqlite3"
    SQLiteTraceableManualExecutionRepository(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM pdl_schema_migrations WHERE version = 6"
        ).fetchone()[0] == 1
        connection.executescript(
            EXECUTION_TRACEABILITY_DOWN_MIGRATION.read_text(encoding="utf-8")
        )
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert "position_books" not in names
    assert "traceable_manual_trade_bindings" not in names
    assert "manual_fills" in names
