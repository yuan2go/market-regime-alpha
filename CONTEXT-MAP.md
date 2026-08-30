# Market Regime Alpha Context Map

> **Status:** CANONICAL_TARGET_ARCHITECTURE
> **Authority:** Target bounded-context vocabulary and dependency map
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-30

This file defines Target names and relationships only. Current implementation
truth and checkpoint evidence remain in code, PostgreSQL, tests actually run,
[Current State](docs/status/Current-State.md), and the linked Verification
records.

## Ubiquitous language

| Term | Canonical meaning | Explicitly not |
|---|---|---|
| Market Fact | A provider-sourced observation normalized without losing source, temporal, price-basis, revision, or capture identity. | A latest-value cache or provider response payload. |
| Known Time | Earliest instant at which the exact normalized revision was legitimately usable by this system. | Event time, provider time, or a reconstructed historical guess. |
| Universe Revision | Immutable, decision-time-resolvable membership scope with every included, excluded, and unknown symbol accounted for. | A current constituent list used retrospectively. |
| Eligibility Assessment | Per-instrument policy result at one decision time: `ELIGIBLE`, `INELIGIBLE`, or `UNKNOWN`, with typed reasons and evidence. | Candidate selection or a silent filter. |
| Decision-input Dataset | Immutable content-addressed Feature input whose rows exactly reconcile the same-DecisionTime `INCLUDED` and `ELIGIBLE` population, with explicit missing cells and exact lineage. | An Evaluation Dataset, Target/Outcome container, or posterior-label panel. |
| Feature Definition | Immutable calculation semantics, type/unit, temporal window, source, availability, missingness, and algorithm/code/config identity. | Alpha evidence, research maturity, external validation, or qualification. |
| Candidate | The immutable terminal disposition for one row of a Decision-input Dataset under one Candidate Policy: `SELECTED`, `RANKED_NOT_SELECTED`, or `UNRANKABLE`, with complete typed score-component facts. | Only the selected subset; a probability, Forecast, Target, Outcome, Entry, or trade recommendation. |
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
| facts/calendar |     | scope/eligibility/   |     | context/portfolio/risk |
|                |     | candidate            |     |                      |
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
| Selection | Universe revisions, membership, eligibility, Candidate Policy/Set/Candidate and typed Candidate Score Components | Universe/Eligibility consume only Market/PIT and immutable scope config; Candidate consumes the immutable Decision-input Dataset and policy-bound Feature Definitions through a Selection-owned DTO/port implemented by Infrastructure | Signal, Strategy action, Fill, Model, Target, Outcome, Evidence, Qualification |
| Research & Qualification (`market_regime_alpha.research_qualification`) | initially Decision-input Dataset/DatasetSource/FeatureDefinition; later owners only in an order approved after Candidate dependency audit | initially Market/PIT and Selection lineage; later inputs remain subject to dependency review | runtime scheduling, Candidate ownership, physical Position mutation, a second realized-label truth beside Outcome |
| Decision Support | Context assessments, Signal, Forecast, Opportunity, Thesis, Strategy Version, Portfolio/Risk decision | Candidate, Research identities, account query model | observed Fill, broker truth, qualification |
| Execution & Account | account authority epoch, intents, Fills, allocations, broker observations, reconciliation, non-trade basis events | accepted Portfolio/Risk decisions, Market instrument identity | Candidate, Forecast, model promotion |
| Outcome & Attribution | factual Outcomes, observations, metrics, reasons and diagnostic Attribution | Decisions, Market/PIT, Fill allocations | qualification, Decision mutation or Position truth |
| Artifact Store | content-addressed immutable bytes | none | business state, lifecycle, latest pointers |

The Candidate-time business dependency direction is
`Market/PIT → Universe → Eligibility → Candidate → Context → Signal/Forecast → Opportunity → Portfolio → Risk`.
Context cannot feed back into the same Candidate Set, and Opportunity cannot
carry a Risk Decision. The sole Risk Authority follows Portfolio. Candidate V1
depends only on the immutable Dataset and real Feature Definition identities;
it has no Model Version, Target, Outcome, Context, Evidence, Assessment, or
Qualification dependency. The only authorized downstream order is the
dependency-coherent sequence in the
[Implementation Roadmap](docs/status/Roadmap.md); Research never owns a second
realized-label truth beside Outcome facts.

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
