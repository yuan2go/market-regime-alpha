"""Current Backtest reporting consumer for historical paired research diagnostics."""

from dataclasses import asdict
from typing import Protocol, Any
from uuid import UUID

from market_regime_alpha.research_qualification.application.backtest_reports import BacktestReportApplication
from market_regime_alpha.research_qualification.application.backtest_diagnostics import BacktestDiagnosticsSourcePort
from market_regime_alpha.research_qualification.domain.backtest import BacktestSpecification, BacktestSessionRole
from market_regime_alpha.research_qualification.domain.backtest_diagnostics import summarize_funnel
from market_regime_alpha.research_qualification.domain.historical_comparison import (
    HistoricalEvaluationPoint,
    historical_comparison_statistics,
)
from market_regime_alpha.research_qualification.errors import BacktestReportIntegrityError
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.research_qualification.ports.source_comparison import SourceComparisonInputs
from market_regime_alpha.research_qualification.ports.model_execution import ModelPredictor


class HistoricalComparisonInputs(Protocol):
    def load(self, run_id: UUID) -> tuple[HistoricalEvaluationPoint, ...]: ...

    def contiguous_folds(self, run_id: UUID) -> frozenset[UUID]: ...

    def fitted_diagnostics(self, run_id: UUID) -> tuple[dict, ...]: ...


class HistoricalSpecificationReader(Protocol):
    def load_specification(self, exploratory_backtest_run_id: UUID) -> BacktestSpecification: ...


class HistoricalComparisonApplication:
    def __init__(
        self,
        inputs: HistoricalComparisonInputs,
        reports: BacktestReportApplication,
        diagnostics: BacktestDiagnosticsSourcePort,
        specifications: HistoricalSpecificationReader,
        source_inputs: SourceComparisonInputs | None = None,
        model_predictor: ModelPredictor | None = None,
    ) -> None:
        self._inputs, self._reports, self._diagnostics, self._specifications = inputs, reports, diagnostics, specifications
        self._source_inputs, self._model_predictor = source_inputs, model_predictor

    def compare_sources(self, **arguments) -> dict[str, Any]:
        from market_regime_alpha.research_qualification.application.source_comparison import source_comparison
        if self._source_inputs is None or self._model_predictor is None:
            raise ValueError("source sensitivity requires the composed Dataset/Model owner inputs")
        return source_comparison(self._specifications, self._inputs, self.project, self._source_inputs, self._model_predictor, **arguments)

    def project(self, run_id: UUID, *, projection_version: int | None = None) -> dict[str, Any]:
        if projection_version not in (None, 3):
            raise ValueError("historical projection supports its original default or explicit version 3")
        report = self._reports.project(run_id)
        spec = self._specifications.load_specification(run_id)
        funnel = self._diagnostics.load(run_id)
        summary = summarize_funnel(funnel)
        points = self._inputs.load(run_id)
        # Completed Evaluation inputs, their exact revisions and frozen plans
        # are immutable. Reconcile once per invocation, then reload those exact
        # identities; no retained verification cache or second full replay.
        if funnel.specification_sha256 != str(spec.content_sha256):
            raise BacktestReportIntegrityError("historical comparison changed while reading canonical inputs")
        sessions = tuple(
            (fold.exploratory_backtest_fold_id, s.exploratory_backtest_fold_session_id, s.session_date)
            for fold in spec.folds
            for s in fold.sessions
            if s.role is BacktestSessionRole.EVALUATION
        )
        members = {(m.arm_id, m.session_id, m.instrument_id): m for m in funnel.members}
        session_ids = {str(session_id) for _, session_id, _ in sessions}
        expected = {
            (m.arm_id, m.session_id, m.instrument_id) for m in funnel.members if m.candidate_id is not None and m.session_id in session_ids
        }
        actual = {(str(p.arm_id), str(p.session_id), str(p.instrument_id)) for p in points}
        if actual != expected:
            raise BacktestReportIntegrityError("historical comparison MAE input roster omits or duplicates canonical candidates")
        statistics = historical_comparison_statistics(
            points,
            arms=tuple((a.exploratory_backtest_arm_id, a.arm_code) for a in spec.arms),
            sessions=sessions,
            instruments=tuple(m.instrument_id for m in spec.sample_members),
            baseline_arm_id=spec.arms[0].exploratory_backtest_arm_id,
            contiguous_folds=self._inputs.contiguous_folds(run_id),
        )
        payload = {
            "schema": "mra-historical-comparison-v1",
            "authority": "READ_ONLY_RECONCILED_EVALUATION_PROJECTION",
            "run_id": run_id,
            "specification_sha256": str(spec.content_sha256),
            "canonical_report": report,
            "full_funnel": summary,
            "statistics": statistics,
            "training_lineage": tuple(asdict(t) for t in funnel.training),
            "input_roster": tuple(asdict(p) for p in points),
            "pre_candidate_exclusions": tuple(asdict(m) for key, m in members.items() if key not in actual and m.candidate_id is None),
            "selection_rule": "ALL_ARM_COMMON_VALIDATION_MAE; TIES_BY_PREDECLARED_ARM_ORDINAL",
            "inference_limitations": (
                "STATIC_UNIVERSE/SURVIVORSHIP_LIMITED",
                "ACTUAL_BACKFILL_KNOWLEDGE_NOT_PIT",
                "TEMPORAL_EXPLORATORY_ONLY",
                "MULTIPLE_CANDIDATES_ALL_RETAINED",
                "NOT_ACCOUNT_NAV_OR_TRADABLE_ALPHA",
            ),
        }
        if spec.walk_forward_policy.policy_version == 2 and spec.walk_forward_policy.policy_code == "explicit_calendar_split":
            from market_regime_alpha.research_qualification.domain.robustness_statistics import robustness_statistics
            payload["schema"] = "mra-historical-comparison-v2"
            payload["robustness"] = robustness_statistics(points,
                arms=tuple((a.exploratory_backtest_arm_id,a.arm_code) for a in spec.arms),sessions=sessions,
                instruments=tuple(m.instrument_id for m in spec.sample_members),contiguous_folds=self._inputs.contiguous_folds(run_id))
            payload["fitted_diagnostics"] = self._inputs.fitted_diagnostics(run_id)
        payload["projection_sha256"] = canonical_json_sha256(payload)
        if projection_version == 3:
            from market_regime_alpha.research_qualification.domain.historical_ordering import with_independent_ordering
            return with_independent_ordering(payload)
        return payload
