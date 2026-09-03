"""Frozen, deterministic Authority plans for the first WP-17P pilot.

The catalog is intentionally small: one feature, one Target, one Selection
policy, one Decision Support baseline, two chronological folds, and two arms.
It contains no fitted parameters and no empirical result.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from market_regime_alpha.decision_support.domain import (
    CandidateDisposition as DecisionCandidateDisposition,
    ContextFailureAction,
    ContextKind,
    ContextMeasure,
    ContextMetricDefinition,
    ContextMissingnessPolicy,
    ContextOperator,
    ContextPolicyPlan,
    ContextReducer,
    ContextSourceRole,
    ContextState,
    DecisionArtifactBinding,
    ForecastSourceMeasure,
    PortfolioAllocationMethod,
    PortfolioPolicyPlan,
    RiskAuthorityScope,
    RiskMissingAction,
    RiskOperator,
    RiskPolicyPlan,
    RiskRulePlan,
    RiskRuleScope,
    RiskSeverity,
    RiskSubject,
    SignalStatus,
    StrategyActionPolicy,
    StrategyContextRequirement,
    StrategyForecastRule,
    StrategyPlan,
    StrategySignalRule,
    StrategyVersionPlan,
)
from market_regime_alpha.market.ports import ArchiveTradingSession
from market_regime_alpha.research_qualification.domain import (
    ArtifactBinding,
    FeatureAvailabilityRule,
    FeatureDefinition,
    FeatureIntervalUnit,
    FeatureMissingnessPolicy,
    FeatureSourceRequirement,
    FeatureValueType,
)
from market_regime_alpha.research_qualification.domain.evaluation import (
    EvaluationProtocolPlan,
    ProtocolMetricDefinition,
)
from market_regime_alpha.research_qualification.domain.exploratory_backtest import (
    BacktestArmKind,
    BacktestArmPlan,
    BacktestCostAssumption,
    BacktestCostKind,
    BacktestFoldPlan,
    BacktestFoldSessionPlan,
    BacktestSessionRole,
    ExploratoryBacktestRunPlan,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    AcceptanceOperator,
    EvaluationReducer,
    EvaluationSliceKind,
    EvaluationSourceKind,
    EvaluationSourceMeasure,
    ExploratoryBacktestArmKind,
    MetricDirection,
    PartitionPurpose,
    SourceMetricValueType,
)
from market_regime_alpha.research_qualification.domain.target_vocabulary import (
    TargetAvailabilityRule,
    TargetBarTimeframe,
    TargetCheckpointRole,
    TargetCompletionRule,
    TargetDependencyRole,
    TargetFinalityRule,
    TargetInstrumentScope,
    TargetMarketScope,
    TargetMetricKind,
    TargetMetricUnit,
    TargetPriceBasis,
    TargetReferenceRule,
    TargetTimingRule,
    TargetValueField,
    TargetValueType,
)
from market_regime_alpha.research_qualification.domain.targets import (
    TargetAlgorithmBinding,
    TargetCheckpoint,
    TargetDefinition,
    TargetMetricDefinition,
    TargetMetricDependency,
)
from market_regime_alpha.selection.domain import (
    CandidateArtifactBinding,
    CandidateFeatureValueType,
    CandidatePolicy,
    CandidatePolicyComponent,
    CriterionOperator,
    CriterionValueKind,
    DesirabilityDirection,
    EligibilityPolicy,
    EligibilityRule,
    EligibilityRuleKind,
    UniverseDefinition,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


_CATALOG_KEY = "mra:wp17p:engineering-pilot:v1"


@dataclass(frozen=True, slots=True)
class Wp17pAuthorityCatalog:
    target: TargetDefinition
    feature: FeatureDefinition
    universe: UniverseDefinition
    eligibility_policy: EligibilityPolicy
    candidate_policy: CandidatePolicy
    context_policy: ContextPolicyPlan
    strategy: StrategyVersionPlan
    portfolio_policy: PortfolioPolicyPlan
    risk_policy: RiskPolicyPlan
    fit_evaluation_protocol: EvaluationProtocolPlan
    validation_evaluation_protocol: EvaluationProtocolPlan
    backtest: ExploratoryBacktestRunPlan


def build_wp17p_authority_catalog(
    *,
    provider_product_id: UUID,
    market_archive_id: UUID,
    market_archive_seal_id: UUID,
    sessions: tuple[ArchiveTradingSession, ...],
    code_artifact: ArtifactBinding,
    config_artifact: ArtifactBinding,
    provenance_sha256: str,
) -> Wp17pAuthorityCatalog:
    if len(sessions) != 8:
        raise ValueError("WP-17P pilot requires exactly eight declared sessions")
    if tuple(item.session_date for item in sessions) != tuple(sorted({item.session_date for item in sessions})):
        raise ValueError("WP-17P sessions must be unique and chronological")
    if any(item.exchange != "XSHG" for item in sessions):
        raise ValueError("WP-17P v1 uses one explicit XSHG calendar")

    target = _target(code_artifact, config_artifact)
    feature = _feature(code_artifact, config_artifact)
    universe = UniverseDefinition(
        _id("universe"),
        "wp17p_csi300_hash32",
        "Stable-hash 32-instrument engineering and exploratory population",
    )
    eligibility = _eligibility(provider_product_id)
    candidate = _candidate(feature, code_artifact, config_artifact)
    context = _context(code_artifact, config_artifact, provenance_sha256)
    strategy = _strategy(
        target,
        context,
        code_artifact,
        config_artifact,
        provenance_sha256,
    )
    portfolio = _portfolio(code_artifact, config_artifact, provenance_sha256)
    risk = _risk(code_artifact, config_artifact, provenance_sha256)
    fit = _evaluation_protocol(
        target,
        PartitionPurpose.FIT,
        code_artifact,
        config_artifact,
        provenance_sha256,
    )
    validation = _evaluation_protocol(
        target,
        PartitionPurpose.VALIDATION,
        code_artifact,
        config_artifact,
        provenance_sha256,
    )
    backtest = _backtest(
        market_archive_id,
        market_archive_seal_id,
        sessions,
        target,
        feature,
        candidate,
        context,
        strategy,
        portfolio,
        risk,
        fit,
        validation,
        code_artifact,
        config_artifact,
        provenance_sha256,
    )
    return Wp17pAuthorityCatalog(
        target,
        feature,
        universe,
        eligibility,
        candidate,
        context,
        strategy,
        portfolio,
        risk,
        fit,
        validation,
        backtest,
    )


def _target(code: ArtifactBinding, config: ArtifactBinding) -> TargetDefinition:
    target_id = _id("target")
    reference_id = _id("target:reference")
    observation_id = _id("target:observation")
    metric_id = _id("target:metric")
    algorithm = TargetAlgorithmBinding(
        algorithm_code="simple_return",
        algorithm_version="1.0.0",
        algorithm_sha256=canonical_json_sha256({"formula": "observation/reference-1", "scale": 18}),
        code_artifact=code,
        config_artifact=config,
    )
    checkpoints = (
        TargetCheckpoint(
            reference_id,
            target_id,
            "decision_reference_1455",
            1,
            TargetCheckpointRole.DECISION_REFERENCE,
            0,
            TargetTimingRule.SESSION_LOCAL_BAR_END,
            time(14, 55),
            "Asia/Shanghai",
            TargetBarTimeframe.MINUTE_5,
            TargetPriceBasis.RAW_UNADJUSTED,
            TargetValueField.CLOSE,
            TargetReferenceRule.EXACT_SESSION_BAR,
            TargetAvailabilityRule.EXACT_REVISION_OR_SOURCE_GAP,
            TargetFinalityRule.RECORD_UNKNOWN,
        ),
        TargetCheckpoint(
            observation_id,
            target_id,
            "next_session_1030",
            2,
            TargetCheckpointRole.OUTCOME_OBSERVATION,
            1,
            TargetTimingRule.SESSION_LOCAL_BAR_END,
            time(10, 30),
            "Asia/Shanghai",
            TargetBarTimeframe.MINUTE_5,
            TargetPriceBasis.RAW_UNADJUSTED,
            TargetValueField.CLOSE,
            TargetReferenceRule.EXACT_SESSION_BAR,
            TargetAvailabilityRule.EXACT_REVISION_OR_SOURCE_GAP,
            TargetFinalityRule.RECORD_UNKNOWN,
        ),
    )
    metric = TargetMetricDefinition(
        metric_id,
        target_id,
        "next_session_return",
        1,
        TargetMetricKind.SIMPLE_RETURN,
        TargetValueType.DECIMAL,
        TargetMetricUnit.RATIO,
        TargetCompletionRule.REQUIRED,
        algorithm,
    )
    dependencies = tuple(
        TargetMetricDependency(
            _id(f"target:dependency:{ordinal}"),
            target_id,
            metric_id,
            checkpoint_id,
            ordinal,
            role,
        )
        for ordinal, (checkpoint_id, role) in enumerate(
            (
                (reference_id, TargetDependencyRole.REFERENCE),
                (observation_id, TargetDependencyRole.OBSERVATION),
            ),
            start=1,
        )
    )
    return TargetDefinition(
        target_id,
        "wp17p_next_session_return",
        1,
        None,
        TargetInstrumentScope.A_SHARE_EQUITY,
        TargetMarketScope.SSE_SZSE,
        algorithm,
        checkpoints,
        (metric,),
        dependencies,
    )


def _feature(code: ArtifactBinding, config: ArtifactBinding) -> FeatureDefinition:
    return FeatureDefinition(
        _id("feature"),
        "intraday_move_1455",
        1,
        FeatureValueType.DECIMAL,
        "RATIO",
        1,
        FeatureIntervalUnit.TRADING_SESSION,
        1,
        FeatureIntervalUnit.TRADING_SESSION,
        0,
        FeatureIntervalUnit.TRADING_SESSION,
        (FeatureSourceRequirement.MARKET_BAR_REVISION,),
        FeatureAvailabilityRule.DECISION_VISIBLE_AT_OR_BEFORE,
        FeatureMissingnessPolicy.EXPLICIT_STATUS,
        "intraday_move",
        "1.0.0",
        canonical_json_sha256({"formula": "close/open-1", "checkpoint": "14:55"}),
        code,
        config,
    )


def _eligibility(provider_product_id: UUID) -> EligibilityPolicy:
    policy_id = _id("eligibility")
    return EligibilityPolicy(
        policy_id,
        provider_product_id,
        "wp17p_minimal_historical_eligibility",
        1,
        (
            EligibilityRule(
                _id("eligibility:listing"),
                "MIN_LISTING_AGE",
                1,
                EligibilityRuleKind.MIN_LISTING_AGE,
                "LISTING_AGE",
                "ELAPSED",
                0,
                "NONE",
                CriterionValueKind.DECIMAL,
                CriterionOperator.GTE,
                "CALENDAR_DAYS",
                threshold_decimal=Decimal("0"),
            ),
            EligibilityRule(
                _id("eligibility:suspension"),
                "NOT_SUSPENDED",
                2,
                EligibilityRuleKind.NOT_SUSPENDED,
                "SECURITY_STATUS",
                "POINT",
                1,
                "SESSION",
                CriterionValueKind.STATUS,
                CriterionOperator.EQ,
                "STATUS",
                threshold_status="ACTIVE",
            ),
            EligibilityRule(
                _id("eligibility:special"),
                "NOT_SPECIAL_TREATMENT",
                3,
                EligibilityRuleKind.NOT_SPECIAL_TREATMENT,
                "SPECIAL_TREATMENT_STATUS",
                "POINT",
                0,
                "NONE",
                CriterionValueKind.STATUS,
                CriterionOperator.EQ,
                "STATUS",
                threshold_status="NORMAL",
            ),
        ),
    )


def _candidate(
    feature: FeatureDefinition,
    code: ArtifactBinding,
    config: ArtifactBinding,
) -> CandidatePolicy:
    policy_id = _id("candidate")
    return CandidatePolicy(
        policy_id,
        "wp17p_intraday_rank_top5",
        1,
        _candidate_artifact(code),
        _candidate_artifact(config),
        5,
        (
            CandidatePolicyComponent(
                _id("candidate:component"),
                policy_id,
                "intraday_move",
                1,
                feature.feature_definition_id,
                feature.content_sha256,
                CandidateFeatureValueType.DECIMAL,
                DesirabilityDirection.HIGHER_IS_BETTER,
                Decimal("1"),
            ),
        ),
    )


def _context(
    code: ArtifactBinding,
    config: ArtifactBinding,
    provenance: str,
) -> ContextPolicyPlan:
    policy_id = _id("context")
    return ContextPolicyPlan(
        policy_id,
        "wp17p_market_breadth",
        1,
        None,
        (
            ContextMetricDefinition(
                _id("context:advance-rate"),
                policy_id,
                "market_advance_rate",
                1,
                ContextKind.MARKET_REGIME,
                ContextMeasure.ADVANCE_RATE,
                ContextReducer.TRUE_RATE,
                ContextOperator.AT_LEAST,
                Decimal("0.50"),
                None,
                0,
                1,
                ContextMissingnessPolicy.NOT_ESTIMABLE,
                ContextSourceRole.PRIMARY_DECISION_REFERENCE,
            ),
        ),
        _decision_artifact(code),
        _decision_artifact(config),
        provenance,
    )


def _strategy(
    target: TargetDefinition,
    context: ContextPolicyPlan,
    code: ArtifactBinding,
    config: ArtifactBinding,
    provenance: str,
) -> StrategyVersionPlan:
    strategy_id = _id("strategy")
    version_id = _id("strategy:version:1")
    return StrategyVersionPlan(
        StrategyPlan(
            strategy_id,
            "wp17p_transparent_rank",
            "Context-confirmed, uncalibrated Target-bound ranking baseline",
        ),
        version_id,
        1,
        None,
        "Initial transparent retrospective baseline",
        StrategyActionPolicy.LONG_ONLY_RESEARCH,
        (
            StrategyContextRequirement(
                _id("strategy:context"),
                version_id,
                1,
                context.context_policy_id,
                context.content_sha256,
                ContextKind.MARKET_REGIME,
                # Neutral is not sufficient for an actionable signal.
                ContextState.POSITIVE,
                ContextFailureAction.WAIT,
            ),
        ),
        StrategySignalRule(
            _id("strategy:signal"),
            version_id,
            DecisionCandidateDisposition.SELECTED,
            SignalStatus.PRESENT,
            SignalStatus.NO_SIGNAL,
            SignalStatus.NO_SIGNAL,
        ),
        (
            StrategyForecastRule(
                _id("strategy:forecast"),
                version_id,
                1,
                target.target_definition_id,
                str(target.content_sha256),
                target.checkpoints[0].target_checkpoint_id,
                str(target.checkpoints[0].content_sha256),
                target.metrics[0].target_metric_definition_id,
                str(target.metrics[0].content_sha256),
                ForecastSourceMeasure.CANDIDATE_COMPOSITE_SCORE,
                Decimal("0.02"),
                Decimal("0"),
                Decimal("0.03"),
                Decimal("0.03"),
                "DECIMAL_RETURN",
            ),
        ),
        _decision_artifact(code),
        _decision_artifact(config),
        provenance,
    )


def _portfolio(
    code: ArtifactBinding,
    config: ArtifactBinding,
    provenance: str,
) -> PortfolioPolicyPlan:
    return PortfolioPolicyPlan(
        _id("portfolio"),
        "wp17p_equal_weight",
        1,
        None,
        PortfolioAllocationMethod.EQUAL_WEIGHT_ACTIONABLE,
        1,
        5,
        Decimal("0.25"),
        Decimal("1"),
        Decimal("1"),
        Decimal("0"),
        Decimal("1"),
        8,
        _decision_artifact(code),
        _decision_artifact(config),
        provenance,
    )


def _risk(
    code: ArtifactBinding,
    config: ArtifactBinding,
    provenance: str,
) -> RiskPolicyPlan:
    policy_id = _id("risk")
    rules = (
        RiskRulePlan(
            _id("risk:gross"),
            policy_id,
            1,
            "gross_weight_cap",
            RiskRuleScope.GLOBAL,
            RiskSubject.GROSS_WEIGHT,
            RiskOperator.AT_MOST,
            Decimal("1"),
            None,
            None,
            None,
            "WEIGHT",
            RiskSeverity.REJECT,
            RiskMissingAction.FAIL,
        ),
        RiskRulePlan(
            _id("risk:line"),
            policy_id,
            2,
            "single_weight_cap",
            RiskRuleScope.LINE,
            RiskSubject.SINGLE_LINE_WEIGHT,
            RiskOperator.AT_MOST,
            Decimal("0.25"),
            None,
            None,
            None,
            "WEIGHT",
            RiskSeverity.REJECT,
            RiskMissingAction.FAIL,
        ),
    )
    return RiskPolicyPlan(
        policy_id,
        "wp17p_research_risk",
        1,
        None,
        RiskAuthorityScope.DECISION_SUPPORT_ONLY,
        rules,
        _decision_artifact(code),
        _decision_artifact(config),
        provenance,
    )


def _evaluation_protocol(
    target: TargetDefinition,
    purpose: PartitionPurpose,
    code: ArtifactBinding,
    config: ArtifactBinding,
    provenance: str,
) -> EvaluationProtocolPlan:
    protocol_id = _id(f"evaluation:{purpose.value}")
    target_metric = target.metrics[0]
    arms = (
        ("baseline", ExploratoryBacktestArmKind.RULE_BASELINE),
        ("model", ExploratoryBacktestArmKind.MODEL_CHALLENGER),
    )
    metrics: list[ProtocolMetricDefinition] = []

    def append(
        suffix: str,
        arm: ExploratoryBacktestArmKind,
        reducer: EvaluationReducer,
        value_type: SourceMetricValueType,
        source_kind: EvaluationSourceKind,
        source_measure: EvaluationSourceMeasure,
        *,
        minimum: int = 1,
        direction: MetricDirection = MetricDirection.DESCRIPTIVE,
    ) -> None:
        metrics.append(
            ProtocolMetricDefinition(
                _id(f"evaluation:{purpose.value}:{suffix}"),
                suffix,
                len(metrics) + 1,
                target_metric.target_metric_definition_id,
                target_metric.metric_code,
                value_type,
                reducer,
                EvaluationSliceKind.EXPLORATORY_BACKTEST_ARM,
                None,
                direction,
                minimum,
                AcceptanceOperator.NONE,
                None,
                arm,
                source_kind=source_kind,
                source_measure=source_measure,
            )
        )

    if purpose is PartitionPurpose.FIT:
        append(
            "fit_model_mean",
            ExploratoryBacktestArmKind.MODEL_CHALLENGER,
            EvaluationReducer.MEAN_DECIMAL,
            SourceMetricValueType.DECIMAL,
            EvaluationSourceKind.OUTCOME_METRIC,
            EvaluationSourceMeasure.TARGET_VALUE,
        )
    else:
        for label, arm in arms:
            for suffix, reducer, value_type, source_kind, measure, minimum in (
                (
                    "mean",
                    EvaluationReducer.MEAN_DECIMAL,
                    SourceMetricValueType.DECIMAL,
                    EvaluationSourceKind.OUTCOME_METRIC,
                    EvaluationSourceMeasure.TARGET_VALUE,
                    1,
                ),
                (
                    "rank_ic",
                    EvaluationReducer.SPEARMAN_RANK_CORRELATION,
                    SourceMetricValueType.DECIMAL,
                    EvaluationSourceKind.FORECAST_OUTCOME_PAIR,
                    EvaluationSourceMeasure.FORECAST_POINT_VS_TARGET,
                    2,
                ),
                (
                    "forecast_coverage",
                    EvaluationReducer.ESTIMABLE_RATE,
                    SourceMetricValueType.DECIMAL,
                    EvaluationSourceKind.FORECAST_OUTCOME_PAIR,
                    EvaluationSourceMeasure.FORECAST_POINT_VS_TARGET,
                    1,
                ),
                (
                    "selected_ratio",
                    EvaluationReducer.TRUE_RATE,
                    SourceMetricValueType.BOOLEAN,
                    EvaluationSourceKind.CANDIDATE_DISPOSITION,
                    EvaluationSourceMeasure.CANDIDATE_SELECTED,
                    1,
                ),
                (
                    "signal_coverage",
                    EvaluationReducer.TRUE_RATE,
                    SourceMetricValueType.BOOLEAN,
                    EvaluationSourceKind.SIGNAL_STATUS,
                    EvaluationSourceMeasure.SIGNAL_PRESENT,
                    1,
                ),
                (
                    "exposure",
                    EvaluationReducer.SUM_DECIMAL,
                    SourceMetricValueType.DECIMAL,
                    EvaluationSourceKind.PORTFOLIO_LINE,
                    EvaluationSourceMeasure.TARGET_WEIGHT,
                    1,
                ),
                (
                    "turnover",
                    EvaluationReducer.ABSOLUTE_MEAN_DECIMAL,
                    SourceMetricValueType.DECIMAL,
                    EvaluationSourceKind.PORTFOLIO_LINE,
                    EvaluationSourceMeasure.TURNOVER,
                    1,
                ),
                (
                    "gross_result",
                    EvaluationReducer.SUM_DECIMAL,
                    SourceMetricValueType.DECIMAL,
                    EvaluationSourceKind.PORTFOLIO_OUTCOME,
                    EvaluationSourceMeasure.GROSS_PORTFOLIO_RETURN,
                    1,
                ),
                (
                    "assumed_cost_net_result",
                    EvaluationReducer.SUM_DECIMAL,
                    SourceMetricValueType.DECIMAL,
                    EvaluationSourceKind.PORTFOLIO_OUTCOME,
                    EvaluationSourceMeasure.NET_PORTFOLIO_RETURN_ASSUMED_COST,
                    1,
                ),
                (
                    "drawdown",
                    EvaluationReducer.MAX_DRAWDOWN,
                    SourceMetricValueType.DECIMAL,
                    EvaluationSourceKind.PORTFOLIO_OUTCOME,
                    EvaluationSourceMeasure.NET_PORTFOLIO_RETURN_ASSUMED_COST,
                    1,
                ),
                (
                    "risk_rejection_rate",
                    EvaluationReducer.TRUE_RATE,
                    SourceMetricValueType.BOOLEAN,
                    EvaluationSourceKind.RISK_DECISION,
                    EvaluationSourceMeasure.RISK_REJECTED,
                    1,
                ),
            ):
                append(
                    f"{label}_{suffix}",
                    arm,
                    reducer,
                    value_type,
                    source_kind,
                    measure,
                    minimum=minimum,
                )
    return EvaluationProtocolPlan(
        protocol_id,
        f"wp17p_{purpose.value.lower()}_evaluation",
        1,
        target.target_definition_id,
        target.version,
        target.content_sha256,
        purpose,
        "Descriptive exploratory metrics only; no formal admission.",
        tuple(metrics),
        code,
        config,
        provenance,
    )


def _backtest(
    archive_id: UUID,
    seal_id: UUID,
    sessions: tuple[ArchiveTradingSession, ...],
    target: TargetDefinition,
    feature: FeatureDefinition,
    candidate: CandidatePolicy,
    context: ContextPolicyPlan,
    strategy: StrategyVersionPlan,
    portfolio: PortfolioPolicyPlan,
    risk: RiskPolicyPlan,
    fit: EvaluationProtocolPlan,
    validation: EvaluationProtocolPlan,
    code: ArtifactBinding,
    config: ArtifactBinding,
    provenance: str,
) -> ExploratoryBacktestRunPlan:
    roles = (
        BacktestSessionRole.FIT_INPUT,
        BacktestSessionRole.PURGE,
        BacktestSessionRole.EVALUATION,
        BacktestSessionRole.EMBARGO,
    )

    def fold(
        ordinal: int,
        purpose: PartitionPurpose,
        protocol: EvaluationProtocolPlan,
        selected: tuple[ArchiveTradingSession, ...],
    ) -> BacktestFoldPlan:
        return BacktestFoldPlan(
            _id(f"fold:{ordinal}"),
            ordinal,
            purpose,
            "XSHG",
            1,
            1,
            protocol.evaluation_protocol_id,
            protocol.content_sha256,
            tuple(
                BacktestFoldSessionPlan(
                    _id(f"fold:{ordinal}:session:{index}"),
                    index,
                    item.session_id.value,
                    item.session_date,
                    role,
                )
                for index, (item, role) in enumerate(
                    zip(selected, roles, strict=True),
                    start=1,
                )
            ),
        )

    return ExploratoryBacktestRunPlan(
        _id("backtest"),
        "wp17p_pilot",
        1,
        archive_id,
        seal_id,
        "A transparent rank baseline and deterministic ridge challenger are compared without parameter search.",
        target.target_definition_id,
        target.version,
        target.content_sha256,
        ((feature.feature_definition_id, feature.content_sha256),),
        candidate.candidate_policy_id,
        candidate.content_sha256,
        context.context_policy_id,
        context.content_sha256,
        strategy.strategy_version_id,
        strategy.content_sha256,
        portfolio.portfolio_policy_id,
        portfolio.content_sha256,
        risk.risk_policy_id,
        risk.content_sha256,
        (
            BacktestArmPlan(_id("arm:baseline"), 1, BacktestArmKind.RULE_BASELINE),
            BacktestArmPlan(_id("arm:model"), 2, BacktestArmKind.MODEL_CHALLENGER),
        ),
        (
            fold(1, PartitionPurpose.FIT, fit, sessions[:4]),
            fold(2, PartitionPurpose.VALIDATION, validation, sessions[4:]),
        ),
        (
            BacktestCostAssumption(
                _id("cost:commission"),
                1,
                BacktestCostKind.COMMISSION_BPS,
                Decimal("3"),
            ),
            BacktestCostAssumption(
                _id("cost:slippage"),
                2,
                BacktestCostKind.SLIPPAGE_BPS,
                Decimal("5"),
            ),
            BacktestCostAssumption(
                _id("cost:stamp-duty"),
                3,
                BacktestCostKind.STAMP_DUTY_BPS,
                Decimal("5"),
            ),
        ),
        1729,
        code,
        config,
        provenance,
    )


def _candidate_artifact(binding: ArtifactBinding) -> CandidateArtifactBinding:
    return CandidateArtifactBinding(
        binding.artifact_id,
        binding.content_sha256,
        binding.size_bytes,
    )


def _decision_artifact(binding: ArtifactBinding) -> DecisionArtifactBinding:
    return DecisionArtifactBinding(
        binding.artifact_id,
        str(binding.content_sha256),
        binding.size_bytes,
    )


def _id(suffix: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"{_CATALOG_KEY}:{suffix}")


__all__ = ["Wp17pAuthorityCatalog", "build_wp17p_authority_catalog"]
