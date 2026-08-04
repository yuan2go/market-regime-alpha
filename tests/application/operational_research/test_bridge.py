from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path

import pytest

from market_regime_alpha.application.daily_loop.commands import (
    DailyRunIdentity,
    RunRequestId,
)
from market_regime_alpha.application.operational_research.bridge import (
    adapt_operational_research_inputs,
)
from market_regime_alpha.application.operational_research.contracts import (
    CapitalObservationEvidence,
    ETFThemeMappingEvidence,
    MissingEvidence,
    PITThemeMembershipEvidence,
    SupplementalResearchEvidenceBundle,
    ThemeObservationEvidence,
)
from market_regime_alpha.application.operational_research.supplemental_artifact import (
    SUPPLEMENTAL_RESEARCH_EVIDENCE_FILES,
    load_verified_supplemental_research_evidence,
    publish_supplemental_research_evidence,
)
from market_regime_alpha.core.identity import (
    ArtifactId,
    FeatureDefinitionId,
    ProviderId,
)
from market_regime_alpha.core.time import AvailabilityTime, RetrievedAt
from market_regime_alpha.data.contracts import (
    DataEligibility,
    SourceArtifactReference,
)
from market_regime_alpha.data.source_manifest import SourceManifest
from market_regime_alpha.data.daily_quality import (
    DailyDataQualityStatus,
    DataQualityFinding,
)
from market_regime_alpha.daily_decision.artifact import (
    DailyDecisionArtifactStatus,
    PhaseDDailyDecisionBundle,
    publish_phase_d_daily_decision_artifact,
)
from market_regime_alpha.daily_decision.entry import assess_entry_plumbing
from market_regime_alpha.daily_decision.reader_registry import (
    load_verified_daily_decision_artifact,
)
from market_regime_alpha.daily_decision.recommendation import (
    project_candidate_recommendations,
)
from market_regime_alpha.research.platform_v2.configs import (
    default_research_pipeline_config,
)
from market_regime_alpha.research.platform_v2.inputs import (
    ETFObservation,
    MarketObservation,
    ResearchEvidenceKind,
    ResearchInputBundle,
    SymbolResearchObservation,
)
from tests.daily_decision.conftest import DailyDecisionFixture
from scripts.run_operational_research import main as operational_research_main


def _daily_bundle(fixture: DailyDecisionFixture) -> PhaseDDailyDecisionBundle:
    recommendations = project_candidate_recommendations(
        prediction_runs=fixture.prediction_runs,
        decision_snapshot=fixture.decision_snapshot,
        data_quality_report=fixture.quality_report,
    )
    entries = assess_entry_plumbing(
        recommendations=recommendations,
        prediction_runs=fixture.prediction_runs,
        decision_snapshot=fixture.decision_snapshot,
        source_manifest=fixture.source_manifest,
        data_quality_report=fixture.quality_report,
        eligibility_snapshot=fixture.reconciliation.eligibility_snapshot,
    )
    return PhaseDDailyDecisionBundle(
        status=DailyDecisionArtifactStatus.DECISION_PUBLISHED,
        run_identity=DailyRunIdentity(
            run_request_id=RunRequestId("run-request-operational-research"),
            run_request_hash="sha256:" + "3" * 64,
            code_revision="phase-1-test-revision",
            configuration_hash="sha256:" + "4" * 64,
            source_manifest_id=fixture.source_manifest.source_manifest_id,
            source_manifest_content_hash=fixture.source_manifest.content_hash,
            source_content_hashes=tuple(
                sorted(set(fixture.source_manifest.source_hashes))
            ),
        ),
        source_archive_id=ArtifactId("source-operational-research-fixture"),
        source_manifest=fixture.source_manifest,
        data_quality_report=fixture.quality_report,
        universe_snapshot=fixture.reconciliation.universe_snapshot,
        eligibility_snapshot=fixture.reconciliation.eligibility_snapshot,
        decision_price_snapshot=fixture.decision_snapshot,
        feature_definitions=fixture.feature_definitions,
        feature_materializations=fixture.feature_materializations,
        prediction_runs=fixture.prediction_runs,
        recommendations=recommendations,
        entry_assessments=entries,
    )


def _supplemental(
    fixture: DailyDecisionFixture,
) -> SupplementalResearchEvidenceBundle:
    decision_time = fixture.source_manifest.decision_time
    available_at = AvailabilityTime(decision_time.value - timedelta(minutes=5))
    source_ids = {
        name: ArtifactId(f"supplemental-{name}-source")
        for name in (
            "market",
            "theme",
            "capital",
            "membership",
            "etf",
            "symbol",
        )
    }
    source_manifest = SourceManifest(
        provider_profile_id="supplemental-exploratory-fixture-v1",
        decision_time=decision_time,
        source_artifacts=tuple(
            SourceArtifactReference(
                artifact_id=artifact_id,
                provider_id=ProviderId("provider-supplemental-fixture"),
                retrieved_at=RetrievedAt(available_at.value),
                content_hash="sha256:" + str(index) * 64,
                locator=f"fixture://supplemental/{name}",
            )
            for index, (name, artifact_id) in enumerate(
                source_ids.items(), start=1
            )
        ),
        fields=(),
        source_conflicts=(),
        limitations=("SYNTHETIC_SUPPLEMENTAL_RESEARCH_EVIDENCE",),
        data_eligibility=DataEligibility.EXPLORATORY,
        schema_version=SourceManifest.SCHEMA_V2,
    )
    symbols = fixture.reconciliation.population.symbols
    memberships = tuple(
        PITThemeMembershipEvidence(
            symbol=symbol,
            primary_theme_id="theme-a" if index % 2 == 0 else "theme-b",
            supporting_theme_ids=(),
            available_at=available_at,
            source_artifact_id=source_ids["membership"],
        )
        for index, symbol in enumerate(symbols)
    )
    themes = tuple(
        ThemeObservationEvidence(
            theme_id=theme_id,
            theme_name=theme_name,
            benchmark_id="000300.SH",
            proxy_etf_ids=(etf_id,),
            available_at=available_at,
            source_artifact_id=source_ids["theme"],
            relative_strength_1d=0.01,
            relative_strength_3d=0.02,
            relative_strength_5d=0.03,
            relative_strength_10d=0.04,
            amount_expansion=0.20,
            breadth=0.70,
            new_high_breadth=0.40,
            leader_strength=0.65,
            participation_change=0.10,
            rank_persistence=0.70,
            confidence=1.0,
            reason_codes=("SYNTHETIC_FIXTURE",),
        )
        for theme_id, theme_name, etf_id in (
            ("theme-a", "Theme A", "510001.SH"),
            ("theme-b", "Theme B", "510002.SH"),
        )
    )
    capital = tuple(
        CapitalObservationEvidence(
            theme_id=theme.theme_id,
            available_at=available_at,
            source_artifact_id=source_ids["capital"],
            etf_amount_expansion=0.25,
            amount_persistence=0.60,
            capital_concentration=0.50,
            diffusion_score=0.55,
            reason_codes=("PUBLIC_PROXY_NOT_ACTOR_INTENT",),
        )
        for theme in themes
    )
    etf_mappings = tuple(
        ETFThemeMappingEvidence(
            etf_id=theme.proxy_etf_ids[0],
            theme_id=theme.theme_id,
            available_at=available_at,
            source_artifact_id=source_ids["etf"],
        )
        for theme in themes
    )
    return SupplementalResearchEvidenceBundle(
        source_manifest=source_manifest,
        decision_time=decision_time,
        market_observation=MarketObservation(
            available_at=available_at,
            source_artifact_id=source_ids["market"],
            market_direction_return=0.01,
            market_intraday_range_to_cutoff=0.01,
            market_amount_change_same_cutoff=0.20,
            candidate_breadth_at_cutoff=0.70,
            limit_structure_score=0.10,
            coverage=1.0,
            reason_codes=("SYNTHETIC_FIXTURE",),
        ),
        theme_observations=themes,
        capital_observations=capital,
        symbol_observations=tuple(
            SymbolResearchObservation(
                symbol=symbol,
                available_at=available_at,
                source_artifact_id=source_ids["symbol"],
                symbol_relative_strength=0.10,
                symbol_amount_expansion=0.20,
                theme_participation_contribution=0.10,
                leader_correlation=0.50,
                leader_lag=1.0,
                rank_persistence=0.50,
                amount_persistence=0.50,
                liquidity_eligible=True,
                history_complete=True,
                status_known=True,
                source_feature_ids=(
                    FeatureDefinitionId("supplemental-symbol-feature-v1"),
                ),
                reason_codes=("SYNTHETIC_FIXTURE",),
            )
            for symbol in symbols
        ),
        theme_memberships=memberships,
        etf_theme_mappings=etf_mappings,
        etf_observations=tuple(
            ETFObservation(
                etf_id=mapping.etf_id,
                theme_id=mapping.theme_id,
                available_at=available_at,
                source_artifact_id=source_ids["etf"],
                relative_strength=0.10,
                amount_expansion=0.20,
            )
            for mapping in etf_mappings
        ),
        stock_daily_bars=(),
        missing_evidence=(),
        reason_codes=("SYNTHETIC_FIXTURE_ONLY",),
        created_at=decision_time.value + timedelta(minutes=5),
        data_eligibility=DataEligibility.EXPLORATORY,
    )


def test_supplemental_bundle_is_content_addressed_and_verified(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    bundle = _supplemental(daily_decision_fixture)
    path = publish_supplemental_research_evidence(root=tmp_path, bundle=bundle)
    verified = load_verified_supplemental_research_evidence(path)

    assert {item.name for item in path.iterdir()} == set(
        SUPPLEMENTAL_RESEARCH_EVIDENCE_FILES
    )
    assert verified.bundle == bundle
    assert verified.bundle.bundle_id == bundle.bundle_id
    assert verified.bundle.content_hash == bundle.content_hash


def test_supplemental_bundle_rejects_late_or_unmanifested_evidence(
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    bundle = _supplemental(daily_decision_fixture)
    with pytest.raises(ValueError, match="available by Decision Time"):
        replace(
            bundle,
            theme_observations=(
                replace(
                    bundle.theme_observations[0],
                    available_at=AvailabilityTime(
                        bundle.decision_time.value + timedelta(seconds=1)
                    ),
                ),
                *bundle.theme_observations[1:],
            ),
        )
    with pytest.raises(ValueError, match="SourceManifest"):
        replace(
            bundle,
            market_observation=replace(
                bundle.market_observation,
                source_artifact_id=ArtifactId("not-in-source-manifest"),
            ),
        )


def test_bridge_fails_closed_on_missing_or_incomplete_mapping(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    daily_path = publish_phase_d_daily_decision_artifact(
        root=tmp_path / "daily",
        bundle=_daily_bundle(daily_decision_fixture),
    )
    daily = load_verified_daily_decision_artifact(daily_path)
    supplemental = _supplemental(daily_decision_fixture)

    with pytest.raises(ValueError, match="supplemental evidence is incomplete"):
        adapt_operational_research_inputs(
            daily,
            replace(
                supplemental,
                missing_evidence=(
                    MissingEvidence(
                        evidence_kind="PIT_THEME_MEMBERSHIP",
                        key="600000.SH",
                        reason_codes=("MAPPING_NOT_AVAILABLE",),
                    ),
                ),
            ),
        )
    with pytest.raises(ValueError, match="membership coverage"):
        adapt_operational_research_inputs(
            daily,
            replace(
                supplemental,
                theme_memberships=supplemental.theme_memberships[:-1],
            ),
        )


def test_legacy_v1_adapter_remains_canonically_readable_without_runner_entry(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    daily_path = publish_phase_d_daily_decision_artifact(
        root=tmp_path / "daily",
        bundle=_daily_bundle(daily_decision_fixture),
    )
    supplemental_path = publish_supplemental_research_evidence(
        root=tmp_path / "supplemental",
        bundle=_supplemental(daily_decision_fixture),
    )
    daily = load_verified_daily_decision_artifact(daily_path)
    supplemental = load_verified_supplemental_research_evidence(
        supplemental_path
    )
    legacy = adapt_operational_research_inputs(daily, supplemental.bundle)
    restored = ResearchInputBundle.from_canonical_dict(
        legacy.to_canonical_dict()
    )

    assert restored == legacy
    assert restored.evidence_kind is ResearchEvidenceKind.HISTORICAL_IMMUTABLE_ARCHIVE
    assert restored.data_eligibility is DataEligibility.EXPLORATORY
    assert str(_supplemental(daily_decision_fixture).bundle_id) in {
        str(item) for item in restored.input_artifact_ids
    }


def test_bridge_rejects_data_blocked_daily_artifact(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    published = _daily_bundle(daily_decision_fixture)
    blocked_quality = replace(
        published.data_quality_report,
        status=DailyDataQualityStatus.DATA_BLOCKED,
        findings=(
            DataQualityFinding(
                symbol=daily_decision_fixture.reconciliation.population.symbols[0],
                field_id="theme_mapping",
                critical_fact=None,
                reason_code="REQUIRED_EVIDENCE_MISSING",
                blocking=True,
            ),
        ),
    )
    blocked_bundle = PhaseDDailyDecisionBundle(
        status=DailyDecisionArtifactStatus.DATA_BLOCKED,
        run_identity=published.run_identity,
        source_archive_id=published.source_archive_id,
        source_manifest=published.source_manifest,
        data_quality_report=blocked_quality,
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
            root=tmp_path,
            bundle=blocked_bundle,
        )
    )
    with pytest.raises(ValueError, match="published Daily Artifact"):
        adapt_operational_research_inputs(
            daily,
            _supplemental(daily_decision_fixture),
        )


def test_operational_research_cli_runs_and_replays(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    daily_path = publish_phase_d_daily_decision_artifact(
        root=tmp_path / "daily",
        bundle=_daily_bundle(daily_decision_fixture),
    )
    supplemental_path = publish_supplemental_research_evidence(
        root=tmp_path / "supplemental",
        bundle=_supplemental(daily_decision_fixture),
    )
    from market_regime_alpha.application.operational_research.composite_artifact import (
        publish_composite_operational_manifest,
    )
    from market_regime_alpha.application.operational_research.composite_manifest import (
        CompositeOperationalManifestBuilder,
    )
    from tests.application.operational_research.test_composite_manifest_builder import (
        _policy,
    )

    daily = load_verified_daily_decision_artifact(daily_path)
    supplemental = load_verified_supplemental_research_evidence(
        supplemental_path
    )
    composite_path = publish_composite_operational_manifest(
        root=tmp_path / "composite",
        manifest=CompositeOperationalManifestBuilder().build(
            daily=daily,
            supplemental=supplemental,
            composition_policy=_policy(),
            created_at=(
                daily.bundle.source_manifest.decision_time.value
                + timedelta(minutes=10)
            ),
        ),
        composition_policy=_policy(),
    )
    config_path = tmp_path / "research-config.json"
    config_path.write_text(
        json.dumps(default_research_pipeline_config().to_canonical_dict()),
        encoding="utf-8",
    )
    output_root = tmp_path / "research"

    assert operational_research_main(
        (
            "run",
            "--composite-package",
            str(composite_path),
            "--daily-artifact",
            str(daily_path),
            "--supplemental-artifact",
            str(supplemental_path),
            "--research-config",
            str(config_path),
            "--output-root",
            str(output_root),
            "--code-revision",
            "phase-1-cli-test",
        )
    ) == 0
    run_result = json.loads(capsys.readouterr().out)
    assert run_result["formal_pit"] == "FORMAL_PIT_NOT_ESTABLISHED"
    assert run_result["formal_oos_alpha"] == "FORMAL_OOS_ALPHA_NOT_ESTABLISHED"
    assert run_result["trading_authority"] == "TRADING_AUTHORITY_NOT_GRANTED"
    artifact_path = output_root / run_result["artifact_id"]
    assert operational_research_main(
        ("replay", "--artifact", str(artifact_path))
    ) == 0
    replay_result = json.loads(capsys.readouterr().out)
    assert replay_result == run_result


def test_operational_research_cli_has_no_direct_v1_run_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        operational_research_main(
            (
                "run",
                "--daily-artifact",
                str(tmp_path / "daily"),
                "--supplemental-artifact",
                str(tmp_path / "supplemental"),
                "--research-config",
                str(tmp_path / "config.json"),
                "--output-root",
                str(tmp_path / "research"),
                "--code-revision",
                "h6-cli-boundary-test",
            )
        )

    assert "--composite-package" in capsys.readouterr().err
