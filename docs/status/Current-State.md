# Current State

> **Status:** CURRENT_STATUS  
> **Authority:** Current implementation/evidence summary  
> **Implementation Checkpoint:** `main@1a92ee41b02dd94df9ef4488c59cba55df4674ce`; WP-ALPHA-CORRECTNESS-02 design on `agent/wp-alpha-correctness-02`
> **Strongest Research Evidence Revision:** `3b58c2a5e374e413fa6fb934ccfe284f39740a40` (WP-ALPHA-PROOF-02 execution)
> **Last Updated:** 2026-08-26
> **Code Evidence:** `src/market_regime_alpha`, `src/market_regime_alpha/persistence/postgres/migrations/*.sql`, `tests`

This document records what the named executable baseline implements and what
its evidence actually supports. It does not inherit stronger claims from the
target architecture.

## 1. Repository baseline

- **Architecture:** Python 3.12+ PostgreSQL-centered modular monolith.
- **Persistent business authority:** PostgreSQL 16; no canonical file/SQLite/memory fallback.
- **Packaged migration head:** 104 (`historical_outcome_forecast_fk_index`).
- **Canonical all-day runtime:** one Continuous Research control plane.
- **Installed operator scripts:** six — `continuous-research`, `state-system`, `decision-system`, `model-governance`, `pit-authority`, `research-shadow`.
- **Execution boundary:** human-operated/manual; no broker writer or automatic live-trading authority.
- **Physical Position truth:** observed effective manual Fills.
- **Golden Loop V2 execution:** one immutable 126-session historical campaign at evidence revision `bcee87a` completed in an isolated PostgreSQL schema migrated from 084 through 090; exact replay and aggregate Evidence are recorded below.
- **WP-ALPHA-RESEARCH-01 execution:** one final immutable 126-session methodology-only owner replay at revision `0d1a5a8`; run `historical-research-run-0e150a21c7869adc84a57af5`, exact report/replay and five PostgreSQL Evidence artifacts are complete.
- **PR #74 closure validation:** the closure branch ran the directly relevant
  Raw/Alpha correctness, Temporal window, Strategy Opportunity, typed resolver,
  Daily Alpha, Continuous FreeData, automatic settlement, migration and
  architecture tests. Focused application/unit/owner groups pass. PostgreSQL
  stateful Continuous and Daily Alpha suites pass. The migration suite applied
  001–096 and passed all 24 test bodies; targeted migration/owner tests then
  applied 001–097 and passed. The earlier full migration run's final
  host-schema teardown reported
  one PostgreSQL `max_locks_per_transaction` environment error. This is
  `TARGETED_TESTED`, not campaign or Alpha evidence.
- **WP-01 branch validation:** docs/platform/full pytest, ruff, mypy and build pass on a fresh PostgreSQL test database; a first full run against a heavily reused test database hit one `pg_catalog` autovacuum DDL lock timeout, while the exact node and the clean-database full suite both pass. This is retained as an environment failure, not hidden.
- **Current WP-ALPHA-CORRECTNESS-02 checkpoint:** documentation and ADR only.
  Business code, migration, Target owners, correctness Evidence and Discovery
  rerun are `NOT_STARTED / NOT_RUN`; prior local or CI results do not prove this
  future implementation.
- **Alpha/Daily engineering closure:** merged `main` binds one explicit Candidate
  admission root to Discovery→Correctness→External→supported Context→Candidate
  lineage, produces
  pre-Strategy Risk/Opportunity from owner-derived facts, projects typed
  Forecast semantics, binds Outcome to an exact immutable Daily snapshot and
  retains settlement inside the one Continuous control plane.
- **Database binding:** Runtime requires an explicit PostgreSQL URL and principal; a database name or stale schema does not establish current Authority. Audit tooling must discover application schemas and columns from packaged migrations and PostgreSQL catalogs rather than infer them from a database name.
- **Local implementation baseline:** Python 3.12.13, uv 0.11.7 and PostgreSQL
  16.14. The packaged migration head is 104. Historical local evidence schemas
  at older migration heads remain provenance only and are not the current
  Runtime schema.

### WP-ALPHA-PROOF-02 terminal research result

- The approved frozen protocol was executed without changing its windows,
  target, three higher-is-better factor directions, Top-5, cost, inference,
  multiple-testing or stopping rules.
- A new immutable reacquired corpus contains 134,134 Daily and 6,414,384 5m
  bars from 2025-01-02 through 2026-08-24 for 338 union symbols. All 1,408
  package files passed checksum verification and independent normalization
  matched all 6,548,518 rows.
- BaoStock remains `RETROSPECTIVE_EVENT_TIME /
  HISTORICAL_AVAILABLE_TIME_NOT_PROVIDED / PIT_INCOMPLETE`. The frozen Locked
  roster remains label-blind and `LOCKED_OOS_CONSUMED=false`.
- Discovery run `historical-research-run-0382e3c92084432a7d7b9c36` completed
  126/126 sessions and exact replay matched. The frozen challenger produced
  mean RankIC `-0.0911379`, Top-5 gross `-0.00089056` and assumed-cost net
  `-0.00299088`; the adverse pre-registered direction is `REJECTED`.
- Independent correctness proof `alpha-correctness-proof:9196bf13...` is
  `CORRECTNESS_FAILED`: eight of 37,800 persisted Targets have
  `PERSISTED_TARGET_SOURCE_NOT_REPRODUCIBLE`. Missing and corporate-action
  cases remain explicit rather than fabricated.
- External Validation was not admitted. Candidate activation, Conditional
  Forecast comparison, calibration, Strategy Economics and Portfolio
  qualification are `NOT_ESTIMABLE / BLOCKED_BY_CORRECTNESS`; Strategy and
  Portfolio Discovery evidence are themselves `NOT_ESTIMABLE`.
- Full identities, metrics, performance and the terminal Evidence matrix are in
  `../references/WP-ALPHA-PROOF-02-Execution-Report.md`.
- **Validation:** Fresh/upgrade PostgreSQL checks and the final full regression pass. The fixes
  align stale migration-head fixtures, require an exact typed Calendar owner at
  the CLI seam and remove the last test/data pair for the already-retired
  duplicate visualization backtest; they create no empirical upgrade.

### WP-ALPHA-CORRECTNESS-02 frozen design boundary

- Owner reload of the immutable predecessor campaign located all eight failed
  rows. Three Decision sessions have no five-minute observations; five contain
  an exact 14:55 placeholder with null OHLC. In every row the writer used the
  preceding session's suspended Daily close, while the checker correctly
  rejected that fallback.
- All eight rows retain a complete twelve-bar T+1 09:30-10:30 Raw path. Their
  frozen state is therefore `Decision reference=UNAVAILABLE`, `Outcome
  window=COMPLETE` and Decision-dependent return/MFE/MAE `UNAVAILABLE`.
- [ADR-014](../architecture/decisions/ADR-014-Frozen-Target-Semantics-and-Independent-Correctness.md)
  and the [frozen protocol](../research/protocols/WP-ALPHA-CORRECTNESS-02-Frozen-Protocol.md)
  define the approved revision, compatibility and Discovery-only boundary.
- Current state is `DESIGN_FROZEN / CODE_NOT_STARTED / RERUN_NOT_RUN`:
  `CODE_IMPLEMENTED=false`, `CANONICAL_WIRED=false`,
  `TEST_EXECUTED=false`, `RUNTIME_PROVEN=false`,
  `RESEARCH_QUALIFIED=false`, `PRODUCTION_QUALIFIED=false` for this Work
  Package. The design checkpoint itself creates no owner or research result.
- The predecessor Experiment remains terminal
  `REJECTED / CORRECTNESS_FAILED / NO-GO`. External remains unexecuted,
  Locked OOS Outcomes remain unconsumed and Formal PIT remains incomplete.

### Engineering closure facts

- Daily Alpha accepts one explicit Candidate Policy admission root. PostgreSQL
  reload follows immutable source references through Discovery, Correctness,
  External Experiment/Hypothesis/Dataset, every declared Context Evidence and
  Candidate Policy. Context must bind the same Experiment, External owner,
  typed definition and research-panel Dataset. Missing,
  superseded, negative, inconclusive, mismatched or hash-drifted owners return
  `VALIDATED_CHALLENGER_INACTIVE`; no latest/best-row selection remains.
- Continuous and Historical Opportunity adapters share the same material,
  Risk and Opportunity producer semantics. Each composition root supplies
  explicitly bound owner-derived Account/Reconciliation/Risk configuration.
  Historical PIT-resolves the exact frozen Account/Reconciliation pair for each
  session, resolves its exact Candidate and Dynamic Pool owners, and fails closed
  when those bindings or required liquidity/restriction facts are absent.
  The producer derives `PRE_STRATEGY_RISK_STATE` from typed account, Position/exposure,
  liquidity, restriction, available-quantity, symbol/theme exposure and
  configured Risk-limit facts,
  records `STRATEGY_OPPORTUNITY`, then typed-reloads both before Strategy.
  `COMPLETE_ACCOUNT_RISK_DECISION` remains forbidden as a Strategy input.
- Runtime/Repository construction no longer applies migrations. Explicit
  migrate/bootstrap surfaces own schema change; runtime schema mismatch fails
  closed.
- Daily Alpha distinguishes `PATH_FORECAST` from `CONDITIONAL_FORECAST`.
  Path output projects status, MFE, MAE, quantiles, sample count and calibration
  state from its owner. Conditional output is shown only after exact owner
  reload; an exact insufficient owner retains only its baseline/calibration
  lineage and limitations, while absence is `NOT_AVAILABLE`, never fabrication.
- Migrations 096–097 freeze exact aggregate Candidate/Signal/Forecast and
  Strategy diagnostic references, snapshot ID/hash/run/tick, and the adjacent
  target session under an exact typed Trading Calendar owner. T+1 settlement
  resolves that unique immutable prediction rather than guessing from a date,
  enforces DecisionTime before Outcome availability, appends Outcome without
  rewriting prediction, and fails closed on missing/ambiguous scope. CLI
  delegates orchestration to
  `ContinuousOutcomeSettlementService`.
- `continuous-research historical-phase-ii` is the single resumable operator
  adapter for Correctness, External, Context and Candidate Phase-II operations.
  It delegates to the existing application service and PostgreSQL Evidence
  owner; it is not another Research Runner.

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

Migration 094 defines and the shared runtime now produces the next two owner
facts:

```text
Candidate / Signal / Forecast / Context
→ owner-derived Account / Position / Risk / Liquidity / Restriction facts
→ PRE_STRATEGY_RISK_STATE
→ STRATEGY_OPPORTUNITY
→ Strategy Runtime
```

The producer semantics and typed material resolver are wired in Continuous and
Historical adapters; PostgreSQL typed reload remains mandatory. Historical
execution PIT-selects and produces the same owner facts from the run's frozen
per-session Account/Reconciliation references and exact Risk reference, and
otherwise fails closed;
unknown historical liquidity, ST, suspension or theme facts never receive a
synthetic safe value.
Conditional Strategy
still remains `RESEARCH/SHADOW`, inactive and fail-closed because no real
correctness/external Candidate admission or qualified conditional Forecast
evidence exists.

### Multi-strategy runtime

The current Strategy Registry/runtime has stable `OVERNIGHT` and `SWING_STATE` Strategy Versions under one shared Strategy runtime. It records gate/rejection attribution, actions/proposals, simple cross-strategy Portfolio decisions, strategy Fill allocations, Path Outcomes and version-scoped feedback.

Candidate is upstream of strategy action; the canonical multi-strategy path no longer treats Candidate itself as Entry.

Existing Overnight/Swing Contract V1 identities are preserved and have explicit
runtime semantics `FORECAST_NOT_REQUIRED` without rewriting their stored payloads.
Contract V2 freezes the declaration: `CONDITIONAL_PREDICTION` must be
`FORECAST_REQUIRED`, while any other V2 family must be
`FORECAST_NOT_REQUIRED`. The conditional family consumes a content-addressed,
DecisionTime-available symbol binding containing the exact Strategy Version,
Candidate, Signal, Forecast, Context, Risk state and Model/version references,
active Signal state, expected return and uncertainty. Missing, inactive,
wrong-version or silently ignored lineage fails closed; no Candidate-only
fallback remains for a Forecast-required Strategy.

### Alpha Research Phase II capability

- Independent correctness recomputes the three discovered intraday Factors
  directly from normalized bars and independently reconstructs the exact
  Decision reference plus next-session 10:30 Target. Value, event interval,
  source-bar identity/hash and Feature/Target lineage discrepancies fail closed.
  A content-addressed aggregate proof can emit `CORRECTNESS_SUPPORTED` only when
  the application service reloads the exact Historical Feature/Outcome and
  normalized-data owners, reopens the physical package, reproduces the full
  population and independently rebuilds placebo, redundancy and block-inference
  results. The status still does not mean Alpha.
- Original Raw and Normalized physical bytes are not currently reopenable.
  Their PostgreSQL owners/checksums remain historical facts, but owner replay is
  not physical reproduction. `ORIGINAL_PHYSICAL_REOPENED=false`; any BaoStock
  reacquisition must create a distinct `REACQUIRED_EQUIVALENT_SOURCE` lineage.
- Five content-addressed placebo kinds, explicit research/execution entry
  proxies independently selected as the first post-cutoff close, strict-next
  bar open and decision-session last close, factor
  correlation/rank/leave-one-out/incremental/residual diagnostics
  and moving-block/block-length/stability inference use the Research Validation
  framework.
- External Validation reuses canonical `ResearchExperimentDefinition`; the
  definition freezes the exact hypothesis and permits exactly one Temporal,
  Universe or Provider change. Scores, Target returns, entry-proxy economics and
  fractional Top-K boundaries are recomputed from frozen inputs; Feature
  configuration, DecisionTime and PIT/free-data ceiling are owner-derived. Each
  economic row must also reload the exact Panel-linked Historical Outcome and
  hash-valid Strategy Economics result, then match its frozen policy, Target
  label, entry lineage, symbol, entry/exit prices and capacity. No external
  dataset was executed. `TEMPORAL_VALIDATION_V1` is now frozen at start session
  `2025-07-15` and 126 Calendar-owner sessions; its ending Decision/Target dates
  are deliberately owner-derived and External outcomes remain gate-closed.
- Context evaluation enforces session-constant versus within-session
  cross-sectional semantics. Market Regime and current Global Theme are
  session-level roles in the observed WP-01 panel; Capital remains a public
  proxy and is not hidden-intent evidence. Cross-sectional Capital interaction
  remains `NOT_ESTIMABLE` without genuine symbol-level variation.
- Candidate Policy V2 keeps Incumbent and dormant Challenger identities
  separate, with Universal Integrity, factor-specific availability, validated
  Alpha contributions and evidence-supported Context adjustment. External,
  Context, Candidate and conditional-prediction results are persisted by typed
  application methods through the existing PostgreSQL Historical Evidence owner.
  Candidate admission V2 binds every supported Context record to the same
  Experiment, External Evidence and research-panel Dataset; malformed Factor
  rows are rejected rather than silently filtered. The conditional Forecast
  owner additionally binds one supported same-Experiment Context record;
  owner reload and embedded artifact hashes fail closed.
- Conditional Forecast keeps the empirical distribution baseline and compares
  a frozen regularized-linear model under chronological sample admission,
  per-fold Target-availability embargo, minimum sample, search budget and
  uncertainty rules. The median estimator is consistent between validation and
  the empirical PathForecast baseline. Barrier outputs remain raw scores;
  `CALIBRATED=false`. Forecast-required Strategy input cannot execute from a
  caller projection: Runtime requires typed owner-authority reload for Signal,
  Forecast, Context, Model, Risk and Opportunity. The former helper that treated
  a post-Portfolio complete-account RiskDecision as pre-Strategy state remains
  retired as semantically circular. Producer wiring does not activate the
  evidence-blocked conditional family.

Migrations 091–092 extend the existing append-only Historical Evidence and
Strategy owners and constrain V1/V2 Forecast semantics without mutating V1
identities. Migration 093 persists the exact frozen Temporal Validation window.
Migration 094 adds immutable pre-Strategy Risk and Opportunity owner tables;
migration 095 admits the Daily Alpha snapshot into the existing Continuous
child and Research Validation authorities. Migration 096 adds the exact
Prediction Snapshot→Outcome locator and lineage bindings without creating a
second Outcome engine. Migration 097 binds every new snapshot to its adjacent
target session and exact typed Calendar owner in an append-only projection.
These migrations grant no Alpha, External, OOS,
prospective, Strategy or Production qualification.

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

The Phase II and Daily Alpha engineering chain is owner/runtime wired. The
conditional Strategy remains inactive because its empirical admission chain is
absent. WP-ALPHA-PROOF-02 did reopen a new immutable physical corpus, verified
all package checksums and reproduced all Raw→Normalized observations, then
ended `REJECTED / CORRECTNESS_FAILED`. Its eight Target failures are now fully
located; that diagnosis does not revise the immutable proof.

The next empirical dependency order remains:

```text
WP-ALPHA-CORRECTNESS-02 design review
→ implementation and full regression
→ new-identity Discovery-only materialization/correctness/economics
→ independent GO / NO-GO
→ only after an explicit GO: freeze a separately reviewed External Experiment
→ WP-ALPHA-CONTEXT-01
→ WP-CANDIDATE-POLICY-02
→ WP-PREDICTION-01
```

The design work has read no External or Locked OOS Outcome and has run no new
Campaign. Even future `CORRECTNESS_SUPPORTED` does not automatically admit
External: unchanged-direction Discovery economics and a credible explanation
of the old/new sign difference must independently support `GO`. Until such
separately executed evidence exists, External validation, Formal OOS,
prospective proof, Strategy qualification and Production qualification remain
false.

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
