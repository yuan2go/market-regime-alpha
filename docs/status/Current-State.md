# Current State

> **Status:** CURRENT_STATUS  
> **Authority:** Current implementation/evidence summary  
> **Repository Baseline:** `main@fc373696990ccdffe5e46a39778fdfedac3e0308`
> **Strongest Research Evidence Revision:** `0d1a5a8` (WP-ALPHA-RESEARCH-01)
> **Last Updated:** 2026-08-21
> **Code Evidence:** `src/market_regime_alpha`, `src/market_regime_alpha/persistence/postgres/migrations/*.sql`, `tests`

This document records what the named executable baseline implements and what
its evidence actually supports. It does not inherit stronger claims from the
target architecture.

## 1. Repository baseline

- **Architecture:** Python 3.12+ PostgreSQL-centered modular monolith.
- **Persistent business authority:** PostgreSQL 16; no canonical file/SQLite/memory fallback.
- **Packaged migration head:** 091 (`alpha_research_phase_ii`).
- **Canonical all-day runtime:** one Continuous Research control plane.
- **Installed operator scripts:** six — `continuous-research`, `state-system`, `decision-system`, `model-governance`, `pit-authority`, `research-shadow`.
- **Execution boundary:** human-operated/manual; no broker writer or automatic live-trading authority.
- **Physical Position truth:** observed effective manual Fills.
- **Golden Loop V2 execution:** one immutable 126-session historical campaign at evidence revision `bcee87a` completed in an isolated PostgreSQL schema migrated from 084 through 090; exact replay and aggregate Evidence are recorded below.
- **WP-ALPHA-RESEARCH-01 execution:** one final immutable 126-session methodology-only owner replay at revision `0d1a5a8`; run `historical-research-run-0e150a21c7869adc84a57af5`, exact report/replay and five PostgreSQL Evidence artifacts are complete.
- **Current main validation:** PR #72 records local full-suite, documentation,
  platform, ruff, mypy and build success for the merged WP-ALPHA-RESEARCH-01
  tree. No GitHub Actions run exists for merge commit `fc37369`; CI supplies no
  qualification for this exact merge baseline.
- **WP-01 branch validation:** docs/platform/full pytest, ruff, mypy and build pass on a fresh PostgreSQL test database; a first full run against a heavily reused test database hit one `pg_catalog` autovacuum DDL lock timeout, while the exact node and the clean-database full suite both pass. This is retained as an environment failure, not hidden.
- **Current CI:** exact-merge CI is `NOT_RUN`, not CI proof.
- **Alpha Research Phase II engineering:** all five Work Packages are
  implemented with focused unit/boundary tests and targeted PostgreSQL
  migration/materializer proof. This is code/wiring evidence, not a new
  historical research result.
- **Database binding:** Runtime requires an explicit PostgreSQL URL and principal; a database name or stale schema does not establish current Authority. The replayable Golden V2 Evidence schema is at migration 090.
- **Local implementation baseline:** Python 3.12.13, uv 0.11.7 and PostgreSQL
  16.14. The packaged migration head is 091. A Golden V2 evidence database is
  at migration 090; the default local application database is only at 055 and
  is not evidence for the current schema.

## 2. Implemented engineering boundary

### Runtime and Authority

The repository has one canonical all-day runtime with PostgreSQL schedule/journal ownership, bounded child execution, leases/fences/recovery semantics and operational inspection. Historical Research is a bounded multi-session runner that reuses the same business/strategy semantics and PostgreSQL owners rather than a second daily architecture.

### Data, PIT and research datasets

The system has recorded BaoStock/Tencent/public-provider evidence, source freeze, canonical market-data datasets, feature materialization, historical corpus owners, effective-dated historical constituent/security facts, selective Parquet reads, Historical Research journaling and replay.

Formal PIT **mechanics** exist, including source/fact qualification, time-aware owners, frozen protocols and as-of validation. Current free-provider evidence does not satisfy the Formal PIT floor.

### State and opportunity pipeline

The canonical chain contains:

```text
Dataset / Feature
→ Market Regime / ETF / Theme / Capital State
→ StateSeries / Dynamic Pool
→ Candidate
→ Signal
→ Path Forecast
```

These artifacts are wired and persisted. Their empirical value is not assumed from their engineering existence.

### Multi-strategy runtime

The current Strategy Registry/runtime has stable `OVERNIGHT` and `SWING_STATE` Strategy Versions under one shared Strategy runtime. It records gate/rejection attribution, actions/proposals, simple cross-strategy Portfolio decisions, strategy Fill allocations, Path Outcomes and version-scoped feedback.

Candidate is upstream of strategy action; the canonical multi-strategy path no longer treats Candidate itself as Entry.

Strategy Contract V2 now explicitly declares `FORECAST_REQUIRED` or
`FORECAST_NOT_REQUIRED`. Existing Overnight/Swing Strategies declare the latter.
The new conditional-prediction family consumes a symbol-level binding containing
Signal, Forecast, Context, Risk state and Model/version references, active
Signal state, expected return and uncertainty. Missing required lineage fails
closed; no Candidate-only fallback remains for a Forecast-required Strategy.

### Alpha Research Phase II capability

- Independent correctness recomputes the three discovered intraday Factors
  directly from normalized bars and independently reconstructs the exact
  Decision reference plus next-session 10:30 Target. Value, event interval,
  source-bar identity/hash and Feature/Target lineage discrepancies fail closed.
- Physical bytes are not currently reopenable. Deterministic owner replay is
  therefore retained as owner evidence only and the real status remains
  `PHYSICAL_REPRODUCTION_NOT_ESTABLISHED`.
- Five content-addressed placebo kinds, explicit research/execution entry
  proxies, factor correlation/rank/leave-one-out/incremental/residual diagnostics
  and moving-block/block-length/stability inference use the Research Validation
  framework.
- External Validation reuses canonical `ResearchExperimentDefinition`; the
  definition freezes the exact hypothesis and permits exactly one Temporal,
  Universe or Provider change. No external dataset was executed.
- Context evaluation enforces session-constant versus within-session
  cross-sectional semantics. Market Regime and current Global Theme are
  session-level roles in the observed WP-01 panel; Capital remains a public
  proxy and is not hidden-intent evidence. Cross-sectional Capital interaction
  remains `NOT_ESTIMABLE` without genuine symbol-level variation.
- Candidate Policy V2 keeps Incumbent and dormant Challenger identities
  separate, with Universal Integrity, factor-specific availability, validated
  Alpha contributions and evidence-supported Context adjustment.
- Conditional Forecast keeps the empirical distribution baseline and compares
  a frozen regularized-linear model under chronological sample admission,
  minimum sample, search budget and uncertainty rules. Barrier outputs remain
  raw scores; `CALIBRATED=false`.

Migration 091 extends the existing append-only Historical Evidence and Strategy
owners. It creates no new table or parallel Authority.

### Manual execution and Position

Accepted cross-strategy Portfolio lines may enter the existing manual execution ledger through exact Strategy/Portfolio/account lineage. The current engineering path supports aggregate Proposal authority, account cash/available-sell checks, A-share lot/T+1 constraints, owner-resolved decision-time price/account facts, partial/corrected observed Fills, physical-position reprojection, strategy sleeves and realized Strategy Outcome supersession.

This is manual-execution correctness. It grants no broker authority and proves no Alpha.

### Outcome, evaluation and governance

The repository includes factual Shadow outcome settlement, Panel/Evaluation datasets, factor extraction, ablation/calibration/formal-evaluation mechanics, Strategy Shadow, Portfolio Shadow, multi-period performance/attribution, qualification owners, Model Governance, RBAC/approval/audit engineering and blocked Production Admission/Controlled Execution gates.

Most formal qualification capability is **engineering-ready but evidence-blocked**.

## 3. Research evidence that exists today

The strongest real historical work remains exploratory and PIT-incomplete.

WP-ALPHA-RESEARCH-01 reused the Golden V2 dataset scope without using its
result as an Alpha baseline. Panel v2 now preserves all 70 canonical Feature
outputs, Candidate state/rank/score/rejection reasons and hard/predictive Gate
diagnostics. Forty-nine numeric factors, 12 Gate variants and five Candidate
policies were evaluated under one 62-hypothesis BH-FDR family.

The frozen discovery result is positive but not qualified Alpha:

- `HARD_INTEGRITY_PRICE_RETURN` has mean RankIC 0.090809, BH-FDR 3.77e-7,
  Top-5 gross 0.016907, frozen assumed-cost net 0.014807, turnover 0.8368 and
  positive Q1/Q2/nine-session-Q3 RankIC. It is the only Candidate policy that
  passes the frozen exploratory discovery rule.
- The individual positive results are intraday return-to-DecisionTime, VWAP
  slope and price-versus-VWAP. Their effects are large, related, high-turnover,
  retrospective-event-time and not externally validated.
- Current Hard Chain still rejects 37,319/37,319 post-integrity rows and is
  `NOT_ESTIMABLE`; Signal, Forecast, Strategy economics and Portfolio
  performance therefore remain unproven/`NOT_ESTIMABLE`.
- Market Regime, Theme and Capital have zero within-session mixed populations;
  Dynamic Pool passes every integrity row and is integrity-confounded. All four
  Gate dispositions are `RETEST`, not `KEEP_AS_HARD_GATE`.
- The final Alpha Evidence is
  `historical-evidence-f9326f869186419a89e450b9@sha256:f9326f869186419a89e450b9b64923046a30677d4c3c0003f1f12060388c1fe6`
  and remains `EXPLORATORY / PIT_INCOMPLETE / IN_SAMPLE_DISCOVERY /
  UNQUALIFIED`.

The initial WP-01 run `a09d…a8d` and its Alpha Evidence are retained as
`METHODOLOGY_INVALIDATED / SUPERSEDED`: temporal Gate subsetting had been
misread as incremental lift and the persisted Candidate registry omitted the
implemented no-Gate control. The final protocol requires matched-session Gate
contrasts and explicitly supersedes that Evidence.

Golden Loop V2 now has an immutable 126-session campaign over the existing
Phase E3 dataset and unchanged Target, Horizon, Factors, gates, Forecast floor,
cost assumptions and canonical Portfolio policy. The shared exact-rational
midrank kernel removes symbol/observation identity from ranking, uses a separate
fractional boundary policy, and persists session evaluation from the canonical
Multi-Strategy Cycle, Cross-Strategy Portfolio, Outcome and Attribution owners.
The bounded run completed after resume with 756 receipts and 1,764 components;
its exact replay is recorded in the V2 campaign report.

The V2 result is negative rather than an Alpha proof:

- Price-only RankIC is -0.061618, Top-10 gross -0.000839, assumed cost
  0.002100 and net -0.002939.
- Adding Volume improves Top-10 gross by only +0.000041; the resulting RankIC
  remains -0.059226, spread -0.001937, net -0.002899 and drawdown -0.457415.
- Market Regime and Theme are ranking-neutral in this corpus; ETF and Capital
  are `NOT_ESTIMABLE`; Dynamic Pool changes RankIC in three non-constant
  sessions but changes neither Top/Bottom boundary exposure nor gross return.
- Candidate rejects all 37,800 rows, so Signal and Forecast coverage are both
  0/37,800. Canonical Portfolio therefore records 126 `NO_ACTION` sessions and
  no lines; Strategy and Portfolio economics are `NOT_ESTIMABLE`, not zero.
- Direct Candidate-owner audit attributes the first failing reason to Capital
  for 15,595 rows, Market Regime for 14,978, Theme for 7,199, Dynamic Pool for
  22 and base Liquidity for 6. These counts diagnose owner data only; WP-01
  Panel/Evidence now preserves them without treating sequential first failure
  as isolated Gate lift.
- V1 Phase E2/E3 ranking conclusions and the first finite-Decimal V2 result are
  retained immutably but explicitly methodology-invalidated/superseded. The
  earlier Phase E2 positive Portfolio interpretation is no longer admissible;
  no replacement V2 Phase E2 estimate was manufactured.

Phase E / E2 / E3 established replayable real historical research runs, including a 300-stock CSI 300 cross-section and a 126-decision-session longitudinal campaign with effective-dated cohort owners and real historical market/reference evidence.

The durable findings do **not** establish general Alpha:

- the pilot/full-chain T+1 economics remained net negative after the declared engineering-assumption cost model;
- Phase E2's six T+1 checkpoint diagnostics remain historical V1 research, not
  Canonical Strategy/Portfolio Evidence;
- the exact-rational Phase E3 rerun remains negative and retains severe
  downstream sample starvation when the frozen ETF context has no observations;
- prior Phase E2/E3 layer-by-layer lifts computed with identity-broken ranking
  are superseded; current V2 evidence supports zero boundary/economic increment
  for Market Regime, Theme and Dynamic Pool in this scope, not the old signed
  layer claims;
- Candidate/Signal/Forecast were not demonstrated as economically useful by that evidence, and downstream Forecasts remained `NOT_ESTIMABLE` where sample/conditioning floors were not satisfied;
- an exploratory ridge challenger produced limited positive validation diagnostics in the pilot, but it is not Formal OOS, calibrated, economically qualified or Production-admitted.

The correct current conclusion is:

> The platform can produce and replay serious quantitative research evidence, including negative evidence. It has one exploratory Candidate challenger worth separately frozen external validation, but has not established trustworthy Formal OOS Alpha or an executable strategy edge.

## 4. Evidence ceiling

At this baseline:

```text
FORMAL_PIT_ESTABLISHED              = false
FORMAL_OOS_ALPHA_ESTABLISHED        = false
CALIBRATED_PROBABILITY_ESTABLISHED  = false
SUSTAINED_PROSPECTIVE_SHADOW_PROVEN = false
RESEARCH_QUALIFIED_ALPHA            = false
PRODUCTION_QUALIFIED                = false
BROKER_INTEGRATION_PROVEN           = false
```

Operational release declarations remain explicitly closed:

```text
automatic_order_execution = false
broker_integration_proven = false
entry_model_empirically_validated = false
production_ready = false
```

Free/public historical evidence remains, as applicable:

```text
EXPLORATORY
PIT_INCOMPLETE
UNQUALIFIED
FORMAL_OOS=false
CALIBRATED=false
```

## 5. Architectural assessment

### Healthy and preserved

- PostgreSQL-only canonical business authority.
- Modular-monolith deployment model.
- One top-level daily control plane.
- Fill-derived physical Position.
- Historical/Replay/Shadow semantic convergence.
- Exact identity/hash/lineage for result-affecting research owners.
- Fail-closed qualification and durable negative/`NOT_ESTIMABLE` evidence.

### Mature enough to freeze unless a real failure is found

- new Authority abstractions;
- new Receipt/Evidence hierarchies;
- new generic Policy/Protocol frameworks;
- new qualification states;
- new orchestration/control planes.

The infrastructure/governance surface is materially more mature than the empirical Alpha/Strategy evidence.

### Still needs active simplification

- legacy Strategy/Portfolio simulation shapes that still have qualification/replay consumers;
- compatibility readers and old runtime/application seams, retired only after consumer inventory and differential replay proof;
- overlapping Candidate/Signal/Forecast concepts if empirical work shows no distinct information/policy/consumer value.

## 6. Current primary bottleneck

The dominant bottleneck is no longer basic software architecture. It is:

```text
Data/PIT evidence quality
+
Alpha discovery / factor information
+
Strategy translation to executable net economics
+
Prospective proof
```

Engineering gaps remain, but they should be selected because they unblock this evidence loop rather than because another platform layer can be designed.

## 7. Current development posture

The engineering implementation for all five Phase II Work Packages is complete.
Its three unusually strong intraday discovery results have not been reclassified
as Alpha because the physical package cannot currently be reopened and no new
external dataset was run.
The registered physical normalized-data package is unavailable locally, so the
current physical reproduction status is
`PHYSICAL_REPRODUCTION_NOT_ESTABLISHED`; PostgreSQL owner reuse does not upgrade
that status.

The next empirical dependency order remains:

```text
WP-ALPHA-CORRECTNESS-01
→ WP-ALPHA-RESEARCH-02
→ WP-ALPHA-CONTEXT-01
→ WP-CANDIDATE-POLICY-02
→ WP-PREDICTION-01
```

No new External Dataset, large historical Campaign or prospective cohort was
run in this implementation phase. Until separately executed evidence exists,
external validation, Formal OOS, prospective proof, Strategy qualification and
Production qualification remain false.

The repository now moves through the **Alpha Proof Campaign**:

```text
Golden Strategy Question
→ transparent quantitative baseline
→ factor/context ablation
→ Strategy/Portfolio economics
→ immutable prospective Shadow
→ Outcome / Attribution
→ diagnosis
→ next evidence-driven engineering/research change
```

Multi-strategy capability remains part of the target platform, but the next empirical program should first make one Golden Vertical Slice trustworthy from decision-time evidence through outcome and attribution.

See:

- `docs/architecture/Canonical-Overall-Design.md`
- `docs/status/Capability-Matrix.md`
- `docs/status/Gap-Register.md`
- `docs/status/Roadmap.md`
- `docs/research/Negative-and-Inconclusive-Results.md`
