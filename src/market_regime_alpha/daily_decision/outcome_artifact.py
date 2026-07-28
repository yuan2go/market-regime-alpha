"""Immutable append-only Outcome Settlement and DailyReview Artifact."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
from types import MappingProxyType
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId, UniverseId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.daily_decision.outcome import (
    DailyReviewReport,
    OutcomeSettlement,
    PopulationTargetObservation,
    RecommendationOutcome,
)
from market_regime_alpha.daily_decision.target_adapter import (
    mr1_next_session_1030_target_protocol,
)


DAILY_REVIEW_ARTIFACT_SCHEMA = "phase-d-daily-review-artifact-v1"
DAILY_REVIEW_ARTIFACT_FILES = (
    "SHA256SUMS.json",
    "daily_review.json",
    "manifest.json",
    "population_outcomes.json",
    "recommendation_outcomes.json",
    "report.md",
    "target_protocol.json",
)


@dataclass(frozen=True, slots=True)
class VerifiedDailyReviewArtifact:
    root: Path
    artifact_id: str
    settlement: OutcomeSettlement
    manifest: Mapping[str, Any]
    checksums_hash: str


def _artifact_id(settlement: OutcomeSettlement) -> str:
    return f"daily-review-artifact-{settlement.content_hash.split(':', 1)[1][:24]}"


def _manifest(settlement: OutcomeSettlement) -> dict[str, Any]:
    return {
        "schema_version": DAILY_REVIEW_ARTIFACT_SCHEMA,
        "artifact_id": _artifact_id(settlement),
        "settlement_id": str(settlement.settlement_id),
        "settlement_content_hash": settlement.content_hash,
        "daily_decision_artifact_id": str(
            settlement.daily_decision_artifact_id
        ),
        "daily_decision_content_hash": settlement.daily_decision_content_hash,
        "settlement_source_archive_id": str(
            settlement.settlement_source_archive_id
        ),
        "settlement_source_result_hash": (
            settlement.settlement_source_result_hash
        ),
        "next_session_date": settlement.next_session_date.isoformat(),
        "target_id": str(settlement.target_protocol.target_id),
        "review_id": str(settlement.review.review_id),
        "data_eligibility": settlement.data_eligibility.value,
        "required_artifacts": sorted(DAILY_REVIEW_ARTIFACT_FILES),
        "formal_oos_authority": "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
        "trading_authority": "TRADING_AUTHORITY_NOT_GRANTED",
    }


def publish_daily_review_artifact(
    *,
    root: Path,
    settlement: OutcomeSettlement,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    final = root / _artifact_id(settlement)
    if final.exists():
        raise FileExistsError(f"DailyReview Artifact exists: {final}")
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    try:
        _write_json(stage / "manifest.json", _manifest(settlement))
        _write_json(
            stage / "target_protocol.json",
            {
                **settlement.target_protocol.canonical_payload(),
                "protocol_hash": settlement.target_protocol.protocol_hash,
            },
        )
        _write_json(
            stage / "population_outcomes.json",
            {
                "schema_version": "phase-d-population-outcomes-v1",
                "items": [
                    item.to_canonical_dict()
                    for item in settlement.population_outcomes
                ],
            },
        )
        _write_json(
            stage / "recommendation_outcomes.json",
            {
                "schema_version": "phase-d-recommendation-outcomes-v1",
                "items": [
                    item.to_canonical_dict()
                    for item in settlement.recommendation_outcomes
                ],
            },
        )
        _write_json(
            stage / "daily_review.json",
            settlement.review.to_canonical_dict(),
        )
        (stage / "report.md").write_text(
            render_daily_review_report(settlement),
            encoding="utf-8",
        )
        _write_json(
            stage / "SHA256SUMS.json",
            {
                name: _file_hash(stage / name)
                for name in DAILY_REVIEW_ARTIFACT_FILES
                if name != "SHA256SUMS.json"
            },
        )
        if {item.name for item in stage.iterdir()} != set(
            DAILY_REVIEW_ARTIFACT_FILES
        ):
            raise RuntimeError("DailyReview exact file set mismatch")
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def load_verified_daily_review_artifact(
    path: Path,
) -> VerifiedDailyReviewArtifact:
    root = path.resolve()
    _verify_files(root)
    manifest = _read_object(root / "manifest.json")
    expected_fields = {
        "schema_version",
        "artifact_id",
        "settlement_id",
        "settlement_content_hash",
        "daily_decision_artifact_id",
        "daily_decision_content_hash",
        "settlement_source_archive_id",
        "settlement_source_result_hash",
        "next_session_date",
        "target_id",
        "review_id",
        "data_eligibility",
        "required_artifacts",
        "formal_oos_authority",
        "trading_authority",
    }
    if set(manifest) != expected_fields:
        raise ValueError("DailyReview manifest fields mismatch")
    if (
        manifest["schema_version"] != DAILY_REVIEW_ARTIFACT_SCHEMA
        or manifest["required_artifacts"] != sorted(DAILY_REVIEW_ARTIFACT_FILES)
    ):
        raise ValueError("DailyReview manifest schema mismatch")
    protocol_payload = _read_object(root / "target_protocol.json")
    if "protocol_hash" not in protocol_payload:
        raise ValueError("TargetProtocol hash missing")
    protocol_hash = protocol_payload.pop("protocol_hash")
    expected_protocol_fields = set(
        mr1_next_session_1030_target_protocol(
            UniverseId(str(protocol_payload["universe_id"]))
        ).canonical_payload()
    )
    if set(protocol_payload) != expected_protocol_fields:
        raise ValueError("TargetProtocol fields mismatch")
    protocol = mr1_next_session_1030_target_protocol(
        UniverseId(str(protocol_payload["universe_id"]))
    )
    if (
        protocol.canonical_payload() != protocol_payload
        or protocol.protocol_hash != protocol_hash
    ):
        raise ValueError("TargetProtocol semantic mismatch")
    population = tuple(
        PopulationTargetObservation.from_canonical_dict(
            _mapping(item, "PopulationTargetObservation")
        )
        for item in _read_items(
            root / "population_outcomes.json",
            "phase-d-population-outcomes-v1",
        )
    )
    recommendations = tuple(
        RecommendationOutcome.from_canonical_dict(
            _mapping(item, "RecommendationOutcome")
        )
        for item in _read_items(
            root / "recommendation_outcomes.json",
            "phase-d-recommendation-outcomes-v1",
        )
    )
    review = DailyReviewReport.from_canonical_dict(
        _read_object(root / "daily_review.json")
    )
    settlement = OutcomeSettlement(
        daily_decision_artifact_id=ArtifactId(
            str(manifest["daily_decision_artifact_id"])
        ),
        daily_decision_content_hash=str(
            manifest["daily_decision_content_hash"]
        ),
        settlement_source_archive_id=ArtifactId(
            str(manifest["settlement_source_archive_id"])
        ),
        settlement_source_result_hash=str(
            manifest["settlement_source_result_hash"]
        ),
        next_session_date=date.fromisoformat(
            str(manifest["next_session_date"])
        ),
        target_protocol=protocol,
        population_outcomes=population,
        recommendation_outcomes=recommendations,
        review=review,
        data_eligibility=DataEligibility(str(manifest["data_eligibility"])),
    )
    if manifest != _manifest(settlement):
        raise ValueError("DailyReview manifest is not reconstructible")
    if root.name != _artifact_id(settlement):
        raise ValueError("DailyReview directory identity mismatch")
    if (root / "report.md").read_text(
        encoding="utf-8"
    ) != render_daily_review_report(settlement):
        raise ValueError("DailyReview report is not reconstructible")
    return VerifiedDailyReviewArtifact(
        root=root,
        artifact_id=root.name,
        settlement=settlement,
        manifest=_deep_freeze(manifest),
        checksums_hash=_file_hash(root / "SHA256SUMS.json"),
    )


def render_daily_review_report(settlement: OutcomeSettlement) -> str:
    review = settlement.review
    top_mean = (
        f"{review.top_k_mean_target:.8f}"
        if review.top_k_mean_target is not None
        else "UNRESOLVED"
    )
    population_mean = (
        f"{review.candidate_population_mean_target:.8f}"
        if review.candidate_population_mean_target is not None
        else "UNRESOLVED"
    )
    return "\n".join(
        (
            "# Phase D Daily Review",
            "",
            f"- Daily Decision Artifact: `{settlement.daily_decision_artifact_id}`",
            f"- Target: `{settlement.target_protocol.target_id}`",
            f"- Recommendation count: `{review.recommendation_count}`",
            f"- Outcome coverage: `{review.outcome_coverage:.6f}`",
            f"- Positive return count: `{review.positive_return_count}`",
            f"- Top-k mean target: `{top_mean}`",
            f"- Candidate population mean target: `{population_mean}`",
            f"- Ranking coverage: `{review.ranking_coverage:.6f}`",
            f"- Unresolved outcome count: `{review.unresolved_outcome_count}`",
            (
                "- B0/B1 top-k overlap: "
                f"`{review.b0_b1_top_k_overlap_count}/"
                f"{review.b0_b1_top_k_union_count}`"
            ),
            "",
            "## Authority boundary",
            "",
            "- `EXPLORATORY_DAILY_LOOP_OPERATIONAL`",
            "- `FORMAL_OOS_ALPHA_NOT_ESTABLISHED`",
            "- `TRADING_AUTHORITY_NOT_GRANTED`",
            "",
        )
    )


def _verify_files(root: Path) -> None:
    if not root.is_dir():
        raise ValueError("DailyReview Artifact is missing")
    entries = tuple(root.iterdir())
    if {item.name for item in entries} != set(DAILY_REVIEW_ARTIFACT_FILES):
        raise ValueError("DailyReview exact file set mismatch")
    if any(not item.is_file() for item in entries):
        raise ValueError("DailyReview contains a non-file")
    checksums = _read_object(root / "SHA256SUMS.json")
    expected = set(DAILY_REVIEW_ARTIFACT_FILES) - {"SHA256SUMS.json"}
    if set(checksums) != expected:
        raise ValueError("DailyReview checksum coverage mismatch")
    for name, content_hash in checksums.items():
        if not isinstance(content_hash, str) or _file_hash(root / name) != content_hash:
            raise ValueError(f"DailyReview checksum mismatch: {name}")


def _read_items(path: Path, schema: str) -> list[Any]:
    payload = _read_object(path)
    if set(payload) != {"schema_version", "items"}:
        raise ValueError(f"{path.name} fields mismatch")
    if payload["schema_version"] != schema or not isinstance(
        payload["items"],
        list,
    ):
        raise ValueError(f"{path.name} schema mismatch")
    return payload["items"]


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid DailyReview JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


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


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType(
            {key: _deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value
