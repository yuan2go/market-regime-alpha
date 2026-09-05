# Current State

> **Status:** CURRENT_STATUS
> **Authority:** Non-authoritative exact-SHA implementation read model
> **Owner:** Market Regime Alpha maintainers
> **Generated At:** 2026-09-05 qualification closure
> **Repository Implementation Checkpoint:** `7818253cda85755175d87ff3acec1b1d8d7af762`
> **Execution-Time Main Baseline:** `66c30e0159b8ce4bb3e17a7fdf1c3cc48dae6167`
> **Schema Epochs:** legacy `LEGACY_MIGRATIONS_001_106`; target `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`
> **Source Tree IDs:** source `a411f63a5534dd91ed4562c9fe87133490d4db51`; tests `8b0c63e5349651f14e583d96a936725498b3d886`; baseline blob `0f40f6d667fc4ecf561162cad4f6434efba9d033`
> **Code Evidence:** `src/market_regime_alpha`, `src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql`, `tests/refoundation`

The active program is WP-18Q qualification closure. Historical WP-17P engineering
success does not qualify the current Generic Platform or today's operational Runtime.

```text
WP18Q_EXIT_GATE = BLOCKED
BACKTEST_PLATFORM = NOT_ENGINEERING_QUALIFIED
Runtime/CLI full cutover = NO-GO
Production = NO-GO
```

Code existence, composition wiring, executed tests, real Runtime evidence and
research validity are distinct. Source/schema/test changes invalidate this snapshot.

## Executable scope

| Area | Current code and bounded evidence |
|---|---|
| Generic Backtest | One `ExploratoryBacktestRun` root with `BacktestSpecification` companion, explicit arm/fold/dependency/cost/Evaluation rosters; Runtime executor and canonical actions wired in `bootstrap.py` |
| Dataset through Evaluation | Generic actions call existing Dataset, Candidate, Decision Support, Outcome, Model and Evaluation Applications; a real current 40-session campaign remains unproven |
| Model | Deterministic ridge adapter, completed-FIT, reproducibility and later-validation lineage exist; no Model is qualified |
| Report | Reconciled canonical Evaluation projection, deterministic JSON/Markdown, Artifact binding and comparison exist; no real current campaign report was produced |
| Prospective | Target-aligned manifest, Runtime claims/fences, PostgreSQL clock, planning-gap and overdue commands exist. Generic `run_due` selects manifest windows and does not itself invoke generation roll-forward, planning-gap recording or overdue finalization |
| Historical compatibility | Exact allowlisted WP-17P decoder and Generic inspect/resume/replay; WP-18 compatibility is definition-only |
| Hard cut | WP-specific executors and exports remain because real campaign/report/replay prerequisites have not passed |
| Legacy | Existing business Runtime and 001–106 migrations remain; CONTINUOUS_RESEARCH is the all-day Runtime; no full cutover |
| Evidence ceiling | WP-15 rejection and WP-16 external-evidence blocker remain unchanged; no new Provider, PIT/OOS, Alpha, trading or Production claim |

## Exact PostgreSQL catalog

Independent clean qualification observes **192 tables, 4 views, 1,364 indexes,
1,834 constraints and 386 non-internal triggers**. Views are not tables.
The draft bootstrap and exact additive operational bundles serve distinct
operations. Existing evidence databases never enter recreate or test teardown.

```text
baseline SHA256   aae59a527154fd19da4bf07a0402d353d2b02a8da56cef6c4a505509683c412b
catalog SHA256    a61a4ed2a4ae93521942053c37ab6560386bc49c43e64ef3a03f21ab4ab14a71
seed SHA256       9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11
vocabulary SHA256 d08800892f5e843a756f53e46205dfbb2787386ebf8281564c31049c45659a1b
```

## Actual evidence access

The accessible historical database `mra_wp18q_closure_history_20260905`
(OID `31313`) is a restored copy, not the original operational database.
Its retrospective archive ends on 2026-01-19. Qualification archive
`94a00500-c867-5ede-bf7d-886fbbd5fcaf` is absent. Separate raw objects and
a manifest cannot replace missing canonical source-capture Authority.

PostgreSQL inspection at 2026-09-05 09:10 UTC found no current generation,
planning-gap or active Attempt rows in the restored copy. Its prospective
snapshot has zero due windows. The Verification records elapsed and future
windows separately. A historical smoke capture is not a new Runtime proof.
Current original operational state is unavailable.

The exact additive upgrade was rehearsed on a newly restored copy with backup
verification and before/after preservation. This is not an upgrade qualification
for the absent original database.

## Qualification and re-entry

[WP-18Q Final Closure Verification](../references/WP-ARCHITECTURE-REFOUNDATION-18Q-Final-Closure-Verification.md) records final commands, database identities, query plans,
historical zero-write proof, retained failures and blockers. Remote Actions is
disabled according to the current GitHub API:
`BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`.

Re-entry requires the exact operational connection and Artifact root, canonical
qualification archive/source lineage, existing Runtime continuity wiring and an
available real due window. Freeze the campaign before validation Outcome access;
retain WP-specific execution until every hard-cut prerequisite passes.
Follow [Roadmap](Roadmap.md).

```text
RETROSPECTIVE = EXPLORATORY_RETROSPECTIVE
FORMAL_PROVIDER = BLOCKED
FORMAL_PIT = BLOCKED
FORMAL_OOS = NOT_RUN
PROSPECTIVE_PROVEN = NO
ALPHA_PROVEN = NO
MODEL_QUALIFIED = NO
```

[WP-17P Verification](../references/WP-ARCHITECTURE-REFOUNDATION-17P-Prospective-Archive-Exploratory-Backtest-Verification.md),
[WP-15 Verification](../references/WP-ARCHITECTURE-REFOUNDATION-15-Formal-Research-Proof-Campaign-Verification.md)
and [WP-16 Verification](../references/WP-ARCHITECTURE-REFOUNDATION-16-Real-Provider-Evidence-Gate-A-Verification.md)
remain immutable.
