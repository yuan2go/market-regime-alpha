"""Feature Artifact V2 publication, deterministic materialization, and replay."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import MappingProxyType
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
from market_regime_alpha.features.materialization_run import (
    DEFAULT_FEATURE_TASK_LEASE,
    FeatureMaterializationExecutionMode,
    FeatureMaterializationTaskSpec,
    SQLiteFeatureMaterializationRunRepository,
)
from market_regime_alpha.features.encoding_v2 import (
    FEATURE_ARTIFACT_ENCODING_V2,
    FEATURE_BUNDLE_ENCODING_V2,
    load_feature_artifact_encoding_v2,
    load_feature_bundle_artifacts_v2,
    publish_feature_artifact_encoding_v2,
    publish_feature_bundle_encoding_v2,
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


class FeatureReplayDivergenceError(ValueError):
    """Recomputation differs from the immutable original Feature Bundle."""


class FeatureConfigurationInvalidError(ValueError):
    """A content-addressed Feature configuration has no executable semantics."""


class FeatureComputationFailedError(RuntimeError):
    """A valid Feature computation failed rather than lacking market evidence."""


class FeatureMaterializationHardCrash(BaseException):
    """Testable process-death boundary that deliberately skips graceful settlement."""


def publish_feature_artifact_v2(
    *,
    root: Path,
    artifact: FeatureArtifactV2,
    failure_injector: FailureInjector | None = None,
    encoding_version: str = FEATURE_ARTIFACT_ENCODING_V2,
    identity_verified: bool = False,
) -> Path:
    if encoding_version == FEATURE_ARTIFACT_ENCODING_V2:
        if failure_injector is not None:
            raise ValueError("Feature Artifact Encoding V2 has no artifact-level injector")
        return publish_feature_artifact_encoding_v2(
            root=root,
            artifact=artifact,
            identity_verified=identity_verified,
        )
    if encoding_version != "feature-artifact-package-json-v1":
        raise ValueError("unsupported Feature Artifact physical encoding")
    return _publish_feature_artifact_json_v1(
        root=root,
        artifact=artifact,
        failure_injector=failure_injector,
    )


def _publish_feature_artifact_json_v1(
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
        try:
            os.replace(stage, final)
        except OSError:
            if not final.exists():
                raise
            existing = load_verified_feature_artifact_v2(final)
            if existing.artifact.to_canonical_dict() != artifact.to_canonical_dict():
                raise FileExistsError(
                    f"conflicting Feature Artifact V2 exists: {final}"
                )
            return final
        installed = True
        _fsync_directory(root)
        if failure_injector is not None:
            failure_injector("AFTER_ATOMIC_INSTALL")
        return final
    finally:
        if not installed and stage.exists():
            shutil.rmtree(stage)


def load_verified_feature_artifact_v2(path: Path) -> VerifiedFeatureArtifactV2:
    if (path / "encoding.json").is_file():
        verified = load_feature_artifact_encoding_v2(path)
        return VerifiedFeatureArtifactV2(
            root=verified.root,
            artifact=verified.artifact,
            checksums_hash=verified.physical_checksums_hash,
        )
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
    materialized_artifacts: tuple[FeatureArtifactV2, ...] | None = None,
    materialized_artifacts_verified: bool = False,
    failure_injector: FailureInjector | None = None,
    encoding_version: str = FEATURE_BUNDLE_ENCODING_V2,
) -> Path:
    if encoding_version == FEATURE_BUNDLE_ENCODING_V2:
        if materialized_artifacts is None:
            artifacts = tuple(
                load_verified_feature_artifact_v2(
                    artifact_root / str(reference.artifact_id)
                ).artifact
                for reference in bundle.feature_artifact_references
            )
        else:
            artifacts = tuple(materialized_artifacts)
            for artifact in artifacts:
                if not (artifact_root / str(artifact.artifact_id)).is_dir():
                    raise ValueError("referenced Feature Artifact is missing")
        return publish_feature_bundle_encoding_v2(
            root=root,
            bundle=bundle,
            artifacts=artifacts,
            artifacts_verified=materialized_artifacts_verified,
            failure_injector=failure_injector,
        )
    if encoding_version != "feature-bundle-package-json-v1":
        raise ValueError("unsupported Feature Bundle physical encoding")
    return _publish_feature_bundle_json_v1(
        root=root,
        artifact_root=artifact_root,
        bundle=bundle,
        failure_injector=failure_injector,
    )


def _publish_feature_bundle_json_v1(
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
        try:
            os.replace(stage, final)
        except OSError:
            if not final.exists():
                raise
            existing = load_verified_feature_bundle_v2(
                final, artifact_root=artifact_root
            )
            if existing.artifact.to_canonical_dict() != bundle.to_canonical_dict():
                raise FileExistsError(f"conflicting Feature Bundle exists: {final}")
            return final
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
    if (path / "encoding.json").is_file():
        bundle, artifacts, checksums_hash = load_feature_bundle_artifacts_v2(path)
        missing = tuple(
            artifact
            for artifact in artifacts
            if not (artifact_root / str(artifact.artifact_id)).is_dir()
        )
        if missing:
            raise ValueError("referenced Feature Artifact is missing")
        verified_artifacts = tuple(
            VerifiedFeatureArtifactV2(
                root=artifact_root / str(artifact.artifact_id),
                artifact=artifact,
                checksums_hash=load_verified_feature_artifact_v2(
                    artifact_root / str(artifact.artifact_id)
                ).checksums_hash,
            )
            for artifact in artifacts
        )
        return VerifiedFeatureBundleV2(
            root=path.resolve(),
            artifact=bundle,
            artifacts=verified_artifacts,
            checksums_hash=checksums_hash,
        )
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
    bundle.verify_materialized_projection(
        tuple(item.artifact for item in artifacts)
    )
    return VerifiedFeatureBundleV2(
        root=root,
        artifact=bundle,
        artifacts=tuple(artifacts),
        checksums_hash=canonical_hash(dict(sorted(checksums.items()))),
    )


@dataclass(frozen=True, slots=True)
class PreparedFeatureExecutionContext:
    """One verified immutable input projection reused by every task batch."""

    verified_dataset: VerifiedMarketDataDataset
    feature_set: FeatureSetConfiguration
    selected_symbols: tuple[str, ...]
    definitions: Mapping[str, FeatureDefinitionV2]
    configurations: Mapping[str, FeatureConfiguration]
    bars_by_scope: Mapping[tuple[str, Timeframe], tuple[CanonicalMarketBar, ...]]
    task_input_scopes: Mapping[str, tuple[str, Timeframe]]
    task_specs: tuple[FeatureMaterializationTaskSpec, ...]
    dataset_membership: Any

    @classmethod
    def create(
        cls,
        *,
        verified_dataset: VerifiedMarketDataDataset,
        feature_set: FeatureSetConfiguration,
        selected_symbols: tuple[str, ...],
    ) -> PreparedFeatureExecutionContext:
        feature_set.verify_identity()
        dataset = verified_dataset.artifact
        membership = _verified_dataset_membership(dataset)
        selected = tuple(sorted(selected_symbols))
        if not selected or len(selected) != len(set(selected)):
            raise ValueError("selected symbols must be non-empty and unique")
        if not set(selected).issubset(dataset.coverage.observed_symbols):
            raise ValueError("selected symbols are not covered by Market Data Dataset")
        definitions = {item.feature_id: item for item in feature_set.definitions}
        configurations = {
            item.feature_id: item for item in feature_set.configurations
        }
        grouped: dict[tuple[str, Timeframe], list[CanonicalMarketBar]] = {}
        for bar in verified_dataset.bars:
            grouped.setdefault((bar.symbol, bar.timeframe), []).append(bar)
        bars_by_scope = {
            key: tuple(values) for key, values in grouped.items()
        }
        task_specs = FeatureMaterializationRunner._task_specs(
            feature_set=feature_set,
            selected_symbols=selected,
        )
        task_input_scopes = {
            item.task_key: (item.symbol, item.timeframe) for item in task_specs
        }
        return cls(
            verified_dataset=verified_dataset,
            feature_set=feature_set,
            selected_symbols=selected,
            definitions=MappingProxyType(definitions),
            configurations=MappingProxyType(configurations),
            bars_by_scope=MappingProxyType(bars_by_scope),
            task_input_scopes=MappingProxyType(task_input_scopes),
            task_specs=task_specs,
            dataset_membership=membership,
        )


class FeatureMaterializationRunner:
    """Materialize a controlled Feature Set without network or execution access."""

    def __init__(
        self,
        *,
        max_workers: int = 1,
        task_batch_size: int = 256,
        clock: Callable[[], datetime] | None = None,
        lease_duration: timedelta = DEFAULT_FEATURE_TASK_LEASE,
    ) -> None:
        if isinstance(max_workers, bool) or not 1 <= max_workers <= 8:
            raise ValueError("max_workers must be between one and eight")
        if isinstance(task_batch_size, bool) or not 1 <= task_batch_size <= 256:
            raise ValueError("task_batch_size must be between one and 256")
        self._max_workers = max_workers
        self._task_batch_size = task_batch_size
        self._clock = clock
        self._lease_duration = lease_duration

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
        execution_mode: FeatureMaterializationExecutionMode,
        artifact_encoding_version: str = FEATURE_ARTIFACT_ENCODING_V2,
        bundle_encoding_version: str = FEATURE_BUNDLE_ENCODING_V2,
        failure_injector: FailureInjector | None = None,
    ) -> FeatureMaterializationReceipt:
        if not isinstance(decision_time, datetime) or not isinstance(created_at, datetime):
            raise TypeError("decision_time and created_at must be datetime")
        require_utc_second("decision_time", decision_time)
        require_utc_second("created_at", created_at)
        if not isinstance(execution_mode, FeatureMaterializationExecutionMode):
            raise TypeError("execution_mode must be FeatureMaterializationExecutionMode")
        require_text("code_revision", code_revision)
        require_text("idempotency_key", idempotency_key)
        if artifact_encoding_version not in {
            FEATURE_ARTIFACT_ENCODING_V2,
            "feature-artifact-package-json-v1",
        }:
            raise ValueError("unsupported Feature Artifact physical encoding")
        if bundle_encoding_version not in {
            FEATURE_BUNDLE_ENCODING_V2,
            "feature-bundle-package-json-v1",
        }:
            raise ValueError("unsupported Feature Bundle physical encoding")
        feature_set.verify_identity()
        dataset = verified_dataset.artifact
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
                "artifact_encoding_version": artifact_encoding_version,
                "bundle_encoding_version": bundle_encoding_version,
            }
        )
        task_specs = self._task_specs(
            feature_set=feature_set,
            selected_symbols=selected_symbols,
        )
        repository_options: dict[str, Any] = {
            "lease_duration": self._lease_duration,
        }
        if self._clock is not None:
            repository_options["clock"] = self._clock
        repository = SQLiteFeatureMaterializationRunRepository(
            output_root / "materialization-run.sqlite3",
            **repository_options,
        )
        snapshot = repository.prepare(
            idempotency_key=idempotency_key,
            command_hash=command_hash,
            tasks=task_specs,
            mode=execution_mode,
        )
        if execution_mode is FeatureMaterializationExecutionMode.RETURN_IF_COMPLETE:
            if snapshot.receipt is None:
                raise ValueError("completed Feature materialization run has no Receipt")
            _verify_materialization_receipt_package(
                receipt=snapshot.receipt,
                output_root=output_root,
            )
            return snapshot.receipt
        context = PreparedFeatureExecutionContext.create(
            verified_dataset=verified_dataset,
            feature_set=feature_set,
            selected_symbols=selected_symbols,
        )
        artifact_root = output_root / "feature-artifacts"
        completed_in_process: dict[str, FeatureArtifactV2] = {}
        while True:
            claims = repository.claim_batch(
                run_id=snapshot.run_id,
                limit=self._task_batch_size,
            )
            if not claims:
                break
            if failure_injector is not None:
                failure_injector("AFTER_TASK_CLAIMED")
            outstanding = list(claims)
            try:
                computed = self._compute_artifacts(
                    context=context,
                    decision_time=decision_time,
                    created_at=created_at,
                    task_scope=tuple(
                        (item.symbol, item.feature_id) for item in claims
                    ),
                )
                by_scope = {
                    (item.symbol, item.feature_id): item for item in computed
                }
                publication_scope = tuple(
                    (claim, by_scope[(claim.symbol, claim.feature_id)])
                    for claim in claims
                )

                def publish(
                    item: tuple[Any, FeatureArtifactV2],
                ) -> tuple[Any, FeatureArtifactV2, bool]:
                    claim, artifact = item
                    if artifact.timeframe is not claim.timeframe:
                        raise ValueError("materialization task timeframe changed")
                    artifact_path = artifact_root / str(artifact.artifact_id)
                    publication_reused = artifact_path.is_dir()
                    publish_feature_artifact_v2(
                        root=artifact_root,
                        artifact=artifact,
                        encoding_version=artifact_encoding_version,
                        identity_verified=True,
                    )
                    if failure_injector is not None:
                        failure_injector("AFTER_ARTIFACT_PUBLISHED")
                    return claim, artifact, publication_reused

                if self._max_workers == 1:
                    published = tuple(publish(item) for item in publication_scope)
                else:
                    with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
                        published = tuple(executor.map(publish, publication_scope))
                for claim, artifact, publication_reused in published:
                    repository.complete_task(
                        claim,
                        artifact_id=str(artifact.artifact_id),
                        artifact_hash=artifact.content_hash,
                        publication_reused=publication_reused,
                    )
                    completed_in_process[str(artifact.artifact_id)] = artifact
                    outstanding.remove(claim)
                    if failure_injector is not None:
                        failure_injector("AFTER_TASK_COMPLETED")
            except FeatureMaterializationHardCrash:
                raise
            except Exception as exc:
                for claim in outstanding:
                    repository.fail_task(claim, error_message=f"{type(exc).__name__}:{exc}")
                raise
        recovered_artifacts: list[FeatureArtifactV2] = []
        for artifact_id, artifact_hash in repository.completed_artifacts(snapshot.run_id):
            recovered = completed_in_process.get(artifact_id)
            if recovered is None:
                recovered = load_verified_feature_artifact_v2(
                    artifact_root / artifact_id
                ).artifact
            if recovered.content_hash != artifact_hash:
                raise ValueError("Feature Artifact durable hash mismatch")
            recovered_artifacts.append(recovered)
        artifacts = tuple(recovered_artifacts)
        if len(artifacts) != len(task_specs):
            raise ValueError("Feature materialization durable task projection is incomplete")
        if failure_injector is not None:
            failure_injector("BEFORE_BUNDLE_PUBLICATION")
        bundle = FeatureBundleArtifact.create(
            dataset=dataset,
            feature_set=feature_set,
            artifacts=artifacts,
            selected_symbols=selected_symbols,
            created_at=created_at,
            code_revision=code_revision,
            _membership=context.dataset_membership,
            _artifacts_verified=True,
        )
        publish_feature_bundle_v2(
            root=output_root / "feature-bundles",
            artifact_root=artifact_root,
            bundle=bundle,
            materialized_artifacts=artifacts,
            materialized_artifacts_verified=True,
            encoding_version=bundle_encoding_version,
        )
        repository.record_bundle_published(
            run_id=snapshot.run_id,
            bundle_id=str(bundle.bundle_id),
            bundle_hash=bundle.content_hash,
        )
        if failure_injector is not None:
            failure_injector("AFTER_BUNDLE_PUBLISHED")
        receipt = FeatureMaterializationReceipt.create(
            command_hash=command_hash,
            bundle=bundle,
        )
        repository.finalize(run_id=snapshot.run_id, receipt=receipt)
        return receipt

    @staticmethod
    def _task_specs(
        *,
        feature_set: FeatureSetConfiguration,
        selected_symbols: tuple[str, ...],
    ) -> tuple[FeatureMaterializationTaskSpec, ...]:
        specifications: list[FeatureMaterializationTaskSpec] = []
        for symbol in selected_symbols:
            for configuration in feature_set.configurations:
                raw_timeframe = configuration.parameter_map().get("selected_timeframe")
                if raw_timeframe is None:
                    raise FeatureConfigurationInvalidError(
                        f"invalid configuration for {configuration.feature_id}"
                    )
                try:
                    timeframe = Timeframe(raw_timeframe)
                except ValueError as exc:
                    raise FeatureConfigurationInvalidError(
                        f"invalid configuration for {configuration.feature_id}"
                    ) from exc
                specifications.append(
                    FeatureMaterializationTaskSpec(
                        symbol=symbol,
                        feature_id=configuration.feature_id,
                        timeframe=timeframe,
                    )
                )
        return tuple(sorted(specifications, key=lambda item: item.task_key))

    def _compute_artifacts(
        self,
        *,
        context: PreparedFeatureExecutionContext,
        decision_time: datetime,
        created_at: datetime,
        task_scope: tuple[tuple[str, str], ...] | None = None,
    ) -> tuple[FeatureArtifactV2, ...]:
        definitions = context.definitions
        configurations = context.configurations
        tasks = (
            tuple(
                (symbol, feature_id)
                for symbol in context.selected_symbols
                for feature_id in sorted(definitions)
            )
            if task_scope is None
            else tuple(task_scope)
        )
        if len(tasks) != len(set(tasks)) or any(
            symbol not in context.selected_symbols or feature_id not in definitions
            for symbol, feature_id in tasks
        ):
            raise ValueError("Feature materialization task scope is invalid")

        def compute(task: tuple[str, str]) -> FeatureArtifactV2:
            symbol, feature_id = task
            definition = definitions[feature_id]
            configuration = configurations[feature_id]
            try:
                raw_timeframe = configuration.parameter_map().get("selected_timeframe")
                if raw_timeframe is None:
                    raise ValueError("Feature Configuration lacks selected_timeframe")
                timeframe = Timeframe(raw_timeframe)
                if timeframe not in definition.supported_timeframes:
                    raise ValueError("configured timeframe is unsupported by definition")
            except ValueError as exc:
                raise FeatureConfigurationInvalidError(
                    f"invalid configuration for {feature_id}"
                ) from exc
            input_bars = context.bars_by_scope.get((symbol, timeframe), ())
            output_ids = tuple(item.output_id for item in definition.output_schema)
            if not input_bars:
                computation = missing_technical_feature_computation(
                    feature_id=feature_id,
                    symbol=symbol,
                    timeframe=timeframe,
                    available_at=decision_time,
                    configuration=configuration,
                    output_ids=output_ids,
                    reason_code="DATA_UNAVAILABLE_TIMEFRAME",
                )
            else:
                try:
                    computation = compute_technical_feature(
                        feature_id=feature_id,
                        bars=input_bars,
                        configuration=configuration,
                        decision_time=decision_time,
                    )
                except ValueError as exc:
                    raise FeatureConfigurationInvalidError(
                        f"invalid configuration for {feature_id}"
                    ) from exc
                except ArithmeticError as exc:
                    raise FeatureComputationFailedError(
                        f"Feature computation failed for {feature_id}/{symbol}"
                    ) from exc
            return FeatureArtifactV2.create(
                definition=definition,
                configuration=configuration,
                dataset=context.verified_dataset.artifact,
                computation=computation,
                input_bars=input_bars,
                created_at=created_at,
                _membership=context.dataset_membership,
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
    report, _ = recompute_feature_bundle_v2(
        bundle_path=bundle_path,
        artifact_root=artifact_root,
        verified_dataset=verified_dataset,
    )
    if report_root is not None:
        publish_feature_replay_report(root=report_root, report=report)
    return report


def migrate_feature_bundle_encoding_v1_to_v2(
    *,
    source_bundle_path: Path,
    source_artifact_root: Path,
    target_bundle_root: Path,
    target_artifact_root: Path,
) -> Path:
    """Re-encode verified JSON V1 Feature packages without semantic mutation."""

    if (source_bundle_path / "encoding.json").exists():
        raise ValueError("Feature migration source must use JSON V1 encoding")
    verified = _load_verified_feature_bundle_v2(
        source_bundle_path,
        artifact_root=source_artifact_root,
        enforce_directory_identity=True,
    )
    for item in verified.artifacts:
        publish_feature_artifact_v2(
            root=target_artifact_root,
            artifact=item.artifact,
            encoding_version=FEATURE_ARTIFACT_ENCODING_V2,
        )
    migrated = publish_feature_bundle_v2(
        root=target_bundle_root,
        artifact_root=target_artifact_root,
        bundle=verified.artifact,
        encoding_version=FEATURE_BUNDLE_ENCODING_V2,
    )
    reloaded = load_verified_feature_bundle_v2(
        migrated, artifact_root=target_artifact_root
    )
    if reloaded.artifact.to_canonical_dict() != verified.artifact.to_canonical_dict():
        raise ValueError("Feature V1 to V2 migration changed logical identity")
    return migrated


def recompute_feature_bundle_v2(
    *,
    bundle_path: Path,
    artifact_root: Path,
    verified_dataset: VerifiedMarketDataDataset,
) -> tuple[FeatureBundleReplayReport, VerifiedFeatureBundleV2]:
    """Recompute both artifacts and Bundle for downstream semantic replay."""

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
    context = PreparedFeatureExecutionContext.create(
        verified_dataset=verified_dataset,
        feature_set=original.feature_set,
        selected_symbols=original.symbols,
    )
    replayed_artifacts = FeatureMaterializationRunner(max_workers=1)._compute_artifacts(
        context=context,
        decision_time=original.decision_time,
        created_at=original.created_at,
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
        raise FeatureReplayDivergenceError("Feature Bundle replay semantic mismatch")
    recomputed_artifacts = tuple(
        VerifiedFeatureArtifactV2(
            root=original_verified.root,
            artifact=recomputed,
            checksums_hash=original_verified.checksums_hash,
        )
        for original_verified, recomputed in zip(
            verified.artifacts, replayed_artifacts, strict=True
        )
    )
    recomputed_bundle = VerifiedFeatureBundleV2(
        root=verified.root,
        artifact=replayed_bundle,
        artifacts=recomputed_artifacts,
        checksums_hash=verified.checksums_hash,
    )
    recomputed_bundle.artifact.verify_materialized_projection(
        tuple(item.artifact for item in recomputed_bundle.artifacts)
    )
    return report, recomputed_bundle


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


def _verified_artifact_hash(path: Path, *, expected_hash: str) -> bool:
    verified = load_verified_feature_artifact_v2(path)
    if verified.artifact.content_hash != expected_hash:
        raise ValueError("Feature materialization task Artifact hash mismatch")
    return True


def _verify_materialization_receipt_package(
    *, receipt: FeatureMaterializationReceipt, output_root: Path
) -> None:
    receipt.verify_identity()
    verified = load_verified_feature_bundle_v2(
        output_root / receipt.bundle_locator,
        artifact_root=output_root / "feature-artifacts",
    )
    if (
        verified.artifact.bundle_id != receipt.bundle_id
        or verified.artifact.content_hash != receipt.bundle_hash
    ):
        raise ValueError("Feature materialization Receipt Bundle mismatch")


def _command_path(output_root: Path, idempotency_key: str) -> Path:
    key_hash = canonical_hash({"idempotency_key": idempotency_key}).split(":", 1)[1]
    return output_root / "materialization-commands" / f"{key_hash}.json"


def _write_command(*, path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError("Feature materialization command already exists")
    prefix = f".{path.name}.tmp-"
    descriptor, raw_temporary = tempfile.mkstemp(prefix=prefix, dir=path.parent)
    temporary = Path(raw_temporary)
    try:
        encoded = (canonical_json(payload) + "\n").encode("utf-8")
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _load_materialization_receipt(
    *, command_path: Path, command_hash: str, output_root: Path
) -> FeatureMaterializationReceipt:
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
    "FeatureMaterializationHardCrash",
    "FeatureMaterializationStatus",
    "PreparedFeatureExecutionContext",
    "FeatureConfigurationInvalidError",
    "FeatureComputationFailedError",
    "FeatureReplayDivergenceError",
    "VerifiedFeatureArtifactV2",
    "VerifiedFeatureBundleV2",
    "load_verified_feature_artifact_v2",
    "load_verified_feature_bundle_v2",
    "load_verified_feature_replay_report",
    "migrate_feature_bundle_encoding_v1_to_v2",
    "publish_feature_artifact_v2",
    "publish_feature_bundle_v2",
    "publish_feature_replay_report",
    "recompute_feature_bundle_v2",
    "replay_feature_bundle_v2",
]
