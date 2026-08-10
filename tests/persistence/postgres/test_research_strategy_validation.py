from __future__ import annotations

from datetime import UTC, datetime

import psycopg
import pytest

from market_regime_alpha.application.continuous_research.contracts import RuntimeTickCommand
from market_regime_alpha.application.continuous_research.policy import ContinuousSessionPhase
from market_regime_alpha.application.continuous_research.postgres_journal import PostgresContinuousResearchJournal
from market_regime_alpha.application.continuous_research.runtime_authority_evidence import (
    PostgresRuntimeAuthorityEvidenceRepository,
    RuntimeAuthorityEvidence,
)
from market_regime_alpha.application.research_validation.common import ValidationArtifactReference
from market_regime_alpha.application.research_validation.factor_extraction import (
    FactorFamily,
    ResearchFactorExposure,
    ResearchPanelEnrichment,
)
from market_regime_alpha.application.research_validation.postgres_repository import PostgresResearchValidationRepository
from market_regime_alpha.application.shadow_research.attestation import ClockMode, RuntimeOrigin
from market_regime_alpha.application.strategy_shadow.operations import (
    StrategyShadowEventKind,
    StrategyShadowSession,
    StrategyShadowSessionStatus,
    replay_strategy_shadow,
)
from market_regime_alpha.application.strategy_shadow.postgres_repository import PostgresStrategyShadowRepository
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode
from tests.persistence.postgres.test_free_data_continuous_runtime import _calendar, _configuration, _continuous_command


def _ref(kind: str, name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(kind, ArtifactId(name), canonical_hash({"name": name}))


def _runtime(factory: PostgresConnectionFactory):
    now = datetime(2026, 8, 10, 6, 55, tzinfo=UTC)
    calendar = _calendar()
    configuration = _configuration(calendar)
    command = _continuous_command(("000001.SZ",), calendar, configuration, RuntimeAuthorityMode.SHADOW)
    tick = RuntimeTickCommand.create(
        idempotency_key="research-strategy-validation-tick",
        run_id=command.run_id,
        trading_date=command.trading_date,
        observed_at=now,
        request_scope_hash=command.request_scope_hash,
        provider_configuration_id=command.provider_configuration_id,
        provider_configuration_hash=command.provider_configuration_hash,
        research_configuration_id=command.research_configuration_id,
        research_configuration_hash=command.research_configuration_hash,
        authority_mode=command.authority_mode,
    )
    journal = PostgresContinuousResearchJournal(factory, clock=lambda: now)
    journal.create_or_get(command)
    journal.admit_tick(tick, session_phase=ContinuousSessionPhase.DECISION_WINDOW)
    return command, tick, now


def test_runtime_authority_evidence_is_durable_and_append_only(postgres_factory: PostgresConnectionFactory) -> None:
    command, tick, now = _runtime(postgres_factory)
    repository = PostgresRuntimeAuthorityEvidenceRepository(postgres_factory)
    evidence = RuntimeAuthorityEvidence.create(
        run_id=command.run_id,
        tick_id=tick.tick_id,
        clock_mode=ClockMode.SIMULATED,
        runtime_origin=RuntimeOrigin.FIXTURE,
        clock_source="PYTEST_SIMULATED_CLOCK",
        origin_source="PYTEST_FIXTURE",
        observed_at=now,
        recorded_at=now,
        code_revision=command.code_revision,
    )

    assert repository.record(evidence) == evidence
    assert repository.get(command.run_id, tick.tick_id) == evidence
    with postgres_factory.connection() as connection, pytest.raises(psycopg.errors.RaiseException):
        connection.execute("DELETE FROM continuous_runtime_authority_evidence WHERE evidence_id = %s", (str(evidence.evidence_id),))


def test_panel_enrichment_and_strategy_shadow_replay_on_postgres(postgres_factory: PostgresConnectionFactory) -> None:
    command, tick, now = _runtime(postgres_factory)
    panel_ref = _ref("RESEARCH_PANEL_V2", "panel-v2")
    exposure = ResearchFactorExposure(
        symbol="000001.SZ",
        family=FactorFamily.PRICE,
        factor_id="bar.close",
        timeframe="DAILY",
        raw_numeric=None,
        raw_text=None,
        normalized_exposure=None,
        model_contribution=None,
        gate_result="MISSING",
        missingness=("CANONICAL_VALUE_MISSING",),
        available_at=None,
        source_reference=panel_ref,
        source_value_path="bars.missing.close",
    )
    enrichment = ResearchPanelEnrichment.create(panel_reference=panel_ref, exposures=(exposure,), extracted_at=now)
    validation = PostgresResearchValidationRepository(postgres_factory)
    validation.record_panel_enrichment(enrichment)
    assert validation.get_payload(enrichment.enrichment_id) == enrichment.identity_payload()

    session = StrategyShadowSession.schedule(
        trading_date=command.trading_date,
        scheduled_for=now,
        research_shadow_reference=_ref("SHADOW_DECISION", "shadow-decision"),
        runtime_run_reference=ValidationArtifactReference("RUNTIME_RUN", command.run_id, command.command_hash),
        runtime_tick_reference=ValidationArtifactReference("RUNTIME_TICK", tick.tick_id, tick.tick_hash),
        policy_reference=_ref("STRATEGY_SHADOW_POLICY", "strategy-policy"),
        created_at=now,
    )
    strategy = PostgresStrategyShadowRepository(postgres_factory)
    assert strategy.save(session, expected_revision=None) == session
    running = session.append(event_kind=StrategyShadowEventKind.STARTED, occurred_at=now, status=StrategyShadowSessionStatus.RUNNING)
    restored = strategy.save(running, expected_revision=1)

    assert replay_strategy_shadow(restored) == running
    with pytest.raises(ValueError, match="CAS conflict"):
        strategy.save(running, expected_revision=1)
