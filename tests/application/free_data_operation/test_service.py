from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from market_regime_alpha.application.free_data_operation.service import (
    FreeDataOperationService,
)
from market_regime_alpha.persistence.repository_factory import RepositoryFactory
from market_regime_alpha.persistence.settings import DatabaseSettings


def test_free_data_service_rejects_sqlite_compatibility_authority(
    tmp_path: Path,
) -> None:
    repositories = RepositoryFactory(
        DatabaseSettings.from_sources(
            database_url=None,
            sqlite_path=tmp_path / "compatibility.sqlite3",
            environ={},
        )
    )

    with pytest.raises(ValueError, match="requires PostgreSQL authority"):
        FreeDataOperationService(
            repositories=repositories,
            output_root=tmp_path / "artifacts",
            code_revision="test-revision",
            clock=lambda: datetime(2026, 8, 5, tzinfo=UTC),
        )
