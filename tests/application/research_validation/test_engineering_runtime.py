from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from market_regime_alpha.application.research_evaluation.targets import engineering_multi_horizon_protocol
from market_regime_alpha.application.research_validation.ablation import (
    AblationProtocol,
    AblationObservation,
    AblationVariant,
    AblationVariantKind,
    run_factor_ablation,
)
from market_regime_alpha.application.research_validation.admission import (
    AdmissionFloor,
    AdmissionFloorStatus,
    ProductionAdmissionStatus,
    current_engineering_blocked_admission,
)
from market_regime_alpha.application.research_validation.calibration import (
    CalibrationMethod,
    CalibrationObservation,
    CalibrationPartition,
    CalibrationProtocol,
    fit_calibration,
)
from market_regime_alpha.application.research_validation.common import ResearchEvidenceAuthority, ValidationArtifactReference
from market_regime_alpha.application.research_validation.entry_qualification import (
    EntryResearchDecision,
    EntryResearchModel,
    EntryResearchVariant,
    assess_entry,
)
from market_regime_alpha.application.research_validation.factor_extraction import (
    CanonicalStateFactorSource,
    FactorFamily,
    extract_canonical_factors,
)
from market_regime_alpha.application.research_validation.formal_evaluation import (
    EvaluationObservation,
    EvaluationPartition,
    EvaluationWindow,
    FormalEvaluationProtocol,
    MultipleTestingMethod,
    run_formal_evaluation,
)
from market_regime_alpha.application.research_validation.liquidity_capacity import (
    CapacityParameter,
    CapacityValueProvenance,
    LiquidityCapacityAssessment,
    LiquidityCapacityProtocol,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.pit_authority import FormalPITEvidenceArtifact, PITSelectedFactAuthority
from market_regime_alpha.data.pit_contracts import PITArtifactKind, PITArtifactReference, PITValidationOutcome
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.features.materialization_v2 import VerifiedFeatureBundleV2
from market_regime_alpha.market_data import VerifiedMarketDataDataset
from tests.data.test_pit_authority import HASH_A, HASH_B, lineage


NOW = datetime(2026, 8, 10, 8, tzinfo=UTC)


def _ref(kind: str, name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(kind, ArtifactId(name), canonical_hash({"name": name}))


def test_factor_extraction_covers_every_family_without_recomputing() -> None:
    dataset_hash = canonical_hash({"dataset": 1})
    dataset = VerifiedMarketDataDataset(
        root=Path("."),
        artifact=SimpleNamespace(dataset_id=ArtifactId("dataset"), content_hash=dataset_hash),
        bars=(),
        checksums_hash=canonical_hash({"checksums": 1}),
    )
    bundle = VerifiedFeatureBundleV2(
        root=Path("."),
        artifact=SimpleNamespace(
            bundle_id=ArtifactId("bundle"),
            content_hash=canonical_hash({"bundle": 1}),
            dataset_id=ArtifactId("dataset"),
            dataset_hash=dataset_hash,
            decision_time=NOW,
        ),
        artifacts=(),
        checksums_hash=canonical_hash({"checksums": 2}),
    )
    state = CanonicalStateFactorSource(
        family=FactorFamily.MARKET_REGIME,
        reference=_ref("MARKET_STATE", "market-state"),
        values={"state": "RISK_ON", "score": Decimal("0.6")},
        available_at=NOW,
    )
    enrichment = extract_canonical_factors(
        panel_reference=_ref("RESEARCH_PANEL_V2", "panel"),
        symbols=("000001.SZ",),
        dataset=dataset,
        feature_bundle=bundle,
        dynamic_pool=None,
        candidate_set=None,
        signal_run=None,
        forecasts=(),
        state_sources=(state,),
        decision_time=NOW,
        extracted_at=NOW,
    )

    assert {item.family for item in enrichment.exposures} == set(FactorFamily)
    assert any(item.factor_id == "state.market_regime.score" and item.raw_numeric == Decimal("0.6") for item in enrichment.exposures)
    assert all(item.normalized_exposure is None and item.model_contribution is None for item in enrichment.exposures)
    assert any("CANONICAL_FACTOR_FAMILY_NOT_AVAILABLE" in item.missingness for item in enrichment.exposures)


def test_ablation_is_exploratory_and_reports_incremental_lift() -> None:
    observations = tuple(
        AblationObservation(
            observation_id=f"o-{index}",
            session_key=f"s-{index // 2}",
            symbol=f"00000{index}.SZ",
            score=Decimal(str(index)),
            realized_return=Decimal(str(index - 2)) / Decimal("100"),
            mfe=Decimal("0.02"),
            mae=Decimal("-0.01"),
            selected=index % 2 == 0,
            previous_selected=index % 3 == 0,
            factor_values=((FactorFamily.PRICE, "price", Decimal(str(index))),),
        )
        for index in range(1, 7)
    )
    variant = AblationVariant.standard(AblationVariantKind.PRICE_ONLY)
    protocol = AblationProtocol.create(
        protocol_version="v1",
        variants=(variant,),
        top_k=1,
        scoring_contract="TEST_PRICE_SCORE_V1",
        created_at=NOW,
    )
    result = run_factor_ablation(
        protocol=protocol,
        panel_reference=_ref("RESEARCH_PANEL_V2", "panel"),
        observations=observations,
        variant=variant,
        score_function=lambda item, _variant: dict((factor_id, value) for _family, factor_id, value in item.factor_values)["price"],
        baseline_metrics=None,
        baseline_result=None,
        created_at=NOW,
    )

    assert result.authority is ResearchEvidenceAuthority.EXPLORATORY
    assert result.metrics.ic is not None
    assert "NOT_GOVERNANCE_QUALIFICATION" in result.limitations


def test_calibration_keeps_qualification_false_and_partitions_disjoint() -> None:
    protocol = CalibrationProtocol.create(
        protocol_version="v1",
        method=CalibrationMethod.PLATT_LOGISTIC,
        minimum_fit_samples=4,
        maximum_iterations=20,
    )
    observations = tuple(
        CalibrationObservation(f"fit-{index}", Decimal(index) / Decimal("10"), index % 2, CalibrationPartition.FIT) for index in range(4)
    ) + tuple(
        CalibrationObservation(f"validation-{index}", Decimal(index) / Decimal("10"), index % 2, CalibrationPartition.VALIDATION)
        for index in range(2)
    )
    artifact = fit_calibration(protocol=protocol, observations=observations, created_at=NOW)

    assert artifact.calibrated is False
    assert {item.partition for item in artifact.evaluations} == {CalibrationPartition.VALIDATION}
    assert artifact.evaluations[0].coverage == Decimal("1")


def test_liquidity_capacity_freezes_assumptions_without_claiming_calibration() -> None:
    protocol = LiquidityCapacityProtocol.create(
        protocol_version="v1",
        parameters=(
            CapacityParameter(
                "participation_rate",
                Decimal("0.10"),
                CapacityValueProvenance.ENGINEERING_ASSUMPTION,
            ),
            CapacityParameter(
                "impact_coefficient_bps",
                Decimal("8"),
                CapacityValueProvenance.ENGINEERING_ASSUMPTION,
            ),
            CapacityParameter(
                "slippage_bps",
                Decimal("5"),
                CapacityValueProvenance.ENGINEERING_ASSUMPTION,
            ),
        ),
        created_at=NOW,
    )
    assessment = LiquidityCapacityAssessment.create(
        symbol="000001.SZ",
        as_of_date=NOW.date(),
        market_data_reference=_ref("MARKET_DATA_DATASET", "liquidity-dataset"),
        bars=(),
        requested_position=Decimal("100000"),
        requested_order=Decimal("10000"),
        protocol=protocol,
        created_at=NOW,
    )

    assert protocol.adv_short_sessions == 5
    assert protocol.adv_long_sessions == 20
    assert assessment.fillability == Decimal("0")
    assert assessment.calibrated_fields == ()
    assert "IMPACT_PARAMETER_UNCALIBRATED" in assessment.reason_codes
    assert "SLIPPAGE_PARAMETER_UNCALIBRATED" in assessment.reason_codes


def test_formal_evaluation_runs_but_cannot_emit_oos_without_formal_pit() -> None:
    target_protocol = engineering_multi_horizon_protocol()
    windows = (
        EvaluationWindow("train", EvaluationPartition.TRAIN, date(2026, 1, 1), date(2026, 3, 31), 1),
        EvaluationWindow("validation", EvaluationPartition.VALIDATION, date(2026, 4, 3), date(2026, 4, 30), 1),
        EvaluationWindow("oos", EvaluationPartition.LOCKED_OOS, date(2026, 5, 3), date(2026, 5, 31), 1),
    )
    protocol = FormalEvaluationProtocol.create(
        protocol_version="v1",
        target_protocol=target_protocol,
        windows=windows,
        bootstrap_iterations=20,
        confidence_level=Decimal("0.90"),
        multiple_testing_method=MultipleTestingMethod.BONFERRONI,
        locked_at=NOW,
    )
    observations = tuple(
        EvaluationObservation(
            observation_id=f"eval-{index}",
            session_date=date(2026, 4, 3) + timedelta(days=index),
            label_end_date=date(2026, 4, 4) + timedelta(days=index),
            symbol=f"00000{index}.SZ",
            score=Decimal(index),
            realized_return=Decimal(index - 2) / Decimal("100"),
            mfe=Decimal("0.02"),
            mae=Decimal("-0.01"),
            regime="RISK_ON",
            liquidity_slice="HIGH",
            market_cap_slice="LARGE",
            theme_slice="T1",
        )
        for index in range(1, 6)
    )
    result = run_formal_evaluation(
        protocol=protocol,
        panel_reference=_ref("RESEARCH_PANEL_V2", "panel"),
        observations=observations,
        formal_pit_evidence=None,
        created_at=NOW,
    )

    assert protocol.embargo_sessions == target_protocol.session_offset
    assert result.formal_oos is False
    assert result.authority is ResearchEvidenceAuthority.ENGINEERING_ONLY
    assert "REAL_FORMAL_PIT_REQUIRED" in result.reason_codes
    assert "FORMAL_OOS_OWNER_QUALIFICATION_REQUIRED" in result.reason_codes
    assert {item.partition for item in result.metrics} == {EvaluationPartition.VALIDATION}
    assert {item.sensitivity_return_multiplier for item in result.metrics} == {
        Decimal("0.9"),
        Decimal("1"),
        Decimal("1.1"),
    }

    dataset_hash = canonical_hash({"formal-dataset": 1})
    fixture_authority = PITSelectedFactAuthority(
        fact_id=ArtifactId("fixture-fact"),
        fact_hash=HASH_A,
        source_qualification_id=ArtifactId("fixture-qualification"),
        source_qualification_hash=HASH_A,
        artifact_resolution_id=ArtifactId("fixture-artifact-resolution"),
        artifact_resolution_hash=HASH_A,
        source_manifest_resolution_id=ArtifactId("fixture-manifest-resolution"),
        source_manifest_resolution_hash=HASH_B,
        temporal_resolution_references=(),
        system_time_authority="ENGINEERING_FIXTURE_CLOCK",
    )
    fixture_pit = FormalPITEvidenceArtifact.create(
        request_hash=HASH_A,
        snapshot_id=ArtifactId("fixture-snapshot"),
        snapshot_hash=HASH_B,
        authority_revision=1,
        lineage=replace(
            lineage(),
            dataset=PITArtifactReference(PITArtifactKind.MARKET_DATA_DATASET.value, ArtifactId("formal-dataset"), dataset_hash),
            validation_protocol=PITArtifactReference(
                PITArtifactKind.VALIDATION_PROTOCOL.value,
                protocol.protocol_id,
                protocol.protocol_hash,
            ),
        ),
        outcome=PITValidationOutcome.SATISFIED,
        rejection_codes=(),
        selected_fact_references=((fixture_authority.fact_id, fixture_authority.fact_hash),),
        selected_fact_authorities=(fixture_authority,),
        lineage_resolution_references=((ArtifactId("fixture-lineage-resolution"), HASH_A),),
        available_at=NOW,
        recorded_at=NOW,
        actor="fixture",
        reason="prove fixture gate",
    )
    fixture_result = run_formal_evaluation(
        protocol=protocol,
        panel_reference=_ref("RESEARCH_PANEL_V2", "panel-fixture"),
        observations=(
            EvaluationObservation(
                observation_id="fixture-oos",
                session_date=date(2026, 5, 10),
                label_end_date=date(2026, 5, 12),
                symbol="000001.SZ",
                score=Decimal("1"),
                realized_return=Decimal("0.01"),
                mfe=Decimal("0.02"),
                mae=Decimal("-0.01"),
                regime="RISK_ON",
                liquidity_slice="HIGH",
                market_cap_slice="LARGE",
                theme_slice="T1",
            ),
        ),
        formal_pit_evidence=fixture_pit,
        panel_source_references=(ValidationArtifactReference("MARKET_DATA_DATASET", ArtifactId("formal-dataset"), dataset_hash),),
        created_at=NOW,
    )
    assert fixture_result.formal_oos is False
    assert "REAL_FORMAL_PIT_POSTGRESQL_CLOCK_REQUIRED" in fixture_result.reason_codes


def test_entry_and_production_admission_remain_blocked() -> None:
    model = EntryResearchModel.create(
        model_version="v1",
        variant=EntryResearchVariant.CANDIDATE_SIGNAL,
        score_threshold=Decimal("0.6"),
    )
    assessment = assess_entry(
        model=model,
        symbol="000001.SZ",
        decision_time=NOW,
        inputs=(("candidate_score", Decimal("0.8")), ("signal_score", Decimal("0.7"))),
        source_references=(_ref("CANDIDATE", "candidate"), _ref("SIGNAL", "signal")),
    )
    admission = current_engineering_blocked_admission(governance_version="v1", evidence={}, evaluated_at=NOW)

    assert assessment.decision is EntryResearchDecision.SHADOW_ENTER
    assert admission.status is ProductionAdmissionStatus.BLOCKED
    assert admission.production_authorized is False
    assert set(admission.blocked_floors) == set(AdmissionFloor)
    assert {item.value for item in AdmissionFloorStatus} == {
        "BLOCKED",
        "MISSING",
        "REJECTED",
        "SATISFIED",
    }
