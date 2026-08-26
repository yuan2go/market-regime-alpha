# Documentation Authority

> **Status:** CURRENT_STATUS  
> **Authority:** Documentation navigation and precedence only  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-26
> **Code Evidence:** `src/market_regime_alpha`, `src/market_regime_alpha/persistence/postgres/migrations/*.sql`, `tests`

Documentation never creates implementation truth, research evidence, qualification, or trading authority.

## Normative authority order

1. latest explicit user decision not superseded;
2. [Canonical Overall Design](architecture/Canonical-Overall-Design.md);
3. supporting current architecture documents listed below;
4. current status, Gap Register and Roadmap;
5. accepted ADRs and evidence/reference reports as subordinate provenance;
6. Git history for historical context only.

The **single normative target-design source** is the Canonical Overall Design. Supporting architecture documents refine it but may not contradict it:

- [System Architecture](architecture/System-Architecture.md)
- [Authority Map](architecture/Authority-Map.md)
- [Data and Evidence Architecture](architecture/Data-and-Evidence-Architecture.md)
- [Research and Strategy Lifecycle](architecture/Research-Strategy-Lifecycle.md)
- [Repository Convergence Inventory](architecture/Repository-Convergence-Inventory.md) — actual consumers, replacements and Legacy dispositions; subordinate to the four current architecture documents.

If a supporting document conflicts with the Canonical Overall Design, the Canonical Overall Design wins and the supporting document must be corrected.

## Implementation fact authority order

When documentation conflicts with the repository, current implementation truth is established in this order:

1. executable code and the real runtime call chain;
2. PostgreSQL schema, migrations, canonical writers and readers;
3. tests and checks actually executed against that code;
4. reproducible runtime, replay and research evidence;
5. current status documents.

Target design does not turn an unimplemented or unproven capability into a current fact.

## Current state and execution order

- [Current State](status/Current-State.md) — what the current `main` actually implements and proves.
- [Capability Matrix](status/Capability-Matrix.md) — capability-by-capability implementation/evidence status.
- [Gap Register](status/Gap-Register.md) — unresolved engineering, prospective and external-evidence gaps.
- [Roadmap](status/Roadmap.md) — dependency-ordered work packages driven by current evidence.
- [Runtime Runbook](operations/Runtime-Runbook.md) — operator procedures for the implemented runtime.

## Research claims

- [WP-ALPHA-CORRECTNESS-02 Frozen Protocol](research/protocols/WP-ALPHA-CORRECTNESS-02-Frozen-Protocol.md) freezes the approved three-dimensional Target semantics and Discovery-only repair boundary before implementation. Its current state is `FROZEN_DESIGN / CODE_NOT_STARTED / RERUN_NOT_RUN`; it creates no new correctness or Alpha claim.
- [WP-ALPHA-CORRECTNESS-02 Baseline Audit](references/WP-ALPHA-CORRECTNESS-02-Baseline-Audit.md) records the exact starting SHA, environment, PostgreSQL schema, immutable owner availability, code call chain and pre-implementation capability boundary.
- [WP-ALPHA-PROOF-02 Frozen Vertical Slice Protocol](research/protocols/WP-ALPHA-PROOF-02-Frozen-Vertical-Slice-Protocol.md) is the immutable pre-registered protocol. Its [Execution Report](references/WP-ALPHA-PROOF-02-Execution-Report.md) records the terminal adverse Discovery result, failed correctness gate, unconsumed External/Locked Outcomes and exact owner identities.
- [Alpha Research Phase II Engineering Protocol](research/protocols/Alpha-Research-Phase-II-Engineering-Protocol.md) is the historical engineering baseline that produced the current kernels and owner wiring. It creates no empirical claim and is superseded as the active execution plan by WP-ALPHA-PROOF-02.
- [TEMPORAL_VALIDATION_V1 Frozen Protocol](research/protocols/TEMPORAL-VALIDATION-V1-Frozen-Protocol.md) freezes the first owner-derived 126-session temporal partition and every unchanged discovery input before outcome access; its [Contamination Audit](references/TEMPORAL-VALIDATION-V1-Contamination-Audit.md) records why the window is admissible but does not unlock it.
- [WP-ALPHA-RESEARCH-01 Frozen Discovery Protocol](research/protocols/WP-ALPHA-RESEARCH-01-Frozen-Discovery-Protocol.md) pre-registers the frozen Phase E3 dataset scope, Factor families, Gate/Candidate variants, metrics, multiple-testing policy and discovery evidence ceiling. The persisted Experiment Definition remains the executable owner.
- [WP-ALPHA-RESEARCH-01 Research Report](references/WP-ALPHA-RESEARCH-01-Research-Report.md) records the final owner-bound Panel, complete pre-registered Factor/Gate/Candidate results, methodology supersession and exploratory evidence ceiling.
- [Golden Loop V2 Scoring and Research Correctness Contract](research/protocols/Golden-Loop-V2-Scoring-Contract.md) freezes the tie-aware scoring, missingness, boundary-selection, immutable-lineage and canonical-Evidence rules for the first V2 campaign.
- [Golden Loop V2 Research Correctness Report](references/Golden-Loop-V2-Research-Correctness-Report.md) records the exact campaign, owner lineage, negative results, replay and evidence ceiling.
- [Negative and Inconclusive Results](research/Negative-and-Inconclusive-Results.md) is the current durable research-claim registry for negative, inconclusive and not-estimable findings.
- Reports under `docs/references/` are evidence/reference material. They are not normative architecture.

## Architecture decisions

ADRs under `docs/architecture/decisions/` record accepted decisions and their historical rationale. They remain useful provenance, but the Canonical Overall Design is the current consolidated design authority.

- [ADR-014: Frozen Target Semantics and Independent Correctness](architecture/decisions/ADR-014-Frozen-Target-Semantics-and-Independent-Correctness.md) records the accepted WP-ALPHA-CORRECTNESS-02 design. It separates Decision reference, Outcome window and derived-metric status while preserving independent source selection.

## Documentation cleanup policy

The former `docs/constitution/00` through `09` document set has been superseded by the Canonical Overall Design and removed from the active documentation tree. Git history preserves it for provenance. It must not be loaded as a second normative architecture.

Historical audits, completed work packages, superseded roadmaps, temporary plans, delivery reports, designed-only specifications and obsolete static documentation are retained in Git history rather than the default documentation tree. See [Archive Boundary](archive/README.md).

## Required evidence language

Documentation must not collapse these distinct implementation/proof states:

```text
CODE_IMPLEMENTED
CANONICAL_WIRED
TEST_EXECUTED
RUNTIME_PROVEN
RESEARCH_QUALIFIED
PRODUCTION_QUALIFIED
```

Research evidence must additionally retain its real limits, including where applicable:

```text
EXPLORATORY
PIT_INCOMPLETE
IN_SAMPLE
SHADOW
NOT_ESTIMABLE
UNQUALIFIED
FORMAL_OOS=false
CALIBRATED=false
```

A class, table, protocol, receipt, passing fixture, or engineering qualification never upgrades an empirical claim by itself.

## Start here

For architecture or implementation work, read in this order:

1. [Canonical Overall Design](architecture/Canonical-Overall-Design.md)
2. [System Architecture](architecture/System-Architecture.md)
3. [Authority Map](architecture/Authority-Map.md)
4. [Data and Evidence Architecture](architecture/Data-and-Evidence-Architecture.md)
5. [Research and Strategy Lifecycle](architecture/Research-Strategy-Lifecycle.md)
6. [Current State](status/Current-State.md)
7. [Gap Register](status/Gap-Register.md)
8. [Roadmap](status/Roadmap.md)
9. the code, schema, tests and runtime evidence relevant to the work package

The design defines where the system should converge. The repository and evidence define what is true today.
