"""Versioned, content-addressed feature definition and configuration contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
    require_unique_text,
)
from market_regime_alpha.market_data import Timeframe
from market_regime_alpha.market_data.contracts import (
    parse_utc_second,
    require_decimal,
    require_utc_second,
)


FEATURE_DEFINITION_V2_SCHEMA = "feature-definition-v2"
FEATURE_CONFIGURATION_SCHEMA = "feature-configuration-v1"
FEATURE_SET_CONFIGURATION_SCHEMA = "feature-set-configuration-v1"


class FeatureValidationStatus(str, Enum):
    MODEL_ASSUMPTION = "MODEL_ASSUMPTION"
    RESEARCH_VALIDATED = "RESEARCH_VALIDATED"


class MissingnessPolicy(str, Enum):
    EXPLICIT_NO_IMPUTATION = "EXPLICIT_NO_IMPUTATION"


class TimeframePolicy(str, Enum):
    EXACT_MATCH_ONLY = "EXACT_MATCH_ONLY"


class RequiredFeatureCoveragePolicy(str, Enum):
    BLOCK_ON_ANY_REQUIRED_MISSING = "BLOCK_ON_ANY_REQUIRED_MISSING"
    ALLOW_PARTIAL = "ALLOW_PARTIAL"


class ValueType(str, Enum):
    DECIMAL = "DECIMAL"
    INTEGER = "INTEGER"
    TEXT = "TEXT"


class FeatureParameterType(str, Enum):
    INTEGER = "INTEGER"
    DECIMAL = "DECIMAL"
    BOOLEAN = "BOOLEAN"
    TEXT = "TEXT"
    INTEGER_LIST = "INTEGER_LIST"


@dataclass(frozen=True, slots=True)
class FeatureOutputDefinition:
    output_id: str
    value_type: ValueType

    def __post_init__(self) -> None:
        require_text("output_id", self.output_id)
        if not isinstance(self.value_type, ValueType):
            raise TypeError("value_type must be ValueType")

    def to_canonical_dict(self) -> dict[str, str]:
        return {"output_id": self.output_id, "value_type": self.value_type.value}

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> FeatureOutputDefinition:
        if set(payload) != {"output_id", "value_type"}:
            raise ValueError("Feature Output Definition fields mismatch")
        return cls(
            output_id=str(payload["output_id"]),
            value_type=ValueType(str(payload["value_type"])),
        )


@dataclass(frozen=True, slots=True)
class FeatureParameter:
    name: str
    parameter_type: FeatureParameterType
    value: str

    def __post_init__(self) -> None:
        require_text("feature parameter name", self.name)
        require_text("feature parameter value", self.value)
        if not isinstance(self.parameter_type, FeatureParameterType):
            raise TypeError("parameter_type must be FeatureParameterType")
        if self.parameter_type is FeatureParameterType.INTEGER:
            try:
                parsed = int(self.value)
            except ValueError as exc:
                raise ValueError("feature parameter must be a canonical integer") from exc
            if str(parsed) != self.value:
                raise ValueError("feature parameter must be a canonical integer")
        elif self.parameter_type is FeatureParameterType.DECIMAL:
            try:
                parsed_decimal = Decimal(self.value)
            except InvalidOperation as exc:
                raise ValueError("feature parameter must be a canonical decimal") from exc
            if not parsed_decimal.is_finite() or _canonical_decimal(parsed_decimal) != self.value:
                raise ValueError("feature parameter must be a canonical decimal")
        elif self.parameter_type is FeatureParameterType.BOOLEAN:
            if self.value not in {"false", "true"}:
                raise ValueError("feature parameter must be a strict boolean")
        elif self.parameter_type is FeatureParameterType.INTEGER_LIST:
            pieces = self.value.split(",")
            try:
                values = tuple(int(item) for item in pieces)
            except ValueError as exc:
                raise ValueError("feature parameter must be a canonical integer list") from exc
            if (
                not values
                or any(value <= 0 for value in values)
                or tuple(str(item) for item in values) != tuple(pieces)
                or values != tuple(sorted(set(values)))
            ):
                raise ValueError("feature parameter must be a unique sorted integer list")

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "parameter_type": self.parameter_type.value,
            "value": self.value,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> FeatureParameter:
        if set(payload) != {"name", "parameter_type", "value"}:
            raise ValueError("Feature Parameter fields mismatch")
        return cls(
            name=str(payload["name"]),
            parameter_type=FeatureParameterType(str(payload["parameter_type"])),
            value=str(payload["value"]),
        )


@dataclass(frozen=True, slots=True)
class FeatureDefinitionV2:
    schema_version: str
    definition_id: ArtifactId
    definition_hash: str
    feature_id: str
    feature_version: str
    model_id: ModelId
    model_version: str
    required_fields: tuple[str, ...]
    supported_timeframes: tuple[Timeframe, ...]
    minimum_history: int
    warmup_policy: str
    missingness_policy: MissingnessPolicy
    output_schema: tuple[FeatureOutputDefinition, ...]
    validation_status: FeatureValidationStatus
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != FEATURE_DEFINITION_V2_SCHEMA:
            raise ValueError("unsupported Feature Definition V2 schema")
        require_sha256("definition_hash", self.definition_hash)
        for label, value in (
            ("feature_id", self.feature_id),
            ("feature_version", self.feature_version),
            ("model_version", self.model_version),
            ("warmup_policy", self.warmup_policy),
        ):
            require_text(label, value)
        require_unique_text("required_field", self.required_fields)
        if self.required_fields != tuple(sorted(self.required_fields)):
            raise ValueError("required fields must be sorted")
        if not self.supported_timeframes or self.supported_timeframes != tuple(
            sorted(set(self.supported_timeframes), key=lambda item: item.value)
        ):
            raise ValueError("supported timeframes must be non-empty, unique, and sorted")
        if isinstance(self.minimum_history, bool) or self.minimum_history <= 0:
            raise ValueError("minimum_history must be a positive integer")
        output_ids = tuple(item.output_id for item in self.output_schema)
        if not output_ids or len(output_ids) != len(set(output_ids)):
            raise ValueError("duplicate output IDs are not allowed")
        if output_ids != tuple(sorted(output_ids)):
            raise ValueError("output schema must be sorted")
        require_unique_text("limitation", self.limitations)
        if self.limitations != tuple(sorted(self.limitations)):
            raise ValueError("limitations must be sorted")

    @classmethod
    def create(
        cls,
        *,
        feature_id: str,
        feature_version: str,
        model_id: ModelId,
        model_version: str,
        required_fields: tuple[str, ...],
        supported_timeframes: tuple[Timeframe, ...],
        minimum_history: int,
        warmup_policy: str,
        missingness_policy: MissingnessPolicy,
        output_schema: tuple[FeatureOutputDefinition, ...],
        validation_status: FeatureValidationStatus,
        limitations: tuple[str, ...],
    ) -> FeatureDefinitionV2:
        ordered_fields = tuple(sorted(required_fields))
        ordered_timeframes = tuple(sorted(supported_timeframes, key=lambda item: item.value))
        ordered_outputs = tuple(sorted(output_schema, key=lambda item: item.output_id))
        ordered_limitations = tuple(sorted(limitations))
        payload = _definition_payload(
            feature_id=feature_id,
            feature_version=feature_version,
            model_id=model_id,
            model_version=model_version,
            required_fields=ordered_fields,
            supported_timeframes=ordered_timeframes,
            minimum_history=minimum_history,
            warmup_policy=warmup_policy,
            missingness_policy=missingness_policy,
            output_schema=ordered_outputs,
            validation_status=validation_status,
            limitations=ordered_limitations,
        )
        definition_hash = canonical_hash(payload)
        result = cls(
            schema_version=FEATURE_DEFINITION_V2_SCHEMA,
            definition_id=ArtifactId(
                f"feature-definition-{definition_hash.split(':', 1)[1][:24]}"
            ),
            definition_hash=definition_hash,
            feature_id=feature_id,
            feature_version=feature_version,
            model_id=model_id,
            model_version=model_version,
            required_fields=ordered_fields,
            supported_timeframes=ordered_timeframes,
            minimum_history=minimum_history,
            warmup_policy=warmup_policy,
            missingness_policy=missingness_policy,
            output_schema=ordered_outputs,
            validation_status=validation_status,
            limitations=ordered_limitations,
        )
        result.verify_identity()
        return result

    def semantic_payload(self) -> dict[str, Any]:
        return _definition_payload(
            feature_id=self.feature_id,
            feature_version=self.feature_version,
            model_id=self.model_id,
            model_version=self.model_version,
            required_fields=self.required_fields,
            supported_timeframes=self.supported_timeframes,
            minimum_history=self.minimum_history,
            warmup_policy=self.warmup_policy,
            missingness_policy=self.missingness_policy,
            output_schema=self.output_schema,
            validation_status=self.validation_status,
            limitations=self.limitations,
        )

    def verify_identity(self) -> None:
        expected_hash = canonical_hash(self.semantic_payload())
        if self.definition_hash != expected_hash:
            raise ValueError("Feature Definition payload hash mismatch")
        expected_id = f"feature-definition-{expected_hash.split(':', 1)[1][:24]}"
        if str(self.definition_id) != expected_id:
            raise ValueError("Feature Definition identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "definition_id": str(self.definition_id),
            "definition_hash": self.definition_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> FeatureDefinitionV2:
        expected = {
            "schema_version",
            "definition_id",
            "definition_hash",
            "feature_id",
            "feature_version",
            "model_id",
            "model_version",
            "required_fields",
            "supported_timeframes",
            "minimum_history",
            "warmup_policy",
            "missingness_policy",
            "output_schema",
            "validation_status",
            "limitations",
        }
        if set(payload) != expected:
            raise ValueError("Feature Definition V2 fields mismatch")
        raw_outputs = payload["output_schema"]
        if not isinstance(raw_outputs, list) or any(
            not isinstance(item, dict) for item in raw_outputs
        ):
            raise ValueError("output_schema must be an array of objects")
        result = cls(
            schema_version=str(payload["schema_version"]),
            definition_id=ArtifactId(str(payload["definition_id"])),
            definition_hash=str(payload["definition_hash"]),
            feature_id=str(payload["feature_id"]),
            feature_version=str(payload["feature_version"]),
            model_id=ModelId(str(payload["model_id"])),
            model_version=str(payload["model_version"]),
            required_fields=_string_tuple(payload["required_fields"], "required_fields"),
            supported_timeframes=tuple(
                Timeframe(item)
                for item in _string_tuple(
                    payload["supported_timeframes"], "supported_timeframes"
                )
            ),
            minimum_history=_positive_int(payload["minimum_history"], "minimum_history"),
            warmup_policy=str(payload["warmup_policy"]),
            missingness_policy=MissingnessPolicy(str(payload["missingness_policy"])),
            output_schema=tuple(
                FeatureOutputDefinition.from_canonical_dict(item) for item in raw_outputs
            ),
            validation_status=FeatureValidationStatus(str(payload["validation_status"])),
            limitations=_string_tuple(payload["limitations"], "limitations"),
        )
        result.verify_identity()
        return result


@dataclass(frozen=True, slots=True)
class FeatureConfiguration:
    schema_version: str
    configuration_id: ArtifactId
    configuration_hash: str
    configuration_version: str
    feature_id: str
    effective_from: datetime
    parameters: tuple[FeatureParameter, ...]
    validation_status: FeatureValidationStatus

    def __post_init__(self) -> None:
        if self.schema_version != FEATURE_CONFIGURATION_SCHEMA:
            raise ValueError("unsupported Feature Configuration schema")
        require_sha256("configuration_hash", self.configuration_hash)
        require_text("configuration_version", self.configuration_version)
        require_text("feature_id", self.feature_id)
        require_utc_second("effective_from", self.effective_from)
        names = tuple(item.name for item in self.parameters)
        if names != tuple(sorted(set(names))):
            raise ValueError("feature parameters must be unique and sorted")

    @classmethod
    def create(
        cls,
        *,
        configuration_version: str,
        feature_id: str,
        effective_from: datetime,
        parameters: tuple[FeatureParameter, ...],
        validation_status: FeatureValidationStatus,
    ) -> FeatureConfiguration:
        ordered = tuple(sorted(parameters, key=lambda item: item.name))
        payload = _configuration_payload(
            configuration_version=configuration_version,
            feature_id=feature_id,
            effective_from=effective_from,
            parameters=ordered,
            validation_status=validation_status,
        )
        configuration_hash = canonical_hash(payload)
        result = cls(
            schema_version=FEATURE_CONFIGURATION_SCHEMA,
            configuration_id=ArtifactId(
                f"feature-configuration-{configuration_hash.split(':', 1)[1][:24]}"
            ),
            configuration_hash=configuration_hash,
            configuration_version=configuration_version,
            feature_id=feature_id,
            effective_from=effective_from,
            parameters=ordered,
            validation_status=validation_status,
        )
        result.verify_identity()
        return result

    def semantic_payload(self) -> dict[str, Any]:
        return _configuration_payload(
            configuration_version=self.configuration_version,
            feature_id=self.feature_id,
            effective_from=self.effective_from,
            parameters=self.parameters,
            validation_status=self.validation_status,
        )

    def verify_identity(self) -> None:
        expected_hash = canonical_hash(self.semantic_payload())
        if self.configuration_hash != expected_hash:
            raise ValueError("Feature Configuration payload hash mismatch")
        expected_id = f"feature-configuration-{expected_hash.split(':', 1)[1][:24]}"
        if str(self.configuration_id) != expected_id:
            raise ValueError("Feature Configuration identity mismatch")

    def parameter_map(self) -> dict[str, str]:
        return {item.name: item.value for item in self.parameters}

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> FeatureConfiguration:
        expected = {
            "schema_version",
            "configuration_id",
            "configuration_hash",
            "configuration_version",
            "feature_id",
            "effective_from",
            "parameters",
            "validation_status",
        }
        if set(payload) != expected:
            raise ValueError("Feature Configuration fields mismatch")
        raw_parameters = payload["parameters"]
        if not isinstance(raw_parameters, list) or any(
            not isinstance(item, dict) for item in raw_parameters
        ):
            raise ValueError("parameters must be an array of objects")
        result = cls(
            schema_version=str(payload["schema_version"]),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
            configuration_version=str(payload["configuration_version"]),
            feature_id=str(payload["feature_id"]),
            effective_from=parse_utc_second("effective_from", payload["effective_from"]),
            parameters=tuple(
                FeatureParameter.from_canonical_dict(item) for item in raw_parameters
            ),
            validation_status=FeatureValidationStatus(str(payload["validation_status"])),
        )
        result.verify_identity()
        return result


@dataclass(frozen=True, slots=True)
class FeatureSetConfiguration:
    schema_version: str
    feature_set_id: ArtifactId
    content_hash: str
    feature_set_version: str
    definitions: tuple[FeatureDefinitionV2, ...]
    configurations: tuple[FeatureConfiguration, ...]
    required_feature_ids: tuple[str, ...]
    optional_feature_ids: tuple[str, ...]
    timeframe_policy: TimeframePolicy
    coverage_policy: RequiredFeatureCoveragePolicy
    minimum_required_coverage: Decimal
    missingness_policy: MissingnessPolicy
    validation_status: FeatureValidationStatus
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != FEATURE_SET_CONFIGURATION_SCHEMA:
            raise ValueError("unsupported Feature Set Configuration schema")
        require_sha256("content_hash", self.content_hash)
        require_text("feature_set_version", self.feature_set_version)
        definition_ids = tuple(item.feature_id for item in self.definitions)
        if not definition_ids or len(definition_ids) != len(set(definition_ids)):
            raise ValueError("duplicate feature definition is not allowed")
        if definition_ids != tuple(sorted(definition_ids)):
            raise ValueError("feature definitions must be sorted")
        configuration_ids = tuple(item.feature_id for item in self.configurations)
        if configuration_ids != definition_ids:
            raise ValueError("feature configurations must exactly cover definitions")
        if set(self.required_feature_ids) & set(self.optional_feature_ids):
            raise ValueError("feature cannot be both required and optional")
        classified = set(self.required_feature_ids) | set(self.optional_feature_ids)
        if classified != set(definition_ids):
            raise ValueError("required/optional classifications must cover definitions")
        for label, values in (
            ("required_feature_ids", self.required_feature_ids),
            ("optional_feature_ids", self.optional_feature_ids),
        ):
            require_unique_text(label, values)
            if values != tuple(sorted(values)):
                raise ValueError(f"{label} must be sorted")
        require_decimal("minimum_required_coverage", self.minimum_required_coverage)
        if not Decimal("0") <= self.minimum_required_coverage <= Decimal("1"):
            raise ValueError("minimum_required_coverage must be between zero and one")
        if (
            self.coverage_policy
            is RequiredFeatureCoveragePolicy.BLOCK_ON_ANY_REQUIRED_MISSING
            and self.minimum_required_coverage != Decimal("1")
        ):
            raise ValueError("blocking coverage policy requires complete coverage")
        require_unique_text("limitation", self.limitations)
        if self.limitations != tuple(sorted(self.limitations)):
            raise ValueError("limitations must be sorted")
        for definition in self.definitions:
            definition.verify_identity()
        for configuration in self.configurations:
            configuration.verify_identity()

    @property
    def configuration_id(self) -> ArtifactId:
        """Typed lifecycle configuration identity view."""

        return self.feature_set_id

    @property
    def configuration_hash(self) -> str:
        """Typed lifecycle configuration hash view."""

        return self.content_hash

    @classmethod
    def create(
        cls,
        *,
        feature_set_version: str,
        definitions: tuple[FeatureDefinitionV2, ...],
        configurations: tuple[FeatureConfiguration, ...],
        required_feature_ids: tuple[str, ...],
        optional_feature_ids: tuple[str, ...],
        timeframe_policy: TimeframePolicy,
        coverage_policy: RequiredFeatureCoveragePolicy,
        minimum_required_coverage: Decimal,
        missingness_policy: MissingnessPolicy,
        validation_status: FeatureValidationStatus,
        limitations: tuple[str, ...],
    ) -> FeatureSetConfiguration:
        ordered_definitions = tuple(sorted(definitions, key=lambda item: item.feature_id))
        ordered_configurations = tuple(sorted(configurations, key=lambda item: item.feature_id))
        ordered_required = tuple(sorted(required_feature_ids))
        ordered_optional = tuple(sorted(optional_feature_ids))
        ordered_limitations = tuple(sorted(limitations))
        payload = _feature_set_payload(
            feature_set_version=feature_set_version,
            definitions=ordered_definitions,
            configurations=ordered_configurations,
            required_feature_ids=ordered_required,
            optional_feature_ids=ordered_optional,
            timeframe_policy=timeframe_policy,
            coverage_policy=coverage_policy,
            minimum_required_coverage=minimum_required_coverage,
            missingness_policy=missingness_policy,
            validation_status=validation_status,
            limitations=ordered_limitations,
        )
        content_hash = canonical_hash(payload)
        result = cls(
            schema_version=FEATURE_SET_CONFIGURATION_SCHEMA,
            feature_set_id=ArtifactId(
                f"feature-set-{content_hash.split(':', 1)[1][:24]}"
            ),
            content_hash=content_hash,
            feature_set_version=feature_set_version,
            definitions=ordered_definitions,
            configurations=ordered_configurations,
            required_feature_ids=ordered_required,
            optional_feature_ids=ordered_optional,
            timeframe_policy=timeframe_policy,
            coverage_policy=coverage_policy,
            minimum_required_coverage=minimum_required_coverage,
            missingness_policy=missingness_policy,
            validation_status=validation_status,
            limitations=ordered_limitations,
        )
        result.verify_identity()
        return result

    def semantic_payload(self) -> dict[str, Any]:
        return _feature_set_payload(
            feature_set_version=self.feature_set_version,
            definitions=self.definitions,
            configurations=self.configurations,
            required_feature_ids=self.required_feature_ids,
            optional_feature_ids=self.optional_feature_ids,
            timeframe_policy=self.timeframe_policy,
            coverage_policy=self.coverage_policy,
            minimum_required_coverage=self.minimum_required_coverage,
            missingness_policy=self.missingness_policy,
            validation_status=self.validation_status,
            limitations=self.limitations,
        )

    def verify_identity(self) -> None:
        expected_hash = canonical_hash(self.semantic_payload())
        if self.content_hash != expected_hash:
            raise ValueError("Feature Set Configuration payload hash mismatch")
        expected_id = f"feature-set-{expected_hash.split(':', 1)[1][:24]}"
        if str(self.feature_set_id) != expected_id:
            raise ValueError("Feature Set Configuration identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "feature_set_id": str(self.feature_set_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> FeatureSetConfiguration:
        expected = {
            "schema_version",
            "feature_set_id",
            "content_hash",
            "feature_set_version",
            "definitions",
            "configurations",
            "required_feature_ids",
            "optional_feature_ids",
            "timeframe_policy",
            "coverage_policy",
            "minimum_required_coverage",
            "missingness_policy",
            "validation_status",
            "limitations",
        }
        if set(payload) != expected:
            raise ValueError("Feature Set Configuration fields mismatch")
        raw_definitions = payload["definitions"]
        raw_configurations = payload["configurations"]
        if not isinstance(raw_definitions, list) or any(
            not isinstance(item, dict) for item in raw_definitions
        ):
            raise ValueError("definitions must be an array of objects")
        if not isinstance(raw_configurations, list) or any(
            not isinstance(item, dict) for item in raw_configurations
        ):
            raise ValueError("configurations must be an array of objects")
        result = cls(
            schema_version=str(payload["schema_version"]),
            feature_set_id=ArtifactId(str(payload["feature_set_id"])),
            content_hash=str(payload["content_hash"]),
            feature_set_version=str(payload["feature_set_version"]),
            definitions=tuple(
                FeatureDefinitionV2.from_canonical_dict(item)
                for item in raw_definitions
            ),
            configurations=tuple(
                FeatureConfiguration.from_canonical_dict(item)
                for item in raw_configurations
            ),
            required_feature_ids=_string_tuple(
                payload["required_feature_ids"], "required_feature_ids"
            ),
            optional_feature_ids=_string_tuple(
                payload["optional_feature_ids"], "optional_feature_ids"
            ),
            timeframe_policy=TimeframePolicy(str(payload["timeframe_policy"])),
            coverage_policy=RequiredFeatureCoveragePolicy(str(payload["coverage_policy"])),
            minimum_required_coverage=Decimal(str(payload["minimum_required_coverage"])),
            missingness_policy=MissingnessPolicy(str(payload["missingness_policy"])),
            validation_status=FeatureValidationStatus(str(payload["validation_status"])),
            limitations=_string_tuple(payload["limitations"], "limitations"),
        )
        result.verify_identity()
        return result


def _definition_payload(
    *,
    feature_id: str,
    feature_version: str,
    model_id: ModelId,
    model_version: str,
    required_fields: tuple[str, ...],
    supported_timeframes: tuple[Timeframe, ...],
    minimum_history: int,
    warmup_policy: str,
    missingness_policy: MissingnessPolicy,
    output_schema: tuple[FeatureOutputDefinition, ...],
    validation_status: FeatureValidationStatus,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": FEATURE_DEFINITION_V2_SCHEMA,
        "feature_id": feature_id,
        "feature_version": feature_version,
        "model_id": str(model_id),
        "model_version": model_version,
        "required_fields": list(required_fields),
        "supported_timeframes": [item.value for item in supported_timeframes],
        "minimum_history": minimum_history,
        "warmup_policy": warmup_policy,
        "missingness_policy": missingness_policy.value,
        "output_schema": [item.to_canonical_dict() for item in output_schema],
        "validation_status": validation_status.value,
        "limitations": list(limitations),
    }


def _configuration_payload(
    *,
    configuration_version: str,
    feature_id: str,
    effective_from: datetime,
    parameters: tuple[FeatureParameter, ...],
    validation_status: FeatureValidationStatus,
) -> dict[str, Any]:
    return {
        "schema_version": FEATURE_CONFIGURATION_SCHEMA,
        "configuration_version": configuration_version,
        "feature_id": feature_id,
        "effective_from": canonical_datetime(effective_from),
        "parameters": [item.to_canonical_dict() for item in parameters],
        "validation_status": validation_status.value,
    }


def _feature_set_payload(
    *,
    feature_set_version: str,
    definitions: tuple[FeatureDefinitionV2, ...],
    configurations: tuple[FeatureConfiguration, ...],
    required_feature_ids: tuple[str, ...],
    optional_feature_ids: tuple[str, ...],
    timeframe_policy: TimeframePolicy,
    coverage_policy: RequiredFeatureCoveragePolicy,
    minimum_required_coverage: Decimal,
    missingness_policy: MissingnessPolicy,
    validation_status: FeatureValidationStatus,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": FEATURE_SET_CONFIGURATION_SCHEMA,
        "feature_set_version": feature_set_version,
        "definitions": [item.to_canonical_dict() for item in definitions],
        "configurations": [item.to_canonical_dict() for item in configurations],
        "required_feature_ids": list(required_feature_ids),
        "optional_feature_ids": list(optional_feature_ids),
        "timeframe_policy": timeframe_policy.value,
        "coverage_policy": coverage_policy.value,
        "minimum_required_coverage": _canonical_decimal(minimum_required_coverage),
        "missingness_policy": missingness_policy.value,
        "validation_status": validation_status.value,
        "limitations": list(limitations),
    }


def _canonical_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be an array of strings")
    return tuple(value)


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value
