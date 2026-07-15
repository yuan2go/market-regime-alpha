# AGENTS.md — Market Regime Alpha Execution Contract

This file governs repository work performed by coding agents, including Codex-style implementation agents.

It is an execution contract, not a replacement for the Constitution.

---

## 1. Project Mission

`market-regime-alpha` is an Alpha Research Operating System for the China A-share market.

The canonical research and decision direction is:

```text
Market / ETF / Theme / Capital Context
        ↓
Tradable Universe
        ↓
Feature / Factor Research
        ↓
Candidate Discovery
        ↓
Entry
        ↓
Position Lifecycle
HOLD / ADD / REDUCE / ROTATE / EXIT
        ↓
Portfolio Decision
        ↓
Execution Simulation / Execution
        ↓
Validation / Review / Research Feedback
```

The project is not defined as:

```text
a fixed next-morning-exit strategy
a single-stock timing engine
a MACD strategy
a Chan strategy
a Tuishen strategy
an ETF-only strategy
a giant rule score
a provider-integration project
```

---

## 2. Document Precedence

Read and obey documents in this order:

```text
1. docs/constitution/00-Project-Vision.md
2. docs/constitution/01-Core-Principles.md
3. docs/constitution/02-Architecture-Blueprint.md
4. docs/constitution/03-Research-Framework.md
5. docs/constitution/04-Data-Constitution.md
6. docs/constitution/05-Factor-Constitution.md
7. docs/constitution/06-Strategy-Constitution.md
8. docs/constitution/07-Validation-Constitution.md
9. docs/constitution/08-Roadmap.md
10. docs/constitution/09-Glossary.md
11. current architecture / research audit documents
12. current implementation-status documents
13. lower-level specifications and task-specific work packages
14. code
15. Legacy behavior, when characterized and intentionally preserved
```

Never change the Constitution unless the user explicitly requests a constitutional change.

If lower-level documentation conflicts with the Constitution, stop and report the conflict.

---

## 3. Current Active Authority Documents

Before implementing current R5 / Candidate / Entry / Exit work, read at minimum:

```text
docs/research/R5-Current-Status.md
docs/research/R5-Xuntou-Provider-and-Strategy-Priority.md
docs/research/R5-Data-Source-Role-Matrix.md
docs/research/R5-Candidate-Model-Research-Program.md
docs/research/Entry-Position-Lifecycle-Exit-Research-Program.md
docs/architecture/Original-Intent-to-Current-Docs-and-Codex-Readiness-Audit.md
```

Where status lines differ, the newest explicitly designated current-status authority wins.

Historical audit and status documents remain evidence; do not reinterpret them as current implementation truth when a newer current-status document explicitly supersedes them.

---

## 4. Current Data-Source Decision

The active primary data provider is:

```text
Xuntou / ThinkTrader / XtQuant
```

Auxiliary sources may include:

```text
Eastmoney
Tencent public market interfaces
other explicitly identified public sources
```

Rules:

1. Xuntou is the current canonical provider-backed rehearsal path.
2. Public sources are auxiliary unless an identified Dataset / Adapter / Research Charter says otherwise.
3. Never silently substitute a public-source field for a Xuntou field.
4. Never invent availability time, PIT semantics, bar finality, adjustment basis, membership history, liquidity identity or buyability.
5. Implement only the Xuntou data path required by an identified research experiment.
6. More provider API coverage is not automatically research progress.

---

## 5. Non-Negotiable Architecture Rules

### 5.1 Prediction is not action

```text
Candidate Prediction
≠
Entry Proposal
≠
Position Lifecycle Proposal
≠
Portfolio Decision
≠
Execution Result
```

### 5.2 Entry and Exit are independent

Do not implement:

```text
Exit = inverse of Entry score
```

### 5.3 Candidate Target Horizon is not Exit Time

```text
Target Horizon
≠
Mandatory Holding Period
≠
Mandatory Exit Time
```

### 5.4 Valid empty results are allowed

Do not fabricate fallback Candidates, trades, positions or signals.

### 5.5 `NO_ACTION` is not `HOLD`

Preserve canonical action semantics.

### 5.6 Score is not probability

Do not rename a normalized score to probability without an explicit calibrated probability contract and evidence.

### 5.7 Data eligibility must not inflate

Derived artifacts cannot gain stronger authority than required source inputs justify.

### 5.8 Feature lineage is mandatory

Do not add a Feature without explicit identity, source information family, source fields or input Feature lineage, time availability semantics and research status.

### 5.9 Do not double-count the same information silently

MACD, moving averages, momentum, price location, Chan-derived price structure and Tuishen-inspired price-volume transforms may share underlying OHLCV information.

Agreement among correlated transforms is not automatically independent confirmation.

### 5.10 Legacy is not the V2 kernel

Do not add new platform responsibility to:

```text
backtest.py
CoscoTimingEngine
dividend_t God Objects
```

unless the task is explicit Legacy characterization or compatibility work.

---

## 6. Research Rules

Every new model / feature / strategy increment must define:

```text
research question
market scope
Candidate / ETF / instrument pool
Decision Time
Target Identity
Feature / evidence source
entry condition or decision policy, when applicable
exit / lifecycle boundary, when applicable
position / risk boundary
baseline comparator
ablation
chronological validation
failure conditions
review outputs
```

External papers and public strategies are hypothesis sources.

They do not become project authority until reproduced under project data, targets and validation rules.

Do not optimize by trying a large unrecorded grid and reporting only the best result.

Retain negative results when they invalidate a hypothesis.

---

## 7. Current Model Ladder

Candidate research progresses through:

```text
B0 — single-feature deterministic rank
B1 — transparent cross-sectional composite rank
B2 — regularized statistical baseline
B3 — nonlinear / Learning-to-Rank model
B4 — target-specific or multi-task opportunity model
B5 — Market / ETF / Theme context-conditioned increment
B6 — transaction-flow / order-flow increment
```

Do not jump directly to a complex model merely because it is available.

A more complex model must show incremental OOS value over a simpler baseline.

---

## 8. Entry / Lifecycle / Exit Research Direction

The practical buy/sell objective is path-dependent.

### Entry failure of interest

```text
ENTER -> adverse event before favorable event
```

Initial target family:

```text
UP_FIRST
DOWN_FIRST
TIMEOUT
```

### Exit failure of interest

```text
EXIT -> strong favorable continuation
```

Initial continuation target family:

```text
CONTINUE_UP_FIRST
DRAWDOWN_FIRST
TIMEOUT
```

Diagnostics include:

```text
Post-Exit Regret
Avoided Drawdown
Late Exit
Profit Giveback
```

Do not implement a monolithic buy/sell score in place of these separate research problems.

---

## 9. Current Implementation State to Preserve

Current known state includes:

```text
Candidate dataset / panel contracts                     implemented
Close Return / MFE / MAE rehearsal target family       implemented
B0 deterministic ranker                                implemented
B1 transparent composite core                          implemented
B1 latest full verification                            not confirmed
Historical Trading Calendar                            implemented
Historical PIT Universe artifacts                      implemented
Eligibility v1 / provider-rehearsal v2                 implemented
Provider-neutral rehearsal market artifact             implemented
Generic provider export adapter                        implemented
Xuntou selected as primary provider                    decided
Xuntou native-field adapter                            not yet implemented
real Xuntou provider-backed rehearsal run              not available
Entry path Target code contract                        not yet implemented
canonical Position State contract                      not yet implemented
Exit continuation Target code contract                 not yet implemented
formal Alpha evidence                                  not available
```

Do not claim a missing capability is implemented because a high-level document exists.

Do not claim tests passed unless they were actually executed successfully in the current repository state.

---

## 10. Quality Commands

From the repository root, install development dependencies when needed:

```bash
pip install -e ".[dev]"
```

Primary quality commands:

```bash
python3 -m pytest
python3 -m ruff check .
python3 -m mypy
```

For a bounded task:

1. run the smallest relevant tests first;
2. run broader affected-area tests;
3. run the full quality commands when the environment permits;
4. report exactly what ran and what did not run.

Never report:

```text
all tests pass
```

when only a focused subset ran.

---

## 11. Work-Package Discipline

Each implementation task should have:

```text
one primary objective
explicit files / bounded context
explicit non-goals
acceptance tests
stop conditions
```

Preferred loop:

```text
Read current authority docs
        ↓
Inspect affected code and tests
        ↓
Write / update characterization or contract tests
        ↓
Implement one bounded change
        ↓
Run focused validation
        ↓
Run broader validation when possible
        ↓
Review for Constitution / ownership drift
        ↓
Commit intentionally
```

Do not mix in unrelated refactors.

---

## 12. Current Recommended Work Packages

### WP-0 — Close B1 Verification

Scope:

```text
repair AVAILABLE Target fixture so future observed_at evidence is present
introduce a common structural ranking evaluation interface for B0 and B1
remove B0-specific type workaround
export B1 public API where intended
include B1 in mypy scope
run focused and broader checks
```

Non-goal:

```text
do not change B1 scoring semantics
```

### WP-1 — Xuntou P0 Native Mapping Specification

Scope only fields required by current Candidate experiments.

Do not build broad API coverage.

### WP-2 — Xuntou P0 Native Adapter

Implement only after the field mapping and semantics are explicit.

### WP-3 — Provider-Backed B0 / B1 REHEARSAL Run

No Alpha claim.

### WP-4 — Entry Path Target Contracts

Implement target identity and materialization semantics before a complex model.

### WP-5 — EXP-ENTRY-001

Compare Candidate-only against Candidate + simple Entry timing gate.

### WP-6 — Canonical Position State Contract

Required before substantive Exit model work.

### WP-7 — Exit Continuation Targets and Control Arms

Implement simple control arms before nonlinear / survival / optimal-stopping models.

---

## 13. Stop and Escalate Conditions

Stop implementation and report before proceeding when any of the following occurs:

1. a requested change conflicts with the Constitution;
2. two current documents claim incompatible authority;
3. provider semantics would need to be guessed;
4. historical PIT meaning is ambiguous;
5. a change would collapse Candidate, Strategy, Portfolio and Execution ownership;
6. a task requires opening or retuning sealed final-test evidence;
7. a new feature duplicates existing information without a lineage / ablation plan;
8. an implementation would require changing project goals rather than implementing them;
9. the required acceptance test cannot be expressed from the current contract;
10. a broad rewrite is proposed where a compatibility boundary or incremental extraction is possible.

Do not resolve these by silently choosing an interpretation.

---

## 14. Commit Discipline

Prefer small, intentional commits.

Examples:

```text
test: ...
feat: ...
fix: ...
docs: ...
chore: ...
```

A commit should have one dominant reason to exist.

Do not combine:

```text
architecture change
+
model semantics change
+
provider change
+
large formatting cleanup
```

in one commit.

---

## 15. Final Rule

> **Implement the smallest evidence-preserving change that advances the currently approved research work package. Do not redesign the project from local code context, do not invent missing market-data semantics, do not convert hypotheses into trading authority, and do not collapse Candidate Discovery, Entry, Position Lifecycle and Exit into another monolithic rule engine.**
