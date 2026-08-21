# Alpha Research Phase II Engineering Protocol

> **Status:** CURRENT_RESEARCH_PROGRAM
> **Authority:** Subordinate implementation and research protocol
> **Repository Baseline:** `main@fc373696990ccdffe5e46a39778fdfedac3e0308`
> **Evidence Ceiling:** `ENGINEERING_ONLY / EXPLORATORY / PIT_INCOMPLETE / NOT_PROVEN`
> **Last Updated:** 2026-08-21

This protocol records the dependency-coherent implementation scope following
WP-ALPHA-RESEARCH-01. It does not create runtime, data, Evidence, qualification
or trading Authority. Executable owners and persisted content-addressed records
remain authoritative.

## Baseline audit

| Item | Observed baseline |
|---|---|
| Branch / worktree | isolated `agent/alpha-research-phase-ii`; original worktree preserved |
| HEAD | `fc373696990ccdffe5e46a39778fdfedac3e0308` |
| Source workspace | existing branch with protected `.idea/modules.xml` modification; untouched |
| Packaged migration head | `090_tie_aware_pool_ranks` |
| Python / uv | Python 3.12.13 / uv 0.11.7 |
| PostgreSQL | PostgreSQL 16.14; sole persistent business Authority |
| Runtime | `CONTINUOUS_RESEARCH` sole all-day Runtime; Historical Research remains bounded |
| CI | no GitHub Actions run for merge commit `fc37369`; exact-merge CI status `NOT_RUN` |
| Physical normalized package | locator cannot be reopened locally; `PHYSICAL_REPRODUCTION_NOT_ESTABLISHED` |

The audited call chain is Historical Research Runtime → bounded Dataset Window
→ canonical Feature/Context/Candidate/Signal/Forecast materialization →
Target/Outcome → Research Panel → Golden Evaluation/Alpha Discovery →
append-only PostgreSQL Evidence. Candidate is currently consumed directly by
`StrategyRuntimeInput`; Signal, Forecast, Context and Risk are not explicit
Strategy input bindings at this baseline.

## Dependency order and boundaries

1. `WP-ALPHA-CORRECTNESS-01` independently checks source bars, persisted
   features, T+1 target semantics, placebo behavior, execution-time semantics,
   factor redundancy and dependence-aware inference.
2. `WP-ALPHA-RESEARCH-02` freezes a single-dimension external-validation
   Experiment for only a correctness-supported hypothesis.
3. `WP-ALPHA-CONTEXT-01` distinguishes session-level conditioning from genuine
   cross-sectional interactions.
4. `WP-CANDIDATE-POLICY-02` keeps Incumbent and Challenger identities separate
   and splits integrity, Alpha ranking and Context conditioning.
5. `WP-PREDICTION-01` binds Candidate, Signal, Forecast, Context, Risk,
   DecisionTime and model/version lineage into Strategy semantics.

The implementation reuses Historical Research, Research Panel, Target/Outcome,
Research Validation statistics, existing Experiment Definition, existing
Forecast primitives, PostgreSQL Historical Evidence and Model/Strategy
Governance. It must not add another runner, scheduler, Feature/Candidate/Outcome
engine, Evidence authority or qualification framework.

## Frozen research and evidence rules

- Correctness states are `CORRECTNESS_SUPPORTED`, `CORRECTNESS_FAILED`,
  `PARTIALLY_REPRODUCED` or `PHYSICAL_REPRODUCTION_NOT_ESTABLISHED`; never
  `ALPHA_PROVEN`.
- Placebo kind, algorithm, seed and protocol are content-addressed before
  evaluation. Supported kinds are symbol permutation, target permutation,
  target time shift, factor lag and deterministic random ranking.
- External validation changes exactly one of time, Universe or Provider. Target,
  DecisionTime, factor definitions/directions, Candidate score, Top-K, costs and
  evaluation protocol remain frozen.
- `FREE_DATA / PIT_INCOMPLETE` imposes `FORMAL_OOS=false` even for an independently
  frozen validation dataset.
- Market/Theme/Capital session constants are conditional session selectors, not
  stock-level hard Gates. Capital remains a public observable proxy, not hidden
  institutional intent. Global Theme scope is not stock-level industry Alpha.
- Challenger Candidate activation requires correctness and external-validation
  support. Synthetic/unit evidence may test the gate but cannot activate a real
  policy.
- Forecast probabilities remain absent until a calibration owner is resolved.
  Logistic outputs are raw scores, not probabilities.
- Historical evidence is immutable. A methodology defect adds
  `METHODOLOGY_INVALIDATED` and a `SUPERSEDED_BY` reference; it never deletes or
  rewrites the prior artifact.

## Test and execution ceiling

This phase runs focused unit tests, failure/boundary tests, documentation checks,
`git diff --check` and only the targeted PostgreSQL tests required to prove
persistence, idempotency and replay. It does not run a 126-session campaign,
CSI300/full-A-share campaign, Provider-scale external validation, prospective
campaign or Production qualification.

Until separately recorded otherwise:

```text
EMPIRICALLY_EXECUTED=false
EXTERNALLY_VALIDATED=false
FORMAL_OOS=false
PROSPECTIVE_PROVEN=false
STRATEGY_QUALIFIED=false
PRODUCTION_QUALIFIED=false
```
