"""Atomic publication, strict reading and deterministic replay for Feature Artifacts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    FeatureDefinitionId,
    ModelId,
)
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.evidence.canonical import canonical_datetime, canonical_hash
from market_regime_alpha.features.model_contracts import (
    FeatureArtifact,
    FeatureComputationRequest,
)


FEATURE_ARTIFACT_SCHEMA = "feature-computation-artifact-v1"
FEATURE_ARTIFACT_PACKAGE_SCHEMA = "feature-artifact-package-v1"
FEATURE_ARTIFACT_FILES = ("SHA256SUMS.json", "artifact.json", "manifest.json")


@dataclass(frozen=True, slots=True)
class VerifiedFeatureArtifact:
    root: Path
    artifact: FeatureArtifact
    checksums_hash: str


def feature_artifact_payload(artifact: FeatureArtifact) -> dict[str, Any]:
    return {
        "schema_version": FEATURE_ARTIFACT_SCHEMA,
        "feature_id": str(artifact.feature_id),
        "dataset_id": str(artifact.dataset_id),
        "model_id": str(artifact.model_id),
        "model_version": artifact.model_version,
        "configuration_id": str(artifact.configuration_id),
        "configuration_version": artifact.configuration_version,
        "configuration_hash": artifact.configuration_hash,
        "configuration_parameters": [
            {"name": name, "value": value}
            for name, value in artifact.configuration_parameters
        ],
        "input_artifact_ids": [str(item) for item in artifact.input_artifact_ids],
        "input_hashes": list(artifact.input_hashes),
        "as_of_time": canonical_datetime(artifact.as_of_time),
        "created_at": canonical_datetime(artifact.created_at),
        "data_availability": artifact.data_availability.value,
        "state": artifact.state,
        "score": str(artifact.score) if artifact.score is not None else None,
        "reason_codes": list(artifact.reason_codes),
        "limitations": list(artifact.limitations),
        "validation_status": artifact.validation_status,
        "observations": [_canonical_observation(item) for item in artifact.observations],
    }


def feature_artifact_to_dict(artifact: FeatureArtifact) -> dict[str, Any]:
    return {
        "artifact_id": str(artifact.artifact_id),
        "content_hash": artifact.content_hash,
        **feature_artifact_payload(artifact),
    }


def verify_feature_artifact_identity(artifact: FeatureArtifact) -> None:
    expected_hash = canonical_hash(feature_artifact_payload(artifact))
    if artifact.content_hash != expected_hash:
        raise ValueError("Feature Artifact payload hash mismatch")
    expected_id = f"feature-artifact-{expected_hash.split(':', 1)[1][:24]}"
    if str(artifact.artifact_id) != expected_id:
        raise ValueError("Feature Artifact identity mismatch")


def bind_feature_artifact_identity(artifact: FeatureArtifact) -> FeatureArtifact:
    """Bind a fully populated immutable Feature Artifact to its semantic payload."""

    content_hash = canonical_hash(feature_artifact_payload(artifact))
    bound = replace(
        artifact,
        artifact_id=ArtifactId(
            f"feature-artifact-{content_hash.split(':', 1)[1][:24]}"
        ),
        content_hash=content_hash,
    )
    verify_feature_artifact_identity(bound)
    return bound


def publish_feature_artifact(*, root: Path, artifact: FeatureArtifact) -> Path:
    verify_feature_artifact_identity(artifact)
    _validate_supported_artifact(artifact)
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(artifact.artifact_id)
    if final.exists():
        existing = load_verified_feature_artifact(final)
        if existing.artifact.to_canonical_dict() != artifact.to_canonical_dict():
            raise FileExistsError(f"conflicting Feature Artifact exists: {final}")
        return final

    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    try:
        _write_json(stage / "artifact.json", feature_artifact_to_dict(artifact))
        _write_json(stage / "manifest.json", _manifest(artifact))
        _write_json(
            stage / "SHA256SUMS.json",
            {
                name: _file_hash(stage / name)
                for name in FEATURE_ARTIFACT_FILES
                if name != "SHA256SUMS.json"
            },
        )
        if {item.name for item in stage.iterdir()} != set(FEATURE_ARTIFACT_FILES):
            raise RuntimeError("Feature Artifact staging exact file set mismatch")
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def load_verified_feature_artifact(path: Path) -> VerifiedFeatureArtifact:
    root = path.resolve()
    _verify_files(root)
    artifact = _feature_artifact_from_dict(_read_object(root / "artifact.json"))
    _validate_supported_artifact(artifact)
    if _read_object(root / "manifest.json") != _manifest(artifact):
        raise ValueError("Feature Artifact manifest is not reconstructible")
    if root.name != str(artifact.artifact_id):
        raise ValueError("Feature Artifact directory identity mismatch")
    return VerifiedFeatureArtifact(
        root=root,
        artifact=artifact,
        checksums_hash=_file_hash(root / "SHA256SUMS.json"),
    )


def replay_feature_artifact(path: Path) -> VerifiedFeatureArtifact:
    verified = load_verified_feature_artifact(path)
    original = verified.artifact

    from market_regime_alpha.features.technical.moving_average import (
        MovingAverageConfiguration,
        MovingAverageObservation,
        NormalizedCloseBar,
        SIMPLE_MOVING_AVERAGE_FEATURE_ID,
        SimpleMovingAverageComputer,
    )

    if original.feature_id != SIMPLE_MOVING_AVERAGE_FEATURE_ID:
        raise ValueError(f"unsupported Feature replay: {original.feature_id}")
    parameters = dict(original.configuration_parameters)
    if set(parameters) != {"window"}:
        raise ValueError("Moving Average replay configuration fields mismatch")
    try:
        window = int(parameters["window"])
    except ValueError as exc:
        raise ValueError("Moving Average replay window must be an integer") from exc
    if str(window) != parameters["window"]:
        raise ValueError("Moving Average replay window is not canonical")
    configuration = MovingAverageConfiguration(
        configuration_id=original.configuration_id,
        configuration_version=original.configuration_version,
        window=window,
        content_hash=original.configuration_hash,
    )
    observations = _moving_average_observations(original)
    bars = tuple(
        NormalizedCloseBar(
            symbol=item.symbol,
            market_date=item.market_date,
            close=item.close,
            available_at=item.source_available_at,
        )
        for item in observations
        if isinstance(item, MovingAverageObservation)
    )
    replayed = SimpleMovingAverageComputer().compute(
        FeatureComputationRequest(
            dataset_id=original.dataset_id,
            as_of_time=original.as_of_time,
            created_at=original.created_at,
            data_availability=original.data_availability,
            configuration_id=original.configuration_id,
            configuration_version=original.configuration_version,
            configuration_hash=original.configuration_hash,
            input_artifact_ids=original.input_artifact_ids,
            input_hashes=original.input_hashes,
            normalized_data=bars,
            configuration=configuration,
        )
    )
    if replayed.to_canonical_dict() != original.to_canonical_dict():
        raise ValueError("Feature replay differs from stored Artifact")
    return verified


def _feature_artifact_from_dict(payload: Mapping[str, object]) -> FeatureArtifact:
    expected = {
        "artifact_id",
        "content_hash",
        "schema_version",
        "feature_id",
        "dataset_id",
        "model_id",
        "model_version",
        "configuration_id",
        "configuration_version",
        "configuration_hash",
        "configuration_parameters",
        "input_artifact_ids",
        "input_hashes",
        "as_of_time",
        "created_at",
        "data_availability",
        "state",
        "score",
        "reason_codes",
        "limitations",
        "validation_status",
        "observations",
    }
    if set(payload) != expected:
        raise ValueError("FeatureArtifact fields mismatch")
    if _text(payload["schema_version"], "schema_version") != FEATURE_ARTIFACT_SCHEMA:
        raise ValueError("unsupported Feature Artifact schema")
    feature_id = FeatureDefinitionId(_text(payload["feature_id"], "feature_id"))
    observations = _load_observations(feature_id, payload["observations"])
    score_value = payload["score"]
    score = _decimal(score_value, "score") if score_value is not None else None
    artifact = FeatureArtifact(
        artifact_id=ArtifactId(_text(payload["artifact_id"], "artifact_id")),
        content_hash=_text(payload["content_hash"], "content_hash"),
        feature_id=feature_id,
        dataset_id=DatasetId(_text(payload["dataset_id"], "dataset_id")),
        model_id=ModelId(_text(payload["model_id"], "model_id")),
        model_version=_text(payload["model_version"], "model_version"),
        configuration_id=ArtifactId(
            _text(payload["configuration_id"], "configuration_id")
        ),
        configuration_version=_text(
            payload["configuration_version"], "configuration_version"
        ),
        configuration_hash=_text(
            payload["configuration_hash"], "configuration_hash"
        ),
        input_artifact_ids=tuple(
            ArtifactId(item)
            for item in _text_array(
                payload["input_artifact_ids"], "input_artifact_ids"
            )
        ),
        input_hashes=_text_array(payload["input_hashes"], "input_hashes"),
        as_of_time=_datetime(payload["as_of_time"], "as_of_time"),
        created_at=_datetime(payload["created_at"], "created_at"),
        data_availability=InputAvailabilityStatus(
            _text(payload["data_availability"], "data_availability")
        ),
        state=_text(payload["state"], "state"),
        score=score,
        reason_codes=_text_array(payload["reason_codes"], "reason_codes"),
        limitations=_text_array(payload["limitations"], "limitations"),
        validation_status=_text(
            payload["validation_status"], "validation_status"
        ),
        observations=observations,
        configuration_parameters=tuple(
            (
                _text(item["name"], "configuration parameter name"),
                _text(item["value"], "configuration parameter value"),
            )
            for item in _object_array(
                payload["configuration_parameters"],
                "configuration_parameters",
                expected_keys={"name", "value"},
            )
        ),
    )
    verify_feature_artifact_identity(artifact)
    return artifact


def _load_observations(
    feature_id: FeatureDefinitionId, value: object
) -> tuple[object, ...]:
    from market_regime_alpha.features.technical.moving_average import (
        MovingAverageObservation,
        SIMPLE_MOVING_AVERAGE_FEATURE_ID,
    )

    if feature_id != SIMPLE_MOVING_AVERAGE_FEATURE_ID:
        raise ValueError(f"unsupported Feature Artifact type: {feature_id}")
    return tuple(
        MovingAverageObservation.from_canonical_dict(item)
        for item in _object_array(value, "observations", expected_keys=None)
    )


def _moving_average_observations(
    artifact: FeatureArtifact,
) -> tuple[object, ...]:
    from market_regime_alpha.features.technical.moving_average import (
        MovingAverageObservation,
    )

    if any(not isinstance(item, MovingAverageObservation) for item in artifact.observations):
        raise TypeError("Moving Average Artifact contains invalid observations")
    return artifact.observations


def _validate_supported_artifact(artifact: FeatureArtifact) -> None:
    from market_regime_alpha.features.technical.moving_average import (
        MovingAverageConfiguration,
        MovingAverageObservation,
        SIMPLE_MOVING_AVERAGE_FEATURE_ID,
        SIMPLE_MOVING_AVERAGE_MODEL_ID,
        SimpleMovingAverageComputer,
    )

    if artifact.feature_id != SIMPLE_MOVING_AVERAGE_FEATURE_ID:
        raise ValueError(f"unsupported Feature Artifact type: {artifact.feature_id}")
    if (
        artifact.model_id != SIMPLE_MOVING_AVERAGE_MODEL_ID
        or artifact.model_version != SimpleMovingAverageComputer.model_version
    ):
        raise ValueError("Moving Average model identity mismatch")
    parameters = dict(artifact.configuration_parameters)
    if set(parameters) != {"window"}:
        raise ValueError("Moving Average configuration fields mismatch")
    try:
        window = int(parameters["window"])
    except ValueError as exc:
        raise ValueError("Moving Average window must be an integer") from exc
    if str(window) != parameters["window"]:
        raise ValueError("Moving Average window is not canonical")
    MovingAverageConfiguration(
        configuration_id=artifact.configuration_id,
        configuration_version=artifact.configuration_version,
        window=window,
        content_hash=artifact.configuration_hash,
    )
    observations = _moving_average_observations(artifact)
    typed = tuple(item for item in observations if isinstance(item, MovingAverageObservation))
    symbols = {item.symbol for item in typed}
    if len(symbols) > 1:
        raise ValueError("Moving Average Artifact must contain one symbol")
    dates = tuple(item.market_date for item in typed)
    if len(dates) != len(set(dates)) or dates != tuple(sorted(dates)):
        raise ValueError("Moving Average Artifact dates must be sorted and unique")
    if tuple(item.observations_seen for item in typed) != tuple(
        range(1, len(typed) + 1)
    ):
        raise ValueError("Moving Average observation sequence mismatch")
    if any(item.window != window for item in typed):
        raise ValueError("Moving Average observation window mismatch")
    if any(item.source_available_at > artifact.as_of_time for item in typed):
        raise ValueError("Moving Average source availability exceeds as_of_time")
    if any(item.available_at > artifact.as_of_time for item in typed):
        raise ValueError("Moving Average feature availability exceeds as_of_time")
    if any(item.market_date > artifact.as_of_time.date() for item in typed):
        raise ValueError("Moving Average market_date exceeds as_of_time")
    expected_score = typed[-1].value if typed else None
    if artifact.score != expected_score:
        raise ValueError("Moving Average Artifact score does not match final observation")
    if artifact.limitations != ("NO_TRADING_AUTHORITY", "RESEARCH_ONLY"):
        raise ValueError("Moving Average Artifact authority limitations mismatch")


def _manifest(artifact: FeatureArtifact) -> dict[str, Any]:
    return {
        "schema_version": FEATURE_ARTIFACT_PACKAGE_SCHEMA,
        "artifact_id": str(artifact.artifact_id),
        "content_hash": artifact.content_hash,
        "feature_id": str(artifact.feature_id),
        "dataset_id": str(artifact.dataset_id),
        "model_id": str(artifact.model_id),
        "model_version": artifact.model_version,
        "configuration_id": str(artifact.configuration_id),
        "configuration_hash": artifact.configuration_hash,
        "data_availability": artifact.data_availability.value,
        "state": artifact.state,
        "validation_status": artifact.validation_status,
        "required_artifacts": sorted(FEATURE_ARTIFACT_FILES),
        "trading_authority": "NO_TRADING_AUTHORITY",
    }


def _verify_files(root: Path) -> None:
    if not root.is_dir() or {item.name for item in root.iterdir()} != set(
        FEATURE_ARTIFACT_FILES
    ):
        raise ValueError("Feature Artifact exact file set mismatch")
    if any(not item.is_file() or item.is_symlink() for item in root.iterdir()):
        raise ValueError("Feature Artifact exact file set contains a non-regular file")
    checksums = _read_object(root / "SHA256SUMS.json")
    expected = set(FEATURE_ARTIFACT_FILES) - {"SHA256SUMS.json"}
    if set(checksums) != expected:
        raise ValueError("Feature Artifact checksum coverage mismatch")
    for name, expected_hash in checksums.items():
        if not isinstance(expected_hash, str) or _file_hash(root / name) != expected_hash:
            raise ValueError(f"Feature Artifact checksum mismatch: {name}")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _read_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Feature Artifact JSON: {path.name}") from exc
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _canonical_observation(value: object) -> Mapping[str, Any]:
    method = getattr(value, "to_canonical_dict", None)
    if method is None or not callable(method):
        raise TypeError("Feature Artifact observations must be canonicalizable")
    payload = method()
    if not isinstance(payload, Mapping) or any(not isinstance(key, str) for key in payload):
        raise TypeError("Feature Artifact observation must encode an object")
    return payload


def _text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _text_array(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    return tuple(value)


def _object_array(
    value: object,
    label: str,
    *,
    expected_keys: set[str] | None,
) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be an object array")
    result: list[dict[str, object]] = []
    for item in value:
        if any(not isinstance(key, str) for key in item):
            raise ValueError(f"{label} object keys must be strings")
        if expected_keys is not None and set(item) != expected_keys:
            raise ValueError(f"{label} object fields mismatch")
        result.append(item)
    return tuple(result)


def _decimal(value: object, label: str) -> Decimal:
    text = _text(value, label)
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{label} must be a Decimal string") from exc


def _datetime(value: object, label: str) -> datetime:
    text = _text(value, label)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO datetime") from exc


__all__ = [
    "FEATURE_ARTIFACT_FILES",
    "FEATURE_ARTIFACT_PACKAGE_SCHEMA",
    "FEATURE_ARTIFACT_SCHEMA",
    "VerifiedFeatureArtifact",
    "bind_feature_artifact_identity",
    "feature_artifact_payload",
    "feature_artifact_to_dict",
    "load_verified_feature_artifact",
    "publish_feature_artifact",
    "replay_feature_artifact",
    "verify_feature_artifact_identity",
]
