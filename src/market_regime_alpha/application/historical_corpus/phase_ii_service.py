"""Owner-resolved Phase II research composition over existing Historical Evidence.

This is an application capability of Historical Research, not a new Runtime or
Evidence authority.  Every admission reloads immutable PostgreSQL Evidence and
every result is written through ``PostgresHistoricalEvidenceRepository``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalEvidenceKind,
    HistoricalEvidenceMetric,
    HistoricalResearchEvidence,
    ResearchFinding,
    ResearchStatement,
    ResearchStatementKind,
)
from market_regime_alpha.application.historical_corpus.alpha_correctness import (
    AlphaCorrectnessProof,
    HistoricalAlphaCorrectnessChecker,
    HistoricalCorrectnessReproduction,
    build_alpha_correctness_proof,
    reproduce_execution_timing_diagnostics,
)
from market_regime_alpha.application.historical_corpus.alpha_diagnostics import (
    AlphaObservation,
    ExecutionTimingDiagnostic,
    FactorObservation,
    FrozenPlaceboProtocol,
    MovingBlockInferenceProtocol,
    PlaceboKind,
    apply_placebo,
    evaluate_factor_redundancy,
    evaluate_robust_inference_family,
    factor_rank_ic_session_estimates,
)
from market_regime_alpha.application.historical_corpus.external_validation import (
    ExternalValidationEvaluation,
    FrozenAlphaHypothesis,
    FrozenExternalValidationExperiment,
    ValidationDimension,
    ValidationScope,
    evaluate_external_validation,
    project_external_validation_observations,
)
from market_regime_alpha.application.historical_corpus.context_conditional import (
    ContextConditionalEvaluation,
    ContextDefinition,
    ContextKind,
    ContextResearchRole,
    evaluate_context_conditioning,
    project_context_observations,
)
from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalNormalizedBar,
)
from market_regime_alpha.application.historical_corpus.postgres_evidence import (
    PostgresHistoricalEvidenceRepository,
)
from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
    HistoricalSessionComponent,
)
from market_regime_alpha.application.historical_corpus.postgres_materialization import (
    PostgresHistoricalMaterializationRepository,
)
from market_regime_alpha.application.historical_corpus.postgres_repository import (
    PostgresHistoricalCorpusRepository,
)
from market_regime_alpha.application.historical_corpus.selective_read import (
    HistoricalReadQuery,
)
from market_regime_alpha.application.historical_corpus.raw_normalization_correctness import (
    PhysicalAcquisitionProvenance,
    verify_independent_baostock_package_normalization,
)
from market_regime_alpha.application.historical_corpus.temporal_validation_window import (
    FrozenTemporalValidationWindow,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.application.research_validation.postgres_research_model import (
    PostgresResearchModelRepository,
)
from market_regime_alpha.application.research_validation.research_model import (
    ResearchModelTrainingRequest,
)
from market_regime_alpha.candidates.policy import (
    CandidatePolicyComparison,
    CandidateComparisonProtocol,
    CandidatePolicyDefinition,
    CandidatePolicyEvaluation,
    CandidatePolicyInput,
    CandidateRealizedReturn,
    ContextAdjustmentDefinition,
    ValidatedFactorDefinition,
    evaluate_candidate_policy as evaluate_candidate_policy_kernel,
    compare_candidate_policies as compare_candidate_policies_kernel,
    research_panel_dataset_reference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.forecasting.conditional import (
    ConditionalForecastConfig,
    ConditionalForecastResult,
)
from market_regime_alpha.forecasting.path import PathForecastArtifact
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.market_data.contracts import Timeframe


@dataclass(frozen=True, slots=True)
class PhaseIIEvidenceWrite:
    run_id: ArtifactId
    command_hash: str
    experiment_reference: ValidationArtifactReference
    evidence_kind: HistoricalEvidenceKind
    research_question: str
    classification: ResearchFinding
    rationale: str
    source_references: tuple[ValidationArtifactReference, ...]
    metrics: tuple[HistoricalEvidenceMetric, ...]
    payload: Mapping[str, Any]
    created_at: datetime
    statements: tuple[ResearchStatement, ...]
    limitations: tuple[str, ...] = ()


class HistoricalPhaseIIResearchService:
    """Canonical PG-backed admission and persistence seam for the five WPs."""

    def __init__(
        self,
        evidence: PostgresHistoricalEvidenceRepository,
        *,
        components: PostgresHistoricalMaterializationRepository | None = None,
        corpus: PostgresHistoricalCorpusRepository | None = None,
        validation: PostgresResearchValidationRepository | None = None,
        research_models: PostgresResearchModelRepository | None = None,
    ) -> None:
        self._evidence = evidence
        self._components = components
        self._corpus = corpus
        self._validation = validation
        self._research_models = research_models

    def load_evidence(
        self,
        evidence_id: ArtifactId,
        *,
        expected_kind: HistoricalEvidenceKind,
    ) -> HistoricalResearchEvidence:
        evidence = self._evidence.get(evidence_id)
        evidence.verify_identity()
        if evidence.evidence_kind is not expected_kind:
            raise ValueError(
                f"Evidence kind mismatch: expected {expected_kind.value}"
            )
        _verify_phase_ii_payload(evidence)
        return evidence

    def evaluate_correctness_campaign(
        self,
        *,
        run_id: ArtifactId,
        trading_calendar: TradingCalendarArtifact,
        physical_package_paths: Mapping[ValidationArtifactReference, Path],
        physical_provenance: PhysicalAcquisitionProvenance,
        target_id: str,
        placebo_seed: int,
        inference_protocol: MovingBlockInferenceProtocol,
    ) -> AlphaCorrectnessProof:
        """Execute the frozen suite from exact PostgreSQL and physical owners.

        This is an application operation of Historical Research. It neither
        creates another Runtime nor admits External Validation; persistence
        still replays the complete suite through ``persist_correctness_proof``.
        """

        components = self._components
        corpus = self._corpus
        if components is None or corpus is None:
            raise ValueError(
                "Alpha Correctness campaign requires Historical owner reload"
            )
        reproduction = HistoricalAlphaCorrectnessChecker(
            components=components,
            corpus=corpus,
        ).reproduce_run(
            run_id=run_id,
            trading_calendar=trading_calendar,
            physical_package_paths=physical_package_paths,
        )
        normalization = []
        for physical in reproduction.physical_verifications:
            normalized_index = corpus.open_index(
                physical.normalized_owner_reference
            )
            raw_reference = normalized_index.parent_reference
            if raw_reference is None:
                raise ValueError("Normalized owner lacks Raw acquisition lineage")
            normalization.append(
                verify_independent_baostock_package_normalization(
                    corpus=corpus,
                    raw_owner_reference=raw_reference,
                    normalized_owner_reference=physical.normalized_owner_reference,
                    provenance=physical_provenance,
                )
            )
        factor_observations = _correctness_factor_observations(reproduction)
        factor_ids = (
            "intraday_return_to_decision_time",
            "price_vs_vwap_return",
            "vwap_slope",
        )
        alpha_by_factor = {
            factor_id: tuple(
                AlphaObservation(
                    item.session,
                    item.symbol,
                    item.factors[factor_id],
                    item.target_return,
                )
                for item in factor_observations
            )
            for factor_id in factor_ids
        }
        placebos = tuple(
            apply_placebo(
                FrozenPlaceboProtocol.create(
                    factor_id=factor_id,
                    target_id=target_id,
                    seed=placebo_seed,
                    kinds=tuple(PlaceboKind),
                ),
                kind=kind,
                observations=alpha_by_factor[factor_id],
            )
            for factor_id in factor_ids
            for kind in PlaceboKind
        )
        inference = evaluate_robust_inference_family(
            inference_protocol,
            {
                factor_id: factor_rank_ic_session_estimates(
                    factor_observations,
                    factor_id=factor_id,
                )
                for factor_id in factor_ids
            },
        )
        execution = _first_complete_execution_diagnostic(
            reproduction=reproduction,
            corpus=corpus,
        )
        return build_alpha_correctness_proof(
            feature_results=reproduction.feature_results,
            target_results=reproduction.target_results,
            physical_verifications=reproduction.physical_verifications,
            normalization_verifications=tuple(normalization),
            placebo_results=placebos,
            execution_diagnostics=execution,
            factor_redundancy=evaluate_factor_redundancy(factor_observations),
            robust_inference=tuple(inference.items()),
        )

    def create_external_experiment(
        self,
        *,
        hypothesis: FrozenAlphaHypothesis,
        correctness_evidence_id: ArtifactId,
        discovery_scope: ValidationScope,
        validation_scope: ValidationScope,
        temporal_window: FrozenTemporalValidationWindow | None,
        validation_panel_references: tuple[ValidationArtifactReference, ...],
        dimension: ValidationDimension,
        expected_population: int,
        random_seed: int,
    ) -> FrozenExternalValidationExperiment:
        correctness = self.load_evidence(
            correctness_evidence_id,
            expected_kind=HistoricalEvidenceKind.ALPHA_CORRECTNESS,
        )
        discovery = self.load_evidence(
            hypothesis.discovery_evidence_reference.artifact_id,
            expected_kind=HistoricalEvidenceKind.ALPHA_ABLATION,
        )
        if discovery.reference != hypothesis.discovery_evidence_reference:
            raise ValueError("frozen hypothesis Discovery Evidence reference drifted")
        _verify_hypothesis_against_owner_evidence(
            hypothesis=hypothesis,
            correctness=correctness,
            discovery=discovery,
        )
        validation = self._validation
        if validation is None:
            raise ValueError(
                "External validation admission requires Feature/Cost owner reload"
            )
        _verify_hypothesis_configuration_owners(validation, hypothesis)
        components = self._components
        if components is None:
            raise ValueError(
                "External validation admission requires Historical Panel owner reload"
            )
        _verify_external_panel_owners(
            components=components,
            panel_references=validation_panel_references,
            discovery_scope=discovery_scope,
            validation_scope=validation_scope,
            temporal_window=temporal_window,
            dimension=dimension,
            discovery=discovery,
            expected_population=expected_population,
        )
        return FrozenExternalValidationExperiment.create(
            hypothesis=hypothesis,
            correctness_evidence=correctness,
            discovery_scope=discovery_scope,
            validation_scope=validation_scope,
            temporal_window=temporal_window,
            validation_panel_references=validation_panel_references,
            dimension=dimension,
            expected_population=expected_population,
            random_seed=random_seed,
        )

    def validated_factor(
        self,
        *,
        factor_id: str,
        direction: str,
        weight: Decimal,
        external_evidence_id: ArtifactId,
    ) -> ValidatedFactorDefinition:
        evidence = self.load_evidence(
            external_evidence_id,
            expected_kind=HistoricalEvidenceKind.EXTERNAL_VALIDATION,
        )
        return ValidatedFactorDefinition(factor_id, direction, weight, evidence)

    def evaluate_external_experiment(
        self,
        experiment: FrozenExternalValidationExperiment,
    ) -> ExternalValidationEvaluation:
        components = self._components
        corpus = self._corpus
        if components is None or corpus is None:
            raise ValueError(
                "External validation evaluation requires Panel/Data owner reload"
            )
        panels = tuple(
            components.get(reference)
            for reference in experiment.validation_panel_references
        )
        outcome_references = tuple(
            sorted(
                {
                    reference
                    for panel in panels
                    for reference in panel.source_references
                    if reference.artifact_kind == "HISTORICAL_OUTCOME"
                },
                key=lambda item: (
                    item.artifact_kind,
                    str(item.artifact_id),
                    item.content_hash,
                ),
            )
        )
        outcomes = tuple(components.get(reference) for reference in outcome_references)
        observations = project_external_validation_observations(
            experiment,
            panels,
            outcomes,
        )
        pit_complete, free_data = _external_data_ceiling(
            components=components,
            corpus=corpus,
            panels=panels,
        )
        return evaluate_external_validation(
            experiment,
            observations=observations,
            pit_complete=pit_complete,
            free_data=free_data,
        )

    def load_conditional_forecast(
        self, evidence_id: ArtifactId
    ) -> ConditionalForecastResult:
        evidence = self.load_evidence(
            evidence_id,
            expected_kind=HistoricalEvidenceKind.CONDITIONAL_PREDICTION,
        )
        forecast = evidence.payload.get("forecast")
        configuration = evidence.payload.get("configuration")
        baseline = evidence.payload.get("baseline_forecast")
        if not isinstance(forecast, Mapping):
            raise ValueError("Conditional Forecast Evidence lacks a typed artifact")
        if (
            not isinstance(configuration, Mapping)
            or not isinstance(baseline, Mapping)
        ):
            raise ValueError("Conditional Forecast Evidence lacks frozen owners")
        restored_configuration = ConditionalForecastConfig.from_canonical_dict(
            configuration
        )
        restored_baseline = PathForecastArtifact.from_canonical_dict(dict(baseline))
        result = ConditionalForecastResult.from_canonical_dict(forecast)
        if restored_configuration.reference != result.configuration_reference:
            raise ValueError("Conditional Forecast configuration projection drifted")
        if _path_forecast_reference(restored_baseline) != result.baseline_reference:
            raise ValueError("Conditional Forecast baseline projection drifted")
        self._verify_conditional_model_owners(
            result,
            configuration=restored_configuration,
            baseline_forecast=restored_baseline,
        )
        return result

    def context_definition(
        self,
        *,
        context_id: str,
        kind: ContextKind,
        role: ContextResearchRole,
        public_observable_proxy: bool,
        research_panel_references: tuple[ValidationArtifactReference, ...],
        top_k: int,
        expected_population: int,
        effect_threshold: Decimal,
        external_evidence_id: ArtifactId,
    ) -> ContextDefinition:
        evidence = self.load_evidence(
            external_evidence_id,
            expected_kind=HistoricalEvidenceKind.EXTERNAL_VALIDATION,
        )
        return ContextDefinition.create(
            context_id=context_id,
            kind=kind,
            role=role,
            public_observable_proxy=public_observable_proxy,
            research_panel_references=research_panel_references,
            top_k=top_k,
            expected_population=expected_population,
            effect_threshold=effect_threshold,
            alpha_evidence=evidence,
        )

    def evaluate_context_definition(
        self,
        definition: ContextDefinition,
    ) -> ContextConditionalEvaluation:
        components = self._components
        if components is None:
            raise ValueError("Context evaluation requires Research Panel owner reload")
        panels = tuple(
            components.get(reference)
            for reference in definition.research_panel_references
        )
        owner_population = sum(
            _panel_row_count(panel, label="Context") for panel in panels
        )
        if owner_population != definition.expected_population:
            raise ValueError("Context expected population drifted from Panel owners")
        return evaluate_context_conditioning(
            definition,
            observations=project_context_observations(definition, panels),
        )

    def context_adjustment(
        self,
        *,
        context_id: str,
        weight: Decimal,
        mode: str,
        context_evidence_id: ArtifactId,
    ) -> ContextAdjustmentDefinition:
        evidence = self.load_evidence(
            context_evidence_id,
            expected_kind=HistoricalEvidenceKind.CONTEXT_CONDITIONAL,
        )
        return ContextAdjustmentDefinition(context_id, weight, mode, evidence)

    def evaluate_candidate_policy(
        self,
        policy: CandidatePolicyDefinition,
        *,
        panel_references: tuple[ValidationArtifactReference, ...],
    ) -> CandidatePolicyEvaluation:
        components = self._components
        if components is None:
            raise ValueError("Candidate Policy evaluation requires Panel owner reload")
        dataset_reference = research_panel_dataset_reference(panel_references)
        if dataset_reference != policy.dataset_reference:
            raise ValueError("Candidate Policy frozen dataset owner drifted")
        self._verify_candidate_policy_evidence(policy)
        panels = tuple(components.get(reference) for reference in panel_references)
        return evaluate_candidate_policy_kernel(
            policy,
            _candidate_inputs_from_panels(policy, panels),
        )

    def compare_candidate_policies(
        self,
        incumbent_policy: CandidatePolicyDefinition,
        challenger_policy: CandidatePolicyDefinition,
        *,
        protocol: CandidateComparisonProtocol,
        panel_references: tuple[ValidationArtifactReference, ...],
    ) -> CandidatePolicyComparison:
        components = self._components
        if components is None:
            raise ValueError("Candidate comparison requires Panel owner reload")
        dataset_reference = research_panel_dataset_reference(panel_references)
        if dataset_reference != protocol.dataset_reference:
            raise ValueError("Candidate comparison frozen dataset owner drifted")
        panels = tuple(components.get(reference) for reference in panel_references)
        self._verify_candidate_policy_evidence(incumbent_policy)
        self._verify_candidate_policy_evidence(challenger_policy)
        incumbent = evaluate_candidate_policy_kernel(
            incumbent_policy,
            _candidate_inputs_from_panels(incumbent_policy, panels),
        )
        challenger = evaluate_candidate_policy_kernel(
            challenger_policy,
            _candidate_inputs_from_panels(challenger_policy, panels),
        )
        realized = _candidate_returns_from_panels(protocol, panels)
        return compare_candidate_policies_kernel(
            incumbent,
            challenger,
            protocol=protocol,
            realized_returns=realized,
        )

    def _verify_candidate_policy_evidence(
        self,
        policy: CandidatePolicyDefinition,
    ) -> None:
        for factor in policy.validated_factors:
            owner = self.load_evidence(
                factor.external_validation_evidence.reference.artifact_id,
                expected_kind=HistoricalEvidenceKind.EXTERNAL_VALIDATION,
            )
            if owner != factor.external_validation_evidence:
                raise ValueError("Candidate Factor Evidence owner drifted")
        for adjustment in policy.context_adjustments:
            owner = self.load_evidence(
                adjustment.context_evidence.reference.artifact_id,
                expected_kind=HistoricalEvidenceKind.CONTEXT_CONDITIONAL,
            )
            if owner != adjustment.context_evidence:
                raise ValueError("Candidate Context Evidence owner drifted")

    def persist(self, write: PhaseIIEvidenceWrite) -> HistoricalResearchEvidence:
        """Persist an unestablished/failed status; support requires a typed proof."""

        if write.evidence_kind is not HistoricalEvidenceKind.ALPHA_CORRECTNESS:
            raise ValueError("non-correctness Phase II Evidence requires a typed artifact")
        if write.payload.get("status") == "CORRECTNESS_SUPPORTED":
            raise ValueError("CORRECTNESS_SUPPORTED requires a typed correctness proof")
        _verify_phase_ii_payload_values(write.evidence_kind, write.payload)
        return self._persist(write)

    def persist_correctness_proof(
        self,
        write: PhaseIIEvidenceWrite,
        proof: AlphaCorrectnessProof,
        *,
        run_id: ArtifactId,
        trading_calendar: TradingCalendarArtifact,
        physical_package_paths: Mapping[ValidationArtifactReference, Path] | None = None,
    ) -> HistoricalResearchEvidence:
        if write.evidence_kind is not HistoricalEvidenceKind.ALPHA_CORRECTNESS:
            raise ValueError("Alpha Correctness proof Evidence kind mismatch")
        if self._components is None or self._corpus is None:
            raise ValueError(
                "Alpha Correctness Evidence requires Historical owner reload"
            )
        reproduction = HistoricalAlphaCorrectnessChecker(
            components=self._components,
            corpus=self._corpus,
        ).reproduce_run(
            run_id=run_id,
            trading_calendar=trading_calendar,
            physical_package_paths=physical_package_paths,
        )
        _verify_correctness_proof_against_owners(
            proof=proof,
            reproduction=reproduction,
            corpus=self._corpus,
        )
        owner_sources = tuple(
            item.reference
            for component_kind in (
                HistoricalComponentKind.FEATURE,
                HistoricalComponentKind.OUTCOME,
            )
            for batch in self._components.iter_for_run(
                run_id=run_id,
                component_kind=component_kind,
                batch_size=1,
            )
            for item in batch
        )
        write = _with_required_sources(
            write,
            proof.reference,
            ValidationArtifactReference(
                "TRADING_CALENDAR",
                trading_calendar.artifact_id,
                trading_calendar.content_hash,
            ),
            *owner_sources,
            *(item.normalized_owner_reference for item in reproduction.physical_verifications),
            *(item.raw_owner_reference for item in proof.normalization_verifications),
            *(
                item.normalized_owner_reference
                for item in proof.normalization_verifications
            ),
        )
        return self._persist(
            replace(
                write,
                payload={
                    "status": proof.conclusion.value,
                    "proof": proof.to_evidence_dict(),
                },
            )
        )

    def persist_external_evaluation(
        self,
        write: PhaseIIEvidenceWrite,
        experiment: FrozenExternalValidationExperiment,
        evaluation: ExternalValidationEvaluation,
    ) -> HistoricalResearchEvidence:
        if write.evidence_kind is not HistoricalEvidenceKind.EXTERNAL_VALIDATION:
            raise ValueError("External Evaluation Evidence kind mismatch")
        if (
            write.experiment_reference != evaluation.experiment_reference
            or experiment.reference != evaluation.experiment_reference
        ):
            raise ValueError("External Evaluation Experiment owner drifted")
        write = _with_required_sources(
            write,
            evaluation.experiment_reference,
            evaluation.thresholds_reference,
            experiment.correctness_evidence.reference,
            experiment.hypothesis.discovery_evidence_reference,
            experiment.hypothesis.feature_reference,
            experiment.hypothesis.target_reference,
            experiment.hypothesis.cost_policy_reference,
            *(
                (experiment.temporal_window.calendar_reference,)
                if experiment.temporal_window is not None
                else ()
            ),
            *experiment.validation_panel_references,
        )
        return self._persist(
            replace(
                write,
                payload={
                    "evaluation": evaluation.to_canonical_dict(),
                    "experiment": experiment.to_canonical_dict(),
                    "qualification_status": evaluation.qualification_status,
                    "validated_factors": [
                        list(item) for item in evaluation.factor_directions
                    ],
                },
            )
        )

    def persist_context_evaluation(
        self,
        write: PhaseIIEvidenceWrite,
        evaluation: ContextConditionalEvaluation,
    ) -> HistoricalResearchEvidence:
        if write.evidence_kind is not HistoricalEvidenceKind.CONTEXT_CONDITIONAL:
            raise ValueError("Context Evaluation Evidence kind mismatch")
        write = _with_required_sources(write, evaluation.definition_reference)
        return self._persist(
            replace(
                write,
                payload={
                    "evaluation": evaluation.to_canonical_dict(),
                    "status": evaluation.status,
                },
            )
        )

    def persist_candidate_evaluation(
        self,
        write: PhaseIIEvidenceWrite,
        evaluation: CandidatePolicyEvaluation,
    ) -> HistoricalResearchEvidence:
        if write.evidence_kind is not HistoricalEvidenceKind.CANDIDATE_POLICY:
            raise ValueError("Candidate Evaluation Evidence kind mismatch")
        write = _with_required_sources(
            write,
            evaluation.policy_reference,
            evaluation.dataset_reference,
        )
        return self._persist(
            replace(
                write,
                payload={"evaluation": evaluation.to_canonical_dict()},
            )
        )

    def persist_candidate_comparison(
        self,
        write: PhaseIIEvidenceWrite,
        comparison: CandidatePolicyComparison,
    ) -> HistoricalResearchEvidence:
        if write.evidence_kind is not HistoricalEvidenceKind.CANDIDATE_POLICY:
            raise ValueError("Candidate Comparison Evidence kind mismatch")
        write = _with_required_sources(
            write,
            comparison.incumbent_reference,
            comparison.challenger_reference,
            comparison.dataset_reference,
            comparison.protocol_reference,
        )
        return self._persist(
            replace(
                write,
                payload={"comparison": comparison.to_canonical_dict()},
            )
        )

    def persist_candidate_admission(
        self,
        write: PhaseIIEvidenceWrite,
        *,
        comparison: CandidatePolicyComparison,
        challenger_policy: CandidatePolicyDefinition,
        activation_status: str,
    ) -> HistoricalResearchEvidence:
        """Persist the single explicit root consumed by Daily Alpha.

        The method reuses Historical Evidence and Candidate Policy owners.  It
        does not select a comparison or policy by recency or metric value.
        """

        if write.evidence_kind is not HistoricalEvidenceKind.CANDIDATE_POLICY:
            raise ValueError("Candidate admission Evidence kind mismatch")
        if activation_status not in {
            "CHALLENGER_ACTIVE",
            "CHALLENGER_DORMANT",
        }:
            raise ValueError("Candidate admission status must be explicit")
        if (
            comparison.challenger_reference != challenger_policy.reference
            or comparison.dataset_reference != challenger_policy.dataset_reference
        ):
            raise ValueError("Candidate admission Policy/Dataset owner drifted")
        self._verify_candidate_policy_evidence(challenger_policy)
        external_references = {
            item.external_validation_evidence.reference
            for item in challenger_policy.validated_factors
        }
        if len(external_references) != 1:
            raise ValueError(
                "Candidate admission requires one External Evidence chain"
            )
        external_reference = next(iter(external_references))
        external = self.load_evidence(
            external_reference.artifact_id,
            expected_kind=HistoricalEvidenceKind.EXTERNAL_VALIDATION,
        )
        if external.reference != external_reference:
            raise ValueError("Candidate External Evidence owner drifted")
        experiment = _mapping_value(external.payload.get("experiment"))
        external_experiment_reference = ValidationArtifactReference(
            "RESEARCH_EXPERIMENT_DEFINITION",
            ArtifactId(str(experiment["experiment_id"])),
            str(experiment["experiment_hash"]),
        )
        if external_experiment_reference != external.experiment_reference:
            raise ValueError("Candidate External Experiment owner drifted")
        correctness_reference = ValidationArtifactReference.from_canonical_dict(
            _mapping_value(experiment["correctness_evidence_reference"])
        )
        hypothesis = _mapping_value(experiment["hypothesis"])
        hypothesis_reference = ValidationArtifactReference(
            "FROZEN_ALPHA_HYPOTHESIS",
            ArtifactId(str(hypothesis["hypothesis_id"])),
            str(hypothesis["hypothesis_hash"]),
        )
        discovery_reference = ValidationArtifactReference.from_canonical_dict(
            _mapping_value(hypothesis["discovery_evidence_reference"])
        )
        correctness = self.load_evidence(
            correctness_reference.artifact_id,
            expected_kind=HistoricalEvidenceKind.ALPHA_CORRECTNESS,
        )
        discovery = self.load_evidence(
            discovery_reference.artifact_id,
            expected_kind=HistoricalEvidenceKind.ALPHA_ABLATION,
        )
        if (
            correctness.reference != correctness_reference
            or discovery.reference != discovery_reference
            or not {correctness.reference, discovery.reference}.issubset(
                external.source_references
            )
        ):
            raise ValueError("Candidate upstream Evidence lineage drifted")
        panels = tuple(
            ValidationArtifactReference.from_canonical_dict(_mapping_value(item))
            for item in experiment.get("validation_panel_references", ())
        )
        if research_panel_dataset_reference(panels) != comparison.dataset_reference:
            raise ValueError("Candidate/External dataset owner drifted")
        context_evidence = tuple(
            sorted(
                (
                    item.context_evidence
                    for item in challenger_policy.context_adjustments
                ),
                key=lambda item: (
                    item.reference.artifact_kind,
                    str(item.reference.artifact_id),
                    item.reference.content_hash,
                ),
            )
        )
        for context in context_evidence:
            if context.experiment_reference != external_experiment_reference:
                raise ValueError("Candidate Context Experiment owner drifted")
            if external.reference not in context.source_references:
                raise ValueError("Candidate Context lacks External Evidence lineage")
            evaluation = _mapping_value(context.payload.get("evaluation"))
            definition_reference = ValidationArtifactReference.from_canonical_dict(
                _mapping_value(evaluation["definition_reference"])
            )
            if definition_reference not in context.source_references:
                raise ValueError("Candidate Context definition owner drifted")
            context_panels = tuple(
                item
                for item in context.source_references
                if item.artifact_kind
                in {"RESEARCH_PANEL", "HISTORICAL_RESEARCH_PANEL"}
            )
            if (
                not context_panels
                or research_panel_dataset_reference(context_panels)
                != comparison.dataset_reference
            ):
                raise ValueError("Candidate Context dataset owner drifted")
        factor_directions = tuple(
            sorted(
                (item.factor_id, item.direction)
                for item in challenger_policy.validated_factors
            )
        )
        if factor_directions != _strict_factor_directions(
            external.payload.get("validated_factors")
        ):
            raise ValueError("Candidate validated Factor family drifted")
        if activation_status == "CHALLENGER_ACTIVE" and (
            write.classification is not ResearchFinding.POSITIVE
            or comparison.stability != "STABLE"
            or external.classification is not ResearchFinding.POSITIVE
            or external.payload.get("qualification_status") != "SUPPORTED"
            or correctness.classification is not ResearchFinding.POSITIVE
            or correctness.payload.get("status") != "CORRECTNESS_SUPPORTED"
            or discovery.classification is not ResearchFinding.POSITIVE
        ):
            raise ValueError(
                "Candidate Challenger activation lacks supported stable Evidence"
            )
        write = _with_required_sources(
            write,
            comparison.incumbent_reference,
            comparison.challenger_reference,
            comparison.dataset_reference,
            comparison.protocol_reference,
            challenger_policy.reference,
            external.reference,
            correctness.reference,
            discovery.reference,
            external_experiment_reference,
            hypothesis_reference,
            *(item.reference for item in context_evidence),
        )
        admission = {
            "schema_version": "daily-alpha-evidence-admission/v2",
            "candidate_policy_reference": challenger_policy.reference.to_canonical_dict(),
            "candidate_dataset_reference": comparison.dataset_reference.to_canonical_dict(),
            "external_validation_evidence_reference": external.reference.to_canonical_dict(),
            "correctness_evidence_reference": correctness.reference.to_canonical_dict(),
            "discovery_evidence_reference": discovery.reference.to_canonical_dict(),
            "external_experiment_reference": external_experiment_reference.to_canonical_dict(),
            "frozen_hypothesis_reference": hypothesis_reference.to_canonical_dict(),
            "factor_directions": [list(item) for item in factor_directions],
            "context_evidence_references": [
                item.reference.to_canonical_dict() for item in context_evidence
            ],
            "lineage_stages": [
                _phase_ii_lineage_stage("DISCOVERY", discovery),
                _phase_ii_lineage_stage("CORRECTNESS", correctness),
                _phase_ii_lineage_stage("EXTERNAL_VALIDATION", external),
                *(
                    _phase_ii_lineage_stage("CONTEXT_CONDITIONAL", item)
                    for item in context_evidence
                ),
            ],
        }
        return self._persist(
            replace(
                write,
                payload={
                    "comparison": comparison.to_canonical_dict(),
                    "activation_status": activation_status,
                    "stability": comparison.stability,
                    "daily_alpha_admission": admission,
                },
            )
        )

    def persist_conditional_forecast(
        self,
        write: PhaseIIEvidenceWrite,
        configuration: ConditionalForecastConfig,
        forecast: ConditionalForecastResult,
        baseline_forecast: PathForecastArtifact,
        context_evidence: HistoricalResearchEvidence,
    ) -> HistoricalResearchEvidence:
        if write.evidence_kind is not HistoricalEvidenceKind.CONDITIONAL_PREDICTION:
            raise ValueError("Conditional Forecast Evidence kind mismatch")
        baseline_forecast.forecast.envelope.verify_payload(
            baseline_forecast.forecast.artifact_payload()
        )
        if configuration.reference != forecast.configuration_reference:
            raise ValueError("Conditional Forecast configuration owner drifted")
        if _path_forecast_reference(baseline_forecast) != forecast.baseline_reference:
            raise ValueError("Conditional Forecast baseline owner drifted")
        if (
            context_evidence.evidence_kind
            is not HistoricalEvidenceKind.CONTEXT_CONDITIONAL
            or context_evidence.experiment_reference != write.experiment_reference
            or context_evidence.classification is not ResearchFinding.POSITIVE
            or context_evidence.payload.get("status")
            not in {"AMPLIFIER", "SUPPRESSOR"}
        ):
            raise ValueError(
                "Conditional Forecast requires supported Context from its Experiment"
            )
        context_payload = _mapping_value(context_evidence.payload.get("evaluation"))
        context_reference = ValidationArtifactReference.from_canonical_dict(
            _mapping_value(context_payload["definition_reference"])
        )
        if context_reference not in context_evidence.source_references:
            raise ValueError("Conditional Forecast Context definition owner drifted")
        self._verify_conditional_model_owners(
            forecast,
            configuration=configuration,
            baseline_forecast=baseline_forecast,
        )
        write = _with_required_sources(
            write,
            forecast.configuration_reference,
            forecast.training_request_reference,
            forecast.baseline_reference,
            context_evidence.reference,
            *((forecast.model_reference,) if forecast.model_reference is not None else ()),
            *((forecast.inference_reference,) if forecast.inference_reference is not None else ()),
        )
        return self._persist(
            replace(
                write,
                payload={
                    "configuration": configuration.to_canonical_dict(),
                    "baseline_forecast": baseline_forecast.to_canonical_dict(),
                    "forecast": forecast.to_canonical_dict(),
                },
            )
        )

    def _verify_conditional_model_owners(
        self,
        forecast: ConditionalForecastResult,
        *,
        configuration: ConditionalForecastConfig,
        baseline_forecast: PathForecastArtifact,
    ) -> None:
        repository = self._research_models
        if repository is None:
            raise ValueError(
                "Conditional Forecast requires PostgreSQL Research Model owner reload"
            )
        request = repository.get_request(
            forecast.training_request_reference.artifact_id
        )
        if (
            request.request_hash
            != forecast.training_request_reference.content_hash
        ):
            raise ValueError("Conditional Forecast Training Request owner drifted")
        _verify_conditional_sample_bindings(forecast, request)
        if forecast.status != "AVAILABLE_FOR_RESEARCH":
            return
        if forecast.model_reference is None or forecast.inference_reference is None:
            raise ValueError("Conditional Forecast available owner lineage is incomplete")
        inference = repository.get_inference(
            forecast.inference_reference.artifact_id
        )
        if inference.receipt_hash != forecast.inference_reference.content_hash:
            raise ValueError("Conditional Forecast inference owner drifted")
        if forecast.fit_available_at != inference.executed_at:
            raise ValueError("Conditional Forecast inference availability drifted")
        comparison_model = repository.get_artifact(
            inference.model_reference.artifact_id
        )
        if (
            comparison_model.artifact_hash
            != inference.model_reference.content_hash
            or comparison_model.request_reference
            != forecast.training_request_reference
        ):
            raise ValueError("Conditional Forecast comparison Model owner drifted")
        if forecast.model_reference.artifact_kind == "RESEARCH_MODEL_ARTIFACT":
            if comparison_model.artifact_hash != forecast.model_reference.content_hash:
                raise ValueError("Conditional Forecast Model owner drifted")
            if inference.model_reference != forecast.model_reference:
                raise ValueError("Conditional Forecast inference/Model binding drifted")
            selected = dict(inference.result.continuous_estimates).get(
                configuration.expected_return_target
            )
        else:
            selected = _path_forecast_median(baseline_forecast)
        if selected != forecast.selected_expected_return:
            raise ValueError("Conditional Forecast selected estimate drifted")
        expected_barriers = (
            tuple(inference.result.raw_barrier_logits)
            if forecast.model_reference.artifact_kind
            == "RESEARCH_MODEL_ARTIFACT"
            else ()
        )
        if expected_barriers != forecast.raw_barrier_scores:
            raise ValueError("Conditional Forecast barrier projection drifted")

    def _persist(self, write: PhaseIIEvidenceWrite) -> HistoricalResearchEvidence:
        if not write.source_references:
            raise ValueError("Phase II Evidence requires immutable owner sources")
        _verify_phase_ii_payload_values(write.evidence_kind, write.payload)
        evidence = HistoricalResearchEvidence.create(
            run_id=write.run_id,
            command_hash=write.command_hash,
            experiment_reference=write.experiment_reference,
            evidence_kind=write.evidence_kind,
            research_question=write.research_question,
            classification=write.classification,
            rationale=write.rationale,
            source_references=write.source_references,
            metrics=write.metrics,
            payload=write.payload,
            created_at=write.created_at,
            limitations=write.limitations,
            statements=(
                *write.statements,
                ResearchStatement(
                    ResearchStatementKind.INVALIDATION_CONDITION,
                    "Any owner reload, hash, time, lineage, or semantic mismatch invalidates this Evidence.",
                ),
            ),
        )
        stored = self._evidence.put(evidence)
        if stored != evidence:
            raise ValueError("Phase II Evidence owner replay diverged")
        return stored


def _verify_phase_ii_payload(evidence: HistoricalResearchEvidence) -> None:
    _verify_phase_ii_payload_values(evidence.evidence_kind, evidence.payload)


def _verify_phase_ii_payload_values(
    kind: HistoricalEvidenceKind,
    payload: Mapping[str, Any],
) -> None:
    if kind is HistoricalEvidenceKind.ALPHA_CORRECTNESS:
        if payload.get("status") not in {
            "CORRECTNESS_SUPPORTED",
            "CORRECTNESS_FAILED",
            "INCONCLUSIVE",
        }:
            raise ValueError("Alpha Correctness Evidence status is invalid")
        raw_proof = payload.get("proof")
        proof = (
            _correctness_proof_projection(raw_proof)
            if isinstance(raw_proof, Mapping)
            else None
        )
        if proof is not None and proof.get("conclusion") != payload.get("status"):
            raise ValueError("Alpha Correctness status projection drifted")
        if payload.get("status") == "CORRECTNESS_SUPPORTED":
            if proof is None:
                raise ValueError("supported Alpha Correctness lacks typed proof")
            if proof.get("conclusion") != "CORRECTNESS_SUPPORTED":
                raise ValueError("Alpha Correctness status projection drifted")
            required_suite = {
                "feature_results",
                "target_results",
                "physical_verifications",
                "normalization_verifications",
                "placebo_results",
                "execution_diagnostics",
                "factor_redundancy",
                "robust_inference",
            }
            if not required_suite.issubset(proof) or any(
                not proof.get(field_name)
                for field_name in required_suite - {"factor_redundancy"}
            ):
                raise ValueError("Alpha Correctness proof suite is incomplete")
            redundancy = proof.get("factor_redundancy")
            if not isinstance(redundancy, Mapping) or redundancy.get("status") == "NOT_ESTIMABLE":
                raise ValueError("Alpha Correctness redundancy diagnostic is incomplete")
        return
    if kind is HistoricalEvidenceKind.EXTERNAL_VALIDATION:
        evaluation = _embedded_artifact(payload, "evaluation", "evaluation_id", "evaluation_hash")
        experiment = payload.get("experiment")
        if not isinstance(experiment, Mapping):
            raise ValueError("External Validation Evidence lacks frozen Experiment")
        if (
            str(experiment.get("experiment_id"))
            != str(_mapping_value(evaluation.get("experiment_reference")).get("artifact_id"))
            or str(experiment.get("experiment_hash"))
            != str(_mapping_value(evaluation.get("experiment_reference")).get("content_hash"))
        ):
            raise ValueError("External Validation Experiment projection drifted")
        if payload.get("qualification_status") != evaluation.get("qualification_status"):
            raise ValueError("External Validation qualification projection drifted")
        if payload.get("validated_factors") != evaluation.get("factor_directions"):
            raise ValueError("External Validation Factor projection drifted")
        return
    if kind is HistoricalEvidenceKind.CONTEXT_CONDITIONAL:
        evaluation = _embedded_artifact(payload, "evaluation", "evaluation_id", "evaluation_hash")
        if payload.get("status") != evaluation.get("status"):
            raise ValueError("Context Evaluation status projection drifted")
        return
    if kind is HistoricalEvidenceKind.CANDIDATE_POLICY:
        if "evaluation" in payload:
            _embedded_artifact(payload, "evaluation", "evaluation_id", "evaluation_hash")
        elif "comparison" in payload:
            _embedded_artifact(payload, "comparison", "comparison_id", "comparison_hash")
        else:
            raise ValueError("Candidate Policy Evidence lacks typed artifact")
        return
    if kind is HistoricalEvidenceKind.CONDITIONAL_PREDICTION:
        forecast = _embedded_artifact(payload, "forecast", "result_id", "result_hash")
        result = ConditionalForecastResult.from_canonical_dict(forecast)
        raw_configuration = payload.get("configuration")
        raw_baseline = payload.get("baseline_forecast")
        if (
            not isinstance(raw_configuration, Mapping)
            or not isinstance(raw_baseline, Mapping)
        ):
            raise ValueError("Conditional Prediction Evidence lacks frozen owners")
        configuration = ConditionalForecastConfig.from_canonical_dict(
            raw_configuration
        )
        baseline = PathForecastArtifact.from_canonical_dict(dict(raw_baseline))
        if configuration.reference != result.configuration_reference:
            raise ValueError("Conditional Forecast configuration projection drifted")
        if _path_forecast_reference(baseline) != result.baseline_reference:
            raise ValueError("Conditional Forecast baseline projection drifted")


def _correctness_proof_projection(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    proof_id = value.get("proof_id")
    proof_hash = value.get("proof_hash")
    projection_hash = value.get("projection_hash")
    if not isinstance(proof_id, str) or not isinstance(proof_hash, str):
        raise ValueError("Alpha Correctness proof projection identity is incomplete")
    require_sha256("Alpha Correctness proof hash", proof_hash)
    if proof_id != f"alpha-correctness-proof:{proof_hash[7:]}":
        raise ValueError("Alpha Correctness full proof root identity mismatch")
    if projection_hash is None:
        legacy_payload = dict(value)
        del legacy_payload["proof_id"]
        del legacy_payload["proof_hash"]
        if canonical_hash(legacy_payload) != proof_hash:
            raise ValueError("Alpha Correctness legacy proof hash mismatch")
        return value
    if not isinstance(projection_hash, str):
        raise ValueError("Alpha Correctness proof projection identity is incomplete")
    require_sha256("Alpha Correctness proof projection hash", projection_hash)
    projection = dict(value)
    del projection["proof_id"]
    del projection["proof_hash"]
    del projection["projection_hash"]
    if (
        canonical_hash(projection) != projection_hash
        or projection.get("schema_version")
        != "alpha-correctness-evidence-projection/v1"
        or projection.get("full_proof_owner_reload_required") is not True
    ):
        raise ValueError("Alpha Correctness proof projection hash mismatch")
    return value


def _embedded_artifact(
    payload: Mapping[str, Any],
    field_name: str,
    identity_field: str,
    hash_field: str,
) -> Mapping[str, Any]:
    artifact = payload.get(field_name)
    if not isinstance(artifact, Mapping):
        raise ValueError(f"Phase II Evidence {field_name} artifact is missing")
    identity = artifact.get(identity_field)
    digest = artifact.get(hash_field)
    if not isinstance(identity, str) or not isinstance(digest, str):
        raise ValueError(f"Phase II Evidence {field_name} identity is incomplete")
    identity_payload = dict(artifact)
    del identity_payload[identity_field]
    del identity_payload[hash_field]
    if canonical_hash(identity_payload) != digest or not identity.endswith(digest[7:]):
        raise ValueError(f"Phase II Evidence {field_name} identity mismatch")
    return artifact


def _with_required_sources(
    write: PhaseIIEvidenceWrite,
    *required: ValidationArtifactReference,
) -> PhaseIIEvidenceWrite:
    """Freeze typed owner-derived lineage; callers cannot omit authoritative refs."""

    references = tuple(
        sorted(
            {*write.source_references, *required},
            key=lambda item: (
                item.artifact_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )
    return replace(write, source_references=references)


def _verify_correctness_proof_against_owners(
    *,
    proof: AlphaCorrectnessProof,
    reproduction: HistoricalCorrectnessReproduction,
    corpus: PostgresHistoricalCorpusRepository,
) -> None:
    """Rebuild every correctness claim from reloaded owners before persistence."""

    if (
        proof.feature_results != reproduction.feature_results
        or proof.target_results != reproduction.target_results
        or proof.physical_verifications != reproduction.physical_verifications
    ):
        raise ValueError("Alpha Correctness proof drifted from Historical owner replay")
    expected_normalization = tuple(
        sorted(
            (
                verify_independent_baostock_package_normalization(
                    corpus=corpus,
                    raw_owner_reference=item.raw_owner_reference,
                    normalized_owner_reference=item.normalized_owner_reference,
                    provenance=item.provenance,
                )
                for item in proof.normalization_verifications
            ),
            key=lambda item: str(item.normalized_owner_reference.artifact_id),
        )
    )
    if expected_normalization != proof.normalization_verifications:
        raise ValueError(
            "Alpha Correctness independent normalization drifted from owners"
        )
    factor_observations = _correctness_factor_observations(reproduction)
    alpha_by_factor = {
        factor_id: tuple(
            AlphaObservation(
                item.session,
                item.symbol,
                item.factors[factor_id],
                item.target_return,
            )
            for item in factor_observations
        )
        for factor_id in (
            "intraday_return_to_decision_time",
            "price_vs_vwap_return",
            "vwap_slope",
        )
    }
    expected_placebos = tuple(
        sorted(
            (
                apply_placebo(
                    result.protocol,
                    kind=result.kind,
                    observations=alpha_by_factor[result.factor_id],
                )
                for result in proof.placebo_results
            ),
            key=lambda item: (item.factor_id, item.kind.value),
        )
    )
    if expected_placebos != proof.placebo_results:
        raise ValueError("Alpha Correctness placebo suite drifted from owner population")
    if evaluate_factor_redundancy(factor_observations) != proof.factor_redundancy:
        raise ValueError("Alpha Correctness redundancy drifted from owner population")
    if proof.robust_inference:
        protocols = {item.protocol for _factor, item in proof.robust_inference}
        if len(protocols) != 1:
            raise ValueError("Alpha Correctness inference protocols drifted")
        protocol = next(iter(protocols))
        expected_inference = tuple(
            sorted(
                evaluate_robust_inference_family(
                    protocol,
                    {
                        factor_id: factor_rank_ic_session_estimates(
                            factor_observations,
                            factor_id=factor_id,
                        )
                        for factor_id, _result in proof.robust_inference
                    },
                ).items()
            )
        )
        if expected_inference != proof.robust_inference:
            raise ValueError("Alpha Correctness inference drifted from owner population")
    _verify_execution_diagnostics_against_corpus(
        proof=proof,
        reproduction=reproduction,
        corpus=corpus,
    )


def _correctness_factor_observations(
    reproduction: HistoricalCorrectnessReproduction,
) -> tuple[FactorObservation, ...]:
    target_return_by_key = {
        (item.decision_time, item.symbol): item.target_return
        for item in reproduction.target_results
        if item.target_return is not None
    }
    return tuple(
        FactorObservation(
            item.session,
            item.symbol,
            {
                comparison.factor_id: comparison.recomputed_value
                for comparison in item.comparisons
            },
            target_return_by_key[(item.decision_time, item.symbol)],
        )
        for item in reproduction.feature_results
        if {comparison.factor_id for comparison in item.comparisons}
        == {
            "intraday_return_to_decision_time",
            "price_vs_vwap_return",
            "vwap_slope",
        }
        and (item.decision_time, item.symbol) in target_return_by_key
    )


def _first_complete_execution_diagnostic(
    *,
    reproduction: HistoricalCorrectnessReproduction,
    corpus: PostgresHistoricalCorpusRepository,
) -> tuple[ExecutionTimingDiagnostic, ...]:
    physical_owners = {
        item.normalized_owner_reference
        for item in reproduction.physical_verifications
    }
    for target in reproduction.target_results:
        owner_reference = target.physical_source_reference
        if target.persisted_observation is None or owner_reference not in physical_owners:
            continue
        source_slice = corpus.read(
            HistoricalReadQuery.create(
                reference=owner_reference,
                timeframes=(Timeframe.MINUTE_5,),
                first_market_date=target.decision_time.date(),
                last_market_date=target.target_session,
                symbols=(target.symbol,),
                max_rows=200,
                batch_size=200,
            )
        )
        source_bars = tuple(
            item
            for item in source_slice.records
            if isinstance(item, HistoricalNormalizedBar)
        )
        try:
            return reproduce_execution_timing_diagnostics(
                target=target,
                source_bars=source_bars,
            )
        except ValueError as exc:
            if str(exc) != "execution proxy is not estimable from frozen source bars":
                raise
    return ()


def _verify_execution_diagnostics_against_corpus(
    *,
    proof: AlphaCorrectnessProof,
    reproduction: HistoricalCorrectnessReproduction,
    corpus: PostgresHistoricalCorpusRepository,
) -> None:
    if not proof.execution_diagnostics:
        return
    physical_owners = {
        item.normalized_owner_reference
        for item in reproduction.physical_verifications
    }
    if not physical_owners:
        if proof.status.value == "CORRECTNESS_SUPPORTED":
            raise ValueError("supported Alpha Correctness lacks physical execution owners")
        return
    targets = tuple(reproduction.target_results)
    populations = {
        (
            item.information_cutoff,
            item.information_cutoff_price,
            item.target_reference_price,
            item.target_observed_at,
        )
        for item in proof.execution_diagnostics
    }
    if len(populations) != 1:
        raise ValueError("Execution diagnostics must describe one frozen population")
    population = next(iter(populations))
    matching = tuple(
        target
        for target in targets
        if (
            target.decision_time,
            target.decision_reference_price,
            target.target_price,
            target.target_event_end,
        )
        == population
    )
    if len(matching) != 1:
        raise ValueError("Execution diagnostics are outside correctness Target owners")
    target = matching[0]
    owner_reference = target.physical_source_reference
    if owner_reference not in physical_owners:
        raise ValueError("Execution diagnostics lack physical owner lineage")
    source_slice = corpus.read(
        HistoricalReadQuery.create(
            reference=owner_reference,
            timeframes=(Timeframe.MINUTE_5,),
            first_market_date=target.decision_time.date(),
            last_market_date=target.target_session,
            symbols=(target.symbol,),
            max_rows=200,
            batch_size=200,
        )
    )
    source_bars = tuple(
        item
        for item in source_slice.records
        if isinstance(item, HistoricalNormalizedBar)
    )
    expected = reproduce_execution_timing_diagnostics(
        target=target,
        source_bars=source_bars,
    )
    if expected != proof.execution_diagnostics:
        raise ValueError("Execution proxy semantics drifted from physical owner bars")


def _verify_hypothesis_against_owner_evidence(
    *,
    hypothesis: FrozenAlphaHypothesis,
    correctness: HistoricalResearchEvidence,
    discovery: HistoricalResearchEvidence,
) -> None:
    """Reject caller projections that cannot be rebuilt from immutable Evidence."""

    required_discovery_sources = {
        hypothesis.feature_reference,
        hypothesis.target_reference,
        hypothesis.cost_policy_reference,
    }
    if not required_discovery_sources.issubset(discovery.source_references):
        raise ValueError("frozen hypothesis owner lineage is absent from Discovery Evidence")
    proof = correctness.payload.get("proof")
    if not isinstance(proof, Mapping):
        raise ValueError("frozen hypothesis requires a typed Alpha Correctness proof")
    factor_projection = proof.get("factor_ids")
    if isinstance(factor_projection, list):
        correctness_factors = {str(item) for item in factor_projection}
    else:
        feature_results = proof.get("feature_results")
        if not isinstance(feature_results, list):
            raise ValueError("Alpha Correctness proof lacks Feature results")
        correctness_factors = {
            str(comparison.get("factor_id"))
            for result in feature_results
            if isinstance(result, Mapping)
            for comparison in result.get("comparisons", [])
            if isinstance(comparison, Mapping)
        }
    hypothesis_factors = {factor_id for factor_id, _direction in hypothesis.factor_directions}
    if correctness_factors != hypothesis_factors:
        raise ValueError("frozen hypothesis Factors drifted from Alpha Correctness proof")
    alpha_discovery = discovery.payload.get("alpha_discovery")
    if not isinstance(alpha_discovery, Mapping):
        raise ValueError("Discovery Evidence lacks canonical Alpha Discovery payload")
    factor_results = alpha_discovery.get("factor_results")
    policy_results = alpha_discovery.get("candidate_policy_results")
    if not isinstance(factor_results, list) or not isinstance(policy_results, list):
        raise ValueError("Discovery Evidence result families are incomplete")
    discovered_factors = {
        str(item.get("variant_id")).rsplit(":", 1)[-1]
        for item in factor_results
        if isinstance(item, Mapping)
    }
    if hypothesis_factors != discovered_factors.intersection(hypothesis_factors):
        raise ValueError("frozen hypothesis includes a Factor absent from Discovery Evidence")
    variants = {
        str(item.get("variant_id")): item
        for item in policy_results
        if isinstance(item, Mapping)
    }
    variant = variants.get(hypothesis.discovery_variant_id)
    if variant is None:
        raise ValueError("frozen hypothesis Candidate variant is absent from Discovery Evidence")
    if Decimal(str(variant.get("mean_rank_ic"))) != hypothesis.discovery_rank_ic:
        raise ValueError("frozen hypothesis Discovery effect projection drifted")
    discovered_directions = tuple(
        sorted(
            (str(item[0]), str(item[1]))
            for item in variant.get("factor_directions", ())
            if isinstance(item, (list, tuple)) and len(item) == 2
        )
    )
    if discovered_directions != hypothesis.factor_directions:
        raise ValueError(
            "frozen hypothesis Factor definitions/directions drifted from Discovery"
        )
    top_k = variant.get("top_k")
    if not isinstance(top_k, Mapping):
        raise ValueError("Discovery Candidate variant lacks Top-K economics")
    top_k_result = top_k.get(str(hypothesis.top_k))
    if not isinstance(top_k_result, Mapping):
        raise ValueError("frozen hypothesis Top-K was not evaluated during Discovery")
    discovered_cost = top_k_result.get("assumed_cost_return")
    if discovered_cost is None or abs(Decimal(str(discovered_cost))) != hypothesis.cost_assumption:
        raise ValueError("frozen hypothesis cost assumption drifted from Discovery Evidence")


def _verify_external_panel_owners(
    *,
    components: PostgresHistoricalMaterializationRepository,
    panel_references: tuple[ValidationArtifactReference, ...],
    discovery_scope: ValidationScope,
    validation_scope: ValidationScope,
    temporal_window: FrozenTemporalValidationWindow | None,
    dimension: ValidationDimension,
    discovery: HistoricalResearchEvidence,
    expected_population: int,
) -> None:
    """Reload Panel owners and prove the declared external scope from lineage."""

    if not panel_references or len(panel_references) != len(set(panel_references)):
        raise ValueError("External validation Panel owner set is empty or duplicated")
    if set(panel_references).intersection(discovery.source_references):
        raise ValueError("External validation cannot reuse a Discovery Panel owner")
    panels = tuple(components.get(reference) for reference in panel_references)
    if any(
        panel.component_kind is not HistoricalComponentKind.RESEARCH_PANEL
        for panel in panels
    ):
        raise ValueError("External validation source is not a canonical Research Panel")
    if dimension is ValidationDimension.TEMPORAL_VALIDATION and not (
        validation_scope.last_session < discovery_scope.first_session
        or validation_scope.first_session > discovery_scope.last_session
    ):
        raise ValueError("Temporal validation sessions overlap Discovery sessions")
    if dimension is ValidationDimension.TEMPORAL_VALIDATION:
        if temporal_window is None:
            raise ValueError("Temporal validation requires a frozen Calendar window")
        panel_sessions = tuple(sorted(panel.trading_date for panel in panels))
        if panel_sessions != temporal_window.decision_sessions:
            raise ValueError(
                "Validation Panel owners do not match all frozen Calendar sessions"
            )
    elif temporal_window is not None:
        raise ValueError("Temporal window cannot qualify another validation dimension")
    row_count = 0
    for panel in panels:
        if not (
            validation_scope.first_session
            <= panel.trading_date
            <= validation_scope.last_session
        ):
            raise ValueError("Validation Panel session is outside frozen temporal scope")
        raw_row_count = panel.payload.get("row_count")
        if not isinstance(raw_row_count, int) or raw_row_count < 0:
            raise ValueError("Validation Panel row count is invalid")
        row_count += raw_row_count
        lineage = _transitive_panel_lineage(components, panel)
        if validation_scope.universe_reference not in lineage:
            raise ValueError("Validation Panel lacks frozen Universe owner lineage")
        if validation_scope.provider_reference not in lineage:
            raise ValueError("Validation Panel lacks frozen Provider dataset owner lineage")
    if row_count != expected_population:
        raise ValueError("External validation population drifted from Panel owners")


def _verify_hypothesis_configuration_owners(
    validation: PostgresResearchValidationRepository,
    hypothesis: FrozenAlphaHypothesis,
) -> None:
    feature = validation.get_feature_set_configuration(
        hypothesis.feature_reference.artifact_id
    )
    feature_reference = ValidationArtifactReference(
        "FEATURE_SET_CONFIGURATION",
        feature.feature_set_id,
        feature.content_hash,
    )
    if (
        feature_reference != hypothesis.feature_reference
        or feature.feature_set_version != hypothesis.feature_version
    ):
        raise ValueError("frozen hypothesis Feature owner/version drifted")
    economics = validation.get_historical_strategy_economics_policy_set(
        hypothesis.cost_policy_reference.artifact_id
    )
    economics_reference = ValidationArtifactReference(
        hypothesis.cost_policy_reference.artifact_kind,
        economics.policy_set_id,
        economics.policy_set_hash,
    )
    if economics_reference != hypothesis.cost_policy_reference:
        raise ValueError("frozen hypothesis Cost policy owner drifted")
    if hypothesis.target_reference not in {
        item.prediction_target_reference for item in economics.strategy_policies
    }:
        raise ValueError("frozen hypothesis Target is absent from Cost policy owner")
    policy = economics.policy_for_reference(hypothesis.target_reference)
    policy_reference = ValidationArtifactReference(
        "STRATEGY_ECONOMICS_POLICY",
        policy.policy_id,
        policy.policy_hash,
    )
    if (
        policy_reference != hypothesis.economics_policy_reference
        or policy.entry_kind.value != hypothesis.execution_entry_kind
    ):
        raise ValueError("frozen hypothesis execution semantics drifted from Cost owner")


def _transitive_panel_lineage(
    components: PostgresHistoricalMaterializationRepository,
    panel: HistoricalSessionComponent,
) -> set[ValidationArtifactReference]:
    component_kinds = {
        f"HISTORICAL_{kind.value}" for kind in HistoricalComponentKind
    }
    lineage: set[ValidationArtifactReference] = set()
    pending = list(panel.source_references)
    visited: set[ValidationArtifactReference] = set()
    while pending:
        reference = pending.pop()
        if reference in visited:
            continue
        visited.add(reference)
        lineage.add(reference)
        if reference.artifact_kind in component_kinds:
            owner = components.get(reference)
            pending.extend(owner.source_references)
    return lineage


def _external_data_ceiling(
    *,
    components: PostgresHistoricalMaterializationRepository,
    corpus: PostgresHistoricalCorpusRepository,
    panels: tuple[HistoricalSessionComponent, ...],
) -> tuple[bool, bool]:
    """Derive PIT/free-data ceilings from exact dataset owners, never callers."""

    normalized = {
        reference
        for panel in panels
        for reference in _transitive_panel_lineage(components, panel)
        if reference.artifact_kind == "NORMALIZED_DATASET"
    }
    if not normalized:
        raise ValueError("External validation lacks normalized-data owner lineage")
    owners = tuple(corpus.load(reference).owner for reference in normalized)
    pit_complete = all(
        owner.formal_pit_status == "PIT_CORRECT_FOR_DECLARED_SCOPE"
        for owner in owners
    )
    free_data = any(owner.data_eligibility != "FORMAL_RESEARCH" for owner in owners)
    return pit_complete, free_data


def _panel_row_count(
    panel: HistoricalSessionComponent,
    *,
    label: str,
) -> int:
    if panel.component_kind is not HistoricalComponentKind.RESEARCH_PANEL:
        raise ValueError(f"{label} source is not a Research Panel owner")
    value = panel.payload.get("row_count")
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} Research Panel row count is invalid")
    return value


def _candidate_inputs_from_panels(
    policy: CandidatePolicyDefinition,
    panels: tuple[HistoricalSessionComponent, ...],
) -> tuple[CandidatePolicyInput, ...]:
    inputs: list[CandidatePolicyInput] = []
    for panel in panels:
        _panel_row_count(panel, label="Candidate")
        rows = panel.payload.get("rows")
        if not isinstance(rows, list):
            raise ValueError("Candidate Research Panel rows are unavailable")
        for raw in rows:
            if not isinstance(raw, Mapping):
                raise ValueError("Candidate Research Panel row is malformed")
            diagnostics = raw.get("gate_diagnostics")
            if not isinstance(diagnostics, Mapping):
                raise ValueError("Candidate hard-integrity diagnostics are unavailable")
            hard = diagnostics.get("hard_integrity")
            if not isinstance(hard, Mapping):
                raise ValueError("Candidate hard-integrity owner projection is malformed")
            passed = bool(hard.get("passed"))
            raw_reasons = hard.get("reason_codes")
            checks = hard.get("checks")
            if not isinstance(raw_reasons, list) or not isinstance(checks, Mapping):
                raise ValueError("Candidate hard-integrity reasons are malformed")
            hard_reasons = tuple(sorted({str(item) for item in raw_reasons}))
            if passed == bool(hard_reasons):
                raise ValueError(
                    "Candidate hard-integrity owner status/reasons disagree"
                )
            factor_values = _panel_feature_values(raw.get("research_features"))
            liquidity = _optional_decimal_value(hard.get("liquidity"))
            if liquidity is None:
                raise ValueError("Candidate universal liquidity owner is unavailable")
            incumbent_score = _optional_decimal_value(raw.get("score"))
            context_values = {
                definition.context_id: _candidate_context_value(
                    definition.context_id, raw
                )
                for definition in policy.context_adjustments
            }
            inputs.append(
                CandidatePolicyInput(
                    session=panel.trading_date,
                    symbol=str(raw["symbol"]),
                    dataset_reference=policy.dataset_reference,
                    universe_eligible=bool(checks.get("universe_eligible")),
                    tradable=bool(checks.get("tradable")),
                    suspended=not bool(checks.get("not_suspended")),
                    data_integrity=bool(checks.get("data_integrity")),
                    required_history=bool(checks.get("required_history")),
                    pit_correct=bool(checks.get("pit_boundary_satisfied")),
                    liquidity=liquidity,
                    trading_restrictions_satisfied=bool(
                        checks.get("a_share_restrictions")
                    ),
                    factor_values=factor_values,
                    context_values=context_values,
                    incumbent_score=incumbent_score,
                    incumbent_selected=bool(raw.get("selected")),
                    incumbent_factor_contributions=(
                        {}
                        if incumbent_score is None
                        else {"INCUMBENT_LEGACY_COMPOSITE": incumbent_score}
                    ),
                    incumbent_hard_integrity_eligible=passed,
                    incumbent_hard_gate_failure_reasons=hard_reasons,
                    universal_hard_integrity_eligible=passed,
                    universal_hard_gate_failure_reasons=hard_reasons,
                )
            )
    return tuple(sorted(inputs, key=lambda item: (item.session, item.symbol)))


def _panel_feature_values(value: object) -> dict[str, Decimal | None]:
    if not isinstance(value, list):
        raise ValueError("Candidate Panel Feature projection is malformed")
    result: dict[str, Decimal | None] = {}
    for raw in value:
        if not isinstance(raw, Mapping):
            raise ValueError("Candidate Panel Feature row is malformed")
        factor_id = str(raw.get("output_id"))
        if factor_id in result:
            raise ValueError("Candidate Panel Feature output is duplicated")
        factor_value = raw.get("value")
        result[factor_id] = (
            None
            if raw.get("state") != "AVAILABLE" or factor_value is None
            else Decimal(str(factor_value))
        )
    return result


def _candidate_returns_from_panels(
    protocol: CandidateComparisonProtocol,
    panels: tuple[HistoricalSessionComponent, ...],
) -> tuple[CandidateRealizedReturn, ...]:
    values: list[CandidateRealizedReturn] = []
    for panel in panels:
        _panel_row_count(panel, label="Candidate comparison")
        rows = panel.payload.get("rows")
        if not isinstance(rows, list):
            raise ValueError("Candidate comparison Panel rows are unavailable")
        for raw in rows:
            if not isinstance(raw, Mapping):
                raise ValueError("Candidate comparison Panel row is malformed")
            target = _validation_reference_value(raw.get("target_reference"))
            realized = _optional_decimal_value(raw.get("target_return"))
            if target is None or realized is None:
                raise ValueError("Candidate comparison frozen Target population is incomplete")
            if target != protocol.target_reference:
                raise ValueError("Candidate comparison Panel Target owner drifted")
            values.append(
                CandidateRealizedReturn(
                    panel.trading_date,
                    str(raw["symbol"]),
                    realized,
                    protocol.dataset_reference,
                    target,
                )
            )
    return tuple(sorted(values, key=lambda item: (item.session, item.symbol)))


def _validation_reference_value(
    value: object,
) -> ValidationArtifactReference | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("Historical Panel owner reference is malformed")
    return ValidationArtifactReference.from_canonical_dict(value)


def _candidate_context_value(
    context_id: str,
    row: Mapping[str, Any],
) -> Decimal | None:
    if context_id.upper() == "LIQUIDITY":
        return _optional_decimal_value(row.get("capacity_ceiling"))
    return None


def _optional_decimal_value(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _path_forecast_reference(
    value: PathForecastArtifact,
) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        "PATH_FORECAST",
        value.artifact_id,
        value.forecast.envelope.content_hash,
    )


def _path_forecast_median(value: PathForecastArtifact) -> Decimal | None:
    return next(
        (
            Decimal(str(item.return_value))
            for item in value.forecast.return_quantiles
            if Decimal(str(item.probability)) == Decimal("0.5")
        ),
        None,
    )


def _verify_conditional_sample_bindings(
    forecast: ConditionalForecastResult,
    request: ResearchModelTrainingRequest,
) -> None:
    samples = {item.sample_id: item for item in request.samples}
    expected_training = {
        item for fold in request.folds for item in fold.train_sample_ids
    }
    expected_validation = {
        item for fold in request.folds for item in fold.validation_sample_ids
    }
    training = tuple(
        sorted((str(item), samples[item].sample_hash) for item in expected_training)
    )
    validation = tuple(
        sorted((str(item), samples[item].sample_hash) for item in expected_validation)
    )
    if (
        training != forecast.training_sample_bindings
        or validation != forecast.validation_sample_bindings
    ):
        raise ValueError("Conditional Forecast sample owner bindings drifted")


def _mapping_value(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Phase II owner payload must be an object")
    return value


def _strict_factor_directions(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("External Validation Factors must be an array")
    parsed: list[tuple[str, str]] = []
    for item in value:
        if (
            not isinstance(item, (list, tuple))
            or len(item) != 2
            or not isinstance(item[0], str)
            or not item[0].strip()
            or not isinstance(item[1], str)
            or not item[1].strip()
        ):
            raise ValueError("External Validation Factor lineage is malformed")
        parsed.append((item[0], item[1]))
    result = tuple(parsed)
    if not result or result != tuple(sorted(set(result))):
        raise ValueError(
            "External Validation Factors must be non-empty, unique and sorted"
        )
    return result


def _phase_ii_lineage_stage(
    stage: str,
    evidence: HistoricalResearchEvidence,
) -> dict[str, str]:
    return {
        "stage": stage,
        "run_id": str(evidence.run_id),
        "command_hash": evidence.command_hash,
        "experiment_id": str(evidence.experiment_reference.artifact_id),
        "experiment_hash": evidence.experiment_reference.content_hash,
    }


__all__ = [
    "HistoricalPhaseIIResearchService",
    "PhaseIIEvidenceWrite",
]
