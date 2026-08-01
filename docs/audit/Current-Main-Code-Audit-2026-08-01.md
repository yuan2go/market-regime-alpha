# Current Main Code Audit — 2026-08-01

> **Status:** CURRENT_AUDIT  
> **Authority:** Code-first audit of current `main`; implementation facts override older design/status prose  
> **Owner:** Market Regime Alpha maintainers  
> **Audited Revision:** `e183fdac285786ed448c835e65c99dc67189c2b9`  
> **Audit Date:** 2026-08-01  
> **Related Documents:** ../status/Current-State.md, ../status/Capability-Matrix.md, ../status/Gap-Register.md, Production-Decision-Lifecycle-Delivery.md, Production-Lifecycle-Hardening-Delivery.md  
> **Evidence Boundary:** Repository code, SQL, tests and connected Git metadata were inspected. The audit environment could not clone the repository because `github.com` DNS resolution failed, so current-HEAD tests were not independently executed.

## 1. Executive finding

The repository has evolved from a collection of A-share research strategies into a modular research and manual decision-support operating system.

Its strongest implemented properties are:

- strict separation of Evidence, Candidate, Signal, Entry, Thesis, Portfolio, Risk, Fill, Position and Outcome;
- immutable content-addressed research artifacts;
- explicit DecisionTime and AvailabilityTime semantics;
- fail-closed data quality;
- SQLite command idempotency and optimistic concurrency;
- append-only Fill evidence;
- full-account Portfolio/Risk recomputation;
- Thesis-scoped execution attribution;
- Fill/calendar-derived A-share T+1 sellability.

The platform is not production-ready and has not established Alpha. The current `main` also contains a concrete H4 integration defect that prevents it from being treated as a green baseline.

## 2. Audit method

The review followed actual implementation paths rather than relying only on README or class names:

```text
Public acquisition stages
→ Source Archive and SourceManifest
→ DataQuality
→ Universe and Eligibility
→ Feature materialization
→ B0/B1 PredictionRun
→ CandidateRecommendation and Entry plumbing
→ Operational Research Bridge
→ Market Regime
→ Theme Rotation
→ Capital Evolution
→ Candidate Discovery
→ Signal and PathForecast
→ TradingOpportunity and TradingThesis
→ Complete-account Portfolio/Risk
→ ManualTrade and Fill
→ PositionBook and T+1 Position
→ Holding/Exit
→ TradeOutcome and LifecycleReview
```

Inspected areas included:

- `pyproject.toml` and dependency metadata;
- `application/daily_loop/**`;
- `application/operational_research/**`;
- `research/market_regime/**`;
- `research/theme_rotation/**`;
- `research/capital_evolution/**`;
- `research/candidate_discovery/**`;
- `signals/**` and `forecasting/**`;
- `decision/**`;
- `portfolio/**` including H1 and H4;
- `execution/**` and SQL migrations;
- `position/**`;
- `evaluation/**`;
- Legacy FastAPI, scheduler and broker placeholders;
- current status, capability and gap documents;
- current commit metadata and available CI status.

## 3. Architecture assessment

### 3.1 Architecture style

The platform is a Python 3.12 modular monolith with domain-oriented bounded contexts and CLI/Application-Service orchestration.

The code formalizes six ownership layers:

1. Data and Evidence Foundation;
2. Research Opportunity Discovery;
3. Signal Timing;
4. Trade Decision and Risk;
5. Position Lifecycle and Execution;
6. Outcome Evaluation and Learning.

The architecture intentionally forbids responsibility inflation. For example:

- Candidate research cannot emit BUY/SELL or PositionPlan;
- Signal cannot create an execution record;
- Decision/Risk cannot create broker Fill;
- Evaluation cannot automatically promote a model.

This is appropriate for a research-first trading system because it prevents a successful engineering path from silently becoming trading authority.

### 3.2 Data and evidence model

The repository distinguishes:

```text
immutable evidence authority
from
mutable/recoverable operational projection
```

Immutable authority includes Source Archives, SourceManifest, PredictionRuns and Decision/Research/Review artifacts. These are generally exact-file, checksummed, non-overwriting and semantically reconstructed by Readers.

Operational state uses SQLite for Runtime Journal, Opportunity/Thesis state, Portfolio/Risk decisions, ManualTrade state, PositionBook indexes and append-only events.

This is a sound local architecture. It does not solve cross-store atomicity or multi-instance production consistency.

## 4. Core implementation facts

### 4.1 Daily research path

`DailyLoopRunner` implements a real staged vertical slice:

1. freeze prior-session history;
2. freeze exact-date security status;
3. freeze Decision Quote;
4. evaluate source quality;
5. reconcile Universe and Eligibility;
6. materialize baseline features;
7. publish B0/B1 PredictionRuns;
8. produce CandidateRecommendation;
9. run Entry plumbing;
10. publish Daily Decision Artifact;
11. settle next-session 10:30 outcomes from a separate immutable archive.

The loop publishes a structured blocked artifact rather than continuing after invalid data. It records stage receipts and supports replay/recovery.

The operating ceiling remains exploratory: fixed smoke Universe, public providers and no sustained controlled-window success evidence.

### 4.2 Research Layer

The implemented Research Layer computes:

```text
Market Regime
→ Theme Rotation
→ inferred Capital Evolution
→ Candidate Discovery
```

Market Regime uses market return, breadth, amount change, intraday range and limit structure to produce a market state, trade permission and gross-exposure cap.

Theme Rotation uses multi-horizon relative strength, amount expansion, breadth, new-high breadth, leader strength, participation change and persistence.

Capital Evolution infers accumulation/ignition/diffusion/acceleration/divergence/exhaustion/collapse from observable proxies. The code correctly marks the result as inference rather than institutional-intent fact.

Candidate Discovery applies mandatory Market/Theme/Capital/Eligibility gates and combines the resulting context with frozen B0/B1 factors. CandidateSet is explicitly not a recommendation.

All configurations remain unvalidated assumptions.

### 4.3 Entry boundary

The canonical daily Entry component is not an Entry Model. It emits only:

- `REJECT` for data/plumbing blockers; or
- `WAIT_CONFIRMATION` with `ENTRY_MODEL_NOT_YET_VALIDATED`.

No canonical path emits `ENTER`.

### 4.4 Decision and persistence

Opportunity and Thesis repositories use:

- `BEGIN IMMEDIATE`;
- command idempotency key and command hash;
- version compare-and-swap;
- append-only event histories;
- restore-time transition validation;
- atomic Opportunity confirmation and Thesis creation.

The read path does not trust the current projection blindly. It reconstructs the requested version from history and checks that the current row remains reconstructible.

### 4.5 H1 complete-account Risk

H1 introduced complete account snapshots and evaluates post-trade exposure across all holdings, not only positions mentioned in the current allocation request.

The repository recomputes Risk before accepting persistence, preventing caller-forged approval. Partial, stale, future or unreconciled account evidence produces fail-closed results.

### 4.6 H2 traceability

H2 introduced `PositionBook` and versioned traceable execution records. The first-version scope allows one OPEN Thesis per account/symbol. Fill remains in the existing append-only ledger and is not duplicated as a second authority.

A closed-trade outcome validates the complete Opportunity→Thesis→Portfolio→Risk→ManualTrade→Fill→Position chain.

### 4.7 H3 A-share T+1

H3 derives available/frozen/today-acquired quantity from effective Fill plus explicit trading sessions and typed symbol-session status evidence.

It correctly handles:

- same-session buys;
- Friday-to-Monday and holiday spans;
- suspension;
- missing/late status;
- Fill corrections;
- invalid sell quantities;
- reconciliation-required state.

The hardened complete-account Risk path enumerates OPEN PositionBooks and builds Risk input from these projections instead of accepting arbitrary caller sellable quantity.

### 4.8 H4 current-main defect

Commit `e183fdac` added:

- `portfolio/risk_routes.py`;
- migration 007 up/down;
- `tests/portfolio/test_risk_route_separation.py`.

The domain implementation substantially defines increasing versus reducing risk:

- OPEN/ADD require an approved complete-account RiskDecision;
- REDUCE/EXIT use a separate gate;
- reductions cannot increase exposure;
- quantity, T+1 availability, reconciliation, suspension, price-limit state, observation availability and liquidity participation are checked;
- decisions are content-addressed and structured.

But the same current commit is incomplete:

```text
missing: src/market_regime_alpha/portfolio/sqlite_risk_routes.py
missing: SQLiteRiskRouteRepository
missing: RiskRouteApplicationService
missing: portfolio/__init__.py exports
missing: application/trading_lifecycle H4 export/integration
```

The H4 test imports all of those missing symbols/modules. This is a static collection blocker and means current `main` cannot be described as passing.

Correct status:

```text
H4_PARTIAL_BROKEN_ON_CURRENT_MAIN
```

not:

```text
H4_CONFIRMED_GAP
```

and not:

```text
H4_DELIVERED
```

## 5. Database, transaction and consistency assessment

### 5.1 Strengths

- explicit migration ownership;
- append-only Fill triggers;
- append-only decision histories;
- command-level idempotency;
- CAS for aggregate transitions;
- transaction rollback;
- reconstruction validation;
- Risk recomputation before write;
- migration-down isolation tests in prior checkpoints.

### 5.2 Remaining limitations

- SQLite is local/test operational authority;
- no full PostgreSQL implementation;
- no multi-instance lease or fencing;
- no cross-filesystem/database transaction;
- no outbox or reliable event delivery;
- no whole-lifecycle Saga;
- no production backup/restore evidence;
- no authenticated external account or Fill authority.

## 6. Frontend and external integration assessment

### 6.1 Legacy FastAPI

`web/dividend_t_app.py` is an operational demo for the Legacy Dividend-T strategy. It is not a presentation layer for the canonical Daily/Research/Decision/Risk/Position system.

Risks:

- no production authentication;
- direct Legacy model evaluation;
- static fallback data can be returned when live scanning fails;
- exception text is included in response metadata;
- no verified Artifact Reader boundary.

### 6.2 Scheduler

The APScheduler factory belongs to Legacy Dividend-T and schedules simple callbacks. It has no durable job store, lifecycle receipts, resume semantics or ShadowRun ownership.

### 6.3 Broker adapters

Paper Broker does not mutate a real account. QMT and PTrade adapters explicitly raise `BrokerUnavailable` and refuse live orders. This is the correct safety default.

## 7. Verification assessment

### 7.1 Historical evidence

Delivery documents contain commit-bound PASS records for Phase 0–7 and H1–H3, including focused tests, full pytest, Ruff and mypy.

These records support the stated earlier checkpoints.

### 7.2 Current HEAD

For `e183fdac`:

- no connected GitHub Actions workflow run was observed;
- no commit status/check was observed;
- the audit environment could not clone and execute tests because `github.com` DNS resolution failed;
- static inspection found the H4 missing-import/module blocker.

Therefore:

```text
CURRENT_HEAD_FULL_TEST_PASS = NOT_ESTABLISHED
CURRENT_HEAD_BUILD_PASS = NOT_ESTABLISHED
CURRENT_HEAD_STATIC_COLLECTION_BLOCKER = CONFIRMED
```

## 8. Maturity assessment

| Dimension | Current assessment |
|---|---|
| Domain/evidence design | Strong research-platform engineering |
| Artifact/replay mechanics | Substantially implemented |
| Daily candidate pipeline | Implemented exploratory vertical slice |
| Market/Theme/Capital models | Implemented, unvalidated |
| Signal/Path | Implemented exploratory, uncalibrated |
| Entry | Plumbing only |
| Portfolio/Risk | H1–H3 substantial; H4 broken integration |
| Manual execution/Position | Implemented manual evidence path |
| Holding/Exit/review | Implemented exploratory one-shot path |
| Shadow operations | Not implemented |
| Production security/ops | Not implemented |
| Formal PIT/OOS Alpha | Not established |
| Live execution | Not authorized and not implemented |

Overall classification:

> **Pre-Shadow research decision platform with strong evidence and manual-lifecycle mechanics.**

## 9. Required next sequence

### P0 — restore current engineering integrity

1. implement `SQLiteRiskRouteRepository`;
2. implement `RiskRouteApplicationService`;
3. add package/application exports;
4. add H4 CLI integration;
5. run focused H4 and migration tests;
6. create a reproducible Python 3.12 lockfile;
7. run full pytest, Ruff, mypy, docs and package-build gates;
8. record exact commit-bound results in delivery/status documents;
9. require these checks in CI.

### P1 — complete pre-Shadow mechanics

```text
H5 Artifact-derived Thesis health
→ H6 Composite operational evidence
→ H7 Durable Holding/Exit operations
→ H8 Recoverable ShadowRun
→ H9 Signal/Path validation infrastructure
```

### P1 — establish qualified evidence

- controlled 14:55 acquisition;
- operational stock Universe;
- canonical ETF Universe;
- PIT Theme/ETF mappings;
- Theme/Capital daily materialization;
- external account and Fill reconciliation;
- formal walk-forward and OOS protocols.

### P2 — production hardening

- PostgreSQL parity;
- authentication and RBAC;
- signed artifacts/operator identity;
- metrics, tracing and alerts;
- backup/recovery drills;
- canonical QuantDesk UI;
- separately approved broker architecture and kill switch.

## 10. Final audit conclusion

The repository’s architecture is materially stronger than a typical personal quant codebase. Its primary asset is the explicit, reconstructible authority chain rather than any single trading formula.

The immediate correct action is not to add another model, dashboard or broker adapter. It is to restore a green exact-commit baseline by completing H4, then build the durable Shadow and validation layers required to convert good engineering mechanics into credible operating evidence.
