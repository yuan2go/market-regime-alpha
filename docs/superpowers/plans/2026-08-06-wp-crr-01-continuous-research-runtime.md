# WP-CRR-01 Continuous Research Runtime Implementation Plan

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Executable TDD plan for approved WP-CRR-01 CRR-01 through CRR-06
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-06
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../specs/2026-08-06-continuous-research-runtime-design.md, ../../audit/WP-CRR-01-CRR-00-Baseline.md
> **Code Evidence:** Planning baseline `origin/main@8de820cd149278bfebbaf18f150a90f36380176d`; completed checklist items require exact-HEAD tests and checkpoint commits

> **For Codex:** Execute this plan in the current isolated worktree in order. Use
> test-driven development for each task and make one dependency-coherent commit
> per CRR phase. Do not touch the original workspace or `.idea/modules.xml`.

**Goal:** Deliver one PostgreSQL-authoritative all-day Continuous Research
Runtime that records provider Attempts separately from valid Evidence, detects
material change, reuses existing research identities, and remains fail-closed
for Entry and all trading writes.

**Architecture:** A new deep application module owns run/tick orchestration and
its PostgreSQL Journal. Provider acquisition and child research remain ports;
production composition adapts existing Daily/FreeData, Feature, Controlled, and
Canonical services rather than copying them. Pure, content-addressed contracts
sit above a PostgreSQL repository whose every mutable operation uses version
CAS plus Lease/fencing checks.

**Tech Stack:** Python 3.12 dataclasses/enums/protocols, existing canonical
hash/Artifact contracts, psycopg 3, PostgreSQL 16, argparse CLI, pytest, Ruff,
mypy, setuptools/uv.

**Design authority:**
`docs/superpowers/specs/2026-08-06-continuous-research-runtime-design.md`

---

## Task 1: CRR-01 decision-window policy and identities

**Files:**

- Create: `src/market_regime_alpha/application/continuous_research/__init__.py`
- Create: `src/market_regime_alpha/application/continuous_research/policy.py`
- Create: `src/market_regime_alpha/application/continuous_research/contracts.py`
- Create: `tests/application/continuous_research/__init__.py`
- Create: `tests/application/continuous_research/test_policy.py`
- Create: `tests/application/continuous_research/test_contracts.py`
- Modify: `pyproject.toml` mypy file list

**Step 1: Write failing policy tests**

Cover aware-time validation, `14:29:59` outside, `14:30:00` inside,
`14:55:00` inside, `14:55:01` outside, lunch/market-close phases, stable policy
hash, tamper rejection, and the fact that no exact 14:55 tick is required.

Run:

```bash
uv run pytest tests/application/continuous_research/test_policy.py -q
```

Expected: FAIL because the CRR package does not exist.

**Step 2: Implement the minimum content-addressed policy**

Add `ContinuousSessionPhase`, `ContinuousRunState`,
`ContinuousDecisionWindowAssessment`, and `ContinuousDecisionWindowPolicy`.
Use `Asia/Shanghai`, canonical hashes, whole-second wall times, sorted
limitations, and additive semantics. Do not import or modify historical target
contracts.

**Step 3: Write failing identity tests**

Cover `ContinuousResearchCommand` and `RuntimeTickCommand` canonical round trip,
sorted unique request scope, aware observation time, stable idempotency keys,
configuration hash sensitivity, and authority-ceiling limitations.

**Step 4: Implement identity contracts and rerun**

Run:

```bash
uv run pytest tests/application/continuous_research/test_policy.py tests/application/continuous_research/test_contracts.py -q
uv run mypy
```

Expected: PASS.

## Task 2: CRR-05 request-scoped Universe and research Orderability contracts

**Files:**

- Create: `src/market_regime_alpha/universe/request_scoped.py`
- Create: `src/market_regime_alpha/universe/orderability.py`
- Create: `tests/universe/test_request_scoped_universe.py`
- Create: `tests/universe/test_orderability.py`
- Modify: `src/market_regime_alpha/universe/__init__.py`
- Modify: `pyproject.toml` mypy file list

**Step 1: Write failing request-scope tests**

Require exact requested/included/excluded partition, excluded-symbol retention,
source Universe Artifact/hash lineage, deterministic identity, tamper rejection,
and literal authority `REQUEST_SCOPED_UNIVERSE`.

**Step 2: Implement the immutable view and Reader**

Build only a verified reference/view over current Universe facts. Do not add a
second universe membership provider or any Dynamic Stock Pool behavior.

**Step 3: Write failing Orderability tests**

Require `ORDERABILITY_UNKNOWN` for every missing authority among suspension,
limit state, valid price, board rule, lot size, auction phase, and liquidity.
Require explicit negative evidence to yield `NOT_ORDERABLE`; allow
`ORDERABLE_FOR_RESEARCH` only when all configured research facts are present.

**Step 4: Implement and verify**

Run:

```bash
uv run pytest tests/universe/test_request_scoped_universe.py tests/universe/test_orderability.py -q
```

Expected: PASS with no execution-domain imports.

## Task 3: CRR-02 migration 020 and schema inventory

**Files:**

- Create: `src/market_regime_alpha/persistence/postgres/migrations/020_continuous_research_runtime.sql`
- Modify: `src/market_regime_alpha/persistence/postgres/schema.py`
- Modify: `tests/persistence/postgres/test_schema.py`
- Modify: `tests/persistence/postgres/test_migrator.py`
- Create: `tests/persistence/postgres/test_continuous_research_schema.py`

**Step 1: Write failing migration/schema tests**

Assert migration versions `001..020`, the exact new table inventory, checks,
foreign keys, indexes, immutable-history triggers, allowed statuses, and
`CONTINUOUS_RESEARCH` binding scope.

Run with a disposable PostgreSQL cluster:

```bash
MARKET_REGIME_ALPHA_TEST_DATABASE_URL="$CRR_TEST_DATABASE_URL" \
  uv run pytest tests/persistence/postgres/test_migrator.py \
  tests/persistence/postgres/test_schema.py \
  tests/persistence/postgres/test_continuous_research_schema.py -q
```

Expected: FAIL before migration 020 exists.

**Step 2: Implement migration 020**

Create the eight tables from the design, constraint names, append-only guards,
terminal immutability, current-pointer monotonic update guard, claim indexes,
and binding-scope extension. Keep 001–019 byte-identical.

**Step 3: Update exact schema inventory and verify fresh migration**

Use a new database/schema, run apply-all, then verify-only. Record the new exact
migration and table counts.

**Step 4: Run PostgreSQL migration tests**

Expected: PASS, including concurrent migrator serialization.

## Task 4: CRR-02 Journal domain port and snapshots

**Files:**

- Create: `src/market_regime_alpha/application/continuous_research/journal.py`
- Create: `tests/application/continuous_research/test_journal_contract.py`
- Modify: `pyproject.toml` mypy file list

**Step 1: Write failing repository-contract tests**

Specify run/tick snapshots, attempt/evidence/change/child/event records, claim
and completion receipts, duplicate-load behavior, identity conflict, stale
version, stale fence, and terminal immutability.

**Step 2: Implement types and Protocol only**

Define narrow atomic methods; do not expose raw SQL or generic save/update
methods. Separate immutable history from mutable projections.

**Step 3: Add deterministic receipt helpers and verify**

Run:

```bash
uv run pytest tests/application/continuous_research/test_journal_contract.py -q
uv run mypy
```

Expected: PASS.

## Task 5: CRR-02 PostgreSQL run/tick Claim, Lease, fencing, CAS, recovery

**Files:**

- Create: `src/market_regime_alpha/application/continuous_research/postgres_journal.py`
- Create: `tests/persistence/postgres/test_continuous_research_journal.py`
- Create: `tests/persistence/postgres/test_continuous_research_concurrency.py`
- Modify: `src/market_regime_alpha/persistence/repository_factory.py`
- Modify: `tests/persistence/test_repository_factory.py`

**Step 1: Write failing parity tests**

Cover create/load, duplicate tick admission, identity conflict, one-claim
winner, heartbeat, expiry/reclaim, monotonic fencing epoch, stale writer
rejection, terminal receipt, restart snapshot, and no SQLite writer.

**Step 2: Implement run/tick operations**

Use the shared `PostgresConnectionFactory`, short transactions, row-level
locking, `FOR UPDATE SKIP LOCKED` for claims, explicit version predicates, and
bounded retry only through existing transaction retry semantics.

**Step 3: Write and implement recovery tests**

Recover only expired non-terminal ticks; preserve attempt history; never delete
or rewrite receipts/events.

**Step 4: Run focused PostgreSQL tests**

```bash
MARKET_REGIME_ALPHA_TEST_DATABASE_URL="$CRR_TEST_DATABASE_URL" \
  uv run pytest tests/persistence/postgres/test_continuous_research_journal.py \
  tests/persistence/postgres/test_continuous_research_concurrency.py \
  tests/persistence/test_repository_factory.py -q
```

Expected: PASS.

## Task 6: CRR-03 Provider Attempt and Evidence isolation

**Files:**

- Create: `src/market_regime_alpha/application/continuous_research/evidence.py`
- Create: `tests/application/continuous_research/test_evidence.py`
- Extend: `src/market_regime_alpha/application/continuous_research/postgres_journal.py`
- Create: `tests/persistence/postgres/test_continuous_evidence_isolation.py`

**Step 1: Write failing pure contract tests**

Cover all Attempt terminal statuses, successful validation, Evidence identity,
SourceManifest/input lineage, and rejection of Evidence for a non-successful or
unvalidated Attempt.

**Step 2: Implement Attempt/Evidence types**

Keep raw transport outcome separate from research-consumable Evidence.

**Step 3: Write failing PostgreSQL isolation tests**

Commit initial Evidence, then record failed, timeout, invalid, rate-limit, and
circuit-open Attempts. Assert current Evidence ID/hash/version remain exactly
unchanged and readable after restart.

**Step 4: Implement transactional commit/CAS**

Record Evidence Commit plus current-pointer CAS atomically under the active
fence. Reject cross-run/scope commits and stale fences.

**Step 5: Run focused tests**

Expected: PASS, with no provider failure capable of changing current Evidence.

## Task 7: CRR-04 material hash and `NO_MATERIAL_CHANGE`

**Files:**

- Create: `src/market_regime_alpha/application/continuous_research/change_detection.py`
- Create: `tests/application/continuous_research/test_change_detection.py`
- Extend: `src/market_regime_alpha/application/continuous_research/postgres_journal.py`
- Create: `tests/persistence/postgres/test_continuous_change_decision.py`

**Step 1: Write failing hash tests**

Prove raw/normalized content, SourceManifest semantics, request scope, as-of,
and relevant config versions affect material identity. Prove retrieved-at,
attempt ID, retry count, and Lease metadata do not.

**Step 2: Implement canonical material identity**

Return `INITIAL_EVIDENCE`, `MATERIAL_CHANGE`, `NO_MATERIAL_CHANGE`, or
`DATA_INSUFFICIENT` with deterministic reasons and identity.

**Step 3: Persist append-only decisions**

Enforce one semantic decision per tick and exact prior/current commit lineage.

**Step 4: Verify**

Expected: PASS and deterministic replay.

## Task 8: CRR-04 child lineage and identity reuse

**Files:**

- Create: `src/market_regime_alpha/application/continuous_research/children.py`
- Create: `tests/application/continuous_research/test_children.py`
- Extend: `src/market_regime_alpha/application/continuous_research/postgres_journal.py`
- Create: `tests/persistence/postgres/test_continuous_child_lineage.py`

**Step 1: Write failing lineage tests**

Require trading date, run/tick/Attempt/Manifest/Evidence/decision, sorted input
Artifact set, aggregate input hash, every relevant configuration version,
existing child run/receipt ID/hash, and `CREATED` versus `REUSED` disposition.

**Step 2: Implement content-addressed child references**

No child computation is implemented here. The module verifies and records
references to existing child receipts.

**Step 3: Prove no-change reuse**

Use counting child ports: an identical second tick records reuse and makes zero
Dataset/Feature/Controlled/Canonical calls.

**Step 4: Verify PostgreSQL restart/replay**

Expected: complete traceability for created and reused identities.

## Task 9: CRR-05 Eligibility basis integration

**Files:**

- Create: `src/market_regime_alpha/application/continuous_research/scope.py`
- Create: `tests/application/continuous_research/test_scope.py`
- Reuse: `src/market_regime_alpha/universe/eligibility_policy.py`
- Reuse: `src/market_regime_alpha/universe/eligibility_artifacts.py`

**Step 1: Write failing adapter tests**

Require CRR scope preparation to call existing eligibility policy/artifact
contracts, retain all excluded rows, propagate missing Evidence, and attach the
request-scoped Universe identity.

**Step 2: Implement the thin adapter**

Do not add Candidate scoring, complete-PIT claims, or Dynamic Pool behavior.

**Step 3: Verify fail-closed Orderability**

Expected: free-data fixtures without formal suspension/limit authority remain
`ORDERABILITY_UNKNOWN`.

## Task 10: CRR-06 bounded Runner and failure recovery

**Files:**

- Create: `src/market_regime_alpha/application/continuous_research/ports.py`
- Create: `src/market_regime_alpha/application/continuous_research/runner.py`
- Create: `tests/application/continuous_research/test_runner.py`
- Create: `tests/application/continuous_research/test_runner_recovery.py`

**Step 1: Write first-Evidence Runner test**

Prepare run, admit/claim one tick, call a scripted provider port, record
Attempt/Evidence/initial change, invoke child port once, record lineage, and
complete a receipt.

**Step 2: Implement the minimum Runner**

One method executes one bounded tick. Inject clock/provider/child ports. Every
write passes claim ID and fence.

**Step 3: Add failure/no-change/change tests**

Prove provider failure preserves Evidence, no-change avoids children, material
change invokes children once, child blocked is fail-closed, and window state is
operational only.

**Step 4: Add crash-boundary recovery tests**

Crash after Attempt, Evidence CAS, Change Decision, child receipt, and CRR child
reference. Resume from the first missing durable boundary without duplicate
publication or child execution.

**Step 5: Verify focused suite**

Expected: PASS.

## Task 11: CRR-06 existing-service composition

**Files:**

- Create: `src/market_regime_alpha/application/continuous_research/composition.py`
- Create: `tests/application/continuous_research/test_composition.py`
- Reuse: `src/market_regime_alpha/application/free_data_operation/service.py`
- Reuse: `src/market_regime_alpha/application/daily_loop/runner.py`
- Reuse: `src/market_regime_alpha/features/materialization_run.py`
- Reuse: `src/market_regime_alpha/application/controlled_operation/runner.py`
- Reuse: `src/market_regime_alpha/application/canonical_lifecycle/runner.py`

**Step 1: Write architecture tests**

Patch/count existing service boundaries and assert CRR delegates through them.
Assert there is no CRR provider/dataset/feature/candidate/signal/forecast
implementation and no execution/Broker import.

**Step 2: Implement thin adapters**

Translate validated existing FreeData/Daily receipts into Provider
Attempt/Evidence inputs; translate a material-change command into existing
Feature/Controlled/Canonical service calls. Preserve their exact command,
Target, Reader, and Entry-blocker semantics.

**Step 3: Prove authority ceiling**

Run one recorded engineering-fixture path and assert Entry is blocked and no
Opportunity/Order/Fill/Position repository is called.

## Task 12: CRR-06 CLI, report, and replay

**Files:**

- Create: `src/market_regime_alpha/cli/continuous_research.py`
- Create: `src/market_regime_alpha/application/continuous_research/report.py`
- Create: `src/market_regime_alpha/application/continuous_research/replay.py`
- Create: `tests/cli/test_continuous_research_cli.py`
- Create: `tests/application/continuous_research/test_replay.py`
- Modify: `pyproject.toml` project scripts and mypy file list

**Step 1: Write failing CLI tests**

Cover prepare, one tick, resume, report, replay, invalid/no PostgreSQL DSN,
invalid scope/time/config, structured JSON, and credential-free errors.

**Step 2: Implement bounded commands**

Require explicit PostgreSQL authority. Do not connect to a default/unknown
database. Keep report/replay read-only and deterministic.

**Step 3: Verify**

```bash
MARKET_REGIME_ALPHA_TEST_DATABASE_URL="$CRR_TEST_DATABASE_URL" \
  uv run pytest tests/cli/test_continuous_research_cli.py \
  tests/application/continuous_research/test_replay.py -q
```

Expected: PASS.

## Task 13: CRR-01–06 documentation and operational evidence

**Files:**

- Create: `docs/roadmap/work-packages/WP-CRR-01-Continuous-Research-Runtime.md`
- Create: `docs/runbooks/Continuous-Research-Runtime.md`
- Create: `docs/evidence/WP-CRR-01-Acceptance.md`
- Modify: `docs/status/Current-State.md`
- Modify: `docs/status/Capability-Matrix.md`
- Modify: `docs/status/Gap-Register.md` if present
- Modify: `docs/README.md`

**Step 1: Record implemented facts only**

Document unique ownership, configuration, isolated PostgreSQL setup, bounded
tick invocation, crash recovery, Provider/Evidence separation, reuse, lineage,
and exact authority ceiling.

**Step 2: Preserve explicit non-claims**

State that Daily Summary, dynamic pool, stateful Market/Theme/Capital, Manual
Account/Reconciliation, Registry Selector, economic validation, Shadow,
production scheduling, PIT qualification, and trading/Broker authority are not
delivered.

**Step 3: Run docs check**

```bash
uv run python scripts/check_docs_links.py
uv run pytest tests/scripts/test_check_docs_links.py -q
```

Expected: PASS.

## Task 14: Exact-HEAD acceptance

**Files:**

- Update: `docs/evidence/WP-CRR-01-Acceptance.md`

**Step 1: Run focused suites on a new isolated PostgreSQL cluster**

```bash
MARKET_REGIME_ALPHA_TEST_DATABASE_URL="$CRR_TEST_DATABASE_URL" \
  uv run pytest tests/application/continuous_research tests/universe \
  tests/persistence/postgres tests/cli/test_continuous_research_cli.py -q
```

**Step 2: Run repository quality gates**

```bash
uv run python scripts/check_docs_links.py
uv run pytest tests/scripts/test_check_docs_links.py -q
MARKET_REGIME_ALPHA_TEST_DATABASE_URL="$CRR_TEST_DATABASE_URL" uv run pytest
uv run ruff check .
uv run mypy
uv run python -m build
git diff --check
```

**Step 3: Record every result**

Use `PASS`, `FAIL`, `NOT_RUN`, or `BLOCKED`; record collected/passed/failed/
skipped/warnings/duration, PostgreSQL version/schema/migration count/table
count, and exact Git SHA. A later evidence-only commit must not be described as
the tested code SHA without rerunning the bound gates.

**Step 4: Audit forbidden authority**

Search CRR code/imports/tests for Broker/QMT/PTrade/Order/Fill/Position writes,
Opportunity creation, Daily Summary, Dynamic Pool, Shadow, and state-machine
scope creep. Verify existing fixed-14:55 compatibility tests still pass.

**Step 5: Final phase commit**

Before each checkpoint commit:

```bash
git diff --check
git status --short
git diff --cached --check
git diff --cached
```

Commit only intentional CRR files. Do not push, open a PR, merge, or modify the
original workspace unless separately requested.

## Self-review record

- The plan preserves migrations 001–019 and historical fixed-14:55 semantics.
- PostgreSQL is required for CRR writes; no SQLite CRR writer is planned.
- Provider Attempt and valid Evidence are different tables/contracts.
- `NO_MATERIAL_CHANGE` is proven by both call-count and persisted lineage tests.
- Existing child services remain the only computation owners.
- Request scope is not upgraded to complete PIT Universe.
- Orderability fails closed and grants no execution authority.
- Recovery writes are fenced at every durable boundary.
- No Daily Summary, model-state expansion, account work, economic validation,
  Shadow operation, Broker, Fill, or Position mutation is included.
