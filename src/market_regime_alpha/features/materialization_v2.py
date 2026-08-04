"""Feature Artifact V2 publication, deterministic materialization, and replay."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Callable, Mapping

from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    canonical_json,
    require_sha256,
    require_text,
)
from market_regime_alpha.features.spine import (
    FeatureConfiguration,
    FeatureDefinitionV2,
    FeatureSetConfiguration,
)
from market_regime_alpha.features.technical.observables import (
    compute_technical_feature,
    missing_technical_feature_computation,
)
from market_regime_alpha.features.v2_contracts import (
    FeatureArtifactV2,
    FeatureBundleArtifact,
    FeatureBundleReplayReport,
    FeatureBundleState,
    FeatureMaterializationReceipt,
    FeatureMaterializationStatus,
    _verified_dataset_membership,
)
from market_regime_alpha.market_data import (
    CanonicalMarketBar,
    Timeframe,
    VerifiedMarketDataDataset,
)
from market_regime_alpha.market_data.contracts import require_utc_second


@dataclass(frozen=True, slots=True)
class VerifiedFeatureArtifactV2:
    root: Path
    artifact: FeatureArtifactV2
    checksums_hash: str


@dataclass(frozen=True, slots=True)
class VerifiedFeatureBundleV2:
    root: Path
    artifact: FeatureBundleArtifact
    artifacts: tuple[VerifiedFeatureArtifactV2, ...]
    checksums_hash: str

    def find_value(
        self,
        *,
        symbol: str,
        feature_id: str,
        output_id: str,
    ) -> Any:
        matches = tuple(
            value
            for verified in self.artifacts
            if verified.artifact.symbol == symbol
            and verified.artifact.feature_id == feature_id
            for value in verified.artifact.values
            if value.output_id == output_id
        )
        if len(matches) != 1:
            raise ValueError("Feature Bundle value lookup is not unique")
        return matches[0]


FailureInjector = Callable[[str], None]


def publish_feature_artifact_v2(
    *,
    root: Path,
    artifact: FeatureArtifactV2,
    failure_injector: FailureInjector | None = None,
) -> Path:
    artifact.verify_identity()
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(artifact.artifact_id)
    if final.exists():
        existing = load_verified_feature_artifact_v2(final)
        if existing.artifact.to_canonical_dict() != artifact.to_canonical_dict():
            raise FileExistsError(f"conflicting Feature Artifact V2 exists: {final}")
        return final
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    installed = False
    try:
        _write_json(stage / "artifact.json", artifact.to_canonical_dict())
        _write_json(stage / "definition.json", artifact.definition.to_canonical_dict())
        _write_json(
            stage / "configuration.json", artifact.configuration.to_canonical_dict()
        )
        checksums = {
            name: _file_hash(stage / name)
            for name in ("artifact.json", "configuration.json", "definition.json")
        }
        _write_json(stage / "SHA256SUMS.json", checksums)
        _fsync_directory(stage)
        _load_verified_feature_artifact_v2(stage, enforce_directory_identity=False)
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


def load_verified_feature_artifact_v2(path: Path) -> VerifiedFeatureArtifactV2:
    return _load_verified_feature_artifact_v2(path, enforce_directory_identity=True)


def _load_verified_feature_artifact_v2(
    path: Path, *, enforce_directory_identity: bool
) -> VerifiedFeatureArtifactV2:
    root = path.resolve()
    expected_files = {
        "SHA256SUMS.json",
        "artifact.json",
        "configuration.json",
        "definition.json",
    }
    _require_exact_files(root, expected_files, "Feature Artifact V2")
    checksums = _read_checksum_index(root / "SHA256SUMS.json", "Feature Artifact V2")
    if set(checksums) != expected_files - {"SHA256SUMS.json"}:
        raise ValueError("Feature Artifact V2 checksum index mismatch")
    _verify_checksums(root, checksums, "Feature Artifact V2")
    definition = FeatureDefinitionV2.from_canonical_dict(
        _read_object(root / "definition.json", "Feature Artifact V2 definition")
    )
    configuration = FeatureConfiguration.from_canonical_dict(
        _read_object(root / "configuration.json", "Feature Artifact V2 configuration")
    )
    artifact = FeatureArtifactV2.from_canonical_dict(
        _read_object(root / "artifact.json", "Feature Artifact V2 artifact"),
        definition=definition,
        configuration=configuration,
    )
    if enforce_directory_identity and root.name != str(artifact.artifact_id):
        raise ValueError("Feature Artifact V2 directory identity mismatch")
    return VerifiedFeatureArtifactV2(
        root=root,
        artifact=artifact,
        checksums_hash=canonical_hash(dict(sorted(checksums.items()))),
    )


def publish_feature_bundle_v2(
    *,
    root: Path,
    artifact_root: Path,
    bundle: FeatureBundleArtifact,
    failure_injector: FailureInjector | None = None,
) -> Path:
    bundle.verify_identity()
    for reference in bundle.feature_artifact_references:
        package = artifact_root / str(reference.artifact_id)
        if not package.is_dir():
            raise ValueError("referenced Feature Artifact is missing")
        verified = load_verified_feature_artifact_v2(package)
        _verify_reference(verified=verified, reference=reference)
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(bundle.bundle_id)
    if final.exists():
        existing = load_verified_feature_bundle_v2(final, artifact_root=artifact_root)
        if existing.artifact.to_canonical_dict() != bundle.to_canonical_dict():
            raise FileExistsError(f"conflicting Feature Bundle exists: {final}")
        return final
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    installed = False
    try:
        _write_json(stage / "artifact.json", bundle.to_canonical_dict())
        _write_json(stage / "feature-set.json", bundle.feature_set.to_canonical_dict())
        checksums = {
            name: _file_hash(stage / name)
            for name in ("artifact.json", "feature-set.json")
        }
        _write_json(stage / "SHA256SUMS.json", checksums)
        _fsync_directory(stage)
        _load_verified_feature_bundle_v2(
            stage,
            artifact_root=artifact_root,
            enforce_directory_identity=False,
        )
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


def load_verified_feature_bundle_v2(
    path: Path, *, artifact_root: Path
) -> VerifiedFeatureBundleV2:
    return _load_verified_feature_bundle_v2(
        path,
        artifact_root=artifact_root,
        enforce_directory_identity=True,
    )


def _load_verified_feature_bundle_v2(
    path: Path,
    *,
    artifact_root: Path,
    enforce_directory_identity: bool,
) -> VerifiedFeatureBundleV2:
    root = path.resolve()
    expected_files = {"SHA256SUMS.json", "artifact.json", "feature-set.json"}
    _require_exact_files(root, expected_files, "Feature Bundle")
    checksums = _read_checksum_index(root / "SHA256SUMS.json", "Feature Bundle")
    if set(checksums) != expected_files - {"SHA256SUMS.json"}:
        raise ValueError("Feature Bundle checksum index mismatch")
    _verify_checksums(root, checksums, "Feature Bundle")
    feature_set = FeatureSetConfiguration.from_canonical_dict(
        _read_object(root / "feature-set.json", "Feature Bundle Feature Set")
    )
    bundle = FeatureBundleArtifact.from_canonical_dict(
        _read_object(root / "artifact.json", "Feature Bundle artifact"),
        feature_set=feature_set,
    )
    if enforce_directory_identity and root.name != str(bundle.bundle_id):
        raise ValueError("Feature Bundle directory identity mismatch")
    artifacts: list[VerifiedFeatureArtifactV2] = []
    for reference in bundle.feature_artifact_references:
        package = artifact_root / str(reference.artifact_id)
        if not package.is_dir():
            raise ValueError("referenced Feature Artifact is missing")
        verified = load_verified_feature_artifact_v2(package)
        _verify_reference(verified=verified, reference=reference)
        artifacts.append(verified)
    return VerifiedFeatureBundleV2(
        root=root,
        artifact=bundle,
        artifacts=tuple(artifacts),
        checksums_hash=canonical_hash(dict(sorted(checksums.items()))),
    )


class FeatureMaterializationRunner:
    """Materialize a controlled Feature Set without network or execution access."""

    def __init__(self, *, max_workers: int = 1) -> None:
        if isinstance(max_workers, bool) or not 1 <= max_workers <= 8:
            raise ValueError("max_workers must be between one and eight")
        self._max_workers = max_workers

    def run(
        self,
        *,
        verified_dataset: VerifiedMarketDataDataset,
        feature_set: FeatureSetConfiguration,
        decision_time: datetime,
        created_at: datetime,
        selected_symbols: tuple[str, ...],
        code_revision: str,
        output_root: Path,
        idempotency_key: str,
        resume: bool,
    ) -> FeatureMaterializationReceipt:
        if not isinstance(decision_time, datetime) or not isinstance(created_at, datetime):
            raise TypeError("decision_time and created_at must be datetime")
        require_utc_second("decision_time", decision_time)
        require_utc_second("created_at", created_at)
        if not isinstance(resume, bool):
            raise TypeError("resume must be boolean")
        require_text("code_revision", code_revision)
        require_text("idempotency_key", idempotency_key)
        feature_set.verify_identity()
        dataset = verified_dataset.artifact
        dataset.verify_identity()
        if decision_time != dataset.decision_time:
            raise ValueError("Feature materialization DecisionTime differs from dataset")
        selected_symbols = tuple(sorted(selected_symbols))
        if not selected_symbols or len(selected_symbols) != len(set(selected_symbols)):
            raise ValueError("selected symbols must be non-empty and unique")
        if not set(selected_symbols).issubset(dataset.coverage.observed_symbols):
            raise ValueError("selected symbols are not covered by Market Data Dataset")
        command_hash = canonical_hash(
            {
                "schema_version": "feature-materialization-command-v1",
                "dataset_id": str(dataset.dataset_id),
                "dataset_hash": dataset.content_hash,
                "feature_set_id": str(feature_set.feature_set_id),
                "feature_set_hash": feature_set.content_hash,
                "decision_time": decision_time.isoformat(),
                "created_at": created_at.isoformat(),
                "selected_symbols": list(selected_symbols),
                "code_revision": code_revision,
            }
        )
        command_path = _command_path(output_root, idempotency_key)
        if command_path.exists():
            payload = _read_object(command_path, "Feature materialization command")
            if payload.get("command_hash") != command_hash:
                raise ValueError("idempotency key semantic conflict")
            raw_receipt = payload.get("receipt")
            if not isinstance(raw_receipt, dict):
                raise ValueError("Feature materialization command receipt is invalid")
            receipt = FeatureMaterializationReceipt.from_canonical_dict(raw_receipt)
            bundle_path = output_root / receipt.bundle_locator
            verified = load_verified_feature_bundle_v2(
                bundle_path,
                artifact_root=output_root / "feature-artifacts",
            )
            if verified.artifact.content_hash != receipt.bundle_hash:
                raise ValueError("Feature materialization command Bundle mismatch")
            return receipt
        artifacts = self._compute_artifacts(
            verified_dataset=verified_dataset,
            feature_set=feature_set,
            decision_time=decision_time,
            created_at=created_at,
            selected_symbols=selected_symbols,
        )
        artifact_root = output_root / "feature-artifacts"
        for artifact in artifacts:
            publish_feature_artifact_v2(root=artifact_root, artifact=artifact)
        bundle = FeatureBundleArtifact.create(
            dataset=dataset,
            feature_set=feature_set,
            artifacts=artifacts,
            selected_symbols=selected_symbols,
            created_at=created_at,
            code_revision=code_revision,
        )
        publish_feature_bundle_v2(
            root=output_root / "feature-bundles",
            artifact_root=artifact_root,
            bundle=bundle,
        )
        receipt = FeatureMaterializationReceipt.create(
            command_hash=command_hash,
            bundle=bundle,
        )
        _write_command(
            path=command_path,
            payload={
                "schema_version": "feature-materialization-command-index-v1",
                "idempotency_key_hash": canonical_hash(
                    {"idempotency_key": idempotency_key}
                ),
                "command_hash": command_hash,
                "receipt": receipt.to_canonical_dict(),
            },
        )
        return receipt

    def _compute_artifacts(
        self,
        *,
        verified_dataset: VerifiedMarketDataDataset,
        feature_set: FeatureSetConfiguration,
        decision_time: datetime,
        created_at: datetime,
        selected_symbols: tuple[str, ...],
    ) -> tuple[FeatureArtifactV2, ...]:
        definitions = {item.feature_id: item for item in feature_set.definitions}
        configurations = {
            item.feature_id: item for item in feature_set.configurations
        }
        membership = _verified_dataset_membership(verified_dataset.artifact)
        bars_by_scope: dict[
            tuple[str, Timeframe], tuple[CanonicalMarketBar, ...]
        ] = {}
        grouped: dict[tuple[str, Timeframe], list[CanonicalMarketBar]] = {}
        for bar in verified_dataset.bars:
            grouped.setdefault((bar.symbol, bar.timeframe), []).append(bar)
        bars_by_scope = {
            key: tuple(values) for key, values in grouped.items()
        }
        tasks = tuple(
            (symbol, feature_id)
            for symbol in selected_symbols
            for feature_id in sorted(definitions)
        )

        def compute(task: tuple[str, str]) -> FeatureArtifactV2:
            symbol, feature_id = task
            definition = definitions[feature_id]
            configuration = configurations[feature_id]
            raw_timeframe = configuration.parameter_map().get("selected_timeframe")
            if raw_timeframe is None:
                raise ValueError("Feature Configuration lacks selected_timeframe")
            timeframe = Timeframe(raw_timeframe)
            if timeframe not in definition.supported_timeframes:
                raise ValueError("configured timeframe is unsupported by definition")
            input_bars = bars_by_scope.get((symbol, timeframe), ())
            output_ids = tuple(item.output_id for item in definition.output_schema)
            computation = (
                compute_technical_feature(
                    feature_id=feature_id,
                    bars=input_bars,
                    configuration=configuration,
                    decision_time=decision_time,
                )
                if input_bars
                else missing_technical_feature_computation(
                    feature_id=feature_id,
                    symbol=symbol,
                    timeframe=timeframe,
                    available_at=decision_time,
                    configuration=configuration,
                    output_ids=output_ids,
                    reason_code="DATA_UNAVAILABLE_TIMEFRAME",
                )
            )
            return FeatureArtifactV2.create(
                definition=definition,
                configuration=configuration,
                dataset=verified_dataset.artifact,
                computation=computation,
                input_bars=input_bars,
                created_at=created_at,
                _membership=membership,
            )

        if self._max_workers == 1:
            artifacts = tuple(compute(task) for task in tasks)
        else:
            with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
                artifacts = tuple(executor.map(compute, tasks))
        return tuple(
            sorted(
                artifacts,
                key=lambda item: (item.feature_id, item.symbol, item.timeframe.value),
            )
        )


def replay_feature_bundle_v2(
    *,
    bundle_path: Path,
    artifact_root: Path,
    verified_dataset: VerifiedMarketDataDataset,
    report_root: Path | None = None,
) -> FeatureBundleReplayReport:
    verified = load_verified_feature_bundle_v2(
        bundle_path,
        artifact_root=artifact_root,
    )
    original = verified.artifact
    if (
        original.dataset_id != verified_dataset.artifact.dataset_id
        or original.dataset_hash != verified_dataset.artifact.content_hash
    ):
        raise ValueError("Feature replay Market Data Dataset mismatch")
    replayed_artifacts = FeatureMaterializationRunner(max_workers=1)._compute_artifacts(
        verified_dataset=verified_dataset,
        feature_set=original.feature_set,
        decision_time=original.decision_time,
        created_at=original.created_at,
        selected_symbols=original.symbols,
    )
    replayed_bundle = FeatureBundleArtifact.create(
        dataset=verified_dataset.artifact,
        feature_set=original.feature_set,
        artifacts=replayed_artifacts,
        selected_symbols=original.symbols,
        created_at=original.created_at,
        code_revision=original.code_revision,
    )
    original_hashes = tuple(
        item.artifact.content_hash for item in verified.artifacts
    )
    replayed_hashes = tuple(item.content_hash for item in replayed_artifacts)
    report = FeatureBundleReplayReport.create(
        original_bundle_hash=original.content_hash,
        replayed_bundle_hash=replayed_bundle.content_hash,
        original_artifact_hashes=original_hashes,
        replayed_artifact_hashes=replayed_hashes,
    )
    if not report.semantic_match:
        raise ValueError("Feature Bundle replay semantic mismatch")
    if report_root is not None:
        publish_feature_replay_report(root=report_root, report=report)
    return report


def publish_feature_replay_report(
    *,
    root: Path,
    report: FeatureBundleReplayReport,
    failure_injector: FailureInjector | None = None,
) -> Path:
    report.verify_identity()
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(report.report_id)
    if final.exists():
        existing = load_verified_feature_replay_report(final)
        if existing.to_canonical_dict() != report.to_canonical_dict():
            raise FileExistsError("conflicting Feature replay report exists")
        return final
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    installed = False
    try:
        _write_json(stage / "report.json", report.to_canonical_dict())
        _write_json(
            stage / "SHA256SUMS.json",
            {"report.json": _file_hash(stage / "report.json")},
        )
        _fsync_directory(stage)
        _load_verified_feature_replay_report(
            stage, enforce_directory_identity=False
        )
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


def load_verified_feature_replay_report(path: Path) -> FeatureBundleReplayReport:
    return _load_verified_feature_replay_report(
        path, enforce_directory_identity=True
    )


def _load_verified_feature_replay_report(
    path: Path, *, enforce_directory_identity: bool
) -> FeatureBundleReplayReport:
    root = path.resolve()
    expected_files = {"SHA256SUMS.json", "report.json"}
    _require_exact_files(root, expected_files, "Feature replay report")
    checksums = _read_checksum_index(
        root / "SHA256SUMS.json", "Feature replay report"
    )
    if set(checksums) != {"report.json"}:
        raise ValueError("Feature replay report checksum index mismatch")
    _verify_checksums(root, checksums, "Feature replay report")
    report = FeatureBundleReplayReport.from_canonical_dict(
        _read_object(root / "report.json", "Feature replay report")
    )
    if enforce_directory_identity and root.name != str(report.report_id):
        raise ValueError("Feature replay report directory identity mismatch")
    return report


def _verify_reference(*, verified: Any, reference: Any) -> None:
    artifact = verified.artifact
    if (
        artifact.artifact_id != reference.artifact_id
        or artifact.content_hash != reference.content_hash
        or artifact.feature_id != reference.feature_id
        or artifact.symbol != reference.symbol
        or artifact.timeframe is not reference.timeframe
        or artifact.state is not reference.state
        or artifact.available_at != reference.available_at
    ):
        raise ValueError("Feature Bundle reference projection mismatch")


def _command_path(output_root: Path, idempotency_key: str) -> Path:
    key_hash = canonical_hash({"idempotency_key": idempotency_key}).split(":", 1)[1]
    return output_root / "materialization-commands" / f"{key_hash}.json"


def _write_command(*, path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError("Feature materialization command already exists")
    temporary = path.with_name(f".{path.name}.tmp")
    _write_json(temporary, payload)
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def _require_exact_files(root: Path, expected: set[str], label: str) -> None:
    if not root.is_dir():
        raise ValueError(f"{label} package path is not a directory")
    actual = {item.name for item in root.iterdir() if item.is_file()}
    if actual != expected or any(item.is_dir() for item in root.iterdir()):
        raise ValueError(f"{label} exact file set mismatch")


def _read_checksum_index(path: Path, label: str) -> dict[str, str]:
    payload = _read_object(path, f"{label} checksum index")
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in payload.items()):
        raise ValueError(f"{label} checksum index mismatch")
    return {str(key): str(value) for key, value in payload.items()}


def _verify_checksums(root: Path, checksums: Mapping[str, str], label: str) -> None:
    for name, expected in checksums.items():
        require_sha256(f"{label} checksum", expected)
        if _file_hash(root / name) != expected:
            raise ValueError(f"{label} checksum mismatch: {name}")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (canonical_json(payload) + "\n").encode("utf-8")
    with path.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be an object")
    if raw != (canonical_json(payload) + "\n").encode("utf-8"):
        raise ValueError(f"{label} is not canonical")
    return payload


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "FeatureBundleState",
    "FeatureMaterializationRunner",
    "FeatureMaterializationStatus",
    "VerifiedFeatureArtifactV2",
    "VerifiedFeatureBundleV2",
    "load_verified_feature_artifact_v2",
    "load_verified_feature_bundle_v2",
    "load_verified_feature_replay_report",
    "publish_feature_artifact_v2",
    "publish_feature_bundle_v2",
    "publish_feature_replay_report",
    "replay_feature_bundle_v2",
]
