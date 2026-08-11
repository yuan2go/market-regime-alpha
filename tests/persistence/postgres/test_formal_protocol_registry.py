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

    assert repository.record_protocol(protocol=protocol) == protocol
    assert repository.record_protocol(protocol=protocol) == protocol
    family = repository.get_hypothesis_family(protocol.protocol_id)
    assert family.formal_protocol_reference.artifact_id == protocol.protocol_id
    assert family.target_references == protocol.target_references
    assert family.hypothesis_family_key == fixture.evaluation.hypothesis_family_id

    forged_payload = protocol.identity_payload()
    forged_payload["frozen_trading_dates"] = [
        item
        for item in forged_payload["frozen_trading_dates"]
        if item != "2026-01-15"
    ]
    forged_hash = canonical_hash(forged_payload)
    forged_calendar_projection = FormalResearchProtocol.from_canonical_dict(
        {
            "protocol_id": f"formal-research-protocol:{forged_hash[7:]}",
            "protocol_hash": forged_hash,
            **forged_payload,
        }
    )
    with pytest.raises(FormalProtocolConflict, match="Protocol dates diverge"):
        repository.record_protocol(protocol=forged_calendar_projection)

    missing_threshold = _reference("THRESHOLD_POLICY", "caller-only-threshold")
    missing_payload = protocol.identity_payload()
    missing_payload["threshold_policy_reference"] = (
        missing_threshold.to_canonical_dict()
    )
    missing_hash = canonical_hash(missing_payload)
    caller_only_protocol = FormalResearchProtocol.from_canonical_dict(
        {
            "protocol_id": f"formal-research-protocol:{missing_hash[7:]}",
            "protocol_hash": missing_hash,
            **missing_payload,
        }
    )
    with pytest.raises(FormalProtocolConflict, match="THRESHOLD_POLICY owner is missing"):
        repository.record_protocol(protocol=caller_only_protocol)

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
    with pytest.raises(FormalProtocolConflict, match="recorded after protocol lock"):
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
