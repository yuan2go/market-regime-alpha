"""Private exact historical Backtest loader over immutable relational evidence."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.research_qualification.domain.backtest import AuthorityBinding
from market_regime_alpha.research_qualification.domain.backtest_compatibility import (
    HistoricalBacktestCompatibilityError,
    decode_exact_historical_backtest,
    is_exact_historical_backtest_identity,
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
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionPurpose,
)
from market_regime_alpha.research_qualification.ports.backtest_queries import (
    BacktestAuthoritySnapshot,
)
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeNotFoundError,
)


class PostgresExactHistoricalBacktestQueryPort:
    """Rebuild an allowlisted old plan without writing or reinterpreting it."""

    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def load(self, exploratory_backtest_run_id: UUID) -> BacktestAuthoritySnapshot:
        if not is_exact_historical_backtest_identity(exploratory_backtest_run_id):
            raise HistoricalBacktestCompatibilityError(
                "Backtest identity is not in the exact historical allowlist"
            )
        with self._pool.connection(read_only=True) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                root = cursor.execute(
                    """
                    SELECT * FROM mra.exploratory_backtest_run
                    WHERE exploratory_backtest_run_id = %s
                    """,
                    (exploratory_backtest_run_id,),
                ).fetchone()
                if root is None:
                    raise RuntimeNotFoundError(
                        f"Backtest {exploratory_backtest_run_id} does not exist"
                    )
                feature_rows = cursor.execute(
                    """
                    SELECT * FROM mra.exploratory_backtest_feature
                    WHERE exploratory_backtest_run_id = %s
                    ORDER BY feature_ordinal
                    """,
                    (exploratory_backtest_run_id,),
                ).fetchall()
                has_arm_strategy = cursor.execute(
                    "SELECT to_regclass('mra.exploratory_backtest_arm_strategy')"
                ).fetchone()
                assert has_arm_strategy is not None
                if has_arm_strategy["to_regclass"] is None:
                    arm_rows = cursor.execute(
                        """
                        SELECT arm.*, NULL::uuid AS arm_strategy_id,
                               NULL::text AS arm_strategy_sha256,
                               NULL::text AS arm_context_mode,
                               NULL::text AS binding_sha256
                        FROM mra.exploratory_backtest_arm AS arm
                        WHERE arm.exploratory_backtest_run_id = %s
                        ORDER BY arm.ordinal
                        """,
                        (exploratory_backtest_run_id,),
                    ).fetchall()
                else:
                    arm_rows = cursor.execute(
                        """
                        SELECT arm.*,
                               binding.strategy_version_id AS arm_strategy_id,
                               binding.strategy_version_sha256 AS arm_strategy_sha256,
                               binding.context_mode AS arm_context_mode,
                               binding.content_sha256 AS binding_sha256
                        FROM mra.exploratory_backtest_arm AS arm
                        LEFT JOIN mra.exploratory_backtest_arm_strategy AS binding
                          ON binding.exploratory_backtest_arm_id =
                             arm.exploratory_backtest_arm_id
                         AND binding.exploratory_backtest_run_id =
                             arm.exploratory_backtest_run_id
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
                cost_rows = cursor.execute(
                    """
                    SELECT * FROM mra.exploratory_backtest_cost_assumption
                    WHERE exploratory_backtest_run_id = %s ORDER BY ordinal
                    """,
                    (exploratory_backtest_run_id,),
                ).fetchall()
                model_rows = cursor.execute(
                    """
                    SELECT DISTINCT training.exploratory_backtest_arm_id,
                           model.model_id, model.content_sha256
                    FROM mra.model_training_run AS training
                    JOIN mra.model AS model ON model.model_id = training.model_id
                    WHERE training.exploratory_backtest_run_id = %s
                    ORDER BY training.exploratory_backtest_arm_id
                    """,
                    (exploratory_backtest_run_id,),
                ).fetchall()
                artifact_rows = cursor.execute(
                    """
                    SELECT artifact_id, content_sha256, size_bytes
                    FROM mra.artifact
                    WHERE (artifact_id, content_sha256, size_bytes) IN (
                        (%s, %s, %s), (%s, %s, %s)
                    )
                    ORDER BY artifact_id
                    """,
                    (
                        root["code_artifact_id"],
                        root["code_content_sha256"],
                        root["code_size_bytes"],
                        root["config_artifact_id"],
                        root["config_content_sha256"],
                        root["config_size_bytes"],
                    ),
                ).fetchall()

        sessions_by_fold: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        for row in session_rows:
            sessions_by_fold[UUID(str(row["exploratory_backtest_fold_id"]))].append(
                row
            )
        arms = tuple(self._arm(row) for row in arm_rows)
        folds = tuple(
            self._fold(
                row,
                sessions_by_fold[UUID(str(row["exploratory_backtest_fold_id"]))],
            )
            for row in fold_rows
        )
        costs = tuple(self._cost(row) for row in cost_rows)
        self._require_stored_child_hashes(arm_rows, arms, fold_rows, folds, cost_rows, costs)
        if len(artifact_rows) != 2:
            raise ArtifactIntegrityError(
                "historical Backtest root Artifact bindings do not reconcile"
            )
        plan = ExploratoryBacktestRunPlan(
            exploratory_backtest_run_id=UUID(
                str(root["exploratory_backtest_run_id"])
            ),
            run_code=str(root["run_code"]),
            generation=int(root["generation"]),
            market_archive_id=UUID(str(root["market_archive_id"])),
            market_archive_seal_id=UUID(str(root["market_archive_seal_id"])),
            hypothesis=str(root["hypothesis"]),
            target_definition_id=UUID(str(root["target_definition_id"])),
            target_version=int(root["target_version"]),
            target_definition_sha256=str(root["target_definition_sha256"]),
            feature_definitions=tuple(
                (
                    UUID(str(row["feature_definition_id"])),
                    str(row["feature_definition_sha256"]),
                )
                for row in feature_rows
            ),
            candidate_policy_id=UUID(str(root["candidate_policy_id"])),
            candidate_policy_sha256=str(root["candidate_policy_sha256"]),
            context_policy_id=UUID(str(root["context_policy_id"])),
            context_policy_sha256=str(root["context_policy_sha256"]),
            strategy_version_id=UUID(str(root["strategy_version_id"])),
            strategy_version_sha256=str(root["strategy_version_sha256"]),
            portfolio_policy_id=UUID(str(root["portfolio_policy_id"])),
            portfolio_policy_sha256=str(root["portfolio_policy_sha256"]),
            risk_policy_id=UUID(str(root["risk_policy_id"])),
            risk_policy_sha256=str(root["risk_policy_sha256"]),
            arms=arms,
            folds=folds,
            cost_assumptions=costs,
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
        )
        self._require_root_hashes(root, plan)
        model_definitions = self._model_definitions(model_rows)
        frozen = decode_exact_historical_backtest(
            plan, model_definitions=model_definitions
        )
        bindings = tuple(
            ArtifactBinding(
                UUID(str(row["artifact_id"])),
                str(row["content_sha256"]),
                int(row["size_bytes"]),
            )
            for row in artifact_rows
        )
        return BacktestAuthoritySnapshot(frozen, bindings)

    @staticmethod
    def _arm(row: dict[str, Any]) -> BacktestArmPlan:
        arm = BacktestArmPlan(
            exploratory_backtest_arm_id=UUID(
                str(row["exploratory_backtest_arm_id"])
            ),
            ordinal=int(row["ordinal"]),
            kind=BacktestArmKind(str(row["arm_kind"])),
            strategy_version_id=(
                None
                if row["arm_strategy_id"] is None
                else UUID(str(row["arm_strategy_id"]))
            ),
            strategy_version_sha256=(
                None
                if row["arm_strategy_sha256"] is None
                else str(row["arm_strategy_sha256"])
            ),
        )
        if row["binding_sha256"] is not None and str(row["binding_sha256"]) != str(
            arm.content_sha256
        ):
            raise ArtifactIntegrityError(
                "historical Backtest arm Strategy binding hash does not reconcile"
            )
        return arm

    @staticmethod
    def _fold(
        row: dict[str, Any], sessions: list[dict[str, Any]]
    ) -> BacktestFoldPlan:
        fold = BacktestFoldPlan(
            exploratory_backtest_fold_id=UUID(
                str(row["exploratory_backtest_fold_id"])
            ),
            ordinal=int(row["ordinal"]),
            purpose=PartitionPurpose(str(row["purpose"])),
            exchange_code=str(row["exchange_code"]),
            purge_sessions=int(row["purge_sessions"]),
            embargo_sessions=int(row["embargo_sessions"]),
            evaluation_protocol_id=UUID(str(row["evaluation_protocol_id"])),
            evaluation_protocol_sha256=str(row["evaluation_protocol_sha256"]),
            sessions=tuple(
                BacktestFoldSessionPlan(
                    exploratory_backtest_fold_session_id=UUID(
                        str(member["exploratory_backtest_fold_session_id"])
                    ),
                    ordinal=int(member["ordinal"]),
                    trading_session_id=UUID(str(member["trading_session_id"])),
                    session_date=member["session_date"],
                    role=BacktestSessionRole(str(member["session_role"])),
                )
                for member in sessions
            ),
        )
        if int(row["session_count"]) != len(fold.sessions) or str(
            row["session_roster_sha256"]
        ) != str(fold.session_roster_sha256):
            raise ArtifactIntegrityError(
                "historical Backtest fold session roster does not reconcile"
            )
        for stored, rebuilt in zip(sessions, fold.sessions, strict=True):
            if str(stored["content_sha256"]) != str(rebuilt.content_sha256):
                raise ArtifactIntegrityError(
                    "historical Backtest fold session hash does not reconcile"
                )
        return fold

    @staticmethod
    def _cost(row: dict[str, Any]) -> BacktestCostAssumption:
        return BacktestCostAssumption(
            exploratory_backtest_cost_assumption_id=UUID(
                str(row["exploratory_backtest_cost_assumption_id"])
            ),
            ordinal=int(row["ordinal"]),
            cost_kind=BacktestCostKind(str(row["cost_kind"])),
            amount_bps=Decimal(str(row["amount_bps"])),
        )

    @staticmethod
    def _require_stored_child_hashes(
        arm_rows: list[dict[str, Any]],
        arms: tuple[BacktestArmPlan, ...],
        fold_rows: list[dict[str, Any]],
        folds: tuple[BacktestFoldPlan, ...],
        cost_rows: list[dict[str, Any]],
        costs: tuple[BacktestCostAssumption, ...],
    ) -> None:
        pairs = (
            zip(arm_rows, arms, strict=True),
            zip(fold_rows, folds, strict=True),
            zip(cost_rows, costs, strict=True),
        )
        for roster in pairs:
            for stored, rebuilt in roster:
                if str(stored["content_sha256"]) != str(rebuilt.content_sha256):
                    raise ArtifactIntegrityError(
                        "historical Backtest child hash does not reconcile"
                    )

    @staticmethod
    def _require_root_hashes(
        root: dict[str, Any], plan: ExploratoryBacktestRunPlan
    ) -> None:
        expected = (
            ("feature_count", len(plan.feature_definitions)),
            ("feature_roster_sha256", str(plan.feature_roster_sha256)),
            ("arm_count", len(plan.arms)),
            ("arm_roster_sha256", str(plan.arm_roster_sha256)),
            ("fold_count", len(plan.folds)),
            ("fold_roster_sha256", str(plan.fold_roster_sha256)),
            ("session_count", plan.session_count),
            ("cost_count", len(plan.cost_assumptions)),
            ("cost_roster_sha256", str(plan.cost_roster_sha256)),
            ("definition_sha256", str(plan.content_sha256)),
        )
        mismatches = tuple(name for name, value in expected if root[name] != value)
        if mismatches:
            raise ArtifactIntegrityError(
                "historical Backtest root does not reconcile: "
                + ",".join(mismatches)
            )

    @staticmethod
    def _model_definitions(
        rows: list[dict[str, Any]],
    ) -> dict[UUID, AuthorityBinding]:
        definitions: dict[UUID, AuthorityBinding] = {}
        for row in rows:
            arm_id = UUID(str(row["exploratory_backtest_arm_id"]))
            binding = AuthorityBinding(
                UUID(str(row["model_id"])), str(row["content_sha256"])
            )
            existing = definitions.setdefault(arm_id, binding)
            if existing != binding:
                raise ArtifactIntegrityError(
                    "historical Backtest model definition roster is ambiguous"
                )
        return definitions


__all__ = ["PostgresExactHistoricalBacktestQueryPort"]
