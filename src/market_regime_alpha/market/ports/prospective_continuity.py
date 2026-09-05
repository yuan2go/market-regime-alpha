"""Read-only references for the existing prospective Runtime application."""
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ProspectiveGenerationRuntimeReference:
    market_archive_id: UUID
    generation: int
    predecessor_market_archive_id: UUID | None
    config_artifact_id: UUID
    config_sha256: str
    config_size_bytes: int
    code_sha: str


class ProspectiveContinuityReadPort(Protocol):
    def generations(self, series_code: str) -> tuple[ProspectiveGenerationRuntimeReference, ...]: ...

    def overdue_slice_ids(self, market_archive_id: UUID) -> tuple[UUID, ...]: ...
