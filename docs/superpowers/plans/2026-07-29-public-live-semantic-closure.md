# Public LIVE Semantic Closure Implementation Plan

> **Status:** ROADMAP
> **Authority:** Approved execution plan for public LIVE semantic closure
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-07-29
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../../audit/Run-First-Daily-Platform-Delivery.md, ../../status/Current-State.md, ../../roadmap/work-packages/WP-D2E-Tencent-Exploratory-Daily-Loop.md
> **Code Evidence:** main@f99f6330192f410cde47234f2fc519818d269d76; `src/market_regime_alpha`; `tests`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the fixed 20-symbol public-data LIVE path semantically honest and capable of reaching `OUTCOME_PENDING` from a verified archive when every required public fact is present, while preserving fail-closed behavior when it is not.

**Architecture:** Keep Provider acquisition, Source facts, Universe policy, per-symbol eligibility and application orchestration separate. Publish protocol/policy evidence and two content-addressed acquisition-stage Artifacts, then freeze one versioned SourceManifest whose identity binds both stages. Admit prior BaoStock daily bars only through an explicit exploratory retrieval policy; keep unknown status explicit and exclude that symbol instead of asserting it trades.

**Tech Stack:** Python 3.12, frozen dataclasses, Protocol, SQLite, immutable JSON Artifacts, SHA-256 identities, pytest, mypy, Ruff.

## Global Constraints

- Scope remains the existing fixed 20-symbol Smoke Pool; Operational Pool 100–300 is forbidden.
- LIVE uses BaoStock and Tencent only and never falls back to a local Archive.
- REPLAY reads a caller-selected immutable Archive and never calls a network client.
- `MR1TargetId.NEXT_SESSION_1030_RETURN` remains the sole next-session 10:30 Target identity.
- B0/B1 formulas, weights, ranking and tie breaking remain unchanged.
- Historical `daily_research` V1 and existing Phase D v1 Artifacts remain readable with unchanged identities.
- Unknown facts stay unknown; no invented Provider Available Time, trading status or Formal PIT.
- Entry plumbing emits only `WAIT_CONFIRMATION` or `REJECT`, never `ENTER`.
- All delivered data remains `DataEligibility.EXPLORATORY`.
- No broker, position, portfolio, Xuntou, UI or automated trading work enters this plan.

---

### Task 1: Version protocol and policy Source facts

**Files:**
- Modify: `src/market_regime_alpha/data/source_manifest.py`
- Modify: `src/market_regime_alpha/data/providers/public_composite/manifest_builder.py`
- Modify: `src/market_regime_alpha/universe/daily_exploratory.py`
- Modify: `src/market_regime_alpha/application/daily_loop/runner.py`
- Test: `tests/data/test_source_manifest_and_quality.py`
- Test: `tests/data/test_public_composite_provider.py`
- Test: `tests/universe/test_daily_exploratory.py`

**Interfaces:**
- Produces: `SourceAuthorityKind`, v2 `SourceManifestField` values, and policy-bound membership/eligibility declarations.
- Preserves: v1 field/manifest serialization and identity when reading an existing v1 payload.

- [ ] **Step 1: Write failing protocol-fact and policy-lineage tests**

Add tests named:

```python
test_decision_time_is_protocol_fact
test_decision_time_not_blocked_by_late_runtime_retrieval
test_smoke_pool_membership_has_policy_lineage
test_membership_does_not_claim_provider_authority
test_missing_membership_policy_blocks_run
test_reader_rejects_tampered_policy_membership
```

The assertions require protocol/policy Provider IDs, policy content hash, explicit boolean membership, v2 routing and unchanged v1 reconstruction.

- [ ] **Step 2: Run focused tests and observe failures**

Run:

```bash
python -m pytest -q tests/data/test_source_manifest_and_quality.py tests/data/test_public_composite_provider.py tests/universe/test_daily_exploratory.py
```

Expected: failures for absent protocol/policy authority and absent v2 values.

- [ ] **Step 3: Implement minimal v2 contracts**

Implement:

```python
class SourceAuthorityKind(str, Enum):
    PROVIDER = "PROVIDER"
    PROTOCOL = "PROTOCOL"
    UNIVERSE_POLICY = "UNIVERSE_POLICY"
    ELIGIBILITY_POLICY = "ELIGIBILITY_POLICY"
```

Add v2-only `authority_kind` and canonical scalar `value` fields while keeping v1 serialization byte-compatible. Build immutable protocol and `smoke_pool_policy_v1` payloads as archived source evidence. Decision Time uses `DailyRunCommand.decision_time`; policy membership uses the policy ID/hash and never Tencent/BaoStock authority.

- [ ] **Step 4: Run focused tests, Ruff, mypy and diff check**

Run:

```bash
python -m pytest -q tests/data/test_source_manifest_and_quality.py tests/data/test_public_composite_provider.py tests/universe/test_daily_exploratory.py
python -m ruff check src tests scripts
python -m mypy
git diff --check
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/market_regime_alpha/data src/market_regime_alpha/universe src/market_regime_alpha/application tests/data tests/universe
git commit -m "refactor: separate protocol and provider source facts"
```

### Task 2: Add exploratory BaoStock daily-history semantics

**Files:**
- Modify: `src/market_regime_alpha/data/providers/public_composite/contracts.py`
- Modify: `src/market_regime_alpha/data/providers/public_composite/live_clients.py`
- Modify: `src/market_regime_alpha/data/providers/public_composite/manifest_builder.py`
- Modify: `src/market_regime_alpha/features/daily_pipeline.py`
- Test: `tests/data/test_public_composite_provider.py`
- Test: `tests/data/test_source_manifest_and_quality.py`
- Test: `tests/features/test_daily_pipeline.py`

**Interfaces:**
- Produces: `HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1`.
- Consumes: BaoStock daily fields `date,open,high,low,close,volume,amount,tradestatus,isST`.
- Guarantees: prior-session daily bars may enter exploratory Features without receiving an invented Provider Available Time.

- [ ] **Step 1: Write failing history-semantics and Feature tests**

Add:

```python
test_history_semantics_remain_exploratory
test_history_window_uses_versioned_public_semantics
test_public_daily_history_materializes_r5_features
test_daily_history_and_decision_quote_are_temporally_separated
test_feature_values_match_frozen_fixture_baseline
```

Assert that same-day daily OHLC is not used as a 14:55 price, prior bars retain `available_time=None`, the Manifest limitation is explicit, and the four existing Feature values match the frozen baseline.

- [ ] **Step 2: Run focused tests and observe failures**

Run:

```bash
python -m pytest -q tests/data/test_public_composite_provider.py tests/data/test_source_manifest_and_quality.py tests/features/test_daily_pipeline.py
```

Expected: current 5-minute/UNKNOWN semantics cannot materialize the daily Features.

- [ ] **Step 3: Implement the daily product and admission policy**

Change the LIVE history query to daily unadjusted BaoStock rows. Retain `tradestatus` and `isST` as separate normalized status inputs. For prior completed sessions:

```text
Provider available_time = None
Provider finality = UNKNOWN
admission policy = HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1
data eligibility = EXPLORATORY
```

The Feature adapter may assign the protocol Decision Time only as its internal exploratory admission time; it must not rewrite the Provider fact.

- [ ] **Step 4: Prove B0/B1 equivalence**

Run existing and new equivalence tests:

```bash
python -m pytest -q tests/features tests/platform/test_prediction_run.py
```

Assert Feature values, B0/B1 scores, ranks, tie breaks, Top-5 and declared identity-version effects.

- [ ] **Step 5: Run static checks and commit**

```bash
python -m ruff check src tests scripts
python -m mypy
git diff --check
git add src/market_regime_alpha/data src/market_regime_alpha/features tests/data tests/features tests/platform
git commit -m "feat: add exploratory public daily history semantics"
```

### Task 3: Freeze history and quote acquisition separately

**Files:**
- Create: `src/market_regime_alpha/data/providers/public_composite/stage_artifact.py`
- Modify: `src/market_regime_alpha/data/providers/public_composite/profiles.py`
- Modify: `src/market_regime_alpha/application/daily_loop/repositories.py`
- Modify: `src/market_regime_alpha/application/daily_loop/sqlite_repository.py`
- Modify: `src/market_regime_alpha/application/daily_loop/runner.py`
- Test: `tests/data/test_public_composite_provider.py`
- Test: `tests/application/daily_loop/test_runtime_journal.py`
- Test: `tests/application/daily_loop/test_runner.py`

**Interfaces:**
- Produces: `SourceAcquisitionStage.HISTORY_SOURCE_FROZEN` and `DECISION_QUOTE_SOURCE_FROZEN`.
- Produces: an exact-file-set content-addressed batch Artifact and semantic Reader.
- Persists: immutable substage receipts keyed by `RunRequestId`, without changing the Runtime Journal primary key.

- [ ] **Step 1: Write failing recovery tests**

Add:

```python
test_history_freeze_is_reused_after_quote_failure
test_daily_run_id_binds_history_and_quote_hashes
test_replay_performs_no_network_calls
test_live_never_uses_local_archive_fallback
```

Use counting fake clients and simulated crashes before/after receipt publication.

- [ ] **Step 2: Run focused tests and observe reacquisition**

```bash
python -m pytest -q tests/application/daily_loop/test_runtime_journal.py tests/application/daily_loop/test_runner.py tests/data/test_public_composite_provider.py
```

Expected: history is currently fetched again after an interrupted acquisition.

- [ ] **Step 3: Implement immutable stage Artifacts and receipts**

Publish each `PublicCompositeBatch` with manifest, payload, exact file set and checksums. Add Protocol methods:

```python
get_acquisition_receipt(run_request_id, stage)
record_acquisition_receipt(run_request_id, stage, artifact_id, content_hash, locator, created_at)
```

The Runner loads and verifies an existing history stage before invoking BaoStock. Quote failure preserves the history receipt and bytes. Final `DailyRunId` binds both stage/source hashes through the final SourceManifest.

- [ ] **Step 4: Run recovery/static tests and commit**

```bash
python -m pytest -q tests/application/daily_loop tests/data
python -m ruff check src tests scripts
python -m mypy
git diff --check
git add src/market_regime_alpha/application src/market_regime_alpha/data tests/application tests/data
git commit -m "refactor: separate history and decision quote acquisition"
```

### Task 4: Split global quality from per-symbol eligibility

**Files:**
- Modify: `src/market_regime_alpha/data/daily_quality.py`
- Modify: `src/market_regime_alpha/universe/daily_exploratory.py`
- Modify: `src/market_regime_alpha/features/daily_pipeline.py`
- Modify: `src/market_regime_alpha/application/daily_loop/runner.py`
- Test: `tests/data/test_source_manifest_and_quality.py`
- Test: `tests/universe/test_daily_exploratory.py`
- Test: `tests/features/test_daily_pipeline.py`
- Test: `tests/application/daily_loop/test_runner.py`

**Interfaces:**
- Produces: global findings for corrupted/unavailable source or policy evidence.
- Produces: per-symbol exclusion reasons for price, freshness, trading status, ST/listing status, history, liquidity and Feature availability.
- Keeps: `MINIMUM_CANDIDATE_POPULATION = 5`.

- [ ] **Step 1: Write failing two-layer-gate tests**

Add:

```python
test_single_symbol_unknown_status_excludes_symbol_not_global_run
test_global_provider_failure_blocks_run
test_insufficient_final_population_blocks_run
test_unknown_trading_status_is_explicit
test_partial_symbol_failure_preserves_remaining_population
```

- [ ] **Step 2: Run focused tests and observe global blocking**

```bash
python -m pytest -q tests/data/test_source_manifest_and_quality.py tests/universe/test_daily_exploratory.py tests/application/daily_loop/test_runner.py
```

- [ ] **Step 3: Implement the two gates**

Protocol/Archive/Policy integrity findings block globally. Per-symbol unknown or insufficient facts create `INELIGIBLE` decisions with explicit reasons. No path converts UNKNOWN to TRADING. After reconciliation, fewer than five eligible symbols publishes a verified `DATA_BLOCKED` Artifact with empty downstream collections.

- [ ] **Step 4: Run bounded-context tests and commit**

```bash
python -m pytest -q tests/application/daily_loop tests/data tests/features tests/universe tests/platform tests/daily_decision
python -m ruff check src tests scripts
python -m mypy
git diff --check
git add src/market_regime_alpha tests
git commit -m "fix: isolate per-symbol eligibility failures"
```

### Task 5: Prove Replay, Artifact and real public-data behavior

**Files:**
- Modify: `tests/application/daily_loop/public_fixture.py`
- Modify: `tests/application/daily_loop/test_runner.py`
- Modify: `tests/daily_decision/test_phase_d_artifact.py`
- Modify: `tests/application/daily_loop/test_cli.py`
- Create: `docs/audit/WP-D3-Public-Live-Semantic-Closure.md`
- Modify: `docs/status/Current-State.md`
- Modify: `docs/status/Capability-Matrix.md`
- Modify: `docs/status/Gap-Register.md`
- Modify: `docs/README.md`

**Interfaces:**
- Produces: Fixture and real Archive runtime evidence with exact IDs/hashes.
- Produces: one honest LIVE result, either `OUTCOME_PENDING` or verified `DATA_BLOCKED`.

- [ ] **Step 1: Add end-to-end tests**

Add:

```python
test_successful_public_replay_reaches_outcome_pending
test_artifact_records_public_history_semantic_limitations
test_reader_rejects_tampered_policy_membership
```

Retain run/replay/settle/report, crash recovery, idempotency, no-network Replay and append-only T+1 assertions.

- [ ] **Step 2: Run focused and full automated validation**

```bash
python -m pytest -q tests/application/daily_loop tests/data tests/features tests/universe tests/platform tests/daily_decision
python -m pytest -q
python -m mypy
python -m ruff check src tests scripts
git diff --check
```

Record exact pass/fail/skip counts.

- [ ] **Step 3: Run and inspect runtime evidence**

Run a fixture Replay through `run/replay/settle/report`. Acquire actual BaoStock/Tencent bytes when the network is available. If quote time is outside the Decision window, publish and replay a verified `DATA_BLOCKED` Artifact rather than changing timestamps. A successful real Archive Replay is required before claiming complete closure.

- [ ] **Step 4: Write fact-bound delivery documentation**

Select exactly one conclusion:

```text
PUBLIC_LIVE_SEMANTIC_CLOSURE_COMPLETE
PUBLIC_LIVE_PARTIALLY_CLOSED
PUBLIC_LIVE_STILL_DATA_BLOCKED
```

Document Source/Manifest/Universe/Feature counts, IDs, hashes, limitations and authority ceiling.

- [ ] **Step 5: Final checks, commit and push**

```bash
python scripts/check_docs_links.py
git status --short
git diff --check
git log --oneline --decorate -10
git add tests docs
git commit -m "docs: record verified wp-d3 delivery state"
git push -u origin feat/public-live-semantic-closure
```
