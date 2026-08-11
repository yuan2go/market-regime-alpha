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
    build_outcome_target_bound_forecast,
)
from market_regime_alpha.application.research_validation.formal_forecast_computation import (
    FormalForecastComputationReceipt,
    FormalForecastComputationRequest,
    ResolvedFormalForecastContext,
    installed_formal_forecast_executors,
)
from market_regime_alpha.application.research_validation.formal_hypothesis_family import (
    FrozenHypothesisFamily,
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
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.pit_authority import (
    FormalPITEvidenceArtifact,
    FormalPITValidationRequest,
    PITFactKind,
    PITFactRevision,
    PITValidationOutcome,
)
from market_regime_alpha.data.pit_contracts import PITArtifactKind
from market_regime_alpha.data.postgres_pit_authority import PostgresPITAuthority
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.persistence.postgres.native_repository import acquire_scope_lock
from market_regime_alpha.platform.runtime_governance import ModelVersionLineage
from market_regime_alpha.platform.governance_serialization import (
    model_registration_from_dict,
)


class FormalProtocolConflict(ValueError):
    """A frozen owner identity or Target lineage conflicted."""


@dataclass(frozen=True, slots=True)
class FormalProtocolFreezeScope:
    """References-only operator scope; PostgreSQL owns the resulting freeze time."""

    protocol_version: str
    outcome_target_protocol_reference: ValidationArtifactReference
    trading_calendar_reference: ValidationArtifactReference
    evaluation_protocol_reference: ValidationArtifactReference
    historical_sample_dataset_references: tuple[ValidationArtifactReference, ...]
    component_references: tuple[tuple[str, ValidationArtifactReference], ...]
    schema_version: str = "formal-protocol-freeze-scope/v1"

    def __post_init__(self) -> None:
        expected_roles = set(FormalResearchProtocol.__dataclass_fields__) - {
            "protocol_id",
            "protocol_hash",
            "protocol_version",
            "outcome_target_protocol_reference",
            "target_references",
            "trading_calendar_reference",
            "frozen_trading_dates",
            "evaluation_protocol_reference",
            "historical_sample_dataset_references",
            "locked_at",
            "locked_oos_reuse_policy",
            "schema_version",
        }
        actual_roles = {role for role, _reference in self.component_references}
        if actual_roles != expected_roles or len(actual_roles) != len(
            self.component_references
        ):
            raise ValueError("Formal Protocol freeze scope component roles mismatch")
        primary_historical = dict(self.component_references)[
            "historical_sample_dataset_reference"
        ]
        if (
            not self.historical_sample_dataset_references
            or self.historical_sample_dataset_references
            != tuple(
                sorted(
                    set(self.historical_sample_dataset_references),
                    key=lambda item: (str(item.artifact_id), item.content_hash),
                )
            )
            or self.historical_sample_dataset_references[0] != primary_historical
        ):
            raise ValueError("Formal Protocol freeze Historical Dataset scope mismatch")
        if self.component_references != tuple(sorted(self.component_references)):
            raise ValueError("Formal Protocol freeze scope components must be sorted")
        expected_kinds = {
            **{
                role: kind
                for role, kind in {
                    "universe_reference": "UNIVERSE",
                    "dataset_reference": "MARKET_DATA_DATASET",
                    "historical_sample_dataset_reference": "HISTORICAL_SAMPLE_DATASET",
                    "feature_reference": "FEATURE_DEFINITION_SET",
                    "factor_reference": "FACTOR_CATALOG",
                    "model_reference": "MODEL_VERSION_LINEAGE",
                    "threshold_policy_reference": "THRESHOLD_POLICY",
                    "formal_oos_qualification_policy_reference": "FORMAL_OOS_QUALIFICATION_POLICY",
                    "cost_policy_reference": "SHADOW_PORTFOLIO_POLICY",
                    "calibration_policy_reference": "CALIBRATION_POLICY",
                    "strategy_policy_reference": "STRATEGY_SHADOW_POLICY",
                    "entry_holding_exit_qualification_policy_reference": "ENTRY_HOLDING_EXIT_QUALIFICATION_POLICY",
                }.items()
            }
        }
        if any(
            reference.artifact_kind != expected_kinds[role]
            for role, reference in self.component_references
        ):
            raise ValueError("Formal Protocol freeze scope component kind mismatch")
        if self.outcome_target_protocol_reference.artifact_kind != "OUTCOME_TARGET_PROTOCOL":
            raise ValueError("Formal Protocol freeze scope Target Protocol kind mismatch")
        if self.trading_calendar_reference.artifact_kind != "TRADING_CALENDAR":
            raise ValueError("Formal Protocol freeze scope Calendar kind mismatch")
        if self.evaluation_protocol_reference.artifact_kind != "FORMAL_EVALUATION_PROTOCOL":
            raise ValueError("Formal Protocol freeze scope Evaluation kind mismatch")

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> FormalProtocolFreezeScope:
        expected = {
            "schema_version",
            "protocol_version",
            "outcome_target_protocol_reference",
            "trading_calendar_reference",
            "evaluation_protocol_reference",
            "historical_sample_dataset_references",
            "component_references",
        }
        if set(value) != expected or not isinstance(value["component_references"], Mapping):
            raise ValueError("Formal Protocol freeze scope fields mismatch")
        components = value["component_references"]
        assert isinstance(components, Mapping)
        return cls(
            protocol_version=str(value["protocol_version"]),
            outcome_target_protocol_reference=ValidationArtifactReference.from_canonical_dict(
                _owner_mapping(value, "outcome_target_protocol_reference")
            ),
            trading_calendar_reference=ValidationArtifactReference.from_canonical_dict(
                _owner_mapping(value, "trading_calendar_reference")
            ),
            evaluation_protocol_reference=ValidationArtifactReference.from_canonical_dict(
                _owner_mapping(value, "evaluation_protocol_reference")
            ),
            historical_sample_dataset_references=tuple(
                ValidationArtifactReference.from_canonical_dict(_owner_mapping(item, "reference"))
                for item in _sequence_mapping(
                    value["historical_sample_dataset_references"],
                    "historical_sample_dataset_references",
                )
            ),
            component_references=tuple(
                sorted(
                    (
                        str(role),
                        ValidationArtifactReference.from_canonical_dict(
                            _owner_mapping(components, str(role))
                        ),
                    )
                    for role in components
                )
            ),
            schema_version=str(value["schema_version"]),
        )

    @classmethod
    def from_protocol_references(
        cls, protocol: FormalResearchProtocol
    ) -> FormalProtocolFreezeScope:
        return cls(
            protocol_version=protocol.protocol_version,
            outcome_target_protocol_reference=protocol.outcome_target_protocol_reference,
            trading_calendar_reference=protocol.trading_calendar_reference,
            evaluation_protocol_reference=protocol.evaluation_protocol_reference,
            historical_sample_dataset_references=(
                protocol.historical_sample_dataset_references
            ),
            component_references=tuple(
                sorted(
                    (role, reference)
                    for role, reference in protocol.component_references().items()
                    if role != "trading_calendar_reference"
                )
            ),
        )

    def reference_map(self) -> dict[str, ValidationArtifactReference]:
        return dict(self.component_references)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "protocol_version": self.protocol_version,
            "outcome_target_protocol_reference": self.outcome_target_protocol_reference.to_canonical_dict(),
            "trading_calendar_reference": self.trading_calendar_reference.to_canonical_dict(),
            "evaluation_protocol_reference": self.evaluation_protocol_reference.to_canonical_dict(),
            "historical_sample_dataset_references": [
                {"reference": item.to_canonical_dict()}
                for item in self.historical_sample_dataset_references
            ],
            "component_references": {
                role: reference.to_canonical_dict()
                for role, reference in self.component_references
            },
        }


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

    def freeze_protocol(
        self,
        *,
        scope: FormalProtocolFreezeScope,
        actor: str,
        reason: str,
        idempotency_key: str,
    ) -> FormalResearchProtocol:
        if not actor.strip() or not reason.strip() or not idempotency_key.strip():
            raise ValueError("Formal Protocol actor, reason and idempotency key are required")
        command_payload = {
            "schema_version": "formal-protocol-freeze-command/v1",
            "scope": scope.to_canonical_dict(),
            "actor": actor,
            "reason": reason,
        }
        command_hash = canonical_hash(command_payload)

        def operation(connection: Any) -> ArtifactId:
            acquire_scope_lock(
                connection,
                namespace="formal-protocol-freeze-idempotency",
                identity=idempotency_key,
            )
            duplicate = connection.execute(
                """
                SELECT command_hash, action_kind, result_artifact_id
                FROM phase_c_formal_operator_command WHERE idempotency_key = %s
                """,
                (idempotency_key,),
            ).fetchone()
            if duplicate is not None:
                if str(duplicate[0]) != command_hash or str(duplicate[1]) != "FREEZE_FORMAL_PROTOCOL":
                    raise FormalProtocolConflict("Formal Protocol idempotency conflict")
                return ArtifactId(str(duplicate[2]))
            resolved_at = _postgres_now(connection)
            protocol = _build_protocol_from_owner_scope(
                connection, scope=scope, locked_at=resolved_at
            )
            target_protocol = _load_target_protocol_owner(connection, protocol)
            evaluation_protocol = _load_evaluation_protocol_owner(
                connection, protocol
            )
            owners = _resolve_component_owners(
                connection,
                protocol=protocol,
            )
            historical_owners = _resolve_historical_dataset_owners(
                connection, protocol=protocol
            )
            if any(
                owner.owner_recorded_at > protocol.locked_at
                for _target, _dataset, owner in historical_owners
            ):
                raise FormalProtocolConflict(
                    "Formal Protocol Historical Dataset owner was recorded after protocol lock"
                )
            _verify_protocol_model_semantics(
                protocol=protocol,
                target_protocol=target_protocol,
                owners=owners,
            )
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
            for target_reference, dataset_reference, owner in historical_owners:
                connection.execute(
                    """
                    INSERT INTO formal_research_protocol_historical_dataset(
                        formal_protocol_id, target_id, target_hash,
                        dataset_id, dataset_hash, owner_payload_hash,
                        owner_payload_json, owner_recorded_at, resolved_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (formal_protocol_id, target_id) DO NOTHING
                    """,
                    (
                        str(protocol.protocol_id),
                        str(target_reference.artifact_id),
                        target_reference.content_hash,
                        str(dataset_reference.artifact_id),
                        dataset_reference.content_hash,
                        owner.owner_payload_hash,
                        Jsonb(dict(owner.owner_payload)),
                        owner.owner_recorded_at,
                        resolved_at,
                    ),
                )
            _verify_historical_dataset_owner_rows(
                connection,
                protocol=protocol,
                owners=historical_owners,
            )
            _record_frozen_hypothesis_family(
                connection,
                protocol=protocol,
                evaluation_protocol=evaluation_protocol,
                created_at=resolved_at,
            )
            connection.execute(
                """
                INSERT INTO phase_c_formal_operator_command(
                    idempotency_key, command_hash, action_kind,
                    result_artifact_id, result_artifact_hash,
                    actor, reason, payload_json, created_at
                ) VALUES (%s, %s, 'FREEZE_FORMAL_PROTOCOL', %s, %s, %s, %s, %s, %s)
                """,
                (
                    idempotency_key,
                    command_hash,
                    str(protocol.protocol_id),
                    protocol.protocol_hash,
                    actor,
                    reason,
                    Jsonb(command_payload),
                    resolved_at,
                ),
            )
            return protocol.protocol_id

        protocol_id = self._factory.run_transaction(operation)
        return self.get_protocol(protocol_id)

    def record_protocol(self, *, protocol: FormalResearchProtocol) -> FormalResearchProtocol:
        del protocol
        raise FormalProtocolConflict(
            "caller-materialized Formal Protocol writes are closed; use freeze_protocol"
        )

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
                    production_authorized, forecast_authority,
                    payload_json, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, false, false,
                    'EXPLORATORY_CALLER_SUBMITTED', %s, %s
                )
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

    def compute_forecast(
        self,
        request: FormalForecastComputationRequest,
        *,
        actor: str,
        reason: str,
    ) -> FormalForecastComputationReceipt:
        """Compute one Formal Forecast entirely from PostgreSQL-owned inputs."""

        if not actor.strip() or not reason.strip():
            raise ValueError("Formal Forecast actor and reason are required")
        executor_set = installed_formal_forecast_executors()
        # This is the canonical PIT owner Reader. Replay happens before the write
        # transaction because PIT evidence is append-only and its reader owns the
        # complete qualification/resolution integrity check.
        pit_evidence = PostgresPITAuthority(self._factory).replay_evidence(
            request.formal_pit_evidence_id
        )
        command_hash = canonical_hash(
            {
                "schema_version": "formal-forecast-computation-command/v1",
                "request": request.to_canonical_dict(),
            }
        )

        def operation(connection: Any) -> ArtifactId:
            acquire_scope_lock(
                connection,
                namespace="formal-forecast-computation-idempotency",
                identity=request.idempotency_key,
            )
            duplicate = connection.execute(
                """
                SELECT command_hash, request_hash, receipt_id
                FROM formal_forecast_computation_command
                WHERE idempotency_key = %s
                """,
                (request.idempotency_key,),
            ).fetchone()
            if duplicate is not None:
                if (
                    str(duplicate[0]) != command_hash
                    or str(duplicate[1]) != request.request_hash
                ):
                    raise FormalProtocolConflict(
                        "Formal Forecast idempotency key conflict"
                    )
                return ArtifactId(str(duplicate[2]))

            protocol = load_formal_protocol_owner(
                connection, request.formal_protocol_id
            )
            target_protocol = _load_target_protocol_owner(connection, protocol)
            model_owner = _model_lineage_owner(connection, protocol.model_reference)
            context = _resolve_formal_forecast_context(
                connection,
                request=request,
                protocol=protocol,
                target_protocol=target_protocol,
                pit_evidence=pit_evidence,
                model_owner=model_owner,
                materialized_at=_postgres_now(connection),
            )
            executor_identity, estimates = executor_set.compute(context)
            forecast = build_outcome_target_bound_forecast(
                target_protocol=target_protocol,
                symbol=context.symbol,
                decision_time=context.decision_time,
                estimates=estimates,
                source_references=_formal_forecast_source_references(context),
                model_reference=protocol.model_reference,
                created_at=context.materialized_at,
            )
            _insert_forecast(
                connection,
                forecast=forecast,
                authority="FORMAL_OWNER_COMPUTED",
            )
            receipt = FormalForecastComputationReceipt.create(
                request=request,
                formal_protocol_reference=ValidationArtifactReference(
                    "FORMAL_RESEARCH_PROTOCOL",
                    protocol.protocol_id,
                    protocol.protocol_hash,
                ),
                formal_pit_evidence_reference=ValidationArtifactReference(
                    "FORMAL_PIT_EVIDENCE",
                    pit_evidence.evidence_id,
                    pit_evidence.evidence_hash,
                ),
                forecast_reference=ValidationArtifactReference(
                    "OUTCOME_TARGET_BOUND_FORECAST",
                    forecast.forecast_id,
                    forecast.forecast_hash,
                ),
                model_reference=protocol.model_reference,
                configuration_reference=context.configuration_reference,
                selected_fact_references=context.selected_fact_references,
                executor_identity=executor_identity,
                decision_time=context.decision_time,
                materialized_at=context.materialized_at,
            )
            connection.execute(
                """
                INSERT INTO formal_forecast_computation_receipt(
                    receipt_id, receipt_hash, request_hash,
                    formal_protocol_id, formal_pit_evidence_id, forecast_id,
                    model_id, model_hash, configuration_id,
                    configuration_hash, executor_identity, decision_time,
                    materialized_at, payload_json
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    str(receipt.receipt_id),
                    receipt.receipt_hash,
                    request.request_hash,
                    str(protocol.protocol_id),
                    str(pit_evidence.evidence_id),
                    str(forecast.forecast_id),
                    str(protocol.model_reference.artifact_id),
                    protocol.model_reference.content_hash,
                    str(context.configuration_reference.artifact_id),
                    context.configuration_reference.content_hash,
                    receipt.executor_identity,
                    receipt.decision_time,
                    receipt.materialized_at,
                    Jsonb(receipt.to_canonical_dict()),
                ),
            )
            connection.execute(
                """
                INSERT INTO formal_forecast_computation_command(
                    idempotency_key, command_hash, request_hash,
                    receipt_id, created_at
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    request.idempotency_key,
                    command_hash,
                    request.request_hash,
                    str(receipt.receipt_id),
                    receipt.materialized_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO phase_c_formal_operator_command(
                    idempotency_key, command_hash, action_kind,
                    result_artifact_id, result_artifact_hash,
                    actor, reason, payload_json, created_at
                ) VALUES (%s, %s, 'COMPUTE_FORMAL_FORECAST', %s, %s, %s, %s, %s, %s)
                """,
                (
                    f"formal-forecast:{request.idempotency_key}",
                    command_hash,
                    str(receipt.receipt_id),
                    receipt.receipt_hash,
                    actor,
                    reason,
                    Jsonb(
                        {
                            "schema_version": "formal-forecast-operator-command/v1",
                            "request": request.to_canonical_dict(),
                        }
                    ),
                    receipt.materialized_at,
                ),
            )
            _load_forecast_computation_receipt(connection, receipt.receipt_id)
            return receipt.receipt_id

        receipt_id = self._factory.run_transaction(operation)
        return self.get_forecast_computation_receipt(receipt_id)

    def get_forecast_computation_receipt(
        self, receipt_id: ArtifactId
    ) -> FormalForecastComputationReceipt:
        with self._factory.connection(read_only=True) as connection:
            return _load_forecast_computation_receipt(connection, receipt_id)

    def replay_forecast_computation(
        self,
        receipt_id: ArtifactId,
    ) -> FormalForecastComputationReceipt:
        """Recompute values and all identities from the immutable receipt."""

        executor_set = installed_formal_forecast_executors()
        receipt = self.get_forecast_computation_receipt(receipt_id)
        pit_evidence = PostgresPITAuthority(self._factory).replay_evidence(
            receipt.request.formal_pit_evidence_id
        )
        with self._factory.connection(read_only=True) as connection:
            protocol = load_formal_protocol_owner(
                connection, receipt.request.formal_protocol_id
            )
            target_protocol = _load_target_protocol_owner(connection, protocol)
            model_owner = _model_lineage_owner(connection, protocol.model_reference)
            context = _resolve_formal_forecast_context(
                connection,
                request=receipt.request,
                protocol=protocol,
                target_protocol=target_protocol,
                pit_evidence=pit_evidence,
                model_owner=model_owner,
                materialized_at=receipt.materialized_at,
            )
            executor_identity, estimates = executor_set.compute(context)
            forecast = build_outcome_target_bound_forecast(
                target_protocol=target_protocol,
                symbol=context.symbol,
                decision_time=context.decision_time,
                estimates=estimates,
                source_references=_formal_forecast_source_references(context),
                model_reference=protocol.model_reference,
                created_at=context.materialized_at,
            )
            stored_forecast = _load_forecast_owner(
                connection,
                forecast_id=receipt.forecast_reference.artifact_id,
                required_authority="FORMAL_OWNER_COMPUTED",
            )
            replayed = FormalForecastComputationReceipt.create(
                request=receipt.request,
                formal_protocol_reference=receipt.formal_protocol_reference,
                formal_pit_evidence_reference=receipt.formal_pit_evidence_reference,
                forecast_reference=ValidationArtifactReference(
                    "OUTCOME_TARGET_BOUND_FORECAST",
                    forecast.forecast_id,
                    forecast.forecast_hash,
                ),
                model_reference=receipt.model_reference,
                configuration_reference=receipt.configuration_reference,
                selected_fact_references=receipt.selected_fact_references,
                executor_identity=executor_identity,
                decision_time=context.decision_time,
                materialized_at=context.materialized_at,
            )
        if stored_forecast != forecast or replayed != receipt:
            raise FormalProtocolConflict("Formal Forecast deterministic replay failed")
        return replayed

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

    def get_hypothesis_family(
        self, formal_protocol_id: ArtifactId
    ) -> FrozenHypothesisFamily:
        with self._factory.connection(read_only=True) as connection:
            return load_frozen_hypothesis_family_owner(
                connection, formal_protocol_id=formal_protocol_id
            )


def _resolve_formal_forecast_context(
    connection: Any,
    *,
    request: FormalForecastComputationRequest,
    protocol: FormalResearchProtocol,
    target_protocol: OutcomeTargetProtocol,
    pit_evidence: FormalPITEvidenceArtifact,
    model_owner: _ComponentOwnerResolution,
    materialized_at: datetime,
) -> ResolvedFormalForecastContext:
    evidence_row = connection.execute(
        """
        SELECT evidence_hash, request_hash, request_json, payload_json,
               action_revision
        FROM formal_pit_validation_evidence WHERE evidence_id = %s
        """,
        (str(request.formal_pit_evidence_id),),
    ).fetchone()
    if (
        evidence_row is None
        or not isinstance(evidence_row[2], Mapping)
        or not isinstance(evidence_row[3], Mapping)
    ):
        raise FormalProtocolConflict("Formal PIT Evidence owner is missing")
    try:
        pit_request = FormalPITValidationRequest.from_canonical_dict(
            dict(evidence_row[2])
        )
        stored_evidence = FormalPITEvidenceArtifact.from_canonical_dict(
            dict(evidence_row[3])
        )
        lineage = ModelVersionLineage.from_canonical_dict(
            dict(_owner_mapping(model_owner.owner_payload, "lineage"))
        )
        definition = dict(
            _owner_mapping(model_owner.owner_payload, "model_definition")
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalProtocolConflict(
            "Formal Forecast owner replay failed"
        ) from exc
    if (
        stored_evidence != pit_evidence
        or str(evidence_row[0]) != pit_evidence.evidence_hash
        or str(evidence_row[1]) != pit_request.request_hash
        or pit_request.request_hash != pit_evidence.request_hash
        or pit_evidence.outcome is not PITValidationOutcome.SATISFIED
        or pit_evidence.rejection_codes
    ):
        raise FormalProtocolConflict(
            "Formal Forecast requires satisfied immutable Formal PIT Evidence"
        )
    if request.symbol not in pit_request.symbols:
        raise FormalProtocolConflict("Formal Forecast symbol is outside PIT scope")
    _verify_forecast_lineage(
        protocol=protocol,
        pit_request=pit_request,
        model_lineage=lineage,
    )
    _verify_formal_pit_clock_authority(
        connection,
        evidence_action_revision=int(evidence_row[4]),
        evidence=pit_evidence,
    )
    _verify_forecast_pit_fact_scope(
        connection,
        protocol=protocol,
        pit_request=pit_request,
        evidence=pit_evidence,
    )
    selected = tuple(
        ValidationArtifactReference("PIT_FACT_REVISION", item_id, digest)
        for item_id, digest in pit_evidence.selected_fact_references
    )
    owners = _resolve_component_owners(connection, protocol=protocol)
    fact_payloads = tuple(
        dict(
            connection.execute(
                "SELECT payload_json FROM pit_fact_revision WHERE fact_id = %s",
                (str(reference.artifact_id),),
            ).fetchone()[0]
        )
        for reference in selected
    )
    return ResolvedFormalForecastContext(
        protocol=protocol,
        target_protocol=target_protocol,
        formal_pit_evidence=pit_evidence,
        model_lineage=lineage,
        model_definition_payload=definition,
        configuration_reference=ValidationArtifactReference(
            "CONFIGURATION",
            lineage.configuration.artifact_id,
            lineage.configuration.content_hash,
        ),
        component_owner_payloads=tuple(
            (role, dict(owner.owner_payload)) for role, owner in sorted(owners.items())
        ),
        selected_fact_references=selected,
        selected_fact_payloads=fact_payloads,
        symbol=request.symbol,
        decision_time=pit_request.decision_time,
        materialized_at=materialized_at,
    )


def _verify_forecast_lineage(
    *,
    protocol: FormalResearchProtocol,
    pit_request: FormalPITValidationRequest,
    model_lineage: ModelVersionLineage,
) -> None:
    pit = pit_request.lineage
    mismatches: list[str] = []
    for label, actual, expected in (
        ("model_id", pit.model_id, model_lineage.model_id),
        ("definition_hash", pit.definition_hash, model_lineage.definition_hash),
        ("model_lineage_id", pit.model_lineage_id, model_lineage.lineage_id),
        ("model_lineage_hash", pit.model_lineage_hash, model_lineage.lineage_hash),
        ("code_revision", pit.code_revision, model_lineage.code_revision),
        ("code_hash", pit.code_hash, model_lineage.code_hash),
        (
            "feature_definition_ids",
            pit.feature_definition_ids,
            tuple(str(item) for item in model_lineage.feature_definition_ids),
        ),
        (
            "dataset_id",
            pit.dataset.artifact_id,
            protocol.dataset_reference.artifact_id,
        ),
        (
            "dataset_hash",
            pit.dataset.content_hash,
            protocol.dataset_reference.content_hash,
        ),
        (
            "universe_id",
            pit.universe.artifact_id,
            protocol.universe_reference.artifact_id,
        ),
        (
            "universe_hash",
            pit.universe.content_hash,
            protocol.universe_reference.content_hash,
        ),
        (
            "configuration_id",
            pit.configuration.artifact_id,
            model_lineage.configuration.artifact_id,
        ),
        (
            "configuration_hash",
            pit.configuration.content_hash,
            model_lineage.configuration.content_hash,
        ),
        (
            "evaluation_protocol_id",
            pit.validation_protocol.artifact_id,
            protocol.evaluation_protocol_reference.artifact_id,
        ),
        (
            "evaluation_protocol_hash",
            pit.validation_protocol.content_hash,
            protocol.evaluation_protocol_reference.content_hash,
        ),
    ):
        if actual != expected:
            mismatches.append(label)
    if protocol.model_reference != ValidationArtifactReference(
        "MODEL_VERSION_LINEAGE",
        model_lineage.lineage_id,
        model_lineage.lineage_hash,
    ):
        mismatches.append("formal_protocol_model")
    if PITArtifactKind.MARKET_DATA_DATASET.value != pit.dataset.reference_kind:
        mismatches.append("dataset_kind")
    if mismatches:
        raise FormalProtocolConflict(
            "Formal Forecast PIT/Protocol lineage mismatch: "
            + ",".join(sorted(mismatches))
        )


def _verify_formal_pit_clock_authority(
    connection: Any,
    *,
    evidence_action_revision: int,
    evidence: FormalPITEvidenceArtifact,
) -> None:
    action = connection.execute(
        """
        SELECT system_time_authority
        FROM pit_authority_action WHERE authority_revision = %s
        """,
        (evidence_action_revision,),
    ).fetchone()
    if action is None or str(action[0]) != "POSTGRESQL_CLOCK":
        raise FormalProtocolConflict(
            "Formal Forecast requires PostgreSQL-clock PIT validation"
        )
    if any(
        item.system_time_authority != "POSTGRESQL_CLOCK"
        for item in evidence.selected_fact_authorities
    ):
        raise FormalProtocolConflict(
            "Formal Forecast requires PostgreSQL-clock PIT Facts"
        )
    for fact_id, fact_hash in evidence.selected_fact_references:
        row = connection.execute(
            """
            SELECT content_hash, system_time_authority
            FROM pit_fact_revision WHERE fact_id = %s
            """,
            (str(fact_id),),
        ).fetchone()
        if (
            row is None
            or str(row[0]) != fact_hash
            or str(row[1]) != "POSTGRESQL_CLOCK"
        ):
            raise FormalProtocolConflict(
                "Formal Forecast PIT Fact authority drift"
            )


def _verify_forecast_pit_fact_scope(
    connection: Any,
    *,
    protocol: FormalResearchProtocol,
    pit_request: FormalPITValidationRequest,
    evidence: FormalPITEvidenceArtifact,
) -> None:
    facts: list[PITFactRevision] = []
    for fact_id, fact_hash in evidence.selected_fact_references:
        row = connection.execute(
            "SELECT content_hash, payload_json FROM pit_fact_revision WHERE fact_id = %s",
            (str(fact_id),),
        ).fetchone()
        if row is None or str(row[0]) != fact_hash or not isinstance(row[1], Mapping):
            raise FormalProtocolConflict("Formal Forecast PIT Fact replay drift")
        try:
            fact = PITFactRevision.from_canonical_dict(dict(row[1]))
        except (KeyError, TypeError, ValueError) as exc:
            raise FormalProtocolConflict(
                "Formal Forecast PIT Fact replay failed"
            ) from exc
        if (
            fact.scope_id != pit_request.scope_id
            or fact.event_time > pit_request.decision_time
            or fact.effective_from > pit_request.decision_time
            or fact.available_at > pit_request.decision_time
            or fact.recorded_at > pit_request.decision_time
            or (
                fact.effective_to is not None
                and pit_request.decision_time >= fact.effective_to
            )
        ):
            raise FormalProtocolConflict(
                "Formal Forecast PIT Fact is not visible at DecisionTime"
            )
        facts.append(fact)
    expected_by_kind = {
        PITFactKind.MARKET_DATA: (
            protocol.dataset_reference.artifact_id,
            protocol.dataset_reference.content_hash,
        ),
        PITFactKind.UNIVERSE_MEMBERSHIP: (
            protocol.universe_reference.artifact_id,
            protocol.universe_reference.content_hash,
        ),
        PITFactKind.TRADING_CALENDAR: (
            protocol.trading_calendar_reference.artifact_id,
            protocol.trading_calendar_reference.content_hash,
        ),
    }
    for fact in facts:
        expected = expected_by_kind.get(fact.fact_kind)
        if expected is not None and (
            fact.artifact.artifact_id,
            fact.artifact.content_hash,
        ) != expected:
            raise FormalProtocolConflict(
                f"Formal Forecast {fact.fact_kind.value} owner mismatch"
            )


def _formal_forecast_source_references(
    context: ResolvedFormalForecastContext,
) -> tuple[ValidationArtifactReference, ...]:
    protocol = context.protocol
    return (
        ValidationArtifactReference(
            "FORMAL_RESEARCH_PROTOCOL",
            protocol.protocol_id,
            protocol.protocol_hash,
        ),
        ValidationArtifactReference(
            "FORMAL_PIT_EVIDENCE",
            context.formal_pit_evidence.evidence_id,
            context.formal_pit_evidence.evidence_hash,
        ),
        protocol.outcome_target_protocol_reference,
        protocol.evaluation_protocol_reference,
        context.configuration_reference,
        *protocol.component_references().values(),
        *context.selected_fact_references,
    )


def _insert_forecast(
    connection: Any,
    *,
    forecast: OutcomeTargetBoundMultiTargetForecast,
    authority: str,
) -> None:
    if authority not in {
        "EXPLORATORY_CALLER_SUBMITTED",
        "FORMAL_OWNER_COMPUTED",
    }:
        raise ValueError("unsupported Forecast authority")
    connection.execute(
        """
        INSERT INTO outcome_target_bound_forecast(
            forecast_id, forecast_hash, target_protocol_id, symbol,
            decision_time, model_id, calibrated, production_authorized,
            forecast_authority, payload_json, created_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, false, false, %s, %s, %s
        ) ON CONFLICT (forecast_id) DO NOTHING
        """,
        (
            str(forecast.forecast_id),
            forecast.forecast_hash,
            str(forecast.target_protocol_reference.artifact_id),
            forecast.symbol,
            forecast.decision_time,
            str(forecast.model_reference.artifact_id),
            authority,
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
    stored = _load_forecast_owner(
        connection,
        forecast_id=forecast.forecast_id,
        required_authority=authority,
    )
    if stored != forecast:
        raise FormalProtocolConflict("Target-bound Forecast identity conflict")


def _load_forecast_owner(
    connection: Any,
    *,
    forecast_id: ArtifactId,
    required_authority: str | None = None,
) -> OutcomeTargetBoundMultiTargetForecast:
    row = connection.execute(
        """
        SELECT payload_json, forecast_hash, calibrated,
               production_authorized, forecast_authority
        FROM outcome_target_bound_forecast WHERE forecast_id = %s
        """,
        (str(forecast_id),),
    ).fetchone()
    if row is None or not isinstance(row[0], Mapping):
        raise KeyError(str(forecast_id))
    try:
        forecast = OutcomeTargetBoundMultiTargetForecast.from_canonical_dict(
            dict(row[0])
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalProtocolConflict("Target-bound Forecast replay failed") from exc
    if (
        forecast.forecast_hash != str(row[1])
        or bool(row[2])
        or bool(row[3])
        or (
            required_authority is not None
            and str(row[4]) != required_authority
        )
    ):
        raise FormalProtocolConflict("Target-bound Forecast storage drift")
    return forecast


def _load_forecast_computation_receipt(
    connection: Any,
    receipt_id: ArtifactId,
) -> FormalForecastComputationReceipt:
    row = connection.execute(
        """
        SELECT receipt_hash, request_hash, payload_json,
               formal_protocol_id, formal_pit_evidence_id, forecast_id,
               model_id, model_hash, configuration_id, configuration_hash,
               executor_identity, decision_time, materialized_at
        FROM formal_forecast_computation_receipt WHERE receipt_id = %s
        """,
        (str(receipt_id),),
    ).fetchone()
    if row is None or not isinstance(row[2], Mapping):
        raise KeyError(str(receipt_id))
    try:
        receipt = FormalForecastComputationReceipt.from_canonical_dict(
            dict(row[2])
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalProtocolConflict(
            "Formal Forecast computation receipt replay failed"
        ) from exc
    projection = (
        receipt.receipt_hash,
        receipt.request.request_hash,
        str(receipt.formal_protocol_reference.artifact_id),
        str(receipt.formal_pit_evidence_reference.artifact_id),
        str(receipt.forecast_reference.artifact_id),
        str(receipt.model_reference.artifact_id),
        receipt.model_reference.content_hash,
        str(receipt.configuration_reference.artifact_id),
        receipt.configuration_reference.content_hash,
        receipt.executor_identity,
        receipt.decision_time,
        receipt.materialized_at,
    )
    stored_projection = (
        str(row[0]),
        str(row[1]),
        str(row[3]),
        str(row[4]),
        str(row[5]),
        str(row[6]),
        str(row[7]),
        str(row[8]),
        str(row[9]),
        str(row[10]),
        row[11],
        row[12],
    )
    if projection != stored_projection:
        raise FormalProtocolConflict(
            "Formal Forecast computation receipt storage drift"
        )
    _load_forecast_owner(
        connection,
        forecast_id=receipt.forecast_reference.artifact_id,
        required_authority="FORMAL_OWNER_COMPUTED",
    )
    return receipt


def _owner_mapping(payload: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = payload.get(name)
    if not isinstance(value, Mapping):
        raise ValueError(f"Formal Forecast owner {name} must be an object")
    return value


def _sequence_mapping(value: object, name: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(item, Mapping) for item in value
    ):
        raise ValueError(f"Formal Protocol {name} must be an object array")
    return tuple(value)


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


def _verify_protocol_model_semantics(
    *,
    protocol: FormalResearchProtocol,
    target_protocol: OutcomeTargetProtocol,
    owners: Mapping[str, _ComponentOwnerResolution],
) -> None:
    """Close cross-owner substitutions that reference-level checks cannot see."""

    try:
        model = ModelVersionLineage.from_canonical_dict(
            dict(
                _owner_mapping(
                    owners["model_reference"].owner_payload,
                    "lineage",
                )
            )
        )
        features = FeatureDefinitionSet.from_canonical_dict(
            owners["feature_reference"].owner_payload
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalProtocolConflict(
            "Formal Protocol cross-owner replay failed"
        ) from exc
    target_ids = {str(item.target_id) for item in target_protocol.targets}
    feature_ids = tuple(sorted(item.feature_id for item in features.definitions))
    model_feature_ids = tuple(sorted(str(item) for item in model.feature_definition_ids))
    evaluation_ref = (
        protocol.evaluation_protocol_reference.artifact_id,
        protocol.evaluation_protocol_reference.content_hash,
    )
    validation_refs = {
        (item.artifact_id, item.content_hash)
        for item in model.validation_protocol_refs
    }
    mismatches: list[str] = []
    if str(model.target_id) not in target_ids:
        mismatches.append("target")
    if ArtifactId(str(model.universe_contract_id)) != protocol.universe_reference.artifact_id:
        mismatches.append("universe")
    if model_feature_ids != feature_ids:
        mismatches.append("feature")
    if evaluation_ref not in validation_refs:
        mismatches.append("evaluation_protocol")
    if DataEligibility.FORMAL_RESEARCH not in model.supported_data_eligibilities:
        mismatches.append("formal_data_eligibility")
    if mismatches:
        raise FormalProtocolConflict(
            "Formal Protocol model/component lineage mismatch: "
            + ",".join(sorted(mismatches))
        )


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


def _build_protocol_from_owner_scope(
    connection: Any,
    *,
    scope: FormalProtocolFreezeScope,
    locked_at: datetime,
) -> FormalResearchProtocol:
    """Materialize Protocol identity only after exact owners and PG time resolve."""

    target_row = connection.execute(
        """
        SELECT protocol_hash, protocol_json
        FROM outcome_target_protocol WHERE protocol_id = %s
        """,
        (str(scope.outcome_target_protocol_reference.artifact_id),),
    ).fetchone()
    if target_row is None or not isinstance(target_row[1], Mapping):
        raise FormalProtocolConflict("Outcome Target Protocol owner is missing")
    evaluation_row = _research_artifact_row(
        connection, scope.evaluation_protocol_reference.artifact_id
    )
    calendar_row = connection.execute(
        """
        SELECT snapshot.payload_json, snapshot.calendar_hash
        FROM pit_artifact_authority_resolution AS resolution
        JOIN pit_trading_calendar_canonical_snapshot AS snapshot
          ON snapshot.resolution_id = resolution.resolution_id
         AND snapshot.resolution_hash = resolution.resolution_hash
        WHERE resolution.reference_kind = 'TRADING_CALENDAR'
          AND resolution.artifact_id = %s AND resolution.artifact_hash = %s
        """,
        (
            str(scope.trading_calendar_reference.artifact_id),
            scope.trading_calendar_reference.content_hash,
        ),
    ).fetchone()
    if (
        evaluation_row is None
        or calendar_row is None
        or not isinstance(calendar_row[0], Mapping)
    ):
        raise FormalProtocolConflict("Formal Protocol freeze owner is missing")
    try:
        target = OutcomeTargetProtocol.from_canonical_dict(dict(target_row[1]))
        evaluation = FormalEvaluationProtocol.from_canonical_dict(
            {
                "protocol_id": str(scope.evaluation_protocol_reference.artifact_id),
                "protocol_hash": evaluation_row[0],
                **evaluation_row[4],
            }
        )
        calendar_payload = dict(calendar_row[0])
        calendar_payload.setdefault(
            "artifact_id", str(scope.trading_calendar_reference.artifact_id)
        )
        calendar = TradingCalendarArtifact.from_canonical_dict(calendar_payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalProtocolConflict("Formal Protocol freeze owner replay failed") from exc
    if (
        target.protocol_id != scope.outcome_target_protocol_reference.artifact_id
        or target.protocol_hash != scope.outcome_target_protocol_reference.content_hash
        or str(target_row[0]) != target.protocol_hash
        or evaluation.protocol_id != scope.evaluation_protocol_reference.artifact_id
        or evaluation.protocol_hash != scope.evaluation_protocol_reference.content_hash
        or evaluation_row[1] != "FORMAL_EVALUATION_PROTOCOL"
        or evaluation_row[2]
        or evaluation_row[3]
        or calendar.artifact_id != scope.trading_calendar_reference.artifact_id
        or calendar.content_hash != scope.trading_calendar_reference.content_hash
        or str(calendar_row[1]) != calendar.content_hash
    ):
        raise FormalProtocolConflict("Formal Protocol freeze owner identity mismatch")
    references = scope.reference_map()
    return FormalResearchProtocol.create(
        protocol_version=scope.protocol_version,
        target_protocol=target,
        trading_calendar=calendar,
        evaluation_protocol=evaluation,
        universe_reference=references["universe_reference"],
        dataset_reference=references["dataset_reference"],
        historical_sample_dataset_reference=references[
            "historical_sample_dataset_reference"
        ],
        historical_sample_dataset_references=(
            scope.historical_sample_dataset_references
        ),
        feature_reference=references["feature_reference"],
        factor_reference=references["factor_reference"],
        model_reference=references["model_reference"],
        threshold_policy_reference=references["threshold_policy_reference"],
        formal_oos_qualification_policy_reference=references[
            "formal_oos_qualification_policy_reference"
        ],
        cost_policy_reference=references["cost_policy_reference"],
        calibration_policy_reference=references["calibration_policy_reference"],
        strategy_policy_reference=references["strategy_policy_reference"],
        entry_holding_exit_qualification_policy_reference=references[
            "entry_holding_exit_qualification_policy_reference"
        ],
        locked_at=locked_at,
    )


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


def _resolve_historical_dataset_owners(
    connection: Any,
    *,
    protocol: FormalResearchProtocol,
) -> tuple[
    tuple[
        ValidationArtifactReference,
        ValidationArtifactReference,
        _ComponentOwnerResolution,
    ],
    ...,
]:
    resolved: list[
        tuple[
            ValidationArtifactReference,
            ValidationArtifactReference,
            _ComponentOwnerResolution,
        ]
    ] = []
    for dataset_reference in protocol.historical_sample_dataset_references:
        owner = _research_owner(
            connection,
            dataset_reference,
            expected_kind="HISTORICAL_SAMPLE_DATASET",
            restore=HistoricalSampleDataset.from_canonical_dict,
        )
        dataset = HistoricalSampleDataset.from_canonical_dict(owner.owner_payload)
        resolved.append((dataset.target_reference, dataset_reference, owner))
    ordered = tuple(sorted(resolved, key=lambda item: str(item[0].artifact_id)))
    if tuple(item[0] for item in ordered) != protocol.target_references:
        raise FormalProtocolConflict(
            "Formal Protocol requires one Historical Sample Dataset per frozen Target"
        )
    return ordered


def _verify_historical_dataset_owner_rows(
    connection: Any,
    *,
    protocol: FormalResearchProtocol,
    owners: tuple[
        tuple[
            ValidationArtifactReference,
            ValidationArtifactReference,
            _ComponentOwnerResolution,
        ],
        ...,
    ],
) -> None:
    rows = connection.execute(
        """
        SELECT target_id, target_hash, dataset_id, dataset_hash,
               owner_payload_hash, owner_payload_json, owner_recorded_at
        FROM formal_research_protocol_historical_dataset
        WHERE formal_protocol_id = %s ORDER BY target_id
        """,
        (str(protocol.protocol_id),),
    ).fetchall()
    expected = tuple(
        (
            str(target.artifact_id),
            target.content_hash,
            str(dataset.artifact_id),
            dataset.content_hash,
            owner.owner_payload_hash,
            dict(owner.owner_payload),
            owner.owner_recorded_at,
        )
        for target, dataset, owner in owners
    )
    if tuple(tuple(row) for row in rows) != expected:
        raise FormalProtocolConflict("Formal Protocol Historical Dataset owner drift")
    if any(owner.owner_recorded_at > protocol.locked_at for _, _, owner in owners):
        raise FormalProtocolConflict(
            "Formal Protocol Historical Dataset owner was recorded after protocol lock"
        )


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
    configuration_row = connection.execute(
        """
        SELECT resolution_id, resolution_hash, payload_json, resolved_at
        FROM pit_artifact_authority_resolution
        WHERE reference_kind = 'CONFIGURATION'
          AND artifact_id = %s AND artifact_hash = %s
        """,
        (
            str(lineage.configuration.artifact_id),
            lineage.configuration.content_hash,
        ),
    ).fetchone()
    if configuration_row is None or not isinstance(configuration_row[2], Mapping):
        raise FormalProtocolConflict("Model Configuration owner is missing")
    try:
        configuration = PITArtifactAuthorityResolution.from_canonical_dict(
            dict(configuration_row[2])
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalProtocolConflict("Model Configuration owner replay failed") from exc
    if (
        configuration.resolution_id != ArtifactId(str(configuration_row[0]))
        or configuration.resolution_hash != str(configuration_row[1])
        or configuration.reference.reference_kind != "CONFIGURATION"
        or configuration.reference.artifact_id != lineage.configuration.artifact_id
        or configuration.reference.content_hash != lineage.configuration.content_hash
    ):
        raise FormalProtocolConflict("Model Configuration owner binding mismatch")
    owner_payload = {
        "schema_version": "formal-model-owner-resolution/v1",
        "lineage": lineage.to_canonical_dict(),
        "model_definition": registration.definition.canonical_payload(),
        "configuration_authority_resolution": configuration.to_canonical_dict(),
    }
    return _ComponentOwnerResolution(
        "MODEL_GOVERNANCE_AUTHORITY",
        lineage.lineage_id,
        lineage.lineage_hash,
        owner_payload,
        max(row[2], configuration_row[3]),
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


def _record_frozen_hypothesis_family(
    connection: Any,
    *,
    protocol: FormalResearchProtocol,
    evaluation_protocol: FormalEvaluationProtocol,
    created_at: datetime,
) -> FrozenHypothesisFamily:
    family = FrozenHypothesisFamily.create(
        formal_protocol_reference=ValidationArtifactReference(
            "FORMAL_RESEARCH_PROTOCOL", protocol.protocol_id, protocol.protocol_hash
        ),
        evaluation_protocol=evaluation_protocol,
        target_references=protocol.target_references,
        frozen_at=protocol.locked_at,
    )
    connection.execute(
        """
        INSERT INTO frozen_hypothesis_family(
            family_id, family_hash, formal_protocol_id, formal_protocol_hash,
            evaluation_protocol_id, evaluation_protocol_hash,
            target_protocol_id, target_protocol_hash, hypothesis_family_key,
            multiple_testing_method, payload_json, frozen_at, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (family_id) DO NOTHING
        """,
        (
            str(family.family_id),
            family.family_hash,
            str(protocol.protocol_id),
            protocol.protocol_hash,
            str(evaluation_protocol.protocol_id),
            evaluation_protocol.protocol_hash,
            str(protocol.outcome_target_protocol_reference.artifact_id),
            protocol.outcome_target_protocol_reference.content_hash,
            family.hypothesis_family_key,
            family.multiple_testing_method.value,
            Jsonb(family.to_canonical_dict()),
            family.frozen_at,
            created_at,
        ),
    )
    for ordinal, target in enumerate(family.target_references, start=1):
        connection.execute(
            """
            INSERT INTO frozen_hypothesis_family_target(
                family_id, target_protocol_id, target_id,
                target_hash, ordinal
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (family_id, target_id) DO NOTHING
            """,
            (
                str(family.family_id),
                str(family.target_protocol_reference.artifact_id),
                str(target.artifact_id),
                target.content_hash,
                ordinal,
            ),
        )
    return load_frozen_hypothesis_family_owner(
        connection, formal_protocol_id=protocol.protocol_id
    )


def load_frozen_hypothesis_family_owner(
    connection: Any,
    *,
    formal_protocol_id: ArtifactId,
) -> FrozenHypothesisFamily:
    row = connection.execute(
        """
        SELECT family_id, family_hash, formal_protocol_hash,
               evaluation_protocol_id, evaluation_protocol_hash,
               target_protocol_id, target_protocol_hash,
               payload_json, frozen_at
        FROM frozen_hypothesis_family
        WHERE formal_protocol_id = %s
        """,
        (str(formal_protocol_id),),
    ).fetchone()
    if row is None or not isinstance(row[7], Mapping):
        raise FormalProtocolConflict("Frozen Hypothesis Family owner is missing")
    try:
        family = FrozenHypothesisFamily.from_canonical_dict(dict(row[7]))
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalProtocolConflict("Frozen Hypothesis Family replay failed") from exc
    targets = connection.execute(
        """
        SELECT target_id, target_hash, ordinal
        FROM frozen_hypothesis_family_target
        WHERE family_id = %s ORDER BY ordinal
        """,
        (str(family.family_id),),
    ).fetchall()
    expected_targets = tuple(
        (str(item.artifact_id), item.content_hash, ordinal)
        for ordinal, item in enumerate(family.target_references, start=1)
    )
    if (
        family.family_id != ArtifactId(str(row[0]))
        or family.family_hash != str(row[1])
        or family.formal_protocol_reference.artifact_id != formal_protocol_id
        or family.formal_protocol_reference.content_hash != str(row[2])
        or family.evaluation_protocol_reference.artifact_id != ArtifactId(str(row[3]))
        or family.evaluation_protocol_reference.content_hash != str(row[4])
        or family.target_protocol_reference.artifact_id != ArtifactId(str(row[5]))
        or family.target_protocol_reference.content_hash != str(row[6])
        or family.frozen_at != row[8]
        or tuple((str(item[0]), str(item[1]), int(item[2])) for item in targets)
        != expected_targets
    ):
        raise FormalProtocolConflict("Frozen Hypothesis Family owner binding mismatch")
    return family


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
    historical_owners = _resolve_historical_dataset_owners(
        connection, protocol=protocol
    )
    _verify_historical_dataset_owner_rows(
        connection,
        protocol=protocol,
        owners=historical_owners,
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
    "load_frozen_hypothesis_family_owner",
    "load_formal_protocol_owner",
]
