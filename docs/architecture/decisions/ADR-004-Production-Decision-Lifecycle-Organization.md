# ADR-004 — Production Decision Lifecycle Organization

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Accepted engineering-organization decision  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-01  
> **Related Documents:** ../10-Production-Decision-Lifecycle.md, ../../specs/Production-Decision-Lifecycle-Requirements.md, ../../roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md  
> **Code Evidence:** Current `main` Platform V2 contracts, DailyLoop runtime and immutable artifact boundary.

## Decision status

`ACCEPTED` on 2026-08-01.

## Context

The repository already owns the identities, semantic time, SourceManifest, PIT Universe, Eligibility, Feature, PredictionRun, Research Artifact, Runtime Journal, model lifecycle and experiment-governance concepts required by the next decision-support increment.

The new lifecycle extends the same domain:

```text
Evidence → Research → Signal → Forecast → Opportunity → Thesis
→ Portfolio and Risk → Manual Record → Position → Review
```

A separate project would duplicate those authorities. Directly adding all behavior to `DailyLoopRunner`, `CandidateDiscovery` or `daily_decision` would collapse established responsibilities. Immediate service decomposition would add network, deployment and consistency complexity before an independent runtime need exists.

## Decision

1. Keep the functionality in `market-regime-alpha` as a modular monolith.
2. Implement explicit bounded contexts in `signals`, `forecasting`, `decision`, `portfolio`, `execution`, `position` and `evaluation`.
3. Keep orchestration in `application`; domain modules must not depend on application code.
4. Reuse existing identity, time, SourceManifest, Universe, Feature, Artifact, DailyRun and governance contracts.
5. Keep `DailyLoopRunner` responsible only for its current source-to-daily-artifact lifecycle.
6. Add an operational-research adapter instead of placing Platform V2 research directly inside DailyLoop.
7. Preserve fixed MR1 next-session 10:30 semantics under `daily_decision`; new multi-horizon semantics receive new contracts.
8. CandidateSet remains research output, Signal remains timing evidence, and actual Position state is derived only from recorded fills.
9. The first delivery supports research, replay, simulation, manual confirmation and manual execution records. It does not authorize unattended broker operation.
10. A future Windows broker adapter may be deployed separately only when the external environment requires it. It shall consume versioned approved intent and return execution events without owning research, portfolio or position semantics.

## Consequences

### Positive

- one data, identity, configuration and governance authority is preserved;
- existing research and recovery infrastructure is reused;
- new responsibilities can be tested independently;
- distributed-system complexity is deferred;
- historical artifacts and readers remain compatible;
- future process extraction remains possible through repository ports and immutable contracts.

### Costs

- module boundaries require disciplined dependency control;
- repository protocols must precede persistence changes;
- a future broker split will still require interface versioning and reconciliation.

## Rejected alternatives

### Direct extension of existing modules

Rejected because it would create oversized modules, circular dependencies and mixed authority.

### Independent services now

Rejected because current scaling and deployment needs do not justify distributed messaging, service authentication, distributed tracing and cross-service consistency.

### Separate project

Rejected because it would recreate SourceManifest, Feature, Candidate, Model, configuration and workflow authorities for the same business domain.

### Repurpose the MR1 path

Rejected because its artifact identity and target semantics are already frozen.

## Invariants

1. Candidate output is not an order list.
2. Uncalibrated score is not probability.
3. Position state requires valid fills.
4. Risk rejection cannot produce an approved action.
5. EXPLORATORY evidence cannot be promoted by construction.
6. Existing artifact meanings remain stable.
7. Application workflows do not create a second acquisition state machine.
8. Review output cannot modify or promote models automatically.

## Delivery order

1. Operational Research Bridge.
2. Durable Model Registry and Experiment Governance.
3. Signal Engine and PathForecast.
4. TradingOpportunity and TradingThesis.
5. Portfolio and Risk.
6. Manual execution records and Position projection.
7. Holding, Exit and Attribution.
8. Shadow operation and operator surface.
9. Optional external execution adapter after explicit approval.
