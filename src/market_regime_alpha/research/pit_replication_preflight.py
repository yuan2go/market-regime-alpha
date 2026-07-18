"""Provider-bound, no-fallback preflight for PIT Candidate replication."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any

from market_regime_alpha.research.provider_rehearsal_market_artifact import (
    ProviderRehearsalMarketArtifact,
)
from market_regime_alpha.research.provider_routing import ProviderAvailabilityStatus
from market_regime_alpha.research.wp3_orchestrator import NormalizedXuntouWP3Backend
from market_regime_alpha.research.xuntou_provider_adapter import (
    XUNTOU_P0_NATIVE_BUNDLE_SCHEMA_VERSION,
    XUNTOU_P0_PRODUCT,
)


class PITReplicationPreflightStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    BLOCKED_EXTERNAL_PROVIDER_INPUT = "BLOCKED_EXTERNAL_PROVIDER_INPUT"
    INVALID_PIT_EVIDENCE = "INVALID_PIT_EVIDENCE"


@dataclass(frozen=True, slots=True)
class PITReplicationPreflight:
    schema_version: str
    status: PITReplicationPreflightStatus
    provider: str
    required_bundle_schema: str
    required_product: str
    expected_source_files: tuple[str, ...]
    bundle_content_hash: str | None
    provider_artifact_id: str | None
    provider_dataset_id: str | None
    membership_source: str | None
    reasons: tuple[str, ...]
    tencent_fallback_allowed: bool
    prepared: ProviderRehearsalMarketArtifact | None

    def __post_init__(self) -> None:
        if self.provider != "XUNTOU" or self.tencent_fallback_allowed:
            raise ValueError("PIT replication preflight is Xuntou-only and forbids fallback")
        if self.status is PITReplicationPreflightStatus.AVAILABLE and self.prepared is None:
            raise ValueError("available PIT preflight requires verified provider evidence")
        if self.status is not PITReplicationPreflightStatus.AVAILABLE and self.prepared is not None:
            raise ValueError("blocked/invalid PIT preflight cannot expose prepared evidence")

    def to_public_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("prepared")
        payload["status"] = self.status.value
        payload["expected_source_files"] = list(self.expected_source_files)
        payload["reasons"] = list(self.reasons)
        return payload


def preflight_xuntou_replication(
    bundle: Path | None,
    *,
    membership_source: str | None = None,
) -> PITReplicationPreflight:
    if membership_source in {"CURRENT_WATCHLIST_BACKFILL", "CURRENT_MEMBERSHIP_BACKFILL"}:
        return _result(
            status=PITReplicationPreflightStatus.INVALID_PIT_EVIDENCE,
            bundle_content_hash=None,
            provider_artifact_id=None,
            provider_dataset_id=None,
            membership_source=membership_source,
            reasons=("CURRENT_WATCHLIST_BACKFILL_REJECTED",),
            prepared=None,
        )
    if bundle is None:
        return _result(
            status=PITReplicationPreflightStatus.BLOCKED_EXTERNAL_PROVIDER_INPUT,
            bundle_content_hash=None,
            provider_artifact_id=None,
            provider_dataset_id=None,
            membership_source=membership_source,
            reasons=("PIT_REPLICATION_BLOCKED_EXTERNAL_XUNTOU_BUNDLE_REQUIRED",),
            prepared=None,
        )
    result = NormalizedXuntouWP3Backend().preflight(bundle)
    if result.report.availability_status is not ProviderAvailabilityStatus.AVAILABLE:
        return _result(
            status=PITReplicationPreflightStatus.INVALID_PIT_EVIDENCE,
            bundle_content_hash=_content_hash(bundle) if bundle.is_file() else None,
            provider_artifact_id=None,
            provider_dataset_id=None,
            membership_source=membership_source,
            reasons=tuple(result.report.limitations),
            prepared=None,
        )
    if not isinstance(result.prepared, ProviderRehearsalMarketArtifact):
        raise ValueError("Xuntou preflight returned an invalid prepared type")
    artifact = result.prepared
    pit_blockers = tuple(
        item
        for item in artifact.dataset_contract.limitations
        if item in {"CURRENT_MEMBERSHIP_BACKFILL_BIAS", "XUNTOU_HISTORICAL_PIT_UNVERIFIED"}
    )
    if pit_blockers:
        return _result(
            status=PITReplicationPreflightStatus.INVALID_PIT_EVIDENCE,
            bundle_content_hash=_content_hash(bundle),
            provider_artifact_id=str(artifact.artifact_id),
            provider_dataset_id=str(artifact.dataset_contract.dataset_id),
            membership_source=artifact.universe_artifact.effective_time_convention,
            reasons=pit_blockers,
            prepared=None,
        )
    return _result(
        status=PITReplicationPreflightStatus.AVAILABLE,
        bundle_content_hash=_content_hash(bundle),
        provider_artifact_id=str(artifact.artifact_id),
        provider_dataset_id=str(artifact.dataset_contract.dataset_id),
        membership_source=artifact.universe_artifact.effective_time_convention,
        reasons=tuple(artifact.dataset_contract.limitations),
        prepared=artifact,
    )


def _result(
    *,
    status: PITReplicationPreflightStatus,
    bundle_content_hash: str | None,
    provider_artifact_id: str | None,
    provider_dataset_id: str | None,
    membership_source: str | None,
    reasons: tuple[str, ...],
    prepared: ProviderRehearsalMarketArtifact | None,
) -> PITReplicationPreflight:
    return PITReplicationPreflight(
        schema_version="pit-replication-provider-preflight-v1",
        status=status,
        provider="XUNTOU",
        required_bundle_schema=XUNTOU_P0_NATIVE_BUNDLE_SCHEMA_VERSION,
        required_product=XUNTOU_P0_PRODUCT,
        expected_source_files=("xuntou_normalized_native_bundle_v3.json",),
        bundle_content_hash=bundle_content_hash,
        provider_artifact_id=provider_artifact_id,
        provider_dataset_id=provider_dataset_id,
        membership_source=membership_source,
        reasons=reasons,
        tencent_fallback_allowed=False,
        prepared=prepared,
    )


def _content_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"
