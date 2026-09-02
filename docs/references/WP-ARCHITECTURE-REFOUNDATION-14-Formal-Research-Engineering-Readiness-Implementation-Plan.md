# WP-14 Formal Research Engineering Readiness Implementation Plan

> **Status:** CURRENT_STATUS
> **Design:** [WP-14 canonical design](WP-ARCHITECTURE-REFOUNDATION-14-Formal-Research-Engineering-Readiness-Design.md)
> **Baseline:** `origin/main@eb7970b4833228a2faba6715c65c26dae88f6ee5`
> **Frozen:** 2026-09-02

## Checkpoint discipline

Implementation proceeds in the dependency order below. Each slice starts with
failing Domain/Application/PostgreSQL tests, ends with a dependency-coherent
commit, and preserves the WP-11 through WP-13 gates. The final engineering
qualification is run only after an exact implementation checkpoint commit.

Any qualification-discovered code change creates a new implementation SHA and
invalidates every affected result. Historical immutable Verification documents
remain read-only.

## Slice 1 — controlled Runtime profiles

1. Add the four due-branch Runtime step kinds to Domain/schema vocabulary.
2. Define pure builders for the exact decision and due proof Step/edge rosters.
3. Extend Domain and deferred PostgreSQL DAG closure for both profiles.
4. Test missing, duplicate, optional, reordered, bypass, and cyclic steps.
5. Prove existing Candidate-to-Context behavior is unchanged.

Focused tests:

```text
tests/refoundation/test_runtime_domain.py
tests/refoundation/test_runtime_postgres.py
tests/refoundation/formal_research/test_runtime_profiles.py
tests/refoundation/formal_research/test_runtime_profiles_postgres.py
```

## Slice 2 — Provider qualification

1. Add Market-owned immutable Protocol/Requirement/FinalityObservation/
   Decision/CaptureMember/RequirementResult domain types.
2. Add a narrow ProviderQualification UoW and PostgreSQL repositories.
3. Extend `001_baseline.sql` with relational roots, complete roster triggers,
   admission evidence ceiling, supersession, append-only guards, and indexes.
4. Implement register protocol, record typed finality observation, complete
   qualification, exact replay, deterministic rejection, bounded transient
   retry, and unknown-commit probe.
5. Derive the complete capture roster and every requirement result in the
   database transaction; include failures and gaps.
6. Add qualified historical source-specific companion tables and command.
7. Add read-only Provider qualification reconciliation.

Focused tests cover empty/incomplete capture windows, source gaps, Artifact and
Runtime lineage, availability, finality, price/timeframe, calendar/membership,
decision reference, Outcome path, rehearsal admission rejection, formal
admission derivation, supersession, idempotency, concurrency, stale fence,
rollback, unknown commit, and reconciliation.

## Slice 3 — campaign predeclaration

1. Add Research-owned Campaign/PartitionPlan/EvaluationBinding/CostAssumption
   domain types with deterministic root and roster hashes.
2. Add a narrow FormalCampaign UoW and PostgreSQL repositories.
3. Add schema roots/children, child-first deferred closure, exact policy and
   Artifact FKs, append-only generation, and immutable plan guards.
4. Implement predeclare with exact idempotency and evidence-class ceiling.
5. Bind one Provider decision and complete actual Partition/Experiment rosters.
6. Validate actual roots exactly match plans, target, purposes, order, calendar,
   windows, purge/embargo, Evaluation protocols, and baseline policies.
7. Open protected mode through an exact LOCKED_OOS/PROSPECTIVE ExperimentRun;
   reject late or changed binding.

Tests cover changed-request replay, partial/duplicate/late rosters, wrong Target
or policy, plan/actual drift, generation/supersession, protected-open ordering,
historical/replay Prospective rejection, and rollback without partial roots.

## Slice 4 — formal PIT read seam and Dataset binding

1. Implement exact source-specific qualified visibility writes, each concrete-
   FK to source, capture, and admitted Provider decision.
2. Implement the campaign-bound read port that resolves only exact qualified
   sources at a requested DecisionTime.
3. Add a formal Dataset registration scope binding so formal Dataset validation
   can accept an exact qualified visibility while ordinary Dataset validation
   continues to require native `decision_visible_at <= DecisionTime`.
4. Reject missing, ambiguous, wrong-product, wrong-campaign, superseded,
   post-cutoff, or unadmitted visibility.
5. Prove ordinary Market/Selection/Outcome queries cannot use the seam.

No old Capture or normalized source row is updated. No unrestricted latest or
current query is introduced.

## Slice 5 — due discovery, campaign binding, and inspection

1. Bind exact Runtime decision/due Runs after persisted DAG reconciliation.
2. Add the narrow database-clock due discovery query over the complete
   campaign-bound PROSPECTIVE Partition roster.
3. Preserve `NOT_DUE`, `DUE`, `SETTLED`, and `MISSING` members explicitly.
4. Add read-only campaign inspection across Provider, Partition, access,
   Outcome, Evaluation, Evidence, Assessment, and Qualification states.
5. Add full campaign/provider verifier with `matched/mismatch_count` result.

Tests cover clock edges, SHADOW live-clock acceptance, HISTORICAL/REPLAY
rejection, missing/gap retention, concurrent settlement discovery, exact first
access, inspection blockers, and mutation-free verifier behavior.

## Slice 6 — sole composition and architecture closure

1. Compose Provider qualification and Formal campaign applications/query ports
   in `TargetApplication`.
2. Keep Runtime dispatch and CLI absent.
3. Add import-architecture tests proving bounded ownership and no Legacy or
   concrete PostgreSQL imports in Domain/Application.
4. Update schema catalog specifications, README navigation, Authority Map,
   Current State, Roadmap, and Capability Matrix.

## Slice 7 — correctness and recovery campaigns

Run real PostgreSQL campaigns for:

```text
identical/changed Protocol registration
complete Capture roster race
formal-vs-rehearsal admission ceiling
identical/changed campaign predeclaration
Partition/Experiment binding race
protected-open race
qualified visibility race
due discovery vs Outcome settlement
stale Runtime fence
serialization/deadlock/transient connection
mid-protocol/mid-result/mid-campaign/mid-binding failure
unknown commit exact probe/replay
read-only reconciliation
```

Passing requires one canonical truth, no partial roster, no unqualified
visibility, no policy mutation, no hidden Outcome access, and zero verifier
mismatches.

## Slice 8 — exact-SHA engineering qualification

Create an implementation checkpoint, then run on that exact SHA:

```bash
uv sync --frozen --extra dev --extra postgres
uv run python -m pytest -q tests/refoundation/formal_research
uv run python -m pytest -q tests/refoundation
uv run python -m pytest -q tests/platform
uv run python -m pytest -q tests/persistence/postgres
uv run python -m pytest -q
uv run python -m ruff check .
uv run python -m mypy
uv run python -m build
uv run python scripts/check_docs_links.py
uv run python -m pytest -q tests/scripts/test_check_docs_links.py
git diff --check
```

Also use a fresh disposable PostgreSQL 16 database for bootstrap/verify,
guarded exact-OID recreate/verify, schema/catalog/checksum reproducibility, and
`EXPLAIN (ANALYZE, BUFFERS)` of capture roster, requirement reconciliation,
qualified visibility, campaign binding, due discovery, and inspection paths.

## Slice 9 — immutable Verification and merge gate

Only when every P0/P1 gate passes:

1. create immutable WP-14 Verification with exact implementation SHA, tree and
   checksum identities, commands/results, remote-CI state, evidence ceiling,
   and NO-GO list;
2. update Current State, Roadmap, Capability Matrix, and Authority Map without
   claiming empirical evidence;
3. commit status documents, confirm clean branch, fetch latest `origin/main`,
   re-evaluate drift, push, open/update PR, and merge;
4. fetch merged main and prove it contains the exact verified implementation
   plus `WP14_EXIT_GATE = PASS`.

Only then create a new WP-15 branch/worktree. If any gate fails, record the
exact SHA and blocker and stop without WP-15 code.

## Permanent non-goals

No slice creates Model, Calibration, broker/Execution authority, Production
Admission, Runtime/CLI cutover, Legacy deletion, formal empirical claims, or
Alpha optimization. WP-14 tests never use `RECORDED_PROVIDER` to establish an
empirical admission.
