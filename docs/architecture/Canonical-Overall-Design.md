# Market Regime Alpha — Hard Cutover Target Architecture

> **Status:** CANONICAL_TARGET_ARCHITECTURE
> **Authority:** WP-ARCHITECTURE-REFOUNDATION-01 design checkpoint
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-30
> **Starting Main:** `0382dad416d6d50d1eea0bda1603d7c359d65274`
> **Implementation State:** `FOUNDATION_MARKET_SELECTION_RESEARCH_DEFINITION_CANDIDATE_IMPLEMENTED_DRAFT / CANDIDATE_EXIT_GATE_PASS / NOT_CUT_OVER`
> **Code Evidence:** target `src/market_regime_alpha/shared`, `src/market_regime_alpha/runtime`, `src/market_regime_alpha/market`, `src/market_regime_alpha/selection`, `src/market_regime_alpha/research_qualification`, `src/market_regime_alpha/infrastructure`, `src/market_regime_alpha/interfaces`, target draft `src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql`, `tests/refoundation`; legacy source/migrations remain current business implementation

This document freezes the approved architecture. Foundation, Market/PIT,
Selection Core, the three-table Research Definition Core, and the five-table
Selection-owned Candidate Authority now exist as an isolated
`MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER` implementation. Candidate passed its
local WP-07 engineering exit gate at
`029c26928af436d7788da1cce3a53c94b96377bf`. All later target contexts remain
unimplemented; the next authorized activity is only a real dependency review,
not an implementation order. Legacy code and the current
283-table schema remain canonical business implementation truth until the
explicit Runtime/CLI Hard Cutover. Neither the design nor the draft creates
research, Provider, trading, or Production proof.

The approved direction is **Hard Cutover Re-foundation**: preserve real business
capabilities and correctness invariants, but do not preserve wrong abstractions,
historic schema shapes, compatibility writers, or redundant state authorities.

Supporting specifications:

- [Context Map](../../CONTEXT-MAP.md)
- [System and Runtime Architecture](System-Architecture.md)
- [Authority Map](Authority-Map.md)
- [PostgreSQL, Temporal and Evidence Architecture](Data-and-Evidence-Architecture.md)
- [Research and Decision Lifecycle](Research-Strategy-Lifecycle.md)
- [Convergence Inventory](Repository-Convergence-Inventory.md)
- [Capability Preservation Matrix](../references/WP-ARCHITECTURE-REFOUNDATION-01-Capability-Preservation-Matrix.md)
- [283-table Disposition](../references/WP-ARCHITECTURE-REFOUNDATION-01-Table-Disposition.md)
- [Domain Invariant Catalog](../references/WP-ARCHITECTURE-REFOUNDATION-01-Domain-Invariant-Catalog.md)
- [ADR-015: Hard Cutover and Schema Epoch](decisions/ADR-015-Hard-Cutover-and-Schema-Epoch.md)

## 1. Product boundary

Market Regime Alpha is an industrial A-share research operating system and
human-in-the-loop decision-support platform. Its output can support a human
decision and record observed execution. It is not unattended live trading and
does not obtain broker authority in this work package.

The canonical business flow is:

```text
Provider Capture
→ Market/PIT Fact
→ Universe Revision
→ Eligibility Assessment
→ Candidate Set
→ Context / Signal / Target-bound Forecast
→ Opportunity / Thesis / Strategy Decision
→ Portfolio Proposal / Risk Decision
→ Human Execution Intent
→ Observed Fill
→ Physical Position / Strategy Allocation
→ Outcome / Attribution
→ Research Assessment / Qualification
```

Every arrow carries stable identity, time, provenance, and availability. Empty,
`UNKNOWN`, `NO_ACTION`, `WAIT`, `NOT_ESTIMABLE`, and rejection are first-class
results.

### Non-goals

- No microservices, message broker, event sourcing, generic workflow framework,
  generic registry framework, AutoML, or broker automation.
- No preservation of old table identities or historical rows.
- No table-count target. The frozen logical catalog contains **91 tables**
  because those relations protect current business semantics; the earlier
  estimate of approximately 41 is explicitly non-binding.
- No document, report, Evidence Ledger, Current State page, CLI output, or
  artifact directory becomes business Authority.
- No compatibility package or dual-write period after cutover.
- No empirical promotion: engineering replay cannot imply Formal PIT, Formal
  OOS, Prospective support, Production qualification, or tradability.

## 2. Target module structure

```text
src/market_regime_alpha/
  shared/
    identity.py
    time.py
    money.py
    errors.py
  runtime/
    domain/
    application/
    ports.py
  market/
    domain/
    application/
    ports.py
  selection/
    domain/
    application/
    ports.py
  research_qualification/
    domain/
    application/
    ports.py
  decision/
    domain/
    application/
    ports.py
  outcome/
    domain/
    application/
    ports.py
  execution/
    domain/
    application/
    ports.py
  infrastructure/
    postgres/
      migrations/
      repositories/
      queries/
    artifacts/
    providers/
    observability/
  interfaces/
    cli/
    inspection/
  bootstrap.py
```

This is a modular monolith. Packages are organized by bounded context first, not
by global technical layers. Each context may contain Domain, Application, and
ports; adapters remain under `infrastructure`. `bootstrap.py` is the sole
composition root.

### Dependency rules

1. `shared` contains only stable value types and errors; it has no business
   services and no infrastructure imports.
2. A context's Domain imports only `shared` and its own Domain.
3. Application services own use-case transactions and depend on ports.
4. Repositories expose aggregate operations, not table CRUD and not one
   repository class per table.
5. Cross-context mutation occurs through commands; cross-context queries return
   immutable read DTOs.
6. Infrastructure never appears in a Domain signature.
7. CLI and inspection code call Application commands/queries; they do not open
   SQL transactions or assemble repositories.
8. Only `bootstrap.py` may import all contexts and concrete adapters.
9. Architecture tests reject cycles, cross-context repository imports, legacy
   imports, hidden composition roots, and SQL outside PostgreSQL adapters.

## 3. Bounded contexts and aggregates

| Context | Aggregate roots / immutable facts | Primary commands | Primary queries |
|---|---|---|---|
| Runtime & Provenance | Schedule, Run, Step, Attempt, Command Receipt, Artifact | schedule, claim, heartbeat, finalize, resume, verify artifact | run trace, due work, integrity report |
| Market & PIT | Capture, Instrument, Trading Session, Fact Revision, Classification Revision, Source Gap | register capture, normalize revision, record gap/correction | as-of fact, exact session grid, source lineage |
| Selection | Universe Revision, Eligibility Assessment, Candidate Policy/Set/Candidate and Candidate Score Component | freeze universe, assess eligibility; register Candidate policy and build Candidate Set only from the immutable Decision-input Dataset | scope and eligibility at Decision time; Candidate funnel and dossier |
| Research & Qualification | initially Dataset, Dataset Source, and Feature Definition; later owner boundaries subject to post-Candidate dependency review | initially register immutable Decision-input definitions; later commands are not yet ordered or authorized | initially exact Dataset/Feature lineage |
| Decision Support | Decision Run, Context Assessment, Signal, Forecast, Opportunity, Thesis, Strategy Version, Portfolio Proposal, Risk Decision | decide, propose, risk-assess | decision dossier, risk authorization |
| Outcome & Attribution | Outcome, Observation, Metric, Reason, Attribution Run/Line | settle outcome, attribute | outcome status/path, metric availability, attribution |
| Execution & Account | Account Authority Epoch, Execution Intent, Fill, Fill Allocation, Broker Observation, Reconciliation, Position Basis Event | approve intent, record/correct fill, observe broker, reconcile, authorize non-trade adjustment | current position, sleeve, cash/exposure evidence |

Value objects include `DecisionTime`, `KnownTime`, `TradingSessionId`,
`InstrumentId`, `PriceBasis`, `Money`, `Quantity`, `ContentHash`,
`EvidenceClass`, `AssessmentStatus`, `QualificationPurpose`, `FenceToken`, and
`IdempotencyKey`. They validate construction and are not string aliases.

## 4. Canonical Authority model

A business fact has exactly one command handler, one transactional repository
operation, and one relational owner. Read views and artifacts are downstream.

```text
Command
  → validate frozen identities and expected versions
  → load aggregate under the declared lock order
  → enforce Domain invariants
  → append/mutate the canonical relational fact
  → insert command receipt + audit link
  → commit once
  → publish immutable read result
```

For a Runtime-owned command whose business transaction raises a deterministic
rejection, that transaction rolls back completely. The owning Application then
opens a new short instance of the same bounded-context UoW and atomically locks
the live fence, records the failed command receipt and audit event, finalizes the
matching Attempt/Step as failed, and commits. A stale fence rejects before any
failure receipt or audit write. The shared contract owns only these
Runtime/receipt/audit failure semantics; Domain error interpretation and command
dispatch remain in each bounded context.

There is no generic `save(payload)`, generic registry, dual-write adapter, or
“latest” row accepted from a caller. Exact authority assignments and the
Fill/Position exception for typed non-trade basis events are specified in the
[Authority Map](Authority-Map.md).

## 5. Command/query and transaction boundaries

Commands are idempotent by `(command_kind, scope_id, idempotency_key)` and return
the original receipt on exact retry. Reusing a key with a different request hash
fails closed. Business writes and their command receipt commit atomically.

A command transaction:

- is short and contains no provider, broker, filesystem, or remote artifact I/O;
- locks only its aggregate in the documented global order;
- checks expected version and, for Runtime work, the current fence token;
- uses database constraints for identity, temporal order, non-negative
  quantities, closed enums, and cardinality;
- emits no best-effort second write after commit.

Selection owns a separate narrow UoW rather than widening Runtime or Market.
Its Market dependency is a read-only exact/as-of query port; the concrete
Selection adapter may use the same PostgreSQL connection but cannot import a
Market repository. If invoked as a Runtime Step, live-fence validation,
Selection business writes, command receipt, audit event, and Step finalization
commit together in that one short transaction.

Queries never acquire mutation authority. “Current” values are database views or
explicit as-of queries over canonical histories. Read models can be rebuilt and
deleted without losing business facts.

## 6. Runtime composition

One schedule owner starts a Run. A Run freezes code SHA, config hash, schedule
revision, clock mode, and requested Decision time. Its DAG uses these canonical
steps when applicable:

```text
CAPTURE
→ NORMALIZE_PIT
→ FREEZE_UNIVERSE
→ ASSESS_ELIGIBILITY
→ REGISTER_DATASET
→ BUILD_CANDIDATE_SET
→ ASSESS_CONTEXT
→ SIGNAL_AND_FORECAST
→ DECIDE_AND_RISK
→ PERSIST_DECISION
→ SETTLE_OUTCOME
→ ATTRIBUTE
→ ASSESS_RESEARCH
```

This is a dependency invariant, not merely a display order. Same-run Context
may consume Market/PIT and the frozen Candidate scope, but Universe,
Eligibility, and Candidate commands never consume that Context result. An
Opportunity carries Decision input Evidence only; the single authoritative Risk
evaluation occurs after a complete Portfolio Proposal.

Selection Core and Research Definition together provide the prerequisites
through `REGISTER_DATASET`; Candidate Closure implements
`BUILD_CANDIDATE_SET`. `BUILD_CANDIDATES` is not an alias or compatibility name.
Before Runtime/CLI Cutover this expanded slice is test-only and creates no
current Runtime dispatch or canonical write authority.

Historical, replay, shadow, and prospective modes reuse Application commands
and business semantics. They differ only in clock, frozen input resolver,
execution adapter, and qualification purpose. They are not parallel business
architectures. Runtime fencing/retry/resume is frozen in
[System Architecture](System-Architecture.md).

## 7. Persistence and artifact boundary

PostgreSQL 16 is the sole relational Authority. The target catalog has 91 tables
across Runtime/Provenance, Market/PIT, Selection, Research/
Qualification, Decision/Outcome, and Execution/Account. Large immutable raw
captures, datasets, matrices, model binaries, and reports are content-addressed
artifacts; their metadata, hashes, business bindings, verification state, and
retention decisions remain in PostgreSQL.

JSONB is not used for facts with stable query/integrity requirements. It is
limited to opaque provider headers, diagnostic detail with a declared schema,
and non-authoritative presentation metadata. Candidate evidence, eligibility
reasons, target checkpoints, MFE/MAE, qualification floors, Fill allocations,
and runtime state are relational and typed.

The complete schema, temporal rules, evidence model, artifact commit protocol,
and destructive-recreate boundary are in
[Data and Evidence Architecture](Data-and-Evidence-Architecture.md).

## 8. Interfaces

The public boundary is intentionally small:

- `mra runtime run|resume|inspect`;
- `mra market capture|verify|inspect`;
- `mra research dataset|experiment|evaluate|qualify|inspect`;
- `mra decision run|inspect|settle`;
- `mra execution intent|fill|observe|reconcile|positions`;
- `mra db bootstrap|verify|recreate`.

Commands accept typed identifiers or files whose content hash is frozen before
execution. Inspection is read-only. There is no CLI that writes tables directly,
no duplicate `__main__` execution plane, and no REST API until a demonstrated
consumer requires one. A future API must call the same Application commands and
queries.

## 9. Configuration

Configuration is split by authority:

- environment: connection strings, artifact root, credentials, process limits;
- runtime schedule: typed `runtime_schedule` rows;
- business/research policy: immutable typed policy/definition rows;
- run snapshot: a content-addressed resolved config artifact bound to the Run.

Secrets are never persisted in artifacts, command receipts, audit rows, or
logs. Unknown keys, invalid enum values, missing required environment variables,
and mismatched config hashes fail startup. No global mutable settings singleton
and no database-stored secret exists.

## 10. Observability and auditability

Every log/metric/trace carries `run_id`, `step_id`, `attempt_id`,
`command_receipt_id`, and affected aggregate identity where available. Required
signals include queue latency, lease expiry, retry reason, stale-fence rejection,
transaction conflict, provider gap, PIT exclusion, Candidate funnel, risk
rejection, artifact mismatch, orphan count, reconciliation difference, and
qualification-floor status.

`audit_event` is append-only and records actor, command receipt, aggregate,
action, reason code, event time, recorded time, and before/after version—not full
secret-bearing payloads. Operational logs are not Authority and may be retained
outside PostgreSQL.

## 11. Testing architecture

The implementation phase must preserve and re-home invariants before deleting
legacy tests. Test layers are:

1. pure Domain invariant/property tests;
2. Application command/query tests with deterministic ports;
3. PostgreSQL repository/constraint/transaction tests against an empty isolated
   database;
4. idempotency, concurrent claim, stale fence, deadlock-order, restart, and
   unknown-external-effect tests;
5. Market/PIT visibility and revision tests;
6. Candidate/Eligibility and Outcome lineage tests;
7. artifact commit, corruption, orphan, and GC tests;
8. composition/CLI smoke and architecture dependency tests;
9. end-to-end empty-database bootstrap through outcome/evidence;
10. full repository gates.

Legacy test disposition is governed by the
[Domain Invariant Catalog](../references/WP-ARCHITECTURE-REFOUNDATION-01-Domain-Invariant-Catalog.md).
No failing test is removed merely because its current module or table disappears.

## 12. Documentation and Skills architecture

The durable knowledge set after implementation is:

- `README.md`: product and operator entry;
- `AGENTS.md`: one execution contract;
- `docs/README.md`: authority/navigation;
- these five architecture documents plus the Context Map;
- a small set of accepted ADRs for irreversible choices;
- Current State generated from canonical queries and test evidence;
- one operator runbook;
- immutable research protocols/reports only when they bind real evidence.

Roadmaps, status pages, Capability views, Evidence Ledgers, and delivery reports
are non-authoritative projections. If retained, each states generation time,
source query/artifact, and code SHA; manual edits cannot promote state.

A repository Skill survives only if it provides a stable, reusable procedure
with an explicit input/output contract, authorization boundary, and testable
failure behavior. The sole retained project Skill is the high-risk,
explicitly-triggered branch-reconciliation procedure. Ordinary coding, testing,
formatting, documentation, table inspection, architecture/research checklists,
and prompt wrappers are not Skills. Overlapping prompts, duplicate agent
instructions, versioned Skill forks, and Skills superseded by code are deleted.

## 13. Hard Cutover sequence

After explicit implementation approval:

1. implement new Domain types and invariant tests without old persistence;
2. create the immutable schema-epoch baseline and target repositories;
3. implement Application commands/queries and the composition root;
4. run both behavior suites only for comparison—never dual-write business state;
5. cut all entry points to the target runtime in one release;
6. require an empty target schema or explicit destructive recreate;
7. delete old migrations, repositories, compatibility packages, CLIs, fixtures,
   and tests only after invariant mapping;
8. regenerate Current State/read models from canonical data;
9. prove clean bootstrap, operation, recovery, lineage, and full gates;
10. commit the implementation in dependency-coherent checkpoints.

No historical business data is migrated. Old databases fail fast on schema epoch
mismatch and are never implicitly dropped.

## 14. Frozen design invariants

- One business fact → one Authority → one canonical write path.
- Decision-time visibility is computed from persisted temporal fields, never
  caller claims or retrieval convenience.
- A score is not a probability without calibration evidence.
- Target horizon never implies holding period or exit.
- Outcome path, Decision reference, and each derived metric retain independent
  statuses.
- Trade-caused Position changes derive only from observed effective Fills.
- Non-trade Position basis changes require a typed, separately authorized event.
- Risk rejection cannot be bypassed.
- Runtime final writes require the live fence.
- Unknown external effects are reconciled, never blindly retried.
- Artifact identity is content hash, not location.
- Qualification is a purpose-scoped vector of floors, not a maturity scalar.
- Documents and projections cannot write canonical state.
- Schema mismatch fails before any destructive DDL.

## 15. Unresolved implementation risks

These do not reopen the architecture direction, but require evidence during the
next checkpoint:

1. Current database business-row counts could not be inspected with the
   available role; no data migration is planned, but live operational ownership
   must still be checked before any destructive command is authorized.
2. Provider contracts may not expose defensible availability/finality metadata;
   such facts remain exploratory or `UNKNOWN` rather than guessed.
3. Corporate-action entitlement and broker observation semantics vary by
   provider/account and need adapter-specific qualification fixtures.
4. Unknown external execution effects need a real operator reconciliation
   workflow before any broker adapter is introduced.
5. The 91-table catalog is frozen semantically, but physical index choices must
   be confirmed with representative query plans during implementation.
6. Historical artifact volume and retention are not yet measured; partitioning
   is deliberately deferred until measured.
7. Some legacy tests encode implementation quirks rather than business
   invariants; deletion requires the cataloged review rule, not an automatic
   translation.
8. No current evidence establishes Formal PIT, Formal OOS Alpha, sustained
   Prospective value, Production admission, or broker integration.
