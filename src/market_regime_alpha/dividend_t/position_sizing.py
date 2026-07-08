"""Position sizing vocabulary and helpers for dividend-T models."""

from __future__ import annotations

from dataclasses import dataclass


MIN_BASE_POSITION_PCT = 0.05
MAX_BASE_POSITION_PCT = 0.10


def clamp_pct(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass(frozen=True)
class PositionBudget:
    """Explicit position budget at account-equity percentage level.

    base_target_pct is the persistent base position target.
    active_position_cap_pct is the incremental active/T budget above base.
    max_total_position_pct is the final total symbol exposure cap.
    """

    base_target_pct: float
    active_position_cap_pct: float
    max_total_position_pct: float

    @classmethod
    def from_total_cap(cls, *, base_target_pct: float, max_total_position_pct: float) -> "PositionBudget":
        base_target = round(clamp_pct(base_target_pct), 4)
        max_total = round(clamp_pct(max_total_position_pct), 4)
        if max_total < base_target:
            max_total = base_target
        return cls(
            base_target_pct=base_target,
            active_position_cap_pct=round(max_total - base_target, 4),
            max_total_position_pct=max_total,
        )

    @property
    def effective_total_cap_pct(self) -> float:
        return round(min(self.max_total_position_pct, self.base_target_pct + self.active_position_cap_pct), 4)

    def validate(self, *, label: str = "position budget") -> None:
        if not 0.0 <= self.base_target_pct <= 1.0:
            raise ValueError(f"{label}: base_target_pct must be in [0, 1]")
        if not 0.0 <= self.active_position_cap_pct <= 1.0:
            raise ValueError(f"{label}: active_position_cap_pct must be in [0, 1]")
        if not 0.0 <= self.max_total_position_pct <= 1.0:
            raise ValueError(f"{label}: max_total_position_pct must be in [0, 1]")
        if self.max_total_position_pct < self.base_target_pct:
            raise ValueError(f"{label}: max_total_position_pct must be >= base_target_pct")
        if self.effective_total_cap_pct < self.base_target_pct:
            raise ValueError(f"{label}: effective total cap must be >= base_target_pct")
