"""PostgreSQL write owner for the target Market/PIT bounded context."""

from __future__ import annotations

from typing import Any

import psycopg


class _MarketRepositorySupport:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection
