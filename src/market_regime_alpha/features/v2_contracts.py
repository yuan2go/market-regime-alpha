"""Immutable Feature Artifact V2, Bundle, receipt, and replay contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId, DatasetId, ModelId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
    require_unique_text,
)
from market_regime_alpha.features.spine import (
    FeatureConfiguration,
    FeatureDefinitionV2,
    FeatureSetConfiguration,
    FeatureValidationStatus,
    RequiredFeatureCoveragePolicy,
    ValueType,
)
from market_regime_alpha.features.technical.observables import (
    FeatureScalar,
    FeatureValueState,
    TechnicalFeatureComputation,
    TechnicalFeatureValue,
)
from market_regime_alpha.market_data import (
    AdjustmentMode,
    CanonicalMarketBar,
    FormalPitStatus,
    MarketDataDatasetArtifact,
    Timeframe,
)
from market_regime_alpha.market_data.contracts import (
    parse_utc_second,
    require_utc_second,
)


FEATURE_ARTIFACT_V2_SCHEMA = "feature-artifact-v2"
FEATURE_BUNDLE_V1_SCHEMA = "feature-bundle-v1"
FEATURE_MATERIALIZATION_RECEIPT_SCHEMA = "feature-materialization-receipt-v1"
FEATURE_REPLAY_REPORT_SCHEMA = "feature-bundle-replay-report-v1"


class FeatureArtifactState(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL_COVERAGE = "PARTIAL_COVERAGE"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


class FeatureBundleState(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL_COVERAGE = "PARTIAL_COVERAGE"
    BLOCKED_REQUIRED_FEATURE = "BLOCKED_REQUIRED_FEATURE"


class FeatureMaterializationStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL_COVERAGE = "PARTIAL_COVERAGE"
    BLOCKED_REQUIRED_FEATURE = "BLOCKED_REQUIRED_FEATURE"


class _VerifiedDatasetMembership:
    """Run-local immutable membership index bound to one Dataset object."""

    __slots__ = ("bar_hashes", "dataset")

    def __init__(self, dataset: MarketDataDatasetArtifact) -> None:
        dataset.verify_identity()
        self.dataset = dataset
        self.bar_hashes: Mapping[ArtifactId, str] = MappingProxyType(
            {item.bar_id: item.content_hash for item in dataset.iter_bars()}
        )


def _verified_dataset_membership(
    dataset: MarketDataDatasetArtifact,
) -> _VerifiedDatasetMembership:
    return _VerifiedDatasetMembership(dataset)


@dataclass(frozen=True, slots=True)
class FeatureArtifactV2:
    schema_version: str
    artifact_id: ArtifactId
    content_hash: str
    feature_id: str
    feature_version: str
    definition: FeatureDefinitionV2
    model_id: ModelId
    model_version: str
    configuration: FeatureConfiguration
    dataset_id: DatasetId
    dataset_hash: str
    symbol: str
    timeframe: Timeframe
    decision_time: datetime
    created_at: datetime
    available_at: datetime
    source_bar_ids: tuple[ArtifactId, ...]
    source_bar_hashes: tuple[str, ...]
    values: tuple[TechnicalFeatureValue, ...]
    state: FeatureArtifactState
    data_eligibility: DataEligibility
    formal_pit_status: FormalPitStatus
    validation_status: FeatureValidationStatus
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != FEATURE_ARTIFACT_V2_SCHEMA:
            raise ValueError("unsupported Feature Artifact V2 schema")
        require_sha256("content_hash", self.content_hash)
        require_text("feature_id", self.feature_id)
        require_text("feature_version", self.feature_version)
        require_text("model_version", self.model_version)
        require_text("symbol", self.symbol)
        for label, timestamp in (
            ("decision_time", self.decision_time),
            ("created_at", self.created_at),
            ("available_at", self.available_at),
        ):
            require_utc_second(label, timestamp)
        if self.created_at < self.decision_time:
            raise ValueError("Feature Artifact created_at cannot precede DecisionTime")
        if self.available_at > self.decision_time:
            raise ValueError("Feature Artifact evidence became available after DecisionTime")
        self.definition.verify_identity()
        self.configuration.verify_identity()
        if (
            self.feature_id != self.definition.feature_id
            or self.feature_version != self.definition.feature_version
            or self.model_id != self.definition.model_id
            or self.model_version != self.definition.model_version
            or self.configuration.feature_id != self.feature_id
        ):
            raise ValueError("Feature Artifact definition/configuration scope mismatch")
        if self.timeframe not in self.definition.supported_timeframes:
            raise ValueError("Feature Artifact timeframe is unsupported by definition")
        require_sha256("dataset_hash", self.dataset_hash)
        if len(self.source_bar_ids) != len(self.source_bar_hashes):
            raise ValueError("Feature Artifact source bars must align")
        if len(self.source_bar_ids) != len(set(self.source_bar_ids)):
            raise ValueError("Feature Artifact source bars must be unique")
        source_map = dict(zip(self.source_bar_ids, self.source_bar_hashes, strict=True))
        for item_hash in self.source_bar_hashes:
            require_sha256("source_bar_hash", item_hash)
        output_map = {item.output_id: item.value_type for item in self.definition.output_schema}
        output_ids = tuple(item.output_id for item in self.values)
        if output_ids != tuple(sorted(output_map)):
            raise ValueError("Feature Artifact values do not match definition output schema")
        for value in self.values:
            _validate_scalar_type(value=value, expected=output_map[value.output_id])
            for item_id, item_hash in zip(
                value.source_bar_ids, value.source_bar_hashes, strict=True
            ):
                if source_map.get(item_id) != item_hash:
                    raise ValueError("Feature value references an unbound source bar")
        available_count = sum(
            item.state is FeatureValueState.AVAILABLE for item in self.values
        )
        expected_state = (
            FeatureArtifactState.DATA_INSUFFICIENT
            if available_count == 0
            else FeatureArtifactState.COMPLETE
            if available_count == len(self.values)
            else FeatureArtifactState.PARTIAL_COVERAGE
        )
        if self.state is not expected_state:
            raise ValueError("Feature Artifact state does not match value coverage")
        require_unique_text("limitation", self.limitations)
        if self.limitations != tuple(sorted(self.limitations)):
            raise ValueError("Feature Artifact limitations must be sorted")
        if "TRADING_AUTHORITY_NOT_GRANTED" not in self.limitations:
            raise ValueError("Feature Artifact must preserve trading authority ceiling")
        if any(
            item.output_id in {"BUY", "SELL", "ENTER", "ADD", "REDUCE", "EXIT"}
            for item in self.values
        ):
            raise ValueError("Feature Artifact cannot contain trading actions")

    @classmethod
    def create(
        cls,
        *,
        definition: FeatureDefinitionV2,
        configuration: FeatureConfiguration,
        dataset: MarketDataDatasetArtifact,
        computation: TechnicalFeatureComputation,
        input_bars: tuple[CanonicalMarketBar, ...],
        created_at: datetime,
        _membership: _VerifiedDatasetMembership | None = None,
    ) -> FeatureArtifactV2:
        if _membership is None:
            dataset.verify_identity()
        elif _membership.dataset is not dataset:
            raise ValueError("Feature Dataset membership index scope mismatch")
        definition.verify_identity()
        configuration.verify_identity()
        if computation.feature_id != definition.feature_id:
            raise ValueError("Feature computation does not match definition")
        if computation.configuration_id != configuration.configuration_id or (
            computation.configuration_hash != configuration.configuration_hash
        ):
            raise ValueError("Feature computation does not match configuration")
        dataset_bars = (
            _membership.bar_hashes
            if _membership is not None
            else {item.bar_id: item.content_hash for item in dataset.iter_bars()}
        )
        for bar in input_bars:
            if _membership is None:
                bar.verify_identity()
            if dataset_bars.get(bar.bar_id) != bar.content_hash:
                raise ValueError("Feature input bar is not part of Market Data Dataset")
        if any(
            item.symbol != computation.symbol
            or item.timeframe is not computation.timeframe
            for item in input_bars
        ):
            raise ValueError("Feature input bar scope mismatch")
        source_ids = tuple(item.bar_id for item in input_bars)
        source_hashes = tuple(item.content_hash for item in input_bars)
        available_count = sum(
            item.state is FeatureValueState.AVAILABLE for item in computation.values
        )
        state = (
            FeatureArtifactState.DATA_INSUFFICIENT
            if available_count == 0
            else FeatureArtifactState.COMPLETE
            if available_count == len(computation.values)
            else FeatureArtifactState.PARTIAL_COVERAGE
        )
        limitations = tuple(
            sorted(
                {
                    *dataset.limitations,
                    *definition.limitations,
                    *computation.limitations,
                    "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
                    "TRADING_AUTHORITY_NOT_GRANTED",
                }
            )
        )
        semantic = _feature_artifact_payload(
            feature_id=definition.feature_id,
            feature_version=definition.feature_version,
            definition=definition,
            model_id=definition.model_id,
            model_version=definition.model_version,
            configuration=configuration,
            dataset_id=dataset.dataset_id,
            dataset_hash=dataset.content_hash,
            symbol=computation.symbol,
            timeframe=computation.timeframe,
            decision_time=dataset.decision_time,
            created_at=created_at,
            available_at=computation.available_at,
            source_bar_ids=source_ids,
            source_bar_hashes=source_hashes,
            values=computation.values,
            state=state,
            data_eligibility=dataset.data_eligibility,
            formal_pit_status=dataset.formal_pit_status,
            validation_status=definition.validation_status,
            limitations=limitations,
        )
        content_hash = canonical_hash(semantic)
        result = cls(
            schema_version=FEATURE_ARTIFACT_V2_SCHEMA,
            artifact_id=ArtifactId(
                f"feature-artifact-v2-{content_hash.split(':', 1)[1][:24]}"
            ),
            content_hash=content_hash,
            feature_id=definition.feature_id,
            feature_version=definition.feature_version,
            definition=definition,
            model_id=definition.model_id,
            model_version=definition.model_version,
            configuration=configuration,
            dataset_id=dataset.dataset_id,
            dataset_hash=dataset.content_hash,
            symbol=computation.symbol,
            timeframe=computation.timeframe,
            decision_time=dataset.decision_time,
            created_at=created_at,
            available_at=computation.available_at,
            source_bar_ids=source_ids,
            source_bar_hashes=source_hashes,
            values=computation.values,
            state=state,
            data_eligibility=dataset.data_eligibility,
            formal_pit_status=dataset.formal_pit_status,
            validation_status=definition.validation_status,
            limitations=limitations,
        )
        result.verify_identity()
        return result

    def semantic_payload(self) -> dict[str, Any]:
        return _feature_artifact_payload(
            feature_id=self.feature_id,
            feature_version=self.feature_version,
            definition=self.definition,
            model_id=self.model_id,
            model_version=self.model_version,
            configuration=self.configuration,
            dataset_id=self.dataset_id,
            dataset_hash=self.dataset_hash,
            symbol=self.symbol,
            timeframe=self.timeframe,
            decision_time=self.decision_time,
            created_at=self.created_at,
            available_at=self.available_at,
            source_bar_ids=self.source_bar_ids,
            source_bar_hashes=self.source_bar_hashes,
            values=self.values,
            state=self.state,
            data_eligibility=self.data_eligibility,
            formal_pit_status=self.formal_pit_status,
            validation_status=self.validation_status,
            limitations=self.limitations,
        )

    def verify_identity(self) -> None:
        expected_hash = canonical_hash(self.semantic_payload())
        if self.content_hash != expected_hash:
            raise ValueError("Feature Artifact V2 payload hash mismatch")
        expected_id = f"feature-artifact-v2-{expected_hash.split(':', 1)[1][:24]}"
        if str(self.artifact_id) != expected_id:
            raise ValueError("Feature Artifact V2 identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": str(self.artifact_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        definition: FeatureDefinitionV2,
        configuration: FeatureConfiguration,
    ) -> FeatureArtifactV2:
        expected = {
            "schema_version",
            "artifact_id",
            "content_hash",
            "feature_id",
            "feature_version",
            "definition_id",
            "definition_hash",
            "model_id",
            "model_version",
            "configuration_id",
            "configuration_hash",
            "dataset_id",
            "dataset_hash",
            "symbol",
            "timeframe",
            "decision_time",
            "created_at",
            "available_at",
            "source_bars",
            "values",
            "state",
            "data_eligibility",
            "formal_pit_status",
            "validation_status",
            "limitations",
        }
        if set(payload) != expected:
            raise ValueError("Feature Artifact V2 fields mismatch")
        if (
            payload["definition_id"] != str(definition.definition_id)
            or payload["definition_hash"] != definition.definition_hash
            or payload["configuration_id"] != str(configuration.configuration_id)
            or payload["configuration_hash"] != configuration.configuration_hash
        ):
            raise ValueError("Feature Artifact V2 definition/configuration projection mismatch")
        raw_sources = _object_array(payload["source_bars"], "source_bars")
        source_ids: list[ArtifactId] = []
        source_hashes: list[str] = []
        for source in raw_sources:
            if set(source) != {"bar_id", "content_hash"}:
                raise ValueError("Feature Artifact V2 source bar fields mismatch")
            source_ids.append(ArtifactId(str(source["bar_id"])))
            source_hashes.append(str(source["content_hash"]))
        output_types = {item.output_id: item.value_type for item in definition.output_schema}
        raw_values = _object_array(payload["values"], "values")
        values = tuple(
            _feature_value_from_dict(item, output_types=output_types) for item in raw_values
        )
        result = cls(
            schema_version=str(payload["schema_version"]),
            artifact_id=ArtifactId(str(payload["artifact_id"])),
            content_hash=str(payload["content_hash"]),
            feature_id=str(payload["feature_id"]),
            feature_version=str(payload["feature_version"]),
            definition=definition,
            model_id=ModelId(str(payload["model_id"])),
            model_version=str(payload["model_version"]),
            configuration=configuration,
            dataset_id=DatasetId(str(payload["dataset_id"])),
            dataset_hash=str(payload["dataset_hash"]),
            symbol=str(payload["symbol"]),
            timeframe=Timeframe(str(payload["timeframe"])),
            decision_time=parse_utc_second("decision_time", payload["decision_time"]),
            created_at=parse_utc_second("created_at", payload["created_at"]),
            available_at=parse_utc_second("available_at", payload["available_at"]),
            source_bar_ids=tuple(source_ids),
            source_bar_hashes=tuple(source_hashes),
            values=values,
            state=FeatureArtifactState(str(payload["state"])),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
            formal_pit_status=FormalPitStatus(str(payload["formal_pit_status"])),
            validation_status=FeatureValidationStatus(str(payload["validation_status"])),
            limitations=_string_tuple(payload["limitations"], "limitations"),
        )
        result.verify_identity()
        return result


@dataclass(frozen=True, slots=True)
class FeatureArtifactReferenceV2:
    artifact_id: ArtifactId
    content_hash: str
    feature_id: str
    symbol: str
    timeframe: Timeframe
    state: FeatureArtifactState
    available_at: datetime
    locator: str

    def __post_init__(self) -> None:
        require_sha256("content_hash", self.content_hash)
        require_text("feature_id", self.feature_id)
        require_text("symbol", self.symbol)
        require_utc_second("available_at", self.available_at)
        require_text("locator", self.locator)
        if self.locator != f"feature-artifacts/{self.artifact_id}":
            raise ValueError("Feature Artifact locator is not canonical")

    @classmethod
    def from_artifact(cls, artifact: FeatureArtifactV2) -> FeatureArtifactReferenceV2:
        artifact.verify_identity()
        return cls(
            artifact_id=artifact.artifact_id,
            content_hash=artifact.content_hash,
            feature_id=artifact.feature_id,
            symbol=artifact.symbol,
            timeframe=artifact.timeframe,
            state=artifact.state,
            available_at=artifact.available_at,
            locator=f"feature-artifacts/{artifact.artifact_id}",
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": str(self.artifact_id),
            "content_hash": self.content_hash,
            "feature_id": self.feature_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "state": self.state.value,
            "available_at": canonical_datetime(self.available_at),
            "locator": self.locator,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> FeatureArtifactReferenceV2:
        expected = {
            "artifact_id",
            "content_hash",
            "feature_id",
            "symbol",
            "timeframe",
            "state",
            "available_at",
            "locator",
        }
        if set(payload) != expected:
            raise ValueError("Feature Artifact Reference V2 fields mismatch")
        return cls(
            artifact_id=ArtifactId(str(payload["artifact_id"])),
            content_hash=str(payload["content_hash"]),
            feature_id=str(payload["feature_id"]),
            symbol=str(payload["symbol"]),
            timeframe=Timeframe(str(payload["timeframe"])),
            state=FeatureArtifactState(str(payload["state"])),
            available_at=parse_utc_second("available_at", payload["available_at"]),
            locator=str(payload["locator"]),
        )


@dataclass(frozen=True, slots=True)
class FeatureBundleCoverage:
    artifact_count: int
    available_value_count: int
    missing_value_count: int
    missing_reason_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        for label, value in (
            ("artifact_count", self.artifact_count),
            ("available_value_count", self.available_value_count),
            ("missing_value_count", self.missing_value_count),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{label} must be a non-negative integer")
        keys = tuple(item[0] for item in self.missing_reason_counts)
        if keys != tuple(sorted(set(keys))) or any(
            count <= 0 for _, count in self.missing_reason_counts
        ):
            raise ValueError("missing reason counts must be positive, unique, and sorted")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "artifact_count": self.artifact_count,
            "available_value_count": self.available_value_count,
            "missing_value_count": self.missing_value_count,
            "missing_reason_counts": [
                {"reason_code": reason, "count": count}
                for reason, count in self.missing_reason_counts
            ],
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> FeatureBundleCoverage:
        expected = {
            "artifact_count",
            "available_value_count",
            "missing_value_count",
            "missing_reason_counts",
        }
        if set(payload) != expected:
            raise ValueError("Feature Bundle Coverage fields mismatch")
        raw_reasons = _object_array(payload["missing_reason_counts"], "missing_reason_counts")
        return cls(
            artifact_count=_non_negative_int(payload["artifact_count"], "artifact_count"),
            available_value_count=_non_negative_int(
                payload["available_value_count"], "available_value_count"
            ),
            missing_value_count=_non_negative_int(
                payload["missing_value_count"], "missing_value_count"
            ),
            missing_reason_counts=tuple(
                (
                    str(item["reason_code"]),
                    _positive_int(item["count"], "missing reason count"),
                )
                for item in raw_reasons
                if set(item) == {"reason_code", "count"}
            ),
        )


@dataclass(frozen=True, slots=True)
class FeatureBundleArtifact:
    schema_version: str
    bundle_id: ArtifactId
    content_hash: str
    dataset_id: DatasetId
    dataset_hash: str
    adjustment_mode: AdjustmentMode
    adjustment_policy_id: ArtifactId
    adjustment_policy_hash: str
    source_manifest_references: tuple[tuple[ArtifactId, str], ...]
    feature_set: FeatureSetConfiguration
    decision_time: datetime
    created_at: datetime
    code_revision: str
    symbols: tuple[str, ...]
    timeframes: tuple[Timeframe, ...]
    feature_artifact_references: tuple[FeatureArtifactReferenceV2, ...]
    coverage: FeatureBundleCoverage
    required_feature_status: str
    state: FeatureBundleState
    data_eligibility: DataEligibility
    formal_pit_status: FormalPitStatus
    limitations: tuple[str, ...]

    @property
    def feature_set_id(self) -> ArtifactId:
        return self.feature_set.feature_set_id

    @property
    def feature_set_hash(self) -> str:
        return self.feature_set.content_hash

    @property
    def available_at(self) -> datetime:
        """Latest bound Feature evidence availability, not publication time."""

        return max(item.available_at for item in self.feature_artifact_references)

    def __post_init__(self) -> None:
        if self.schema_version != FEATURE_BUNDLE_V1_SCHEMA:
            raise ValueError("unsupported Feature Bundle schema")
        require_sha256("content_hash", self.content_hash)
        require_sha256("dataset_hash", self.dataset_hash)
        require_sha256("adjustment_policy_hash", self.adjustment_policy_hash)
        source_references = tuple(
            (str(item_id), item_hash)
            for item_id, item_hash in self.source_manifest_references
        )
        if not source_references or source_references != tuple(
            sorted(set(source_references))
        ):
            raise ValueError(
                "Feature Bundle source manifest references must be non-empty and sorted"
            )
        for _, item_hash in self.source_manifest_references:
            require_sha256("source_manifest_hash", item_hash)
        self.feature_set.verify_identity()
        require_utc_second("decision_time", self.decision_time)
        require_utc_second("created_at", self.created_at)
        if self.created_at < self.decision_time:
            raise ValueError("Feature Bundle created_at cannot precede DecisionTime")
        require_text("code_revision", self.code_revision)
        require_unique_text("symbol", self.symbols)
        if not self.symbols or self.symbols != tuple(sorted(self.symbols)):
            raise ValueError("Feature Bundle symbols must be non-empty and sorted")
        if not self.timeframes or self.timeframes != tuple(
            sorted(set(self.timeframes), key=lambda item: item.value)
        ):
            raise ValueError("Feature Bundle timeframes must be non-empty and sorted")
        reference_keys = tuple(
            (item.feature_id, item.symbol, item.timeframe.value)
            for item in self.feature_artifact_references
        )
        if not reference_keys or reference_keys != tuple(sorted(set(reference_keys))):
            raise ValueError("Feature Bundle references must be non-empty, unique, and sorted")
        if self.coverage.artifact_count != len(self.feature_artifact_references):
            raise ValueError("Feature Bundle coverage artifact count mismatch")
        if self.required_feature_status not in {"BLOCKED", "COMPLETE"}:
            raise ValueError("Feature Bundle required feature status is invalid")
        if (
            self.state is FeatureBundleState.BLOCKED_REQUIRED_FEATURE
        ) != (self.required_feature_status == "BLOCKED"):
            raise ValueError("Feature Bundle required status and state mismatch")
        require_unique_text("limitation", self.limitations)
        if self.limitations != tuple(sorted(self.limitations)):
            raise ValueError("Feature Bundle limitations must be sorted")
        if "TRADING_AUTHORITY_NOT_GRANTED" not in self.limitations:
            raise ValueError("Feature Bundle must preserve trading authority ceiling")

    @classmethod
    def create(
        cls,
        *,
        dataset: MarketDataDatasetArtifact,
        feature_set: FeatureSetConfiguration,
        artifacts: tuple[FeatureArtifactV2, ...],
        selected_symbols: tuple[str, ...],
        created_at: datetime,
        code_revision: str,
    ) -> FeatureBundleArtifact:
        dataset.verify_identity()
        feature_set.verify_identity()
        selected_symbols = tuple(sorted(selected_symbols))
        ordered_artifacts = tuple(
            sorted(
                artifacts,
                key=lambda item: (item.feature_id, item.symbol, item.timeframe.value),
            )
        )
        expected = {
            (definition.feature_id, symbol)
            for definition in feature_set.definitions
            for symbol in selected_symbols
        }
        actual = {(item.feature_id, item.symbol) for item in ordered_artifacts}
        if actual != expected or len(ordered_artifacts) != len(expected):
            raise ValueError("Feature Bundle artifacts do not cover Feature Set and symbols")
        _verify_feature_set_artifact_bindings(
            feature_set=feature_set,
            artifacts=ordered_artifacts,
        )
        if any(
            item.dataset_id != dataset.dataset_id
            or item.dataset_hash != dataset.content_hash
            or item.decision_time != dataset.decision_time
            for item in ordered_artifacts
        ):
            raise ValueError("Feature Bundle artifact dataset scope mismatch")
        (
            references,
            coverage,
            required_status,
            state,
        ) = _derive_bundle_projection(
            feature_set=feature_set,
            artifacts=ordered_artifacts,
            selected_symbols=selected_symbols,
        )
        limitations = tuple(
            sorted(
                {
                    *dataset.limitations,
                    *feature_set.limitations,
                    *(limitation for item in ordered_artifacts for limitation in item.limitations),
                    "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
                    "TRADING_AUTHORITY_NOT_GRANTED",
                }
            )
        )
        semantic = _feature_bundle_payload(
            dataset_id=dataset.dataset_id,
            dataset_hash=dataset.content_hash,
            adjustment_mode=dataset.adjustment_policy.mode,
            adjustment_policy_id=dataset.adjustment_policy.policy_id,
            adjustment_policy_hash=dataset.adjustment_policy.policy_hash,
            source_manifest_references=dataset.source_manifest_references,
            feature_set=feature_set,
            decision_time=dataset.decision_time,
            created_at=created_at,
            code_revision=code_revision,
            symbols=selected_symbols,
            timeframes=tuple(
                sorted({item.timeframe for item in ordered_artifacts}, key=lambda item: item.value)
            ),
            references=references,
            coverage=coverage,
            required_feature_status=required_status,
            state=state,
            data_eligibility=dataset.data_eligibility,
            formal_pit_status=dataset.formal_pit_status,
            limitations=limitations,
        )
        content_hash = canonical_hash(semantic)
        result = cls(
            schema_version=FEATURE_BUNDLE_V1_SCHEMA,
            bundle_id=ArtifactId(f"feature-bundle-{content_hash.split(':', 1)[1][:24]}"),
            content_hash=content_hash,
            dataset_id=dataset.dataset_id,
            dataset_hash=dataset.content_hash,
            adjustment_mode=dataset.adjustment_policy.mode,
            adjustment_policy_id=dataset.adjustment_policy.policy_id,
            adjustment_policy_hash=dataset.adjustment_policy.policy_hash,
            source_manifest_references=dataset.source_manifest_references,
            feature_set=feature_set,
            decision_time=dataset.decision_time,
            created_at=created_at,
            code_revision=code_revision,
            symbols=selected_symbols,
            timeframes=tuple(
                sorted({item.timeframe for item in ordered_artifacts}, key=lambda item: item.value)
            ),
            feature_artifact_references=references,
            coverage=coverage,
            required_feature_status=required_status,
            state=state,
            data_eligibility=dataset.data_eligibility,
            formal_pit_status=dataset.formal_pit_status,
            limitations=limitations,
        )
        result.verify_identity()
        return result

    def semantic_payload(self) -> dict[str, Any]:
        return _feature_bundle_payload(
            dataset_id=self.dataset_id,
            dataset_hash=self.dataset_hash,
            adjustment_mode=self.adjustment_mode,
            adjustment_policy_id=self.adjustment_policy_id,
            adjustment_policy_hash=self.adjustment_policy_hash,
            source_manifest_references=self.source_manifest_references,
            feature_set=self.feature_set,
            decision_time=self.decision_time,
            created_at=self.created_at,
            code_revision=self.code_revision,
            symbols=self.symbols,
            timeframes=self.timeframes,
            references=self.feature_artifact_references,
            coverage=self.coverage,
            required_feature_status=self.required_feature_status,
            state=self.state,
            data_eligibility=self.data_eligibility,
            formal_pit_status=self.formal_pit_status,
            limitations=self.limitations,
        )

    def verify_identity(self) -> None:
        expected_hash = canonical_hash(self.semantic_payload())
        if self.content_hash != expected_hash:
            raise ValueError("Feature Bundle payload hash mismatch")
        expected_id = f"feature-bundle-{expected_hash.split(':', 1)[1][:24]}"
        if str(self.bundle_id) != expected_id:
            raise ValueError("Feature Bundle identity mismatch")

    def verify_materialized_projection(
        self, artifacts: tuple[FeatureArtifactV2, ...]
    ) -> None:
        ordered = tuple(
            sorted(
                artifacts,
                key=lambda item: (item.feature_id, item.symbol, item.timeframe.value),
            )
        )
        expected_scope = {
            (definition.feature_id, symbol)
            for definition in self.feature_set.definitions
            for symbol in self.symbols
        }
        actual_scope = {(item.feature_id, item.symbol) for item in ordered}
        if actual_scope != expected_scope or len(ordered) != len(expected_scope):
            raise ValueError("Feature Bundle materialized scope mismatch")
        _verify_feature_set_artifact_bindings(
            feature_set=self.feature_set,
            artifacts=ordered,
        )
        for item in ordered:
            item.verify_identity()
            if (
                item.dataset_id != self.dataset_id
                or item.dataset_hash != self.dataset_hash
                or item.decision_time != self.decision_time
            ):
                raise ValueError("Feature Bundle artifact dataset scope mismatch")
        references, coverage, required_status, state = _derive_bundle_projection(
            feature_set=self.feature_set,
            artifacts=ordered,
            selected_symbols=self.symbols,
        )
        if (
            references != self.feature_artifact_references
            or coverage != self.coverage
            or required_status != self.required_feature_status
            or state is not self.state
            or tuple(
                sorted({item.timeframe for item in ordered}, key=lambda item: item.value)
            )
            != self.timeframes
        ):
            raise ValueError("Feature Bundle materialized projection mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": str(self.bundle_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        feature_set: FeatureSetConfiguration,
    ) -> FeatureBundleArtifact:
        expected = {
            "schema_version",
            "bundle_id",
            "content_hash",
            "dataset_id",
            "dataset_hash",
            "adjustment_mode",
            "adjustment_policy_id",
            "adjustment_policy_hash",
            "source_manifest_references",
            "feature_set_id",
            "feature_set_hash",
            "decision_time",
            "created_at",
            "code_revision",
            "symbols",
            "timeframes",
            "feature_artifact_references",
            "coverage",
            "required_feature_status",
            "state",
            "data_eligibility",
            "formal_pit_status",
            "limitations",
        }
        if set(payload) != expected:
            raise ValueError("Feature Bundle fields mismatch")
        if (
            payload["feature_set_id"] != str(feature_set.feature_set_id)
            or payload["feature_set_hash"] != feature_set.content_hash
        ):
            raise ValueError("Feature Bundle Feature Set projection mismatch")
        raw_references = _object_array(
            payload["feature_artifact_references"], "feature_artifact_references"
        )
        raw_coverage = payload["coverage"]
        if not isinstance(raw_coverage, dict):
            raise ValueError("Feature Bundle coverage must be an object")
        result = cls(
            schema_version=str(payload["schema_version"]),
            bundle_id=ArtifactId(str(payload["bundle_id"])),
            content_hash=str(payload["content_hash"]),
            dataset_id=DatasetId(str(payload["dataset_id"])),
            dataset_hash=str(payload["dataset_hash"]),
            adjustment_mode=AdjustmentMode(str(payload["adjustment_mode"])),
            adjustment_policy_id=ArtifactId(str(payload["adjustment_policy_id"])),
            adjustment_policy_hash=str(payload["adjustment_policy_hash"]),
            source_manifest_references=_artifact_hash_references(
                payload["source_manifest_references"],
                "source_manifest_references",
            ),
            feature_set=feature_set,
            decision_time=parse_utc_second("decision_time", payload["decision_time"]),
            created_at=parse_utc_second("created_at", payload["created_at"]),
            code_revision=str(payload["code_revision"]),
            symbols=_string_tuple(payload["symbols"], "symbols"),
            timeframes=tuple(
                Timeframe(item)
                for item in _string_tuple(payload["timeframes"], "timeframes")
            ),
            feature_artifact_references=tuple(
                FeatureArtifactReferenceV2.from_canonical_dict(item)
                for item in raw_references
            ),
            coverage=FeatureBundleCoverage.from_canonical_dict(raw_coverage),
            required_feature_status=str(payload["required_feature_status"]),
            state=FeatureBundleState(str(payload["state"])),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
            formal_pit_status=FormalPitStatus(str(payload["formal_pit_status"])),
            limitations=_string_tuple(payload["limitations"], "limitations"),
        )
        result.verify_identity()
        return result


@dataclass(frozen=True, slots=True)
class FeatureMaterializationReceipt:
    schema_version: str
    receipt_id: ArtifactId
    content_hash: str
    command_hash: str
    status: FeatureMaterializationStatus
    dataset_id: DatasetId
    dataset_hash: str
    feature_set_id: ArtifactId
    feature_set_hash: str
    bundle_id: ArtifactId
    bundle_hash: str
    bundle_locator: str
    artifact_count: int
    available_value_count: int
    missing_value_count: int
    limitations: tuple[str, ...]
    no_order_created: bool = True
    broker_not_invoked: bool = True
    no_fill_created: bool = True
    trading_authority: str = "TRADING_AUTHORITY_NOT_GRANTED"

    def __post_init__(self) -> None:
        if self.schema_version != FEATURE_MATERIALIZATION_RECEIPT_SCHEMA:
            raise ValueError("unsupported Feature Materialization Receipt schema")
        for label, hash_value in (
            ("content_hash", self.content_hash),
            ("command_hash", self.command_hash),
            ("dataset_hash", self.dataset_hash),
            ("feature_set_hash", self.feature_set_hash),
            ("bundle_hash", self.bundle_hash),
        ):
            require_sha256(label, hash_value)
        require_text("bundle_locator", self.bundle_locator)
        if self.bundle_locator != f"feature-bundles/{self.bundle_id}":
            raise ValueError("Feature Materialization bundle locator mismatch")
        for label, count_value in (
            ("artifact_count", self.artifact_count),
            ("available_value_count", self.available_value_count),
            ("missing_value_count", self.missing_value_count),
        ):
            _non_negative_int(count_value, label)
        require_unique_text("limitation", self.limitations)
        if self.limitations != tuple(sorted(self.limitations)):
            raise ValueError("Feature Materialization limitations must be sorted")
        if not (self.no_order_created and self.broker_not_invoked and self.no_fill_created):
            raise ValueError("Feature Materialization cannot create execution effects")
        if self.trading_authority != "TRADING_AUTHORITY_NOT_GRANTED":
            raise ValueError("Feature Materialization cannot receive trading authority")

    @classmethod
    def create(
        cls,
        *,
        command_hash: str,
        bundle: FeatureBundleArtifact,
    ) -> FeatureMaterializationReceipt:
        status = (
            FeatureMaterializationStatus.COMPLETE
            if bundle.state is FeatureBundleState.COMPLETE
            else FeatureMaterializationStatus.BLOCKED_REQUIRED_FEATURE
            if bundle.state is FeatureBundleState.BLOCKED_REQUIRED_FEATURE
            else FeatureMaterializationStatus.PARTIAL_COVERAGE
        )
        semantic = _receipt_payload(
            command_hash=command_hash,
            status=status,
            bundle=bundle,
            limitations=bundle.limitations,
        )
        content_hash = canonical_hash(semantic)
        result = cls(
            schema_version=FEATURE_MATERIALIZATION_RECEIPT_SCHEMA,
            receipt_id=ArtifactId(
                f"feature-materialization-receipt-{content_hash.split(':', 1)[1][:24]}"
            ),
            content_hash=content_hash,
            command_hash=command_hash,
            status=status,
            dataset_id=bundle.dataset_id,
            dataset_hash=bundle.dataset_hash,
            feature_set_id=bundle.feature_set_id,
            feature_set_hash=bundle.feature_set_hash,
            bundle_id=bundle.bundle_id,
            bundle_hash=bundle.content_hash,
            bundle_locator=f"feature-bundles/{bundle.bundle_id}",
            artifact_count=bundle.coverage.artifact_count,
            available_value_count=bundle.coverage.available_value_count,
            missing_value_count=bundle.coverage.missing_value_count,
            limitations=bundle.limitations,
        )
        result.verify_identity()
        return result

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "command_hash": self.command_hash,
            "status": self.status.value,
            "dataset_id": str(self.dataset_id),
            "dataset_hash": self.dataset_hash,
            "feature_set_id": str(self.feature_set_id),
            "feature_set_hash": self.feature_set_hash,
            "bundle_id": str(self.bundle_id),
            "bundle_hash": self.bundle_hash,
            "bundle_locator": self.bundle_locator,
            "artifact_count": self.artifact_count,
            "available_value_count": self.available_value_count,
            "missing_value_count": self.missing_value_count,
            "limitations": list(self.limitations),
            "no_order_created": self.no_order_created,
            "broker_not_invoked": self.broker_not_invoked,
            "no_fill_created": self.no_fill_created,
            "trading_authority": self.trading_authority,
        }

    def verify_identity(self) -> None:
        expected_hash = canonical_hash(self.semantic_payload())
        if self.content_hash != expected_hash:
            raise ValueError("Feature Materialization Receipt payload hash mismatch")
        expected_id = (
            f"feature-materialization-receipt-{expected_hash.split(':', 1)[1][:24]}"
        )
        if str(self.receipt_id) != expected_id:
            raise ValueError("Feature Materialization Receipt identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": str(self.receipt_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> FeatureMaterializationReceipt:
        expected = {
            "schema_version",
            "receipt_id",
            "content_hash",
            "command_hash",
            "status",
            "dataset_id",
            "dataset_hash",
            "feature_set_id",
            "feature_set_hash",
            "bundle_id",
            "bundle_hash",
            "bundle_locator",
            "artifact_count",
            "available_value_count",
            "missing_value_count",
            "limitations",
            "no_order_created",
            "broker_not_invoked",
            "no_fill_created",
            "trading_authority",
        }
        if set(payload) != expected:
            raise ValueError("Feature Materialization Receipt fields mismatch")
        result = cls(
            schema_version=str(payload["schema_version"]),
            receipt_id=ArtifactId(str(payload["receipt_id"])),
            content_hash=str(payload["content_hash"]),
            command_hash=str(payload["command_hash"]),
            status=FeatureMaterializationStatus(str(payload["status"])),
            dataset_id=DatasetId(str(payload["dataset_id"])),
            dataset_hash=str(payload["dataset_hash"]),
            feature_set_id=ArtifactId(str(payload["feature_set_id"])),
            feature_set_hash=str(payload["feature_set_hash"]),
            bundle_id=ArtifactId(str(payload["bundle_id"])),
            bundle_hash=str(payload["bundle_hash"]),
            bundle_locator=str(payload["bundle_locator"]),
            artifact_count=_non_negative_int(payload["artifact_count"], "artifact_count"),
            available_value_count=_non_negative_int(
                payload["available_value_count"], "available_value_count"
            ),
            missing_value_count=_non_negative_int(
                payload["missing_value_count"], "missing_value_count"
            ),
            limitations=_string_tuple(payload["limitations"], "limitations"),
            no_order_created=_boolean(payload["no_order_created"], "no_order_created"),
            broker_not_invoked=_boolean(payload["broker_not_invoked"], "broker_not_invoked"),
            no_fill_created=_boolean(payload["no_fill_created"], "no_fill_created"),
            trading_authority=str(payload["trading_authority"]),
        )
        result.verify_identity()
        return result


@dataclass(frozen=True, slots=True)
class FeatureBundleReplayReport:
    schema_version: str
    report_id: ArtifactId
    content_hash: str
    original_bundle_hash: str
    replayed_bundle_hash: str
    original_artifact_hashes: tuple[str, ...]
    replayed_artifact_hashes: tuple[str, ...]
    semantic_match: bool
    limitations: tuple[str, ...]

    @classmethod
    def create(
        cls,
        *,
        original_bundle_hash: str,
        replayed_bundle_hash: str,
        original_artifact_hashes: tuple[str, ...],
        replayed_artifact_hashes: tuple[str, ...],
    ) -> FeatureBundleReplayReport:
        semantic_match = (
            original_bundle_hash == replayed_bundle_hash
            and original_artifact_hashes == replayed_artifact_hashes
        )
        limitations = (
            "NO_EXECUTION_SIDE_EFFECTS",
            "REPLAY_DOES_NOT_PROMOTE_MODEL_OR_DATA_AUTHORITY",
            "TRADING_AUTHORITY_NOT_GRANTED",
        )
        semantic = {
            "schema_version": FEATURE_REPLAY_REPORT_SCHEMA,
            "original_bundle_hash": original_bundle_hash,
            "replayed_bundle_hash": replayed_bundle_hash,
            "original_artifact_hashes": list(original_artifact_hashes),
            "replayed_artifact_hashes": list(replayed_artifact_hashes),
            "semantic_match": semantic_match,
            "limitations": list(limitations),
        }
        content_hash = canonical_hash(semantic)
        return cls(
            schema_version=FEATURE_REPLAY_REPORT_SCHEMA,
            report_id=ArtifactId(
                f"feature-replay-report-{content_hash.split(':', 1)[1][:24]}"
            ),
            content_hash=content_hash,
            original_bundle_hash=original_bundle_hash,
            replayed_bundle_hash=replayed_bundle_hash,
            original_artifact_hashes=original_artifact_hashes,
            replayed_artifact_hashes=replayed_artifact_hashes,
            semantic_match=semantic_match,
            limitations=limitations,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "original_bundle_hash": self.original_bundle_hash,
            "replayed_bundle_hash": self.replayed_bundle_hash,
            "original_artifact_hashes": list(self.original_artifact_hashes),
            "replayed_artifact_hashes": list(self.replayed_artifact_hashes),
            "semantic_match": self.semantic_match,
            "limitations": list(self.limitations),
        }

    def verify_identity(self) -> None:
        for label, value in (
            ("content_hash", self.content_hash),
            ("original_bundle_hash", self.original_bundle_hash),
            ("replayed_bundle_hash", self.replayed_bundle_hash),
            *(
                ("original_artifact_hash", item)
                for item in self.original_artifact_hashes
            ),
            *(
                ("replayed_artifact_hash", item)
                for item in self.replayed_artifact_hashes
            ),
        ):
            require_sha256(label, value)
        if len(self.original_artifact_hashes) != len(
            self.replayed_artifact_hashes
        ):
            raise ValueError("Feature replay artifact hashes must align")
        expected_match = (
            self.original_bundle_hash == self.replayed_bundle_hash
            and self.original_artifact_hashes == self.replayed_artifact_hashes
        )
        if self.semantic_match is not expected_match:
            raise ValueError("Feature replay semantic match projection mismatch")
        require_unique_text("limitation", self.limitations)
        if self.limitations != tuple(sorted(self.limitations)):
            raise ValueError("Feature replay limitations must be sorted")
        expected_hash = canonical_hash(self.semantic_payload())
        if self.content_hash != expected_hash:
            raise ValueError("Feature replay report hash mismatch")
        expected_id = f"feature-replay-report-{expected_hash.split(':', 1)[1][:24]}"
        if str(self.report_id) != expected_id:
            raise ValueError("Feature replay report identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        self.verify_identity()
        return {
            "report_id": str(self.report_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> FeatureBundleReplayReport:
        if set(payload) != {
            "schema_version",
            "report_id",
            "content_hash",
            "original_bundle_hash",
            "replayed_bundle_hash",
            "original_artifact_hashes",
            "replayed_artifact_hashes",
            "semantic_match",
            "limitations",
        } or payload["schema_version"] != FEATURE_REPLAY_REPORT_SCHEMA:
            raise ValueError("Feature replay report fields mismatch")
        semantic_match = payload["semantic_match"]
        if not isinstance(semantic_match, bool):
            raise TypeError("Feature replay semantic_match must be boolean")
        result = cls(
            schema_version=str(payload["schema_version"]),
            report_id=ArtifactId(str(payload["report_id"])),
            content_hash=str(payload["content_hash"]),
            original_bundle_hash=str(payload["original_bundle_hash"]),
            replayed_bundle_hash=str(payload["replayed_bundle_hash"]),
            original_artifact_hashes=_string_tuple(
                payload["original_artifact_hashes"], "original_artifact_hashes"
            ),
            replayed_artifact_hashes=_string_tuple(
                payload["replayed_artifact_hashes"], "replayed_artifact_hashes"
            ),
            semantic_match=semantic_match,
            limitations=_string_tuple(payload["limitations"], "limitations"),
        )
        result.verify_identity()
        return result


def _feature_artifact_payload(
    *,
    feature_id: str,
    feature_version: str,
    definition: FeatureDefinitionV2,
    model_id: ModelId,
    model_version: str,
    configuration: FeatureConfiguration,
    dataset_id: DatasetId,
    dataset_hash: str,
    symbol: str,
    timeframe: Timeframe,
    decision_time: datetime,
    created_at: datetime,
    available_at: datetime,
    source_bar_ids: tuple[ArtifactId, ...],
    source_bar_hashes: tuple[str, ...],
    values: tuple[TechnicalFeatureValue, ...],
    state: FeatureArtifactState,
    data_eligibility: DataEligibility,
    formal_pit_status: FormalPitStatus,
    validation_status: FeatureValidationStatus,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    output_types = {item.output_id: item.value_type for item in definition.output_schema}
    return {
        "schema_version": FEATURE_ARTIFACT_V2_SCHEMA,
        "feature_id": feature_id,
        "feature_version": feature_version,
        "definition_id": str(definition.definition_id),
        "definition_hash": definition.definition_hash,
        "model_id": str(model_id),
        "model_version": model_version,
        "configuration_id": str(configuration.configuration_id),
        "configuration_hash": configuration.configuration_hash,
        "dataset_id": str(dataset_id),
        "dataset_hash": dataset_hash,
        "symbol": symbol,
        "timeframe": timeframe.value,
        "decision_time": canonical_datetime(decision_time),
        "created_at": canonical_datetime(created_at),
        "available_at": canonical_datetime(available_at),
        "source_bars": [
            {"bar_id": str(item_id), "content_hash": item_hash}
            for item_id, item_hash in zip(source_bar_ids, source_bar_hashes, strict=True)
        ],
        "values": [
            _feature_value_to_dict(item, value_type=output_types[item.output_id])
            for item in values
        ],
        "state": state.value,
        "data_eligibility": data_eligibility.value,
        "formal_pit_status": formal_pit_status.value,
        "validation_status": validation_status.value,
        "limitations": list(limitations),
    }


def _feature_bundle_payload(
    *,
    dataset_id: DatasetId,
    dataset_hash: str,
    adjustment_mode: AdjustmentMode,
    adjustment_policy_id: ArtifactId,
    adjustment_policy_hash: str,
    source_manifest_references: tuple[tuple[ArtifactId, str], ...],
    feature_set: FeatureSetConfiguration,
    decision_time: datetime,
    created_at: datetime,
    code_revision: str,
    symbols: tuple[str, ...],
    timeframes: tuple[Timeframe, ...],
    references: tuple[FeatureArtifactReferenceV2, ...],
    coverage: FeatureBundleCoverage,
    required_feature_status: str,
    state: FeatureBundleState,
    data_eligibility: DataEligibility,
    formal_pit_status: FormalPitStatus,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": FEATURE_BUNDLE_V1_SCHEMA,
        "dataset_id": str(dataset_id),
        "dataset_hash": dataset_hash,
        "adjustment_mode": adjustment_mode.value,
        "adjustment_policy_id": str(adjustment_policy_id),
        "adjustment_policy_hash": adjustment_policy_hash,
        "source_manifest_references": [
            {"artifact_id": str(item_id), "content_hash": item_hash}
            for item_id, item_hash in source_manifest_references
        ],
        "feature_set_id": str(feature_set.feature_set_id),
        "feature_set_hash": feature_set.content_hash,
        "decision_time": canonical_datetime(decision_time),
        "created_at": canonical_datetime(created_at),
        "code_revision": code_revision,
        "symbols": list(symbols),
        "timeframes": [item.value for item in timeframes],
        "feature_artifact_references": [item.to_canonical_dict() for item in references],
        "coverage": coverage.to_canonical_dict(),
        "required_feature_status": required_feature_status,
        "state": state.value,
        "data_eligibility": data_eligibility.value,
        "formal_pit_status": formal_pit_status.value,
        "limitations": list(limitations),
    }


def _derive_bundle_projection(
    *,
    feature_set: FeatureSetConfiguration,
    artifacts: tuple[FeatureArtifactV2, ...],
    selected_symbols: tuple[str, ...],
) -> tuple[
    tuple[FeatureArtifactReferenceV2, ...],
    FeatureBundleCoverage,
    str,
    FeatureBundleState,
]:
    references = tuple(FeatureArtifactReferenceV2.from_artifact(item) for item in artifacts)
    available_count = sum(
        value.state is FeatureValueState.AVAILABLE
        for item in artifacts
        for value in item.values
    )
    missing_values = tuple(
        value
        for item in artifacts
        for value in item.values
        if value.state is FeatureValueState.MISSING
    )
    reason_counts: dict[str, int] = {}
    for value in missing_values:
        for reason in value.missing_reason_codes:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    coverage = FeatureBundleCoverage(
        artifact_count=len(artifacts),
        available_value_count=available_count,
        missing_value_count=len(missing_values),
        missing_reason_counts=tuple(sorted(reason_counts.items())),
    )
    required_pairs = {
        (feature_id, symbol)
        for feature_id in feature_set.required_feature_ids
        for symbol in selected_symbols
    }
    required_artifacts = tuple(
        item
        for item in artifacts
        if (item.feature_id, item.symbol) in required_pairs
    )
    # Coverage policy is deliberately defined at Feature Family granularity. A
    # PARTIAL_COVERAGE Artifact proves that the required family ran and emitted
    # at least one observable; missing optional outputs keep the Bundle partial
    # but do not erase the whole family's usable evidence.
    covered_count = sum(
        item.state is not FeatureArtifactState.DATA_INSUFFICIENT
        for item in required_artifacts
    )
    if feature_set.coverage_policy is RequiredFeatureCoveragePolicy.BLOCK_ON_ANY_REQUIRED_MISSING:
        blocked = covered_count != len(required_artifacts)
    else:
        coverage_ratio = (
            Decimal("1")
            if not required_artifacts
            else Decimal(covered_count) / Decimal(len(required_artifacts))
        )
        blocked = coverage_ratio < feature_set.minimum_required_coverage
    required_status = "BLOCKED" if blocked else "COMPLETE"
    state = (
        FeatureBundleState.BLOCKED_REQUIRED_FEATURE
        if blocked
        else FeatureBundleState.PARTIAL_COVERAGE
        if missing_values
        else FeatureBundleState.COMPLETE
    )
    return references, coverage, required_status, state


def _verify_feature_set_artifact_bindings(
    *,
    feature_set: FeatureSetConfiguration,
    artifacts: tuple[FeatureArtifactV2, ...],
) -> None:
    definitions = {item.feature_id: item for item in feature_set.definitions}
    configurations = {
        item.feature_id: item for item in feature_set.configurations
    }
    for artifact in artifacts:
        if artifact.definition != definitions.get(artifact.feature_id):
            raise ValueError("Feature Bundle Artifact definition binding mismatch")
        if artifact.configuration != configurations.get(artifact.feature_id):
            raise ValueError("Feature Bundle Artifact configuration binding mismatch")


def _receipt_payload(
    *,
    command_hash: str,
    status: FeatureMaterializationStatus,
    bundle: FeatureBundleArtifact,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": FEATURE_MATERIALIZATION_RECEIPT_SCHEMA,
        "command_hash": command_hash,
        "status": status.value,
        "dataset_id": str(bundle.dataset_id),
        "dataset_hash": bundle.dataset_hash,
        "feature_set_id": str(bundle.feature_set_id),
        "feature_set_hash": bundle.feature_set_hash,
        "bundle_id": str(bundle.bundle_id),
        "bundle_hash": bundle.content_hash,
        "bundle_locator": f"feature-bundles/{bundle.bundle_id}",
        "artifact_count": bundle.coverage.artifact_count,
        "available_value_count": bundle.coverage.available_value_count,
        "missing_value_count": bundle.coverage.missing_value_count,
        "limitations": list(limitations),
        "no_order_created": True,
        "broker_not_invoked": True,
        "no_fill_created": True,
        "trading_authority": "TRADING_AUTHORITY_NOT_GRANTED",
    }


def _feature_value_to_dict(
    value: TechnicalFeatureValue, *, value_type: ValueType
) -> dict[str, Any]:
    encoded: str | int | None
    if value.value is None:
        encoded = None
    elif value_type is ValueType.DECIMAL:
        assert isinstance(value.value, Decimal)
        encoded = _canonical_decimal(value.value)
    elif value_type is ValueType.INTEGER:
        assert isinstance(value.value, int) and not isinstance(value.value, bool)
        encoded = value.value
    else:
        assert isinstance(value.value, str)
        encoded = value.value
    return {
        "output_id": value.output_id,
        "value_type": value_type.value,
        "state": value.state.value,
        "value": encoded,
        "available_at": canonical_datetime(value.available_at),
        "source_bars": [
            {"bar_id": str(item_id), "content_hash": item_hash}
            for item_id, item_hash in zip(
                value.source_bar_ids, value.source_bar_hashes, strict=True
            )
        ],
        "missing_reason_codes": list(value.missing_reason_codes),
    }


def _feature_value_from_dict(
    payload: Mapping[str, Any], *, output_types: Mapping[str, ValueType]
) -> TechnicalFeatureValue:
    expected = {
        "output_id",
        "value_type",
        "state",
        "value",
        "available_at",
        "source_bars",
        "missing_reason_codes",
    }
    if set(payload) != expected:
        raise ValueError("Feature value fields mismatch")
    output_id = str(payload["output_id"])
    try:
        value_type = output_types[output_id]
    except KeyError as exc:
        raise ValueError("Feature value output is not in definition") from exc
    if payload["value_type"] != value_type.value:
        raise ValueError("Feature value type projection mismatch")
    raw_value = payload["value"]
    value: FeatureScalar | None
    if raw_value is None:
        value = None
    elif value_type is ValueType.DECIMAL and isinstance(raw_value, str):
        value = Decimal(raw_value)
        if _canonical_decimal(value) != raw_value:
            raise ValueError("Feature decimal value is not canonical")
    elif value_type is ValueType.INTEGER and isinstance(raw_value, int) and not isinstance(raw_value, bool):
        value = raw_value
    elif value_type is ValueType.TEXT and isinstance(raw_value, str):
        value = raw_value
    else:
        raise ValueError("Feature value does not match declared type")
    raw_sources = _object_array(payload["source_bars"], "source_bars")
    source_ids: list[ArtifactId] = []
    source_hashes: list[str] = []
    for source in raw_sources:
        if set(source) != {"bar_id", "content_hash"}:
            raise ValueError("Feature value source fields mismatch")
        source_ids.append(ArtifactId(str(source["bar_id"])))
        source_hashes.append(str(source["content_hash"]))
    return TechnicalFeatureValue(
        output_id=output_id,
        state=FeatureValueState(str(payload["state"])),
        value=value,
        available_at=parse_utc_second("available_at", payload["available_at"]),
        source_bar_ids=tuple(source_ids),
        source_bar_hashes=tuple(source_hashes),
        missing_reason_codes=_string_tuple(
            payload["missing_reason_codes"], "missing_reason_codes"
        ),
    )


def _validate_scalar_type(
    *, value: TechnicalFeatureValue, expected: ValueType
) -> None:
    if value.value is None:
        return
    if expected is ValueType.DECIMAL and not isinstance(value.value, Decimal):
        raise TypeError("Feature output requires Decimal value")
    if expected is ValueType.INTEGER and (
        isinstance(value.value, bool) or not isinstance(value.value, int)
    ):
        raise TypeError("Feature output requires integer value")
    if expected is ValueType.TEXT and not isinstance(value.value, str):
        raise TypeError("Feature output requires text value")


def _canonical_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    return "0" if normalized == 0 else format(normalized, "f")


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be an array of strings")
    return tuple(value)


def _object_array(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be an array of objects")
    return value


def _artifact_hash_references(
    value: object, label: str
) -> tuple[tuple[ArtifactId, str], ...]:
    items = _object_array(value, label)
    if any(set(item) != {"artifact_id", "content_hash"} for item in items):
        raise ValueError(f"{label} entries have invalid fields")
    return tuple(
        (ArtifactId(str(item["artifact_id"])), str(item["content_hash"]))
        for item in items
    )


def _non_negative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value
