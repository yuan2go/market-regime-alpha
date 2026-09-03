"""Narrow exact Target contract used only to schedule prospective captures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from market_regime_alpha.market.domain.prospective_archive import TargetArchiveCheckpoint


@dataclass(frozen=True, slots=True)
class TargetArchiveContract:
    target_definition_id: UUID
    version: int
    content_sha256: str
    checkpoints: tuple[TargetArchiveCheckpoint, ...]


class TargetArchiveScheduleReadPort(Protocol):
    def exact_contract(self, target_definition_id: UUID) -> TargetArchiveContract: ...


__all__ = ["TargetArchiveContract", "TargetArchiveScheduleReadPort"]
