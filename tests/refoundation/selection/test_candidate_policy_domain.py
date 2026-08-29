"""Candidate policy is an immutable, Selection-owned ranking contract."""

from dataclasses import fields, replace
from decimal import Decimal
from fractions import Fraction
from uuid import UUID

import pytest

from market_regime_alpha.selection.domain.candidate_policy import (
    CandidateFeatureValueType,
    CandidatePolicy,
    CandidatePolicyComponent,
    DesirabilityDirection,
)
from market_regime_alpha.selection.domain.candidate_inputs import (
    CandidateArtifactBinding,
)
from market_regime_alpha.selection.domain.candidate_ranking import (
    normalize_declared_weights,
)


def _uuid(value: int) -> UUID:
    return UUID(int=value)


def _component(
    ordinal: int,
    weight: str,
    *,
    policy_id: int = 1,
    feature_value_type: CandidateFeatureValueType = CandidateFeatureValueType.DECIMAL,
) -> CandidatePolicyComponent:
    return CandidatePolicyComponent(
        candidate_policy_component_id=_uuid(100 + ordinal),
        candidate_policy_id=_uuid(policy_id),
        component_code=f"feature_{ordinal}",
        ordinal=ordinal,
        feature_definition_id=_uuid(200 + ordinal),
        feature_content_sha256=f"{ordinal:064x}",
        feature_value_type=feature_value_type,
        direction=DesirabilityDirection.HIGHER_IS_BETTER,
        declared_weight=Decimal(weight),
    )


def _artifact(value: int) -> CandidateArtifactBinding:
    return CandidateArtifactBinding(
        artifact_id=_uuid(300 + value),
        content_sha256=f"{300 + value:064x}",
        size_bytes=value,
    )


def test_declared_decimal_weights_normalize_as_exact_rationals() -> None:
    policy = CandidatePolicy(
        candidate_policy_id=_uuid(1),
        policy_code="candidate_v1",
        version=1,
        code_artifact=_artifact(1),
        config_artifact=_artifact(2),
        requested_top_k=2,
        components=(_component(1, "0.1"), _component(2, "0.2")),
    )

    assert normalize_declared_weights(policy.components) == {
        _uuid(101): Fraction(1, 3),
        _uuid(102): Fraction(2, 3),
    }


def test_policy_component_binds_its_parent_and_has_one_weight_authority() -> None:
    component = _component(1, "3")
    assert component.candidate_policy_id == _uuid(1)
    assert "declared_weight" in {item.name for item in fields(component)}
    assert "normalized_weight" not in {item.name for item in fields(component)}

    with pytest.raises(ValueError, match="parent CandidatePolicy"):
        CandidatePolicy(
            candidate_policy_id=_uuid(1),
            policy_code="candidate_v1",
            version=1,
            code_artifact=_artifact(1),
            config_artifact=_artifact(2),
            requested_top_k=1,
            components=(_component(1, "1", policy_id=999),),
        )


def test_policy_content_hash_excludes_aggregate_row_identities() -> None:
    first = CandidatePolicy(
        candidate_policy_id=_uuid(1),
        policy_code="candidate_v1",
        version=1,
        code_artifact=_artifact(1),
        config_artifact=_artifact(2),
        requested_top_k=1,
        components=(_component(1, "1"),),
    )
    renamed_component = replace(
        first.components[0],
        candidate_policy_component_id=_uuid(9_001),
        candidate_policy_id=_uuid(9_000),
    )
    renamed = CandidatePolicy(
        candidate_policy_id=_uuid(9_000),
        policy_code="candidate_v1",
        version=1,
        code_artifact=_artifact(1),
        config_artifact=_artifact(2),
        requested_top_k=1,
        components=(renamed_component,),
    )

    assert first.content_sha256 == renamed.content_sha256
