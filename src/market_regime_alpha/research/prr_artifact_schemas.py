"""Single source of truth for immutable PRR Dataset and MR-1 artifact schemas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from hashlib import sha256
import json


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


MR1_CANDIDATE_BASELINE_SCHEMA_VERSION = "mr-1-model-population-baseline-family-v3"
MR1_RUN_SCHEMA = ArtifactSchema(
    schema_version="mr-1-run-v4",
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
            "matched_k_selections.parquet",
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
            "dataset_manifest_hash",
            "dataset_checksums_hash",
            "dataset_locator_role",
            "data_eligibility",
            "required_artifacts",
            "candidate_daily_baseline_schema_version",
            "matched_k_selection_schema_version",
            "model_count",
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
    "model_id",
    "exit_time",
    "cost_scenario",
    "baseline_id",
    "baseline_seed",
)
MR1_MATCHED_K_SELECTION_PRIMARY_KEY = (
    "decision_date",
    "model_id",
    "exit_time",
    "cost_scenario",
    "baseline_seed",
    "slot_index",
)

MR1_EXIT_TIMES = ("09:35", "10:00", "10:30", "CLOSE")
MR1_COST_SCENARIOS = ("LOW", "BASE", "HIGH")
MR1_MATCHED_K_ALGORITHM_ID = "mr1-matched-k-sha256-rank-blind-v1"
MR1_BASELINE_PRIMARY_SEED = 17
MR1_CASH_LOCK_POLICY_ID = "mr1-close-overlap-cash-lock-v1"
MR1_MISSING_WEIGHT_POLICY_ID = "mr1-fixed-slot-missing-as-cash-v1"
PRR_BAR_CONSUMPTION_POLICY_ID = "prr-bars-history-retained-target-dates-resolved-by-prepared-calendar-v1"

MR1_MODEL_POPULATION_SCHEMA_VERSION = "mr-1-model-candidate-population-v1"
MR1_MODEL_POPULATION_DEFINITION_ID = "mr1-close-target-eligible-ranked-symbols-v1"
MR1_POPULATION_HASH_POLICY_ID = "mr1-canonical-symbol-set-sha256-v1"
MR1_MATCHED_K_SELECTION_SCHEMA_VERSION = "mr-1-matched-k-selection-evidence-v1"
MR1_SELECTION_EVIDENCE_SCHEMA_VERSION = MR1_MATCHED_K_SELECTION_SCHEMA_VERSION
MR1_RANKING_POPULATION_VALIDATION_RULE_ID = "mr1-eligible-contiguous-rank-validation-v1"

MR2B_F2A_RUN_SCHEMA = ArtifactSchema(
    schema_version="mr-2b-f2a-run-v2",
    required_files=frozenset(
        {
            "manifest.json",
            "seed_config.json",
            "auxiliary_watchlist_context.parquet",
            "auxiliary_watchlist_context_symbol_evidence.parquet",
            "multi_seed_matched_k_selections.parquet",
            "multi_seed_matched_k_returns.parquet",
            "multi_seed_null_summary.parquet",
            "daily_candidate_excess.parquet",
            "primary_seed_reconciliation.json",
            "primary_comparison_input.json",
            "coverage.json",
            "limitations.json",
            "report.md",
            "SHA256SUMS.json",
        }
    ),
    required_manifest_keys=frozenset(
        {
            "schema_version",
            "run_id",
            "dataset_id",
            "mr1_run_id",
            "data_eligibility",
            "required_artifacts",
            "run_identity",
            "seed_set_id",
            "seed_count",
            "primary_seed",
            "top_k",
            "model_count",
            "decision_date_count",
            "row_counts",
        }
    ),
)

MR2B_CONTEXT_PRIMARY_KEY = ("decision_date",)
MR2B_CONTEXT_SYMBOL_EVIDENCE_PRIMARY_KEY = ("decision_date", "symbol")
MR2B_MULTISEED_SELECTION_PRIMARY_KEY = ("decision_date", "model_id", "seed", "slot_index")
MR2B_MULTISEED_RETURN_PRIMARY_KEY = (
    "decision_date",
    "model_id",
    "exit_time",
    "cost_scenario",
    "seed",
)
MR2B_NULL_SUMMARY_PRIMARY_KEY = ("decision_date", "model_id", "exit_time", "cost_scenario")
MR2B_DAILY_EXCESS_PRIMARY_KEY = MR2B_NULL_SUMMARY_PRIMARY_KEY


def canonical_identity_hash(payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return f"sha256:{sha256(canonical.encode()).hexdigest()}"


def model_population_hash(
    *,
    dataset_id: str,
    decision_date: date,
    target_id: str,
    symbols: tuple[str, ...],
) -> str:
    """Identify the comparable symbol set; model_id is deliberately not part of set identity."""

    return canonical_identity_hash(
        {
            "schema_version": MR1_MODEL_POPULATION_SCHEMA_VERSION,
            "definition_id": MR1_MODEL_POPULATION_DEFINITION_ID,
            "dataset_id": dataset_id,
            "decision_date": decision_date.isoformat(),
            "target_id": target_id,
            "symbols": list(symbols),
        }
    )


def selected_symbols_hash(symbols: tuple[str, ...]) -> str:
    return canonical_identity_hash(
        {
            "schema_version": MR1_MATCHED_K_SELECTION_SCHEMA_VERSION,
            "symbols": list(symbols),
        }
    )


def matched_k_selection_id(
    *,
    population_hash: str,
    symbols: tuple[str, ...],
    top_k: int,
    seed: int,
) -> str:
    return canonical_identity_hash(
        {
            "schema_version": MR1_MATCHED_K_SELECTION_SCHEMA_VERSION,
            "algorithm_id": MR1_MATCHED_K_ALGORITHM_ID,
            "population_hash": population_hash,
            "selected_symbols_hash": selected_symbols_hash(symbols),
            "top_k": top_k,
            "seed": seed,
        }
    )


@dataclass(frozen=True, slots=True)
class ModelCandidatePopulation:
    dataset_id: str
    decision_date: date
    model_id: str
    target_id: str
    symbols: tuple[str, ...]
    population_size: int
    population_hash: str
    definition_id: str = MR1_MODEL_POPULATION_DEFINITION_ID
    schema_version: str = MR1_MODEL_POPULATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MR1_MODEL_POPULATION_SCHEMA_VERSION:
            raise ValueError("model Candidate Population schema is unsupported")
        if self.definition_id != MR1_MODEL_POPULATION_DEFINITION_ID:
            raise ValueError("model Candidate Population definition is unsupported")
        for label, value in (
            ("dataset_id", self.dataset_id),
            ("model_id", self.model_id),
            ("target_id", self.target_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if not isinstance(self.decision_date, date):
            raise TypeError("decision_date must be a date")
        if tuple(sorted(self.symbols)) != self.symbols or len(self.symbols) != len(set(self.symbols)):
            raise ValueError("model Candidate Population symbols must be canonical and unique")
        if self.population_size != len(self.symbols):
            raise ValueError("model Candidate Population size must match symbols")
        expected = model_population_hash(
            dataset_id=self.dataset_id,
            decision_date=self.decision_date,
            target_id=self.target_id,
            symbols=self.symbols,
        )
        if self.population_hash != expected:
            raise ValueError("model Candidate Population hash does not match canonical payload")


@dataclass(frozen=True, slots=True)
class MatchedKSelection:
    population: ModelCandidatePopulation
    symbols: tuple[str, ...]
    top_k: int
    seed: int
    selection_id: str
    selected_symbols_hash: str
    algorithm_id: str = MR1_MATCHED_K_ALGORITHM_ID
    schema_version: str = MR1_MATCHED_K_SELECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MR1_MATCHED_K_SELECTION_SCHEMA_VERSION:
            raise ValueError("matched-K selection schema is unsupported")
        if self.algorithm_id != MR1_MATCHED_K_ALGORITHM_ID:
            raise ValueError("matched-K selection algorithm is unsupported")
        if self.top_k <= 0 or isinstance(self.top_k, bool):
            raise ValueError("matched-K top_k must be positive")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise TypeError("matched-K seed must be an int")
        if len(self.symbols) != min(self.top_k, self.population.population_size):
            raise ValueError("matched-K selected count must equal min(K, population size)")
        if len(self.symbols) != len(set(self.symbols)) or not set(self.symbols) <= set(
            self.population.symbols
        ):
            raise ValueError("matched-K symbols must be unique members of the model population")
        if self.selected_symbols_hash != selected_symbols_hash(self.symbols):
            raise ValueError("selected symbols hash does not match canonical selection")
        expected = matched_k_selection_id(
            population_hash=self.population.population_hash,
            symbols=self.symbols,
            top_k=self.top_k,
            seed=self.seed,
        )
        if self.selection_id != expected:
            raise ValueError("matched-K selection ID does not match canonical payload")
