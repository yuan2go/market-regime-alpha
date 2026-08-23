from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalEvidenceKind,
)
from market_regime_alpha.application.historical_corpus.phase_ii_operator import (
    CORRECTNESS_INFERENCE_BLOCK_LENGTHS,
    CORRECTNESS_INFERENCE_CONFIDENCE,
    CORRECTNESS_INFERENCE_ITERATIONS,
    CORRECTNESS_PLACEBO_SEED,
    HistoricalPhaseIIResearchOperator,
    PHASE_II_OPERATOR_SCHEMA,
)
from market_regime_alpha.application.historical_corpus.external_validation import (
    FrozenExternalValidationExperiment,
    ValidationDimension,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId, DatasetId
from market_regime_alpha.data.trading_calendar import (
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from tests.application.historical_corpus.test_external_validation import (
    _correctness as correctness_fixture,
    _hypothesis as hypothesis_fixture,
    _scope as scope_fixture,
    _temporal_window as temporal_window_fixture,
)
from tests.candidates.test_candidate_policy_v2 import (
    TARGET as CANDIDATE_TARGET,
    _challenger as challenger_fixture,
)


class FakeCalendars:
    def __init__(self, calendar) -> None:
        self.calendar = calendar

    def get(self, calendar_id: ArtifactId):
        assert calendar_id == self.calendar.artifact_id
        return self.calendar


class FakeService:
    def __init__(self) -> None:
        self.evaluate_kwargs = None
        self.persist_args = None
        self.result = object()
        self.proof = object()

    def evaluate_correctness_campaign(self, **kwargs):
        self.evaluate_kwargs = kwargs
        return self.proof

    def persist_correctness_proof(self, *args, **kwargs):
        self.persist_args = (args, kwargs)
        return self.result


class FakeExternalService:
    def __init__(self, experiment: FrozenExternalValidationExperiment) -> None:
        self.experiment = experiment
        self.create_kwargs = None
        self.persist_args = None
        self.result = object()
        self.evaluation = object()

    def create_external_experiment(self, **kwargs):
        self.create_kwargs = kwargs
        return self.experiment

    def evaluate_external_experiment(self, experiment):
        assert experiment is self.experiment
        return self.evaluation

    def persist_external_evaluation(self, *args):
        self.persist_args = args
        return self.result


class FakeWindows:
    def __init__(self, window) -> None:
        self.window = window

    def get(self, reference: ValidationArtifactReference):
        assert reference == self.window.reference
        return self.window


class FakeCandidateService:
    def __init__(self) -> None:
        challenger = challenger_fixture()
        self.external = challenger.validated_factors[0].external_validation_evidence
        self.factor = challenger.validated_factors[0]
        self.context = challenger.context_adjustments[0]
        self.comparison = object()
        self.result = object()
        self.policies = None
        self.persist_kwargs = None

    def load_evidence(self, _evidence_id, *, expected_kind):
        assert expected_kind is HistoricalEvidenceKind.EXTERNAL_VALIDATION
        return self.external

    def validated_factor(self, **kwargs):
        assert kwargs["external_evidence_id"] == self.external.evidence_id
        return self.factor

    def context_adjustment(self, **_kwargs):
        return self.context

    def compare_candidate_policies(
        self,
        incumbent,
        challenger,
        *,
        protocol,
        panel_references,
    ):
        self.policies = (incumbent, challenger, protocol, panel_references)
        return self.comparison

    def persist_candidate_admission(self, write, **kwargs):
        self.persist_kwargs = (write, kwargs)
        return self.result


class FakeContextService:
    def __init__(self) -> None:
        self.external = (
            challenger_fixture()
            .validated_factors[0]
            .external_validation_evidence
        )
        self.definition = object()
        self.evaluation = object()
        self.definition_kwargs = None
        self.persist_args = None
        self.result = object()

    def load_evidence(self, _evidence_id, *, expected_kind):
        assert expected_kind is HistoricalEvidenceKind.EXTERNAL_VALIDATION
        return self.external

    def context_definition(self, **kwargs):
        self.definition_kwargs = kwargs
        return self.definition

    def evaluate_context_definition(self, definition):
        assert definition is self.definition
        return self.evaluation

    def persist_context_evaluation(self, *args):
        self.persist_args = args
        return self.result


def _calendar():
    return build_trading_calendar_artifact(
        source_dataset_id=DatasetId("phase-ii-calendar-source"),
        market="CN_A_SHARE",
        calendar_version="phase-ii-calendar-v1",
        timezone_name="Asia/Shanghai",
        sessions=(
            TradingSession(
                date(2026, 8, 20),
                datetime(2026, 8, 20, 15, tzinfo=UTC),
            ),
        ),
    )


def _reference(kind: str, identity: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(identity),
        canonical_hash({"kind": kind, "identity": identity}),
    )


def _command(tmp_path: Path) -> dict[str, object]:
    calendar = _calendar()
    calendar_reference = ValidationArtifactReference(
        "TRADING_CALENDAR",
        calendar.artifact_id,
        calendar.content_hash,
    )
    physical_reference = _reference(
        "HISTORICAL_NORMALIZED_DATA",
        "normalized-owner-1",
    )
    return {
        "schema_version": PHASE_II_OPERATOR_SCHEMA,
        "operation": "CORRECTNESS",
        "evidence": {
            "run_id": "historical-research-run-fixture",
            "command_hash": canonical_hash({"command": "phase-ii"}),
            "research_question": "Can the frozen Alpha inputs be reproduced?",
            "classification": "INCONCLUSIVE",
            "rationale": "Operator fixture only; no empirical campaign is run.",
            "created_at": "2026-08-24T00:00:00Z",
            "statements": [
                {
                    "statement_kind": "LIMITATION",
                    "text": "This is an operator wiring fixture.",
                }
            ],
        },
        "parameters": {
            "experiment_reference": _reference(
                "RESEARCH_EXPERIMENT_DEFINITION",
                "phase-ii-experiment",
            ).to_canonical_dict(),
            "calendar_reference": calendar_reference.to_canonical_dict(),
            "physical_packages": [
                {
                    "owner_reference": physical_reference.to_canonical_dict(),
                    "path": str(tmp_path / "physical-package"),
                }
            ],
            "physical_provenance": "REACQUIRED_EQUIVALENT_SOURCE",
            "target_id": "next-session-10:30-return",
        },
    }


def test_correctness_operator_freezes_protocol_and_delegates_to_existing_service(
    tmp_path: Path,
) -> None:
    service = FakeService()
    operator = HistoricalPhaseIIResearchOperator(
        service=service,  # type: ignore[arg-type]
        calendars=FakeCalendars(_calendar()),  # type: ignore[arg-type]
        temporal_windows=object(),  # type: ignore[arg-type]
    )

    result = operator.execute(_command(tmp_path))

    assert result is service.result
    assert service.evaluate_kwargs is not None
    assert service.evaluate_kwargs["placebo_seed"] == CORRECTNESS_PLACEBO_SEED
    protocol = service.evaluate_kwargs["inference_protocol"]
    assert protocol.iterations == CORRECTNESS_INFERENCE_ITERATIONS
    assert protocol.block_lengths == CORRECTNESS_INFERENCE_BLOCK_LENGTHS
    assert protocol.confidence_level == CORRECTNESS_INFERENCE_CONFIDENCE
    assert protocol.seed == CORRECTNESS_PLACEBO_SEED
    assert service.persist_args is not None
    write = service.persist_args[0][0]
    assert write.evidence_kind is HistoricalEvidenceKind.ALPHA_CORRECTNESS
    assert {item.artifact_kind for item in write.source_references} == {
        "HISTORICAL_NORMALIZED_DATA",
        "TRADING_CALENDAR",
    }


def test_correctness_operator_rejects_research_protocol_override(
    tmp_path: Path,
) -> None:
    service = FakeService()
    operator = HistoricalPhaseIIResearchOperator(
        service=service,  # type: ignore[arg-type]
        calendars=FakeCalendars(_calendar()),  # type: ignore[arg-type]
        temporal_windows=object(),  # type: ignore[arg-type]
    )
    command = _command(tmp_path)
    parameters = command["parameters"]
    assert isinstance(parameters, dict)
    parameters["inference_iterations"] = 1

    with pytest.raises(ValueError, match="Correctness parameters fields mismatch"):
        operator.execute(command)

    assert service.evaluate_kwargs is None


def test_external_operator_rebuilds_exact_experiment_and_delegates(
    tmp_path: Path,
) -> None:
    hypothesis = hypothesis_fixture()
    correctness = correctness_fixture()
    discovery_scope = scope_fixture("2025-H1", "universe-a", "provider-a")
    validation_scope = scope_fixture("2025-H2", "universe-a", "provider-a")
    window = temporal_window_fixture()
    panel = _reference("HISTORICAL_RESEARCH_PANEL", "external-panel")
    experiment = FrozenExternalValidationExperiment.create(
        hypothesis=hypothesis,
        correctness_evidence=correctness,
        discovery_scope=discovery_scope,
        validation_scope=validation_scope,
        temporal_window=window,
        validation_panel_references=(panel,),
        dimension=ValidationDimension.TEMPORAL_VALIDATION,
        expected_population=100,
        random_seed=20260819,
    )
    service = FakeExternalService(experiment)
    operator = HistoricalPhaseIIResearchOperator(
        service=service,  # type: ignore[arg-type]
        calendars=object(),  # type: ignore[arg-type]
        temporal_windows=FakeWindows(window),  # type: ignore[arg-type]
    )
    command = _command(tmp_path)
    command["operation"] = "EXTERNAL_VALIDATION"
    command["parameters"] = {
        "hypothesis": hypothesis.to_canonical_dict(),
        "correctness_evidence_id": str(correctness.evidence_id),
        "discovery_scope": discovery_scope.to_canonical_dict(),
        "validation_scope": validation_scope.to_canonical_dict(),
        "temporal_window_reference": window.reference.to_canonical_dict(),
        "validation_panel_references": [panel.to_canonical_dict()],
        "dimension": "TEMPORAL_VALIDATION",
        "expected_population": 100,
        "random_seed": 20260819,
        "expected_experiment_reference": experiment.reference.to_canonical_dict(),
    }

    result = operator.execute(command)

    assert result is service.result
    assert service.create_kwargs is not None
    assert service.create_kwargs["hypothesis"] == hypothesis
    assert service.create_kwargs["temporal_window"] == window
    assert service.create_kwargs["validation_panel_references"] == (panel,)
    assert service.persist_args is not None
    write = service.persist_args[0]
    assert write.experiment_reference == experiment.reference
    assert write.evidence_kind is HistoricalEvidenceKind.EXTERNAL_VALIDATION


def test_candidate_operator_builds_both_policies_and_one_explicit_admission(
    tmp_path: Path,
) -> None:
    service = FakeCandidateService()
    operator = HistoricalPhaseIIResearchOperator(
        service=service,  # type: ignore[arg-type]
        calendars=object(),  # type: ignore[arg-type]
        temporal_windows=object(),  # type: ignore[arg-type]
    )
    panel = _reference("HISTORICAL_RESEARCH_PANEL", "candidate-panel")
    command = _command(tmp_path)
    command["operation"] = "CANDIDATE"
    command["parameters"] = {
        "external_evidence_id": str(service.external.evidence_id),
        "validated_factors": [
            {
                "factor_id": service.factor.factor_id,
                "direction": service.factor.direction,
                "weight": str(service.factor.weight),
            }
        ],
        "context_adjustments": [
            {
                "context_id": service.context.context_id,
                "weight": str(service.context.weight),
                "mode": service.context.mode,
                "context_evidence_id": str(service.context.context_evidence.evidence_id),
            }
        ],
        "research_panel_references": [panel.to_canonical_dict()],
        "incumbent_policy": {
            "policy_version": "incumbent-v1",
            "top_k": 1,
            "minimum_liquidity": "100",
        },
        "challenger_policy": {
            "policy_version": "challenger-v1",
            "top_k": 1,
            "minimum_liquidity": "100",
        },
        "target_reference": CANDIDATE_TARGET.to_canonical_dict(),
        "cost_assumption": "0.001",
        "activation_status": "CHALLENGER_DORMANT",
    }

    result = operator.execute(command)

    assert result is service.result
    assert service.policies is not None
    incumbent, challenger, protocol, panels = service.policies
    assert incumbent.role.value == "INCUMBENT"
    assert challenger.role.value == "CHALLENGER"
    assert challenger.validated_factors == (service.factor,)
    assert challenger.context_adjustments == (service.context,)
    assert protocol.target_reference == CANDIDATE_TARGET
    assert panels == (panel,)
    assert service.persist_kwargs is not None
    write, persist = service.persist_kwargs
    assert write.experiment_reference == service.external.experiment_reference
    assert persist["activation_status"] == "CHALLENGER_DORMANT"
    assert persist["comparison"] is service.comparison


def test_context_operator_preserves_session_context_role_and_owner_lineage(
    tmp_path: Path,
) -> None:
    service = FakeContextService()
    operator = HistoricalPhaseIIResearchOperator(
        service=service,  # type: ignore[arg-type]
        calendars=object(),  # type: ignore[arg-type]
        temporal_windows=object(),  # type: ignore[arg-type]
    )
    panel = _reference("HISTORICAL_RESEARCH_PANEL", "context-panel")
    command = _command(tmp_path)
    command["operation"] = "CONTEXT"
    command["parameters"] = {
        "external_evidence_id": str(service.external.evidence_id),
        "context_id": "MARKET_REGIME",
        "kind": "SESSION_LEVEL_CONTEXT",
        "role": "CONDITIONAL_PERFORMANCE",
        "public_observable_proxy": True,
        "research_panel_references": [panel.to_canonical_dict()],
        "top_k": 5,
        "expected_population": 100,
        "effect_threshold": "0.01",
    }

    result = operator.execute(command)

    assert result is service.result
    assert service.definition_kwargs is not None
    assert service.definition_kwargs["kind"].value == "SESSION_LEVEL_CONTEXT"
    assert service.definition_kwargs["role"].value == "CONDITIONAL_PERFORMANCE"
    assert service.definition_kwargs["research_panel_references"] == (panel,)
    assert service.persist_args is not None
    write = service.persist_args[0]
    assert write.experiment_reference == service.external.experiment_reference
    assert {item for item in write.source_references} == {
        panel,
        service.external.reference,
    }
