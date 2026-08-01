---
name: advance-production-lifecycle
description: Continuously advance the Market Regime Alpha WP-PDL engineering program through dependency-ready phases with code-first analysis, vertical implementation, tests, documentation, checkpoint commits and evidence-preserving recovery. Use when the user asks to improve, complete or continue the whole engineering project.
disable-model-invocation: true
---

Advance the complete `WP-PDL — Production Decision Lifecycle` program. This is a continuous implementation workflow, not a planning-only review.

## Program authority

Read and obey:

- `CLAUDE.md`;
- `AGENTS.md`;
- `docs/architecture/10-Production-Decision-Lifecycle.md`;
- `docs/architecture/decisions/ADR-004-Production-Decision-Lifecycle-Organization.md`;
- `docs/specs/Production-Decision-Lifecycle-Requirements.md`;
- `docs/roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md`;
- `docs/audit/Production-Decision-Lifecycle-Gap-Analysis.md`;
- `docs/prompts/Claude-Code-Production-Decision-Lifecycle.md`.

Actual code, tests and reproducible Artifacts override implementation claims in prose. Normative architecture and evidence ceilings remain binding unless explicitly superseded.

## Startup

1. Run `git status --short --branch`, `git rev-parse HEAD`, `git diff --stat` and inspect untracked files.
2. Preserve every user change. Do not fetch, pull, switch, reset, clean, stash or rewrite history unless explicitly authorized.
3. Never implement directly on `main`; use the current isolated branch or create a dedicated program branch from the verified local HEAD.
4. Record the baseline branch, HEAD, workspace state, current phase, evidence ceiling and unresolved assumptions.
5. Read actual code, imports, call chains, migrations and tests before editing.

## Dependency order

Execute only dependency-ready phases:

```text
Phase 0  Code facts, architecture reconciliation and test baseline
Phase 1  Operational Research Bridge
Phase 2  Durable Model Registry and Experiment Governance
Phase 3  Signal Engine and multi-horizon PathForecast
Phase 4  TradingOpportunity and TradingThesis
Phase 5  Portfolio and independent Risk Authority
Phase 6  Manual Execution Record and fill-derived Position authority
Phase 7  Holding, Exit and Attribution
Phase 8  Sustained Shadow operations and operator surface
```

Do not skip an unfinished dependency and do not build future horizontal shells without an executable vertical slice.

## Continuous work loop

For each phase:

```text
Scan affected code and tests
→ Build current-state and dependency model
→ Check target assumptions against code facts
→ Freeze scope, invariants and acceptance tests
→ Add or strengthen tests
→ Implement the smallest coherent vertical slice
→ Run focused tests
→ Fix ordinary failures
→ Run full repository validation
→ Run an independent review using bounded subagents where useful
→ Update status, architecture, audit and runbook documents
→ Inspect diff and migration impact
→ Create a semantic checkpoint commit
→ Continue to the next dependency-ready phase
```

Do not stop after a scan, plan, expected red test, ordinary defect, documentation update or checkpoint commit. Continue until a genuine blocker or the approved program boundary is reached.

## Genuine blockers

Stop the affected phase only when:

- a required external Provider/runtime is unavailable;
- an unresolved business or risk value has no approved value and no fail-closed default;
- formal PIT, OOS, calibration or trading authority would need to be fabricated;
- historical Artifact/model identity or actual-position authority cannot be preserved;
- a Constitution or accepted ADR conflict requires explicit user resolution;
- the next action would require live broker mutation, automatic model promotion or another prohibited capability.

A blocker in one independent lane must not prevent safe work in another dependency-ready lane. Publish exact evidence, impact and the smallest required user decision.

## Mandatory invariants

- Preserve one authority per identity, data, configuration, model, experiment, run, fill and position domain.
- Do not create duplicate Runtime Journals, registries, Artifact envelopes, Candidate models, state machines or position ledgers.
- Candidate, Signal, Forecast, Opportunity, Thesis, Portfolio, Risk, Execution, Position, Holding, Exit and Evaluation remain separate.
- Actual Position state comes only from observed fills.
- Risk rejection cannot create an approved intent.
- Scores are not probabilities without calibration.
- Public capital proxies do not identify hidden actors.
- Existing MR1 next-session 10:30 and frozen `daily_research` identities retain their semantics.
- No LIVE_ORDER, QMT/PTrade mutation, unattended trading, automatic model promotion or live risk-limit mutation.
- All result-affecting evidence is versioned and traceable.

## Validation and checkpoints

After every phase run:

```bash
git diff --check
python scripts/check_docs_links.py
python -m pytest -q tests/scripts/test_check_docs_links.py
python -m pytest -q tests/platform
python -m pytest -q
python -m ruff check .
python -m mypy
```

Also run focused tests for the affected contexts, migrations, replay, concurrency, idempotency, recovery and compatibility.

Report every command as `PASS`, `FAIL`, `NOT_RUN`, or `BLOCKED`. Fix ordinary failures before continuing. Each checkpoint commit must contain one dependency-coherent phase or correction and must exclude unrelated user files.

## Required documentation updates

When implementation facts change, update:

- `docs/status/Current-State.md`;
- `docs/status/Capability-Matrix.md`;
- `docs/status/Gap-Register.md`;
- relevant architecture and domain documents;
- `docs/roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md`;
- `docs/operations/Production-Decision-Lifecycle-Runbook.md`;
- a commit-bound delivery audit for the completed phase.

Do not change a status from planned or contract-only to implemented without code and test evidence.

## Final report

Return a consolidated report with:

```text
BASELINE AND WORKSPACE
CURRENT-STATE MODEL
DESIGN ASSUMPTIONS CONFIRMED OR REJECTED
PHASES COMPLETED
CHECKPOINT COMMITS
FILE AND DATABASE CHANGES
TEST COMMANDS AND RESULTS
AUTHORITIES AND COMPATIBILITY PRESERVED
CAPABILITY MATRIX BEFORE AND AFTER
ROLLBACK AND RECOVERY
UNFINISHED WORK
GENUINE BLOCKERS AND REQUIRED USER DECISIONS
EVIDENCE CEILING AND NON-CLAIMS
NEXT DEPENDENCY-READY PHASE
PR AND MERGE STATE
```

Do not claim that the entire project, strategy, production environment or trading system is complete unless every relevant production gate has reproducible evidence and explicit approval.
