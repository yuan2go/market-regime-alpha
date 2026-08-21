from __future__ import annotations

from datetime import UTC, date, datetime

import psycopg
import pytest

from market_regime_alpha.application.continuous_research.daily_alpha import (
    DailyAlphaEvidenceGate,
    DailyAlphaPredictionSnapshot,
    PostgresDailyAlphaPredictionAuthority,
)
from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory


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


def _snapshot() -> DailyAlphaPredictionSnapshot:
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
    expected = _snapshot()

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
