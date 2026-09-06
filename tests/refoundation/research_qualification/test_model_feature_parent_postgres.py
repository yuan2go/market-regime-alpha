from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest

from market_regime_alpha.infrastructure.postgres.schema import SchemaManager


@pytest.mark.parametrize('mutation', ['none', 'hash', 'identity', 'order', 'missing', 'extra', 'empty'])
def test_model_backtest_feature_parents_compare_exact_ordered_members(target_database_url, mutation):
    """Owner-specific aggregate hashes differ; ordered Feature identities must agree."""
    SchemaManager(target_database_url).bootstrap()
    model, backtest = uuid4(), uuid4()
    features = [(1, uuid4(), 'a' * 64), (2, uuid4(), 'b' * 64)]
    model_features = list(features)
    if mutation == 'hash':
        model_features[0] = (1, features[0][1], 'c' * 64)
    elif mutation == 'identity':
        model_features[0] = (1, uuid4(), 'a' * 64)
    elif mutation == 'order':
        model_features = [(1, *features[1][1:]), (2, *features[0][1:])]
    elif mutation == 'missing':
        model_features.pop()
    elif mutation == 'extra':
        model_features.append((3, uuid4(), 'c' * 64))
    elif mutation == 'empty':
        features = []
        model_features = []
    with psycopg.connect(target_database_url) as connection:
        # This isolated fixture deliberately omits unrelated parent graphs and
        # probes the database guard's relational membership boundary directly.
        connection.execute('SET LOCAL session_replication_role = replica')
        for ordinal, identity, digest in features:
            connection.execute(
                'INSERT INTO mra.exploratory_backtest_feature VALUES (%s,%s,%s,%s)',
                (backtest, ordinal, identity, digest),
            )
        for ordinal, identity, digest in model_features:
            connection.execute(
                'INSERT INTO mra.model_feature_definition VALUES (%s,%s,%s,%s,%s)',
                (model, ordinal, identity, digest, 'DECIMAL'),
            )
        assert connection.execute(
            'SELECT mra.model_backtest_feature_rosters_match(%s,%s)',
            (model, backtest),
        ).fetchone() == (mutation == 'none',)
        connection.rollback()
