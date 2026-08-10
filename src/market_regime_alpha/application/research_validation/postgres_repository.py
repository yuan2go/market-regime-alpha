"""Durable PostgreSQL registry for immutable validation artifacts."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Mapping

from psycopg.types.json import Jsonb

from market_regime_alpha.application.research_validation.calibration import (
    CalibrationArtifact,
    CalibrationObservation,
    CalibrationProtocol,
)
from market_regime_alpha.application.research_validation.factor_extraction import ResearchPanelEnrichment
from market_regime_alpha.application.research_validation.samples import HistoricalSampleDataset
from market_regime_alpha.application.research_validation.samples import HistoricalSampleQualification
from market_regime_alpha.core.identity import ArtifactId, TargetId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.forecasting.path import PathForecastSample
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator

if TYPE_CHECKING:
    from market_regime_alpha.application.research_validation.free_historical_samples import (
        FreeHistoricalDecision,
        FreeHistoricalMultiHorizonOutcome,
    )


class PostgresResearchValidationRepository:
    def __init__(self, factory: PostgresConnectionFactory, *, apply_migrations: bool = True) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def record(
        self,
        *,
        artifact_id: ArtifactId,
        artifact_hash: str,
        artifact_kind: str,
        evidence_authority: str,
        payload: Mapping[str, Any],
        created_at: datetime,
        qualified: bool = False,
        production_authorized: bool = False,
    ) -> None:
        _reject_unresolved_authority_claims(payload)
        if (
            qualified
            or production_authorized
            or evidence_authority
            not in {"EXPLORATORY", "ENGINEERING_ONLY", "BLOCKED"}
        ):
            raise ValueError(
                "Research Validation recording cannot grant unresolved "
                "evidence, qualification, or Production authority"
            )
        if canonical_hash(dict(payload)) != artifact_hash:
            raise ValueError("Research Validation payload hash mismatch")

        def operation(connection: Any) -> None:
            connection.execute(
                """
                INSERT INTO research_validation_artifact(
                    artifact_id, artifact_hash, artifact_kind,
                    evidence_authority, qualified, production_authorized,
                    payload_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (artifact_id) DO NOTHING
                """,
                (
                    str(artifact_id),
                    artifact_hash,
                    artifact_kind,
                    evidence_authority,
                    qualified,
                    production_authorized,
                    Jsonb(dict(payload)),
                    created_at,
                ),
            )
            row = connection.execute(
                "SELECT artifact_hash FROM research_validation_artifact WHERE artifact_id = %s", (str(artifact_id),)
            ).fetchone()
            if row is None or str(row[0]) != artifact_hash:
                raise ValueError("Research Validation artifact identity conflict")

        self._factory.run_transaction(operation)

    def record_panel_enrichment(self, enrichment: ResearchPanelEnrichment) -> None:
        def operation(connection: Any) -> None:
            self._insert_artifact(
                connection,
                enrichment.enrichment_id,
                enrichment.enrichment_hash,
                "PANEL_ENRICHMENT",
                "EXPLORATORY",
                enrichment.identity_payload(),
                enrichment.extracted_at,
            )
            for item in enrichment.exposures:
                connection.execute(
                    """
                    INSERT INTO research_panel_factor_exposure(
                        enrichment_id, symbol, factor_family, factor_id,
                        timeframe, source_artifact_id, source_content_hash,
                        exposure_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        str(enrichment.enrichment_id),
                        item.symbol,
                        item.family.value,
                        item.factor_id,
                        item.timeframe or "",
                        str(item.source_reference.artifact_id),
                        item.source_reference.content_hash,
                        Jsonb(item.to_canonical_dict()),
                    ),
                )

        self._factory.run_transaction(operation)

    def record_sample_dataset(self, dataset: HistoricalSampleDataset) -> None:
        if dataset.qualification is not HistoricalSampleQualification.UNQUALIFIED:
            raise ValueError(
                "Historical Sample qualification requires a future "
                "owner-resolving PostgreSQL writer"
            )

        self._factory.run_transaction(
            lambda connection: self._insert_sample_dataset(connection, dataset)
        )

    def record_free_historical_pipeline(
        self,
        *,
        decisions: tuple[FreeHistoricalDecision, ...],
        outcomes: tuple[FreeHistoricalMultiHorizonOutcome, ...],
        dataset: HistoricalSampleDataset,
    ) -> None:
        """Atomically persist the retrospective evidence chain and Registry."""

        if dataset.qualification is not HistoricalSampleQualification.UNQUALIFIED:
            raise ValueError("Free Historical Sample pipeline must remain UNQUALIFIED")
        decision_ids = {item.decision_id for item in decisions}
        if any(item.decision_reference.artifact_id not in decision_ids for item in outcomes):
            raise ValueError("Free Historical Outcome omits its Decision payload")

        def operation(connection: Any) -> None:
            for decision in decisions:
                self._insert_artifact(
                    connection,
                    decision.decision_id,
                    decision.decision_hash,
                    "FREE_HISTORICAL_DECISION",
                    "EXPLORATORY",
                    decision.identity_payload(),
                    decision.retrieved_at,
                )
            for outcome in outcomes:
                self._insert_artifact(
                    connection,
                    outcome.outcome_id,
                    outcome.outcome_hash,
                    "FREE_HISTORICAL_MULTI_HORIZON_OUTCOME",
                    "EXPLORATORY",
                    outcome.identity_payload(),
                    outcome.retrieved_at,
                )
            for record in dataset.records:
                stored = connection.execute(
                    """
                    SELECT artifact_hash, artifact_kind
                    FROM research_validation_artifact
                    WHERE artifact_id = %s
                    """,
                    (str(record.outcome_reference.artifact_id),),
                ).fetchone()
                if (
                    stored is None
                    or str(stored[0]) != record.outcome_reference.content_hash
                    or str(stored[1]) != "FREE_HISTORICAL_MULTI_HORIZON_OUTCOME"
                ):
                    raise ValueError("Historical Sample Dataset omits its Outcome payload")
            self._insert_sample_dataset(connection, dataset)

        self._factory.run_transaction(operation)

    def _insert_sample_dataset(
        self,
        connection: Any,
        dataset: HistoricalSampleDataset,
    ) -> None:
        self._insert_artifact(
            connection,
            dataset.dataset_id,
            dataset.dataset_hash,
            "HISTORICAL_SAMPLE_DATASET",
            "EXPLORATORY",
            dataset.identity_payload(),
            dataset.available_at,
        )
        for item in dataset.records:
            connection.execute(
                """
                INSERT INTO historical_path_sample_record(
                    record_id, record_hash, dataset_id, sample_id, symbol,
                    target_id, sample_decision_time, available_at,
                    qualification, payload_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (record_id) DO NOTHING
                """,
                (
                    str(item.record_id),
                    item.record_hash,
                    str(dataset.dataset_id),
                    str(item.sample.sample_id),
                    item.sample.symbol,
                    str(item.sample.target_id),
                    item.sample.sample_decision_time.value,
                    item.sample.available_at.value,
                    item.qualification.value,
                    Jsonb(item.identity_payload()),
                ),
            )
            stored = connection.execute(
                "SELECT record_hash, dataset_id FROM historical_path_sample_record WHERE record_id = %s",
                (str(item.record_id),),
            ).fetchone()
            if (
                stored is None
                or str(stored[0]) != item.record_hash
                or str(stored[1]) != str(dataset.dataset_id)
            ):
                raise ValueError("Historical Sample record identity conflict")

    def find_sample_dataset(
        self,
        *,
        registry_version: str,
        target_id: TargetId,
    ) -> HistoricalSampleDataset | None:
        """Return the latest immutable build for one deterministic operator scope."""

        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT artifact_id, artifact_hash, payload_json
                FROM research_validation_artifact
                WHERE artifact_kind = 'HISTORICAL_SAMPLE_DATASET'
                ORDER BY created_at DESC, artifact_id DESC
                """
            ).fetchall()
        for row in rows:
            if not isinstance(row[2], dict):
                raise ValueError("Historical Sample Dataset payload is invalid")
            if row[2].get("registry_version") != registry_version:
                continue
            dataset = HistoricalSampleDataset.from_canonical_dict(
                {"dataset_id": str(row[0]), "dataset_hash": str(row[1]), **row[2]}
            )
            if str(dataset.target_reference.artifact_id) == str(target_id):
                return dataset
        return None

    def bind_calibration_partitions(self, artifact: CalibrationArtifact, observations: tuple[CalibrationObservation, ...]) -> None:
        def operation(connection: Any) -> None:
            for item in observations:
                connection.execute(
                    """
                    INSERT INTO calibration_partition_binding(
                        calibration_artifact_id, observation_id, partition_name
                    ) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
                    """,
                    (str(artifact.artifact_id), item.observation_id, item.partition.value),
                )

        self._factory.run_transaction(operation)

    def record_calibration_protocol(
        self,
        protocol: CalibrationProtocol,
        *,
        recorded_at: datetime,
    ) -> None:
        self._factory.run_transaction(
            lambda connection: self._insert_artifact(
                connection,
                protocol.protocol_id,
                protocol.protocol_hash,
                "CALIBRATION_PROTOCOL",
                "ENGINEERING_ONLY",
                protocol.identity_payload(),
                recorded_at,
            )
        )

    def record_calibration(
        self,
        *,
        protocol: CalibrationProtocol,
        artifact: CalibrationArtifact,
        observations: tuple[CalibrationObservation, ...],
    ) -> None:
        if artifact.calibrated or artifact.qualification_evidence is not None:
            raise ValueError(
                "Calibration qualification requires a future owner-resolving writer"
            )
        if artifact.protocol_reference.artifact_id != protocol.protocol_id or (
            artifact.protocol_reference.content_hash != protocol.protocol_hash
        ):
            raise ValueError("Calibration Artifact Protocol lineage mismatch")
        observation_ids = {item.observation_id for item in observations}
        bound_ids = {
            *artifact.fit.fit_observation_ids,
            *(
                observation_id
                for evaluation in artifact.evaluations
                for observation_id in evaluation.observation_ids
            ),
        }
        if bound_ids != observation_ids:
            raise ValueError("Calibration Artifact observation binding mismatch")

        def operation(connection: Any) -> None:
            self._insert_artifact(
                connection,
                protocol.protocol_id,
                protocol.protocol_hash,
                "CALIBRATION_PROTOCOL",
                "ENGINEERING_ONLY",
                protocol.identity_payload(),
                artifact.created_at,
            )
            self._insert_artifact(
                connection,
                artifact.fit.fit_id,
                artifact.fit.fit_hash,
                "CALIBRATION_FIT",
                "ENGINEERING_ONLY",
                artifact.fit.identity_payload(),
                artifact.fit.created_at,
            )
            for evaluation in artifact.evaluations:
                self._insert_artifact(
                    connection,
                    evaluation.evaluation_id,
                    evaluation.evaluation_hash,
                    "CALIBRATION_EVALUATION",
                    "ENGINEERING_ONLY",
                    evaluation.identity_payload(),
                    artifact.created_at,
                )
            self._insert_artifact(
                connection,
                artifact.artifact_id,
                artifact.artifact_hash,
                "CALIBRATION_ARTIFACT",
                "ENGINEERING_ONLY",
                artifact.identity_payload(),
                artifact.created_at,
            )
            for item in observations:
                connection.execute(
                    """
                    INSERT INTO calibration_partition_binding(
                        calibration_artifact_id, observation_id, partition_name
                    ) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
                    """,
                    (
                        str(artifact.artifact_id),
                        item.observation_id,
                        item.partition.value,
                    ),
                )

        self._factory.run_transaction(operation)

    def get_payload(self, artifact_id: ArtifactId) -> dict[str, Any]:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT artifact_hash, payload_json FROM research_validation_artifact WHERE artifact_id = %s", (str(artifact_id),)
            ).fetchone()
        if row is None or not isinstance(row[1], dict):
            raise KeyError(str(artifact_id))
        if canonical_hash(row[1]) != str(row[0]):
            raise ValueError("Research Validation stored payload diverged")
        return row[1]

    def read_for_forecast(
        self,
        *,
        symbol: str,
        target_id: TargetId,
        decision_time: DecisionTime,
    ) -> HistoricalSampleDataset | None:
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT artifact_id, artifact_hash, payload_json
                FROM research_validation_artifact
                WHERE artifact_kind = 'HISTORICAL_SAMPLE_DATASET'
                  AND created_at < %s
                ORDER BY created_at DESC, artifact_id DESC
                """,
                (decision_time.value,),
            ).fetchall()
        for row in rows:
            if not isinstance(row[2], dict):
                raise ValueError("Historical Sample Dataset payload is invalid")
            value = {"dataset_id": str(row[0]), "dataset_hash": str(row[1]), **row[2]}
            dataset = HistoricalSampleDataset.from_canonical_dict(value)
            if (
                dataset.available_at < decision_time.value
                and str(dataset.target_reference.artifact_id) == str(target_id)
                and any(item.sample.symbol == symbol for item in dataset.records)
            ):
                return dataset
        return None

    def load_available_samples(
        self,
        *,
        symbol: str,
        target_id: object,
        decision_time: DecisionTime,
    ) -> tuple[tuple[PathForecastSample, ...], str, tuple[str, ...]]:
        dataset = self.read_for_forecast(symbol=symbol, target_id=TargetId(str(target_id)), decision_time=decision_time)
        if dataset is None:
            return (), HistoricalSampleQualification.UNQUALIFIED.value, ("HISTORICAL_SAMPLE_DATASET_NOT_AVAILABLE",)
        samples = tuple(
            item.sample for item in dataset.records if item.sample.symbol == symbol and item.sample.available_at.value < decision_time.value
        )
        reasons = ("HISTORICAL_SAMPLE_DATASET_LOADED",) if samples else ("HISTORICAL_SAMPLES_NOT_AVAILABLE_AT_DECISION_TIME",)
        return samples, dataset.qualification.value, reasons

    @staticmethod
    def _insert_artifact(
        connection: Any,
        artifact_id: ArtifactId,
        artifact_hash: str,
        kind: str,
        authority: str,
        payload: Mapping[str, Any],
        created_at: datetime,
    ) -> None:
        _reject_unresolved_authority_claims(payload)
        if canonical_hash(dict(payload)) != artifact_hash:
            raise ValueError("Research Validation payload hash mismatch")
        connection.execute(
            """
            INSERT INTO research_validation_artifact(
                artifact_id, artifact_hash, artifact_kind, evidence_authority,
                qualified, production_authorized, payload_json, created_at
            ) VALUES (%s, %s, %s, %s, false, false, %s, %s)
            ON CONFLICT (artifact_id) DO NOTHING
            """,
            (str(artifact_id), artifact_hash, kind, authority, Jsonb(dict(payload)), created_at),
        )
        stored = connection.execute(
            "SELECT artifact_hash FROM research_validation_artifact WHERE artifact_id = %s",
            (str(artifact_id),),
        ).fetchone()
        if stored is None or str(stored[0]) != artifact_hash:
            raise ValueError("Research Validation artifact identity conflict")


def _reject_unresolved_authority_claims(payload: Mapping[str, Any]) -> None:
    for field in (
        "calibrated",
        "formal_oos",
        "formal_pit",
        "production_authorized",
        "qualified",
    ):
        if payload.get(field) is True:
            raise ValueError(
                f"Research Validation payload cannot claim unresolved {field} authority"
            )
    if payload.get("qualification_evidence") is not None:
        raise ValueError(
            "Research Validation payload cannot bind unresolved qualification evidence"
        )
