"""No-fallback preflight for qualified Xuntou PIT v4 inputs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from market_regime_alpha.research.xuntou_pit_v4_contract import (
    XUNTOU_PIT_V4_BUNDLE_SCHEMA_VERSION,
)
from market_regime_alpha.research.xuntou_pit_v4_evidence import validate_pit_v4_evidence
from market_regime_alpha.research.xuntou_pit_v4_qualification import (
    PITEvidenceQualification,
    build_qualified_pit_market_artifact,
)


class XuntouPITV4PreflightStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    BLOCKED_EXTERNAL_PROVIDER_INPUT = "BLOCKED_EXTERNAL_PROVIDER_INPUT"
    INVALID_PIT_EVIDENCE = "INVALID_PIT_EVIDENCE"
    INSUFFICIENT_PROVIDER_CAPABILITY = "INSUFFICIENT_PROVIDER_CAPABILITY"


@dataclass(frozen=True, slots=True)
class XuntouPITV4Preflight:
    schema_version: str
    status: XuntouPITV4PreflightStatus
    provider: str
    required_bundle_schema: str
    bundle_content_hash: str | None
    qualification: PITEvidenceQualification | None
    provider_artifact_id: str | None
    reasons: tuple[str, ...]
    tencent_fallback_used: bool
    research_result_produced: bool

    def to_public_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["reasons"] = list(self.reasons)
        if self.qualification is not None:
            payload["qualification"] = self.qualification.to_canonical_dict()
        return payload


def preflight_xuntou_pit_v4(bundle: Path | None) -> XuntouPITV4Preflight:
    if bundle is None or not bundle.exists():
        return _result(
            XuntouPITV4PreflightStatus.BLOCKED_EXTERNAL_PROVIDER_INPUT,
            None,
            None,
            ("EXTERNAL_XTQUANT_RUNTIME_AND_V4_BUNDLE_REQUIRED",),
        )
    content_hash = _hash(bundle) if bundle.is_file() else None
    if not bundle.is_file():
        return _result(
            XuntouPITV4PreflightStatus.INVALID_PIT_EVIDENCE,
            content_hash,
            None,
            ("V4_BUNDLE_MUST_BE_A_CONTENT_ADDRESSED_FILE",),
        )
    try:
        payload = json.loads(bundle.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return _result(
            XuntouPITV4PreflightStatus.INVALID_PIT_EVIDENCE,
            content_hash,
            None,
            ("V4_BUNDLE_IS_NOT_VALID_JSON",),
        )
    if not isinstance(payload, dict):
        return _result(XuntouPITV4PreflightStatus.INVALID_PIT_EVIDENCE, content_hash, None, ("V4_BUNDLE_ROOT_INVALID",))
    schema = payload.get("schema_version")
    if schema == "xuntou-p0-native-bundle-v3":
        return _result(
            XuntouPITV4PreflightStatus.INVALID_PIT_EVIDENCE,
            content_hash,
            None,
            ("V3_REHEARSAL_BUNDLE_CANNOT_BE_PROMOTED",),
        )
    if schema != XUNTOU_PIT_V4_BUNDLE_SCHEMA_VERSION:
        return _result(XuntouPITV4PreflightStatus.INVALID_PIT_EVIDENCE, content_hash, None, ("V4_BUNDLE_SCHEMA_MISMATCH",))
    if payload.get("evidence_classification") == "TEST_ONLY_NOT_RESEARCH_EVIDENCE":
        return _result(
            XuntouPITV4PreflightStatus.INVALID_PIT_EVIDENCE,
            content_hash,
            None,
            ("TEST_FIXTURE_NOT_RESEARCH_EVIDENCE",),
        )
    validation = validate_pit_v4_evidence(payload)
    qualification = validation.qualification
    if any(_invalid_evidence_reason(reason) for reason in validation.reasons):
        status = XuntouPITV4PreflightStatus.INVALID_PIT_EVIDENCE
    elif (
        qualification is not None
        and qualification.pit_correct_for_scope
        and not validation.reasons
    ):
        status = XuntouPITV4PreflightStatus.AVAILABLE
    else:
        status = XuntouPITV4PreflightStatus.INSUFFICIENT_PROVIDER_CAPABILITY
    provider_artifact_id = None
    if status is XuntouPITV4PreflightStatus.AVAILABLE:
        if validation.source is None or qualification is None:
            raise ValueError("available v4 evidence is missing its derived provider identity")
        provider_artifact_id = build_qualified_pit_market_artifact(
            source=validation.source,
            qualification=qualification,
        ).provider_artifact_id
    return _result(
        status,
        content_hash,
        qualification,
        validation.reasons,
        provider_artifact_id=provider_artifact_id,
    )


def _result(
    status: XuntouPITV4PreflightStatus,
    content_hash: str | None,
    qualification: PITEvidenceQualification | None,
    reasons: tuple[str, ...],
    *,
    provider_artifact_id: str | None = None,
) -> XuntouPITV4Preflight:
    return XuntouPITV4Preflight(
        "xuntou-pit-validation-preflight-v4",
        status,
        "XUNTOU",
        XUNTOU_PIT_V4_BUNDLE_SCHEMA_VERSION,
        content_hash,
        qualification,
        provider_artifact_id,
        reasons,
        False,
        False,
    )


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _invalid_evidence_reason(reason: str) -> bool:
    return (
        reason.endswith("_CONTENT_HASH_MISMATCH")
        or reason.endswith("_FIELDS_MISMATCH")
        or reason.endswith("_EVIDENCE_INVALID")
        or reason
        in {
            "SOURCE_ARTIFACT_RAW_HASH_IDENTITY_MISMATCH",
            "SOURCE_EVIDENCE_CLASSIFICATION_NOT_QUALIFIED",
            "RAW_SOURCE_HASH_EVIDENCE_INVALID",
            "V4_MAPPING_CONTRACT_MISMATCH",
            "V4_EVIDENCE_CONVENTION_MISMATCH",
            "PIT_EVIDENCE_SCOPE_INVALID",
            "EVIDENCE_SECTION_SET_MISMATCH",
        }
    )
