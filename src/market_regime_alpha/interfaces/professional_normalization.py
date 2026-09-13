"""Recorded daily normalization through the sole Market command owner."""

from market_regime_alpha.infrastructure.artifacts.local import LocalArtifactStore
from market_regime_alpha.infrastructure.postgres.queries.market_revision_lineage import PostgresMarketRevisionLineageReadPort
from market_regime_alpha.infrastructure.postgres.queries.professional_normalization import PostgresProfessionalNormalizationReferences
from market_regime_alpha.infrastructure.providers.recorded_professional_normalizer import RecordedProfessionalDailyNormalizer
from market_regime_alpha.runtime.application import ActorType, CommandContext


def normalize_recorded_capture(app, settings, arguments) -> dict:
    normalizer = RecordedProfessionalDailyNormalizer(
        PostgresProfessionalNormalizationReferences(app._pool,LocalArtifactStore(settings.artifact_root)),
        PostgresMarketRevisionLineageReadPort(app._pool))
    result = app.market.normalize(arguments.capture_id,normalizer,CommandContext(arguments.idempotency_key,
        ActorType.OPERATOR,arguments.actor_id,"RECORDED_DAILY_NORMALIZATION"))
    return {"normalization":result,"supported_price_basis":"RAW_UNADJUSTED",
        "archive_study_readiness":"REQUIRES_SELECTED_ARCHIVE_SEAL_CALENDAR_MEMBERSHIP_AND_COMPLETE_DEPENDENCIES",
        "professional_provider_validation":"NOT_RUN","formal_pit":False}
