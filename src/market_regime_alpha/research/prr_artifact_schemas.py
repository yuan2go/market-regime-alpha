"""Single source of truth for immutable PRR Dataset and MR-1 artifact schemas."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, slots=True)
class ArtifactSchema:
    """Version, exact file set, and required manifest fields for one artifact."""

    schema_version: str
    required_files: frozenset[str]
    required_manifest_keys: frozenset[str]

    def __post_init__(self) -> None:
        if not self.schema_version or not self.schema_version.strip():
            raise ValueError("artifact schema_version must be non-empty")
        if "SHA256SUMS.json" not in self.required_files:
            raise ValueError("artifact schema must require SHA256SUMS.json")
        if "schema_version" not in self.required_manifest_keys:
            raise ValueError("artifact manifest must require schema_version")


PRR_DATASET_SCHEMA = ArtifactSchema(
    schema_version="prr-mvp-1-dataset-v1",
    required_files=frozenset(
        {
            "bars.parquet",
            "prepared_sessions.parquet",
            "decision_snapshots.parquet",
            "candidate_rankings.parquet",
            "dataset_manifest.json",
            "data_quality.json",
            "limitations.json",
            "SHA256SUMS.json",
        }
    ),
    required_manifest_keys=frozenset(
        {
            "schema_version",
            "dataset_id",
            "data_eligibility",
            "symbol_count",
            "accepted_symbol_count",
            "session_count",
            "decision_count",
            "row_counts",
            "date_range",
            "quality_disposition",
            "retrieved_at",
        }
    ),
)


class CandidateBaselineId(str, Enum):
    ALL_CANDIDATE_GROSS_V1 = "ALL_CANDIDATE_GROSS_V1"
    MATCHED_K_HASH_GROSS_V1 = "MATCHED_K_HASH_GROSS_V1"
    MATCHED_K_HASH_NET_V1 = "MATCHED_K_HASH_NET_V1"
    ALL_CANDIDATE_NET_DIAGNOSTIC_V1 = "ALL_CANDIDATE_NET_DIAGNOSTIC_V1"


MR1_CANDIDATE_BASELINE_SCHEMA_VERSION = "mr-1-candidate-baseline-family-v2"
MR1_RUN_SCHEMA = ArtifactSchema(
    schema_version="mr-1-run-v3",
    required_files=frozenset(
        {
            "manifest.json",
            "limitations.json",
            "morning_targets.parquet",
            "orders.parquet",
            "fills.parquet",
            "trades.parquet",
            "daily_equity.parquet",
            "candidate_daily_baselines.parquet",
            "chronological_model_metrics.parquet",
            "model_target_matrix.csv",
            "exit_time_comparison.json",
            "metrics.json",
            "report.md",
            "SHA256SUMS.json",
        }
    ),
    required_manifest_keys=frozenset(
        {
            "schema_version",
            "run_id",
            "dataset_id",
            "data_eligibility",
            "required_artifacts",
            "candidate_daily_baseline_schema_version",
            "top_k",
            "exit_times",
            "cost_scenarios",
            "run_identity",
        }
    ),
)

PREPARED_SESSION_PRIMARY_KEY = ("symbol", "session_date")
BAR_PRIMARY_KEY = ("symbol", "timestamp")
DECISION_SNAPSHOT_PRIMARY_KEY = ("decision_date", "symbol")
# The physical PRR table contains three Target families. MR-1 separately validates its
# close-return projection under the narrower key below.
CANDIDATE_RANKING_PRIMARY_KEY = ("decision_date", "target_id", "model_id", "symbol")
MR1_SOURCE_RANKING_PRIMARY_KEY = ("decision_date", "model_id", "symbol")
MR1_DAILY_EQUITY_PRIMARY_KEY = ("session_date", "model_id", "exit_time", "cost_scenario")
MR1_CANDIDATE_BASELINE_PRIMARY_KEY = (
    "decision_date",
    "exit_time",
    "cost_scenario",
    "baseline_id",
    "baseline_seed",
)

MR1_EXIT_TIMES = ("09:35", "10:00", "10:30", "CLOSE")
MR1_COST_SCENARIOS = ("LOW", "BASE", "HIGH")
MR1_MATCHED_K_ALGORITHM_ID = "mr1-matched-k-sha256-rank-blind-v1"
MR1_BASELINE_PRIMARY_SEED = 17
MR1_CASH_LOCK_POLICY_ID = "mr1-close-overlap-cash-lock-v1"
MR1_MISSING_WEIGHT_POLICY_ID = "mr1-fixed-slot-missing-as-cash-v1"
PRR_BAR_CONSUMPTION_POLICY_ID = "prr-bars-history-retained-target-dates-resolved-by-prepared-calendar-v1"
