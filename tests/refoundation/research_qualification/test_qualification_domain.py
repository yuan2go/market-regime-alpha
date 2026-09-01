from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from market_regime_alpha.research_qualification.domain.assessment import AssessmentStatus
from market_regime_alpha.research_qualification.domain import ArtifactBinding
from market_regime_alpha.research_qualification.domain.evidence import (
    EvidenceClass,
    EvidenceOriginClass,
    EvidenceRole,
)
from market_regime_alpha.research_qualification.domain.qualification import (
    FloorMissingnessPolicy,
    FloorResultStatus,
    QualificationDecisionStatus,
    QualificationOperator,
    QualificationPolicyFloorPlan,
    QualificationPurpose,
    ResearchQualificationPolicyPlan,
    qualification_decision_status,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    EvaluationReducer,
    EvaluationSliceKind,
    MetricDirection,
    PartitionPurpose,
    SourceMetricValueType,
)


_HASH = "a" * 64


def _floor(**changes: object) -> QualificationPolicyFloorPlan:
    values: dict[str, object] = {
        "research_qualification_policy_floor_id": uuid4(),
        "floor_code": "locked-oos-primary",
        "ordinal": 1,
        "evaluation_protocol_id": uuid4(),
        "evaluation_protocol_metric_id": uuid4(),
        "evaluation_protocol_metric_sha256": _HASH,
        "required_partition_purpose": PartitionPurpose.LOCKED_OOS,
        "required_evaluation_status": "COMPLETED",
        "metric_code": "mean-return",
        "source_value_type": SourceMetricValueType.DECIMAL,
        "reducer": EvaluationReducer.MEAN_DECIMAL,
        "slice_kind": EvaluationSliceKind.ALL_MEMBERS,
        "candidate_disposition": None,
        "direction": MetricDirection.HIGHER,
        "operator": QualificationOperator.AT_LEAST,
        "decimal_threshold": Decimal("0.01"),
        "boolean_threshold": None,
        "minimum_member_count": 10,
        "minimum_estimable_count": 8,
        "missingness_policy": FloorMissingnessPolicy.INCONCLUSIVE,
        "required_evidence_class": EvidenceClass.RESEARCH_RESULT,
        "required_origin_class": EvidenceOriginClass.DERIVED_CANONICAL,
        "required_evidence_role": EvidenceRole.PRIMARY_RESULT,
        "minimum_support_evidence_count": 1,
        "maximum_counter_evidence_count": 0,
        "required": True,
    }
    values.update(changes)
    return QualificationPolicyFloorPlan(**values)  # type: ignore[arg-type]


def test_floor_threshold_shape_matches_source_value_type() -> None:
    with pytest.raises(ValueError, match="Decimal"):
        _floor(decimal_threshold=None, boolean_threshold=True)
    boolean_floor = _floor(
        source_value_type=SourceMetricValueType.BOOLEAN,
        reducer=EvaluationReducer.TRUE_RATE,
        operator=QualificationOperator.EQUALS,
        decimal_threshold=None,
        boolean_threshold=True,
    )
    assert boolean_floor.boolean_threshold is True


def test_all_members_floor_forbids_candidate_disposition() -> None:
    with pytest.raises(ValueError, match="candidate_disposition"):
        _floor(candidate_disposition="SELECTED")


def test_policy_requires_contiguous_non_empty_floors_and_protected_preaccess() -> None:
    floor = _floor()
    policy = ResearchQualificationPolicyPlan(
        research_qualification_policy_id=uuid4(),
        policy_code="locked-oos-admission",
        version=1,
        supersedes_policy_id=None,
        target_definition_id=uuid4(),
        target_version=1,
        target_definition_sha256="b" * 64,
        qualification_purpose=QualificationPurpose.LOCKED_OOS,
        required_assessment_status=AssessmentStatus.SUPPORTED,
        require_preaccess_freeze=True,
        floors=(floor,),
        code_artifact=ArtifactBinding(uuid4(), "c" * 64, 12),
        config_artifact=ArtifactBinding(uuid4(), "d" * 64, 13),
        provenance_sha256="e" * 64,
    )
    assert policy.floor_count == 1
    with pytest.raises(ValueError, match="pre-access"):
        ResearchQualificationPolicyPlan(
            research_qualification_policy_id=uuid4(),
            policy_code="prospective-admission",
            version=1,
            supersedes_policy_id=None,
            target_definition_id=uuid4(),
            target_version=1,
            target_definition_sha256="b" * 64,
            qualification_purpose=QualificationPurpose.PROSPECTIVE,
            required_assessment_status=AssessmentStatus.SUPPORTED,
            require_preaccess_freeze=False,
            floors=(floor,),
            code_artifact=ArtifactBinding(uuid4(), "c" * 64, 12),
            config_artifact=ArtifactBinding(uuid4(), "d" * 64, 13),
            provenance_sha256="e" * 64,
        )


def test_policy_rejects_duplicate_metric_floor_and_requires_one_required_floor() -> None:
    floor = _floor()
    duplicate = _floor(
        floor_code="duplicate-primary",
        ordinal=2,
        evaluation_protocol_id=floor.evaluation_protocol_id,
        evaluation_protocol_metric_id=floor.evaluation_protocol_metric_id,
    )
    common = {
        "research_qualification_policy_id": uuid4(),
        "policy_code": "validation-admission",
        "version": 1,
        "supersedes_policy_id": None,
        "target_definition_id": uuid4(),
        "target_version": 1,
        "target_definition_sha256": "b" * 64,
        "qualification_purpose": QualificationPurpose.VALIDATION,
        "required_assessment_status": AssessmentStatus.SUPPORTED,
        "require_preaccess_freeze": False,
        "code_artifact": ArtifactBinding(uuid4(), "c" * 64, 12),
        "config_artifact": ArtifactBinding(uuid4(), "d" * 64, 13),
        "provenance_sha256": "e" * 64,
    }
    with pytest.raises(ValueError, match="bindings"):
        ResearchQualificationPolicyPlan(floors=(floor, duplicate), **common)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="required floor"):
        ResearchQualificationPolicyPlan(
            floors=(_floor(required=False),),
            **common,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("assessment", "floors", "expected"),
    [
        (AssessmentStatus.SUPPORTED, (FloorResultStatus.SATISFIED,), QualificationDecisionStatus.ADMITTED),
        (AssessmentStatus.REJECTED, (FloorResultStatus.SATISFIED,), QualificationDecisionStatus.REJECTED),
        (AssessmentStatus.SUPPORTED, (FloorResultStatus.REJECTED,), QualificationDecisionStatus.REJECTED),
        (AssessmentStatus.SUPPORTED, (FloorResultStatus.NOT_ESTIMABLE,), QualificationDecisionStatus.INCONCLUSIVE),
        (AssessmentStatus.INCONCLUSIVE, (FloorResultStatus.SATISFIED,), QualificationDecisionStatus.INCONCLUSIVE),
    ],
)
def test_qualification_decision_requires_every_required_floor(
    assessment: AssessmentStatus,
    floors: tuple[FloorResultStatus, ...],
    expected: QualificationDecisionStatus,
) -> None:
    assert qualification_decision_status(
        assessment_status=assessment,
        required_assessment_status=AssessmentStatus.SUPPORTED,
        required_floor_statuses=floors,
    ) is expected


def test_qualification_rejects_empty_floor_vector() -> None:
    with pytest.raises(ValueError, match="floor"):
        qualification_decision_status(
            assessment_status=AssessmentStatus.SUPPORTED,
            required_assessment_status=AssessmentStatus.SUPPORTED,
            required_floor_statuses=(),
        )
