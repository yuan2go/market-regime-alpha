"""PostgreSQL index and lineage verifier for frozen Evaluation Datasets."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Callable

from psycopg.types.json import Jsonb

from market_regime_alpha.application.research_evaluation.dataset import (
    FrozenResearchEvaluationDataset,
    load_research_evaluation_dataset,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


Clock = Callable[[], datetime]


class ResearchEvaluationDatasetConflict(ValueError):
    """Dataset idempotency, Artifact or lineage conflict."""


class ResearchEvaluationDatasetIntegrityError(ValueError):
    """Stored Evaluation Dataset failed canonical restoration."""


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class PostgresResearchEvaluationDatasetRepository:
    """Register immutable files after validating every settled Outcome owner."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        clock: Clock = _now,
        apply_migrations: bool = True,
    ) -> None:
        if not isinstance(factory, PostgresConnectionFactory):
            raise TypeError("factory must be PostgresConnectionFactory")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._factory = factory
        self._clock = clock
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def register(
        self,
        dataset: FrozenResearchEvaluationDataset,
        *,
        artifact_path: Path,
    ) -> FrozenResearchEvaluationDataset:
        if load_research_evaluation_dataset(artifact_path) != dataset:
            raise ResearchEvaluationDatasetConflict(
                "Evaluation Artifact does not match Dataset"
            )
        if artifact_path.name != f"{dataset.dataset_id}.json":
            raise ResearchEvaluationDatasetConflict(
                "Evaluation Artifact locator is not content-addressed"
            )

        def operation(connection: Any) -> None:
            existing = connection.execute(
                "SELECT dataset_hash, artifact_locator "
                "FROM research_evaluation_dataset WHERE dataset_id = %s",
                (str(dataset.dataset_id),),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) != dataset.dataset_hash
                    or str(existing[1]) != str(artifact_path.resolve())
                ):
                    raise ResearchEvaluationDatasetConflict(
                        "Evaluation Dataset identity conflict"
                    )
                return
            settlement_rows: list[tuple[str, str, str]] = []
            for value in dataset.slices:
                row = connection.execute(
                    "SELECT settlement_hash, shadow_decision_id "
                    "FROM prospective_outcome_settlement WHERE settlement_id = %s",
                    (str(value.outcome.artifact_id),),
                ).fetchone()
                if row is None:
                    raise ResearchEvaluationDatasetConflict(
                        "Evaluation Dataset references an unknown Outcome"
                    )
                if (
                    str(row[0]) != value.outcome.content_hash
                    or str(row[1]) != str(value.shadow_decision.artifact_id)
                ):
                    raise ResearchEvaluationDatasetConflict(
                        "Evaluation Dataset Outcome lineage mismatch"
                    )
                settlement_rows.append(
                    (
                        str(value.outcome.artifact_id),
                        value.outcome.content_hash,
                        str(value.shadow_decision.artifact_id),
                    )
                )
            connection.execute(
                """
                INSERT INTO research_evaluation_dataset(
                    dataset_id, dataset_hash, protocol_id, protocol_hash,
                    observation_count, included_count, excluded_count,
                    missing_count, payload_json, artifact_locator, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(dataset.dataset_id),
                    dataset.dataset_hash,
                    dataset.protocol_id,
                    dataset.protocol_hash,
                    dataset.observation_count,
                    dataset.included_count,
                    dataset.excluded_count,
                    dataset.missing_count,
                    Jsonb(dataset.to_canonical_dict()),
                    str(artifact_path.resolve()),
                    dataset.created_at,
                ),
            )
            for settlement_id, digest, decision_id in settlement_rows:
                connection.execute(
                    """
                    INSERT INTO research_evaluation_dataset_settlement(
                        dataset_id, settlement_id, settlement_hash,
                        shadow_decision_id
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (
                        str(dataset.dataset_id),
                        settlement_id,
                        digest,
                        decision_id,
                    ),
                )

        self._factory.run_transaction(operation)
        return self.get(dataset.dataset_id)

    def get(self, dataset_id: ArtifactId) -> FrozenResearchEvaluationDataset:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT payload_json, dataset_hash, artifact_locator "
                "FROM research_evaluation_dataset WHERE dataset_id = %s",
                (str(dataset_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(dataset_id))
        try:
            dataset = FrozenResearchEvaluationDataset.from_canonical_dict(
                _json_object(row[0])
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ResearchEvaluationDatasetIntegrityError(
                "Evaluation Dataset failed canonical restoration"
            ) from exc
        if dataset.dataset_hash != str(row[1]):
            raise ResearchEvaluationDatasetIntegrityError(
                "Evaluation Dataset owner hash drift"
            )
        path = Path(str(row[2]))
        if load_research_evaluation_dataset(path) != dataset:
            raise ResearchEvaluationDatasetIntegrityError(
                "Evaluation Dataset Artifact drift"
            )
        return dataset

    def replay(self, dataset_id: ArtifactId) -> FrozenResearchEvaluationDataset:
        stored = self.get(dataset_id)
        rebuilt = FrozenResearchEvaluationDataset.create(
            protocol_id=stored.protocol_id,
            protocol_hash=stored.protocol_hash,
            slices=stored.slices,
            created_at=stored.created_at,
        )
        if rebuilt != stored:
            raise ResearchEvaluationDatasetIntegrityError(
                "Evaluation Dataset did not replay deterministically"
            )
        return rebuilt


def _json_object(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ResearchEvaluationDatasetIntegrityError(
            "stored Evaluation Dataset payload is not an object"
        )
    return value


__all__ = [
    "PostgresResearchEvaluationDatasetRepository",
    "ResearchEvaluationDatasetConflict",
    "ResearchEvaluationDatasetIntegrityError",
]
