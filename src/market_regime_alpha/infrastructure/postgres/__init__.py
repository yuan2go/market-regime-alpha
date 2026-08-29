"""PostgreSQL adapters for the target schema epoch."""

from market_regime_alpha.infrastructure.postgres.schema import (
    EXPECTED_FOUNDATION_TABLES,
    EXPECTED_MARKET_TABLES,
    EXPECTED_SELECTION_TABLES,
    EXPECTED_TARGET_TABLES,
    SCHEMA_EPOCH,
    SchemaManager,
)

__all__ = [
    "EXPECTED_FOUNDATION_TABLES",
    "EXPECTED_MARKET_TABLES",
    "EXPECTED_SELECTION_TABLES",
    "EXPECTED_TARGET_TABLES",
    "SCHEMA_EPOCH",
    "SchemaManager",
]
