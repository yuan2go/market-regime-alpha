from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from market_regime_alpha.infrastructure.backtest_features import DailyMoveBacktestFeatureAdapter
from market_regime_alpha.research_qualification.domain.daily_inputs import DailyInputMember, DailyInputState
from market_regime_alpha.research_qualification.domain.exploratory import ExploratoryRetrospectiveDatasetScope
from market_regime_alpha.research_qualification.ports.backtest_actions import BacktestFeatureExecutionDefinition, BacktestFeatureRequest
from market_regime_alpha.shared.identity import InstrumentId


def test_historical_adapter_uses_shared_daily_feature_without_intraday_fallback() -> None:
    close = datetime(2026, 8, 3, 7, tzinfo=UTC)
    cutoff = datetime(2026, 9, 7, tzinfo=UTC)
    scope = ExploratoryRetrospectiveDatasetScope(UUID(int=1), UUID(int=2), cutoff, close)
    member = DailyInputMember(
        UUID(int=3),
        DailyInputState.AVAILABLE,
        "EXACT_DAILY_BAR",
        UUID(int=4),
        UUID(int=5),
        "a" * 64,
        cutoff,
        cutoff,
        datetime(2026, 8, 3, 1, 30, tzinfo=UTC),
        close,
        Decimal("3"),
        Decimal("4"),
    )

    class Inputs:
        def archived(self, *, scope, instrument_id, session_date):
            assert scope.knowledge_cutoff == cutoff
            assert instrument_id == InstrumentId(UUID(int=3))
            assert session_date == date(2026, 8, 3)
            return member

    definition = BacktestFeatureExecutionDefinition(UUID(int=6), "a" * 64, "daily_move", "session_open_close_move_v1", "1", "b" * 64)
    adapter = DailyMoveBacktestFeatureAdapter(Inputs())
    result = adapter.materialize(BacktestFeatureRequest(definition, scope, InstrumentId(UUID(int=3)), date(2026, 8, 3), close))
    assert result.value == Decimal("0.333333333333")
    assert result.lineage_id == UUID(int=4)


def test_daily_feature_identity_rejects_changed_window_units_or_lookback():
    from dataclasses import replace
    import pytest
    from market_regime_alpha.research_qualification.domain.daily_protocol import daily_feature_definition
    from market_regime_alpha.research_qualification.domain.model import ArtifactBinding

    definition = daily_feature_definition(
        UUID(int=10), ArtifactBinding(UUID(int=11), "a" * 64, 1), ArtifactBinding(UUID(int=12), "b" * 64, 1)
    )
    for change in ({"window_value": 2}, {"lookback_value": 1}, {"value_unit": "CNY"}, {"frequency_value": 2}):
        with pytest.raises(ValueError, match="daily Feature"):
            replace(definition, **change)
