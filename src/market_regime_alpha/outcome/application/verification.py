"""Read-only exact replay of frozen Outcome facts."""

from __future__ import annotations

from uuid import UUID

from market_regime_alpha.outcome.domain import (
    OutcomeMismatch,
    OutcomeMismatchKind,
    OutcomeVerificationReport,
    calculate_market_target_outcome,
)
from market_regime_alpha.outcome.errors import OutcomeAuthorityIntegrityError
from market_regime_alpha.outcome.ports import OutcomeReadPort, OutcomeVerificationProvider


class OutcomeVerifier:
    def __init__(
        self,
        queries: OutcomeReadPort,
        verification: OutcomeVerificationProvider,
    ) -> None:
        self._queries = queries
        self._verification = verification

    def verify(self, revision_id: UUID) -> OutcomeVerificationReport:
        mismatches = list(self._verification.inspect(revision_id))
        try:
            snapshot = self._queries.load(revision_id)
        except OutcomeAuthorityIntegrityError as exc:
            mismatches.append(
                OutcomeMismatch(
                    kind=OutcomeMismatchKind.IMMUTABLE_FACT_MUTATION,
                    path="revision",
                    expected="canonical immutable reconstruction",
                    actual=str(exc),
                )
            )
            return OutcomeVerificationReport.create(
                market_target_outcome_id=None,
                revision_id=revision_id,
                mismatches=tuple(mismatches),
            )
        authority = snapshot.authority
        expected = calculate_market_target_outcome(
            target=authority.target,
            reference=authority.commitment.reference,
            sessions=authority.revision.draft.sessions,
            sources=authority.revision.draft.sources,
            observation_cutoff=authority.revision.draft.observation_cutoff,
            knowledge_cutoff=authority.revision.draft.knowledge_cutoff,
        )
        if expected != authority.revision.draft:
            mismatches.append(
                OutcomeMismatch(
                    kind=OutcomeMismatchKind.METRIC_VALUE_MISMATCH,
                    path="revision.pure_kernel",
                    expected=expected.definition_summary_sha256,
                    actual=authority.revision.draft.definition_summary_sha256,
                )
            )
        return OutcomeVerificationReport.create(
            market_target_outcome_id=authority.root.market_target_outcome_id,
            revision_id=revision_id,
            mismatches=tuple(mismatches),
        )


__all__ = ["OutcomeVerifier"]
