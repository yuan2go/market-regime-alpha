"""PostgreSQL-backed owner seam for the frozen Temporal Validation window."""

from __future__ import annotations

from datetime import datetime

from market_regime_alpha.application.historical_corpus.temporal_validation_window import (
    FrozenTemporalValidationWindow,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact


class PostgresTemporalValidationWindowAuthority:
    """Use the existing Research Validation PostgreSQL authority, not a new store."""

    def __init__(self, repository: PostgresResearchValidationRepository) -> None:
        self._repository = repository

    def record(
        self,
        *,
        calendar: TradingCalendarArtifact,
        window: FrozenTemporalValidationWindow,
        recorded_at: datetime,
    ) -> FrozenTemporalValidationWindow:
        calendar_reference = ValidationArtifactReference(
            "TRADING_CALENDAR",
            calendar.artifact_id,
            calendar.content_hash,
        )
        if window.calendar_reference != calendar_reference:
            raise ValueError("Temporal window Calendar owner drifted")
        self._repository.record(
            artifact_id=calendar.artifact_id,
            artifact_hash=calendar.content_hash,
            artifact_kind="TRADING_CALENDAR",
            evidence_authority="ENGINEERING_ONLY",
            payload=calendar.semantic_payload(),
            created_at=recorded_at,
        )
        self._repository.record(
            artifact_id=window.window_id,
            artifact_hash=window.window_hash,
            artifact_kind="FROZEN_TEMPORAL_VALIDATION_WINDOW",
            evidence_authority="ENGINEERING_ONLY",
            payload=window.identity_payload(),
            created_at=recorded_at,
        )
        return self.get(window.reference)

    def get(
        self,
        reference: ValidationArtifactReference,
    ) -> FrozenTemporalValidationWindow:
        if reference.artifact_kind != "FROZEN_TEMPORAL_VALIDATION_WINDOW":
            raise ValueError("Temporal window reference kind is invalid")
        payload = self._repository.get_artifact_payload(reference)
        window = FrozenTemporalValidationWindow.from_canonical_dict(
            {
                "window_id": str(reference.artifact_id),
                "window_hash": reference.content_hash,
                **payload,
            }
        )
        calendar_payload = self._repository.get_artifact_payload(
            window.calendar_reference
        )
        calendar = TradingCalendarArtifact.from_canonical_dict(
            {
                "artifact_id": str(window.calendar_reference.artifact_id),
                **calendar_payload,
            }
        )
        if calendar.content_hash != window.calendar_reference.content_hash:
            raise ValueError("Temporal window Calendar payload drifted")
        return window


__all__ = ["PostgresTemporalValidationWindowAuthority"]
