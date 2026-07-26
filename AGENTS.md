# AGENTS.md — Market Regime Alpha Execution Contract

> **Status:** CURRENT_STATUS  
> **Authority:** Repository execution contract for coding/research agents  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** docs/README.md, docs/status/Current-State.md, docs/roadmap/Phase-D-Work-Packages.md  
> **Code Evidence:** main baseline 96e41a12d86b3b5f7472c2d4e44011736b087b6b

## Mission

`market-regime-alpha` is an A-share Alpha Research Operating System. Current delivery is research and manual decision support, not automated trading.

```text
Market / ETF / Theme / Capital Context
→ Tradable Universe
→ Feature / Factor
→ Candidate Discovery
→ Entry
→ Position Lifecycle
→ Exit
→ Portfolio Decision
→ Execution Simulation / Manual Record
→ Validation / Review / Research Feedback
```

## Document precedence

```text
1. explicit latest user decision
2. docs/constitution/00–09
3. docs/status/Current-State.md
4. docs/architecture/00–08
5. docs/research/Current-Research-Program.md and focused current research docs
6. docs/specs/**
7. docs/roadmap/Phase-D-Work-Packages.md
8. code/tests/artifacts for implementation facts
9. historical/archive materials
```

Never change Constitution without explicit authorization. Never let an older “CURRENT” label override the unique Current-State document.

## Current main facts

Implemented/tested: identity/time/data, calendar, PIT universe/eligibility, Feature and Candidate datasets, B0/B1, diagnostics, provider routing, Tencent exploratory path, Xuntou native/v4 adapters, Entry Path Target infrastructure, Research Artifact readers/verifiers and PIT replication mechanics.

Externally blocked: real qualified Xuntou v4/XtQuant input and formal replication run.

Not canonical on main: platform Model Registry/governance (Draft PR #12 only), Phase D daily snapshot/recommendations, actual-position authority, Holding/Exit, review/attribution, portfolio, Codex evidence pack and QuantDesk integration.

## Non-negotiable rules

- Candidate Prediction ≠ Entry ≠ Lifecycle ≠ Exit ≠ Portfolio ≠ Execution.
- Target horizon ≠ holding/exit time.
- Exit is not inverse Entry.
- Empty results and `NO_ACTION` are valid; `NO_ACTION ≠ HOLD`.
- Score is not probability without calibration.
- Data authority cannot inflate; no silent provider substitution or invented PIT/finality/adjustment.
- One primary change per experiment; preserve negative results.
- Codex proposes; it does not mutate/promote/execute.
- New platform responsibility does not enter Legacy God Objects.

## Provider rules

Xuntou/ThinkTrader/XtQuant is the primary provider-backed path. Tencent/BaoStock/Tushare/AKShare/EastMoney are explicit auxiliary or exploratory sources unless a qualified contract says otherwise. A runnable adapter is not proof of formal evidence.

## Current non-goals

No real QMT/PTrade order flow, cancel/replace, account sync, unattended trading, automatic rebalance, HFT or unqualified Level-2 inference.

## Required work-package discipline

Every change identifies research question, market scope, Universe, Decision Time, Target, Feature/evidence source, comparator, costs, validation, risk/failure conditions, outputs and documentation updates. Follow the ordered Phase D roadmap and run the declared validation commands before reporting completion.
