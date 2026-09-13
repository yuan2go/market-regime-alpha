"""Canonical batch adapter for evidenced constant baseline inputs."""

from decimal import Decimal
from typing import Protocol
from uuid import UUID

from market_regime_alpha.research_qualification.domain.backtest_dataset import BacktestDatasetFeatureCell, BacktestFeatureDependency, BacktestFeatureLineageKind as Kind
from market_regime_alpha.research_qualification.domain.research_intercept import INTERCEPT_CODE, INTERCEPT_SHA256
from market_regime_alpha.research_qualification.domain.vocabulary import FeatureCellStatus
from market_regime_alpha.research_qualification.ports.backtest_actions import BacktestFeatureExecutionDefinition, BacktestFeatureRequest


class ResearchInterceptInputs(Protocol):
    def listing_identities(self, requests: tuple[BacktestFeatureRequest, ...]) -> dict[UUID, tuple[UUID, UUID]]: ...


class ResearchInterceptFeatureAdapter:
    def __init__(self, inputs: ResearchInterceptInputs) -> None:
        self._inputs = inputs

    def supports(self, definition: BacktestFeatureExecutionDefinition) -> bool:
        return (definition.algorithm_code, definition.algorithm_version, str(definition.algorithm_sha256)) == (INTERCEPT_CODE, "1", INTERCEPT_SHA256)

    def materialize(self, request: BacktestFeatureRequest) -> BacktestDatasetFeatureCell:
        return self.materialize_batch((request,))[0]

    def materialize_batch(self, requests: tuple[BacktestFeatureRequest, ...]) -> tuple[BacktestDatasetFeatureCell, ...]:
        if not requests:
            return ()
        first = requests[0]
        if any(not self.supports(r.definition) or (r.scope,r.session_date,r.session_close_at,r.definition) !=
                (first.scope,first.session_date,first.session_close_at,first.definition) for r in requests) or len({r.instrument_id for r in requests}) != len(requests):
            raise ValueError("research intercept requires one exact shared scope, definition and unique population")
        identities = self._inputs.listing_identities(requests)
        return tuple(BacktestDatasetFeatureCell(r.definition.feature_definition_id, FeatureCellStatus.AVAILABLE,
            "EXACT_ARCHIVED_LISTING_INTERCEPT", Kind.INSTRUMENT_FACT, identities[r.instrument_id.value][0], Decimal(1),
            (BacktestFeatureDependency(Kind.TRADING_SESSION, identities[r.instrument_id.value][1]),)) for r in requests)
