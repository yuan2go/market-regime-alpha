# Claude Code Master Prompt — Complete the Production Decision Lifecycle

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Master implementation prompt for Claude Code  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-01  
> **Supersedes:** Earlier planning-oriented versions of this prompt  
> **Superseded By:** None  
> **Related Documents:** ../../CLAUDE.md, ../../AGENTS.md, ../architecture/10-Production-Decision-Lifecycle.md, ../architecture/decisions/ADR-004-Production-Decision-Lifecycle-Organization.md, ../roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md, ../specs/Production-Decision-Lifecycle-Requirements.md, ../audit/Production-Decision-Lifecycle-Gap-Analysis.md  
> **Code Evidence:** This is an execution instruction. Implementation claims must come from current code, tests and reproducible Artifacts.

Use the prompt below in Claude Code from the repository workspace.

---

You are the engineering lead for `market-regime-alpha`. Act as a senior Python architect, domain-modeling specialist, quantitative research engineer, data-governance engineer, test engineer and delivery owner.

Your task is not to produce another high-level plan. Your task is to inspect the actual repository and continuously implement the dependency-ready work required to complete the production decision-support lifecycle, while preserving all existing evidence, compatibility and authority boundaries.

## Repository and execution boundary

Repository:

```text
https://github.com/yuan2go/market-regime-alpha
```

Target architecture:

```text
Data and Evidence
→ Market / Theme / Capital Research
→ Candidate Discovery
→ Signal and multi-horizon PathForecast
→ TradingOpportunity and TradingThesis
→ Portfolio construction and independent Risk Authority
→ Manual Execution Record
→ fill-derived Position authority
→ Holding and independent Exit
→ Attribution, Scorecards and Governance
```

The engineering organization is fixed:

```text
existing repository
+ modular monolith
+ explicit bounded contexts
+ application-layer orchestration
+ immutable research evidence authority
+ append-only execution evidence
+ actual positions derived only from observed fills
```

Do not create a second project. Do not convert the repository into premature microservices. Do not implement unattended live trading in this program.

## Start by loading repository instructions

Read and obey, in order:

1. `CLAUDE.md`;
2. `AGENTS.md`;
3. `docs/README.md`;
4. `docs/status/Current-State.md`;
5. `docs/status/Capability-Matrix.md`;
6. `docs/status/Gap-Register.md`;
7. `docs/architecture/09-Platform-Architecture-V2.md`;
8. `docs/architecture/10-Production-Decision-Lifecycle.md`;
9. `docs/architecture/decisions/ADR-004-Production-Decision-Lifecycle-Organization.md`;
10. `docs/specs/Production-Decision-Lifecycle-Requirements.md`;
11. `docs/roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md`;
12. `docs/audit/Production-Decision-Lifecycle-Gap-Analysis.md`;
13. `docs/operations/Production-Decision-Lifecycle-Runbook.md`.

Then inspect actual code, imports, call chains, migrations, scripts and tests. Do not trust README, status documents or target architecture as implementation evidence when code differs.

## Workspace safety

Before any edit, run:

```bash
git status --short --branch
git rev-parse HEAD
git diff --stat
git ls-files --others --exclude-standard
```

Treat the current checked-out workspace as the implementation-fact baseline. Preserve every user change and untracked file.

Do not run any of the following unless the user explicitly authorizes them:

```text
git fetch
git pull
git switch
git checkout that overwrites files
git reset
git clean
git stash
force push
history rewrite
branch deletion
```

Never implement directly on `main`. Use the current valid isolated branch, or create a dedicated feature branch from the verified local HEAD without discarding changes.

Do not commit credentials, `.claude/settings.local.json`, brokerage secrets, personal paths or unrelated workspace files.

## Current facts that must remain true

The repository already contains important canonical capabilities. Reuse them rather than rebuilding them:

- stable domain identities and semantic times;
- Provider, Source Artifact and SourceManifest contracts;
- explicit availability, finality and data-eligibility semantics;
- PIT Universe and Trading Eligibility boundaries;
- Feature definitions and materializations;
- immutable, content-addressed research Artifacts and Readers;
- recoverable Daily Runtime Journal and stage receipts;
- Market Regime, Theme Rotation, Capital Evolution and Candidate Discovery V0/V2 research flow;
- B0/B1 PredictionRuns and compatibility adapters;
- Entry Path Target contracts;
- Platform V2 layer boundaries;
- Model Registry and Experiment Governance domain rules;
- fixed MR1 next-session 10:30 compatibility semantics;
- frozen `daily_research` compatibility identities.

Do not create duplicate StableId, SemanticTime, SourceManifest, Universe, Feature, Candidate, Runtime Journal, Artifact Envelope, Model Registry, Experiment Governance, configuration or position systems.

## Authority and domain invariants

The following distinctions are mandatory:

```text
Candidate
≠ Signal
≠ Forecast
≠ TradingOpportunity
≠ TradingThesis
≠ PortfolioDecision
≠ RiskDecision
≠ ExecutionIntent
≠ Fill
≠ PositionSnapshot
≠ HoldingAssessment
≠ ExitAssessment
≠ Attribution
```

Additional invariants:

1. A Candidate is not a buy list.
2. A score is not a probability without calibration.
3. Public capital proxies do not identify hidden institutional intent.
4. A Target horizon is not an automatic holding or exit time.
5. Exit is not inverse Entry.
6. `NO_ACTION`, `WAIT`, `DATA_INSUFFICIENT` and empty results are valid outcomes.
7. Strategy code cannot override a hard Risk rejection.
8. An intended or target position cannot create an actual position.
9. Actual Position state comes only from observed manual or future broker fills.
10. Fill, audit and lifecycle transition records are append-only; corrections create new records.
11. Historical Artifacts and identities are immutable.
12. Existing MR1 and `daily_research` compatibility contracts retain their established meaning.
13. Research evidence cannot silently promote itself from EXPLORATORY to Formal PIT, Formal OOS or trading authority.
14. No phase may add LIVE_ORDER, QMT/PTrade mutation, unattended broker execution, automatic model promotion or live risk-limit mutation.

## Mandatory work cycle

Follow this loop continuously:

```text
Scan code and tests
→ Build the current-state model
→ Compare target design with implementation facts
→ Freeze the next dependency-ready vertical slice
→ Define invariants and acceptance tests
→ Add or strengthen tests
→ Implement domain, persistence, application and adapter changes
→ Run focused tests
→ Fix ordinary failures
→ Run regression and quality gates
→ Perform independent architecture/evidence verification
→ Update status, architecture, audit and runbook documents
→ Review the complete diff and migration impact
→ Create a semantic checkpoint commit
→ Continue to the next dependency-ready phase
```

Do not stop after scanning, planning, producing red tests, finding ordinary defects, updating documentation or creating a commit. Fix ordinary problems and continue.

Do not ask whether to continue between dependency-ready phases. Continue until a genuine blocker is reached or the approved program boundary is completed.

## Genuine blockers

Stop only the affected phase when one of the following is true and cannot be resolved safely from repository evidence:

- a required external Provider/runtime is unavailable;
- a business or risk parameter has no approved value and no fail-closed default is valid;
- PIT, availability, finality, calibration, OOS or trading authority would have to be invented;
- historical Artifact/model identity or actual-position authority cannot be preserved;
- Constitution or an accepted ADR conflicts with the required implementation and explicit user resolution is necessary;
- the next step would require live broker mutation or another prohibited capability.

A blocker in one independent lane does not justify stopping safe work in another dependency-ready lane. Record the evidence, impact, attempted resolution and smallest required user decision.

## Dependency-ordered implementation program

### Phase 0 — Code facts, baseline and design reconciliation

Goal: establish a verified code-first baseline and remove stale assumptions before runtime changes.

Required work:

- inspect the actual package tree, imports, application flows, repositories, migrations, scripts and tests;
- identify current authorities, state machines and compatibility paths;
- compare code facts with Architecture 10 and the WP-PDL work package;
- classify capabilities as implemented, partial, missing, conflicting or externally blocked;
- run the full baseline validation suite;
- update `docs/audit/Production-Decision-Lifecycle-Gap-Analysis.md` only where new evidence changes conclusions;
- produce a phase execution ledger with dependencies and acceptance criteria.

Do not recreate existing architecture documents. Do not modify runtime code until the current-state model and test baseline are recorded.

### Phase 1 — Operational Research Bridge

Goal: convert verified DailyLoop evidence into a Platform V2 `ResearchInputBundle` without copying or inflating authority.

Suggested paths:

```text
src/market_regime_alpha/application/operational_research/
scripts/run_operational_research.py
tests/application/operational_research/
```

Required behavior:

- verify Artifact checksums and SourceManifest semantics;
- verify DecisionTime and AvailabilityTime;
- reuse existing Universe and Eligibility;
- preserve source Artifact IDs and hashes;
- create typed market, ETF, theme, capital and symbol observations;
- fail closed on missing required mappings or observations;
- never create a fake LIVE fixture or raise DataEligibility;
- deterministic run and replay;
- no network access during replay;
- no new responsibility inside `DailyLoopRunner`.

Acceptance tests include lineage preservation, late-evidence rejection, missing-mapping blocking, idempotent duplicate run and deterministic replay.

### Phase 2 — Durable Model Registry and Experiment Governance

Goal: make current governance rules recoverable, durable and concurrency safe.

Required behavior:

- define repository protocols around existing domain rules;
- retain in-memory adapters for unit tests;
- add SQLite durable adapters first;
- keep contracts PostgreSQL-compatible without premature migration;
- persist model registrations, lifecycle transitions, evidence references, experiment protocols and access budgets;
- use optimistic concurrency or equivalent compare-and-set;
- reject duplicate identity conflicts, invalid transitions and non-contiguous restore history;
- persistence must not bypass domain validation.

Acceptance tests include restart recovery, duplicate registration, concurrent transition, concurrent validation/sealed access, corrupt-history rejection and in-memory/SQLite contract parity.

### Phase 3 — Signal Engine and multi-horizon PathForecast

Goal: create replayable timing and path-risk research without creating a trade.

Signal V1 scope:

- price action;
- volume confirmation;
- trend confirmation;
- VWAP context;
- overheat state.

Required behavior:

- versioned model, configuration, Artifact, Reader and deterministic replay;
- consume only evidence available by DecisionTime;
- MA, MACD, RSI, KDJ and similar indicators remain features, not authority layers;
- preserve compatible `SignalSnapshot` contracts;
- add `PathForecast` rather than changing `NextSessionForecast` semantics;
- reuse Entry Path Target contracts;
- support horizon, barriers, MFE, MAE, return quantiles, uncertainty and calibration status;
- never emit probability when uncalibrated;
- preserve daily-bar dual-touch ambiguity and missing-evidence states.

Acceptance tests include temporal leakage rejection, missing feature behavior, reason codes, dual-touch ambiguity, missing future bars, deterministic publication/replay and absence of trade authority.

### Phase 4 — TradingOpportunity and TradingThesis

Goal: establish the explicit human decision boundary between research and trade consideration.

Implement under `decision/`:

- `TradingOpportunity` and `OpportunityState`;
- `TradingThesis` and `ThesisState`;
- `InvalidationCondition`;
- repository protocols and application services;
- audit events and optimistic concurrency.

Required behavior:

- Opportunity binds exact CandidateSet, SignalSnapshot, PathForecast, DecisionTime, model and configuration;
- deterministic or idempotent identity and explicit expiry;
- expired or evidence-mismatched Opportunity cannot become a Thesis;
- Thesis stores rationale, supporting evidence, invalidation, actor, time and version;
- invalidated Thesis cannot authorize ADD;
- Candidate cannot directly create a position or execution intent.

Acceptance tests cover state transitions, expiry, duplicate command, concurrent confirmation, evidence mismatch, invalidation and close.

### Phase 5 — Portfolio construction and independent Risk Authority

Goal: construct target positions and apply independent fail-closed risk constraints.

Implement or extend:

- `RiskBudget`;
- `PortfolioConstraint`;
- `TargetPosition`;
- `PortfolioDecision`;
- `RiskDecision`;
- repositories and application services.

Required behavior:

- consume active Theses, current authoritative positions, available cash and market risk ceiling;
- enforce gross exposure, symbol limit, theme limit, liquidity/capacity, T+1, available quantity and loss budget;
- persist exact limit snapshot and structured reason codes;
- fail closed on timeout, unavailable risk state or inconsistent position evidence;
- output only simulation or manual-confirmation semantics;
- Risk rejection cannot create approved execution intent.

Acceptance tests cover cash, concentration, exposure, T+1, conflicting Theses, timeout and non-bypassable rejection.

### Phase 6 — Manual Execution Record and fill-derived Position authority

Goal: create an append-only human execution ledger and actual positions derived only from fills.

Implement under `execution/`:

- `ManualTradeRecord`;
- manual order state;
- `Fill`;
- correction and deviation contracts;
- repositories and idempotent application services.

Implement under `position/`:

- `PositionSnapshot`;
- position lots and states;
- `PositionProjector`;
- reconciliation contracts and recovery.

Required behavior:

- fills append only;
- corrections create explicit new records;
- duplicate fill or idempotency key has no second effect;
- partial fill, cancellation, rejection and unknown state remain explicit;
- quantity, cost and PnL rebuild deterministically from fills;
- recommendations and target positions never create actual positions;
- mismatch enters reconciliation-required state and blocks new exposure.

Acceptance tests cover full/partial fill, duplicate fill, cancellation, correction, open/reduce/close, restart rebuild and reconciliation mismatch.

### Phase 7 — Holding, independent Exit and Attribution

Goal: complete the open-position lifecycle and controlled research feedback.

Required behavior:

- independent `HoldingAssessment` and `ExitAssessment`;
- consume current Thesis, authoritative Position and fresh market/theme/capital/signal evidence;
- Holding supports HOLD, ADD, REDUCE, WAIT and DATA_INSUFFICIENT;
- Exit supports NO_ACTION, WAIT, REDUCE, EXIT and DATA_INSUFFICIENT;
- ADD requires fresh Portfolio/Risk approval and is prohibited after Thesis invalidation;
- support T+1 unavailable-exit state;
- add complete-trade Outcome, MFE, MAE, capture ratio and selection/entry/holding/exit/sizing/execution attribution;
- publish immutable evaluation evidence;
- never mutate model configuration or lifecycle automatically.

Acceptance tests cover Holding/Exit independence, invalidated Thesis, T+1 constraints, closed lifecycle, attribution identity/hash and scorecard protocol.

### Phase 8 — Sustained Shadow operations and operator surface

Goal: prove that the full human-in-the-loop lifecycle can run repeatedly and be operated without direct database mutation.

Required behavior:

- scheduled operational research and position review;
- durable read models for daily plan, active Theses, positions, risk, exceptions and attribution;
- minimal CLI or FastAPI operator commands using application services;
- no UI-side recomputation of canonical scores;
- metrics, audit Trace, alerts and runbook procedures;
- sustained Shadow operation with no unexplained state, lineage or position mismatch.

Do not add live broker mutation. A broker adapter requires a separate accepted work package and explicit authority approval.

## Persistence rules

1. Immutable Artifacts remain research evidence authority.
2. Mutable workflow, approval, manual execution and position projections use repository interfaces.
3. SQLite is the first durable adapter for local and test execution.
4. Repository contracts must allow later PostgreSQL adapters.
5. Do not duplicate full Artifact semantics into mutable tables.
6. Every mutable aggregate has a version.
7. Every command has an idempotency key or deterministic identity.
8. Manual actions record actor, reason and time.
9. Fill, audit and lifecycle-transition histories are append-only.
10. Every migration has tests and rollback or safe forward-repair instructions.
11. Existing `daily_runs`, `stage_receipts` and `acquisition_stage_receipts` semantics do not change silently.

## Dependency constraints

- `core`, `data` and `evidence` do not depend on upper layers.
- `research` does not depend on decision, portfolio, execution or position.
- `signals` consumes verified research and evidence contracts only.
- `decision` does not write actual position state.
- `portfolio` and Risk do not manufacture research evidence.
- `execution` does not recompute research.
- `position` does not fetch Provider data directly.
- `evaluation` consumes versioned evidence and authoritative positions.
- `application` orchestrates cross-domain flows without owning domain truth.
- CLI/API/UI adapters call application services and never recompute canonical scores.
- Legacy and `daily_research` code are compatibility sources only.

## Tests and quality gates

After each phase run focused tests and then run:

```bash
git diff --check
python scripts/check_docs_links.py
python -m pytest -q tests/scripts/test_check_docs_links.py
python -m pytest -q tests/platform
python -m pytest -q
python -m ruff check .
python -m mypy
```

Also run relevant database, migration, concurrency, idempotency, replay, recovery, temporal leakage, compatibility and end-to-end tests.

Report each command as `PASS`, `FAIL`, `NOT_RUN`, or `BLOCKED`. Do not continue while an ordinary failure remains unresolved. Do not weaken or delete tests to manufacture success.

## Commits, review and rollback

- create one dependency-coherent checkpoint commit or small commit series per phase;
- do not combine unrelated refactors;
- inspect `git diff --check`, staged changes, unstaged changes and untracked files before every commit;
- preserve unrelated user work;
- keep schema and migration changes reversible or forward-repairable;
- preserve new evidence and ledgers during code rollback;
- use bounded subagents for independent architecture, evidence and repository verification;
- do not merge automatically;
- open or update a Draft PR only when requested or required by repository workflow.

## Documentation updates

When implementation facts change, update:

- `docs/status/Current-State.md`;
- `docs/status/Capability-Matrix.md`;
- `docs/status/Gap-Register.md`;
- relevant architecture and domain documents;
- `docs/roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md`;
- `docs/operations/Production-Decision-Lifecycle-Runbook.md`;
- a commit-bound delivery audit for every completed phase.

Do not change a capability from planned, designed or contract-only to implemented without matching code, test and runtime evidence.

## Final report format

Return one consolidated report:

```text
# 1. Baseline branch, HEAD and workspace state
# 2. Code-first current-state model
# 3. Design assumptions confirmed, rejected or changed
# 4. Dependency phases completed
# 5. Checkpoint commits
# 6. File, contract, schema and migration changes
# 7. Tests and quality gates actually executed
# 8. Authorities, compatibility and evidence ceilings preserved
# 9. Capability Matrix before and after
# 10. Rollback, recovery and operational impact
# 11. Unfinished work and genuine blockers
# 12. Exact user decisions still required
# 13. Next dependency-ready phase
# 14. PR and merge state
```

Do not claim that the project, strategy, model, production environment or trading system is complete unless every relevant production gate has reproducible evidence and explicit governance approval.

Begin now with the startup protocol and Phase 0. Do not stop after the plan when implementation is possible.

---
