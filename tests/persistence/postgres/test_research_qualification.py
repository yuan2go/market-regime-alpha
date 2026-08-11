from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

import market_regime_alpha.application.research_validation.postgres_qualification as qualification_module

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
from market_regime_alpha.application.research_validation.formal_protocol import (
    OutcomeTargetForecastEstimate,
    OutcomeTargetForecastStatus,
    build_outcome_target_bound_forecast,
)
from market_regime_alpha.application.research_validation.postgres_qualification import (
    PostgresResearchQualificationAuthority,
    ResearchQualificationConflict,
    _historical_pit_temporal_reason_codes,
    _historical_target_label_reason_codes,
    _load_evaluation_label_metadata,
    _require_locked_oos_pit_universe_scope,
)
from market_regime_alpha.application.research_validation.postgres_formal_protocol import (
    PostgresFormalProtocolRepository,
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
from market_regime_alpha.data.pit_authority import (
    PITArtifactReference,
    PITFactKind,
)
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
    PostgresResearchValidationRepository(postgres_factory).record_sample_dataset(
        dataset
    )
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
                "formal_locked_oos_roster",
                "formal_locked_oos_roster_member",
                "locked_oos_raw_evidence_unlock",
                "locked_oos_target_observation_consumption",
                "formal_hypothesis_family_evaluation",
            )
        )
    assert counts == (0, 0, 0, 0, 0, 0)


def test_family_evaluation_commits_roster_claim_before_full_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class Cursor:
        def fetchone(self) -> None:
            return None

    class Connection:
        def execute(self, _query: str, _parameters: object) -> Cursor:
            return Cursor()

    class TwoPhaseFactory:
        transactions = 0
        roster_committed = False

        def run_transaction(self, operation: Any) -> Any:
            self.transactions += 1
            phase = self.transactions
            events.append(f"transaction-{phase}-begin")
            result = operation(Connection())
            if phase == 1:
                self.roster_committed = True
                events.append("roster-claim-committed")
            return result

        class ReadOnlyConnection:
            def __enter__(self) -> Connection:
                return Connection()

            def __exit__(self, *_values: object) -> None:
                return None

        def connection(self, *, read_only: bool = False) -> ReadOnlyConnection:
            assert read_only
            return self.ReadOnlyConnection()

    factory = TwoPhaseFactory()
    frozen_at = NOW

    def prepare(_connection: object, **_values: object) -> object:
        events.append("roster-claim-written")
        return qualification_module._LockedOOSRosterPreparation(
            ArtifactId("formal-locked-oos-roster:test"),
            canonical_hash({"roster": "test"}),
            frozen_at,
        )

    def fail_full_resolution(_connection: object, _protocol_id: ArtifactId) -> object:
        assert factory.roster_committed
        events.append("full-resolution-after-commit")
        raise ResearchQualificationConflict("SIMULATED_LOCKED_LABEL_PHASE_FAILURE")

    monkeypatch.setattr(qualification_module, "_prepare_locked_oos_roster", prepare)
    monkeypatch.setattr(qualification_module, "_load_formal_protocol", fail_full_resolution)
    authority = object.__new__(PostgresResearchQualificationAuthority)
    authority._factory = factory  # type: ignore[assignment]
    group = FamilyEvaluationObservationBindings(
        target_reference=_reference("OUTCOME_TARGET", "two-phase-target"),
        panel_reference=_reference("RESEARCH_PANEL_V2", "two-phase-panel"),
        observation_bindings=(
            FormalEvaluationObservationBinding.create(
                forecast_reference=_reference(
                    "OUTCOME_TARGET_BOUND_FORECAST", "two-phase-forecast"
                ),
                label_reference=_reference(
                    "TARGET_OUTCOME_LABEL", "two-phase-label"
                ),
                panel_slice_reference=_reference(
                    "RESEARCH_PANEL_SLICE_V2", "two-phase-slice"
                ),
                panel_row_reference=_reference(
                    "RESEARCH_PANEL_ROW_V2", "two-phase-row"
                ),
            ),
        ),
    )

    with pytest.raises(
        ResearchQualificationConflict,
        match="SIMULATED_LOCKED_LABEL_PHASE_FAILURE",
    ):
        authority.record_family_evaluation_candidate(
            formal_protocol_id=ArtifactId("two-phase-protocol"),
            observation_groups=(group,),
            historical_sample_decision_ids=(ArtifactId("two-phase-c3"),),
            formal_pit_evidence_id=ArtifactId("two-phase-pit"),
            actor="phase-c-test",
            reason="prove durable claim boundary",
            idempotency_key="two-phase-evaluation",
        )

    assert factory.transactions == 2
    assert events == [
        "transaction-1-begin",
        "roster-claim-written",
        "roster-claim-committed",
        "transaction-2-begin",
        "full-resolution-after-commit",
    ]


def test_legacy_single_target_writer_rejects_locked_oos_before_owner_reads(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    fixture = record_phase_c_protocol_owners(postgres_factory)
    protocol = freeze_phase_c_protocol(
        postgres_factory,
        fixture,
        idempotency_key="legacy-writer-locked-replay-only-protocol",
    )
    decision_time = datetime(2026, 1, 22, 6, 45, tzinfo=UTC)
    forecast = build_outcome_target_bound_forecast(
        target_protocol=fixture.targets,
        symbol="600000.SH",
        decision_time=decision_time,
        estimates=tuple(
            OutcomeTargetForecastEstimate(
                target.target_id,
                target.target_hash,
                OutcomeTargetForecastStatus.AVAILABLE_FOR_RESEARCH,
                Decimal("0.5"),
                    None,
                    None,
                    None,
                    tuple(
                        (barrier.barrier_id, Decimal("0.5"))
                        for barrier in target.barriers
                    ),
                    (),
            )
            for target in fixture.targets.targets
        ),
        source_references=(
            protocol.universe_reference,
            protocol.dataset_reference,
            protocol.feature_reference,
            protocol.factor_reference,
            protocol.threshold_policy_reference,
        ),
        model_reference=protocol.model_reference,
        created_at=decision_time,
    )
    PostgresFormalProtocolRepository(postgres_factory).record_forecast(forecast)
    target = protocol.target_references[0]
    binding = FormalEvaluationObservationBinding.create(
        forecast_reference=ValidationArtifactReference(
            "OUTCOME_TARGET_BOUND_FORECAST",
            forecast.forecast_id,
            forecast.forecast_hash,
        ),
        label_reference=_reference("TARGET_OUTCOME_LABEL", "must-not-read-label"),
        panel_slice_reference=_reference(
            "RESEARCH_PANEL_SLICE_V2", "must-not-read-slice"
        ),
        panel_row_reference=_reference(
            "RESEARCH_PANEL_ROW_V2", "must-not-read-row"
        ),
    )

    with pytest.raises(
        ResearchQualificationConflict,
        match="LEGACY_SINGLE_TARGET_LOCKED_OOS_REPLAY_ONLY_USE_FAMILY_AUTHORITY",
    ):
        PostgresResearchQualificationAuthority(
            postgres_factory
        ).record_evaluation_candidate(
            formal_protocol_id=protocol.protocol_id,
            panel_reference=_reference(
                "RESEARCH_PANEL_V2", "must-not-read-panel"
            ),
            target_reference=target,
            observation_bindings=(binding,),
            formal_pit_evidence_id=ArtifactId("must-not-read-formal-pit"),
        )

    with postgres_factory.connection(read_only=True) as connection:
        assert connection.execute(
            "SELECT count(*) FROM formal_locked_oos_roster"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM locked_oos_evidence_consumption"
        ).fetchone()[0] == 0


def test_locked_oos_pit_scope_cannot_cherry_pick_frozen_universe_members() -> None:
    universe_reference = _reference("UNIVERSE", "complete-universe")
    universe = PITArtifactReference(
        universe_reference.artifact_kind,
        universe_reference.artifact_id,
        universe_reference.content_hash,
    )
    decision_time = datetime(2026, 1, 22, 6, 45, tzinfo=UTC)
    projection = SimpleNamespace(
        universe_reference=universe,
        included_symbols=("000001.SZ", "000002.SZ"),
        effective_at=decision_time - timedelta(days=1),
        available_at=decision_time - timedelta(minutes=1),
    )
    request = SimpleNamespace(
        lineage=SimpleNamespace(universe=universe),
        symbols=("000001.SZ",),
        decision_time=decision_time,
    )

    with pytest.raises(
        ResearchQualificationConflict,
        match="LOCKED_OOS_PIT_SCOPE_DOES_NOT_EQUAL_CANONICAL_UNIVERSE",
    ):
        _require_locked_oos_pit_universe_scope(
            request=request,  # type: ignore[arg-type]
            projection=projection,  # type: ignore[arg-type]
        )


def test_train_forecast_cannot_read_substituted_locked_label_payload() -> None:
    target_protocol = _reference("OUTCOME_TARGET_PROTOCOL", "metadata-protocol")
    target = _reference("OUTCOME_TARGET", "metadata-target")
    label = _reference("TARGET_OUTCOME_LABEL", "substituted-locked-label")
    forecast_time = NOW - timedelta(days=30)
    locked_time = NOW - timedelta(days=1)
    binding = FormalEvaluationObservationBinding.create(
        forecast_reference=_reference(
            "OUTCOME_TARGET_BOUND_FORECAST", "train-forecast"
        ),
        label_reference=label,
        panel_slice_reference=_reference("RESEARCH_PANEL_SLICE_V2", "train-slice"),
        panel_row_reference=_reference("RESEARCH_PANEL_ROW_V2", "train-row"),
    )

    class MetadataOnlyResult:
        def fetchall(self) -> list[tuple[Any, ...]]:
            return [
                (
                    "locked-settlement",
                    label.content_hash,
                    str(target_protocol.artifact_id),
                    str(target.artifact_id),
                    "000001.SZ",
                    locked_time,
                    locked_time + timedelta(days=1),
                    OutcomeAvailabilityStatus.COMPLETE.value,
                    canonical_hash({"settlement": "locked"}),
                    "locked-decision",
                    canonical_hash({"decision": "locked"}),
                    target.content_hash,
                    target_protocol.content_hash,
                    "metadata-dataset",
                    "metadata-dataset",
                    canonical_hash({"dataset": "metadata"}),
                )
            ]

    class MetadataOnlyConnection:
        queries: list[str]

        def __init__(self) -> None:
            self.queries = []

        def execute(self, query: str, _parameters: object) -> MetadataOnlyResult:
            self.queries.append(query)
            assert "label_json" not in query
            return MetadataOnlyResult()

    connection = MetadataOnlyConnection()
    with pytest.raises(
        ResearchQualificationConflict,
        match="Label metadata/Forecast temporal mismatch",
    ):
        _load_evaluation_label_metadata(
            connection,
            protocol=SimpleNamespace(
                outcome_target_protocol_reference=target_protocol,
                dataset_reference=SimpleNamespace(
                    artifact_id=ArtifactId("metadata-dataset"),
                    content_hash=canonical_hash({"dataset": "metadata"}),
                ),
            ),  # type: ignore[arg-type]
            target_reference=target,
            binding=binding,
            forecast=SimpleNamespace(symbol="000001.SZ", decision_time=forecast_time),  # type: ignore[arg-type]
        )
    assert len(connection.queries) == 1


def test_locked_label_metadata_rejects_same_dataset_id_with_wrong_hash() -> None:
    target_protocol = _reference("OUTCOME_TARGET_PROTOCOL", "hash-protocol")
    target = _reference("OUTCOME_TARGET", "hash-target")
    label = _reference("TARGET_OUTCOME_LABEL", "wrong-dataset-hash-label")
    decision_time = NOW - timedelta(days=1)
    dataset_hash = canonical_hash({"dataset": "canonical"})
    binding = FormalEvaluationObservationBinding.create(
        forecast_reference=_reference(
            "OUTCOME_TARGET_BOUND_FORECAST", "hash-forecast"
        ),
        label_reference=label,
        panel_slice_reference=_reference("RESEARCH_PANEL_SLICE_V2", "hash-slice"),
        panel_row_reference=_reference("RESEARCH_PANEL_ROW_V2", "hash-row"),
    )

    class MetadataResult:
        def fetchall(self) -> list[tuple[Any, ...]]:
            return [
                (
                    "hash-settlement",
                    label.content_hash,
                    str(target_protocol.artifact_id),
                    str(target.artifact_id),
                    "000001.SZ",
                    decision_time,
                    decision_time + timedelta(days=1),
                    OutcomeAvailabilityStatus.COMPLETE.value,
                    canonical_hash({"settlement": "hash"}),
                    "hash-decision",
                    canonical_hash({"decision": "hash"}),
                    target.content_hash,
                    target_protocol.content_hash,
                    "dataset-a",
                    "dataset-a",
                    canonical_hash({"dataset": "substituted"}),
                )
            ]

    class MetadataConnection:
        def execute(self, query: str, _parameters: object) -> MetadataResult:
            assert "label_json" not in query
            assert "prospective_outcome_settlement" in query
            return MetadataResult()

    with pytest.raises(
        ResearchQualificationConflict,
        match="Target Outcome Label owner mismatch",
    ):
        _load_evaluation_label_metadata(
            MetadataConnection(),  # type: ignore[arg-type]
            protocol=SimpleNamespace(
                outcome_target_protocol_reference=target_protocol,
                dataset_reference=SimpleNamespace(
                    artifact_id=ArtifactId("dataset-a"),
                    content_hash=dataset_hash,
                ),
            ),  # type: ignore[arg-type]
            target_reference=target,
            binding=binding,
            forecast=SimpleNamespace(
                symbol="000001.SZ", decision_time=decision_time
            ),  # type: ignore[arg-type]
        )


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
    assert (
        _historical_target_label_reason_codes(
            protocol=fixture.protocol,
            record=record,
            outcome=canonical_outcome,
            label=label,
        )
        == ()
    )

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
