from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.postgres_qualification import (
    PostgresResearchQualificationAuthority,
    ResearchQualificationConflict,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.application.research_validation.qualification import (
    QualificationOutcome,
)
from market_regime_alpha.application.research_validation.samples import (
    HistoricalPathSampleRecord,
    HistoricalSampleDataset,
)
from market_regime_alpha.core.identity import ArtifactId, TargetId
from market_regime_alpha.core.time import AvailabilityTime, DecisionTime
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.forecasting.path import (
    PATH_FORECAST_SAMPLE_SCHEMA,
    PathForecastSample,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.strategies.entry.contracts import (
    EntryPathObservationStatus,
    EntryPathReasonCode,
)


NOW = datetime(2026, 8, 11, 8, tzinfo=UTC)


def _reference(kind: str, name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(name),
        canonical_hash({"kind": kind, "name": name}),
    )


def _dataset() -> HistoricalSampleDataset:
    target = _reference("OUTCOME_TARGET", "qualified-sample-target")
    sample = PathForecastSample(
        sample_id=ArtifactId("qualified-sample"),
        source_artifact_id=ArtifactId("qualified-sample-outcome"),
        source_content_hash=canonical_hash({"outcome": "qualified-sample"}),
        symbol="000001.SZ",
        target_id=TargetId(str(target.artifact_id)),
        sample_decision_time=DecisionTime(NOW - timedelta(days=5)),
        available_at=AvailabilityTime(NOW - timedelta(days=1)),
        observation_status=EntryPathObservationStatus.AVAILABLE,
        observation_reason_code=EntryPathReasonCode.OUTCOME_RESOLVED,
        realized_mfe=0.04,
        realized_mae=-0.02,
        realized_return=0.01,
        schema_version=PATH_FORECAST_SAMPLE_SCHEMA,
    )
    record = HistoricalPathSampleRecord.register_unqualified(
        sample=sample,
        target_reference=target,
        outcome_reference=_reference("FACTUAL_OUTCOME", "qualified-sample-outcome"),
        pit_lineage=(),
        registered_at=NOW - timedelta(days=1),
    )
    return HistoricalSampleDataset.create(
        registry_version="qualification-test-v1",
        target_reference=target,
        records=(record,),
        available_at=NOW - timedelta(days=1),
    )


def test_historical_sample_owner_persists_missing_formal_evidence_as_blocked(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    dataset = _dataset()
    PostgresResearchValidationRepository(postgres_factory).record_sample_dataset(dataset)
    authority = PostgresResearchQualificationAuthority(postgres_factory)

    first = authority.qualify_historical_sample(
        dataset_id=dataset.dataset_id,
        formal_protocol_id=None,
        formal_pit_evidence_id=None,
        actor="phase-c-test",
        reason="resolve current evidence ceiling",
        idempotency_key="blocked-historical-sample",
    )
    replayed = authority.qualify_historical_sample(
        dataset_id=dataset.dataset_id,
        formal_protocol_id=None,
        formal_pit_evidence_id=None,
        actor="phase-c-test",
        reason="resolve current evidence ceiling",
        idempotency_key="blocked-historical-sample",
    )

    assert replayed == first
    assert first.outcome is QualificationOutcome.BLOCKED
    assert first.qualified is False
    assert first.reason_codes == (
        "FORMAL_PIT_EVIDENCE_MISSING",
        "FORMAL_RESEARCH_PROTOCOL_MISSING",
    )
    with postgres_factory.connection(read_only=True) as connection:
        stored = connection.execute(
            "SELECT outcome, qualified FROM historical_sample_qualification_decision"
        ).fetchone()
    assert stored == ("BLOCKED", False)

    with pytest.raises(ResearchQualificationConflict, match="idempotency"):
        authority.qualify_historical_sample(
            dataset_id=dataset.dataset_id,
            formal_protocol_id=None,
            formal_pit_evidence_id=None,
            actor="phase-c-test",
            reason="different command",
            idempotency_key="blocked-historical-sample",
        )
