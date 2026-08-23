"""PostgreSQL authority for pre-Strategy Risk and Strategy Opportunity facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Protocol

from psycopg.types.json import Jsonb

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
    HistoricalSessionComponent,
)
from market_regime_alpha.application.historical_corpus.context_conditional import (
    ContextConditionalEvaluation,
)
from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalEvidenceKind,
)
from market_regime_alpha.application.historical_corpus.postgres_evidence import (
    PostgresHistoricalEvidenceRepository,
)
from market_regime_alpha.application.controlled_operation.evidence_package import (
    load_controlled_operation_package,
)
from market_regime_alpha.application.controlled_operation.longitudinal_index import (
    resolve_artifact_root_locator,
)
from market_regime_alpha.application.decision_system.postgres_repository import (
    PostgresDecisionSystemRepository,
)
from market_regime_alpha.application.state_system.postgres_repository import (
    PostgresStateSystemRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.forecasting.artifact import load_verified_path_forecast
from market_regime_alpha.forecasting.conditional import ConditionalForecastResult
from market_regime_alpha.forecasting.path import PathForecastArtifact
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.application.research_validation.research_model import (
    ResearchModelArtifact,
)
from market_regime_alpha.research.state_system.pool import DynamicStockPoolVersion
from market_regime_alpha.signals.decimal_model import CanonicalSignalSnapshotV3
from market_regime_alpha.signals.v3 import load_verified_signal_run_v3
from market_regime_alpha.strategies.contracts import (
    StrategyOpportunityInput,
    StrategyRegistry,
    StrategyVersion,
)
from market_regime_alpha.strategies.opportunity import PreStrategyRiskState


@dataclass(frozen=True, slots=True)
class ResolvedStrategySource:
    reference: RuntimeArtifactReference
    available_at: datetime
    symbols: tuple[str, ...]
    source_references: tuple[RuntimeArtifactReference, ...]
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.available_at.tzinfo is None or self.available_at.utcoffset() is None:
            raise ValueError("Strategy source availability must be timezone-aware")
        if self.symbols != tuple(sorted(set(self.symbols))):
            raise ValueError("Strategy source symbols must be unique and sorted")
        if self.source_references != _references(self.source_references):
            raise ValueError("Strategy source lineage must be unique and sorted")


class StrategySourceAuthority(Protocol):
    def reload(
        self,
        reference: RuntimeArtifactReference,
    ) -> ResolvedStrategySource: ...


class StrategyOpportunityResolverAuthority(Protocol):
    def record_risk_state(
        self,
        state: PreStrategyRiskState,
        *,
        created_at: datetime,
    ) -> PreStrategyRiskState: ...

    def record_opportunity(
        self,
        opportunity: StrategyOpportunityInput,
        *,
        created_at: datetime,
    ) -> StrategyOpportunityInput: ...

    def resolve(
        self,
        *,
        candidate_reference: RuntimeArtifactReference,
        decision_time: datetime,
        registry: StrategyRegistry,
    ) -> tuple[StrategyOpportunityInput, ...]: ...


class PostgresStrategySourceAuthority:
    """Resolve supported canonical source owners directly from PostgreSQL."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        artifact_root: Path | None = None,
    ) -> None:
        self._factory = factory
        self._artifact_root = (
            None if artifact_root is None else artifact_root.resolve()
        )

    def reload(
        self,
        reference: RuntimeArtifactReference,
    ) -> ResolvedStrategySource:
        if reference.reference_kind == "CANDIDATE_SET":
            return self._candidate(reference)
        if reference.reference_kind.startswith("HISTORICAL_"):
            return self._historical(reference)
        if reference.reference_kind == "STRATEGY_VERSION":
            return self._strategy_version(reference)
        if reference.reference_kind == "RESEARCH_MODEL_ARTIFACT":
            return self._research_model(reference)
        if reference.reference_kind in {
            "SIGNAL",
            "SIGNAL_SNAPSHOT",
            "FORECAST_SET",
            "PATH_FORECAST",
        }:
            return self._controlled_artifact(reference)
        if reference.reference_kind in {
            "CONDITIONAL_FORECAST_RESULT",
            "CONTEXT_CONDITIONAL_EVALUATION",
        }:
            return self._phase_ii_source(reference)
        if reference.reference_kind in {
            "MANUAL_ACCOUNT_OBSERVATION",
            "ACCOUNT_RECONCILIATION",
            "DECISION_RISK_CONFIGURATION",
            "DYNAMIC_STOCK_POOL",
        }:
            return self._pre_strategy_risk_source(reference)
        raise ValueError(
            f"unsupported typed Strategy source owner: {reference.reference_kind}"
        )

    def _pre_strategy_risk_source(
        self,
        reference: RuntimeArtifactReference,
    ) -> ResolvedStrategySource:
        decision = PostgresDecisionSystemRepository(self._factory)
        if reference.reference_kind == "MANUAL_ACCOUNT_OBSERVATION":
            account = decision.get_manual_observation(reference.artifact_id)
            if account.content_hash != reference.content_hash:
                raise ValueError("Manual Account Observation owner hash drifted")
            return ResolvedStrategySource(
                reference,
                account.as_of_time,
                tuple(item.symbol for item in account.positions),
                (),
                account.to_canonical_dict(),
            )
        if reference.reference_kind == "ACCOUNT_RECONCILIATION":
            reconciliation = decision.get_reconciliation(reference.artifact_id)
            if reconciliation.content_hash != reference.content_hash:
                raise ValueError("Account Reconciliation owner hash drifted")
            return ResolvedStrategySource(
                reference,
                reconciliation.as_of_time,
                (),
                (),
                reconciliation.to_canonical_dict(),
            )
        if reference.reference_kind == "DECISION_RISK_CONFIGURATION":
            configuration = decision.get_risk_configuration(reference.artifact_id)
            if configuration.configuration_hash != reference.content_hash:
                raise ValueError("Decision Risk Configuration owner hash drifted")
            with self._factory.connection(read_only=True) as connection:
                row = connection.execute(
                    """
                    SELECT created_at FROM decision_risk_configuration
                    WHERE configuration_id = %s AND configuration_hash = %s
                    """,
                    (str(reference.artifact_id), reference.content_hash),
                ).fetchone()
            if row is None:
                raise KeyError(str(reference.artifact_id))
            return ResolvedStrategySource(
                reference,
                row[0],
                (),
                (),
                configuration.to_canonical_dict(),
            )
        payload = PostgresStateSystemRepository(
            self._factory,
            apply_migrations=False,
        ).read_pool(reference.artifact_id)
        pool = DynamicStockPoolVersion.from_canonical_dict(payload)
        if pool.pool_hash != reference.content_hash:
            raise ValueError("Dynamic Pool owner hash drifted")
        return ResolvedStrategySource(
            reference,
            pool.available_at,
            tuple(item.symbol for item in pool.members),
            (),
            pool.to_canonical_dict(),
        )

    def _candidate(
        self,
        reference: RuntimeArtifactReference,
    ) -> ResolvedStrategySource:
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT payload_json, created_at
                FROM state_runtime_candidate_artifact
                WHERE candidate_id = %s AND candidate_hash = %s
                UNION ALL
                SELECT payload_json->'payload', source_max_event_time
                FROM historical_corpus_session_component
                WHERE component_kind = 'CANDIDATE'
                  AND payload_json->'payload'->'envelope'->>'artifact_id' = %s
                  AND payload_json->'payload'->'envelope'->>'content_hash' = %s
                """,
                (
                    str(reference.artifact_id),
                    reference.content_hash,
                    str(reference.artifact_id),
                    reference.content_hash,
                ),
            ).fetchall()
        if len(rows) != 1 or not isinstance(rows[0][0], Mapping):
            raise KeyError(str(reference.artifact_id))
        candidate = CandidateSet.from_canonical_dict(dict(rows[0][0]))
        candidate.envelope.verify_payload(candidate.artifact_payload())
        actual = RuntimeArtifactReference(
            "CANDIDATE_SET",
            candidate.envelope.artifact_id,
            candidate.envelope.content_hash,
        )
        if actual != reference:
            raise ValueError("Candidate owner projection drifted")
        return ResolvedStrategySource(
            reference,
            rows[0][1],
            tuple(sorted(item.symbol for item in candidate.records)),
            (),
            candidate.to_canonical_dict(),
        )

    def _historical(
        self,
        reference: RuntimeArtifactReference,
    ) -> ResolvedStrategySource:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json, source_max_event_time
                FROM historical_corpus_session_component
                WHERE component_id = %s AND component_hash = %s
                """,
                (str(reference.artifact_id), reference.content_hash),
            ).fetchone()
        if row is None or not isinstance(row[0], Mapping):
            raise KeyError(str(reference.artifact_id))
        component = HistoricalSessionComponent.from_canonical_dict(row[0])
        actual = _runtime_reference(component.reference)
        if actual != reference:
            raise ValueError("Historical Strategy source owner drifted")
        symbols: tuple[str, ...]
        if component.component_kind is HistoricalComponentKind.CANDIDATE:
            candidate = CandidateSet.from_canonical_dict(dict(component.payload))
            symbols = tuple(item.symbol for item in candidate.records)
        elif component.component_kind is HistoricalComponentKind.SIGNAL:
            snapshots = component.payload.get("snapshots")
            if not isinstance(snapshots, list):
                raise ValueError("Historical Signal owner payload is malformed")
            symbols = tuple(
                CanonicalSignalSnapshotV3.from_canonical_dict(item).symbol
                for item in snapshots
                if isinstance(item, Mapping)
            )
            if len(symbols) != len(snapshots):
                raise ValueError("Historical Signal owner payload is malformed")
        elif component.component_kind is HistoricalComponentKind.FORECAST:
            forecasts = component.payload.get("forecasts")
            if not isinstance(forecasts, list):
                raise ValueError("Historical Forecast owner payload is malformed")
            symbols = tuple(
                PathForecastArtifact.from_canonical_dict(dict(item)).forecast.symbol
                for item in forecasts
                if isinstance(item, Mapping)
            )
            if len(symbols) != len(forecasts):
                raise ValueError("Historical Forecast owner payload is malformed")
        else:
            symbols = ()
        return ResolvedStrategySource(
            reference,
            row[1],
            tuple(sorted(symbols)),
            tuple(_runtime_reference(item) for item in component.source_references),
            component.to_canonical_dict(),
        )

    def _strategy_version(
        self,
        reference: RuntimeArtifactReference,
    ) -> ResolvedStrategySource:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json, created_at
                FROM strategy_version
                WHERE version_id = %s AND version_hash = %s
                """,
                (str(reference.artifact_id), reference.content_hash),
            ).fetchone()
        if row is None or not isinstance(row[0], Mapping):
            raise KeyError(str(reference.artifact_id))
        version = StrategyVersion.from_canonical_dict(row[0])
        if version.version_id != reference.artifact_id or version.version_hash != reference.content_hash:
            raise ValueError("Strategy Version owner drifted")
        return ResolvedStrategySource(reference, row[1], (), (), dict(row[0]))

    def _research_model(
        self,
        reference: RuntimeArtifactReference,
    ) -> ResolvedStrategySource:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json, trained_at
                FROM research_model_artifact
                WHERE artifact_id = %s AND artifact_hash = %s
                """,
                (str(reference.artifact_id), reference.content_hash),
            ).fetchone()
        if row is None or not isinstance(row[0], Mapping):
            raise KeyError(str(reference.artifact_id))
        model = ResearchModelArtifact.from_canonical_dict(row[0])
        if (
            model.artifact_id != reference.artifact_id
            or model.artifact_hash != reference.content_hash
        ):
            raise ValueError("Research Model owner drifted")
        return ResolvedStrategySource(
            reference,
            model.trained_at,
            (),
            (_runtime_reference(model.request_reference),),
            model.to_canonical_dict(),
        )

    def _phase_ii_source(
        self,
        reference: RuntimeArtifactReference,
    ) -> ResolvedStrategySource:
        with self._factory.connection(read_only=True) as connection:
            key = (
                "forecast"
                if reference.reference_kind == "CONDITIONAL_FORECAST_RESULT"
                else "evaluation"
            )
            id_key = (
                "result_id"
                if reference.reference_kind == "CONDITIONAL_FORECAST_RESULT"
                else "evaluation_id"
            )
            hash_key = (
                "result_hash"
                if reference.reference_kind == "CONDITIONAL_FORECAST_RESULT"
                else "evaluation_hash"
            )
            rows = connection.execute(
                """
                SELECT evidence_id FROM historical_research_evidence
                WHERE payload_json->'payload'->%s->>%s = %s
                  AND payload_json->'payload'->%s->>%s = %s
                """,
                (
                    key,
                    id_key,
                    str(reference.artifact_id),
                    key,
                    hash_key,
                    reference.content_hash,
                ),
            ).fetchall()
        if len(rows) != 1:
            raise KeyError(str(reference.artifact_id))
        evidence = PostgresHistoricalEvidenceRepository(
            self._factory,
            apply_migrations=False,
        ).get(ArtifactId(str(rows[0][0])))
        if reference.reference_kind == "CONDITIONAL_FORECAST_RESULT":
            if evidence.evidence_kind is not HistoricalEvidenceKind.CONDITIONAL_PREDICTION:
                raise ValueError("Conditional Forecast owner Evidence kind drifted")
            payload = evidence.payload.get("forecast")
            if not isinstance(payload, Mapping):
                raise ValueError("Conditional Forecast owner payload is malformed")
            forecast = ConditionalForecastResult.from_canonical_dict(payload)
            if _runtime_reference(forecast.reference) != reference:
                raise ValueError("Conditional Forecast owner drifted")
            sources = (
                forecast.configuration_reference,
                forecast.training_request_reference,
                forecast.baseline_reference,
                *((forecast.model_reference,) if forecast.model_reference else ()),
                *((forecast.inference_reference,) if forecast.inference_reference else ()),
            )
            baseline_payload = evidence.payload.get("baseline_forecast")
            if not isinstance(baseline_payload, Mapping):
                raise ValueError("Conditional Forecast baseline owner is missing")
            baseline = PathForecastArtifact.from_canonical_dict(
                dict(baseline_payload)
            )
            if _runtime_reference(forecast.baseline_reference) != RuntimeArtifactReference(
                "PATH_FORECAST",
                baseline.artifact_id,
                baseline.forecast.envelope.content_hash,
            ):
                raise ValueError("Conditional Forecast baseline owner drifted")
            symbols: tuple[str, ...] = (baseline.forecast.symbol,)
            available_at = forecast.fit_available_at or evidence.created_at
            owner_payload = forecast.to_canonical_dict()
        else:
            if evidence.evidence_kind is not HistoricalEvidenceKind.CONTEXT_CONDITIONAL:
                raise ValueError("Context owner Evidence kind drifted")
            payload = evidence.payload.get("evaluation")
            if not isinstance(payload, Mapping):
                raise ValueError("Context owner payload is malformed")
            context = ContextConditionalEvaluation.from_canonical_dict(payload)
            if _runtime_reference(context.reference) != reference:
                raise ValueError("Context owner drifted")
            sources = (context.definition_reference,)
            symbols = ()
            available_at = evidence.created_at
            owner_payload = context.to_canonical_dict()
        return ResolvedStrategySource(
            reference,
            available_at,
            symbols,
            tuple(_runtime_reference(item) for item in sources),
            owner_payload,
        )

    def _controlled_artifact(
        self,
        reference: RuntimeArtifactReference,
    ) -> ResolvedStrategySource:
        if self._artifact_root is None:
            raise ValueError("Strategy source Artifact root is not configured")
        with self._factory.connection(read_only=True) as connection:
            locators = tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT package_locator "
                    "FROM controlled_operation_package_locator"
                ).fetchall()
            )
        matches: dict[
            tuple[str, str, str],
            ResolvedStrategySource,
        ] = {}
        for locator in locators:
            package_path = resolve_artifact_root_locator(
                artifact_root=self._artifact_root,
                locator=locator,
            )
            package = load_controlled_operation_package(package_path)
            run_root = package_path.parent.parent
            if reference.reference_kind == "FORECAST_SET":
                path_items = tuple(
                    item
                    for item in package.evidence_references
                    if item.reference_type == "PATH_FORECAST"
                )
                verified_forecasts = tuple(
                    load_verified_path_forecast(run_root / item.locator)
                    for item in path_items
                )
                digest = canonical_hash(
                    {
                        "forecasts": [
                            {
                                "artifact_id": str(item.artifact.artifact_id),
                                "content_hash": (
                                    item.artifact.forecast.envelope.content_hash
                                ),
                            }
                            for item in verified_forecasts
                        ]
                    }
                )
                actual = RuntimeArtifactReference(
                    "FORECAST_SET",
                    ArtifactId(f"forecast-set:{digest[7:]}"),
                    digest,
                )
                if actual == reference and verified_forecasts:
                    matches[
                        (
                            reference.reference_kind,
                            str(reference.artifact_id),
                            reference.content_hash,
                        )
                    ] = ResolvedStrategySource(
                        reference,
                        max(
                            item.artifact.forecast.envelope.decision_time.value
                            for item in verified_forecasts
                        ),
                        tuple(
                            sorted(
                                item.artifact.forecast.symbol
                                for item in verified_forecasts
                            )
                        ),
                        _references(
                            tuple(
                                RuntimeArtifactReference(
                                    "SIGNAL_SNAPSHOT",
                                    item.artifact.signal_snapshot.envelope.artifact_id,
                                    item.artifact.signal_snapshot.envelope.content_hash,
                                )
                                for item in verified_forecasts
                            )
                        ),
                        {
                            "forecasts": [
                                item.artifact.to_canonical_dict()
                                for item in verified_forecasts
                            ]
                        },
                    )
            elif reference.reference_kind == "PATH_FORECAST":
                evidence = tuple(
                    item
                    for item in package.evidence_references
                    if item.reference_type == "PATH_FORECAST"
                    and item.object_id == reference.artifact_id
                    and item.content_hash == reference.content_hash
                )
                for item in evidence:
                    verified_path = load_verified_path_forecast(
                        run_root / item.locator
                    )
                    forecast = verified_path.artifact.forecast
                    signal = verified_path.artifact.signal_snapshot
                    resolved = ResolvedStrategySource(
                        reference,
                        forecast.envelope.decision_time.value,
                        (forecast.symbol,),
                        (
                            RuntimeArtifactReference(
                                "SIGNAL_SNAPSHOT",
                                signal.envelope.artifact_id,
                                signal.envelope.content_hash,
                            ),
                        ),
                        verified_path.artifact.to_canonical_dict(),
                    )
                    matches[(reference.reference_kind, str(reference.artifact_id), reference.content_hash)] = resolved
            else:
                signal_runs = tuple(
                    item
                    for item in package.evidence_references
                    if item.reference_type == "SIGNAL_V3"
                )
                for item in signal_runs:
                    signal_run = load_verified_signal_run_v3(run_root / item.locator)
                    if reference.reference_kind == "SIGNAL":
                        signal_run_artifact = signal_run.artifact
                        actual = RuntimeArtifactReference(
                            "SIGNAL",
                            signal_run_artifact.artifact_id,
                            signal_run_artifact.envelope.content_hash,
                        )
                        if actual == reference:
                            candidate = signal_run_artifact.candidate_set
                            matches[
                                (
                                    reference.reference_kind,
                                    str(reference.artifact_id),
                                    reference.content_hash,
                                )
                            ] = ResolvedStrategySource(
                                reference,
                                signal_run_artifact.envelope.decision_time.value,
                                tuple(
                                    sorted(
                                        snapshot.symbol
                                        for snapshot in signal_run_artifact.snapshots
                                    )
                                ),
                                (
                                    RuntimeArtifactReference(
                                        "CANDIDATE_SET",
                                        candidate.envelope.artifact_id,
                                        candidate.envelope.content_hash,
                                    ),
                                ),
                                signal_run_artifact.to_canonical_dict(),
                            )
                        continue
                    snapshots = tuple(
                        snapshot
                        for snapshot in signal_run.artifact.snapshots
                        if snapshot.artifact_id == reference.artifact_id
                        and snapshot.envelope.content_hash == reference.content_hash
                    )
                    for snapshot in snapshots:
                        candidate = signal_run.artifact.candidate_set
                        resolved = ResolvedStrategySource(
                            reference,
                            snapshot.envelope.decision_time.value,
                            (snapshot.symbol,),
                            (
                                RuntimeArtifactReference(
                                    "CANDIDATE_SET",
                                    candidate.envelope.artifact_id,
                                    candidate.envelope.content_hash,
                                ),
                            ),
                            snapshot.to_canonical_dict(),
                        )
                        matches[(reference.reference_kind, str(reference.artifact_id), reference.content_hash)] = resolved
        if len(matches) != 1:
            raise KeyError(str(reference.artifact_id))
        return next(iter(matches.values()))


class PostgresStrategyOpportunityAuthority:
    """Persist, reload and semantically verify both pre-Strategy owner facts."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        source_authority: StrategySourceAuthority | None = None,
        apply_migrations: bool = False,
    ) -> None:
        self._factory = factory
        self._sources = source_authority or PostgresStrategySourceAuthority(factory)
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def record_risk_state(
        self,
        state: PreStrategyRiskState,
        *,
        created_at: datetime,
    ) -> PreStrategyRiskState:
        resolved = tuple(self._sources.reload(item) for item in state.source_references)
        if any(item.available_at > state.decision_time for item in resolved):
            raise ValueError("pre-Strategy Risk source is unavailable at DecisionTime")

        def operation(connection: Any) -> None:
            connection.execute(
                """
                INSERT INTO pre_strategy_risk_state(
                    risk_state_id, risk_state_hash, account_scope,
                    candidate_id, candidate_hash, decision_time,
                    available_at, payload_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (risk_state_id) DO NOTHING
                """,
                (
                    str(state.risk_state_id),
                    state.risk_state_hash,
                    state.account_scope,
                    str(state.candidate_reference.artifact_id),
                    state.candidate_reference.content_hash,
                    state.decision_time,
                    state.available_at,
                    Jsonb(state.to_canonical_dict()),
                    created_at,
                ),
            )
            _insert_bindings(
                connection,
                table="pre_strategy_risk_source_binding",
                id_column="risk_state_id",
                hash_column="risk_state_hash",
                owner_id=state.risk_state_id,
                owner_hash=state.risk_state_hash,
                references=state.source_references,
            )

        self._factory.run_transaction(operation)
        return self.get_risk_state(state.reference)

    def get_risk_state(
        self,
        reference: RuntimeArtifactReference,
    ) -> PreStrategyRiskState:
        if reference.reference_kind != "PRE_STRATEGY_RISK_STATE":
            raise ValueError("pre-Strategy Risk reference kind is invalid")
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM pre_strategy_risk_state
                WHERE risk_state_id = %s AND risk_state_hash = %s
                """,
                (str(reference.artifact_id), reference.content_hash),
            ).fetchone()
            bindings = _load_bindings(
                connection,
                table="pre_strategy_risk_source_binding",
                id_column="risk_state_id",
                owner_id=reference.artifact_id,
            )
        if row is None or not isinstance(row[0], Mapping):
            raise KeyError(str(reference.artifact_id))
        state = PreStrategyRiskState.from_canonical_dict(row[0])
        if state.reference != reference or bindings != state.source_references:
            raise ValueError("pre-Strategy Risk PostgreSQL projection drifted")
        return state

    def record_opportunity(
        self,
        opportunity: StrategyOpportunityInput,
        *,
        created_at: datetime,
    ) -> StrategyOpportunityInput:
        self._verify_opportunity(opportunity)
        references = _opportunity_sources(opportunity)

        def operation(connection: Any) -> None:
            connection.execute(
                """
                INSERT INTO strategy_opportunity(
                    opportunity_id, opportunity_hash,
                    strategy_version_id, strategy_version_hash,
                    candidate_id, candidate_hash, risk_state_id,
                    risk_state_hash, symbol, decision_time, available_at,
                    payload_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (opportunity_id) DO NOTHING
                """,
                (
                    str(opportunity.opportunity_id),
                    opportunity.binding_hash,
                    str(opportunity.strategy_version_reference.artifact_id),
                    opportunity.strategy_version_reference.content_hash,
                    str(opportunity.candidate_reference.artifact_id),
                    opportunity.candidate_reference.content_hash,
                    str(opportunity.risk_state_reference.artifact_id),
                    opportunity.risk_state_reference.content_hash,
                    opportunity.symbol,
                    opportunity.decision_time,
                    opportunity.available_at,
                    Jsonb(opportunity.to_canonical_dict()),
                    created_at,
                ),
            )
            _insert_bindings(
                connection,
                table="strategy_opportunity_source_binding",
                id_column="opportunity_id",
                hash_column="opportunity_hash",
                owner_id=opportunity.opportunity_id,
                owner_hash=opportunity.binding_hash,
                references=references,
            )

        self._factory.run_transaction(operation)
        return self.reload(opportunity)

    def reload(
        self,
        opportunity: StrategyOpportunityInput,
    ) -> StrategyOpportunityInput:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM strategy_opportunity
                WHERE opportunity_id = %s AND opportunity_hash = %s
                """,
                (str(opportunity.opportunity_id), opportunity.binding_hash),
            ).fetchone()
            bindings = _load_bindings(
                connection,
                table="strategy_opportunity_source_binding",
                id_column="opportunity_id",
                owner_id=opportunity.opportunity_id,
            )
        if row is None or not isinstance(row[0], Mapping):
            raise KeyError(str(opportunity.opportunity_id))
        restored = StrategyOpportunityInput.from_canonical_dict(row[0])
        if restored != opportunity or bindings != _opportunity_sources(restored):
            raise ValueError("Strategy Opportunity PostgreSQL projection drifted")
        self._verify_opportunity(restored)
        return restored

    def resolve(
        self,
        *,
        candidate_reference: RuntimeArtifactReference,
        decision_time: datetime,
        registry: StrategyRegistry,
    ) -> tuple[StrategyOpportunityInput, ...]:
        version_references = tuple(
            RuntimeArtifactReference(
                "STRATEGY_VERSION", item.version_id, item.version_hash
            )
            for item in registry.active_versions
        )
        if not version_references:
            return ()
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM strategy_opportunity
                WHERE candidate_id = %s AND candidate_hash = %s
                  AND decision_time = %s
                ORDER BY strategy_version_id, symbol
                """,
                (
                    str(candidate_reference.artifact_id),
                    candidate_reference.content_hash,
                    decision_time,
                ),
            ).fetchall()
        allowed = set(version_references)
        opportunities = tuple(
            StrategyOpportunityInput.from_canonical_dict(row[0])
            for row in rows
            if isinstance(row[0], Mapping)
        )
        if len(opportunities) != len(rows):
            raise ValueError("Strategy Opportunity owner payload is malformed")
        selected = tuple(
            item for item in opportunities if item.strategy_version_reference in allowed
        )
        for item in selected:
            self.reload(item)
        return selected

    def _verify_opportunity(self, opportunity: StrategyOpportunityInput) -> None:
        risk = self.get_risk_state(opportunity.risk_state_reference)
        if (
            risk.candidate_reference != opportunity.candidate_reference
            or risk.decision_time != opportunity.decision_time
        ):
            raise ValueError("Strategy Opportunity Risk/Candidate DecisionTime drifted")
        risk_decision = risk.decision_for(opportunity.symbol)
        if (
            risk_decision.allows_action != opportunity.risk_allows_action
            or risk_decision.reason_codes != opportunity.risk_reason_codes
        ):
            raise ValueError("Strategy Opportunity Risk projection drifted")
        resolved = {
            item.reference: item
            for item in (
                self._sources.reload(reference)
                for reference in _opportunity_sources(opportunity)
                if reference != opportunity.risk_state_reference
            )
        }
        if any(item.available_at > opportunity.decision_time for item in resolved.values()):
            raise ValueError("Strategy Opportunity owner is unavailable at DecisionTime")
        for reference in (
            opportunity.candidate_reference,
            opportunity.signal_reference,
            opportunity.forecast_reference,
        ):
            if opportunity.symbol not in resolved[reference].symbols:
                raise ValueError("Strategy Opportunity owner has different symbol")
        signal = resolved[opportunity.signal_reference]
        forecast = resolved[opportunity.forecast_reference]
        if opportunity.candidate_reference not in signal.source_references:
            raise ValueError("Strategy Signal does not bind the Candidate owner")
        for required in (
            opportunity.signal_reference,
            opportunity.context_reference,
            opportunity.model_reference,
        ):
            if required not in forecast.source_references:
                raise ValueError("Strategy Forecast lineage is incomplete")
        maximum_availability = max(
            risk.available_at,
            *(item.available_at for item in resolved.values()),
        )
        if opportunity.available_at != maximum_availability:
            raise ValueError("Strategy Opportunity available_at drifted from owners")


def _opportunity_sources(
    opportunity: StrategyOpportunityInput,
) -> tuple[RuntimeArtifactReference, ...]:
    return _references(
        (
            opportunity.strategy_version_reference,
            opportunity.candidate_reference,
            opportunity.signal_reference,
            opportunity.forecast_reference,
            opportunity.context_reference,
            opportunity.risk_state_reference,
            opportunity.model_reference,
        )
    )


def _insert_bindings(
    connection: Any,
    *,
    table: str,
    id_column: str,
    hash_column: str,
    owner_id: ArtifactId,
    owner_hash: str,
    references: tuple[RuntimeArtifactReference, ...],
) -> None:
    allowed = {
        (
            "pre_strategy_risk_source_binding",
            "risk_state_id",
            "risk_state_hash",
        ),
        (
            "strategy_opportunity_source_binding",
            "opportunity_id",
            "opportunity_hash",
        ),
    }
    if (table, id_column, hash_column) not in allowed:
        raise ValueError("Strategy binding table is not allowed")
    with connection.cursor() as cursor:
        cursor.executemany(
            f"""
            INSERT INTO {table}(
                {id_column}, {hash_column}, ordinal,
                reference_kind, artifact_id, content_hash
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT ({id_column}, ordinal) DO NOTHING
            """,
            tuple(
                (
                    str(owner_id),
                    owner_hash,
                    ordinal,
                    item.reference_kind,
                    str(item.artifact_id),
                    item.content_hash,
                )
                for ordinal, item in enumerate(references, 1)
            ),
        )


def _load_bindings(
    connection: Any,
    *,
    table: str,
    id_column: str,
    owner_id: ArtifactId,
) -> tuple[RuntimeArtifactReference, ...]:
    allowed = {
        ("pre_strategy_risk_source_binding", "risk_state_id"),
        ("strategy_opportunity_source_binding", "opportunity_id"),
    }
    if (table, id_column) not in allowed:
        raise ValueError("Strategy binding table is not allowed")
    rows = connection.execute(
        f"""
        SELECT reference_kind, artifact_id, content_hash
        FROM {table} WHERE {id_column} = %s ORDER BY ordinal
        """,
        (str(owner_id),),
    ).fetchall()
    return tuple(
        RuntimeArtifactReference(str(row[0]), ArtifactId(str(row[1])), str(row[2]))
        for row in rows
    )


def _runtime_reference(reference: Any) -> RuntimeArtifactReference:
    return RuntimeArtifactReference(
        reference.artifact_kind,
        reference.artifact_id,
        reference.content_hash,
    )


def _references(
    references: tuple[RuntimeArtifactReference, ...],
) -> tuple[RuntimeArtifactReference, ...]:
    return tuple(
        sorted(
            set(references),
            key=lambda item: (
                item.reference_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )


__all__ = [
    "PostgresStrategyOpportunityAuthority",
    "PostgresStrategySourceAuthority",
    "ResolvedStrategySource",
    "StrategySourceAuthority",
    "StrategyOpportunityResolverAuthority",
]
