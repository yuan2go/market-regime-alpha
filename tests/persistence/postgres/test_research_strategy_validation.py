from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

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
from market_regime_alpha.application.research_validation.calibration import (
    CalibrationArtifact,
    CalibrationMethod,
    CalibrationObservation,
    CalibrationPartition,
    CalibrationProtocol,
    fit_calibration,
)
from market_regime_alpha.application.research_validation.factor_extraction import (
    FactorFamily,
    ResearchFactorExposure,
    ResearchPanelEnrichment,
)
from market_regime_alpha.application.research_validation.postgres_repository import PostgresResearchValidationRepository
from market_regime_alpha.application.research_validation.samples import (
    HistoricalPathSampleRecord,
    HistoricalSampleDataset,
    HistoricalSampleQualification,
)
from market_regime_alpha.application.shadow_research.attestation import ClockMode, RuntimeOrigin
from market_regime_alpha.application.strategy_shadow.operations import (
    StrategyShadowArtifactKind,
    StrategyShadowArtifactRecord,
    StrategyShadowEventKind,
    StrategyShadowSession,
    StrategyShadowSessionStatus,
    replay_strategy_shadow,
)
from market_regime_alpha.application.strategy_shadow.postgres_repository import PostgresStrategyShadowRepository
from market_regime_alpha.core.identity import ArtifactId, TargetId
from market_regime_alpha.core.time import AvailabilityTime, DecisionTime
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.forecasting.path import PATH_FORECAST_SAMPLE_SCHEMA, PathForecastSample
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode
from market_regime_alpha.strategies.entry.contracts import EntryPathObservationStatus, EntryPathReasonCode
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
    artifact_payload = {"entry": "shadow-only"}
    artifact_reference = ValidationArtifactReference("SHADOW_ENTRY", ArtifactId("pg-shadow-entry"), canonical_hash(artifact_payload))
    artifact = StrategyShadowArtifactRecord(
        artifact_reference,
        StrategyShadowArtifactKind.ENTRY,
        session.session_id,
        artifact_payload,
        now,
    )
    with_entry = running.append(
        event_kind=StrategyShadowEventKind.ENTRY_CREATED,
        occurred_at=now,
        artifact_reference=artifact_reference,
    )
    assert strategy.save_with_artifact(with_entry, expected_revision=2, artifact=artifact) == with_entry
    with postgres_factory.connection(read_only=True) as connection:
        stored_artifact = connection.execute(
            "SELECT payload_json FROM strategy_shadow_artifact WHERE artifact_id = %s",
            (str(artifact_reference.artifact_id),),
        ).fetchone()
        stored_event = connection.execute(
            "SELECT payload_json FROM strategy_shadow_event WHERE session_id = %s AND sequence = 3",
            (str(session.session_id),),
        ).fetchone()
    assert stored_artifact is not None and stored_artifact[0] == artifact_payload
    assert stored_event is not None and stored_event[0]["artifact_reference"]["artifact_id"] == "pg-shadow-entry"
    with pytest.raises(ValueError, match="CAS conflict"):
        strategy.save(running, expected_revision=1)


def test_postgres_historical_sample_reader_cannot_invent_qualification(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    now = datetime(2026, 8, 10, 6, 55, tzinfo=UTC)
    target_id = TargetId("target-path")
    sample = PathForecastSample(
        sample_id=ArtifactId("sample-path"),
        source_artifact_id=ArtifactId("outcome-path"),
        source_content_hash=canonical_hash({"outcome": "path"}),
        symbol="000001.SZ",
        target_id=target_id,
        sample_decision_time=DecisionTime(now - timedelta(days=5)),
        available_at=AvailabilityTime(now - timedelta(days=1)),
        observation_status=EntryPathObservationStatus.AVAILABLE,
        observation_reason_code=EntryPathReasonCode.OUTCOME_RESOLVED,
        realized_mfe=0.05,
        realized_mae=-0.02,
        realized_return=0.03,
        schema_version=PATH_FORECAST_SAMPLE_SCHEMA,
    )
    target = _ref("OUTCOME_TARGET", str(target_id))
    target = ValidationArtifactReference(target.artifact_kind, ArtifactId(str(target_id)), target.content_hash)
    record = HistoricalPathSampleRecord.register_unqualified(
        sample=sample,
        target_reference=target,
        outcome_reference=_ref("FACTUAL_OUTCOME", "outcome-path"),
        pit_lineage=(),
        registered_at=now - timedelta(days=1),
    )
    repository = PostgresResearchValidationRepository(postgres_factory)
    repository.record_sample_dataset(
        HistoricalSampleDataset.create(
            registry_version="v1",
            target_reference=target,
            records=(record,),
            available_at=now - timedelta(days=1),
        )
    )
    samples, qualification, _reasons = repository.load_available_samples(
        symbol="000001.SZ",
        target_id=target_id,
        decision_time=DecisionTime(now + timedelta(seconds=1)),
    )
    assert samples == (sample,)
    assert qualification == HistoricalSampleQualification.UNQUALIFIED.value


def test_postgres_calibration_records_complete_unqualified_lineage(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    now = datetime(2026, 8, 10, 8, tzinfo=UTC)
    protocol = CalibrationProtocol.create(
        protocol_version="postgres-path-calibration-v1",
        method=CalibrationMethod.PLATT_LOGISTIC,
        minimum_fit_samples=2,
        maximum_iterations=5,
    )
    observations = (
        CalibrationObservation(
            "fit-1", Decimal("0.1"), 0, CalibrationPartition.FIT
        ),
        CalibrationObservation(
            "fit-2", Decimal("0.9"), 1, CalibrationPartition.FIT
        ),
        CalibrationObservation(
            "validation-1",
            Decimal("0.8"),
            1,
            CalibrationPartition.VALIDATION,
        ),
    )
    artifact = fit_calibration(
        protocol=protocol,
        observations=observations,
        created_at=now,
    )
    repository = PostgresResearchValidationRepository(postgres_factory)

    repository.record_calibration(
        protocol=protocol,
        artifact=artifact,
        observations=observations,
    )
    repository.record_calibration(
        protocol=protocol,
        artifact=artifact,
        observations=observations,
    )

    assert repository.get_payload(artifact.artifact_id) == artifact.identity_payload()
    with postgres_factory.connection(read_only=True) as connection:
        kinds = connection.execute(
            """
            SELECT artifact_kind, count(*)
            FROM research_validation_artifact
            GROUP BY artifact_kind ORDER BY artifact_kind
            """
        ).fetchall()
        bindings = connection.execute(
            """
            SELECT observation_id, partition_name
            FROM calibration_partition_binding
            WHERE calibration_artifact_id = %s
            ORDER BY observation_id
            """,
            (str(artifact.artifact_id),),
        ).fetchall()
    assert dict(kinds) == {
        "CALIBRATION_ARTIFACT": 1,
        "CALIBRATION_EVALUATION": 1,
        "CALIBRATION_FIT": 1,
        "CALIBRATION_PROTOCOL": 1,
    }
    assert bindings == [
        ("fit-1", "FIT"),
        ("fit-2", "FIT"),
        ("validation-1", "VALIDATION"),
    ]
    assert artifact.calibrated is False


def test_postgres_calibration_writer_rejects_caller_supplied_qualification(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    now = datetime(2026, 8, 10, 8, tzinfo=UTC)
    protocol = CalibrationProtocol.create(
        protocol_version="rejected-qualified-calibration-v1",
        method=CalibrationMethod.PLATT_LOGISTIC,
        minimum_fit_samples=2,
        maximum_iterations=5,
    )
    observations = (
        CalibrationObservation("fit-1", Decimal("0.1"), 0, CalibrationPartition.FIT),
        CalibrationObservation("fit-2", Decimal("0.9"), 1, CalibrationPartition.FIT),
        CalibrationObservation(
            "validation-1", Decimal("0.8"), 1, CalibrationPartition.VALIDATION
        ),
        CalibrationObservation("oos-1", Decimal("0.7"), 1, CalibrationPartition.OOS),
    )
    engineering = fit_calibration(
        protocol=protocol,
        observations=observations,
        created_at=now,
    )
    qualification = _ref("QUALIFICATION_EVIDENCE", "caller-supplied")
    promoted_payload = {
        **engineering.identity_payload(),
        "calibrated": True,
        "qualification_evidence": qualification.to_canonical_dict(),
    }
    promoted = CalibrationArtifact(
        artifact_id=ArtifactId("caller-supplied-calibration"),
        artifact_hash=canonical_hash(promoted_payload),
        protocol_reference=engineering.protocol_reference,
        fit=engineering.fit,
        evaluations=engineering.evaluations,
        calibrated=True,
        qualification_evidence=qualification,
        created_at=engineering.created_at,
        limitations=engineering.limitations,
    )

    with pytest.raises(ValueError, match="future owner-resolving writer"):
        PostgresResearchValidationRepository(postgres_factory).record_calibration(
            protocol=protocol,
            artifact=promoted,
            observations=observations,
        )


def test_migration_046_rejects_reference_only_authority_rows(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    now = datetime(2026, 8, 10, 6, 55, tzinfo=UTC)
    PostgresResearchValidationRepository(postgres_factory)
    dataset_id = "migration-046-dataset"
    with postgres_factory.connection() as connection:
        connection.execute(
            """
            INSERT INTO research_validation_artifact(
                artifact_id, artifact_hash, artifact_kind,
                evidence_authority, payload_json, created_at
            ) VALUES (%s, %s, 'HISTORICAL_SAMPLE_DATASET',
                      'ENGINEERING_ONLY', '{}'::jsonb, %s)
            """,
            (dataset_id, "sha256:" + "a" * 64, now),
        )

    with pytest.raises(psycopg.errors.CheckViolation):
        with postgres_factory.connection() as connection:
            connection.execute(
                """
                INSERT INTO research_validation_artifact(
                    artifact_id, artifact_hash, artifact_kind,
                    evidence_authority, qualified, payload_json, created_at
                ) VALUES ('forged-formal-oos', %s, 'FORMAL_EVALUATION_RESULT',
                          'FORMAL_OOS', true, '{}'::jsonb, %s)
                """,
                ("sha256:" + "b" * 64, now),
            )

    with pytest.raises(psycopg.errors.CheckViolation):
        with postgres_factory.connection() as connection:
            connection.execute(
                """
                INSERT INTO historical_path_sample_record(
                    record_id, record_hash, dataset_id, sample_id, symbol,
                    target_id, sample_decision_time, available_at,
                    qualification, payload_json
                ) VALUES ('forged-pit-sample', %s, %s, 'sample-046',
                          '000001.SZ', 'target-046', %s, %s,
                          'PIT_ELIGIBLE', '{}'::jsonb)
                """,
                (
                    "sha256:" + "c" * 64,
                    dataset_id,
                    now - timedelta(days=2),
                    now - timedelta(days=1),
                ),
            )
