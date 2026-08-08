from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

import pytest

from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.pit_authority import (
    PITAsOfQuery,
    PITFactKind,
    PITRequiredFact,
    PITValidationOutcome,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from tests.persistence.postgres.pit_fixture import (
    DECISION_TIME,
    INGEST_TIME,
    MutableClock,
    NOW,
    authorize_source,
    pit_authority,
    pit_fact,
    pit_request,
    ref,
    required_facts,
)


def _validate_with_attacked_fact(
    factory: PostgresConnectionFactory,
    *,
    attacked_kind: PITFactKind,
    attack: Callable[[PITRequiredFact], dict[str, object]],
    evidence_key: str,
) -> tuple[PITValidationOutcome, tuple[str, ...]]:
    clock = MutableClock(INGEST_TIME)
    authority = pit_authority(factory, clock=clock)
    authorize_source(authority, idempotency_key=f"{evidence_key}-source")
    attacked_required = next(
        item for item in required_facts() if item.fact_kind is attacked_kind
    )
    attacked_values = attack(attacked_required)
    attacked_source = attacked_values.get("source_manifest")
    if attacked_source is not None:
        authorize_source(
            authority,
            source_manifest=attacked_source,
            idempotency_key=f"{evidence_key}-attacked-source",
        )
    for index, required in enumerate(required_facts()):
        values = attacked_values if required == attacked_required else {}
        if any(
            key in values
            for key in ("event_time", "available_at", "recorded_at")
        ):
            clock.value = NOW
        authority.record_fact(
            pit_fact(required, **values),
            actor="source-ingestor",
            reason="record leakage attack fixture",
            idempotency_key=f"{evidence_key}-fact-{index}",
        )
        clock.value = INGEST_TIME
    clock.value = NOW
    evidence = authority.validate(pit_request(idempotency_key=evidence_key))
    assert authority.replay_evidence(evidence.evidence_id) == evidence
    return evidence.outcome, evidence.rejection_codes


@pytest.mark.parametrize(
    ("kind", "attack", "expected"),
    [
        (
            PITFactKind.MARKET_DATA,
            lambda _: {
                "event_time": DECISION_TIME + timedelta(seconds=1),
                "available_at": DECISION_TIME + timedelta(seconds=2),
                "recorded_at": DECISION_TIME + timedelta(seconds=3),
            },
            "FUTURE_EVENT_REJECTED:market:600000.SH:2026-08-08T06:44:00Z",
        ),
        (
            PITFactKind.MARKET_DATA,
            lambda _: {
                "available_at": DECISION_TIME + timedelta(seconds=1),
                "recorded_at": DECISION_TIME + timedelta(seconds=2),
            },
            "LATE_AVAILABLE_FACT_REJECTED:market:600000.SH:2026-08-08T06:44:00Z",
        ),
        (
            PITFactKind.MARKET_DATA,
            lambda _: {"recorded_at": DECISION_TIME + timedelta(seconds=1)},
            "LATE_RECORDED_FACT_REJECTED:market:600000.SH:2026-08-08T06:44:00Z",
        ),
        (
            PITFactKind.UNIVERSE_MEMBERSHIP,
            lambda _: {"effective_from": DECISION_TIME + timedelta(seconds=1)},
            "FUTURE_EFFECTIVE_STATE_REJECTED:universe:600000.SH",
        ),
        (
            PITFactKind.FEATURE_MATERIALIZATION,
            lambda _: {
                "available_at": DECISION_TIME + timedelta(seconds=1),
                "recorded_at": DECISION_TIME + timedelta(seconds=2),
            },
            "LATE_AVAILABLE_FACT_REJECTED:feature:feature-run-a",
        ),
    ],
)
def test_temporal_leakage_is_rejected_and_replayable(
    postgres_factory: PostgresConnectionFactory,
    kind: PITFactKind,
    attack: Callable[[PITRequiredFact], dict[str, object]],
    expected: str,
) -> None:
    outcome, reasons = _validate_with_attacked_fact(
        postgres_factory,
        attacked_kind=kind,
        attack=attack,
        evidence_key=f"attack-{expected}",
    )

    assert outcome is PITValidationOutcome.REJECTED
    assert expected in reasons


def test_late_server_ingest_is_rejected_even_when_caller_times_look_safe(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(INGEST_TIME)
    authority = pit_authority(postgres_factory, clock=clock)
    authorize_source(authority, idempotency_key="late-ingest-source")
    for index, required in enumerate(required_facts()):
        if required.fact_kind is PITFactKind.MARKET_DATA:
            clock.value = NOW
        authority.record_fact(
            pit_fact(required),
            actor="source-ingestor",
            reason="record late ingest attack",
            idempotency_key=f"late-ingest-fact-{index}",
        )
        clock.value = INGEST_TIME
    clock.value = NOW
    evidence = authority.validate(pit_request(idempotency_key="validate-late-ingest"))

    assert evidence.outcome is PITValidationOutcome.REJECTED
    assert (
        "LATE_INGESTED_FACT_REJECTED:market:600000.SH:2026-08-08T06:44:00Z"
        in evidence.rejection_codes
    )


@pytest.mark.parametrize(
    ("attack", "expected"),
    [
        (
            {"eligibility": DataEligibility.EXPLORATORY},
            "INPUT_AUTHORITY_NOT_FORMAL:market:600000.SH:2026-08-08T06:44:00Z",
        ),
        (
            {"artifact": ref("DATASET", "alternate-authoritative-dataset")},
            "DATASET_LINEAGE_MISMATCH:market:600000.SH:2026-08-08T06:44:00Z",
        ),
        (
            {
                "source_manifest": ref(
                    "SOURCE_MANIFEST", "alternate-authoritative-source"
                )
            },
            "SOURCE_MANIFEST_LINEAGE_MISMATCH:market:600000.SH:2026-08-08T06:44:00Z",
        ),
    ],
)
def test_non_formal_or_mismatched_lineage_is_rejected(
    postgres_factory: PostgresConnectionFactory,
    attack: dict[str, object],
    expected: str,
) -> None:
    outcome, reasons = _validate_with_attacked_fact(
        postgres_factory,
        attacked_kind=PITFactKind.MARKET_DATA,
        attack=lambda _: attack,
        evidence_key=f"lineage-{expected}",
    )

    assert outcome is PITValidationOutcome.REJECTED
    assert expected in reasons


def test_back_adjusted_research_data_cannot_be_formal_pit(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(INGEST_TIME)
    authority = pit_authority(postgres_factory, clock=clock)
    authorize_source(authority, idempotency_key="back-adjusted-source")
    for index, required in enumerate(required_facts()):
        authority.record_fact(
            pit_fact(required),
            actor="source-ingestor",
            reason="record raw facts",
            idempotency_key=f"back-adjusted-fact-{index}",
        )
    clock.value = NOW

    evidence = authority.validate(
        pit_request(
            adjustment_mode="RESEARCH_BACK_ADJUSTED",
            idempotency_key="validate-back-adjusted",
        )
    )

    assert evidence.outcome is PITValidationOutcome.REJECTED
    assert "RESEARCH_BACK_ADJUSTED_NOT_PIT_SAFE" in evidence.rejection_codes


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (
            PITFactKind.THEME_MEMBERSHIP,
            "HISTORICAL_THEME_MEMBERSHIP_UNAVAILABLE",
        ),
        (PITFactKind.ETF_MEMBERSHIP, "HISTORICAL_ETF_MEMBERSHIP_UNAVAILABLE"),
        (PITFactKind.ST_STATUS, "HISTORICAL_ST_STATUS_UNAVAILABLE"),
        (
            PITFactKind.TRADING_STATUS,
            "HISTORICAL_SUSPENSION_STATUS_UNAVAILABLE",
        ),
        (PITFactKind.LISTING_STATUS, "HISTORICAL_LISTING_STATUS_UNAVAILABLE"),
        (
            PITFactKind.ADJUSTMENT_FACTOR,
            "CORPORATE_ACTION_AUTHORITY_UNAVAILABLE",
        ),
    ],
)
def test_missing_historical_authority_is_typed_and_rejected(
    postgres_factory: PostgresConnectionFactory,
    kind: PITFactKind,
    expected: str,
) -> None:
    authority = pit_authority(postgres_factory, clock=lambda: INGEST_TIME)
    authorize_source(authority, idempotency_key=f"typed-missing-source-{kind.value}")
    required = PITRequiredFact(
        logical_key=f"missing:{kind.value.lower()}:600000.SH",
        fact_kind=kind,
        subject="600000.SH",
    )

    snapshot = authority.as_of(
        PITAsOfQuery.create(
            scope_id="daily:2026-08-08",
            decision_time=DECISION_TIME,
            required_facts=(required,),
        )
    )

    assert snapshot.outcome is PITValidationOutcome.REJECTED
    assert f"{expected}:{required.logical_key}" in snapshot.rejection_codes
