from __future__ import annotations

import pytest
from psycopg.types.json import Jsonb

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
    timestamp,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    FormalResearchProtocol,
    build_outcome_target_bound_forecast,
    not_estimable_target_forecast,
)
from market_regime_alpha.application.research_validation.postgres_formal_protocol import (
    FormalProtocolFreezeScope,
    FormalProtocolConflict,
    PostgresFormalProtocolRepository,
    load_formal_protocol_owner,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.platform.contracts import ModelLifecycleStatus
from market_regime_alpha.platform.durable_governance import PersistentModelRegistry
from market_regime_alpha.platform.postgres_runtime_governance import (
    PostgresModelGovernanceRepository,
)
from tests.persistence.postgres.phase_c_owner_fixture import (
    NOW,
    freeze_phase_c_protocol,
    record_phase_c_protocol_owners,
)


def _reference(kind: str, name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(name),
        canonical_hash({"kind": kind, "name": name}),
    )


def test_formal_protocol_model_owner_freezes_current_governance_and_fails_terminal(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    fixture = record_phase_c_protocol_owners(postgres_factory)
    protocol = freeze_phase_c_protocol(
        postgres_factory,
        fixture,
        idempotency_key="model-governance-resolution-protocol",
    )
    with postgres_factory.connection(read_only=True) as connection:
        row = connection.execute(
            """
            SELECT owner_artifact_id, owner_artifact_hash,
                   owner_payload_json
            FROM formal_research_protocol_component_owner_resolution
            WHERE protocol_id = %s AND component_role = 'model_reference'
            """,
            (str(protocol.protocol_id),),
        ).fetchone()
    assert row is not None and isinstance(row[2], dict)
    resolution = row[2]["model_governance_resolution"]
    assert str(row[0]).startswith("formal-research-model-lineage-resolution:")
    assert str(row[1]) == resolution["resolution_hash"]
    assert resolution["registration"]["lifecycle_status"] == "DRAFT"
    assert resolution["registry_governance_revision"] > 0
    assert resolution["lineage_governance_revision"] > 0

    governance = PostgresModelGovernanceRepository(postgres_factory)
    current = PersistentModelRegistry(governance).get(fixture.model_lineage.model_id)
    PersistentModelRegistry(governance).transition(
        fixture.model_lineage.model_id,
        expected_version=current.version,
        idempotency_key="retire-model-after-formal-freeze",
        to_status=ModelLifecycleStatus.RETIRED,
        changed_at=NOW,
        reason="terminal governance state must invalidate Formal replay",
    )

    with pytest.raises(FormalProtocolConflict, match="lifecycle is terminal"):
        PostgresFormalProtocolRepository(postgres_factory).get_protocol(
            protocol.protocol_id
        )
    with pytest.raises(FormalProtocolConflict, match="lifecycle is terminal"):
        PostgresFormalProtocolRepository(postgres_factory).freeze_protocol(
            scope=FormalProtocolFreezeScope.from_protocol_references(fixture.protocol),
            actor="phase-c-owner-test",
            reason="terminal model cannot be frozen again",
            idempotency_key="terminal-model-formal-freeze",
        )


def test_pre_057_protocol_is_replayable_but_cannot_enter_new_formal_research(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    fixture = record_phase_c_protocol_owners(postgres_factory)
    current = freeze_phase_c_protocol(
        postgres_factory,
        fixture,
        idempotency_key="current-protocol-for-legacy-replay",
    )
    source = fixture.protocol
    assert source.experiment_definition is not None
    legacy = FormalResearchProtocol.create(
        protocol_version="legacy-056-replay",
        target_protocol=fixture.targets,
        trading_calendar=fixture.calendar,
        evaluation_protocol=fixture.evaluation,
        experiment_definition=source.experiment_definition,
        universe_reference=source.universe_reference,
        dataset_reference=source.dataset_reference,
        historical_sample_dataset_reference=(
            source.historical_sample_dataset_reference
        ),
        feature_reference=source.feature_reference,
        factor_reference=source.factor_reference,
        model_reference=source.model_reference,
        threshold_policy_reference=source.threshold_policy_reference,
        formal_oos_qualification_policy_reference=(
            source.formal_oos_qualification_policy_reference
        ),
        cost_policy_reference=source.cost_policy_reference,
        calibration_policy_reference=source.calibration_policy_reference,
        strategy_policy_reference=source.strategy_policy_reference,
        entry_holding_exit_qualification_policy_reference=(
            source.entry_holding_exit_qualification_policy_reference
        ),
        locked_at=current.locked_at,
    )
    with postgres_factory.connection() as connection:
        model_owner = connection.execute(
            """
            SELECT owner_payload_json, owner_recorded_at, resolved_at
            FROM formal_research_protocol_component_owner_resolution
            WHERE protocol_id = %s AND component_role = 'model_reference'
            """,
            (str(current.protocol_id),),
        ).fetchone()
        assert model_owner is not None and isinstance(model_owner[0], dict)
        legacy_model_payload = dict(model_owner[0])
        legacy_model_payload.pop("model_governance_resolution")
        legacy_model_payload_hash = canonical_hash(legacy_model_payload)
        connection.execute(
            """
            INSERT INTO formal_research_protocol(
                protocol_id, protocol_hash, protocol_version,
                outcome_target_protocol_id, evaluation_protocol_id,
                trading_calendar_id, trading_calendar_hash,
                payload_json, locked_at, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(legacy.protocol_id),
                legacy.protocol_hash,
                legacy.protocol_version,
                str(legacy.outcome_target_protocol_reference.artifact_id),
                str(legacy.evaluation_protocol_reference.artifact_id),
                str(legacy.trading_calendar_reference.artifact_id),
                legacy.trading_calendar_reference.content_hash,
                Jsonb(legacy.to_canonical_dict()),
                legacy.locked_at,
                legacy.locked_at,
            ),
        )
        connection.execute(
            """
            INSERT INTO formal_research_protocol_component
            SELECT %s, component_role, artifact_kind, artifact_id,
                   artifact_hash, payload_json
            FROM formal_research_protocol_component
            WHERE protocol_id = %s AND component_role <> 'model_reference'
            """,
            (str(legacy.protocol_id), str(current.protocol_id)),
        )
        connection.execute(
            """
            INSERT INTO formal_research_protocol_component(
                protocol_id, component_role, artifact_kind,
                artifact_id, artifact_hash, payload_json
            ) VALUES (%s, 'model_reference', 'MODEL_VERSION_LINEAGE',
                      %s, %s, %s)
            """,
            (
                str(legacy.protocol_id),
                str(legacy.model_reference.artifact_id),
                legacy.model_reference.content_hash,
                Jsonb(legacy_model_payload),
            ),
        )
        connection.execute(
            """
            INSERT INTO formal_research_protocol_component_owner_resolution
            SELECT %s, component_role, artifact_kind, artifact_id,
                   artifact_hash, owner_kind, owner_artifact_id,
                   owner_artifact_hash, owner_payload_hash,
                   owner_payload_json, owner_recorded_at, resolved_at
            FROM formal_research_protocol_component_owner_resolution
            WHERE protocol_id = %s AND component_role <> 'model_reference'
            """,
            (str(legacy.protocol_id), str(current.protocol_id)),
        )
        connection.execute(
            """
            INSERT INTO formal_research_protocol_component_owner_resolution(
                protocol_id, component_role, artifact_kind,
                artifact_id, artifact_hash, owner_kind,
                owner_artifact_id, owner_artifact_hash,
                owner_payload_hash, owner_payload_json,
                owner_recorded_at, resolved_at
            ) VALUES (
                %s, 'model_reference', 'MODEL_VERSION_LINEAGE', %s, %s,
                'MODEL_GOVERNANCE_AUTHORITY', %s, %s, %s, %s, %s, %s
            )
            """,
            (
                str(legacy.protocol_id),
                str(legacy.model_reference.artifact_id),
                legacy.model_reference.content_hash,
                str(legacy.model_reference.artifact_id),
                legacy.model_reference.content_hash,
                legacy_model_payload_hash,
                Jsonb(legacy_model_payload),
                model_owner[1],
                model_owner[2],
            ),
        )
        connection.execute(
            """
            INSERT INTO formal_research_protocol_historical_dataset
            SELECT %s, target_id, target_hash, dataset_id, dataset_hash,
                   owner_payload_hash, owner_payload_json,
                   owner_recorded_at, resolved_at
            FROM formal_research_protocol_historical_dataset
            WHERE formal_protocol_id = %s AND dataset_id = %s
            """,
            (
                str(legacy.protocol_id),
                str(current.protocol_id),
                str(legacy.historical_sample_dataset_reference.artifact_id),
            ),
        )

    assert PostgresFormalProtocolRepository(postgres_factory).get_protocol(
        legacy.protocol_id
    ) == legacy
    with postgres_factory.connection(read_only=True) as connection:
        with pytest.raises(FormalProtocolConflict, match="replay-only"):
            load_formal_protocol_owner(connection, legacy.protocol_id)


def test_protocol_and_outcome_target_forecast_replay_from_postgres(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    fixture = record_phase_c_protocol_owners(postgres_factory)
    protocol = fixture.protocol
    repository = PostgresFormalProtocolRepository(postgres_factory)

    caller_panel = {"schema_version": "research-panel-enrichment/v1"}
    with pytest.raises(ValueError, match="typed owner-specific writer"):
        PostgresResearchValidationRepository(postgres_factory).record(
            artifact_id=ArtifactId("caller-panel-enrichment"),
            artifact_hash=canonical_hash(caller_panel),
            artifact_kind="PANEL_ENRICHMENT",
            evidence_authority="ENGINEERING_ONLY",
            payload=caller_panel,
            created_at=NOW,
        )
    forged_family = {"schema_version": "formal-hypothesis-family-evaluation-result/v1"}
    with pytest.raises(ValueError, match="typed owner-specific writer"):
        PostgresResearchValidationRepository(postgres_factory).record(
            artifact_id=ArtifactId("caller-family-evaluation"),
            artifact_hash=canonical_hash(forged_family),
            artifact_kind="FORMAL_HYPOTHESIS_FAMILY_EVALUATION_RESULT",
            evidence_authority="ENGINEERING_ONLY",
            payload=forged_family,
            created_at=NOW,
        )

    scope = FormalProtocolFreezeScope.from_protocol_references(protocol)
    frozen = repository.freeze_protocol(
        scope=scope,
        actor="phase-c-test",
        reason="freeze formal protocol",
        idempotency_key="formal-protocol-freeze",
    )
    assert repository.freeze_protocol(
        scope=scope,
        actor="phase-c-test",
        reason="freeze formal protocol",
        idempotency_key="formal-protocol-freeze",
    ) == frozen
    protocol = frozen
    family = repository.get_hypothesis_family(protocol.protocol_id)
    assert family.formal_protocol_reference.artifact_id == protocol.protocol_id
    assert family.target_references == protocol.target_references
    assert family.hypothesis_family_key == fixture.evaluation.hypothesis_family_id

    forged_scope = scope.to_canonical_dict()
    forged_scope["locked_at"] = timestamp(NOW)
    with pytest.raises(ValueError, match="fields mismatch"):
        FormalProtocolFreezeScope.from_canonical_dict(forged_scope)

    missing_threshold = _reference("THRESHOLD_POLICY", "caller-only-threshold")
    missing_components = dict(scope.component_references)
    missing_components["threshold_policy_reference"] = missing_threshold
    caller_only_scope = FormalProtocolFreezeScope(
        protocol_version=scope.protocol_version,
        outcome_target_protocol_reference=scope.outcome_target_protocol_reference,
        trading_calendar_reference=scope.trading_calendar_reference,
        evaluation_protocol_reference=scope.evaluation_protocol_reference,
        historical_sample_dataset_references=(
            scope.historical_sample_dataset_references
        ),
        component_references=tuple(sorted(missing_components.items())),
        experiment_definition=scope.experiment_definition,
    )
    with pytest.raises(FormalProtocolConflict, match="THRESHOLD_POLICY owner is missing"):
        repository.freeze_protocol(
            scope=caller_only_scope,
            actor="phase-c-test",
            reason="reject missing owner",
            idempotency_key="missing-threshold-protocol",
        )

    backdated_payload = protocol.identity_payload()
    backdated_payload["locked_at"] = timestamp(NOW)
    backdated_hash = canonical_hash(backdated_payload)
    backdated_protocol = FormalResearchProtocol.from_canonical_dict(
        {
            "protocol_id": f"formal-research-protocol:{backdated_hash[7:]}",
            "protocol_hash": backdated_hash,
            **backdated_payload,
        }
    )
    with pytest.raises(FormalProtocolConflict, match="caller-materialized"):
        repository.record_protocol(protocol=backdated_protocol)

    forecast = build_outcome_target_bound_forecast(
        target_protocol=fixture.targets,
        symbol="000001.SZ",
        decision_time=NOW,
        estimates=tuple(
            not_estimable_target_forecast(
                target_id=target.target_id,
                target_hash=target.target_hash,
                barrier_ids=tuple(item.barrier_id for item in target.barriers),
                reason_codes=("QUALIFIED_HISTORICAL_SAMPLE_MISSING",),
            )
            for target in fixture.targets.targets
        ),
        source_references=(_reference("FROZEN_DECISION", "decision-v1"),),
        model_reference=protocol.model_reference,
        created_at=NOW,
    )
    assert repository.record_forecast(forecast) == forecast
    assert repository.record_forecast(forecast) == forecast

    caller_model_forecast = build_outcome_target_bound_forecast(
        target_protocol=fixture.targets,
        symbol="000002.SZ",
        decision_time=NOW,
        estimates=forecast.estimates,
        source_references=forecast.source_references,
        model_reference=_reference("MODEL_VERSION_LINEAGE", "caller-model"),
        created_at=NOW,
    )
    with pytest.raises(FormalProtocolConflict, match="Model Version Lineage owner"):
        repository.record_forecast(caller_model_forecast)

    with postgres_factory.connection(read_only=True) as connection:
        assert connection.execute(
            "SELECT count(*) FROM formal_research_protocol"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM formal_research_protocol_component"
        ).fetchone()[0] == len(protocol.component_references())
        assert connection.execute(
            """
            SELECT count(*)
            FROM formal_research_protocol_component_owner_resolution
            """
        ).fetchone()[0] == len(protocol.component_references()) + 2
        assert connection.execute(
            "SELECT count(*) FROM outcome_target_bound_forecast"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT forecast_authority FROM outcome_target_bound_forecast"
        ).fetchone() == ("EXPLORATORY_CALLER_SUBMITTED",)
        assert connection.execute(
            "SELECT count(*) FROM outcome_target_bound_forecast_estimate"
        ).fetchone()[0] == len(fixture.targets.targets)
        assert connection.execute(
            "SELECT count(*) FROM frozen_hypothesis_family"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM frozen_hypothesis_family_target"
        ).fetchone()[0] == len(fixture.targets.targets)
