"""Explicit BaoStock ETF supplemental acquisition with policy lineage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Callable

from market_regime_alpha.core.time import RetrievedAt
from market_regime_alpha.data.providers.public_composite.contracts import (
    BAOSTOCK_PUBLIC_PROVIDER_ID,
    PublicAcquisitionClient,
    PublicCompositeBatch,
    PublicCompositeRequest,
)

if TYPE_CHECKING:
    from market_regime_alpha.data.free_operational_policy import (
        FreeOperationalEvidencePolicy,
    )


Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class BaoStockFreeSupplementalClient:
    """Acquire only configured ETF history; never discover or substitute."""

    history_client: PublicAcquisitionClient
    policy: FreeOperationalEvidencePolicy
    provider_profile_id: str
    clock: Clock = lambda: datetime.now(UTC).replace(microsecond=0)

    def acquire(self, request: PublicCompositeRequest) -> PublicCompositeBatch:
        from market_regime_alpha.data.free_operational_policy import (
            build_free_operational_policy_source,
        )

        if request.decision_time.value.date() < min(
            item.effective_from for item in self.policy.themes
        ):
            raise ValueError("free operational policy is not yet effective")
        etf_request = PublicCompositeRequest(
            symbols=tuple(item.etf_id for item in self.policy.etfs),
            decision_time=request.decision_time,
            history_start=request.history_start,
            minimum_history_sessions=max(request.minimum_history_sessions, 11),
        )
        batch = self.history_client.acquire(etf_request)
        if any(
            item.provider_id != BAOSTOCK_PUBLIC_PROVIDER_ID
            for item in batch.raw_payloads
        ):
            raise ValueError("supplemental ETF history must come only from BaoStock")
        if any(item.symbol not in etf_request.symbols for item in batch.bars):
            raise ValueError("supplemental Provider exceeded configured ETF scope")
        observed = self.clock()
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise ValueError("supplemental acquisition clock must be timezone-aware")
        policy_source = build_free_operational_policy_source(
            policy=self.policy,
            retrieved_at=RetrievedAt(observed),
            decision_time=request.decision_time,
            provider_profile_id=self.provider_profile_id,
        )
        return PublicCompositeBatch(
            raw_payloads=(*batch.raw_payloads, policy_source),
            bars=batch.bars,
            quotes=(),
            source_conflicts=batch.source_conflicts,
            limitations=tuple(
                dict.fromkeys(
                    (
                        *batch.limitations,
                        *self.policy.limitations,
                        "FREE_OPERATIONAL_SUPPLEMENTAL",
                        "NO_PROVIDER_FALLBACK",
                    )
                )
            ),
            security_status_observations=(),
        )


__all__ = ["BaoStockFreeSupplementalClient"]
