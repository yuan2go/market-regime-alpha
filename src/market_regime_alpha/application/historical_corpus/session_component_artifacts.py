"""Immutable physical encoding for large Historical session components.

PostgreSQL remains the component owner.  This module only stores the exact
canonical payload bytes addressed by the owner's locator and physical hash.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import struct
import tempfile
from typing import Any, Callable, Mapping

import pyarrow as pa
import pyarrow.parquet as pq

from market_regime_alpha.application.controlled_operation.longitudinal_index import (
    encode_artifact_root_locator,
    resolve_artifact_root_locator,
)
from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
    HistoricalSessionComponent,
)
from market_regime_alpha.application.historical_corpus.panel_projection import (
    panel_research_features,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.evidence.canonical import canonical_json, require_sha256


HISTORICAL_COMPONENT_PAYLOAD_STORAGE = "ARTIFACT_PHYSICAL_V1"
HISTORICAL_COMPONENT_EXTERNAL_PROJECTION = (
    "historical-session-component-external-projection/v1"
)
_COMPRESSION_LEVEL = 22
_PANEL_FEATURE_REFERENCE_ENCODING = (
    "historical-session-component-panel-feature-reference/v1"
)
_JSON_ZSTD_MAGIC = b"MRAJZ1\n"
_OUTCOME_PARQUET_MAGIC = b"MRAOP1\n"
FeatureResolver = Callable[
    [ValidationArtifactReference], HistoricalSessionComponent
]


@dataclass(frozen=True, slots=True)
class HistoricalComponentPayloadArtifact:
    locator: str
    physical_hash: str
    size_bytes: int
    logical_size_bytes: int

    def __post_init__(self) -> None:
        require_sha256("physical_hash", self.physical_hash)
        if self.size_bytes <= 0 or self.logical_size_bytes <= 0:
            raise ValueError("Historical component payload sizes must be positive")


def publish_historical_component_payload(
    *,
    artifact_root: Path,
    component: HistoricalSessionComponent,
    feature_component: HistoricalSessionComponent | None = None,
) -> HistoricalComponentPayloadArtifact:
    """Compress and atomically publish one exact canonical component payload."""

    component.verify_identity()
    root = artifact_root.resolve()
    family = root / "historical-corpus" / "session-component-payload"
    family.mkdir(parents=True, exist_ok=True)
    final = family / f"{component.component_id}.json.zst"
    canonical = canonical_json(component.to_canonical_dict()).encode("utf-8")
    encoded_payload = _encoded_payload(
        component,
        feature_component=feature_component,
    )
    physical = _encode_physical(
        component=component,
        encoded_payload=encoded_payload,
    )
    artifact = HistoricalComponentPayloadArtifact(
        locator=encode_artifact_root_locator(artifact_root=root, path=final),
        physical_hash=f"sha256:{sha256(physical).hexdigest()}",
        size_bytes=len(physical),
        logical_size_bytes=len(canonical),
    )
    if final.exists():
        _verify_existing(
            final,
            artifact,
            component,
            feature_component=feature_component,
        )
        return artifact

    descriptor, stage_name = tempfile.mkstemp(
        prefix=f".{component.component_id}.",
        suffix=".tmp",
        dir=family,
    )
    stage = Path(stage_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(physical)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(stage, final)
        except FileExistsError:
            _verify_existing(
                final,
                artifact,
                component,
                feature_component=feature_component,
            )
        _fsync_directory(family)
    finally:
        stage.unlink(missing_ok=True)
    return artifact


def load_historical_component_payload(
    *,
    artifact_root: Path,
    artifact: HistoricalComponentPayloadArtifact,
    feature_resolver: FeatureResolver | None = None,
) -> HistoricalSessionComponent:
    path = resolve_artifact_root_locator(
        artifact_root=artifact_root.resolve(),
        locator=artifact.locator,
    )
    if not path.is_file():
        raise FileNotFoundError(path)
    physical = path.read_bytes()
    if len(physical) != artifact.size_bytes:
        raise ValueError("Historical component physical size mismatch")
    actual_hash = f"sha256:{sha256(physical).hexdigest()}"
    if actual_hash != artifact.physical_hash:
        raise ValueError("Historical component physical hash mismatch")
    encoded = _decode_physical(physical)
    payload = _decoded_payload(encoded, feature_resolver=feature_resolver)
    component = HistoricalSessionComponent.from_canonical_dict(payload)
    if (
        len(canonical_json(component.to_canonical_dict()).encode("utf-8"))
        != artifact.logical_size_bytes
    ):
        raise ValueError("Historical component logical size mismatch")
    return component


def _encode_physical(
    *,
    component: HistoricalSessionComponent,
    encoded_payload: Mapping[str, Any],
) -> bytes:
    del component
    raw = canonical_json(encoded_payload).encode("utf-8")
    return _JSON_ZSTD_MAGIC + struct.pack(">Q", len(raw)) + _compress(raw)


def _decode_physical(physical: bytes) -> Mapping[str, Any]:
    if physical.startswith(_JSON_ZSTD_MAGIC):
        offset = len(_JSON_ZSTD_MAGIC)
        if len(physical) < offset + 8:
            raise ValueError("Historical component physical header is truncated")
        raw_size = struct.unpack(">Q", physical[offset : offset + 8])[0]
        return _decode_json(_decompress(physical[offset + 8 :], raw_size))
    if physical.startswith(_OUTCOME_PARQUET_MAGIC):
        offset = len(_OUTCOME_PARQUET_MAGIC)
        if len(physical) < offset + 16:
            raise ValueError("Historical Outcome physical header is truncated")
        header_size, compressed_size = struct.unpack(
            ">QQ", physical[offset : offset + 16]
        )
        compressed_start = offset + 16
        parquet_start = compressed_start + compressed_size
        if parquet_start >= len(physical):
            raise ValueError("Historical Outcome physical payload is truncated")
        compact = _decode_json(
            _decompress(
                physical[compressed_start:parquet_start],
                header_size,
            )
        )
        payload = compact.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("Historical Outcome compact payload is invalid")
        try:
            labels = pq.read_table(pa.BufferReader(physical[parquet_start:])).to_pylist()
        except pa.ArrowException as error:
            raise ValueError("Historical Outcome columnar payload is invalid") from error
        if not labels:
            raise ValueError("Historical Outcome columnar payload is empty")
        payload["labels"] = labels
        return compact
    raise ValueError("Historical component physical encoding is unsupported")


def _compress(payload: bytes) -> bytes:
    return bytes(
        pa.Codec("zstd", compression_level=_COMPRESSION_LEVEL).compress(payload)
    )


def _decompress(payload: bytes, size: int) -> bytes:
    try:
        restored = bytes(
            pa.Codec("zstd").decompress(payload, decompressed_size=size)
        )
    except (pa.ArrowException, ValueError) as error:
        raise ValueError("Historical component payload decompression failed") from error
    if len(restored) != size:
        raise ValueError("Historical component encoded size mismatch")
    return restored


def _decode_json(payload: bytes) -> Mapping[str, Any]:
    try:
        raw = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Historical component payload is not canonical JSON") from error
    if not isinstance(raw, Mapping):
        raise ValueError("Historical component payload must decode to an object")
    if canonical_json(raw).encode("utf-8") != payload:
        raise ValueError("Historical component payload encoding is not canonical")
    return raw


def external_projection(
    component: HistoricalSessionComponent,
    artifact: HistoricalComponentPayloadArtifact,
) -> dict[str, Any]:
    """Return the compact PostgreSQL identity/locator projection."""

    return {
        "schema_version": HISTORICAL_COMPONENT_EXTERNAL_PROJECTION,
        "component_id": str(component.component_id),
        "component_hash": component.component_hash,
        "run_id": str(component.run_id),
        "session_id": str(component.session_id),
        "trading_date": component.trading_date.isoformat(),
        "component_kind": component.component_kind.value,
        "source_max_event_time": component.source_max_event_time.isoformat().replace(
            "+00:00", "Z"
        ),
        "materialized_at": component.materialized_at.isoformat().replace(
            "+00:00", "Z"
        ),
        "payload_locator": artifact.locator,
        "payload_physical_hash": artifact.physical_hash,
        "payload_size_bytes": artifact.size_bytes,
        "payload_logical_size_bytes": artifact.logical_size_bytes,
    }


def _verify_existing(
    path: Path,
    artifact: HistoricalComponentPayloadArtifact,
    component: HistoricalSessionComponent,
    *,
    feature_component: HistoricalSessionComponent | None,
) -> None:
    restored = load_historical_component_payload(
        artifact_root=_artifact_root(path),
        artifact=artifact,
        feature_resolver=(
            None
            if feature_component is None
            else lambda reference: _resolved_feature(
                reference,
                feature_component,
            )
        ),
    )
    if restored != component:
        raise FileExistsError("conflicting Historical component payload exists")


def _encoded_payload(
    component: HistoricalSessionComponent,
    *,
    feature_component: HistoricalSessionComponent | None,
) -> Mapping[str, Any]:
    if (
        component.component_kind is not HistoricalComponentKind.RESEARCH_PANEL
        or feature_component is None
    ):
        return component.to_canonical_dict()
    feature_reference = feature_component.reference
    if feature_reference not in component.source_references:
        raise ValueError("Historical Panel Feature source reference mismatch")
    compact = json.loads(canonical_json(component.to_canonical_dict()))
    rows = compact.get("payload", {}).get("rows")
    if not isinstance(rows, list):
        raise ValueError("Historical Panel rows are invalid")
    by_symbol = panel_research_features(feature_component)
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Historical Panel row is invalid")
        symbol = str(row.get("symbol"))
        actual = row.pop("research_features", None)
        if actual != list(by_symbol.get(symbol, ())):
            raise ValueError("Historical Panel Feature projection mismatch")
    return {
        "schema_version": _PANEL_FEATURE_REFERENCE_ENCODING,
        "feature_reference": feature_reference.to_canonical_dict(),
        "compact_component": compact,
    }


def _decoded_payload(
    encoded: Mapping[str, Any],
    *,
    feature_resolver: FeatureResolver | None,
) -> Mapping[str, Any]:
    if encoded.get("schema_version") != _PANEL_FEATURE_REFERENCE_ENCODING:
        return encoded
    if feature_resolver is None:
        raise ValueError("Historical Panel Feature resolver is required")
    raw_reference = encoded.get("feature_reference")
    compact = encoded.get("compact_component")
    if not isinstance(raw_reference, Mapping) or not isinstance(compact, Mapping):
        raise ValueError("Historical Panel Feature-reference payload is invalid")
    reference = ValidationArtifactReference.from_canonical_dict(raw_reference)
    feature_component = feature_resolver(reference)
    if feature_component.reference != reference:
        raise ValueError("Historical Panel Feature owner drifted")
    restored = json.loads(canonical_json(compact))
    rows = restored.get("payload", {}).get("rows")
    if not isinstance(rows, list):
        raise ValueError("Historical Panel rows are invalid")
    by_symbol = panel_research_features(feature_component)
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Historical Panel row is invalid")
        symbol = str(row.get("symbol"))
        features = by_symbol.get(symbol)
        if features is None:
            raise ValueError("Historical Panel Feature symbol is missing")
        row["research_features"] = [dict(item) for item in features]
    return restored


def _resolved_feature(
    reference: ValidationArtifactReference,
    feature_component: HistoricalSessionComponent,
) -> HistoricalSessionComponent:
    if feature_component.reference != reference:
        raise ValueError("Historical Panel Feature owner drifted")
    return feature_component


def _artifact_root(path: Path) -> Path:
    # ``.../<root>/historical-corpus/session-component-payload/<file>``
    return path.parents[2]


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "HISTORICAL_COMPONENT_EXTERNAL_PROJECTION",
    "HISTORICAL_COMPONENT_PAYLOAD_STORAGE",
    "HistoricalComponentPayloadArtifact",
    "external_projection",
    "load_historical_component_payload",
    "publish_historical_component_payload",
]
