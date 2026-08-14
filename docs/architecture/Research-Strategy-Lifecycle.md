# Research and Strategy Lifecycle

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Canonical research/strategy responsibility split
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-14
> **Code Evidence:** `src/market_regime_alpha/application/research_evaluation`, `src/market_regime_alpha/application/research_validation`, `src/market_regime_alpha/application/shadow_research`, `src/market_regime_alpha/application/strategy_shadow`

## Lifecycle

```text
Research Universe Policy / immutable Runtime Scope
-> Canonical Dataset / Feature / State / Candidate / Signal / Forecast
-> ResearchDailySummary
-> shared MultiStrategyRuntime
   -> Overnight action/proposal
   -> Swing Entry/Hold/Add/Reduce/Exit action/proposal
-> simple cross-strategy Portfolio/Risk baseline
-> Strategy Shadow simulated lifecycle or observed manual Fill
   -> immutable Strategy Fill Allocation
   -> owner-resolved Strategy Sleeve State on the next session
   -> fill-derived realized Strategy Outcome after full Exit
-> Research Shadow decision
-> factual multi-target Outcome
-> Evaluation Dataset and complete Panel V2
-> canonical Factor Extraction
-> exploratory Ablation and capacity analysis
-> calibration fit/evaluation (not calibrated)
-> locked-partition metric computation (not Formal OOS Authority)
-> Entry research
-> Portfolio Shadow Cash/NAV/Exposure/Cost/Attribution
-> Holding/Exit engineering assessment
-> blocked Production Admission projection
```

The same owner stages can be applied across a frozen multi-session range by the
Shared Decision Session Kernel. `HistoricalResearchRunner` journals each
session/stage in PostgreSQL, resumes under lease/fence, and replays exact owner
hashes. It is exploratory Historical Research, not a second daily Runtime and
not Formal OOS.

Candidate eligibility/ranking is upstream evidence, not an Entry decision. Each
Strategy Run records every input symbol's terminal eligibility and policy reason
before it may emit a proposal. This makes an empty or starved sample observable.
The current deterministic Path Outcome kernel supports short and multi-session
MFE/MAE, target-before-stop, time-to-MFE, continuation/failure, post-exit
opportunity loss and avoided drawdown. Automatic longitudinal outcome production
and scheduled feedback are still pending empirical work.

Observed manual Fill remains the sole source of physical Position. An immutable
Fill Allocation may attribute that quantity to Strategy Version sleeves; it
cannot allocate more than the physical Fill or sell a sleeve below zero. The
cross-strategy Portfolio remains a proposal/risk decision and never manufactures
an Order or Fill. On each account-bound Continuous tick, the existing Strategy
Shadow PostgreSQL owner reconstructs open sleeve quantity, average cost,
current/peak price, sessions held, add/reduce counts, exact Strategy Version and
Proposal/Fill lineage. Same-session marks update price but do not age a sleeve.
The frozen cycle input is the replay boundary; callers cannot supply those
values through the production composition.

For free-data operation, retrospective decisions and later outcomes additionally
feed an immutable Historical Sample Dataset in PostgreSQL. The Registry Reader
may supply those already-available `UNQUALIFIED` samples to a later
Research/Shadow PathForecast. This is operational sample plumbing, not PIT/OOS
qualification or empirical validation.

## Responsibility split

- Factor Extraction reads verified canonical Dataset, FeatureBundle, State, Pool, Candidate, Signal and Forecast values. It records missingness; it does not recompute those owners.
- Runtime Scope owns the session symbol decision. It combines overlapping free
  Operational Universe facts conservatively, preserves every Provider artifact
  reference and retains `EXCLUDED`/`UNKNOWN`; downstream owners receive the
  resulting scope rather than selecting a Provider.
- Evaluation Dataset binds frozen decisions to later settlements. Panel V2 provides the complete row/slice cross-section used by factor and evaluation consumers. They are complementary, not V1/V2 competing Authorities.
- Ablation compares factor variants and incremental lift under exploratory evidence. Formal Evaluation applies frozen windows, purge/embargo, multiple-testing and sensitivity rules. Neither grants model qualification.
- Calibration fits and evaluates Platt/isotonic/binning mappings on disjoint
  partitions. The qualification owner now exists, but it remains
  `calibrated=false` until exact Formal OOS and calibration evidence satisfy its
  independently frozen policy; current evidence does not.
- Entry research evaluates Candidate-only, Candidate+Signal, Candidate+Forecast and Candidate+Intraday variants. Its strongest output is `SHADOW_ENTER`; Canonical Entry still has no `ENTER` state.
- Research Shadow freezes what the research system knew and later binds factual outcomes. It has no simulated account or execution ledger.
- Strategy Shadow owns the isolated simulated Entry/Fill/Position/Holding/Exit
  session and the observed-Fill Strategy sleeve projection. When a canonical
  Multi-Strategy cycle exists, the free-data Shadow Entry is downstream of the
  exact Overnight `StrategyProposal`; a non-Entry gate yields `NO_ACTION`
  instead of a second Candidate-to-Entry decision. Candidate pass-through is
  retained only for historical rows/ticks with no Multi-Strategy cycle. Later
  invocations reload simulated Entry/Fill/Position artifacts and append
  Holding/Exit observations until settlement. Simulated artifacts keep
  `real_trading_mutation=false`; physical Position still comes only from the
  manual Fill owner.
- A fully closed observed-Fill allocation chain persists one immutable realized
  Strategy Outcome with exact account/version, entry/exit Proposal, pre-exit
  state, allocation and Fill lineage. It reconciles gross, costs and net cash
  flows for ENTER/ADD/REDUCE/EXIT. It is not a market Path Outcome and grants no
  Alpha, PIT, OOS, economic-support or Production status.
- Portfolio Shadow owns an independent simulated Cash/Order Intent/Fill/Position/NAV ledger under the same Strategy Shadow boundary. Top1/3/5 Equal/Score/Risk policies and all cost/capacity inputs carry explicit provenance; T+1, 100-share lots, suspension, price limits and continuous-auction constraints fail closed. It cannot write actual account or Position authorities.
- Performance/Attribution reloads the immutable Portfolio Shadow chain and emits
  content-addressed metric, monthly/yearly return and attribution rows. Missing
  denominators or dimensions remain `NOT_ESTIMABLE`; reconciliation failure is
  rejected rather than hidden in a residual.
- Migration 067 binds new Strategy and Portfolio rows to the exact Experiment,
  session, Policy, Target, Outcome, Observation Receipt and source owners. Every
  binding verifies artifact ID and content hash, and every derived timestamp is
  at or after its required inputs. Pre-067 policy-only rows stay readable as
  legacy-unbound data and cannot enter typed Historical or qualification paths.
- Exploratory Model Research freezes samples, features, targets, walk-forward
  folds, coefficients and lineage. Its executor emits raw barrier scores, not
  probabilities. A real stored research artifact makes
  `RESEARCH_MODEL_AVAILABLE=true`; Formal qualification, OOS and calibration
  remain false.
- Holding/Exit validation consumes Strategy Shadow outcomes only. It cannot mutate actual `position_books` or `manual_fills`.
- Production Admission lists missing floors. It is not an Authority and cannot reach review eligibility or authorization.

## Qualification state

The repository contains operational writers for `UNQUALIFIED` free-data
Historical Samples, exploratory model artifacts and narrow owner-specific
Formal assessment decisions. The Formal orchestration checks Provider Fact
qualification, Formal PIT, Historical Sample, Locked OOS and Calibration in
order and stops at the first missing or rejected predecessor. With current free
data it persists `BLOCKED`; it cannot invoke OOS consumption or calibration fit.
Migration 046 still prevents reference-only promotion.

## Phase D Alpha proof foundation decision

> **Decision state:** IMPLEMENTED engineering boundary; empirical evidence pending

Phase D converges the existing research owners around one semantic spine rather
than adding another governance plane:

```text
Frozen Experiment Definition
-> Canonical Target/Horizon
-> deterministic measure-oriented Forecast computation
-> Outcome settlement
-> metric-specific Evaluation and Calibration
-> target-bound Strategy/Portfolio research
-> diagnostic Attribution
-> frozen follow-up Experiment
```

The following decisions are normative for the implementation:

- Confidence intervals describe sampling uncertainty. Hypothesis tests use a
  separately frozen null, benchmark, alternative and inference method. Effect
  size and economic significance remain separate results. Metrics without a
  defensible frozen null do not manufacture a p-value.
- `FormalResearchProtocol` remains the experiment Authority. Its immutable,
  content-addressed Experiment Definition freezes the research question,
  hypothesis, decision time, target, feature and model search space, budget,
  metrics, multiplicity family, stopping rule, train/validation and
  purge/embargo policies, OOS policy, randomness and cost assumptions before
  execution. A mutation creates a different Protocol identity and cannot reuse
  consumed Locked OOS evidence.
- `TargetDefinition` is the canonical semantic identity shared by Forecast,
  Outcome, Evaluation and Calibration. Strategy policies bind that identity but
  retain independent Holding and Exit responsibilities. A bar that touches both
  barriers without adequate path resolution is `AMBIGUOUS`/`NOT_OBSERVABLE`;
  the system never invents an intrabar path.
- Forecast estimators are deterministic mathematical kernels independent of PIT
  qualification. Exploratory Research may execute them over explicitly
  unqualified data. Only the existing owner-resolving Formal gate may persist a
  Formal Forecast, and only from qualified PIT inputs.
- Forecast output is measure-oriented. Expected return, downside, direction,
  barriers, MFE and MAE each report `AVAILABLE` or `NOT_ESTIMABLE`. An
  uncalibrated classifier emits a raw score or logit, never a probability.
- Free public data remains `EXPLORATORY`/`PIT_INCOMPLETE`/`UNQUALIFIED` unless
  its real Provider evidence satisfies the existing contract. Phase D neither
  weakens the floor nor makes a paid Provider a dependency.

The approved public seams are:

```text
FormalResearchProtocol.create(..., experiment_definition=...)
FormalEvaluationProtocol.create(..., hypothesis_specs=...)
TargetDefinition.create(..., canonical_horizon=...)
FormalForecastExecutor.compute(resolved_owner_context)
ResearchDecisionSessionKernel.run_next(...)
HistoricalResearchRunner.run/resume/replay(...)
run_shadow_portfolio_day(..., target_identity, policy_v2)
FreeDataSettlementOperator.settle_day(...)
```

Earlier Phase D work is an implementation inventory, not a merge unit. Each
capability is classified against the current `main` schema and this decision as
`REUSE`, `PORT`, `REWRITE` or `DROP`. New migrations start after the current
migration head and express only the accepted current semantics; historical
migrations are not mechanically cherry-picked.

The implementation order is dependency-bound: Statistics, Protocol/Target,
Formal Forecast, Alpha/Ablation, Strategy Economics, Portfolio Risk,
Attribution/Feedback, architecture simplification and full verification.

The implemented boundary now includes deterministic synthetic null/power
proofs, explicit hypothesis-specific inference, Protocol V2 and Target
Definition V2, measure-oriented benchmark/linear/raw-logit/regime Forecast
kernels, PostgreSQL research-model and multi-year Historical journals, Full-A
Runtime Scope, owner-derived Strategy/Portfolio observations, multi-period
performance, factor coverage and cumulative ablation, target-bound Strategy
Economics, constrained Portfolio Risk, and non-causal Attribution/Feedback.
These are executable research capabilities, not positive Alpha evidence.

Only the bounded Strategy/Portfolio observation and simulated ledger operators
have a natural CLI/runtime consumer. Strategy Economics, Portfolio Risk,
Ablation and Attribution/Feedback remain exploratory kernels consumed by the
Historical research composition; they are not installed as new Canonical
Runtime stages and do not create a second Authority or qualification plane.

Canonical free-data composition now calls `SourceFreezeService`; the retained
DailyLoop owns historical Daily identities only behind that adapter. Controlled
package recovery uses the PostgreSQL longitudinal record's explicit
`artifact-root-v1` locator and verifies immutable content hash. No recovery path
discovers package or Feature identities by filesystem scan. Canonical Lifecycle
keeps its journal-compatible stage identities but publishes three actual
boundaries: Research Decision Support, Manual Account Observation, and
contract-only Position Review. The last boundary remains fail-closed.

## Non-claims

- no Alpha winner;
- no parameter optimization in this lifecycle;
- no formal OOS result;
- no calibrated probability;
- no Entry authorization;
- no actual Fill or physical Position from simulated Strategy Shadow artifacts;
- no authenticated operator or broker readiness proof; engineering RBAC is not authentication or Production Admission.
