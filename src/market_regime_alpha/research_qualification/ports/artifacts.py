"""Narrow physical-byte and Artifact metadata ports for Research definitions."""

from typing import Protocol
from uuid import UUID

from market_regime_alpha.research_qualification.domain import ArtifactBinding
from market_regime_alpha.runtime.ports import (
    ArtifactRecord,
    ArtifactVerificationRecord,
    ByteVerification,
)


class ResearchArtifactByteStore(Protocol):
    def verify(
        self,
        content_sha256: str,
        *,
        expected_size: int,
    ) -> ByteVerification: ...

    def read_bytes(
        self,
        content_sha256: str,
        *,
        expected_size: int,
    ) -> bytes: ...


class ResearchArtifactRepository(Protocol):
    def lock_exact_identity(self, binding: ArtifactBinding) -> ArtifactRecord: ...

    def require_exact(
        self,
        binding: ArtifactBinding,
        *,
        lock: bool,
    ) -> ArtifactRecord: ...

    def record_verification(
        self,
        *,
        verification_id: UUID,
        receipt_id: UUID,
        artifact: ArtifactRecord,
        verifier_id: str,
        policy: str,
        verification: ByteVerification,
    ) -> ArtifactVerificationRecord: ...


__all__ = ["ResearchArtifactByteStore", "ResearchArtifactRepository"]
