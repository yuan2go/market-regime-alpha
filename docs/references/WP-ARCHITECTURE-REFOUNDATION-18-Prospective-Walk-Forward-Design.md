# WP-18 Continuous Prospective Operations and Exploratory Walk-Forward Design

> **Status:** CURRENT_STATUS
> **Authority:** Canonical implementation contract for WP-18; not Provider, Formal PIT/OOS, prospective, Alpha, model, trading, or Production evidence
> **Baseline:** `origin/main@097f19ecf846aef7cf55a3013adf5eb91faefce6`
> **Owner:** Market Regime Alpha maintainers
> **Frozen:** 2026-09-03

## 1. Outcome and evidence ceiling

WP-18 closes two engineering gaps without changing their evidence classes:

```text
Track A: TradingSession + TargetDefinition
         -> immutable ProspectiveArchiveGeneration
         -> due Market Application capture
         -> explicit terminal slice fact
         -> first-party observed revision chain

Track B: sealed RETROSPECTIVE_BACKFILL
         -> immutable multi-fold ExploratoryBacktestRun
         -> canonical Dataset / Candidate / Decision Support / Outcome
         -> Evaluation-bound layer attribution
         -> derived AlphaFunnelDiagnosis
```

Track A accumulates first-party contemporaneous facts only when capture actually
occurs in the declared real window. Track B remains
`EXPLORATORY_RETROSPECTIVE`. Neither track changes the WP-15/WP-16 Provider
decisions or WP-17P evidence.

The following remain forced closed:

```text
FORMAL_PROVIDER = BLOCKED
FORMAL_PIT = BLOCKED
FORMAL_OOS = NOT_RUN
PROSPECTIVE_PROVEN = NO
ALPHA_PROVEN = NO
MODEL_QUALIFIED = NO
PRODUCTION = NO-GO
```

## 2. Ownership and rejected alternatives

Market remains the owner of archive planning, capture observations, gaps,
resource stops, terminal slice facts, and observed revisions. Runtime remains
the only scheduler/run/attempt/fence owner. Research & Qualification remains
the owner of exploratory predeclaration, fold/arm lineage, model lineage,
Evaluation and diagnostic read models.

The following alternatives are rejected:

- mutating WP-17P archive/backtest rows to retrofit new semantics;
- a second scheduler, campaign runtime, Outcome calculator, portfolio ledger,
  Evaluation store, or pandas/report result Authority;
- caller-selected dates, `weekday` inference, or `date + timedelta` for a
  session transition;
- a wide generic campaign registry or JSON business ownership.

WP-18 uses additive companion relations and existing narrow UoWs. Historical
rows and hashes remain byte-for-byte immutable.

## 3. Trading-session and Target schedule authority

One prospective generation has exactly one exchange calendar. All session
transitions are resolved by the typed `TradingSessionReadPort` and persisted by
exact `trading_session_id`. Missing or ambiguous calendar evidence fails
closed. Local time construction inside an already resolved session is allowed;
calendar-day arithmetic is not.

`TargetArchiveScheduleReadPort` resolves one exact registered
`TargetDefinition(id, version, hash)` and its ordered checkpoints. For the
current target it must prove:

```text
REFERENCE: decision session D, exact 14:55 Asia/Shanghai
OBSERVATION: offset 1 actual exchange session, exact 10:30 Asia/Shanghai
```

The planner then freezes these purpose-specific windows:

| Slot | Exact session | Evidence window |
|---|---|---|
| `PRE_DECISION` | D | pre-decision capture |
| `DECISION_NEAR` | D | contains exact 14:55 reference |
| `POST_CLOSE` | D | post-close observation |
| `EVENING_REVISION` | D | evening comparison |
| `OUTCOME_PRE_OPEN` | target-resolved T+1 | pre-open observation |
| `OUTCOME_PATH` | target-resolved T+1 | 09:30 through 10:30 path |
| `OUTCOME_10_30` | target-resolved T+1 | exact outcome checkpoint |
| `OUTCOME_POST_CLOSE` | target-resolved T+1 | post-close comparison |
| `REVISION_VERIFICATION` | a later resolved actual session | later comparison |

The persisted session and target checkpoint bindings, not the slot names, are
the proof. A Product incapable of serving a window yields an explicit gap; a
later download never becomes an on-time capture.

## 4. ProspectiveArchiveGeneration

`ProspectiveArchiveGeneration` is a Market-owned immutable companion to one
exact `MarketArchive` root. It freezes:

- archive series code and contiguous generation;
- optional exact predecessor generation;
- exchange and exact decision/outcome/later TradingSessions;
- exact TargetDefinition version/hash and checkpoint roster;
- deterministic instrument member roster and Product identifiers;
- complete ordered capture schedule/count/hash;
- archive start, code/config Artifacts and provenance;
- generation content hash and PostgreSQL registration time.

Generation 1 may lack a predecessor. Every later generation requires the
immediately preceding generation, a strictly later decision session, the same
series/exchange/Target, and an unchanged stable instrument roster unless a new
series is opened. Child ordinals are contiguous. Root success is deferred until
the complete member and schedule rosters reconcile.

`MarketArchiveSlice` remains the executable unit. Each scheduled slice has one
exact generation, member, slot, TradingSession, Target checkpoint, Provider
request identity, and comparison group/ordinal. This is a typed companion, not
a replacement archive.

## 5. Due and terminal semantics

PostgreSQL authoritative time drives readiness:

```text
now < window_start                 -> NOT_DUE (read state)
window_start <= now <= window_end  -> DUE (read state)
now > window_end, no terminal      -> OVERDUE (transient read state)
```

`run-due` first closes overdue slices, then executes due slices. Every elapsed
slice becomes one immutable terminal fact:

```text
CAPTURED_ON_TIME | CAPTURED_LATE | MISSED |
PROVIDER_GAP | RESOURCE_STOP | FAILED
```

The terminal row always concrete-FKs to its scheduled slice. Database guards
verify the matching capture observation, SourceGap, resource-stop fact, or
failure receipt by the same slice. `CAPTURED_ON_TIME` additionally proves the
capture completed no later than the window end. `MISSED` proves the window had
ended before PostgreSQL recorded the terminal. Exactly one terminal is allowed;
therefore a later retry cannot repair `MISSED` into `CAPTURED_ON_TIME`.

Provider I/O and Artifact byte writes remain outside business transactions.
Each command is short, fence-first when claimed, idempotent, and uses exact
unknown-commit probe/replay.

## 6. Revision observations and inspection

Every comparable capture freezes its current observation, optional immediate
predecessor observation, ordinal, comparison key, Artifact hash, normalized
revision-roster hash and relation:

```text
FIRST | IDENTICAL | CHANGED
```

Predecessors must form a contiguous, acyclic chain inside the same generation,
instrument/resource/comparison group. The relation is computed, never caller
asserted. Content stability is observed evidence only; it is not vendor
finality.

Read-only operations expose `plan-next-session`, `run-due`, `resume`, `inspect`,
`gap-report`, `revision-report`, and `daily-health`. These call Market
Application commands and never write SQL directly. Inspection derives
NOT_DUE/DUE/OVERDUE from the PostgreSQL clock and persisted windows.

## 7. Operational durability and forward upgrade

Qualification databases are disposable. Operational archive databases and
Artifact roots are durable evidence and must never enter recreate/test teardown.

Before an operational upgrade the operator must:

1. verify exact database name/OID, schema epoch and prior catalog checksum;
2. produce `pg_dump` backup plus SHA-256 and verify it is readable;
3. run disk preflight without deleting evidence;
4. apply a single additive transaction containing only WP-18 tables,
   constraints, indexes, functions and triggers;
5. write an immutable upgrade receipt and advance the unreleased baseline
   checksum only after the exact old checksum matches;
6. run schema and archive reconciliation.

Low disk yields `RESOURCE_STOP`. No raw Artifact or recorded evidence may be
deleted to make a run appear complete.

## 8. Walk-forward predeclaration

WP-18 appends a new generation of the existing `ExploratoryBacktestRun`; it
does not replace WP-17P. It freezes at least 40 distinct actual XSHG sessions,
with stable deterministic 32-instrument pilot scope. Time depth takes priority
over symbol breadth.

Folds are chronological and non-overlapping. V1 uses paired expanding/rolling
steps:

```text
FIT_k (completed samples only)
  -> ModelTrainingRun_k
  -> immutable ModelVersion_k
  -> later VALIDATION_k Decision generation
```

Each fold freezes ordinal, exact session roster, purpose, purge, embargo,
EvaluationProtocol, training-generation ordinal and validation-generation
ordinal. Random splits are prohibited. A ModelVersion may bind only to a
strictly later validation session/fold; the existing database generation guard
remains authoritative.

The root freezes a complete ordered four-arm roster:

1. `RULE_CURRENT_CONTEXT`
2. `RIDGE_CURRENT_CONTEXT`
3. `RULE_CONTEXT_OBSERVATIONAL`
4. `RIDGE_CONTEXT_OBSERVATIONAL`

Each arm concrete-FKs to an immutable StrategyVersion. Current-context arms
retain the existing `advance_rate >= 0.50` requirement and failure behavior.
Observational arms calculate and bind the same Context facts but their frozen
Strategy requirement uses typed `OBSERVE_ONLY`: Context cannot block Signal and
is never rewritten to POSITIVE. No threshold changes are permitted.

All four arms share Dataset identity inputs, Target, folds, Candidate policy,
cost assumptions, portfolio/risk policies and Evaluation protocol. Rule versus
ridge is the only forecast-source difference within a Context mode.

## 9. Candidate-first and layer-complete Evaluation

Evaluation is extended with typed exact-source measures. It must bind the
canonical owner row for every member; it never recalculates business facts from
bars or report data.

Required metric families are:

- Dataset/Feature: row and declared-feature availability;
- Candidate: composite score coverage, selected ratio, score-vs-Target RankIC,
  Top-K/spread and hit rate;
- Context: POSITIVE/NEUTRAL/NEGATIVE/NOT_ESTIMABLE state distributions and pass
  rate;
- Signal: PRESENT/NO_SIGNAL/NOT_ESTIMABLE distribution and coverage;
- Forecast: AVAILABLE/NOT_ESTIMABLE distribution, coverage and predictive
  relation;
- Opportunity: creation rate;
- Portfolio: proposal/line count, exposure and turnover;
- Risk: accept/reject/unknown distribution and typed rejection reasons;
- Outcome/economics: gross return, `ASSUMED_COST` net, MFE, MAE, hit/barrier and
  drawdown.

Every metric retains the complete member denominator through the existing
EvaluationMetricObservation Cartesian roster. `UNAVAILABLE`, `FAILED`, and
`NOT_ESTIMABLE` are data, never sample deletion. When realized portfolio
exposure is zero, economics is `NOT_ESTIMABLE`; it is neither `ZERO_RETURN` nor
`NO_ACTION`.

## 10. AlphaFunnelDiagnosis

`AlphaFunnelDiagnosis` is a deterministic read model over reconciled Evaluation
metrics, not business Authority. It returns exactly one:

```text
DATA | FEATURE | CANDIDATE | CONTEXT | SIGNAL | FORECAST |
PORTFOLIO | RISK | ECONOMICS | NOT_DETERMINED
```

The frozen precedence is upstream-first. A stage is selected only when all
upstream denominators are estimable and its own configured sufficiency or
information condition fails. CONTEXT is selected only when observational arms
remain estimable while current-gate arms lose coverage or conditional outcome;
ECONOMICS requires an estimable gross result whose assumed-cost result loses
the gross edge. Missing or contradictory metrics yield `NOT_DETERMINED`.
Callers cannot supply the result.

## 11. Reconciliation and exit evidence

Read-only reconciliation recomputes:

- generation/predecessor/session/Target/member/schedule hashes;
- terminal completeness and clock classification;
- capture/gap/resource/failure bindings;
- revision predecessor chain and computed relations;
- backtest fold/arm/session/policy rosters;
- Model training-to-later-inference ordering;
- Dataset/Candidate/Decision/Outcome exact lineage;
- Evaluation metric-source and metric-member Cartesian completeness;
- diagnostic inputs and derived loss stage;
- receipt/audit/Runtime provenance.

Passing is `matched = true` and `mismatch_count = 0`. Verification against one
exact implementation SHA may claim engineering closure only after disposable
PostgreSQL bootstrap/recreate, focused and full suites, concurrency,
failure/recovery, query plans, static/build/docs checks, safe operational
upgrade, and real execution evidence all pass. Waiting future windows remain
NOT_DUE and cannot be reported as captured.

## 12. Non-scope

WP-18 does not weaken Provider floors, modify immutable WP-15/16/17P evidence,
qualify a Model, optimize parameters, introduce a complex model, execute Formal
OOS, claim prospective proof, perform broker execution, cut over the full CLI,
delete Legacy, or admit Production.
