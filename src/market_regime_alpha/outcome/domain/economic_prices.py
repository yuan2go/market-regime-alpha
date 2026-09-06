"""Exact Outcome-owned checkpoint facts for hypothetical economics consumers."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from market_regime_alpha.outcome.domain.authority import MarketTargetOutcomeAuthority
from market_regime_alpha.outcome.domain.model import OutcomeBarSource
from market_regime_alpha.outcome.domain.vocabulary import OutcomeStatus


@dataclass(frozen=True, slots=True)
class OutcomeEpisodePrices:
    revision_id: UUID
    revision_sha256: str
    entry_checkpoint_id: UUID
    exit_checkpoint_id: UUID
    entry_observation_id: UUID
    exit_observation_id: UUID
    entry_observation_sha256: str
    exit_observation_sha256: str
    entry_time: datetime
    exit_time: datetime
    entry_close: Decimal
    exit_close: Decimal
    known_at: datetime
    knowledge_cutoff: datetime
    price_basis: str


def episode_prices(authority: MarketTargetOutcomeAuthority, entry_id: UUID, exit_id: UUID) -> OutcomeEpisodePrices:
    """No bars-to-label calculation; project two reconciled Outcome observations."""
    if entry_id == exit_id:
        raise ValueError("episode entry and exit checkpoints must differ")
    revision = authority.revision
    observations = {item.target_checkpoint_id: item for item in revision.draft.observations}
    sources = {item.target_checkpoint_id: item for item in revision.draft.sources}
    if entry_id not in observations or exit_id not in observations:
        raise ValueError("episode checkpoint is absent from exact Outcome revision")
    entry, exit = observations[entry_id], observations[exit_id]
    a, b = sources.get(entry_id), sources.get(exit_id)
    if not isinstance(a, OutcomeBarSource) or not isinstance(b, OutcomeBarSource):
        raise ValueError("episode price source is unavailable or a SourceGap")
    if (entry.status is not OutcomeStatus.COMPLETE or exit.status is not OutcomeStatus.COMPLETE
            or entry.close_value is None or exit.close_value is None):
        raise ValueError("episode requires complete Outcome checkpoint prices")
    if (a.session_id != b.session_id or a.provider_product_id != b.provider_product_id
            or a.instrument_id != b.instrument_id or a.price_basis != b.price_basis
            or a.price_basis != "RAW_UNADJUSTED"):
        raise ValueError("episode requires same-session/provider/instrument RAW price facts")
    if not authority.commitment.decision_time < entry.event_end < exit.event_end:
        raise ValueError("episode checkpoints must strictly follow DecisionTime")
    bound = {revision.draft.observations[item.draft_index].target_checkpoint_id: item for item in revision.observations}
    return OutcomeEpisodePrices(
        revision.market_target_outcome_revision_id, revision.definition_summary_sha256,
        entry_id, exit_id, bound[entry_id].market_target_outcome_observation_id,
        bound[exit_id].market_target_outcome_observation_id,
        entry.content_sha256, exit.content_sha256, entry.event_end, exit.event_end,
        entry.close_value, exit.close_value, max(entry.known_at, exit.known_at),
        revision.draft.knowledge_cutoff, a.price_basis,
    )
