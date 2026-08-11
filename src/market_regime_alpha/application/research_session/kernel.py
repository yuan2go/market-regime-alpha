"""Deterministic stage kernel shared by live and historical research sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Protocol

from market_regime_alpha.application.research_session.contracts import (
    ResearchDecisionSessionRequest,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    normalize_canonical_datetime,
    require_sha256,
)


SESSION_STAGE_RECEIPT_SCHEMA = "research-session-stage-receipt/v1"


class ResearchSessionStage(str, Enum):
    SCOPE = "SCOPE"
    DECISION = "DECISION"
    STRATEGY = "STRATEGY"
    PORTFOLIO = "PORTFOLIO"
    OUTCOME = "OUTCOME"
    PERFORMANCE = "PERFORMANCE"

    @property
    def ordinal(self) -> int:
        return tuple(ResearchSessionStage).index(self) + 1


class SessionStageStatus(str, Enum):
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


@dataclass(frozen=True, slots=True)
class SessionStageComputation:
    """Output returned by one existing business-fact owner adapter."""

    status: SessionStageStatus
    output_references: tuple[ValidationArtifactReference, ...]
    input_references: tuple[ValidationArtifactReference, ...]
    completed_at: datetime
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        normalize_canonical_datetime(self.completed_at)
        if self.input_references != _references(self.input_references):
            raise ValueError("stage computation input references must be unique and sorted")
        if self.output_references != _references(self.output_references):
            raise ValueError("stage computation output references must be unique and sorted")
        if self.status is SessionStageStatus.COMPLETE and not self.output_references:
            raise ValueError("complete stage computation requires an owner output")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("stage computation reasons must be unique and sorted")
        if not self.reason_codes:
            raise ValueError("stage computation requires an explicit reason")


class ResearchSessionStageOwner(Protocol):
    """Adapter to the existing owners; the kernel never reimplements facts."""

    def compute_stage(
        self,
        *,
        request: ResearchDecisionSessionRequest,
        stage: ResearchSessionStage,
        input_references: tuple[ValidationArtifactReference, ...],
    ) -> SessionStageComputation: ...


@dataclass(frozen=True, slots=True)
class ResearchSessionStageReceipt:
    receipt_id: ArtifactId
    receipt_hash: str
    session_id: ArtifactId
    session_hash: str
    stage: ResearchSessionStage
    status: SessionStageStatus
    predecessor_receipt_ids: tuple[ArtifactId, ...]
    predecessor_receipt_hashes: tuple[str, ...]
    input_references: tuple[ValidationArtifactReference, ...]
    output_references: tuple[ValidationArtifactReference, ...]
    completed_at: datetime
    reason_codes: tuple[str, ...]
    schema_version: str = SESSION_STAGE_RECEIPT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != SESSION_STAGE_RECEIPT_SCHEMA:
            raise ValueError("unsupported Research Session stage receipt schema")
        require_sha256("receipt_hash", self.receipt_hash)
        require_sha256("session_hash", self.session_hash)
        for value in self.predecessor_receipt_hashes:
            require_sha256("predecessor_receipt_hash", value)
        if len(self.predecessor_receipt_ids) != len(
            self.predecessor_receipt_hashes
        ):
            raise ValueError("stage predecessor identities and hashes must be paired")
        if len(self.predecessor_receipt_ids) != self.stage.ordinal - 1:
            raise ValueError("stage receipt requires the complete predecessor chain")
        if self.input_references != _references(self.input_references):
            raise ValueError("stage receipt input references must be unique and sorted")
        if self.output_references != _references(self.output_references):
            raise ValueError("stage receipt output references must be unique and sorted")
        if self.status is SessionStageStatus.COMPLETE and not self.output_references:
            raise ValueError("complete stage receipt requires an owner output")
        normalize_canonical_datetime(self.completed_at)
        if not self.reason_codes or self.reason_codes != tuple(
            sorted(set(self.reason_codes))
        ):
            raise ValueError("stage receipt reasons must be non-empty, unique, sorted")
        digest = canonical_hash(self.identity_payload())
        if digest != self.receipt_hash:
            raise ValueError("Research Session stage receipt hash mismatch")
        if str(self.receipt_id) != f"research-session-stage-{digest[7:31]}":
            raise ValueError("Research Session stage receipt identity mismatch")

    @property
    def entry_authority_granted(self) -> bool:
        return False

    @classmethod
    def create(
        cls,
        *,
        request: ResearchDecisionSessionRequest,
        stage: ResearchSessionStage,
        status: SessionStageStatus,
        predecessors: tuple[ResearchSessionStageReceipt, ...],
        input_references: tuple[ValidationArtifactReference, ...],
        output_references: tuple[ValidationArtifactReference, ...],
        completed_at: datetime,
        reason_codes: tuple[str, ...],
    ) -> ResearchSessionStageReceipt:
        values = {
            "schema_version": SESSION_STAGE_RECEIPT_SCHEMA,
            "session_id": str(request.session_id),
            "session_hash": request.session_hash,
            "stage": stage.value,
            "status": status.value,
            "predecessor_receipt_ids": [
                str(item.receipt_id) for item in predecessors
            ],
            "predecessor_receipt_hashes": [
                item.receipt_hash for item in predecessors
            ],
            "input_references": [
                item.to_canonical_dict() for item in input_references
            ],
            "output_references": [
                item.to_canonical_dict() for item in output_references
            ],
            "completed_at": canonical_datetime(completed_at),
            "reason_codes": list(reason_codes),
        }
        digest = canonical_hash(values)
        return cls(
            receipt_id=ArtifactId(f"research-session-stage-{digest[7:31]}"),
            receipt_hash=digest,
            session_id=request.session_id,
            session_hash=request.session_hash,
            stage=stage,
            status=status,
            predecessor_receipt_ids=tuple(item.receipt_id for item in predecessors),
            predecessor_receipt_hashes=tuple(
                item.receipt_hash for item in predecessors
            ),
            input_references=input_references,
            output_references=output_references,
            completed_at=normalize_canonical_datetime(completed_at),
            reason_codes=reason_codes,
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": str(self.session_id),
            "session_hash": self.session_hash,
            "stage": self.stage.value,
            "status": self.status.value,
            "predecessor_receipt_ids": [
                str(item) for item in self.predecessor_receipt_ids
            ],
            "predecessor_receipt_hashes": list(self.predecessor_receipt_hashes),
            "input_references": [
                item.to_canonical_dict() for item in self.input_references
            ],
            "output_references": [
                item.to_canonical_dict() for item in self.output_references
            ],
            "completed_at": canonical_datetime(self.completed_at),
            "reason_codes": list(self.reason_codes),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": str(self.receipt_id),
            "receipt_hash": self.receipt_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ResearchSessionStageReceipt:
        return cls(
            receipt_id=ArtifactId(str(payload["receipt_id"])),
            receipt_hash=str(payload["receipt_hash"]),
            session_id=ArtifactId(str(payload["session_id"])),
            session_hash=str(payload["session_hash"]),
            stage=ResearchSessionStage(str(payload["stage"])),
            status=SessionStageStatus(str(payload["status"])),
            predecessor_receipt_ids=tuple(
                ArtifactId(str(item))
                for item in payload["predecessor_receipt_ids"]
            ),
            predecessor_receipt_hashes=tuple(
                str(item) for item in payload["predecessor_receipt_hashes"]
            ),
            input_references=_references(
                tuple(
                    ValidationArtifactReference.from_canonical_dict(item)
                    for item in payload["input_references"]
                )
            ),
            output_references=_references(
                tuple(
                    ValidationArtifactReference.from_canonical_dict(item)
                    for item in payload["output_references"]
                )
            ),
            completed_at=datetime.fromisoformat(
                str(payload["completed_at"]).replace("Z", "+00:00")
            ),
            reason_codes=tuple(str(item) for item in payload["reason_codes"]),
            schema_version=str(payload["schema_version"]),
        )


class ResearchDecisionSessionKernel:
    """Apply exact stage ordering and lineage around existing fact owners."""

    def __init__(self, owner: ResearchSessionStageOwner) -> None:
        if not hasattr(owner, "compute_stage"):
            raise TypeError("owner must implement compute_stage")
        self._owner = owner

    def run(
        self,
        *,
        request: ResearchDecisionSessionRequest,
        completed_prefix: tuple[ResearchSessionStageReceipt, ...] = (),
    ) -> tuple[ResearchSessionStageReceipt, ...]:
        completed = tuple(self._validate_prefix(request, completed_prefix))
        while len(completed) < len(ResearchSessionStage) and (
            not completed
            or completed[-1].status is SessionStageStatus.COMPLETE
        ):
            completed = self.run_next(
                request=request,
                completed_prefix=completed,
            )
        return completed

    def run_next(
        self,
        *,
        request: ResearchDecisionSessionRequest,
        completed_prefix: tuple[ResearchSessionStageReceipt, ...] = (),
    ) -> tuple[ResearchSessionStageReceipt, ...]:
        """Compute exactly one owner stage for transaction-bound checkpoints."""

        completed = list(self._validate_prefix(request, completed_prefix))
        if len(completed) == len(ResearchSessionStage):
            return tuple(completed)
        if completed and completed[-1].status is not SessionStageStatus.COMPLETE:
            return tuple(completed)
        stage = tuple(ResearchSessionStage)[len(completed)]
        expected_inputs = _references(
            tuple(
                reference
                for predecessor in completed
                for reference in predecessor.output_references
            )
        )
        computation = self._owner.compute_stage(
            request=request,
            stage=stage,
            input_references=expected_inputs,
        )
        if not set(expected_inputs).issubset(computation.input_references):
            raise ValueError("stage computation omits predecessor owner lineage")
        receipt = ResearchSessionStageReceipt.create(
            request=request,
            stage=stage,
            status=computation.status,
            predecessors=tuple(completed),
            input_references=computation.input_references,
            output_references=computation.output_references,
            completed_at=computation.completed_at,
            reason_codes=computation.reason_codes,
        )
        completed.append(receipt)
        return tuple(completed)

    @staticmethod
    def _validate_prefix(
        request: ResearchDecisionSessionRequest,
        prefix: tuple[ResearchSessionStageReceipt, ...],
    ) -> tuple[ResearchSessionStageReceipt, ...]:
        expected_stages = tuple(ResearchSessionStage)[: len(prefix)]
        if tuple(item.stage for item in prefix) != expected_stages:
            raise ValueError("completed receipts must form a contiguous stage prefix")
        for ordinal, receipt in enumerate(prefix):
            if receipt.session_id != request.session_id or (
                receipt.session_hash != request.session_hash
            ):
                raise ValueError("completed receipt belongs to a different decision session")
            predecessors = prefix[:ordinal]
            if receipt.predecessor_receipt_ids != tuple(
                item.receipt_id for item in predecessors
            ) or receipt.predecessor_receipt_hashes != tuple(
                item.receipt_hash for item in predecessors
            ):
                raise ValueError("completed receipt predecessor chain is invalid")
        return prefix


def _references(
    references: tuple[ValidationArtifactReference, ...],
) -> tuple[ValidationArtifactReference, ...]:
    values = {
        (item.artifact_kind, str(item.artifact_id), item.content_hash): item
        for item in references
    }
    return tuple(values[key] for key in sorted(values))


__all__ = [
    "ResearchDecisionSessionKernel",
    "ResearchSessionStage",
    "ResearchSessionStageOwner",
    "ResearchSessionStageReceipt",
    "SESSION_STAGE_RECEIPT_SCHEMA",
    "SessionStageComputation",
    "SessionStageStatus",
]
