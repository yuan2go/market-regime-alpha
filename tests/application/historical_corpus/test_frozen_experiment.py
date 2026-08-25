from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime, time

import pytest

from market_regime_alpha.application.historical_corpus.frozen_experiment import (
    WP_ALPHA_PROOF_02_LOCKED_AT,
    WP_ALPHA_RESEARCH_01_MULTIPLE_TESTING_FAMILY,
    create_golden_loop_v2_historical_experiment,
    create_phase_e3_feature_configuration,
    create_phase_e3_historical_experiment,
    create_phase_e3_strategy_economics_policy_set,
    create_wp_alpha_research_01_historical_experiment,
    create_wp_alpha_proof_02_historical_experiment,
    verify_golden_loop_v2_historical_experiment,
    verify_phase_e3_historical_experiment,
    verify_wp_alpha_research_01_historical_experiment,
)
from market_regime_alpha.application.historical_corpus.golden_loop import (
    GoldenLoopScoringContract,
)
from market_regime_alpha.application.historical_corpus.alpha_discovery import (
    alpha_discovery_evaluation_contract_reference,
)
from market_regime_alpha.application.research_evaluation.targets import (
    exploratory_five_minute_multi_horizon_protocol,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    ResearchExperimentDefinition,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.historical_economics import (
    HistoricalStrategyEconomicsPolicySet,
)
from market_regime_alpha.core.identity import ArtifactId


LOCKED_AT = datetime(2026, 8, 13, 8, 0, tzinfo=UTC)


def test_phase_e3_experiment_accepts_only_exact_frozen_methodology() -> None:
    target = exploratory_five_minute_multi_horizon_protocol()
    experiment = create_phase_e3_historical_experiment(target, locked_at=LOCKED_AT)
    feature = create_phase_e3_feature_configuration()
    economics = create_phase_e3_strategy_economics_policy_set(
        target_protocol=target,
        created_at=LOCKED_AT,
    )
    configuration = (
        experiment.feature_reference,
        experiment.cost_policy_reference,
    )

    assert HistoricalStrategyEconomicsPolicySet.from_canonical_dict(
        economics.to_canonical_dict()
    ) == economics

    verify_phase_e3_historical_experiment(
        experiment,
        target_protocol=target,
        feature_owner=feature,
        economics_owner=economics,
        decision_local_time=time(14, 55),
        timezone_name="Asia/Shanghai",
        configuration_references=configuration,
    )

    values = {
        item.name: getattr(experiment, item.name)
        for item in fields(experiment)
        if item.name not in {"definition_id", "definition_hash"}
    }
    values["feature_version"] = "after-the-fact-tuning"
    changed = ResearchExperimentDefinition.create(**values)
    with pytest.raises(ValueError, match="frozen Phase E3 methodology"):
        verify_phase_e3_historical_experiment(
            changed,
            target_protocol=target,
            feature_owner=feature,
            economics_owner=economics,
            decision_local_time=time(14, 55),
            timezone_name="Asia/Shanghai",
            configuration_references=(
                changed.feature_reference,
                changed.cost_policy_reference,
            ),
        )


def test_phase_e3_experiment_requires_command_level_feature_and_cost_bindings() -> None:
    target = exploratory_five_minute_multi_horizon_protocol()
    experiment = create_phase_e3_historical_experiment(target, locked_at=LOCKED_AT)

    with pytest.raises(ValueError, match="omits frozen feature or cost"):
        verify_phase_e3_historical_experiment(
            experiment,
            target_protocol=target,
            feature_owner=create_phase_e3_feature_configuration(),
            economics_owner=create_phase_e3_strategy_economics_policy_set(
                target_protocol=target,
                created_at=LOCKED_AT,
            ),
            decision_local_time=time(14, 55),
            timezone_name="Asia/Shanghai",
            configuration_references=(experiment.feature_reference,),
        )


def test_golden_loop_v2_changes_only_research_correctness_identity() -> None:
    target = exploratory_five_minute_multi_horizon_protocol()
    v1 = create_phase_e3_historical_experiment(target, locked_at=LOCKED_AT)
    v2 = create_golden_loop_v2_historical_experiment(target, locked_at=LOCKED_AT)

    assert v2.definition_hash != v1.definition_hash
    assert v2.target_references == v1.target_references
    assert v2.feature_reference == v1.feature_reference
    assert v2.feature_version == v1.feature_version
    assert v2.cost_policy_reference == v1.cost_policy_reference
    assert v2.decision_time_policy == v1.decision_time_policy
    assert v2.allowed_model_families == v1.allowed_model_families
    assert v2.search_budget == v1.search_budget
    assert v2.train_validation_policy == v1.train_validation_policy
    assert v2.purge_embargo_policy == v1.purge_embargo_policy
    assert v2.oos_unlock_policy == v1.oos_unlock_policy
    assert v2.random_seeds == v1.random_seeds
    assert GoldenLoopScoringContract.create_v2().contract_hash in {
        value
        for domain in v2.hyperparameter_space
        if domain.parameter_name == "scoring_contract_hash"
        for value in domain.allowed_values
    }

    verify_golden_loop_v2_historical_experiment(
        v2,
        target_protocol=target,
        feature_owner=create_phase_e3_feature_configuration(),
        economics_owner=create_phase_e3_strategy_economics_policy_set(
            target_protocol=target,
            created_at=LOCKED_AT,
        ),
        decision_local_time=time(14, 55),
        timezone_name="Asia/Shanghai",
        configuration_references=(
            v2.feature_reference,
            v2.cost_policy_reference,
            GoldenLoopScoringContract.create_v2().reference,
        ),
    )


def test_wp_alpha_research_01_freezes_complete_discovery_design() -> None:
    target = exploratory_five_minute_multi_horizon_protocol()
    golden = create_golden_loop_v2_historical_experiment(
        target,
        locked_at=LOCKED_AT,
    )
    discovery = create_wp_alpha_research_01_historical_experiment(
        target,
        locked_at=LOCKED_AT,
    )
    domains = {
        item.parameter_name: item.allowed_values
        for item in discovery.hyperparameter_space
    }

    assert discovery.definition_hash != golden.definition_hash
    assert discovery.feature_reference == golden.feature_reference
    assert discovery.cost_policy_reference == golden.cost_policy_reference
    assert discovery.target_references == golden.target_references
    assert discovery.multiple_testing_family_id == (
        WP_ALPHA_RESEARCH_01_MULTIPLE_TESTING_FAMILY
    )
    assert domains["dataset_owner"] == (
        "NORMALIZED_DATASET|historical-data-owner-c4cc4f5fd5a39248c116b3e7|"
        "sha256:c4cc4f5fd5a39248c116b3e72d83dac09cb7ee6466f8ef84f803e64b4c38ea77",
    )
    assert domains["session_range"] == ("2025-01-02|2025-07-11|126",)
    assert domains["universe"] == ("CSI_300_EFFECTIVE_DATED|300_PER_SESSION",)
    assert domains["gate_variants"] == (
        "CURRENT_HARD_GATE",
        "NO_PREDICTIVE_GATE",
        "SOFT_FEATURE",
    )
    assert domains["candidate_policies"] == (
        "CURRENT_HARD_CHAIN",
        "HARD_INTEGRITY_PRICE_RETURN",
        "HARD_INTEGRITY_PRICE_VOLUME_TREND",
        "NO_PREDICTIVE_GATES",
        "SOFT_CONTEXT_CANDIDATE",
    )
    assert domains["gate_incremental_effect_contract"] == (
        "MATCHED_SESSION_ONLY_REQUIRE_WITHIN_SESSION_ACCEPTED_AND_REJECTED",
    )
    assert domains["evaluation_top_k"] == ("1", "10", "3", "5")
    assert domains["multiple_testing_method"] == ("BENJAMINI_HOCHBERG_FDR",)
    assert domains["discovery_evidence_ceiling"] == (
        "EXPLORATORY|PIT_INCOMPLETE|IN_SAMPLE_DISCOVERY|UNQUALIFIED|"
        "FORMAL_OOS_FALSE|CALIBRATED_FALSE|PRODUCTION_QUALIFIED_FALSE",
    )

    verify_wp_alpha_research_01_historical_experiment(
        discovery,
        target_protocol=target,
        feature_owner=create_phase_e3_feature_configuration(),
        economics_owner=create_phase_e3_strategy_economics_policy_set(
            target_protocol=target,
            created_at=LOCKED_AT,
        ),
        decision_local_time=time(14, 55),
        timezone_name="Asia/Shanghai",
        configuration_references=(
            discovery.feature_reference,
            discovery.cost_policy_reference,
            GoldenLoopScoringContract.create_v2().reference,
            alpha_discovery_evaluation_contract_reference(
                create_phase_e3_feature_configuration()
            ),
            ValidationArtifactReference(
                "HISTORICAL_RESEARCH_SOURCE_RUN",
                ArtifactId("historical-research-run-12e8dd606b480380dc0df356"),
                "sha256:12e8dd606b480380dc0df356ca5aa6c2fdc7b2abd6b215feca74195a50227029",
            ),
        ),
    )


def test_wp_alpha_proof_02_binds_reacquired_owners_without_changing_protocol() -> None:
    target = exploratory_five_minute_multi_horizon_protocol()
    references = {
        "raw_owner_reference": _reference("RAW_PROVIDER_ARCHIVE", "raw-v2"),
        "normalized_owner_reference": _reference(
            "NORMALIZED_DATASET", "normalized-v2"
        ),
        "calendar_reference": _reference("TRADING_CALENDAR", "calendar-v2"),
        "universe_timeline_reference": _reference(
            "HISTORICAL_CONSTITUENT_TIMELINE", "timeline-v2"
        ),
        "security_facts_reference": _reference(
            "HISTORICAL_SECURITY_FACTS", "facts-v2"
        ),
    }

    experiment = create_wp_alpha_proof_02_historical_experiment(
        target,
        locked_at=WP_ALPHA_PROOF_02_LOCKED_AT,
        **references,
    )
    domains = {
        item.parameter_name: item.allowed_values
        for item in experiment.hyperparameter_space
    }

    assert domains["factor_directions"] == (
        "intraday_return_to_decision_time|HIGHER_IS_BETTER",
        "price_vs_vwap_return|HIGHER_IS_BETTER",
        "vwap_slope|HIGHER_IS_BETTER",
    )
    assert domains["candidate_selection_top_k"] == (
        "5_WITH_BOUNDARY_TIES",
    )
    assert domains["round_trip_cost"] == ("0.002100",)
    assert domains["inference_iterations"] == ("2000",)
    assert domains["inference_block_lengths"] == ("1|5|10",)
    assert domains["random_seed"] == ("20260813",)
    assert domains["discovery_sessions"] == (
        "2025-01-02|2025-07-11|126|FINAL_TARGET_2025-07-14",
    )
    assert domains["external_sessions"] == (
        "2025-07-15|2026-01-16|126|FINAL_TARGET_2026-01-19",
    )
    assert domains["parent_discovery_experiment"] == (
        "RESEARCH_EXPERIMENT_DEFINITION|"
        "research-experiment-definition:"
        "ab6820cb12247973feab2103684b47b9785d8969b5d4362a595888752f99c02e|"
        "sha256:ab6820cb12247973feab2103684b47b9785d8969b5d4362a595888752f99c02e",
    )
    assert domains["formal_pit_locked_oos_gate"] == (
        "FORMAL_PIT_SUPPORTED_AND_PHYSICAL_CORRECTNESS_SUPPORTED",
    )
    assert domains["raw_owner"] == (
        _render_reference(references["raw_owner_reference"]),
    )
    assert domains["normalized_owner"] == (
        _render_reference(references["normalized_owner_reference"]),
    )
    assert experiment.stopping_rule == (
        "EXHAUST_FROZEN_EXTERNAL_SCOPE_ONCE_NO_RESULT_DEPENDENT_CHANGE"
    )
    with pytest.raises(ValueError, match="lock time is frozen"):
        create_wp_alpha_proof_02_historical_experiment(
            target,
            locked_at=LOCKED_AT,
            **references,
        )


def _reference(kind: str, name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(f"{name}-owner"),
        "sha256:" + name.encode().hex().ljust(64, "0")[:64],
    )


def _render_reference(reference: ValidationArtifactReference) -> str:
    return (
        f"{reference.artifact_kind}|{reference.artifact_id}|"
        f"{reference.content_hash}"
    )
