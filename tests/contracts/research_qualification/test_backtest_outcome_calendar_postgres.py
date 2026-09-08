from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from market_regime_alpha.infrastructure.postgres.queries.backtest_actions import PostgresBacktestActionReadPort
from market_regime_alpha.runtime.errors import ArtifactIntegrityError, RuntimeNotFoundError
from tests.contracts.research_qualification import test_backtest_postgres as _backtests
from tests.contracts.research_qualification import test_exploratory_backtest_postgres as _legacy


@pytest.fixture
def backtest_stack(target_database_url, tmp_path, request):
    return _backtests.backtest_stack.__wrapped__(target_database_url, tmp_path, request)


def test_outcome_calendar_is_bounded_and_extends_beyond_decision_roster(backtest_stack):
    specification = _backtests._current_specification(backtest_stack)
    reads = PostgresBacktestActionReadPort(backtest_stack.pool)
    sessions = reads.outcome_sessions(
        specification,
        reference_session_id=specification.last_trading_session_id,
        maximum_offset=1,
    )
    assert len(sessions) == 2
    assert sessions[0].trading_session_id == specification.last_trading_session_id
    # January 9 is deliberately absent from this engineering Calendar fixture.
    # Calendar Authority, never a weekday inference, supplies the next session.
    assert tuple(s.session_date.isoformat() for s in sessions) == ("2026-01-08", "2026-01-12")
    with pytest.raises(RuntimeNotFoundError, match="horizon"):
        reads.outcome_sessions(specification, reference_session_id=specification.last_trading_session_id, maximum_offset=10)


def test_outcome_calendar_rejects_intervening_session_known_after_archive_seal(backtest_stack):
    stack = backtest_stack
    specification = _backtests._current_specification(stack)
    capture = stack.market.capture(
        _legacy.CaptureRequest(
            provider_product_id=stack.product.provider_product_id,
            capture_key="late-calendar-session",
            resource="fixture://late-calendar",
            request_headers_hash="c" * 64,
        ),
        _legacy._research._BytesProvider(),
        _legacy._context("late-calendar-capture"),
    )
    session = _legacy.TradingSession(
        session_id=uuid4(),
        exchange="XSHG",
        session_date=datetime(2026, 1, 9).date(),
        timezone_name="Asia/Shanghai",
        open_at=datetime(2026, 1, 9, 1, 30, tzinfo=UTC),
        break_start_at=datetime(2026, 1, 9, 3, 30, tzinfo=UTC),
        break_end_at=datetime(2026, 1, 9, 5, tzinfo=UTC),
        close_at=datetime(2026, 1, 9, 7, tzinfo=UTC),
        decision_reference_at=datetime(2026, 1, 9, 6, 55, tzinfo=UTC),
        source_capture_id=capture.capture.capture_id,
    )
    stack.market.normalize(
        capture.capture.capture_id,
        _legacy._research._Normalizer(
            lambda observed: _legacy.NormalizationBatch(
                source_capture_id=observed.capture_id,
                source_provider_product_id=observed.provider_product_id,
                trading_sessions=(session,),
            )
        ),
        _legacy._context("late-calendar-normalize"),
    )
    with pytest.raises(ArtifactIntegrityError, match="known.*cutoff"):
        PostgresBacktestActionReadPort(stack.pool).outcome_sessions(
            specification,
            reference_session_id=specification.last_trading_session_id,
            maximum_offset=1,
        )
