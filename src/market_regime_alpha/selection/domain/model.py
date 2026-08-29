"""Immutable Universe scope and Eligibility policy definitions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
import re
from uuid import UUID

from market_regime_alpha.selection.domain.vocabulary import (
    CriterionOperator,
    CriterionValueKind,
    EligibilityRuleKind,
)
from market_regime_alpha.shared.financial import bounded_decimal
from market_regime_alpha.shared.hashing import canonical_json_sha256, sha256_bytes
from market_regime_alpha.shared.identity import ContentHash, InstrumentId


_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,99}$")


@dataclass(frozen=True, slots=True)
class UniverseDefinition:
    universe_id: UUID
    universe_code: str
    purpose: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,99}", self.universe_code):
            raise ValueError("universe_code has an invalid format")
        if not self.purpose:
            raise ValueError("Universe purpose is required")


@dataclass(frozen=True, slots=True)
class UniverseScopeSpecification:
    """Exact config Artifact binding for one explicit classification roster."""

    artifact_id: UUID
    content_sha256: ContentHash | str
    size_bytes: int
    market_provider_product_id: UUID
    classification_scheme: str
    classification_code: str
    instrument_ids: tuple[InstrumentId, ...]
    schema: str = "selection-universe-scope-v1"

    def __post_init__(self) -> None:
        content_hash = self.content_sha256 if isinstance(self.content_sha256, ContentHash) else ContentHash(self.content_sha256)
        object.__setattr__(self, "content_sha256", content_hash)
        if isinstance(self.size_bytes, bool) or self.size_bytes < 0:
            raise ValueError("scope size_bytes must be non-negative")
        if self.schema != "selection-universe-scope-v1":
            raise ValueError("unsupported Universe scope schema")
        if not re.fullmatch(
            r"[A-Z][A-Z0-9_]{0,31}",
            self.classification_scheme,
        ):
            raise ValueError("classification_scheme has an invalid format")
        if not self.classification_code:
            raise ValueError("classification_code is required")
        instruments = tuple(InstrumentId.parse(item) for item in self.instrument_ids)
        if instruments != tuple(sorted(set(instruments), key=lambda item: str(item))):
            raise ValueError("scope instrument_ids must be unique and sorted")
        object.__setattr__(self, "instrument_ids", instruments)
        content = self.canonical_bytes()
        if len(content) != self.size_bytes:
            raise ValueError("scope size does not match canonical config bytes")
        if sha256_bytes(content) != content_hash.value:
            raise ValueError("scope hash does not match canonical config bytes")

    def canonical_bytes(self) -> bytes:
        payload = {
            "classification_code": self.classification_code,
            "classification_scheme": self.classification_scheme,
            "instrument_ids": [str(item) for item in self.instrument_ids],
            "market_provider_product_id": str(self.market_provider_product_id),
            "schema": self.schema,
        }
        return json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class EligibilityRule:
    eligibility_rule_id: UUID
    rule_code: str
    ordinal: int
    rule_kind: EligibilityRuleKind
    measure_code: str
    aggregation: str
    window_value: int
    window_unit: str
    value_kind: CriterionValueKind
    operator: CriterionOperator
    value_unit: str
    threshold_decimal: Decimal | None = None
    threshold_status: str | None = None
    threshold_count: int | None = None

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.rule_code):
            raise ValueError("rule_code has an invalid format")
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("rule ordinal must be positive")
        if not isinstance(self.rule_kind, EligibilityRuleKind):
            raise TypeError("rule_kind must be EligibilityRuleKind")
        if not isinstance(self.value_kind, CriterionValueKind):
            raise TypeError("value_kind must be CriterionValueKind")
        if not isinstance(self.operator, CriterionOperator):
            raise TypeError("operator must be CriterionOperator")
        if not _CODE.fullmatch(self.measure_code):
            raise ValueError("measure_code has an invalid format")
        if not _CODE.fullmatch(self.aggregation):
            raise ValueError("aggregation has an invalid format")
        if not _CODE.fullmatch(self.window_unit):
            raise ValueError("window_unit has an invalid format")
        if not _CODE.fullmatch(self.value_unit):
            raise ValueError("value_unit has an invalid format")
        if isinstance(self.window_value, bool) or self.window_value < 0:
            raise ValueError("window_value must be non-negative")
        if self.threshold_decimal is not None:
            object.__setattr__(
                self,
                "threshold_decimal",
                bounded_decimal(
                    self.threshold_decimal,
                    field="eligibility threshold",
                    precision=30,
                    scale=10,
                ),
            )
        if self.threshold_count is not None and (isinstance(self.threshold_count, bool) or self.threshold_count < 0):
            raise ValueError("threshold_count must be non-negative")
        self._validate_shape()

    def _validate_shape(self) -> None:
        expected: dict[EligibilityRuleKind, tuple[object, ...]] = {
            EligibilityRuleKind.NOT_SUSPENDED: (
                "SECURITY_STATUS",
                "POINT",
                1,
                "SESSION",
                CriterionValueKind.STATUS,
                CriterionOperator.EQ,
                "STATUS",
                None,
                "ACTIVE",
                None,
            ),
            EligibilityRuleKind.NOT_SPECIAL_TREATMENT: (
                "SPECIAL_TREATMENT_STATUS",
                "POINT",
                0,
                "NONE",
                CriterionValueKind.STATUS,
                CriterionOperator.EQ,
                "STATUS",
                None,
                "NORMAL",
                None,
            ),
            EligibilityRuleKind.MIN_LISTING_AGE: (
                "LISTING_AGE",
                "ELAPSED",
                0,
                "NONE",
                CriterionValueKind.DECIMAL,
                CriterionOperator.GTE,
                "CALENDAR_DAYS",
                self.threshold_decimal,
                None,
                None,
            ),
            EligibilityRuleKind.MIN_LIQUIDITY: (
                "TURNOVER_VALUE",
                "MEAN",
                self.window_value,
                "SESSION",
                CriterionValueKind.DECIMAL,
                CriterionOperator.GTE,
                self.value_unit,
                self.threshold_decimal,
                None,
                None,
            ),
            EligibilityRuleKind.LIMIT_METADATA_PRESENT: (
                "LIMIT_PRICE_FACT_COUNT",
                "COUNT",
                1,
                "SESSION",
                CriterionValueKind.COUNT,
                CriterionOperator.GTE,
                "FACT_COUNT",
                None,
                None,
                3,
            ),
        }
        actual = (
            self.measure_code,
            self.aggregation,
            self.window_value,
            self.window_unit,
            self.value_kind,
            self.operator,
            self.value_unit,
            self.threshold_decimal,
            self.threshold_status,
            self.threshold_count,
        )
        if actual != expected[self.rule_kind]:
            raise ValueError(f"invalid explicit shape for {self.rule_kind.value}")
        if self.rule_kind in {
            EligibilityRuleKind.MIN_LISTING_AGE,
            EligibilityRuleKind.MIN_LIQUIDITY,
        } and (self.threshold_decimal is None or self.threshold_decimal < 0):
            raise ValueError("decimal threshold must be explicit and non-negative")
        if self.rule_kind is EligibilityRuleKind.MIN_LIQUIDITY:
            if self.window_value < 1 or not re.fullmatch(r"[A-Z]{3}", self.value_unit):
                raise ValueError("liquidity needs an explicit session window and currency")

    def semantic_payload(self) -> dict[str, object]:
        return {
            "aggregation": self.aggregation,
            "measure_code": self.measure_code,
            "operator": self.operator.value,
            "ordinal": self.ordinal,
            "rule_code": self.rule_code,
            "rule_kind": self.rule_kind.value,
            "threshold_count": self.threshold_count,
            "threshold_decimal": self.threshold_decimal,
            "threshold_status": self.threshold_status,
            "value_kind": self.value_kind.value,
            "value_unit": self.value_unit,
            "window_unit": self.window_unit,
            "window_value": self.window_value,
        }


@dataclass(frozen=True, slots=True)
class EligibilityPolicy:
    eligibility_policy_id: UUID
    market_provider_product_id: UUID
    policy_code: str
    version: int
    rules: tuple[EligibilityRule, ...]

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,99}", self.policy_code):
            raise ValueError("policy_code has an invalid format")
        if isinstance(self.version, bool) or self.version < 1:
            raise ValueError("policy version must be positive")
        if not self.rules:
            raise ValueError("Eligibility policy requires at least one rule")
        if tuple(rule.ordinal for rule in self.rules) != tuple(range(1, len(self.rules) + 1)):
            raise ValueError("Eligibility rules must be completely ordered")
        if len({rule.rule_code for rule in self.rules}) != len(self.rules):
            raise ValueError("Eligibility rule codes must be unique")
        if len({rule.eligibility_rule_id for rule in self.rules}) != len(self.rules):
            raise ValueError("Eligibility rule identities must be unique")

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(
            {
                "market_provider_product_id": self.market_provider_product_id,
                "policy_code": self.policy_code,
                "rules": [rule.semantic_payload() for rule in self.rules],
                "version": self.version,
            }
        )


__all__ = [
    "EligibilityPolicy",
    "EligibilityRule",
    "UniverseDefinition",
    "UniverseScopeSpecification",
]
