"""Closed parser for label-free Decision-input Dataset manifests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any, Iterable
from uuid import UUID

from market_regime_alpha.research_qualification.domain.model import (
    ArtifactBinding,
    DecisionInputDatasetDefinition,
    FeatureDefinition,
)
from market_regime_alpha.research_qualification.domain.vocabulary import (
    DatasetSourceRole,
    FeatureCellStatus,
    FeatureValueType,
)
from market_regime_alpha.shared.financial import bounded_decimal
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import DecisionTime


_FORBIDDEN_FIELD_TOKENS = frozenset(
    {
        "target",
        "outcome",
        "return",
        "returns",
        "mfe",
        "mae",
        "barrier",
        "future",
        "realized",
        "label",
        "posterior",
    }
)
_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,99}$")
_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]{1,12})?$")


@dataclass(frozen=True, slots=True)
class DatasetSource:
    dataset_source_id: UUID
    role: DatasetSourceRole
    instrument_id: UUID | None = None
    universe_member_id: UUID | None = None
    eligibility_assessment_id: UUID | None = None
    feature_definition_id: UUID | None = None
    market_bar_revision_id: UUID | None = None
    market_instrument_fact_revision_id: UUID | None = None
    market_trading_session_id: UUID | None = None
    market_source_gap_id: UUID | None = None
    market_capture_id: UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.role, DatasetSourceRole):
            raise TypeError("Dataset source role must be DatasetSourceRole")
        expected = {
            DatasetSourceRole.POPULATION: {
                "instrument_id",
                "universe_member_id",
                "eligibility_assessment_id",
            },
            DatasetSourceRole.FEATURE_DEFINITION: {"feature_definition_id"},
            DatasetSourceRole.MARKET_BAR_REVISION: {"market_bar_revision_id"},
            DatasetSourceRole.MARKET_INSTRUMENT_FACT_REVISION: {
                "market_instrument_fact_revision_id"
            },
            DatasetSourceRole.MARKET_TRADING_SESSION: {
                "market_trading_session_id"
            },
            DatasetSourceRole.MARKET_SOURCE_GAP: {"market_source_gap_id"},
            DatasetSourceRole.MARKET_CAPTURE: {"market_capture_id"},
        }[self.role]
        identity_fields = {
            "instrument_id",
            "universe_member_id",
            "eligibility_assessment_id",
            "feature_definition_id",
            "market_bar_revision_id",
            "market_instrument_fact_revision_id",
            "market_trading_session_id",
            "market_source_gap_id",
            "market_capture_id",
        }
        actual = {
            name for name in identity_fields if getattr(self, name) is not None
        }
        if actual != expected:
            raise ValueError(
                f"Dataset source {self.role.value} has an invalid FK shape"
            )


@dataclass(frozen=True, slots=True)
class FeatureCell:
    feature_definition_id: UUID
    status: FeatureCellStatus
    value: Decimal | int | bool | str | None
    reason_code: str
    source_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class DecisionInputDatasetRow:
    instrument_id: UUID
    population_source_id: UUID
    cells: tuple[FeatureCell, ...]


@dataclass(frozen=True, slots=True)
class DecisionInputDatasetManifest:
    dataset_id: UUID
    dataset_code: str
    dataset_version: int
    decision_time: DecisionTime
    universe_revision_id: UUID
    eligibility_policy_id: UUID
    feature_definition_ids: tuple[UUID, ...]
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding
    sources: tuple[DatasetSource, ...]
    rows: tuple[DecisionInputDatasetRow, ...]
    content_sha256: ContentHash

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def feature_count(self) -> int:
        return len(self.feature_definition_ids)

    @property
    def source_count(self) -> int:
        return len(self.sources)

    @property
    def cell_count(self) -> int:
        return sum(len(row.cells) for row in self.rows)

    def status_count(self, status: FeatureCellStatus) -> int:
        return sum(
            cell.status is status for row in self.rows for cell in row.cells
        )

    @property
    def available_cell_count(self) -> int:
        return self.status_count(FeatureCellStatus.AVAILABLE)

    @property
    def missing_cell_count(self) -> int:
        return self.status_count(FeatureCellStatus.MISSING)

    @property
    def unknown_cell_count(self) -> int:
        return self.status_count(FeatureCellStatus.UNKNOWN)

    @property
    def stale_cell_count(self) -> int:
        return self.status_count(FeatureCellStatus.STALE)

    @property
    def conflict_cell_count(self) -> int:
        return self.status_count(FeatureCellStatus.CONFLICT)


def parse_decision_input_dataset_manifest(
    content: bytes,
    *,
    dataset: DecisionInputDatasetDefinition,
    feature_definitions: tuple[FeatureDefinition, ...],
) -> DecisionInputDatasetManifest:
    if not isinstance(content, bytes):
        raise TypeError("Dataset manifest content must be exact bytes")
    try:
        payload = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_closed_object,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise ValueError("Dataset manifest must be UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("Dataset manifest is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Dataset manifest root must be an object")
    _reject_label_leakage_fields(payload)
    _require_keys(
        payload,
        {
            "schema",
            "dataset_id",
            "dataset_code",
            "dataset_version",
            "decision_time",
            "universe_revision_id",
            "eligibility_policy_id",
            "feature_definition_ids",
            "code_artifact",
            "config_artifact",
            "sources",
            "rows",
        },
        context="Dataset manifest",
    )
    if payload["schema"] != "mra-decision-input-dataset-v1":
        raise ValueError("unsupported Decision-input Dataset manifest schema")
    definitions = {item.feature_definition_id: item for item in feature_definitions}
    if len(definitions) != len(feature_definitions):
        raise ValueError("Feature definitions must be unique")
    if tuple(sorted(definitions, key=str)) != dataset.feature_definition_ids:
        raise ValueError("Feature definitions do not match Dataset binding")
    feature_ids = _uuid_tuple(payload["feature_definition_ids"], "feature_definition_ids")
    code_artifact = _artifact_binding(payload["code_artifact"], "code_artifact")
    config_artifact = _artifact_binding(
        payload["config_artifact"], "config_artifact"
    )
    decision_time = _decision_time(payload["decision_time"])
    identity = (
        _uuid(payload["dataset_id"], "dataset_id"),
        payload["dataset_code"],
        _integer(payload["dataset_version"], "dataset_version", positive=True),
        decision_time,
        _uuid(payload["universe_revision_id"], "universe_revision_id"),
        _uuid(payload["eligibility_policy_id"], "eligibility_policy_id"),
        feature_ids,
        code_artifact,
        config_artifact,
    )
    expected_identity = (
        dataset.dataset_id,
        dataset.dataset_code,
        dataset.version,
        dataset.decision_time,
        dataset.universe_revision_id,
        dataset.eligibility_policy_id,
        dataset.feature_definition_ids,
        dataset.code_artifact,
        dataset.config_artifact,
    )
    if identity != expected_identity:
        raise ValueError("Dataset manifest identity does not match registration")
    sources = _parse_sources(payload["sources"])
    feature_source_ids = tuple(
        sorted(
            (
                item.feature_definition_id
                for item in sources
                if item.role is DatasetSourceRole.FEATURE_DEFINITION
                and item.feature_definition_id is not None
            ),
            key=str,
        )
    )
    if feature_source_ids != feature_ids:
        raise ValueError(
            "Dataset manifest FeatureDefinition sources must match bindings exactly"
        )
    rows = _parse_rows(
        payload["rows"],
        feature_ids=feature_ids,
        definitions=definitions,
        sources=sources,
    )
    return DecisionInputDatasetManifest(
        dataset_id=identity[0],
        dataset_code=identity[1],
        dataset_version=identity[2],
        decision_time=decision_time,
        universe_revision_id=identity[4],
        eligibility_policy_id=identity[5],
        feature_definition_ids=feature_ids,
        code_artifact=code_artifact,
        config_artifact=config_artifact,
        sources=sources,
        rows=rows,
        content_sha256=ContentHash(_sha256(content)),
    )


def _closed_object(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Dataset manifest contains duplicate field {key}")
        result[key] = value
    return result


def _reject_float(_value: str) -> Any:
    raise ValueError("floating-point JSON values are prohibited")


def _reject_constant(_value: str) -> Any:
    raise ValueError("non-finite JSON values are prohibited")


def _reject_label_leakage_fields(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key).lower()
            tokens = set(re.findall(r"[a-z]+", snake))
            if tokens & _FORBIDDEN_FIELD_TOKENS:
                raise ValueError(
                    f"Decision-input Dataset label leakage field is prohibited: {key}"
                )
            _reject_label_leakage_fields(item)
    elif isinstance(value, list):
        for item in value:
            _reject_label_leakage_fields(item)


def _parse_sources(raw: Any) -> tuple[DatasetSource, ...]:
    if not isinstance(raw, list):
        raise ValueError("sources must be an array")
    sources = tuple(_parse_source(item) for item in raw)
    if sources != tuple(sorted(sources, key=lambda item: str(item.dataset_source_id))):
        raise ValueError("Dataset sources must be unique and sorted")
    if len({item.dataset_source_id for item in sources}) != len(sources):
        raise ValueError("Dataset sources must be unique and sorted")
    source_identities = tuple(_source_identity(item) for item in sources)
    if len(set(source_identities)) != len(source_identities):
        raise ValueError("Dataset role-specific source identities must be unique")
    return sources


def _source_identity(source: DatasetSource) -> tuple[object, ...]:
    return (
        source.role,
        source.instrument_id,
        source.universe_member_id,
        source.eligibility_assessment_id,
        source.feature_definition_id,
        source.market_bar_revision_id,
        source.market_instrument_fact_revision_id,
        source.market_trading_session_id,
        source.market_source_gap_id,
        source.market_capture_id,
    )


def _parse_source(raw: Any) -> DatasetSource:
    if not isinstance(raw, dict):
        raise ValueError("Dataset source must be an object")
    role_value = raw.get("role")
    if not isinstance(role_value, str):
        raise ValueError("Dataset source role is not supported")
    try:
        role = DatasetSourceRole(role_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Dataset source role is not supported") from exc
    role_fields = {
        DatasetSourceRole.POPULATION: {
            "instrument_id",
            "universe_member_id",
            "eligibility_assessment_id",
        },
        DatasetSourceRole.FEATURE_DEFINITION: {"feature_definition_id"},
        DatasetSourceRole.MARKET_BAR_REVISION: {"market_bar_revision_id"},
        DatasetSourceRole.MARKET_INSTRUMENT_FACT_REVISION: {
            "market_instrument_fact_revision_id"
        },
        DatasetSourceRole.MARKET_TRADING_SESSION: {
            "market_trading_session_id"
        },
        DatasetSourceRole.MARKET_SOURCE_GAP: {"market_source_gap_id"},
        DatasetSourceRole.MARKET_CAPTURE: {"market_capture_id"},
    }[role]
    _require_keys(
        raw,
        {"dataset_source_id", "role"} | role_fields,
        context=f"Dataset source {role.value}",
    )
    values = {name: _uuid(raw[name], name) for name in role_fields}
    return DatasetSource(
        dataset_source_id=_uuid(raw["dataset_source_id"], "dataset_source_id"),
        role=role,
        **values,
    )


def _parse_rows(
    raw: Any,
    *,
    feature_ids: tuple[UUID, ...],
    definitions: dict[UUID, FeatureDefinition],
    sources: tuple[DatasetSource, ...],
) -> tuple[DecisionInputDatasetRow, ...]:
    if not isinstance(raw, list):
        raise ValueError("rows must be an array")
    source_map = {item.dataset_source_id: item for item in sources}
    rows = tuple(
        _parse_row(
            item,
            feature_ids=feature_ids,
            definitions=definitions,
            source_map=source_map,
        )
        for item in raw
    )
    if rows != tuple(sorted(rows, key=lambda item: str(item.instrument_id))):
        raise ValueError("Dataset rows must be unique and sorted")
    if len({item.instrument_id for item in rows}) != len(rows):
        raise ValueError("Dataset rows must be unique and sorted")
    referenced = {
        row.population_source_id for row in rows
    } | {
        source_id
        for row in rows
        for cell in row.cells
        for source_id in cell.source_ids
    }
    unreferenced = set(source_map) - referenced
    if any(
        source_map[source_id].role is not DatasetSourceRole.FEATURE_DEFINITION
        for source_id in unreferenced
    ) or (rows and unreferenced):
        raise ValueError("Dataset manifest source lineage must reconcile exactly")
    return rows


def _parse_row(
    raw: Any,
    *,
    feature_ids: tuple[UUID, ...],
    definitions: dict[UUID, FeatureDefinition],
    source_map: dict[UUID, DatasetSource],
) -> DecisionInputDatasetRow:
    if not isinstance(raw, dict):
        raise ValueError("Dataset row must be an object")
    _require_keys(
        raw,
        {"instrument_id", "population_source_id", "cells"},
        context="Dataset row",
    )
    instrument_id = _uuid(raw["instrument_id"], "instrument_id")
    population_source_id = _uuid(
        raw["population_source_id"], "population_source_id"
    )
    population = source_map.get(population_source_id)
    if (
        population is None
        or population.role is not DatasetSourceRole.POPULATION
        or population.instrument_id != instrument_id
    ):
        raise ValueError("Dataset row has invalid Selection population lineage")
    if not isinstance(raw["cells"], list):
        raise ValueError("Dataset row cells must be an array")
    cells = tuple(
        _parse_cell(item, definitions=definitions, source_map=source_map)
        for item in raw["cells"]
    )
    if tuple(item.feature_definition_id for item in cells) != feature_ids:
        raise ValueError("Dataset row must contain every Feature exactly once")
    return DecisionInputDatasetRow(
        instrument_id=instrument_id,
        population_source_id=population_source_id,
        cells=cells,
    )


def _parse_cell(
    raw: Any,
    *,
    definitions: dict[UUID, FeatureDefinition],
    source_map: dict[UUID, DatasetSource],
) -> FeatureCell:
    if not isinstance(raw, dict):
        raise ValueError("Feature cell must be an object")
    _require_keys(
        raw,
        {"feature_definition_id", "status", "value", "reason_code", "source_ids"},
        context="Feature cell",
    )
    feature_definition_id = _uuid(
        raw["feature_definition_id"], "feature_definition_id"
    )
    definition = definitions.get(feature_definition_id)
    if definition is None:
        raise ValueError("Feature cell references an unbound FeatureDefinition")
    try:
        status = FeatureCellStatus(raw["status"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Feature cell status is not supported") from exc
    reason_code = raw["reason_code"]
    if not isinstance(reason_code, str) or not _REASON_CODE.fullmatch(reason_code):
        raise ValueError("Feature cell reason_code has an invalid format")
    source_ids = _uuid_tuple(raw["source_ids"], "source_ids")
    source_records = tuple(source_map.get(item) for item in source_ids)
    if any(item is None for item in source_records):
        raise ValueError("Feature cell references unknown Dataset sources")
    feature_sources = tuple(
        item
        for item in source_records
        if item is not None
        and item.role is DatasetSourceRole.FEATURE_DEFINITION
        and item.feature_definition_id == feature_definition_id
    )
    if len(feature_sources) != 1:
        raise ValueError("Feature cell must bind its exact FeatureDefinition source")
    evidence_sources = tuple(
        item
        for item in source_records
        if item is not None
        and item.role
        not in {DatasetSourceRole.FEATURE_DEFINITION, DatasetSourceRole.POPULATION}
    )
    if not evidence_sources:
        raise ValueError("Feature cell must retain exact Market evidence lineage")
    if status is FeatureCellStatus.AVAILABLE and not any(
        item.role
        in {
            DatasetSourceRole.MARKET_BAR_REVISION,
            DatasetSourceRole.MARKET_INSTRUMENT_FACT_REVISION,
        }
        for item in evidence_sources
    ):
        raise ValueError("AVAILABLE Feature cell requires exact Market fact lineage")
    value = _typed_value(raw["value"], definition.value_type, status)
    return FeatureCell(
        feature_definition_id=feature_definition_id,
        status=status,
        value=value,
        reason_code=reason_code,
        source_ids=source_ids,
    )


def _typed_value(
    raw: Any,
    value_type: FeatureValueType,
    status: FeatureCellStatus,
) -> Decimal | int | bool | str | None:
    if status is not FeatureCellStatus.AVAILABLE:
        if raw is not None:
            raise ValueError("non-AVAILABLE Feature cell cannot contain a value")
        return None
    if value_type is FeatureValueType.DECIMAL:
        if not isinstance(raw, str) or not _DECIMAL.fullmatch(raw):
            raise ValueError("DECIMAL Feature value must be a canonical string")
        try:
            value = Decimal(raw)
        except InvalidOperation as exc:
            raise ValueError("DECIMAL Feature value is invalid") from exc
        return bounded_decimal(
            value,
            field="Feature cell value",
            precision=38,
            scale=12,
        )
    if value_type is FeatureValueType.INTEGER:
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ValueError("INTEGER Feature value must be an integer")
        return raw
    if value_type is FeatureValueType.BOOLEAN:
        if not isinstance(raw, bool):
            raise ValueError("BOOLEAN Feature value must be a boolean")
        return raw
    if value_type is FeatureValueType.TEXT:
        if not isinstance(raw, str):
            raise ValueError("TEXT Feature value must be text")
        return raw
    raise AssertionError("unsupported Feature value type")


def _artifact_binding(raw: Any, field: str) -> ArtifactBinding:
    if not isinstance(raw, dict):
        raise ValueError(f"{field} must be an object")
    _require_keys(
        raw,
        {"artifact_id", "content_sha256", "size_bytes"},
        context=field,
    )
    return ArtifactBinding(
        artifact_id=_uuid(raw["artifact_id"], f"{field}.artifact_id"),
        content_sha256=raw["content_sha256"],
        size_bytes=_integer(raw["size_bytes"], f"{field}.size_bytes"),
    )


def _uuid_tuple(raw: Any, field: str) -> tuple[UUID, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"{field} must be an array")
    values = tuple(_uuid(item, field) for item in raw)
    if values != tuple(sorted(set(values), key=str)):
        raise ValueError(f"{field} must be unique and sorted")
    return values


def _uuid(raw: Any, field: str) -> UUID:
    if not isinstance(raw, str):
        raise ValueError(f"{field} must be a UUID string")
    try:
        return UUID(raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be a UUID string") from exc


def _integer(raw: Any, field: str, *, positive: bool = False) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f"{field} must be an integer")
    if raw < (1 if positive else 0):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{field} must be {qualifier}")
    return raw


def _decision_time(raw: Any) -> DecisionTime:
    if not isinstance(raw, str):
        raise ValueError("decision_time must be an ISO timestamp")
    try:
        return DecisionTime(datetime.fromisoformat(raw))
    except ValueError as exc:
        raise ValueError("decision_time must be an ISO timestamp") from exc


def _require_keys(raw: dict[str, Any], expected: set[str], *, context: str) -> None:
    if set(raw) != expected:
        raise ValueError(f"{context} has fields outside its closed schema")


def _sha256(content: bytes) -> str:
    from market_regime_alpha.shared.hashing import sha256_bytes

    return sha256_bytes(content)


__all__ = [
    "DatasetSource",
    "DecisionInputDatasetManifest",
    "DecisionInputDatasetRow",
    "FeatureCell",
    "parse_decision_input_dataset_manifest",
]
