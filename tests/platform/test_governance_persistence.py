from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
import psycopg
from tests.postgres_path_repositories import postgres_connection
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.identity import ModelId
from market_regime_alpha.platform.contracts import (
    EvidenceLevel,
    ModelLifecycleStatus,
)
from market_regime_alpha.platform.durable_governance import (
    PersistentExperimentGovernance,
    PersistentModelRegistry,
)
from market_regime_alpha.platform.repositories import VersionConflictError
from tests.postgres_path_repositories import (
    PostgresExperimentGovernanceRepository,
    PostgresModelRegistryRepository,
)
from tests.platform.test_platform_kernel import (
    _dataset,
    _model_definition,
)
from market_regime_alpha.platform.contracts import (
    EvaluationProtocolId,
    ResearchHypothesisId,
)
from market_regime_alpha.platform.experiment_governance import (
    ExperimentBudget,
    FrozenExperimentProtocol,
    PrimaryChangeDimension,
    ResearchHypothesis,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
CHANGED_AT = datetime(2026, 8, 1, 10, 0, tzinfo=SHANGHAI)


def _protocol(*, accesses: int = 2) -> FrozenExperimentProtocol:
    dataset = _dataset()
    return FrozenExperimentProtocol(
        hypothesis=ResearchHypothesis(
            hypothesis_id=ResearchHypothesisId(
                "hypothesis-durable-governance-v1"
            ),
            statement="Durable access control preserves frozen research.",
            rationale="Restart and concurrency must not reset access budgets.",
            expected_result="Access counts are restored exactly.",
            counter_evidence=("Postgres transaction failure may interrupt writes.",),
            invalidation_condition="Any restart resets or duplicates access.",
        ),
        model_id=ModelId("candidate-durable-governance-v1"),
        parent_model_id=ModelId("platform-b0-momentum-v1"),
        dataset_id=dataset.dataset_id,
        universe_id=dataset.universe_id,
        target_ids=(dataset.target_id,),
        evaluation_protocol_id=EvaluationProtocolId(
            "durable-governance-evaluation-v1"
        ),
        feature_ids=dataset.feature_definition_ids[:1],
        parameter_variants=((('weight', '1.0'),),),
        primary_change=PrimaryChangeDimension.PARAMETER_SET,
        comparison_model_ids=(ModelId("platform-b0-momentum-v1"),),
        sample_split_ref="chronological-v1",
        cost_model_ref="manual-cost-v1",
        code_revision="phase-2-test",
        environment_ref="pytest-postgres",
        budget=ExperimentBudget(
            max_validation_accesses=accesses,
            max_sealed_test_accesses=1,
        ),
    )


def test_model_registry_restores_validated_state_after_restart(
    tmp_path: Path,
) -> None:
    path = tmp_path / "governance.postgres-scope"
    service = PersistentModelRegistry(PostgresModelRegistryRepository(path))
    registered = service.register(
        _model_definition(), idempotency_key="register-model-v1"
    )
    transitioned = service.transition(
        registered.registration.definition.model_id,
        expected_version=registered.version,
        idempotency_key="research-transition-v1",
        to_status=ModelLifecycleStatus.RESEARCH,
        changed_at=CHANGED_AT,
        reason="begin durable research",
    )

    restored = PersistentModelRegistry(
        PostgresModelRegistryRepository(path)
    ).get(transitioned.registration.definition.model_id)

    assert restored == transitioned
    assert restored.version == 1
    assert len(restored.registration.transitions) == 1


def test_model_commands_are_idempotent_and_conflicting_reuse_is_rejected(
    tmp_path: Path,
) -> None:
    service = PersistentModelRegistry(
        PostgresModelRegistryRepository(tmp_path / "governance.postgres-scope")
    )
    definition = _model_definition()
    first = service.register(definition, idempotency_key="register-once")
    assert service.register(
        definition, idempotency_key="register-once"
    ) == first

    transitioned = service.transition(
        definition.model_id,
        expected_version=0,
        idempotency_key="transition-once",
        to_status=ModelLifecycleStatus.RESEARCH,
        changed_at=CHANGED_AT,
        reason="research",
    )
    assert service.transition(
        definition.model_id,
        expected_version=0,
        idempotency_key="transition-once",
        to_status=ModelLifecycleStatus.RESEARCH,
        changed_at=CHANGED_AT,
        reason="research",
    ) == transitioned
    with pytest.raises(ValueError, match="idempotency"):
        service.register(
            replace(definition, name="conflicting definition"),
            idempotency_key="register-once",
        )


def test_model_registry_uses_optimistic_version_and_rejects_domain_bypass(
    tmp_path: Path,
) -> None:
    repository = PostgresModelRegistryRepository(
        tmp_path / "governance.postgres-scope"
    )
    first = PersistentModelRegistry(repository)
    second = PersistentModelRegistry(
        PostgresModelRegistryRepository(repository.path)
    )
    current = first.register(
        _model_definition(), idempotency_key="register-model"
    )
    first.transition(
        current.registration.definition.model_id,
        expected_version=0,
        idempotency_key="first-transition",
        to_status=ModelLifecycleStatus.RESEARCH,
        changed_at=CHANGED_AT,
        reason="first writer",
    )
    with pytest.raises(VersionConflictError):
        second.transition(
            current.registration.definition.model_id,
            expected_version=0,
            idempotency_key="stale-transition",
            to_status=ModelLifecycleStatus.RETIRED,
            changed_at=CHANGED_AT,
            reason="stale writer",
        )

    forged = replace(
        current.registration,
        lifecycle_status=ModelLifecycleStatus.ACTIVE,
        evidence_level=EvidenceLevel.SHADOW_EVIDENCE,
    )
    with pytest.raises(ValueError, match="transition history"):
        repository.compare_and_set(
            current.registration.definition.model_id,
            expected_version=1,
            registration=forged,
            idempotency_key="database-bypass",
        )


def test_model_transaction_failure_rolls_back_transition_and_recovers(
    tmp_path: Path,
) -> None:
    path = tmp_path / "governance.postgres-scope"
    service = PersistentModelRegistry(PostgresModelRegistryRepository(path))
    model_id = _model_definition().model_id
    service.register(_model_definition(), idempotency_key="register-before-crash")
    with postgres_connection(path) as connection:
        connection.execute(
            """
            CREATE FUNCTION abort_model_update_fn()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'simulated crash';
            END;
            $$;
            CREATE TRIGGER abort_model_update
            BEFORE UPDATE ON model_registrations
            FOR EACH ROW EXECUTE FUNCTION abort_model_update_fn()
            """
            , prepare=False
        )
    with pytest.raises(psycopg.Error, match="simulated crash"):
        service.transition(
            model_id,
            expected_version=0,
            idempotency_key="crashing-transition",
            to_status=ModelLifecycleStatus.RESEARCH,
            changed_at=CHANGED_AT,
            reason="must roll back",
        )
    with postgres_connection(path) as connection:
        connection.execute(
            "DROP TRIGGER abort_model_update ON model_registrations"
        )
        connection.execute("DROP FUNCTION abort_model_update_fn()")

    recovered = PersistentModelRegistry(
        PostgresModelRegistryRepository(path)
    ).get(model_id)
    assert recovered.version == 0
    assert recovered.registration.transitions == ()


def test_experiment_access_is_append_only_recoverable_and_budgeted(
    tmp_path: Path,
) -> None:
    path = tmp_path / "governance.postgres-scope"
    service = PersistentExperimentGovernance(
        PostgresExperimentGovernanceRepository(path)
    )
    protocol = _protocol(accesses=2)
    registered = service.register(
        protocol, idempotency_key="register-experiment"
    )
    first = service.record_validation_access(
        protocol.experiment_id,
        expected_version=registered.version,
        idempotency_key="validation-access-1",
    )
    assert service.record_validation_access(
        protocol.experiment_id,
        expected_version=registered.version,
        idempotency_key="validation-access-1",
    ) == first
    with pytest.raises(ValueError, match="idempotency"):
        service.record_sealed_test_access(
            protocol.experiment_id,
            expected_version=registered.version,
            idempotency_key="validation-access-1",
        )

    restored_service = PersistentExperimentGovernance(
        PostgresExperimentGovernanceRepository(path)
    )
    restored = restored_service.get(protocol.experiment_id)
    assert restored == first
    second = restored_service.record_validation_access(
        protocol.experiment_id,
        expected_version=restored.version,
        idempotency_key="validation-access-2",
    )
    assert second.access_record.validation_access_count == 2
    with pytest.raises(ValueError, match="budget exhausted"):
        restored_service.record_validation_access(
            protocol.experiment_id,
            expected_version=second.version,
            idempotency_key="validation-access-3",
        )


def test_experiment_access_conflict_is_persisted(
    tmp_path: Path,
) -> None:
    path = tmp_path / "governance.postgres-scope"
    first = PersistentExperimentGovernance(
        PostgresExperimentGovernanceRepository(path)
    )
    protocol = _protocol()
    first.register(protocol, idempotency_key="register-exp")
    stale = PersistentExperimentGovernance(
        PostgresExperimentGovernanceRepository(path)
    )
    first.record_sealed_test_access(
        protocol.experiment_id,
        expected_version=0,
        idempotency_key="sealed-access",
    )
    with pytest.raises(VersionConflictError):
        stale.record_validation_access(
            protocol.experiment_id,
            expected_version=0,
            idempotency_key="stale-validation",
        )

    with postgres_connection(path, read_only=True) as connection:
        migration = connection.execute(
            "SELECT MAX(version) AS version FROM schema_migrations"
        ).fetchone()
        assert migration is not None
        assert int(migration[0]) >= 23


def test_experiment_transaction_failure_rolls_back_access_event(
    tmp_path: Path,
) -> None:
    path = tmp_path / "governance.postgres-scope"
    service = PersistentExperimentGovernance(
        PostgresExperimentGovernanceRepository(path)
    )
    protocol = _protocol()
    service.register(protocol, idempotency_key="register-before-access-crash")
    with postgres_connection(path) as connection:
        connection.execute(
            """
            CREATE FUNCTION abort_experiment_update_fn()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'simulated access crash';
            END;
            $$;
            CREATE TRIGGER abort_experiment_update
            BEFORE UPDATE ON governed_experiments
            FOR EACH ROW EXECUTE FUNCTION abort_experiment_update_fn()
            """
            , prepare=False
        )
    with pytest.raises(psycopg.Error, match="simulated access crash"):
        service.record_validation_access(
            protocol.experiment_id,
            expected_version=0,
            idempotency_key="crashing-access",
        )
    with postgres_connection(path) as connection:
        connection.execute(
            "DROP TRIGGER abort_experiment_update ON governed_experiments"
        )
        connection.execute("DROP FUNCTION abort_experiment_update_fn()")

    recovered = PersistentExperimentGovernance(
        PostgresExperimentGovernanceRepository(path)
    ).get(protocol.experiment_id)
    assert recovered.version == 0
    assert recovered.access_record.validation_access_count == 0
