from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
import psycopg

import pytest

from market_regime_alpha.application.continuous_research.policy import ContinuousSessionPhase
from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.application.state_system.postgres_repository import (
    PostgresStateSystemRepository,
)
from market_regime_alpha.application.state_system.repository import (
    StateArtifactWrite,
    StateDomain,
    StateSystemConflict,
    StateSystemIntegrityError,
)
from market_regime_alpha.core.identity import ArtifactId, DatasetId, ModelId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.research.state_system.common import StateLineage
from market_regime_alpha.research.state_system.configuration import DynamicPoolConfiguration
from market_regime_alpha.research.state_system.pool import (
    DynamicPoolStateContext,
    DynamicStockPoolVersion,
    PoolEligibilityObservation,
    evaluate_dynamic_pool,
)
from tests.persistence.postgres.test_continuous_research_journal import (
    NOW,
    MutableClock,
    _command,
    _tick,
)
from tests.persistence.postgres.conftest import postgres_factory as postgres_factory


def _configuration() -> DynamicPoolConfiguration:
    return DynamicPoolConfiguration.create(
        configuration_id=ArtifactId("dynamic-pool-config-v1"),
        configuration_version="1.0.0",
        allowed_etf_states=("LEADING", "STRENGTHENING"),
        allowed_theme_states=("LEADING", "STRENGTHENING"),
        minimum_state_dwell_seconds=120,
        minimum_evidence_coverage=Decimal("0.70"),
        material_change_threshold=Decimal("0.20"),
    )


def _pool(claim) -> DynamicStockPoolVersion:
    selected = _configuration()
    lineage = StateLineage(
        continuous_operation_id=claim.run_id,
        runtime_tick_id=claim.tick_id,
        provider_attempt_ids=(ArtifactId("provider-attempt-1"),),
        evidence_ids=(ArtifactId("evidence-1"),),
        dataset_id=DatasetId("dataset-1"),
        feature_id=ArtifactId("feature-1"),
        source_artifact_ids=(ArtifactId("eligibility-1"),),
        model_id=ModelId("dynamic-pool-policy"),
        model_version="1.0.0",
        configuration_id=selected.configuration_id,
        configuration_hash=selected.configuration_hash,
        as_of_time=NOW,
        available_at=NOW,
        created_at=NOW,
    )
    context = DynamicPoolStateContext(
        market_regime_state_id=ArtifactId("market-state-1"),
        market_regime_state="NEUTRAL",
        etf_rotation_states=((ArtifactId("etf-state-1"), "STRENGTHENING", 300),),
        theme_rotation_states=((ArtifactId("theme-state-1"), "STRENGTHENING", 300),),
        capital_state_id=ArtifactId("capital-state-1"),
        capital_state="EXPANSION_BIAS",
        data_coverage=Decimal("0.90"),
        available_at=NOW,
    )
    eligibility = (
        PoolEligibilityObservation(
            symbol="600000.SH",
            eligible=True,
            eligibility_reason="ELIGIBLE",
            liquidity=Decimal("0.90"),
            board="MAIN",
            is_st=False,
            suspended=False,
            listing_age_days=1000,
            theme_overlap=("AI_COMPUTE",),
            data_coverage=Decimal("0.90"),
            missing_evidence=(),
        ),
    )
    return evaluate_dynamic_pool(
        state_context=context,
        eligibility=eligibility,
        previous=None,
        configuration=selected,
        lineage=lineage,
    ).pool


def _active_claim(postgres_factory: PostgresConnectionFactory, clock: MutableClock):
    journal = PostgresContinuousResearchJournal(postgres_factory, clock=clock)
    command = _command()
    journal.create_or_get(command)
    tick = journal.admit_tick(
        _tick(command), session_phase=ContinuousSessionPhase.DECISION_WINDOW
    )
    return journal, journal.claim_tick(run_id=command.run_id, tick_id=tick.command.tick_id)


def _state_write(claim, domain: StateDomain) -> StateArtifactWrite:
    lineage = StateLineage(
        continuous_operation_id=claim.run_id,
        runtime_tick_id=claim.tick_id,
        provider_attempt_ids=(ArtifactId("provider-attempt-1"),),
        evidence_ids=(ArtifactId("evidence-1"),),
        dataset_id=DatasetId("dataset-1"),
        feature_id=ArtifactId("feature-1"),
        source_artifact_ids=(ArtifactId("observable-1"),),
        model_id=ModelId("state-model-v1"),
        model_version="1.0.0",
        configuration_id=ArtifactId("state-config-v1"),
        configuration_hash="sha256:" + "a" * 64,
        as_of_time=NOW,
        available_at=NOW,
        created_at=NOW,
    )
    prefix = domain.value.lower()
    observation_payload = {
        "schema": f"{prefix}_observation/v1",
        "lineage": lineage.identity_payload(),
    }
    observation_hash = canonical_hash(observation_payload)
    observation_id = ArtifactId(f"{prefix}-observation:{observation_hash[7:]}")
    state_payload = {
        "schema": f"{prefix}_state/v1",
        "observation_id": str(observation_id),
        "effective_state": "DATA_INSUFFICIENT",
        "lineage": lineage.identity_payload(),
    }
    state_hash = canonical_hash(state_payload)
    state_id = ArtifactId(f"{prefix}-state:{state_hash[7:]}")
    transition_payload = {
        "schema": f"{prefix}_transition/v1",
        "state_id": str(state_id),
        "lineage": lineage.identity_payload(),
    }
    transition_hash = canonical_hash(transition_payload)
    return StateArtifactWrite(
        domain=domain,
        scope_key="MARKET" if domain is not StateDomain.ETF_ROTATION else "510300.SH",
        observation_id=observation_id,
        observation_hash=observation_hash,
        observation_payload=observation_payload,
        state_id=state_id,
        state_hash=state_hash,
        previous_state_id=None,
        effective_state="DATA_INSUFFICIENT",
        state_payload=state_payload,
        transition_id=ArtifactId(f"{prefix}-transition:{transition_hash[7:]}"),
        transition_hash=transition_hash,
        transition_payload=transition_payload,
        lineage=lineage,
    )


def test_postgres_pool_write_is_fenced_idempotent_and_content_validated(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(NOW)
    _journal, claim = _active_claim(postgres_factory, clock)
    repository = PostgresStateSystemRepository(postgres_factory, clock=clock)
    pool = _pool(claim)

    first = repository.append_pool(pool, claim=claim, expected_previous_pool_id=None)
    second = repository.append_pool(pool, claim=claim, expected_previous_pool_id=None)

    assert first == second == repository.read_pool(pool.pool_id)
    assert repository.latest_pool_id(claim.run_id) == pool.pool_id


def test_postgres_persists_all_four_state_domains_with_active_fence(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(NOW)
    _journal, claim = _active_claim(postgres_factory, clock)
    repository = PostgresStateSystemRepository(postgres_factory, clock=clock)

    written = tuple(
        repository.append_state(
            _state_write(claim, domain),
            claim=claim,
            expected_previous_state_id=None,
        )
        for domain in StateDomain
    )

    assert len(written) == 4
    with postgres_factory.connection(read_only=True) as connection:
        assert connection.execute("SELECT count(*) FROM state_current_pointer").fetchone() == (4,)


def test_postgres_stale_worker_cannot_commit_pool(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(NOW)
    journal, stale = _active_claim(postgres_factory, clock)
    repository = PostgresStateSystemRepository(postgres_factory, clock=clock)
    pool = _pool(stale)
    clock.advance(timedelta(seconds=31))
    journal.resume(stale.run_id)
    fresh = journal.claim_tick(run_id=stale.run_id, tick_id=stale.tick_id)

    with pytest.raises(StateSystemConflict, match="stale"):
        repository.append_pool(pool, claim=stale, expected_previous_pool_id=None)
    assert fresh.fencing_token == stale.fencing_token + 1


def test_postgres_concurrent_identical_pool_creation_has_one_durable_row(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(NOW)
    _journal, claim = _active_claim(postgres_factory, clock)
    repository = PostgresStateSystemRepository(postgres_factory, clock=clock)
    pool = _pool(claim)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(
            executor.map(
                lambda _index: repository.append_pool(
                    pool, claim=claim, expected_previous_pool_id=None
                ),
                range(2),
            )
        )
    with postgres_factory.connection(read_only=True) as connection:
        count = connection.execute(
            "SELECT count(*) FROM dynamic_stock_pool WHERE pool_id = %s",
            (str(pool.pool_id),),
        ).fetchone()

    assert len(results) == 2
    assert count == (1,)


def test_postgres_pool_history_is_append_only(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(NOW)
    _journal, claim = _active_claim(postgres_factory, clock)
    repository = PostgresStateSystemRepository(postgres_factory, clock=clock)
    pool = _pool(claim)
    repository.append_pool(pool, claim=claim, expected_previous_pool_id=None)

    with postgres_factory.connection() as connection:
        with pytest.raises(psycopg.errors.RaiseException):
            connection.execute(
                "UPDATE dynamic_stock_pool SET pool_version = 2 WHERE pool_id = %s",
                (str(pool.pool_id),),
            )


def test_postgres_authority_survives_repository_restart(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(NOW)
    _journal, claim = _active_claim(postgres_factory, clock)
    pool = _pool(claim)
    repository = PostgresStateSystemRepository(postgres_factory, clock=clock)

    repository.append_pool(
        pool,
        claim=claim,
        expected_previous_pool_id=None,
    )
    restarted = PostgresStateSystemRepository(postgres_factory, clock=clock)

    assert restarted.runtime_authority is True
    assert restarted.read_pool(pool.pool_id)["pool_id"] == str(pool.pool_id)


def test_postgres_reader_rejects_tampered_pool_content(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(NOW)
    _journal, claim = _active_claim(postgres_factory, clock)
    pool = _pool(claim)
    repository = PostgresStateSystemRepository(postgres_factory, clock=clock)
    repository.append_pool(
        pool,
        claim=claim,
        expected_previous_pool_id=None,
    )
    with postgres_factory.connection() as connection:
        connection.execute(
            "DROP TRIGGER dynamic_stock_pool_no_update ON dynamic_stock_pool"
        )
        connection.execute(
            "UPDATE dynamic_stock_pool SET pool_json = replace(pool_json, '600000.SH', '600999.SH')"
        )

    with pytest.raises(StateSystemIntegrityError, match="hash mismatch"):
        repository.read_pool(pool.pool_id)


def test_postgres_state_history_supports_explicit_restart_replay(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(NOW)
    _journal, claim = _active_claim(postgres_factory, clock)
    write = _state_write(claim, StateDomain.MARKET_REGIME)
    assert PostgresStateSystemRepository(postgres_factory, clock=clock).append_state(
        write,
        claim=claim,
        expected_previous_state_id=None,
    ) == write.state_id
    restored = PostgresStateSystemRepository(
        postgres_factory,
        clock=clock,
    ).read_current_state(StateDomain.MARKET_REGIME, write.scope_key)
    assert restored is not None
    assert restored[:3] == (
        write.state_id,
        write.state_hash,
        dict(write.state_payload),
    )
    assert PostgresStateSystemRepository(postgres_factory, clock=clock).append_state(
        write,
        claim=claim,
        expected_previous_state_id=None,
    ) == write.state_id
