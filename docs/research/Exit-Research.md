# Exit Research

> **Status:** CURRENT_RESEARCH_PROGRAM  
> **Authority:** Independent Exit research design  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Current-Research-Program.md, ../specs/ExitAssessment.md, Position-Lifecycle-Research.md  
> **Code Evidence:** Canonical implementation NOT_STARTED; Legacy sell_side/sell_pressure/risk exist

## Exit taxonomy

```text
THESIS_INVALIDATION
TREND_INVALIDATION
STRUCTURE_BREAK
EXHAUSTION
PROFIT_TAKING
RISK_STOP
TIME_EXPIRY
THEME_DETERIORATION
MARKET_DETERIORATION
FORCED_EXIT
```

## Evaluation

- avoided drawdown;
- profit giveback;
- post-exit regret;
- premature/late exit rates;
- tail loss and maximum drawdown;
- cost and turnover;
- effect on total strategy distribution.

A good Exit cannot be selected only for reducing drawdown if it destroys the right tail. It must be compared with fixed-horizon and simple trailing baselines.

## Current state

Legacy sell-side modules and a frozen sell-side design are research assets. No canonical Exit Target/Model/Assessment has production authority on main.
