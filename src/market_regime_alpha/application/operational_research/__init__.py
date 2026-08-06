"""Operational bridge from verified DailyLoop evidence to Platform V2 research."""

from market_regime_alpha.application.operational_research.bridge import (
    OperationalResearchRunner,
    adapt_legacy_operational_research_inputs,
    adapt_operational_research_inputs,
    adapt_verified_composite_operational_inputs,
)
from market_regime_alpha.application.operational_research.composite_artifact import (
    VerifiedCompositeOperationalManifest,
    cleanup_orphan_composite_staging,
    load_verified_composite_operational_manifest,
    publish_composite_operational_manifest,
)
from market_regime_alpha.application.operational_research.contracts import (
    SupplementalResearchEvidenceBundle,
)
from market_regime_alpha.application.operational_research.composite_manifest import (
    CompositeCoveragePolicy,
    CompositeDecisionTimePolicy,
    CompositeOperationalComponentReference,
    CompositeOperationalComponentRole,
    CompositeOperationalCompositionPolicy,
    CompositeOperationalCompositionStatus,
    CompositeOperationalFieldAuthorityReference,
    CompositeOperationalFieldAuthorityRequirement,
    CompositeOperationalFieldGroup,
    CompositeOperationalInputManifest,
    CompositeOperationalManifestBuilder,
    CompositeSourceConflictPolicy,
)
from market_regime_alpha.application.operational_research.composite_repository import (
    CompositeOperationalRepository,
)
from market_regime_alpha.application.operational_research.composite_service import (
    CompositeOperationalEvidenceApplicationService,
)
from market_regime_alpha.application.operational_research.postgres_composite_repository import (
    PostgresCompositeOperationalRepository,
)

__all__ = [
    "CompositeCoveragePolicy",
    "CompositeDecisionTimePolicy",
    "CompositeOperationalComponentReference",
    "CompositeOperationalComponentRole",
    "CompositeOperationalCompositionPolicy",
    "CompositeOperationalCompositionStatus",
    "CompositeOperationalFieldAuthorityReference",
    "CompositeOperationalFieldAuthorityRequirement",
    "CompositeOperationalFieldGroup",
    "CompositeOperationalInputManifest",
    "CompositeOperationalManifestBuilder",
    "CompositeOperationalRepository",
    "CompositeSourceConflictPolicy",
    "CompositeOperationalEvidenceApplicationService",
    "OperationalResearchRunner",
    "PostgresCompositeOperationalRepository",
    "SupplementalResearchEvidenceBundle",
    "VerifiedCompositeOperationalManifest",
    "adapt_legacy_operational_research_inputs",
    "adapt_operational_research_inputs",
    "adapt_verified_composite_operational_inputs",
    "cleanup_orphan_composite_staging",
    "load_verified_composite_operational_manifest",
    "publish_composite_operational_manifest",
]
