from __future__ import annotations

from datetime import UTC, date, datetime

import psycopg
import pytest

from market_regime_alpha.application.continuous_research.daily_alpha import (
    DailyAlphaEvidenceGate,
    DailyAlphaPredictionSnapshot,
)
from market_regime_alpha.application.continuous_research.postgres_daily_alpha import (
    PostgresDailyAlphaPredictionAuthority,
)
from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId, DatasetId
from market_regime_alpha.data.pit_authority import PITArtifactReference
from market_regime_alpha.data.postgres_pit_authority import PostgresPITAuthority
from market_regime_alpha.data.postgres_trading_calendar import (
    PostgresPITTradingCalendarSnapshotRepository,
)
from market_regime_alpha.data.trading_calendar import (
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from tests.persistence.postgres.pit_fixture import (
    FixturePITArtifactAuthorityResolver,
    MutableClock,
    fixture_provider_policy,
)


NOW = datetime(2026, 8, 21, 6, 55, tzinfo=UTC)


def _reference(kind: str, name: str) -> RuntimeArtifactReference:
    return RuntimeArtifactReference(
        kind,
        ArtifactId(name),
        canonical_hash({"kind": kind, "name": name}),
    )


class RecordingResolver:
    def __init__(self) -> None:
        self.calls = 0

    def verify_snapshot_sources(self, snapshot: DailyAlphaPredictionSnapshot) -> None:
        snapshot.verify_identity()
        self.calls += 1


def _snapshot(
    calendar_reference: RuntimeArtifactReference,
) -> DailyAlphaPredictionSnapshot:
    return DailyAlphaPredictionSnapshot.create(
        run_reference=_reference("CONTINUOUS_RESEARCH_RUN", "run"),
        tick_reference=_reference("CONTINUOUS_RUNTIME_TICK", "tick"),
        code_reference=_reference("CONTINUOUS_RUN_CODE_IDENTITY", "code"),
        configuration_references=(_reference("RESEARCH_CONFIGURATION", "config"),),
        provider_evidence_reference=_reference("EVIDENCE_COMMIT", "evidence"),
        dataset_reference=_reference("MARKET_DATA_DATASET", "dataset"),
        universe_reference=_reference("OPERATIONAL_UNIVERSE", "universe"),
        feature_references=(_reference("FEATURE_BUNDLE_V2", "features"),),
        context_references=(
            _reference("RESEARCH_DAILY_SUMMARY", "research-summary"),
        ),
        candidate_reference=_reference("CANDIDATE_SET", "candidate"),
        signal_reference=None,
        forecast_references=(_reference("STATE_STAGE_FORECAST", "forecast"),),
        strategy_diagnostic_reference=_reference(
            "MULTI_STRATEGY_CYCLE", "strategy"
        ),
        evidence_gate=DailyAlphaEvidenceGate.inactive(),
        trading_date=date(2026, 8, 21),
        target_session_date=date(2026, 8, 24),
        target_calendar_reference=calendar_reference,
        decision_time=NOW,
        available_at=NOW,
        symbols=(),
        reason_codes=("DAILY_PREDICTION_FROZEN_BEFORE_OUTCOME",),
    )


def test_daily_alpha_owner_is_idempotent_append_only_and_reload_verified(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    resolver = RecordingResolver()
    authority = PostgresDailyAlphaPredictionAuthority(
        postgres_factory,
        resolver=resolver,
    )
    expected = _snapshot(_seed_calendar(postgres_factory))
    assert expected.target_calendar_reference is not None

    assert authority.put(expected) == expected
    assert authority.put(expected) == expected
    assert authority.get(expected.snapshot_id) == expected
    assert resolver.calls == 5

    with postgres_factory.connection() as connection:
        with pytest.raises(psycopg.errors.RaiseException):
            connection.execute(
                """
                UPDATE research_validation_artifact
                SET evidence_authority = 'BLOCKED'
                WHERE artifact_id = %s
                """,
                (str(expected.snapshot_id),),
            )
        connection.rollback()
        row = connection.execute(
            """
            SELECT decision_session, target_session,
                   trading_calendar_id, trading_calendar_hash
            FROM daily_alpha_prediction_target_session
            WHERE snapshot_id = %s AND snapshot_hash = %s
            """,
            (str(expected.snapshot_id), expected.snapshot_hash),
        ).fetchone()
        assert row == (
            expected.trading_date,
            expected.target_session_date,
            str(expected.target_calendar_reference.artifact_id),
            expected.target_calendar_reference.content_hash,
        )
        with pytest.raises(psycopg.errors.RaiseException):
            connection.execute(
                """
                UPDATE daily_alpha_prediction_target_session
                SET target_session = target_session + 1
                WHERE snapshot_id = %s
                """,
                (str(expected.snapshot_id),),
            )


def _seed_calendar(
    factory: PostgresConnectionFactory,
) -> RuntimeArtifactReference:
    calendar = build_trading_calendar_artifact(
        source_dataset_id=DatasetId("daily-alpha-target-calendar-dataset"),
        market="CN_A_SHARE",
        calendar_version="daily-alpha-target-calendar-v1",
        timezone_name="Asia/Shanghai",
        sessions=(
            TradingSession(date(2026, 8, 21), datetime(2026, 8, 21, 7, tzinfo=UTC)),
            TradingSession(date(2026, 8, 24), datetime(2026, 8, 24, 7, tzinfo=UTC)),
        ),
    )
    PostgresPITAuthority(
        factory,
        clock=MutableClock(NOW),
        artifact_resolver=FixturePITArtifactAuthorityResolver(),
        provider_policy=fixture_provider_policy(),
    ).resolve_artifact(
        PITArtifactReference(
            "TRADING_CALENDAR", calendar.artifact_id, calendar.content_hash
        ),
        actor="daily-alpha-target-test",
        reason="bind exact target calendar",
        idempotency_key="daily-alpha-target-calendar-owner",
    )
    PostgresPITTradingCalendarSnapshotRepository(factory).record(calendar)
    return RuntimeArtifactReference(
        "TRADING_CALENDAR", calendar.artifact_id, calendar.content_hash
    )
