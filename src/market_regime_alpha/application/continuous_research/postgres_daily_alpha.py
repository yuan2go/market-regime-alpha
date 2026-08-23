"""PostgreSQL owner resolution for Daily Alpha prediction snapshots."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from market_regime_alpha.application.continuous_research.daily_alpha import (
    DAILY_ALPHA_PREDICTION_KIND,
    DailyAlphaEvidenceGate,
    DailyAlphaConditionalForecastProjection,
    DailyAlphaOwnerResolver,
    DailyAlphaPredictionSnapshot,
    DailyAlphaLegacySymbolProjection,
    DailyAlphaPathForecastProjection,
    assess_daily_alpha_evidence_gate,
    daily_alpha_admission_evidence_references,
)
from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.historical_corpus.postgres_evidence import (
    PostgresHistoricalEvidenceRepository,
)
from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalEvidenceKind,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.forecasting.conditional import ConditionalForecastResult
from market_regime_alpha.forecasting.path import PathForecastArtifact
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.strategies.postgres_opportunity import (
    PostgresStrategySourceAuthority,
)
from market_regime_alpha.strategies.postgres_opportunity_material import (
    PostgresConditionalForecastOwnerResolver,
)
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

    def get_for_tick(
        self,
        *,
        run_id: ArtifactId,
        tick_id: ArtifactId,
    ) -> DailyAlphaPredictionSnapshot:
        """Resolve one immutable prediction by its exact Continuous scope."""

        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT artifact_id
                FROM research_validation_artifact
                WHERE artifact_kind = %s
                  AND payload_json->'run_reference'->>'artifact_id' = %s
                  AND payload_json->'tick_reference'->>'artifact_id' = %s
                ORDER BY artifact_id
                """,
                (DAILY_ALPHA_PREDICTION_KIND, str(run_id), str(tick_id)),
            ).fetchall()
        if not rows:
            raise KeyError(f"{run_id}:{tick_id}")
        if len(rows) != 1:
            raise DailyAlphaSourceIntegrityError(
                "Daily Alpha prediction scope is ambiguous"
            )
        snapshot = self.get(ArtifactId(str(rows[0][0])))
        if (
            snapshot.run_reference.artifact_id != run_id
            or snapshot.tick_reference.artifact_id != tick_id
        ):
            raise DailyAlphaSourceIntegrityError(
                "Daily Alpha prediction exact scope drifted"
            )
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
    """Reload one explicitly configured immutable Phase-II Evidence chain."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        root_candidate_policy_reference: ValidationArtifactReference | None = None,
    ) -> None:
        self._factory = factory
        self._root = root_candidate_policy_reference
        self._evidence = PostgresHistoricalEvidenceRepository(
            factory, apply_migrations=False
        )

    def assess(self) -> DailyAlphaEvidenceGate:
        if self._root is None:
            return assess_daily_alpha_evidence_gate(
                (), root_candidate_policy_reference=None
            )
        loaded = []
        try:
            candidate = self._evidence.get(self._root.artifact_id)
            loaded.append(candidate)
            if candidate.reference != self._root:
                return DailyAlphaEvidenceGate.inactive(
                    candidate_policy_reference=self._root,
                    reason_codes=("EVIDENCE_HASH_DRIFT",),
                )
            upstream_references = daily_alpha_admission_evidence_references(
                candidate
            )
            for reference in upstream_references:
                owner = self._evidence.get(reference.artifact_id)
                loaded.append(owner)
                if owner.reference != reference:
                    return DailyAlphaEvidenceGate.inactive(
                        candidate_policy_reference=self._root,
                        reason_codes=("EVIDENCE_HASH_DRIFT",),
                    )
        except (KeyError, ValueError):
            return assess_daily_alpha_evidence_gate(
                tuple(loaded),
                root_candidate_policy_reference=self._root,
            )
        superseded = self._superseded_references(
            tuple(item.reference for item in loaded)
        )
        return assess_daily_alpha_evidence_gate(
            tuple(loaded),
            root_candidate_policy_reference=self._root,
            superseded_references=superseded,
        )

    def _superseded_references(
        self,
        references: tuple[ValidationArtifactReference, ...],
    ) -> tuple[ValidationArtifactReference, ...]:
        superseded: list[ValidationArtifactReference] = []
        with self._factory.connection(read_only=True) as connection:
            for reference in references:
                row = connection.execute(
                    """
                    SELECT 1
                    FROM historical_research_evidence invalidation
                    JOIN historical_research_evidence_source_binding source
                      ON source.evidence_id = invalidation.evidence_id
                     AND source.evidence_hash = invalidation.evidence_hash
                    WHERE invalidation.evidence_kind = 'METHODOLOGY_ASSESSMENT'
                      AND invalidation.payload_json->'payload'->>'status'
                          = 'METHODOLOGY_INVALIDATED'
                      AND source.artifact_kind = %s
                      AND source.artifact_id = %s
                      AND source.content_hash = %s
                    LIMIT 1
                    """,
                    (
                        reference.artifact_kind,
                        str(reference.artifact_id),
                        reference.content_hash,
                    ),
                ).fetchone()
                if row is not None:
                    superseded.append(reference)
        return tuple(superseded)


class PostgresDailyAlphaConditionalForecastResolver:
    """Project one uniquely owner-resolved Conditional Forecast for a Path owner."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        root_candidate_policy_reference: ValidationArtifactReference | None,
        artifact_root: Path | None = None,
    ) -> None:
        self._root = root_candidate_policy_reference
        self._evidence = PostgresHistoricalEvidenceRepository(
            factory,
            apply_migrations=False,
        )
        self._conditional = PostgresConditionalForecastOwnerResolver(factory)
        self._sources = PostgresStrategySourceAuthority(
            factory,
            artifact_root=artifact_root,
        )

    def resolve(
        self,
        *,
        path_forecast: PathForecastArtifact,
        decision_time: datetime,
    ) -> DailyAlphaConditionalForecastProjection:
        if self._root is None:
            return DailyAlphaConditionalForecastProjection.not_available(
                "CONDITIONAL_FORECAST_EVIDENCE_ROOT_NOT_CONFIGURED"
            )
        try:
            candidate = self._evidence.get(self._root.artifact_id)
            if (
                candidate.reference != self._root
                or candidate.evidence_kind
                is not HistoricalEvidenceKind.CANDIDATE_POLICY
            ):
                raise ValueError("Conditional Forecast Candidate root drifted")
            admission = candidate.payload.get("daily_alpha_admission")
            if (
                not isinstance(admission, Mapping)
                or admission.get("schema_version")
                != "daily-alpha-evidence-admission/v2"
            ):
                raise ValueError("Conditional Forecast Candidate lineage is invalid")
            context_reference = _single_context_evidence_reference(admission)
            path_reference = ValidationArtifactReference(
                "PATH_FORECAST",
                path_forecast.artifact_id,
                path_forecast.forecast.envelope.content_hash,
            )
            _evidence, result = self._conditional.resolve(
                path_reference=path_reference,
                experiment_reference=candidate.experiment_reference,
                context_evidence_reference=context_reference,
            )
            reference = RuntimeArtifactReference(
                result.reference.artifact_kind,
                result.reference.artifact_id,
                result.reference.content_hash,
            )
            owner = self._sources.reload(reference)
            if owner.available_at > decision_time:
                raise ValueError("Conditional Forecast is unavailable at DecisionTime")
            if result.status == "DATA_INSUFFICIENT":
                baseline_reference = RuntimeArtifactReference(
                    result.baseline_reference.artifact_kind,
                    result.baseline_reference.artifact_id,
                    result.baseline_reference.content_hash,
                )
                if self._sources.reload(baseline_reference).available_at > decision_time:
                    raise ValueError(
                        "Conditional Forecast baseline is unavailable at DecisionTime"
                    )
                return DailyAlphaConditionalForecastProjection(
                    availability_status="DATA_INSUFFICIENT",
                    reference=reference,
                    selected_expected_return=None,
                    prediction_uncertainty=None,
                    model_reference=None,
                    baseline_reference=baseline_reference,
                    calibration_status=result.calibration_status,
                    reason_codes=tuple(
                        sorted(
                            set(
                                result.limitations
                                or ("CONDITIONAL_FORECAST_DATA_INSUFFICIENT",)
                            )
                        )
                    ),
                )
            if (
                result.status != "AVAILABLE_FOR_RESEARCH"
                or result.model_reference is None
                or result.selected_expected_return is None
            ):
                raise ValueError("Conditional Forecast owner status is unsupported")
            model_reference = RuntimeArtifactReference(
                result.model_reference.artifact_kind,
                result.model_reference.artifact_id,
                result.model_reference.content_hash,
            )
            baseline_reference = RuntimeArtifactReference(
                result.baseline_reference.artifact_kind,
                result.baseline_reference.artifact_id,
                result.baseline_reference.content_hash,
            )
            for source in (model_reference, baseline_reference):
                if self._sources.reload(source).available_at > decision_time:
                    raise ValueError(
                        "Conditional Forecast lineage is unavailable at DecisionTime"
                    )
            return DailyAlphaConditionalForecastProjection(
                availability_status="AVAILABLE_FOR_RESEARCH",
                reference=reference,
                selected_expected_return=str(result.selected_expected_return),
                prediction_uncertainty=(
                    None
                    if result.prediction_uncertainty is None
                    else str(result.prediction_uncertainty)
                ),
                model_reference=model_reference,
                baseline_reference=baseline_reference,
                calibration_status=result.calibration_status,
                reason_codes=("CONDITIONAL_FORECAST_OWNER_RELOADED",),
            )
        except (KeyError, TypeError, ValueError):
            return DailyAlphaConditionalForecastProjection.not_available(
                "CONDITIONAL_FORECAST_OWNER_MISSING_OR_AMBIGUOUS"
            )


def _single_context_evidence_reference(
    admission: Mapping[str, Any],
) -> ValidationArtifactReference:
    raw = admission.get("context_evidence_references")
    if not isinstance(raw, list):
        raise ValueError("Conditional Forecast Context lineage is malformed")
    references = tuple(
        ValidationArtifactReference.from_canonical_dict(item)
        for item in raw
        if isinstance(item, Mapping)
    )
    if len(references) != len(raw) or len(references) != 1:
        raise ValueError("Conditional Forecast requires one admitted Context owner")
    if references[0].artifact_kind != "HISTORICAL_CONTEXT_CONDITIONAL_EVIDENCE":
        raise ValueError("Conditional Forecast Context owner kind is invalid")
    return references[0]


class DailyAlphaSourceIntegrityError(ValueError):
    """A Daily Alpha projection no longer resolves to its exact source owners."""


class DailyAlphaRelationalSourceIntegrityError(DailyAlphaSourceIntegrityError):
    """A PostgreSQL run/stage/strategy owner failed exact reload."""


class DailyAlphaTypedSourceIntegrityError(DailyAlphaSourceIntegrityError):
    """A typed Signal/Forecast owner failed exact reload."""


class DailyAlphaTypedReloadIntegrityError(DailyAlphaTypedSourceIntegrityError):
    """A typed owner could not be reloaded by exact id/hash."""


class DailyAlphaSignalReloadIntegrityError(DailyAlphaTypedReloadIntegrityError):
    """An exact Signal Snapshot could not be reloaded."""


class DailyAlphaForecastReloadIntegrityError(DailyAlphaTypedReloadIntegrityError):
    """An exact Forecast could not be reloaded."""


class DailyAlphaTypedAvailabilityIntegrityError(DailyAlphaTypedSourceIntegrityError):
    """A typed owner exceeded the DecisionTime boundary."""


class DailyAlphaTypedSymbolIntegrityError(DailyAlphaTypedSourceIntegrityError):
    """A typed owner did not contain the projected symbol."""


class DailyAlphaForecastSetIntegrityError(DailyAlphaTypedSourceIntegrityError):
    """The snapshot Forecast index and per-symbol projections diverged."""


class PostgresDailyAlphaOwnerResolver:
    """Reload the canonical Continuous/State/Decision/Strategy owner chain."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        artifact_root: Path | None = None,
    ) -> None:
        self._factory = factory
        self._sources = PostgresStrategySourceAuthority(
            factory,
            artifact_root=artifact_root,
        )

    def verify_snapshot_sources(self, snapshot: DailyAlphaPredictionSnapshot) -> None:
        try:
            with self._factory.connection(read_only=True) as connection:
                self._verify_run_tick(connection, snapshot)
                self._verify_evidence(connection, snapshot)
                self._verify_summary(connection, snapshot)
                self._verify_universe(connection, snapshot.universe_reference)
                self._verify_candidate(connection, snapshot)
                self._verify_state_stages(connection, snapshot)
                self._verify_strategy(connection, snapshot)
        except DailyAlphaSourceIntegrityError as exc:
            raise DailyAlphaRelationalSourceIntegrityError(str(exc)) from exc
        self._verify_symbol_sources(snapshot)

    def _verify_symbol_sources(self, snapshot: DailyAlphaPredictionSnapshot) -> None:
        aggregate_references = tuple(
            item
            for item in (
                snapshot.signal_reference,
                *snapshot.forecast_references,
            )
            if item is not None
            and item.reference_kind in {"SIGNAL", "FORECAST_SET"}
        )
        projected_symbols = {item.symbol for item in snapshot.symbols}
        for reference in aggregate_references:
            try:
                owner = self._sources.reload(reference)
            except (KeyError, ValueError) as exc:
                error = (
                    DailyAlphaSignalReloadIntegrityError
                    if reference.reference_kind == "SIGNAL"
                    else DailyAlphaForecastReloadIntegrityError
                )
                raise error(
                    f"Daily Alpha aggregate {reference.reference_kind} owner drift"
                ) from exc
            if owner.available_at > snapshot.decision_time:
                raise DailyAlphaTypedAvailabilityIntegrityError(
                    f"Daily Alpha {reference.reference_kind} owner is post-DecisionTime"
                )
            if owner.symbols and not projected_symbols.issubset(owner.symbols):
                raise DailyAlphaTypedSymbolIntegrityError(
                    f"Daily Alpha {reference.reference_kind} symbol drift"
                )
        raw_forecasts = {
            item
            for item in snapshot.forecast_references
            if item.reference_kind
            in {"PATH_FORECAST", "CONDITIONAL_FORECAST_RESULT"}
        }
        projected_forecasts: set[RuntimeArtifactReference] = set()
        for item in snapshot.symbols:
            references: list[RuntimeArtifactReference] = []
            if item.signal_reference is not None:
                references.append(item.signal_reference)
            if isinstance(item, DailyAlphaLegacySymbolProjection):
                if item.forecast_reference is not None:
                    references.append(item.forecast_reference)
                    projected_forecasts.add(item.forecast_reference)
            else:
                if item.path_forecast is not None:
                    references.append(item.path_forecast.reference)
                    projected_forecasts.add(item.path_forecast.reference)
                if item.conditional_forecast.reference is not None:
                    references.append(item.conditional_forecast.reference)
                    projected_forecasts.add(item.conditional_forecast.reference)
            for reference in references:
                try:
                    owner = self._sources.reload(reference)
                except (KeyError, ValueError) as exc:
                    error = (
                        DailyAlphaSignalReloadIntegrityError
                        if reference.reference_kind == "SIGNAL_SNAPSHOT"
                        else DailyAlphaForecastReloadIntegrityError
                    )
                    raise error(
                        f"Daily Alpha typed {reference.reference_kind} owner drift"
                    ) from exc
                if owner.available_at > snapshot.decision_time:
                    raise DailyAlphaTypedAvailabilityIntegrityError(
                        f"Daily Alpha {reference.reference_kind} owner is post-DecisionTime"
                    )
                if owner.symbols and item.symbol not in owner.symbols:
                    raise DailyAlphaTypedSymbolIntegrityError(
                        f"Daily Alpha {reference.reference_kind} symbol drift"
                    )
                if (
                    not isinstance(item, DailyAlphaLegacySymbolProjection)
                    and item.conditional_forecast.reference == reference
                ):
                    self._verify_conditional_projection(
                        item.conditional_forecast,
                        owner.payload,
                    )
                if (
                    not isinstance(item, DailyAlphaLegacySymbolProjection)
                    and item.path_forecast is not None
                    and item.path_forecast.reference == reference
                ):
                    self._verify_path_projection(item.path_forecast, owner.payload)
        if projected_forecasts != raw_forecasts:
            raise DailyAlphaForecastSetIntegrityError(
                "Daily Alpha raw Forecast projection/reference set drifted"
            )

    @staticmethod
    def _verify_path_projection(
        projection: DailyAlphaPathForecastProjection,
        payload: Mapping[str, Any],
    ) -> None:
        path = PathForecastArtifact.from_canonical_dict(dict(payload))
        forecast = path.forecast
        expected_quantiles = tuple(
            (
                str(item.probability),
                None if item.return_value is None else str(item.return_value),
            )
            for item in forecast.return_quantiles
        )
        if (
            projection.forecast_status != forecast.forecast_status.value
            or projection.expected_mfe
            != (None if forecast.expected_mfe is None else str(forecast.expected_mfe))
            or projection.expected_mae
            != (None if forecast.expected_mae is None else str(forecast.expected_mae))
            or projection.return_quantiles != expected_quantiles
            or projection.usable_sample_count != forecast.usable_sample_count
            or projection.excluded_sample_count != forecast.excluded_sample_count
            or projection.calibration_status != forecast.calibration_status.value
            or projection.reason_codes
            != tuple(sorted(forecast.reason_codes or ("NO_PATH_FORECAST_REASON",)))
        ):
            raise DailyAlphaForecastReloadIntegrityError(
                "Daily Alpha Path Forecast semantic projection drift"
            )

    @staticmethod
    def _verify_conditional_projection(
        projection: DailyAlphaConditionalForecastProjection,
        payload: Mapping[str, Any],
    ) -> None:
        result = ConditionalForecastResult.from_canonical_dict(payload)
        reference = RuntimeArtifactReference(
            result.reference.artifact_kind,
            result.reference.artifact_id,
            result.reference.content_hash,
        )
        if projection.reference != reference:
            raise DailyAlphaForecastReloadIntegrityError(
                "Daily Alpha Conditional Forecast identity drift"
            )
        if result.status == "DATA_INSUFFICIENT":
            expected_baseline = RuntimeArtifactReference(
                result.baseline_reference.artifact_kind,
                result.baseline_reference.artifact_id,
                result.baseline_reference.content_hash,
            )
            if (
                projection.availability_status != "DATA_INSUFFICIENT"
                or projection.selected_expected_return is not None
                or projection.prediction_uncertainty is not None
                or projection.model_reference is not None
                or projection.baseline_reference != expected_baseline
                or projection.calibration_status != result.calibration_status
                or projection.reason_codes
                != tuple(
                    sorted(
                        set(
                            result.limitations
                            or ("CONDITIONAL_FORECAST_DATA_INSUFFICIENT",)
                        )
                    )
                )
            ):
                raise DailyAlphaForecastReloadIntegrityError(
                    "Daily Alpha insufficient Conditional Forecast drift"
                )
            return
        expected_model = (
            None
            if result.model_reference is None
            else RuntimeArtifactReference(
                result.model_reference.artifact_kind,
                result.model_reference.artifact_id,
                result.model_reference.content_hash,
            )
        )
        expected_baseline = RuntimeArtifactReference(
            result.baseline_reference.artifact_kind,
            result.baseline_reference.artifact_id,
            result.baseline_reference.content_hash,
        )
        if (
            result.status != "AVAILABLE_FOR_RESEARCH"
            or projection.availability_status != result.status
            or projection.selected_expected_return
            != (
                None
                if result.selected_expected_return is None
                else str(result.selected_expected_return)
            )
            or projection.prediction_uncertainty
            != (
                None
                if result.prediction_uncertainty is None
                else str(result.prediction_uncertainty)
            )
            or projection.model_reference != expected_model
            or projection.baseline_reference != expected_baseline
            or projection.calibration_status != result.calibration_status
        ):
            raise DailyAlphaForecastReloadIntegrityError(
                "Daily Alpha Conditional Forecast semantic projection drift"
            )

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
        stage_rows = connection.execute(
            """
            SELECT stage, output_artifact_id, output_artifact_hash
            FROM research_summary_stage WHERE summary_id = %s
            """,
            (str(summary.artifact_id),),
        ).fetchall()
        outputs = {
            str(item[0]): (str(item[1]), str(item[2]))
            for item in stage_rows
            if item[1] is not None and item[2] is not None
        }
        expected_outputs = {
            **(
                {}
                if snapshot.signal_reference is None
                else {"SIGNAL": snapshot.signal_reference}
            ),
            **{
                "FORECAST": item
                for item in snapshot.forecast_references
                if item.reference_kind == "FORECAST_SET"
            },
        }
        if any(
            outputs.get(stage)
            != (str(reference.artifact_id), reference.content_hash)
            for stage, reference in expected_outputs.items()
        ):
            raise DailyAlphaSourceIntegrityError(
                "Daily Alpha Summary stage owner drift"
            )

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
        if (
            snapshot.signal_reference is not None
            and snapshot.signal_reference.reference_kind == "STATE_STAGE_SIGNAL"
        ):
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
    "DailyAlphaForecastSetIntegrityError",
    "DailyAlphaRelationalSourceIntegrityError",
    "DailyAlphaSourceIntegrityError",
    "DailyAlphaTypedSourceIntegrityError",
    "PostgresDailyAlphaEvidenceGateResolver",
    "PostgresDailyAlphaOwnerResolver",
    "PostgresDailyAlphaPredictionAuthority",
]
