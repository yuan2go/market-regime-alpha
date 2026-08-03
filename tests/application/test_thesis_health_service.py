from __future__ import annotations

import pytest

import market_regime_alpha.execution  # noqa: F401  # existing package initialization order
from market_regime_alpha.application.trading_lifecycle import (
    ThesisHealthApplicationService,
)
from market_regime_alpha.position import (
    ThesisHealth,
    ThesisHealthInputBundle,
    ThesisInvalidationRuleSet,
)
from market_regime_alpha.position.sqlite_thesis_health import (
    SQLiteThesisHealthRepository,
)

from tests.position.test_thesis_health_builder import _bundle
from tests.position.thesis_health_fixtures import make_h5_fixture


def test_application_service_builds_persists_and_replays_same_command(tmp_path) -> None:
    repository = SQLiteThesisHealthRepository(tmp_path / "health.sqlite3")
    service = ThesisHealthApplicationService(repository)
    fixture = make_h5_fixture()
    bundle = _bundle(fixture)

    first = service.assess(input_bundle=bundle, idempotency_key="health-service")
    replay = service.assess(input_bundle=bundle, idempotency_key="health-service")

    assert first == replay
    assert first.observed_health_state is ThesisHealth.HEALTHY
    assert repository.get_observation(first.observation_id) == first
    assert fixture.thesis.state.value == "APPROVED"


def test_application_service_rejects_same_key_for_different_semantics(tmp_path) -> None:
    service = ThesisHealthApplicationService(
        SQLiteThesisHealthRepository(tmp_path / "health.sqlite3")
    )
    bundle = _bundle(make_h5_fixture())
    service.assess(input_bundle=bundle, idempotency_key="semantic-conflict")

    with pytest.raises(ValueError, match="idempotency key reused"):
        service.assess(
            input_bundle=ThesisHealthInputBundle.create(
                **{
                    **{
                        name: getattr(bundle, name)
                        for name in (
                            "thesis",
                            "opportunity",
                            "market_regime",
                            "theme_rotation",
                            "capital_evolution",
                            "candidate_set",
                            "signal_snapshot",
                            "path_forecast",
                            "price_snapshot",
                            "configuration",
                            "rule_set",
                            "manual_evidence",
                            "prior_observation",
                            "assessed_at",
                            "actor",
                        )
                    },
                    "reason": "different operator reason",
                }
            ),
            idempotency_key="semantic-conflict",
        )


def test_application_service_rejects_incomplete_rule_set_before_persistence(tmp_path) -> None:
    repository = SQLiteThesisHealthRepository(tmp_path / "health.sqlite3")
    service = ThesisHealthApplicationService(repository)
    bundle = _bundle(make_h5_fixture())
    invalid_rules = ThesisInvalidationRuleSet.create(
        thesis_id=bundle.thesis.thesis_id,
        thesis_version=bundle.thesis.version,
        rules=bundle.rule_set.rules[:-1],
    )
    invalid_bundle = ThesisHealthInputBundle.create(
        **{
            name: invalid_rules if name == "rule_set" else getattr(bundle, name)
            for name in (
                "thesis",
                "opportunity",
                "market_regime",
                "theme_rotation",
                "capital_evolution",
                "candidate_set",
                "signal_snapshot",
                "path_forecast",
                "price_snapshot",
                "configuration",
                "rule_set",
                "manual_evidence",
                "prior_observation",
                "assessed_at",
                "actor",
                "reason",
            )
        }
    )

    with pytest.raises(ValueError, match="THESIS_INVALIDATION_RULESET_NOT_ESTABLISHED"):
        service.assess(
            input_bundle=invalid_bundle,
            idempotency_key="incomplete-rules",
        )
