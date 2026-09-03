"""Immutable ex-ante Research Partition declarations."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from uuid import UUID

from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionOverlapPolicy,
    PartitionPopulationScope,
    PartitionPurpose,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


_CODE = re.compile(r"^[a-z][a-z0-9_-]{0,99}$")
_EXCHANGE_CODE = re.compile(r"^[A-Z][A-Z0-9]{1,15}$")


@dataclass(frozen=True, slots=True)
class BacktestPartitionSource:
    """Exact canonical Decision lineage used to derive a Partition roster."""

    exploratory_backtest_run_id: UUID
    exploratory_backtest_arm_id: UUID
    exploratory_backtest_fold_id: UUID | None
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "exploratory_backtest_arm_id": (
                            self.exploratory_backtest_arm_id
                        ),
                        "exploratory_backtest_fold_id": (
                            self.exploratory_backtest_fold_id
                        ),
                        "exploratory_backtest_run_id": (
                            self.exploratory_backtest_run_id
                        ),
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ResearchPartitionPlan:
    """Caller declaration; the PostgreSQL adapter derives the member roster."""

    research_partition_id: UUID
    partition_code: str
    target_definition_id: UUID
    target_version: int
    target_definition_sha256: ContentHash | str
    purpose: PartitionPurpose
    population_scope: PartitionPopulationScope
    overlap_policy: PartitionOverlapPolicy
    exchange_code: str
    decision_start_session_id: UUID
    decision_end_session_id: UUID
    purge_before_sessions: int
    purge_after_sessions: int
    embargo_sessions: int
    series_code: str
    fold_ordinal: int
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding
    provenance_sha256: ContentHash | str
    backtest_source: BacktestPartitionSource | None = None
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.partition_code):
            raise ValueError("partition_code has an invalid format")
        if not _CODE.fullmatch(self.series_code):
            raise ValueError("series_code has an invalid format")
        if not _EXCHANGE_CODE.fullmatch(self.exchange_code):
            raise ValueError("exchange_code has an invalid format")
        if isinstance(self.target_version, bool) or self.target_version < 1:
            raise ValueError("target_version must be positive")
        for name in (
            "purge_before_sessions",
            "purge_after_sessions",
            "embargo_sessions",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be non-negative")
        if isinstance(self.fold_ordinal, bool) or self.fold_ordinal < 1:
            raise ValueError("fold_ordinal must be positive")
        target_hash = ContentHash(str(self.target_definition_sha256))
        provenance_hash = ContentHash(str(self.provenance_sha256))
        object.__setattr__(self, "target_definition_sha256", target_hash)
        object.__setattr__(self, "provenance_sha256", provenance_hash)
        allowed = {
            PartitionPurpose.DISCOVERY: {PartitionOverlapPolicy.DIAGNOSTIC_REUSE},
            PartitionPurpose.FIT: {
                PartitionOverlapPolicy.DIAGNOSTIC_REUSE,
                PartitionOverlapPolicy.PURGED_WALK_FORWARD,
            },
            PartitionPurpose.VALIDATION: {
                PartitionOverlapPolicy.DIAGNOSTIC_REUSE,
                PartitionOverlapPolicy.PURGED_WALK_FORWARD,
            },
            PartitionPurpose.LOCKED_OOS: {
                PartitionOverlapPolicy.ISOLATED_PROTECTED
            },
            PartitionPurpose.PROSPECTIVE: {
                PartitionOverlapPolicy.ISOLATED_PROTECTED
            },
        }
        if self.overlap_policy not in allowed[self.purpose]:
            raise ValueError("purpose and overlap_policy are incompatible")
        content: dict[str, object] = {
            "code_artifact": self.code_artifact,
            "config_artifact": self.config_artifact,
            "decision_end_session_id": self.decision_end_session_id,
            "decision_start_session_id": self.decision_start_session_id,
            "embargo_sessions": self.embargo_sessions,
            "exchange_code": self.exchange_code,
            "fold_ordinal": self.fold_ordinal,
            "overlap_policy": self.overlap_policy,
            "partition_code": self.partition_code,
            "population_scope": self.population_scope,
            "provenance_sha256": provenance_hash,
            "purge_after_sessions": self.purge_after_sessions,
            "purge_before_sessions": self.purge_before_sessions,
            "purpose": self.purpose,
            "series_code": self.series_code,
            "target_definition_id": self.target_definition_id,
            "target_definition_sha256": target_hash,
            "target_version": self.target_version,
        }
        # Absence preserves every historical Partition request/hash byte.
        if self.backtest_source is not None:
            content["backtest_source"] = self.backtest_source
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(canonical_json_sha256(content)),
        )


__all__ = ["BacktestPartitionSource", "ResearchPartitionPlan"]
