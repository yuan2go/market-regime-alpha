"""Mutation-free Provider qualification reconciliation contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ProviderQualificationVerification:
    aggregate_kind: str
    aggregate_id: UUID
    matched: bool
    mismatch_count: int
    mismatches: tuple[str, ...]


class ProviderQualificationQueryPort(Protocol):
    def verify_protocol(
        self, provider_qualification_protocol_id: UUID
    ) -> ProviderQualificationVerification: ...

    def verify_decision(
        self, provider_qualification_decision_id: UUID
    ) -> ProviderQualificationVerification: ...


__all__ = [
    "ProviderQualificationQueryPort",
    "ProviderQualificationVerification",
]
