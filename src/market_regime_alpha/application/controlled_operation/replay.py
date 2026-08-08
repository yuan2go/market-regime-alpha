"""Network-free semantic replay for a Controlled operational evidence package."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeVar

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleRunId,
)
from market_regime_alpha.application.canonical_lifecycle.replay_snapshot import (
    lifecycle_history_hash,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LifecycleStageName,
)
from market_regime_alpha.application.controlled_operation.entry_blocker import (
    ControlledEntryAssessmentBlocker,
    load_controlled_entry_blocker,
)
from market_regime_alpha.application.controlled_operation.canonical_bridge import (
    CanonicalRepositoryFactory,
)
from market_regime_alpha.application.controlled_operation.canonical_segment import (
    CanonicalLifecycleRunObjectReference,
    LEGACY_CONTROLLED_CANONICAL_RUN_SCHEMA,
    load_controlled_canonical_lifecycle_run,
)
from market_regime_alpha.application.controlled_operation.evidence_package import (
    ControlledEvidenceReference,
    ControlledOperationalEvidencePackage,
    ControlledOperationalEvidenceStatus,
    load_controlled_operation_package,
    replay_controlled_operation_package,
)
from market_regime_alpha.application.controlled_operation.input_artifacts import (
    load_controlled_source_manifest,
    load_controlled_trading_calendar,
)
from market_regime_alpha.application.controlled_operation.outcome_evidence import (
    build_trade_horizon_outcome_evidence,
    replay_trade_horizon_outcome_evidence,
)
from market_regime_alpha.application.controlled_operation.outcome_source_archive import (
    load_outcome_settlement_source_archive,
    replay_outcome_dataset_from_source_archive,
)
from market_regime_alpha.application.controlled_operation.research_runner import (
    ControlledPlatformResearchRunner,
    load_verified_controlled_research_artifact,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.providers.public_composite import (
    load_verified_public_source_stage_artifact,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.features.materialization_v2 import (
    load_verified_feature_bundle_v2,
    replay_feature_bundle_v2,
)
from market_regime_alpha.features.operational_overlay import (
    CandidateIntradayFeatureOverlay,
    load_candidate_intraday_feature_overlay,
    load_static_universe_feature_bundle,
)
from market_regime_alpha.features.v2_contracts import FeatureMaterializationReceipt
from market_regime_alpha.forecasting.artifact import replay_path_forecast
from market_regime_alpha.market_data import (
    AssetType,
    normalize_public_history_stage,
    replay_market_data_dataset,
)
from market_regime_alpha.market_data.minute_batch import (
    load_minute_acquisition_coverage,
)
from market_regime_alpha.market_data.minute_source import (
    CanonicalVolumeUnitPolicy,
    RawMinuteSourceReader,
    minute_normalizations_to_dataset,
    normalize_tencent_minute_source,
)
from market_regime_alpha.signals.candidate_view_v2 import (
    CandidateFeatureViewV2,
    load_candidate_feature_view_v2,
)
from market_regime_alpha.signals.v3 import replay_signal_run_v3
from market_regime_alpha.universe import load_operational_universe


@dataclass(frozen=True, slots=True)
class ControlledOperationReplayReport:
    package_id: ArtifactId
    package_hash: str
    package_status: ControlledOperationalEvidenceStatus
    component_hashes: tuple[tuple[str, str], ...]
    receipt_fingerprint: str
    semantic_hash: str
    replay_status: str = "STABLE"
    network_accessed: bool = False
    broker_invoked: bool = False
    manual_trade_created: bool = False
    fill_created: bool = False
    model_promoted: bool = False

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "package_id": str(self.package_id),
            "package_hash": self.package_hash,
            "package_status": self.package_status.value,
            "component_hashes": [{"component": name, "content_hash": digest} for name, digest in self.component_hashes],
            "receipt_fingerprint": self.receipt_fingerprint,
            "semantic_hash": self.semantic_hash,
            "replay_status": self.replay_status,
            "network_accessed": self.network_accessed,
            "broker_invoked": self.broker_invoked,
            "manual_trade_created": self.manual_trade_created,
            "fill_created": self.fill_created,
            "model_promoted": self.model_promoted,
        }


def replay_controlled_operation(
    package_path: Path,
    *,
    canonical_repository_factory: CanonicalRepositoryFactory,
    feature_receipt_loader: Callable[
        [Path], tuple[FeatureMaterializationReceipt, ...]
    ],
) -> ControlledOperationReplayReport:
    """Recompute the recorded chain without a clock, network, broker, or writes."""

    package_path = package_path.resolve()
    receipt_loader = feature_receipt_loader
    package = replay_controlled_operation_package(package_path)
    run_root = package_path.parent.parent
    components: list[tuple[str, str]] = []

    calendar = _load_ref(run_root, package, "TRADING_CALENDAR", load_controlled_trading_calendar)
    universe = _load_ref(run_root, package, "OPERATIONAL_UNIVERSE", load_operational_universe)
    source = _load_ref(
        run_root,
        package,
        "DAILY_SOURCE_ARCHIVE",
        load_verified_public_source_stage_artifact,
    )
    source_manifest = _load_ref(
        run_root,
        package,
        "DAILY_SOURCE_MANIFEST",
        load_controlled_source_manifest,
    )
    daily_path = _single_ref_path(run_root, package, "DAILY_DATASET")
    daily = replay_market_data_dataset(daily_path)
    recomputed_daily = normalize_public_history_stage(
        verified=source,
        decision_time=daily.artifact.decision_time,
        created_at=daily.artifact.created_at,
        expected_symbols=universe.symbols,
        source_manifest=source_manifest,
        asset_types={symbol: AssetType.A_SHARE for symbol in universe.symbols},
    )
    if recomputed_daily.to_canonical_dict() != daily.artifact.to_canonical_dict():
        raise ValueError("Controlled replay daily Dataset divergence")
    components.append(("DAILY_DATASET", daily.artifact.content_hash))

    static = _load_ref(
        run_root,
        package,
        "STATIC_FEATURE_BUNDLE",
        load_static_universe_feature_bundle,
    )
    static_bundle_path = _identity_directory(run_root / "static-features", static.feature_bundle_id)
    static_features = load_verified_feature_bundle_v2(
        static_bundle_path,
        artifact_root=run_root / "static-features" / "feature-artifacts",
    )
    static_report = replay_feature_bundle_v2(
        bundle_path=static_bundle_path,
        artifact_root=run_root / "static-features" / "feature-artifacts",
        verified_dataset=daily,
    )
    if not static_report.semantic_match:
        raise ValueError("Controlled replay static Feature divergence")
    components.append(("STATIC_FEATURE_BUNDLE", static.content_hash))

    research_path = _single_ref_path(run_root, package, "CONTROLLED_RESEARCH")
    research = load_verified_controlled_research_artifact(research_path)
    ControlledPlatformResearchRunner().replay(
        path=research_path,
        static_feature_bundle=static_features,
    )
    candidates = research.artifact.candidate_set
    components.append(("CANDIDATE_SET", candidates.envelope.content_hash))

    coverage = _load_ref(
        run_root,
        package,
        "MINUTE_ACQUISITION_COVERAGE",
        load_minute_acquisition_coverage,
    )
    source_reader = RawMinuteSourceReader()
    normalized_sources = []
    for source_id, expected_hash in coverage.accepted_source_references:
        raw_source = source_reader.read(run_root / "minute-acquisition" / "sources" / str(source_id))
        if raw_source.content_hash != expected_hash:
            raise ValueError("Controlled replay minute Source reference mismatch")
        normalized_sources.append(
            (
                normalize_tencent_minute_source(
                    artifact=raw_source,
                    asset_type=AssetType.A_SHARE,
                    volume_policy=CanonicalVolumeUnitPolicy.a_share_v1(),
                ),
                raw_source,
            )
        )
    minute_path = _single_ref_path(run_root, package, "MINUTE_DATASET")
    minute = replay_market_data_dataset(minute_path)
    recomputed_minute = minute_normalizations_to_dataset(
        normalized_sources=tuple(normalized_sources),
        expected_symbols=tuple(sorted(item.symbol for item in candidates.selected)),
        decision_time=minute.artifact.decision_time,
        created_at=minute.artifact.created_at,
    )
    if recomputed_minute.to_canonical_dict() != minute.artifact.to_canonical_dict():
        raise ValueError("Controlled replay minute Dataset divergence")
    components.append(("MINUTE_DATASET", minute.artifact.content_hash))

    overlay = _load_ref(
        run_root,
        package,
        "INTRADAY_FEATURE_OVERLAY",
        load_candidate_intraday_feature_overlay,
    )
    intraday_bundle_path = _identity_directory(run_root / "intraday-features", overlay.intraday_feature_bundle_id)
    intraday_features = load_verified_feature_bundle_v2(
        intraday_bundle_path,
        artifact_root=run_root / "intraday-features" / "feature-artifacts",
    )
    intraday_report = replay_feature_bundle_v2(
        bundle_path=intraday_bundle_path,
        artifact_root=run_root / "intraday-features" / "feature-artifacts",
        verified_dataset=minute,
    )
    if not intraday_report.semantic_match:
        raise ValueError("Controlled replay intraday Feature divergence")
    replayed_overlay = CandidateIntradayFeatureOverlay.create(
        candidate_set=candidates,
        static_bundle=static,
        minute_dataset=minute,
        intraday_feature_bundle=intraday_features,
        trading_calendar=calendar,
    )
    if replayed_overlay != overlay:
        raise ValueError("Controlled replay intraday Overlay divergence")
    components.append(("INTRADAY_FEATURE_OVERLAY", overlay.content_hash))

    view_path = _single_ref_path(run_root, package, "CANDIDATE_FEATURE_VIEW_V2")
    view = load_candidate_feature_view_v2(view_path)
    if (
        CandidateFeatureViewV2.create(
            candidate_set=candidates,
            static_bundle=static,
            intraday_overlay=overlay,
        )
        != view
    ):
        raise ValueError("Controlled replay CandidateFeatureViewV2 divergence")
    signal_path = _single_ref_path(run_root, package, "SIGNAL_V3")
    signal = replay_signal_run_v3(
        signal_path,
        feature_bundle=static_features,
        verified_dataset=daily,
        trading_calendar=calendar,
        static_bundle=static,
        intraday_overlay=overlay,
        intraday_feature_bundle=intraday_features,
        minute_dataset=minute,
    )
    components.append(("SIGNAL_V3", signal.artifact.envelope.content_hash))

    forecasts = tuple(replay_path_forecast(path) for path in _ref_paths(run_root, package, "PATH_FORECAST"))
    entry = _load_ref(run_root, package, "ENTRY_BLOCKER", load_controlled_entry_blocker)
    replayed_entry = ControlledEntryAssessmentBlocker.create(
        signal=signal,
        forecasts=forecasts,
        created_at=entry.created_at,
    )
    if replayed_entry != entry:
        raise ValueError("Controlled replay Entry blocker divergence")
    components.append(("ENTRY_BLOCKER", entry.content_hash))
    canonical_run = _load_ref(
        run_root,
        package,
        "CANONICAL_LIFECYCLE_RUN",
        load_controlled_canonical_lifecycle_run,
    )
    expected_inputs = (
        CanonicalLifecycleRunObjectReference(
            "CANDIDATE_FEATURE_VIEW_V2",
            view.view_id,
            view.content_hash,
        ),
    )
    expected_outputs = tuple(
        sorted(
            (
            CanonicalLifecycleRunObjectReference(
                "SIGNAL_V3",
                signal.artifact.artifact_id,
                signal.artifact.envelope.content_hash,
            ),
            *(
                CanonicalLifecycleRunObjectReference(
                    "PATH_FORECAST",
                    item.artifact.artifact_id,
                    item.artifact.forecast.envelope.content_hash,
                )
                for item in forecasts
            ),
            CanonicalLifecycleRunObjectReference(
                "ENTRY_BLOCKER",
                entry.artifact_id,
                entry.content_hash,
            ),
            ),
            key=lambda item: (item.reference_type, str(item.object_id)),
        )
    )
    if (
        canonical_run.parent_operation_run_id != package.command.run_id
        or canonical_run.parent_operation_command_hash
        != package.command.command_hash
        or canonical_run.decision_time != package.command.decision_time
        or canonical_run.code_revision != package.code_revision
        or canonical_run.configuration_manifest_hash
        != package.configuration_manifest_hash
        or canonical_run.model_manifest_hash != package.model_manifest_hash
        or canonical_run.input_references != expected_inputs
        or canonical_run.output_references != expected_outputs
    ):
        raise ValueError("Controlled replay Canonical child-run divergence")
    if canonical_run.schema_version != LEGACY_CONTROLLED_CANONICAL_RUN_SCHEMA:
        canonical_repository = canonical_repository_factory(True)
        lifecycle_run_id = LifecycleRunId(str(canonical_run.run_id))
        stored_command = canonical_repository.get_command(lifecycle_run_id)
        stored_history = canonical_repository.history(lifecycle_run_id)
        receipt_by_stage = {
            item.stage_name: item.receipt_hash for item in stored_history.receipts
        }
        expected_receipts = tuple(
            receipt_by_stage[LifecycleStageName(stage)]
            for stage in canonical_run.completed_stages
        )
        if (
            stored_command.command_hash != canonical_run.command_hash
            or stored_history.run.command_hash != canonical_run.command_hash
            or lifecycle_history_hash(stored_history) != canonical_run.history_hash
            or tuple(
                item.stage_name.value
                for item in stored_history.stages
                if item.stage_name in receipt_by_stage
            )
            != canonical_run.completed_stages
            or expected_receipts != canonical_run.stage_receipt_hashes
            or stored_history.run.status.value != canonical_run.lifecycle_status
        ):
            raise ValueError("Controlled replay Canonical durable journal divergence")
    static_child = _feature_child_reference(
        run_root / "static-features",
        bundle_id=static.feature_bundle_id,
        bundle_hash=static.feature_bundle_hash,
        receipt_loader=receipt_loader,
    )
    intraday_child = _feature_child_reference(
        run_root / "intraday-features",
        bundle_id=overlay.intraday_feature_bundle_id,
        bundle_hash=overlay.intraday_feature_bundle_hash,
        receipt_loader=receipt_loader,
    )
    expected_children = {
        "DAILY_ACQUISITION_RUN": {
            (source.acquisition_key or str(source.artifact_id), source.checksums_hash)
        },
        "STATIC_FEATURE_RUN": {static_child},
        "MINUTE_ACQUISITION_BATCH": {
            (str(coverage.command.command_id), coverage.content_hash)
        },
        "INTRADAY_FEATURE_RUN": {intraday_child},
        "CANONICAL_LIFECYCLE_RUN": {
            (str(canonical_run.run_id), canonical_run.content_hash)
        },
    }
    components.append(("CANONICAL_LIFECYCLE_RUN", canonical_run.content_hash))

    if package.status is ControlledOperationalEvidenceStatus.SETTLED:
        outcome_source_archive = _load_ref(
            run_root,
            package,
            "OUTCOME_SOURCE_ARCHIVE",
            load_outcome_settlement_source_archive,
        )
        outcome_source_manifest = _load_ref(
            run_root,
            package,
            "OUTCOME_SOURCE_MANIFEST",
            load_controlled_source_manifest,
        )
        if (
            outcome_source_archive.source_manifest_id
            != outcome_source_manifest.source_manifest_id
            or outcome_source_archive.source_manifest_hash
            != outcome_source_manifest.content_hash
        ):
            raise ValueError("Controlled replay Outcome source lineage divergence")
        outcome_path = _single_ref_path(run_root, package, "OUTCOME_OBSERVATION")
        outcome = replay_trade_horizon_outcome_evidence(outcome_path)
        settlement = replay_market_data_dataset(_single_ref_path(run_root, package, "OUTCOME_DATASET"))
        if (
            outcome_source_manifest.source_manifest_id,
            outcome_source_manifest.content_hash,
        ) not in settlement.artifact.source_manifest_references:
            raise ValueError("Controlled replay Outcome Dataset lineage divergence")
        if outcome_source_archive.next_session_date != outcome.observations[0].next_session_date:
            raise ValueError("Controlled replay Outcome source session divergence")
        replayed_settlement = replay_outcome_dataset_from_source_archive(
            archive_path=_single_ref_path(
                run_root,
                package,
                "OUTCOME_SOURCE_ARCHIVE",
            ),
            source_manifest=outcome_source_manifest,
            expected_dataset=settlement,
        )
        if replayed_settlement.to_canonical_dict() != settlement.artifact.to_canonical_dict():
            raise ValueError("Controlled replay Outcome Dataset source divergence")
        pending_path = package_path.parent / str(package.supersedes_package_id)
        pending = load_controlled_operation_package(pending_path)
        replayed_outcome = build_trade_horizon_outcome_evidence(
            operation_package=pending,
            candidate_set=candidates,
            signal=signal,
            forecasts=forecasts,
            decision_dataset=daily,
            settlement_dataset=settlement,
            next_session_date=outcome.observations[0].next_session_date,
            horizon=outcome.horizon,
            created_at=outcome.created_at,
        )
        if replayed_outcome != outcome:
            raise ValueError("Controlled replay T+1 Outcome divergence")
        expected_children["OUTCOME_RUN"] = {
            (str(outcome.artifact_id), outcome.content_hash)
        }
        components.append(
            ("OUTCOME_SOURCE_ARCHIVE", outcome_source_archive.content_hash)
        )
        components.append(("OUTCOME_OBSERVATION", outcome.content_hash))

    _validate_stage_receipt_bindings(
        package,
        expected_children=expected_children,
    )
    component_hashes = tuple(sorted(components))
    receipt_fingerprint = canonical_hash({"stage_receipts": [item.to_canonical_dict() for item in package.stage_receipts]})
    semantic_hash = canonical_hash(
        {
            "package_hash": package.content_hash,
            "component_hashes": [list(item) for item in component_hashes],
            "receipt_fingerprint": receipt_fingerprint,
        }
    )
    return ControlledOperationReplayReport(
        package_id=package.package_id,
        package_hash=package.content_hash,
        package_status=package.status,
        component_hashes=component_hashes,
        receipt_fingerprint=receipt_fingerprint,
        semantic_hash=semantic_hash,
    )


T = TypeVar("T")


def _load_ref(
    run_root: Path,
    package: ControlledOperationalEvidencePackage,
    reference_type: str,
    loader: Callable[[Path], T],
) -> T:
    reference = _single_ref(package, reference_type)
    result = loader(_resolved_locator(run_root, reference))
    actual_id, actual_hash = _identity(result)
    if actual_id != reference.object_id or actual_hash != reference.content_hash:
        raise ValueError(f"Controlled replay reference mismatch: {reference_type}")
    return result


def _identity(value: object) -> tuple[ArtifactId, str]:
    for id_name, hash_name in (
        ("artifact_id", "content_hash"),
        ("universe_id", "content_hash"),
        ("source_manifest_id", "content_hash"),
        ("run_id", "content_hash"),
    ):
        if hasattr(value, id_name) and hasattr(value, hash_name):
            return (
                ArtifactId(str(getattr(value, id_name))),
                str(getattr(value, hash_name)),
            )
    if hasattr(value, "artifact"):
        return _identity(getattr(value, "artifact"))
    if hasattr(value, "dataset_id") and hasattr(value, "content_hash"):
        return (
            ArtifactId(str(getattr(value, "dataset_id"))),
            str(getattr(value, "content_hash")),
        )
    raise TypeError(f"unsupported Controlled replay identity: {type(value).__name__}")


def _validate_stage_receipt_bindings(
    package: ControlledOperationalEvidencePackage,
    *,
    expected_children: dict[str, set[tuple[str, str]]],
) -> None:
    evidence = {
        (item.reference_type, str(item.object_id)): item.content_hash
        for item in package.evidence_references
    }
    actual_children: dict[str, list[tuple[str, str]]] = {}
    for receipt in package.stage_receipts:
        for reference in receipt.output_references:
            expected = evidence.get(
                (reference.reference_type, str(reference.object_id))
            )
            if (
                expected is None
                and reference.reference_type == "OPERATION_PACKAGE"
                and package.supersedes_package_id == reference.object_id
            ):
                expected = package.supersedes_package_hash
            if expected is None or expected != reference.content_hash:
                raise ValueError(
                    f"Controlled replay stage Receipt output divergence: {receipt.stage_name.value}"
                )
        for child in receipt.child_run_references:
            actual_children.setdefault(child.reference_kind.value, []).append(
                (child.child_run_id, child.child_receipt_hash)
            )
            expected_child_set = expected_children.get(child.reference_kind.value)
            if expected_child_set is None or (
                child.child_run_id,
                child.child_receipt_hash,
            ) not in expected_child_set:
                raise ValueError(
                    "Controlled replay child Receipt divergence: "
                    f"{child.reference_kind.value}"
                )
    actual_child_sets = {
        kind: set(values) for kind, values in actual_children.items()
    }
    if (
        actual_child_sets != expected_children
        or any(len(values) != len(set(values)) for values in actual_children.values())
    ):
        raise ValueError("Controlled replay child Receipt set is incomplete or duplicated")


def _feature_child_reference(
    output_root: Path,
    *,
    bundle_id: ArtifactId,
    bundle_hash: str,
    receipt_loader: Callable[[Path], tuple[FeatureMaterializationReceipt, ...]],
) -> tuple[str, str]:
    matches = [
        receipt
        for receipt in receipt_loader(output_root)
        if receipt.bundle_id == bundle_id and receipt.bundle_hash == bundle_hash
    ]
    if len(matches) != 1:
        raise ValueError("Controlled replay Feature child Receipt is ambiguous")
    return matches[0].command_hash, matches[0].content_hash


def _single_ref(
    package: ControlledOperationalEvidencePackage,
    reference_type: str,
) -> ControlledEvidenceReference:
    matches = tuple(item for item in package.evidence_references if item.reference_type == reference_type)
    if len(matches) != 1:
        raise ValueError(f"Controlled replay requires one {reference_type} reference")
    return matches[0]


def _ref_paths(
    run_root: Path,
    package: ControlledOperationalEvidencePackage,
    reference_type: str,
) -> tuple[Path, ...]:
    references = tuple(item for item in package.evidence_references if item.reference_type == reference_type)
    if not references:
        raise ValueError(f"Controlled replay reference missing: {reference_type}")
    return tuple(_resolved_locator(run_root, item) for item in references)


def _single_ref_path(
    run_root: Path,
    package: ControlledOperationalEvidencePackage,
    reference_type: str,
) -> Path:
    return _resolved_locator(run_root, _single_ref(package, reference_type))


def _resolved_locator(run_root: Path, reference: ControlledEvidenceReference) -> Path:
    root = run_root.resolve()
    path = (root / reference.locator).resolve()
    if path != root and root not in path.parents:
        raise ValueError("Controlled replay locator escapes run root")
    return path


def _identity_directory(root: Path, object_id: ArtifactId) -> Path:
    matches = tuple(path for path in root.rglob(str(object_id)) if path.is_dir())
    if len(matches) != 1:
        raise ValueError(f"Controlled replay identity directory mismatch: {object_id}")
    return matches[0]


__all__ = [
    "ControlledOperationReplayReport",
    "replay_controlled_operation",
]
