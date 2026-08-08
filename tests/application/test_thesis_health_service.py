from __future__ import annotations

from datetime import timedelta

import pytest

import market_regime_alpha.execution  # noqa: F401  # existing package initialization order
from market_regime_alpha.application.trading_lifecycle import (
    ThesisHealthApplicationService,
)
from market_regime_alpha.position import (
    ThesisHealth,
    ThesisHealthInputBundle,
    ThesisHealthObservationV2,
    ThesisInvalidationRuleSet,
)
from tests.postgres_path_repositories import (
    PostgresThesisHealthRepository,
)

from tests.position.test_thesis_health_builder import _bundle
from tests.position.thesis_health_fixtures import make_h5_fixture


def _assess(
    service: ThesisHealthApplicationService,
    bundle: ThesisHealthInputBundle,
    *,
    idempotency_key: str,
    reason: str | None = None,
    rule_set: ThesisInvalidationRuleSet | None = None,
    thesis: object | None = None,
    expected_prior_id=None,
    expected_prior_hash=None,
) -> ThesisHealthObservationV2:
    prior = bundle.prior_observation
    if expected_prior_id is None and expected_prior_hash is None and prior is not None:
        expected_prior_id = prior.observation_id
        expected_prior_hash = prior.content_hash
    return service.assess(
        thesis=thesis if thesis is not None else bundle.thesis,  # type: ignore[arg-type]
        opportunity=bundle.opportunity,
        market_regime=bundle.market_regime,
        theme_rotation=bundle.theme_rotation,
        capital_evolution=bundle.capital_evolution,
        candidate_set=bundle.candidate_set,
        signal_snapshot=bundle.signal_snapshot,
        path_forecast=bundle.path_forecast,
        price_snapshot=bundle.price_snapshot,
        configuration=bundle.configuration,
        rule_set=rule_set or bundle.rule_set,
        manual_evidence=bundle.manual_evidence,
        expected_prior_observation_id=expected_prior_id,
        expected_prior_observation_hash=expected_prior_hash,
        assessed_at=bundle.assessed_at,
        actor=bundle.actor,
        reason=reason or bundle.reason,
        idempotency_key=idempotency_key,
    )


def test_application_service_builds_persists_and_replays_same_command(tmp_path) -> None:
    repository = PostgresThesisHealthRepository(tmp_path / "health.postgres-scope")
    service = ThesisHealthApplicationService(repository)
    fixture = make_h5_fixture()
    bundle = _bundle(fixture)

    first = _assess(service, bundle, idempotency_key="health-service")
    replay = _assess(service, bundle, idempotency_key="health-service")

    assert first == replay
    assert first.observed_health_state is ThesisHealth.HEALTHY
    assert repository.get_observation(first.observation_id) == first
    assert fixture.thesis.state.value == "APPROVED"


def test_application_service_rejects_same_key_for_different_semantics(tmp_path) -> None:
    service = ThesisHealthApplicationService(
        PostgresThesisHealthRepository(tmp_path / "health.postgres-scope")
    )
    bundle = _bundle(make_h5_fixture())
    _assess(service, bundle, idempotency_key="semantic-conflict")

    with pytest.raises(ValueError, match="idempotency key reused"):
        _assess(
            service,
            bundle,
            idempotency_key="semantic-conflict",
            reason="different operator reason",
        )


def test_application_service_rejects_incomplete_rule_set_before_persistence(tmp_path) -> None:
    repository = PostgresThesisHealthRepository(tmp_path / "health.postgres-scope")
    service = ThesisHealthApplicationService(repository)
    bundle = _bundle(make_h5_fixture())
    invalid_rules = ThesisInvalidationRuleSet.create(
        thesis_id=bundle.thesis.thesis_id,
        thesis_version=bundle.thesis.version,
        rules=bundle.rule_set.rules[:-1],
    )
    with pytest.raises(ValueError, match="THESIS_INVALIDATION_RULESET_NOT_ESTABLISHED"):
        _assess(
            service,
            bundle,
            idempotency_key="incomplete-rules",
            rule_set=invalid_rules,
        )


def test_application_service_requires_explicit_latest_prior_after_first_observation(
    tmp_path,
) -> None:
    service = ThesisHealthApplicationService(
        PostgresThesisHealthRepository(tmp_path / "health.postgres-scope")
    )
    bundle = _bundle(make_h5_fixture())
    _assess(service, bundle, idempotency_key="first-health")

    with pytest.raises(ValueError, match="omits the latest prior"):
        _assess(service, bundle, idempotency_key="missing-prior")


def test_application_service_loads_and_verifies_expected_prior(tmp_path) -> None:
    service = ThesisHealthApplicationService(
        PostgresThesisHealthRepository(tmp_path / "health.postgres-scope")
    )
    fixture = make_h5_fixture()
    first_bundle = _bundle(fixture)
    prior = _assess(service, first_bundle, idempotency_key="prior-health")
    current_bundle = _bundle(
        fixture,
        prior_observation=prior,
        assessed_at=prior.assessed_at + timedelta(minutes=1),
    )

    with pytest.raises(ValueError, match="expected prior Observation hash mismatch"):
        _assess(
            service,
            current_bundle,
            idempotency_key="wrong-prior-hash",
            expected_prior_id=prior.observation_id,
            expected_prior_hash="sha256:" + "0" * 64,
        )

    current = _assess(
        service,
        current_bundle,
        idempotency_key="current-health",
    )
    assert current.prior_observation_id == prior.observation_id
    assert current.prior_observation_hash == prior.content_hash


def test_application_service_accepts_actual_domain_inputs_not_private_bundle(
    tmp_path,
) -> None:
    service = ThesisHealthApplicationService(
        PostgresThesisHealthRepository(tmp_path / "health.postgres-scope")
    )
    with pytest.raises(TypeError, match="thesis must be a TradingThesis"):
        _assess(
            service,
            _bundle(make_h5_fixture()),
            idempotency_key="strict-domain-inputs",
            thesis={"caller": "authored bundle"},
        )
