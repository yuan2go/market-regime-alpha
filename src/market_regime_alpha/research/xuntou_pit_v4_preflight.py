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
from market_regime_alpha.research.xuntou_pit_v4_qualification import (
    PITEvidenceQualification,
    derive_pit_qualification,
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
    inputs = payload.get("qualification_inputs")
    if not isinstance(inputs, dict):
        return _result(
            XuntouPITV4PreflightStatus.INSUFFICIENT_PROVIDER_CAPABILITY,
            content_hash,
            None,
            ("QUALIFICATION_EVIDENCE_MISSING",),
        )
    qualification = derive_pit_qualification(
        historical_membership_complete=inputs.get("historical_membership_complete") is True,
        security_master_complete=inputs.get("security_master_complete") is True,
        st_history_complete=inputs.get("st_history_complete") is True,
        suspension_history_complete=inputs.get("suspension_history_complete") is True,
        orderability_complete=inputs.get("orderability_complete") is True,
        liquidity_unit_verified=inputs.get("liquidity_unit_verified") is True,
        bar_finality_verified=inputs.get("bar_finality_verified") is True,
        availability_verified=inputs.get("availability_verified") is True,
        evaluation_path_complete=inputs.get("evaluation_path_complete") is True,
        membership_sources=tuple(str(value) for value in inputs.get("membership_sources", ())),
        input_declared_pit_correct=payload.get("pit_correct_for_scope"),
    )
    status = (
        XuntouPITV4PreflightStatus.AVAILABLE
        if qualification.pit_correct_for_scope
        else XuntouPITV4PreflightStatus.INSUFFICIENT_PROVIDER_CAPABILITY
    )
    return _result(status, content_hash, qualification, qualification.reasons)


def _result(
    status: XuntouPITV4PreflightStatus,
    content_hash: str | None,
    qualification: PITEvidenceQualification | None,
    reasons: tuple[str, ...],
) -> XuntouPITV4Preflight:
    return XuntouPITV4Preflight(
        "xuntou-pit-validation-preflight-v4",
        status,
        "XUNTOU",
        XUNTOU_PIT_V4_BUNDLE_SCHEMA_VERSION,
        content_hash,
        qualification,
        reasons,
        False,
        False,
    )


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"
