"""Atomic immutable Phase D Daily Decision Artifact Publisher."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from market_regime_alpha.application.daily_loop.commands import DailyRunIdentity
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.daily_quality import (
    DailyDataQualityStatus,
    DataQualityReport,
)
from market_regime_alpha.data.source_manifest import SourceManifest
from market_regime_alpha.daily_decision._support import canonical_hash
from market_regime_alpha.daily_decision.entry import EntryAssessment
from market_regime_alpha.daily_decision.recommendation import (
    CandidateRecommendation,
)
from market_regime_alpha.daily_decision.report import render_phase_d_daily_report
from market_regime_alpha.daily_decision.serialization import (
    eligibility_snapshot_to_dict,
    feature_definition_to_dict,
    feature_materialization_to_dict,
    universe_snapshot_to_dict,
)
from market_regime_alpha.daily_decision.snapshot import DecisionPriceSnapshot
from market_regime_alpha.features.contracts import (
    FeatureDefinition,
    FeatureMaterialization,
)
from market_regime_alpha.platform.prediction_run import PredictionRun
from market_regime_alpha.universe.contracts import (
    PITUniverseSnapshot,
    TradingEligibilitySnapshot,
)


PHASE_D_DAILY_DECISION_SCHEMA = "phase-d-daily-decision-artifact-v1"
PHASE_D_DAILY_DECISION_FILES = (
    "SHA256SUMS.json",
    "candidate_recommendations.json",
    "data_quality_report.json",
    "decision_price_snapshot.json",
    "eligibility_snapshot.json",
    "entry_assessments.json",
    "feature_manifest.json",
    "manifest.json",
    "prediction_runs.json",
    "report.md",
    "source_manifest.json",
    "universe_snapshot.json",
)
FORMAL_OOS_AUTHORITY = "FORMAL_OOS_ALPHA_NOT_ESTABLISHED"
TRADING_AUTHORITY = "TRADING_AUTHORITY_NOT_GRANTED"
DELIVERY_AUTHORITY = "EXPLORATORY_DAILY_LOOP_OPERATIONAL"


class DailyDecisionArtifactStatus(str, Enum):
    DATA_BLOCKED = "DATA_BLOCKED"
    DECISION_PUBLISHED = "DECISION_PUBLISHED"


@dataclass(frozen=True, slots=True)
class PhaseDDailyDecisionBundle:
    """Complete semantic payload for either decision publication or DATA_BLOCKED."""

    status: DailyDecisionArtifactStatus
    run_identity: DailyRunIdentity
    source_archive_id: ArtifactId
    source_manifest: SourceManifest
    data_quality_report: DataQualityReport
    universe_snapshot: PITUniverseSnapshot | None
    eligibility_snapshot: TradingEligibilitySnapshot | None
    decision_price_snapshot: DecisionPriceSnapshot | None
    feature_definitions: tuple[FeatureDefinition, ...]
    feature_materializations: tuple[FeatureMaterialization, ...]
    prediction_runs: tuple[PredictionRun, ...]
    recommendations: tuple[CandidateRecommendation, ...]
    entry_assessments: tuple[EntryAssessment, ...]
    content_hash: str = field(init=False)
    artifact_id: ArtifactId = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.status, DailyDecisionArtifactStatus):
            raise TypeError("status must be a DailyDecisionArtifactStatus")
        if (
            self.run_identity.source_manifest_id
            != self.source_manifest.source_manifest_id
            or self.run_identity.source_manifest_content_hash
            != self.source_manifest.content_hash
            or self.run_identity.source_content_hashes
            != tuple(sorted(set(self.source_manifest.source_hashes)))
        ):
            raise ValueError("DailyRunIdentity does not bind exact Source Freeze")
        if (
            self.data_quality_report.source_manifest_id
            != self.source_manifest.source_manifest_id
        ):
            raise ValueError("DataQualityReport does not bind SourceManifest")
        if (
            self.decision_price_snapshot is not None
            and (
                self.decision_price_snapshot.source_manifest_id
                != self.source_manifest.source_manifest_id
                or self.decision_price_snapshot.decision_time
                != self.source_manifest.decision_time
            )
        ):
            raise ValueError("Decision Price Snapshot scope mismatch")
        self._validate_feature_lineage()
        if self.status is DailyDecisionArtifactStatus.DATA_BLOCKED:
            self._validate_blocked()
        else:
            self._validate_published()
        content_hash = canonical_hash(self.semantic_payload())
        object.__setattr__(self, "content_hash", content_hash)
        object.__setattr__(
            self,
            "artifact_id",
            ArtifactId(f"daily-decision-{content_hash.split(':', 1)[1][:24]}"),
        )

    def _validate_feature_lineage(self) -> None:
        definition_ids = tuple(item.feature_id for item in self.feature_definitions)
        materialization_definition_ids = tuple(
            item.definition_id for item in self.feature_materializations
        )
        if definition_ids != materialization_definition_ids:
            raise ValueError("Feature definitions and materializations must align")
        if len(definition_ids) != len(set(definition_ids)):
            raise ValueError("Feature definitions must be unique")

    def _validate_blocked(self) -> None:
        if self.data_quality_report.status is not DailyDataQualityStatus.DATA_BLOCKED:
            raise ValueError("DATA_BLOCKED Artifact requires DATA_BLOCKED quality")
        if any(
            (
                self.universe_snapshot is not None,
                self.eligibility_snapshot is not None,
                bool(self.feature_definitions),
                bool(self.feature_materializations),
                bool(self.prediction_runs),
                bool(self.recommendations),
                bool(self.entry_assessments),
            )
        ):
            raise ValueError("DATA_BLOCKED Artifact cannot carry downstream decisions")

    def _validate_published(self) -> None:
        if self.data_quality_report.status is DailyDataQualityStatus.DATA_BLOCKED:
            raise ValueError("published decision cannot bind DATA_BLOCKED quality")
        if (
            self.universe_snapshot is None
            or self.eligibility_snapshot is None
            or self.decision_price_snapshot is None
            or not self.feature_definitions
            or not self.prediction_runs
        ):
            raise ValueError("published decision requires complete pipeline evidence")
        if (
            self.universe_snapshot.universe_id
            != self.prediction_runs[0].universe_id
            or self.eligibility_snapshot.source_dataset_id
            != self.universe_snapshot.source_dataset_id
        ):
            raise ValueError("published Universe/Prediction scope mismatch")
        run_ids = tuple(item.prediction_run_id for item in self.prediction_runs)
        model_ids = tuple(item.model_id for item in self.prediction_runs)
        if len(run_ids) != len(set(run_ids)) or len(model_ids) != len(set(model_ids)):
            raise ValueError("PredictionRuns must be unique")
        if any(
            item.data_eligibility is not DataEligibility.EXPLORATORY
            for item in self.prediction_runs
        ):
            raise ValueError("published Predictions are EXPLORATORY-only")
        run_by_id = {
            item.prediction_run_id: item for item in self.prediction_runs
        }
        recommendation_ids: set[ArtifactId] = set()
        last_order: tuple[int, int] | None = None
        run_order = {
            item.prediction_run_id: index
            for index, item in enumerate(self.prediction_runs)
        }
        for item in self.recommendations:
            run = run_by_id.get(item.prediction_run_id)
            if (
                run is None
                or item.model_id != run.model_id
                or item.target_id != run.target_id
                or item.decision_snapshot_id
                != self.decision_price_snapshot.decision_snapshot_id
            ):
                raise ValueError("Recommendation lineage mismatch")
            order = (run_order[item.prediction_run_id], item.rank)
            if last_order is not None and order <= last_order:
                raise ValueError("Recommendations are not in canonical model/rank order")
            last_order = order
            recommendation_ids.add(item.recommendation_id)
        if len(recommendation_ids) != len(self.recommendations):
            raise ValueError("Recommendations must be unique")
        if len(self.entry_assessments) != len(self.recommendations):
            raise ValueError("every Recommendation requires one EntryAssessment")
        for assessment, recommendation in zip(
            self.entry_assessments,
            self.recommendations,
            strict=True,
        ):
            if (
                assessment.recommendation_id != recommendation.recommendation_id
                or assessment.prediction_run_id
                != recommendation.prediction_run_id
                or assessment.decision_snapshot_id
                != recommendation.decision_snapshot_id
                or assessment.symbol != recommendation.symbol
            ):
                raise ValueError("EntryAssessment lineage mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": PHASE_D_DAILY_DECISION_SCHEMA,
            "status": self.status.value,
            "run_identity": self.run_identity.to_canonical_dict(),
            "source_archive_id": str(self.source_archive_id),
            "source_manifest": self.source_manifest.to_canonical_dict(),
            "data_quality_report": self.data_quality_report.to_canonical_dict(),
            "universe_snapshot": (
                universe_snapshot_to_dict(self.universe_snapshot)
                if self.universe_snapshot is not None
                else None
            ),
            "eligibility_snapshot": (
                eligibility_snapshot_to_dict(self.eligibility_snapshot)
                if self.eligibility_snapshot is not None
                else None
            ),
            "decision_price_snapshot": (
                self.decision_price_snapshot.to_canonical_dict()
                if self.decision_price_snapshot is not None
                else None
            ),
            "feature_definitions": [
                feature_definition_to_dict(item)
                for item in self.feature_definitions
            ],
            "feature_materializations": [
                feature_materialization_to_dict(item)
                for item in self.feature_materializations
            ],
            "prediction_runs": [
                item.to_canonical_dict() for item in self.prediction_runs
            ],
            "recommendations": [
                item.to_canonical_dict() for item in self.recommendations
            ],
            "entry_assessments": [
                item.to_canonical_dict() for item in self.entry_assessments
            ],
            "delivery_authority": DELIVERY_AUTHORITY,
            "formal_oos_authority": FORMAL_OOS_AUTHORITY,
            "trading_authority": TRADING_AUTHORITY,
        }


def build_phase_d_manifest(
    bundle: PhaseDDailyDecisionBundle,
) -> dict[str, Any]:
    return {
        "schema_version": PHASE_D_DAILY_DECISION_SCHEMA,
        "artifact_id": str(bundle.artifact_id),
        "content_hash": bundle.content_hash,
        "status": bundle.status.value,
        "run_identity": bundle.run_identity.to_canonical_dict(),
        "source_archive_id": str(bundle.source_archive_id),
        "source_manifest_id": str(bundle.source_manifest.source_manifest_id),
        "source_manifest_hash": bundle.source_manifest.content_hash,
        "data_quality_report_id": str(bundle.data_quality_report.report_id),
        "required_artifacts": sorted(PHASE_D_DAILY_DECISION_FILES),
        "evidence_authority": "IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT",
        "delivery_authority": DELIVERY_AUTHORITY,
        "formal_oos_authority": FORMAL_OOS_AUTHORITY,
        "trading_authority": TRADING_AUTHORITY,
    }


def publish_phase_d_daily_decision_artifact(
    *,
    root: Path,
    bundle: PhaseDDailyDecisionBundle,
) -> Path:
    """Stage and atomically publish one exact non-overwriting package."""

    root.mkdir(parents=True, exist_ok=True)
    final = root / str(bundle.artifact_id)
    if final.exists():
        raise FileExistsError(f"Phase D Daily Decision Artifact exists: {final}")
    stage = Path(
        tempfile.mkdtemp(prefix=f".{bundle.artifact_id}.", dir=root)
    )
    try:
        _write_json(stage / "manifest.json", build_phase_d_manifest(bundle))
        _write_json(
            stage / "source_manifest.json",
            bundle.source_manifest.to_canonical_dict(),
        )
        _write_json(
            stage / "data_quality_report.json",
            bundle.data_quality_report.to_canonical_dict(),
        )
        _write_json(
            stage / "universe_snapshot.json",
            {
                "schema_version": "phase-d-universe-snapshot-v1",
                "snapshot": (
                    universe_snapshot_to_dict(bundle.universe_snapshot)
                    if bundle.universe_snapshot is not None
                    else None
                ),
            },
        )
        _write_json(
            stage / "eligibility_snapshot.json",
            {
                "schema_version": "phase-d-eligibility-snapshot-v1",
                "snapshot": (
                    eligibility_snapshot_to_dict(bundle.eligibility_snapshot)
                    if bundle.eligibility_snapshot is not None
                    else None
                ),
            },
        )
        _write_json(
            stage / "decision_price_snapshot.json",
            {
                "schema_version": "phase-d-decision-price-file-v1",
                "snapshot": (
                    bundle.decision_price_snapshot.to_canonical_dict()
                    if bundle.decision_price_snapshot is not None
                    else None
                ),
            },
        )
        _write_json(
            stage / "feature_manifest.json",
            {
                "schema_version": "phase-d-feature-manifest-v1",
                "definitions": [
                    feature_definition_to_dict(item)
                    for item in bundle.feature_definitions
                ],
                "materializations": [
                    feature_materialization_to_dict(item)
                    for item in bundle.feature_materializations
                ],
            },
        )
        _write_json(
            stage / "prediction_runs.json",
            {
                "schema_version": "phase-d-prediction-runs-v1",
                "items": [
                    item.to_canonical_dict() for item in bundle.prediction_runs
                ],
            },
        )
        _write_json(
            stage / "candidate_recommendations.json",
            {
                "schema_version": "phase-d-candidate-recommendations-v1",
                "items": [
                    item.to_canonical_dict() for item in bundle.recommendations
                ],
            },
        )
        _write_json(
            stage / "entry_assessments.json",
            {
                "schema_version": "phase-d-entry-assessments-v1",
                "items": [
                    item.to_canonical_dict()
                    for item in bundle.entry_assessments
                ],
            },
        )
        (stage / "report.md").write_text(
            render_phase_d_daily_report(bundle),
            encoding="utf-8",
        )
        checksums = {
            name: _file_hash(stage / name)
            for name in PHASE_D_DAILY_DECISION_FILES
            if name != "SHA256SUMS.json"
        }
        _write_json(stage / "SHA256SUMS.json", checksums)
        if {item.name for item in stage.iterdir()} != set(
            PHASE_D_DAILY_DECISION_FILES
        ):
            raise RuntimeError("Phase D Daily Decision exact file set mismatch")
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


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


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"
