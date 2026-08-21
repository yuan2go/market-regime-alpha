"""PostgreSQL owner resolution for Daily Alpha prediction snapshots."""

from __future__ import annotations

from typing import Any

from market_regime_alpha.application.continuous_research.daily_alpha import (
    DAILY_ALPHA_PREDICTION_KIND,
    DailyAlphaEvidenceGate,
    DailyAlphaOwnerResolver,
    DailyAlphaPredictionSnapshot,
    assess_daily_alpha_evidence_gate,
)
from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalEvidenceKind,
)
from market_regime_alpha.application.historical_corpus.postgres_evidence import (
    PostgresHistoricalEvidenceRepository,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.universe.operational import OperationalUniverseArtifact


class PostgresDailyAlphaPredictionAuthority:
    """Persist a snapshot after reloading every exact PostgreSQL source owner."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        resolver: DailyAlphaOwnerResolver,
    ) -> None:
        self._factory = factory
        self._repository = PostgresResearchValidationRepository(factory)
        self._resolver = resolver

    def put(
        self,
        snapshot: DailyAlphaPredictionSnapshot,
        *,
        universe: OperationalUniverseArtifact | None = None,
    ) -> DailyAlphaPredictionSnapshot:
        snapshot.verify_identity()
        if universe is not None:
            universe.verify_identity()
            if (
                str(universe.universe_id)
                != str(snapshot.universe_reference.artifact_id)
                or universe.content_hash
                != snapshot.universe_reference.content_hash
            ):
                raise ValueError("Daily Alpha snapshot does not bind supplied Universe")
            self._repository.record(
                artifact_id=ArtifactId(str(universe.universe_id)),
                artifact_hash=universe.content_hash,
                artifact_kind="OPERATIONAL_UNIVERSE",
                evidence_authority="ENGINEERING_ONLY",
                payload=universe.semantic_payload(),
                created_at=universe.available_at,
            )
        self._resolver.verify_snapshot_sources(snapshot)
        self._repository.record(
            artifact_id=snapshot.snapshot_id,
            artifact_hash=snapshot.snapshot_hash,
            artifact_kind=DAILY_ALPHA_PREDICTION_KIND,
            evidence_authority="ENGINEERING_ONLY",
            payload=snapshot.identity_payload(),
            created_at=snapshot.available_at,
        )
        return self.get(snapshot.snapshot_id)

    def get(self, snapshot_id: ArtifactId) -> DailyAlphaPredictionSnapshot:
        reference = self._reference(snapshot_id)
        payload = self._repository.get_artifact_payload(reference)
        snapshot = DailyAlphaPredictionSnapshot.from_canonical_dict(
            {
                "snapshot_id": str(snapshot_id),
                "snapshot_hash": reference.content_hash,
                **payload,
            }
        )
        self._resolver.verify_snapshot_sources(snapshot)
        return snapshot

    def _reference(self, snapshot_id: ArtifactId) -> ValidationArtifactReference:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT artifact_hash, artifact_kind FROM research_validation_artifact "
                "WHERE artifact_id = %s",
                (str(snapshot_id),),
            ).fetchone()
        if row is None or str(row[1]) != DAILY_ALPHA_PREDICTION_KIND:
            raise KeyError(str(snapshot_id))
        return ValidationArtifactReference(
            DAILY_ALPHA_PREDICTION_KIND, snapshot_id, str(row[0])
        )


class PostgresDailyAlphaEvidenceGateResolver:
    """Resolve the latest immutable Phase-II dependency chain from PostgreSQL."""

    def __init__(self, factory: PostgresConnectionFactory) -> None:
        self._factory = factory
        self._evidence = PostgresHistoricalEvidenceRepository(factory)

    def assess(self) -> DailyAlphaEvidenceGate:
        kinds = (
            HistoricalEvidenceKind.ALPHA_CORRECTNESS,
            HistoricalEvidenceKind.EXTERNAL_VALIDATION,
            HistoricalEvidenceKind.CANDIDATE_POLICY,
        )
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT ON (evidence_kind) evidence_id
                FROM historical_research_evidence
                WHERE evidence_kind = ANY(%s)
                ORDER BY evidence_kind, created_at DESC, evidence_id DESC
                """,
                ([item.value for item in kinds],),
            ).fetchall()
        return assess_daily_alpha_evidence_gate(
            tuple(self._evidence.get(ArtifactId(str(row[0]))) for row in rows)
        )


class DailyAlphaSourceIntegrityError(ValueError):
    """A Daily Alpha projection no longer resolves to its exact source owners."""


class PostgresDailyAlphaOwnerResolver:
    """Reload the canonical Continuous/State/Decision/Strategy owner chain."""

    def __init__(self, factory: PostgresConnectionFactory) -> None:
        self._factory = factory

    def verify_snapshot_sources(self, snapshot: DailyAlphaPredictionSnapshot) -> None:
        with self._factory.connection(read_only=True) as connection:
            self._verify_run_tick(connection, snapshot)
            self._verify_evidence(connection, snapshot)
            self._verify_summary(connection, snapshot)
            self._verify_universe(connection, snapshot.universe_reference)
            self._verify_candidate(connection, snapshot)
            self._verify_state_stages(connection, snapshot)
            self._verify_strategy(connection, snapshot)

    @staticmethod
    def _verify_run_tick(connection: Any, snapshot: DailyAlphaPredictionSnapshot) -> None:
        run = connection.execute(
            """
            SELECT command_hash, trading_date, command_json
            FROM continuous_research_run WHERE run_id = %s
            """,
            (str(snapshot.run_reference.artifact_id),),
        ).fetchone()
        if (
            run is None
            or str(run[0]) != snapshot.run_reference.content_hash
            or run[1] != snapshot.trading_date
        ):
            raise DailyAlphaSourceIntegrityError("Daily Alpha Continuous Run owner drift")
        tick = connection.execute(
            """
            SELECT tick_hash, observed_at FROM continuous_runtime_tick
            WHERE run_id = %s AND tick_id = %s
            """,
            (
                str(snapshot.run_reference.artifact_id),
                str(snapshot.tick_reference.artifact_id),
            ),
        ).fetchone()
        if (
            tick is None
            or str(tick[0]) != snapshot.tick_reference.content_hash
            or tick[1] < snapshot.decision_time
        ):
            raise DailyAlphaSourceIntegrityError("Daily Alpha Continuous Tick owner drift")
        if (
            snapshot.code_reference.artifact_id != snapshot.run_reference.artifact_id
            or snapshot.code_reference.content_hash != snapshot.run_reference.content_hash
        ):
            raise DailyAlphaSourceIntegrityError("Daily Alpha code identity is outside Run owner")

    @staticmethod
    def _verify_evidence(connection: Any, snapshot: DailyAlphaPredictionSnapshot) -> None:
        item = snapshot.provider_evidence_reference
        row = connection.execute(
            """
            SELECT commit_hash, run_id, tick_id, available_at, as_of_time
            FROM continuous_evidence_commit WHERE evidence_commit_id = %s
            """,
            (str(item.artifact_id),),
        ).fetchone()
        if (
            row is None
            or str(row[0]) != item.content_hash
            or str(row[1]) != str(snapshot.run_reference.artifact_id)
            or str(row[2]) != str(snapshot.tick_reference.artifact_id)
            or row[3] > snapshot.decision_time
            or row[4] > snapshot.decision_time
        ):
            raise DailyAlphaSourceIntegrityError("Daily Alpha Provider Evidence owner drift")

    @staticmethod
    def _verify_summary(connection: Any, snapshot: DailyAlphaPredictionSnapshot) -> None:
        summaries = tuple(
            item
            for item in snapshot.context_references
            if item.reference_kind == "RESEARCH_DAILY_SUMMARY"
        )
        if len(summaries) != 1:
            raise DailyAlphaSourceIntegrityError("Daily Alpha requires one Research Summary owner")
        summary = summaries[0]
        row = connection.execute(
            """
            SELECT content_hash, run_id, tick_id, dataset_id, dataset_hash,
                   feature_bundle_id, feature_bundle_hash, decision_time
            FROM research_daily_summary WHERE summary_id = %s
            """,
            (str(summary.artifact_id),),
        ).fetchone()
        if (
            row is None
            or str(row[0]) != summary.content_hash
            or str(row[1]) != str(snapshot.run_reference.artifact_id)
            or str(row[2]) != str(snapshot.tick_reference.artifact_id)
            or (str(row[3]), str(row[4]))
            != (
                str(snapshot.dataset_reference.artifact_id),
                snapshot.dataset_reference.content_hash,
            )
            or (str(row[5]), str(row[6]))
            not in {
                (str(item.artifact_id), item.content_hash)
                for item in snapshot.feature_references
            }
            or row[7] != snapshot.decision_time
        ):
            raise DailyAlphaSourceIntegrityError("Daily Alpha Research Summary owner drift")

    @staticmethod
    def _verify_universe(connection: Any, reference: RuntimeArtifactReference) -> None:
        if reference.reference_kind != "OPERATIONAL_UNIVERSE":
            raise DailyAlphaSourceIntegrityError(
                "Daily Alpha Universe reference kind drift"
            )
        row = connection.execute(
            """
            SELECT artifact_hash, payload_json
            FROM research_validation_artifact
            WHERE artifact_id = %s AND artifact_kind = 'OPERATIONAL_UNIVERSE'
            """,
            (str(reference.artifact_id),),
        ).fetchone()
        if (
            row is None
            or str(row[0]) != reference.content_hash
            or not isinstance(row[1], dict)
        ):
            raise DailyAlphaSourceIntegrityError("Daily Alpha Universe owner drift")
        universe = OperationalUniverseArtifact.from_canonical_dict(
            {
                "universe_id": str(reference.artifact_id),
                "content_hash": reference.content_hash,
                **row[1],
            }
        )
        universe.verify_identity()
        if (
            str(universe.universe_id) != str(reference.artifact_id)
            or universe.content_hash != reference.content_hash
        ):
            raise DailyAlphaSourceIntegrityError("Daily Alpha Universe payload drift")

    @staticmethod
    def _verify_candidate(connection: Any, snapshot: DailyAlphaPredictionSnapshot) -> None:
        row = connection.execute(
            """
            SELECT candidate_hash FROM state_runtime_candidate_artifact
            WHERE run_id = %s AND tick_id = %s AND candidate_id = %s
            """,
            (
                str(snapshot.run_reference.artifact_id),
                str(snapshot.tick_reference.artifact_id),
                str(snapshot.candidate_reference.artifact_id),
            ),
        ).fetchone()
        if row is None or str(row[0]) != snapshot.candidate_reference.content_hash:
            raise DailyAlphaSourceIntegrityError("Daily Alpha Candidate owner drift")

    @staticmethod
    def _verify_state_stages(connection: Any, snapshot: DailyAlphaPredictionSnapshot) -> None:
        rows = connection.execute(
            """
            SELECT stage, artifact_id, artifact_hash, available_at
            FROM state_research_stage_authority
            WHERE run_id = %s AND tick_id = %s
            """,
            (
                str(snapshot.run_reference.artifact_id),
                str(snapshot.tick_reference.artifact_id),
            ),
        ).fetchall()
        by_stage = {
            str(row[0]): (str(row[1]), str(row[2]), row[3]) for row in rows
        }
        required: list[tuple[str, RuntimeArtifactReference]] = []
        required.extend(
            (item.reference_kind.removeprefix("STATE_STAGE_"), item)
            for item in snapshot.context_references
            if item.reference_kind.startswith("STATE_STAGE_")
        )
        if snapshot.signal_reference is not None:
            required.append(("SIGNAL", snapshot.signal_reference))
        required.extend(
            ("FORECAST", item)
            for item in snapshot.forecast_references
            if item.reference_kind == "STATE_STAGE_FORECAST"
        )
        for stage, reference in required:
            owner = by_stage.get(stage)
            if (
                owner is None
                or owner[:2]
                != (str(reference.artifact_id), reference.content_hash)
                or owner[2] > snapshot.decision_time
            ):
                raise DailyAlphaSourceIntegrityError(
                    f"Daily Alpha {stage} State owner drift"
                )

    @staticmethod
    def _verify_strategy(connection: Any, snapshot: DailyAlphaPredictionSnapshot) -> None:
        reference = snapshot.strategy_diagnostic_reference
        row = connection.execute(
            """
            SELECT cycle_hash, parent_run_id, parent_tick_id,
                   candidate_artifact_id, candidate_artifact_hash, decision_time
            FROM multi_strategy_cycle WHERE cycle_id = %s
            """,
            (str(reference.artifact_id),),
        ).fetchone()
        if (
            row is None
            or str(row[0]) != reference.content_hash
            or str(row[1]) != str(snapshot.run_reference.artifact_id)
            or str(row[2]) != str(snapshot.tick_reference.artifact_id)
            or (str(row[3]), str(row[4]))
            != (
                str(snapshot.candidate_reference.artifact_id),
                snapshot.candidate_reference.content_hash,
            )
            or row[5] != snapshot.decision_time
        ):
            raise DailyAlphaSourceIntegrityError("Daily Alpha Strategy owner drift")


__all__ = [
    "DailyAlphaSourceIntegrityError",
    "PostgresDailyAlphaEvidenceGateResolver",
    "PostgresDailyAlphaOwnerResolver",
    "PostgresDailyAlphaPredictionAuthority",
]
