from __future__ import annotations

from datetime import timedelta

import psycopg
import pytest

from market_regime_alpha.universe.postgres_runtime_scope import (
    PostgresRuntimeScopeRepository,
)
from market_regime_alpha.universe.runtime_scope import build_runtime_scope
from tests.universe.test_runtime_scope import (
    AS_OF,
    KNOWN_AT,
    _eligibility,
    _policy,
    _snapshot,
)


def _receipt():
    return build_runtime_scope(
        policy=_policy(),
        as_of=AS_OF,
        built_at=KNOWN_AT,
        security_master=_snapshot(),
        eligibility_observations=(
            _eligibility("000001.SZ"),
            _eligibility("000002.SZ", is_st=True),
        ),
        membership_snapshots=(),
        code_revision="d27bc355",
    )


def test_runtime_scope_is_idempotent_reloadable_and_asof_resolved(
    postgres_factory,
) -> None:
    repository = PostgresRuntimeScopeRepository(postgres_factory)
    policy = _policy()
    receipt = _receipt()

    assert repository.publish(policy=policy, receipt=receipt) == receipt
    assert repository.publish(policy=policy, receipt=receipt) == receipt
    assert repository.get_policy(policy.policy_id) == policy
    assert repository.get(receipt.scope_id) == receipt
    assert repository.resolve(
        policy_id=policy.policy_id,
        as_of=AS_OF,
        known_at=KNOWN_AT,
    ) == receipt
    with pytest.raises(KeyError, match="known at that time"):
        repository.resolve(
            policy_id=policy.policy_id,
            as_of=AS_OF,
            known_at=KNOWN_AT - timedelta(seconds=1),
        )


def test_runtime_scope_tables_are_append_only(postgres_factory) -> None:
    repository = PostgresRuntimeScopeRepository(postgres_factory)
    receipt = repository.publish(policy=_policy(), receipt=_receipt())

    with postgres_factory.connection() as connection, pytest.raises(
        psycopg.errors.RaiseException,
        match="runtime_scope_receipt is append-only",
    ):
        connection.execute(
            "UPDATE runtime_scope_receipt SET payload_json = payload_json "
            "WHERE scope_id = %s",
            (str(receipt.scope_id),),
        )


def test_runtime_scope_reload_detects_projection_corruption(postgres_factory) -> None:
    repository = PostgresRuntimeScopeRepository(postgres_factory)
    receipt = repository.publish(policy=_policy(), receipt=_receipt())

    with postgres_factory.connection() as connection:
        connection.execute(
            "ALTER TABLE runtime_scope_member DISABLE TRIGGER "
            "runtime_scope_member_no_update"
        )
        connection.execute(
            "UPDATE runtime_scope_member SET decision = 'UNKNOWN' "
            "WHERE scope_id = %s AND symbol = '000001.SZ'",
            (str(receipt.scope_id),),
        )
        connection.execute(
            "ALTER TABLE runtime_scope_member ENABLE TRIGGER "
            "runtime_scope_member_no_update"
        )

    with pytest.raises(ValueError, match="member projection diverged"):
        repository.get(receipt.scope_id)
