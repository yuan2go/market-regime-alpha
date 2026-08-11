"""PostgreSQL registry for frozen C0 Protocol and Target-bound Forecast artifacts."""

from __future__ import annotations

from typing import Any, Mapping

from psycopg.types.json import Jsonb

from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeTargetProtocol,
)
from market_regime_alpha.application.research_validation.formal_evaluation import (
    FormalEvaluationProtocol,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    FormalResearchProtocol,
    OutcomeTargetBoundMultiTargetForecast,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


class FormalProtocolConflict(ValueError):
    """A frozen owner identity or Target lineage conflicted."""


class PostgresFormalProtocolRepository:
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = True,
    ) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def record_protocol(
        self,
        *,
        protocol: FormalResearchProtocol,
        target_protocol: OutcomeTargetProtocol,
        evaluation_protocol: FormalEvaluationProtocol,
        component_payloads: Mapping[str, Mapping[str, Any]],
    ) -> FormalResearchProtocol:
        expected_target_ref = protocol.outcome_target_protocol_reference
        if (
            expected_target_ref.artifact_id != target_protocol.protocol_id
            or expected_target_ref.content_hash != target_protocol.protocol_hash
            or protocol.evaluation_protocol_reference.artifact_id
            != evaluation_protocol.protocol_id
            or protocol.evaluation_protocol_reference.content_hash
            != evaluation_protocol.protocol_hash
        ):
            raise FormalProtocolConflict("Formal Protocol typed lineage mismatch")
        references = protocol.component_references()
        if set(component_payloads) != set(references):
            raise FormalProtocolConflict(
                "Formal Protocol requires an exact payload for every component role"
            )
        normalized_components = {
            role: dict(component_payloads[role]) for role in sorted(references)
        }
        for role, reference in references.items():
            if canonical_hash(normalized_components[role]) != reference.content_hash:
                raise FormalProtocolConflict(
                    f"Formal Protocol component payload hash mismatch: {role}"
                )
        _verify_calendar_component(
            protocol,
            normalized_components["trading_calendar_reference"],
        )

        def operation(connection: Any) -> None:
            self._require_target_owner(connection, target_protocol)
            connection.execute(
                """
                INSERT INTO research_validation_artifact(
                    artifact_id, artifact_hash, artifact_kind,
                    evidence_authority, qualified, production_authorized,
                    payload_json, created_at
                ) VALUES (%s, %s, 'FORMAL_EVALUATION_PROTOCOL',
                          'ENGINEERING_ONLY', false, false, %s, %s)
                ON CONFLICT (artifact_id) DO NOTHING
                """,
                (
                    str(evaluation_protocol.protocol_id),
                    evaluation_protocol.protocol_hash,
                    Jsonb(evaluation_protocol.identity_payload()),
                    evaluation_protocol.locked_at,
                ),
            )
            evaluation = connection.execute(
                """
                SELECT artifact_hash, artifact_kind, evidence_authority,
                       qualified, production_authorized
                FROM research_validation_artifact
                WHERE artifact_id = %s
                """,
                (str(evaluation_protocol.protocol_id),),
            ).fetchone()
            if evaluation is None or (
                str(evaluation[0]) != evaluation_protocol.protocol_hash
                or str(evaluation[1]) != "FORMAL_EVALUATION_PROTOCOL"
                or str(evaluation[2]) != "ENGINEERING_ONLY"
                or bool(evaluation[3])
                or bool(evaluation[4])
            ):
                raise FormalProtocolConflict(
                    "Formal Evaluation Protocol owner mismatch"
                )
            connection.execute(
                """
                INSERT INTO formal_research_protocol(
                    protocol_id, protocol_hash, protocol_version,
                    outcome_target_protocol_id, evaluation_protocol_id,
                    trading_calendar_id, trading_calendar_hash,
                    payload_json, locked_at, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                          date_trunc('second', clock_timestamp()))
                ON CONFLICT (protocol_id) DO NOTHING
                """,
                (
                    str(protocol.protocol_id),
                    protocol.protocol_hash,
                    protocol.protocol_version,
                    str(target_protocol.protocol_id),
                    str(evaluation_protocol.protocol_id),
                    str(protocol.trading_calendar_reference.artifact_id),
                    protocol.trading_calendar_reference.content_hash,
                    Jsonb(protocol.to_canonical_dict()),
                    protocol.locked_at,
                ),
            )
            stored = connection.execute(
                """
                SELECT protocol_hash
                FROM formal_research_protocol
                WHERE protocol_id = %s
                """,
                (str(protocol.protocol_id),),
            ).fetchone()
            if stored is None or str(stored[0]) != protocol.protocol_hash:
                raise FormalProtocolConflict("Formal Research Protocol identity conflict")
            for role, reference in sorted(references.items()):
                connection.execute(
                    """
                    INSERT INTO formal_research_protocol_component(
                        protocol_id, component_role, artifact_kind,
                        artifact_id, artifact_hash, payload_json
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (protocol_id, component_role) DO NOTHING
                    """,
                    (
                        str(protocol.protocol_id),
                        role,
                        reference.artifact_kind,
                        str(reference.artifact_id),
                        reference.content_hash,
                        Jsonb(normalized_components[role]),
                    ),
                )
            component_rows = connection.execute(
                """
                SELECT component_role, artifact_kind, artifact_id,
                       artifact_hash, payload_json
                FROM formal_research_protocol_component
                WHERE protocol_id = %s ORDER BY component_role
                """,
                (str(protocol.protocol_id),),
            ).fetchall()
            actual_components = {
                str(item[0]): (
                    str(item[1]),
                    str(item[2]),
                    str(item[3]),
                    item[4],
                )
                for item in component_rows
            }
            expected_components = {
                role: (
                    reference.artifact_kind,
                    str(reference.artifact_id),
                    reference.content_hash,
                    normalized_components[role],
                )
                for role, reference in references.items()
            }
            if actual_components != expected_components:
                raise FormalProtocolConflict(
                    "Formal Protocol component owner binding mismatch"
                )

        self._factory.run_transaction(operation)
        return self.get_protocol(protocol.protocol_id)

    def record_forecast(
        self,
        forecast: OutcomeTargetBoundMultiTargetForecast,
    ) -> OutcomeTargetBoundMultiTargetForecast:
        def operation(connection: Any) -> None:
            owner = connection.execute(
                """
                SELECT protocol_hash
                FROM outcome_target_protocol
                WHERE protocol_id = %s
                """,
                (str(forecast.target_protocol_reference.artifact_id),),
            ).fetchone()
            if owner is None or str(owner[0]) != forecast.target_protocol_reference.content_hash:
                raise FormalProtocolConflict("Forecast Target Protocol owner mismatch")
            target_rows = connection.execute(
                """
                SELECT target_id, target_hash
                FROM outcome_target_definition
                WHERE protocol_id = %s
                ORDER BY target_id
                """,
                (str(forecast.target_protocol_reference.artifact_id),),
            ).fetchall()
            expected = tuple((str(item[0]), str(item[1])) for item in target_rows)
            actual = tuple(
                (str(item.target_id), item.target_hash) for item in forecast.estimates
            )
            if actual != expected:
                raise FormalProtocolConflict(
                    "Forecast estimates do not match PostgreSQL Outcome Target owner"
                )
            connection.execute(
                """
                INSERT INTO outcome_target_bound_forecast(
                    forecast_id, forecast_hash, target_protocol_id, symbol,
                    decision_time, model_id, calibrated,
                    production_authorized, payload_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, false, false, %s, %s)
                ON CONFLICT (forecast_id) DO NOTHING
                """,
                (
                    str(forecast.forecast_id),
                    forecast.forecast_hash,
                    str(forecast.target_protocol_reference.artifact_id),
                    forecast.symbol,
                    forecast.decision_time,
                    str(forecast.model_reference.artifact_id),
                    Jsonb(forecast.to_canonical_dict()),
                    forecast.created_at,
                ),
            )
            for estimate in forecast.estimates:
                connection.execute(
                    """
                    INSERT INTO outcome_target_bound_forecast_estimate(
                        forecast_id, target_protocol_id, target_id,
                        target_hash, status, payload_json
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (forecast_id, target_id) DO NOTHING
                    """,
                    (
                        str(forecast.forecast_id),
                        str(forecast.target_protocol_reference.artifact_id),
                        str(estimate.target_id),
                        estimate.target_hash,
                        estimate.status.value,
                        Jsonb(estimate.to_canonical_dict()),
                    ),
                )
            stored = connection.execute(
                """
                SELECT forecast_hash, calibrated, production_authorized
                FROM outcome_target_bound_forecast
                WHERE forecast_id = %s
                """,
                (str(forecast.forecast_id),),
            ).fetchone()
            stored_estimates = connection.execute(
                """
                SELECT target_id, target_hash
                FROM outcome_target_bound_forecast_estimate
                WHERE forecast_id = %s
                ORDER BY target_id
                """,
                (str(forecast.forecast_id),),
            ).fetchall()
            if stored is None or (
                str(stored[0]) != forecast.forecast_hash
                or bool(stored[1])
                or bool(stored[2])
                or tuple((str(item[0]), str(item[1])) for item in stored_estimates)
                != actual
            ):
                raise FormalProtocolConflict("Target-bound Forecast identity conflict")

        self._factory.run_transaction(operation)
        return self.get_forecast(forecast.forecast_id)

    def get_protocol(self, protocol_id: ArtifactId) -> FormalResearchProtocol:
        with self._factory.connection(read_only=True) as connection:
            return load_formal_protocol_owner(connection, protocol_id)

    def get_forecast(
        self, forecast_id: ArtifactId
    ) -> OutcomeTargetBoundMultiTargetForecast:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json, forecast_hash, calibrated,
                       production_authorized
                FROM outcome_target_bound_forecast
                WHERE forecast_id = %s
                """,
                (str(forecast_id),),
            ).fetchone()
        if row is None or not isinstance(row[0], dict):
            raise KeyError(str(forecast_id))
        forecast = OutcomeTargetBoundMultiTargetForecast.from_canonical_dict(row[0])
        if (
            forecast.forecast_hash != str(row[1])
            or bool(row[2])
            or bool(row[3])
        ):
            raise FormalProtocolConflict("Target-bound Forecast storage drift")
        return forecast

    @staticmethod
    def _require_target_owner(
        connection: Any, target_protocol: OutcomeTargetProtocol
    ) -> None:
        row = connection.execute(
            """
            SELECT protocol_hash
            FROM outcome_target_protocol
            WHERE protocol_id = %s
            """,
            (str(target_protocol.protocol_id),),
        ).fetchone()
        targets = connection.execute(
            """
            SELECT target_id, target_hash
            FROM outcome_target_definition
            WHERE protocol_id = %s
            ORDER BY target_id
            """,
            (str(target_protocol.protocol_id),),
        ).fetchall()
        expected = tuple(
            (str(item.target_id), item.target_hash) for item in target_protocol.targets
        )
        if row is None or (
            str(row[0]) != target_protocol.protocol_hash
            or tuple((str(item[0]), str(item[1])) for item in targets) != expected
        ):
            raise FormalProtocolConflict("Outcome Target Protocol owner mismatch")


def _verify_calendar_component(
    protocol: FormalResearchProtocol,
    payload: Mapping[str, Any],
) -> None:
    try:
        calendar = TradingCalendarArtifact.from_canonical_dict(
            {
                "artifact_id": str(protocol.trading_calendar_reference.artifact_id),
                **dict(payload),
            }
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalProtocolConflict(
            "Frozen Trading Calendar component replay failed"
        ) from exc
    if (
        calendar.content_hash != protocol.trading_calendar_reference.content_hash
        or calendar.trading_dates != protocol.frozen_trading_dates
    ):
        raise FormalProtocolConflict(
            "Frozen Trading Calendar component and Protocol dates diverge"
        )


def load_formal_protocol_owner(
    connection: Any,
    protocol_id: ArtifactId,
) -> FormalResearchProtocol:
    """Replay every typed C0 owner needed by downstream qualification writers."""

    row = connection.execute(
        """
        SELECT payload_json, protocol_hash
        FROM formal_research_protocol WHERE protocol_id = %s
        """,
        (str(protocol_id),),
    ).fetchone()
    if row is None or not isinstance(row[0], Mapping):
        raise KeyError(str(protocol_id))
    try:
        protocol = FormalResearchProtocol.from_canonical_dict(dict(row[0]))
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalProtocolConflict("Formal Protocol canonical replay failed") from exc
    if protocol.protocol_hash != str(row[1]):
        raise FormalProtocolConflict("Formal Protocol storage hash mismatch")

    component_rows = connection.execute(
        """
        SELECT component_role, artifact_kind, artifact_id,
               artifact_hash, payload_json
        FROM formal_research_protocol_component
        WHERE protocol_id = %s ORDER BY component_role
        """,
        (str(protocol_id),),
    ).fetchall()
    references = protocol.component_references()
    stored = {
        str(item[0]): (
            str(item[1]),
            str(item[2]),
            str(item[3]),
            item[4],
        )
        for item in component_rows
    }
    expected = {
        role: (
            reference.artifact_kind,
            str(reference.artifact_id),
            reference.content_hash,
        )
        for role, reference in references.items()
    }
    if set(stored) != set(expected) or any(
        stored[role][:3] != expected[role]
        or not isinstance(stored[role][3], Mapping)
        or canonical_hash(dict(stored[role][3])) != expected[role][2]
        for role in expected
    ):
        raise FormalProtocolConflict("Formal Protocol component replay mismatch")
    calendar_payload = stored["trading_calendar_reference"][3]
    assert isinstance(calendar_payload, Mapping)
    _verify_calendar_component(protocol, calendar_payload)

    target_row = connection.execute(
        """
        SELECT protocol_hash, protocol_json
        FROM outcome_target_protocol WHERE protocol_id = %s
        """,
        (str(protocol.outcome_target_protocol_reference.artifact_id),),
    ).fetchone()
    if target_row is None or not isinstance(target_row[1], Mapping):
        raise FormalProtocolConflict("Outcome Target Protocol owner is missing")
    try:
        target_protocol = OutcomeTargetProtocol.from_canonical_dict(target_row[1])
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalProtocolConflict("Outcome Target Protocol replay failed") from exc
    target_rows = connection.execute(
        """
        SELECT target_id, target_hash, target_json
        FROM outcome_target_definition WHERE protocol_id = %s
        ORDER BY target_id
        """,
        (str(target_protocol.protocol_id),),
    ).fetchall()
    expected_targets = tuple(
        (
            str(item.target_id),
            item.target_hash,
            item.to_canonical_dict(),
        )
        for item in target_protocol.targets
    )
    if (
        target_protocol.protocol_hash != str(target_row[0])
        or protocol.outcome_target_protocol_reference.artifact_id
        != target_protocol.protocol_id
        or protocol.outcome_target_protocol_reference.content_hash
        != target_protocol.protocol_hash
        or protocol.target_references
        != tuple(
            ValidationArtifactReference("OUTCOME_TARGET", item.target_id, item.target_hash)
            for item in target_protocol.targets
        )
        or tuple((str(item[0]), str(item[1]), item[2]) for item in target_rows)
        != expected_targets
    ):
        raise FormalProtocolConflict("Outcome Target owner binding mismatch")

    evaluation_row = connection.execute(
        """
        SELECT artifact_hash, payload_json, artifact_kind,
               qualified, production_authorized
        FROM research_validation_artifact WHERE artifact_id = %s
        """,
        (str(protocol.evaluation_protocol_reference.artifact_id),),
    ).fetchone()
    if evaluation_row is None or not isinstance(evaluation_row[1], Mapping):
        raise FormalProtocolConflict("Formal Evaluation Protocol owner is missing")
    try:
        evaluation = FormalEvaluationProtocol.from_canonical_dict(
            {
                "protocol_id": str(protocol.evaluation_protocol_reference.artifact_id),
                "protocol_hash": str(evaluation_row[0]),
                **dict(evaluation_row[1]),
            }
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalProtocolConflict("Formal Evaluation Protocol replay failed") from exc
    if (
        str(evaluation_row[2]) != "FORMAL_EVALUATION_PROTOCOL"
        or bool(evaluation_row[3])
        or bool(evaluation_row[4])
        or evaluation.protocol_id
        != protocol.evaluation_protocol_reference.artifact_id
        or evaluation.protocol_hash
        != protocol.evaluation_protocol_reference.content_hash
        or evaluation.target_protocol_reference
        != protocol.outcome_target_protocol_reference
        or evaluation.locked_at > protocol.locked_at
    ):
        raise FormalProtocolConflict("Formal Evaluation owner binding mismatch")
    return protocol


__all__ = [
    "FormalProtocolConflict",
    "PostgresFormalProtocolRepository",
    "load_formal_protocol_owner",
]
