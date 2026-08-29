# Market Regime Alpha Context Map

> **Status:** CANONICAL_TARGET_ARCHITECTURE
> **Authority:** Target bounded-context vocabulary and dependency map
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-29
> **Implementation State:** `FOUNDATION_MARKET_SELECTION_IMPLEMENTED_DRAFT / RESEARCH_DEFINITION_DESIGN_FROZEN / NOT_CUT_OVER`

This file defines names and relationships only. Foundation, Market/PIT, and
Selection Core exist in the isolated target draft; Research Definition Core is
approved but not yet implemented at this checkpoint. Current implementation
truth remains code, PostgreSQL, tests actually run, and reproducible evidence.

## Ubiquitous language

| Term | Canonical meaning | Explicitly not |
|---|---|---|
| Market Fact | A provider-sourced observation normalized without losing source, temporal, price-basis, revision, or capture identity. | A latest-value cache or provider response payload. |
| Known Time | Earliest instant at which the exact normalized revision was legitimately usable by this system. | Event time, provider time, or a reconstructed historical guess. |
| Universe Revision | Immutable, decision-time-resolvable membership scope with every included, excluded, and unknown symbol accounted for. | A current constituent list used retrospectively. |
| Eligibility Assessment | Per-instrument policy result at one decision time: `ELIGIBLE`, `INELIGIBLE`, or `UNKNOWN`, with typed reasons and evidence. | Candidate selection or a silent filter. |
| Decision-input Dataset | Immutable content-addressed Feature input whose rows exactly reconcile the same-DecisionTime `INCLUDED` and `ELIGIBLE` population, with explicit missing cells and exact lineage. | An Evaluation Dataset, Target/Outcome container, or posterior-label panel. |
| Feature Definition | Immutable calculation semantics, type/unit, temporal window, source, availability, missingness, and algorithm/code/config identity. | Alpha evidence, research maturity, external validation, or qualification. |
| Candidate | An eligible instrument admitted by a versioned Candidate policy, with exact score components and evidence lineage. | A Signal, Forecast, Entry, or trade recommendation. |
| Signal | A target-independent setup/state assertion produced from frozen inputs. | A calibrated probability or execution instruction. |
| Forecast | A Target/Checkpoint-bound estimate with explicit uncertainty and calibration status. | A raw score relabelled as probability. |
| Opportunity | A Decision-time binding of Candidate, Signal, Forecast, Context, Strategy Version, and exact input Evidence. | A Risk authorization, Fill, or Position. |
| Thesis | A versioned, falsifiable decision rationale with explicit conditions and invalidation evidence. | Free-form notes that mutate trading state. |
| Portfolio Proposal | An allocation proposal over Opportunities under a Portfolio Policy. | Account truth, reservation, or Fill. |
| Risk Decision | A fail-closed authorization or rejection under one Risk Policy and exact account/evidence state. | A Strategy bypass or after-the-fact flag. |
| Execution Intent | A human-approved request bounded by Portfolio and Risk decisions. | An Order acknowledgment, Fill, or Position. |
| Fill | An observed execution fact, including append-only correction lineage. | A target quantity, intent, or broker snapshot. |
| Physical Position | Deterministic projection of effective observed Fills plus explicitly authorized non-trade basis events. | A mutable independent ledger or recommendation. |
| Outcome | Factual post-decision observations and independently stated metric availability. | Qualification, attribution, or an assumed zero return. |
| Attribution | A diagnostic allocation of a realized/observed result to declared dimensions. | A replacement for Outcome or residual-balancing authority. |
| Evidence Item | Immutable, typed, content-addressed support or counter-evidence with provenance. | A document claim, boolean capability flag, or generic payload registry. |
| Assessment | A governed conclusion over a declared claim and evidence set. | Automatic promotion because a table or artifact exists. |
| Qualification Decision | The sole owner of a purpose-scoped admission decision and every required floor result. | A scalar maturity level inferred from other data. |
| Runtime Run | One immutable invocation envelope over a frozen schedule/config/code identity. | A business aggregate or daily truth table. |
| Runtime Step | A logical unit in a Run DAG; its state is derived from Attempts and dependencies. | An autonomous scheduler. |
| Runtime Attempt | One fenced execution claim with a lease, retry number, and terminal effect classification. | A mutable retry counter with no stale-writer protection. |
| Artifact | Immutable physical bytes identified by SHA-256; PostgreSQL owns metadata and business binding. | A pathname-based Authority. |

## Bounded contexts

```text
                                      +----------------------+
                                      | Runtime & Provenance |
                                      | schedule/run/fencing |
                                      +----------+-----------+
                                                 |
                         commands + frozen inputs|receipts + audit
                                                 v
+----------------+     +----------------------+     +----------------------+
| Market & PIT   | --> | Selection            | --> | Decision Support     |
| facts/calendar |     | scope/eligibility    |     | context/portfolio/risk |
+-------+--------+     +----------+-----------+     +----------+-----------+
        |                         |                            |
        | immutable evidence      | datasets/candidate facts   | intents
        v                         v                            v
+----------------+     +----------------------+     +----------------------+
| Research &     | <-- | Outcome/Attribution  | <-- | Execution & Account  |
| Qualification  |     | factual evaluation   |     | fills/positions      |
+-------+--------+     +----------------------+     +----------+-----------+
        |                                                         |
        +---------------- evidence/proof --------------------------+
                              |
                              v
                    +----------------------+
                    | Artifact Store       |
                    | bytes only; PG binds |
                    +----------------------+
```

The seven bounded contexts and one infrastructure boundary remain modules in one
Python process and one PostgreSQL database. They are not microservices.

## Context responsibilities and upstream contracts

| Context | Owns | May consume | Must not own |
|---|---|---|---|
| Runtime & Provenance | schedules, Runs, Steps, Attempts, command receipts, audit, artifact metadata/integrity | all application command results by stable ID | Market facts, decisions, qualifications, Positions |
| Market & PIT | providers, captures, instruments, sessions, classifications, revisions, gaps | raw artifact bytes | Candidates, model assessment, Portfolio |
| Selection | Universe revisions, membership, eligibility; later Candidate Sets | Universe/Eligibility consume only Market/PIT and immutable scope config; Candidate may later consume only actual policy-required Research definitions | Signal, Strategy action, Fill |
| Research & Qualification (`market_regime_alpha.research_qualification`) | initially Decision-input Dataset/DatasetSource/FeatureDefinition; later targets, partitions, experiments, models, evaluation, evidence, assessment, qualification | initially Market/PIT and Selection lineage; later Outcomes and Attribution | runtime scheduling, Candidate ownership, physical Position mutation |
| Decision Support | Context assessments, Signal, Forecast, Opportunity, Thesis, Strategy Version, Portfolio/Risk decision | Candidate, Research identities, account query model | observed Fill, broker truth, qualification |
| Execution & Account | account authority epoch, intents, Fills, allocations, broker observations, reconciliation, non-trade basis events | accepted Portfolio/Risk decisions, Market instrument identity | Candidate, Forecast, model promotion |
| Outcome & Attribution | factual Outcomes, observations, metrics, reasons and diagnostic Attribution | Decisions, Market/PIT, Fill allocations | qualification, Decision mutation or Position truth |
| Artifact Store | content-addressed immutable bytes | none | business state, lifecycle, latest pointers |

The business dependency direction is
`Market/PIT → Universe → Eligibility → Candidate → Context → Signal/Forecast → Opportunity → Portfolio → Risk`.
Context cannot feed back into the same Candidate Set, and Opportunity cannot
carry a Risk Decision. The sole Risk Authority follows Portfolio. Candidate is
implemented only after its required Dataset, Feature Definition, or Model
Version identities exist. Candidate Set creation does not require a Decision
Run, Evidence graph, Assessment, or Qualification; a later Decision Run must
reference an already-existing Candidate Set.

## Allowed dependency direction

Within each context:

```text
domain <- application -> ports <- infrastructure adapters
                         ^
                         |
                    composition root
```

- Domain imports only the standard library and `shared` value types.
- Application imports its own Domain and declared ports.
- PostgreSQL, clocks, providers, artifact clients, CLI, and logging implement ports.
- Cross-context writes are application commands, never repository imports.
- Cross-context reads use stable query DTOs or IDs and cannot mutate the source.
- The composition root is the only place allowed to assemble every context.
- No package named `legacy`, `v1`, `v2`, `v3`, `registry`, or `snapshot` is a permanent architectural boundary.

Detailed target design is in
[Canonical Overall Design](docs/architecture/Canonical-Overall-Design.md).
