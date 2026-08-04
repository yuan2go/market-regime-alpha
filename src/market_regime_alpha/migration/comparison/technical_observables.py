"""Content-addressed differential evidence for migrated technical observables."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.features.materialization_v2 import VerifiedFeatureBundleV2
from market_regime_alpha.features.technical.catalog import (
    CAPITAL_VOLUME_FEATURE_ID,
    MACD_FEATURE_ID,
    MOVING_AVERAGE_FEATURE_ID,
)
from market_regime_alpha.features.technical.observables import FeatureValueState
from market_regime_alpha.market_data import Timeframe, VerifiedMarketDataDataset
from market_regime_alpha.migration.comparison.contracts import DifferenceClassification
from market_regime_alpha.migration.legacy.adapters.technical_observables import (
    LegacyScalar,
    LegacyTechnicalFamily,
    LegacyTechnicalObservableAdapter,
    LegacyTechnicalResult,
    LegacyTechnicalResultState,
)


POLICY_SCHEMA = "technical-comparison-policy-v1"
REPORT_SCHEMA = "technical-comparison-report-v1"
_PACKAGE_FILES = ("SHA256SUMS.json", "artifact.json", "policy.json")


@dataclass(frozen=True, slots=True)
class TechnicalFamilyComparisonPolicy:
    family: LegacyTechnicalFamily
    output_mappings: tuple[tuple[str, str], ...]
    numeric_tolerance: Decimal
    expected_semantic_change: str | None
    known_legacy_defects: tuple[str, ...]
    canonical_invariants: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.output_mappings != tuple(sorted(self.output_mappings)) or len(
            self.output_mappings
        ) != len(set(self.output_mappings)):
            raise ValueError("technical comparison mappings must be sorted and unique")
        if not self.numeric_tolerance.is_finite() or self.numeric_tolerance < 0:
            raise ValueError("technical comparison tolerance must be non-negative")
        for values in (self.known_legacy_defects, self.canonical_invariants):
            if values != tuple(sorted(set(values))):
                raise ValueError("technical comparison rules must be sorted and unique")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "family": self.family.value,
            "output_mappings": [
                {"legacy": legacy, "canonical": canonical}
                for legacy, canonical in self.output_mappings
            ],
            "numeric_tolerance": str(self.numeric_tolerance),
            "expected_semantic_change": self.expected_semantic_change,
            "known_legacy_defects": list(self.known_legacy_defects),
            "canonical_invariants": list(self.canonical_invariants),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> TechnicalFamilyComparisonPolicy:
        if set(payload) != {
            "family",
            "output_mappings",
            "numeric_tolerance",
            "expected_semantic_change",
            "known_legacy_defects",
            "canonical_invariants",
        }:
            raise ValueError("Technical Family Comparison Policy fields mismatch")
        mappings = _objects(payload["output_mappings"], "output_mappings")
        if any(set(item) != {"legacy", "canonical"} for item in mappings):
            raise ValueError("technical output mapping fields mismatch")
        semantic = payload["expected_semantic_change"]
        if semantic is not None and not isinstance(semantic, str):
            raise ValueError("expected semantic change must be text or null")
        return cls(
            family=LegacyTechnicalFamily(str(payload["family"])),
            output_mappings=tuple(
                (str(item["legacy"]), str(item["canonical"])) for item in mappings
            ),
            numeric_tolerance=Decimal(str(payload["numeric_tolerance"])),
            expected_semantic_change=semantic,
            known_legacy_defects=_strings(
                payload["known_legacy_defects"], "known_legacy_defects"
            ),
            canonical_invariants=_strings(
                payload["canonical_invariants"], "canonical_invariants"
            ),
        )


@dataclass(frozen=True, slots=True)
class TechnicalObservableComparisonPolicy:
    policy_id: ArtifactId
    policy_hash: str
    policy_version: str
    family_policies: tuple[TechnicalFamilyComparisonPolicy, ...]

    def __post_init__(self) -> None:
        require_sha256("policy_hash", self.policy_hash)
        if tuple(item.family.value for item in self.family_policies) != tuple(
            sorted(item.value for item in LegacyTechnicalFamily)
        ):
            raise ValueError("technical comparison policy must cover every family")
        expected_hash = canonical_hash(self.semantic_payload())
        if self.policy_hash != expected_hash:
            raise ValueError("technical comparison policy hash mismatch")
        expected_id = (
            f"technical-comparison-policy-{expected_hash.split(':', 1)[1][:24]}"
        )
        if str(self.policy_id) != expected_id:
            raise ValueError("technical comparison policy identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        policy_version: str,
        family_policies: tuple[TechnicalFamilyComparisonPolicy, ...],
    ) -> TechnicalObservableComparisonPolicy:
        ordered = tuple(sorted(family_policies, key=lambda item: item.family.value))
        payload = {
            "schema_version": POLICY_SCHEMA,
            "policy_version": policy_version,
            "family_policies": [item.to_canonical_dict() for item in ordered],
        }
        content_hash = canonical_hash(payload)
        return cls(
            policy_id=ArtifactId(
                f"technical-comparison-policy-{content_hash.split(':', 1)[1][:24]}"
            ),
            policy_hash=content_hash,
            policy_version=policy_version,
            family_policies=ordered,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": POLICY_SCHEMA,
            "policy_version": self.policy_version,
            "family_policies": [
                item.to_canonical_dict() for item in self.family_policies
            ],
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "policy_id": str(self.policy_id),
            "policy_hash": self.policy_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> TechnicalObservableComparisonPolicy:
        if set(payload) != {
            "schema_version",
            "policy_id",
            "policy_hash",
            "policy_version",
            "family_policies",
        } or payload["schema_version"] != POLICY_SCHEMA:
            raise ValueError("Technical Observable Comparison Policy fields mismatch")
        return cls(
            policy_id=ArtifactId(str(payload["policy_id"])),
            policy_hash=str(payload["policy_hash"]),
            policy_version=str(payload["policy_version"]),
            family_policies=tuple(
                TechnicalFamilyComparisonPolicy.from_canonical_dict(item)
                for item in _objects(payload["family_policies"], "family_policies")
            ),
        )


@dataclass(frozen=True, slots=True)
class TechnicalValueDifference:
    path: str
    legacy_value: str
    canonical_value: str
    absolute_difference: Decimal | None
    within_tolerance: bool

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "legacy_value": self.legacy_value,
            "canonical_value": self.canonical_value,
            "absolute_difference": (
                str(self.absolute_difference)
                if self.absolute_difference is not None
                else None
            ),
            "within_tolerance": self.within_tolerance,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> TechnicalValueDifference:
        if set(payload) != {
            "path",
            "legacy_value",
            "canonical_value",
            "absolute_difference",
            "within_tolerance",
        } or not isinstance(payload["within_tolerance"], bool):
            raise ValueError("Technical Value Difference fields mismatch")
        raw = payload["absolute_difference"]
        if raw is not None and not isinstance(raw, str):
            raise ValueError("technical absolute difference must be text or null")
        return cls(
            path=str(payload["path"]),
            legacy_value=str(payload["legacy_value"]),
            canonical_value=str(payload["canonical_value"]),
            absolute_difference=Decimal(raw) if raw is not None else None,
            within_tolerance=payload["within_tolerance"],
        )


@dataclass(frozen=True, slots=True)
class TechnicalFamilyComparison:
    family: LegacyTechnicalFamily
    classification: DifferenceClassification
    differences: tuple[TechnicalValueDifference, ...]
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]
    unexpected_difference: bool

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "family": self.family.value,
            "classification": self.classification.value,
            "differences": [item.to_canonical_dict() for item in self.differences],
            "reason_codes": list(self.reason_codes),
            "limitations": list(self.limitations),
            "unexpected_difference": self.unexpected_difference,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> TechnicalFamilyComparison:
        if set(payload) != {
            "family",
            "classification",
            "differences",
            "reason_codes",
            "limitations",
            "unexpected_difference",
        } or not isinstance(payload["unexpected_difference"], bool):
            raise ValueError("Technical Family Comparison fields mismatch")
        return cls(
            family=LegacyTechnicalFamily(str(payload["family"])),
            classification=DifferenceClassification(str(payload["classification"])),
            differences=tuple(
                TechnicalValueDifference.from_canonical_dict(item)
                for item in _objects(payload["differences"], "differences")
            ),
            reason_codes=_strings(payload["reason_codes"], "reason_codes"),
            limitations=_strings(payload["limitations"], "limitations"),
            unexpected_difference=payload["unexpected_difference"],
        )


@dataclass(frozen=True, slots=True)
class TechnicalObservableComparisonReport:
    report_id: ArtifactId
    content_hash: str
    policy_id: ArtifactId
    policy_hash: str
    dataset_id: str
    dataset_hash: str
    feature_bundle_id: ArtifactId
    feature_bundle_hash: str
    symbol: str
    items: tuple[TechnicalFamilyComparison, ...]
    unexpected_difference: bool
    canonical_regression: bool
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for label, value in (
            ("content_hash", self.content_hash),
            ("policy_hash", self.policy_hash),
            ("dataset_hash", self.dataset_hash),
            ("feature_bundle_hash", self.feature_bundle_hash),
        ):
            require_sha256(label, value)
        if tuple(item.family.value for item in self.items) != tuple(
            sorted(item.value for item in LegacyTechnicalFamily)
        ):
            raise ValueError("technical report must cover every family")
        if self.unexpected_difference != any(
            item.unexpected_difference for item in self.items
        ):
            raise ValueError("technical report unexpected projection mismatch")
        if self.canonical_regression != any(
            item.classification is DifferenceClassification.CANONICAL_REGRESSION
            for item in self.items
        ):
            raise ValueError("technical report regression projection mismatch")
        expected_hash = canonical_hash(self.semantic_payload())
        if self.content_hash != expected_hash:
            raise ValueError("technical comparison report hash mismatch")
        expected_id = f"technical-comparison-{expected_hash.split(':', 1)[1][:24]}"
        if str(self.report_id) != expected_id:
            raise ValueError("technical comparison report identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": REPORT_SCHEMA,
            "policy_id": str(self.policy_id),
            "policy_hash": self.policy_hash,
            "dataset_id": self.dataset_id,
            "dataset_hash": self.dataset_hash,
            "feature_bundle_id": str(self.feature_bundle_id),
            "feature_bundle_hash": self.feature_bundle_hash,
            "symbol": self.symbol,
            "items": [item.to_canonical_dict() for item in self.items],
            "unexpected_difference": self.unexpected_difference,
            "canonical_regression": self.canonical_regression,
            "limitations": list(self.limitations),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "report_id": str(self.report_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> TechnicalObservableComparisonReport:
        if set(payload) != {
            "schema_version",
            "report_id",
            "content_hash",
            "policy_id",
            "policy_hash",
            "dataset_id",
            "dataset_hash",
            "feature_bundle_id",
            "feature_bundle_hash",
            "symbol",
            "items",
            "unexpected_difference",
            "canonical_regression",
            "limitations",
        } or payload["schema_version"] != REPORT_SCHEMA:
            raise ValueError("Technical Observable Comparison Report fields mismatch")
        if not isinstance(payload["unexpected_difference"], bool) or not isinstance(
            payload["canonical_regression"], bool
        ):
            raise ValueError("technical report projections must be boolean")
        return cls(
            report_id=ArtifactId(str(payload["report_id"])),
            content_hash=str(payload["content_hash"]),
            policy_id=ArtifactId(str(payload["policy_id"])),
            policy_hash=str(payload["policy_hash"]),
            dataset_id=str(payload["dataset_id"]),
            dataset_hash=str(payload["dataset_hash"]),
            feature_bundle_id=ArtifactId(str(payload["feature_bundle_id"])),
            feature_bundle_hash=str(payload["feature_bundle_hash"]),
            symbol=str(payload["symbol"]),
            items=tuple(
                TechnicalFamilyComparison.from_canonical_dict(item)
                for item in _objects(payload["items"], "items")
            ),
            unexpected_difference=payload["unexpected_difference"],
            canonical_regression=payload["canonical_regression"],
            limitations=_strings(payload["limitations"], "limitations"),
        )


@dataclass(frozen=True, slots=True)
class VerifiedTechnicalComparison:
    root: Path
    report: TechnicalObservableComparisonReport
    policy: TechnicalObservableComparisonPolicy


def canonical_technical_comparison_policy() -> TechnicalObservableComparisonPolicy:
    invariants = tuple(
        sorted(
            {
                "AVAILABLE_OUTPUTS_FINITE",
                "NO_FUTURE_INPUT",
                "NO_TRADING_SEMANTICS",
            }
        )
    )
    return TechnicalObservableComparisonPolicy.create(
        policy_version="canonical-technical-migration-v1",
        family_policies=(
            TechnicalFamilyComparisonPolicy(
                family=LegacyTechnicalFamily.MOVING_AVERAGE,
                output_mappings=tuple(
                    sorted(
                        (f"sma_{period}", f"sma_{period}")
                        for period in (5, 10, 20, 60)
                    )
                ),
                numeric_tolerance=Decimal("0.000000000001"),
                expected_semantic_change=None,
                known_legacy_defects=(),
                canonical_invariants=tuple(
                    sorted((*invariants, "SMA_STRICT_TRAILING_WINDOW"))
                ),
            ),
            TechnicalFamilyComparisonPolicy(
                family=LegacyTechnicalFamily.EMA,
                output_mappings=tuple(
                    sorted(
                        (f"ema_{period}", f"ema_{period}")
                        for period in (5, 10, 12, 20, 26, 60)
                    )
                ),
                numeric_tolerance=Decimal("0.00000000001"),
                expected_semantic_change=None,
                known_legacy_defects=(),
                canonical_invariants=tuple(
                    sorted((*invariants, "EMA_FIRST_OBSERVATION_RECURSION"))
                ),
            ),
            TechnicalFamilyComparisonPolicy(
                family=LegacyTechnicalFamily.MACD,
                output_mappings=(
                    ("cross", "cross_state"),
                    ("dea", "dea"),
                    ("dif", "dif"),
                    ("histogram", "histogram"),
                    ("histogram_trend", "histogram_expansion_state"),
                    ("zero_axis", "zero_axis_state"),
                ),
                numeric_tolerance=Decimal("0.00000000001"),
                expected_semantic_change="MACD_STATE_VOCABULARY_VERSIONED",
                known_legacy_defects=(),
                canonical_invariants=tuple(
                    sorted(
                        (
                            *invariants,
                            "MACD_DIF_EQUALS_EMA_FAST_MINUS_EMA_SLOW",
                            "MACD_HISTOGRAM_MULTIPLIER_TWO",
                        )
                    )
                ),
            ),
            TechnicalFamilyComparisonPolicy(
                family=LegacyTechnicalFamily.VOLUME_RATIO,
                output_mappings=(
                    ("volume_ratio_20_including_current", "volume_ratio_20"),
                ),
                numeric_tolerance=Decimal("0"),
                expected_semantic_change=(
                    "CANONICAL_DENOMINATOR_EXCLUDES_CURRENT_SESSION"
                ),
                known_legacy_defects=(
                    "LEGACY_DENOMINATOR_INCLUDES_CURRENT_SESSION",
                ),
                canonical_invariants=tuple(
                    sorted((*invariants, "VOLUME_RATIO_PRIOR_COMPLETED_WINDOW"))
                ),
            ),
            TechnicalFamilyComparisonPolicy(
                family=LegacyTechnicalFamily.AMOUNT_STRUCTURE,
                output_mappings=(),
                numeric_tolerance=Decimal("0.0000000000010"),
                expected_semantic_change=None,
                known_legacy_defects=(),
                canonical_invariants=tuple(
                    sorted((*invariants, "AMOUNT_USES_REAL_PROVIDER_FIELD"))
                ),
            ),
        ),
    )


def compare_technical_observables(
    *,
    verified_dataset: VerifiedMarketDataDataset,
    feature_bundle: VerifiedFeatureBundleV2,
    symbol: str,
    policy: TechnicalObservableComparisonPolicy,
) -> TechnicalObservableComparisonReport:
    dataset = verified_dataset.artifact
    bundle = feature_bundle.artifact
    dataset.verify_identity()
    bundle.verify_identity()
    if bundle.dataset_id != dataset.dataset_id or bundle.dataset_hash != dataset.content_hash:
        raise ValueError("technical comparison Dataset and Feature Bundle mismatch")
    if symbol not in bundle.symbols:
        raise ValueError("technical comparison symbol is not in Feature Bundle")
    bars = verified_dataset.bars_for(symbol=symbol, timeframe=Timeframe.DAILY)
    adapter = LegacyTechnicalObservableAdapter()
    items = tuple(
        _compare_family(
            legacy=adapter.compute(family=family_policy.family, bars=bars),
            family_policy=family_policy,
            feature_bundle=feature_bundle,
            verified_dataset=verified_dataset,
            symbol=symbol,
        )
        for family_policy in policy.family_policies
    )
    limitations = (
        "COMPARISON_EVIDENCE_NOT_SIGNAL_AUTHORITY",
        "LEGACY_FLOAT_SEMANTICS",
        "NO_TRADING_AUTHORITY",
        "RESEARCH_ONLY",
    )
    unexpected_difference = any(item.unexpected_difference for item in items)
    canonical_regression = any(
        item.classification is DifferenceClassification.CANONICAL_REGRESSION
        for item in items
    )
    semantic = _report_payload(
        policy_id=policy.policy_id,
        policy_hash=policy.policy_hash,
        dataset_id=str(dataset.dataset_id),
        dataset_hash=dataset.content_hash,
        feature_bundle_id=bundle.bundle_id,
        feature_bundle_hash=bundle.content_hash,
        symbol=symbol,
        items=items,
        unexpected_difference=unexpected_difference,
        canonical_regression=canonical_regression,
        limitations=limitations,
    )
    content_hash = canonical_hash(semantic)
    return TechnicalObservableComparisonReport(
        report_id=ArtifactId(
            f"technical-comparison-{content_hash.split(':', 1)[1][:24]}"
        ),
        content_hash=content_hash,
        policy_id=policy.policy_id,
        policy_hash=policy.policy_hash,
        dataset_id=str(dataset.dataset_id),
        dataset_hash=dataset.content_hash,
        feature_bundle_id=bundle.bundle_id,
        feature_bundle_hash=bundle.content_hash,
        symbol=symbol,
        items=items,
        unexpected_difference=unexpected_difference,
        canonical_regression=canonical_regression,
        limitations=limitations,
    )


def _compare_family(
    *,
    legacy: LegacyTechnicalResult,
    family_policy: TechnicalFamilyComparisonPolicy,
    feature_bundle: VerifiedFeatureBundleV2,
    verified_dataset: VerifiedMarketDataDataset,
    symbol: str,
) -> TechnicalFamilyComparison:
    invariant_reasons = _validate_canonical_invariants(
        family=family_policy.family,
        feature_bundle=feature_bundle,
        verified_dataset=verified_dataset,
        symbol=symbol,
    )
    if invariant_reasons:
        return TechnicalFamilyComparison(
            family=family_policy.family,
            classification=DifferenceClassification.CANONICAL_REGRESSION,
            differences=(),
            reason_codes=invariant_reasons,
            limitations=legacy.limitations,
            unexpected_difference=True,
        )
    state_classification = {
        LegacyTechnicalResultState.NOT_COMPARABLE: (
            DifferenceClassification.NOT_COMPARABLE
        ),
        LegacyTechnicalResultState.DATA_INSUFFICIENT: (
            DifferenceClassification.INSUFFICIENT_DATA
        ),
        LegacyTechnicalResultState.FAILED: DifferenceClassification.NOT_COMPARABLE,
    }.get(legacy.state)
    if state_classification is not None:
        return _state_comparison(legacy, state_classification)
    canonical = _canonical_values(
        family=family_policy.family,
        feature_bundle=feature_bundle,
        symbol=symbol,
    )
    differences: list[TechnicalValueDifference] = []
    for legacy_key, canonical_key in family_policy.output_mappings:
        legacy_value = legacy.values[legacy_key]
        canonical_value = canonical.get(canonical_key)
        if canonical_value is None:
            return TechnicalFamilyComparison(
                family=family_policy.family,
                classification=DifferenceClassification.CANONICAL_REGRESSION,
                differences=(),
                reason_codes=(f"CANONICAL_OUTPUT_MISSING:{canonical_key}",),
                limitations=legacy.limitations,
                unexpected_difference=True,
            )
        difference = _difference(
            path=f"{family_policy.family.value}.{canonical_key}",
            legacy_value=legacy_value,
            canonical_value=canonical_value,
            tolerance=family_policy.numeric_tolerance,
        )
        if difference is not None:
            differences.append(difference)
    if not differences:
        classification = DifferenceClassification.EXACT_MATCH
        reasons = ("LEGACY_CANONICAL_EXACT_MATCH",)
        unexpected = False
    elif all(item.within_tolerance for item in differences):
        classification = DifferenceClassification.NUMERIC_TOLERANCE
        reasons = ("LEGACY_CANONICAL_WITHIN_FAMILY_TOLERANCE",)
        unexpected = False
    elif family_policy.expected_semantic_change is not None:
        classification = DifferenceClassification.EXPECTED_SEMANTIC_CHANGE
        reasons = (family_policy.expected_semantic_change,)
        unexpected = False
    else:
        classification = DifferenceClassification.CANONICAL_REGRESSION
        reasons = ("UNEXPECTED_LEGACY_CANONICAL_DIFFERENCE",)
        unexpected = True
    return TechnicalFamilyComparison(
        family=family_policy.family,
        classification=classification,
        differences=tuple(differences),
        reason_codes=reasons,
        limitations=legacy.limitations,
        unexpected_difference=unexpected,
    )


def _validate_canonical_invariants(
    *,
    family: LegacyTechnicalFamily,
    feature_bundle: VerifiedFeatureBundleV2,
    verified_dataset: VerifiedMarketDataDataset,
    symbol: str,
) -> tuple[str, ...]:
    artifacts = tuple(
        item.artifact
        for item in feature_bundle.artifacts
        if item.artifact.symbol == symbol
    )
    if any(item.available_at > feature_bundle.artifact.decision_time for item in artifacts):
        return ("CANONICAL_FEATURE_FROM_FUTURE",)
    trading_outputs = {"BUY", "SELL", "ENTER", "ADD", "REDUCE", "EXIT"}
    if any(
        value.output_id in trading_outputs
        for artifact in artifacts
        for value in artifact.values
    ):
        return ("CANONICAL_FEATURE_HAS_TRADING_SEMANTICS",)
    if family is LegacyTechnicalFamily.MACD:
        values = _canonical_values(
            family=family, feature_bundle=feature_bundle, symbol=symbol
        )
        if not all(
            isinstance(values.get(key), Decimal)
            for key in ("dif", "dea", "histogram")
        ):
            return ("CANONICAL_MACD_NUMERIC_OUTPUT_MISSING",)
        dif = values["dif"]
        dea = values["dea"]
        histogram = values["histogram"]
        assert isinstance(dif, Decimal)
        assert isinstance(dea, Decimal)
        assert isinstance(histogram, Decimal)
        if abs(histogram - Decimal("2") * (dif - dea)) > Decimal(
            "0.000000000002"
        ):
            return ("CANONICAL_MACD_HISTOGRAM_INVARIANT_FAILED",)
    if family is LegacyTechnicalFamily.VOLUME_RATIO:
        bars = verified_dataset.bars_for(
            symbol=symbol, timeframe=Timeframe.DAILY
        )
        if len(bars) >= 21 and all(item.volume is not None for item in bars[-21:]):
            prior = tuple(item.volume for item in bars[-21:-1])
            denominator = sum(
                (item for item in prior if item is not None), Decimal("0")
            ) / Decimal("20")
            current = bars[-1].volume
            assert current is not None
            expected = (current / denominator).quantize(Decimal("0.000000000001"))
            actual = _canonical_values(
                family=family, feature_bundle=feature_bundle, symbol=symbol
            ).get("volume_ratio_20")
            if actual != expected:
                return ("CANONICAL_VOLUME_RATIO_DENOMINATOR_INVARIANT_FAILED",)
    return ()


def _canonical_values(
    *,
    family: LegacyTechnicalFamily,
    feature_bundle: VerifiedFeatureBundleV2,
    symbol: str,
) -> dict[str, LegacyScalar]:
    feature_id = {
        LegacyTechnicalFamily.MOVING_AVERAGE: MOVING_AVERAGE_FEATURE_ID,
        LegacyTechnicalFamily.EMA: MOVING_AVERAGE_FEATURE_ID,
        LegacyTechnicalFamily.MACD: MACD_FEATURE_ID,
        LegacyTechnicalFamily.VOLUME_RATIO: CAPITAL_VOLUME_FEATURE_ID,
        LegacyTechnicalFamily.AMOUNT_STRUCTURE: CAPITAL_VOLUME_FEATURE_ID,
    }[family]
    matches = tuple(
        item.artifact
        for item in feature_bundle.artifacts
        if item.artifact.symbol == symbol
        and item.artifact.feature_id == feature_id
        and item.artifact.timeframe is Timeframe.DAILY
    )
    if len(matches) != 1:
        raise ValueError("canonical comparison Feature Artifact is not unique")
    return {
        item.output_id: item.value
        for item in matches[0].values
        if item.state is FeatureValueState.AVAILABLE
        and isinstance(item.value, (Decimal, str))
    }


def _difference(
    *,
    path: str,
    legacy_value: LegacyScalar,
    canonical_value: LegacyScalar,
    tolerance: Decimal,
) -> TechnicalValueDifference | None:
    if isinstance(legacy_value, Decimal) and isinstance(canonical_value, Decimal):
        absolute = abs(legacy_value - canonical_value)
        if absolute == 0:
            return None
        return TechnicalValueDifference(
            path=path,
            legacy_value=str(legacy_value),
            canonical_value=str(canonical_value),
            absolute_difference=absolute,
            within_tolerance=absolute <= tolerance,
        )
    if str(legacy_value) == str(canonical_value):
        return None
    return TechnicalValueDifference(
        path=path,
        legacy_value=str(legacy_value),
        canonical_value=str(canonical_value),
        absolute_difference=None,
        within_tolerance=False,
    )


def _state_comparison(
    legacy: LegacyTechnicalResult,
    classification: DifferenceClassification,
) -> TechnicalFamilyComparison:
    return TechnicalFamilyComparison(
        family=legacy.family,
        classification=classification,
        differences=(),
        reason_codes=legacy.reason_codes,
        limitations=legacy.limitations,
        unexpected_difference=False,
    )


def _report_payload(
    *,
    policy_id: ArtifactId,
    policy_hash: str,
    dataset_id: str,
    dataset_hash: str,
    feature_bundle_id: ArtifactId,
    feature_bundle_hash: str,
    symbol: str,
    items: tuple[TechnicalFamilyComparison, ...],
    unexpected_difference: bool,
    canonical_regression: bool,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": REPORT_SCHEMA,
        "policy_id": str(policy_id),
        "policy_hash": policy_hash,
        "dataset_id": dataset_id,
        "dataset_hash": dataset_hash,
        "feature_bundle_id": str(feature_bundle_id),
        "feature_bundle_hash": feature_bundle_hash,
        "symbol": symbol,
        "items": [item.to_canonical_dict() for item in items],
        "unexpected_difference": unexpected_difference,
        "canonical_regression": canonical_regression,
        "limitations": list(limitations),
    }


def publish_technical_comparison(
    *,
    root: Path,
    report: TechnicalObservableComparisonReport,
    policy: TechnicalObservableComparisonPolicy,
) -> Path:
    if report.policy_id != policy.policy_id or report.policy_hash != policy.policy_hash:
        raise ValueError("technical report Policy binding mismatch")
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(report.report_id)
    if final.exists():
        existing = load_verified_technical_comparison(final)
        if existing.report != report or existing.policy != policy:
            raise FileExistsError("conflicting technical comparison package exists")
        return final
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    installed = False
    try:
        _write_json(stage / "artifact.json", report.to_canonical_dict())
        _write_json(stage / "policy.json", policy.to_canonical_dict())
        _write_json(
            stage / "SHA256SUMS.json",
            {
                name: _file_hash(stage / name)
                for name in _PACKAGE_FILES
                if name != "SHA256SUMS.json"
            },
        )
        _fsync_directory(stage)
        _load_verified_technical_comparison(stage, enforce_identity=False)
        os.replace(stage, final)
        installed = True
        _fsync_directory(root)
        return final
    finally:
        if not installed and stage.exists():
            shutil.rmtree(stage)


def load_verified_technical_comparison(path: Path) -> VerifiedTechnicalComparison:
    return _load_verified_technical_comparison(path, enforce_identity=True)


def _load_verified_technical_comparison(
    path: Path, *, enforce_identity: bool
) -> VerifiedTechnicalComparison:
    root = path.resolve()
    if not root.is_dir() or {item.name for item in root.iterdir()} != set(
        _PACKAGE_FILES
    ):
        raise ValueError("technical comparison exact file set mismatch")
    checksums = _read_object(root / "SHA256SUMS.json")
    if set(checksums) != set(_PACKAGE_FILES) - {"SHA256SUMS.json"}:
        raise ValueError("technical comparison checksum coverage mismatch")
    for name, expected_hash in checksums.items():
        if not isinstance(expected_hash, str) or _file_hash(root / name) != expected_hash:
            raise ValueError(f"technical comparison checksum mismatch: {name}")
    policy = TechnicalObservableComparisonPolicy.from_canonical_dict(
        _read_object(root / "policy.json")
    )
    report = TechnicalObservableComparisonReport.from_canonical_dict(
        _read_object(root / "artifact.json")
    )
    if report.policy_id != policy.policy_id or report.policy_hash != policy.policy_hash:
        raise ValueError("technical comparison Policy reference mismatch")
    if enforce_identity and root.name != str(report.report_id):
        raise ValueError("technical comparison directory identity mismatch")
    return VerifiedTechnicalComparison(root=root, report=report, policy=policy)


def replay_technical_comparison(
    path: Path,
    *,
    verified_dataset: VerifiedMarketDataDataset,
    feature_bundle: VerifiedFeatureBundleV2,
) -> VerifiedTechnicalComparison:
    verified = load_verified_technical_comparison(path)
    replayed = compare_technical_observables(
        verified_dataset=verified_dataset,
        feature_bundle=feature_bundle,
        symbol=verified.report.symbol,
        policy=verified.policy,
    )
    if replayed != verified.report:
        raise ValueError("technical comparison replay mismatch")
    return verified


def _write_json(path: Path, payload: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("invalid technical comparison JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("technical comparison JSON must be an object")
    return payload


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be an array of strings")
    return tuple(value)


def _objects(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be an array of objects")
    return value


__all__ = [
    "TechnicalFamilyComparison",
    "TechnicalFamilyComparisonPolicy",
    "TechnicalObservableComparisonPolicy",
    "TechnicalObservableComparisonReport",
    "TechnicalValueDifference",
    "VerifiedTechnicalComparison",
    "canonical_technical_comparison_policy",
    "compare_technical_observables",
    "load_verified_technical_comparison",
    "publish_technical_comparison",
    "replay_technical_comparison",
]
