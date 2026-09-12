"""Prepare one finite study for the existing canonical Backtest CLI.

This module declares inputs, never executes a separate research loop. Runtime
progress, recovery, Outcome, Evaluation, reports and replay use mra backtest.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from decimal import Decimal as D
from hashlib import sha256
import json
from pathlib import Path
import platform
from typing import Any
from uuid import UUID, uuid5, NAMESPACE_URL

from market_regime_alpha.bootstrap import TargetApplication
from market_regime_alpha.decision_support.domain.strategy import StrategyPlan, ContextFailureAction
from market_regime_alpha.infrastructure.postgres.queries.historical_study import read_study_dependencies
from market_regime_alpha.interfaces.backtest import encode_backtest_specification
from market_regime_alpha.interfaces.historical_study_definitions import prediction_protocol
from market_regime_alpha.interfaces.historical_study_build import verify_historical_build
from market_regime_alpha.interfaces.historical_feature_definitions import historical_feature_definitions
from market_regime_alpha.research_qualification.domain.historical_features import FACTORS_BY_CODE
from market_regime_alpha.research_qualification.domain.historical_matrix import HistoricalMatrixPlan, HistoricalTimeSplit
from market_regime_alpha.research_qualification.domain import backtest as B, research_models as M, research_vocabulary as V
from market_regime_alpha.research_qualification.domain.daily_protocol import daily_feature_definition, daily_target_definition
from market_regime_alpha.research_qualification.domain.historical_study import HistoricalStudyPlan
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.runtime.application import CommandContext, ActorType
from market_regime_alpha.selection.domain import (
    UniverseDefinition, UniverseScopeSpecification, ExploratoryRetrospectiveSelectionScope,
    EligibilityPolicy, EligibilityRule, EligibilityRuleKind, CriterionValueKind, CriterionOperator,
    CandidatePolicy, CandidatePolicyComponent, CandidateArtifactBinding, CandidateFeatureValueType, DesirabilityDirection,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash, InstrumentId


def _json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False) + "\n").encode()


def _exact(path: Path, content: bytes) -> None:
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError("frozen study output changed; use a new study identity")
    else:
        with path.open("xb") as stream:
            stream.write(content)


def prepare_study(app: TargetApplication, plan: HistoricalStudyPlan, *, wheel: Path,
                  lockfile: Path, source_checkout: Path, code_sha: str, output: Path, actor_id: str,
                  matrix: HistoricalMatrixPlan | None = None, reuse_contracts_from: UUID | None = None) -> dict[str, Any]:
    """Owner declarations and a frozen portable specification, resumable by ID."""
    if not output.is_dir():
        raise ValueError("study output must be an existing persistent directory")
    build = verify_historical_build(wheel=wheel, lockfile=lockfile, source_checkout=source_checkout, code_sha=code_sha)
    if matrix is not None and matrix.baseline!=plan:
        raise ValueError("historical matrix baseline identity mismatch")
    splits = ((HistoricalTimeSplit(plan.fit_dates,plan.purge_dates,plan.embargo_dates,plan.validation_dates),) if matrix is None else matrix.splits)
    evidence = read_study_dependencies(app._pool, plan, () if matrix is None else matrix.additional_splits, None if matrix is None else matrix.step_sessions)
    reused = None
    if reuse_contracts_from is not None:
        from market_regime_alpha.infrastructure.postgres.queries.candidate_research_inputs import load_parser_feature_definitions
        from market_regime_alpha.infrastructure.postgres.repositories.target_definitions import PostgresTargetDefinitionRepository
        from market_regime_alpha.infrastructure.postgres.queries.decision_inference_inputs import _load_strategy
        from market_regime_alpha.infrastructure.postgres.repositories.selection import PostgresSelectionRepository
        from market_regime_alpha.infrastructure.postgres.repositories.candidate import PostgresCandidateRepository
        reused = app.backtest_specifications.load_specification(reuse_contracts_from)
        if matrix is None or reused.market_archive.authority_id != plan.market_archive_id or reused.market_archive_seal.authority_id != plan.market_archive_seal_id:
            raise ValueError("heldout contract reuse requires an expanded matrix over the exact original sealed Archive")
        with app._pool.connection(read_only=True) as connection:
            reused_target = PostgresTargetDefinitionRepository(connection).target_definition(reused.target.authority_id, lock=False)
            reused_features = load_parser_feature_definitions(connection, tuple(f.authority_id for f in reused.feature_definitions))
            reused_strategy = _load_strategy(connection, reused.defaults.strategy.authority_id, lock=False)
            reused_eligibility = PostgresSelectionRepository(connection).load_eligibility_policy(reused.eligibility_policy.authority_id, lock=False)
            reused_candidate = PostgresCandidateRepository(connection).policy(reused.defaults.candidate.authority_id, lock=False)
    frozen = {"schema": "mra-historical-study-freeze-v1" if matrix is None else "mra-historical-matrix-freeze-v1", "plan": asdict(plan if matrix is None else matrix), "code_sha": code_sha,
              "wheel_sha256": build.wheel_sha256, "lockfile_sha256": build.lockfile_sha256,
              "sessions": evidence["sessions"], "target_coverage": evidence["target_coverage"],
              "preprocessing": "FIT_ONLY_ZSCORE_FOR_RIDGE_IDENTITY_FOR_CONTROLS", "ridge_alpha": "1",
              "target": "NEXT_SESSION_OPEN_TO_CLOSE", "primary_selection_metric": "COMMON_VALIDATION_MAE",
              "ordering_metric": "DAILY_RANK_IC", "formal_pit": False, "formal_oos": False,
              "economics": "NOT_ESTIMABLE_NON_TRADABLE_PREDICTION_DIAGNOSTIC"}
    if matrix is not None:
        frozen["ridge_alpha"]="BASELINE_1_EXPANDED_PER_CANDIDATE"
    if reused is not None:
        frozen["reuse_contracts_from"] = {"run_id": reused.exploratory_backtest_run_id, "specification_sha256": str(reused.content_sha256)}
    content = _json(frozen)
    _exact(output / "frozen-study.json", content)
    provenance = sha256(content).hexdigest()
    namespace = uuid5(NAMESPACE_URL, "mra:historical-study:" + plan.study_code)
    def uid(name: str) -> UUID:
        return uuid5(namespace, name)
    def ctx(name: str) -> CommandContext:
        return CommandContext(plan.study_code + ":" + name, ActorType.OPERATOR, actor_id, "EXPLORATORY_HISTORICAL_RESEARCH")
    def artifact(raw: bytes, label: str, media: str = "application/json") -> ArtifactBinding:
        result = app.artifacts.publish(raw, media_type=media, context=ctx(label))
        return ArtifactBinding(result.artifact_id, result.content_sha256, result.size_bytes)
    code = artifact(build.content, "wheel", "application/zip")
    config = artifact(content, "study-config")
    target = replace(daily_target_definition(uid("target"), code, config), target_code=plan.study_code + "_daily_target")
    feature = replace(daily_feature_definition(uid("feature"), code, config), feature_code=plan.study_code + "_session_move")
    expanded_features = () if matrix is None else tuple(replace(f,feature_code=plan.study_code+"_"+f.algorithm_code)
        for f in historical_feature_definitions(uid("historical-features"),code,config))
    if reused is not None:
        target = reused_target
        originals = tuple(f for f in reused_features if f.algorithm_code == "session_open_close_move_v1")
        if len(originals) != 1:
            raise ValueError("reused baseline Feature identity is ambiguous")
        feature = originals[0]
        expanded_features = tuple(f for f in reused_features if f.algorithm_code in FACTORS_BY_CODE)
        if len(expanded_features) != len(FACTORS_BY_CODE):
            raise ValueError("reused expanded Feature roster is incomplete")
    feature_by_name = {FACTORS_BY_CODE[f.algorithm_code].name:f for f in expanded_features}
    features = tuple(sorted((feature,*expanded_features),key=lambda f:str(f.feature_definition_id)))
    universe = UniverseDefinition(uid("universe"), plan.study_code + "_universe", plan.universe_limitation)
    product_id = evidence["archive"]["provider_product_id"]
    eligibility = EligibilityPolicy(uid("eligibility"), product_id, plan.study_code + "_eligible", 1, (
        EligibilityRule(uid("listing"), "MIN_LISTING_AGE", 1, EligibilityRuleKind.MIN_LISTING_AGE,
            "LISTING_AGE", "ELAPSED", 0, "NONE", CriterionValueKind.DECIMAL, CriterionOperator.GTE, "CALENDAR_DAYS", threshold_decimal=D(0)),
        EligibilityRule(uid("active"), "LAST_COMPLETE_ACTIVE", 2, EligibilityRuleKind.LAST_COMPLETED_SESSION_ACTIVE,
            "SECURITY_STATUS", "POINT", 1, "SESSION", CriterionValueKind.STATUS, CriterionOperator.EQ, "STATUS", threshold_status="ACTIVE")))
    def candidate_artifact(binding: ArtifactBinding) -> CandidateArtifactBinding:
        return CandidateArtifactBinding(binding.artifact_id, str(binding.content_sha256), binding.size_bytes)
    candidate = CandidatePolicy(uid("candidate"), plan.study_code + "_rank", 1, candidate_artifact(code), candidate_artifact(config), len(plan.instrument_ids), (
        CandidatePolicyComponent(uid("component"), uid("candidate"), "session_move", 1, feature.feature_definition_id,
            feature.content_sha256, CandidateFeatureValueType.DECIMAL, DesirabilityDirection.HIGHER_IS_BETTER, D(1)),))
    old = evidence["strategy"]
    sid = uid("strategy_version")
    strategy = replace(old, strategy=StrategyPlan(uid("strategy"), plan.study_code + "_rule", "Frozen midrank affine comparator; exploratory predictions only"),
        strategy_version_id=sid, version=1, supersedes_strategy_version_id=None, primary_change="Daily input and next-session intraday Target; fixed original rule coefficients",
        context_requirements=tuple(replace(r, strategy_context_requirement_id=uid("context:" + str(r.ordinal)), strategy_version_id=sid, missing_action=ContextFailureAction.OBSERVE_ONLY) for r in old.context_requirements),
        signal_rule=replace(old.signal_rule, strategy_signal_rule_id=uid("signal"), strategy_version_id=sid),
        forecast_rules=tuple(replace(r, strategy_forecast_rule_id=uid("forecast:" + str(r.ordinal)), strategy_version_id=sid,
            target_definition_id=target.target_definition_id, target_definition_sha256=str(target.content_sha256),
            target_checkpoint_id=target.checkpoints[0].target_checkpoint_id, target_checkpoint_sha256=str(target.checkpoints[0].content_sha256),
            target_metric_definition_id=target.metrics[0].target_metric_definition_id, target_metric_definition_sha256=str(target.metrics[0].content_sha256),
            coefficient=D(".02"), intercept=D("-.01")) for r in old.forecast_rules),
        code_artifact=replace(old.code_artifact, artifact_id=code.artifact_id, content_sha256=str(code.content_sha256), size_bytes=code.size_bytes),
        config_artifact=replace(old.config_artifact, artifact_id=config.artifact_id, content_sha256=str(config.content_sha256), size_bytes=config.size_bytes), provenance_sha256=provenance)
    if reused is not None:
        strategy = reused_strategy
        sid = strategy.strategy_version_id
        eligibility, candidate = reused_eligibility, reused_candidate
    fit = prediction_protocol(uid("fit_protocol"), plan.study_code + "_fit", V.PartitionPurpose.FIT, target, code, config, provenance)
    validation = prediction_protocol(uid("validation_protocol"), plan.study_code + "_validation", V.PartitionPurpose.VALIDATION, target, code, config, provenance)
    if reused is None:
        app.research_definitions.register_target_definition(target, ctx("register:target"))
        for registered in features:
            app.research_definitions.register_feature_definition(registered,ctx("register:feature" if registered is feature else "register:feature:"+registered.algorithm_code))
    app.selection.register_universe(universe, ctx("register:universe"))
    if reused is None:
        app.selection.register_eligibility_policy(eligibility, ctx("register:eligibility"))
        app.candidates.register_candidate_policy(candidate, ctx("register:candidate"))
        app.decision_strategies.register(strategy, ctx("register:strategy"))
        app.research_evaluations.register_protocol(fit, ctx("register:fit_protocol"))
        app.research_evaluations.register_protocol(validation, ctx("register:validation_protocol"))
    scope_content = _json({"schema": "selection-universe-scope-v1", "classification_code": "SURVIVORSHIP_LIMITED_V1", "classification_scheme": "STATIC_RESEARCH_ROSTER",
        "instrument_ids": [str(x) for x in plan.instrument_ids], "market_provider_product_id": str(product_id)}).rstrip(b"\n")
    scope_artifact = artifact(scope_content, "universe_scope")
    scope = UniverseScopeSpecification(scope_artifact.artifact_id, scope_artifact.content_sha256, scope_artifact.size_bytes,
        product_id, "STATIC_RESEARCH_ROSTER", "SURVIVORSHIP_LIMITED_V1", tuple(InstrumentId(x) for x in plan.instrument_ids))
    frozen_universe = app.selection.freeze_exploratory_retrospective_universe(universe_id=universe.universe_id, scope=scope,
        retrospective_scope=ExploratoryRetrospectiveSelectionScope(plan.market_archive_id, plan.market_archive_seal_id,
            evidence["seal"]["knowledge_cutoff"], evidence["sessions"][0]["close_at"]), context=ctx("freeze_universe"))
    def binding(identity: UUID, digest: Any) -> B.AuthorityBinding:
        return B.AuthorityBinding(identity, str(digest))
    previous = evidence["template"]
    defaults = B.BacktestPolicyDefaults(binding(candidate.candidate_policy_id, candidate.content_sha256),
        binding(previous["context_policy_id"], previous["context_policy_sha256"]), binding(sid, strategy.content_sha256),
        binding(previous["portfolio_policy_id"], previous["portfolio_policy_sha256"]), binding(previous["risk_policy_id"], previous["risk_policy_sha256"]))
    if reused is not None:
        defaults = reused.defaults
    cost = B.BacktestCostAssumption(uid("cost"), 1, B.BacktestCostKind.COMMISSION_BPS, B.BacktestCostChargeSide.BOTH, D(0))
    cost_hash = canonical_json_sha256(({"assumption_id": cost.assumption_id, "ordinal": 1, "content_sha256": str(cost.content_sha256)},))
    sessions = {row["session_date"]: row for row in evidence["sessions"]}
    folded: list[B.BacktestFoldSpecification] = []
    for split in splits:
        for purpose,protocol,roster in (
            (V.PartitionPurpose.FIT,fit,tuple((day,B.BacktestSessionRole.FIT_INPUT) for day in split.fit_dates)),
            (V.PartitionPurpose.VALIDATION,validation,tuple((day,B.BacktestSessionRole.PURGE) for day in split.purge_dates)
                +tuple((day,B.BacktestSessionRole.EMBARGO) for day in split.embargo_dates)+tuple((day,B.BacktestSessionRole.EVALUATION) for day in split.validation_dates))):
            i=len(folded)+1
            protocol_binding = (binding(protocol.evaluation_protocol_id,protocol.content_sha256) if reused is None else
                next(f.evaluation_protocol for f in reused.folds if f.purpose is purpose))
            folded.append(B.BacktestFoldSpecification(uid("fold:"+str(i)),i,purpose,evidence["archive"]["exchange_code"],
                0 if purpose is V.PartitionPurpose.FIT else len(split.purge_dates),0 if purpose is V.PartitionPurpose.FIT else len(split.embargo_dates),protocol_binding,
                tuple(B.BacktestFoldSession(uid("session:"+("" if matrix is None else str(i)+":")+str(day)),j,sessions[day]["session_id"],day,role) for j,(day,role) in enumerate(roster,1))))
    folds=tuple(folded)
    environment = M.ModelExecutionEnvironment(platform.python_implementation().lower(), platform.python_version(), "uv", build.package_manager_version,
        ContentHash(str(frozen["lockfile_sha256"])), (M.ModelDependencyVersion(1, "market_regime_alpha", build.version, build.wheel_sha256),))
    arms: list[B.BacktestArmSpecification] = []
    training: list[B.BacktestModelTrainingRequirement] = []
    expanded_candidates = {} if matrix is None else {c.name:c for c in matrix.ridge_candidates}
    candidate_names = (*plan.candidates,*expanded_candidates)
    for ordinal, name in enumerate(candidate_names, 1):
        model_binding = None
        if name != "rule":
            expanded = expanded_candidates.get(name)
            model_features = (feature,) if expanded is None else tuple(feature_by_name[n] for n in expanded.feature_names)
            model = M.ResearchModelPlan(uid("model:" + name), plan.study_code + "_" + name, target.target_definition_id, 1, target.content_sha256,
                tuple((f.feature_definition_id,str(f.content_sha256)) for f in model_features), code, config, provenance)
            app.research_models.register_model(model, ctx("model:" + name))
            model_binding = binding(model.model_id, model.content_sha256)
            ridge = name in {"ridge_v1", "ridge_v2"} or expanded is not None
            parameters = ((M.ModelScalarParameter(1, "ridge_alpha", M.ModelScalarType.DECIMAL, decimal_value=D(1) if expanded is None else expanded.ridge_alpha),) if ridge else
                (M.ModelScalarParameter(1, "baseline_kind", M.ModelScalarType.TEXT, text_value=name.upper()),))
            recipe = B.BacktestModelTrainingRecipe("deterministic_ridge" if ridge else "research_baseline", "2.0.0" if name == "ridge_v2" or expanded is not None else "1.0.0",
                build.ridge_sha256 if ridge else build.baseline_sha256, environment, parameters)
            for split_index in range(len(splits)):
                training.append(B.BacktestModelTrainingRequirement(uid("training:"+name+("" if matrix is None else ":"+str(split_index+1))),len(training)+1,uid("arm:"+name),
                    folds[2*split_index].exploratory_backtest_fold_id,folds[2*split_index+1].exploratory_backtest_fold_id,model_binding,
                    (binding(fit.metrics[0].evaluation_protocol_metric_id,fit.metrics[0].content_sha256) if reused is None else reused.model_training_requirements[0].training_metric),split_index+1,recipe))
        arms.append(B.BacktestArmSpecification(uid("arm:" + name), ordinal, name, B.BacktestExecutionKind.RULE if name == "rule" else B.BacktestExecutionKind.MODEL,
            B.BacktestComparisonRole.BASELINE if name == "rule" else B.BacktestComparisonRole.CHALLENGER, B.BacktestContextMode.OBSERVATIONAL,
            defaults.candidate, defaults.context, defaults.strategy, model_binding, defaults.portfolio, defaults.risk, cost_hash))
    evaluations = [B.BacktestEvaluationRequirement(uid(f"evaluation:{f.ordinal}:{a.ordinal}"), i, f.exploratory_backtest_fold_id,
        f.evaluation_protocol, True, arm_id=a.exploratory_backtest_arm_id)
        for i, (f, a) in enumerate(((f, a) for f in folds for a in arms), 1)]
    for arm in arms:
        evaluations.append(B.BacktestEvaluationRequirement(uid("aggregate:" + str(arm.ordinal)), len(evaluations) + 1, None, folds[1].evaluation_protocol, True,
            scope_kind=B.BacktestEvaluationScopeKind.AGGREGATE, arm_id=arm.exploratory_backtest_arm_id))
    spec = B.BacktestSpecification(uid("backtest"), plan.study_code, 1, "Finite real historical daily baseline comparison; descriptive exploratory evidence only",
        binding(plan.market_archive_id, plan.market_archive_sha256), binding(plan.market_archive_seal_id, plan.market_archive_seal_sha256),
        binding(frozen_universe.universe_revision_id, scope.content_sha256), binding(eligibility.eligibility_policy_id, eligibility.content_sha256), "static_complete_roster",
        tuple(B.BacktestSampleMember(m.universe_member_id, m.instrument_id.value, i) for i, m in enumerate(sorted(frozen_universe.members, key=lambda x: str(x.instrument_id)), 1)),
        evidence["archive"]["exchange_code"], evidence["sessions"][0]["session_id"], evidence["sessions"][-1]["session_id"],
        tuple(binding(f.feature_definition_id,f.content_sha256) for f in features), B.VersionedAuthorityBinding(target.target_definition_id, 1, target.content_sha256),
        defaults, tuple(arms), folds, tuple(B.BacktestFoldDependency(uid("dependency"+("" if matrix is None else ":"+str(i+1))),i+1,
            folds[2*i].exploratory_backtest_fold_id,folds[2*i+1].exploratory_backtest_fold_id) for i in range(len(splits))),
        tuple(B.BacktestArmFold(uid(f"arm_fold:{f.ordinal}:{a.ordinal}"), i, a.exploratory_backtest_arm_id, f.exploratory_backtest_fold_id) for i, (f, a) in enumerate(((f, a) for f in folds for a in arms), 1)),
        tuple(training), B.BacktestWalkForwardPolicy("explicit_calendar_split", 1, B.BacktestWalkForwardMode.FIXED if matrix is None else B.BacktestWalkForwardMode.ROLLING, len(plan.fit_dates), len(plan.validation_dates), len(plan.validation_dates) if matrix is None else matrix.step_sessions),
        (cost,), tuple(evaluations), plan.seed, code, config, provenance,
        specification_schema_version=1 if matrix is None else 2)
    _exact(output / "backtest-specification.json", encode_backtest_specification(spec))
    app.backtests.predeclare(spec, ctx("predeclare"))
    result = {"run_id": spec.exploratory_backtest_run_id, "specification_sha256": spec.content_sha256,
              "study_sha256": provenance, "candidate_count": len(arms), "population_size": len(plan.instrument_ids),
              "execution_entry": "mra backtest run --run-id " + str(spec.exploratory_backtest_run_id),
              "recovery_entry": "mra backtest resume --run-id " + str(spec.exploratory_backtest_run_id), "state": "PREDECLARED_NOT_EXECUTED"}
    _exact(output / "catalog.json", _json(result))
    return result
