from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from market_regime_alpha.application.continuous_research.daily_alpha import (
    DailyAlphaActivationStatus,
    DailyAlphaEvidenceGate,
    DailyAlphaPredictionSnapshot,
    DailyAlphaSymbolProjection,
    EVIDENCE_DEPENDENCY_NOT_SATISFIED,
    assess_daily_alpha_evidence_gate,
)
from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalEvidenceKind,
    HistoricalResearchEvidence,
    ResearchFinding,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.candidates.policy import research_panel_dataset_reference
from market_regime_alpha.evidence.canonical import canonical_hash


NOW = datetime(2026, 8, 21, 6, 55, tzinfo=UTC)


def _reference(kind: str, name: str) -> RuntimeArtifactReference:
    return RuntimeArtifactReference(
        kind,
        ArtifactId(name),
        canonical_hash({"kind": kind, "name": name}),
    )


def _validation_reference(kind: str, name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(name),
        canonical_hash({"kind": kind, "name": name}),
    )


def _historical(
    kind: HistoricalEvidenceKind,
    payload: dict[str, object],
    *,
    name: str | None = None,
    run_id: ArtifactId = ArtifactId("historical-run"),
    command_hash: str | None = None,
    experiment_reference: ValidationArtifactReference | None = None,
    source_references: tuple[ValidationArtifactReference, ...] | None = None,
    classification: ResearchFinding = ResearchFinding.POSITIVE,
) -> HistoricalResearchEvidence:
    return HistoricalResearchEvidence.create(
        run_id=run_id,
        command_hash=command_hash or canonical_hash({"command": str(run_id)}),
        experiment_reference=experiment_reference
        or _validation_reference(
            "RESEARCH_EXPERIMENT_DEFINITION", name or f"{kind.value}-experiment"
        ),
        evidence_kind=kind,
        research_question=kind.value,
        classification=classification,
        rationale="frozen result",
        source_references=source_references
        or (_validation_reference("SOURCE", name or kind.value),),
        metrics=(),
        payload=payload,
        created_at=NOW,
    )


def _lineage_stage(stage: str, evidence: HistoricalResearchEvidence) -> dict[str, str]:
    return {
        "stage": stage,
        "run_id": str(evidence.run_id),
        "command_hash": evidence.command_hash,
        "experiment_id": str(evidence.experiment_reference.artifact_id),
        "experiment_hash": evidence.experiment_reference.content_hash,
    }


def _supported_chain() -> tuple[
    HistoricalResearchEvidence,
    HistoricalResearchEvidence,
    HistoricalResearchEvidence,
    HistoricalResearchEvidence,
]:
    panels = (
        _validation_reference("HISTORICAL_RESEARCH_PANEL", "panel-a"),
        _validation_reference("HISTORICAL_RESEARCH_PANEL", "panel-b"),
    )
    dataset = research_panel_dataset_reference(panels)
    factor_directions = (("price_vs_vwap_return", "HIGHER_IS_BETTER"),)
    discovery = _historical(
        HistoricalEvidenceKind.ALPHA_ABLATION,
        {"status": "DISCOVERY_SUPPORTED"},
        name="discovery",
    )
    correctness = _historical(
        HistoricalEvidenceKind.ALPHA_CORRECTNESS,
        {"status": "CORRECTNESS_SUPPORTED"},
        name="correctness",
        source_references=(discovery.reference,),
    )
    external_experiment = _validation_reference(
        "RESEARCH_EXPERIMENT_DEFINITION", "external-experiment"
    )
    hypothesis = _validation_reference("FROZEN_ALPHA_HYPOTHESIS", "hypothesis")
    external = _historical(
        HistoricalEvidenceKind.EXTERNAL_VALIDATION,
        {
            "qualification_status": "SUPPORTED",
            "validated_factors": [list(item) for item in factor_directions],
            "experiment": {
                "experiment_id": str(external_experiment.artifact_id),
                "experiment_hash": external_experiment.content_hash,
                "correctness_evidence_reference": correctness.reference.to_canonical_dict(),
                "hypothesis": {
                    "hypothesis_id": str(hypothesis.artifact_id),
                    "hypothesis_hash": hypothesis.content_hash,
                    "discovery_evidence_reference": discovery.reference.to_canonical_dict(),
                    "factor_directions": [list(item) for item in factor_directions],
                },
                "validation_panel_references": [
                    item.to_canonical_dict() for item in panels
                ],
            },
        },
        name="external",
        experiment_reference=external_experiment,
        source_references=(
            correctness.reference,
            discovery.reference,
            hypothesis,
            *panels,
        ),
    )
    candidate_policy = _validation_reference(
        "CHALLENGER_CANDIDATE_POLICY", "challenger-policy"
    )
    candidate_experiment = _validation_reference(
        "RESEARCH_EXPERIMENT_DEFINITION", "candidate-experiment"
    )
    candidate = _historical(
        HistoricalEvidenceKind.CANDIDATE_POLICY,
        {
            "activation_status": "CHALLENGER_ACTIVE",
            "stability": "STABLE",
            "daily_alpha_admission": {
                "schema_version": "daily-alpha-evidence-admission/v1",
                "candidate_policy_reference": candidate_policy.to_canonical_dict(),
                "candidate_dataset_reference": dataset.to_canonical_dict(),
                "external_validation_evidence_reference": external.reference.to_canonical_dict(),
                "correctness_evidence_reference": correctness.reference.to_canonical_dict(),
                "discovery_evidence_reference": discovery.reference.to_canonical_dict(),
                "external_experiment_reference": external_experiment.to_canonical_dict(),
                "frozen_hypothesis_reference": hypothesis.to_canonical_dict(),
                "factor_directions": [list(item) for item in factor_directions],
                "lineage_stages": [
                    _lineage_stage("DISCOVERY", discovery),
                    _lineage_stage("CORRECTNESS", correctness),
                    _lineage_stage("EXTERNAL_VALIDATION", external),
                ],
            },
        },
        name="candidate",
        experiment_reference=candidate_experiment,
        source_references=(
            candidate_policy,
            dataset,
            external.reference,
            correctness.reference,
            discovery.reference,
            external_experiment,
            hypothesis,
        ),
    )
    return discovery, correctness, external, candidate


def _symbol() -> DailyAlphaSymbolProjection:
    return DailyAlphaSymbolProjection(
        symbol="600000.SH",
        selection_status="SELECTED",
        candidate_rank=1,
        factor_score="0.75",
        factor_values=(("price_vs_vwap_return:value", "0.01"),),
        factor_contributions=(("price_vs_vwap_return", "0.75"),),
        context=(("market_regime", "RISK_ON"),),
        signal_reference=_reference("SIGNAL_SNAPSHOT", "signal"),
        signal_state="ACTIVE",
        signal_score="0.8",
        forecast_reference=_reference("PATH_FORECAST", "forecast"),
        forecast_expected_return=None,
        forecast_uncertainty=None,
        calibration_status="NOT_CALIBRATED",
        strategy_diagnostic_reference=_reference(
            "MULTI_STRATEGY_CYCLE", "strategy-cycle"
        ),
        reason_codes=("PATH_FORECAST_EXPECTED_RETURN_NOT_IMPLEMENTED",),
    )


def _snapshot(gate: DailyAlphaEvidenceGate) -> DailyAlphaPredictionSnapshot:
    return DailyAlphaPredictionSnapshot.create(
        run_reference=_reference("CONTINUOUS_RESEARCH_RUN", "run"),
        tick_reference=_reference("CONTINUOUS_RUNTIME_TICK", "tick"),
        code_reference=_reference("CONTINUOUS_RUN_CODE_IDENTITY", "code"),
        configuration_references=(_reference("RESEARCH_CONFIGURATION", "config"),),
        provider_evidence_reference=_reference("EVIDENCE_COMMIT", "evidence"),
        dataset_reference=_reference("MARKET_DATA_DATASET", "dataset"),
        universe_reference=_reference("OPERATIONAL_UNIVERSE", "universe"),
        feature_references=(_reference("FEATURE_BUNDLE_V2", "features"),),
        context_references=(
            _reference("RESEARCH_DAILY_SUMMARY", "research-summary"),
        ),
        candidate_reference=_reference("CANDIDATE_SET", "candidates"),
        signal_reference=_reference("STATE_STAGE_SIGNAL", "signal-stage"),
        forecast_references=(_reference("STATE_STAGE_FORECAST", "forecast-stage"),),
        strategy_diagnostic_reference=_reference(
            "MULTI_STRATEGY_CYCLE", "strategy-cycle"
        ),
        evidence_gate=gate,
        trading_date=date(2026, 8, 21),
        decision_time=NOW,
        available_at=NOW,
        symbols=(_symbol(),),
        reason_codes=("DAILY_PREDICTION_FROZEN_BEFORE_OUTCOME",),
    )


def test_daily_snapshot_is_content_addressed_and_replay_stable() -> None:
    first = _snapshot(DailyAlphaEvidenceGate.inactive())
    second = _snapshot(DailyAlphaEvidenceGate.inactive())

    assert first == second
    assert first.snapshot_id == second.snapshot_id
    assert DailyAlphaPredictionSnapshot.from_canonical_dict(
        first.to_canonical_dict()
    ) == first
    assert EVIDENCE_DEPENDENCY_NOT_SATISFIED in first.reason_codes


def test_inactive_gate_cannot_silently_look_successful() -> None:
    with pytest.raises(ValueError, match="dependency reason"):
        DailyAlphaEvidenceGate(
            DailyAlphaActivationStatus.VALIDATED_CHALLENGER_INACTIVE,
            None,
            None,
            None,
            ("ENGINEERING_RUN_COMPLETED",),
        )


def test_gate_requires_explicitly_supported_full_chain() -> None:
    discovery, correctness, external, active = _supported_chain()
    blocked = assess_daily_alpha_evidence_gate(
        (discovery, correctness, external, active),
        root_candidate_policy_reference=None,
    )
    assert blocked.status is DailyAlphaActivationStatus.VALIDATED_CHALLENGER_INACTIVE
    assert "EVIDENCE_ROOT_NOT_CONFIGURED" in blocked.reason_codes

    admitted = assess_daily_alpha_evidence_gate(
        (discovery, correctness, external, active),
        root_candidate_policy_reference=active.reference,
    )
    assert admitted.status is DailyAlphaActivationStatus.VALIDATED_CHALLENGER_ACTIVE
    assert EVIDENCE_DEPENDENCY_NOT_SATISFIED not in admitted.reason_codes


def test_gate_rejects_cross_experiment_or_dataset_mixing() -> None:
    discovery, correctness, external, candidate = _supported_chain()
    unrelated = _historical(
        HistoricalEvidenceKind.ALPHA_CORRECTNESS,
        {"status": "CORRECTNESS_SUPPORTED"},
        name="unrelated-correctness",
    )

    mixed = assess_daily_alpha_evidence_gate(
        (discovery, unrelated, external, candidate),
        root_candidate_policy_reference=candidate.reference,
    )

    assert mixed.status is DailyAlphaActivationStatus.VALIDATED_CHALLENGER_INACTIVE
    assert "EVIDENCE_LINEAGE_INCOMPLETE" in mixed.reason_codes


def test_gate_uses_only_the_explicit_root_and_rejects_superseded_chain() -> None:
    discovery, correctness, external, candidate = _supported_chain()
    newer_unrelated_candidate = _historical(
        HistoricalEvidenceKind.CANDIDATE_POLICY,
        {"activation_status": "CHALLENGER_ACTIVE", "stability": "STABLE"},
        name="newer-unrelated-candidate",
    )

    admitted = assess_daily_alpha_evidence_gate(
        (discovery, correctness, external, candidate, newer_unrelated_candidate),
        root_candidate_policy_reference=candidate.reference,
    )
    superseded = assess_daily_alpha_evidence_gate(
        (discovery, correctness, external, candidate, newer_unrelated_candidate),
        root_candidate_policy_reference=candidate.reference,
        superseded_references=(external.reference,),
    )

    assert admitted.status is DailyAlphaActivationStatus.VALIDATED_CHALLENGER_ACTIVE
    assert admitted.candidate_policy_reference == candidate.reference
    assert superseded.status is DailyAlphaActivationStatus.VALIDATED_CHALLENGER_INACTIVE
    assert "EVIDENCE_SUPERSEDED" in superseded.reason_codes


def test_snapshot_rejects_future_availability() -> None:
    value = _snapshot(DailyAlphaEvidenceGate.inactive())
    payload = value.to_canonical_dict()
    payload["available_at"] = "2026-08-21T06:54:59Z"
    with pytest.raises(ValueError, match="predate DecisionTime"):
        DailyAlphaPredictionSnapshot.from_canonical_dict(payload)
