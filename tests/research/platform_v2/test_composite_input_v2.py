from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from market_regime_alpha.application.operational_research.bridge import (
    adapt_verified_composite_operational_inputs,
    adapt_operational_research_inputs,
)
from market_regime_alpha.application.operational_research.composite_artifact import (
    publish_composite_operational_manifest,
    load_verified_composite_operational_manifest,
)
from market_regime_alpha.application.operational_research.composite_manifest import (
    CompositeOperationalCompositionStatus,
    CompositeOperationalInputManifest,
    CompositeOperationalManifestBuilder,
)
from market_regime_alpha.application.operational_research.supplemental_artifact import (
    load_verified_supplemental_research_evidence,
    publish_supplemental_research_evidence,
)
from market_regime_alpha.application.research_layer.runner import (
    PlatformResearchRunner,
)
from market_regime_alpha.daily_decision.artifact import (
    publish_phase_d_daily_decision_artifact,
)
from market_regime_alpha.daily_decision.reader_registry import (
    load_verified_daily_decision_artifact,
)
from market_regime_alpha.research.platform_v2.configs import (
    default_research_pipeline_config,
)
from market_regime_alpha.research.platform_v2.inputs import (
    ResearchEvidenceKind,
    ResearchInputBundle,
    research_input_bundle_from_canonical_dict,
)
from tests.application.operational_research.test_bridge import (
    _daily_bundle,
    _supplemental,
)
from tests.application.operational_research.test_composite_manifest_builder import (
    _policy,
)
from tests.daily_decision.conftest import DailyDecisionFixture


def _v2_inputs(tmp_path: Path, fixture: DailyDecisionFixture):
    daily = load_verified_daily_decision_artifact(
        publish_phase_d_daily_decision_artifact(
            root=tmp_path / "daily", bundle=_daily_bundle(fixture)
        )
    )
    supplemental = load_verified_supplemental_research_evidence(
        publish_supplemental_research_evidence(
            root=tmp_path / "supplemental", bundle=_supplemental(fixture)
        )
    )
    manifest = CompositeOperationalManifestBuilder().build(
        daily=daily,
        supplemental=supplemental,
        composition_policy=_policy(),
        created_at=daily.bundle.source_manifest.decision_time.value
        + timedelta(minutes=10),
    )
    verified_manifest = load_verified_composite_operational_manifest(
        publish_composite_operational_manifest(
            root=tmp_path / "composite",
            manifest=manifest,
            composition_policy=_policy(),
        )
    )
    legacy = adapt_operational_research_inputs(daily, supplemental.bundle)
    return (
        adapt_verified_composite_operational_inputs(
            composite=verified_manifest,
            daily=daily,
            supplemental=supplemental,
        ),
        legacy,
        verified_manifest,
    )


def test_v1_round_trip_remains_exact_while_v2_is_independent(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    inputs, legacy, _ = _v2_inputs(tmp_path, daily_decision_fixture)
    legacy_payload = legacy.to_canonical_dict()

    assert ResearchInputBundle.from_canonical_dict(legacy_payload) == legacy
    assert legacy_payload["schema_version"] == "research-input-bundle-v1"
    assert inputs.to_canonical_dict()["schema_version"] == "research-input-bundle-v2"
    assert inputs.evidence_kind is (
        ResearchEvidenceKind.OPERATIONAL_EXPLORATORY_ARCHIVE
    )
    assert research_input_bundle_from_canonical_dict(
        inputs.to_canonical_dict()
    ) == inputs


def test_v1_cannot_represent_operational_exploratory_evidence(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    _, legacy, _ = _v2_inputs(tmp_path, daily_decision_fixture)

    with pytest.raises(ValueError, match="ResearchInputBundleV2"):
        ResearchInputBundle(
            evidence_kind=(
                ResearchEvidenceKind.OPERATIONAL_EXPLORATORY_ARCHIVE
            ),
            source_manifest=legacy.source_manifest,
            universe_snapshot=legacy.universe_snapshot,
            eligibility_snapshot=legacy.eligibility_snapshot,
            decision_price_snapshot=legacy.decision_price_snapshot,
            market_observation=legacy.market_observation,
            theme_observations=legacy.theme_observations,
            symbol_observations=legacy.symbol_observations,
            theme_memberships=legacy.theme_memberships,
            etf_observations=legacy.etf_observations,
            stock_daily_bars=legacy.stock_daily_bars,
            prediction_runs=legacy.prediction_runs,
            input_artifact_ids=legacy.input_artifact_ids,
            input_content_hashes=legacy.input_content_hashes,
            created_at=legacy.created_at,
            data_eligibility=legacy.data_eligibility,
        )


def test_v2_binds_composite_and_keeps_daily_primary_source_manifest(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    inputs, _, verified_manifest = _v2_inputs(tmp_path, daily_decision_fixture)
    lineage = dict(
        zip(inputs.input_artifact_ids, inputs.input_content_hashes, strict=True)
    )

    assert inputs.primary_source_manifest.source_manifest_id == (
        verified_manifest.manifest.daily_source_manifest_id
    )
    assert lineage[inputs.composite_manifest_id] == inputs.composite_manifest_hash
    assert lineage[verified_manifest.manifest.supplemental_source_manifest_id] == (
        verified_manifest.manifest.supplemental_source_manifest_hash
    )


def test_v2_requires_verified_package_wrapper(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    _, _, verified_manifest = _v2_inputs(tmp_path, daily_decision_fixture)
    with pytest.raises(TypeError, match="VerifiedCompositeOperationalManifest"):
        adapt_verified_composite_operational_inputs(
            composite=verified_manifest.manifest,  # type: ignore[arg-type]
            daily=load_verified_daily_decision_artifact(
                verified_manifest.root.parent.parent
                / "daily"
                / str(verified_manifest.manifest.daily_artifact_id)
            ),
            supplemental=load_verified_supplemental_research_evidence(
                verified_manifest.root.parent.parent
                / "supplemental"
                / str(verified_manifest.manifest.supplemental_bundle_id)
            ),
        )


@pytest.mark.parametrize(
    ("status", "missing", "conflicts"),
    [
        (
            CompositeOperationalCompositionStatus.DATA_INSUFFICIENT,
            ("REQUIRED_EVIDENCE_MISSING",),
            (),
        ),
        (
            CompositeOperationalCompositionStatus.CONFLICTED,
            (),
            ("SOURCE_AUTHORITY_CONFLICT",),
        ),
    ],
)
def test_non_verified_terminal_manifests_cannot_enter_v2_research(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
    status: CompositeOperationalCompositionStatus,
    missing: tuple[str, ...],
    conflicts: tuple[str, ...],
) -> None:
    _, legacy, verified = _v2_inputs(tmp_path, daily_decision_fixture)
    source = verified.manifest
    terminal = CompositeOperationalInputManifest.create(
        status=status,
        decision_time=source.decision_time,
        created_at=source.created_at,
        composition_policy=verified.composition_policy,
        daily_artifact_id=source.daily_artifact_id,
        daily_artifact_hash=source.daily_artifact_hash,
        daily_source_manifest_id=source.daily_source_manifest_id,
        daily_source_manifest_hash=source.daily_source_manifest_hash,
        supplemental_bundle_id=source.supplemental_bundle_id,
        supplemental_bundle_hash=source.supplemental_bundle_hash,
        supplemental_source_manifest_id=source.supplemental_source_manifest_id,
        supplemental_source_manifest_hash=(
            source.supplemental_source_manifest_hash
        ),
        component_references=source.component_references,
        field_authority_references=source.field_authority_references,
        missing_evidence=missing,
        source_conflicts=conflicts,
        reason_codes=(f"COMPOSITE_OPERATIONAL_EVIDENCE_{status.value}",),
        limitations=source.limitations,
    )
    terminal_verified = load_verified_composite_operational_manifest(
        publish_composite_operational_manifest(
            root=tmp_path / "terminal",
            manifest=terminal,
            composition_policy=verified.composition_policy,
        )
    )

    with pytest.raises(ValueError, match="VERIFIED"):
        adapt_verified_composite_operational_inputs(
            composite=terminal_verified,
            daily=load_verified_daily_decision_artifact(
                tmp_path / "daily" / str(terminal.daily_artifact_id)
            ),
            supplemental=load_verified_supplemental_research_evidence(
                tmp_path
                / "supplemental"
                / str(terminal.supplemental_bundle_id)
            ),
        )


def test_v2_operational_adapter_replays_builder_before_accepting_package(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    _, _, verified = _v2_inputs(tmp_path, daily_decision_fixture)
    source = verified.manifest
    forged = CompositeOperationalInputManifest.create(
        status=CompositeOperationalCompositionStatus.VERIFIED,
        decision_time=source.decision_time,
        created_at=source.created_at,
        composition_policy=verified.composition_policy,
        daily_artifact_id=source.daily_artifact_id,
        daily_artifact_hash=source.daily_artifact_hash,
        daily_source_manifest_id=source.daily_source_manifest_id,
        daily_source_manifest_hash=source.daily_source_manifest_hash,
        supplemental_bundle_id=source.supplemental_bundle_id,
        supplemental_bundle_hash=source.supplemental_bundle_hash,
        supplemental_source_manifest_id=source.supplemental_source_manifest_id,
        supplemental_source_manifest_hash=(
            source.supplemental_source_manifest_hash
        ),
        component_references=source.component_references,
        field_authority_references=source.field_authority_references,
        missing_evidence=(),
        source_conflicts=(),
        reason_codes=("FORGED_BUT_SELF_CONSISTENT_REASON",),
        limitations=source.limitations,
    )
    forged_verified = load_verified_composite_operational_manifest(
        publish_composite_operational_manifest(
            root=tmp_path / "forged",
            manifest=forged,
            composition_policy=verified.composition_policy,
        )
    )
    daily = load_verified_daily_decision_artifact(
        tmp_path / "daily" / str(source.daily_artifact_id)
    )
    supplemental = load_verified_supplemental_research_evidence(
        tmp_path / "supplemental" / str(source.supplemental_bundle_id)
    )

    with pytest.raises(ValueError, match="Builder replay mismatch"):
        adapt_verified_composite_operational_inputs(
            composite=forged_verified,
            daily=daily,
            supplemental=supplemental,
        )


def test_platform_artifact_v2_round_trip_binds_composite_lineage(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    inputs, _, verified_manifest = _v2_inputs(
        tmp_path / "inputs", daily_decision_fixture
    )

    verified = PlatformResearchRunner().run(
        inputs=inputs,
        configuration=default_research_pipeline_config(),
        output_root=tmp_path / "research",
        code_revision="h6-test-revision",
    )

    assert verified.artifact.inputs == inputs
    assert verified.artifact.envelope.source_manifest_id == (
        verified_manifest.manifest.daily_source_manifest_id
    )
    assert verified_manifest.manifest.manifest_id in (
        verified.artifact.envelope.input_artifact_ids
    )
    for component in (
        verified.artifact.market_regime,
        verified.artifact.theme_rotation,
        verified.artifact.capital_evolution,
        verified.artifact.candidate_set,
    ):
        assert component.envelope.source_manifest_id == (
            verified_manifest.manifest.daily_source_manifest_id
        )
        assert verified_manifest.manifest.manifest_id in (
            component.envelope.input_artifact_ids
        )
