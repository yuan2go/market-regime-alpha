"""Narrow Artifact metadata port for Target registration."""

from typing import Protocol

from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.runtime.ports import ArtifactRecord


class TargetArtifactRepository(Protocol):
    def require_exact(
        self,
        binding: ArtifactBinding,
        *,
        lock: bool,
    ) -> ArtifactRecord: ...


__all__ = ["TargetArtifactRepository"]
