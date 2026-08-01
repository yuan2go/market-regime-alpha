"""Atomic publisher, semantic reader and deterministic replay for Signal runs."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from market_regime_alpha.signals.engine import SignalRunArtifact, run_signal_model


SIGNAL_ARTIFACT_SCHEMA = "signal-run-package-v1"
SIGNAL_ARTIFACT_FILES = ("SHA256SUMS.json", "artifact.json", "manifest.json")


@dataclass(frozen=True, slots=True)
class VerifiedSignalRunArtifact:
    root: Path
    artifact: SignalRunArtifact
    checksums_hash: str


def publish_signal_run(*, root: Path, artifact: SignalRunArtifact) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(artifact.artifact_id)
    if final.exists():
        existing = load_verified_signal_run(final)
        if existing.artifact != artifact:
            raise FileExistsError(f"conflicting Signal Artifact exists: {final}")
        return final
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    try:
        _write_json(stage / "artifact.json", artifact.to_canonical_dict())
        _write_json(stage / "manifest.json", _manifest(artifact))
        _write_json(
            stage / "SHA256SUMS.json",
            {
                name: _file_hash(stage / name)
                for name in SIGNAL_ARTIFACT_FILES
                if name != "SHA256SUMS.json"
            },
        )
        if {item.name for item in stage.iterdir()} != set(SIGNAL_ARTIFACT_FILES):
            raise RuntimeError("Signal staging exact file set mismatch")
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def load_verified_signal_run(path: Path) -> VerifiedSignalRunArtifact:
    root = path.resolve()
    _verify_files(root)
    artifact = SignalRunArtifact.from_canonical_dict(
        _read_object(root / "artifact.json")
    )
    if _read_object(root / "manifest.json") != _manifest(artifact):
        raise ValueError("Signal manifest is not reconstructible")
    if root.name != str(artifact.artifact_id):
        raise ValueError("Signal directory identity mismatch")
    return VerifiedSignalRunArtifact(
        root=root,
        artifact=artifact,
        checksums_hash=_file_hash(root / "SHA256SUMS.json"),
    )


def replay_signal_run(path: Path) -> VerifiedSignalRunArtifact:
    verified = load_verified_signal_run(path)
    original = verified.artifact
    replayed = run_signal_model(
        candidate_set=original.candidate_set,
        configuration=original.configuration,
        observations=original.observations,
        decision_time=original.envelope.decision_time,
        created_at=original.envelope.created_at,
        code_revision=original.envelope.code_revision,
    )
    if replayed != original:
        raise ValueError("Signal replay differs from stored Artifact")
    return verified


def _manifest(artifact: SignalRunArtifact) -> dict[str, Any]:
    return {
        "schema_version": SIGNAL_ARTIFACT_SCHEMA,
        "artifact_id": str(artifact.artifact_id),
        "content_hash": artifact.envelope.content_hash,
        "configuration_id": str(artifact.configuration.configuration_id),
        "candidate_set_id": str(artifact.candidate_set.envelope.artifact_id),
        "snapshot_ids": [str(item.envelope.artifact_id) for item in artifact.snapshots],
        "required_artifacts": sorted(SIGNAL_ARTIFACT_FILES),
        "data_eligibility": artifact.envelope.data_eligibility.value,
        "formal_pit": artifact.envelope.formal_pit,
        "formal_oos_alpha": artifact.envelope.formal_oos_alpha,
        "trading_authority": artifact.envelope.trading_authority,
    }


def _verify_files(root: Path) -> None:
    if not root.is_dir() or {item.name for item in root.iterdir()} != set(
        SIGNAL_ARTIFACT_FILES
    ):
        raise ValueError("Signal exact file set mismatch")
    if any(not item.is_file() for item in root.iterdir()):
        raise ValueError("Signal exact file set contains a non-file")
    checksums = _read_object(root / "SHA256SUMS.json")
    expected = set(SIGNAL_ARTIFACT_FILES) - {"SHA256SUMS.json"}
    if set(checksums) != expected:
        raise ValueError("Signal checksum coverage mismatch")
    for name, expected_hash in checksums.items():
        if not isinstance(expected_hash, str) or _file_hash(root / name) != expected_hash:
            raise ValueError(f"Signal checksum mismatch: {name}")


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
        raise ValueError(f"invalid Signal JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"
