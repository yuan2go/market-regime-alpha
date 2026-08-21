"""Owner-resolved Phase II research composition over existing Historical Evidence.

This is an application capability of Historical Research, not a new Runtime or
Evidence authority.  Every admission reloads immutable PostgreSQL Evidence and
every result is written through ``PostgresHistoricalEvidenceRepository``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
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
)
from market_regime_alpha.application.historical_corpus.external_validation import (
    ExternalValidationEvaluation,
    FrozenAlphaHypothesis,
    FrozenExternalValidationExperiment,
    ValidationDimension,
    ValidationScope,
)
from market_regime_alpha.application.historical_corpus.context_conditional import (
    ContextConditionalEvaluation,
    ContextDefinition,
    ContextKind,
    ContextResearchRole,
)
from market_regime_alpha.application.historical_corpus.postgres_evidence import (
    PostgresHistoricalEvidenceRepository,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.candidates.policy import (
    CandidatePolicyComparison,
    CandidatePolicyEvaluation,
    ContextAdjustmentDefinition,
    ValidatedFactorDefinition,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.forecasting.conditional import ConditionalForecastResult


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

    def __init__(self, evidence: PostgresHistoricalEvidenceRepository) -> None:
        self._evidence = evidence

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

    def create_external_experiment(
        self,
        *,
        hypothesis: FrozenAlphaHypothesis,
        correctness_evidence_id: ArtifactId,
        discovery_scope: ValidationScope,
        validation_scope: ValidationScope,
        dimension: ValidationDimension,
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
        return FrozenExternalValidationExperiment.create(
            hypothesis=hypothesis,
            correctness_evidence=correctness,
            discovery_scope=discovery_scope,
            validation_scope=validation_scope,
            dimension=dimension,
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

    def context_definition(
        self,
        *,
        context_id: str,
        kind: ContextKind,
        role: ContextResearchRole,
        public_observable_proxy: bool,
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
            alpha_evidence=evidence,
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
    ) -> HistoricalResearchEvidence:
        if write.evidence_kind is not HistoricalEvidenceKind.ALPHA_CORRECTNESS:
            raise ValueError("Alpha Correctness proof Evidence kind mismatch")
        return self._persist(
            replace(
                write,
                payload={
                    "status": proof.status.value,
                    "proof": proof.to_canonical_dict(),
                },
            )
        )

    def persist_external_evaluation(
        self,
        write: PhaseIIEvidenceWrite,
        evaluation: ExternalValidationEvaluation,
    ) -> HistoricalResearchEvidence:
        if write.evidence_kind is not HistoricalEvidenceKind.EXTERNAL_VALIDATION:
            raise ValueError("External Evaluation Evidence kind mismatch")
        if write.experiment_reference != evaluation.experiment_reference:
            raise ValueError("External Evaluation Experiment owner drifted")
        _require_sources(write, evaluation.thresholds_reference)
        return self._persist(
            replace(
                write,
                payload={
                    "evaluation": evaluation.to_canonical_dict(),
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
        _require_sources(write, evaluation.definition_reference)
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
        _require_sources(
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
        _require_sources(
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

    def persist_conditional_forecast(
        self,
        write: PhaseIIEvidenceWrite,
        forecast: ConditionalForecastResult,
    ) -> HistoricalResearchEvidence:
        if write.evidence_kind is not HistoricalEvidenceKind.CONDITIONAL_PREDICTION:
            raise ValueError("Conditional Forecast Evidence kind mismatch")
        _require_sources(
            write,
            forecast.configuration_reference,
            forecast.baseline_reference,
            *((forecast.model_reference,) if forecast.model_reference is not None else ()),
        )
        return self._persist(
            replace(write, payload={"forecast": forecast.to_canonical_dict()})
        )

    def _persist(self, write: PhaseIIEvidenceWrite) -> HistoricalResearchEvidence:
        if not write.source_references:
            raise ValueError("Phase II Evidence requires immutable owner sources")
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
            "PARTIALLY_REPRODUCED",
            "PHYSICAL_REPRODUCTION_NOT_ESTABLISHED",
        }:
            raise ValueError("Alpha Correctness Evidence status is invalid")
        if payload.get("status") == "CORRECTNESS_SUPPORTED":
            proof = _embedded_artifact(payload, "proof", "proof_id", "proof_hash")
            if proof.get("status") != "CORRECTNESS_SUPPORTED":
                raise ValueError("Alpha Correctness status projection drifted")
        return
    if kind is HistoricalEvidenceKind.EXTERNAL_VALIDATION:
        evaluation = _embedded_artifact(payload, "evaluation", "evaluation_id", "evaluation_hash")
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
        _embedded_artifact(payload, "forecast", "result_id", "result_hash")


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


def _require_sources(
    write: PhaseIIEvidenceWrite,
    *required: ValidationArtifactReference,
) -> None:
    missing = set(required).difference(write.source_references)
    if missing:
        raise ValueError("Phase II Evidence is missing required artifact owner lineage")


__all__ = [
    "HistoricalPhaseIIResearchService",
    "PhaseIIEvidenceWrite",
]
