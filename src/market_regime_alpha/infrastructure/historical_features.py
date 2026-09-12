"""Batch materializer for the ten pinned daily research formulas."""

from market_regime_alpha.research_qualification.domain.backtest_dataset import BacktestDatasetFeatureCell, BacktestFeatureLineageKind as Kind
from market_regime_alpha.research_qualification.domain.historical_features import FACTORS_BY_CODE, calculate_historical_features
from market_regime_alpha.research_qualification.domain.vocabulary import FeatureCellStatus
from market_regime_alpha.research_qualification.ports.backtest_actions import BacktestFeatureExecutionDefinition, BacktestFeatureRequest
from market_regime_alpha.research_qualification.ports.historical_features import HistoricalFeatureInputReadPort


class HistoricalBacktestFeatureAdapter:
    def __init__(self, inputs: HistoricalFeatureInputReadPort) -> None:
        self._inputs = inputs

    def supports(self, definition: BacktestFeatureExecutionDefinition) -> bool:
        factor = FACTORS_BY_CODE.get(definition.algorithm_code)
        return factor is not None and definition.algorithm_version == "1" and str(definition.algorithm_sha256) == factor.algorithm_sha256

    def materialize(self, request: BacktestFeatureRequest) -> BacktestDatasetFeatureCell:
        # Peer factors cannot be evaluated with an implicitly singleton universe.
        raise ValueError("historical factors require exact Dataset batch materialization")

    def materialize_batch(self, requests: tuple[BacktestFeatureRequest, ...]) -> tuple[BacktestDatasetFeatureCell, ...]:
        if not requests:
            return ()
        first = requests[0]
        if any(not self.supports(r.definition) or (r.scope, r.session_date, r.session_close_at) !=
            (first.scope, first.session_date, first.session_close_at) for r in requests):
            raise ValueError("historical batch requires exact shared scope/session and pinned formulas")
        instruments = tuple(sorted({r.instrument_id.value for r in requests}, key=str))
        features = {r.definition.feature_definition_id for r in requests}
        if {(r.instrument_id.value, r.definition.feature_definition_id) for r in requests} != {
            (i, f) for i in instruments for f in features} or len(requests) != len(instruments) * len(features):
            raise ValueError("historical batch must retain the complete population/feature rectangle")
        snapshot = self._inputs.snapshot(scope=first.scope, instruments=instruments, session_date=first.session_date)
        if snapshot.sessions[-1][2] != first.session_close_at or set(snapshot.population) != set(instruments):
            raise ValueError("historical snapshot differs from requested close/population")
        values = calculate_historical_features(tuple(s[0] for s in snapshot.sessions), snapshot.population)
        cells = []
        for request in requests:
            factor = FACTORS_BY_CODE[request.definition.algorithm_code]
            observed = values[request.instrument_id.value][factor.name]
            keys = tuple((i, d, factor.basis) for i, d in observed.dependencies)
            # Failed peers remain explicit unavailable cells in this exact
            # Dataset rectangle; their request failure cannot support a value.
            dependencies = tuple(sorted({d for key in keys for d in snapshot.dependencies[key]
                if d.identity not in snapshot.failed_request_gap_ids or (observed.value is None and key[0]==request.instrument_id.value)},
                key=lambda d: (d.kind.value, str(d.identity))))
            problems = {snapshot.problems[key] for key in keys if key in snapshot.problems and key[0]==request.instrument_id.value}
            status, reason = FeatureCellStatus.AVAILABLE, observed.reason
            if observed.value is None:
                if "FEATURE_INPUT_CONFLICT" in problems:
                    status, reason = FeatureCellStatus.CONFLICT, "FEATURE_INPUT_CONFLICT"
                elif "FEATURE_PROVIDER_UNKNOWN" in problems:
                    status, reason = FeatureCellStatus.UNKNOWN, "FEATURE_PROVIDER_UNKNOWN"
                else:
                    status = FeatureCellStatus.MISSING
                primary = next(d for d in snapshot.dependencies[(request.instrument_id.value, first.session_date, factor.basis)] if d.kind is Kind.TRADING_SESSION)
            else:
                primary = next(d for d in snapshot.dependencies[(request.instrument_id.value, first.session_date, factor.basis)] if d.kind is Kind.BAR_REVISION)
            cells.append(BacktestDatasetFeatureCell(request.definition.feature_definition_id, status, reason,
                primary.kind, primary.identity, observed.value, tuple(d for d in dependencies if d != primary)))
        return tuple(cells)
