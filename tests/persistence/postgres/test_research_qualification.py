from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.controlled_operation.prospective_outcome import (
    OutcomeAvailabilityStatus,
    OutcomeMarketCondition,
)
from market_regime_alpha.application.research_evaluation.targeted_outcome import (
    TargetOutcomeLabel,
    TargetedShadowOutcome,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.formal_hypothesis_family import (
    FamilyEvaluationObservationBindings,
)
from market_regime_alpha.application.research_validation.postgres_qualification import (
    PostgresResearchQualificationAuthority,
    ResearchQualificationConflict,
    _historical_pit_temporal_reason_codes,
    _historical_target_label_reason_codes,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.application.research_validation.qualification import (
    FormalEvaluationObservationBinding,
    QualificationOutcome,
)
from market_regime_alpha.application.research_validation.samples import (
    HistoricalPathSampleRecord,
    HistoricalSampleDataset,
)
from market_regime_alpha.core.identity import ArtifactId, TargetId
from market_regime_alpha.core.time import AvailabilityTime, DecisionTime
from market_regime_alpha.data.pit_authority import PITFactKind
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
from tests.persistence.postgres.phase_c_owner_fixture import (
    freeze_phase_c_protocol,
    record_phase_c_protocol_owners,
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


def test_family_evaluation_rejects_c3_before_reading_or_unlocking_locked_oos(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    fixture = record_phase_c_protocol_owners(postgres_factory)
    protocol = freeze_phase_c_protocol(
        postgres_factory,
        fixture,
        idempotency_key="pre-oos-c3-gate-protocol",
    )
    authority = PostgresResearchQualificationAuthority(postgres_factory)
    blocked = authority.qualify_historical_sample(
        dataset_id=protocol.historical_sample_dataset_references[0].artifact_id,
        formal_protocol_id=None,
        formal_pit_evidence_id=None,
        actor="phase-c-test",
        reason="prove C3 gate precedes Locked OOS",
        idempotency_key="pre-oos-blocked-c3",
    )
    groups = tuple(
        FamilyEvaluationObservationBindings(
            target_reference=target,
            panel_reference=_reference(
                "RESEARCH_PANEL_V2", f"unread-panel:{target.artifact_id}"
            ),
            observation_bindings=(
                FormalEvaluationObservationBinding.create(
                    forecast_reference=_reference(
                        "OUTCOME_TARGET_BOUND_FORECAST",
                        f"unread-forecast:{target.artifact_id}",
                    ),
                    label_reference=_reference(
                        "TARGET_OUTCOME_LABEL",
                        f"unread-locked-label:{target.artifact_id}",
                    ),
                    panel_slice_reference=_reference(
                        "RESEARCH_PANEL_SLICE_V2",
                        f"unread-slice:{target.artifact_id}",
                    ),
                    panel_row_reference=_reference(
                        "RESEARCH_PANEL_ROW_V2",
                        f"unread-row:{target.artifact_id}",
                    ),
                ),
            ),
        )
        for target in protocol.target_references
    )

    with pytest.raises(
        ResearchQualificationConflict,
        match="C3_QUALIFIED_HISTORICAL_SAMPLE_REQUIRED_BEFORE_LOCKED_OOS",
    ):
        authority.record_family_evaluation_candidate(
            formal_protocol_id=protocol.protocol_id,
            observation_groups=groups,
            historical_sample_decision_ids=(blocked.decision_id,),
            formal_pit_evidence_id=ArtifactId("unread-formal-pit"),
            actor="phase-c-test",
            reason="must stop before any Locked OOS owner read",
            idempotency_key="pre-oos-c3-gate-evaluation",
        )

    with postgres_factory.connection(read_only=True) as connection:
        counts = tuple(
            connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in (
                "formal_evaluation_observation_set",
                "locked_oos_raw_evidence_unlock",
                "locked_oos_target_observation_consumption",
                "formal_hypothesis_family_evaluation",
            )
        )
    assert counts == (0, 0, 0, 0)


def test_historical_label_lineage_rejects_unrelated_market_dataset(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    fixture = record_phase_c_protocol_owners(postgres_factory)
    target = fixture.protocol.target_references[0]
    decision_time = NOW - timedelta(days=5)
    available_at = NOW - timedelta(days=1)
    label = TargetOutcomeLabel.create(
        symbol="000001.SZ",
        target=RuntimeArtifactReference(
            "OUTCOME_TARGET", target.artifact_id, target.content_hash
        ),
        label_interval_start=decision_time,
        label_interval_end=decision_time + timedelta(days=1),
        decision_reference_price=Decimal("10"),
        checkpoint_price=Decimal("10.1"),
        mfe=Decimal("0.04"),
        mae=Decimal("-0.02"),
        barrier_passages=(),
        market_conditions=(OutcomeMarketCondition.TRADING,),
        availability_status=OutcomeAvailabilityStatus.COMPLETE,
        outcome_available_at=available_at,
        reason_codes=("TARGET_COMPLETE",),
    )

    def outcome(source: ValidationArtifactReference) -> TargetedShadowOutcome:
        return TargetedShadowOutcome.create(
            shadow_decision=RuntimeArtifactReference(
                "SHADOW_DECISION",
                ArtifactId("historical-lineage-decision"),
                canonical_hash({"decision": "historical-lineage"}),
            ),
            factual_outcome_v1=RuntimeArtifactReference(
                "FACTUAL_OUTCOME_V1",
                ArtifactId("historical-lineage-factual"),
                canonical_hash({"outcome": "historical-lineage"}),
            ),
            source_dataset=RuntimeArtifactReference(
                source.artifact_kind, source.artifact_id, source.content_hash
            ),
            target_protocol_id=(
                fixture.protocol.outcome_target_protocol_reference.artifact_id
            ),
            target_protocol_hash=(
                fixture.protocol.outcome_target_protocol_reference.content_hash
            ),
            next_session_date=(decision_time + timedelta(days=1)).date(),
            labels=(label,),
            availability_status=OutcomeAvailabilityStatus.COMPLETE,
            outcome_available_at=available_at,
            created_at=available_at,
            reason_codes=("TARGETED_OUTCOME_COMPLETE",),
            limitations=(
                "ENGINEERING_RECORDED_ONLY",
                "FACTUAL_LABELS_ONLY",
                "NOT_ALPHA_VALIDATION",
                "NOT_PROSPECTIVE_EVIDENCE",
            ),
        )

    canonical_outcome = outcome(fixture.protocol.dataset_reference)
    sample = PathForecastSample(
        sample_id=ArtifactId("historical-lineage-sample"),
        source_artifact_id=canonical_outcome.settlement_id,
        source_content_hash=canonical_outcome.settlement_hash,
        symbol=label.symbol,
        target_id=TargetId(str(target.artifact_id)),
        sample_decision_time=DecisionTime(decision_time),
        available_at=AvailabilityTime(available_at),
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
        outcome_reference=ValidationArtifactReference(
            "TARGET_OUTCOME_LABEL", label.label_id, label.label_hash
        ),
        pit_lineage=(),
        registered_at=available_at,
    )
    assert _historical_target_label_reason_codes(
        protocol=fixture.protocol,
        record=record,
        outcome=canonical_outcome,
        label=label,
    ) == ()

    unrelated_outcome = outcome(
        _reference("MARKET_DATA_DATASET", "unrelated-market-dataset")
    )
    assert "TARGET_OUTCOME_DATASET_OR_PROTOCOL_LINEAGE_MISMATCH" in (
        _historical_target_label_reason_codes(
            protocol=fixture.protocol,
            record=record,
            outcome=unrelated_outcome,
            label=label,
        )
    )


def test_historical_pit_rejects_later_as_of_and_calendar_substitution() -> None:
    record = _dataset().records[0]
    sample_time = record.sample.sample_decision_time.value
    fact_id = ArtifactId("historical-calendar-fact")
    fact_hash = canonical_hash({"fact": "historical-calendar"})
    required = SimpleNamespace(
        logical_key="calendar:XSHG-XSHE",
        fact_kind=PITFactKind.TRADING_CALENDAR,
        subject="XSHG-XSHE",
    )
    selected = SimpleNamespace(fact_id=fact_id, fact_hash=fact_hash)
    protocol_calendar = _reference("TRADING_CALENDAR", "frozen-calendar")
    substituted_calendar = _reference("TRADING_CALENDAR", "later-calendar")
    row = (
        fact_hash,
        required.logical_key,
        required.fact_kind.value,
        required.subject,
        sample_time - timedelta(days=1),
        sample_time - timedelta(days=2),
        None,
        sample_time + timedelta(hours=1),
        sample_time + timedelta(hours=2),
        str(substituted_calendar.artifact_id),
        substituted_calendar.content_hash,
    )

    class Cursor:
        def fetchone(self) -> tuple[Any, ...]:
            return row

    class Connection:
        def execute(self, query: str, params: tuple[str]) -> Cursor:
            assert "FROM pit_fact_revision" in query
            assert params == (str(fact_id),)
            return Cursor()

    reasons = _historical_pit_temporal_reason_codes(
        Connection(),
        protocol=SimpleNamespace(trading_calendar_reference=protocol_calendar),
        record=record,
        pit_request=SimpleNamespace(
            decision_time=sample_time + timedelta(days=1),
            required_facts=(required,),
        ),
        pit=SimpleNamespace(selected_fact_authorities=(selected,)),
    )

    assert reasons == (
        "FORMAL_PIT_FROZEN_CALENDAR_LINEAGE_MISMATCH",
        "HISTORICAL_SAMPLE_FORMAL_PIT_DECISION_TIME_MISMATCH",
        "HISTORICAL_SAMPLE_PIT_FACT_NOT_AS_OF_SAMPLE",
    )
