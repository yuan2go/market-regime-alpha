from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from market_regime_alpha.application.operational_research.composite_manifest import (
    CompositeCoveragePolicy,
    CompositeDecisionTimePolicy,
    CompositeOperationalComponentRole,
    CompositeOperationalCompositionPolicy,
    CompositeOperationalCompositionStatus,
    CompositeOperationalFieldAuthorityRequirement,
    CompositeOperationalFieldGroup,
    CompositeOperationalManifestBuilder,
    CompositeSourceConflictPolicy,
)
from market_regime_alpha.application.operational_research.contracts import (
    MissingEvidence,
)
from market_regime_alpha.application.operational_research.supplemental_artifact import (
    load_verified_supplemental_research_evidence,
    publish_supplemental_research_evidence,
)
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.daily_quality import (
    DailyDataQualityStatus,
    DataQualityFinding,
)
from market_regime_alpha.daily_decision.artifact import (
    DailyDecisionArtifactStatus,
    PhaseDDailyDecisionBundle,
    publish_phase_d_daily_decision_artifact,
)
from market_regime_alpha.daily_decision.reader_registry import (
    load_verified_daily_decision_artifact,
)
from tests.application.operational_research.test_bridge import (
    _daily_bundle,
    _supplemental,
)
from tests.daily_decision.conftest import DailyDecisionFixture


def _policy() -> CompositeOperationalCompositionPolicy:
    roles = tuple(CompositeOperationalComponentRole)
    roles = tuple(
        item
        for item in roles
        if item is not CompositeOperationalComponentRole.STOCK_DAILY_BAR
    )
    requirements = (
        (
            CompositeOperationalFieldGroup.PRICE,
            CompositeOperationalComponentRole.DECISION_PRICE_SNAPSHOT,
        ),
        (
            CompositeOperationalFieldGroup.TRADING_STATUS,
            CompositeOperationalComponentRole.DAILY_SOURCE_MANIFEST,
        ),
        (
            CompositeOperationalFieldGroup.ST_LISTING_STATUS,
            CompositeOperationalComponentRole.DAILY_SOURCE_MANIFEST,
        ),
        (
            CompositeOperationalFieldGroup.HISTORY,
            CompositeOperationalComponentRole.DAILY_SOURCE_MANIFEST,
        ),
        (
            CompositeOperationalFieldGroup.UNIVERSE,
            CompositeOperationalComponentRole.UNIVERSE_SNAPSHOT,
        ),
        (
            CompositeOperationalFieldGroup.ELIGIBILITY,
            CompositeOperationalComponentRole.ELIGIBILITY_SNAPSHOT,
        ),
        (
            CompositeOperationalFieldGroup.PREDICTION_POPULATION,
            CompositeOperationalComponentRole.PREDICTION_RUN,
        ),
        (
            CompositeOperationalFieldGroup.MARKET_OBSERVATION,
            CompositeOperationalComponentRole.MARKET_OBSERVATION,
        ),
        (
            CompositeOperationalFieldGroup.THEME_OBSERVATION,
            CompositeOperationalComponentRole.THEME_OBSERVATION,
        ),
        (
            CompositeOperationalFieldGroup.CAPITAL_OBSERVATION,
            CompositeOperationalComponentRole.CAPITAL_OBSERVATION,
        ),
        (
            CompositeOperationalFieldGroup.SYMBOL_CAPITAL_PROXY,
            CompositeOperationalComponentRole.SYMBOL_OBSERVATION,
        ),
        (
            CompositeOperationalFieldGroup.THEME_MEMBERSHIP,
            CompositeOperationalComponentRole.THEME_MEMBERSHIP,
        ),
        (
            CompositeOperationalFieldGroup.ETF_THEME_MAPPING,
            CompositeOperationalComponentRole.ETF_THEME_MAPPING,
        ),
        (
            CompositeOperationalFieldGroup.ETF_OBSERVATION,
            CompositeOperationalComponentRole.ETF_OBSERVATION,
        ),
    )
    return CompositeOperationalCompositionPolicy.create(
        profile_id="operational-exploratory-complete-v1",
        required_component_roles=roles,
        required_field_authorities=tuple(
            CompositeOperationalFieldAuthorityRequirement(
                field_group=field_group,
                component_role=component_role,
            )
            for field_group, component_role in requirements
        ),
        allowed_data_eligibility=(DataEligibility.EXPLORATORY,),
        decision_time_policy=CompositeDecisionTimePolicy.EXACT_MATCH,
        source_conflict_policy=CompositeSourceConflictPolicy.FAIL_CLOSED,
        coverage_policy=CompositeCoveragePolicy.EXACT_PREDICTION_POPULATION,
        builder_revision="h6-builder-v1",
    )


def _build(
    tmp_path: Path,
    fixture: DailyDecisionFixture,
    *,
    supplemental_override: object | None = None,
):
    supplemental = (
        supplemental_override
        if supplemental_override is not None
        else _supplemental(fixture)
    )
    daily = load_verified_daily_decision_artifact(
        publish_phase_d_daily_decision_artifact(
            root=tmp_path / "daily",
            bundle=_daily_bundle(fixture),
        )
    )
    supplemental_verified = load_verified_supplemental_research_evidence(
        publish_supplemental_research_evidence(
            root=tmp_path / "supplemental",
            bundle=supplemental,  # type: ignore[arg-type]
        )
    )
    return CompositeOperationalManifestBuilder().build(
        daily=daily,
        supplemental=supplemental_verified,
        composition_policy=_policy(),
        created_at=daily.bundle.source_manifest.decision_time.value
        + timedelta(minutes=10),
    )


def test_valid_daily_and_supplemental_build_verified_manifest(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    manifest = _build(tmp_path, daily_decision_fixture)

    assert manifest.status is CompositeOperationalCompositionStatus.VERIFIED
    assert set(item.role for item in manifest.component_references) == set(
        _policy().required_component_roles
    )
    assert not manifest.missing_evidence
    assert not manifest.source_conflicts
    assert manifest.reason_codes == ("COMPOSITE_OPERATIONAL_EVIDENCE_VERIFIED",)


def test_missing_supplemental_evidence_is_auditable_but_cannot_verify(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    supplemental = _supplemental(daily_decision_fixture)
    incomplete = replace(
        supplemental,
        missing_evidence=(
            MissingEvidence(
                evidence_kind="THEME_MEMBERSHIP",
                key="600000.SH",
                reason_codes=("MAPPING_NOT_AVAILABLE",),
            ),
        ),
    )

    manifest = _build(
        tmp_path,
        daily_decision_fixture,
        supplemental_override=incomplete,
    )

    assert (
        manifest.status
        is CompositeOperationalCompositionStatus.DATA_INSUFFICIENT
    )
    assert "MAPPING_NOT_AVAILABLE" in manifest.missing_evidence


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        (
            lambda bundle: replace(
                bundle,
                theme_memberships=bundle.theme_memberships[:-1],
            ),
            "PREDICTION_THEME_MEMBERSHIP_COVERAGE_CONFLICT",
        ),
        (
            lambda bundle: replace(
                bundle,
                capital_observations=bundle.capital_observations[:-1],
            ),
            "THEME_CAPITAL_COVERAGE_CONFLICT",
        ),
        (
            lambda bundle: replace(
                bundle,
                etf_observations=bundle.etf_observations[:-1],
            ),
            "ETF_MAPPING_OBSERVATION_COVERAGE_CONFLICT",
        ),
    ],
)
def test_scope_conflicts_are_terminal_and_fail_closed(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
    mutation: object,
    expected_reason: str,
) -> None:
    supplemental = _supplemental(daily_decision_fixture)
    conflicted = mutation(supplemental)  # type: ignore[operator]

    manifest = _build(
        tmp_path,
        daily_decision_fixture,
        supplemental_override=conflicted,
    )

    assert manifest.status is CompositeOperationalCompositionStatus.CONFLICTED
    assert expected_reason in manifest.source_conflicts


def test_source_conflict_wins_over_unrelated_missing_evidence(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    supplemental = _supplemental(daily_decision_fixture)
    conflicted = replace(
        supplemental,
        source_manifest=replace(
            supplemental.source_manifest,
            source_conflicts=("PROVIDER_VALUE_CONFLICT",),
        ),
        missing_evidence=(
            MissingEvidence(
                evidence_kind="STOCK_DAILY_BAR",
                key="600000.SH",
                reason_codes=("BAR_MISSING",),
            ),
        ),
    )

    manifest = _build(
        tmp_path,
        daily_decision_fixture,
        supplemental_override=conflicted,
    )

    assert manifest.status is CompositeOperationalCompositionStatus.CONFLICTED
    assert "SUPPLEMENTAL_SOURCE_CONFLICT:PROVIDER_VALUE_CONFLICT" in (
        manifest.source_conflicts
    )
    assert "BAR_MISSING" in manifest.missing_evidence


def test_data_blocked_daily_package_produces_data_insufficient_manifest(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    published = _daily_bundle(daily_decision_fixture)
    blocked = PhaseDDailyDecisionBundle(
        status=DailyDecisionArtifactStatus.DATA_BLOCKED,
        run_identity=published.run_identity,
        source_archive_id=published.source_archive_id,
        source_manifest=published.source_manifest,
        data_quality_report=replace(
            published.data_quality_report,
            status=DailyDataQualityStatus.DATA_BLOCKED,
            findings=(
                DataQualityFinding(
                    symbol=(
                        daily_decision_fixture.reconciliation.population.symbols[0]
                    ),
                    field_id="theme_mapping",
                    critical_fact=None,
                    reason_code="REQUIRED_EVIDENCE_MISSING",
                    blocking=True,
                ),
            ),
        ),
        universe_snapshot=None,
        eligibility_snapshot=None,
        decision_price_snapshot=published.decision_price_snapshot,
        feature_definitions=(),
        feature_materializations=(),
        prediction_runs=(),
        recommendations=(),
        entry_assessments=(),
    )
    daily = load_verified_daily_decision_artifact(
        publish_phase_d_daily_decision_artifact(
            root=tmp_path / "daily", bundle=blocked
        )
    )
    supplemental = load_verified_supplemental_research_evidence(
        publish_supplemental_research_evidence(
            root=tmp_path / "supplemental",
            bundle=_supplemental(daily_decision_fixture),
        )
    )

    manifest = CompositeOperationalManifestBuilder().build(
        daily=daily,
        supplemental=supplemental,
        composition_policy=_policy(),
        created_at=(
            daily.bundle.source_manifest.decision_time.value
            + timedelta(minutes=10)
        ),
    )

    assert (
        manifest.status
        is CompositeOperationalCompositionStatus.DATA_INSUFFICIENT
    )
    assert "DAILY_DECISION_NOT_PUBLISHED" in manifest.missing_evidence
    assert "DAILY_UNIVERSE_SNAPSHOT_MISSING" in manifest.missing_evidence
    assert "DAILY_ELIGIBILITY_SNAPSHOT_MISSING" in manifest.missing_evidence
    assert "DAILY_PREDICTION_RUNS_MISSING" in manifest.missing_evidence


def test_daily_and_supplemental_decision_time_mismatch_is_conflicted(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    supplemental = _supplemental(daily_decision_fixture)
    later = replace(
        supplemental.source_manifest.decision_time,
        value=(
            supplemental.source_manifest.decision_time.value
            + timedelta(minutes=1)
        ),
    )
    mismatched = replace(
        supplemental,
        source_manifest=replace(
            supplemental.source_manifest,
            decision_time=later,
        ),
        decision_time=later,
    )

    manifest = _build(
        tmp_path,
        daily_decision_fixture,
        supplemental_override=mismatched,
    )

    assert manifest.status is CompositeOperationalCompositionStatus.CONFLICTED
    assert "DAILY_SUPPLEMENTAL_DECISION_TIME_CONFLICT" in (
        manifest.source_conflicts
    )
