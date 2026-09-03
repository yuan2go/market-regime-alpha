"""Read-only reload and hash reconciliation for current Backtests."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
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
    FrozenBacktestRun,
    VersionedAuthorityBinding,
    freeze_backtest_specification,
)
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionPurpose,
)
from market_regime_alpha.research_qualification.domain.research_models import (
    ModelDependencyVersion,
    ModelExecutionEnvironment,
    ModelScalarParameter,
    ModelScalarType,
)
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeNotFoundError,
    RuntimeStateConflictError,
)


class PostgresBacktestQueryPort:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def load(self, exploratory_backtest_run_id: UUID) -> FrozenBacktestRun:
        return freeze_backtest_specification(self.load_specification(exploratory_backtest_run_id))

    def load_specification(
        self,
        exploratory_backtest_run_id: UUID,
    ) -> BacktestSpecification:
        """Reload the exact current relational closure for execution.

        This is an immutable application projection of the canonical rows, not
        an additional Authority or identity.
        """

        with self._pool.connection(read_only=True) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                root = cursor.execute(
                    """
                    SELECT root.*,
                           specification.specification_schema_version,
                           specification.definition_version,
                           specification.specification_sha256,
                           specification.universe_revision_id,
                           specification.universe_scope_sha256,
                           specification.eligibility_policy_id,
                           specification.eligibility_policy_sha256,
                           specification.sample_algorithm_code,
                           specification.sample_algorithm_version,
                           specification.sample_input_key,
                           specification.exchange_code,
                           specification.first_trading_session_id,
                           specification.last_trading_session_id,
                           specification.distinct_trading_session_count,
                           specification.fold_session_binding_count,
                           specification.walk_forward_policy_code,
                           specification.walk_forward_policy_version,
                           specification.walk_forward_mode,
                           specification.minimum_fit_sessions,
                           specification.minimum_validation_sessions,
                           specification.step_sessions,
                           specification.formal_provider_state,
                           specification.formal_pit_state,
                           specification.formal_oos_state,
                           specification.prospective_proven,
                           specification.alpha_proven,
                           archive.content_sha256 AS market_archive_sha256,
                           seal.content_sha256 AS market_archive_seal_sha256
                    FROM mra.exploratory_backtest_run AS root
                    LEFT JOIN mra.backtest_specification AS specification
                      USING (exploratory_backtest_run_id)
                    JOIN mra.market_archive AS archive
                      ON archive.market_archive_id = root.market_archive_id
                    JOIN mra.market_archive_seal AS seal
                      ON seal.market_archive_seal_id = root.market_archive_seal_id
                    WHERE root.exploratory_backtest_run_id = %s
                    """,
                    (exploratory_backtest_run_id,),
                ).fetchone()
                if root is None:
                    raise RuntimeNotFoundError(f"Backtest {exploratory_backtest_run_id} does not exist")
                if root["current_specification_sha256"] is None:
                    raise RuntimeStateConflictError(
                        "current Backtest specification is missing; legacy decoding requires the private exact compatibility seam"
                    )
                sample_rows = cursor.execute(
                    """
                    SELECT * FROM mra.backtest_sample_member
                    WHERE exploratory_backtest_run_id = %s ORDER BY ordinal
                    """,
                    (exploratory_backtest_run_id,),
                ).fetchall()
                feature_rows = cursor.execute(
                    """
                    SELECT * FROM mra.exploratory_backtest_feature
                    WHERE exploratory_backtest_run_id = %s
                    ORDER BY feature_ordinal
                    """,
                    (exploratory_backtest_run_id,),
                ).fetchall()
                arm_rows = cursor.execute(
                    """
                    SELECT arm.ordinal, arm.arm_kind,
                           specification.*
                    FROM mra.exploratory_backtest_arm AS arm
                    JOIN mra.backtest_arm_specification AS specification
                      USING (exploratory_backtest_arm_id,
                             exploratory_backtest_run_id)
                    WHERE arm.exploratory_backtest_run_id = %s
                    ORDER BY arm.ordinal
                    """,
                    (exploratory_backtest_run_id,),
                ).fetchall()
                fold_rows = cursor.execute(
                    """
                    SELECT * FROM mra.exploratory_backtest_fold
                    WHERE exploratory_backtest_run_id = %s ORDER BY ordinal
                    """,
                    (exploratory_backtest_run_id,),
                ).fetchall()
                session_rows = cursor.execute(
                    """
                    SELECT * FROM mra.exploratory_backtest_fold_session
                    WHERE exploratory_backtest_run_id = %s
                    ORDER BY exploratory_backtest_fold_id, ordinal
                    """,
                    (exploratory_backtest_run_id,),
                ).fetchall()
                dependency_rows = cursor.execute(
                    """
                    SELECT * FROM mra.backtest_fold_dependency
                    WHERE exploratory_backtest_run_id = %s ORDER BY ordinal
                    """,
                    (exploratory_backtest_run_id,),
                ).fetchall()
                arm_fold_rows = cursor.execute(
                    """
                    SELECT * FROM mra.backtest_arm_fold
                    WHERE exploratory_backtest_run_id = %s ORDER BY ordinal
                    """,
                    (exploratory_backtest_run_id,),
                ).fetchall()
                model_rows = cursor.execute(
                    """
                    SELECT * FROM mra.backtest_model_training_requirement
                    WHERE exploratory_backtest_run_id = %s ORDER BY ordinal
                    """,
                    (exploratory_backtest_run_id,),
                ).fetchall()
                model_dependency_rows = cursor.execute(
                    """
                    SELECT * FROM mra.backtest_model_training_dependency
                    WHERE exploratory_backtest_run_id = %s
                    ORDER BY backtest_model_training_requirement_id, ordinal
                    """,
                    (exploratory_backtest_run_id,),
                ).fetchall()
                model_hyperparameter_rows = cursor.execute(
                    """
                    SELECT * FROM mra.backtest_model_training_hyperparameter
                    WHERE exploratory_backtest_run_id = %s
                    ORDER BY backtest_model_training_requirement_id, ordinal
                    """,
                    (exploratory_backtest_run_id,),
                ).fetchall()
                cost_rows = cursor.execute(
                    """
                    SELECT * FROM mra.exploratory_backtest_cost_assumption
                    WHERE exploratory_backtest_run_id = %s ORDER BY ordinal
                    """,
                    (exploratory_backtest_run_id,),
                ).fetchall()
                evaluation_rows = cursor.execute(
                    """
                    SELECT * FROM mra.backtest_evaluation_requirement
                    WHERE exploratory_backtest_run_id = %s ORDER BY ordinal
                    """,
                    (exploratory_backtest_run_id,),
                ).fetchall()

        sessions_by_fold: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        for row in session_rows:
            sessions_by_fold[UUID(str(row["exploratory_backtest_fold_id"]))].append(row)
        sample_members = tuple(
            BacktestSampleMember(
                universe_revision_member_id=UUID(str(row["universe_member_id"])),
                instrument_id=UUID(str(row["instrument_id"])),
                ordinal=int(row["ordinal"]),
            )
            for row in sample_rows
        )
        features = tuple(
            AuthorityBinding(
                UUID(str(row["feature_definition_id"])),
                str(row["feature_definition_sha256"]),
            )
            for row in feature_rows
        )
        arms = tuple(self._arm(row) for row in arm_rows)
        folds = tuple(
            self._fold(
                row,
                sessions_by_fold[UUID(str(row["exploratory_backtest_fold_id"]))],
            )
            for row in fold_rows
        )
        dependencies = tuple(
            BacktestFoldDependency(
                dependency_id=UUID(str(row["backtest_fold_dependency_id"])),
                ordinal=int(row["ordinal"]),
                fit_fold_id=UUID(str(row["fit_fold_id"])),
                validation_fold_id=UUID(str(row["validation_fold_id"])),
            )
            for row in dependency_rows
        )
        arm_folds = tuple(
            BacktestArmFold(
                arm_fold_id=UUID(str(row["backtest_arm_fold_id"])),
                ordinal=int(row["ordinal"]),
                arm_id=UUID(str(row["exploratory_backtest_arm_id"])),
                fold_id=UUID(str(row["exploratory_backtest_fold_id"])),
            )
            for row in arm_fold_rows
        )
        model_dependencies_by_requirement: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        for row in model_dependency_rows:
            model_dependencies_by_requirement[UUID(str(row["backtest_model_training_requirement_id"]))].append(row)
        model_hyperparameters_by_requirement: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        for row in model_hyperparameter_rows:
            model_hyperparameters_by_requirement[UUID(str(row["backtest_model_training_requirement_id"]))].append(row)
        model_requirements = tuple(
            BacktestModelTrainingRequirement(
                requirement_id=UUID(str(row["backtest_model_training_requirement_id"])),
                ordinal=int(row["ordinal"]),
                model_arm_id=UUID(str(row["exploratory_backtest_arm_id"])),
                fit_fold_id=UUID(str(row["fit_fold_id"])),
                validation_fold_id=UUID(str(row["validation_fold_id"])),
                model_definition=AuthorityBinding(UUID(str(row["model_id"])), str(row["model_sha256"])),
                training_metric=AuthorityBinding(
                    UUID(str(row["required_fit_evaluation_protocol_metric_id"])),
                    str(row["required_fit_evaluation_metric_sha256"]),
                ),
                planned_model_version=int(row["planned_model_version"]),
                recipe=self._model_training_recipe(
                    row,
                    model_dependencies_by_requirement[UUID(str(row["backtest_model_training_requirement_id"]))],
                    model_hyperparameters_by_requirement[UUID(str(row["backtest_model_training_requirement_id"]))],
                ),
            )
            for row in model_rows
        )
        costs = tuple(
            BacktestCostAssumption(
                assumption_id=UUID(str(row["exploratory_backtest_cost_assumption_id"])),
                ordinal=int(row["ordinal"]),
                cost_kind=BacktestCostKind(str(row["cost_kind"])),
                charge_side=BacktestCostChargeSide(str(row["charge_side"])),
                amount_bps=Decimal(str(row["amount_bps"])),
            )
            for row in cost_rows
        )
        evaluations = [
            BacktestEvaluationRequirement(
                requirement_id=UUID(str(row["backtest_evaluation_requirement_id"])),
                ordinal=int(row["ordinal"]),
                fold_id=(None if row["exploratory_backtest_fold_id"] is None else UUID(str(row["exploratory_backtest_fold_id"]))),
                evaluation_protocol=AuthorityBinding(
                    UUID(str(row["evaluation_protocol_id"])),
                    str(row["evaluation_protocol_sha256"]),
                ),
                primary=bool(row["is_primary"]),
                scope_kind=BacktestEvaluationScopeKind(str(row["scope_kind"])),
                arm_id=UUID(str(row["exploratory_backtest_arm_id"])),
                slice_key=(None if row["slice_key"] is None else str(row["slice_key"])),
            )
            for row in evaluation_rows
        ]
        specification = BacktestSpecification(
            exploratory_backtest_run_id=UUID(str(root["exploratory_backtest_run_id"])),
            run_code=str(root["run_code"]),
            generation=int(root["generation"]),
            hypothesis=str(root["hypothesis"]),
            market_archive=AuthorityBinding(
                UUID(str(root["market_archive_id"])),
                str(root["market_archive_sha256"]),
            ),
            market_archive_seal=AuthorityBinding(
                UUID(str(root["market_archive_seal_id"])),
                str(root["market_archive_seal_sha256"]),
            ),
            universe_revision=AuthorityBinding(
                UUID(str(root["universe_revision_id"])),
                str(root["universe_scope_sha256"]),
            ),
            eligibility_policy=AuthorityBinding(
                UUID(str(root["eligibility_policy_id"])),
                str(root["eligibility_policy_sha256"]),
            ),
            sample_scope_code=str(root["sample_algorithm_code"]),
            sample_members=sample_members,
            exchange_code=str(root["exchange_code"]),
            first_trading_session_id=UUID(str(root["first_trading_session_id"])),
            last_trading_session_id=UUID(str(root["last_trading_session_id"])),
            feature_definitions=features,
            target=VersionedAuthorityBinding(
                UUID(str(root["target_definition_id"])),
                int(root["target_version"]),
                str(root["target_definition_sha256"]),
            ),
            defaults=BacktestPolicyDefaults(
                candidate=_binding(root, "candidate_policy"),
                context=_binding(root, "context_policy"),
                strategy=_binding(root, "strategy_version"),
                portfolio=_binding(root, "portfolio_policy"),
                risk=_binding(root, "risk_policy"),
            ),
            arms=arms,
            folds=folds,
            fold_dependencies=dependencies,
            arm_folds=arm_folds,
            model_training_requirements=model_requirements,
            walk_forward_policy=BacktestWalkForwardPolicy(
                policy_code=str(root["walk_forward_policy_code"]),
                policy_version=int(root["walk_forward_policy_version"]),
                mode=BacktestWalkForwardMode(str(root["walk_forward_mode"])),
                minimum_fit_sessions=int(root["minimum_fit_sessions"]),
                validation_sessions=int(root["minimum_validation_sessions"]),
                step_sessions=int(root["step_sessions"]),
            ),
            cost_assumptions=costs,
            evaluation_requirements=tuple(evaluations),
            random_seed=int(root["random_seed"]),
            code_artifact=ArtifactBinding(
                UUID(str(root["code_artifact_id"])),
                str(root["code_content_sha256"]),
                int(root["code_size_bytes"]),
            ),
            config_artifact=ArtifactBinding(
                UUID(str(root["config_artifact_id"])),
                str(root["config_content_sha256"]),
                int(root["config_size_bytes"]),
            ),
            provenance_sha256=str(root["provenance_sha256"]),
            sample_algorithm_version=int(root["sample_algorithm_version"]),
            sample_input_key=str(root["sample_input_key"]),
        )
        if str(specification.content_sha256) != str(root["current_specification_sha256"]) or str(specification.definition_sha256) != str(
            root["definition_sha256"]
        ):
            raise ArtifactIntegrityError("reloaded Backtest differs from canonical specification hashes")
        return specification

    @staticmethod
    def _model_training_recipe(
        row: dict[str, Any],
        dependency_rows: list[dict[str, Any]],
        hyperparameter_rows: list[dict[str, Any]],
    ) -> BacktestModelTrainingRecipe:
        environment = ModelExecutionEnvironment(
            python_implementation=str(row["python_implementation"]),
            python_version=str(row["python_version"]),
            runtime_code=str(row["runtime_code"]),
            runtime_version=str(row["runtime_version"]),
            uv_lock_sha256=str(row["uv_lock_sha256"]),
            dependencies=tuple(
                ModelDependencyVersion(
                    ordinal=int(item["ordinal"]),
                    package_name=str(item["package_name"]),
                    package_version=str(item["package_version"]),
                    distribution_sha256=str(item["distribution_sha256"]),
                )
                for item in dependency_rows
            ),
        )
        hyperparameters = tuple(
            ModelScalarParameter(
                ordinal=int(item["ordinal"]),
                parameter_code=str(item["parameter_code"]),
                value_type=ModelScalarType(str(item["value_type"])),
                decimal_value=(None if item["decimal_value"] is None else Decimal(str(item["decimal_value"]))),
                integer_value=(None if item["integer_value"] is None else int(item["integer_value"])),
                boolean_value=(None if item["boolean_value"] is None else bool(item["boolean_value"])),
                text_value=(None if item["text_value"] is None else str(item["text_value"])),
            )
            for item in hyperparameter_rows
        )
        recipe = BacktestModelTrainingRecipe(
            algorithm_code=str(row["algorithm_code"]),
            algorithm_version=str(row["algorithm_version"]),
            implementation_sha256=str(row["implementation_sha256"]),
            environment=environment,
            hyperparameters=hyperparameters,
        )
        if (
            str(environment.dependency_roster_sha256) != str(row["dependency_roster_sha256"])
            or str(environment.content_sha256) != str(row["environment_sha256"])
            or str(recipe.hyperparameter_roster_sha256) != str(row["hyperparameter_roster_sha256"])
            or str(recipe.content_sha256) != str(row["recipe_sha256"])
        ):
            raise ArtifactIntegrityError("reloaded Backtest Model recipe differs from canonical hashes")
        return recipe

    @staticmethod
    def _arm(row: dict[str, Any]) -> BacktestArmSpecification:
        model = None if row["model_id"] is None else AuthorityBinding(UUID(str(row["model_id"])), str(row["model_sha256"]))
        arm = BacktestArmSpecification(
            exploratory_backtest_arm_id=UUID(str(row["exploratory_backtest_arm_id"])),
            ordinal=int(row["ordinal"]),
            arm_code=str(row["arm_kind"]),
            execution_kind=BacktestExecutionKind(str(row["execution_kind"])),
            comparison_role=BacktestComparisonRole(str(row["comparison_role"])),
            context_mode=BacktestContextMode(str(row["context_mode"])),
            candidate=_binding(row, "candidate_policy"),
            context=_binding(row, "context_policy"),
            strategy=_binding(row, "strategy_version"),
            model=model,
            portfolio=_binding(row, "portfolio_policy"),
            risk=_binding(row, "risk_policy"),
            effective_cost_roster_sha256=str(row["effective_cost_roster_sha256"]),
            candidate_binding_source=BacktestBindingSource(str(row["candidate_binding_source"])),
            context_binding_source=BacktestBindingSource(str(row["context_binding_source"])),
            strategy_binding_source=BacktestBindingSource(str(row["strategy_binding_source"])),
            portfolio_binding_source=BacktestBindingSource(str(row["portfolio_binding_source"])),
            risk_binding_source=BacktestBindingSource(str(row["risk_binding_source"])),
            cost_binding_source=BacktestBindingSource(str(row["cost_binding_source"])),
        )
        if str(arm.content_sha256) != str(row["content_sha256"]):
            raise ArtifactIntegrityError("Backtest Arm hash mismatch")
        return arm

    @staticmethod
    def _fold(
        row: dict[str, Any],
        session_rows: list[dict[str, Any]],
    ) -> BacktestFoldSpecification:
        sessions = tuple(
            BacktestFoldSession(
                exploratory_backtest_fold_session_id=UUID(str(item["exploratory_backtest_fold_session_id"])),
                ordinal=int(item["ordinal"]),
                trading_session_id=UUID(str(item["trading_session_id"])),
                session_date=item["session_date"],
                role=BacktestSessionRole(str(item["session_role"])),
            )
            for item in session_rows
        )
        fold = BacktestFoldSpecification(
            exploratory_backtest_fold_id=UUID(str(row["exploratory_backtest_fold_id"])),
            ordinal=int(row["ordinal"]),
            purpose=PartitionPurpose(str(row["purpose"])),
            exchange_code=str(row["exchange_code"]),
            purge_sessions=int(row["purge_sessions"]),
            embargo_sessions=int(row["embargo_sessions"]),
            evaluation_protocol=AuthorityBinding(
                UUID(str(row["evaluation_protocol_id"])),
                str(row["evaluation_protocol_sha256"]),
            ),
            sessions=sessions,
        )
        if str(fold.content_sha256) != str(row["content_sha256"]):
            raise ArtifactIntegrityError("Backtest Fold hash mismatch")
        return fold


def _binding(row: dict[str, Any], prefix: str) -> AuthorityBinding:
    return AuthorityBinding(UUID(str(row[f"{prefix}_id"])), str(row[f"{prefix}_sha256"]))


__all__ = ["PostgresBacktestQueryPort"]
