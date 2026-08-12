from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import psycopg
import pytest

from market_regime_alpha.universe.postgres_runtime_scope import (
    PostgresRuntimeScopeRepository,
)
from market_regime_alpha.universe.runtime_scope_operator import (
    PostgresRuntimeScopeOperator,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.market_data import AssetType, Exchange, FormalPitStatus
from market_regime_alpha.universe.operational import (
    ListingStatus,
    OperationalLiquidityEvidence,
    OperationalUniverseArtifact,
    OperationalUniverseRecord,
    STStatus,
    SuspensionStatus,
)
from market_regime_alpha.universe.postgres_research import (
    PostgresFreeResearchUniverseRepository,
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


def _operational_universe(
    source_id: ArtifactId = ArtifactId("free-operational-universe-source"),
    *,
    first_included: bool = True,
    first_listing_status: ListingStatus = ListingStatus.LISTED,
) -> OperationalUniverseArtifact:
    records = tuple(
        OperationalUniverseRecord(
            symbol=symbol,
            asset_type=AssetType.A_SHARE,
            exchange=Exchange.SZ,
            membership_source="FREE_A_SHARE_OPERATIONAL_UNIVERSE",
            listing_status=(
                first_listing_status if symbol == "000001.SZ" else ListingStatus.LISTED
            ),
            st_status=st_status,
            suspension_status=SuspensionStatus.NOT_SUSPENDED,
            liquidity_evidence=OperationalLiquidityEvidence(
                lookback_sessions=20,
                observed_sessions=20,
                median_daily_amount=Decimal("200000000"),
                minimum_daily_amount=Decimal("100000000"),
                available_at=KNOWN_AT,
                source_artifact_id=source_id,
                source_content_hash=_snapshot().snapshot_hash,
            ),
            history_sessions_observed=300,
            history_sessions_required=250,
            included=(
                first_included
                if symbol == "000001.SZ"
                else st_status is STStatus.NOT_ST
            ),
            inclusion_reasons=("FREE_DATA_OPERATIONAL_ELIGIBLE",)
            if st_status is STStatus.NOT_ST
            and (symbol != "000001.SZ" or first_included)
            else (),
            exclusion_reasons=(
                ("PROVIDER_EXCLUDED",)
                if symbol == "000001.SZ" and not first_included
                else ("ST_STATUS_ST",) if st_status is STStatus.ST else ()
            ),
            source_artifact_references=((source_id, _snapshot().snapshot_hash),),
            data_eligibility=DataEligibility.EXPLORATORY,
        )
        for symbol, st_status in (
            ("000001.SZ", STStatus.NOT_ST),
            ("000002.SZ", STStatus.ST),
        )
    )
    return OperationalUniverseArtifact.create(
        decision_date=AS_OF.date(),
        effective_at=AS_OF,
        available_at=KNOWN_AT,
        records=records,
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        data_eligibility=DataEligibility.EXPLORATORY,
        source_artifact_references=((source_id, _snapshot().snapshot_hash),),
        limitations=(
            "FORMAL_PIT_NOT_ESTABLISHED",
            "FREE_DATA_EXPLORATORY",
        ),
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


def test_runtime_scope_operator_builds_full_a_from_owned_free_inputs_and_replays(
    postgres_factory,
) -> None:
    snapshot = PostgresFreeResearchUniverseRepository(postgres_factory).publish(
        _snapshot()
    )
    operator = PostgresRuntimeScopeOperator(postgres_factory)

    built = operator.build(
        policy=_policy(),
        as_of=AS_OF,
        built_at=KNOWN_AT,
        security_master_snapshot_id=snapshot.snapshot_id,
        operational_universes=(_operational_universe(),),
        code_revision="phase-d-runtime-scope",
    )

    assert built.requested_symbols == ("000001.SZ",)
    assert built.record_for("000002.SZ").decision.value == "EXCLUDED"
    assert built.record_for("689999.SH").decision.value == "UNKNOWN"
    assert operator.replay(built.scope_id) == built


def test_runtime_scope_operator_conservatively_combines_overlapping_free_providers(
    postgres_factory,
) -> None:
    snapshot = PostgresFreeResearchUniverseRepository(postgres_factory).publish(
        _snapshot()
    )
    operator = PostgresRuntimeScopeOperator(postgres_factory)

    built = operator.build(
        policy=_policy(),
        as_of=AS_OF,
        built_at=KNOWN_AT,
        security_master_snapshot_id=snapshot.snapshot_id,
        operational_universes=(
            _operational_universe(ArtifactId("baostock-operational-source")),
            _operational_universe(ArtifactId("tencent-operational-source")),
        ),
        code_revision="phase-d-runtime-scope-cross-provider",
    )

    provider_references = tuple(
        item
        for item in built.record_for("000001.SZ").source_references
        if item.artifact_kind == "OPERATIONAL_UNIVERSE"
    )
    assert built.requested_symbols == ("000001.SZ",)
    assert len(provider_references) == 2
    assert operator.replay(built.scope_id) == built


def test_runtime_scope_operator_cannot_readmit_provider_or_listing_exclusion(
    postgres_factory,
) -> None:
    snapshot = PostgresFreeResearchUniverseRepository(postgres_factory).publish(
        _snapshot()
    )
    operator = PostgresRuntimeScopeOperator(postgres_factory)

    built = operator.build(
        policy=_policy(),
        as_of=AS_OF,
        built_at=KNOWN_AT,
        security_master_snapshot_id=snapshot.snapshot_id,
        operational_universes=(
            _operational_universe(ArtifactId("provider-includes")),
            _operational_universe(
                ArtifactId("provider-excludes"),
                first_included=False,
                first_listing_status=ListingStatus.DELISTED,
            ),
        ),
        code_revision="phase-d-runtime-scope-exclusion-priority",
    )

    record = built.record_for("000001.SZ")
    assert record.decision.value == "EXCLUDED"
    assert "PROVIDER_EXCLUDED" in record.reason_codes
    assert "SECURITY_NOT_LISTED" in record.reason_codes


def test_runtime_scope_operator_rejects_substituted_operational_projection(
    postgres_factory,
) -> None:
    snapshot = PostgresFreeResearchUniverseRepository(postgres_factory).publish(
        _snapshot()
    )
    operator = PostgresRuntimeScopeOperator(postgres_factory)
    built = operator.build(
        policy=_policy(),
        as_of=AS_OF,
        built_at=KNOWN_AT,
        security_master_snapshot_id=snapshot.snapshot_id,
        operational_universes=(_operational_universe(),),
        code_revision="phase-d-runtime-scope",
    )

    with postgres_factory.connection() as connection:
        connection.execute(
            "ALTER TABLE runtime_scope_operational_input DISABLE TRIGGER "
            "runtime_scope_operational_input_no_update"
        )
        connection.execute(
            "UPDATE runtime_scope_operational_input "
            "SET universe_hash = %s WHERE scope_id = %s",
            ("sha256:" + "0" * 64, str(built.scope_id)),
        )
        connection.execute(
            "ALTER TABLE runtime_scope_operational_input ENABLE TRIGGER "
            "runtime_scope_operational_input_no_update"
        )

    with pytest.raises(ValueError, match="Operational Universe projection diverged"):
        operator.replay(built.scope_id)
    with pytest.raises(ValueError, match="Operational Universe projection diverged"):
        PostgresRuntimeScopeRepository(postgres_factory).publish(
            policy=_policy(),
            receipt=built,
            operational_universes=(_operational_universe(),),
        )
