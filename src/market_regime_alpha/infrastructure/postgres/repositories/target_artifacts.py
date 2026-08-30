"""Target-facing exact Artifact metadata adapter."""

from market_regime_alpha.infrastructure.postgres.repositories.research_artifacts import (
    PostgresResearchArtifactRepository,
)


class PostgresTargetArtifactRepository(PostgresResearchArtifactRepository):
    """The Target port narrows the shared immutable Artifact table to exact reads."""


__all__ = ["PostgresTargetArtifactRepository"]
