"""Versioned free ETF/Theme semantics; observations still come from Providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from market_regime_alpha.core.identity import ArtifactId, ProviderId
from market_regime_alpha.core.time import DecisionTime, RetrievedAt
from market_regime_alpha.data.providers.public_composite.contracts import (
    AcquiredSourcePayload,
    RawSourceRequestMetadata,
)
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    canonical_json,
    require_text,
)


FREE_OPERATIONAL_POLICY_SCHEMA = "free-operational-evidence-policy-v1"
FREE_OPERATIONAL_POLICY_AUTHORITY_ID = ProviderId(
    "authority-free-operational-evidence-policy"
)


@dataclass(frozen=True, slots=True)
class FreeOperationalETFDefinition:
    etf_id: str
    etf_name: str
    tracking_index_id: str
    tracking_index_name: str
    theme_id: str

    def __post_init__(self) -> None:
        for label, value in (
            ("etf_id", self.etf_id),
            ("etf_name", self.etf_name),
            ("tracking_index_id", self.tracking_index_id),
            ("tracking_index_name", self.tracking_index_name),
            ("theme_id", self.theme_id),
        ):
            require_text(label, value)

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "etf_id": self.etf_id,
            "etf_name": self.etf_name,
            "tracking_index_id": self.tracking_index_id,
            "tracking_index_name": self.tracking_index_name,
            "theme_id": self.theme_id,
        }


@dataclass(frozen=True, slots=True)
class FreeOperationalThemeDefinition:
    theme_id: str
    theme_name: str
    benchmark_id: str
    membership_rule: str
    effective_from: date

    def __post_init__(self) -> None:
        for label, value in (
            ("theme_id", self.theme_id),
            ("theme_name", self.theme_name),
            ("benchmark_id", self.benchmark_id),
            ("membership_rule", self.membership_rule),
        ):
            require_text(label, value)
        if self.membership_rule != "CURRENT_OPERATIONAL_UNIVERSE":
            raise ValueError("unsupported free Theme membership rule")

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "theme_id": self.theme_id,
            "theme_name": self.theme_name,
            "benchmark_id": self.benchmark_id,
            "membership_rule": self.membership_rule,
            "effective_from": self.effective_from.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class FreeOperationalEvidencePolicy:
    policy_version: str
    themes: tuple[FreeOperationalThemeDefinition, ...]
    etfs: tuple[FreeOperationalETFDefinition, ...]
    limitations: tuple[str, ...]
    schema_version: str = FREE_OPERATIONAL_POLICY_SCHEMA
    content_hash: str = field(init=False)
    policy_id: ArtifactId = field(init=False)

    def __post_init__(self) -> None:
        if self.schema_version != FREE_OPERATIONAL_POLICY_SCHEMA:
            raise ValueError("unsupported free operational evidence policy")
        require_text("policy_version", self.policy_version)
        theme_ids = tuple(item.theme_id for item in self.themes)
        etf_ids = tuple(item.etf_id for item in self.etfs)
        if not theme_ids or theme_ids != tuple(sorted(set(theme_ids))):
            raise ValueError("free policy Themes must be non-empty and ordered")
        if not etf_ids or etf_ids != tuple(sorted(set(etf_ids))):
            raise ValueError("free policy ETFs must be non-empty and ordered")
        if any(item.theme_id not in theme_ids for item in self.etfs):
            raise ValueError("free policy ETF references an unknown Theme")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("free policy limitations must be ordered and unique")
        for required in (
            "FORMAL_PIT_NOT_ESTABLISHED",
            "OBSERVABLE_PROXIES_ONLY",
            "PROXY_MAPPING_IS_NOT_INDEX_MEMBERSHIP",
        ):
            if required not in self.limitations:
                raise ValueError("free policy authority ceiling is incomplete")
        digest = canonical_hash(self.semantic_payload())
        object.__setattr__(self, "content_hash", digest)
        object.__setattr__(
            self,
            "policy_id",
            ArtifactId(f"free-operational-policy-{digest[7:31]}"),
        )

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "themes": [item.to_canonical_dict() for item in self.themes],
            "etfs": [item.to_canonical_dict() for item in self.etfs],
            "limitations": list(self.limitations),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "policy_id": str(self.policy_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }


def canonical_free_operational_evidence_policy() -> FreeOperationalEvidencePolicy:
    """Small explicit V1 policy; the proxy is not declared constituent truth."""

    theme_id = "FREE_A_SHARE_OPERATIONAL_UNIVERSE"
    return FreeOperationalEvidencePolicy(
        policy_version="2026-08-09.v1",
        themes=(
            FreeOperationalThemeDefinition(
                theme_id=theme_id,
                theme_name="Free A-Share Operational Universe",
                benchmark_id="000300.SH",
                membership_rule="CURRENT_OPERATIONAL_UNIVERSE",
                effective_from=date(2026, 8, 1),
            ),
        ),
        etfs=(
            FreeOperationalETFDefinition(
                etf_id="510300.SH",
                etf_name="CSI 300 ETF Proxy",
                tracking_index_id="000300.SH",
                tracking_index_name="CSI 300",
                theme_id=theme_id,
            ),
        ),
        limitations=(
            "CURRENT_MEMBERSHIP_ONLY",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "OBSERVABLE_PROXIES_ONLY",
            "PROXY_MAPPING_IS_NOT_INDEX_MEMBERSHIP",
            "TRADING_AUTHORITY_NOT_GRANTED",
        ),
    )


def build_free_operational_policy_source(
    *,
    policy: FreeOperationalEvidencePolicy,
    retrieved_at: RetrievedAt,
    decision_time: DecisionTime,
    provider_profile_id: str,
) -> AcquiredSourcePayload:
    """Bind exact policy bytes and their real observation time into lineage."""

    raw = (canonical_json(policy.to_canonical_dict()) + "\n").encode("utf-8")
    return AcquiredSourcePayload(
        provider_id=FREE_OPERATIONAL_POLICY_AUTHORITY_ID,
        product="free-operational-etf-theme-policy",
        locator=f"policy://free-operational/{policy.policy_id}",
        raw_payload=raw,
        retrieved_time=retrieved_at,
        limitations=policy.limitations,
        request_metadata=RawSourceRequestMetadata(
            provider_profile_id=provider_profile_id,
            endpoint="repository-policy",
            request_parameters=(("policy_id", str(policy.policy_id)),),
            requested_at=retrieved_at.value,
            provider_timestamp=None,
            event_time=None,
            available_at=retrieved_at.value,
            decision_time=decision_time.value,
            http_status=None,
            content_type="application/json",
            response_size=len(raw),
            encoding="utf-8",
            symbol_scope=tuple(item.etf_id for item in policy.etfs),
            field_scope=(
                "effective_theme_taxonomy",
                "etf_identity",
                "etf_theme_proxy_mapping",
                "tracking_index_identity",
            ),
        ),
    )


__all__ = [
    "FREE_OPERATIONAL_POLICY_AUTHORITY_ID",
    "FreeOperationalETFDefinition",
    "FreeOperationalEvidencePolicy",
    "FreeOperationalThemeDefinition",
    "build_free_operational_policy_source",
    "canonical_free_operational_evidence_policy",
]
