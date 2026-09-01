"""Read-only WP-11 Authority verifier."""

from uuid import UUID

from market_regime_alpha.research_qualification.domain.verification import (
    ResearchVerificationReport,
)
from market_regime_alpha.research_qualification.ports.verification import (
    ResearchEvaluationVerificationProvider,
)


class ResearchEvaluationVerifier:
    def __init__(self, provider: ResearchEvaluationVerificationProvider) -> None:
        self._provider = provider

    def verify_partition(self, research_partition_id: UUID) -> ResearchVerificationReport:
        return ResearchVerificationReport.create(
            authority_kind="RESEARCH_PARTITION",
            authority_id=research_partition_id,
            mismatches=self._provider.inspect_partition(research_partition_id),
        )

    def verify_experiment(self, experiment_id: UUID) -> ResearchVerificationReport:
        return ResearchVerificationReport.create(
            authority_kind="EXPERIMENT",
            authority_id=experiment_id,
            mismatches=self._provider.inspect_experiment(experiment_id),
        )

    def verify_evaluation_run(self, evaluation_run_id: UUID) -> ResearchVerificationReport:
        return ResearchVerificationReport.create(
            authority_kind="EVALUATION_RUN",
            authority_id=evaluation_run_id,
            mismatches=self._provider.inspect_evaluation_run(evaluation_run_id),
        )


__all__ = ["ResearchEvaluationVerifier"]
