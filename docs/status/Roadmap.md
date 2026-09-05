# Architecture Re-foundation Implementation Roadmap

> **Status:** ROADMAP
> **Authority:** Planning and dependency order only; never business, evidence or qualification Authority
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-09-05
> **Code Evidence:** `src/market_regime_alpha`, `tests/refoundation`, `docs/status/Current-State.md`

Architecture Re-foundation is the sole engineering program. This document
contains the current gap register; historical research and Verification remain
immutable provenance. The current qualification result is recorded in
[WP-18Q Final Closure Verification](../references/WP-ARCHITECTURE-REFOUNDATION-18Q-Final-Closure-Verification.md).

## Dependency sequence

```text
Foundation -> Market/PIT -> Selection Core -> Research Definition -> Candidate
-> Target commitment / Decision Run -> Market Target Outcome
-> WP-11 Partition / Experiment / Evaluation -> WP-12 Evidence / Qualification
-> WP-13 Decision Support -> WP-14 Formal Research engineering readiness
-> WP-15 rejected real Provider gate -> WP-16 external-evidence blocker
-> WP-17P separated archives and bounded exploratory Model/backtest proof
-> WP-18 prospective / walk-forward definition
-> WP-18Q Generic Platform and prospective qualification closure (ACTIVE, BLOCKED)
-> optional separately justified Calibration
-> separately authorized Execution / TradeOutcome / Attribution
-> explicit Runtime/CLI cutover -> separately authorized Legacy deletion
```

WP-15/WP-16 negative evidence is not a prerequisite waiver. WP-17P and WP-18Q
operate only in the explicitly separated exploratory lane. No future item
receives authority from its position in this sequence.

## Preserved predecessor results

| Checkpoint | Bound result |
|---|---|
| Foundation through Candidate, WP-09/10 | Prior local engineering proofs retained; exact records are indexed by [Documentation Authority](../README.md) |
| WP-11 / WP-12 / WP-13 | Partition/Evaluation, Evidence/Qualification and Decision Support engineering checkpoints; no empirical promotion |
| WP-14 | Formal Research engineering readiness only; no qualified Provider, PIT/OOS or prospective value |
| WP-15 | Recorded BaoStock scope rejected; no downstream Formal campaign admitted |
| WP-16 | External availability/finality evidence unavailable; no replacement Provider claim |
| WP-17P | Historical engineering-qualified two-lane archive and bounded campaign at `5cc3831e93fa30a58283471e2185bbad5c72cec3`; not current Generic qualification |
| WP-18 | Approved prospective and four-arm multi-fold specification; historical equivalence is definition-only |
| WP-18Q | Implemented Generic surfaces under qualification; exit remains `BLOCKED` |

## Current P0 closure

Follow the approved
[WP-18Q Design](../references/WP-ARCHITECTURE-REFOUNDATION-18Q-Reusable-Backtest-Platform-Design.md)
and [Implementation Plan](../references/WP-ARCHITECTURE-REFOUNDATION-18Q-Reusable-Backtest-Platform-Implementation-Plan.md).
Freeze architecture. Do not add a root, bounded context, Runtime, registry,
second metric truth or compatibility facade.

| Gate / dependency | Concrete remaining boundary |
|---|---|
| Operational identity | Locate the current exact operational DB/OID and Artifact root. A restored copy and an old dump do not attest to current operational state |
| Real campaign source | Restore access to the canonical 40-session qualification archive and exact source-capture lineage; isolated raw objects/manifest cannot substitute |
| Track A continuity | Finish/qualify the existing Runtime call chain for generation roll-forward, PostgreSQL due selection, planning gaps, overdue terminalization, lease recovery and unknown-effect reconciliation; no second scheduler |
| Real prospective Attempt | At execution time inspect PostgreSQL clock and actual due windows first; execute an available due Runtime claim with an honest terminal result. If no real window exists, record NOT_DUE and the temporal blocker without waiting or backdating |
| Track C campaign | Freeze >=40 actual sessions, deterministic 32-symbol roster, >=2 explicit FIT-to-VALIDATION dependencies and four rule/ridge arms with shared comparison-compatible Portfolio/Risk/Cost before validation access |
| Canonical metrics/report | Complete canonical Evaluation, preserve NOT_ESTIMABLE reasons, publish deterministic content-addressed JSON/Markdown and derive funnel diagnosis; never reread bars in reports |
| Exact resume/replay | Inspect/resume/replay the same frozen campaign to zero mismatches; completed actions and every canonical/Artifact identity remain unchanged |
| Operational upgrade | Exact OID/checksum/disk/readable pg_dump/no conflicting Attempt preflight, additive-only upgrade and preservation/reconciliation on the original operational database |
| Hard cut | Delete WP-specific execution only after WP-17P zero-write, WP-18 definition-only, fresh generic executions, real campaign/report/replay and full regression all pass |
| Exit decision | Clean exact-SHA gate and immutable Verification, then reconcile current documentation; any failed/missing P0 proof keeps BLOCKED/NO-GO |

The 2026-09-05 closure repaired historical name compatibility, query join
amplification, stale strict catalog/composition tests and the prospective test
clock. Exact command results belong to the Verification, not this planning page.

## Deferred boundaries

| Work | Rule |
|---|---|
| Provider/PIT | Reopen WP-16 only with new direct purpose-specific external evidence; preserve rejected/unknown facts |
| Model qualification / Calibration | Separate empirical purpose and approved evidence floors required |
| Broker / Execution / Account | Separately authorized observed-fill and reconciliation work; no orders or automatic Position creation |
| Runtime/CLI full cutover / Legacy deletion | Explicit complete consumer, schema and compatibility cutover gate; WP-specific hard-cut is not full Legacy deletion |
| Production | NO-GO; engineering tests and exploratory returns cannot admit Production |

No AutoML, parameter search, post-hoc validation tuning, new model family,
formal OOS experiment, microservice or infrastructure expansion is part of this closure.
