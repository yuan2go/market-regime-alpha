# Production Decision Lifecycle Requirements

> **Status:** CURRENT_SPECIFICATION  
> **Authority:** Product and engineering requirements for the next production-decision work stream  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-01  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../architecture/10-Production-Decision-Lifecycle.md, ../architecture/decisions/ADR-004-Production-Decision-Lifecycle-Organization.md, ../roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md  
> **Code Evidence:** Requirements derived from the current `main` implementation and the 2026-08-01 architecture review; no implementation claim is made by this document.

## 1. Background

The repository already provides a recoverable exploratory daily loop, immutable evidence, Platform V2 research contracts, Market Regime, Theme Rotation, Capital Evolution and Candidate Discovery. The next system increment must convert those research outputs into a controlled decision-support lifecycle without inflating evidence authority or introducing unattended live execution.

The target is not a one-shot prediction of whether a symbol rises on the next session. The target is a verifiable process that discovers opportunities, evaluates entry structure, records a trade thesis, applies portfolio and risk constraints, captures actual manual execution, maintains authoritative positions, evaluates holding and exit decisions, and attributes outcomes back to the responsible layer.

## 2. Product objective

The system shall help a human operator answer the following questions with versioned evidence:

1. Is the current market environment compatible with risk taking?
2. Which themes and capital structures deserve attention?
3. Which symbols belong in a complete candidate population?
4. Is the current price, volume and trend structure suitable for entry research?
5. What reward, adverse excursion and time-horizon assumptions are being made?
6. What invalidates the trading thesis?
7. What position is permitted by portfolio and hard-risk constraints?
8. What did the human actually order and fill?
9. What is the authoritative current position?
10. Should the position be held, increased, reduced or exited?
11. Which layer contributed to profit, loss, missed opportunity or execution deviation?
12. Should a model remain in research, advance, degrade, suspend or retire?

## 3. Users and roles

| Role | Responsibilities |
|---|---|
| Researcher | Define targets, features, models, experiments and evaluation protocols |
| Strategy Reviewer | Review research evidence and model lifecycle transitions |
| Operator | Review opportunities, confirm manual actions and record orders/fills |
| Risk Approver | Own hard limits, strategy pauses and risk approval decisions |
| Administrator | Manage providers, configuration, credentials and runtime operations |
| Auditor | Reconstruct evidence, decisions, manual actions and position history |

A single-user deployment may assign multiple roles to one person, but the domain contracts shall preserve actor, permission and audit semantics.

## 4. Functional requirements

### 4.1 Evidence and operational research

- The system shall consume verified SourceManifest, Universe, Eligibility, Feature and Prediction artifacts.
- The system shall reject information whose Availability Time is later than Decision Time.
- The system shall preserve original Artifact identities and content hashes when adapting DailyLoop evidence into Platform V2 research inputs.
- The system shall not invent a LIVE research fixture or promote EXPLORATORY evidence.
- Missing theme membership, capital observations or required mappings shall fail closed.

### 4.2 Market, theme, capital and candidate research

- Market Regime shall control research permission and maximum risk exposure; it shall not emit stock trade actions.
- Theme Rotation shall own cross-theme priority.
- Theme lifecycle shall be separated from one-snapshot ranking when historical state becomes available.
- Capital Evolution shall remain an inference from observable proxies and shall not claim hidden actor intent.
- Candidate Discovery shall preserve every eligible-universe member as selected, watchlisted, rejected or data-insufficient.
- B0/B1 and later model scores shall not be described as probabilities without calibration.

### 4.3 Signal and path forecast

- The system shall provide versioned SignalSnapshot artifacts for price action, volume confirmation, trend confirmation, VWAP context and overheat state.
- Signal output shall remain research evidence and shall not create a position.
- The system shall support path-based targets with upper barrier, lower barrier and holding horizon semantics.
- The system shall represent MFE, MAE, return quantiles and calibration status.
- Uncalibrated models shall not emit probability semantics.
- Daily-bar dual-touch ambiguity shall remain explicit rather than being resolved by an invented intraday ordering.

### 4.4 Trading opportunity and thesis

- A TradingOpportunity shall bind an exact CandidateSet, SignalSnapshot, forecast, Decision Time, model version and configuration.
- An expired opportunity shall not be converted into a new thesis.
- A TradingThesis shall record rationale, supporting evidence, invalidation conditions, time invalidation, state, actor and version.
- A Candidate shall never be treated as a buy list.
- An invalidated thesis shall not permit additional exposure.

### 4.5 Portfolio and risk

- Portfolio construction shall account for current positions, cash, target positions, gross exposure, per-symbol limits, theme concentration, liquidity, T+1 restrictions and loss budgets.
- Hard-risk rules shall be owned by an independent Risk Authority.
- Risk rejection or timeout shall fail closed.
- Strategy code shall not override hard-risk rejection.
- The first production-decision release shall output simulation or manual-confirmation actions only.

### 4.6 Manual execution and authoritative position

- The first execution authority shall be a Manual Execution Ledger, not a broker order API.
- ManualTradeRecord shall capture intent, operator decision and reason.
- Fill records shall be append-only.
- Fill correction shall be represented by a correction record, not by mutation.
- PositionSnapshot shall be derived only from valid fills.
- Partial fill, cancellation, rejection and reconciliation-required states shall be represented explicitly.
- A position plan shall never be interpreted as an actual position.

### 4.7 Holding, exit and attribution

- Holding and Exit shall remain independently modeled and evaluated.
- Holding assessment shall support HOLD, ADD, REDUCE, WAIT and DATA_INSUFFICIENT semantics.
- Exit assessment shall support NO_ACTION, WAIT, EXIT and DATA_INSUFFICIENT semantics.
- ADD shall require a fresh risk decision and a still-valid thesis.
- Closed positions shall produce outcome and attribution evidence.
- Attribution shall distinguish selection, entry, holding, exit, portfolio and execution effects.
- Model evaluation shall not mutate model configuration automatically.

### 4.8 Governance

- Model Registry and Experiment Governance shall become durable and recoverable.
- Model promotion shall require evidence references and approval where required by lifecycle rules.
- Experiment validation and sealed-test access budgets shall be enforced durably.
- A model shall not advance because a single trade was profitable.

## 5. State requirements

### 5.1 Opportunity

```text
DISCOVERED → READY → TRIGGERED → CONVERTED_TO_THESIS
                 └→ EXPIRED
                 └→ REJECTED
```

### 5.2 Thesis

```text
PROPOSED → APPROVED → ACTIVE ↔ WEAKENING → INVALIDATED → CLOSED
       └→ REJECTED                 └───────────────→ CLOSED
```

### 5.3 Manual execution

```text
INTENT_RECORDED → USER_CONFIRMED → PARTIALLY_FILLED → FILLED
                       ├→ CANCELLED
                       ├→ REJECTED
                       └→ RECONCILIATION_REQUIRED
```

### 5.4 Position

```text
FLAT → OPENING → OPEN ↔ PARTIALLY_REDUCED → CLOSING → CLOSED
```

All mutable aggregate transitions shall use optimistic version control and append an audit event.

## 6. Non-functional requirements

### 6.1 Correctness

- Point-in-time semantics are mandatory.
- Equivalent inputs, configuration and code revision shall produce equivalent immutable artifacts.
- Data-insufficient paths shall fail closed.
- Position quantity and cost shall be reproducible from fills.

### 6.2 Reliability

- Commands shall support idempotency keys.
- Runtime stages shall be restartable.
- Artifact-written/receipt-missing failures shall be recoverable without duplicate acquisition or duplicate business effects.
- Database commit and event publication shall use an outbox or equivalent recoverable pattern before service separation.

### 6.3 Compatibility

- Existing DailyLoop, Phase D, Platform V2, `daily_decision` and historical `daily_research` identities shall remain readable.
- The fixed MR1 next-session 10:30 recommendation semantics shall not be silently repurposed.
- New semantics shall receive new schema or artifact identities.

### 6.4 Security and audit

- Every write shall include actor, time and reason where applicable.
- Provider and broker credentials shall not appear in artifacts or logs.
- Hard-risk limits shall be permission protected.
- The full chain from RunRequest to attribution shall be traceable.

### 6.5 Observability

The system shall expose at least:

- source delay and data-quality status;
- stage duration and failure count;
- blocked-run count;
- candidate coverage;
- opportunity conversion;
- risk rejection;
- execution deviation;
- position mismatch;
- MFE/MAE and realized outcome;
- model drift and lifecycle state;
- artifact storage and provider call volume.

## 7. Explicit non-goals for the first delivery

- Unattended live order placement;
- QMT/PTrade broker mutation;
- Level-2 order-book modeling;
- automatic strategy-weight optimization;
- automatic model promotion;
- multi-account and multi-broker execution;
- high-frequency trading;
- claims of guaranteed return;
- claims that public proxies reveal institutional intent.

## 8. Acceptance criteria

The requirements are satisfied for the first decision-support release only when:

1. Daily evidence can be adapted into a verified research artifact without authority inflation.
2. Signal and path forecast artifacts are replayable and reject time leakage.
3. Opportunity, thesis, risk and manual execution state transitions are tested.
4. A real manual fill ledger can rebuild the same PositionSnapshot after restart.
5. Risk rejection cannot produce an executable intent.
6. Existing tests, Ruff, mypy and documentation checks remain green.
7. No LIVE_ORDER code path exists.
8. A complete trace can be reconstructed from source evidence to closed-position attribution.

## 9. Open product decisions

The following decisions must be frozen before implementation reaches portfolio and position stages:

- stock-only, ETF-only or mixed first universe;
- canonical Decision Time;
- first path-target barriers and horizons;
- per-trade and portfolio risk limits;
- maximum theme concentration;
- whether manual fills are entered through CLI, web UI or CSV import;
- production provider and theme-mapping authority;
- SQLite-only pilot or PostgreSQL operational authority;
- first operator workbench scope.
