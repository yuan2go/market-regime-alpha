"""PostgreSQL H4.5 reducing-risk-to-manual-intent adapter."""

from market_regime_alpha.application.operational_research.postgres_composite_repository import (
    PostgresCompositeOperationalRepository,
)
from market_regime_alpha.application.trading_lifecycle.sqlite_risk_reduction import (
    SQLiteRiskReductionManualIntentRepository,
)
from market_regime_alpha.decision.postgres_repository import (
    PostgresDecisionLifecycleRepository,
)
from market_regime_alpha.persistence.postgres.adapter import (
    PostgresRepositoryAdapter,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.portfolio.postgres_repository import (
    PostgresRiskRouteRepository,
)
from market_regime_alpha.position.postgres_thesis_health import (
    PostgresThesisHealthRepository,
)


class PostgresRiskReductionManualIntentRepository(
    PostgresRepositoryAdapter,
    SQLiteRiskReductionManualIntentRepository,
):
    """One PostgreSQL persistence seam for H4/H5/H6/H4.5 authority."""

    def __init__(self, factory: PostgresConnectionFactory) -> None:
        PostgresRepositoryAdapter.__init__(self, factory)
        self._risk_routes = PostgresRiskRouteRepository(factory)
        self._thesis_health = PostgresThesisHealthRepository(factory)
        self._decisions = PostgresDecisionLifecycleRepository(factory)
        self._composite = PostgresCompositeOperationalRepository(factory)


__all__ = ["PostgresRiskReductionManualIntentRepository"]
