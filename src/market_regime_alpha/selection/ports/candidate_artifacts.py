"""Selection-owned Artifact ports for Candidate policy and Dataset inputs."""

from typing import Protocol
from uuid import UUID

from market_regime_alpha.runtime.ports import (
    ArtifactRecord,
    ArtifactVerificationRecord,
    ByteVerification,
)
from market_regime_alpha.selection.domain.candidate_inputs import (
    CandidateArtifactBinding,
)


class CandidateArtifactByteStore(Protocol):
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


class CandidateArtifactRepository(Protocol):
    def lock_exact_identity(
        self,
        binding: CandidateArtifactBinding,
    ) -> ArtifactRecord: ...

    def require_exact(
        self,
        binding: CandidateArtifactBinding,
        *,
        lock: bool,
    ) -> ArtifactRecord: ...

    def require_exact_for_verification(
        self,
        binding: CandidateArtifactBinding,
    ) -> ArtifactRecord:
        """Lock an exact Artifact before recording verification against it."""
        ...

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


__all__ = [
    "CandidateArtifactBinding",
    "CandidateArtifactByteStore",
    "CandidateArtifactRepository",
]
