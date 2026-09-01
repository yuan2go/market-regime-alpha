"""Typed read-only reconciliation results for WP-11 Authorities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class ResearchVerificationMismatchKind(StrEnum):
    MISSING_ROW = "MISSING_ROW"
    EXTRA_ROW = "EXTRA_ROW"
    COUNT_MISMATCH = "COUNT_MISMATCH"
    HASH_MISMATCH = "HASH_MISMATCH"
    ORDER_MISMATCH = "ORDER_MISMATCH"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    STATE_MISMATCH = "STATE_MISMATCH"
    TEMPORAL_MISMATCH = "TEMPORAL_MISMATCH"
    PROVENANCE_MISMATCH = "PROVENANCE_MISMATCH"


@dataclass(frozen=True, slots=True)
class ResearchVerificationMismatch:
    kind: ResearchVerificationMismatchKind
    path: str
    expected: str
    actual: str


@dataclass(frozen=True, slots=True)
class ResearchVerificationReport:
    authority_kind: str
    authority_id: UUID
    matched: bool
    mismatch_count: int
    mismatches: tuple[ResearchVerificationMismatch, ...]

    @classmethod
    def create(
        cls,
        *,
        authority_kind: str,
        authority_id: UUID,
        mismatches: tuple[ResearchVerificationMismatch, ...],
    ) -> ResearchVerificationReport:
        return cls(
            authority_kind=authority_kind,
            authority_id=authority_id,
            matched=not mismatches,
            mismatch_count=len(mismatches),
            mismatches=mismatches,
        )


__all__ = [
    "ResearchVerificationMismatch",
    "ResearchVerificationMismatchKind",
    "ResearchVerificationReport",
]
