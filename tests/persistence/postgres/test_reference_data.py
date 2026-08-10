from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest

from market_regime_alpha.data.free_operational_policy import (
    canonical_free_operational_evidence_policy,
)
from market_regime_alpha.data.postgres_reference_data import (
    PostgresETFThemeReferenceRepository,
)
from market_regime_alpha.data.reference_data import (
    ETFThemeReferenceSnapshot,
    MembershipKind,
    REFERENCE_SNAPSHOT_SCHEMA_V1,
    free_v1_reference_snapshot,
    publish_reference_snapshot,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)


def test_free_v1_reference_is_exploratory_append_only_and_replayable(
    tmp_path: Path,
    postgres_factory: PostgresConnectionFactory,
) -> None:
    available_at = datetime(2026, 8, 9, 6, 0, tzinfo=UTC)
    snapshot = free_v1_reference_snapshot(
        policy=canonical_free_operational_evidence_policy(),
        available_at=available_at,
    )
    artifact_path = publish_reference_snapshot(
        root=tmp_path / "reference-data",
        snapshot=snapshot,
    )
    repository = PostgresETFThemeReferenceRepository(postgres_factory)

    assert repository.publish(snapshot, artifact_path=artifact_path) == snapshot
    assert repository.publish(snapshot, artifact_path=artifact_path) == snapshot
    assert repository.replay(snapshot.snapshot_id) == snapshot
    assert repository.latest_as_of(
        effective_at=available_at,
        known_at=available_at,
    ) == snapshot

    legacy = ETFThemeReferenceSnapshot.create(
        reference_version="legacy-v1-replay-fixture",
        etfs=snapshot.etfs,
        themes=snapshot.themes,
        memberships=snapshot.memberships,
        mappings=snapshot.mappings,
        data_eligibility=snapshot.data_eligibility,
        evidence_ceiling=snapshot.evidence_ceiling,
        created_at=snapshot.created_at,
        limitations=snapshot.limitations,
        schema_version=REFERENCE_SNAPSHOT_SCHEMA_V1,
    )
    legacy_path = publish_reference_snapshot(
        root=tmp_path / "reference-data",
        snapshot=legacy,
    )
    assert repository.publish(legacy, artifact_path=legacy_path) == legacy
    assert repository.replay(legacy.snapshot_id) == legacy
    assert tuple(item.etf_id for item in snapshot.etfs) == ("510300.SH",)
    assert tuple(item.theme_id for item in snapshot.themes) == (
        "FREE_A_SHARE_OPERATIONAL_UNIVERSE",
    )
    assert snapshot.memberships == ()
    assert tuple((item.etf_id, item.theme_id) for item in snapshot.mappings) == (
        ("510300.SH", "FREE_A_SHARE_OPERATIONAL_UNIVERSE"),
    )
    assert {
        item.membership_kind for item in snapshot.mappings
    } == {MembershipKind.PROXY_MEMBERSHIP}
    assert snapshot.schema_version == "etf-theme-reference-snapshot/v2"

    with pytest.raises(KeyError, match="known at that time"):
        repository.latest_as_of(
            effective_at=available_at,
            known_at=available_at - timedelta(seconds=1),
        )
    with postgres_factory.connection() as connection, pytest.raises(
        psycopg.errors.RaiseException,
        match="etf_theme_reference_snapshot is append-only",
    ):
        connection.execute(
            "UPDATE etf_theme_reference_snapshot "
            "SET payload_json = payload_json WHERE snapshot_id = %s",
            (str(snapshot.snapshot_id),),
        )
