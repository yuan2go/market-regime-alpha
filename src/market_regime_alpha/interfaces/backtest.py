"""Controlled operator adapters for the generic Backtest Platform.

JSON is an input convenience only.  Decoding immediately constructs the
typed command and successful predeclaration freezes the relational closure.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from typing import Mapping, Sequence, cast
from uuid import UUID

from market_regime_alpha.research_qualification.domain.backtest import (
    AuthorityBinding,
    BacktestArmFold,
    BacktestArmSpecification,
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
    BacktestModelTrainingRecipe,
    BacktestModelTrainingRequirement,
    BacktestPolicyDefaults,
    BacktestSampleMember,
    BacktestSessionRole,
    BacktestSpecification,
    BacktestWalkForwardMode,
    BacktestWalkForwardPolicy,
    VersionedAuthorityBinding,
)
from market_regime_alpha.research_qualification.domain.model import (
    ArtifactBinding,
)
from market_regime_alpha.research_qualification.domain.research_models import (
    ModelDependencyVersion,
    ModelExecutionEnvironment,
    ModelScalarParameter,
    ModelScalarType,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionPurpose,
)


_SCHEMA = "mra-backtest-specification-input-v1"


def load_backtest_specification(path: Path) -> BacktestSpecification:
    """Decode a strictly typed operator input Artifact from disk."""

    return decode_backtest_specification(path.read_bytes())


def decode_backtest_specification(payload: bytes | str) -> BacktestSpecification:
    try:
        document = json.loads(payload)
        root = _object(document, "Backtest specification")
        if _text(root, "schema") != _SCHEMA:
            raise ValueError(f"Backtest specification schema must be {_SCHEMA}")
        defaults = _object(root["defaults"], "defaults")
        return BacktestSpecification(
            exploratory_backtest_run_id=_uuid(root, "exploratory_backtest_run_id"),
            run_code=_text(root, "run_code"),
            generation=_integer(root, "generation"),
            hypothesis=_text(root, "hypothesis"),
            market_archive=_authority(root["market_archive"], "market_archive"),
            market_archive_seal=_authority(root["market_archive_seal"], "market_archive_seal"),
            universe_revision=_authority(root["universe_revision"], "universe_revision"),
            eligibility_policy=_authority(root["eligibility_policy"], "eligibility_policy"),
            sample_scope_code=_text(root, "sample_scope_code"),
            sample_members=tuple(_sample_member(item) for item in _sequence(root["sample_members"], "sample_members")),
            exchange_code=_text(root, "exchange_code"),
            first_trading_session_id=_uuid(root, "first_trading_session_id"),
            last_trading_session_id=_uuid(root, "last_trading_session_id"),
            feature_definitions=tuple(
                _authority(item, "feature_definition") for item in _sequence(root["feature_definitions"], "feature_definitions")
            ),
            target=_versioned_authority(root["target"], "target"),
            defaults=BacktestPolicyDefaults(
                candidate=_authority(defaults["candidate"], "defaults.candidate"),
                context=_authority(defaults["context"], "defaults.context"),
                strategy=_authority(defaults["strategy"], "defaults.strategy"),
                portfolio=_authority(defaults["portfolio"], "defaults.portfolio"),
                risk=_authority(defaults["risk"], "defaults.risk"),
            ),
            arms=tuple(_arm(item) for item in _sequence(root["arms"], "arms")),
            folds=tuple(_fold(item) for item in _sequence(root["folds"], "folds")),
            fold_dependencies=tuple(_fold_dependency(item) for item in _sequence(root["fold_dependencies"], "fold_dependencies")),
            arm_folds=tuple(_arm_fold(item) for item in _sequence(root["arm_folds"], "arm_folds")),
            model_training_requirements=tuple(
                _model_requirement(item)
                for item in _sequence(
                    root["model_training_requirements"],
                    "model_training_requirements",
                )
            ),
            walk_forward_policy=_walk_forward(root["walk_forward_policy"]),
            cost_assumptions=tuple(_cost(item) for item in _sequence(root["cost_assumptions"], "cost_assumptions")),
            evaluation_requirements=tuple(
                _evaluation_requirement(item)
                for item in _sequence(
                    root["evaluation_requirements"],
                    "evaluation_requirements",
                )
            ),
            random_seed=_integer(root, "random_seed"),
            code_artifact=_artifact(root["code_artifact"], "code_artifact"),
            config_artifact=_artifact(root["config_artifact"], "config_artifact"),
            provenance_sha256=_text(root, "provenance_sha256"),
            sample_algorithm_version=_integer(root, "sample_algorithm_version"),
            sample_input_key=_text(root, "sample_input_key"),
        )
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Backtest specification input has invalid required shape") from exc


def encode_backtest_specification(specification: BacktestSpecification) -> bytes:
    """Render deterministic source fields for operator transport or review."""

    payload: dict[str, object] = {
        "schema": _SCHEMA,
        "exploratory_backtest_run_id": str(specification.exploratory_backtest_run_id),
        "run_code": specification.run_code,
        "generation": specification.generation,
        "hypothesis": specification.hypothesis,
        "market_archive": _authority_payload(specification.market_archive),
        "market_archive_seal": _authority_payload(specification.market_archive_seal),
        "universe_revision": _authority_payload(specification.universe_revision),
        "eligibility_policy": _authority_payload(specification.eligibility_policy),
        "sample_scope_code": specification.sample_scope_code,
        "sample_members": tuple(
            {
                "universe_revision_member_id": str(item.universe_revision_member_id),
                "instrument_id": str(item.instrument_id),
                "ordinal": item.ordinal,
            }
            for item in specification.sample_members
        ),
        "exchange_code": specification.exchange_code,
        "first_trading_session_id": str(specification.first_trading_session_id),
        "last_trading_session_id": str(specification.last_trading_session_id),
        "feature_definitions": tuple(_authority_payload(item) for item in specification.feature_definitions),
        "target": {
            **_authority_payload(specification.target),
            "version": specification.target.version,
        },
        "defaults": {
            "candidate": _authority_payload(specification.defaults.candidate),
            "context": _authority_payload(specification.defaults.context),
            "strategy": _authority_payload(specification.defaults.strategy),
            "portfolio": _authority_payload(specification.defaults.portfolio),
            "risk": _authority_payload(specification.defaults.risk),
        },
        "arms": tuple(_arm_payload(item) for item in specification.arms),
        "folds": tuple(_fold_payload(item) for item in specification.folds),
        "fold_dependencies": tuple(
            {
                "dependency_id": str(item.dependency_id),
                "ordinal": item.ordinal,
                "fit_fold_id": str(item.fit_fold_id),
                "validation_fold_id": str(item.validation_fold_id),
            }
            for item in specification.fold_dependencies
        ),
        "arm_folds": tuple(
            {
                "arm_fold_id": str(item.arm_fold_id),
                "ordinal": item.ordinal,
                "arm_id": str(item.arm_id),
                "fold_id": str(item.fold_id),
            }
            for item in specification.arm_folds
        ),
        "model_training_requirements": tuple(_model_requirement_payload(item) for item in specification.model_training_requirements),
        "walk_forward_policy": {
            "policy_code": specification.walk_forward_policy.policy_code,
            "policy_version": specification.walk_forward_policy.policy_version,
            "mode": specification.walk_forward_policy.mode.value,
            "minimum_fit_sessions": (specification.walk_forward_policy.minimum_fit_sessions),
            "validation_sessions": (specification.walk_forward_policy.validation_sessions),
            "step_sessions": specification.walk_forward_policy.step_sessions,
        },
        "cost_assumptions": tuple(
            {
                "assumption_id": str(item.assumption_id),
                "ordinal": item.ordinal,
                "cost_kind": item.cost_kind.value,
                "charge_side": item.charge_side.value,
                "amount_bps": format(item.amount_bps, "f"),
                "arm_id": None if item.arm_id is None else str(item.arm_id),
            }
            for item in specification.cost_assumptions
        ),
        "evaluation_requirements": tuple(
            {
                "requirement_id": str(item.requirement_id),
                "ordinal": item.ordinal,
                "fold_id": None if item.fold_id is None else str(item.fold_id),
                "evaluation_protocol": _authority_payload(item.evaluation_protocol),
                "primary": item.primary,
                "scope_kind": item.scope_kind.value,
                "arm_id": None if item.arm_id is None else str(item.arm_id),
                "slice_key": item.slice_key,
            }
            for item in specification.evaluation_requirements
        ),
        "random_seed": specification.random_seed,
        "code_artifact": _artifact_payload(specification.code_artifact),
        "config_artifact": _artifact_payload(specification.config_artifact),
        "provenance_sha256": str(specification.provenance_sha256),
        "sample_algorithm_version": specification.sample_algorithm_version,
        "sample_input_key": specification.sample_input_key,
    }
    return (json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def _sample_member(value: object) -> BacktestSampleMember:
    row = _object(value, "sample member")
    return BacktestSampleMember(
        _uuid(row, "universe_revision_member_id"),
        _uuid(row, "instrument_id"),
        _integer(row, "ordinal"),
    )


def _fold(value: object) -> BacktestFoldSpecification:
    row = _object(value, "fold")
    return BacktestFoldSpecification(
        exploratory_backtest_fold_id=_uuid(row, "exploratory_backtest_fold_id"),
        ordinal=_integer(row, "ordinal"),
        purpose=PartitionPurpose(_text(row, "purpose")),
        exchange_code=_text(row, "exchange_code"),
        purge_sessions=_integer(row, "purge_sessions"),
        embargo_sessions=_integer(row, "embargo_sessions"),
        evaluation_protocol=_authority(row["evaluation_protocol"], "evaluation_protocol"),
        sessions=tuple(_fold_session(item) for item in _sequence(row["sessions"], "fold.sessions")),
    )


def _fold_session(value: object) -> BacktestFoldSession:
    row = _object(value, "fold session")
    return BacktestFoldSession(
        exploratory_backtest_fold_session_id=_uuid(row, "exploratory_backtest_fold_session_id"),
        ordinal=_integer(row, "ordinal"),
        trading_session_id=_uuid(row, "trading_session_id"),
        session_date=date.fromisoformat(_text(row, "session_date")),
        role=BacktestSessionRole(_text(row, "role")),
    )


def _fold_dependency(value: object) -> BacktestFoldDependency:
    row = _object(value, "fold dependency")
    return BacktestFoldDependency(
        _uuid(row, "dependency_id"),
        _integer(row, "ordinal"),
        _uuid(row, "fit_fold_id"),
        _uuid(row, "validation_fold_id"),
    )


def _arm_fold(value: object) -> BacktestArmFold:
    row = _object(value, "arm fold")
    return BacktestArmFold(
        _uuid(row, "arm_fold_id"),
        _integer(row, "ordinal"),
        _uuid(row, "arm_id"),
        _uuid(row, "fold_id"),
    )


def _arm(value: object) -> BacktestArmSpecification:
    row = _object(value, "arm")
    model = row["model"]
    return BacktestArmSpecification(
        exploratory_backtest_arm_id=_uuid(row, "exploratory_backtest_arm_id"),
        ordinal=_integer(row, "ordinal"),
        arm_code=_text(row, "arm_code"),
        execution_kind=BacktestExecutionKind(_text(row, "execution_kind")),
        comparison_role=BacktestComparisonRole(_text(row, "comparison_role")),
        context_mode=BacktestContextMode(_text(row, "context_mode")),
        candidate=_authority(row["candidate"], "arm.candidate"),
        context=_authority(row["context"], "arm.context"),
        strategy=_authority(row["strategy"], "arm.strategy"),
        model=None if model is None else _authority(model, "arm.model"),
        portfolio=_authority(row["portfolio"], "arm.portfolio"),
        risk=_authority(row["risk"], "arm.risk"),
        effective_cost_roster_sha256=_text(row, "effective_cost_roster_sha256"),
        candidate_binding_source=BacktestBindingSource(_text(row, "candidate_binding_source")),
        context_binding_source=BacktestBindingSource(_text(row, "context_binding_source")),
        strategy_binding_source=BacktestBindingSource(_text(row, "strategy_binding_source")),
        portfolio_binding_source=BacktestBindingSource(_text(row, "portfolio_binding_source")),
        risk_binding_source=BacktestBindingSource(_text(row, "risk_binding_source")),
        cost_binding_source=BacktestBindingSource(_text(row, "cost_binding_source")),
    )


def _model_requirement(value: object) -> BacktestModelTrainingRequirement:
    row = _object(value, "Model training requirement")
    return BacktestModelTrainingRequirement(
        requirement_id=_uuid(row, "requirement_id"),
        ordinal=_integer(row, "ordinal"),
        model_arm_id=_uuid(row, "model_arm_id"),
        fit_fold_id=_uuid(row, "fit_fold_id"),
        validation_fold_id=_uuid(row, "validation_fold_id"),
        model_definition=_authority(row["model_definition"], "model_definition"),
        training_metric=_authority(row["training_metric"], "training_metric"),
        planned_model_version=_integer(row, "planned_model_version"),
        recipe=_model_recipe(row["recipe"]),
    )


def _model_recipe(value: object) -> BacktestModelTrainingRecipe:
    row = _object(value, "Model training recipe")
    return BacktestModelTrainingRecipe(
        algorithm_code=_text(row, "algorithm_code"),
        algorithm_version=_text(row, "algorithm_version"),
        implementation_sha256=_text(row, "implementation_sha256"),
        environment=_model_environment(row["environment"]),
        hyperparameters=tuple(_model_scalar(item) for item in _sequence(row["hyperparameters"], "hyperparameters")),
    )


def _model_environment(value: object) -> ModelExecutionEnvironment:
    row = _object(value, "Model execution environment")
    return ModelExecutionEnvironment(
        python_implementation=_text(row, "python_implementation"),
        python_version=_text(row, "python_version"),
        runtime_code=_text(row, "runtime_code"),
        runtime_version=_text(row, "runtime_version"),
        uv_lock_sha256=_text(row, "uv_lock_sha256"),
        dependencies=tuple(_model_dependency(item) for item in _sequence(row["dependencies"], "dependencies")),
    )


def _model_dependency(value: object) -> ModelDependencyVersion:
    row = _object(value, "Model dependency")
    return ModelDependencyVersion(
        ordinal=_integer(row, "ordinal"),
        package_name=_text(row, "package_name"),
        package_version=_text(row, "package_version"),
        distribution_sha256=_text(row, "distribution_sha256"),
    )


def _model_scalar(value: object) -> ModelScalarParameter:
    row = _object(value, "Model scalar parameter")
    value_type = ModelScalarType(_text(row, "value_type"))
    scalar = row["value"]
    values: dict[str, object | None] = {
        "decimal_value": None,
        "integer_value": None,
        "boolean_value": None,
        "text_value": None,
    }
    if value_type is ModelScalarType.DECIMAL:
        values["decimal_value"] = Decimal(_scalar_text(scalar, "decimal"))
    elif value_type is ModelScalarType.INTEGER:
        if isinstance(scalar, bool) or not isinstance(scalar, int):
            raise ValueError("integer Model parameter requires an integer")
        values["integer_value"] = scalar
    elif value_type is ModelScalarType.BOOLEAN:
        if not isinstance(scalar, bool):
            raise ValueError("boolean Model parameter requires a boolean")
        values["boolean_value"] = scalar
    else:
        if not isinstance(scalar, str):
            raise ValueError("text Model parameter requires text")
        values["text_value"] = scalar
    return ModelScalarParameter(
        ordinal=_integer(row, "ordinal"),
        parameter_code=_text(row, "parameter_code"),
        value_type=value_type,
        decimal_value=cast(Decimal | None, values["decimal_value"]),
        integer_value=cast(int | None, values["integer_value"]),
        boolean_value=cast(bool | None, values["boolean_value"]),
        text_value=cast(str | None, values["text_value"]),
    )


def _walk_forward(value: object) -> BacktestWalkForwardPolicy:
    row = _object(value, "walk-forward policy")
    return BacktestWalkForwardPolicy(
        policy_code=_text(row, "policy_code"),
        policy_version=_integer(row, "policy_version"),
        mode=BacktestWalkForwardMode(_text(row, "mode")),
        minimum_fit_sessions=_integer(row, "minimum_fit_sessions"),
        validation_sessions=_integer(row, "validation_sessions"),
        step_sessions=_integer(row, "step_sessions"),
    )


def _cost(value: object) -> BacktestCostAssumption:
    row = _object(value, "cost assumption")
    return BacktestCostAssumption(
        assumption_id=_uuid(row, "assumption_id"),
        ordinal=_integer(row, "ordinal"),
        cost_kind=BacktestCostKind(_text(row, "cost_kind")),
        charge_side=BacktestCostChargeSide(_text(row, "charge_side")),
        amount_bps=Decimal(_scalar_text(row["amount_bps"], "amount_bps")),
        arm_id=_optional_uuid(row["arm_id"], "arm_id"),
    )


def _evaluation_requirement(value: object) -> BacktestEvaluationRequirement:
    row = _object(value, "Evaluation requirement")
    return BacktestEvaluationRequirement(
        requirement_id=_uuid(row, "requirement_id"),
        ordinal=_integer(row, "ordinal"),
        fold_id=_optional_uuid(row["fold_id"], "fold_id"),
        evaluation_protocol=_authority(row["evaluation_protocol"], "evaluation_protocol"),
        primary=_boolean(row, "primary"),
        scope_kind=BacktestEvaluationScopeKind(_text(row, "scope_kind")),
        arm_id=_optional_uuid(row["arm_id"], "arm_id"),
        slice_key=_optional_text(row["slice_key"], "slice_key"),
    )


def _authority(value: object, name: str) -> AuthorityBinding:
    row = _object(value, name)
    return AuthorityBinding(_uuid(row, "authority_id"), _text(row, "content_sha256"))


def _versioned_authority(value: object, name: str) -> VersionedAuthorityBinding:
    row = _object(value, name)
    return VersionedAuthorityBinding(
        _uuid(row, "authority_id"),
        _integer(row, "version"),
        _text(row, "content_sha256"),
    )


def _artifact(value: object, name: str) -> ArtifactBinding:
    row = _object(value, name)
    return ArtifactBinding(
        _uuid(row, "artifact_id"),
        _text(row, "content_sha256"),
        _integer(row, "size_bytes"),
    )


def _arm_payload(item: BacktestArmSpecification) -> dict[str, object]:
    return {
        "exploratory_backtest_arm_id": str(item.exploratory_backtest_arm_id),
        "ordinal": item.ordinal,
        "arm_code": item.arm_code,
        "execution_kind": item.execution_kind.value,
        "comparison_role": item.comparison_role.value,
        "context_mode": item.context_mode.value,
        "candidate": _authority_payload(item.candidate),
        "context": _authority_payload(item.context),
        "strategy": _authority_payload(item.strategy),
        "model": None if item.model is None else _authority_payload(item.model),
        "portfolio": _authority_payload(item.portfolio),
        "risk": _authority_payload(item.risk),
        "effective_cost_roster_sha256": str(item.effective_cost_roster_sha256),
        "candidate_binding_source": item.candidate_binding_source.value,
        "context_binding_source": item.context_binding_source.value,
        "strategy_binding_source": item.strategy_binding_source.value,
        "portfolio_binding_source": item.portfolio_binding_source.value,
        "risk_binding_source": item.risk_binding_source.value,
        "cost_binding_source": item.cost_binding_source.value,
    }


def _fold_payload(item: BacktestFoldSpecification) -> dict[str, object]:
    return {
        "exploratory_backtest_fold_id": str(item.exploratory_backtest_fold_id),
        "ordinal": item.ordinal,
        "purpose": item.purpose.value,
        "exchange_code": item.exchange_code,
        "purge_sessions": item.purge_sessions,
        "embargo_sessions": item.embargo_sessions,
        "evaluation_protocol": _authority_payload(item.evaluation_protocol),
        "sessions": tuple(
            {
                "exploratory_backtest_fold_session_id": str(session.exploratory_backtest_fold_session_id),
                "ordinal": session.ordinal,
                "trading_session_id": str(session.trading_session_id),
                "session_date": session.session_date.isoformat(),
                "role": session.role.value,
            }
            for session in item.sessions
        ),
    }


def _model_requirement_payload(
    item: BacktestModelTrainingRequirement,
) -> dict[str, object]:
    if item.training_metric is None or item.planned_model_version is None or item.recipe is None:
        raise ValueError("current Model training requirement is incomplete")
    return {
        "requirement_id": str(item.requirement_id),
        "ordinal": item.ordinal,
        "model_arm_id": str(item.model_arm_id),
        "fit_fold_id": str(item.fit_fold_id),
        "validation_fold_id": str(item.validation_fold_id),
        "model_definition": _authority_payload(item.model_definition),
        "training_metric": _authority_payload(item.training_metric),
        "planned_model_version": item.planned_model_version,
        "recipe": _model_recipe_payload(item.recipe),
    }


def _model_recipe_payload(item: BacktestModelTrainingRecipe) -> dict[str, object]:
    return {
        "algorithm_code": item.algorithm_code,
        "algorithm_version": item.algorithm_version,
        "implementation_sha256": str(item.implementation_sha256),
        "environment": {
            "python_implementation": item.environment.python_implementation,
            "python_version": item.environment.python_version,
            "runtime_code": item.environment.runtime_code,
            "runtime_version": item.environment.runtime_version,
            "uv_lock_sha256": str(item.environment.uv_lock_sha256),
            "dependencies": tuple(
                {
                    "ordinal": dependency.ordinal,
                    "package_name": dependency.package_name,
                    "package_version": dependency.package_version,
                    "distribution_sha256": str(dependency.distribution_sha256),
                }
                for dependency in item.environment.dependencies
            ),
        },
        "hyperparameters": tuple(
            {
                "ordinal": parameter.ordinal,
                "parameter_code": parameter.parameter_code,
                "value_type": parameter.value_type.value,
                "value": _model_scalar_value(parameter),
            }
            for parameter in item.hyperparameters
        ),
    }


def _model_scalar_value(parameter: ModelScalarParameter) -> object:
    if parameter.value_type is ModelScalarType.DECIMAL:
        assert parameter.decimal_value is not None
        return format(parameter.decimal_value, "f")
    if parameter.value_type is ModelScalarType.INTEGER:
        return parameter.integer_value
    if parameter.value_type is ModelScalarType.BOOLEAN:
        return parameter.boolean_value
    return parameter.text_value


def _authority_payload(item: AuthorityBinding | VersionedAuthorityBinding) -> dict[str, object]:
    return {
        "authority_id": str(item.authority_id),
        "content_sha256": str(item.content_sha256),
    }


def _artifact_payload(item: ArtifactBinding) -> dict[str, object]:
    return {
        "artifact_id": str(item.artifact_id),
        "content_sha256": str(item.content_sha256),
        "size_bytes": item.size_bytes,
    }


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be a JSON object")
    return cast(dict[str, object], value)


def _sequence(value: object, name: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a JSON array")
    return cast(list[object], value)


def _text(row: Mapping[str, object], key: str) -> str:
    value = row[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be non-empty text")
    return value


def _optional_text(value: object, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be null or non-empty text")
    return value


def _integer(row: Mapping[str, object], key: str) -> int:
    value = row[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _boolean(row: Mapping[str, object], key: str) -> bool:
    value = row[key]
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _uuid(row: Mapping[str, object], key: str) -> UUID:
    return UUID(_text(row, key))


def _optional_uuid(value: object, name: str) -> UUID | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be null or UUID text")
    return UUID(value)


def _scalar_text(value: object, name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"{name} must be a numeric scalar")
    return str(value)


__all__ = [
    "decode_backtest_specification",
    "encode_backtest_specification",
    "load_backtest_specification",
]
