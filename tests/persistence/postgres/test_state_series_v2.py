from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Callable

import pytest

from market_regime_alpha.application.continuous_research.contracts import (
    ContinuousResearchCommand,
    RuntimeTickCommand,
)
from market_regime_alpha.application.continuous_research.policy import (
    ContinuousRunState,
    ContinuousSessionPhase,
    default_continuous_decision_window_policy,
)
from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.application.continuous_research.journal import RuntimeTickReceipt
from market_regime_alpha.application.state_system.postgres_repository import (
    PostgresStateSystemRepository,
)
from market_regime_alpha.application.state_system.repository import (
    StateArtifactWrite,
    StateDomain,
    StateSystemConflict,
)
from market_regime_alpha.core.identity import ArtifactId, DatasetId, ModelId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode
from market_regime_alpha.research.state_system.authority import (
    StateAuthorityDomain,
    StateSeries,
    StateTransitionPolicy,
    engineering_state_transition_policy,
)
from market_regime_alpha.research.state_system.common import StateLineage


HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64
LIMITATIONS = (
    "ENTRY_BLOCKED",
    "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
    "FORMAL_PIT_NOT_ESTABLISHED",
    "NO_BROKER_AUTHORITY",
)


def _clock(at: datetime) -> Callable[[], datetime]:
    return lambda: at


def _series(policy: StateTransitionPolicy, *, configuration_hash: str = HASH_C) -> StateSeries:
    return StateSeries.create(
        domain=StateAuthorityDomain.MARKET_REGIME,
        logical_scope="A_SHARE_MARKET",
        research_family="FREE_DATA_STATE_RESEARCH",
        authority_mode="SHADOW",
        universe_policy_id=ArtifactId("universe-policy-v1"),
        universe_policy_hash=HASH_A,
        model_id=ModelId("market-state-model"),
        model_version="1.0.0",
        configuration_id=ArtifactId("market-state-config"),
        configuration_hash=configuration_hash,
        state_policy_id=policy.policy_id,
        state_policy_version=policy.policy_version,
        state_policy_hash=policy.policy_hash,
    )


def _claim(
    factory: PostgresConnectionFactory,
    *,
    trading_date: date,
    minute: int = 42,
):
    now = datetime(
        trading_date.year,
        trading_date.month,
        trading_date.day,
        6,
        minute,
        tzinfo=UTC,
    )
    runtime_policy = default_continuous_decision_window_policy()
    command = ContinuousResearchCommand.create(
        idempotency_key=f"state-series-{trading_date.isoformat()}",
        trading_date=trading_date,
        requested_symbols=("000001.SZ",),
        trading_calendar_id=ArtifactId("calendar-v1"),
        trading_calendar_hash=HASH_A,
        policy_id=runtime_policy.policy_id,
        policy_hash=runtime_policy.content_hash,
        provider_configuration_id=ArtifactId("provider-v1"),
        provider_configuration_hash=HASH_B,
        research_configuration_id=ArtifactId("research-v1"),
        research_configuration_hash=HASH_C,
        code_revision="phase-a-test",
        authority_mode=RuntimeAuthorityMode.SHADOW,
        limitations=LIMITATIONS,
    )
    tick = RuntimeTickCommand.create(
        idempotency_key=f"state-series-tick-{trading_date.isoformat()}-{minute}",
        run_id=command.run_id,
        trading_date=trading_date,
        observed_at=now,
        request_scope_hash=command.request_scope_hash,
        provider_configuration_id=command.provider_configuration_id,
        provider_configuration_hash=command.provider_configuration_hash,
        research_configuration_id=command.research_configuration_id,
        research_configuration_hash=command.research_configuration_hash,
    )
    journal = PostgresContinuousResearchJournal(factory, clock=lambda: now)
    journal.create_or_get(command)
    journal.admit_tick(tick, session_phase=ContinuousSessionPhase.DECISION_WINDOW)
    return journal, journal.claim_tick(run_id=command.run_id, tick_id=tick.tick_id), now


def _write(
    claim,
    at: datetime,
    *,
    series: StateSeries,
    policy: StateTransitionPolicy,
    previous: ArtifactId | None,
) -> StateArtifactWrite:
    lineage = StateLineage(
        continuous_operation_id=claim.run_id,
        runtime_tick_id=claim.tick_id,
        provider_attempt_ids=(ArtifactId("provider-attempt"),),
        evidence_ids=(ArtifactId("evidence"),),
        dataset_id=DatasetId("dataset"),
        feature_id=ArtifactId("feature"),
        source_artifact_ids=(ArtifactId("market-observation"),),
        model_id=series.model_id,
        model_version=series.model_version,
        configuration_id=series.configuration_id,
        configuration_hash=series.configuration_hash,
        as_of_time=at,
        available_at=at,
        created_at=at,
        state_series_id=series.series_id,
        state_series_hash=series.series_hash,
        state_policy_id=policy.policy_id,
        state_policy_version=policy.policy_version,
        state_policy_hash=policy.policy_hash,
    )
    observation_payload = {
        "schema": "market_regime_observation/v1",
        "lineage": lineage.identity_payload(),
    }
    observation_hash = canonical_hash(observation_payload)
    observation_id = ArtifactId(f"market-observation:{observation_hash[7:]}")
    state_payload = {
        "schema": "market_regime_state/v1",
        "observation_id": str(observation_id),
        "previous_state_id": None if previous is None else str(previous),
        "effective_state": "NEUTRAL",
        "lineage": lineage.identity_payload(),
    }
    state_hash = canonical_hash(state_payload)
    state_id = ArtifactId(f"market-state:{state_hash[7:]}")
    transition_payload = {
        "schema": "market_regime_transition/v1",
        "state_id": str(state_id),
        "previous_state_id": None if previous is None else str(previous),
        "lineage": lineage.identity_payload(),
    }
    transition_hash = canonical_hash(transition_payload)
    return StateArtifactWrite(
        domain=StateDomain.MARKET_REGIME,
        scope_key=series.logical_scope,
        observation_id=observation_id,
        observation_hash=observation_hash,
        observation_payload=observation_payload,
        state_id=state_id,
        state_hash=state_hash,
        previous_state_id=previous,
        effective_state="NEUTRAL",
        state_payload=state_payload,
        transition_id=ArtifactId(f"market-transition:{transition_hash[7:]}"),
        transition_hash=transition_hash,
        transition_payload=transition_payload,
        lineage=lineage,
        state_series=series,
        state_policy=policy,
    )


def test_state_series_crosses_friday_to_monday_and_replays_identically(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    policy = engineering_state_transition_policy(StateAuthorityDomain.MARKET_REGIME)
    series = _series(policy)
    previous = None
    writes: list[StateArtifactWrite] = []
    for trading_date in (date(2026, 8, 7), date(2026, 8, 10), date(2026, 8, 11)):
        _journal, claim, at = _claim(postgres_factory, trading_date=trading_date)
        write = _write(claim, at, series=series, policy=policy, previous=previous)
        PostgresStateSystemRepository(postgres_factory, clock=_clock(at)).append_state(
            write,
            claim=claim,
            expected_previous_state_id=previous,
        )
        writes.append(write)
        previous = write.state_id

    expected = tuple(
        (write.state_id, write.previous_state_id, write.lineage.continuous_operation_id, write.lineage.as_of_time) for write in writes
    )
    restarted = PostgresStateSystemRepository(postgres_factory, apply_migrations=False)

    assert restarted.read_series_chain(series.series_id) == expected
    assert restarted.read_series_chain(series.series_id) == PostgresStateSystemRepository(
        postgres_factory, apply_migrations=False
    ).read_series_chain(series.series_id)
    assert [item.previous_state_id for item in writes] == [None, writes[0].state_id, writes[1].state_id]
    current = restarted.read_current_series_state(StateDomain.MARKET_REGIME, series.series_id)
    assert current is not None and current[0] == writes[-1].state_id


def test_state_series_rejects_stale_predecessor_and_resets_on_policy_or_config_change(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    policy = engineering_state_transition_policy(StateAuthorityDomain.MARKET_REGIME)
    series = _series(policy)
    _journal, first_claim, first_at = _claim(postgres_factory, trading_date=date(2026, 8, 12))
    first = _write(first_claim, first_at, series=series, policy=policy, previous=None)
    repository = PostgresStateSystemRepository(postgres_factory, clock=lambda: first_at)
    repository.append_state(first, claim=first_claim, expected_previous_state_id=None)

    _journal, second_claim, second_at = _claim(postgres_factory, trading_date=date(2026, 8, 13))
    repository = PostgresStateSystemRepository(postgres_factory, clock=lambda: second_at)
    stale = _write(second_claim, second_at, series=series, policy=policy, previous=None)
    with pytest.raises(StateSystemConflict, match="predecessor"):
        repository.append_state(stale, claim=second_claim, expected_previous_state_id=None)

    changed_configuration = _series(policy, configuration_hash=HASH_B)
    reset = _write(
        second_claim,
        second_at,
        series=changed_configuration,
        policy=policy,
        previous=None,
    )
    assert (
        repository.append_state(
            reset,
            claim=second_claim,
            expected_previous_state_id=None,
        )
        == reset.state_id
    )
    assert changed_configuration.series_id != series.series_id
    assert repository.read_series_chain(changed_configuration.series_id)[0][1] is None

    changed_policy = StateTransitionPolicy.create(
        domain=StateAuthorityDomain.MARKET_REGIME,
        policy_version="engineering-v2",
        thresholds=policy.thresholds,
        transition_parameters=dict(policy.transition_parameters),
    )
    policy_reset_series = _series(changed_policy)
    policy_reset = _write(
        second_claim,
        second_at,
        series=policy_reset_series,
        policy=changed_policy,
        previous=None,
    )
    assert (
        repository.append_state(
            policy_reset,
            claim=second_claim,
            expected_previous_state_id=None,
        )
        == policy_reset.state_id
    )
    assert policy_reset_series.series_id != series.series_id


def test_state_series_advances_across_multiple_ticks_on_the_same_day(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    policy = engineering_state_transition_policy(StateAuthorityDomain.MARKET_REGIME)
    series = _series(policy)
    journal, first_claim, first_at = _claim(
        postgres_factory,
        trading_date=date(2026, 8, 14),
        minute=42,
    )
    first = _write(first_claim, first_at, series=series, policy=policy, previous=None)
    PostgresStateSystemRepository(postgres_factory, clock=_clock(first_at)).append_state(
        first,
        claim=first_claim,
        expected_previous_state_id=None,
    )
    journal.complete_tick(
        claim=first_claim,
        receipt=RuntimeTickReceipt.create(
            claim=first_claim,
            input_references=(),
            output_references=(),
            reason_codes=("STATE_SERIES_TEST_COMPLETED",),
            created_at=first_at,
        ),
        run_state=ContinuousRunState.WAITING_FOR_NEW_DATA,
    )
    _journal, second_claim, second_at = _claim(
        postgres_factory,
        trading_date=date(2026, 8, 14),
        minute=43,
    )
    second = _write(
        second_claim,
        second_at,
        series=series,
        policy=policy,
        previous=first.state_id,
    )
    repository = PostgresStateSystemRepository(postgres_factory, clock=_clock(second_at))
    repository.append_state(
        second,
        claim=second_claim,
        expected_previous_state_id=first.state_id,
    )

    assert repository.read_series_chain(series.series_id) == (
        (first.state_id, None, first_claim.run_id, first_at),
        (second.state_id, first.state_id, second_claim.run_id, second_at),
    )
