from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from market_regime_alpha.application.historical_corpus.postgres_temporal_validation_window import (
    PostgresTemporalValidationWindowAuthority,
)
from market_regime_alpha.application.historical_corpus.temporal_validation_window import (
    freeze_temporal_validation_window,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.core.identity import DatasetId
from market_regime_alpha.data.trading_calendar import (
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)


def test_temporal_validation_window_is_owner_reloaded_and_idempotent(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    start = date(2025, 7, 15)
    dates = tuple(start + timedelta(days=index) for index in range(127))
    calendar = build_trading_calendar_artifact(
        source_dataset_id=DatasetId("calendar-source-owner-test"),
        market="A_SHARE",
        calendar_version="temporal-validation-owner-test/v1",
        timezone_name="Asia/Shanghai",
        sessions=tuple(
            TradingSession(
                item,
                datetime.combine(item, time(15), ZoneInfo("Asia/Shanghai")),
            )
            for item in dates
        ),
    )
    window = freeze_temporal_validation_window(
        calendar=calendar,
        start_decision_session=start,
        session_count=126,
    )
    authority = PostgresTemporalValidationWindowAuthority(
        PostgresResearchValidationRepository(postgres_factory)
    )
    recorded_at = datetime(2026, 8, 21, tzinfo=UTC)

    assert authority.record(
        calendar=calendar,
        window=window,
        recorded_at=recorded_at,
    ) == window
    assert authority.record(
        calendar=calendar,
        window=window,
        recorded_at=recorded_at,
    ) == window
    assert authority.get(window.reference) == window
