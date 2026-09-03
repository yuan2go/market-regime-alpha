"""PostgreSQL Authority writer for current generic Backtest specifications."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.research_qualification.domain.backtest import (
    BacktestSpecification,
)
from market_regime_alpha.research_qualification.ports.backtest_uow import (
    BacktestSpecificationRecord,
)
from market_regime_alpha.runtime.errors import (
    RuntimeNotFoundError,
    RuntimeStateConflictError,
)


class PostgresBacktestRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_identity(self, run_code: str, generation: int) -> None:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"backtest:{run_code}:{generation}",),
        )

    def predeclare(
        self,
        specification: BacktestSpecification,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> BacktestSpecificationRecord:
        universe_id = self._require_exact_parents(specification)
        run_id = specification.exploratory_backtest_run_id
        specification_hash = str(specification.content_sha256)
        defaults = specification.defaults
        self._connection.execute(
            """
            INSERT INTO mra.exploratory_backtest_run (
                exploratory_backtest_run_id, run_code, generation,
                evidence_lane, market_archive_id, market_archive_seal_id,
                hypothesis, target_definition_id, target_version,
                target_definition_sha256,
                candidate_policy_id, candidate_policy_sha256,
                context_policy_id, context_policy_sha256,
                strategy_version_id, strategy_version_sha256,
                portfolio_policy_id, portfolio_policy_sha256,
                risk_policy_id, risk_policy_sha256,
                feature_count, feature_roster_sha256,
                arm_count, arm_roster_sha256,
                fold_count, fold_roster_sha256, session_count,
                cost_count, cost_roster_sha256, random_seed,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256, config_size_bytes,
                provenance_sha256, current_specification_sha256,
                definition_sha256, request_identity, request_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                run_id,
                specification.run_code,
                specification.generation,
                specification.evidence_lane,
                specification.market_archive.authority_id,
                specification.market_archive_seal.authority_id,
                specification.hypothesis,
                specification.target.authority_id,
                specification.target.version,
                str(specification.target.content_sha256),
                defaults.candidate.authority_id,
                str(defaults.candidate.content_sha256),
                defaults.context.authority_id,
                str(defaults.context.content_sha256),
                defaults.strategy.authority_id,
                str(defaults.strategy.content_sha256),
                defaults.portfolio.authority_id,
                str(defaults.portfolio.content_sha256),
                defaults.risk.authority_id,
                str(defaults.risk.content_sha256),
                len(specification.feature_definitions),
                str(specification.feature_roster_sha256),
                len(specification.arms),
                str(specification.arm_roster_sha256),
                len(specification.folds),
                str(specification.fold_roster_sha256),
                len(specification.cost_assumptions),
                str(specification.cost_roster_sha256),
                specification.random_seed,
                specification.code_artifact.artifact_id,
                str(specification.code_artifact.content_sha256),
                specification.code_artifact.size_bytes,
                specification.config_artifact.artifact_id,
                str(specification.config_artifact.content_sha256),
                specification.config_artifact.size_bytes,
                str(specification.provenance_sha256),
                specification_hash,
                str(specification.definition_sha256),
                request_identity,
                request_sha256,
            ),
        )
        self._connection.execute(
            """
            INSERT INTO mra.backtest_specification (
                exploratory_backtest_run_id, specification_schema_version,
                definition_version, specification_sha256,
                universe_revision_id, universe_id, universe_scope_sha256,
                sample_algorithm_code, sample_algorithm_version,
                sample_input_key, sample_seed,
                sample_member_count, sample_roster_sha256,
                exchange_code, first_trading_session_id,
                last_trading_session_id, distinct_trading_session_count,
                fold_session_binding_count, fold_dependency_count,
                fold_dependency_roster_sha256,
                arm_fold_count, arm_fold_roster_sha256,
                model_training_requirement_count,
                model_training_requirement_roster_sha256,
                walk_forward_policy_code, walk_forward_policy_version,
                walk_forward_mode, minimum_fit_sessions,
                minimum_validation_sessions, step_sessions,
                evaluation_requirement_count,
                evaluation_requirement_roster_sha256,
                retrospective_classification, formal_provider_state,
                formal_pit_state, formal_oos_state,
                prospective_proven, alpha_proven
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                run_id,
                specification.specification_schema_version,
                specification.definition_version,
                specification_hash,
                specification.universe_revision.authority_id,
                universe_id,
                str(specification.universe_revision.content_sha256),
                specification.sample_scope_code,
                specification.sample_algorithm_version,
                specification.sample_input_key,
                specification.random_seed,
                len(specification.sample_members),
                str(specification.sample_roster_sha256),
                specification.exchange_code,
                specification.first_trading_session_id,
                specification.last_trading_session_id,
                specification.distinct_trading_session_count,
                specification.fold_session_binding_count,
                len(specification.fold_dependencies),
                str(specification.dependency_roster_sha256),
                len(specification.arm_folds),
                str(specification.arm_fold_roster_sha256),
                len(specification.model_training_requirements),
                str(specification.model_training_requirement_roster_sha256),
                specification.walk_forward_policy.policy_code,
                specification.walk_forward_policy.policy_version,
                specification.walk_forward_policy.mode.value,
                specification.walk_forward_policy.minimum_fit_sessions,
                specification.walk_forward_policy.validation_sessions,
                specification.walk_forward_policy.step_sessions,
                len(specification.evaluation_requirements),
                str(specification.evaluation_roster_sha256),
                specification.evidence_lane,
                specification.formal_provider_state,
                specification.formal_pit_state,
                specification.formal_oos_state,
                specification.prospective_proven,
                specification.alpha_proven,
            ),
        )
        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.exploratory_backtest_feature (
                    exploratory_backtest_run_id, feature_ordinal,
                    feature_definition_id, feature_definition_sha256,
                    specification_sha256
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    (
                        run_id,
                        ordinal,
                        feature.authority_id,
                        str(feature.content_sha256),
                        specification_hash,
                    )
                    for ordinal, feature in enumerate(
                        specification.feature_definitions, start=1
                    )
                ),
            )
            cursor.executemany(
                """
                INSERT INTO mra.exploratory_backtest_arm (
                    exploratory_backtest_arm_id,
                    exploratory_backtest_run_id, ordinal, arm_kind,
                    content_sha256, specification_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    (
                        arm.exploratory_backtest_arm_id,
                        run_id,
                        arm.ordinal,
                        arm.arm_code,
                        str(arm.content_sha256),
                        specification_hash,
                    )
                    for arm in specification.arms
                ),
            )
            cursor.executemany(
                """
                INSERT INTO mra.exploratory_backtest_fold (
                    exploratory_backtest_fold_id,
                    exploratory_backtest_run_id, ordinal, purpose,
                    exchange_code, purge_sessions, embargo_sessions,
                    evaluation_protocol_id, evaluation_protocol_sha256,
                    session_count, session_roster_sha256, content_sha256,
                    specification_sha256
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    (
                        fold.exploratory_backtest_fold_id,
                        run_id,
                        fold.ordinal,
                        fold.purpose.value,
                        fold.exchange_code,
                        fold.purge_sessions,
                        fold.embargo_sessions,
                        fold.evaluation_protocol.authority_id,
                        str(fold.evaluation_protocol.content_sha256),
                        len(fold.sessions),
                        str(fold.session_roster_sha256),
                        str(fold.content_sha256),
                        specification_hash,
                    )
                    for fold in specification.folds
                ),
            )
            cursor.executemany(
                """
                INSERT INTO mra.exploratory_backtest_fold_session (
                    exploratory_backtest_fold_session_id,
                    exploratory_backtest_fold_id,
                    exploratory_backtest_run_id, ordinal,
                    trading_session_id, session_date, session_role,
                    content_sha256, specification_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    (
                        session.exploratory_backtest_fold_session_id,
                        fold.exploratory_backtest_fold_id,
                        run_id,
                        session.ordinal,
                        session.trading_session_id,
                        session.session_date,
                        session.role.value,
                        str(session.content_sha256),
                        specification_hash,
                    )
                    for fold in specification.folds
                    for session in fold.sessions
                ),
            )
            cursor.executemany(
                """
                INSERT INTO mra.exploratory_backtest_cost_assumption (
                    exploratory_backtest_cost_assumption_id,
                    exploratory_backtest_run_id, ordinal,
                    cost_kind, amount_bps, evidence_class, content_sha256,
                    specification_sha256, charge_side,
                    exploratory_backtest_arm_id
                ) VALUES (%s, %s, %s, %s, %s, 'ASSUMED_COST', %s, %s, %s, NULL)
                """,
                (
                    (
                        cost.assumption_id,
                        run_id,
                        cost.ordinal,
                        cost.cost_kind.value,
                        cost.amount_bps,
                        str(cost.content_sha256),
                        specification_hash,
                        cost.charge_side.value,
                    )
                    for cost in specification.cost_assumptions
                ),
            )
            cursor.executemany(
                """
                INSERT INTO mra.backtest_sample_member (
                    exploratory_backtest_run_id, specification_sha256,
                    ordinal, universe_revision_id, universe_member_id,
                    instrument_id, content_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    (
                        run_id,
                        specification_hash,
                        member.ordinal,
                        specification.universe_revision.authority_id,
                        member.universe_revision_member_id,
                        member.instrument_id,
                        str(member.content_sha256),
                    )
                    for member in specification.sample_members
                ),
            )
            cursor.executemany(
                """
                INSERT INTO mra.backtest_arm_specification (
                    exploratory_backtest_arm_id,
                    exploratory_backtest_run_id, specification_sha256,
                    execution_kind, comparison_role, context_mode,
                    candidate_policy_id, candidate_policy_sha256,
                    candidate_binding_source,
                    context_policy_id, context_policy_sha256,
                    context_binding_source,
                    strategy_version_id, strategy_version_sha256,
                    strategy_binding_source,
                    model_id, model_sha256,
                    portfolio_policy_id, portfolio_policy_sha256,
                    portfolio_binding_source,
                    risk_policy_id, risk_policy_sha256, risk_binding_source,
                    effective_cost_roster_sha256, cost_binding_source,
                    content_sha256
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    (
                        arm.exploratory_backtest_arm_id,
                        run_id,
                        specification_hash,
                        arm.execution_kind.value,
                        arm.comparison_role.value,
                        arm.context_mode.value,
                        arm.candidate.authority_id,
                        str(arm.candidate.content_sha256),
                        arm.candidate_binding_source.value,
                        arm.context.authority_id,
                        str(arm.context.content_sha256),
                        arm.context_binding_source.value,
                        arm.strategy.authority_id,
                        str(arm.strategy.content_sha256),
                        arm.strategy_binding_source.value,
                        None if arm.model is None else arm.model.authority_id,
                        None
                        if arm.model is None
                        else str(arm.model.content_sha256),
                        arm.portfolio.authority_id,
                        str(arm.portfolio.content_sha256),
                        arm.portfolio_binding_source.value,
                        arm.risk.authority_id,
                        str(arm.risk.content_sha256),
                        arm.risk_binding_source.value,
                        str(arm.effective_cost_roster_sha256),
                        arm.cost_binding_source.value,
                        str(arm.content_sha256),
                    )
                    for arm in specification.arms
                ),
            )
            cursor.executemany(
                """
                INSERT INTO mra.backtest_fold_dependency (
                    backtest_fold_dependency_id,
                    exploratory_backtest_run_id, specification_sha256,
                    ordinal, fit_fold_id, validation_fold_id,
                    dependency_kind, content_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s, 'MODEL_TRAINING', %s)
                """,
                (
                    (
                        dependency.dependency_id,
                        run_id,
                        specification_hash,
                        dependency.ordinal,
                        dependency.fit_fold_id,
                        dependency.validation_fold_id,
                        str(dependency.content_sha256),
                    )
                    for dependency in specification.fold_dependencies
                ),
            )
            cursor.executemany(
                """
                INSERT INTO mra.backtest_arm_fold (
                    backtest_arm_fold_id, exploratory_backtest_run_id,
                    specification_sha256, ordinal,
                    exploratory_backtest_arm_id,
                    exploratory_backtest_fold_id, content_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    (
                        item.arm_fold_id,
                        run_id,
                        specification_hash,
                        item.ordinal,
                        item.arm_id,
                        item.fold_id,
                        str(item.content_sha256),
                    )
                    for item in specification.arm_folds
                ),
            )
            folds_by_id = {
                fold.exploratory_backtest_fold_id: fold
                for fold in specification.folds
            }
            cursor.executemany(
                """
                INSERT INTO mra.backtest_model_training_requirement (
                    backtest_model_training_requirement_id,
                    exploratory_backtest_run_id, specification_sha256,
                    ordinal, exploratory_backtest_arm_id,
                    fit_fold_id, validation_fold_id, model_id, model_sha256,
                    required_fit_evaluation_protocol_id,
                    required_fit_evaluation_protocol_sha256,
                    content_sha256
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    (
                        requirement.requirement_id,
                        run_id,
                        specification_hash,
                        requirement.ordinal,
                        requirement.model_arm_id,
                        requirement.fit_fold_id,
                        requirement.validation_fold_id,
                        requirement.model_definition.authority_id,
                        str(requirement.model_definition.content_sha256),
                        folds_by_id[
                            requirement.fit_fold_id
                        ].evaluation_protocol.authority_id,
                        str(
                            folds_by_id[
                                requirement.fit_fold_id
                            ].evaluation_protocol.content_sha256
                        ),
                        str(requirement.content_sha256),
                    )
                    for requirement in specification.model_training_requirements
                ),
            )
            cursor.executemany(
                """
                INSERT INTO mra.backtest_evaluation_requirement (
                    backtest_evaluation_requirement_id,
                    exploratory_backtest_run_id, specification_sha256,
                    ordinal, scope_kind, exploratory_backtest_arm_id,
                    exploratory_backtest_fold_id, slice_key,
                    evaluation_protocol_id, evaluation_protocol_sha256,
                    is_primary, content_sha256
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    (
                        requirement.requirement_id,
                        run_id,
                        specification_hash,
                        requirement.ordinal,
                        requirement.scope_kind.value,
                        requirement.arm_id,
                        requirement.fold_id,
                        requirement.slice_key,
                        requirement.evaluation_protocol.authority_id,
                        str(requirement.evaluation_protocol.content_sha256),
                        requirement.primary,
                        str(requirement.content_sha256),
                    )
                    for requirement in specification.evaluation_requirements
                ),
            )
        self._connection.execute(
            "SET CONSTRAINTS backtest_specification_reconcile_guard IMMEDIATE"
        )
        return self.record(run_id, lock=False)

    def _require_exact_parents(self, specification: BacktestSpecification) -> UUID:
        defaults = specification.defaults
        row = self._connection.execute(
            """
            SELECT revision.universe_id
            FROM mra.market_archive AS archive
            JOIN mra.market_archive_seal AS seal
              ON seal.market_archive_seal_id = %s
             AND seal.market_archive_id = archive.market_archive_id
             AND seal.content_sha256 = %s
            JOIN mra.target_definition AS target
              ON target.target_definition_id = %s
             AND target.version = %s AND target.content_sha256 = %s
            JOIN mra.candidate_policy AS candidate
              ON candidate.candidate_policy_id = %s
             AND candidate.content_sha256 = %s
            JOIN mra.context_policy AS context
              ON context.context_policy_id = %s AND context.content_sha256 = %s
            JOIN mra.strategy_version AS strategy
              ON strategy.strategy_version_id = %s AND strategy.content_sha256 = %s
            JOIN mra.portfolio_policy AS portfolio
              ON portfolio.portfolio_policy_id = %s
             AND portfolio.content_sha256 = %s
            JOIN mra.risk_policy AS risk
              ON risk.risk_policy_id = %s AND risk.content_sha256 = %s
            JOIN mra.universe_revision AS revision
              ON revision.universe_revision_id = %s
             AND revision.scope_content_sha256 = %s
            WHERE archive.market_archive_id = %s
              AND archive.content_sha256 = %s
              AND archive.lane = 'RETROSPECTIVE_BACKFILL'
              AND archive.evidence_class = 'EXPLORATORY_RETROSPECTIVE'
            FOR SHARE OF archive, seal, target, candidate, context,
                         strategy, portfolio, risk, revision
            """,
            (
                specification.market_archive_seal.authority_id,
                str(specification.market_archive_seal.content_sha256),
                specification.target.authority_id,
                specification.target.version,
                str(specification.target.content_sha256),
                defaults.candidate.authority_id,
                str(defaults.candidate.content_sha256),
                defaults.context.authority_id,
                str(defaults.context.content_sha256),
                defaults.strategy.authority_id,
                str(defaults.strategy.content_sha256),
                defaults.portfolio.authority_id,
                str(defaults.portfolio.content_sha256),
                defaults.risk.authority_id,
                str(defaults.risk.content_sha256),
                specification.universe_revision.authority_id,
                str(specification.universe_revision.content_sha256),
                specification.market_archive.authority_id,
                str(specification.market_archive.content_sha256),
            ),
        ).fetchone()
        if row is None:
            raise RuntimeStateConflictError(
                "Backtest parent roster is not exact or archive is not retrospective"
            )
        features = self._connection.execute(
            """
            SELECT feature_definition_id, content_sha256
            FROM mra.feature_definition
            WHERE feature_definition_id = ANY(%s::uuid[])
            FOR SHARE
            """,
            ([item.authority_id for item in specification.feature_definitions],),
        ).fetchall()
        if {(UUID(str(item[0])), str(item[1])) for item in features} != {
            (item.authority_id, str(item.content_sha256))
            for item in specification.feature_definitions
        }:
            raise RuntimeStateConflictError("Backtest Feature roster is not exact")
        for fold in specification.folds:
            protocol = self._connection.execute(
                """
                SELECT 1 FROM mra.evaluation_protocol
                WHERE evaluation_protocol_id = %s AND content_sha256 = %s
                  AND target_definition_id = %s AND applicable_purpose = %s
                FOR SHARE
                """,
                (
                    fold.evaluation_protocol.authority_id,
                    str(fold.evaluation_protocol.content_sha256),
                    specification.target.authority_id,
                    fold.purpose.value,
                ),
            ).fetchone()
            if protocol is None:
                raise RuntimeStateConflictError(
                    "Backtest EvaluationProtocol roster is not exact"
                )
        sessions = {
            (item.trading_session_id, item.session_date, fold.exchange_code)
            for fold in specification.folds
            for item in fold.sessions
        }
        rows = self._connection.execute(
            """
            SELECT session_id, session_date, exchange
            FROM mra.trading_session
            WHERE session_id = ANY(%s::uuid[])
            FOR SHARE
            """,
            ([item[0] for item in sessions],),
        ).fetchall()
        if {(UUID(str(item[0])), item[1], str(item[2])) for item in rows} != sessions:
            raise RuntimeStateConflictError(
                "Backtest TradingSession roster is not exact"
            )
        return UUID(str(row[0]))

    def record(
        self,
        exploratory_backtest_run_id: UUID,
        *,
        lock: bool,
    ) -> BacktestSpecificationRecord:
        row = self._connection.execute(
            """
            SELECT root.exploratory_backtest_run_id, root.generation,
                   specification.specification_sha256,
                   root.definition_sha256, root.arm_count, root.fold_count,
                   specification.distinct_trading_session_count,
                   specification.fold_session_binding_count,
                   root.registered_at
            FROM mra.exploratory_backtest_run AS root
            JOIN mra.backtest_specification AS specification
              USING (exploratory_backtest_run_id)
            WHERE root.exploratory_backtest_run_id = %s
            """
            + (" FOR SHARE OF root, specification" if lock else ""),
            (exploratory_backtest_run_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(
                f"current Backtest {exploratory_backtest_run_id} does not exist"
            )
        return BacktestSpecificationRecord(
            exploratory_backtest_run_id=UUID(str(row[0])),
            generation=int(row[1]),
            specification_sha256=str(row[2]),
            definition_sha256=str(row[3]),
            arm_count=int(row[4]),
            fold_count=int(row[5]),
            distinct_trading_session_count=int(row[6]),
            fold_session_binding_count=int(row[7]),
            registered_at=row[8],
        )


__all__ = ["PostgresBacktestRepository"]
