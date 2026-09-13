"""Version two: bounded, calendar-resolved rolling hypotheses; no executor.

Earlier validation observations may enter a later FIT only after the later
fold's declared maturity gap. Actual knowledge/collection timestamps remain
those of the sealed exploratory Archive. This grants no protected-label access.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import json
from typing import ClassVar

from market_regime_alpha.research_qualification.domain.historical_matrix import HistoricalRidgeCandidate, HistoricalTimeSplit
from market_regime_alpha.research_qualification.domain.historical_study import HistoricalStudyPlan


ROBUSTNESS_CONTROLS = ("zero", "training_mean", "training_median", "ridge_v2")
MATURE_UPDATE_POLICY = "MATURE_EARLIER_VALIDATION_ALLOWED_PROTECTED_LABELS_REQUIRE_OWNER_PERMISSION_V1"


@dataclass(frozen=True, slots=True)
class RollingStudyPlan(HistoricalStudyPlan):
    allowed_candidates: ClassVar[tuple[str, ...]] = ROBUSTNESS_CONTROLS


@dataclass(frozen=True, slots=True)
class HistoricalRollingPlan:
    baseline: RollingStudyPlan
    additional_splits: tuple[HistoricalTimeSplit, ...]
    ridge_candidates: tuple[HistoricalRidgeCandidate, ...]
    step_sessions: int
    mode: str = "ROLLING"
    update_policy: str = MATURE_UPDATE_POLICY

    def __post_init__(self) -> None:
        if self.baseline.candidates != ROBUSTNESS_CONTROLS:
            raise ValueError("rolling v2 requires ZERO, FIT mean, FIT median and original Ridge controls")
        if not self.ridge_candidates or len(self.ridge_candidates) + len(ROBUSTNESS_CONTROLS) > 10:
            raise ValueError("rolling v2 requires 1–6 frozen Ridge hypotheses within ten configurations")
        if len({c.name for c in self.ridge_candidates}) != len(self.ridge_candidates):
            raise ValueError("rolling candidate identities must be unique")
        if self.mode not in {"ROLLING", "EXPANDING"} or self.update_policy != MATURE_UPDATE_POLICY:
            raise ValueError("unsupported rolling mode or historical label update policy")
        if type(self.step_sessions) is not int or not 1 <= self.step_sessions <= 2000:
            raise ValueError("rolling stride requires 1..2000 actual Calendar sessions")
        if len(self.splits) > 12:
            raise ValueError("rolling v2 supports at most twelve predeclared folds")
        previous = None
        for split in self.splits:
            if not 2 <= len(split.fit_dates) <= 252 or not 1 <= len(split.validation_dates) <= 250:
                raise ValueError("rolling v2 FIT/validation exceeds the bounded session budget")
            if len(split.validation_dates) != len(self.baseline.validation_dates):
                raise ValueError("validation lengths must remain fixed before execution")
            if previous is not None:
                if split.validation_dates[0] <= previous.validation_dates[-1] or split.fit_dates[-1] <= previous.validation_dates[-1]:
                    raise ValueError("validation cannot repeat; subsequent FIT cutoff must advance past earlier validation")
                if self.mode == "ROLLING" and (len(split.fit_dates) != len(previous.fit_dates) or split.fit_dates[0] <= previous.fit_dates[0]):
                    raise ValueError("rolling FIT requires an advancing fixed-length window")
                if self.mode == "EXPANDING" and split.fit_dates[:len(previous.fit_dates)] != previous.fit_dates:
                    raise ValueError("expanding FIT must retain its exact chronological prefix")
            previous = split

    @property
    def splits(self) -> tuple[HistoricalTimeSplit, ...]:
        p = self.baseline
        return (HistoricalTimeSplit(p.fit_dates, p.purge_dates, p.embargo_dates, p.validation_dates), *self.additional_splits)

    @classmethod
    def from_bytes(cls, content: bytes) -> "HistoricalRollingPlan":
        def closed(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate rolling plan field")
                result[key] = value
            return result
        raw = json.loads(content, object_pairs_hook=closed)
        fields = {"schema", "baseline", "additional_splits", "ridge_candidates", "step_sessions", "mode", "update_policy"}
        if not isinstance(raw, dict) or set(raw) != fields or raw["schema"] != "mra-historical-rolling-v2":
            raise ValueError("unsupported rolling v2 schema/fields")
        baseline_raw = raw["baseline"]
        if not isinstance(baseline_raw, dict) or baseline_raw.get("schema") != "mra-rolling-study-v2":
            raise ValueError("rolling v2 requires its distinct study contract")
        # Reuse the strict structural decoder without expanding the v1 whitelist.
        baseline = RollingStudyPlan.from_bytes(json.dumps(baseline_raw | {"schema": "mra-historical-study-v1"}).encode())
        if not isinstance(raw["additional_splits"], list) or not isinstance(raw["ridge_candidates"], list):
            raise ValueError("rolling splits/candidates must be arrays")
        splits = []
        for split in raw["additional_splits"]:
            if not isinstance(split, dict) or set(split) != {"fit_dates", "purge_dates", "embargo_dates", "validation_dates"} or any(not isinstance(v, list) for v in split.values()):
                raise ValueError("rolling split requires exactly four date arrays")
            splits.append(HistoricalTimeSplit(**{name: tuple(date.fromisoformat(d) for d in values) for name, values in split.items()}))
        candidates = []
        for candidate in raw["ridge_candidates"]:
            if not isinstance(candidate, dict) or set(candidate) != {"name", "feature_names", "ridge_alpha"} or not isinstance(candidate["feature_names"], list) or not isinstance(candidate["ridge_alpha"], str):
                raise ValueError("rolling candidate requires exact feature order and decimal-string alpha")
            candidates.append(HistoricalRidgeCandidate(candidate["name"], tuple(candidate["feature_names"]), Decimal(candidate["ridge_alpha"])))
        return cls(baseline, tuple(splits), tuple(candidates), raw["step_sessions"], raw["mode"], raw["update_policy"])
