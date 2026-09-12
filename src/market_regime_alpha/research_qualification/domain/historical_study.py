"""Finite exploratory study inputs; canonical Backtest remains the executor."""

from dataclasses import dataclass
from datetime import date
import json
import re
from uuid import UUID


BASELINE_CANDIDATES = ("rule", "zero", "training_mean", "feature", "inverse_feature", "ridge_v1", "ridge_v2")


@dataclass(frozen=True, slots=True)
class HistoricalStudyPlan:
    study_code: str
    template_backtest_id: UUID
    template_definition_sha256: str
    market_archive_id: UUID
    market_archive_sha256: str
    market_archive_seal_id: UUID
    market_archive_seal_sha256: str
    fit_dates: tuple[date, ...]
    purge_dates: tuple[date, ...]
    embargo_dates: tuple[date, ...]
    validation_dates: tuple[date, ...]
    instrument_ids: tuple[UUID, ...]
    candidates: tuple[str, ...] = BASELINE_CANDIDATES
    seed: int = 18
    universe_limitation: str = "STATIC_UNIVERSE/SURVIVORSHIP_LIMITED"

    def __post_init__(self) -> None:
        from market_regime_alpha.shared.identity import ContentHash
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,49}", self.study_code):
            raise ValueError("study_code requires a lowercase code of at most 50 characters")
        for digest in (self.template_definition_sha256, self.market_archive_sha256, self.market_archive_seal_sha256):
            ContentHash(digest)
        if not all(isinstance(identity, UUID) for identity in (self.template_backtest_id,self.market_archive_id,self.market_archive_seal_id,*self.instrument_ids)):
            raise TypeError("historical study identities must be UUID values")
        if not self.fit_dates or not self.validation_dates:
            raise ValueError("historical study needs explicit FIT and validation sessions")
        dates = self.fit_dates + self.purge_dates + self.embargo_dates + self.validation_dates
        if dates != tuple(sorted(set(dates))):
            raise ValueError("study sessions must be unique and strictly chronological")
        if not self.purge_dates or not self.embargo_dates:
            raise ValueError("next-session labels require explicit maturity purge and embargo sessions")
        if not self.instrument_ids or len(self.instrument_ids) > 500 or self.instrument_ids != tuple(sorted(set(self.instrument_ids), key=str)):
            raise ValueError("study requires 1–500 unique sorted instruments")
        if not self.candidates or len(set(self.candidates)) != len(self.candidates) or any(x not in BASELINE_CANDIDATES for x in self.candidates):
            raise ValueError("unsupported or duplicate baseline candidate")
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("study seed must be a non-negative integer")
        if self.universe_limitation != "STATIC_UNIVERSE/SURVIVORSHIP_LIMITED":
            raise ValueError("this fixed-roster study cannot claim historical membership or PIT")

    @classmethod
    def from_bytes(cls, content: bytes) -> "HistoricalStudyPlan":
        def closed(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate study field")
                result[key] = value
            return result
        raw = json.loads(content, object_pairs_hook=closed)
        if not isinstance(raw, dict) or raw.pop("schema", None) != "mra-historical-study-v1":
            raise ValueError("historical study schema is unsupported")
        for name in ("template_backtest_id", "market_archive_id", "market_archive_seal_id"):
            raw[name] = UUID(raw[name])
        for name in ("fit_dates", "purge_dates", "embargo_dates", "validation_dates"):
            raw[name] = tuple(date.fromisoformat(x) for x in raw[name])
        raw["instrument_ids"] = tuple(UUID(x) for x in raw["instrument_ids"])
        if "candidates" in raw:
            raw["candidates"] = tuple(raw["candidates"])
        return cls(**raw)
