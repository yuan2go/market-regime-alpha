"""PostgreSQL registry for frozen C0 Protocol and Target-bound Forecast artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Mapping

from psycopg.types.json import Jsonb

from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeTargetProtocol,
)
from market_regime_alpha.application.research_validation.formal_evaluation import (
    FormalEvaluationProtocol,
)
from market_regime_alpha.application.research_validation.calibration_qualification import (
    CalibrationQualificationPolicy,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    FormalResearchProtocol,
    OutcomeTargetBoundMultiTargetForecast,
)
from market_regime_alpha.application.research_validation.factor_research import (
    FactorResearchCatalog,
)
from market_regime_alpha.application.research_validation.formal_protocol_components import (
    FeatureDefinitionSet,
    ThresholdPolicy,
)
from market_regime_alpha.application.research_validation.phase_c_gates import (
    EntryHoldingExitQualificationPolicy,
)
from market_regime_alpha.application.research_validation.qualification import (
    FormalOOSQualificationPolicy,
)
from market_regime_alpha.application.research_validation.samples import (
    HistoricalSampleDataset,
)
from market_regime_alpha.application.strategy_shadow.contracts import (
    StrategyShadowPolicy,
    restore_strategy_shadow_artifact,
)
from market_regime_alpha.application.strategy_shadow.portfolio import (
    ShadowPortfolioPolicy,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.pit_artifact_authority import (
    PITArtifactAuthorityResolution,
)
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.platform.runtime_governance import ModelVersionLineage
from market_regime_alpha.platform.governance_serialization import (
    model_registration_from_dict,
)


class FormalProtocolConflict(ValueError):
    """A frozen owner identity or Target lineage conflicted."""


@dataclass(frozen=True, slots=True)
class _ComponentOwnerResolution:
    owner_kind: str
    owner_artifact_id: ArtifactId
    owner_artifact_hash: str
    owner_payload: Mapping[str, Any]
    owner_recorded_at: datetime

    @property
    def owner_payload_hash(self) -> str:
        return canonical_hash(dict(self.owner_payload))


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
    ) -> FormalResearchProtocol:
        def operation(connection: Any) -> None:
            target_protocol = _load_target_protocol_owner(connection, protocol)
            evaluation_protocol = _load_evaluation_protocol_owner(
                connection, protocol
            )
            owners = _resolve_component_owners(
                connection,
                protocol=protocol,
            )
            resolved_at = _postgres_now(connection)
            _verify_owner_times(
                protocol=protocol,
                owners=owners,
                resolved_at=resolved_at,
            )
            references = protocol.component_references()
            owner_references = _formal_owner_references(protocol)
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
                owner = owners[role]
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
                        Jsonb(dict(owner.owner_payload)),
                    ),
                )
            for role, reference in sorted(owner_references.items()):
                owner = owners[role]
                connection.execute(
                    """
                    INSERT INTO formal_research_protocol_component_owner_resolution(
                        protocol_id, component_role, artifact_kind,
                        artifact_id, artifact_hash, owner_kind,
                        owner_artifact_id, owner_artifact_hash,
                        owner_payload_hash, owner_payload_json,
                        owner_recorded_at, resolved_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (protocol_id, component_role) DO NOTHING
                    """,
                    (
                        str(protocol.protocol_id),
                        role,
                        reference.artifact_kind,
                        str(reference.artifact_id),
                        reference.content_hash,
                        owner.owner_kind,
                        str(owner.owner_artifact_id),
                        owner.owner_artifact_hash,
                        owner.owner_payload_hash,
                        Jsonb(dict(owner.owner_payload)),
                        owner.owner_recorded_at,
                        resolved_at,
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
                    dict(owners[role].owner_payload),
                )
                for role, reference in references.items()
            }
            if actual_components != expected_components:
                raise FormalProtocolConflict(
                    "Formal Protocol component owner binding mismatch"
                )
            _verify_stored_owner_resolutions(
                connection,
                protocol=protocol,
                owners=owners,
            )

        self._factory.run_transaction(operation)
        return self.get_protocol(protocol.protocol_id)

    def record_forecast(
        self,
        forecast: OutcomeTargetBoundMultiTargetForecast,
    ) -> OutcomeTargetBoundMultiTargetForecast:
        def operation(connection: Any) -> None:
            _model_lineage_owner(connection, forecast.model_reference)
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


def _formal_owner_references(
    protocol: FormalResearchProtocol,
) -> dict[str, ValidationArtifactReference]:
    return {
        "outcome_target_protocol_reference": (
            protocol.outcome_target_protocol_reference
        ),
        "evaluation_protocol_reference": protocol.evaluation_protocol_reference,
        **protocol.component_references(),
    }


def _load_target_protocol_owner(
    connection: Any,
    protocol: FormalResearchProtocol,
) -> OutcomeTargetProtocol:
    reference = protocol.outcome_target_protocol_reference
    row = connection.execute(
        """
        SELECT protocol_hash, protocol_json
        FROM outcome_target_protocol WHERE protocol_id = %s
        """,
        (str(reference.artifact_id),),
    ).fetchone()
    if row is None or not isinstance(row[1], Mapping):
        raise FormalProtocolConflict("Outcome Target Protocol owner is missing")
    try:
        target_protocol = OutcomeTargetProtocol.from_canonical_dict(dict(row[1]))
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
    frozen_targets = tuple(
        ValidationArtifactReference("OUTCOME_TARGET", item.target_id, item.target_hash)
        for item in target_protocol.targets
    )
    if (
        target_protocol.protocol_hash != str(row[0])
        or reference.artifact_id != target_protocol.protocol_id
        or reference.content_hash != target_protocol.protocol_hash
        or protocol.target_references != frozen_targets
        or tuple((str(item[0]), str(item[1]), item[2]) for item in target_rows)
        != expected_targets
    ):
        raise FormalProtocolConflict("Outcome Target owner binding mismatch")
    return target_protocol


def _load_evaluation_protocol_owner(
    connection: Any,
    protocol: FormalResearchProtocol,
) -> FormalEvaluationProtocol:
    reference = protocol.evaluation_protocol_reference
    row = _research_artifact_row(connection, reference.artifact_id)
    if row is None:
        raise FormalProtocolConflict("Formal Evaluation Protocol owner is missing")
    artifact_hash, artifact_kind, qualified, production_authorized, payload, _ = row
    try:
        evaluation = FormalEvaluationProtocol.from_canonical_dict(
            {
                "protocol_id": str(reference.artifact_id),
                "protocol_hash": artifact_hash,
                **payload,
            }
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalProtocolConflict("Formal Evaluation Protocol replay failed") from exc
    if (
        artifact_kind != "FORMAL_EVALUATION_PROTOCOL"
        or qualified
        or production_authorized
        or evaluation.protocol_id != reference.artifact_id
        or evaluation.protocol_hash != reference.content_hash
        or evaluation.target_protocol_reference
        != protocol.outcome_target_protocol_reference
        or evaluation.locked_at > protocol.locked_at
    ):
        raise FormalProtocolConflict("Formal Evaluation owner binding mismatch")
    return evaluation


def _resolve_component_owners(
    connection: Any,
    *,
    protocol: FormalResearchProtocol,
) -> dict[str, _ComponentOwnerResolution]:
    target_protocol = _load_target_protocol_owner(connection, protocol)
    evaluation = _load_evaluation_protocol_owner(connection, protocol)
    target_row = connection.execute(
        "SELECT created_at FROM outcome_target_protocol WHERE protocol_id = %s",
        (str(target_protocol.protocol_id),),
    ).fetchone()
    evaluation_row = _research_artifact_row(
        connection, evaluation.protocol_id
    )
    if target_row is None or evaluation_row is None:
        raise FormalProtocolConflict("Formal Protocol owner timestamp is missing")
    owners: dict[str, _ComponentOwnerResolution] = {
        "outcome_target_protocol_reference": _ComponentOwnerResolution(
            "OUTCOME_TARGET_AUTHORITY",
            target_protocol.protocol_id,
            target_protocol.protocol_hash,
            target_protocol.to_canonical_dict(),
            target_row[0],
        ),
        "evaluation_protocol_reference": _ComponentOwnerResolution(
            "RESEARCH_VALIDATION_AUTHORITY",
            evaluation.protocol_id,
            evaluation.protocol_hash,
            evaluation.to_canonical_dict(),
            evaluation_row[5],
        ),
    }
    owners["trading_calendar_reference"] = _calendar_owner(
        connection, protocol
    )
    owners["universe_reference"] = _pit_owner(
        connection, protocol.universe_reference
    )
    owners["dataset_reference"] = _pit_owner(
        connection, protocol.dataset_reference
    )
    owners["historical_sample_dataset_reference"] = _research_owner(
        connection,
        protocol.historical_sample_dataset_reference,
        expected_kind="HISTORICAL_SAMPLE_DATASET",
        restore=HistoricalSampleDataset.from_canonical_dict,
    )
    owners["feature_reference"] = _research_owner(
        connection,
        protocol.feature_reference,
        expected_kind="FEATURE_DEFINITION_SET",
        restore=FeatureDefinitionSet.from_canonical_dict,
    )
    owners["factor_reference"] = _research_owner(
        connection,
        protocol.factor_reference,
        expected_kind="FACTOR_RESEARCH_CATALOG",
        restore=FactorResearchCatalog.from_canonical_dict,
    )
    owners["threshold_policy_reference"] = _research_owner(
        connection,
        protocol.threshold_policy_reference,
        expected_kind="THRESHOLD_POLICY",
        restore=ThresholdPolicy.from_canonical_dict,
    )
    owners["model_reference"] = _model_lineage_owner(
        connection, protocol.model_reference
    )
    owners["formal_oos_qualification_policy_reference"] = _policy_owner(
        connection,
        protocol.formal_oos_qualification_policy_reference,
        table="formal_oos_qualification_policy",
        payload_column="payload_json",
        restore=FormalOOSQualificationPolicy.from_canonical_dict,
        owner_kind="FORMAL_OOS_POLICY_AUTHORITY",
    )
    owners["cost_policy_reference"] = _portfolio_policy_owner(
        connection, protocol.cost_policy_reference
    )
    owners["calibration_policy_reference"] = _policy_owner(
        connection,
        protocol.calibration_policy_reference,
        table="calibration_qualification_policy",
        payload_column="payload_json",
        restore=CalibrationQualificationPolicy.from_canonical_dict,
        owner_kind="CALIBRATION_POLICY_AUTHORITY",
    )
    owners["strategy_policy_reference"] = _strategy_policy_owner(
        connection, protocol.strategy_policy_reference
    )
    owners[
        "entry_holding_exit_qualification_policy_reference"
    ] = _policy_owner(
        connection,
        protocol.entry_holding_exit_qualification_policy_reference,
        table="entry_holding_exit_qualification_policy",
        payload_column="policy_json",
        restore=EntryHoldingExitQualificationPolicy.from_canonical_dict,
        owner_kind="ENTRY_HOLDING_EXIT_POLICY_AUTHORITY",
    )
    _verify_component_semantics(protocol, owners)
    return owners


def _research_artifact_row(
    connection: Any, artifact_id: ArtifactId
) -> tuple[str, str, bool, bool, dict[str, Any], datetime] | None:
    row = connection.execute(
        """
        SELECT artifact_hash, artifact_kind, qualified,
               production_authorized, payload_json, created_at
        FROM research_validation_artifact WHERE artifact_id = %s
        """,
        (str(artifact_id),),
    ).fetchone()
    if row is None or not isinstance(row[4], Mapping):
        return None
    return (
        str(row[0]),
        str(row[1]),
        bool(row[2]),
        bool(row[3]),
        dict(row[4]),
        row[5],
    )


def _research_owner(
    connection: Any,
    reference: ValidationArtifactReference,
    *,
    expected_kind: str,
    restore: Any,
) -> _ComponentOwnerResolution:
    row = _research_artifact_row(connection, reference.artifact_id)
    if row is None:
        raise FormalProtocolConflict(f"{expected_kind} owner is missing")
    artifact_hash, artifact_kind, qualified, production_authorized, payload, created = row
    canonical = _with_research_identity(expected_kind, reference, payload)
    try:
        restored = restore(canonical)
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalProtocolConflict(f"{expected_kind} owner replay failed") from exc
    if (
        artifact_kind != expected_kind
        or artifact_hash != reference.content_hash
        or qualified
        or production_authorized
        or canonical_hash(payload) != artifact_hash
    ):
        raise FormalProtocolConflict(f"{expected_kind} owner binding mismatch")
    _verify_restored_reference(restored, reference, expected_kind)
    if expected_kind == "FACTOR_RESEARCH_CATALOG":
        enrichment = restored.enrichment_reference
        enrichment_row = _research_artifact_row(
            connection, enrichment.artifact_id
        )
        if enrichment_row is None or (
            enrichment_row[0] != enrichment.content_hash
            or enrichment_row[1] != "PANEL_ENRICHMENT"
        ):
            raise FormalProtocolConflict("Factor Catalog enrichment owner mismatch")
    return _ComponentOwnerResolution(
        "RESEARCH_VALIDATION_AUTHORITY",
        reference.artifact_id,
        reference.content_hash,
        canonical,
        created,
    )


def _with_research_identity(
    expected_kind: str,
    reference: ValidationArtifactReference,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    identity_fields = {
        "HISTORICAL_SAMPLE_DATASET": ("dataset_id", "dataset_hash"),
        "FEATURE_DEFINITION_SET": ("definition_set_id", "definition_set_hash"),
        "FACTOR_RESEARCH_CATALOG": ("catalog_id", "catalog_hash"),
        "THRESHOLD_POLICY": ("policy_id", "policy_hash"),
    }
    id_field, hash_field = identity_fields[expected_kind]
    return {
        id_field: str(reference.artifact_id),
        hash_field: reference.content_hash,
        **dict(payload),
    }


def _verify_restored_reference(
    restored: Any,
    reference: ValidationArtifactReference,
    expected_kind: str,
) -> None:
    fields = {
        "HISTORICAL_SAMPLE_DATASET": ("dataset_id", "dataset_hash"),
        "FEATURE_DEFINITION_SET": ("definition_set_id", "definition_set_hash"),
        "FACTOR_RESEARCH_CATALOG": ("catalog_id", "catalog_hash"),
        "THRESHOLD_POLICY": ("policy_id", "policy_hash"),
    }
    id_field, hash_field = fields[expected_kind]
    if (
        getattr(restored, id_field) != reference.artifact_id
        or getattr(restored, hash_field) != reference.content_hash
    ):
        raise FormalProtocolConflict(f"{expected_kind} replay identity mismatch")


def _calendar_owner(
    connection: Any, protocol: FormalResearchProtocol
) -> _ComponentOwnerResolution:
    reference = protocol.trading_calendar_reference
    row = connection.execute(
        """
        SELECT resolution.resolution_id, resolution.resolution_hash,
               resolution.payload_json, resolution.resolved_at,
               snapshot.calendar_hash, snapshot.payload_json
        FROM pit_artifact_authority_resolution AS resolution
        JOIN pit_trading_calendar_canonical_snapshot AS snapshot
          ON snapshot.resolution_id = resolution.resolution_id
         AND snapshot.resolution_hash = resolution.resolution_hash
        WHERE resolution.reference_kind = 'TRADING_CALENDAR'
          AND resolution.artifact_id = %s
          AND resolution.artifact_hash = %s
        """,
        (str(reference.artifact_id), reference.content_hash),
    ).fetchone()
    if (
        row is None
        or not isinstance(row[2], Mapping)
        or not isinstance(row[5], Mapping)
    ):
        raise FormalProtocolConflict("Trading Calendar owner is missing")
    try:
        resolution = PITArtifactAuthorityResolution.from_canonical_dict(dict(row[2]))
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalProtocolConflict("Trading Calendar PIT owner replay failed") from exc
    calendar_payload = dict(row[5])
    _verify_calendar_component(protocol, calendar_payload)
    if (
        resolution.resolution_id != ArtifactId(str(row[0]))
        or resolution.resolution_hash != str(row[1])
        or resolution.reference.reference_kind != "TRADING_CALENDAR"
        or resolution.reference.artifact_id != reference.artifact_id
        or resolution.reference.content_hash != reference.content_hash
        or str(row[4]) != reference.content_hash
    ):
        raise FormalProtocolConflict("Trading Calendar owner binding mismatch")
    owner_payload = {
        "schema_version": "formal-pit-trading-calendar-owner/v1",
        "authority_resolution": resolution.to_canonical_dict(),
        "calendar": calendar_payload,
    }
    return _ComponentOwnerResolution(
        "PIT_ARTIFACT_AUTHORITY",
        resolution.resolution_id,
        resolution.resolution_hash,
        owner_payload,
        row[3],
    )


def _pit_owner(
    connection: Any,
    reference: ValidationArtifactReference,
) -> _ComponentOwnerResolution:
    row = connection.execute(
        """
        SELECT resolution_id, resolution_hash, payload_json, resolved_at
        FROM pit_artifact_authority_resolution
        WHERE reference_kind = %s AND artifact_id = %s AND artifact_hash = %s
        """,
        (reference.artifact_kind, str(reference.artifact_id), reference.content_hash),
    ).fetchone()
    if row is None or not isinstance(row[2], Mapping):
        raise FormalProtocolConflict(
            f"{reference.artifact_kind} PIT owner resolution is missing"
        )
    try:
        resolution = PITArtifactAuthorityResolution.from_canonical_dict(
            dict(row[2])
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalProtocolConflict("PIT owner resolution replay failed") from exc
    if (
        resolution.resolution_id != ArtifactId(str(row[0]))
        or resolution.resolution_hash != str(row[1])
        or resolution.reference.artifact_id != reference.artifact_id
        or resolution.reference.content_hash != reference.content_hash
        or resolution.reference.reference_kind != reference.artifact_kind
    ):
        raise FormalProtocolConflict("PIT owner resolution binding mismatch")
    return _ComponentOwnerResolution(
        "PIT_ARTIFACT_AUTHORITY",
        resolution.resolution_id,
        resolution.resolution_hash,
        resolution.to_canonical_dict(),
        row[3],
    )


def _model_lineage_owner(
    connection: Any,
    reference: ValidationArtifactReference,
) -> _ComponentOwnerResolution:
    row = connection.execute(
        """
        SELECT lineage.lineage_hash, lineage.payload_json, lineage.created_at,
               registration.registration_json, registration.definition_hash
        FROM model_version_lineage AS lineage
        JOIN model_registrations AS registration
          ON registration.model_id = lineage.model_id
        WHERE lineage.lineage_id = %s
        """,
        (str(reference.artifact_id),),
    ).fetchone()
    if row is None or not isinstance(row[1], Mapping):
        raise FormalProtocolConflict("Model Version Lineage owner is missing")
    try:
        lineage = ModelVersionLineage.from_canonical_dict(dict(row[1]))
        registration_payload = json.loads(str(row[3]))
        if not isinstance(registration_payload, Mapping):
            raise ValueError("Model Registration payload must be an object")
        registration = model_registration_from_dict(registration_payload)
        lineage.validate_definition(registration.definition)
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalProtocolConflict("Model Version Lineage replay failed") from exc
    if (
        lineage.lineage_id != reference.artifact_id
        or lineage.lineage_hash != reference.content_hash
        or str(row[0]) != reference.content_hash
        or str(row[4]) != lineage.definition_hash
    ):
        raise FormalProtocolConflict("Model Version Lineage binding mismatch")
    owner_payload = {
        "schema_version": "formal-model-owner-resolution/v1",
        "lineage": lineage.to_canonical_dict(),
        "model_definition": registration.definition.canonical_payload(),
    }
    return _ComponentOwnerResolution(
        "MODEL_GOVERNANCE_AUTHORITY",
        lineage.lineage_id,
        lineage.lineage_hash,
        owner_payload,
        row[2],
    )


def _policy_owner(
    connection: Any,
    reference: ValidationArtifactReference,
    *,
    table: str,
    payload_column: str,
    restore: Any,
    owner_kind: str,
) -> _ComponentOwnerResolution:
    allowed = {
        ("formal_oos_qualification_policy", "payload_json"),
        ("calibration_qualification_policy", "payload_json"),
        ("entry_holding_exit_qualification_policy", "policy_json"),
    }
    if (table, payload_column) not in allowed:
        raise AssertionError("unapproved Formal Protocol policy owner")
    row = connection.execute(
        f"SELECT policy_hash, {payload_column}, created_at FROM {table} "
        "WHERE policy_id = %s",
        (str(reference.artifact_id),),
    ).fetchone()
    if row is None or not isinstance(row[1], Mapping):
        raise FormalProtocolConflict(f"{reference.artifact_kind} owner is missing")
    payload = dict(row[1])
    try:
        policy = restore(payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalProtocolConflict(
            f"{reference.artifact_kind} owner replay failed"
        ) from exc
    if (
        policy.policy_id != reference.artifact_id
        or policy.policy_hash != reference.content_hash
        or str(row[0]) != reference.content_hash
    ):
        raise FormalProtocolConflict(
            f"{reference.artifact_kind} owner binding mismatch"
        )
    return _ComponentOwnerResolution(
        owner_kind,
        policy.policy_id,
        policy.policy_hash,
        payload,
        row[2],
    )


def _portfolio_policy_owner(
    connection: Any,
    reference: ValidationArtifactReference,
) -> _ComponentOwnerResolution:
    row = connection.execute(
        """
        SELECT policy_hash, policy_json, created_at
        FROM strategy_shadow_portfolio WHERE policy_id = %s
        """,
        (str(reference.artifact_id),),
    ).fetchone()
    if row is None or not isinstance(row[1], Mapping):
        raise FormalProtocolConflict("Shadow Portfolio Policy owner is missing")
    try:
        policy = ShadowPortfolioPolicy.from_canonical_dict(dict(row[1]))
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalProtocolConflict("Shadow Portfolio Policy replay failed") from exc
    if (
        policy.policy_id != reference.artifact_id
        or policy.policy_hash != reference.content_hash
        or str(row[0]) != reference.content_hash
    ):
        raise FormalProtocolConflict("Shadow Portfolio Policy binding mismatch")
    return _ComponentOwnerResolution(
        "SHADOW_PORTFOLIO_POLICY_AUTHORITY",
        policy.policy_id,
        policy.policy_hash,
        policy.to_canonical_dict(),
        row[2],
    )


def _strategy_policy_owner(
    connection: Any,
    reference: ValidationArtifactReference,
) -> _ComponentOwnerResolution:
    row = connection.execute(
        """
        SELECT policy_hash, policy_json, created_at
        FROM strategy_shadow_policy_authority WHERE policy_id = %s
        """,
        (str(reference.artifact_id),),
    ).fetchone()
    if row is None or not isinstance(row[1], Mapping):
        raise FormalProtocolConflict("Strategy Shadow Policy owner is missing")
    payload = dict(row[1])
    try:
        policy = restore_strategy_shadow_artifact(
            artifact_kind="POLICY",
            artifact_id=reference.artifact_id,
            artifact_hash=str(row[0]),
            payload=payload,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalProtocolConflict("Strategy Shadow Policy replay failed") from exc
    if not isinstance(policy, StrategyShadowPolicy) or (
        policy.policy_id != reference.artifact_id
        or policy.policy_hash != reference.content_hash
    ):
        raise FormalProtocolConflict("Strategy Shadow Policy binding mismatch")
    return _ComponentOwnerResolution(
        "STRATEGY_SHADOW_POLICY_AUTHORITY",
        policy.policy_id,
        policy.policy_hash,
        payload,
        row[2],
    )


def _verify_component_semantics(
    protocol: FormalResearchProtocol,
    owners: Mapping[str, _ComponentOwnerResolution],
) -> None:
    historical = HistoricalSampleDataset.from_canonical_dict(
        owners["historical_sample_dataset_reference"].owner_payload
    )
    if historical.target_reference not in protocol.target_references:
        raise FormalProtocolConflict("Historical Sample Target is not frozen")
    oos = FormalOOSQualificationPolicy.from_canonical_dict(
        owners["formal_oos_qualification_policy_reference"].owner_payload
    )
    calibration = CalibrationQualificationPolicy.from_canonical_dict(
        owners["calibration_policy_reference"].owner_payload
    )
    entry = EntryHoldingExitQualificationPolicy.from_canonical_dict(
        owners[
            "entry_holding_exit_qualification_policy_reference"
        ].owner_payload
    )
    if (
        oos.locked_at > protocol.locked_at
        or calibration.locked_at > protocol.locked_at
        or entry.locked_at > protocol.locked_at
        or calibration.target_protocol_reference
        != protocol.outcome_target_protocol_reference
        or calibration.target_reference not in protocol.target_references
        or entry.strategy_policy_reference != protocol.strategy_policy_reference
        or entry.portfolio_policy_reference != protocol.cost_policy_reference
    ):
        raise FormalProtocolConflict("Formal Protocol component semantics diverge")


def _verify_owner_times(
    *,
    protocol: FormalResearchProtocol,
    owners: Mapping[str, _ComponentOwnerResolution],
    resolved_at: datetime,
) -> None:
    if protocol.locked_at > resolved_at:
        raise FormalProtocolConflict(
            "Formal Protocol lock time cannot follow PostgreSQL owner resolution"
        )
    late_roles = tuple(
        sorted(
            role
            for role, owner in owners.items()
            if owner.owner_recorded_at > protocol.locked_at
        )
    )
    if late_roles:
        raise FormalProtocolConflict(
            "Formal Protocol component owner was recorded after protocol lock: "
            + ",".join(late_roles)
        )


def _verify_stored_owner_resolutions(
    connection: Any,
    *,
    protocol: FormalResearchProtocol,
    owners: Mapping[str, _ComponentOwnerResolution],
) -> None:
    rows = connection.execute(
        """
        SELECT component_role, artifact_kind, artifact_id, artifact_hash,
               owner_kind, owner_artifact_id, owner_artifact_hash,
               owner_payload_hash, owner_payload_json, owner_recorded_at,
               resolved_at
        FROM formal_research_protocol_component_owner_resolution
        WHERE protocol_id = %s ORDER BY component_role
        """,
        (str(protocol.protocol_id),),
    ).fetchall()
    references = _formal_owner_references(protocol)
    actual = {
        str(row[0]): tuple(row[1:8]) + (row[8], row[9])
        for row in rows
    }
    expected = {
        role: (
            reference.artifact_kind,
            str(reference.artifact_id),
            reference.content_hash,
            owners[role].owner_kind,
            str(owners[role].owner_artifact_id),
            owners[role].owner_artifact_hash,
            owners[role].owner_payload_hash,
            dict(owners[role].owner_payload),
            owners[role].owner_recorded_at,
        )
        for role, reference in references.items()
    }
    if actual != expected:
        raise FormalProtocolConflict("Formal Protocol owner resolution drift")
    resolved_times = {row[10] for row in rows}
    if len(resolved_times) != 1:
        raise FormalProtocolConflict("Formal Protocol owner resolution time drift")
    _verify_owner_times(
        protocol=protocol,
        owners=owners,
        resolved_at=next(iter(resolved_times)),
    )


def _postgres_now(connection: Any) -> datetime:
    return connection.execute(
        "SELECT date_trunc('second', clock_timestamp())"
    ).fetchone()[0]

def _verify_calendar_component(
    protocol: FormalResearchProtocol,
    payload: Mapping[str, Any],
) -> None:
    try:
        canonical = dict(payload)
        canonical.setdefault(
            "artifact_id", str(protocol.trading_calendar_reference.artifact_id)
        )
        calendar = TradingCalendarArtifact.from_canonical_dict(
            canonical
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
        for role in expected
    ):
        raise FormalProtocolConflict("Formal Protocol component replay mismatch")
    owners = _resolve_component_owners(
        connection,
        protocol=protocol,
    )
    if any(
        dict(stored[role][3]) != dict(owners[role].owner_payload)
        for role in expected
    ):
        raise FormalProtocolConflict(
            "Formal Protocol component snapshot diverges from Canonical owner"
        )
    _verify_stored_owner_resolutions(
        connection,
        protocol=protocol,
        owners=owners,
    )

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
