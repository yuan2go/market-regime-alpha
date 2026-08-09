# Pre-Live Engineering Hardening — Design

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Current user request, Constitution, Architecture 09–11, existing bounded-context authorities
> **Baseline:** `origin/main@94c1f99f56deeb5019a9a014f9b752328020f8fd`
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-09
> **Supersedes:** Pre-live portions of `2026-08-09-prospective-formal-qualification-master-design.md`
> **Superseded By:** None
> **Related Documents:** ../plans/2026-08-09-pre-live-engineering-hardening.md, ../../status/Current-State.md
> **Code Evidence:** `src/market_regime_alpha`; `tests`; PostgreSQL migrations 001–033
> **Authority ceiling:** Engineering readiness over exploratory free data. No Live, prospective, Alpha, Formal PIT/OOS, qualification, Production, Entry, Order, Fill, Broker, or Position authority.

## Objective

Make the one Canonical Stateful Free Runtime operable, inspectable, recoverable,
and ready to freeze future prospective decisions before the next real 14:54–14:55
window. Engineering fixtures prove mechanisms only. They never prove a Live run,
a prospective sample, an outcome observation, or Alpha.

## Verified starting facts

- `CanonicalFreeDataResearchComposition` remains the sole executable Continuous
  Runtime composition. The PostgreSQL Continuous Journal owns schedule, Tick,
  Lease/fence, acquisition recovery and owner child references.
- State, Governance, Research Summary V3 and Formal PIT engineering authorities
  are already PostgreSQL-backed and independently replayable.
- The current Continuous report is a limited V1 projection. There is no unified
  preflight, trace, metrics, or Canonical DAG query surface.
- Controlled Operation already owns immutable raw outcome source packages and a
  10:30 factual outcome contract. It does not own a Summary-scoped prospective
  Shadow decision, the requested checkpoint series, or a frozen evaluation
  dataset.
- Current operational ETF/Theme policy is a Free V1 proxy, not a canonical or
  Formal PIT reference authority.

## Authority design

| Fact | Sole owner | Design rule |
|---|---|---|
| Runtime readiness | Preflight projection | Read existing PostgreSQL/config/filesystem facts; grants no authority |
| Trace and metrics | Observability projection | Derive from Journal events, attempts, receipts and Summary; never changes decisions |
| Canonical DAG | Query service | Read existing owners; never recompute a model or Stage |
| Shadow lifecycle | Shadow Research authority | Reference existing Run/Tick/Summary; frozen decision payload is immutable |
| T+1 settlement | Existing factual Outcome bounded context | Add Summary-scoped append-only outcome; raw source archive remains authoritative |
| Evaluation sample set | Evaluation Dataset authority | Content-addressed immutable manifest over frozen decisions/outcomes |
| ETF/Theme reference | Reference Data authority | Effective-dated, source-bound, explicitly exploratory/unqualified facts |
| Recovery proof | Disaster-recovery operation | PostgreSQL archive plus immutable Artifact inventory, isolated restore and replay |
| Verification result | Engineering verification Artifact | SHA-bound machine-readable local/CI result; never a capability or Alpha claim |

## Invariants

- No second Runtime, acquisition Journal, State System, Governance Registry,
  Evidence authority, factual Outcome authority, or research evaluation truth.
- Preflight, trace and query are read-only projections. Their output never enters
  model selection or business decisions.
- A Shadow decision can be invalidated but never edited after `FROZEN`.
  `decision_frozen_at < outcome_available_at` is enforced for settlement.
- Outcome settlement is append-only and idempotent. A conflicting second payload
  fails closed; no outcome field can alter a T decision.
- Evaluation datasets accept only frozen Shadow decisions and settled outcomes.
  Inclusion/exclusion and missing samples are explicit and hashed.
- Reference records require effective time, availability time, source lineage and
  declared evidence level. Free V1 remains exploratory and cannot emit Formal PIT.
- Research/Shadow creates no Order, Fill, Broker call or Position mutation.

## PostgreSQL additions

Migrations are additive and dependency-ordered:

1. `034_shadow_research_authority.sql` — Shadow Session/Decision/event state,
   immutable frozen lineage and CAS versioning.
2. `035_prospective_outcome_authority.sql` — append-only Summary-scoped factual
   outcome index bound to the existing raw source archive.
3. `036_evaluation_dataset_authority.sql` — immutable content-addressed dataset
   manifest index.
4. `037_etf_theme_reference_authority.sql` — effective-dated ETF/Theme reference
   Artifacts and immutable source lineage.

## Operational surfaces

The existing `continuous-research` entry remains the Runtime owner. It gains
`preflight`, `inspect-*`, `trace` and `metrics` operations. Separate bounded
administration commands may freeze Shadow decisions, settle outcomes, materialize
evaluation datasets, publish reference Artifacts, and verify disaster recovery;
none can execute the Canonical research decision.

## Exit gates and non-claims

Each work package exits only after real PostgreSQL tests cover identity,
idempotency, conflict/CAS, historical reads, recovery/replay and forged lineage.
The aggregate exit state is `ENGINEERING_READY` if configuration-specific
Preflight is READY and all engineering gates pass. Regardless of fixture tests,
the following remain false until separately observed: `LIVE_PROVEN`,
`PROSPECTIVE_PROVEN`, `ECONOMICALLY_VALIDATED`, and `PRODUCTION_AUTHORIZED`.

Rollback is forward repair: additive tables can remain unused; immutable rows are
never deleted or rewritten. External market time is a blocker only for WP-LIVE-01,
not for these engineering mechanisms.
