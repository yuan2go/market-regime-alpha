# AGENTS.md — Market Regime Alpha Execution Contract

> **Status:** CURRENT_STATUS  
> **Authority:** Repository execution contract for coding and research agents  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** docs/README.md, docs/status/Current-State.md, docs/roadmap/work-packages/README.md  
> **Code Evidence:** path:src/market_regime_alpha; path:tests

## Mission

`market-regime-alpha` is an A-share Alpha Research Operating System. The current delivery boundary is research and manual decision support, not unattended trading.

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

## Normative authority order

```text
1. Latest explicit user decision not superseded
2. docs/constitution/00–09
3. docs/architecture/00–08 and architecture/domains/**
4. current research programs
5. current specifications and work packages
6. historical material for context only
```

## Implementation fact authority order

```text
1. current code
2. current tests and static checks
3. reproducible runtime/research Artifacts
4. docs/status/Current-State.md and Capability-Matrix.md
5. commit-bound audit evidence
6. historical status/plans
```

Never use a plan or design document to overrule executable evidence. Never change Constitution without explicit authorization.

## Current implementation boundary

Implemented/tested on the audited main baseline: identity/time/data contracts, calendar, PIT universe/eligibility, Feature and Candidate datasets, B0/B1, diagnostics, provider routing, Tencent exploratory path, Xuntou native/v4 semantics, Entry Path Target infrastructure, Research Artifact verification and PIT replication mechanics.

Externally blocked: real qualified Xuntou v4/XtQuant input and formal replication run.

Not canonical on main: platform registry/governance until PR #12 is merged, Phase D daily snapshot/recommendations, actual-position authority, Holding/Exit, review/attribution, portfolio, Codex evidence pack and QuantDesk integration.

## Non-negotiable rules

- Candidate Prediction ≠ Entry ≠ Lifecycle ≠ Exit ≠ Portfolio ≠ Execution.
- Target horizon ≠ holding or exit time.
- Exit is not inverse Entry.
- Empty results and `NO_ACTION` are valid; `NO_ACTION ≠ HOLD`.
- A score is not a probability without calibration.
- Data authority cannot inflate; no silent provider substitution or invented PIT/finality/adjustment.
- One primary change per experiment; preserve negative results.
- Codex diagnoses and proposes; it does not mutate, promote or execute.
- New platform responsibility does not enter Legacy God Objects.
- Every implementation claim cites code/test/artifact evidence.

## Provider rules

Xuntou/ThinkTrader/XtQuant remains the formal provider direction. Tencent/BaoStock/Tushare/AKShare/EastMoney are explicit auxiliary or exploratory sources unless a qualified contract says otherwise. A runnable adapter is not formal evidence.

## Work-package discipline

Every work package declares objective, bounded contexts, dependencies, inputs, outputs, affected files, contracts, code work, tests, acceptance evidence, risks, stop conditions, migration effect, documentation updates and non-goals. Use [the detailed Phase D work packages](docs/roadmap/work-packages/README.md).

## Validation

```bash
python scripts/check_docs_links.py
python -m pytest -q
python -m ruff check .
python -m mypy
```

Report exactly what ran. Do not claim a capability, test result, Alpha result or provider authority that was not observed.
