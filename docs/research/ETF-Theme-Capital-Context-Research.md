# ETF, Theme and Capital Context Research

> **Status:** CURRENT_RESEARCH_PROGRAM  
> **Authority:** Research design for upstream context and independent ETF strategies  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Current-Research-Program.md, ../specs/ETFDirectionSnapshot.md, ../specs/ThemeDirectionSnapshot.md, ../specs/CapitalContextSnapshot.md  
> **Code Evidence:** Canonical domains NOT_STARTED; partial Legacy/MR2 evidence only

## Roles

Each context signal must declare one role:

```text
DESCRIPTOR
FEATURE
INTERACTION
MODEL_SELECTOR
RISK_BUDGET_INPUT
HARD_GATE
```

Hard-gate authority requires specific incremental validation. Market Regime or theme strength is not trusted merely because it explains past moves.

## Candidate variables

- ETF relative strength, turnover/volume expansion, breadth and persistence;
- theme breadth, leadership, concentration, diffusion and decay;
- market advance/decline, limit-up/down structure, total turnover and volatility;
- capital/liquidity proxies with explicit source semantics.

## Current evidence

MR-2B tested one context-conditioned Candidate hypothesis and did not support the primary claim. Candidate ranking may remain an exploratory baseline; the failed context hypothesis is retained and must not be relabeled as success.
