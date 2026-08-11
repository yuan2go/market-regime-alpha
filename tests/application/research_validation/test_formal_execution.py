from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.formal_execution import (
    FormalExecutionRequest,
    FormalExecutionStage,
    FormalExecutionStatus,
    ProviderFactRequirement,
    assess_formal_execution,
)
from market_regime_alpha.application.research_validation.qualification import (
    QualificationOutcome,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.pit_contracts import PITFactKind, PITValidationOutcome
from market_regime_alpha.data.postgres_provider_qualification import (
    ProviderFactQualificationDecision,
    ProviderFactQualificationStatus,
)
from market_regime_alpha.platform.runtime_governance import (
    QualificationStatus,
    RuntimePurpose,
)


NOW = datetime(2026, 8, 11, 12, tzinfo=UTC)


def _hash(character: str) -> str:
    return "sha256:" + character * 64


def _ref(kind: str, suffix: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(f"{kind.lower()}:{suffix}"),
        _hash(suffix),
    )


def _provider_decision(
    status: ProviderFactQualificationStatus,
) -> ProviderFactQualificationDecision:
    qualified = status is ProviderFactQualificationStatus.QUALIFIED
    return ProviderFactQualificationDecision.create(
        policy_reference=_ref("PROVIDER_QUALIFICATION_POLICY_V2", "a"),
        provider_id="BAOSTOCK",
        provider_contract="query_history_k_data_plus:daily:adjustflag=3",
        fact_kind=PITFactKind.MARKET_DATA,
        status=status,
        source_qualification_references=(
            (_ref("PIT_SOURCE_QUALIFICATION", "b"),) if qualified else ()
        ),
        evidence_kinds=(),
        evidence_references=(),
        revision=1,
        supersedes_decision_id=None,
        evaluated_at=NOW,
        actor="research-operator",
        reason="test formal predecessor",
        reason_codes=() if qualified else ("FORMAL_PIT_NOT_ESTABLISHED",),
    )


def _request(
    decision_id: ArtifactId | None,
    **overrides,
) -> FormalExecutionRequest:
    values = {
        "provider_requirements": (
            ProviderFactRequirement(
                "BAOSTOCK",
                "query_history_k_data_plus:daily:adjustflag=3",
                PITFactKind.MARKET_DATA,
                decision_id,
            ),
        ),
        "formal_protocol_id": None,
        "formal_pit_evidence_ids": (),
        "historical_qualification_ids": (),
        "model_qualification_decision_id": None,
        "formal_oos_decision_id": None,
        "calibration_decision_id": None,
        "assessed_at": NOW,
        "actor": "research-operator",
        "reason": "evaluate Formal evidence without weakening floors",
        "idempotency_key": "formal-execution-test-1",
    }
    values.update(overrides)
    return FormalExecutionRequest.create(**values)


class _Resolver:
    def __init__(self, provider=None) -> None:
        self.provider = provider
        self.calls: list[str] = []
        self.owners: dict[str, object] = {}

    def provider_fact(self, decision_id):
        self.calls.append("provider")
        if self.provider is None:
            raise KeyError(str(decision_id))
        return self.provider

    def protocol(self, protocol_id):
        self.calls.append("protocol")
        return self.owners["protocol"]

    def formal_pit(self, evidence_id):
        self.calls.append("pit")
        return self.owners["pit"]

    def historical(self, decision_id):
        self.calls.append("historical")
        return self.owners["historical"]

    def model(self, decision_id):
        self.calls.append("model")
        return self.owners["model"]

    def formal_oos(self, decision_id):
        self.calls.append("oos")
        return self.owners["oos"]

    def calibration(self, decision_id):
        self.calls.append("calibration")
        return self.owners["calibration"]


def test_free_provider_incomplete_stops_before_all_formal_owners() -> None:
    provider = _provider_decision(ProviderFactQualificationStatus.INCOMPLETE)
    resolver = _Resolver(provider)
    request = _request(provider.decision_id)

    assessment = assess_formal_execution(request, resolver=resolver)

    assert assessment.status is FormalExecutionStatus.INCOMPLETE
    assert assessment.terminal_stage is FormalExecutionStage.PROVIDER_FACT_QUALIFICATION
    assert resolver.calls == ["provider"]
    assert assessment.formal_model_qualified is False
    assert assessment.formal_oos_alpha_established is False
    assert assessment.calibrated is False
    assert assessment.production_authorized is False
    assert request == FormalExecutionRequest.from_canonical_dict(
        request.to_canonical_dict()
    )
    assert assessment == assessment.from_canonical_dict(
        assessment.to_canonical_dict()
    )


def test_missing_provider_decision_is_persistable_blocked_not_an_exception() -> None:
    resolver = _Resolver()

    assessment = assess_formal_execution(_request(None), resolver=resolver)

    assert assessment.status is FormalExecutionStatus.BLOCKED
    assert assessment.reason_codes == (
        "PROVIDER_FACT_DECISION_MISSING:BAOSTOCK:query_history_k_data_plus:daily:adjustflag=3:MARKET_DATA",
    )
    assert resolver.calls == []


def test_full_chain_uses_only_bound_predecessors_and_still_grants_no_production() -> None:
    provider = _provider_decision(ProviderFactQualificationStatus.QUALIFIED)
    resolver = _Resolver(provider)
    protocol_ref = _ref("FORMAL_RESEARCH_PROTOCOL", "c")
    model_lineage_ref = _ref("MODEL_VERSION_LINEAGE", "d")
    pit_ref = _ref("FORMAL_PIT_EVIDENCE", "e")
    historical_ref = _ref("HISTORICAL_SAMPLE_QUALIFICATION_DECISION", "f")
    model_ref = _ref("MODEL_QUALIFICATION_DECISION", "1")
    oos_ref = _ref("FORMAL_OOS_QUALIFICATION_DECISION", "2")
    calibration_ref = _ref("CALIBRATION_QUALIFICATION_DECISION", "3")
    source_qualification = provider.source_qualification_references[0]
    resolver.owners = {
        "protocol": SimpleNamespace(
            protocol_id=protocol_ref.artifact_id,
            protocol_hash=protocol_ref.content_hash,
            model_reference=model_lineage_ref,
        ),
        "pit": SimpleNamespace(
            evidence_id=pit_ref.artifact_id,
            evidence_hash=pit_ref.content_hash,
            outcome=PITValidationOutcome.SATISFIED,
            rejection_codes=(),
            selected_fact_authorities=(
                SimpleNamespace(
                    source_qualification_id=source_qualification.artifact_id
                ),
            ),
        ),
        "historical": SimpleNamespace(
            decision_id=historical_ref.artifact_id,
            decision_hash=historical_ref.content_hash,
            formal_protocol_reference=protocol_ref,
            outcome=QualificationOutcome.SATISFIED,
            reason_codes=(),
        ),
        "model": SimpleNamespace(
            decision_id=model_ref.artifact_id,
            decision_hash=model_ref.content_hash,
            status=QualificationStatus.QUALIFIED,
            purpose=RuntimePurpose.BACKTEST,
            lineage_id=model_lineage_ref.artifact_id,
            lineage_hash=model_lineage_ref.content_hash,
        ),
        "oos": SimpleNamespace(
            decision_id=oos_ref.artifact_id,
            decision_hash=oos_ref.content_hash,
            formal_protocol_reference=protocol_ref,
            formal_pit_references=(pit_ref,),
            historical_sample_decision_references=(historical_ref,),
            outcome=QualificationOutcome.SATISFIED,
            formal_oos_passed=True,
            reason_codes=(),
        ),
        "calibration": SimpleNamespace(
            decision_id=calibration_ref.artifact_id,
            decision_hash=calibration_ref.content_hash,
            formal_protocol_reference=protocol_ref,
            formal_oos_reference=oos_ref,
            outcome=QualificationOutcome.SATISFIED,
            calibrated=True,
            reason_codes=(),
        ),
    }
    request = _request(
        provider.decision_id,
        formal_protocol_id=protocol_ref.artifact_id,
        formal_pit_evidence_ids=(pit_ref.artifact_id,),
        historical_qualification_ids=(historical_ref.artifact_id,),
        model_qualification_decision_id=model_ref.artifact_id,
        formal_oos_decision_id=oos_ref.artifact_id,
        calibration_decision_id=calibration_ref.artifact_id,
        idempotency_key="formal-execution-complete-test",
    )

    assessment = assess_formal_execution(request, resolver=resolver)

    assert assessment.status is FormalExecutionStatus.SATISFIED
    assert resolver.calls == [
        "provider",
        "protocol",
        "pit",
        "historical",
        "model",
        "oos",
        "calibration",
    ]
    assert assessment.formal_model_qualified is True
    assert assessment.formal_oos_alpha_established is True
    assert assessment.calibrated is True
    assert assessment.production_authorized is False
