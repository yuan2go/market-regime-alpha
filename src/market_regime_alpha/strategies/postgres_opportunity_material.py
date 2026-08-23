"""Typed material resolution for owner-produced Strategy Opportunities."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from market_regime_alpha.application.continuous_research.daily_alpha import (
    DailyAlphaActivationStatus,
    DailyAlphaEvidenceGate,
)
from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.historical_corpus.context_conditional import (
    ContextConditionalEvaluation,
)
from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalEvidenceKind,
    HistoricalResearchEvidence,
    ResearchFinding,
)
from market_regime_alpha.application.historical_corpus.postgres_evidence import (
    PostgresHistoricalEvidenceRepository,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.forecasting.conditional import ConditionalForecastResult
from market_regime_alpha.forecasting.path import PathForecastArtifact
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.research.candidate_discovery.contracts import (
    CandidateSelectionStatus,
    CandidateSet,
)
from market_regime_alpha.signals.contracts import SignalState
from market_regime_alpha.strategies.contracts import (
    StrategyForecastRequirement,
    StrategyRegistry,
    strategy_reference,
)
from market_regime_alpha.strategies.opportunity import StrategyOpportunityMaterial
from market_regime_alpha.strategies.postgres_opportunity import (
    PostgresStrategySourceAuthority,
    ResolvedStrategySource,
)


class PostgresConditionalForecastOwnerResolver:
    """Find one Conditional Forecast by exact baseline and Experiment lineage."""

    def __init__(self, factory: PostgresConnectionFactory) -> None:
        self._factory = factory
        self._evidence = PostgresHistoricalEvidenceRepository(
            factory,
            apply_migrations=False,
        )

    def resolve(
        self,
        *,
        path_reference: ValidationArtifactReference,
        experiment_reference: ValidationArtifactReference,
        context_evidence_reference: ValidationArtifactReference | None = None,
    ) -> tuple[HistoricalResearchEvidence, ConditionalForecastResult]:
        context_join = ""
        context_predicate = ""
        parameters: list[str] = [
            str(experiment_reference.artifact_id),
            experiment_reference.content_hash,
            path_reference.artifact_kind,
            str(path_reference.artifact_id),
            path_reference.content_hash,
        ]
        if context_evidence_reference is not None:
            context_join = """
                JOIN historical_research_evidence_source_binding context
                  ON context.evidence_id = evidence.evidence_id
                 AND context.evidence_hash = evidence.evidence_hash
            """
            context_predicate = """
                  AND context.artifact_kind = %s
                  AND context.artifact_id = %s
                  AND context.content_hash = %s
            """
            parameters.extend(
                (
                    context_evidence_reference.artifact_kind,
                    str(context_evidence_reference.artifact_id),
                    context_evidence_reference.content_hash,
                )
            )
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                f"""
                SELECT evidence.evidence_id
                FROM historical_research_evidence evidence
                JOIN historical_research_evidence_source_binding baseline
                  ON baseline.evidence_id = evidence.evidence_id
                 AND baseline.evidence_hash = evidence.evidence_hash
                {context_join}
                WHERE evidence.evidence_kind = 'CONDITIONAL_PREDICTION'
                  AND evidence.experiment_id = %s
                  AND evidence.experiment_hash = %s
                  AND baseline.artifact_kind = %s
                  AND baseline.artifact_id = %s
                  AND baseline.content_hash = %s
                {context_predicate}
                ORDER BY evidence.evidence_id
                """,
                tuple(parameters),
            ).fetchall()
        if len(rows) != 1:
            raise ValueError(
                "Conditional Forecast owner is missing or ambiguous for exact lineage"
            )
        evidence = self._evidence.get(ArtifactId(str(rows[0][0])))
        if (
            evidence.experiment_reference != experiment_reference
            or path_reference not in evidence.source_references
            or (
                context_evidence_reference is not None
                and context_evidence_reference not in evidence.source_references
            )
        ):
            raise ValueError("Conditional Forecast Evidence source lineage drifted")
        result = ConditionalForecastResult.from_canonical_dict(
            _mapping(evidence.payload.get("forecast"))
        )
        if result.baseline_reference != path_reference:
            raise ValueError("Conditional Forecast baseline owner drifted")
        return evidence, result


class PostgresStrategyOpportunityMaterialResolver:
    """Resolve exact Signal/Forecast/Context/Model owners for active contracts."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        root_candidate_policy_reference: ValidationArtifactReference | None,
        evidence_gate: Callable[[], DailyAlphaEvidenceGate],
        artifact_root: Path | None = None,
    ) -> None:
        self._factory = factory
        self._root = root_candidate_policy_reference
        self._evidence_gate = evidence_gate
        self._evidence = PostgresHistoricalEvidenceRepository(
            factory,
            apply_migrations=False,
        )
        self._sources = PostgresStrategySourceAuthority(
            factory,
            artifact_root=artifact_root,
        )
        self._conditional = PostgresConditionalForecastOwnerResolver(factory)

    def resolve(
        self,
        *,
        candidates: CandidateSet,
        decision_time: datetime,
        registry: StrategyRegistry,
        path_forecasts: tuple[PathForecastArtifact, ...],
    ) -> tuple[StrategyOpportunityMaterial, ...]:
        versions = tuple(
            item
            for item in registry.active_versions
            if registry.contract_for(item).forecast_requirement
            is StrategyForecastRequirement.FORECAST_REQUIRED
        )
        if not versions:
            return ()
        root, context_evidence, context = self._candidate_context_owner()
        paths = {item.forecast.symbol: item for item in path_forecasts}
        if len(paths) != len(path_forecasts):
            raise ValueError("Strategy Path Forecast material is ambiguous")
        admitted_symbols = tuple(
            item.symbol
            for item in candidates.records
            if item.selection_status
            in {
                CandidateSelectionStatus.SELECTED,
                CandidateSelectionStatus.WATCHLIST,
            }
        )
        materials: list[StrategyOpportunityMaterial] = []
        for version in versions:
            version_reference = strategy_reference(version)
            self._reload_before_decision(version_reference, decision_time)
            for symbol in admitted_symbols:
                path = paths.get(symbol)
                if path is None:
                    raise ValueError(
                        "FORECAST_REQUIRED Strategy lacks a symbol Path Forecast owner"
                    )
                materials.append(
                    self._material(
                        candidates=candidates,
                        decision_time=decision_time,
                        version_reference=version_reference,
                        path=path,
                        root=root,
                        context_evidence=context_evidence,
                        context=context,
                    )
                )
        return tuple(materials)

    def _candidate_context_owner(
        self,
    ) -> tuple[
        HistoricalResearchEvidence,
        HistoricalResearchEvidence,
        ContextConditionalEvaluation,
    ]:
        if self._root is None:
            raise ValueError(
                "FORECAST_REQUIRED Strategy requires an explicit Candidate Evidence root"
            )
        gate = self._evidence_gate()
        if (
            gate.status is not DailyAlphaActivationStatus.VALIDATED_CHALLENGER_ACTIVE
            or gate.candidate_policy_reference != self._root
        ):
            raise ValueError(
                "FORECAST_REQUIRED Strategy requires one fully admitted Evidence chain"
            )
        root = self._evidence.get(self._root.artifact_id)
        if (
            root.reference != self._root
            or root.evidence_kind is not HistoricalEvidenceKind.CANDIDATE_POLICY
            or root.classification is not ResearchFinding.POSITIVE
            or root.payload.get("activation_status") != "CHALLENGER_ACTIVE"
            or root.payload.get("stability") != "STABLE"
        ):
            raise ValueError("Strategy Candidate Evidence root is not active")
        admission = _mapping(root.payload.get("daily_alpha_admission"))
        if admission.get("schema_version") != "daily-alpha-evidence-admission/v2":
            raise ValueError("Strategy Candidate Evidence lineage is unsupported")
        context_references = _references(
            admission.get("context_evidence_references")
        )
        if len(context_references) != 1:
            raise ValueError(
                "FORECAST_REQUIRED Strategy requires one explicit Context Evidence owner"
            )
        context_evidence = self._evidence.get(
            context_references[0].artifact_id
        )
        if (
            context_evidence.reference != context_references[0]
            or context_evidence.reference not in root.source_references
            or context_evidence.evidence_kind
            is not HistoricalEvidenceKind.CONTEXT_CONDITIONAL
            or context_evidence.experiment_reference != root.experiment_reference
            or context_evidence.classification is not ResearchFinding.POSITIVE
            or context_evidence.payload.get("status")
            not in {"AMPLIFIER", "SUPPRESSOR"}
        ):
            raise ValueError("Strategy Context Evidence lineage drifted")
        payload = _mapping(context_evidence.payload.get("evaluation"))
        context = ContextConditionalEvaluation.from_canonical_dict(payload)
        return root, context_evidence, context

    def _material(
        self,
        *,
        candidates: CandidateSet,
        decision_time: datetime,
        version_reference: RuntimeArtifactReference,
        path: PathForecastArtifact,
        root: HistoricalResearchEvidence,
        context_evidence: HistoricalResearchEvidence,
        context: ContextConditionalEvaluation,
    ) -> StrategyOpportunityMaterial:
        root_experiment = root.experiment_reference
        context_reference = context_evidence.reference
        path_reference = ValidationArtifactReference(
            "PATH_FORECAST",
            path.artifact_id,
            path.forecast.envelope.content_hash,
        )
        conditional_evidence, result = self._conditional.resolve(
            path_reference=path_reference,
            context_evidence_reference=context_reference,
            experiment_reference=root_experiment,
        )
        if (
            result.status != "AVAILABLE_FOR_RESEARCH"
            or result.model_reference is None
            or result.selected_expected_return is None
        ):
            raise ValueError(
                "FORECAST_REQUIRED Strategy requires an available model-owned Forecast"
            )
        forecast_reference = _runtime_reference(result.reference)
        signal = path.signal_snapshot
        signal_reference = RuntimeArtifactReference(
            "SIGNAL_SNAPSHOT",
            signal.envelope.artifact_id,
            signal.envelope.content_hash,
        )
        candidate_reference = RuntimeArtifactReference(
            "CANDIDATE_SET",
            candidates.envelope.artifact_id,
            candidates.envelope.content_hash,
        )
        context_owner_reference = _runtime_reference(context.reference)
        model_reference = _runtime_reference(result.model_reference)
        resolved = tuple(
            self._reload_before_decision(item, decision_time)
            for item in (
                candidate_reference,
                signal_reference,
                forecast_reference,
                context_owner_reference,
                model_reference,
            )
        )
        signal_owner = resolved[1]
        forecast_owner = resolved[2]
        if candidate_reference not in signal_owner.source_references:
            raise ValueError("Strategy Signal does not bind the Candidate owner")
        for required in (
            signal_reference,
            context_owner_reference,
            model_reference,
        ):
            if required not in forecast_owner.source_references:
                raise ValueError("Conditional Forecast material lineage is incomplete")
        return StrategyOpportunityMaterial(
            symbol=path.forecast.symbol,
            strategy_version_reference=version_reference,
            signal_reference=signal_reference,
            forecast_reference=forecast_reference,
            context_reference=context_owner_reference,
            model_reference=model_reference,
            signal_active=(
                signal.signal_state is SignalState.CONFIRMED_FOR_RESEARCH
            ),
            expected_return=result.selected_expected_return,
            prediction_uncertainty=result.prediction_uncertainty,
            calibration_status=result.calibration_status,
            available_at=max(item.available_at for item in resolved),
        )

    def _reload_before_decision(
        self,
        reference: RuntimeArtifactReference,
        decision_time: datetime,
    ) -> ResolvedStrategySource:
        owner = self._sources.reload(reference)
        if owner.available_at > decision_time:
            raise ValueError("Strategy material owner is unavailable at DecisionTime")
        return owner


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Strategy material owner payload must be an object")
    return value


def _references(value: object) -> tuple[ValidationArtifactReference, ...]:
    if not isinstance(value, list):
        raise ValueError("Strategy Context Evidence references must be an array")
    references = tuple(
        ValidationArtifactReference.from_canonical_dict(_mapping(item))
        for item in value
    )
    expected = tuple(
        sorted(
            set(references),
            key=lambda item: (
                item.artifact_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )
    if references != expected:
        raise ValueError("Strategy Context Evidence references are ambiguous")
    return references


def _runtime_reference(
    reference: ValidationArtifactReference,
) -> RuntimeArtifactReference:
    return RuntimeArtifactReference(
        reference.artifact_kind,
        reference.artifact_id,
        reference.content_hash,
    )


__all__ = [
    "PostgresConditionalForecastOwnerResolver",
    "PostgresStrategyOpportunityMaterialResolver",
]
