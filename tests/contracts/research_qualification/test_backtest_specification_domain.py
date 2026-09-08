from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from market_regime_alpha.research_qualification.domain.backtest import (
    AuthorityBinding,
    BacktestArmSpecification,
    BacktestArmFold,
    BacktestBindingSource,
    BacktestComparisonRole,
    BacktestContextMode,
    BacktestCostAssumption,
    BacktestCostChargeSide,
    BacktestCostKind,
    BacktestEvaluationRequirement,
    BacktestEvaluationScopeKind,
    BacktestExecutionKind,
    BacktestFoldDependency,
    BacktestFoldSession,
    BacktestFoldSpecification,
    BacktestModelTrainingRequirement,
    BacktestModelTrainingRecipe,
    BacktestPolicyDefaults,
    BacktestSampleMember,
    BacktestSessionRole,
    BacktestSpecification,
    BacktestWalkForwardMode,
    BacktestWalkForwardPolicy,
    VersionedAuthorityBinding,
)
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.research_models import (
    ModelDependencyVersion,
    ModelExecutionEnvironment,
    ModelScalarParameter,
    ModelScalarType,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionPurpose,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


def _id(value: int) -> UUID:
    return UUID(int=value)


def _binding(value: int) -> AuthorityBinding:
    return AuthorityBinding(_id(value), f"{value:064x}")


def _artifact(value: int) -> ArtifactBinding:
    return ArtifactBinding(_id(value), f"{value:064x}", value)


def _cost(identity: int = 440, amount: str = "3") -> BacktestCostAssumption:
    return BacktestCostAssumption(
        assumption_id=_id(identity),
        ordinal=1,
        cost_kind=BacktestCostKind.COMMISSION_BPS,
        charge_side=BacktestCostChargeSide.BOTH,
        amount_bps=Decimal(amount),
    )


def _cost_hash(cost: BacktestCostAssumption) -> str:
    return canonical_json_sha256(
        (
            {
                "content_sha256": str(cost.content_sha256),
                "assumption_id": cost.assumption_id,
                "ordinal": cost.ordinal,
            },
        )
    )


def _model_recipe() -> BacktestModelTrainingRecipe:
    return BacktestModelTrainingRecipe(
        algorithm_code="deterministic_ridge",
        algorithm_version="1.0.0",
        implementation_sha256="d" * 64,
        environment=ModelExecutionEnvironment(
            python_implementation="cpython",
            python_version="3.12.11",
            runtime_code="uv",
            runtime_version="0.8.13",
            uv_lock_sha256="e" * 64,
            dependencies=(
                ModelDependencyVersion(
                    ordinal=1,
                    package_name="market_regime_alpha",
                    package_version="0.1.0",
                    distribution_sha256="f" * 64,
                ),
            ),
        ),
        hyperparameters=(
            ModelScalarParameter(
                ordinal=1,
                parameter_code="ridge_alpha",
                value_type=ModelScalarType.DECIMAL,
                decimal_value=Decimal("0.01"),
            ),
        ),
    )


def _fold(
    *,
    identity: int,
    ordinal: int,
    purpose: PartitionPurpose,
    sessions: tuple[tuple[int, int, BacktestSessionRole], ...],
) -> BacktestFoldSpecification:
    return BacktestFoldSpecification(
        exploratory_backtest_fold_id=_id(identity),
        ordinal=ordinal,
        purpose=purpose,
        exchange_code="XSHG",
        purge_sessions=sum(role is BacktestSessionRole.PURGE for _, _, role in sessions),
        embargo_sessions=sum(role is BacktestSessionRole.EMBARGO for _, _, role in sessions),
        evaluation_protocol=_binding(identity + 100),
        sessions=tuple(
            BacktestFoldSession(
                exploratory_backtest_fold_session_id=_id(identity * 100 + index),
                ordinal=index,
                trading_session_id=_id(session_id),
                session_date=date(2026, 1, day),
                role=role,
            )
            for index, (session_id, day, role) in enumerate(sessions, start=1)
        ),
    )


def _arm(
    *,
    identity: int,
    ordinal: int,
    code: str,
    execution_kind: BacktestExecutionKind = BacktestExecutionKind.RULE,
    role: BacktestComparisonRole = BacktestComparisonRole.CHALLENGER,
    effective_cost_roster_sha256: str | None = None,
) -> BacktestArmSpecification:
    return BacktestArmSpecification(
        exploratory_backtest_arm_id=_id(identity),
        ordinal=ordinal,
        arm_code=code,
        execution_kind=execution_kind,
        comparison_role=role,
        context_mode=BacktestContextMode.CURRENT_GATE,
        candidate=_binding(432),
        context=_binding(433),
        strategy=_binding(identity + 10),
        model=_binding(identity + 20) if execution_kind is BacktestExecutionKind.MODEL else None,
        portfolio=_binding(40),
        risk=_binding(41),
        effective_cost_roster_sha256=(_cost_hash(_cost()) if effective_cost_roster_sha256 is None else effective_cost_roster_sha256),
        candidate_binding_source=BacktestBindingSource.ARM_OVERRIDE,
        context_binding_source=BacktestBindingSource.ARM_OVERRIDE,
        strategy_binding_source=BacktestBindingSource.ARM_OVERRIDE,
        cost_binding_source=BacktestBindingSource.SHARED_DEFAULT,
    )


def _evaluation_requirements(
    arms: tuple[BacktestArmSpecification, ...],
    folds: tuple[BacktestFoldSpecification, ...],
    arm_folds: tuple[BacktestArmFold, ...],
    *,
    first_identity: int,
) -> tuple[BacktestEvaluationRequirement, ...]:
    fold_by_id = {fold.exploratory_backtest_fold_id: fold for fold in folds}
    requirements: list[BacktestEvaluationRequirement] = []
    for ordinal, participation in enumerate(arm_folds, start=1):
        requirements.append(
            BacktestEvaluationRequirement(
                requirement_id=_id(first_identity + ordinal),
                ordinal=ordinal,
                fold_id=participation.fold_id,
                evaluation_protocol=fold_by_id[participation.fold_id].evaluation_protocol,
                primary=True,
                arm_id=participation.arm_id,
            )
        )
    validation_protocol = next(fold.evaluation_protocol for fold in folds if fold.purpose is PartitionPurpose.VALIDATION)
    for arm in arms:
        ordinal = len(requirements) + 1
        requirements.append(
            BacktestEvaluationRequirement(
                requirement_id=_id(first_identity + ordinal),
                ordinal=ordinal,
                fold_id=None,
                evaluation_protocol=validation_protocol,
                primary=True,
                scope_kind=BacktestEvaluationScopeKind.AGGREGATE,
                arm_id=arm.exploratory_backtest_arm_id,
            )
        )
    return tuple(requirements)


def test_arm_meaning_is_orthogonal_and_not_derived_from_arm_code() -> None:
    diagnostic_model = BacktestArmSpecification(
        exploratory_backtest_arm_id=_id(1),
        ordinal=1,
        arm_code="custom-diagnostic",
        execution_kind=BacktestExecutionKind.MODEL,
        comparison_role=BacktestComparisonRole.DIAGNOSTIC,
        context_mode=BacktestContextMode.OBSERVATIONAL,
        candidate=_binding(6),
        context=_binding(7),
        strategy=_binding(2),
        model=_binding(3),
        portfolio=_binding(4),
        risk=_binding(5),
        effective_cost_roster_sha256="6" * 64,
    )

    assert diagnostic_model.arm_code == "custom-diagnostic"
    assert diagnostic_model.execution_kind is BacktestExecutionKind.MODEL
    assert diagnostic_model.comparison_role is BacktestComparisonRole.DIAGNOSTIC
    assert diagnostic_model.context_mode is BacktestContextMode.OBSERVATIONAL
    assert diagnostic_model.model == _binding(3)
    assert diagnostic_model.content_sha256


def test_context_evaluation_requires_a_typed_canonical_context_slice() -> None:
    valid = BacktestEvaluationRequirement(
        requirement_id=_id(998),
        ordinal=1,
        fold_id=None,
        evaluation_protocol=_binding(999),
        primary=False,
        scope_kind=BacktestEvaluationScopeKind.CONTEXT,
        arm_id=_id(1),
        slice_key="MARKET_REGIME:POSITIVE",
    )

    assert valid.slice_key == "MARKET_REGIME:POSITIVE"
    with pytest.raises(ValueError, match="CONTEXT slice_key"):
        replace(valid, slice_key="invented:bull")


def test_specification_accepts_arbitrary_arms_and_overlapping_rolling_fit_sessions() -> None:
    first_fit = _fold(
        identity=100,
        ordinal=1,
        purpose=PartitionPurpose.FIT,
        sessions=(
            (1001, 2, BacktestSessionRole.FIT_INPUT),
            (1002, 3, BacktestSessionRole.FIT_INPUT),
        ),
    )
    validation = _fold(
        identity=101,
        ordinal=2,
        purpose=PartitionPurpose.VALIDATION,
        sessions=((1003, 4, BacktestSessionRole.EVALUATION),),
    )
    expanding_fit = _fold(
        identity=102,
        ordinal=3,
        purpose=PartitionPurpose.FIT,
        sessions=(
            (1001, 2, BacktestSessionRole.FIT_INPUT),
            (1002, 3, BacktestSessionRole.FIT_INPUT),
            (1003, 4, BacktestSessionRole.FIT_INPUT),
        ),
    )
    later_validation = _fold(
        identity=103,
        ordinal=4,
        purpose=PartitionPurpose.VALIDATION,
        sessions=((1004, 5, BacktestSessionRole.EVALUATION),),
    )
    arms = (
        _arm(
            identity=200,
            ordinal=1,
            code="rule-base",
            role=BacktestComparisonRole.BASELINE,
        ),
        _arm(
            identity=201,
            ordinal=2,
            code="ridge-one",
            execution_kind=BacktestExecutionKind.MODEL,
        ),
        _arm(
            identity=202,
            ordinal=3,
            code="rule-diagnostic",
            role=BacktestComparisonRole.DIAGNOSTIC,
        ),
    )
    dependencies = (
        BacktestFoldDependency(_id(300), 1, first_fit.exploratory_backtest_fold_id, validation.exploratory_backtest_fold_id),
        BacktestFoldDependency(_id(301), 2, expanding_fit.exploratory_backtest_fold_id, later_validation.exploratory_backtest_fold_id),
    )
    arm_folds = tuple(
        BacktestArmFold(
            arm_fold_id=_id(500 + index),
            ordinal=index,
            arm_id=arm.exploratory_backtest_arm_id,
            fold_id=fold.exploratory_backtest_fold_id,
        )
        for index, (fold, arm) in enumerate(
            ((fold, arm) for fold in (first_fit, validation, expanding_fit, later_validation) for arm in arms),
            start=1,
        )
    )
    model_definition = arms[1].model
    assert model_definition is not None
    model_requirements = (
        BacktestModelTrainingRequirement(
            requirement_id=_id(600),
            ordinal=1,
            model_arm_id=arms[1].exploratory_backtest_arm_id,
            fit_fold_id=first_fit.exploratory_backtest_fold_id,
            validation_fold_id=validation.exploratory_backtest_fold_id,
            model_definition=model_definition,
            training_metric=_binding(900),
            planned_model_version=1,
            recipe=_model_recipe(),
        ),
        BacktestModelTrainingRequirement(
            requirement_id=_id(601),
            ordinal=2,
            model_arm_id=arms[1].exploratory_backtest_arm_id,
            fit_fold_id=expanding_fit.exploratory_backtest_fold_id,
            validation_fold_id=later_validation.exploratory_backtest_fold_id,
            model_definition=model_definition,
            training_metric=_binding(901),
            planned_model_version=2,
            recipe=_model_recipe(),
        ),
    )
    specification = BacktestSpecification(
        exploratory_backtest_run_id=_id(400),
        run_code="generic-rolling",
        generation=17,
        hypothesis="Arbitrary ordered arms over expanding chronological folds.",
        market_archive=_binding(401),
        market_archive_seal=_binding(402),
        universe_revision=_binding(403),
        eligibility_policy=_binding(404),
        sample_scope_code="stable-hash-3",
        sample_members=tuple(BacktestSampleMember(_id(410 + index), _id(420 + index), index) for index in range(1, 4)),
        exchange_code="XSHG",
        first_trading_session_id=_id(1001),
        last_trading_session_id=_id(1004),
        feature_definitions=(_binding(430),),
        target=VersionedAuthorityBinding(_id(431), 1, "a" * 64),
        defaults=BacktestPolicyDefaults(
            candidate=_binding(432),
            context=_binding(433),
            strategy=_binding(434),
            portfolio=_binding(40),
            risk=_binding(41),
        ),
        arms=arms,
        folds=(first_fit, validation, expanding_fit, later_validation),
        fold_dependencies=dependencies,
        arm_folds=arm_folds,
        model_training_requirements=model_requirements,
        walk_forward_policy=BacktestWalkForwardPolicy(
            policy_code="expanding-v1",
            policy_version=1,
            mode=BacktestWalkForwardMode.EXPANDING,
            minimum_fit_sessions=2,
            validation_sessions=1,
            step_sessions=1,
        ),
        cost_assumptions=(_cost(),),
        evaluation_requirements=_evaluation_requirements(
            arms,
            (first_fit, validation, expanding_fit, later_validation),
            arm_folds,
            first_identity=1000,
        ),
        random_seed=1729,
        code_artifact=_artifact(460),
        config_artifact=_artifact(461),
        provenance_sha256="b" * 64,
    )

    assert len(specification.arms) == 3
    assert specification.distinct_trading_session_count == 4
    assert specification.fold_session_binding_count == 7
    assert specification.content_sha256
    assert "model_version_id" not in BacktestModelTrainingRequirement.__dataclass_fields__

    override_cost = replace(
        _cost(441, "7.5"),
        ordinal=2,
        arm_id=arms[0].exploratory_backtest_arm_id,
    )
    override_hash = canonical_json_sha256(
        (
            {
                "content_sha256": str(override_cost.content_sha256),
                "assumption_id": override_cost.assumption_id,
                "ordinal": override_cost.ordinal,
            },
        )
    )
    override_arm = replace(
        arms[0],
        cost_binding_source=BacktestBindingSource.ARM_OVERRIDE,
        effective_cost_roster_sha256=override_hash,
    )
    overridden = replace(
        specification,
        arms=(override_arm, *arms[1:]),
        cost_assumptions=(*specification.cost_assumptions, override_cost),
    )
    assert str(overridden.arms[0].effective_cost_roster_sha256) == override_hash
    with pytest.raises(ValueError, match="Cost override differs"):
        replace(specification, arms=(override_arm, *arms[1:]))

    with pytest.raises(ValueError, match="training metric"):
        replace(
            specification,
            model_training_requirements=(
                replace(model_requirements[0], training_metric=None),
                model_requirements[1],
            ),
        )
    with pytest.raises(ValueError, match="training recipe"):
        replace(
            specification,
            model_training_requirements=(
                replace(model_requirements[0], recipe=None),
                model_requirements[1],
            ),
        )
    with pytest.raises(ValueError, match="planned Model version"):
        replace(
            specification,
            model_training_requirements=(
                model_requirements[0],
                replace(model_requirements[1], planned_model_version=1),
            ),
        )

    sparse_bindings = tuple(
        item
        for item in specification.arm_folds
        if not (
            item.arm_id == arms[0].exploratory_backtest_arm_id
            and item.fold_id
            in {
                first_fit.exploratory_backtest_fold_id,
                expanding_fit.exploratory_backtest_fold_id,
            }
        )
    )
    sparse = replace(
        specification,
        arm_folds=tuple(replace(item, ordinal=ordinal) for ordinal, item in enumerate(sparse_bindings, start=1)),
        evaluation_requirements=_evaluation_requirements(
            specification.arms,
            specification.folds,
            tuple(replace(item, ordinal=ordinal) for ordinal, item in enumerate(sparse_bindings, start=1)),
            first_identity=1100,
        ),
    )
    assert len(sparse.arm_folds) == 10

    with pytest.raises(ValueError, match="arm codes must be unique"):
        replace(
            specification,
            arms=(
                arms[0],
                BacktestArmSpecification(
                    exploratory_backtest_arm_id=_id(999),
                    ordinal=2,
                    arm_code=arms[0].arm_code,
                    execution_kind=BacktestExecutionKind.RULE,
                    comparison_role=BacktestComparisonRole.CHALLENGER,
                    context_mode=BacktestContextMode.CURRENT_GATE,
                    candidate=_binding(432),
                    context=_binding(433),
                    strategy=_binding(998),
                    model=None,
                    portfolio=_binding(40),
                    risk=_binding(41),
                    effective_cost_roster_sha256="6" * 64,
                    strategy_binding_source=BacktestBindingSource.ARM_OVERRIDE,
                    cost_binding_source=BacktestBindingSource.ARM_OVERRIDE,
                ),
                arms[2],
            ),
        )


def test_rule_only_specification_requires_no_model_training_requirement() -> None:
    fit = _fold(
        identity=700,
        ordinal=1,
        purpose=PartitionPurpose.FIT,
        sessions=((7001, 6, BacktestSessionRole.FIT_INPUT),),
    )
    validation = _fold(
        identity=701,
        ordinal=2,
        purpose=PartitionPurpose.VALIDATION,
        sessions=((7002, 7, BacktestSessionRole.EVALUATION),),
    )
    arm = _arm(
        identity=702,
        ordinal=1,
        code="rule-only",
        role=BacktestComparisonRole.BASELINE,
        effective_cost_roster_sha256=_cost_hash(_cost(717, "0")),
    )
    specification = BacktestSpecification(
        exploratory_backtest_run_id=_id(703),
        run_code="rule-only",
        generation=99,
        hypothesis="A rule strategy remains valid without a ModelVersion.",
        market_archive=_binding(704),
        market_archive_seal=_binding(705),
        universe_revision=_binding(706),
        eligibility_policy=_binding(7070),
        sample_scope_code="fixed-one",
        sample_members=(BacktestSampleMember(_id(707), _id(708), 1),),
        exchange_code="XSHG",
        first_trading_session_id=_id(7001),
        last_trading_session_id=_id(7002),
        feature_definitions=(_binding(709),),
        target=VersionedAuthorityBinding(_id(710), 1, "a" * 64),
        defaults=BacktestPolicyDefaults(
            candidate=_binding(711),
            context=_binding(712),
            strategy=_binding(713),
            portfolio=_binding(40),
            risk=_binding(41),
        ),
        arms=(arm,),
        folds=(fit, validation),
        fold_dependencies=(
            BacktestFoldDependency(
                _id(714),
                1,
                fit.exploratory_backtest_fold_id,
                validation.exploratory_backtest_fold_id,
            ),
        ),
        arm_folds=(
            BacktestArmFold(
                _id(715),
                1,
                arm.exploratory_backtest_arm_id,
                fit.exploratory_backtest_fold_id,
            ),
            BacktestArmFold(
                _id(716),
                2,
                arm.exploratory_backtest_arm_id,
                validation.exploratory_backtest_fold_id,
            ),
        ),
        model_training_requirements=(),
        walk_forward_policy=BacktestWalkForwardPolicy(
            policy_code="fixed-v1",
            policy_version=1,
            mode=BacktestWalkForwardMode.FIXED,
            minimum_fit_sessions=1,
            validation_sessions=1,
            step_sessions=1,
        ),
        cost_assumptions=(_cost(717, "0"),),
        evaluation_requirements=_evaluation_requirements(
            (arm,),
            (fit, validation),
            (
                BacktestArmFold(
                    _id(715),
                    1,
                    arm.exploratory_backtest_arm_id,
                    fit.exploratory_backtest_fold_id,
                ),
                BacktestArmFold(
                    _id(716),
                    2,
                    arm.exploratory_backtest_arm_id,
                    validation.exploratory_backtest_fold_id,
                ),
            ),
            first_identity=1200,
        ),
        random_seed=1,
        code_artifact=_artifact(720),
        config_artifact=_artifact(721),
        provenance_sha256="b" * 64,
    )

    assert specification.model_training_requirements == ()
    assert specification.model_training_requirement_roster_sha256
