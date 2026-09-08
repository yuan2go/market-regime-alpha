"""Small canonical Generic fixture; no operational DB or WP execution facade."""

from dataclasses import replace
from datetime import date, datetime, time
from decimal import Decimal as D
import json
from uuid import uuid4
from zoneinfo import ZoneInfo

from tests.contracts.research_qualification import _historical_backtest_catalog as catalog_factory
from market_regime_alpha.research_qualification.domain.backtest import (
    AuthorityBinding,
    BacktestSpecification,
    BacktestSampleMember,
    BacktestPolicyDefaults,
    BacktestArmSpecification,
    BacktestArmFold,
    BacktestFoldSpecification,
    BacktestFoldSession,
    BacktestFoldDependency,
    BacktestCostAssumption,
    BacktestCostKind,
    BacktestCostChargeSide,
    BacktestEvaluationRequirement,
    BacktestEvaluationScopeKind,
    BacktestExecutionKind,
    BacktestComparisonRole,
    BacktestContextMode,
    BacktestWalkForwardPolicy,
    BacktestWalkForwardMode,
    BacktestSessionRole,
    VersionedAuthorityBinding,
)
from market_regime_alpha.research_qualification.domain.evaluation import EvaluationProtocolPlan
from market_regime_alpha.research_qualification.domain.evaluation_formula import (
    BacktestFormulaCode as Code,
    EvaluationFormulaDefinition,
    BacktestMetricSurface,
    EvaluationFormulaParameter,
    FormulaParameterType,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionPurpose,
    EvaluationSliceKind,
    EvaluationSourceKind,
    EvaluationSourceMeasure,
)
from market_regime_alpha.selection.domain import ExploratoryRetrospectiveSelectionScope, UniverseScopeSpecification
from market_regime_alpha.shared.hashing import canonical_json_sha256
from tests.contracts.research_qualification.archive_campaign_fixture import seed_complete_archive, _context, _binding
from tests.contracts.research_qualification.test_episode_formula import formula
from tests.contracts.research_qualification.test_evaluation_source_repository import _metric


def funded_specification(app, monkeypatch, *, multi_episode=False, february_only=False):
    product, instruments, sessions, code, config, archive_id, seal = seed_complete_archive(app, episode_entry=True, multi_episode=multi_episode)
    target_factory = catalog_factory._target
    portfolio_factory = catalog_factory._portfolio
    risk_factory = catalog_factory._risk
    fit_day = date(2026, 1, 26) if multi_episode else date(2026, 1, 5)

    def target(code, config):
        old = target_factory(code, config)
        identity = uuid4()
        checkpoints = tuple(replace(c, target_definition_id=identity, target_checkpoint_id=uuid4()) for c in old.checkpoints)
        entry = replace(
            checkpoints[1], target_checkpoint_id=uuid4(), checkpoint_code="episode_entry_0935", ordinal=3, local_time=time(9, 35)
        )
        metrics = (
            replace(old.metrics[0], target_definition_id=identity, target_metric_definition_id=uuid4()),
            replace(
                old.metrics[0],
                target_definition_id=identity,
                target_metric_definition_id=uuid4(),
                ordinal=2,
                metric_code="entry_reference_return",
            ),
        )
        dependencies = []
        for metric, point in zip(metrics, (checkpoints[1], entry), strict=True):
            for original, checkpoint in zip(old.dependencies, (checkpoints[0], point), strict=True):
                dependencies.append(
                    replace(
                        original,
                        target_definition_id=identity,
                        target_metric_dependency_id=uuid4(),
                        target_metric_definition_id=metric.target_metric_definition_id,
                        target_checkpoint_id=checkpoint.target_checkpoint_id,
                        ordinal=len(dependencies) + 1,
                    )
                )
        return replace(
            old,
            target_definition_id=identity,
            target_code="episode_checkpoint_marks",
            checkpoints=(*checkpoints, entry),
            metrics=metrics,
            dependencies=tuple(dependencies),
        )

    def portfolio(code, config, provenance):
        return replace(
            portfolio_factory(code, config, provenance),
            portfolio_policy_id=uuid4(),
            policy_code="funded_episode_control",
            maximum_gross_weight=D(".8"),
            maximum_net_weight=D(".8"),
            minimum_cash_weight=D(".2"),
        )

    def risk(code, config, provenance):
        from market_regime_alpha.decision_support.domain.risk import RiskSubject
        old = risk_factory(code, config, provenance)
        if not multi_episode:
            return old
        identity = uuid4()
        return replace(old, risk_policy_id=identity, policy_code="episode_fixed_line_cap",
            rules=tuple(replace(rule, risk_rule_id=uuid4(), risk_policy_id=identity,
                decimal_threshold=D(".20") if rule.subject is RiskSubject.SINGLE_LINE_WEIGHT else rule.decimal_threshold)
                for rule in old.rules))

    with monkeypatch.context() as patch:
        patch.setattr(catalog_factory, "_target", target)
        patch.setattr(catalog_factory, "_portfolio", portfolio)
        patch.setattr(catalog_factory, "_risk", risk)
        selected_dates = {
            date(2026, 1, 5),
            date(2026, 1, 6),
            date(2026, 1, 7),
            date(2026, 1, 8),
            date(2026, 1, 12),
            date(2026, 1, 13),
            date(2026, 1, 14),
            date(2026, 1, 15),
        }
        if multi_episode:
            selected_dates = {session.session_date for session in sessions}
        catalog = catalog_factory.build_wp17p_authority_catalog(
            provider_product_id=product.provider_product_id,
            market_archive_id=archive_id,
            market_archive_seal_id=seal.market_archive_seal_id,
            sessions=tuple(
                s
                for s in app.archive_trading_sessions.sessions(
                    exchange="XSHG", start_date=min(selected_dates), end_date=max(selected_dates)
                )
                if s.session_date in selected_dates
            ),
            code_artifact=_binding(code),
            config_artifact=_binding(config),
            provenance_sha256="f" * 64,
        )

    # Current Generic protocols require explicit formulas, including the
    # non-economic FIT/FOLD prerequisites. These are new fixture identities.
    def prerequisite(old):
        metric = _metric(EvaluationSourceKind.OUTCOME_METRIC, EvaluationSourceMeasure.TARGET_VALUE)
        metric = replace(
            metric,
            ordinal=1,
            metric_code="market_return_mean",
            slice_kind=EvaluationSliceKind.ALL_MEMBERS,
            backtest_arm_kind=None,
            source_target_metric_definition_id=catalog.target.metrics[0].target_metric_definition_id,
            source_metric_code="next_session_return",
            formula=EvaluationFormulaDefinition(
                metric.evaluation_protocol_metric_id, Code.MEAN, 1, 34, "ROUND_HALF_EVEN", (), BacktestMetricSurface.DATA
            ),
        )
        return replace(
            old,
            evaluation_protocol_id=uuid4(),
            protocol_code="episode-prerequisite-" + old.applicable_purpose.value.lower(),
            metrics=(metric,),
        )

    catalog = replace(
        catalog,
        fit_evaluation_protocol=prerequisite(catalog.fit_evaluation_protocol),
        validation_evaluation_protocol=prerequisite(catalog.validation_evaluation_protocol),
    )
    registrations = (
        (app.research_definitions.register_target_definition, catalog.target),
        (app.research_definitions.register_feature_definition, catalog.feature),
        (app.selection.register_universe, catalog.universe),
        (app.selection.register_eligibility_policy, catalog.eligibility_policy),
        (app.candidates.register_candidate_policy, catalog.candidate_policy),
        (app.decision_contexts.register_policy, catalog.context_policy),
        (app.decision_strategies.register, catalog.strategy),
        (app.decision_portfolios.register_policy, catalog.portfolio_policy),
        (app.decision_risk.register_policy, catalog.risk_policy),
        (app.research_evaluations.register_protocol, catalog.fit_evaluation_protocol),
        (app.research_evaluations.register_protocol, catalog.validation_evaluation_protocol),
    )
    for ordinal, (command, plan) in enumerate(registrations):
        command(plan, _context("economic-register-" + str(ordinal)))
    archive = app.archive_inspection.inspect(archive_id)
    selection = ExploratoryRetrospectiveSelectionScope(
        archive_id, seal.market_archive_seal_id, archive.sealed_at, datetime.combine(fit_day, time(14, 55), ZoneInfo("Asia/Shanghai"))
    )
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
    scope_artifact = app.artifacts.publish(scope_bytes, media_type="application/json", context=_context("economic-universe-scope"))
    scope = UniverseScopeSpecification(
        scope_artifact.artifact_id,
        scope_artifact.content_sha256,
        scope_artifact.size_bytes,
        product.provider_product_id,
        "INDEX_MEMBERSHIP",
        "CSI300",
        tuple(sorted(instruments, key=str)),
    )
    universe = app.selection.freeze_exploratory_retrospective_universe(
        universe_id=catalog.universe.universe_id, scope=scope, retrospective_scope=selection, context=_context("economic-universe")
    )
    with app._pool.connection(read_only=True) as c:
        archive_hash = c.execute("SELECT content_sha256 FROM mra.market_archive WHERE market_archive_id=%s", (archive_id,)).fetchone()[0]
        seal_hash = c.execute(
            "SELECT content_sha256 FROM mra.market_archive_seal WHERE market_archive_seal_id=%s", (seal.market_archive_seal_id,)
        ).fetchone()[0]
        universe_hash = c.execute(
            "SELECT scope_content_sha256 FROM mra.universe_revision WHERE universe_revision_id=%s", (universe.universe_revision_id,)
        ).fetchone()[0]
    defaults = BacktestPolicyDefaults(
        AuthorityBinding(catalog.candidate_policy.candidate_policy_id, catalog.candidate_policy.content_sha256),
        AuthorityBinding(catalog.context_policy.context_policy_id, catalog.context_policy.content_sha256),
        AuthorityBinding(catalog.strategy.strategy_version_id, catalog.strategy.content_sha256),
        AuthorityBinding(catalog.portfolio_policy.portfolio_policy_id, catalog.portfolio_policy.content_sha256),
        AuthorityBinding(catalog.risk_policy.risk_policy_id, catalog.risk_policy.content_sha256),
    )
    costs = (
        BacktestCostAssumption(uuid4(), 1, BacktestCostKind.COMMISSION_BPS, BacktestCostChargeSide.BOTH, D(3)),
        BacktestCostAssumption(uuid4(), 2, BacktestCostKind.STAMP_DUTY_BPS, BacktestCostChargeSide.SELL, D(5)),
    )
    cost_hash = canonical_json_sha256(
        tuple({"assumption_id": c.assumption_id, "ordinal": c.ordinal, "content_sha256": str(c.content_sha256)} for c in costs)
    )
    arm = BacktestArmSpecification(
        uuid4(),
        1,
        "funded-rule",
        BacktestExecutionKind.RULE,
        BacktestComparisonRole.BASELINE,
        BacktestContextMode.CURRENT_GATE,
        defaults.candidate,
        defaults.context,
        defaults.strategy,
        None,
        defaults.portfolio,
        defaults.risk,
        cost_hash,
    )
    by_date = {s.session_date: s for s in sessions}
    folds = []
    groups = (
        ((fit_day,), PartitionPurpose.FIT, catalog.fit_evaluation_protocol),
        ((date(2026, 1, 14),), PartitionPurpose.VALIDATION, catalog.validation_evaluation_protocol),
    )
    if multi_episode:
        groups = (
            ((fit_day,), PartitionPurpose.FIT, catalog.fit_evaluation_protocol),
            ((date(2026, 1, 28), date(2026, 1, 29)), PartitionPurpose.VALIDATION, catalog.validation_evaluation_protocol),
            ((date(2026, 1, 30), date(2026, 2, 3)), PartitionPurpose.VALIDATION, catalog.validation_evaluation_protocol),
        )
    for ordinal, (days, purpose, protocol) in enumerate(groups, 1):
        folds.append(BacktestFoldSpecification(
            uuid4(), ordinal, purpose, "XSHG", 0, 0,
            AuthorityBinding(protocol.evaluation_protocol_id, protocol.content_sha256),
            tuple(BacktestFoldSession(uuid4(), index, by_date[day].session_id.value, day,
                BacktestSessionRole.FIT_INPUT if purpose is PartitionPurpose.FIT else BacktestSessionRole.EVALUATION)
                for index, day in enumerate(days, 1)),
        ))
    entry = catalog.target.checkpoints[2].target_checkpoint_id
    exit = catalog.target.checkpoints[1].target_checkpoint_id
    metrics = []
    definitions = (("episode-1", Code.NET_RETURN_ASSUMED_COST, None, None), ("episode-2", Code.TURNOVER, None, None))
    if multi_episode:
        definitions = (
            ("all-net", Code.NET_RETURN_ASSUMED_COST, None, None),
            ("all-turnover", Code.TURNOVER, None, None),
            ("fold-a-net", Code.NET_RETURN_ASSUMED_COST, "FOLD", str(folds[1].exploratory_backtest_fold_id)),
            ("fold-b-net", Code.NET_RETURN_ASSUMED_COST, "FOLD", str(folds[2].exploratory_backtest_fold_id)),
            ("january-net", Code.NET_RETURN_ASSUMED_COST, "TIME_MONTH", "2026-01"),
            ("february-net", Code.NET_RETURN_ASSUMED_COST, "TIME_MONTH", "2026-02"),
        )
    if february_only:
        assert multi_episode
        definitions = tuple(item for item in definitions if item[0] == "february-net")
    for ordinal, (name, code_kind, slice_kind, slice_key) in enumerate(definitions, 1):
        metric = _metric(EvaluationSourceKind.PORTFOLIO_OUTCOME, EvaluationSourceMeasure.NET_PORTFOLIO_RETURN_ASSUMED_COST)
        definition = formula(metric.evaluation_protocol_metric_id, code_kind, entry=entry, exit=exit)
        definition = replace(
            definition,
            parameters=tuple(
                replace(p, decimal_value={"buy_fee_bps": D(3), "sell_fee_bps": D(8)}.get(p.parameter_code, p.decimal_value))
                for p in definition.parameters
            ),
        )
        if slice_kind is not None:
            definition = replace(definition, parameters=(*definition.parameters,
                EvaluationFormulaParameter(uuid4(), len(definition.parameters)+1, "episode_slice_kind", FormulaParameterType.TEXT, text_value=slice_kind),
                EvaluationFormulaParameter(uuid4(), len(definition.parameters)+2, "episode_slice_key", FormulaParameterType.TEXT, text_value=slice_key)))
        metrics.append(
            replace(
                metric,
                ordinal=ordinal,
                metric_code=name,
                formula=definition,
                slice_kind=EvaluationSliceKind.ALL_MEMBERS,
                backtest_arm_kind=None,
                source_target_metric_definition_id=catalog.target.metrics[0].target_metric_definition_id,
                source_metric_code="next_session_return",
            )
        )
    protocol = EvaluationProtocolPlan(
        uuid4(),
        "funded_episode_v2",
        2,
        catalog.target.target_definition_id,
        1,
        catalog.target.content_sha256,
        PartitionPurpose.VALIDATION,
        "Complete independent checkpoint-mark episodes",
        tuple(metrics),
        _binding(code),
        _binding(config),
        "d" * 64,
    )
    app.research_evaluations.register_protocol(protocol, _context("economic-protocol"))
    evaluations = tuple(
        BacktestEvaluationRequirement(
            uuid4(), f.ordinal, f.exploratory_backtest_fold_id, f.evaluation_protocol, True, arm_id=arm.exploratory_backtest_arm_id
        )
        for f in folds
    ) + (
        BacktestEvaluationRequirement(
            uuid4(),
            len(folds) + 1,
            None,
            AuthorityBinding(protocol.evaluation_protocol_id, protocol.content_sha256),
            True,
            scope_kind=BacktestEvaluationScopeKind.AGGREGATE,
            arm_id=arm.exploratory_backtest_arm_id,
        ),
    )
    return BacktestSpecification(
        uuid4(),
        "funded-economics-fixture",
        1,
        "Independent hypothetical episode financial correctness",
        AuthorityBinding(archive_id, archive_hash),
        AuthorityBinding(seal.market_archive_seal_id, seal_hash),
        AuthorityBinding(universe.universe_revision_id, universe_hash),
        AuthorityBinding(catalog.eligibility_policy.eligibility_policy_id, catalog.eligibility_policy.content_sha256),
        "deterministic-32",
        tuple(
            BacktestSampleMember(m.universe_member_id, m.instrument_id.value, i)
            for i, m in enumerate(sorted(universe.members, key=lambda m: str(m.instrument_id)), 1)
        ),
        "XSHG",
        folds[0].sessions[0].trading_session_id,
        folds[-1].sessions[-1].trading_session_id,
        (AuthorityBinding(catalog.feature.feature_definition_id, catalog.feature.content_sha256),),
        VersionedAuthorityBinding(catalog.target.target_definition_id, 1, catalog.target.content_sha256),
        defaults,
        (arm,),
        tuple(folds),
        tuple(BacktestFoldDependency(uuid4(), index, folds[0].exploratory_backtest_fold_id, fold.exploratory_backtest_fold_id)
              for index, fold in enumerate(folds[1:], 1)),
        tuple(BacktestArmFold(uuid4(), f.ordinal, arm.exploratory_backtest_arm_id, f.exploratory_backtest_fold_id) for f in folds),
        (),
        BacktestWalkForwardPolicy("fixed-episode", 1, BacktestWalkForwardMode.FIXED, 1, 2 if multi_episode else 1, 1),
        costs,
        evaluations,
        1729,
        _binding(code),
        _binding(config),
        "e" * 64,
    )
