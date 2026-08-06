from __future__ import annotations

import pytest

from market_regime_alpha.persistence.settings import (
    DatabaseConfigurationError,
    DatabaseSettings,
)


def test_free_data_service_cannot_be_composed_with_sqlite_authority() -> None:
    with pytest.raises(DatabaseConfigurationError, match="PostgreSQL URL"):
        DatabaseSettings.from_sources(
            database_url="postgresql:///tmp/compatibility.postgres-scope",
            environ={},
        )
