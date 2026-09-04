"""Explicit supported Feature adapters for generic Backtest materialization."""

from __future__ import annotations

from datetime import timedelta

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


__all__ = ["IntradayMoveBacktestFeatureAdapter"]
