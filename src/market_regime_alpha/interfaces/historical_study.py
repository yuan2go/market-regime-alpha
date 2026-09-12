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
import subprocess
from typing import Any
from uuid import UUID, uuid5, NAMESPACE_URL
from zipfile import ZipFile

from market_regime_alpha.bootstrap import TargetApplication
from market_regime_alpha.decision_support.domain.strategy import StrategyPlan, ContextFailureAction
from market_regime_alpha.infrastructure.postgres.queries.historical_study import read_study_dependencies
from market_regime_alpha.interfaces.backtest import encode_backtest_specification
from market_regime_alpha.interfaces.historical_study_definitions import prediction_protocol
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
                  lockfile: Path, code_sha: str, output: Path, actor_id: str) -> dict[str, Any]:
    """Owner declarations and a frozen portable specification, resumable by ID."""
    if len(code_sha) != 40 or any(c not in "0123456789abcdef" for c in code_sha):
        raise ValueError("study requires a full implementation Git SHA")
    if not output.is_dir():
        raise ValueError("study output must be an existing persistent directory")
    evidence = read_study_dependencies(app._pool, plan)
    # Expensive reads and wheel validation precede every declaration transaction.
    wheel_content = wheel.read_bytes()
    wheel_hash = sha256(wheel_content).hexdigest()
    with ZipFile(wheel) as archive:
        package_root = Path(__file__).resolve().parents[1]
        for name in archive.namelist():
            if name.startswith("market_regime_alpha/") and name.endswith((".py", ".sql")):
                local = package_root / name.removeprefix("market_regime_alpha/")
                if not local.is_file() or local.read_bytes() != archive.read(name):
                    raise ValueError("study wheel differs from the executing source installation")
        ridge_hash = sha256(archive.read("market_regime_alpha/research_qualification/application/deterministic_linear.py")).hexdigest()
        baseline_hash = sha256(archive.read("market_regime_alpha/infrastructure/models/research_baselines.py")).hexdigest()
        metadata_names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(metadata_names) != 1:
            raise ValueError("study wheel metadata is ambiguous")
        version = next(line.removeprefix("Version: ") for line in archive.read(metadata_names[0]).decode().splitlines() if line.startswith("Version: "))
    frozen = {"schema": "mra-historical-study-freeze-v1", "plan": asdict(plan), "code_sha": code_sha,
              "wheel_sha256": wheel_hash, "lockfile_sha256": sha256(lockfile.read_bytes()).hexdigest(),
              "sessions": evidence["sessions"], "target_coverage": evidence["target_coverage"],
              "preprocessing": "FIT_ONLY_ZSCORE_FOR_RIDGE_IDENTITY_FOR_CONTROLS", "ridge_alpha": "1",
              "target": "NEXT_SESSION_OPEN_TO_CLOSE", "primary_selection_metric": "COMMON_VALIDATION_MAE",
              "ordering_metric": "DAILY_RANK_IC", "formal_pit": False, "formal_oos": False,
              "economics": "NOT_ESTIMABLE_NON_TRADABLE_PREDICTION_DIAGNOSTIC"}
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
    code = artifact(wheel_content, "wheel", "application/zip")
    config = artifact(content, "study-config")
    target = replace(daily_target_definition(uid("target"), code, config), target_code=plan.study_code + "_daily_target")
    feature = replace(daily_feature_definition(uid("feature"), code, config), feature_code=plan.study_code + "_session_move")
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
    fit = prediction_protocol(uid("fit_protocol"), plan.study_code + "_fit", V.PartitionPurpose.FIT, target, code, config, provenance)
    validation = prediction_protocol(uid("validation_protocol"), plan.study_code + "_validation", V.PartitionPurpose.VALIDATION, target, code, config, provenance)
    app.research_definitions.register_target_definition(target, ctx("register:target"))
    app.research_definitions.register_feature_definition(feature, ctx("register:feature"))
    app.selection.register_universe(universe, ctx("register:universe"))
    app.selection.register_eligibility_policy(eligibility, ctx("register:eligibility"))
    app.candidates.register_candidate_policy(candidate, ctx("register:candidate"))
    app.decision_strategies.register(strategy, ctx("register:strategy"))
    app.research_evaluations.register_protocol(fit, ctx("register:fit_protocol"))
    app.research_evaluations.register_protocol(validation, ctx("register:validation_protocol"))
    scope_content = _json({"schema": "selection-universe-scope-v1", "classification_code": "CSI300", "classification_scheme": "INDEX_MEMBERSHIP",
        "instrument_ids": [str(x) for x in plan.instrument_ids], "market_provider_product_id": str(product_id)}).rstrip(b"\n")
    scope_artifact = artifact(scope_content, "universe_scope")
    scope = UniverseScopeSpecification(scope_artifact.artifact_id, scope_artifact.content_sha256, scope_artifact.size_bytes,
        product_id, "INDEX_MEMBERSHIP", "CSI300", tuple(InstrumentId(x) for x in plan.instrument_ids))
    frozen_universe = app.selection.freeze_exploratory_retrospective_universe(universe_id=universe.universe_id, scope=scope,
        retrospective_scope=ExploratoryRetrospectiveSelectionScope(plan.market_archive_id, plan.market_archive_seal_id,
            evidence["seal"]["knowledge_cutoff"], evidence["sessions"][0]["close_at"]), context=ctx("freeze_universe"))
    def binding(identity: UUID, digest: Any) -> B.AuthorityBinding:
        return B.AuthorityBinding(identity, str(digest))
    previous = evidence["template"]
    defaults = B.BacktestPolicyDefaults(binding(candidate.candidate_policy_id, candidate.content_sha256),
        binding(previous["context_policy_id"], previous["context_policy_sha256"]), binding(sid, strategy.content_sha256),
        binding(previous["portfolio_policy_id"], previous["portfolio_policy_sha256"]), binding(previous["risk_policy_id"], previous["risk_policy_sha256"]))
    cost = B.BacktestCostAssumption(uid("cost"), 1, B.BacktestCostKind.COMMISSION_BPS, B.BacktestCostChargeSide.BOTH, D(0))
    cost_hash = canonical_json_sha256(({"assumption_id": cost.assumption_id, "ordinal": 1, "content_sha256": str(cost.content_sha256)},))
    sessions = {row["session_date"]: row for row in evidence["sessions"]}
    folds = tuple(B.BacktestFoldSpecification(uid("fold:" + str(i)), i, purpose, evidence["archive"]["exchange_code"],
        0 if i == 1 else len(plan.purge_dates), 0 if i == 1 else len(plan.embargo_dates), binding(p.evaluation_protocol_id, p.content_sha256),
        tuple(B.BacktestFoldSession(uid("session:" + str(day)), j, sessions[day]["session_id"], day, role) for j, (day, role) in enumerate(roster, 1)))
        for i, purpose, p, roster in (
            (1, V.PartitionPurpose.FIT, fit, tuple((day, B.BacktestSessionRole.FIT_INPUT) for day in plan.fit_dates)),
            (2, V.PartitionPurpose.VALIDATION, validation,
                tuple((day, B.BacktestSessionRole.PURGE) for day in plan.purge_dates) + tuple((day, B.BacktestSessionRole.EMBARGO) for day in plan.embargo_dates)
                + tuple((day, B.BacktestSessionRole.EVALUATION) for day in plan.validation_dates))))
    environment = M.ModelExecutionEnvironment(platform.python_implementation().lower(), platform.python_version(), "uv", subprocess.check_output(["uv", "--version"], text=True).split()[1],
        ContentHash(str(frozen["lockfile_sha256"])), (M.ModelDependencyVersion(1, "market_regime_alpha", version, wheel_hash),))
    arms: list[B.BacktestArmSpecification] = []
    training: list[B.BacktestModelTrainingRequirement] = []
    for ordinal, name in enumerate(plan.candidates, 1):
        model_binding = None
        if name != "rule":
            model = M.ResearchModelPlan(uid("model:" + name), plan.study_code + "_" + name, target.target_definition_id, 1, target.content_sha256,
                ((feature.feature_definition_id, str(feature.content_sha256)),), code, config, provenance)
            app.research_models.register_model(model, ctx("model:" + name))
            model_binding = binding(model.model_id, model.content_sha256)
            ridge = name in {"ridge_v1", "ridge_v2"}
            parameters = ((M.ModelScalarParameter(1, "ridge_alpha", M.ModelScalarType.DECIMAL, decimal_value=D(1)),) if ridge else
                (M.ModelScalarParameter(1, "baseline_kind", M.ModelScalarType.TEXT, text_value=name.upper()),))
            recipe = B.BacktestModelTrainingRecipe("deterministic_ridge" if ridge else "research_baseline", "2.0.0" if name == "ridge_v2" else "1.0.0",
                ridge_hash if ridge else baseline_hash, environment, parameters)
            training.append(B.BacktestModelTrainingRequirement(uid("training:" + name), len(training) + 1, uid("arm:" + name),
                folds[0].exploratory_backtest_fold_id, folds[1].exploratory_backtest_fold_id, model_binding,
                binding(fit.metrics[0].evaluation_protocol_metric_id, fit.metrics[0].content_sha256), 1, recipe))
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
        (binding(feature.feature_definition_id, feature.content_sha256),), B.VersionedAuthorityBinding(target.target_definition_id, 1, target.content_sha256),
        defaults, tuple(arms), folds, (B.BacktestFoldDependency(uid("dependency"), 1, folds[0].exploratory_backtest_fold_id, folds[1].exploratory_backtest_fold_id),),
        tuple(B.BacktestArmFold(uid(f"arm_fold:{f.ordinal}:{a.ordinal}"), i, a.exploratory_backtest_arm_id, f.exploratory_backtest_fold_id) for i, (f, a) in enumerate(((f, a) for f in folds for a in arms), 1)),
        tuple(training), B.BacktestWalkForwardPolicy("explicit_calendar_split", 1, B.BacktestWalkForwardMode.FIXED, len(plan.fit_dates), len(plan.validation_dates), len(plan.validation_dates)),
        (cost,), tuple(evaluations), plan.seed, code, config, provenance)
    _exact(output / "backtest-specification.json", encode_backtest_specification(spec))
    app.backtests.predeclare(spec, ctx("predeclare"))
    result = {"run_id": spec.exploratory_backtest_run_id, "specification_sha256": spec.content_sha256,
              "study_sha256": provenance, "candidate_count": len(arms), "population_size": len(plan.instrument_ids),
              "execution_entry": "mra backtest run --run-id " + str(spec.exploratory_backtest_run_id),
              "recovery_entry": "mra backtest resume --run-id " + str(spec.exploratory_backtest_run_id), "state": "PREDECLARED_NOT_EXECUTED"}
    _exact(output / "catalog.json", _json(result))
    return result
