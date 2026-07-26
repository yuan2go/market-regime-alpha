# CLAUDE.md — Market Regime Alpha Project Memory

@AGENTS.md

This file is the Claude Code project entry point. `AGENTS.md` is the shared cross-agent execution contract and remains authoritative for rules that apply to every coding agent.

## Startup protocol

Before editing:

1. Run `git status --short --branch`, `git fetch --all --prune`, and `git rev-parse HEAD`.
2. Never work directly on `main`; create one branch for one Work Package or bounded correction.
3. Read, in order:
   - `docs/README.md`;
   - `docs/status/Current-State.md`;
   - `docs/status/Capability-Matrix.md`;
   - `docs/status/Gap-Register.md`;
   - the selected file under `docs/roadmap/work-packages/`;
   - the relevant architecture, research and specification documents.
4. Inspect current code and tests before trusting any implementation claim in prose.
5. State the actual baseline HEAD, scope, non-goals and evidence boundary before implementation.

## Current priority

The next canonical implementation package is:

```text
WP-D0 — Platform Governance Kernel Hardening
```

Do not skip ahead to DailyResearchSnapshot, Entry, Holding, Exit, Portfolio, Codex Feedback, QuantDesk or broker execution until WP-D0 acceptance evidence is complete.

WP-D0 must:

- close direct Model Registry lifecycle-bypass paths;
- separate input `DataEligibility` from model `EvidenceLevel`;
- define persistence/recovery protocols for Registry and Experiment Governance;
- include the Platform package in mypy coverage;
- preserve B0/B1 behavior through adapters and characterization tests;
- resolve the transparent-composite model currently misnamed as B2 through explicit migration;
- bind Multi-model Candidate runs to registered Model, Target, Evaluation and Frozen Experiment identities;
- produce an immutable, content-addressed PredictionRun.

WP-D0 must not change factors, weights, Target definitions, Universe semantics or Alpha conclusions.

## Execution loop

Use this sequence for every task:

```text
Scan
→ Diagnose
→ Freeze scope and invariants
→ Write or strengthen tests
→ Implement the smallest coherent change
→ Run focused validation
→ Run full validation
→ Update status/evidence documents
→ Review diff and migration impact
→ Commit semantically
→ Open a Draft PR
```

When a stop condition in the Work Package is met, stop and publish a blocked or negative result. Do not widen scope to manufacture success.

## Architecture constraints

- Reuse existing `StableId`, semantic-time, `DataEligibility`, Feature, Candidate Dataset, Candidate Prediction, Target and Experiment authorities.
- Do not create parallel registries or duplicate ontologies.
- Result-affecting contracts should be immutable, typed, versioned and content-addressed.
- Preserve complete populations, rankings, rejections and lineage—not only Top-K projections.
- Fail closed on missing, stale, late, unknown or incompatible data.
- Candidate Prediction, Entry, Holding, Exit, Portfolio and Execution remain independent authorities.
- Legacy code may be characterized and adapted, but new platform responsibility must not enter Legacy God Objects.
- Historical Artifacts are immutable; corrections use explicit versioning or `supersedes` relationships.

## Research governance

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
```

No test fixture, Tencent/public-source run, mechanical model slice or descriptive return may be promoted into Formal OOS Alpha, a model winner or trading authority.

Claude may diagnose, implement approved Work Packages and draft research proposals. Claude may not automatically mutate active models, promote models, open sealed validation evidence, change live risk limits or place real orders.

## Git and branch rules

- One primary objective per branch and PR.
- Do not merge a historical branch merely because its head is not an ancestor of `main`; first check merged-PR metadata and compare effective content.
- Do not force-push shared branches unless the user explicitly authorizes history replacement.
- Do not delete remote branches unless explicitly requested.
- Merge only after required CI succeeds and the diff matches the declared scope.
- After merging, re-read `main` and reconcile Current State when implementation facts changed.

## Validation

Minimum repository validation:

```bash
python scripts/check_docs_links.py
python -m pytest -q tests/scripts/test_check_docs_links.py
python -m pytest -q tests/platform
python -m pytest -q
python -m ruff check .
python -m mypy
```

Also run `git diff --check` and relevant focused tests. Report each command as `PASS`, `FAIL`, `NOT_RUN`, or `BLOCKED`; never collapse partial validation into “all passed.”

## Project Claude assets

- Project subagents: `.claude/agents/`
- Reusable project skills: `.claude/skills/`
- Asset guidance: `.claude/README.md`

Use subagents for bounded read-only analysis that would otherwise flood the main context. Use skills for repeatable procedures; keep durable facts and invariants in this file and `AGENTS.md`.

## Completion report

Every implementation report must include:

1. baseline HEAD and branch;
2. files and contracts changed;
3. invariants preserved;
4. focused and full validation results;
5. Capability Matrix before/after;
6. migration and compatibility effects;
7. remaining gaps and blockers;
8. evidence ceiling;
9. next Work Package;
10. PR URL and merge state.

Never report “project complete,” “strategy proven,” “model profitable,” or “ready for live trading” without matching reproducible evidence and explicit governance approval.
