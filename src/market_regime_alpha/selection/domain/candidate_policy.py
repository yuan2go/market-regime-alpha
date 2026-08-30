"""Immutable Candidate V1 ranking policy owned by Selection."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
import re
from typing import cast
from uuid import UUID

from market_regime_alpha.selection.domain.candidate_inputs import (
    CandidateArtifactBinding,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


_CODE = re.compile(r"^[a-z][a-z0-9_]{0,99}$")
_POSTGRES_NUMERIC_MAX_INTEGER_DIGITS = 131_072
_POSTGRES_NUMERIC_MAX_FRACTIONAL_DIGITS = 16_383


def _canonical_decimal_payload(value: Decimal) -> dict[str, object]:
    """Encode an exact Decimal without ambient context or spelling artifacts."""

    _, digit_tuple, exponent_value = value.as_tuple()
    if not isinstance(exponent_value, int):  # finite values always have int exponents
        raise ValueError("declared_weight must be finite")
    digits = list(digit_tuple)
    exponent = exponent_value
    while len(digits) > 1 and digits[-1] == 0:
        digits.pop()
        exponent += 1
    integer_digits = max(len(digits) + exponent, 0)
    fractional_digits = max(-exponent, 0)
    if (
        integer_digits > _POSTGRES_NUMERIC_MAX_INTEGER_DIGITS
        or fractional_digits > _POSTGRES_NUMERIC_MAX_FRACTIONAL_DIGITS
    ):
        raise ValueError(
            "declared_weight exceeds PostgreSQL numeric physical limits"
        )
    return {
        "coefficient": "".join(str(digit) for digit in digits),
        "exponent": exponent,
    }


class CandidateFeatureValueType(StrEnum):
    DECIMAL = "DECIMAL"
    INTEGER = "INTEGER"


class DesirabilityDirection(StrEnum):
    HIGHER_IS_BETTER = "HIGHER_IS_BETTER"
    LOWER_IS_BETTER = "LOWER_IS_BETTER"


@dataclass(frozen=True, slots=True)
class CandidatePolicyComponent:
    candidate_policy_component_id: UUID
    candidate_policy_id: UUID
    component_code: str
    ordinal: int
    feature_definition_id: UUID
    feature_content_sha256: ContentHash | str
    feature_value_type: CandidateFeatureValueType
    direction: DesirabilityDirection
    declared_weight: Decimal

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.component_code):
            raise ValueError("component_code has an invalid format")
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("component ordinal must be positive")
        content_hash = (
            self.feature_content_sha256
            if isinstance(self.feature_content_sha256, ContentHash)
            else ContentHash(self.feature_content_sha256)
        )
        object.__setattr__(
            self,
            "feature_content_sha256",
            content_hash,
        )
        if not isinstance(self.feature_value_type, CandidateFeatureValueType):
            raise TypeError(
                "feature_value_type must be CandidateFeatureValueType"
            )
        if not isinstance(self.direction, DesirabilityDirection):
            raise TypeError(
                "direction must be DesirabilityDirection"
            )
        if not isinstance(self.declared_weight, Decimal):
            raise TypeError("declared_weight must be Decimal")
        if not self.declared_weight.is_finite() or self.declared_weight <= 0:
            raise ValueError("declared_weight must be finite and positive")
        _canonical_decimal_payload(self.declared_weight)

    @property
    def feature_definition_content_sha256(self) -> ContentHash:
        return cast(ContentHash, self.feature_content_sha256)

    @property
    def desirability_direction(self) -> DesirabilityDirection:
        return self.direction

    def semantic_payload(self) -> dict[str, object]:
        return {
            "component_code": self.component_code,
            "declared_weight": _canonical_decimal_payload(self.declared_weight),
            "direction": self.direction,
            "feature_content_sha256": self.feature_content_sha256,
            "feature_definition_id": self.feature_definition_id,
            "feature_value_type": self.feature_value_type,
            "ordinal": self.ordinal,
        }


@dataclass(frozen=True, slots=True)
class CandidatePolicy:
    candidate_policy_id: UUID
    policy_code: str
    version: int
    code_artifact: CandidateArtifactBinding
    config_artifact: CandidateArtifactBinding
    requested_top_k: int
    components: tuple[CandidatePolicyComponent, ...]
    normalization_method: str = "ARITHMETIC_MIDRANK"
    rank_method: str = "COMPETITION"
    missing_policy: str = "STRICT_COMPLETE_CASE"
    selection_method: str = "TOP_K"
    tie_policy: str = "INCLUDE_ALL_BOUNDARY_TIES"
    score_semantics: str = "DESCRIPTIVE_RANK_SCORE"
    decimal_projection_method: str = "EXACT_RATIONAL_ADAPTIVE_HALF_EVEN"
    decimal_projection_version: int = 1
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.policy_code):
            raise ValueError("policy_code has an invalid format")
        if isinstance(self.version, bool) or self.version < 1:
            raise ValueError("policy version must be positive")
        if not isinstance(self.code_artifact, CandidateArtifactBinding):
            raise TypeError("code_artifact must be CandidateArtifactBinding")
        if not isinstance(self.config_artifact, CandidateArtifactBinding):
            raise TypeError("config_artifact must be CandidateArtifactBinding")
        if isinstance(self.requested_top_k, bool) or self.requested_top_k < 1:
            raise ValueError("requested_top_k must be positive")
        if not self.components:
            raise ValueError("CandidatePolicy requires at least one component")
        components = tuple(sorted(self.components, key=lambda item: item.ordinal))
        if any(
            item.candidate_policy_id != self.candidate_policy_id
            for item in components
        ):
            raise ValueError("component parent CandidatePolicy identity must match")
        if len({item.ordinal for item in components}) != len(components):
            raise ValueError("component ordinals must be unique")
        if tuple(item.ordinal for item in components) != tuple(
            range(1, len(components) + 1)
        ):
            raise ValueError("component ordinals must be contiguous from one")
        for field_name, values in (
            ("component codes", [item.component_code for item in components]),
            (
                "component identities",
                [item.candidate_policy_component_id for item in components],
            ),
            (
                "FeatureDefinition identities",
                [item.feature_definition_id for item in components],
            ),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must be unique")
        object.__setattr__(self, "components", components)
        expected_contract = {
            "normalization_method": "ARITHMETIC_MIDRANK",
            "rank_method": "COMPETITION",
            "missing_policy": "STRICT_COMPLETE_CASE",
            "selection_method": "TOP_K",
            "tie_policy": "INCLUDE_ALL_BOUNDARY_TIES",
            "score_semantics": "DESCRIPTIVE_RANK_SCORE",
            "decimal_projection_method": "EXACT_RATIONAL_ADAPTIVE_HALF_EVEN",
        }
        for name, expected in expected_contract.items():
            if getattr(self, name) != expected:
                raise ValueError(f"Candidate V1 requires {name}={expected}")
        if (
            isinstance(self.decimal_projection_version, bool)
            or self.decimal_projection_version != 1
        ):
            raise ValueError("Candidate V1 requires decimal_projection_version=1")
        content_hash = canonical_json_sha256(
            {
                "components": [item.semantic_payload() for item in components],
                "code_artifact": self.code_artifact,
                "config_artifact": self.config_artifact,
                "normalization_method": self.normalization_method,
                "policy_code": self.policy_code,
                "decimal_projection_method": self.decimal_projection_method,
                "decimal_projection_version": self.decimal_projection_version,
                "rank_method": self.rank_method,
                "requested_top_k": self.requested_top_k,
                "score_semantics": self.score_semantics,
                "selection_method": self.selection_method,
                "tie_policy": self.tie_policy,
                "version": self.version,
                "missing_policy": self.missing_policy,
            }
        )
        object.__setattr__(self, "content_sha256", ContentHash(content_hash))

    @property
    def component_count(self) -> int:
        return len(self.components)

    @property
    def projection_method(self) -> str:
        return self.decimal_projection_method

    @property
    def projection_version(self) -> int:
        return self.decimal_projection_version


__all__ = [
    "CandidateFeatureValueType",
    "CandidatePolicy",
    "CandidatePolicyComponent",
    "DesirabilityDirection",
]
