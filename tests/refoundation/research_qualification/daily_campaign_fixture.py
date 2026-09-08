"""Small deterministic Generic baseline, with real canonical owner writes."""

from dataclasses import replace
from datetime import datetime, time
from decimal import Decimal as D
import json
from uuid import uuid4
from zoneinfo import ZoneInfo

from market_regime_alpha.research_qualification.domain import (
    backtest as B,
    evaluation as E,
    evaluation_formula as F,
    research_vocabulary as V,
    research_models as M,
)
from market_regime_alpha.research_qualification.domain.daily_protocol import daily_feature_definition, daily_target_definition
from market_regime_alpha.selection.domain import ExploratoryRetrospectiveSelectionScope, UniverseScopeSpecification, EligibilityRuleKind
from market_regime_alpha.shared.hashing import canonical_json_sha256
from tests.refoundation.research_qualification import _historical_backtest_catalog as C
from tests.refoundation.research_qualification.archive_campaign_fixture import seed_complete_archive, _binding, _context


def daily_baseline(app):
    product, instruments, sessions, code, config, archive_id, seal = seed_complete_archive(app, daily_bars=True)
    ca, cf = _binding(code), _binding(config)
    target = daily_target_definition(uuid4(), ca, cf)
    feature = daily_feature_definition(uuid4(), ca, cf)
    universe = C.UniverseDefinition(uuid4(), "daily_fixture_population", "Complete 32-member synthetic population")
    old = C._eligibility(product.provider_product_id)
    eligibility = replace(
        old,
        eligibility_policy_id=uuid4(),
        policy_code="daily_fixture_eligibility",
        rules=(old.rules[0], replace(old.rules[1], rule_kind=EligibilityRuleKind.LAST_COMPLETED_SESSION_ACTIVE)),
    )
    candidate = replace(C._candidate(feature, ca, cf), requested_top_k=32)
    context = C._context(ca, cf, "d" * 64)
    strategy = C._wp18_observational_strategy(target, context, ca, cf, "d" * 64)
    strategy = replace(strategy, forecast_rules=tuple(replace(r, intercept=D("-.01")) for r in strategy.forecast_rules))
    portfolio = C._portfolio(ca, cf, "d" * 64)
    risk = C._risk(ca, cf, "d" * 64)

    def protocol(purpose):
        pid = uuid4()
        metrics = []
        recipes = (
            (("label_mean", "OUTCOME_METRIC", "TARGET_VALUE", "MEAN"),)
            if purpose is V.PartitionPurpose.FIT
            else (
                ("coverage", "FORECAST_OUTCOME_PAIR", "FORECAST_POINT_VS_TARGET", "COVERAGE_RATE"),
                ("bias", "FORECAST_OUTCOME_PAIR", "FORECAST_POINT_VS_TARGET", "PREDICTIVE_BIAS"),
                ("mae", "FORECAST_OUTCOME_PAIR", "FORECAST_POINT_VS_TARGET", "PREDICTIVE_MAE"),
                ("rmse", "FORECAST_OUTCOME_PAIR", "FORECAST_POINT_VS_TARGET", "PREDICTIVE_RMSE"),
                ("rank_ic", "FORECAST_OUTCOME_PAIR", "FORECAST_POINT_VS_TARGET", "RANK_IC"),
            )
        )
        for ordinal, (name, source, measure, formula) in enumerate(recipes, 1):
            mid = uuid4()
            params = (
                (F.EvaluationFormulaParameter(uuid4(), 1, "expected_roster_size", F.FormulaParameterType.INTEGER, integer_value=32),)
                if formula == "COVERAGE_RATE"
                else ()
            )
            definition = F.EvaluationFormulaDefinition(
                mid, F.BacktestFormulaCode[formula], 1, 38, "ROUND_HALF_EVEN", params, F.BacktestMetricSurface.SIGNAL_FORECAST
            )
            metrics.append(
                E.ProtocolMetricDefinition(
                    mid,
                    name,
                    ordinal,
                    target.metrics[0].target_metric_definition_id,
                    target.metrics[0].metric_code,
                    V.SourceMetricValueType.DECIMAL,
                    V.EvaluationReducer.MEAN_DECIMAL,
                    V.EvaluationSliceKind.ALL_MEMBERS,
                    None,
                    V.MetricDirection.DESCRIPTIVE,
                    1,
                    V.AcceptanceOperator.NONE,
                    None,
                    source_kind=V.EvaluationSourceKind[source],
                    source_measure=V.EvaluationSourceMeasure[measure],
                    formula=definition,
                )
            )
        return E.EvaluationProtocolPlan(
            pid,
            "daily_fixture_" + purpose.value.lower(),
            1,
            target.target_definition_id,
            1,
            target.content_sha256,
            purpose,
            "SYNTHETIC_DESCRIPTIVE_ONLY",
            tuple(metrics),
            ca,
            cf,
            "d" * 64,
        )

    fit, validation = protocol(V.PartitionPurpose.FIT), protocol(V.PartitionPurpose.VALIDATION)
    for i, (command, value) in enumerate(
        (
            (app.research_definitions.register_target_definition, target),
            (app.research_definitions.register_feature_definition, feature),
            (app.selection.register_universe, universe),
            (app.selection.register_eligibility_policy, eligibility),
            (app.candidates.register_candidate_policy, candidate),
            (app.decision_contexts.register_policy, context),
            (app.decision_strategies.register, strategy),
            (app.decision_portfolios.register_policy, portfolio),
            (app.decision_risk.register_policy, risk),
            (app.research_evaluations.register_protocol, fit),
            (app.research_evaluations.register_protocol, validation),
        )
    ):
        command(value, _context("daily-definition:" + str(i)))
    scope_bytes = json.dumps(
        {
            "schema": "selection-universe-scope-v1",
            "classification_code": "CSI300",
            "classification_scheme": "INDEX_MEMBERSHIP",
            "instrument_ids": sorted(str(i) for i in instruments),
            "market_provider_product_id": str(product.provider_product_id),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    scope_artifact = app.artifacts.publish(scope_bytes, media_type="application/json", context=_context("daily-scope"))
    scope = UniverseScopeSpecification(
        scope_artifact.artifact_id,
        scope_artifact.content_sha256,
        scope_artifact.size_bytes,
        product.provider_product_id,
        "INDEX_MEMBERSHIP",
        "CSI300",
        tuple(sorted(instruments, key=str)),
    )
    inspection = app.archive_inspection.inspect(archive_id)
    frozen = app.selection.freeze_exploratory_retrospective_universe(
        universe_id=universe.universe_id,
        scope=scope,
        retrospective_scope=ExploratoryRetrospectiveSelectionScope(
            archive_id,
            seal.market_archive_seal_id,
            inspection.sealed_at,
            datetime.combine(sessions[1].session_date, time(15), ZoneInfo("Asia/Shanghai")),
        ),
        context=_context("daily-universe"),
    )

    def binding(identity, digest):
        return B.AuthorityBinding(identity, str(digest))

    with app._pool.connection(read_only=True) as c:
        ah = c.execute("SELECT content_sha256 FROM mra.market_archive WHERE market_archive_id=%s", (archive_id,)).fetchone()[0]
        sh = c.execute(
            "SELECT content_sha256 FROM mra.market_archive_seal WHERE market_archive_seal_id=%s", (seal.market_archive_seal_id,)
        ).fetchone()[0]
    defaults = B.BacktestPolicyDefaults(
        binding(candidate.candidate_policy_id, candidate.content_sha256),
        binding(context.context_policy_id, context.content_sha256),
        binding(strategy.strategy_version_id, strategy.content_sha256),
        binding(portfolio.portfolio_policy_id, portfolio.content_sha256),
        binding(risk.risk_policy_id, risk.content_sha256),
    )
    cost = B.BacktestCostAssumption(uuid4(), 1, B.BacktestCostKind.COMMISSION_BPS, B.BacktestCostChargeSide.BOTH, D(0))
    cost_hash = canonical_json_sha256(({"assumption_id": cost.assumption_id, "ordinal": 1, "content_sha256": str(cost.content_sha256)},))
    model = M.ResearchModelPlan(
        uuid4(),
        "daily_fixture_ridge",
        target.target_definition_id,
        1,
        target.content_sha256,
        ((feature.feature_definition_id, str(feature.content_sha256)),),
        ca,
        cf,
        "d" * 64,
    )
    app.research_models.register_model(model, _context("daily-model"))
    arms = tuple(
        B.BacktestArmSpecification(
            uuid4(),
            i,
            name,
            kind,
            B.BacktestComparisonRole.BASELINE if i == 1 else B.BacktestComparisonRole.CHALLENGER,
            B.BacktestContextMode.OBSERVATIONAL,
            defaults.candidate,
            defaults.context,
            defaults.strategy,
            None if i == 1 else binding(model.model_id, model.content_sha256),
            defaults.portfolio,
            defaults.risk,
            cost_hash,
        )
        for i, name, kind in ((1, "rule", B.BacktestExecutionKind.RULE), (2, "ridge", B.BacktestExecutionKind.MODEL))
    )
    folds = tuple(
        B.BacktestFoldSpecification(
            uuid4(),
            i,
            purpose,
            "XSHG",
            0,
            0,
            binding(p.evaluation_protocol_id, p.content_sha256),
            (B.BacktestFoldSession(uuid4(), 1, sessions[index].session_id.value, sessions[index].session_date, role),),
        )
        for i, purpose, p, index, role in (
            (1, V.PartitionPurpose.FIT, fit, 1, B.BacktestSessionRole.FIT_INPUT),
            (2, V.PartitionPurpose.VALIDATION, validation, 8, B.BacktestSessionRole.EVALUATION),
        )
    )
    environment = M.ModelExecutionEnvironment(
        "cpython", "3.12.13", "uv", "0.8.15", "1" * 64, (M.ModelDependencyVersion(1, "fixture", "1", str(ca.content_sha256)),)
    )
    recipe = B.BacktestModelTrainingRecipe(
        "deterministic_ridge",
        "1.0.0",
        "2" * 64,
        environment,
        (M.ModelScalarParameter(1, "ridge_alpha", M.ModelScalarType.DECIMAL, decimal_value=D(1)),),
    )
    train = B.BacktestModelTrainingRequirement(
        uuid4(),
        1,
        arms[1].exploratory_backtest_arm_id,
        folds[0].exploratory_backtest_fold_id,
        folds[1].exploratory_backtest_fold_id,
        binding(model.model_id, model.content_sha256),
        binding(fit.metrics[0].evaluation_protocol_metric_id, fit.metrics[0].content_sha256),
        1,
        recipe,
    )
    evaluations = tuple(
        B.BacktestEvaluationRequirement(
            uuid4(), i, f.exploratory_backtest_fold_id, f.evaluation_protocol, True, arm_id=a.exploratory_backtest_arm_id
        )
        for i, (f, a) in enumerate(((f, a) for f in folds for a in arms), 1)
    )
    evaluations += tuple(
        B.BacktestEvaluationRequirement(
            uuid4(),
            len(evaluations) + i,
            None,
            folds[1].evaluation_protocol,
            True,
            scope_kind=B.BacktestEvaluationScopeKind.AGGREGATE,
            arm_id=a.exploratory_backtest_arm_id,
        )
        for i, a in enumerate(arms, 1)
    )
    spec = B.BacktestSpecification(
        uuid4(),
        "daily_fixture_generic",
        1,
        "Synthetic shared-feature temporal integration",
        binding(archive_id, ah),
        binding(seal.market_archive_seal_id, sh),
        binding(frozen.universe_revision_id, scope.content_sha256),
        binding(eligibility.eligibility_policy_id, eligibility.content_sha256),
        "complete-32",
        tuple(
            B.BacktestSampleMember(m.universe_member_id, m.instrument_id.value, i)
            for i, m in enumerate(sorted(frozen.members, key=lambda m: str(m.instrument_id)), 1)
        ),
        "XSHG",
        folds[0].sessions[0].trading_session_id,
        folds[1].sessions[0].trading_session_id,
        (binding(feature.feature_definition_id, feature.content_sha256),),
        B.VersionedAuthorityBinding(target.target_definition_id, 1, target.content_sha256),
        defaults,
        arms,
        folds,
        (B.BacktestFoldDependency(uuid4(), 1, folds[0].exploratory_backtest_fold_id, folds[1].exploratory_backtest_fold_id),),
        tuple(
            B.BacktestArmFold(uuid4(), i, a.exploratory_backtest_arm_id, f.exploratory_backtest_fold_id)
            for i, (f, a) in enumerate(((f, a) for f in folds for a in arms), 1)
        ),
        (train,),
        B.BacktestWalkForwardPolicy("daily_fixture_fixed", 1, B.BacktestWalkForwardMode.FIXED, 1, 1, 1),
        (cost,),
        evaluations,
        18,
        ca,
        cf,
        "d" * 64,
    )
    return spec, dict(
        target=target,
        feature=feature,
        model=model,
        product=product,
        instruments=instruments,
        sessions=sessions,
        universe=universe,
        scope=scope,
        eligibility=eligibility,
        candidate=candidate,
        context=context,
        strategy=strategy,
        code=ca,
        config=cf,
    )
