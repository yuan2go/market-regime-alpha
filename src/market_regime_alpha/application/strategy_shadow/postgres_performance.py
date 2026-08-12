"""PostgreSQL owner for immutable Portfolio Shadow performance reports."""

from __future__ import annotations

from datetime import date
from typing import Any

from psycopg.types.json import Jsonb

from market_regime_alpha.application.strategy_shadow.performance import (
    PerformancePolicy,
    PortfolioPerformanceReport,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


class PostgresPortfolioPerformanceRepository:
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = True,
    ) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def publish(
        self,
        *,
        policy: PerformancePolicy,
        report: PortfolioPerformanceReport,
    ) -> PortfolioPerformanceReport:
        if (
            report.policy_reference.artifact_id != policy.policy_id
            or report.policy_reference.content_hash != policy.policy_hash
        ):
            raise ValueError("Performance report does not bind the supplied Policy")

        def operation(connection: Any) -> None:
            self._verify_owner_chain(connection, report)
            connection.execute(
                """
                INSERT INTO shadow_performance_policy(
                    policy_id, policy_hash, policy_version, payload_json, created_at
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (policy_id) DO NOTHING
                """,
                (
                    str(policy.policy_id),
                    policy.policy_hash,
                    policy.policy_version,
                    Jsonb(policy.to_canonical_dict()),
                    report.generated_at,
                ),
            )
            policy_row = connection.execute(
                "SELECT policy_hash, payload_json FROM shadow_performance_policy WHERE policy_id = %s",
                (str(policy.policy_id),),
            ).fetchone()
            if policy_row is None or (
                str(policy_row[0]) != policy.policy_hash
                or policy_row[1] != policy.to_canonical_dict()
            ):
                raise ValueError("Performance Policy identity conflict")
            connection.execute(
                """
                INSERT INTO shadow_performance_report(
                    report_id, report_hash, portfolio_id, portfolio_hash,
                    policy_id, policy_hash, start_date, end_date, generated_at,
                    reconciliation_difference, negative_results_preserved,
                    payload_json, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true, %s, %s
                ) ON CONFLICT (report_id) DO NOTHING
                """,
                (
                    str(report.report_id),
                    report.report_hash,
                    str(report.portfolio_reference.artifact_id),
                    report.portfolio_reference.content_hash,
                    str(policy.policy_id),
                    policy.policy_hash,
                    report.start_date,
                    report.end_date,
                    report.generated_at,
                    report.reconciliation_difference,
                    Jsonb(report.to_canonical_dict()),
                    report.generated_at,
                ),
            )
            report_row = connection.execute(
                "SELECT report_hash FROM shadow_performance_report WHERE report_id = %s",
                (str(report.report_id),),
            ).fetchone()
            if report_row is None or str(report_row[0]) != report.report_hash:
                raise ValueError("Performance report identity conflict")
            for ordinal, reference in enumerate(
                report.input_state_references, start=1
            ):
                connection.execute(
                    """
                    INSERT INTO shadow_performance_state_binding(
                        report_id, ordinal, state_id, state_hash
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (report_id, ordinal) DO NOTHING
                    """,
                    (
                        str(report.report_id),
                        ordinal,
                        str(reference.artifact_id),
                        reference.content_hash,
                    ),
                )
            for metric in report.metrics:
                connection.execute(
                    """
                    INSERT INTO shadow_performance_metric(
                        report_id, metric_name, estimation_status,
                        metric_value, payload_json
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (report_id, metric_name) DO NOTHING
                    """,
                    (
                        str(report.report_id),
                        metric.name,
                        metric.status.value,
                        metric.value,
                        Jsonb(metric.to_canonical_dict()),
                    ),
                )
            for kind, values in (
                ("MONTHLY", report.monthly_returns),
                ("YEARLY", report.yearly_returns),
            ):
                for item in values:
                    connection.execute(
                        """
                        INSERT INTO shadow_performance_period_return(
                            report_id, period_kind, period_key,
                            return_value, payload_json
                        ) VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (report_id, period_kind, period_key) DO NOTHING
                        """,
                        (
                            str(report.report_id),
                            kind,
                            item.period,
                            item.value,
                            Jsonb(item.to_canonical_dict()),
                        ),
                    )
            for item in report.attribution:
                connection.execute(
                    """
                    INSERT INTO shadow_performance_attribution(
                        report_id, dimension, attribution_key,
                        estimation_status, contribution, payload_json
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (report_id, dimension, attribution_key) DO NOTHING
                    """,
                    (
                        str(report.report_id),
                        item.dimension,
                        item.key,
                        item.status.value,
                        item.contribution,
                        Jsonb(item.to_canonical_dict()),
                    ),
                )
            self._verify_projections(connection, report)

        self._factory.run_transaction(operation)
        return self.get(report.report_id)

    def get_policy(self, policy_id: ArtifactId) -> PerformancePolicy:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT policy_hash, payload_json FROM shadow_performance_policy "
                "WHERE policy_id = %s",
                (str(policy_id),),
            ).fetchone()
        if row is None or not isinstance(row[1], dict):
            raise KeyError(str(policy_id))
        policy = PerformancePolicy.from_canonical_dict(row[1])
        if str(row[0]) != policy.policy_hash:
            raise ValueError("Performance Policy owner hash diverged")
        return policy

    def get(self, report_id: ArtifactId) -> PortfolioPerformanceReport:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT report_hash, payload_json FROM shadow_performance_report "
                "WHERE report_id = %s",
                (str(report_id),),
            ).fetchone()
            if row is None or not isinstance(row[1], dict):
                raise KeyError(str(report_id))
            report = PortfolioPerformanceReport.from_canonical_dict(row[1])
            if str(row[0]) != report.report_hash:
                raise ValueError("Performance report owner hash diverged")
            self._verify_owner_chain(connection, report)
            self._verify_projections(connection, report)
        return report

    def find(
        self,
        *,
        portfolio_id: ArtifactId,
        start_date: date,
        end_date: date,
        policy_id: ArtifactId,
    ) -> PortfolioPerformanceReport:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT report_id FROM shadow_performance_report
                WHERE portfolio_id = %s AND start_date = %s AND end_date = %s
                  AND policy_id = %s
                """,
                (str(portfolio_id), start_date, end_date, str(policy_id)),
            ).fetchone()
        if row is None:
            raise KeyError("Portfolio performance report not found")
        return self.get(ArtifactId(str(row[0])))

    @staticmethod
    def _verify_owner_chain(
        connection: Any,
        report: PortfolioPerformanceReport,
    ) -> None:
        portfolio = connection.execute(
            "SELECT portfolio_hash, created_at FROM strategy_shadow_portfolio "
            "WHERE portfolio_id = %s",
            (str(report.portfolio_reference.artifact_id),),
        ).fetchone()
        if (
            portfolio is None
            or str(portfolio[0]) != report.portfolio_reference.content_hash
            or report.generated_at < portfolio[1]
        ):
            raise ValueError("Performance Portfolio owner identity/time mismatch")
        state_rows = connection.execute(
            """
            SELECT state_id, state_hash, portfolio_id, recorded_at
            FROM strategy_shadow_portfolio_day
            WHERE state_id = ANY(%s::text[])
            """,
            ([str(item.artifact_id) for item in report.input_state_references],),
        ).fetchall()
        by_id = {str(item[0]): item for item in state_rows}
        for reference in report.input_state_references:
            row = by_id.get(str(reference.artifact_id))
            if (
                row is None
                or str(row[1]) != reference.content_hash
                or str(row[2]) != str(report.portfolio_reference.artifact_id)
                or report.generated_at < row[3]
            ):
                raise ValueError("Performance State owner identity/time mismatch")

    @staticmethod
    def _verify_projections(connection: Any, report: PortfolioPerformanceReport) -> None:
        state_rows = connection.execute(
            "SELECT ordinal, state_id, state_hash "
            "FROM shadow_performance_state_binding "
            "WHERE report_id = %s ORDER BY ordinal",
            (str(report.report_id),),
        ).fetchall()
        state_count = connection.execute(
            "SELECT count(*) FROM shadow_performance_state_binding "
            "WHERE report_id = %s",
            (str(report.report_id),),
        ).fetchone()
        metric_count = connection.execute(
            "SELECT count(*) FROM shadow_performance_metric WHERE report_id = %s",
            (str(report.report_id),),
        ).fetchone()
        period_count = connection.execute(
            "SELECT count(*) FROM shadow_performance_period_return "
            "WHERE report_id = %s",
            (str(report.report_id),),
        ).fetchone()
        attribution_count = connection.execute(
            "SELECT count(*) FROM shadow_performance_attribution "
            "WHERE report_id = %s",
            (str(report.report_id),),
        ).fetchone()
        expected = (
            len(report.input_state_references),
            len(report.metrics),
            len(report.monthly_returns) + len(report.yearly_returns),
            len(report.attribution),
        )
        actual = tuple(
            -1 if item is None else int(item[0])
            for item in (state_count, metric_count, period_count, attribution_count)
        )
        if actual != expected:
            raise ValueError("Performance report projection diverged")
        if [
            (int(row[0]), str(row[1]), str(row[2])) for row in state_rows
        ] != [
            (ordinal, str(reference.artifact_id), reference.content_hash)
            for ordinal, reference in enumerate(
                report.input_state_references, start=1
            )
        ]:
            raise ValueError("Performance State binding projection diverged")


__all__ = ["PostgresPortfolioPerformanceRepository"]
