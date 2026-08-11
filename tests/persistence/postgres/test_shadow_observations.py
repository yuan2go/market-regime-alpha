from __future__ import annotations

import psycopg
import pytest

from market_regime_alpha.application.strategy_shadow.observation_builder import (
    ObservationKind,
    build_observation_receipt,
)
from market_regime_alpha.application.strategy_shadow.postgres_observations import (
    PostgresShadowObservationRepository,
)
from tests.application.strategy_shadow.test_observation_builder import (
    NOW,
    _policy,
    _reference,
    _strategy_values,
)


def _receipt():
    return build_observation_receipt(
        kind=ObservationKind.STRATEGY,
        research_trading_date=NOW.date(),
        trading_date=NOW.date(),
        observed_at=NOW,
        symbol="000001.SZ",
        policy=_policy(),
        values=_strategy_values(),
        source_references=(_reference("TARGETED_OUTCOME", "b"),),
    )


def test_shadow_observation_is_idempotent_reloadable_and_replayable(
    postgres_factory,
) -> None:
    policy = _policy()
    receipt = _receipt()
    repository = PostgresShadowObservationRepository(postgres_factory)

    assert repository.publish(policy=policy, receipt=receipt) == receipt
    assert repository.publish(policy=policy, receipt=receipt) == receipt
    assert repository.get_policy(policy.policy_id) == policy
    assert repository.get(receipt.receipt_id) == receipt
    assert repository.replay(receipt.receipt_id) == receipt
    assert repository.find(
        kind=ObservationKind.STRATEGY,
        research_trading_date=NOW.date(),
        trading_date=NOW.date(),
        observed_at=NOW,
        symbol="000001.SZ",
        policy_id=policy.policy_id,
    ) == receipt


def test_shadow_observation_owner_rows_are_append_only(postgres_factory) -> None:
    policy = _policy()
    receipt = _receipt()
    repository = PostgresShadowObservationRepository(postgres_factory)
    repository.publish(policy=policy, receipt=receipt)

    with postgres_factory.connection() as connection, pytest.raises(
        psycopg.errors.RaiseException,
        match="shadow_observation_receipt is append-only",
    ):
        connection.execute(
            "UPDATE shadow_observation_receipt SET payload_json = payload_json "
            "WHERE receipt_id = %s",
            (str(receipt.receipt_id),),
        )
