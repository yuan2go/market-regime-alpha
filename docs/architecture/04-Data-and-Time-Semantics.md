# Data and Time Semantics

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical interpretation of market and research time  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../constitution/04-Data-Constitution.md, ../specs/DailyResearchSnapshot.md  
> **Code Evidence:** src/market_regime_alpha/core/time.py, data/contracts.py, data/path_evidence.py

## Required semantic times

| Time | Meaning |
|---|---|
| event_time | market event/bar interval time |
| available_time | earliest defensible time the information was usable |
| retrieved_at | when the project retrieved/recorded it |
| finalization_time | when the observation/bar became final |
| decision_time | frozen model decision cutoff |
| effective_date | when membership/ST/classification became effective |
| as_of | information-state reference time |

All timestamps are timezone-aware. Retrieval time must never substitute for market availability.

## PIT rule

At Decision Time `t`, every Feature and eligibility fact must satisfy its declared availability rule at or before `t`. Current constituents, current ST state or later revised prices cannot be backfilled into history without a qualified historical contract.

## Adjustment rule

Price adjustment basis is part of Dataset and Target identity. Instrument and benchmark comparisons use compatible bases. A provider Adapter cannot guess a missing adjustment convention.

## Bar finality

Intraday bar labels, close boundaries and finality must be provider-bound. A 14:55 quote observed after the Decision Time is not evidence for a 14:55 decision.

## Source roles

| Source | Current role | Authority ceiling |
|---|---|---|
| Xuntou/ThinkTrader/XtQuant v4 | primary provider-backed path | qualified by evidence; actual formal input currently blocked |
| Tencent current-session interfaces | real-time/exploratory acquisition | EXPLORATORY |
| BaoStock/local historical data | identified historical gap fill | EXPLORATORY unless separately qualified |
| Tushare/AKShare/EastMoney | auxiliary/Legacy access | source-specific; no silent promotion |
