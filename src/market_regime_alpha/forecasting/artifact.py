"""Atomic publisher, semantic reader and replay for PathForecast Artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from market_regime_alpha.forecasting.path import PathForecastArtifact, build_path_forecast


PATH_FORECAST_ARTIFACT_SCHEMA = "path-forecast-package-v1"
PATH_FORECAST_ARTIFACT_FILES = ("SHA256SUMS.json", "artifact.json", "manifest.json")


@dataclass(frozen=True, slots=True)
class VerifiedPathForecastArtifact:
    root: Path
    artifact: PathForecastArtifact
    checksums_hash: str


def publish_path_forecast(*, root: Path, artifact: PathForecastArtifact) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(artifact.artifact_id)
    if final.exists():
        existing = load_verified_path_forecast(final)
        if existing.artifact != artifact:
            raise FileExistsError(f"conflicting PathForecast Artifact exists: {final}")
        return final
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    try:
        _write_json(stage / "artifact.json", artifact.to_canonical_dict())
        _write_json(stage / "manifest.json", _manifest(artifact))
        _write_json(
            stage / "SHA256SUMS.json",
            {
                name: _file_hash(stage / name)
                for name in PATH_FORECAST_ARTIFACT_FILES
                if name != "SHA256SUMS.json"
            },
        )
        if {item.name for item in stage.iterdir()} != set(PATH_FORECAST_ARTIFACT_FILES):
            raise RuntimeError("PathForecast staging exact file set mismatch")
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def load_verified_path_forecast(path: Path) -> VerifiedPathForecastArtifact:
    root = path.resolve()
    _verify_files(root)
    artifact = PathForecastArtifact.from_canonical_dict(
        _read_object(root / "artifact.json")
    )
    if _read_object(root / "manifest.json") != _manifest(artifact):
        raise ValueError("PathForecast manifest is not reconstructible")
    if root.name != str(artifact.artifact_id):
        raise ValueError("PathForecast directory identity mismatch")
    return VerifiedPathForecastArtifact(
        root=root,
        artifact=artifact,
        checksums_hash=_file_hash(root / "SHA256SUMS.json"),
    )


def replay_path_forecast(path: Path) -> VerifiedPathForecastArtifact:
    verified = load_verified_path_forecast(path)
    original = verified.artifact
    replayed = build_path_forecast(
        signal_snapshot=original.signal_snapshot,
        configuration=original.configuration,
        samples=original.samples,
        decision_time=original.forecast.envelope.decision_time,
        created_at=original.forecast.envelope.created_at,
        code_revision=original.forecast.envelope.code_revision,
    )
    if replayed != original:
        raise ValueError("PathForecast replay differs from stored Artifact")
    return verified


def _manifest(artifact: PathForecastArtifact) -> dict[str, Any]:
    forecast = artifact.forecast
    return {
        "schema_version": PATH_FORECAST_ARTIFACT_SCHEMA,
        "artifact_id": str(artifact.artifact_id),
        "content_hash": forecast.envelope.content_hash,
        "configuration_id": str(artifact.configuration.configuration_id),
        "signal_snapshot_id": str(artifact.signal_snapshot.envelope.artifact_id),
        "target_id": str(forecast.target_id),
        "forecast_status": forecast.forecast_status.value,
        "calibration_status": forecast.calibration_status.value,
        "required_artifacts": sorted(PATH_FORECAST_ARTIFACT_FILES),
        "data_eligibility": forecast.envelope.data_eligibility.value,
        "formal_pit": forecast.envelope.formal_pit,
        "formal_oos_alpha": forecast.envelope.formal_oos_alpha,
        "trading_authority": forecast.envelope.trading_authority,
    }


def _verify_files(root: Path) -> None:
    if not root.is_dir() or {item.name for item in root.iterdir()} != set(
        PATH_FORECAST_ARTIFACT_FILES
    ):
        raise ValueError("PathForecast exact file set mismatch")
    if any(not item.is_file() for item in root.iterdir()):
        raise ValueError("PathForecast exact file set contains a non-file")
    checksums = _read_object(root / "SHA256SUMS.json")
    expected = set(PATH_FORECAST_ARTIFACT_FILES) - {"SHA256SUMS.json"}
    if set(checksums) != expected:
        raise ValueError("PathForecast checksum coverage mismatch")
    for name, expected_hash in checksums.items():
        if not isinstance(expected_hash, str) or _file_hash(root / name) != expected_hash:
            raise ValueError(f"PathForecast checksum mismatch: {name}")


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


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid PathForecast JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"
