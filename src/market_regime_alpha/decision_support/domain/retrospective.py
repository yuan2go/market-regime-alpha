"""Typed dual-clock seam for exploratory retrospective Decision simulation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import require_utc


@dataclass(frozen=True, slots=True)
class ExploratoryRetrospectiveDecisionScope:
    dataset_id: UUID
    exploratory_backtest_run_id: UUID
    exploratory_backtest_arm_id: UUID
    exploratory_backtest_fold_id: UUID
    exploratory_backtest_fold_session_id: UUID
    market_archive_id: UUID
    market_archive_seal_id: UUID
    knowledge_cutoff: datetime
    simulated_event_cutoff: datetime
    evidence_lane: str = field(default="EXPLORATORY_RETROSPECTIVE", init=False)
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        knowledge = require_utc(self.knowledge_cutoff, field="knowledge_cutoff")
        simulated = require_utc(
            self.simulated_event_cutoff,
            field="simulated_event_cutoff",
        )
        if simulated >= knowledge:
            raise ValueError("simulated_event_cutoff must precede knowledge_cutoff")
        object.__setattr__(self, "knowledge_cutoff", knowledge)
        object.__setattr__(self, "simulated_event_cutoff", simulated)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "dataset_id": self.dataset_id,
                        "evidence_lane": self.evidence_lane,
                        "exploratory_backtest_arm_id": (
                            self.exploratory_backtest_arm_id
                        ),
                        "exploratory_backtest_fold_id": (
                            self.exploratory_backtest_fold_id
                        ),
                        "exploratory_backtest_fold_session_id": (
                            self.exploratory_backtest_fold_session_id
                        ),
                        "exploratory_backtest_run_id": (
                            self.exploratory_backtest_run_id
                        ),
                        "knowledge_cutoff": knowledge,
                        "market_archive_id": self.market_archive_id,
                        "market_archive_seal_id": self.market_archive_seal_id,
                        "simulated_event_cutoff": simulated,
                    }
                )
            ),
        )


__all__ = ["ExploratoryRetrospectiveDecisionScope"]
