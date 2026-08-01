# CLAUDE.md — Market Regime Alpha Project Memory

@AGENTS.md

This file is the Claude Code project entry point. `AGENTS.md` is the shared cross-agent execution contract and remains authoritative for rules that apply to every coding agent.

## Startup protocol

Before editing:

1. Run `git status --short --branch`, `git rev-parse HEAD`, `git diff --stat`, and inspect untracked files.
2. Treat the current checked-out workspace and local code as the implementation-fact baseline. Preserve all user changes. Do not run `git fetch`, `git pull`, `git switch`, `git reset`, `git clean`, `git stash`, destructive checkout, or history-rewriting commands unless the user explicitly authorizes them.
3. Never implement directly on `main`. Create or reuse one dedicated feature branch from the current verified HEAD without discarding local changes.
4. Read, in order:
   - `docs/README.md`;
   - `docs/status/Current-State.md`;
   - `docs/status/Capability-Matrix.md`;
   - `docs/status/Gap-Register.md`;
   - `docs/architecture/09-Platform-Architecture-V2.md`;
   - `docs/architecture/10-Production-Decision-Lifecycle.md`;
   - `docs/specs/Production-Decision-Lifecycle-Requirements.md`;
   - `docs/roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md`;
   - `docs/audit/Production-Decision-Lifecycle-Gap-Analysis.md`;
   - the bounded-context documents and tests affected by the next phase.
5. Inspect executable code, imports, call chains, migrations and tests before accepting any implementation claim from prose.
6. Record the baseline branch, HEAD, working-tree state, scope, non-goals, evidence ceiling and unresolved assumptions before implementation.

## Current engineering program

The current canonical engineering program is:

```text
WP-PDL — Production Decision Lifecycle
```

The objective is to complete the existing repository as a production-grade, human-in-the-loop A-share research and decision-support platform. The system remains a modular monolith with explicit bounded contexts and immutable evidence authority. It does not become an unattended live-trading system in this program.

The dependency-ordered implementation sequence is:

```text
Phase 0  Code facts, architecture reconciliation and test baseline
Phase 1  Operational Research Bridge
Phase 2  Durable Model Registry and Experiment Governance
Phase 3  Signal Engine and multi-horizon PathForecast
Phase 4  TradingOpportunity and TradingThesis
Phase 5  Portfolio construction and independent Risk Authority
Phase 6  Manual Execution Record and fill-derived Position authority
Phase 7  Holding, Exit and Attribution
Phase 8  Sustained Shadow operations and operator surface
Future   Separately approved broker adapter; no authority is implied now
```

Work vertically in dependency order. Do not horizontally create every future interface before the preceding phase has an executable, tested and replayable slice.

## Continuous execution mode

When the user asks Claude Code to improve or complete the engineering program, continue through the dependency-ordered phases without stopping for ordinary planning checkpoints, commits, expected red tests, local code defects or documentation updates.

After each coherent phase:

1. run focused tests;
2. run the required repository quality gate;
3. fix ordinary failures;
4. review the complete diff and migration impact;
5. update implementation-state and delivery evidence documents;
6. create a semantic checkpoint commit;
7. continue to the next dependency-ready phase.

Stop only for a genuine blocker that cannot be resolved from code, tests, repository evidence or safe implementation work, including:

- a required external Provider/runtime is unavailable;
- a business or risk parameter has no approved value and no fail-closed default is allowed;
- formal PIT, OOS or trading authority would have to be invented;
- historical Artifact identity or actual-position authority cannot be preserved;
- a Constitution or accepted ADR conflict requires an explicit user decision;
- progress would require live broker mutation or another prohibited capability.

A blocked phase must produce a precise evidence report and must not prevent work on independent, dependency-safe improvements.

## Mandatory execution loop

Use this sequence for every phase:

```text
Scan code and tests
→ Build the current-state model
→ Check design assumptions against implementation facts
→ Freeze scope, invariants and acceptance tests
→ Add or strengthen tests
→ Implement the smallest coherent vertical slice
→ Run focused validation
→ Fix failures
→ Run full regression validation
→ Update architecture, status, audit and runbook documents
→ Review diff, migration and compatibility
→ Commit semantically
→ Continue or report a genuine blocker
```

Do not stop after producing a plan when implementation is possible. Do not report a phase complete when only contracts, fixtures or documentation exist.

## Architecture constraints

- Reuse existing Stable IDs, semantic times, `DataEligibility`, SourceManifest, Universe, Eligibility, Feature, Candidate, Target, Experiment and Artifact authorities.
- Do not create parallel registries, duplicate ontologies, a second Runtime Journal, a second position ledger or another configuration authority.
- Immutable research Artifacts remain evidence authority; operational databases store indexes, mutable workflow state, approvals, manual records and projections.
- Result-affecting contracts must be typed, versioned, deterministic and content-addressed where appropriate.
- Preserve complete populations, rankings, exclusions, missingness, reason codes and lineage, not only Top-K projections.
- Fail closed on missing, stale, late, unknown, conflicting or incompatible evidence.
- Candidate, Signal, Forecast, Opportunity, Thesis, Portfolio, Risk, Execution, Position, Holding, Exit and Evaluation remain distinct authorities.
- Actual Position state comes only from observed manual or future broker fills, never from recommendations or target positions.
- Risk rejection cannot be overridden by strategy code or ordinary operator actions.
- Legacy code may be characterized and adapted, but new platform responsibility must not enter Legacy God Objects.
- Historical Artifacts are immutable; corrections use new versions, explicit corrections or `supersedes` relationships.
- Existing MR1 next-session 10:30 and `daily_research` compatibility semantics must not be silently repurposed.

## Research and trading governance

Always distinguish:

```text
FACT
INFERENCE
HYPOTHESIS
MODEL ASSUMPTION
EXPERIMENT
RESULT
LIMITATION
INVALIDATION CONDITION
TRADING PLAN
RISK
```

No fixture, public-source dry run, mechanical model slice, descriptive return or passing unit test may be promoted into Formal PIT, Formal OOS Alpha, a model winner, production readiness or trading authority.

Claude may diagnose, implement approved phases, run experiments, produce evidence packs and draft promotion proposals. Claude may not automatically mutate active models, promote models, open sealed validation evidence, change approved live risk limits or place real orders.

## Git and workspace rules

- Preserve unrelated local and user changes; never overwrite them to obtain a clean diff.
- One dependency-coherent phase or bounded correction per checkpoint commit.
- Use a dedicated feature branch or worktree when available; do not require a new branch if the user already supplied a valid isolated branch.
- Do not merge, force-push, rewrite history or delete branches unless explicitly requested.
- Do not pause merely to ask whether to commit; checkpoint commits are part of continuous execution.
- Before every commit, run `git diff --check`, inspect staged and unstaged changes, and exclude credentials, local settings, generated secrets and unrelated files.
- Open a Draft PR only when requested or when the repository workflow requires it. Do not merge automatically.

## Validation

Minimum repository validation:

```bash
git diff --check
python scripts/check_docs_links.py
python -m pytest -q tests/scripts/test_check_docs_links.py
python -m pytest -q tests/platform
python -m pytest -q
python -m ruff check .
python -m mypy
```

Also run the focused tests required by the affected bounded contexts, migrations, recovery paths and compatibility Readers. Report every command as `PASS`, `FAIL`, `NOT_RUN`, or `BLOCKED`; never collapse partial validation into “all passed.”

## Claude Code project assets

- Project subagents: `.claude/agents/`
- Reusable project skills: `.claude/skills/`
- Asset guidance: `.claude/README.md`
- Master implementation prompt: `docs/prompts/Claude-Code-Production-Decision-Lifecycle.md`

Use `/advance-production-lifecycle` for the continuous WP-PDL program and `/implement-work-package` for a single bounded work package. Subagents are for bounded evidence collection and review; the main Claude session remains responsible for implementation, integration, validation and final claims.

## Completion report

Every execution report must include:

1. baseline branch, HEAD and workspace state;
2. code and call-chain facts discovered;
3. design assumptions confirmed, rejected or changed;
4. phases and checkpoint commits completed;
5. files, contracts, schemas and migrations changed;
6. invariants and authorities preserved;
7. focused and full validation results;
8. compatibility, rollback and data-migration effects;
9. Capability Matrix before and after;
10. remaining gaps, external blockers and unresolved business decisions;
11. evidence ceiling and explicit non-claims;
12. exact next dependency-ready phase.

Never report “project complete,” “strategy proven,” “model profitable,” “production ready” or “ready for live trading” without matching reproducible evidence and explicit governance approval.
