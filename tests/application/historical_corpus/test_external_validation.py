from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalEvidenceKind,
    HistoricalResearchEvidence,
    ResearchFinding,
    ResearchStatement,
    ResearchStatementKind,
)
from market_regime_alpha.application.historical_corpus.external_validation import (
    ExternalValidationObservation,
    FrozenAlphaHypothesis,
    FrozenExternalValidationExperiment,
    ValidationDimension,
    ValidationScope,
    evaluate_external_validation,
    project_external_validation_observations,
)
from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
    HistoricalSessionComponent,
)
from market_regime_alpha.application.research_validation.common import (
    ResearchEvidenceAuthority,
    ValidationArtifactReference,
)
from market_regime_alpha.application.strategy_shadow.economics import (
    StrategyEconomicsResult,
    StrategyEconomicsStatus,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash


def _ref(kind: str, value: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(value),
        canonical_hash({"kind": kind, "value": value}),
    )


def _hypothesis(top_k: int = 3) -> FrozenAlphaHypothesis:
    return FrozenAlphaHypothesis.create(
        factor_directions=(
            ("intraday_return_to_decision_time", "HIGHER_IS_BETTER"),
            ("price_vs_vwap_return", "HIGHER_IS_BETTER"),
            ("vwap_slope", "HIGHER_IS_BETTER"),
        ),
        candidate_scoring="EQUAL_WEIGHT_RANK_PERCENTILE",
        decision_time_policy="FROZEN_14_55_ASIA_SHANGHAI",
        target_reference=_ref("OUTCOME_TARGET", "target-a"),
        top_k=top_k,
        cost_assumption=Decimal("0.001"),
        minimum_effect_retention=Decimal("0.5"),
        minimum_coverage=Decimal("0.8"),
        feature_reference=_ref("FEATURE_SET_CONFIGURATION", "feature-a"),
        feature_version="intraday-alpha-v1",
        cost_policy_reference=_ref(
            "HISTORICAL_STRATEGY_ECONOMICS_POLICY_SET", "cost-a"
        ),
        economics_policy_reference=_ref(
            "STRATEGY_ECONOMICS_POLICY", "economics-a"
        ),
        execution_entry_kind="FROZEN_DECISION_REFERENCE",
        discovery_evidence_reference=_ref(
            "HISTORICAL_ALPHA_ABLATION_EVIDENCE", "discovery-a"
        ),
        discovery_variant_id="PRICE_RETURN_CHALLENGER",
        discovery_rank_ic=Decimal("1"),
    )


def _scope(period: str, universe: str, provider: str) -> ValidationScope:
    first_session, last_session = (
        (date(2025, 1, 1), date(2025, 12, 31))
        if period == "2025-H1"
        else (date(2026, 1, 1), date(2026, 12, 31))
    )
    return ValidationScope(
        temporal_partition=period,
        first_session=first_session,
        last_session=last_session,
        universe_reference=_ref("UNIVERSE", universe),
        provider_reference=_ref("PROVIDER", provider),
    )


def _correctness(status: str = "CORRECTNESS_SUPPORTED") -> HistoricalResearchEvidence:
    return HistoricalResearchEvidence.create(
        run_id=ArtifactId("correctness-run"),
        command_hash="sha256:" + "c" * 64,
        experiment_reference=_ref(
            "RESEARCH_EXPERIMENT_DEFINITION", "correctness-experiment"
        ),
        evidence_kind=HistoricalEvidenceKind.ALPHA_CORRECTNESS,
        research_question="Is the frozen intraday hypothesis correct?",
        classification=(
            ResearchFinding.POSITIVE
            if status == "CORRECTNESS_SUPPORTED"
            else ResearchFinding.INCONCLUSIVE
        ),
        rationale=status,
        source_references=(_ref("NORMALIZED_DATASET", "physical-a"),),
        metrics=(),
        payload={"status": status},
        created_at=datetime(2026, 8, 21, tzinfo=UTC),
        statements=(
            ResearchStatement(ResearchStatementKind.FACT, "Synthetic owner test."),
        ),
    )


VALIDATION_PANEL = _ref("RESEARCH_PANEL", "frozen-validation-panel")
ECONOMICS_RESULT = _ref("STRATEGY_ECONOMICS_RESULT", "economics-result")
ENTRY_EXECUTION = _ref("HISTORICAL_CANDIDATE", "entry-execution")


def test_external_experiment_freezes_hypothesis_and_one_dimension() -> None:
    experiment = FrozenExternalValidationExperiment.create(
        hypothesis=_hypothesis(),
        correctness_evidence=_correctness(),
        discovery_scope=_scope("2025-H1", "universe-a", "provider-a"),
        validation_scope=_scope("2025-H2", "universe-a", "provider-a"),
        validation_panel_references=(VALIDATION_PANEL,),
        dimension=ValidationDimension.TEMPORAL_VALIDATION,
        expected_population=1,
        random_seed=20260819,
    )

    assert experiment.experiment_hash.startswith("sha256:")
    assert experiment.reference.artifact_kind == "RESEARCH_EXPERIMENT_DEFINITION"
    assert experiment.hypothesis.minimum_effect_retention == Decimal("0.5")


def test_external_experiment_rejects_dimension_confounding() -> None:
    with pytest.raises(ValueError, match="exactly the declared validation dimension"):
        FrozenExternalValidationExperiment.create(
            hypothesis=_hypothesis(),
            correctness_evidence=_correctness(),
            discovery_scope=_scope("2025-H1", "universe-a", "provider-a"),
            validation_scope=_scope("2025-H2", "universe-b", "provider-a"),
            validation_panel_references=(VALIDATION_PANEL,),
            dimension=ValidationDimension.TEMPORAL_VALIDATION,
            expected_population=1,
            random_seed=20260819,
        )


def test_external_experiment_rejects_uncorrected_hypothesis() -> None:
    with pytest.raises(ValueError, match="correctness-supported"):
        FrozenExternalValidationExperiment.create(
            hypothesis=_hypothesis(),
            correctness_evidence=_correctness("PARTIALLY_REPRODUCED"),
            discovery_scope=_scope("2025-H1", "universe-a", "provider-a"),
            validation_scope=_scope("2025-H2", "universe-a", "provider-a"),
            validation_panel_references=(VALIDATION_PANEL,),
            dimension=ValidationDimension.TEMPORAL_VALIDATION,
            expected_population=1,
            random_seed=20260819,
        )


def test_external_evaluation_preserves_pit_oos_ceiling_and_frozen_thresholds() -> None:
    experiment = FrozenExternalValidationExperiment.create(
        hypothesis=_hypothesis(),
        correctness_evidence=_correctness(),
        discovery_scope=_scope("2025-H1", "universe-a", "provider-a"),
        validation_scope=_scope("2025-H2", "universe-a", "provider-a"),
        validation_panel_references=(VALIDATION_PANEL,),
        dimension=ValidationDimension.TEMPORAL_VALIDATION,
        expected_population=40,
        random_seed=20260819,
    )
    observations = tuple(
        ExternalValidationObservation(
            session=date(2026, 1, day),
            symbol=f"S{index}",
            factor_values={
                "intraday_return_to_decision_time": Decimal(index),
                "price_vs_vwap_return": Decimal(index),
                "vwap_slope": Decimal(index),
            },
            decision_reference_price=Decimal("100"),
            executable_entry_price=Decimal("100"),
            target_reference_price=Decimal("100")
            * (Decimal("1") + Decimal(index - 2) / Decimal("100")),
            source_reference=VALIDATION_PANEL,
            validation_scope_reference=experiment.validation_scope.reference,
            economics_result_reference=ECONOMICS_RESULT,
            entry_execution_reference=ENTRY_EXECUTION,
            capacity=Decimal("1000000"),
        )
        for day in range(2, 10)
        for index in range(5)
    )

    result = evaluate_external_validation(
        experiment,
        observations=observations,
        pit_complete=False,
        free_data=True,
    )

    assert result.coverage == Decimal("1")
    assert result.rank_ic == Decimal("1")
    assert result.effect_retention == Decimal("1")
    assert result.external_validation_classification == "EXTERNAL_VALIDATION"
    assert result.formal_oos is False
    assert "PIT_INCOMPLETE" in result.limitations
    assert result.thresholds_reference == experiment.hypothesis.reference
    assert result.cost_diagnostic == Decimal("0.001")


def test_external_top_k_ties_use_fractional_boundary_not_symbol_identity() -> None:
    experiment = FrozenExternalValidationExperiment.create(
        hypothesis=_hypothesis(top_k=1),
        correctness_evidence=_correctness(),
        discovery_scope=_scope("2025-H1", "universe-a", "provider-a"),
        validation_scope=_scope("2025-H2", "universe-a", "provider-a"),
        validation_panel_references=(VALIDATION_PANEL,),
        dimension=ValidationDimension.TEMPORAL_VALIDATION,
        expected_population=2,
        random_seed=20260819,
    )
    observations = tuple(
        ExternalValidationObservation(
            session=date(2026, 2, 2),
            symbol=symbol,
            factor_values={
                "intraday_return_to_decision_time": Decimal("1"),
                "price_vs_vwap_return": Decimal("1"),
                "vwap_slope": Decimal("1"),
            },
            decision_reference_price=Decimal("100"),
            executable_entry_price=Decimal("100"),
            target_reference_price=target,
            source_reference=VALIDATION_PANEL,
            validation_scope_reference=experiment.validation_scope.reference,
            economics_result_reference=ECONOMICS_RESULT,
            entry_execution_reference=ENTRY_EXECUTION,
            capacity=None,
        )
        for symbol, target in (("A", Decimal("110")), ("B", Decimal("90")))
    )

    result = evaluate_external_validation(
        experiment,
        observations=observations,
        pit_complete=False,
        free_data=True,
    )

    assert result.top_k_gross == Decimal("0")
    assert result.top_k_net == Decimal("-0.001")


def test_external_validation_binds_input_set_and_frozen_population() -> None:
    experiment = FrozenExternalValidationExperiment.create(
        hypothesis=_hypothesis(top_k=1),
        correctness_evidence=_correctness(),
        discovery_scope=_scope("2025-H1", "universe-a", "provider-a"),
        validation_scope=_scope("2025-H2", "universe-a", "provider-a"),
        validation_panel_references=(VALIDATION_PANEL,),
        dimension=ValidationDimension.TEMPORAL_VALIDATION,
        expected_population=1,
        random_seed=20260819,
    )
    observation = ExternalValidationObservation(
        session=date(2026, 2, 2),
        symbol="A",
        factor_values={
            "intraday_return_to_decision_time": Decimal("1"),
            "price_vs_vwap_return": Decimal("1"),
            "vwap_slope": Decimal("1"),
        },
        decision_reference_price=Decimal("100"),
        executable_entry_price=Decimal("101"),
        target_reference_price=Decimal("102"),
        source_reference=VALIDATION_PANEL,
        validation_scope_reference=experiment.validation_scope.reference,
        economics_result_reference=ECONOMICS_RESULT,
        entry_execution_reference=ENTRY_EXECUTION,
        capacity=None,
    )

    result = evaluate_external_validation(
        experiment,
        observations=(observation,),
        pit_complete=False,
        free_data=True,
    )
    assert result.evaluation_hash == canonical_hash(result.identity_payload())

    with pytest.raises(ValueError, match="outside the frozen Panel"):
        evaluate_external_validation(
            experiment,
            observations=(
                replace(
                    observation,
                    source_reference=_ref("RESEARCH_PANEL", "panel-bound-b"),
                ),
            ),
            pit_complete=False,
            free_data=True,
        )

    with pytest.raises(ValueError, match="outside frozen sessions"):
        evaluate_external_validation(
            experiment,
            observations=(replace(observation, session=date(2027, 1, 2)),),
            pit_complete=False,
            free_data=True,
        )

    with pytest.raises(ValueError, match="exceed frozen population"):
        evaluate_external_validation(
            experiment,
            observations=(
                observation,
                replace(
                    observation,
                    symbol="B",
                    source_reference=_ref("RESEARCH_PANEL", "panel-bound-b"),
                ),
            ),
            pit_complete=False,
            free_data=True,
        )


def test_external_projection_binds_feature_decision_and_entry_owners() -> None:
    hypothesis = _hypothesis(top_k=1)
    session = date(2026, 2, 2)
    available_at = datetime(2026, 2, 2, 6, 50, tzinfo=UTC)
    target_label_reference = _ref("TARGET_OUTCOME_LABEL", "target-label-a")
    entry_execution_reference = _ref("HISTORICAL_CANDIDATE", "entry-a")
    economics = _economics_result(
        hypothesis=hypothesis,
        target_label_reference=target_label_reference,
        entry_execution_reference=entry_execution_reference,
    )
    outcome = HistoricalSessionComponent.create(
        run_id=ArtifactId("external-run"),
        session_id=ArtifactId("external-outcome-session"),
        trading_date=session,
        component_kind=HistoricalComponentKind.OUTCOME,
        source_max_event_time=datetime(2026, 2, 3, tzinfo=UTC),
        materialized_at=datetime(2026, 2, 4, tzinfo=UTC),
        source_references=(_ref("NORMALIZED_DATASET", "external-normalized"),),
        payload={"strategy_economics": [economics.to_canonical_dict()]},
    )
    economics_reference = ValidationArtifactReference(
        "STRATEGY_ECONOMICS_RESULT",
        economics.result_id,
        economics.result_hash,
    )
    row = {
        "trading_date": session.isoformat(),
        "symbol": "A",
        "research_features": [
            {
                "output_id": factor_id,
                "state": "AVAILABLE",
                "value": "1",
                "configuration_id": str(hypothesis.feature_reference.artifact_id),
                "configuration_hash": hypothesis.feature_reference.content_hash,
                "available_at": available_at.isoformat(),
                "source_event_end": available_at.isoformat(),
            }
            for factor_id, _direction in hypothesis.factor_directions
        ],
        "target_reference": hypothesis.target_reference.to_canonical_dict(),
        "target_label_reference": target_label_reference.to_canonical_dict(),
        "economics_policy_reference": (
            hypothesis.economics_policy_reference.to_canonical_dict()
        ),
        "economics_result_reference": economics_reference.to_canonical_dict(),
        "entry_execution_reference": entry_execution_reference.to_canonical_dict(),
        "decision_reference_price": "100",
        "executable_entry_price": "100",
        "target_reference_price": "102",
        "capacity_ceiling": "1000000",
    }
    panel = HistoricalSessionComponent.create(
        run_id=ArtifactId("external-run"),
        session_id=ArtifactId("external-session"),
        trading_date=session,
        component_kind=HistoricalComponentKind.RESEARCH_PANEL,
        source_max_event_time=datetime(2026, 2, 3, tzinfo=UTC),
        materialized_at=datetime(2026, 2, 4, tzinfo=UTC),
        source_references=(outcome.reference,),
        payload={"rows": [row], "row_count": 1},
    )
    experiment = FrozenExternalValidationExperiment.create(
        hypothesis=hypothesis,
        correctness_evidence=_correctness(),
        discovery_scope=_scope("2025-H1", "universe-a", "provider-a"),
        validation_scope=_scope("2025-H2", "universe-a", "provider-a"),
        validation_panel_references=(panel.reference,),
        dimension=ValidationDimension.TEMPORAL_VALIDATION,
        expected_population=1,
        random_seed=20260819,
    )

    projected = project_external_validation_observations(
        experiment,
        (panel,),
        (outcome,),
    )
    assert len(projected) == 1
    assert projected[0].economics_result_reference == economics_reference

    drifted_row = dict(row)
    drifted_row["research_features"] = [
        dict(item, configuration_hash=canonical_hash({"drifted": True}))
        for item in row["research_features"]
    ]
    drifted_panel = HistoricalSessionComponent.create(
        run_id=ArtifactId("external-run"),
        session_id=ArtifactId("external-session-drifted"),
        trading_date=session,
        component_kind=HistoricalComponentKind.RESEARCH_PANEL,
        source_max_event_time=datetime(2026, 2, 3, tzinfo=UTC),
        materialized_at=datetime(2026, 2, 4, tzinfo=UTC),
        source_references=(outcome.reference,),
        payload={"rows": [drifted_row], "row_count": 1},
    )
    drifted_experiment = FrozenExternalValidationExperiment.create(
        hypothesis=hypothesis,
        correctness_evidence=_correctness(),
        discovery_scope=_scope("2025-H1", "universe-a", "provider-a"),
        validation_scope=_scope("2025-H2", "universe-a", "provider-a"),
        validation_panel_references=(drifted_panel.reference,),
        dimension=ValidationDimension.TEMPORAL_VALIDATION,
        expected_population=1,
        random_seed=20260819,
    )
    with pytest.raises(ValueError, match="Feature configuration drifted"):
        project_external_validation_observations(
            drifted_experiment,
            (drifted_panel,),
            (outcome,),
        )


def _economics_result(
    *,
    hypothesis: FrozenAlphaHypothesis,
    target_label_reference: ValidationArtifactReference,
    entry_execution_reference: ValidationArtifactReference,
) -> StrategyEconomicsResult:
    policy_reference = hypothesis.economics_policy_reference
    liquidity_reference = _ref("LIQUIDITY_CAPACITY_ASSESSMENT", "liquidity-a")
    exit_reference = _ref("NORMALIZED_DATASET", "exit-a")
    identity = {
        "schema_version": "strategy-economics-result/v1",
        "policy_reference": policy_reference.to_canonical_dict(),
        "target_label_reference": target_label_reference.to_canonical_dict(),
        "liquidity_reference": liquidity_reference.to_canonical_dict(),
        "entry_execution_reference": entry_execution_reference.to_canonical_dict(),
        "exit_execution_reference": exit_reference.to_canonical_dict(),
        "symbol": "A",
        "status": "AVAILABLE",
        "requested_notional": "100000",
        "capacity_ceiling": "1000000",
        "filled_quantity": "1000",
        "entry_price": "100",
        "exit_price": "102",
        "gross_return": "0.02",
        "cost_return": "0.001",
        "net_return": "0.019",
        "turnover": "2",
        "mfe": "0.03",
        "mae": "-0.01",
        "reason_codes": ["ECONOMICS_AVAILABLE"],
        "evaluated_at": "2026-02-04T00:00:00Z",
        "authority": ResearchEvidenceAuthority.EXPLORATORY.value,
        "limitations": ["NOT_REAL_FILL"],
    }
    digest = canonical_hash(identity)
    return StrategyEconomicsResult(
        result_id=ArtifactId(f"strategy-economics-result:{digest[7:]}"),
        result_hash=digest,
        policy_reference=policy_reference,
        target_label_reference=target_label_reference,
        liquidity_reference=liquidity_reference,
        entry_execution_reference=entry_execution_reference,
        exit_execution_reference=exit_reference,
        symbol="A",
        status=StrategyEconomicsStatus.AVAILABLE,
        requested_notional=Decimal("100000"),
        capacity_ceiling=Decimal("1000000"),
        filled_quantity=Decimal("1000"),
        entry_price=Decimal("100"),
        exit_price=Decimal("102"),
        gross_return=Decimal("0.02"),
        cost_return=Decimal("0.001"),
        net_return=Decimal("0.019"),
        turnover=Decimal("2"),
        mfe=Decimal("0.03"),
        mae=Decimal("-0.01"),
        reason_codes=("ECONOMICS_AVAILABLE",),
        evaluated_at=datetime(2026, 2, 4, tzinfo=UTC),
        authority=ResearchEvidenceAuthority.EXPLORATORY,
        limitations=("NOT_REAL_FILL",),
    )
