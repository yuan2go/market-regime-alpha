# AGENTS.md — Market Regime Alpha Execution Contract

> **Status:** CURRENT_STATUS  
> **Authority:** Repository execution contract for coding and research agents  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-06
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** CLAUDE.md, docs/README.md, docs/status/Current-State.md, docs/architecture/10-Production-Decision-Lifecycle.md, docs/roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md  
> **Code Evidence:** `src/market_regime_alpha`; `tests`; target-state statements are explicitly separated from implementation facts.

## Mission

`market-regime-alpha` is an A-share Alpha Research Operating System. The current product boundary is a production-grade, human-in-the-loop research and trading decision-support platform, not unattended live trading.

```text
Data and Evidence
→ Market / ETF / Theme / Capital Context
→ Tradable Universe and Features
→ Candidate Discovery
→ Signal and Path Forecast
→ Trading Opportunity and Thesis
→ Portfolio and Risk
→ Manual Execution Record
→ Fill-derived Position Lifecycle
→ Holding and Exit
→ Validation, Attribution and Research Feedback
```

## Agent entry points

- `AGENTS.md`: shared cross-agent execution contract.
- `CLAUDE.md`: Claude Code project memory; imports this file and adds Claude-specific workflow.
- `.claude/agents/**`: bounded project subagents for evidence collection and review.
- `.claude/skills/**`: repeatable execution procedures.
- `docs/prompts/Claude-Code-Production-Decision-Lifecycle.md`: master program prompt.

Do not create a parallel instruction hierarchy that contradicts these files.

## Normative authority order

```text
1. Latest explicit user decision not superseded
2. docs/constitution/00–09
3. docs/architecture/00–11 and architecture/domains/**
4. current research programs
5. current specifications, accepted ADRs and work packages
6. historical material for context only
```

## Implementation fact authority order

```text
1. current checked-out code and actual call chains
2. current tests and static checks
3. reproducible runtime/research Artifacts and manifests
4. docs/status/Current-State.md and Capability-Matrix.md
5. commit-bound audit evidence
6. historical status and plans
```

Never use a plan or design document to overrule executable evidence. Never change Constitution without explicit authorization.

## Current implementation boundary

Implemented and tested on the current repository baseline include stable identity and semantic-time contracts, Provider and SourceManifest boundaries, PIT Universe and Eligibility contracts, Feature and Candidate datasets, B0/B1 PredictionRuns, Entry Path Target infrastructure, immutable Artifacts and Readers, the recoverable exploratory Daily Runtime Journal, public exploratory acquisition and replay, Platform V2 research, the Operational Research Bridge, durable PostgreSQL Model Registry and Experiment Governance adapters, Signal and uncalibrated PathForecast research, durable Opportunity/Thesis and Portfolio/Risk decisions, a manual Fill ledger, Fill-derived PositionSnapshot, independent Holding/Exit assessment models and complete-trade diagnostic evaluation/replay. PostgreSQL 16 is the only persistent Runtime, Journal, Repository, Replay, account, Position and Risk database; database unavailability fails closed.

These Phase 0–7 mechanics are not production-qualified. H1 complete-account
Portfolio/Risk, H2 Thesis-to-Outcome trace, H3 Fill-derived A-share T+1
sellability, H4 reducing-risk gate, H5 derived Thesis health, H6 composite
operational evidence and H4.5 reducing-risk-to-manual-intent mechanics are now
implemented and locally verified engineering checkpoints. Durable H7 assessment
state, H8 sustained Shadow operation, H9 formal validation, authenticated
operators and the operator workbench remain unimplemented.

The existing Continuous Runtime also owns one `DECISION_SYSTEM` child for a
14:30–14:55 Daily Summary, append-only Manual Account Observation,
Fill-derived Reconciliation, research-only Portfolio Proposal and independently
reloaded Risk Decision. These mechanics do not create Order, Fill or Position
changes and do not raise Entry or Broker authority.

External or evidence blockers remain for qualified formal data, operational PIT theme mappings, formal OOS Alpha, calibrated model probabilities and any live broker authority.

The current implementation program is `WP-PDL-HARDENING — Production Lifecycle Hardening and Shadow Readiness`. It extends the delivered WP-PDL mechanics in dependency order and preserves the existing evidence ceiling.

## Non-negotiable domain rules

- Candidate ≠ Signal ≠ Forecast ≠ Opportunity ≠ Thesis ≠ Portfolio ≠ Risk ≠ Execution ≠ Position ≠ Holding ≠ Exit.
- Target horizon is not an automatic holding or exit time.
- Exit is not inverse Entry.
- Empty results, `WAIT`, `DATA_INSUFFICIENT` and `NO_ACTION` are valid outcomes; `NO_ACTION ≠ HOLD`.
- A score is not a probability without calibration.
- Publicly observable capital proxies do not identify hidden institutional intent.
- Data authority cannot inflate; no silent Provider substitution or invented PIT, finality, availability or adjustment semantics.
- A recommendation, target position or intended order cannot create an actual position.
- Actual positions come only from observed manual or future broker fills.
- Risk rejection cannot be bypassed by strategy code or ordinary operator action.
- One primary research change per experiment; preserve negative and inconclusive results.
- Agents may diagnose, implement approved scope and propose model changes; they do not auto-mutate, auto-promote or execute models.
- New platform responsibility does not enter Legacy God Objects.
- Every implementation claim cites code, test, Artifact or runtime evidence.
- Historical Artifacts and identities remain immutable unless an explicit migration or supersession contract exists.
- Existing MR1 next-session 10:30 and `daily_research` compatibility identities retain their established meaning.

## Provider rules

Xuntou/ThinkTrader/XtQuant remains the formal Provider direction unless a later qualified contract changes that decision. Tencent, BaoStock, Tushare, AKShare and EastMoney remain explicit auxiliary or exploratory sources unless formal qualification evidence exists. A runnable adapter is not formal evidence.

## Workspace, branch and commit discipline

- Inspect the current workspace before any Git mutation.
- Preserve all unrelated user changes, untracked files and local configuration.
- Do not fetch, pull, switch, reset, clean, stash, force-push, rewrite history or delete branches unless explicitly authorized.
- Never implement directly on `main`; use the current isolated branch or create a dedicated feature branch from the verified local HEAD.
- Use one dependency-coherent phase or bounded correction per checkpoint commit.
- Do not pause merely to request permission for ordinary checkpoint commits when the user asked for continuous engineering execution.
- Do not merge automatically. Open or update a Draft PR only when requested or required by the repository workflow.
- Before every commit, run `git diff --check`, inspect all staged and unstaged changes, and exclude credentials, generated secrets, personal paths and unrelated files.
- After merge, reconcile Current State, Capability Matrix, Gap Register and delivery evidence when implementation facts changed.

## Continuous program discipline

When the user requests completion or broad improvement of the engineering project, the main agent must continue across dependency-ready WP-PDL phases rather than stop after a plan or a single ordinary defect.

Each phase must declare:

- objective and bounded contexts;
- current facts and assumptions;
- dependencies and non-goals;
- input and output contracts;
- invariants and authority ceilings;
- code and migration scope;
- focused and regression tests;
- acceptance evidence;
- rollback or forward-repair plan;
- documentation updates;
- genuine stop conditions.

A phase is complete only when it has executable behavior, required tests, compatibility evidence, documentation and a reviewable checkpoint commit. Documentation-only or contract-only work must be reported as such.

Stop only when a genuine blocker cannot be resolved safely from repository evidence, tests or implementation work. Ordinary compile errors, red tests, refactoring needs, documentation drift and local implementation defects are not stop conditions.

## Validation

```bash
git diff --check
python scripts/check_docs_links.py
python -m pytest -q tests/scripts/test_check_docs_links.py
python -m pytest -q tests/platform
python -m pytest -q
python -m ruff check .
python -m mypy
```

Run additional focused tests for affected bounded contexts, migrations, idempotency, concurrency, replay, recovery and compatibility Readers. Report every command as `PASS`, `FAIL`, `NOT_RUN`, or `BLOCKED`. Never claim a capability, Alpha result, Provider authority or production status that was not observed.
