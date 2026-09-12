"""Finite, explicit rolling Feature/Ridge matrix over the original study contract."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import json
import re

from market_regime_alpha.research_qualification.domain.historical_features import FACTORS
from market_regime_alpha.research_qualification.domain.historical_study import BASELINE_CANDIDATES, HistoricalStudyPlan


@dataclass(frozen=True, slots=True)
class HistoricalTimeSplit:
    fit_dates: tuple[date, ...]
    purge_dates: tuple[date, ...]
    embargo_dates: tuple[date, ...]
    validation_dates: tuple[date, ...]

    def __post_init__(self) -> None:
        dates = self.fit_dates+self.purge_dates+self.embargo_dates+self.validation_dates
        if any(not getattr(self,name) for name in ("fit_dates","purge_dates","embargo_dates","validation_dates")):
            raise ValueError("each historical split requires FIT, maturity purge, embargo and validation")
        if dates != tuple(sorted(set(dates))):
            raise ValueError("historical split dates must be unique and chronological")


@dataclass(frozen=True, slots=True)
class HistoricalRidgeCandidate:
    name: str
    feature_names: tuple[str, ...]
    ridge_alpha: Decimal

    def __post_init__(self) -> None:
        if not re.fullmatch(r"ridge_[a-z0-9_]{1,39}",self.name) or self.name in BASELINE_CANDIDATES:
            raise ValueError("expanded Ridge candidate needs a distinct explicit name")
        expected = tuple(f.name for f in FACTORS if f.name in self.feature_names)
        if not expected or self.feature_names!=expected:
            raise ValueError("expanded Ridge Features must be unique and in the frozen factor order")
        if not isinstance(self.ridge_alpha,Decimal) or self.ridge_alpha not in {Decimal(".1"),Decimal(1),Decimal(10)}:
            raise ValueError("finite research alpha budget is exactly 0.1, 1 or 10")


@dataclass(frozen=True, slots=True)
class HistoricalMatrixPlan:
    baseline: HistoricalStudyPlan
    additional_splits: tuple[HistoricalTimeSplit, ...]
    ridge_candidates: tuple[HistoricalRidgeCandidate, ...]
    step_sessions: int = 250

    def __post_init__(self) -> None:
        if self.baseline.candidates != BASELINE_CANDIDATES:
            raise ValueError("expanded research must retain all seven original baseline controls")
        if not self.ridge_candidates or len(self.ridge_candidates)+len(BASELINE_CANDIDATES)>20:
            raise ValueError("historical matrix requires expanded candidates within the frozen 20-configuration budget")
        if len({c.name for c in self.ridge_candidates}) != len(self.ridge_candidates):
            raise ValueError("historical candidate names must be unique")
        if len(self.additional_splits)>5:
            raise ValueError("historical matrix supports at most six explicit rolling splits")
        if type(self.step_sessions) is not int or not 1<=self.step_sessions<=2000:
            raise ValueError("rolling step must be 1..2000 actual Calendar sessions")
        previous_fit = self.baseline.fit_dates[0]
        previous_validation = self.baseline.validation_dates[-1]
        for split in self.additional_splits:
            if split.fit_dates[0]<=previous_fit or split.fit_dates[0]<=previous_validation:
                raise ValueError("this bounded rolling matrix requires separated FIT/validation periods")
            previous_fit,previous_validation=split.fit_dates[0],split.validation_dates[-1]
            if (len(split.fit_dates),len(split.validation_dates)) != (len(self.baseline.fit_dates),len(self.baseline.validation_dates)):
                raise ValueError("rolling study requires the same predeclared FIT and validation window lengths")

    @property
    def splits(self) -> tuple[HistoricalTimeSplit, ...]:
        p=self.baseline
        return (HistoricalTimeSplit(p.fit_dates,p.purge_dates,p.embargo_dates,p.validation_dates),*self.additional_splits)

    @classmethod
    def from_bytes(cls,content: bytes) -> "HistoricalMatrixPlan":
        def closed(pairs):
            result={}
            for key,value in pairs:
                if key in result:
                    raise ValueError("duplicate historical matrix field")
                result[key]=value
            return result
        raw=json.loads(content,object_pairs_hook=closed)
        required={"schema","baseline","additional_splits","ridge_candidates"}
        if not isinstance(raw,dict) or not required.issubset(raw) or set(raw)-required-{"step_sessions"} or raw["schema"]!="mra-historical-matrix-v1":
            raise ValueError("unsupported historical matrix schema/fields")
        baseline=HistoricalStudyPlan.from_bytes(json.dumps(raw["baseline"]).encode())
        if not isinstance(raw["additional_splits"],list) or not isinstance(raw["ridge_candidates"],list):
            raise ValueError("matrix split and candidate rosters must be arrays")
        split_fields={"fit_dates","purge_dates","embargo_dates","validation_dates"}
        for split in raw["additional_splits"]:
            if not isinstance(split,dict) or set(split)!=split_fields or any(not isinstance(values,list) for values in split.values()):
                raise ValueError("each matrix split requires exactly four date arrays")
        for candidate in raw["ridge_candidates"]:
            if (not isinstance(candidate,dict) or set(candidate)!={"name","feature_names","ridge_alpha"}
                    or not isinstance(candidate["feature_names"],list) or not isinstance(candidate["ridge_alpha"],str)):
                raise ValueError("each matrix candidate requires exact fields and a decimal string alpha")
        splits=tuple(HistoricalTimeSplit(**{name:tuple(date.fromisoformat(v) for v in values) for name,values in split.items()}) for split in raw["additional_splits"])
        candidates=tuple(HistoricalRidgeCandidate(**(candidate|{"feature_names":tuple(candidate["feature_names"]),"ridge_alpha":Decimal(candidate["ridge_alpha"])})) for candidate in raw["ridge_candidates"])
        return cls(baseline,splits,candidates,raw.get("step_sessions",250))
