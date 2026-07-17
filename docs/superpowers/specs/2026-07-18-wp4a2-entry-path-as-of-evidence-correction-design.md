# WP-4A.2 Entry Path As-Of Evidence Correction Design

> **Date:** 2026-07-18
> **Status:** APPROVED DESIGN
> **Authority:** Bounded WP-4A.2 design under `AGENTS.md`, the Constitution, and the Entry/Lifecycle/Exit research program.

## Purpose

WP-4A.2 corrects as-of semantics in Entry Path materialization. It separates stable absence readiness from observed Dataset coverage, prevents unavailable future coverage from influencing current artifacts, and lets finalized direct bar/suspension evidence resolve a path without waiting for absence controls. It remains REHEARSAL-only Target infrastructure and does not create an Entry Gate, Entry Proposal, Entry model, Candidate change, WP-3 runner/artifact change, Portfolio decision, or Execution action.

## Data Ownership

The Data domain replaces mixed `RehearsalFuturePathEvidenceCompleteness` with two provider-neutral contracts.

`RehearsalFuturePathReadinessPolicy` contains `source_dataset_id`, `policy_convention`, `effective_at`, `session_readiness`, and a deterministic `policy_id` over its complete canonical payload. It declares only when absence can be interpreted and has no coverage watermark. Its source Dataset must be declared; `effective_at <= CandidatePopulation.decision_time`; readiness records must exactly cover the horizon in chronological, unique order; and each deadline must be at or after that explicit Calendar session close.

`RehearsalFuturePathCoverageAssertion` contains `source_dataset_id`, `available_at`, `coverage_convention`, `covered_symbols`, `coverage_through_session_date`, and a deterministic `evidence_id`. It expresses Dataset coverage progress and is never truncated or recreated per Target horizon. Its watermark must be an explicit current Trading Calendar session, may be before, inside, or after the current Target horizon, and its `available_at` must be at or after that watermark session close. Covered symbols must exactly equal the Candidate Population.

## As-Of Input Boundary

The materializer accepts:

```python
future_path_readiness_policy: RehearsalFuturePathReadinessPolicy
future_path_coverage_assertion: RehearsalFuturePathCoverageAssertion | None
```

An unavailable coverage assertion is not passed as a future object to be partly ignored: the caller passes `None`. Core validation fail-closes rather than filtering future input:

```text
bar.available_at > materialized_at                 -> structural error
suspension.available_at > materialized_at          -> structural error
coverage.available_at > materialized_at            -> structural error
readiness_policy.effective_at > Decision Time      -> structural error
```

Readiness policy, present coverage assertion, future bars, and future suspensions must have the same Dataset identity. Entry reference evidence may use a distinct Dataset, but it must be declared in the top-level source set and continue to match the Target and bar adjustment basis.

## Evaluation Order

For every unresolved exchange session:

```text
1. materialized_at < session_close
   -> NOT_YET_OBSERVED / HORIZON_NOT_COMPLETE

2. finalized, as-of available daily bar exists
   -> consume and classify immediately

3. confirmed, as-of available suspension exists
   -> consume immediately and continue

4. neither direct evidence exists
   materialized_at < readiness deadline
   -> NOT_YET_OBSERVED / EVIDENCE_NOT_YET_AVAILABLE

   coverage assertion is None or does not cover the session
   -> NOT_YET_OBSERVED / EVIDENCE_COVERAGE_NOT_COMPLETE

   coverage assertion covers the session
   -> MISSING / FUTURE_DAILY_BAR_MISSING
      observed_at = coverage assertion available_at
```

Readiness controls only absent direct evidence. It never delays a validated bar or confirmed suspension. Coverage is read only after direct evidence is absent and readiness elapsed.

## Schema and Identity

Current V1 has no explicit evidence contract for a reference-unavailable fact. This version removes `INVALID` and `ENTRY_REFERENCE_MISSING`; legal statuses are only `AVAILABLE`, `AMBIGUOUS`, `MISSING`, and `NOT_YET_OBSERVED`. A future provider-backed unavailable-reference evidence contract must use a new Observation schema version before it can introduce another state.

`ENTRY_PATH_TARGET_SCHEMA_VERSION` remains `entry-path-target-v1`, because the barrier/path truth function is unchanged. Observation gains `ENTRY_PATH_OBSERVATION_SCHEMA_VERSION = "entry-path-observation-v2"`; every observation stores, validates, and serializes it. Materialization artifact payloads use `entry-path-materialization-v2`.

`EntryPathTargetMaterialization` stores `readiness_policy_id`, `consumed_coverage_assertion_id: ArtifactId | None`, entry reference IDs, consumed bar IDs, and consumed suspension IDs. The policy ID always contributes to identity. A coverage ID contributes only if at least one symbol/session reached the absent-evidence coverage branch with an assertion; direct evidence-only and `None`-coverage paths retain `None`. Future coverage cannot be passed and cannot alter identity. Evidence-ID tuples use canonical sorted order, and reference-ID count equals observation count.

## Delivery and CI

TDD tests cover future coverage exclusion, watermark Calendar/finality validation, bar/suspension precedence over readiness, every absence branch, consumed identity behavior, policy identity sensitivity, reference-ID cardinality, canonical ordering, and retained barrier classification. Domain semantics and documentation form one commit. A subsequent pure formatting commit reformats `materialization.py` long signatures, calls, and returns only. The CI workflow gains `workflow_dispatch` in a separate CI-only commit. `gh` is unauthenticated, so status may only be: CI workflow implemented; remote CI result not verified, unless a real successful remote Actions run is observed.
