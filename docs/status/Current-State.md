# Current State

> **Status:** CURRENT_STATUS  
> **Authority:** Current implementation/evidence summary  
> **Baseline:** `agent/alpha-proof-campaign-01@bcee87a7d79f1028667a5874b7273a10fdcaacfa` (executable V2 evidence)
> **Last Updated:** 2026-08-20
> **Code Evidence:** `src/market_regime_alpha`, `src/market_regime_alpha/persistence/postgres/migrations/*.sql`, `tests`

This document records what the named executable baseline implements and what
its evidence actually supports. It does not inherit stronger claims from the
target architecture.

## 1. Repository baseline

- **Architecture:** Python 3.12+ PostgreSQL-centered modular monolith.
- **Persistent business authority:** PostgreSQL 16; no canonical file/SQLite/memory fallback.
- **Migration head:** 090.
- **Canonical all-day runtime:** one Continuous Research control plane.
- **Installed operator scripts:** six — `continuous-research`, `state-system`, `decision-system`, `model-governance`, `pit-authority`, `research-shadow`.
- **Execution boundary:** human-operated/manual; no broker writer or automatic live-trading authority.
- **Physical Position truth:** observed effective manual Fills.
- **Golden Loop V2 execution:** one immutable 126-session historical campaign at the baseline SHA completed in an isolated PostgreSQL schema migrated from 084 through 090; exact replay and aggregate Evidence are recorded below.
- **Current branch validation:** the full local quality gate is recorded at handoff; GitHub CI remains a separate Provider result.

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

### Manual execution and Position

Accepted cross-strategy Portfolio lines may enter the existing manual execution ledger through exact Strategy/Portfolio/account lineage. The current engineering path supports aggregate Proposal authority, account cash/available-sell checks, A-share lot/T+1 constraints, owner-resolved decision-time price/account facts, partial/corrected observed Fills, physical-position reprojection, strategy sleeves and realized Strategy Outcome supersession.

This is manual-execution correctness. It grants no broker authority and proves no Alpha.

### Outcome, evaluation and governance

The repository includes factual Shadow outcome settlement, Panel/Evaluation datasets, factor extraction, ablation/calibration/formal-evaluation mechanics, Strategy Shadow, Portfolio Shadow, multi-period performance/attribution, qualification owners, Model Governance, RBAC/approval/audit engineering and blocked Production Admission/Controlled Execution gates.

Most formal qualification capability is **engineering-ready but evidence-blocked**.

## 3. Research evidence that exists today

The strongest real historical work remains exploratory and PIT-incomplete.

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

> The platform can produce and replay serious quantitative research evidence, including negative evidence. It has not yet demonstrated a trustworthy Alpha or executable strategy edge.

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

The repository now moves into an **Alpha Proof Campaign**:

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
