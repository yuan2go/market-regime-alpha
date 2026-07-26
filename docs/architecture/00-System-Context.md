# System Context

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical system context for the current product boundary  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../constitution/00-Project-Vision.md, 01-Domain-Boundaries.md, 05-Phase-D-Daily-Decision-Engine-V1.md  
> **Code Evidence:** src/market_regime_alpha/**

## Product boundary

The system is a research and decision-support platform. It transforms identified market data into versioned research artifacts, predictions, assessments and reviews. A human retains final trading authority during Phase D.

## Actors and systems

| Actor/system | Responsibility | Authority |
|---|---|---|
| Researcher/user | Approves hypotheses, experiments, model promotion and final trades | Final human decision |
| Data providers | Supply raw market/reference data | Source facts only |
| Research platform | Normalize PIT data, materialize features, run models, preserve artifacts | Research evidence |
| Phase D decision engine | Produce daily context, Candidate, Entry and position assessments | Decision support, not orders |
| Codex | Diagnose evidence and propose controlled experiments | Proposal only |
| QuantDesk | Present/query artifacts and capture manual decisions | UI/workbench only |
| Broker/QMT/PTrade | Future execution/account source | Out of current mainline |

## Trust boundaries

```text
External Provider
  → raw source artifact
  → PIT normalization and qualification
  → research dataset
  → model prediction
  → strategy/portfolio proposal
  → human decision
  → manual trade record
```

Authority cannot increase silently across a boundary. Public data remains exploratory unless an explicit Dataset contract proves stronger eligibility.

## Non-goals for Phase D

- automatic broker orders, cancel/replace and unattended trading;
- automated account reconciliation;
- HFT or queue-position modeling;
- treating Level-1/5-level snapshots as Level-2 order-flow evidence;
- allowing UI or Codex to own model truth.
