"""Atomic, content-hashed, non-overwriting evidence artifacts for WP-3 runs."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
import shutil
from typing import Any, Mapping

from market_regime_alpha.core.identity import StableId
from market_regime_alpha.core.time import SemanticTime


SUCCESS_FILENAMES = frozenset(
    {
        "manifest.json",
        "provider_selection.json",
        "source_artifacts.json",
        "quality.json",
        "candidate_panel_summary.json",
        "b0_b1_evaluation.json",
        "limitations.json",
        "report.md",
        "SHA256SUMS.json",
    }
)
FAILURE_FILENAMES = frozenset(
    {"manifest.json", "failure.json", "SHA256SUMS.json"}
)


class WP3RunArtifactErrorCode(str, Enum):
    """Stable artifact-publication failures."""

    ALREADY_EXISTS = "WP3_RUN_ARTIFACT_ALREADY_EXISTS"
    INCOMPLETE = "WP3_RUN_ARTIFACT_INCOMPLETE"


class WP3RunArtifactAlreadyExistsError(FileExistsError):
    """The requested final or staging run directory already exists."""

    code = WP3RunArtifactErrorCode.ALREADY_EXISTS


class WP3RunArtifactIncompleteError(RuntimeError):
    """The owned staging directory does not contain the exact artifact set."""

    code = WP3RunArtifactErrorCode.INCOMPLETE


@dataclass(frozen=True, slots=True)
class WP3RunArtifactPayload:
    """JSON-ready successful WP-3 evidence plus a Markdown audit report."""

    manifest: Mapping[str, Any]
    provider_selection: Any
    source_artifacts: Any
    quality: Any
    candidate_panel_summary: Any
    b0_b1_evaluation: Any
    limitations: Any
    report: str

    def __post_init__(self) -> None:
        eligibility = _enum_value(self.manifest.get("data_eligibility"))
        if eligibility not in {"EXPLORATORY", "REHEARSAL"}:
            raise ValueError("successful WP-3 artifacts require EXPLORATORY or REHEARSAL data")
        if not isinstance(self.report, str) or not self.report.strip():
            raise ValueError("report must be non-empty Markdown")


@dataclass(frozen=True, slots=True)
class WP3FailureArtifactPayload:
    """JSON-ready failed WP-3 attempt without Candidate evaluation output."""

    manifest: Mapping[str, Any]
    failure: Any

    def __post_init__(self) -> None:
        if _enum_value(self.manifest.get("data_eligibility")) == "FORMAL_RESEARCH":
            raise ValueError("WP-3 failure artifacts cannot claim FORMAL_RESEARCH")


def write_wp3_candidate_run(
    *,
    root: str | Path,
    run_id: str,
    payload: WP3RunArtifactPayload,
) -> Path:
    """Publish a successful run through one validated staging-directory rename."""

    _validate_run_id(run_id)
    _validate_manifest_run_id(payload.manifest, run_id)
    root_path = Path(root)
    final, stage = _reserve_paths(root_path, run_id)
    stage.mkdir(parents=True)
    try:
        values = {
            "provider_selection.json": payload.provider_selection,
            "source_artifacts.json": payload.source_artifacts,
            "quality.json": payload.quality,
            "candidate_panel_summary.json": payload.candidate_panel_summary,
            "b0_b1_evaluation.json": payload.b0_b1_evaluation,
            "limitations.json": payload.limitations,
        }
        for filename, value in values.items():
            _write_json(stage / filename, value)
        _write_report(stage / "report.md", payload.report)

        payload_hashes = {
            filename: _content_hash(stage / filename)
            for filename in sorted((*values, "report.md"))
        }
        manifest = {
            **dict(payload.manifest),
            "artifacts": payload_hashes,
            "checksum_file": "SHA256SUMS.json",
        }
        _write_json(stage / "manifest.json", manifest)
        checksums = {
            path.name: _content_hash(path)
            for path in sorted(stage.iterdir(), key=lambda item: item.name)
        }
        _write_json(stage / "SHA256SUMS.json", checksums)
        _validate_staging_set(stage, SUCCESS_FILENAMES)
        _publish(stage=stage, final=final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def write_wp3_candidate_failure(
    *,
    root: str | Path,
    run_id: str,
    payload: WP3FailureArtifactPayload,
) -> Path:
    """Publish a failed attempt without producing Candidate evaluation artifacts."""

    _validate_run_id(run_id)
    _validate_manifest_run_id(payload.manifest, run_id)
    root_path = Path(root)
    final, stage = _reserve_paths(root_path, run_id)
    stage.mkdir(parents=True)
    try:
        _write_json(stage / "failure.json", payload.failure)
        manifest = {
            **dict(payload.manifest),
            "artifacts": {"failure.json": _content_hash(stage / "failure.json")},
            "checksum_file": "SHA256SUMS.json",
        }
        _write_json(stage / "manifest.json", manifest)
        checksums = {
            path.name: _content_hash(path)
            for path in sorted(stage.iterdir(), key=lambda item: item.name)
        }
        _write_json(stage / "SHA256SUMS.json", checksums)
        _validate_staging_set(stage, FAILURE_FILENAMES)
        _publish(stage=stage, final=final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def _reserve_paths(root: Path, run_id: str) -> tuple[Path, Path]:
    final = root / run_id
    stage = root / f".{run_id}.staging"
    if final.exists() or stage.exists():
        raise WP3RunArtifactAlreadyExistsError(
            f"{WP3RunArtifactErrorCode.ALREADY_EXISTS.value}: run path exists: {final}"
        )
    return final, stage


def _publish(*, stage: Path, final: Path) -> None:
    if final.exists():
        raise WP3RunArtifactAlreadyExistsError(
            f"{WP3RunArtifactErrorCode.ALREADY_EXISTS.value}: run path exists: {final}"
        )
    stage.rename(final)


def _validate_staging_set(stage: Path, expected: frozenset[str]) -> None:
    actual = {path.name for path in stage.iterdir()}
    if actual != expected:
        raise WP3RunArtifactIncompleteError(
            f"{WP3RunArtifactErrorCode.INCOMPLETE.value}: expected {sorted(expected)}, "
            f"got {sorted(actual)}"
        )


def _validate_run_id(run_id: str) -> None:
    if (
        not isinstance(run_id, str)
        or not run_id.strip()
        or run_id != run_id.strip()
        or Path(run_id).name != run_id
        or run_id in {".", ".."}
    ):
        raise ValueError("run_id must be one non-empty path-safe name")


def _validate_manifest_run_id(manifest: Mapping[str, Any], run_id: str) -> None:
    if manifest.get("run_id") != run_id:
        raise ValueError("manifest run_id must match the output run_id")


def _write_report(path: Path, report: str) -> None:
    path.write_text(report.rstrip() + "\n", encoding="utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(
            _json_value(value),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _content_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, StableId):
        return str(value)
    if isinstance(value, SemanticTime):
        return value.isoformat()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_value(item) for item in value]
    return value
