"""PostgreSQL Model Registry and Experiment Governance adapters."""

from market_regime_alpha.persistence.postgres.adapter import (
    PostgresRepositoryAdapter,
)
from market_regime_alpha.platform.sqlite_governance import (
    SQLiteExperimentGovernanceRepository,
    SQLiteModelRegistryRepository,
)


class PostgresModelRegistryRepository(
    PostgresRepositoryAdapter,
    SQLiteModelRegistryRepository,
):
    """PostgreSQL implementation of ModelRegistryRepository."""


class PostgresExperimentGovernanceRepository(
    PostgresRepositoryAdapter,
    SQLiteExperimentGovernanceRepository,
):
    """PostgreSQL implementation of ExperimentGovernanceRepository."""


__all__ = [
    "PostgresExperimentGovernanceRepository",
    "PostgresModelRegistryRepository",
]
