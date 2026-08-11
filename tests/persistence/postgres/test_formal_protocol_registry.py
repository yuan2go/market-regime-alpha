from __future__ import annotations

import pytest

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
    timestamp,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    FormalResearchProtocol,
    OutcomeTargetForecastEstimate,
    OutcomeTargetForecastStatus,
    build_outcome_target_bound_forecast,
)
from market_regime_alpha.application.research_validation.postgres_formal_protocol import (
    FormalProtocolFreezeScope,
    FormalProtocolConflict,
    PostgresFormalProtocolRepository,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from tests.persistence.postgres.phase_c_owner_fixture import (
    NOW,
    record_phase_c_protocol_owners,
)


def _reference(kind: str, name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(name),
        canonical_hash({"kind": kind, "name": name}),
    )


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
            OutcomeTargetForecastEstimate(
                target.target_id,
                target.target_hash,
                OutcomeTargetForecastStatus.NOT_ESTIMABLE,
                None,
                None,
                None,
                None,
                (),
                ("QUALIFIED_HISTORICAL_SAMPLE_MISSING",),
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
