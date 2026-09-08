"""PostgreSQL closure must reproduce Context's Decimal result exactly."""
from decimal import Decimal, localcontext

import psycopg
import pytest

from market_regime_alpha.infrastructure.postgres.schema import SchemaManager


def test_context_true_rate_preserves_28_significant_digits(target_database_url):
    SchemaManager(target_database_url).bootstrap()
    counts = [(25, 31), (1, 3), (1, 31), (30, 31), (0, 31), (31, 31),
              (1, 2), (1, 9223372036854775807)]
    with psycopg.connect(target_database_url) as connection:
        for positive, available in counts:
            actual = connection.execute(
                "SELECT mra.context_true_rate(%s::bigint, %s::bigint)",
                (positive, available),
            ).fetchone()[0]
            with localcontext() as context:
                context.prec = 28
                expected = Decimal(positive) / Decimal(available)
            assert actual == expected
        assert connection.execute("SELECT mra.context_true_rate(0, 0)").fetchone() == (None,)
        with pytest.raises(psycopg.Error):
            connection.execute("SELECT mra.context_true_rate(2, 1)")
