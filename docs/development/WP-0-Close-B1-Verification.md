# WP-0 — Close B1 Verification

> **Status:** READY FOR CODEX IMPLEMENTATION
> **Owner boundary:** Candidate ranking verification and evaluation interface only
> **Primary objective:** Close the current B1 verification gap without changing B1 ranking semantics
> **Depends on:** Constitution, `AGENTS.md`, `R5-Current-Status.md`, `R5-Candidate-Model-Research-Program.md`

---

## 1. Objective

The B1 transparent composite ranking core and tests are already committed.

The current task is to close verification and integration gaps so B0 and B1 can be evaluated through one structural Candidate-ranking interface.

Do not redesign B1.

---

## 2. Current Known Issues

### Issue A — Invalid AVAILABLE Target fixture

In:

```text
tests/candidates/test_composite_baseline.py
```

an `AVAILABLE` `CandidateTargetValue` fixture currently provides:

```text
observed_at = None
```

The current Target contract requires an observed future target to carry explicit observation time evidence.

Repair the fixture so:

```text
TargetObservationStatus.AVAILABLE
→ value is present
→ observed_at is present
→ observed_at is after Decision Time
```

Do not weaken the Target contract to make the test pass.

### Issue B — Evaluation is typed to the B0 concrete run type

Current evaluation functions in:

```text
src/market_regime_alpha/candidates/evaluation.py
```

accept:

```text
CandidateRankingRun
```

from the B0 baseline.

B1 currently has a structurally compatible but distinct:

```text
CompositeCandidateRankingRun
```

The B1 test currently relies on a type-ignore workaround.

Replace the concrete B0-only evaluation type dependency with a minimal structural interface.

Preferred direction:

```text
typing.Protocol
```

or an equivalently explicit shared contract.

The structural interface should include only fields actually required by evaluation, such as:

```text
dataset_id
experiment_id
model_id
universe_id
target_id
decision_time
candidate_population_size
ranked_population_size
predictions
rejections
```

Do not create a broad new ranking hierarchy unless the minimal structural contract is insufficient.

### Issue C — Public API and mypy scope

Inspect whether B1 intended public symbols are exported from:

```text
src/market_regime_alpha/candidates/__init__.py
```

and whether the B1 module is included in the intended mypy scope in:

```text
pyproject.toml
```

Add only the exports / mypy coverage required by current repository conventions.

---

## 3. Files Expected to Change

Likely files:

```text
src/market_regime_alpha/candidates/evaluation.py
src/market_regime_alpha/candidates/__init__.py
src/market_regime_alpha/candidates/composite_baseline.py   only if required for typing compatibility

tests/candidates/test_composite_baseline.py
additional focused evaluation protocol tests if useful

pyproject.toml
```

Do not change unrelated files.

---

## 4. Non-Goals

Do not:

```text
change B1 score arithmetic
change rank-percentile semantics
change weight normalization semantics
change complete-case rejection policy
add new Features
add a machine-learning model
implement Xuntou adapter work
implement Entry / Exit targets
modify Legacy trading logic
change Constitution
```

---

## 5. Required Behavioral Invariants

### B1 scoring invariants

Preserve:

```text
within-cross-section rank-percentile normalization
explicit HIGHER_IS_BETTER / LOWER_IS_BETTER direction
normalized positive weights
strict complete-case rejection
prediction + rejection exact Candidate Population accounting
stable composite specification identity under equivalent component ordering / common weight scaling
ranking target blindness
```

### Evaluation invariants

Preserve:

```text
ranking Dataset identity must match Candidate Dataset
Universe identity must match
Target identity must match
Decision Time must match
Candidate Population size must match
predictions + rejections must preserve exact Candidate symbols
only AVAILABLE Target observations enter evaluation metrics
```

---

## 6. Acceptance Tests

At minimum, focused tests must prove:

1. an `AVAILABLE` Target fixture carries valid future `observed_at` evidence;
2. B0 ranking can still be evaluated without behavior change;
3. B1 ranking can be evaluated without `type: ignore`;
4. exact Candidate Population accounting remains enforced;
5. B1 rank-normalization scale invariance still holds;
6. B1 lower-is-better direction still works;
7. B1 missing components remain explicit rejections;
8. equivalent component ordering / common weight scaling retains specification identity;
9. the common ranking interface does not require B0-specific fields that B1 does not semantically own.

---

## 7. Validation Commands

Run focused tests first, for example:

```bash
python3 -m pytest tests/candidates/test_composite_baseline.py
python3 -m pytest tests/candidates/test_baseline_ranking_evaluation_guards.py
python3 -m pytest tests/candidates
```

Then run, when the environment permits:

```bash
python3 -m pytest
python3 -m ruff check .
python3 -m mypy
```

Report exactly which commands ran and their actual result.

---

## 8. Stop Conditions

Stop and report rather than expanding scope when:

1. the existing B0 and B1 run objects are not structurally compatible without changing model semantics;
2. fixing the issue appears to require a new architecture hierarchy rather than a minimal protocol;
3. current Target semantics conflict with another authoritative contract;
4. unrelated tests reveal a pre-existing failure outside the affected area;
5. a full-repository check cannot run because of environment or dependency limitations.

Do not hide these conditions with `type: ignore`, weakened validation or silent fallbacks.

---

## 9. Completion Definition

This work package is complete only when:

```text
B1 test fixture respects Target time semantics
B0 and B1 use one explicit structural evaluation interface
B1 evaluation requires no type-ignore workaround
focused Candidate tests pass in the execution environment
intended public exports and mypy scope are updated
no B1 scoring semantics changed
actual validation results are recorded honestly
```

---

## 10. Suggested Commit Sequence

Prefer small commits such as:

```text
fix: correct B1 target observation fixture
feat: generalize Candidate ranking evaluation contract
test: cover shared B0 B1 ranking evaluation interface
chore: include B1 ranking module in public API and mypy scope
```

Do not combine unrelated provider, Entry, Exit or Legacy work into WP-0.
