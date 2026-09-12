"""Finite historical acquisition inputs, distinct from prospective scheduling."""

from dataclasses import dataclass
from datetime import date
import json
import math
import re
from uuid import UUID

from market_regime_alpha.shared.identity import ContentHash


@dataclass(frozen=True, slots=True)
class HistoricalAcquisitionPlan:
    archive_code: str
    template_archive_id: UUID
    template_archive_sha256: str
    start_date: date
    end_date: date
    codes: tuple[str, ...]
    maximum_archive_bytes: int = 536870912
    maximum_slice_bytes: int = 33554432
    reserved_free_bytes: int = 1073741824

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,49}", self.archive_code):
            raise ValueError("historical archive code requires at most 50 lowercase characters")
        ContentHash(self.template_archive_sha256)
        if not self.codes or self.codes != tuple(sorted(set(self.codes))) or len(self.codes) > 66:
            raise ValueError("historical acquisition requires 1–66 unique sorted securities (at most 199 requests)")
        if any(not re.fullmatch(r"(?:sh|sz)\.[0-9]{6}", code) for code in self.codes):
            raise ValueError("historical acquisition requires exact BaoStock security identifiers")
        if not 0 <= (self.end_date - self.start_date).days <= 2192:
            raise ValueError("historical acquisition interval must be ordered and at most six years")
        for name in ("maximum_archive_bytes", "maximum_slice_bytes", "reserved_free_bytes"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.maximum_slice_bytes > 33554432 or self.maximum_archive_bytes > 536870912 or self.maximum_slice_bytes > self.maximum_archive_bytes:
            raise ValueError("historical request/storage budget exceeds 32 MiB per request or 512 MiB total")

    @classmethod
    def from_bytes(cls, content: bytes) -> "HistoricalAcquisitionPlan":
        def closed(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate historical acquisition field")
                result[key] = value
            return result
        raw = json.loads(content, object_pairs_hook=closed)
        if not isinstance(raw, dict) or raw.pop("schema", None) != "mra-historical-acquisition-v1":
            raise ValueError("unsupported historical acquisition schema")
        raw["template_archive_id"] = UUID(raw["template_archive_id"])
        raw["start_date"] = date.fromisoformat(raw["start_date"])
        raw["end_date"] = date.fromisoformat(raw["end_date"])
        raw["codes"] = tuple(raw["codes"])
        return cls(**raw)


@dataclass(frozen=True, slots=True)
class HistoricalAcquisitionBudget:
    maximum_slices: int = 8
    maximum_seconds: float = 1200
    minimum_interval_seconds: float = 0.25

    def __post_init__(self) -> None:
        if type(self.maximum_slices) is not int or not 1 <= self.maximum_slices <= 200:
            raise ValueError("maximum_slices must be an integer between 1 and 200")
        for name, lower, upper in (("maximum_seconds", 1, 7200), ("minimum_interval_seconds", .25, 30)):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or not lower <= value <= upper:
                raise ValueError(f"{name} must be finite and between {lower} and {upper}")
