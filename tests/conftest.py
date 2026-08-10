"""Repository-wide pytest lifecycle guards."""

from __future__ import annotations

from tests.postgres_path_repositories import (
    cleanup_postgres_path_repositories,
)


def pytest_runtest_logfinish(
    nodeid: str,
    location: tuple[str, int | None, str],
) -> None:
    """Bound legacy-shaped PostgreSQL test schemas to one completed item."""

    del nodeid, location
    cleanup_postgres_path_repositories()
