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
    daily_override: PhaseDDailyDecisionBundle | None = None,
    policy_override: CompositeOperationalCompositionPolicy | None = None,
):
    supplemental = (
        supplemental_override
        if supplemental_override is not None
        else _supplemental(fixture)
    )
    daily = load_verified_daily_decision_artifact(
        publish_phase_d_daily_decision_artifact(
            root=tmp_path / "daily",
            bundle=daily_override or _daily_bundle(fixture),
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
        composition_policy=policy_override or _policy(),
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
    "field_name",
    [
        "theme_observations",
        "capital_observations",
        "symbol_observations",
        "theme_memberships",
        "etf_theme_mappings",
        "etf_observations",
    ],
)
def test_empty_required_collection_is_missing_not_conflicted(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
    field_name: str,
) -> None:
    supplemental = _supplemental(daily_decision_fixture)
    incomplete = replace(supplemental, **{field_name: ()})

    manifest = _build(
        tmp_path,
        daily_decision_fixture,
        supplemental_override=incomplete,
    )

    assert (
        manifest.status
        is CompositeOperationalCompositionStatus.DATA_INSUFFICIENT
    )
    assert manifest.missing_evidence
    assert not manifest.source_conflicts


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


def test_container_availability_is_derived_from_verified_evidence(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    supplemental = _supplemental(daily_decision_fixture)
    manifest = _build(
        tmp_path,
        daily_decision_fixture,
        supplemental_override=supplemental,
    )
    by_role = {
        item.role: item for item in manifest.component_references
        if item.role in {
            CompositeOperationalComponentRole.DAILY_SOURCE_MANIFEST,
            CompositeOperationalComponentRole.DAILY_DECISION_ARTIFACT,
            CompositeOperationalComponentRole.SUPPLEMENTAL_SOURCE_MANIFEST,
            CompositeOperationalComponentRole.SUPPLEMENTAL_EVIDENCE_BUNDLE,
        }
    }
    expected_daily = max(
        item.retrieved_at.value
        for item in daily_decision_fixture.source_manifest.source_artifacts
    )
    expected_supplemental = max(
        item.available_at.value
        for values in (
            (supplemental.market_observation,),
            supplemental.theme_observations,
            supplemental.capital_observations,
            supplemental.symbol_observations,
            supplemental.theme_memberships,
            supplemental.etf_theme_mappings,
            supplemental.etf_observations,
            supplemental.stock_daily_bars,
        )
        for item in values
    )

    assert by_role[
        CompositeOperationalComponentRole.DAILY_SOURCE_MANIFEST
    ].availability_time.value == expected_daily
    assert by_role[
        CompositeOperationalComponentRole.DAILY_DECISION_ARTIFACT
    ].availability_time.value == expected_daily
    assert by_role[
        CompositeOperationalComponentRole.SUPPLEMENTAL_SOURCE_MANIFEST
    ].availability_time.value == expected_supplemental
    assert by_role[
        CompositeOperationalComponentRole.SUPPLEMENTAL_EVIDENCE_BUNDLE
    ].availability_time.value == expected_supplemental


def test_unknown_membership_theme_is_conflicted(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    supplemental = _supplemental(daily_decision_fixture)
    conflicted = replace(
        supplemental,
        theme_memberships=(
            replace(
                supplemental.theme_memberships[0],
                primary_theme_id="unknown-theme",
            ),
            *supplemental.theme_memberships[1:],
        ),
    )

    manifest = _build(
        tmp_path,
        daily_decision_fixture,
        supplemental_override=conflicted,
    )

    assert manifest.status is CompositeOperationalCompositionStatus.CONFLICTED
    assert "THEME_MEMBERSHIP_UNKNOWN_THEME_CONFLICT" in manifest.source_conflicts


def test_policy_required_role_and_field_absence_is_data_insufficient(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    base = _policy()
    strict = CompositeOperationalCompositionPolicy.create(
        profile_id=base.profile_id,
        required_component_roles=(
            *base.required_component_roles,
            CompositeOperationalComponentRole.STOCK_DAILY_BAR,
        ),
        required_field_authorities=(
            *base.required_field_authorities,
            CompositeOperationalFieldAuthorityRequirement(
                field_group=CompositeOperationalFieldGroup.STOCK_DAILY_BAR,
                component_role=(
                    CompositeOperationalComponentRole.STOCK_DAILY_BAR
                ),
            ),
        ),
        allowed_data_eligibility=base.allowed_data_eligibility,
        decision_time_policy=base.decision_time_policy,
        source_conflict_policy=base.source_conflict_policy,
        coverage_policy=base.coverage_policy,
        builder_revision=base.builder_revision,
    )

    manifest = _build(
        tmp_path,
        daily_decision_fixture,
        policy_override=strict,
    )

    assert (
        manifest.status
        is CompositeOperationalCompositionStatus.DATA_INSUFFICIENT
    )
    assert "REQUIRED_COMPONENT_ROLE_MISSING:STOCK_DAILY_BAR" in (
        manifest.missing_evidence
    )
    assert (
        "REQUIRED_FIELD_AUTHORITY_MISSING:STOCK_DAILY_BAR:STOCK_DAILY_BAR"
        in manifest.missing_evidence
    )


def test_future_source_availability_is_conflicted(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    supplemental = _supplemental(daily_decision_fixture)
    future_source = replace(
        supplemental.source_manifest.source_artifacts[0],
        retrieved_at=replace(
            supplemental.source_manifest.source_artifacts[0].retrieved_at,
            value=supplemental.decision_time.value + timedelta(seconds=1),
        ),
    )
    future_manifest = replace(
        supplemental.source_manifest,
        source_artifacts=(
            future_source,
            *supplemental.source_manifest.source_artifacts[1:],
        ),
    )

    manifest = _build(
        tmp_path,
        daily_decision_fixture,
        supplemental_override=replace(
            supplemental,
            source_manifest=future_manifest,
        ),
    )

    assert manifest.status is CompositeOperationalCompositionStatus.CONFLICTED
    assert any(
        item.startswith("COMPONENT_AVAILABLE_AFTER_DECISION_TIME")
        for item in manifest.source_conflicts
    )


def test_cross_authority_artifact_id_with_different_hash_is_conflicted(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    supplemental = _supplemental(daily_decision_fixture)
    daily_price_id = daily_decision_fixture.decision_snapshot.decision_snapshot_id
    market_source_id = supplemental.market_observation.source_artifact_id
    source_artifacts = tuple(
        replace(item, artifact_id=daily_price_id)
        if item.artifact_id == market_source_id
        else item
        for item in supplemental.source_manifest.source_artifacts
    )
    conflicting_manifest = replace(
        supplemental.source_manifest,
        source_artifacts=source_artifacts,
    )
    conflicting = replace(
        supplemental,
        source_manifest=conflicting_manifest,
        market_observation=replace(
            supplemental.market_observation,
            source_artifact_id=daily_price_id,
        ),
    )

    manifest = _build(
        tmp_path,
        daily_decision_fixture,
        supplemental_override=conflicting,
    )

    assert manifest.status is CompositeOperationalCompositionStatus.CONFLICTED
    assert f"ARTIFACT_HASH_CONFLICT:{daily_price_id}" in manifest.source_conflicts


def test_prediction_run_population_mismatch_is_conflicted(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    daily = _daily_bundle(daily_decision_fixture)
    assert len(daily.prediction_runs) >= 2
    run = daily.prediction_runs[1]
    if run.predictions:
        changed_run = replace(
            run,
            predictions=(
                replace(run.predictions[0], symbol="999999.SH"),
                *run.predictions[1:],
            ),
        )
    else:
        changed_run = replace(
            run,
            rejections=tuple(
                sorted(
                    (
                        replace(run.rejections[0], symbol="999999.SH"),
                        *run.rejections[1:],
                    ),
                    key=lambda item: item.symbol,
                )
            ),
        )
    mismatched_daily = replace(
        daily,
        prediction_runs=(daily.prediction_runs[0], changed_run),
        recommendations=(),
        entry_assessments=(),
    )

    manifest = _build(
        tmp_path,
        daily_decision_fixture,
        daily_override=mismatched_daily,
    )

    assert manifest.status is CompositeOperationalCompositionStatus.CONFLICTED
    assert "PREDICTION_RUN_POPULATION_CONFLICT" in manifest.source_conflicts
