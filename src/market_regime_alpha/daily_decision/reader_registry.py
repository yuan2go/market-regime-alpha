"""Versioned reader routing isolated from historical daily_research V1."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable

from market_regime_alpha.daily_decision.artifact import (
    PHASE_D_DAILY_DECISION_SCHEMA,
)
from market_regime_alpha.daily_decision.reader import (
    VerifiedPhaseDDailyDecisionArtifact,
    load_verified_phase_d_daily_decision_artifact,
)


DailyDecisionLoader = Callable[[Path], VerifiedPhaseDDailyDecisionArtifact]


@dataclass(frozen=True, slots=True)
class DailyDecisionReaderRegistration:
    schema_version: str
    reader_id: str
    loader: DailyDecisionLoader


def build_daily_decision_reader_registry(
    registrations: tuple[DailyDecisionReaderRegistration, ...],
) -> dict[str, DailyDecisionReaderRegistration]:
    result: dict[str, DailyDecisionReaderRegistration] = {}
    for item in registrations:
        if not item.schema_version or not item.reader_id:
            raise ValueError("daily decision Reader identity must be non-empty")
        if item.schema_version in result:
            raise ValueError("duplicate daily decision Reader schema")
        result[item.schema_version] = item
    return result


DAILY_DECISION_READER_REGISTRY = build_daily_decision_reader_registry(
    (
        DailyDecisionReaderRegistration(
            schema_version=PHASE_D_DAILY_DECISION_SCHEMA,
            reader_id="phase-d-daily-decision-semantic-reader-v1",
            loader=load_verified_phase_d_daily_decision_artifact,
        ),
    )
)


def load_verified_daily_decision_artifact(
    path: Path,
) -> VerifiedPhaseDDailyDecisionArtifact:
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("daily decision Artifact manifest is missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("daily decision Artifact manifest is invalid") from exc
    if not isinstance(manifest, dict):
        raise ValueError("daily decision Artifact manifest must be an object")
    schema = manifest.get("schema_version")
    if not isinstance(schema, str):
        raise ValueError("daily decision Artifact schema is missing")
    registration = DAILY_DECISION_READER_REGISTRY.get(schema)
    if registration is None:
        raise ValueError(
            f"unsupported daily decision Artifact schema: {schema}"
        )
    verified = registration.loader(path)
    if verified.manifest["schema_version"] != registration.schema_version:
        raise ValueError("daily decision Reader returned the wrong schema")
    return verified
