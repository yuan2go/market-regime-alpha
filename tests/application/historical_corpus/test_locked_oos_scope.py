from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.application.historical_corpus.locked_oos_scope import (
    FrozenLockedOOSScope,
    assess_locked_oos_access,
    freeze_locked_oos_scope,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId, DatasetId
from market_regime_alpha.data.trading_calendar import (
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.universe.research import (
    HistoricalConstituentCohort,
    HistoricalConstituentTimeline,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
EXTERNAL_TARGET = date(2026, 1, 19)
CUTOFF = datetime(2026, 1, 22, 11, tzinfo=SHANGHAI)
PROTOCOL = ValidationArtifactReference(
    "RESEARCH_EXPERIMENT_DEFINITION",
    ArtifactId("research-experiment-definition:wp-alpha-proof-02"),
    canonical_hash({"protocol": "wp-alpha-proof-02"}),
)


def test_locked_scope_freezes_after_external_without_outcome_values() -> None:
    scope = freeze_locked_oos_scope(
        protocol_reference=PROTOCOL,
        calendar=_calendar(),
        universe_timeline=_timeline(),
        external_final_target_session=EXTERNAL_TARGET,
        data_cutoff=CUTOFF,
    )

    assert scope.decision_sessions == (date(2026, 1, 20), date(2026, 1, 21))
    assert scope.target_session_bindings == (
        (date(2026, 1, 20), date(2026, 1, 21)),
        (date(2026, 1, 21), date(2026, 1, 22)),
    )
    assert scope.outcome_values_read is False
    assert scope.session_universe_references == (
        (date(2026, 1, 20), _universe_reference()),
        (date(2026, 1, 21), _universe_reference()),
    )
    assert FrozenLockedOOSScope.from_canonical_dict(
        scope.to_canonical_dict()
    ) == scope


def test_locked_scope_access_fails_closed_until_both_gates_support() -> None:
    scope = freeze_locked_oos_scope(
        protocol_reference=PROTOCOL,
        calendar=_calendar(),
        universe_timeline=_timeline(),
        external_final_target_session=EXTERNAL_TARGET,
        data_cutoff=CUTOFF,
    )

    blocked = assess_locked_oos_access(
        scope=scope,
        formal_pit_supported=False,
        physical_correctness_supported=False,
    )
    allowed = assess_locked_oos_access(
        scope=scope,
        formal_pit_supported=True,
        physical_correctness_supported=True,
    )

    assert blocked.outcome_access_allowed is False
    assert blocked.reason_codes == (
        "FORMAL_PIT_NOT_SUPPORTED",
        "PHYSICAL_CORRECTNESS_NOT_SUPPORTED",
    )
    assert allowed.outcome_access_allowed is True
    assert allowed.reason_codes == ("LOCKED_OOS_OUTCOME_ACCESS_ELIGIBLE",)


def test_locked_scope_rejects_changed_external_boundary_or_incomplete_target() -> None:
    with pytest.raises(ValueError, match="frozen External final Target"):
        freeze_locked_oos_scope(
            protocol_reference=PROTOCOL,
            calendar=_calendar(),
            universe_timeline=_timeline(),
            external_final_target_session=date(2026, 1, 16),
            data_cutoff=CUTOFF,
        )
    with pytest.raises(ValueError, match="complete Locked OOS Target"):
        freeze_locked_oos_scope(
            protocol_reference=PROTOCOL,
            calendar=_calendar(),
            universe_timeline=_timeline(),
            external_final_target_session=EXTERNAL_TARGET,
            data_cutoff=datetime(2026, 1, 20, 10, tzinfo=SHANGHAI),
        )


def _calendar():
    sessions = tuple(
        TradingSession(
            item,
            datetime.combine(item, time(15), SHANGHAI),
        )
        for item in (
            EXTERNAL_TARGET,
            date(2026, 1, 20),
            date(2026, 1, 21),
            date(2026, 1, 22),
            date(2026, 1, 23),
        )
    )
    return build_trading_calendar_artifact(
        source_dataset_id=DatasetId("wp-alpha-proof-calendar"),
        market="A_SHARE",
        calendar_version="wp-alpha-proof-02/v1",
        timezone_name="Asia/Shanghai",
        sessions=sessions,
    )


def _universe_reference() -> ValidationArtifactReference:
    return ValidationArtifactReference(
        "FREE_RESEARCH_UNIVERSE",
        ArtifactId("free-research-universe:wp-alpha-proof-cohort"),
        canonical_hash({"cohort": "wp-alpha-proof"}),
    )


def _timeline() -> HistoricalConstituentTimeline:
    return HistoricalConstituentTimeline.create(
        start_date=date(2026, 1, 20),
        end_date=date(2026, 1, 21),
        queried_trading_dates=(date(2026, 1, 20), date(2026, 1, 21)),
        query_effective_dates=(
            (date(2026, 1, 20), date(2026, 1, 1)),
            (date(2026, 1, 21), date(2026, 1, 1)),
        ),
        cohorts=(
            HistoricalConstituentCohort(
                date(2026, 1, 1),
                _universe_reference(),
            ),
        ),
        scan_source_manifest_reference=ValidationArtifactReference(
            "SOURCE_MANIFEST",
            ArtifactId("source-manifest:wp-alpha-proof-timeline"),
            canonical_hash({"source": "timeline"}),
        ),
        raw_archive_id="wp-alpha-proof-timeline-archive",
        known_at=datetime(2026, 8, 25, tzinfo=ZoneInfo("UTC")),
    )
