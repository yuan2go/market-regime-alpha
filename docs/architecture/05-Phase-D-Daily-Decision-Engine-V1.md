# Phase D — A 股量化交易决策引擎 V1

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Target architecture for the next implementation phase  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../roadmap/Phase-D-Work-Packages.md, ../specs/README.md, ../status/Gap-Register.md  
> **Code Evidence:** Exploratory Phase D daily runtime implemented under `application/daily_loop/**` and `daily_decision/**`; broader production/position/portfolio contracts remain designed; `daily_research/**` is a frozen historical V1 compatibility layer

## Objective

Phase D turns the existing research spine into an immutable daily research and manual-decision loop. It does not grant automatic trading authority.

The exploratory implementation covers the recoverable daily loop, B0/B1
PredictionRuns, CandidateRecommendation projection, non-`ENTER` Entry plumbing,
MR1 outcome settlement and Daily Review. It does not establish formal data,
Alpha, position, portfolio or trading authority.

The implemented historical `daily_research` V1 contracts share several names
with this architecture but have different fields and semantics. They remain a
frozen compatibility layer and do not establish the Phase D runtime.

## Daily products

1. Market, ETF, theme and capital context.
2. Stock/ETF Candidate predictions and recommendations.
3. Entry suitability with explicit zones and invalidation.
4. Existing-position HOLD/ADD/REDUCE/ROTATE/EXIT/NO_ACTION assessments.
5. Manual decisions and actual fill/deviation records.
6. Recommendation outcomes, daily review and failure attribution.
7. 20/60-day rolling model scorecards and research proposals.

## Daily schedule

| Window | Job | Output |
|---|---|---|
| pre-open | calendar, universes, mappings and prior-position refresh | readiness report |
| intraday | source ingestion and freshness monitoring | source manifest |
| 14:30–14:50 | context and Feature materialization | immutable feature/context artifacts |
| 14:50 | multi-model Candidate run | Prediction Run |
| 14:50–14:55 | Entry and risk assessment | Strategy Proposal |
| user action | record decision/order/fill | ManualTradeRecord |
| next 10:30/14:45/close | target/outcome matching | RecommendationOutcome |
| after close | position, Holding/Exit and review | DailyReviewReport |
| nightly | rolling evaluation and Codex evidence pack | scorecard/proposals |

## State machine

```text
CREATED
→ DATA_LOADING
→ DATA_VALIDATED
→ UNIVERSE_BUILT
→ CONTEXT_BUILT
→ FEATURES_BUILT
→ MODELS_RUNNING
→ PREDICTIONS_FROZEN
→ DECISION_SUPPORT_PUBLISHED
→ OUTCOME_PENDING
→ OUTCOME_MATCHED
→ EVALUATED
→ CODEX_ANALYZED
→ COMPLETED
```

Terminal exceptions: `BLOCKED`, `FAILED`, `CANCELLED`. Retries are idempotent and cannot overwrite frozen output.

## Model layers

- Context models describe/forecast market/ETF/theme/capital state.
- Candidate models rank opportunities; no action.
- Entry models decide `ENTER/WAIT_PULLBACK/WAIT_CONFIRMATION/REJECT/NO_ACTION`.
- Holding models decide whether the thesis remains valid.
- Exit models classify independent exit reasons.
- Portfolio models allocate risk only after component validation.

## Risk gates

- stale/incomplete data;
- unknown eligibility/orderability;
- suspension and limit-state constraints;
- liquidity and concentration limits;
- strategy/model degraded state;
- daily loss/risk budgets;
- incompatible Candidate/Entry/Exit composition.

## Success criteria

Phase D V1 is complete when the same daily input can be reconstructed, every recommendation is immutable, outcomes match automatically, model/strategy/manual performance is separated, and 60-day scorecards can be generated without manual data editing. Profitability is a later evidence result, not an implementation acceptance criterion.
