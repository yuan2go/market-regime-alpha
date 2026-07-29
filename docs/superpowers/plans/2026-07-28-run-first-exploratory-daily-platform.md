# Run-First Exploratory Daily Platform Implementation Plan

> **Status:** ROADMAP  
> **Authority:** Approved execution plan for the Run-First exploratory daily platform  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-28  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../../audit/Run-First-Daily-Platform-Baseline-Audit.md, ../../architecture/decisions/ADR-001-Run-First-Phase-D-Daily-Platform-Boundaries.md, ../../roadmap/work-packages/README.md  
> **Code Evidence:** main@772ecfb09410588b5a406ad900d793a5850e60d5; `src/market_regime_alpha`; `tests`

> **Execution:** follow TDD, complete one work package and commit before starting the next.

## Objective

Deliver a daily, exploratory, recoverable vertical loop:

```text
public Source
-> Source Freeze
-> Quality Gate
-> Universe/Eligibility
-> Feature
-> B0/B1 PredictionRun
-> Recommendation
-> WAIT/REJECT Entry plumbing
-> Phase D Decision Artifact
-> exact MR1 10:30 Outcome
-> DailyReview
```

Every stage preserves `EXPLORATORY` data authority, no formal OOS Alpha claim and no trading
authority.

## Work package A — Baseline audit and ADR

**Files**

- `docs/audit/Run-First-Daily-Platform-Baseline-Audit.md`
- `docs/architecture/decisions/README.md`
- `docs/architecture/decisions/ADR-001-Run-First-Phase-D-Daily-Platform-Boundaries.md`
- this plan
- `docs/README.md`

**Validation**

```bash
python scripts/check_docs_links.py
python -m pytest -q tests/scripts/test_check_docs_links.py
python -m ruff check .
python -m mypy
git diff --check
```

**Commit**

```text
docs: audit run-first daily platform baseline
```

## Work package B — Platform minimum governance fix

### Task B1: write failing lifecycle and type-separation tests

**Files**

- modify `tests/platform/test_platform_kernel.py`

Add tests that:

```python
registry.register(definition)
# returns DRAFT + UNQUALIFIED only

registry.register(
    definition,
    lifecycle_status=ModelLifecycleStatus.ACTIVE,
)
# is a TypeError because register no longer accepts promotion state

registry.restore(valid_historical_registration)
# validates ordered transitions and reconstructs existing state
```

Test `ModelDefinition.supported_data_eligibilities` with
`DataEligibility.EXPLORATORY` and assert EvidenceLevel is not accepted as a data grade.

Run:

```bash
python -m pytest -q tests/platform/test_platform_kernel.py
```

Expected before implementation: FAIL.

### Task B2: separate data eligibility from evidence maturity

**Files**

- modify `src/market_regime_alpha/platform/contracts.py`
- modify current Platform tests and fixtures using `supported_data_grades`

Change the model definition field to:

```python
supported_data_eligibilities: tuple[DataEligibility, ...] = (
    DataEligibility.EXPLORATORY,
)
```

`definition_hash` must bind the new semantic field. EvidenceLevel remains only on
`ModelRegistration` and lifecycle transitions.

### Task B3: harden registration and add validated restore

**Files**

- modify `src/market_regime_alpha/platform/model_registry.py`

`register(definition)` always creates:

```python
ModelRegistration(
    definition=definition,
    lifecycle_status=ModelLifecycleStatus.DRAFT,
    evidence_level=EvidenceLevel.UNQUALIFIED,
)
```

Add a separately named historical API:

```python
def restore(self, registration: ModelRegistration) -> ModelRegistration:
    """Restore a validated historical registration without treating it as new registration."""
```

Validation replays every transition from `DRAFT`, checks from/to continuity, allowed transitions,
required promotion evidence, ACTIVE approval, and monotonic transition times. It rejects state or
evidence summaries that do not equal the replayed result.

Transition data compatibility checks use the ModelDefinition's
`supported_data_eligibilities` only when a run supplies DataEligibility; lifecycle EvidenceLevel
is never compared to a data grade.

### Task B4: include Platform in mypy

**Files**

- modify `pyproject.toml`

Add every current `src/market_regime_alpha/platform/*.py` file explicitly, consistent with the
project's existing mypy style.

### Task B5: validate and commit

```bash
python -m pytest -q tests/platform
python -m pytest -q tests/candidates
python -m ruff check .
python -m mypy
git diff --check
```

Commit:

```text
fix: harden minimum platform governance boundary
```

## Work package C — PredictionRun and B0/B1 equivalence adapter

### Task C1: characterize full existing outputs

**Files**

- add `tests/platform/test_prediction_run.py`
- add `tests/platform/test_b0_b1_prediction_adapter.py`

Build datasets with available values, missing values and score ties. Capture the direct outputs of:

```python
rank_candidates_by_feature(...)
rank_candidates_by_transparent_composite(...)
```

Compare the adapter output over:

```text
population symbols and size
prediction semantic payload
rejection semantic payload
score and rank
symbol tie break
ranking coverage
Target ID
Dataset ID
FeatureDefinition IDs
FeatureMaterialization IDs
```

### Task C2: add immutable PredictionRun

**Files**

- add `src/market_regime_alpha/platform/prediction_run.py`
- add `src/market_regime_alpha/platform/prediction_artifacts.py`
- add `src/market_regime_alpha/platform/prediction_reader.py`
- update `src/market_regime_alpha/platform/__init__.py`

PredictionRun binds all required protocols, source identities, predictions, rejections, coverage,
DataEligibility and EvidenceLevel. `content_hash` is full SHA-256 over canonical semantics;
`prediction_run_id` is derived from that hash. Caller-supplied identity overrides are impossible.

Publisher uses staging, exact file set, checksum and non-overwrite. Reader recomputes identities
and semantic invariants.

### Task C3: add B0/B1 adapter

**Files**

- add `src/market_regime_alpha/platform/candidate_prediction_adapter.py`

Select only the existing `platform-b0-momentum-v1` and `platform-b1-balanced-v1` specs. Invoke the
existing ranking functions and project their complete output; do not recalculate scores.

### Task C4: validate and commit

```bash
python -m pytest -q tests/platform
python -m pytest -q tests/candidates
python -m ruff check .
python -m mypy
git diff --check
```

Commit:

```text
feat: publish protocol-bound candidate prediction runs
```

## Work package D — Runtime Journal and state machine

### Task D1: test identities and transitions

**Files**

- add `tests/application/daily_loop/test_commands.py`
- add `tests/application/daily_loop/test_state.py`
- add `tests/application/daily_loop/test_sqlite_repository.py`

Test deterministic RunRequestId, post-freeze DailyRunId, legal transitions, terminal
`DATA_BLOCKED`, duplicate request reuse, immutable request primary key, restart recovery and
compare-and-set conflict.

### Task D2: implement application kernel

**Files**

- add `src/market_regime_alpha/application/__init__.py`
- add `src/market_regime_alpha/application/daily_loop/__init__.py`
- add `commands.py`, `state.py`, `repositories.py`, `sqlite_repository.py`, `errors.py`

The SQLite schema uses `run_request_id TEXT PRIMARY KEY` and a nullable unique `daily_run_id`.
Stage receipts bind input/output Artifact IDs. Repository APIs are Protocols; SQLite is one
implementation.

### Task D3: validate and commit

```bash
python -m pytest -q tests/application/daily_loop
python -m ruff check .
python -m mypy
git diff --check
```

Commit:

```text
feat: add recoverable daily run kernel
```

## Work package E — Public Provider, SourceManifest and Quality Gate

### Task E1: test strict profiles and field evidence

**Files**

- add `tests/data/providers/public_composite/test_profiles.py`
- add `tests/data/test_source_manifest.py`
- add `tests/data/test_daily_quality_gate.py`

Test that LIVE never invokes a local reader, REPLAY never invokes a network client, raw payload
hashes verify, later-than-decision availability blocks, missing critical facts block and source
conflicts are explicit.

### Task E2: implement data contracts

**Files**

- add `src/market_regime_alpha/data/source_manifest.py`
- add `src/market_regime_alpha/data/daily_quality.py`
- add `src/market_regime_alpha/data/content_store.py`

Each Source field retains provider, source Artifact, event/available/retrieved/decision times,
unit, adjustment, finality, eligibility, status and reasons. The gate is fail-closed.

### Task E3: implement profiles

**Files**

- add `src/market_regime_alpha/data/providers/__init__.py`
- add `src/market_regime_alpha/data/providers/public_composite/__init__.py`
- add `contracts.py`, `live.py`, `replay.py`, `router.py`

Provider results contain archived raw payloads and normalized records only. No Candidate or Entry
imports are allowed.

### Task E4: validate and commit

```bash
python -m pytest -q tests/data
python -m pytest -q tests/data/providers/public_composite
python -m ruff check .
python -m mypy
git diff --check
```

Commit:

```text
feat: add public provider source manifest and quality gate
```

## Work package F — Smoke Universe and Feature pipeline

### Task F1: test reason-complete reconciliation

**Files**

- add `tests/universe/test_daily_smoke_policy.py`
- add `tests/application/daily_loop/test_feature_pipeline.py`

Test the fixed 20 symbols, policy identity, A-share-only enforcement, every-symbol reconciliation,
unknown ST blocking/exclusion, stale quote, missing history and deterministic Feature lineage.

### Task F2: implement adapters

**Files**

- add `src/market_regime_alpha/universe/daily_policy.py`
- add `src/market_regime_alpha/application/daily_loop/pipeline.py`

Reuse canonical Universe/Eligibility and R5 baseline Feature contracts. Do not silently delete a
symbol or use current status to backfill history.

### Task F3: validate and commit

```bash
python -m pytest -q tests/universe
python -m pytest -q tests/application/daily_loop
python -m pytest -q tests/candidates
python -m ruff check .
python -m mypy
git diff --check
```

Commit:

```text
feat: add smoke universe and daily feature pipeline
```

## Work package G — Recommendation and Entry plumbing

### Task G1: add fail-closed tests

**Files**

- add `tests/candidates/test_daily_recommendation.py`
- add `tests/strategies/entry/test_plumbing_gate.py`

Test separate B0/B1 Top-5 projections, complete lineage, no action fields, WAIT/REJECT rules,
Decision Price Snapshot binding and absence of price/size/order fields.

### Task G2: implement domain projections

**Files**

- add `src/market_regime_alpha/candidates/recommendation.py`
- add `src/market_regime_alpha/strategies/entry/plumbing_gate.py`

Recommendation never contains BUY/SELL/ENTER. Entry plumbing never contains `ENTER`.

### Task G3: validate and commit

```bash
python -m pytest -q tests/candidates
python -m pytest -q tests/strategies/entry
python -m ruff check .
python -m mypy
git diff --check
```

Commit:

```text
feat: add recommendation and entry plumbing projections
```

## Work package H — Phase D Artifact, Reader and Replay

### Task H1: test exact publication and routing

**Files**

- add `tests/daily_decision/test_artifacts.py`
- add `tests/daily_decision/test_reader.py`
- add `tests/daily_decision/test_reader_registry.py`
- add `tests/application/daily_loop/test_replay.py`

Test exact files, staged rename, non-overwrite, checksum, semantic tampering, report reconstruction,
V1 routing, Phase D routing, successful replay hash equality and DATA_BLOCKED empty downstream
collections.

### Task H2: implement Phase D package

**Files**

- add `src/market_regime_alpha/daily_decision/__init__.py`
- add `contracts.py`, `artifacts.py`, `reader.py`, `reader_registry.py`, `report.py`
- add `src/market_regime_alpha/application/daily_loop/runner.py`
- add `src/market_regime_alpha/application/daily_loop/replay.py`

The Phase D exact file set is independent from V1 and includes the required Source, Quality,
Universe, Eligibility, Feature, Prediction, Recommendation, Entry, report and checksum records.

### Task H3: validate and commit

```bash
python -m pytest -q tests/daily_research
python -m pytest -q tests/daily_decision
python -m pytest -q tests/application/daily_loop
python -m ruff check .
python -m mypy
git diff --check
```

Commit:

```text
feat: add phase d daily artifact reader and replay
```

## Work package I — MR1 10:30 Outcome and DailyReview

### Task I1: characterize the sole Target

**Files**

- add `tests/daily_decision/test_mr1_outcome_adapter.py`
- add `tests/daily_decision/test_review.py`

Assert the Target ID equals `MR1TargetId.NEXT_SESSION_1030_RETURN.value`, requires the exact 10:30
bar, never substitutes close, preserves unresolved outcomes and does not modify T-day bytes.

### Task I2: implement settlement

**Files**

- add `src/market_regime_alpha/daily_decision/mr1_outcome_adapter.py`
- add `src/market_regime_alpha/daily_decision/outcomes.py`
- add `src/market_regime_alpha/daily_decision/review.py`
- add `src/market_regime_alpha/application/daily_loop/settlement.py`

Outcome/Review publication is an immutable successor package binding the T-day Decision Artifact.

### Task I3: validate and commit

```bash
python -m pytest -q tests/daily_decision
python -m pytest -q tests/research/test_mr1_morning_pop.py
python -m ruff check .
python -m mypy
git diff --check
```

Commit:

```text
feat: add mr1 1030 outcome and daily review flow
```

## Work package J — Replay, live dry run and CLI evidence

### Task J1: implement CLI and fixtures

**Files**

- add `scripts/run_exploratory_daily_loop.py`
- add `tests/application/daily_loop/test_cli.py`
- add `tests/application/daily_loop/test_ten_session_replay.py`
- add versioned test fixtures under `tests/fixtures/daily_loop`

Commands:

```text
run --decision-date ... --provider-profile public-composite-live-v1
replay --run-id ...
settle --run-id ...
report --run-id ...
```

### Task J2: execute operational acceptance

Run a one-session 20-symbol Replay twice, a ten-session Replay, settlement when available and a
LIVE dry run. If public acquisition is unavailable, preserve a verified DATA_BLOCKED Artifact.

### Task J3: full validation

```bash
python scripts/check_docs_links.py
python -m pytest -q tests/platform
python -m pytest -q tests/application
python -m pytest -q tests/data
python -m pytest -q tests/universe
python -m pytest -q tests/candidates
python -m pytest -q
python -m ruff check .
python -m mypy
python -m pip check
git diff --check
```

Commit test evidence and then delivery documentation separately:

```text
test: add ten-session replay and recovery evidence
docs: record run-first daily platform delivery
```

## Final authority statement

Successful completion means only:

```text
EXPLORATORY_DAILY_LOOP_OPERATIONAL
FORMAL_OOS_ALPHA_NOT_ESTABLISHED
TRADING_AUTHORITY_NOT_GRANTED
```
