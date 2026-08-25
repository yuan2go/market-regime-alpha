from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.application.historical_corpus.frozen_experiment import (
    create_wp_alpha_research_01_historical_experiment,
)
from market_regime_alpha.application.historical_corpus.locked_oos_scope import (
    WP_ALPHA_PROOF_02_EXTERNAL_FINAL_TARGET,
)
from market_regime_alpha.application.historical_corpus.postgres_locked_oos_scope import (
    PostgresLockedOOSScopeAuthority,
)
from market_regime_alpha.application.research_evaluation.targets import (
    exploratory_five_minute_multi_horizon_protocol,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.core.identity import ArtifactId, DatasetId
from market_regime_alpha.data.trading_calendar import (
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.universe.postgres_research import (
    PostgresFreeResearchUniverseRepository,
)
from market_regime_alpha.universe.research import (
    FreeDataEvidenceOrigin,
    HistoricalConstituentCohort,
    HistoricalConstituentTimeline,
    build_free_research_universe_snapshot,
)


NOW = datetime(2026, 8, 25, 1, tzinfo=UTC)
SHANGHAI = ZoneInfo("Asia/Shanghai")


def test_locked_scope_is_exact_owner_reloaded_idempotent_and_append_only(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    research = PostgresResearchValidationRepository(postgres_factory)
    universe = PostgresFreeResearchUniverseRepository(postgres_factory)
    experiment = create_wp_alpha_research_01_historical_experiment(
        exploratory_five_minute_multi_horizon_protocol(),
        locked_at=NOW,
    )
    research.record_historical_experiment_definition(
        experiment,
        recorded_at=NOW,
    )
    calendar = _calendar()
    calendar_reference = ValidationArtifactReference(
        "TRADING_CALENDAR",
        calendar.artifact_id,
        calendar.content_hash,
    )
    research.record(
        artifact_id=calendar.artifact_id,
        artifact_hash=calendar.content_hash,
        artifact_kind="TRADING_CALENDAR",
        evidence_authority="ENGINEERING_ONLY",
        payload=calendar.semantic_payload(),
        created_at=NOW,
    )
    snapshot = _universe_snapshot()
    universe.publish(snapshot)
    timeline = _timeline(
        ValidationArtifactReference(
            "FREE_RESEARCH_UNIVERSE",
            snapshot.snapshot_id,
            snapshot.snapshot_hash,
        )
    )
    universe.publish_timeline(timeline)
    authority = PostgresLockedOOSScopeAuthority(postgres_factory)

    first = authority.freeze(
        protocol_reference=ValidationArtifactReference(
            "RESEARCH_EXPERIMENT_DEFINITION",
            experiment.definition_id,
            experiment.definition_hash,
        ),
        calendar_reference=calendar_reference,
        universe_timeline_reference=timeline.reference,
        external_final_target_session=(
            WP_ALPHA_PROOF_02_EXTERNAL_FINAL_TARGET
        ),
        data_cutoff=datetime(2026, 1, 22, 11, tzinfo=SHANGHAI),
        recorded_at=NOW,
    )
    second = authority.freeze(
        protocol_reference=first.protocol_reference,
        calendar_reference=first.calendar_reference,
        universe_timeline_reference=first.universe_timeline_reference,
        external_final_target_session=first.external_final_target_session,
        data_cutoff=first.data_cutoff,
        recorded_at=NOW,
    )

    assert second == first
    assert authority.get(first.reference) == first
    assert first.outcome_values_read is False

    with postgres_factory.connection() as connection:
        with pytest.raises(Exception, match="append-only"):
            connection.execute(
                "UPDATE frozen_locked_oos_scope "
                "SET decision_session_count = 99 WHERE scope_id = %s",
                (str(first.scope_id),),
            )
        connection.rollback()


def test_locked_scope_owner_rejects_upstream_hash_drift(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    authority = PostgresLockedOOSScopeAuthority(postgres_factory)

    with pytest.raises(KeyError):
        authority.freeze(
            protocol_reference=ValidationArtifactReference(
                "RESEARCH_EXPERIMENT_DEFINITION",
                ArtifactId("missing-protocol"),
                canonical_hash({"missing": "protocol"}),
            ),
            calendar_reference=ValidationArtifactReference(
                "TRADING_CALENDAR",
                ArtifactId("missing-calendar"),
                canonical_hash({"missing": "calendar"}),
            ),
            universe_timeline_reference=ValidationArtifactReference(
                "HISTORICAL_CONSTITUENT_TIMELINE",
                ArtifactId("missing-timeline"),
                canonical_hash({"missing": "timeline"}),
            ),
            external_final_target_session=(
                WP_ALPHA_PROOF_02_EXTERNAL_FINAL_TARGET
            ),
            data_cutoff=datetime(2026, 1, 22, 11, tzinfo=SHANGHAI),
            recorded_at=NOW,
        )


def _calendar():
    dates = (
        date(2026, 1, 19),
        date(2026, 1, 20),
        date(2026, 1, 21),
        date(2026, 1, 22),
        date(2026, 1, 23),
    )
    return build_trading_calendar_artifact(
        source_dataset_id=DatasetId("locked-oos-owner-calendar"),
        market="A_SHARE",
        calendar_version="wp-alpha-proof-02-test/v1",
        timezone_name="Asia/Shanghai",
        sessions=tuple(
            TradingSession(item, datetime.combine(item, time(15), SHANGHAI))
            for item in dates
        ),
    )


def _universe_snapshot():
    return build_free_research_universe_snapshot(
        as_of_date=date(2026, 1, 1),
        known_at=NOW,
        provider_id="provider-test",
        provider_contract="provider-test/v1",
        source_manifest_reference=ValidationArtifactReference(
            "SOURCE_MANIFEST",
            ArtifactId("locked-oos-owner-manifest"),
            canonical_hash({"source": "locked-oos-owner"}),
        ),
        raw_archive_id="locked-oos-owner-archive",
        evidence_origin=FreeDataEvidenceOrigin.ENGINEERING_FIXTURE,
        rows=(
            {
                "code": "sz.000001",
                "code_name": "fixture",
                "ipoDate": "1991-04-03",
                "outDate": "",
                "type": "1",
                "status": "1",
            },
        ),
    )


def _timeline(
    universe_reference: ValidationArtifactReference,
) -> HistoricalConstituentTimeline:
    decisions = (date(2026, 1, 20), date(2026, 1, 21))
    return HistoricalConstituentTimeline.create(
        start_date=decisions[0],
        end_date=decisions[-1],
        queried_trading_dates=decisions,
        query_effective_dates=tuple(
            (item, date(2026, 1, 1)) for item in decisions
        ),
        cohorts=(
            HistoricalConstituentCohort(
                date(2026, 1, 1),
                universe_reference,
            ),
        ),
        scan_source_manifest_reference=ValidationArtifactReference(
            "SOURCE_MANIFEST",
            ArtifactId("locked-oos-timeline-manifest"),
            canonical_hash({"source": "locked-oos-timeline"}),
        ),
        raw_archive_id="locked-oos-timeline-archive",
        known_at=NOW,
    )
