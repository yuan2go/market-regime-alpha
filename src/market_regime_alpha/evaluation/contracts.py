"""Layer-specific Platform V2 Evaluation Report."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from market_regime_alpha.core.identity import ModelId
from market_regime_alpha.evidence.envelope import ArtifactEnvelope


@dataclass(frozen=True, slots=True)
class EvaluationMetric:
    metric_id: str
    value: float

    def __post_init__(self) -> None:
        if not isfinite(self.value):
            raise ValueError("evaluation metric must be finite")


@dataclass(frozen=True, slots=True)
class EvaluationSlice:
    slice_id: str
    sample_count: int
    metrics: tuple[EvaluationMetric, ...]

    def __post_init__(self) -> None:
        if self.sample_count < 0:
            raise ValueError("slice sample_count must be non-negative")


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    envelope: ArtifactEnvelope
    layer_id: str
    model_id: ModelId
    evaluation_scope: str
    sample_count: int
    coverage: float
    metrics: tuple[EvaluationMetric, ...]
    slice_metrics: tuple[EvaluationSlice, ...]
    blocked_reasons: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.sample_count < 0:
            raise ValueError("sample_count must be non-negative")
        if not 0.0 <= self.coverage <= 1.0:
            raise ValueError("evaluation coverage must be within [0, 1]")
        self.envelope.verify_payload(self.artifact_payload())

    def artifact_payload(self) -> dict[str, Any]:
        return {
            "layer_id": self.layer_id,
            "model_id": str(self.model_id),
            "evaluation_scope": self.evaluation_scope,
            "sample_count": self.sample_count,
            "coverage": self.coverage,
            "metrics": [
                {"metric_id": item.metric_id, "value": item.value}
                for item in self.metrics
            ],
            "slice_metrics": [
                {
                    "slice_id": item.slice_id,
                    "sample_count": item.sample_count,
                    "metrics": [
                        {
                            "metric_id": metric.metric_id,
                            "value": metric.value,
                        }
                        for metric in item.metrics
                    ],
                }
                for item in self.slice_metrics
            ],
            "blocked_reasons": list(self.blocked_reasons),
            "limitations": list(self.limitations),
        }

