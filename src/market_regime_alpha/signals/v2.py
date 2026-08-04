"""Feature-derived Signal V2 Artifact, immutable package, and recomputation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.evidence.envelope import ArtifactEnvelope, EvidenceAuthority
from market_regime_alpha.features.materialization_v2 import VerifiedFeatureBundleV2
from market_regime_alpha.market_data import VerifiedMarketDataDataset
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.signals.contracts import SignalSnapshot
from market_regime_alpha.signals.engine import (
    SignalModelConfig,
    build_signal_snapshot_from_metrics,
)
from market_regime_alpha.signals.input_assembly import (
    SignalFactorName,
    SignalInputAssembler,
    SignalInputMappingConfiguration,
    SignalObservationV2,
)


SIGNAL_RUN_V2_SCHEMA = "signal-run-artifact-v2"
SIGNAL_RUN_V2_PACKAGE_SCHEMA = "signal-run-package-v2"
SIGNAL_RUN_V2_FILES = ("SHA256SUMS.json", "artifact.json", "manifest.json")


@dataclass(frozen=True, slots=True)
class SignalRunArtifactV2:
    """A Signal run whose metrics are resolved from one verified Feature Bundle."""

    envelope: ArtifactEnvelope
    candidate_set: CandidateSet
    feature_bundle_id: ArtifactId
    feature_bundle_hash: str
    mapping_configuration: SignalInputMappingConfiguration
    signal_configuration: SignalModelConfig
    observations: tuple[SignalObservationV2, ...]
    snapshots: tuple[SignalSnapshot, ...]

    def __post_init__(self) -> None:
        if self.envelope.artifact_type != "SIGNAL_RUN_V2":
            raise ValueError("Signal V2 run requires SIGNAL_RUN_V2 Envelope")
        if self.envelope.configuration_id != self.signal_configuration.configuration_id:
            raise ValueError("Signal V2 model configuration identity mismatch")
        symbols = tuple(item.symbol for item in self.snapshots)
        if symbols != tuple(sorted(symbols)) or len(symbols) != len(set(symbols)):
            raise ValueError("Signal V2 snapshots must be sorted and unique")
        if tuple(item.symbol for item in self.observations) != symbols:
            raise ValueError("Signal V2 observations and snapshots must align")
        if any(
            item.candidate_set_id != self.candidate_set.envelope.artifact_id
            or item.candidate_set_hash != self.candidate_set.envelope.content_hash
            or
            item.feature_bundle_id != self.feature_bundle_id
            or item.feature_bundle_hash != self.feature_bundle_hash
            or item.mapping_configuration_id
            != self.mapping_configuration.configuration_id
            or item.mapping_configuration_hash
            != self.mapping_configuration.configuration_hash
            for item in self.observations
        ):
            raise ValueError("Signal V2 observation input scope mismatch")
        self.mapping_configuration.verify_identity()
        self.envelope.verify_payload(self.artifact_payload())

    @property
    def artifact_id(self) -> ArtifactId:
        return self.envelope.artifact_id

    @property
    def configuration(self) -> SignalModelConfig:
        """Common read-only view used by V1-compatible downstream models."""

        return self.signal_configuration

    def artifact_payload(self) -> dict[str, Any]:
        return {
            "schema_version": SIGNAL_RUN_V2_SCHEMA,
            "candidate_set": {
                "artifact_id": str(self.candidate_set.envelope.artifact_id),
                "content_hash": self.candidate_set.envelope.content_hash,
            },
            "feature_bundle": {
                "artifact_id": str(self.feature_bundle_id),
                "content_hash": self.feature_bundle_hash,
            },
            "mapping_configuration": self.mapping_configuration.to_canonical_dict(),
            "signal_configuration": self.signal_configuration.to_canonical_dict(),
            "observations": [item.to_canonical_dict() for item in self.observations],
            "snapshots": [item.to_canonical_dict() for item in self.snapshots],
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "envelope": self.envelope.to_canonical_dict(),
            "candidate_set": self.candidate_set.to_canonical_dict(),
            "feature_bundle_id": str(self.feature_bundle_id),
            "feature_bundle_hash": self.feature_bundle_hash,
            "mapping_configuration": self.mapping_configuration.to_canonical_dict(),
            "signal_configuration": self.signal_configuration.to_canonical_dict(),
            "observations": [item.to_canonical_dict() for item in self.observations],
            "snapshots": [item.to_canonical_dict() for item in self.snapshots],
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> SignalRunArtifactV2:
        expected = {
            "envelope",
            "candidate_set",
            "feature_bundle_id",
            "feature_bundle_hash",
            "mapping_configuration",
            "signal_configuration",
            "observations",
            "snapshots",
        }
        if set(payload) != expected:
            raise ValueError("SignalRunArtifactV2 fields mismatch")
        envelope = _object(payload["envelope"], "envelope")
        candidate = _object(payload["candidate_set"], "candidate_set")
        mapping = _object(payload["mapping_configuration"], "mapping_configuration")
        signal_config = _object(payload["signal_configuration"], "signal_configuration")
        observations = _objects(payload["observations"], "observations")
        snapshots = _objects(payload["snapshots"], "snapshots")
        return cls(
            envelope=ArtifactEnvelope.from_canonical_dict(envelope),
            candidate_set=CandidateSet.from_canonical_dict(candidate),
            feature_bundle_id=ArtifactId(str(payload["feature_bundle_id"])),
            feature_bundle_hash=str(payload["feature_bundle_hash"]),
            mapping_configuration=SignalInputMappingConfiguration.from_canonical_dict(
                mapping
            ),
            signal_configuration=SignalModelConfig.from_canonical_dict(signal_config),
            observations=tuple(
                SignalObservationV2.from_canonical_dict(item) for item in observations
            ),
            snapshots=tuple(
                SignalSnapshot.from_canonical_dict(item) for item in snapshots
            ),
        )


@dataclass(frozen=True, slots=True)
class VerifiedSignalRunArtifactV2:
    root: Path
    artifact: SignalRunArtifactV2
    checksums_hash: str


def run_signal_model_v2(
    *,
    candidate_set: CandidateSet,
    feature_bundle: VerifiedFeatureBundleV2,
    mapping_configuration: SignalInputMappingConfiguration,
    signal_configuration: SignalModelConfig,
    observations: tuple[SignalObservationV2, ...],
    decision_time: DecisionTime,
    created_at: datetime,
    code_revision: str,
) -> SignalRunArtifactV2:
    """Apply the existing Signal rule to verified, per-factor Feature inputs."""

    candidate_set.envelope.verify_payload(candidate_set.artifact_payload())
    feature_bundle.artifact.verify_identity()
    mapping_configuration.verify_identity()
    if candidate_set.envelope.decision_time != decision_time or (
        feature_bundle.artifact.decision_time != decision_time.value
    ):
        raise ValueError("Signal V2 DecisionTime input mismatch")
    selected_symbols = tuple(sorted(item.symbol for item in candidate_set.selected))
    observation_by_symbol = {item.symbol: item for item in observations}
    if len(observation_by_symbol) != len(observations) or (
        tuple(sorted(observation_by_symbol)) != selected_symbols
    ):
        raise ValueError("Signal V2 observations must exactly cover selected Candidates")
    ordered_observations = tuple(
        observation_by_symbol[symbol] for symbol in selected_symbols
    )
    for observation in ordered_observations:
        observation.verify_identity()
        if (
            observation.decision_time != decision_time.value
            or observation.candidate_set_id != candidate_set.envelope.artifact_id
            or observation.candidate_set_hash != candidate_set.envelope.content_hash
        ):
            raise ValueError("Signal V2 observation DecisionTime mismatch")

    snapshots = tuple(
        _build_v2_snapshot(
            candidate_set=candidate_set,
            mapping_configuration=mapping_configuration,
            signal_configuration=signal_configuration,
            observation=observation_by_symbol[symbol],
            decision_time=decision_time,
            created_at=created_at,
            code_revision=code_revision,
        )
        for symbol in selected_symbols
    )
    input_pairs: dict[ArtifactId, str] = {
        candidate_set.envelope.artifact_id: candidate_set.envelope.content_hash,
        feature_bundle.artifact.bundle_id: feature_bundle.artifact.content_hash,
        mapping_configuration.configuration_id: mapping_configuration.configuration_hash,
    }
    for observation in ordered_observations:
        input_pairs[observation.observation_id] = observation.content_hash
        for factor in observation.factors:
            existing = input_pairs.get(factor.source_artifact_id)
            if existing is not None and existing != factor.source_content_hash:
                raise ValueError("Signal V2 Feature Artifact hash conflict")
            input_pairs[factor.source_artifact_id] = factor.source_content_hash
    for snapshot in snapshots:
        input_pairs[snapshot.envelope.artifact_id] = snapshot.envelope.content_hash
    payload = _signal_run_payload(
        candidate_set=candidate_set,
        feature_bundle_id=feature_bundle.artifact.bundle_id,
        feature_bundle_hash=feature_bundle.artifact.content_hash,
        mapping_configuration=mapping_configuration,
        signal_configuration=signal_configuration,
        observations=ordered_observations,
        snapshots=snapshots,
    )
    envelope = ArtifactEnvelope.create(
        artifact_type="SIGNAL_RUN_V2",
        artifact_payload=payload,
        decision_date=decision_time.value.date(),
        decision_time=decision_time,
        created_at=created_at,
        code_revision=code_revision,
        configuration_id=signal_configuration.configuration_id,
        configuration_hash=signal_configuration.configuration_hash,
        source_manifest_id=candidate_set.envelope.source_manifest_id,
        source_manifest_hash=candidate_set.envelope.source_manifest_hash,
        input_artifact_ids=tuple(input_pairs),
        input_content_hashes=tuple(input_pairs.values()),
        model_id=signal_configuration.model_id,
        model_version=signal_configuration.model_version,
        data_eligibility=candidate_set.envelope.data_eligibility,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status="RESEARCH_ONLY",
        reason_codes=("SIGNAL_DERIVED_FROM_VERIFIED_FEATURE_BUNDLE",),
        limitations=(
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "NO_CALIBRATED_PROBABILITY",
            "NO_ENTRY_ACTION",
            "NO_TRADING_AUTHORITY",
        ),
    )
    return SignalRunArtifactV2(
        envelope=envelope,
        candidate_set=candidate_set,
        feature_bundle_id=feature_bundle.artifact.bundle_id,
        feature_bundle_hash=feature_bundle.artifact.content_hash,
        mapping_configuration=mapping_configuration,
        signal_configuration=signal_configuration,
        observations=ordered_observations,
        snapshots=snapshots,
    )


def _build_v2_snapshot(
    *,
    candidate_set: CandidateSet,
    mapping_configuration: SignalInputMappingConfiguration,
    signal_configuration: SignalModelConfig,
    observation: SignalObservationV2,
    decision_time: DecisionTime,
    created_at: datetime,
    code_revision: str,
) -> SignalSnapshot:
    factors = {item.factor_name: item for item in observation.factors}
    source_pairs: dict[ArtifactId, str] = {
        observation.feature_bundle_id: observation.feature_bundle_hash,
        mapping_configuration.configuration_id: mapping_configuration.configuration_hash,
        observation.observation_id: observation.content_hash,
    }
    for factor in observation.factors:
        source_pairs[factor.source_artifact_id] = factor.source_content_hash
    return build_signal_snapshot_from_metrics(
        candidate_set=candidate_set,
        configuration=signal_configuration,
        symbol=observation.symbol,
        price_action_return=_float(factors[SignalFactorName.PRICE_ACTION_RETURN].value),
        volume_ratio=_float(factors[SignalFactorName.VOLUME_RATIO].value),
        trend_return=_float(factors[SignalFactorName.TREND_RETURN].value),
        price_vs_vwap_return=_float(
            factors[SignalFactorName.PRICE_VS_VWAP_RETURN].value
        ),
        overheat_return=_float(factors[SignalFactorName.OVERHEAT_RETURN].value),
        reason_codes=observation.reason_codes,
        source_artifact_pairs=tuple(source_pairs.items()),
        decision_time=decision_time,
        created_at=created_at,
        code_revision=code_revision,
    )


def publish_signal_run_v2(*, root: Path, artifact: SignalRunArtifactV2) -> Path:
    artifact.envelope.verify_payload(artifact.artifact_payload())
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(artifact.artifact_id)
    if final.exists():
        existing = load_verified_signal_run_v2(final)
        if existing.artifact.to_canonical_dict() != artifact.to_canonical_dict():
            raise FileExistsError(f"conflicting Signal V2 Artifact exists: {final}")
        return final
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    installed = False
    try:
        _write_json(stage / "artifact.json", artifact.to_canonical_dict())
        _write_json(stage / "manifest.json", _manifest(artifact))
        _write_json(
            stage / "SHA256SUMS.json",
            {
                name: _file_hash(stage / name)
                for name in SIGNAL_RUN_V2_FILES
                if name != "SHA256SUMS.json"
            },
        )
        _fsync_directory(stage)
        _load_verified_signal_run_v2(stage, enforce_directory_identity=False)
        os.replace(stage, final)
        installed = True
        _fsync_directory(root)
        return final
    finally:
        if not installed and stage.exists():
            shutil.rmtree(stage)


def load_verified_signal_run_v2(path: Path) -> VerifiedSignalRunArtifactV2:
    return _load_verified_signal_run_v2(path, enforce_directory_identity=True)


def _load_verified_signal_run_v2(
    path: Path, *, enforce_directory_identity: bool
) -> VerifiedSignalRunArtifactV2:
    root = path.resolve()
    _verify_files(root)
    artifact = SignalRunArtifactV2.from_canonical_dict(
        _read_object(root / "artifact.json")
    )
    if _read_object(root / "manifest.json") != _manifest(artifact):
        raise ValueError("Signal V2 manifest is not reconstructible")
    if enforce_directory_identity and root.name != str(artifact.artifact_id):
        raise ValueError("Signal V2 directory identity mismatch")
    return VerifiedSignalRunArtifactV2(
        root=root,
        artifact=artifact,
        checksums_hash=_file_hash(root / "SHA256SUMS.json"),
    )


def replay_signal_run_v2(
    path: Path,
    *,
    feature_bundle: VerifiedFeatureBundleV2,
    verified_dataset: VerifiedMarketDataDataset,
) -> VerifiedSignalRunArtifactV2:
    """Reassemble factors from Feature Artifacts, then rerun the Signal model."""

    verified = load_verified_signal_run_v2(path)
    original = verified.artifact
    if feature_bundle.artifact.bundle_id != original.feature_bundle_id or (
        feature_bundle.artifact.content_hash != original.feature_bundle_hash
    ):
        raise ValueError("Signal V2 replay Feature Bundle mismatch")
    observations = SignalInputAssembler().assemble(
        candidate_set=original.candidate_set,
        feature_bundle=feature_bundle,
        verified_dataset=verified_dataset,
        configuration=original.mapping_configuration,
        decision_time=original.envelope.decision_time,
    )
    replayed = run_signal_model_v2(
        candidate_set=original.candidate_set,
        feature_bundle=feature_bundle,
        mapping_configuration=original.mapping_configuration,
        signal_configuration=original.signal_configuration,
        observations=observations,
        decision_time=original.envelope.decision_time,
        created_at=original.envelope.created_at,
        code_revision=original.envelope.code_revision,
    )
    if replayed.to_canonical_dict() != original.to_canonical_dict():
        raise ValueError("Signal V2 replay differs from stored Artifact")
    return verified


def _signal_run_payload(
    *,
    candidate_set: CandidateSet,
    feature_bundle_id: ArtifactId,
    feature_bundle_hash: str,
    mapping_configuration: SignalInputMappingConfiguration,
    signal_configuration: SignalModelConfig,
    observations: tuple[SignalObservationV2, ...],
    snapshots: tuple[SignalSnapshot, ...],
) -> dict[str, Any]:
    return {
        "schema_version": SIGNAL_RUN_V2_SCHEMA,
        "candidate_set": {
            "artifact_id": str(candidate_set.envelope.artifact_id),
            "content_hash": candidate_set.envelope.content_hash,
        },
        "feature_bundle": {
            "artifact_id": str(feature_bundle_id),
            "content_hash": feature_bundle_hash,
        },
        "mapping_configuration": mapping_configuration.to_canonical_dict(),
        "signal_configuration": signal_configuration.to_canonical_dict(),
        "observations": [item.to_canonical_dict() for item in observations],
        "snapshots": [item.to_canonical_dict() for item in snapshots],
    }


def _manifest(artifact: SignalRunArtifactV2) -> dict[str, Any]:
    return {
        "schema_version": SIGNAL_RUN_V2_PACKAGE_SCHEMA,
        "artifact_id": str(artifact.artifact_id),
        "content_hash": artifact.envelope.content_hash,
        "candidate_set_id": str(artifact.candidate_set.envelope.artifact_id),
        "feature_bundle_id": str(artifact.feature_bundle_id),
        "feature_bundle_hash": artifact.feature_bundle_hash,
        "mapping_configuration_id": str(
            artifact.mapping_configuration.configuration_id
        ),
        "mapping_configuration_hash": artifact.mapping_configuration.configuration_hash,
        "signal_configuration_id": str(
            artifact.signal_configuration.configuration_id
        ),
        "signal_configuration_hash": artifact.signal_configuration.configuration_hash,
        "snapshot_ids": [str(item.envelope.artifact_id) for item in artifact.snapshots],
        "required_artifacts": sorted(SIGNAL_RUN_V2_FILES),
        "data_eligibility": artifact.envelope.data_eligibility.value,
        "formal_pit": artifact.envelope.formal_pit,
        "formal_oos_alpha": artifact.envelope.formal_oos_alpha,
        "trading_authority": artifact.envelope.trading_authority,
    }


def _verify_files(root: Path) -> None:
    if not root.is_dir() or {item.name for item in root.iterdir()} != set(
        SIGNAL_RUN_V2_FILES
    ):
        raise ValueError("Signal V2 exact file set mismatch")
    if any(not item.is_file() for item in root.iterdir()):
        raise ValueError("Signal V2 exact file set contains a non-file")
    checksums = _read_object(root / "SHA256SUMS.json")
    expected = set(SIGNAL_RUN_V2_FILES) - {"SHA256SUMS.json"}
    if set(checksums) != expected:
        raise ValueError("Signal V2 checksum coverage mismatch")
    for name, expected_hash in checksums.items():
        if not isinstance(expected_hash, str) or _file_hash(root / name) != expected_hash:
            raise ValueError(f"Signal V2 checksum mismatch: {name}")


def _write_json(path: Path, payload: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(
            payload,
            stream,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Signal V2 JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Signal V2 {label} must be an object")
    return value


def _objects(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"Signal V2 {label} must be an array of objects")
    return value


def _float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None
