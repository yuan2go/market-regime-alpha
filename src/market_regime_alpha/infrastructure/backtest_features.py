"""Explicit supported Feature adapters for generic Backtest materialization."""

from __future__ import annotations

from datetime import timedelta

from market_regime_alpha.research_qualification.domain.daily_inputs import DailyInputState, session_open_close_move
from market_regime_alpha.research_qualification.ports.daily_inputs import DailyFeatureInputReadPort

from market_regime_alpha.research_qualification.domain.backtest_dataset import (
    BacktestDatasetFeatureCell,
    BacktestFeatureLineageKind,
)
from market_regime_alpha.research_qualification.domain.vocabulary import (
    FeatureCellStatus,
)
from market_regime_alpha.research_qualification.ports.backtest_actions import (
    BacktestFeatureExecutionDefinition,
    BacktestFeatureRequest,
)
from market_regime_alpha.research_qualification.ports.exploratory_feature_inputs import (
    ExploratoryFeatureInputReadPort,
    ExploratoryIntradayFeatureGap,
)


class IntradayMoveBacktestFeatureAdapter:
    """Concrete adapter for the frozen ``intraday_move`` Feature family."""

    def __init__(self, inputs: ExploratoryFeatureInputReadPort) -> None:
        self._inputs = inputs

    def supports(self, definition: BacktestFeatureExecutionDefinition) -> bool:
        return definition.algorithm_code == "intraday_move"

    def materialize(
        self,
        request: BacktestFeatureRequest,
    ) -> BacktestDatasetFeatureCell:
        if not self.supports(request.definition):
            raise ValueError("Feature adapter does not support this definition")
        observed = self._inputs.exact_intraday_move(
            scope=request.scope,
            instrument_id=request.instrument_id,
            session_date=request.session_date,
            feature_event_end=request.session_close_at - timedelta(minutes=5),
        )
        if isinstance(observed, ExploratoryIntradayFeatureGap):
            status = {
                "MISSING": FeatureCellStatus.MISSING,
                "PLACEHOLDER": FeatureCellStatus.MISSING,
                "PROVIDER_FAILURE": FeatureCellStatus.UNKNOWN,
                "CONFLICT": FeatureCellStatus.CONFLICT,
                "INVALID_OHLC": FeatureCellStatus.CONFLICT,
            }[observed.gap_kind]
            return BacktestDatasetFeatureCell(
                request.definition.feature_definition_id,
                status,
                f"ARCHIVE_{observed.reason_code}",
                BacktestFeatureLineageKind.SOURCE_GAP,
                observed.gap_id,
                None,
            )
        return BacktestDatasetFeatureCell(
            request.definition.feature_definition_id,
            FeatureCellStatus.AVAILABLE,
            "EXACT_ARCHIVED_BAR",
            BacktestFeatureLineageKind.BAR_REVISION,
            observed.bar_revision_id,
            observed.intraday_move,
        )


class DailyMoveBacktestFeatureAdapter:
    """Complete-session Feature; five-minute semantics use a separate adapter."""

    def __init__(self, inputs: DailyFeatureInputReadPort) -> None:
        self._inputs = inputs

    def supports(self, definition: BacktestFeatureExecutionDefinition) -> bool:
        return definition.algorithm_code == "session_open_close_move_v1" and definition.algorithm_version == "1"

    def materialize(self, request: BacktestFeatureRequest) -> BacktestDatasetFeatureCell:
        if not self.supports(request.definition):
            raise ValueError("unsupported daily Feature definition")
        member = self._inputs.archived(scope=request.scope, instrument_id=request.instrument_id, session_date=request.session_date)
        if member.state is DailyInputState.AVAILABLE:
            if member.event_end != request.session_close_at:
                raise ValueError("daily Feature does not cover the complete session")
            assert member.bar_revision_id is not None and member.open_value is not None and member.close_value is not None
            return BacktestDatasetFeatureCell(request.definition.feature_definition_id, FeatureCellStatus.AVAILABLE,
                "EXACT_ARCHIVED_DAILY_BAR", BacktestFeatureLineageKind.BAR_REVISION,
                member.bar_revision_id, session_open_close_move(member.open_value, member.close_value))
        if member.source_gap_id is None:
            raise ValueError("unavailable historical Feature requires canonical SourceGap")
        state = FeatureCellStatus.CONFLICT if member.state is DailyInputState.CONFLICT else FeatureCellStatus.MISSING
        return BacktestDatasetFeatureCell(request.definition.feature_definition_id, state, member.reason_code,
            BacktestFeatureLineageKind.SOURCE_GAP, member.source_gap_id, None)


__all__ = ["DailyMoveBacktestFeatureAdapter", "IntradayMoveBacktestFeatureAdapter"]
