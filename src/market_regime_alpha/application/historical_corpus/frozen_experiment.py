"""Typed owners for the frozen Phase E3 longitudinal methodology.

Changing a feature, threshold, Target, cost, capacity, or evaluation choice
produces a different content-addressed owner and Experiment Definition.  The
module intentionally freezes only the currently consumed Historical policy;
it is not a second feature or Strategy implementation.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from decimal import Decimal

from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeCheckpoint,
    OutcomeTargetProtocol,
    TargetDefinition,
)
from market_regime_alpha.application.historical_corpus.alpha_discovery import (
    ALPHA_DISCOVERY_GATE_IDS,
    ALPHA_DISCOVERY_TOP_K,
    alpha_discovery_evaluation_contract_reference,
    canonical_alpha_factor_registry,
)
from market_regime_alpha.application.historical_corpus.golden_loop import (
    GoldenLoopScoringContract,
)
from market_regime_alpha.application.research_validation.common import (
    ENGINEERING_LIMITATIONS,
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    HyperparameterDomain,
    ResearchExperimentDefinition,
    SearchBudget,
)
from market_regime_alpha.application.research_validation.historical_economics import (
    HistoricalStrategyEconomicsPolicySet,
)
from market_regime_alpha.application.research_validation.liquidity_capacity import (
    CapacityParameter,
    CapacityValueProvenance,
    LiquidityCapacityProtocol,
)
from market_regime_alpha.application.strategy_shadow.economics import (
    StrategyEconomicsPolicy,
    StrategyEntryKind,
    StrategyExitKind,
)
from market_regime_alpha.application.strategy_shadow.portfolio import (
    ShadowParameterProvenance,
)
from market_regime_alpha.features.technical.catalog import canonical_technical_feature_set
from market_regime_alpha.features.spine import FeatureSetConfiguration
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.universe.runtime_scope import (
    ResearchUniversePolicy,
    UniversePolicySelector,
    UniverseScopeKind,
    build_research_universe_policy,
)


PHASE_E3_DECISION_LOCAL_TIME = time(14, 55)
PHASE_E3_TIMEZONE = "Asia/Shanghai"
_FEATURE_EFFECTIVE_FROM = datetime(1990, 1, 1, tzinfo=UTC)
WP_ALPHA_RESEARCH_01_MULTIPLE_TESTING_FAMILY = (
    "WP_ALPHA_RESEARCH_01_DISCOVERY_V1"
)
WP_ALPHA_PROOF_02_MULTIPLE_TESTING_FAMILY = "WP_ALPHA_PROOF_02_FROZEN_V1"
WP_ALPHA_PROOF_02_LOCKED_AT = datetime(2026, 8, 25, 1, 5, 33, tzinfo=UTC)
_WP_ALPHA_PROOF_02_DISCOVERY_EXPERIMENT = ValidationArtifactReference(
    "RESEARCH_EXPERIMENT_DEFINITION",
    ArtifactId(
        "research-experiment-definition:"
        "ab6820cb12247973feab2103684b47b9785d8969b5d4362a595888752f99c02e"
    ),
    "sha256:ab6820cb12247973feab2103684b47b9785d8969b5d4362a595888752f99c02e",
)

_WP_ALPHA_DATASET_OWNER = (
    "NORMALIZED_DATASET|historical-data-owner-c4cc4f5fd5a39248c116b3e7|"
    "sha256:c4cc4f5fd5a39248c116b3e72d83dac09cb7ee6466f8ef84f803e64b4c38ea77"
)
_WP_ALPHA_CONSTITUENT_TIMELINE = (
    "HISTORICAL_CONSTITUENT_TIMELINE|"
    "historical-constituent-timeline:af987d1d42d9137abaab010ca6047b8a09ea27cb6d2936480566ec2fc8bb9b58|"
    "sha256:af987d1d42d9137abaab010ca6047b8a09ea27cb6d2936480566ec2fc8bb9b58"
)
_WP_ALPHA_SECURITY_FACTS = (
    "HISTORICAL_SECURITY_FACTS|"
    "historical-security-facts:4fc1085c2579c2fae6028636d8c506b30f1f39884440a3ebf0dad57546aa28df|"
    "sha256:4fc1085c2579c2fae6028636d8c506b30f1f39884440a3ebf0dad57546aa28df"
)
_WP_ALPHA_CONTEXT_OWNER = (
    "HISTORICAL_CONTEXT_INSTRUMENT_SET|"
    "historical-context-instrument-set:d5151fdd88ba8949e173cd7e0533cdaf2e89b275b1e0663ee40518b59ba580d4|"
    "sha256:d5151fdd88ba8949e173cd7e0533cdaf2e89b275b1e0663ee40518b59ba580d4"
)
_WP_ALPHA_SOURCE_RUN = (
    "HISTORICAL_RESEARCH_SOURCE_RUN|"
    "historical-research-run-12e8dd606b480380dc0df356|"
    "sha256:12e8dd606b480380dc0df356ca5aa6c2fdc7b2abd6b215feca74195a50227029"
)


def create_phase_e3_research_universe_policy() -> ResearchUniversePolicy:
    """Rebuild the exact CSI300 policy frozen by the canonical source run."""

    return build_research_universe_policy(
        policy_version="phase-e3-csi300-longitudinal-v1",
        selectors=(
            UniversePolicySelector(
                kind=UniverseScopeKind.INDEX,
                selector_id="CSI300_EFFECTIVE_DATED_CONSTITUENTS",
                symbols=(),
            ),
        ),
        minimum_history_sessions=60,
        minimum_median_daily_amount=Decimal("1000000"),
        include_st=False,
        require_tradable=True,
        lot_size=100,
        data_authority="FREE_RESEARCH_ARCHIVE_PIT_INCOMPLETE",
    )


def phase_e3_decision_policy_identity() -> tuple[
    ArtifactId,
    str,
    dict[str, str],
]:
    """Return the exact DecisionTime identity frozen by the source run."""

    payload = {
        "schema_version": "phase-e3-historical-decision-policy/v1",
        "decision_local_time": "14:55:00",
        "timezone_name": "Asia/Shanghai",
        "methodology": "UNCHANGED_PHASE_E2_CANONICAL_CHAIN",
    }
    digest = canonical_hash(payload)
    return ArtifactId(f"phase-e3-decision-policy:{digest[7:]}"), digest, payload


def create_phase_e3_feature_configuration() -> FeatureSetConfiguration:
    return canonical_technical_feature_set(effective_from=_FEATURE_EFFECTIVE_FROM)


def create_phase_e3_strategy_economics_policy_set(
    *,
    target_protocol: OutcomeTargetProtocol,
    created_at: datetime,
) -> HistoricalStrategyEconomicsPolicySet:
    policies = tuple(
        _strategy_policy(target, created_at) for target in target_protocol.targets
    )
    return HistoricalStrategyEconomicsPolicySet.create(
        policy_set_version="phase-e3-unchanged-phase-e2-economics-v1",
        target_protocol_reference=ValidationArtifactReference(
            "OUTCOME_TARGET_PROTOCOL",
            target_protocol.protocol_id,
            target_protocol.protocol_hash,
        ),
        strategy_policies=policies,
        capacity_protocol=_capacity_protocol(created_at),
        created_at=created_at,
        limitations=tuple(
            sorted(
                {
                    *ENGINEERING_LIMITATIONS,
                    "COST_AND_FILLABILITY_ENGINEERING_ASSUMPTIONS",
                    "NOT_EMPIRICALLY_CALIBRATED",
                }
            )
        ),
    )


def create_phase_e3_historical_experiment(
    target_protocol: OutcomeTargetProtocol,
    *,
    locked_at: datetime,
) -> ResearchExperimentDefinition:
    """Create the sole unchanged Phase E2 methodology admitted by Phase E3."""

    feature_owner = create_phase_e3_feature_configuration()
    economics_owner = create_phase_e3_strategy_economics_policy_set(
        target_protocol=target_protocol,
        created_at=locked_at,
    )
    return ResearchExperimentDefinition.create(
        research_question=(
            "Does the unchanged Phase E alpha chain retain incremental ranking "
            "and executable economic value across longitudinal CSI300 history?"
        ),
        hypothesis=(
            "No Alpha layer is presumed valuable; positive, negative, "
            "inconclusive and not-estimable results are retained."
        ),
        decision_time_policy="FROZEN_14_55_ASIA_SHANGHAI",
        target_references=tuple(
            ValidationArtifactReference(
                "OUTCOME_TARGET",
                item.target_id,
                item.target_hash,
            )
            for item in target_protocol.targets
        ),
        feature_reference=ValidationArtifactReference(
            "FEATURE_SET_CONFIGURATION",
            feature_owner.feature_set_id,
            feature_owner.content_hash,
        ),
        feature_version=feature_owner.feature_set_version,
        allowed_model_families=("CANONICAL_HISTORICAL_FORECAST",),
        hyperparameter_space=(
            HyperparameterDomain("frozen_configuration", ("phase-e2-v1",)),
        ),
        search_budget=SearchBudget(1, 1),
        primary_hypothesis_ids=(
            "LONGITUDINAL:ABLATION_INCREMENTAL_LIFT:V1",
            "LONGITUDINAL:STRATEGY_NET_RETURN:V1",
        ),
        secondary_hypothesis_ids=(
            "LONGITUDINAL:FORECAST_ESTIMABILITY:V1",
            "LONGITUDINAL:SIGNAL_ACTIVE_COVERAGE:V1",
        ),
        multiple_testing_family_id="PHASE_E3_LONGITUDINAL_CHAIN_V1",
        stopping_rule="EXHAUST_FROZEN_SIX_MONTH_CORPUS",
        train_validation_policy="EXPANDING_PRIOR_SESSIONS_EXPLORATORY_ONLY",
        purge_embargo_policy="T_PLUS_1_OUTCOME_AVAILABLE_AFTER_NEXT_SESSION_ONLY",
        oos_unlock_policy="FORMAL_OOS_LOCKED_CLOSED",
        randomness_algorithm="DETERMINISTIC_CANONICAL_KERNELS",
        random_seeds=(20260813,),
        cost_policy_reference=economics_owner.reference,
        schema_version="research-experiment-definition/v2",
    )


def create_golden_loop_v2_historical_experiment(
    target_protocol: OutcomeTargetProtocol,
    *,
    locked_at: datetime,
) -> ResearchExperimentDefinition:
    """Freeze the V2 correctness change without tuning Phase E3 inputs."""

    v1 = create_phase_e3_historical_experiment(
        target_protocol,
        locked_at=locked_at,
    )
    scoring = GoldenLoopScoringContract.create_v2()
    return ResearchExperimentDefinition.create(
        research_question=v1.research_question,
        hypothesis=v1.hypothesis,
        decision_time_policy=v1.decision_time_policy,
        target_references=v1.target_references,
        feature_reference=v1.feature_reference,
        feature_version=v1.feature_version,
        allowed_model_families=v1.allowed_model_families,
        hyperparameter_space=(
            *v1.hyperparameter_space,
            HyperparameterDomain(
                "canonical_evidence_wiring",
                ("MULTI_STRATEGY_PORTFOLIO_OUTCOME_V2",),
            ),
            HyperparameterDomain("missing_policy", (scoring.missing_policy,)),
            HyperparameterDomain(
                "scoring_contract_hash",
                (scoring.contract_hash,),
            ),
            HyperparameterDomain("selection_policy", (scoring.selection_policy,)),
        ),
        search_budget=v1.search_budget,
        primary_hypothesis_ids=(
            "GOLDEN_LOOP_V2:ABLATION_INCREMENTAL_LIFT",
            "GOLDEN_LOOP_V2:CANONICAL_STRATEGY_NET_RETURN",
        ),
        secondary_hypothesis_ids=(
            "GOLDEN_LOOP_V2:CONSTANT_FACTOR_NEUTRALITY",
            "GOLDEN_LOOP_V2:FORECAST_ESTIMABILITY",
            "GOLDEN_LOOP_V2:SIGNAL_ACTIVE_COVERAGE",
            "GOLDEN_LOOP_V2:SYMBOL_EXCHANGE_BIAS",
        ),
        multiple_testing_family_id="WP_GOLDEN_LOOP_01_CORRECTNESS_V2",
        stopping_rule=v1.stopping_rule,
        train_validation_policy=v1.train_validation_policy,
        purge_embargo_policy=v1.purge_embargo_policy,
        oos_unlock_policy=v1.oos_unlock_policy,
        randomness_algorithm=v1.randomness_algorithm,
        random_seeds=v1.random_seeds,
        cost_policy_reference=v1.cost_policy_reference,
        schema_version=v1.schema_version,
    )


def create_wp_alpha_research_01_historical_experiment(
    target_protocol: OutcomeTargetProtocol,
    *,
    locked_at: datetime,
) -> ResearchExperimentDefinition:
    """Freeze the controlled Factor → Gate → Candidate discovery campaign."""

    golden = create_golden_loop_v2_historical_experiment(
        target_protocol,
        locked_at=locked_at,
    )
    feature_owner = create_phase_e3_feature_configuration()
    registry = canonical_alpha_factor_registry(feature_owner)
    target = next(
        item
        for item in target_protocol.targets
        if item.checkpoint is OutcomeCheckpoint.TIME_1030
    )
    factor_values = tuple(
        sorted(
            f"{item.family}|{item.feature_id}|{item.output_id}|"
            f"{item.role.value}|HIGHER_RAW_VALUE"
            for item in registry
        )
    )
    factor_registry_hash = canonical_hash(
        {"factor_registry": [item.to_canonical_dict() for item in registry]}
    )
    discovery_contract = alpha_discovery_evaluation_contract_reference(feature_owner)
    frozen_domains = (
        HyperparameterDomain("candidate_minimum_population", ("5",)),
        HyperparameterDomain("canonical_source_run", (_WP_ALPHA_SOURCE_RUN,)),
        HyperparameterDomain(
            "candidate_policies",
            (
                "CURRENT_HARD_CHAIN",
                "HARD_INTEGRITY_PRICE_RETURN",
                "HARD_INTEGRITY_PRICE_VOLUME_TREND",
                "NO_PREDICTIVE_GATES",
                "SOFT_CONTEXT_CANDIDATE",
            ),
        ),
        HyperparameterDomain("candidate_selection_top_k", ("5_WITH_BOUNDARY_TIES",)),
        HyperparameterDomain("constituent_timeline", (_WP_ALPHA_CONSTITUENT_TIMELINE,)),
        HyperparameterDomain("context_instrument_owner", (_WP_ALPHA_CONTEXT_OWNER,)),
        HyperparameterDomain("context_instruments", ("000300.SH", "510300.SH")),
        HyperparameterDomain("dataset_owner", (_WP_ALPHA_DATASET_OWNER,)),
        HyperparameterDomain("data_authority_mode", ("FREE_RESEARCH_ARCHIVE",)),
        HyperparameterDomain(
            "decision_policy",
            (
                "phase-e3-decision-policy:290d0639913fe993c6b5b6db5b21b98d513e20a4cef2e6230c3a30f98dc6c894|"
                "sha256:290d0639913fe993c6b5b6db5b21b98d513e20a4cef2e6230c3a30f98dc6c894",
            ),
        ),
        HyperparameterDomain("discovery_target", (f"OUTCOME_TARGET|{target.target_id}|{target.target_hash}",)),
        HyperparameterDomain(
            "discovery_evidence_ceiling",
            (
                "EXPLORATORY|PIT_INCOMPLETE|IN_SAMPLE_DISCOVERY|UNQUALIFIED|"
                "FORMAL_OOS_FALSE|CALIBRATED_FALSE|PRODUCTION_QUALIFIED_FALSE",
            ),
        ),
        HyperparameterDomain("evaluation_bucket_count", ("5",)),
        HyperparameterDomain(
            "evaluation_metrics",
            tuple(
                sorted(
                    (
                        "ASSUMED_COST_NET",
                        "BEFORE_AFTER_SAMPLE_SIZE",
                        "BUCKET_MONOTONICITY",
                        "CAPACITY_FILLABILITY",
                        "CONDITIONAL_EFFECT",
                        "DRAWDOWN",
                        "FORWARD_IC",
                        "FORWARD_RANK_IC",
                        "HIT_RATE",
                        "INCREMENTAL_LIFT",
                        "MAE",
                        "MFE",
                        "REJECTION_RATE",
                        "TEMPORAL_STABILITY",
                        "TOP_K_GROSS",
                        "TURNOVER_OVERLAP",
                    )
                )
            ),
        ),
        HyperparameterDomain(
            "evaluation_top_k",
            tuple(sorted(str(item) for item in ALPHA_DISCOVERY_TOP_K)),
        ),
        HyperparameterDomain("factor_registry", factor_values),
        HyperparameterDomain("factor_registry_hash", (factor_registry_hash,)),
        HyperparameterDomain(
            "alpha_discovery_evaluation_contract",
            (
                f"{discovery_contract.artifact_kind}|"
                f"{discovery_contract.artifact_id}|{discovery_contract.content_hash}",
            ),
        ),
        HyperparameterDomain(
            "gate_disposition_policy",
            (
                "DEMOTE_TO_FACTOR",
                "KEEP_AS_HARD_GATE",
                "RETEST",
                "RETIRE",
            ),
        ),
        HyperparameterDomain(
            "gate_incremental_effect_contract",
            (
                "MATCHED_SESSION_ONLY_REQUIRE_WITHIN_SESSION_ACCEPTED_AND_REJECTED",
            ),
        ),
        HyperparameterDomain(
            "gate_ids",
            tuple(sorted(ALPHA_DISCOVERY_GATE_IDS)),
        ),
        HyperparameterDomain(
            "gate_variants",
            ("CURRENT_HARD_GATE", "NO_PREDICTIVE_GATE", "SOFT_FEATURE"),
        ),
        HyperparameterDomain(
            "hard_integrity_gates",
            tuple(
                sorted(
                    (
                        "BASE_LIQUIDITY",
                        "CANONICAL_UNIVERSE_MEMBERSHIP",
                        "DATA_COMPLETENESS",
                        "DECISION_TIME_PIT_CORRECTNESS",
                        "REQUIRED_HISTORY",
                        "SUSPENSION_TRADABILITY",
                    )
                )
            ),
        ),
        HyperparameterDomain(
            "multiple_testing_method",
            ("BENJAMINI_HOCHBERG_FDR",),
        ),
        HyperparameterDomain(
            "ranking_contract",
            (GoldenLoopScoringContract.create_v2().contract_hash,),
        ),
        HyperparameterDomain("security_facts_owner", (_WP_ALPHA_SECURITY_FACTS,)),
        HyperparameterDomain("session_range", ("2025-01-02|2025-07-11|126",)),
        HyperparameterDomain(
            "runtime_scope_policy",
            (
                "research-universe-policy-b8f7171e930c35e52292dc49|"
                "sha256:b8f7171e930c35e52292dc492215973fca55321aa5ae0443345619cf9f680e4a",
            ),
        ),
        HyperparameterDomain(
            "target_protocol",
            (f"OUTCOME_TARGET_PROTOCOL|{target_protocol.protocol_id}|{target_protocol.protocol_hash}",),
        ),
        HyperparameterDomain("universe", ("CSI_300_EFFECTIVE_DATED|300_PER_SESSION",)),
    )
    return ResearchExperimentDefinition.create(
        research_question=(
            "Which DecisionTime-observable Factors and predictive Gates add stable, "
            "reproducible and economically meaningful T+1 10:30 information?"
        ),
        hypothesis=(
            "No current Factor, Gate or Candidate policy is presumed useful; all "
            "pre-registered results, including negative and not-estimable results, remain."
        ),
        decision_time_policy=golden.decision_time_policy,
        target_references=golden.target_references,
        feature_reference=golden.feature_reference,
        feature_version=golden.feature_version,
        allowed_model_families=("OWNER_RESOLVED_TIE_AWARE_FACTOR_RESEARCH",),
        hyperparameter_space=frozen_domains,
        search_budget=SearchBudget(1, 1),
        primary_hypothesis_ids=tuple(
            sorted(
                {
                    *(f"FACTOR:RANK_IC:{item.factor_id}" for item in registry if item.role.value == "NUMERIC_RANKED"),
                    *(f"GATE:INCREMENTAL_LIFT:{item}" for item in ALPHA_DISCOVERY_GATE_IDS),
                    "CANDIDATE_POLICY:INCREMENTAL_LIFT",
                }
            )
        ),
        secondary_hypothesis_ids=(
            "DISCOVERY:BUCKET_MONOTONICITY",
            "DISCOVERY:TEMPORAL_STABILITY",
            "DISCOVERY:TOP_K_ASSUMED_COST_NET",
        ),
        multiple_testing_family_id=WP_ALPHA_RESEARCH_01_MULTIPLE_TESTING_FAMILY,
        stopping_rule="EXHAUST_EXACTLY_126_FROZEN_DECISION_SESSIONS_NO_RESULT_DEPENDENT_CHANGE",
        train_validation_policy="FROZEN_IN_SAMPLE_DISCOVERY_ONLY_NO_SELECTION_CLAIM",
        purge_embargo_policy=golden.purge_embargo_policy,
        oos_unlock_policy="FORMAL_OOS_LOCKED_CLOSED_EXTERNAL_VALIDATION_IS_WP_ALPHA_RESEARCH_02",
        randomness_algorithm=golden.randomness_algorithm,
        random_seeds=golden.random_seeds,
        cost_policy_reference=golden.cost_policy_reference,
        schema_version=golden.schema_version,
    )


def create_wp_alpha_proof_02_historical_experiment(
    target_protocol: OutcomeTargetProtocol,
    *,
    locked_at: datetime,
    raw_owner_reference: ValidationArtifactReference,
    normalized_owner_reference: ValidationArtifactReference,
    calendar_reference: ValidationArtifactReference,
    universe_timeline_reference: ValidationArtifactReference,
    security_facts_reference: ValidationArtifactReference,
) -> ResearchExperimentDefinition:
    """Bind reacquired physical owners to the approved frozen vertical slice.

    This is an Experiment revision, not a replacement for the immutable
    Discovery parent. Execution must still reload every typed PostgreSQL owner
    before producing Evidence.
    """

    if locked_at != WP_ALPHA_PROOF_02_LOCKED_AT:
        raise ValueError("WP-ALPHA-PROOF-02 lock time is frozen at protocol checkpoint a926b95")
    expected_kinds = (
        (raw_owner_reference, "RAW_PROVIDER_ARCHIVE"),
        (normalized_owner_reference, "NORMALIZED_DATASET"),
        (calendar_reference, "TRADING_CALENDAR"),
        (
            universe_timeline_reference,
            "HISTORICAL_CONSTITUENT_TIMELINE",
        ),
        (security_facts_reference, "HISTORICAL_SECURITY_FACTS"),
    )
    for reference, expected_kind in expected_kinds:
        if reference.artifact_kind != expected_kind:
            raise ValueError(
                f"WP-ALPHA-PROOF-02 requires {expected_kind} owner"
            )
    discovery = create_wp_alpha_research_01_historical_experiment(
        target_protocol,
        locked_at=locked_at,
    )
    primary_target = next(
        item
        for item in target_protocol.targets
        if item.checkpoint is OutcomeCheckpoint.TIME_1030
    )
    domains = {
        item.parameter_name: item for item in discovery.hyperparameter_space
    }

    def bind(name: str, *values: str) -> None:
        domains[name] = HyperparameterDomain(name, tuple(sorted(set(values))))

    bind("raw_owner", _render_reference(raw_owner_reference))
    bind("normalized_owner", _render_reference(normalized_owner_reference))
    bind("dataset_owner", _render_reference(normalized_owner_reference))
    bind("trading_calendar_owner", _render_reference(calendar_reference))
    bind(
        "constituent_timeline",
        _render_reference(universe_timeline_reference),
    )
    bind("security_facts_owner", _render_reference(security_facts_reference))
    bind(
        "parent_discovery_experiment",
        _render_reference(_WP_ALPHA_PROOF_02_DISCOVERY_EXPERIMENT),
    )
    bind(
        "parent_discovery_evidence",
        "HISTORICAL_ALPHA_ABLATION_EVIDENCE|"
        "historical-evidence-f9326f869186419a89e450b9|"
        "sha256:f9326f869186419a89e450b9b64923046a30677d4c3c0003f1f12060388c1fe6",
    )
    bind(
        "external_window_owner",
        "FROZEN_TEMPORAL_VALIDATION_WINDOW|"
        "frozen-temporal-validation-window:"
        "b9e0dfaf85e5ed006f217b1e4b309347a6e5d296d2a8c09beba4296c0800278e|"
        "sha256:b9e0dfaf85e5ed006f217b1e4b309347a6e5d296d2a8c09beba4296c0800278e",
    )
    bind(
        "primary_target",
        f"OUTCOME_TARGET|{primary_target.target_id}|{primary_target.target_hash}",
    )
    bind(
        "factor_directions",
        "intraday_return_to_decision_time|HIGHER_IS_BETTER",
        "price_vs_vwap_return|HIGHER_IS_BETTER",
        "vwap_slope|HIGHER_IS_BETTER",
    )
    bind("factor_composite", "EQUAL_WEIGHT_RANK_PERCENTILE")
    bind("candidate_policies", "HARD_INTEGRITY_PRICE_RETURN")
    bind("candidate_selection_top_k", "5_WITH_BOUNDARY_TIES")
    bind("fractional_boundary", "FRACTIONAL_BOUNDARY_WEIGHT_V1")
    bind("round_trip_cost", "0.002100")
    bind("minimum_observation_coverage", "0.80")
    bind("minimum_discovery_rank_ic_retention", "0.50")
    bind("minimum_top_5_net_return", "0")
    bind("multiple_testing_method", "BENJAMINI_HOCHBERG_FDR")
    bind("inference_iterations", "2000")
    bind("inference_block_lengths", "1|5|10")
    bind("inference_confidence", "0.95")
    bind("random_seed", "20260813")
    bind(
        "discovery_sessions",
        "2025-01-02|2025-07-11|126|FINAL_TARGET_2025-07-14",
    )
    bind(
        "external_sessions",
        "2025-07-15|2026-01-16|126|FINAL_TARGET_2026-01-19",
    )
    bind(
        "forecast_model_families",
        "NAIVE_BASELINE",
        "EMPIRICAL_PATH_FORECAST",
        "REGULARIZED_LINEAR_CONDITIONAL",
    )
    bind("conditional_forecast_penalties", "0.1", "1")
    bind("conditional_forecast_max_fits_per_fold", "2")
    bind("purge_embargo", "ONE_TARGET_SESSION")
    bind(
        "formal_pit_locked_oos_gate",
        "FORMAL_PIT_SUPPORTED_AND_PHYSICAL_CORRECTNESS_SUPPORTED",
    )
    bind("locked_oos_outcome_access", "FAIL_CLOSED_BEFORE_GATE")
    bind("protocol_checkpoint", "git:a926b95")
    return ResearchExperimentDefinition.create(
        research_question=(
            "Does the frozen three-Factor equal-weight rank composite reproduce "
            "and retain stable T+1 10:30 information and non-negative Top-5 "
            "net research economics in the frozen External window?"
        ),
        hypothesis=(
            "All three Factor directions, equal weights, Top-5, cost, "
            "partitions and inference rules are pre-registered; negative and "
            "not-estimable results are terminal for this Experiment."
        ),
        decision_time_policy="FROZEN_14_55_ASIA_SHANGHAI",
        target_references=discovery.target_references,
        feature_reference=discovery.feature_reference,
        feature_version=discovery.feature_version,
        allowed_model_families=(
            "EMPIRICAL_PATH_FORECAST",
            "NAIVE_BASELINE",
            "REGULARIZED_LINEAR_CONDITIONAL",
        ),
        hyperparameter_space=tuple(domains.values()),
        search_budget=SearchBudget(2, 3_600),
        primary_hypothesis_ids=(
            "ALPHA:THREE_FACTOR_COMPOSITE:RANK_IC",
            "ALPHA:THREE_FACTOR_COMPOSITE:TOP_5_NET",
        ),
        secondary_hypothesis_ids=(
            "CANDIDATE:INCUMBENT_VS_CHALLENGER",
            "FORECAST:CONDITIONAL_BASELINE_LIFT",
            "STRATEGY:NET_ECONOMICS",
        ),
        multiple_testing_family_id=(
            WP_ALPHA_PROOF_02_MULTIPLE_TESTING_FAMILY
        ),
        stopping_rule=(
            "EXHAUST_FROZEN_EXTERNAL_SCOPE_ONCE_NO_RESULT_DEPENDENT_CHANGE"
        ),
        train_validation_policy=(
            "DISCOVERY_REPRODUCTION_THEN_FROZEN_EXTERNAL_NO_OOS_TUNING"
        ),
        purge_embargo_policy="ONE_TARGET_SESSION_PURGE_AND_EMBARGO",
        oos_unlock_policy=(
            "FORMAL_PIT_AND_PHYSICAL_CORRECTNESS_HARD_GATE_NO_OUTCOME_READ"
        ),
        randomness_algorithm="DETERMINISTIC_FROZEN_SEED",
        random_seeds=(20260813,),
        cost_policy_reference=discovery.cost_policy_reference,
        schema_version="research-experiment-definition/v2",
    )


def _render_reference(reference: ValidationArtifactReference) -> str:
    return (
        f"{reference.artifact_kind}|{reference.artifact_id}|"
        f"{reference.content_hash}"
    )


def verify_phase_e3_historical_experiment(
    definition: ResearchExperimentDefinition,
    *,
    target_protocol: OutcomeTargetProtocol,
    feature_owner: FeatureSetConfiguration,
    economics_owner: HistoricalStrategyEconomicsPolicySet,
    decision_local_time: time,
    timezone_name: str,
    configuration_references: tuple[ValidationArtifactReference, ...],
) -> None:
    """Fail closed unless owner reload proves the exact frozen methodology."""

    expected = create_phase_e3_historical_experiment(
        target_protocol,
        locked_at=economics_owner.created_at,
    )
    if definition != expected:
        raise ValueError(
            "Longitudinal Historical Experiment diverges from the frozen Phase E3 methodology"
        )
    if feature_owner != create_phase_e3_feature_configuration():
        raise ValueError("Longitudinal Historical Feature owner diverged")
    if economics_owner != create_phase_e3_strategy_economics_policy_set(
        target_protocol=target_protocol,
        created_at=economics_owner.created_at,
    ):
        raise ValueError("Longitudinal Historical Economics owner diverged")
    if (
        decision_local_time != PHASE_E3_DECISION_LOCAL_TIME
        or timezone_name != PHASE_E3_TIMEZONE
    ):
        raise ValueError("Longitudinal Historical DecisionTime policy diverged")
    required = {
        definition.feature_reference,
        definition.cost_policy_reference,
    }
    if not required.issubset(set(configuration_references)):
        raise ValueError(
            "Longitudinal Historical command omits frozen feature or cost bindings"
        )


def verify_golden_loop_v2_historical_experiment(
    definition: ResearchExperimentDefinition,
    *,
    target_protocol: OutcomeTargetProtocol,
    feature_owner: FeatureSetConfiguration,
    economics_owner: HistoricalStrategyEconomicsPolicySet,
    decision_local_time: time,
    timezone_name: str,
    configuration_references: tuple[ValidationArtifactReference, ...],
) -> None:
    """Fail closed unless the exact Golden Loop V2 correction is bound."""

    expected = create_golden_loop_v2_historical_experiment(
        target_protocol,
        locked_at=economics_owner.created_at,
    )
    if definition != expected:
        raise ValueError(
            "Historical Experiment diverges from the frozen Golden Loop V2 methodology"
        )
    if feature_owner != create_phase_e3_feature_configuration():
        raise ValueError("Golden Loop V2 Historical Feature owner diverged")
    if economics_owner != create_phase_e3_strategy_economics_policy_set(
        target_protocol=target_protocol,
        created_at=economics_owner.created_at,
    ):
        raise ValueError("Golden Loop V2 Historical Economics owner diverged")
    if (
        decision_local_time != PHASE_E3_DECISION_LOCAL_TIME
        or timezone_name != PHASE_E3_TIMEZONE
    ):
        raise ValueError("Golden Loop V2 Historical DecisionTime policy diverged")
    required = {
        definition.feature_reference,
        definition.cost_policy_reference,
        GoldenLoopScoringContract.create_v2().reference,
    }
    if not required.issubset(set(configuration_references)):
        raise ValueError(
            "Golden Loop V2 command omits frozen feature or cost bindings"
        )


def verify_wp_alpha_research_01_historical_experiment(
    definition: ResearchExperimentDefinition,
    *,
    target_protocol: OutcomeTargetProtocol,
    feature_owner: FeatureSetConfiguration,
    economics_owner: HistoricalStrategyEconomicsPolicySet,
    decision_local_time: time,
    timezone_name: str,
    configuration_references: tuple[ValidationArtifactReference, ...],
) -> None:
    """Fail closed on any post-registration campaign methodology drift."""

    expected = create_wp_alpha_research_01_historical_experiment(
        target_protocol,
        locked_at=economics_owner.created_at,
    )
    if definition != expected:
        raise ValueError("WP-ALPHA-RESEARCH-01 Experiment Definition drifted")
    if feature_owner != create_phase_e3_feature_configuration():
        raise ValueError("WP-ALPHA-RESEARCH-01 Feature owner drifted")
    if economics_owner != create_phase_e3_strategy_economics_policy_set(
        target_protocol=target_protocol,
        created_at=economics_owner.created_at,
    ):
        raise ValueError("WP-ALPHA-RESEARCH-01 Economics owner drifted")
    if (
        decision_local_time != PHASE_E3_DECISION_LOCAL_TIME
        or timezone_name != PHASE_E3_TIMEZONE
    ):
        raise ValueError("WP-ALPHA-RESEARCH-01 DecisionTime drifted")
    required = {
        definition.feature_reference,
        definition.cost_policy_reference,
        GoldenLoopScoringContract.create_v2().reference,
        alpha_discovery_evaluation_contract_reference(feature_owner),
        ValidationArtifactReference(
            "HISTORICAL_RESEARCH_SOURCE_RUN",
            ArtifactId("historical-research-run-12e8dd606b480380dc0df356"),
            "sha256:12e8dd606b480380dc0df356ca5aa6c2fdc7b2abd6b215feca74195a50227029",
        ),
    }
    if not required.issubset(set(configuration_references)):
        raise ValueError("WP-ALPHA-RESEARCH-01 command omits a frozen binding")


def verify_wp_alpha_proof_02_historical_experiment(
    definition: ResearchExperimentDefinition,
    *,
    target_protocol: OutcomeTargetProtocol,
    feature_owner: FeatureSetConfiguration,
    economics_owner: HistoricalStrategyEconomicsPolicySet,
    decision_local_time: time,
    timezone_name: str,
    runtime_scope_policy_id: ArtifactId,
    runtime_scope_policy_hash: str,
    decision_policy_id: ArtifactId,
    decision_policy_hash: str,
    configuration_references: tuple[ValidationArtifactReference, ...],
) -> None:
    """Reload and verify the exact approved vertical-slice methodology."""

    references = set(configuration_references)

    def required_owner(kind: str) -> ValidationArtifactReference:
        matches = tuple(item for item in references if item.artifact_kind == kind)
        if len(matches) != 1:
            raise ValueError(
                f"WP-ALPHA-PROOF-02 command omits frozen physical owner {kind}"
            )
        return matches[0]

    expected = create_wp_alpha_proof_02_historical_experiment(
        target_protocol,
        locked_at=WP_ALPHA_PROOF_02_LOCKED_AT,
        raw_owner_reference=required_owner("RAW_PROVIDER_ARCHIVE"),
        normalized_owner_reference=required_owner("NORMALIZED_DATASET"),
        calendar_reference=required_owner("TRADING_CALENDAR"),
        universe_timeline_reference=required_owner(
            "HISTORICAL_CONSTITUENT_TIMELINE"
        ),
        security_facts_reference=required_owner("HISTORICAL_SECURITY_FACTS"),
    )
    if definition != expected:
        raise ValueError("WP-ALPHA-PROOF-02 Experiment Definition drifted")
    if feature_owner != create_phase_e3_feature_configuration():
        raise ValueError("WP-ALPHA-PROOF-02 Feature owner drifted")
    if economics_owner != create_phase_e3_strategy_economics_policy_set(
        target_protocol=target_protocol,
        created_at=WP_ALPHA_PROOF_02_LOCKED_AT,
    ):
        raise ValueError("WP-ALPHA-PROOF-02 Economics owner drifted")
    if (
        decision_local_time != PHASE_E3_DECISION_LOCAL_TIME
        or timezone_name != PHASE_E3_TIMEZONE
    ):
        raise ValueError("WP-ALPHA-PROOF-02 DecisionTime drifted")
    domains = {
        item.parameter_name: item.allowed_values
        for item in definition.hyperparameter_space
    }
    if domains.get("runtime_scope_policy") != (
        f"{runtime_scope_policy_id}|{runtime_scope_policy_hash}",
    ):
        raise ValueError("WP-ALPHA-PROOF-02 Runtime Scope Policy drifted")
    if domains.get("decision_policy") != (
        f"{decision_policy_id}|{decision_policy_hash}",
    ):
        raise ValueError("WP-ALPHA-PROOF-02 Decision Policy drifted")
    methodology = {
        definition.feature_reference,
        definition.cost_policy_reference,
        GoldenLoopScoringContract.create_v2().reference,
        alpha_discovery_evaluation_contract_reference(feature_owner),
    }
    if not methodology.issubset(references):
        raise ValueError("WP-ALPHA-PROOF-02 command omits frozen methodology owner")


def _strategy_policy(
    target: TargetDefinition,
    created_at: datetime,
) -> StrategyEconomicsPolicy:
    return StrategyEconomicsPolicy.create(
        policy_version=f"phase-e-{target.checkpoint.value}-engineering-cost-v1",
        prediction_target=target,
        entry_kind=StrategyEntryKind.FROZEN_DECISION_REFERENCE,
        exit_kind=StrategyExitKind.FIXED_TIME,
        fixed_exit_checkpoint=target.checkpoint,
        barrier_id=None,
        forecast_raw_score_threshold=None,
        lot_size=100,
        t_plus_one=True,
        parameters={
            "commission_bps": (
                Decimal("3"),
                ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
            ),
            "stamp_duty_bps": (
                Decimal("5"),
                ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
            ),
            "spread_slippage_bps": (
                Decimal("5"),
                ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
            ),
        },
        created_at=created_at,
    )


def _capacity_protocol(created_at: datetime) -> LiquidityCapacityProtocol:
    return LiquidityCapacityProtocol.create(
        protocol_version="phase-e-capacity-engineering-v1",
        parameters=tuple(
            CapacityParameter(
                name,
                value,
                CapacityValueProvenance.ENGINEERING_ASSUMPTION,
            )
            for name, value in (
                ("impact_coefficient_bps", Decimal("8")),
                ("participation_rate", Decimal("0.1")),
                ("slippage_bps", Decimal("5")),
            )
        ),
        created_at=created_at,
    )


__all__ = [
    "HistoricalStrategyEconomicsPolicySet",
    "PHASE_E3_DECISION_LOCAL_TIME",
    "PHASE_E3_TIMEZONE",
    "WP_ALPHA_PROOF_02_LOCKED_AT",
    "WP_ALPHA_PROOF_02_MULTIPLE_TESTING_FAMILY",
    "WP_ALPHA_RESEARCH_01_MULTIPLE_TESTING_FAMILY",
    "create_phase_e3_feature_configuration",
    "create_golden_loop_v2_historical_experiment",
    "create_phase_e3_historical_experiment",
    "create_phase_e3_research_universe_policy",
    "create_phase_e3_strategy_economics_policy_set",
    "create_wp_alpha_proof_02_historical_experiment",
    "create_wp_alpha_research_01_historical_experiment",
    "phase_e3_decision_policy_identity",
    "verify_phase_e3_historical_experiment",
    "verify_golden_loop_v2_historical_experiment",
    "verify_wp_alpha_research_01_historical_experiment",
    "verify_wp_alpha_proof_02_historical_experiment",
]
