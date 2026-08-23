# Alpha Research Phase II Engineering Protocol

> **Status:** CURRENT_RESEARCH_PROGRAM
> **Authority:** Subordinate implementation and research protocol
> **Implementation Checkpoint:** `agent/engineering-closure-architecture-convergence-01@879849b6b899944dd51961fee1e719f661c96833`, based on `main@b617844d338523d7dfea72642cfce8213121786e`
> **Evidence Ceiling:** `ENGINEERING_ONLY / EXPLORATORY / PIT_INCOMPLETE / NOT_PROVEN`
> **Last Updated:** 2026-08-24

This protocol records the dependency-coherent implementation scope following
WP-ALPHA-RESEARCH-01. It does not create runtime, data, Evidence, qualification
or trading Authority. Executable owners and persisted content-addressed records
remain authoritative.

## Baseline audit

| Item | Observed baseline |
|---|---|
| Branch / worktree | isolated `agent/engineering-closure-architecture-convergence-01`; original worktree preserved |
| Historical Phase II audit HEAD | `091324c7e28a2b6a3b89f894d18afc7380486d13` |
| Current implementation checkpoint | `879849b6b899944dd51961fee1e719f661c96833` |
| Source workspace | existing branch with protected `.idea/modules.xml` modification; untouched |
| Packaged migration head | `096_daily_alpha_outcome_lineage` |
| Python / uv | Python 3.12.13 / uv 0.11.7 |
| PostgreSQL | PostgreSQL 16.14; sole persistent business Authority |
| Runtime | `CONTINUOUS_RESEARCH` sole all-day Runtime; Historical Research remains bounded |
| CI / validation | no GitHub run for `b617844` or the unpushed closure branch; directly relevant unit/architecture/PostgreSQL owner tests are `PASS`, full repository pytest is `NOT_RUN` |
| Physical Raw/Normalized packages | owner rows/checksums exist, but locators cannot be reopened locally; `ORIGINAL_PHYSICAL_REOPENED=false` |

The audited call chain is Historical Research Runtime → bounded Dataset Window
→ canonical Feature/Context/Candidate/Signal/Forecast materialization →
Target/Outcome → Research Panel → Golden Evaluation/Alpha Discovery →
append-only PostgreSQL Evidence. At the audited baseline Candidate was consumed
directly by `StrategyRuntimeInput`; Phase II closes that contract gap for any
`FORECAST_REQUIRED` Strategy while preserving explicit `FORECAST_NOT_REQUIRED`
runtime semantics and byte-identical V1 payload identities for the incumbent
Overnight/Swing policies.

## Implemented engineering state

| Work Package | Implementation state | Empirical state |
|---|---|---|
| WP-ALPHA-CORRECTNESS-01 | independent normalized-bar Feature/T+1 Target reproduction, exact temporal/lineage comparison, five frozen placebo kinds, four entry proxies, three-factor redundancy diagnostics and Research Validation moving-block inference are implemented; the Research Panel now separates universal integrity from incumbent factor availability | focused synthetic/unit evidence only; current real physical package remains unavailable, so `PHYSICAL_REPRODUCTION_NOT_ESTABLISHED`; `ALPHA_PROVEN=false` |
| WP-ALPHA-RESEARCH-02 | `FrozenExternalValidationExperiment` is owned by the existing `ResearchExperimentDefinition`, changes exactly one of Temporal/Universe/Provider, freezes thresholds and emits the requested evaluation diagnostics | `NOT_RUN`; `EMPIRICALLY_EXECUTED=false`; `EXTERNALLY_VALIDATED=false` |
| WP-ALPHA-CONTEXT-01 | typed session-level versus cross-sectional evaluation, interaction/incremental-information boundary and five research interpretation states | synthetic/unit evidence only; no Context promoted to trading authority |
| WP-CANDIDATE-POLICY-02 | content-addressed Incumbent/Challenger definitions, Universal Integrity → validated Alpha → supported Context layers, full explanation and same-dataset comparison; admission v2 rejects cross-Experiment/External/Dataset Context mixing | Challenger is dormant because no real correctness/external evidence has passed |
| WP-PREDICTION-01 | empirical median baseline plus frozen regularized model comparison; Continuous/Historical adapters share typed material/Risk/Opportunity producer semantics and owner reload, while missing DecisionTime Account facts fail closed | `ENGINEERING_CLOSED / EVIDENCE_INACTIVE`; post-Portfolio RiskDecision remains forbidden and no conditional action path is active; no calibration, Formal OOS, Strategy qualification or Production proof |

Migrations 091–092 extend the existing immutable Historical Evidence and Strategy
owners and constrain Forecast semantics without rewriting V1. Migration 093
persists the frozen Temporal window; 094 adds pre-Strategy Risk/Opportunity
owners; 095 admits the Daily Alpha snapshot; 096 binds its exact immutable
prediction and Strategy diagnostic to T+1 Outcome. Phase II Evidence V2 carries typed
`FACT`, `MODEL_ASSUMPTION`, `RESEARCH_RESULT`, `INFERENCE`, `LIMITATION` and
`INVALIDATION_CONDITION` statements while retaining positive, negative,
inconclusive and not-estimable classifications.

The Historical Phase II application service reloads exact prerequisite Evidence
and materialization/data owners from PostgreSQL and persists typed correctness, external,
Context, Candidate and conditional-prediction artifacts through that same owner.
`continuous-research historical-phase-ii` is its single idempotent operator
adapter for the four campaign stages; it adds no runner or scheduler and fixes
the correctness placebo/inference protocol instead of exposing tuning flags.
External/Context results bind the exact input set and Research Panel lineage;
External and Candidate Top-K boundaries reuse the canonical fractional tie
kernel rather than symbol identity.
Candidate admission schema v2 additionally binds each declared Context Evidence
to the same External Experiment and research-panel Dataset. Conditional Forecast
Evidence must bind one supported same-Experiment Context owner. These are
lineage constraints only and do not upgrade any empirical state.

## Dependency order and boundaries

1. `WP-ALPHA-CORRECTNESS-CLOSURE-01` first establishes a distinct
   `REACQUIRED_EQUIVALENT_SOURCE` lineage when the original physical bytes are
   unavailable, independently parses and normalizes Raw provider records, then
   checks canonical normalized bars, persisted
   features, T+1 target semantics, placebo behavior, execution-time semantics,
   factor redundancy and dependence-aware inference. Entry diagnostics are
   rebuilt from bar order (first post-cutoff close, strict-next bar open and
   decision-session last close), not admitted by price existence alone.
2. `TEMPORAL_VALIDATION_V1` is frozen before correctness results using the
   canonical Calendar owner: start `2025-07-15`, exactly 126 Decision sessions,
   plus the last T+1 Target session. Outcome access and execution remain gated
   by a correctness-supported hypothesis.
3. `WP-ALPHA-CONTEXT-01` distinguishes session-level conditioning from genuine
   cross-sectional interactions.
4. `WP-CANDIDATE-POLICY-02` keeps Incumbent and Challenger identities separate
   and splits integrity, Alpha ranking and Context conditioning.
5. `WP-PREDICTION-01` freezes Candidate, Signal, Forecast, Context, Risk,
   DecisionTime and model/version lineage in Strategy semantics; canonical
   producer/reload wiring is complete, while consumption remains fail-closed
   until correctness, external, calibration and economic Evidence exists.

The implementation reuses Historical Research, Research Panel, Target/Outcome,
Research Validation statistics, existing Experiment Definition, existing
Forecast primitives, PostgreSQL Historical Evidence and Model/Strategy
Governance. It must not add another runner, scheduler, Feature/Candidate/Outcome
engine, Evidence authority or qualification framework.

## Frozen research and evidence rules

- Top-level Correctness states are `CORRECTNESS_SUPPORTED`,
  `CORRECTNESS_FAILED` or `INCONCLUSIVE`; internal physical/reproduction
  classifications remain diagnostic only. Correctness is never `ALPHA_PROVEN`.
- Original physical packages are unavailable at this baseline. Reacquisition
  must use a new `REACQUIRED_EQUIVALENT_SOURCE` owner and can never claim
  `ORIGINAL_PHYSICAL_REOPENED`.
- Placebo kind, algorithm, seed and protocol are content-addressed before
  evaluation. Supported kinds are symbol permutation, target permutation,
  target time shift, factor lag and deterministic random ranking.
- The closure campaign reuses the Discovery Experiment seed `20260813` for
  every per-Factor placebo protocol. Robust inference is frozen at 2,000
  moving-block draws, block lengths `(1, 5, 10)`, confidence `0.95` and seed
  `20260813`. These values were frozen before the reacquired campaign result
  and may not be changed after inspection.
- External validation changes exactly one of time, Universe or Provider. Target,
  DecisionTime, factor definitions/directions, Candidate score, Top-K, costs and
  evaluation protocol remain frozen. An economic observation is admissible only
  after the exact Panel-linked Outcome and its hash-valid Strategy Economics
  result are reloaded and semantically matched.
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

The current engineering-closure program runs focused tests only. The real
126-session correctness, Temporal External Validation, Context and Candidate
campaigns are explicitly `NOT_RUN`; any later execution remains gated by the
frozen dependency order. No engineering completion creates Formal OOS,
prospective proof, Strategy qualification or Production qualification.

Until separately recorded otherwise:

```text
EMPIRICALLY_EXECUTED=false
EXTERNALLY_VALIDATED=false
FORMAL_OOS=false
PROSPECTIVE_PROVEN=false
STRATEGY_QUALIFIED=false
PRODUCTION_QUALIFIED=false
```

The completed PR #74 implementation plan is retained in Git history and is
`HISTORICAL / SUPERSEDED`; this current protocol and the status/Roadmap documents
are the only live planning surfaces.
