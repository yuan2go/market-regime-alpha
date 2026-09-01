# Documentation Authority

> **Status:** CURRENT_STATUS
> **Authority:** Documentation navigation and precedence only
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-31
> **Code Evidence:** `src/market_regime_alpha`, both legacy and target PostgreSQL migration packages, `tests`

Documentation never creates implementation truth, research evidence,
qualification, account state, or trading authority.

## Two truths that must not be collapsed

| Plane | Meaning | Source |
|---|---|---|
| Approved Target | The Hard Cutover architecture to be implemented | Canonical Overall Design, supporting target documents, ADR-015 |
| Current implementation | What the checked-out source, legacy 001–106 migrations, draft target baseline, tests, and reproducible evidence actually do | code → PostgreSQL → tests → artifacts |

The approved Target is normative for new implementation. Current implementation
scope, exact checkpoint SHAs, schema counts, and verification state live only
in [Current State](status/Current-State.md) and the linked immutable
Verification records. The target Runtime has not cut over a business CLI or
canonical write path; there is no dual write or target fallback.

## Normative authority order

1. latest explicit user decision not superseded;
2. [Canonical Overall Design](architecture/Canonical-Overall-Design.md) and
   [ADR-015](architecture/decisions/ADR-015-Hard-Cutover-and-Schema-Epoch.md);
3. supporting Target documents below;
4. the planning-only [Implementation Roadmap](status/Roadmap.md);
5. historical ADRs, frozen protocols, and evidence reports as provenance;
6. Git history for historical context only.

## Implementation fact authority order

1. executable code and actual call chains;
2. PostgreSQL schema, migrations, canonical writers, and readers;
3. tests and checks actually executed at an exact SHA;
4. reproducible Runtime, replay, and research artifacts;
5. non-authoritative status read models.

No status page, Capability view, Roadmap, Evidence Ledger, report, or CLI output
may write or promote canonical state.

## Approved Target architecture

- [Context Map](../CONTEXT-MAP.md)
- [Canonical Overall Design](architecture/Canonical-Overall-Design.md)
- [System and Runtime Architecture](architecture/System-Architecture.md)
- [Authority Map](architecture/Authority-Map.md)
- [PostgreSQL, Temporal and Evidence Architecture](architecture/Data-and-Evidence-Architecture.md)
- [Research and Decision Lifecycle](architecture/Research-Strategy-Lifecycle.md)
- [Repository Convergence Inventory](architecture/Repository-Convergence-Inventory.md)

Checkpoint traceability:

- [Capability Preservation Matrix](references/WP-ARCHITECTURE-REFOUNDATION-01-Capability-Preservation-Matrix.md)
- [283 to Target Table Disposition](references/WP-ARCHITECTURE-REFOUNDATION-01-Table-Disposition.md)
- [Domain Invariant Catalog](references/WP-ARCHITECTURE-REFOUNDATION-01-Domain-Invariant-Catalog.md)
- [WP-07 Candidate Closure Design](references/WP-ARCHITECTURE-REFOUNDATION-07-Candidate-Closure-Design.md)
  — approved five-table Candidate Authority, ranking semantics, dependency seam,
  and implementation proof contract. Its post-Candidate routing question was
  superseded by WP-08; implementation evidence lives only in the immutable
  WP-07 Verification.
- [WP-08 Post-Candidate Authority Design](references/WP-ARCHITECTURE-REFOUNDATION-08-Post-Candidate-Authority-Design.md)
  — approved acyclic Target commitment, Market Target Outcome, Partition,
  Evaluation, Evidence, Assessment, and Research Qualification semantics plus
  the original post-Candidate implementation order. Its architecture semantics
  remain applicable, while its separate Partition/Experiment then Evaluation
  packaging is superseded by the integrated WP-11 work package; design only,
  not implementation or evidence.
- [WP-09 Target Commitment and Decision Run Design](references/WP-ARCHITECTURE-REFOUNDATION-09-Target-Commitment-Decision-Run-Design.md)
  — approved Target-owned relational closure, provider-neutral Target
  semantics, one canonical Decision Run per Candidate Set, mandatory Runtime
  edge, and exact replay/reconciliation implementation contract; this remains
  the design-time decision record, not implementation evidence.
- [WP-10 Market Target Outcome Design](references/WP-ARCHITECTURE-REFOUNDATION-10-Market-Target-Outcome-Design.md)
  — approved commitment-bound realized-market-fact Authority, append-only full
  revisions, frozen Decision-reference binding, dual cutoffs, concrete source
  and metric dependency rosters, pure numerical kernel, and read-only Outcome
  port; exact implementation evidence is kept separately in the immutable
  WP-10 Verification.
- [WP-11 Research Validity and Evaluation Closure Design](references/WP-ARCHITECTURE-REFOUNDATION-11-Research-Validity-Evaluation-Design.md)
  — approved integrated Target/Outcome parity, database-derived Partition,
  Experiment, Evaluation Protocol/Run, transactional first-Outcome-access,
  complete observation, and metric-roster implementation contract; it grants
  only draft implementation scope and no engineering qualification claim.
- [WP-11 Research Validity and Evaluation Closure Implementation Status](references/WP-ARCHITECTURE-REFOUNDATION-11-Research-Validity-Evaluation-Implementation-Status.md)
  — historical exact-base draft implementation and focused-validation record.
  Its original ceiling is preserved and superseded by the immutable WP-11
  Verification below.
- [WP-11Q Research Validity and Evaluation Qualification Design](references/WP-ARCHITECTURE-REFOUNDATION-11Q-Research-Validity-Evaluation-Qualification-Design.md)
  — execution-time correctness and exact-SHA qualification contract that
  closes sole composition, single-exchange Partition calendar Authority,
  complete Experiment binding rosters, formal reconciliation, concurrency and
  recovery before any WP-11 exit-gate decision.
- [WP-11Q Research Validity and Evaluation Qualification Implementation Plan](references/WP-ARCHITECTURE-REFOUNDATION-11Q-Research-Validity-Evaluation-Qualification-Implementation-Plan.md)
  — file-level TDD slices, checkpoint boundaries, PostgreSQL campaigns, full
  exact-SHA gate and merge-stop procedure for executing the approved WP-11Q
  design without entering WP-12 early.
- [WP-11 Research Validity and Evaluation Verification](references/WP-ARCHITECTURE-REFOUNDATION-11-Research-Validity-Evaluation-Verification.md)
  — immutable exact-SHA engineering proof for sole composition,
  single-exchange Partition calendar Authority, complete ordered Experiment
  rosters, controlled Outcome access, full Evaluation closure, PostgreSQL
  qualification, concurrency/recovery/replay, full regression, static/build,
  and `WP11_EXIT_GATE = PASS` without Runtime/CLI cutover.
- [WP-12 Research Evidence, Assessment and Qualification Closure Design](references/WP-ARCHITECTURE-REFOUNDATION-12-Research-Evidence-Assessment-Qualification-Design.md)
  — canonical implementation contract for Evaluation-bound immutable Evidence,
  complete Experiment Assessment rosters, purpose-specific relational Policy
  floors, explicit floor results/Evidence, append-only supersession, and
  generation-safe qualification reads; design only until its exact-SHA
  engineering gate passes.

Design documents in this section define the Target destination. Status and
Verification records report their explicitly bounded implementation evidence;
they do not grant canonical business write or research-promotion Authority.

## Current implementation and forward plan

- [Current State](status/Current-State.md) — exact-SHA, non-authoritative
  implementation snapshot and invalidation rules.
- [Capability Matrix](status/Capability-Matrix.md) — compact current-to-Target
  convergence view; no evidence promotion.
- [Implementation Roadmap](status/Roadmap.md) — the only active engineering
  sequence. It includes unresolved gaps; there is no separate Gap Register.
- [WP-02 Pre-Refoundation Verification Baseline](references/WP-ARCHITECTURE-REFOUNDATION-02-Pre-Refoundation-Verification-Baseline.md)
  — immutable commands/results at the approved design SHA.
- [WP-03 Foundation Verification](references/WP-ARCHITECTURE-REFOUNDATION-03-Foundation-Verification.md)
  — exact-SHA engineering proof for the merged Foundation substrate.
- [WP-04 Market/PIT Verification](references/WP-ARCHITECTURE-REFOUNDATION-04-Market-PIT-Verification.md)
  — exact-SHA engineering proof for the test-only Market/PIT draft slice.
- [WP-05 Selection Core Verification](references/WP-ARCHITECTURE-REFOUNDATION-05-Selection-Core-Verification.md)
  — exact-SHA engineering proof for the test-only Universe/Eligibility draft
  slice; Candidate remains deferred.
- [WP-06 Research Definition Core Verification](references/WP-ARCHITECTURE-REFOUNDATION-06-Research-Definition-Core-Verification.md)
  — exact-SHA engineering proof for strict Decision-input Dataset,
  DatasetSource, FeatureDefinition, and shared deterministic command-failure
  semantics; Candidate code was absent at that historical checkpoint.
- [WP-07 Candidate Closure Verification](references/WP-ARCHITECTURE-REFOUNDATION-07-Candidate-Closure-Verification.md)
  — exact-SHA local engineering proof for the five-table Selection-owned
  Candidate draft. It grants no later-context implementation order, Runtime
  cutover, Provider/Alpha evidence, trading, or Production authority.
- [WP-09 Target Commitment and Decision Run Verification](references/WP-ARCHITECTURE-REFOUNDATION-09-Target-Commitment-Decision-Run-Verification.md)
  — exact-SHA local engineering proof for provider-neutral Target Definition,
  one Decision Run per Candidate Set, complete Candidate × Target commitments,
  immutable Decision-visible references, and mandatory test-only Runtime DAG;
  Market Target Outcome is absent and Runtime/CLI cutover remains NO-GO.
- [WP-10 Market Target Outcome Verification](references/WP-ARCHITECTURE-REFOUNDATION-10-Market-Target-Outcome-Verification.md)
  — exact-SHA local engineering proof for the commitment-bound, append-only,
  dual-cutoff Market Target Outcome Authority, pure Decimal kernel, concrete
  source/observation/metric dependencies, replay/reconciliation and read-only
  consumer port; Partition/Experiment and Runtime/CLI cutover remain absent.
- [Runtime Runbook](operations/Runtime-Runbook.md) — current 001–106 operator
  procedures only; it will be rewritten at Runtime/CLI Cutover.

Current State and Capability Matrix are read models. They must display their
generation time, repository SHA, schema epoch, source tree IDs, and proof
ceiling. A later code/schema change invalidates them until regenerated.

## Historical research and decisions

Frozen protocols, negative/inconclusive results, and execution reports under
`docs/research/` and `docs/references/` are retained only as immutable
provenance. They are not the current engineering program and do not constrain
the Hard Cutover to preserve old module/table identities.

ADR-008 through ADR-014 describe superseded implementation eras. The valid
temporal rules originally established by ADR-014 are restated in the Target
architecture; its v1/v2 readers and additive-migration policy are historical and
create no compatibility requirement. ADR-015 owns the new schema epoch and
destructive-recreate decision.

## Status vocabulary

| Status | Meaning |
|---|---|
| `CANONICAL_TARGET_ARCHITECTURE` | approved future architecture; implementation may be absent |
| `CURRENT_ARCHITECTURE` | retained decision that is both implemented and compatible with the Target |
| `CURRENT_STATUS` | navigation or exact-SHA non-authoritative read model |
| `ROADMAP` | planning order only |
| `HISTORICAL` | immutable provenance, not current instruction |
| `SUPERSEDED` | replaced and retained only for traceability |

`CURRENT_ARCHITECTURE` must not label an unimplemented Target document.

## Start here

For architecture or implementation work, read:

1. [Canonical Overall Design](architecture/Canonical-Overall-Design.md)
2. [System Architecture](architecture/System-Architecture.md)
3. [Authority Map](architecture/Authority-Map.md)
4. [Data and Evidence Architecture](architecture/Data-and-Evidence-Architecture.md)
5. [Research and Decision Lifecycle](architecture/Research-Strategy-Lifecycle.md)
6. [Repository Convergence Inventory](architecture/Repository-Convergence-Inventory.md)
7. [Current State](status/Current-State.md)
8. [Capability Matrix](status/Capability-Matrix.md)
9. [Implementation Roadmap](status/Roadmap.md)
10. affected code, schema, tests, and exact evidence

The design says where to converge. Executable evidence says what is true today.
