from __future__ import annotations

from datetime import timedelta

import psycopg
import pytest

from market_regime_alpha.universe.postgres_research import (
    PostgresFreeResearchUniverseRepository,
)
from tests.universe.test_free_research_universe import KNOWN_AT, _snapshot


def test_free_research_universe_is_append_only_idempotent_and_asof_queryable(
    postgres_factory,
) -> None:
    repository = PostgresFreeResearchUniverseRepository(postgres_factory)
    snapshot = _snapshot()

    assert repository.publish(snapshot) == snapshot
    assert repository.publish(snapshot) == snapshot
    assert repository.get(snapshot.snapshot_id) == snapshot
    assert repository.latest_known_at(
        as_of_date=snapshot.as_of_date,
        known_at=KNOWN_AT,
    ) == snapshot
    with pytest.raises(KeyError, match="known at that time"):
        repository.latest_known_at(
            as_of_date=snapshot.as_of_date,
            known_at=KNOWN_AT - timedelta(seconds=1),
        )
    with postgres_factory.connection() as connection, pytest.raises(
        psycopg.errors.RaiseException,
        match="free_data_research_universe_snapshot is append-only",
    ):
        connection.execute(
            "UPDATE free_data_research_universe_snapshot "
            "SET payload_json = payload_json WHERE snapshot_id = %s",
            (str(snapshot.snapshot_id),),
        )
