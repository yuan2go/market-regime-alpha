"""Cross-context lifecycle review orchestration and immutable replay package."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
from datetime import datetime
from typing import Any

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.decision.thesis import TradingThesis
from market_regime_alpha.evaluation.lifecycle import (
    RollingScorecard,
    RollingScorecardBuilder,
    TradeEvaluationConfig,
    TradeOutcome,
    TradeOutcomeEvaluator,
    TradePathObservation,
)
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.execution.manual import ExecutionDeviation, Fill
from market_regime_alpha.portfolio.lifecycle import PortfolioDecision, RiskDecision
from market_regime_alpha.portfolio.serialization import (
    portfolio_decision_from_dict,
    risk_decision_from_dict,
)
from market_regime_alpha.position.assessment import (
    ExitAssessment,
    ExitAssessmentModel,
    HoldingAssessment,
    HoldingAssessmentModel,
    PositionLifecycleConfig,
    ThesisHealthObservation,
)
from market_regime_alpha.position.authority import PositionProjector, PositionSnapshot


LIFECYCLE_REVIEW_SCHEMA = "production-decision-lifecycle-review-v1"
LIFECYCLE_REVIEW_PACKAGE_SCHEMA = "production-decision-lifecycle-package-v1"
LIFECYCLE_REVIEW_FILES = ("SHA256SUMS.json", "artifact.json", "manifest.json")


@dataclass(frozen=True, slots=True)
class LifecycleReviewRun:
    schema_version: str
    artifact_id: ArtifactId
    content_hash: str
    thesis: TradingThesis
    assessment_configuration: PositionLifecycleConfig
    health_observation: ThesisHealthObservation
    assessed_at: datetime
    evaluation_configuration: TradeEvaluationConfig
    path_observation: TradePathObservation
    fills: tuple[Fill, ...]
    execution_deviations: tuple[ExecutionDeviation, ...]
    prior_outcomes: tuple[TradeOutcome, ...]
    add_portfolio: PortfolioDecision | None
    add_risk: RiskDecision | None
    actor: str
    reason: str
    evaluated_at: datetime
    code_revision: str
    assessment_position: PositionSnapshot
    holding_assessment: HoldingAssessment
    exit_assessment: ExitAssessment
    final_position: PositionSnapshot
    trade_outcome: TradeOutcome
    rolling_scorecard: RollingScorecard

    def __post_init__(self) -> None:
        if self.schema_version != LIFECYCLE_REVIEW_SCHEMA:
            raise ValueError("unsupported LifecycleReviewRun schema")
        require_sha256("content_hash", self.content_hash)
        for label, value in (
            ("actor", self.actor),
            ("reason", self.reason),
            ("code_revision", self.code_revision),
        ):
            if not value or value != value.strip():
                raise ValueError(f"{label} must be a non-empty trimmed string")
        semantic = self.semantic_payload()
        if canonical_hash(semantic) != self.content_hash:
            raise ValueError("LifecycleReviewRun content hash mismatch")
        digest = self.content_hash.split(":", 1)[1]
        if self.artifact_id != ArtifactId(f"lifecycle-review-{digest[:24]}"):
            raise ValueError("LifecycleReviewRun identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return {
            **self.input_payload(),
            "assessment_position": self.assessment_position.to_canonical_dict(),
            "holding_assessment": self.holding_assessment.to_canonical_dict(),
            "exit_assessment": self.exit_assessment.to_canonical_dict(),
            "final_position": self.final_position.to_canonical_dict(),
            "trade_outcome": self.trade_outcome.to_canonical_dict(),
            "rolling_scorecard": self.rolling_scorecard.to_canonical_dict(),
        }

    def input_payload(self) -> dict[str, Any]:
        """Canonical CLI input; it contains no derived assessment/outcome facts."""
        return {
            "schema_version": self.schema_version,
            "thesis": self.thesis.to_canonical_dict(),
            "assessment_configuration": (
                self.assessment_configuration.to_canonical_dict()
            ),
            "health_observation": self.health_observation.to_canonical_dict(),
            "assessed_at": self.assessed_at.isoformat(),
            "evaluation_configuration": (
                self.evaluation_configuration.to_canonical_dict()
            ),
            "path_observation": self.path_observation.to_canonical_dict(),
            "fills": [item.to_canonical_dict() for item in self.fills],
            "execution_deviations": [
                item.to_canonical_dict() for item in self.execution_deviations
            ],
            "prior_outcomes": [
                item.to_canonical_dict() for item in self.prior_outcomes
            ],
            "add_portfolio": (
                self.add_portfolio.to_canonical_dict()
                if self.add_portfolio is not None
                else None
            ),
            "add_risk": (
                self.add_risk.to_canonical_dict()
                if self.add_risk is not None
                else None
            ),
            "actor": self.actor,
            "reason": self.reason,
            "evaluated_at": self.evaluated_at.isoformat(),
            "code_revision": self.code_revision,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": str(self.artifact_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> LifecycleReviewRun:
        expected = {
            "artifact_id",
            "content_hash",
            "schema_version",
            "thesis",
            "assessment_configuration",
            "health_observation",
            "assessed_at",
            "evaluation_configuration",
            "path_observation",
            "fills",
            "execution_deviations",
            "prior_outcomes",
            "add_portfolio",
            "add_risk",
            "actor",
            "reason",
            "evaluated_at",
            "code_revision",
            "assessment_position",
            "holding_assessment",
            "exit_assessment",
            "final_position",
            "trade_outcome",
            "rolling_scorecard",
        }
        if set(payload) != expected:
            raise ValueError("LifecycleReviewRun fields mismatch")
        add_portfolio = payload["add_portfolio"]
        add_risk = payload["add_risk"]
        return cls(
            schema_version=str(payload["schema_version"]),
            artifact_id=ArtifactId(str(payload["artifact_id"])),
            content_hash=str(payload["content_hash"]),
            thesis=TradingThesis.from_canonical_dict(_object(payload["thesis"])),
            assessment_configuration=PositionLifecycleConfig.from_canonical_dict(
                _object(payload["assessment_configuration"])
            ),
            health_observation=ThesisHealthObservation.from_canonical_dict(
                _object(payload["health_observation"])
            ),
            assessed_at=datetime.fromisoformat(str(payload["assessed_at"])),
            evaluation_configuration=TradeEvaluationConfig.from_canonical_dict(
                _object(payload["evaluation_configuration"])
            ),
            path_observation=TradePathObservation.from_canonical_dict(
                _object(payload["path_observation"])
            ),
            fills=tuple(
                Fill.from_canonical_dict(_object(item))
                for item in _array(payload["fills"])
            ),
            execution_deviations=tuple(
                ExecutionDeviation.from_canonical_dict(_object(item))
                for item in _array(payload["execution_deviations"])
            ),
            prior_outcomes=tuple(
                TradeOutcome.from_canonical_dict(_object(item))
                for item in _array(payload["prior_outcomes"])
            ),
            add_portfolio=(
                portfolio_decision_from_dict(_object(add_portfolio))
                if add_portfolio is not None
                else None
            ),
            add_risk=(
                risk_decision_from_dict(_object(add_risk))
                if add_risk is not None
                else None
            ),
            actor=str(payload["actor"]),
            reason=str(payload["reason"]),
            evaluated_at=datetime.fromisoformat(str(payload["evaluated_at"])),
            code_revision=str(payload["code_revision"]),
            assessment_position=PositionSnapshot.from_canonical_dict(
                _object(payload["assessment_position"])
            ),
            holding_assessment=HoldingAssessment.from_canonical_dict(
                _object(payload["holding_assessment"])
            ),
            exit_assessment=ExitAssessment.from_canonical_dict(
                _object(payload["exit_assessment"])
            ),
            final_position=PositionSnapshot.from_canonical_dict(
                _object(payload["final_position"])
            ),
            trade_outcome=TradeOutcome.from_canonical_dict(
                _object(payload["trade_outcome"])
            ),
            rolling_scorecard=RollingScorecard.from_canonical_dict(
                _object(payload["rolling_scorecard"])
            ),
        )


@dataclass(frozen=True, slots=True)
class VerifiedLifecycleReview:
    root: Path
    review: LifecycleReviewRun
    checksums_hash: str


class LifecycleReviewApplicationService:
    def run(
        self,
        *,
        thesis: TradingThesis,
        assessment_configuration: PositionLifecycleConfig,
        health_observation: ThesisHealthObservation,
        assessed_at: datetime,
        evaluation_configuration: TradeEvaluationConfig,
        path_observation: TradePathObservation,
        fills: tuple[Fill, ...],
        execution_deviations: tuple[ExecutionDeviation, ...],
        prior_outcomes: tuple[TradeOutcome, ...],
        actor: str,
        reason: str,
        evaluated_at: datetime,
        code_revision: str,
        add_portfolio: PortfolioDecision | None = None,
        add_risk: RiskDecision | None = None,
    ) -> LifecycleReviewRun:
        ordered_fills = tuple(
            sorted(fills, key=lambda item: (item.recorded_at, str(item.fill_id)))
        )
        if not ordered_fills or len({item.fill_id for item in ordered_fills}) != len(
            ordered_fills
        ):
            raise ValueError("lifecycle replay requires unique Fill history")
        assessment_fills = tuple(
            item for item in ordered_fills if item.recorded_at <= assessed_at
        )
        final_fills = tuple(
            item for item in ordered_fills if item.recorded_at <= evaluated_at
        )
        if final_fills != ordered_fills:
            raise ValueError("lifecycle review cannot consume future Fill")
        first = ordered_fills[0]
        projector = PositionProjector()
        assessment_position = projector.project(
            account_id=first.account_id,
            symbol=first.symbol,
            fills=assessment_fills,
            as_of=assessed_at,
        )
        holding = HoldingAssessmentModel().assess(
            thesis,
            assessment_position,
            health_observation,
            assessment_configuration,
            assessed_at=assessed_at,
            actor=actor,
            reason=reason,
            add_portfolio=add_portfolio,
            add_risk=add_risk,
        )
        exit_assessment = ExitAssessmentModel().assess(
            thesis,
            assessment_position,
            health_observation,
            assessment_configuration,
            assessed_at=assessed_at,
            actor=actor,
            reason=reason,
        )
        final_position = projector.project(
            account_id=first.account_id,
            symbol=first.symbol,
            fills=ordered_fills,
            as_of=evaluated_at,
        )
        outcome = TradeOutcomeEvaluator().evaluate(
            thesis=thesis,
            final_position=final_position,
            fills=ordered_fills,
            path=path_observation,
            execution_deviations=execution_deviations,
            configuration=evaluation_configuration,
            evaluated_at=evaluated_at,
        )
        scorecard = RollingScorecardBuilder().build(
            (*prior_outcomes, outcome),
            evaluation_configuration,
            evaluated_at=evaluated_at,
        )
        semantic = {
            "schema_version": LIFECYCLE_REVIEW_SCHEMA,
            "thesis": thesis.to_canonical_dict(),
            "assessment_configuration": assessment_configuration.to_canonical_dict(),
            "health_observation": health_observation.to_canonical_dict(),
            "assessed_at": assessed_at.isoformat(),
            "evaluation_configuration": evaluation_configuration.to_canonical_dict(),
            "path_observation": path_observation.to_canonical_dict(),
            "fills": [item.to_canonical_dict() for item in ordered_fills],
            "execution_deviations": [
                item.to_canonical_dict()
                for item in sorted(
                    execution_deviations, key=lambda item: str(item.manual_trade_id)
                )
            ],
            "prior_outcomes": [item.to_canonical_dict() for item in prior_outcomes],
            "add_portfolio": (
                add_portfolio.to_canonical_dict()
                if add_portfolio is not None
                else None
            ),
            "add_risk": add_risk.to_canonical_dict() if add_risk is not None else None,
            "actor": actor,
            "reason": reason,
            "evaluated_at": evaluated_at.isoformat(),
            "code_revision": code_revision,
            "assessment_position": assessment_position.to_canonical_dict(),
            "holding_assessment": holding.to_canonical_dict(),
            "exit_assessment": exit_assessment.to_canonical_dict(),
            "final_position": final_position.to_canonical_dict(),
            "trade_outcome": outcome.to_canonical_dict(),
            "rolling_scorecard": scorecard.to_canonical_dict(),
        }
        digest = canonical_hash(semantic)
        return LifecycleReviewRun(
            schema_version=LIFECYCLE_REVIEW_SCHEMA,
            artifact_id=ArtifactId(
                f"lifecycle-review-{digest.split(':', 1)[1][:24]}"
            ),
            content_hash=digest,
            thesis=thesis,
            assessment_configuration=assessment_configuration,
            health_observation=health_observation,
            assessed_at=assessed_at,
            evaluation_configuration=evaluation_configuration,
            path_observation=path_observation,
            fills=ordered_fills,
            execution_deviations=tuple(
                sorted(
                    execution_deviations, key=lambda item: str(item.manual_trade_id)
                )
            ),
            prior_outcomes=prior_outcomes,
            add_portfolio=add_portfolio,
            add_risk=add_risk,
            actor=actor,
            reason=reason,
            evaluated_at=evaluated_at,
            code_revision=code_revision,
            assessment_position=assessment_position,
            holding_assessment=holding,
            exit_assessment=exit_assessment,
            final_position=final_position,
            trade_outcome=outcome,
            rolling_scorecard=scorecard,
        )


def publish_lifecycle_review(*, root: Path, review: LifecycleReviewRun) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(review.artifact_id)
    if final.exists():
        existing = load_verified_lifecycle_review(final)
        if existing.review != review:
            raise FileExistsError(f"conflicting lifecycle review exists: {final}")
        return final
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    try:
        _write_json(stage / "artifact.json", review.to_canonical_dict())
        _write_json(stage / "manifest.json", _manifest(review))
        _write_json(
            stage / "SHA256SUMS.json",
            {
                name: _file_hash(stage / name)
                for name in LIFECYCLE_REVIEW_FILES
                if name != "SHA256SUMS.json"
            },
        )
        if {item.name for item in stage.iterdir()} != set(LIFECYCLE_REVIEW_FILES):
            raise RuntimeError("lifecycle review staging exact file set mismatch")
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def run_lifecycle_review_input(payload: dict[str, Any]) -> LifecycleReviewRun:
    expected = {
        "schema_version",
        "thesis",
        "assessment_configuration",
        "health_observation",
        "assessed_at",
        "evaluation_configuration",
        "path_observation",
        "fills",
        "execution_deviations",
        "prior_outcomes",
        "add_portfolio",
        "add_risk",
        "actor",
        "reason",
        "evaluated_at",
        "code_revision",
    }
    if set(payload) != expected or payload["schema_version"] != LIFECYCLE_REVIEW_SCHEMA:
        raise ValueError("lifecycle review input fields mismatch")
    add_portfolio = payload["add_portfolio"]
    add_risk = payload["add_risk"]
    return LifecycleReviewApplicationService().run(
        thesis=TradingThesis.from_canonical_dict(_object(payload["thesis"])),
        assessment_configuration=PositionLifecycleConfig.from_canonical_dict(
            _object(payload["assessment_configuration"])
        ),
        health_observation=ThesisHealthObservation.from_canonical_dict(
            _object(payload["health_observation"])
        ),
        assessed_at=datetime.fromisoformat(str(payload["assessed_at"])),
        evaluation_configuration=TradeEvaluationConfig.from_canonical_dict(
            _object(payload["evaluation_configuration"])
        ),
        path_observation=TradePathObservation.from_canonical_dict(
            _object(payload["path_observation"])
        ),
        fills=tuple(
            Fill.from_canonical_dict(_object(item))
            for item in _array(payload["fills"])
        ),
        execution_deviations=tuple(
            ExecutionDeviation.from_canonical_dict(_object(item))
            for item in _array(payload["execution_deviations"])
        ),
        prior_outcomes=tuple(
            TradeOutcome.from_canonical_dict(_object(item))
            for item in _array(payload["prior_outcomes"])
        ),
        add_portfolio=(
            portfolio_decision_from_dict(_object(add_portfolio))
            if add_portfolio is not None
            else None
        ),
        add_risk=(
            risk_decision_from_dict(_object(add_risk))
            if add_risk is not None
            else None
        ),
        actor=str(payload["actor"]),
        reason=str(payload["reason"]),
        evaluated_at=datetime.fromisoformat(str(payload["evaluated_at"])),
        code_revision=str(payload["code_revision"]),
    )


def load_verified_lifecycle_review(path: Path) -> VerifiedLifecycleReview:
    root = path.resolve()
    _verify_files(root)
    review = LifecycleReviewRun.from_canonical_dict(
        _read_object(root / "artifact.json")
    )
    if root.name != str(review.artifact_id):
        raise ValueError("lifecycle review directory identity mismatch")
    if _read_object(root / "manifest.json") != _manifest(review):
        raise ValueError("lifecycle review manifest is not reconstructible")
    return VerifiedLifecycleReview(
        root=root,
        review=review,
        checksums_hash=_file_hash(root / "SHA256SUMS.json"),
    )


def replay_lifecycle_review(path: Path) -> VerifiedLifecycleReview:
    verified = load_verified_lifecycle_review(path)
    original = verified.review
    replayed = LifecycleReviewApplicationService().run(
        thesis=original.thesis,
        assessment_configuration=original.assessment_configuration,
        health_observation=original.health_observation,
        assessed_at=original.assessed_at,
        evaluation_configuration=original.evaluation_configuration,
        path_observation=original.path_observation,
        fills=original.fills,
        execution_deviations=original.execution_deviations,
        prior_outcomes=original.prior_outcomes,
        actor=original.actor,
        reason=original.reason,
        evaluated_at=original.evaluated_at,
        code_revision=original.code_revision,
        add_portfolio=original.add_portfolio,
        add_risk=original.add_risk,
    )
    if replayed != original:
        raise ValueError("lifecycle review replay differs from stored Artifact")
    return verified


def _manifest(review: LifecycleReviewRun) -> dict[str, Any]:
    return {
        "schema_version": LIFECYCLE_REVIEW_PACKAGE_SCHEMA,
        "artifact_id": str(review.artifact_id),
        "content_hash": review.content_hash,
        "thesis_id": str(review.thesis.thesis_id),
        "position_snapshot_id": str(review.final_position.snapshot_id),
        "trade_outcome_id": str(review.trade_outcome.outcome_id),
        "scorecard_id": str(review.rolling_scorecard.scorecard_id),
        "required_artifacts": sorted(LIFECYCLE_REVIEW_FILES),
        "data_eligibility": "EXPLORATORY",
        "formal_pit": "FORMAL_PIT_NOT_ESTABLISHED",
        "formal_oos_alpha": "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
        "trading_authority": "TRADING_AUTHORITY_NOT_GRANTED",
    }


def _verify_files(root: Path) -> None:
    if not root.is_dir() or {item.name for item in root.iterdir()} != set(
        LIFECYCLE_REVIEW_FILES
    ):
        raise ValueError("lifecycle review exact file set mismatch")
    if any(not item.is_file() for item in root.iterdir()):
        raise ValueError("lifecycle review exact file set contains a non-file")
    checksums = _read_object(root / "SHA256SUMS.json")
    expected = set(LIFECYCLE_REVIEW_FILES) - {"SHA256SUMS.json"}
    if set(checksums) != expected:
        raise ValueError("lifecycle review checksum coverage mismatch")
    for name, expected_hash in checksums.items():
        if not isinstance(expected_hash, str) or _file_hash(root / name) != expected_hash:
            raise ValueError(f"lifecycle review checksum mismatch: {name}")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid lifecycle review JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("lifecycle review value must be an object")
    return value


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("lifecycle review value must be an array")
    return value
