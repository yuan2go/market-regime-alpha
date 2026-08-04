"""Atomic publication, strict reading and replay of comparison reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId, DatasetId, ModelId
from market_regime_alpha.migration.comparison.contracts import (
    MODEL_COMPARISON_REPORT_SCHEMA,
    ComparisonObservation,
    ComparisonPolicy,
    DifferenceClassification,
    FieldDifference,
    ModelComparisonOutput,
    ModelComparisonReport,
    NumericDifference,
    SemanticDifference,
    decimal_from_string,
)
from market_regime_alpha.migration.comparison.harness import (
    DifferentialTestHarness,
    LegacyFeatureAdapter,
)
from market_regime_alpha.features.model_contracts import FeatureComputer
from market_regime_alpha.migration.legacy.normalization.market_data import (
    NormalizedFeatureDataset,
)


MODEL_COMPARISON_REPORT_PACKAGE_SCHEMA = "model-comparison-report-package-v1"
MODEL_COMPARISON_REPORT_FILES = ("SHA256SUMS.json", "manifest.json", "report.json")


@dataclass(frozen=True, slots=True)
class VerifiedModelComparisonReport:
    root: Path
    report: ModelComparisonReport
    checksums_hash: str


def publish_model_comparison_report(
    *,
    root: Path,
    report: ModelComparisonReport,
) -> Path:
    report.verify_content_identity()
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(report.comparison_id)
    if final.exists():
        existing = load_verified_model_comparison_report(final)
        if existing.report.semantic_payload() != report.semantic_payload():
            raise FileExistsError(f"conflicting Model Comparison report exists: {final}")
        return final

    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    try:
        _write_json(stage / "report.json", report.to_canonical_dict())
        _write_json(stage / "manifest.json", _manifest(report))
        _write_json(
            stage / "SHA256SUMS.json",
            {
                name: _file_hash(stage / name)
                for name in MODEL_COMPARISON_REPORT_FILES
                if name != "SHA256SUMS.json"
            },
        )
        if {item.name for item in stage.iterdir()} != set(
            MODEL_COMPARISON_REPORT_FILES
        ):
            raise RuntimeError("Model Comparison staging exact file set mismatch")
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def load_verified_model_comparison_report(
    path: Path,
) -> VerifiedModelComparisonReport:
    root = path.resolve()
    _verify_files(root)
    report = _report_from_dict(_read_object(root / "report.json"))
    report.verify_content_identity()
    if _read_object(root / "manifest.json") != _manifest(report):
        raise ValueError("Model Comparison manifest is not reconstructible")
    if root.name != str(report.comparison_id):
        raise ValueError("Model Comparison directory identity mismatch")
    return VerifiedModelComparisonReport(
        root=root,
        report=report,
        checksums_hash=_file_hash(root / "SHA256SUMS.json"),
    )


def replay_model_comparison_report(
    path: Path,
    *,
    dataset: NormalizedFeatureDataset,
    legacy_adapter: LegacyFeatureAdapter,
    canonical_model: FeatureComputer,
    policy: ComparisonPolicy,
) -> VerifiedModelComparisonReport:
    verified = load_verified_model_comparison_report(path)
    replayed = DifferentialTestHarness().compare(
        dataset=dataset,
        legacy_adapter=legacy_adapter,
        canonical_model=canonical_model,
        policy=policy,
        created_at=verified.report.created_at,
    )
    if replayed.to_canonical_dict() != verified.report.to_canonical_dict():
        raise ValueError("Model Comparison replay differs from stored report")
    return verified


def _manifest(report: ModelComparisonReport) -> dict[str, Any]:
    return {
        "schema_version": MODEL_COMPARISON_REPORT_PACKAGE_SCHEMA,
        "comparison_id": str(report.comparison_id),
        "report_hash": report.report_hash,
        "policy_id": str(report.policy_id),
        "policy_hash": report.policy_hash,
        "legacy_model_id": str(report.legacy_model_id),
        "legacy_model_version": report.legacy_model_version,
        "canonical_model_id": str(report.canonical_model_id),
        "canonical_model_version": report.canonical_model_version,
        "dataset_id": str(report.dataset_id),
        "input_hash": report.input_hash,
        "difference_classification": report.difference_classification.value,
        "required_artifacts": sorted(MODEL_COMPARISON_REPORT_FILES),
        "trading_authority": "NO_TRADING_AUTHORITY",
    }


def _report_from_dict(payload: Mapping[str, object]) -> ModelComparisonReport:
    expected = {
        "comparison_id",
        "report_hash",
        "created_at",
        "schema_version",
        "policy_id",
        "policy_hash",
        "legacy_model_id",
        "legacy_model_version",
        "canonical_model_id",
        "canonical_model_version",
        "dataset_id",
        "as_of_time",
        "input_hash",
        "legacy_output",
        "canonical_output",
        "field_differences",
        "numeric_differences",
        "semantic_differences",
        "difference_classification",
        "expected_difference",
        "unexpected_difference",
    }
    if set(payload) != expected:
        raise ValueError("ModelComparisonReport fields mismatch")
    if _text(payload["schema_version"], "schema_version") != (
        MODEL_COMPARISON_REPORT_SCHEMA
    ):
        raise ValueError("unsupported Model Comparison report schema")
    return ModelComparisonReport(
        comparison_id=ArtifactId(
            _text(payload["comparison_id"], "comparison_id")
        ),
        report_hash=_text(payload["report_hash"], "report_hash"),
        policy_id=ArtifactId(_text(payload["policy_id"], "policy_id")),
        policy_hash=_text(payload["policy_hash"], "policy_hash"),
        legacy_model_id=ModelId(
            _text(payload["legacy_model_id"], "legacy_model_id")
        ),
        legacy_model_version=_text(
            payload["legacy_model_version"], "legacy_model_version"
        ),
        canonical_model_id=ModelId(
            _text(payload["canonical_model_id"], "canonical_model_id")
        ),
        canonical_model_version=_text(
            payload["canonical_model_version"], "canonical_model_version"
        ),
        dataset_id=DatasetId(_text(payload["dataset_id"], "dataset_id")),
        as_of_time=_datetime(payload["as_of_time"], "as_of_time"),
        input_hash=_text(payload["input_hash"], "input_hash"),
        legacy_output=_output_from_dict(
            _object(payload["legacy_output"], "legacy_output")
        ),
        canonical_output=_output_from_dict(
            _object(payload["canonical_output"], "canonical_output")
        ),
        field_differences=tuple(
            FieldDifference(
                path=_text(item["path"], "field path"),
                legacy_value=_optional_text(item["legacy_value"], "legacy_value"),
                canonical_value=_optional_text(
                    item["canonical_value"], "canonical_value"
                ),
            )
            for item in _object_array(
                payload["field_differences"],
                "field_differences",
                {"path", "legacy_value", "canonical_value"},
            )
        ),
        numeric_differences=tuple(
            NumericDifference(
                path=_text(item["path"], "numeric path"),
                legacy_value=decimal_from_string(
                    item["legacy_value"], "legacy_value"
                ),
                canonical_value=decimal_from_string(
                    item["canonical_value"], "canonical_value"
                ),
                absolute_difference=decimal_from_string(
                    item["absolute_difference"], "absolute_difference"
                ),
                tolerance=(
                    decimal_from_string(item["tolerance"], "tolerance")
                    if item["tolerance"] is not None
                    else None
                ),
                within_tolerance=_boolean(
                    item["within_tolerance"], "within_tolerance"
                ),
            )
            for item in _object_array(
                payload["numeric_differences"],
                "numeric_differences",
                {
                    "path",
                    "legacy_value",
                    "canonical_value",
                    "absolute_difference",
                    "tolerance",
                    "within_tolerance",
                },
            )
        ),
        semantic_differences=tuple(
            SemanticDifference(
                rule_id=_text(item["rule_id"], "rule_id"),
                difference_kind=_text(
                    item["difference_kind"], "difference_kind"
                ),
                path=_text(item["path"], "semantic path"),
                legacy_value=_optional_text(item["legacy_value"], "legacy_value"),
                canonical_value=_optional_text(
                    item["canonical_value"], "canonical_value"
                ),
            )
            for item in _object_array(
                payload["semantic_differences"],
                "semantic_differences",
                {
                    "rule_id",
                    "difference_kind",
                    "path",
                    "legacy_value",
                    "canonical_value",
                },
            )
        ),
        difference_classification=DifferenceClassification(
            _text(
                payload["difference_classification"],
                "difference_classification",
            )
        ),
        expected_difference=_boolean(
            payload["expected_difference"], "expected_difference"
        ),
        unexpected_difference=_boolean(
            payload["unexpected_difference"], "unexpected_difference"
        ),
        created_at=_datetime(payload["created_at"], "created_at"),
    )


def _output_from_dict(payload: Mapping[str, object]) -> ModelComparisonOutput:
    expected = {
        "model_id",
        "model_version",
        "state",
        "score",
        "observations",
        "reason_codes",
        "limitations",
        "exception_type",
        "exception_message",
    }
    if set(payload) != expected:
        raise ValueError("ModelComparisonOutput fields mismatch")
    score = payload["score"]
    return ModelComparisonOutput(
        model_id=ModelId(_text(payload["model_id"], "model_id")),
        model_version=_text(payload["model_version"], "model_version"),
        state=_text(payload["state"], "state"),
        score=decimal_from_string(score, "score") if score is not None else None,
        observations=tuple(
            ComparisonObservation(
                key=_text(item["key"], "observation key"),
                value=(
                    decimal_from_string(item["value"], "observation value")
                    if item["value"] is not None
                    else None
                ),
                missing_reason=_optional_text(
                    item["missing_reason"], "missing_reason"
                ),
            )
            for item in _object_array(
                payload["observations"],
                "observations",
                {"key", "value", "missing_reason"},
            )
        ),
        reason_codes=_text_array(payload["reason_codes"], "reason_codes"),
        limitations=_text_array(payload["limitations"], "limitations"),
        exception_type=_optional_text(payload["exception_type"], "exception_type"),
        exception_message=_optional_text(
            payload["exception_message"], "exception_message"
        ),
    )


def _verify_files(root: Path) -> None:
    if not root.is_dir() or {item.name for item in root.iterdir()} != set(
        MODEL_COMPARISON_REPORT_FILES
    ):
        raise ValueError("Model Comparison report exact file set mismatch")
    if any(not item.is_file() or item.is_symlink() for item in root.iterdir()):
        raise ValueError("Model Comparison exact file set contains a non-regular file")
    checksums = _read_object(root / "SHA256SUMS.json")
    expected = set(MODEL_COMPARISON_REPORT_FILES) - {"SHA256SUMS.json"}
    if set(checksums) != expected:
        raise ValueError("Model Comparison checksum coverage mismatch")
    for name, expected_hash in checksums.items():
        if not isinstance(expected_hash, str) or _file_hash(root / name) != expected_hash:
            raise ValueError(f"Model Comparison checksum mismatch: {name}")


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
        raise ValueError(f"invalid Model Comparison JSON: {path.name}") from exc
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return value


def _object_array(
    value: object,
    label: str,
    expected_keys: set[str],
) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be an object array")
    result = []
    for item in value:
        if any(not isinstance(key, str) for key in item) or set(item) != expected_keys:
            raise ValueError(f"{label} object fields mismatch")
        result.append(item)
    return tuple(result)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _optional_text(value: object, label: str) -> str | None:
    return _text(value, label) if value is not None else None


def _text_array(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    return tuple(value)


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _datetime(value: object, label: str) -> datetime:
    text = _text(value, label)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO datetime") from exc


__all__ = [
    "MODEL_COMPARISON_REPORT_FILES",
    "MODEL_COMPARISON_REPORT_PACKAGE_SCHEMA",
    "VerifiedModelComparisonReport",
    "load_verified_model_comparison_report",
    "publish_model_comparison_report",
    "replay_model_comparison_report",
]
