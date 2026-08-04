"""Columnar Feature Package Encoding V2 with shared configuration registries."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Callable, Mapping
import zlib

from market_regime_alpha.evidence.canonical import canonical_hash, canonical_json
from market_regime_alpha.features.spine import (
    FeatureConfiguration,
    FeatureDefinitionV2,
    FeatureSetConfiguration,
)
from market_regime_alpha.features.v2_contracts import (
    FeatureArtifactV2,
    FeatureBundleArtifact,
)
from market_regime_alpha.market_data import Timeframe


FEATURE_ARTIFACT_ENCODING_V2 = "feature-artifact-package-encoding-v2"
FEATURE_BUNDLE_ENCODING_V2 = "feature-bundle-package-encoding-v2"
FEATURE_VALUE_PARQUET_SCHEMA_V2 = "feature-value-parquet-v2"
FEATURE_ARTIFACT_LOGICAL_PACK_V1 = "feature-artifact-logical-pack-v1"
FailureInjector = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class EncodedFeatureArtifactV2:
    root: Path
    artifact: FeatureArtifactV2
    physical_checksums_hash: str


@dataclass(frozen=True, slots=True)
class FeatureValueSelectionV2:
    root: Path
    bundle_id: str
    bundle_hash: str
    rows: tuple[dict[str, Any], ...]
    physical_checksums_hash: str


def publish_feature_artifact_encoding_v2(*, root: Path, artifact: FeatureArtifactV2) -> Path:
    artifact.verify_identity()
    _publish_registry(root=root, artifact=artifact)
    final = root / str(artifact.artifact_id)
    if final.exists():
        existing = load_feature_artifact_encoding_v2(final)
        if existing.artifact.to_canonical_dict() != artifact.to_canonical_dict():
            raise FileExistsError(f"conflicting Feature Encoding V2 exists: {final}")
        return final
    root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    installed = False
    try:
        logical_bytes = canonical_json(_pack_artifact_payload(artifact.to_canonical_dict())).encode()
        (stage / "artifact.json.zlib").write_bytes(zlib.compress(logical_bytes, level=9))
        _write_json(
            stage / "encoding.json",
            {
                "encoding_version": FEATURE_ARTIFACT_ENCODING_V2,
                "logical_artifact_id": str(artifact.artifact_id),
                "logical_artifact_hash": artifact.content_hash,
                "definition_id": str(artifact.definition.definition_id),
                "definition_hash": artifact.definition.definition_hash,
                "configuration_id": str(artifact.configuration.configuration_id),
                "configuration_hash": artifact.configuration.configuration_hash,
                "logical_hash_basis": "CANONICAL_LOGICAL_PAYLOAD",
                "physical_hash_basis": "FILE_SHA256",
                "physical_format": "ZLIB_CANONICAL_LOGICAL_PACK_V1",
                "packing_schema": FEATURE_ARTIFACT_LOGICAL_PACK_V1,
            },
        )
        _write_json(
            stage / "SHA256SUMS.json",
            {name: _file_hash(stage / name) for name in ("artifact.json.zlib", "encoding.json")},
        )
        _fsync_directory(stage)
        _load_feature_artifact_encoding_v2(stage, enforce_identity=False)
        os.replace(stage, final)
        installed = True
        _fsync_directory(root)
        return final
    finally:
        if not installed and stage.exists():
            shutil.rmtree(stage)


def load_feature_artifact_encoding_v2(path: Path) -> EncodedFeatureArtifactV2:
    return _load_feature_artifact_encoding_v2(path, enforce_identity=True)


def _load_feature_artifact_encoding_v2(path: Path, *, enforce_identity: bool) -> EncodedFeatureArtifactV2:
    root = path.resolve()
    expected = {"SHA256SUMS.json", "artifact.json.zlib", "encoding.json"}
    if not root.is_dir() or {item.name for item in root.iterdir()} != expected:
        raise ValueError("Feature Encoding V2 exact file set mismatch")
    checksums = _read_object(root / "SHA256SUMS.json")
    if set(checksums) != {"artifact.json.zlib", "encoding.json"}:
        raise ValueError("Feature Encoding V2 checksum index mismatch")
    for name, expected_hash in checksums.items():
        if _file_hash(root / name) != expected_hash:
            raise ValueError(f"Feature Encoding V2 checksum mismatch: {name}")
    encoding = _read_object(root / "encoding.json")
    if encoding.get("encoding_version") != FEATURE_ARTIFACT_ENCODING_V2:
        raise ValueError("unsupported Feature Artifact encoding")
    definition_path = root.parent / "_registry" / "definitions" / f"{encoding['definition_id']}.json"
    configuration_path = root.parent / "_registry" / "configurations" / f"{encoding['configuration_id']}.json"
    definition = FeatureDefinitionV2.from_canonical_dict(_read_object(definition_path))
    configuration = FeatureConfiguration.from_canonical_dict(_read_object(configuration_path))
    if definition.definition_hash != encoding.get("definition_hash") or configuration.configuration_hash != encoding.get(
        "configuration_hash"
    ):
        raise ValueError("Feature Encoding V2 registry hash mismatch")
    try:
        encoded_payload = json.loads(zlib.decompress((root / "artifact.json.zlib").read_bytes()))
    except (OSError, zlib.error, json.JSONDecodeError) as exc:
        raise ValueError("Feature Encoding V2 logical payload is invalid") from exc
    if not isinstance(encoded_payload, dict):
        raise ValueError("Feature Encoding V2 logical payload is invalid")
    logical_payload = _unpack_artifact_payload(encoded_payload)
    artifact = FeatureArtifactV2.from_canonical_dict(
        logical_payload,
        definition=definition,
        configuration=configuration,
    )
    if str(artifact.artifact_id) != encoding.get("logical_artifact_id") or artifact.content_hash != encoding.get("logical_artifact_hash"):
        raise ValueError("Feature Encoding V2 logical identity mismatch")
    if enforce_identity and root.name != str(artifact.artifact_id):
        raise ValueError("Feature Encoding V2 directory identity mismatch")
    return EncodedFeatureArtifactV2(
        root=root,
        artifact=artifact,
        physical_checksums_hash=canonical_hash(dict(sorted(checksums.items()))),
    )


def publish_feature_bundle_encoding_v2(
    *,
    root: Path,
    bundle: FeatureBundleArtifact,
    artifacts: tuple[FeatureArtifactV2, ...],
    failure_injector: FailureInjector | None = None,
) -> Path:
    import pyarrow as pa
    import pyarrow.parquet as pq

    bundle.verify_identity()
    bundle.verify_materialized_projection(artifacts)
    final = root / str(bundle.bundle_id)
    if final.exists():
        selection = read_feature_values_v2(final)
        if selection.bundle_hash != bundle.content_hash:
            raise FileExistsError(f"conflicting Feature Bundle Encoding V2: {final}")
        return final
    root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    installed = False
    try:
        _write_json(stage / "artifact.json", bundle.to_canonical_dict())
        _write_json(stage / "feature-set.json", bundle.feature_set.to_canonical_dict())
        artifact_rows = [
            {
                "artifact_id": str(item.artifact_id),
                "content_hash": item.content_hash,
                "symbol": item.symbol,
                "feature_id": item.feature_id,
                "timeframe": item.timeframe.value,
                "artifact_json": canonical_json(_pack_artifact_payload(item.to_canonical_dict())),
            }
            for item in artifacts
        ]
        pq.write_table(
            pa.Table.from_pylist(artifact_rows),
            stage / "artifacts.parquet",
            compression="zstd",
            compression_level=9,
            use_dictionary=True,
        )
        value_rows: list[dict[str, Any]] = []
        for artifact in artifacts:
            payload = artifact.to_canonical_dict()
            raw_values = payload.get("values")
            if not isinstance(raw_values, list):
                raise ValueError("Feature Artifact values projection is invalid")
            for value in raw_values:
                if not isinstance(value, dict):
                    raise ValueError("Feature Artifact value projection is invalid")
                value_rows.append(
                    {
                        "schema_version": FEATURE_VALUE_PARQUET_SCHEMA_V2,
                        "artifact_id": str(artifact.artifact_id),
                        "artifact_hash": artifact.content_hash,
                        "symbol": artifact.symbol,
                        "feature_id": artifact.feature_id,
                        "timeframe": artifact.timeframe.value,
                        "output_id": str(value["output_id"]),
                        "state": str(value["state"]),
                        "value_json": canonical_json({"value": value.get("value")}),
                        "available_at": str(value["available_at"]),
                        "missing_reason_codes_json": canonical_json({"values": value["missing_reason_codes"]}),
                    }
                )
        pq.write_table(
            pa.Table.from_pylist(value_rows),
            stage / "values.parquet",
            compression="zstd",
            compression_level=9,
            use_dictionary=True,
            write_statistics=True,
        )
        _write_json(
            stage / "encoding.json",
            {
                "encoding_version": FEATURE_BUNDLE_ENCODING_V2,
                "logical_bundle_id": str(bundle.bundle_id),
                "logical_bundle_hash": bundle.content_hash,
                "logical_hash_basis": "CANONICAL_LOGICAL_PAYLOAD",
                "physical_hash_basis": "FILE_SHA256",
                "artifact_count": len(artifact_rows),
                "value_count": len(value_rows),
            },
        )
        files = {
            "artifact.json",
            "artifacts.parquet",
            "encoding.json",
            "feature-set.json",
            "values.parquet",
        }
        _write_json(
            stage / "SHA256SUMS.json",
            {name: _file_hash(stage / name) for name in sorted(files)},
        )
        _fsync_directory(stage)
        _read_feature_bundle_index(stage, verify_all=True, enforce_directory_identity=False)
        if failure_injector is not None:
            failure_injector("AFTER_STAGING_VALIDATED")
        os.replace(stage, final)
        installed = True
        _fsync_directory(root)
        if failure_injector is not None:
            failure_injector("AFTER_ATOMIC_INSTALL")
        return final
    finally:
        if not installed and stage.exists():
            shutil.rmtree(stage)


def load_feature_bundle_artifacts_v2(
    path: Path,
) -> tuple[FeatureBundleArtifact, tuple[FeatureArtifactV2, ...], str]:
    import pyarrow.parquet as pq

    root, checksums, bundle, feature_set = _read_feature_bundle_index(path, verify_all=True, enforce_directory_identity=True)
    table = pq.read_table(root / "artifacts.parquet", columns=["artifact_json"])
    definitions = {item.feature_id: item for item in feature_set.definitions}
    configurations = {item.feature_id: item for item in feature_set.configurations}
    artifacts: list[FeatureArtifactV2] = []
    for value in table.column("artifact_json").to_pylist():
        payload = _unpack_artifact_payload(_json_object(value))
        feature_id = str(payload["feature_id"])
        artifacts.append(
            FeatureArtifactV2.from_canonical_dict(
                payload,
                definition=definitions[feature_id],
                configuration=configurations[feature_id],
            )
        )
    ordered = tuple(
        sorted(
            artifacts,
            key=lambda item: (item.feature_id, item.symbol, item.timeframe.value),
        )
    )
    bundle.verify_materialized_projection(ordered)
    return bundle, ordered, canonical_hash(dict(sorted(checksums.items())))


def read_feature_values_v2(
    path: Path,
    *,
    symbols: tuple[str, ...] | None = None,
    feature_ids: tuple[str, ...] | None = None,
    output_ids: tuple[str, ...] | None = None,
    timeframes: tuple[Timeframe, ...] | None = None,
) -> FeatureValueSelectionV2:
    import pyarrow.parquet as pq

    root, checksums, bundle, _feature_set = _read_feature_bundle_index(path, verify_all=False, enforce_directory_identity=True)
    values_path = root / "values.parquet"
    expected = checksums.get("values.parquet")
    if expected is None or _file_hash(values_path) != expected:
        raise ValueError("Feature Bundle Encoding V2 checksum mismatch: values.parquet")
    selections = (
        ("symbol", symbols),
        ("feature_id", feature_ids),
        ("output_id", output_ids),
        (
            "timeframe",
            tuple(item.value for item in timeframes) if timeframes is not None else None,
        ),
    )
    filters = [(column, "in", list(values)) for column, values in selections if values is not None]
    table = pq.read_table(values_path, filters=filters or None)
    return FeatureValueSelectionV2(
        root=root,
        bundle_id=str(bundle.bundle_id),
        bundle_hash=bundle.content_hash,
        rows=tuple(dict(item) for item in table.to_pylist()),
        physical_checksums_hash=canonical_hash(
            {
                name: checksums[name]
                for name in (
                    "artifact.json",
                    "encoding.json",
                    "feature-set.json",
                    "values.parquet",
                )
            }
        ),
    )


def _read_feature_bundle_index(
    path: Path, *, verify_all: bool, enforce_directory_identity: bool
) -> tuple[
    Path,
    dict[str, str],
    FeatureBundleArtifact,
    FeatureSetConfiguration,
]:
    root = path.resolve()
    expected_files = {
        "SHA256SUMS.json",
        "artifact.json",
        "artifacts.parquet",
        "encoding.json",
        "feature-set.json",
        "values.parquet",
    }
    if not root.is_dir() or {item.name for item in root.iterdir()} != expected_files:
        raise ValueError("Feature Bundle Encoding V2 exact file set mismatch")
    checksums_raw = _read_object(root / "SHA256SUMS.json")
    checksums = {str(key): str(value) for key, value in checksums_raw.items()}
    if set(checksums) != expected_files - {"SHA256SUMS.json"}:
        raise ValueError("Feature Bundle Encoding V2 checksum index mismatch")
    names = (
        set(checksums)
        if verify_all
        else {
            "artifact.json",
            "encoding.json",
            "feature-set.json",
        }
    )
    for name in names:
        if _file_hash(root / name) != checksums[name]:
            raise ValueError(f"Feature Bundle Encoding V2 checksum mismatch: {name}")
    encoding = _read_object(root / "encoding.json")
    if encoding.get("encoding_version") != FEATURE_BUNDLE_ENCODING_V2:
        raise ValueError("unsupported Feature Bundle encoding")
    feature_set = FeatureSetConfiguration.from_canonical_dict(_read_object(root / "feature-set.json"))
    bundle = FeatureBundleArtifact.from_canonical_dict(_read_object(root / "artifact.json"), feature_set=feature_set)
    if (
        encoding.get("logical_bundle_id") != str(bundle.bundle_id)
        or encoding.get("logical_bundle_hash") != bundle.content_hash
        or (enforce_directory_identity and root.name != str(bundle.bundle_id))
    ):
        raise ValueError("Feature Bundle Encoding V2 logical identity mismatch")
    return root, checksums, bundle, feature_set


def _publish_registry(*, root: Path, artifact: FeatureArtifactV2) -> None:
    definitions = root / "_registry" / "definitions"
    configurations = root / "_registry" / "configurations"
    _publish_registry_object(
        definitions / f"{artifact.definition.definition_id}.json",
        artifact.definition.to_canonical_dict(),
    )
    _publish_registry_object(
        configurations / f"{artifact.configuration.configuration_id}.json",
        artifact.configuration.to_canonical_dict(),
    )


def _publish_registry_object(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (canonical_json(payload) + "\n").encode()
    if path.exists():
        if path.read_bytes() != encoded:
            raise FileExistsError(f"conflicting Feature shared registry object: {path}")
        return
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != encoded:
                raise FileExistsError(f"conflicting Feature shared registry object: {path}")
    finally:
        temporary.unlink(missing_ok=True)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = (canonical_json(payload) + "\n").encode()
    with path.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Feature Encoding V2 JSON: {path.name}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Feature Encoding V2 JSON must be an object")
    return payload


def _json_object(value: object) -> dict[str, Any]:
    if not isinstance(value, str):
        raise ValueError("Feature Encoding V2 logical payload is invalid")
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("Feature Encoding V2 logical payload is invalid")
    return payload


def _pack_artifact_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Deduplicate repeated per-value source Bars without changing logical JSON."""

    raw_sources = payload.get("source_bars")
    raw_values = payload.get("values")
    if not isinstance(raw_sources, list) or not isinstance(raw_values, list):
        raise ValueError("Feature Artifact logical source projection is invalid")
    source_registry = tuple(raw_sources)
    source_indexes = {canonical_json(item): index for index, item in enumerate(source_registry)}
    if len(source_indexes) != len(source_registry):
        raise ValueError("Feature Artifact source Bar projection is duplicated")
    packed_values: list[dict[str, Any]] = []
    for value in raw_values:
        if not isinstance(value, dict) or not isinstance(value.get("source_bars"), list):
            raise ValueError("Feature Artifact value source projection is invalid")
        packed = dict(value)
        value_sources = packed.pop("source_bars")
        try:
            packed["source_bar_indices"] = [source_indexes[canonical_json(item)] for item in value_sources]
        except KeyError as exc:
            raise ValueError("Feature value references a Bar outside Artifact source lineage") from exc
        packed_values.append(packed)
    logical = dict(payload)
    logical.pop("source_bars")
    logical["values"] = packed_values
    return {
        "packing_schema": FEATURE_ARTIFACT_LOGICAL_PACK_V1,
        "source_bar_registry": list(source_registry),
        "logical_payload": logical,
    }


def _unpack_artifact_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Restore the exact canonical logical payload; accept early V2 JSON packages."""

    if payload.get("packing_schema") != FEATURE_ARTIFACT_LOGICAL_PACK_V1:
        return dict(payload)
    if set(payload) != {
        "packing_schema",
        "source_bar_registry",
        "logical_payload",
    }:
        raise ValueError("Feature Artifact packed payload fields mismatch")
    registry = payload["source_bar_registry"]
    logical_raw = payload["logical_payload"]
    if not isinstance(registry, list) or not isinstance(logical_raw, dict):
        raise ValueError("Feature Artifact packed payload is invalid")
    raw_values = logical_raw.get("values")
    if not isinstance(raw_values, list):
        raise ValueError("Feature Artifact packed values are invalid")
    values: list[dict[str, Any]] = []
    for value in raw_values:
        if not isinstance(value, dict):
            raise ValueError("Feature Artifact packed value is invalid")
        restored = dict(value)
        raw_indices = restored.pop("source_bar_indices", None)
        if not isinstance(raw_indices, list) or any(
            not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(registry) for index in raw_indices
        ):
            raise ValueError("Feature Artifact packed source indexes are invalid")
        restored["source_bars"] = [registry[index] for index in raw_indices]
        values.append(restored)
    logical = dict(logical_raw)
    logical["source_bars"] = registry
    logical["values"] = values
    return logical


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "FEATURE_ARTIFACT_ENCODING_V2",
    "FEATURE_ARTIFACT_LOGICAL_PACK_V1",
    "FEATURE_BUNDLE_ENCODING_V2",
    "FeatureValueSelectionV2",
    "load_feature_artifact_encoding_v2",
    "load_feature_bundle_artifacts_v2",
    "publish_feature_artifact_encoding_v2",
    "publish_feature_bundle_encoding_v2",
    "read_feature_values_v2",
]
