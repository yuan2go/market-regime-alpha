from datetime import UTC, date, datetime

from market_regime_alpha.application.free_data_operation.research_universe import (
    build_historical_trading_calendar,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.universe.research import (
    HistoricalConstituentCohort,
    HistoricalConstituentTimeline,
)


def test_historical_calendar_uses_exact_provider_sessions_and_timeline_identity() -> None:
    timeline = HistoricalConstituentTimeline.create(
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 6),
        queried_trading_dates=(
            date(2025, 1, 2),
            date(2025, 1, 3),
            date(2025, 1, 6),
        ),
        query_effective_dates=(
            (date(2025, 1, 2), date(2024, 12, 30)),
            (date(2025, 1, 3), date(2024, 12, 30)),
            (date(2025, 1, 6), date(2025, 1, 6)),
        ),
        cohorts=(
            HistoricalConstituentCohort(
                effective_date=date(2024, 12, 30),
                snapshot_reference=_reference("FREE_RESEARCH_UNIVERSE", "u1"),
            ),
            HistoricalConstituentCohort(
                effective_date=date(2025, 1, 6),
                snapshot_reference=_reference("FREE_RESEARCH_UNIVERSE", "u2"),
            ),
        ),
        scan_source_manifest_reference=_reference("SOURCE_MANIFEST", "manifest"),
        raw_archive_id="raw-calendar-history",
        known_at=datetime(2026, 8, 25, tzinfo=UTC),
    )

    calendar = build_historical_trading_calendar(timeline)

    assert calendar.trading_dates == timeline.queried_trading_dates
    assert str(calendar.source_dataset_id) == str(timeline.timeline_id)
    assert calendar.calendar_version == "BAOSTOCK_HISTORY_SCAN_V1"
    assert all(
        session.session_close.hour == 15
        and session.session_close.minute == 0
        and session.session_close.utcoffset() is not None
        for session in calendar.sessions
    )


def _reference(kind: str, name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(name),
        "sha256:" + name.encode().hex().ljust(64, "0")[:64],
    )
