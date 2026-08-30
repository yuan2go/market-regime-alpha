# Research and Decision Lifecycle

> **Status:** CANONICAL_TARGET_ARCHITECTURE
> **Authority:** Target research, context, decision, outcome, and qualification lifecycle
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-30
> **Code Evidence:** target `src/market_regime_alpha/selection`, `src/market_regime_alpha/research_qualification`, target draft schema and `tests/refoundation`; existing `src/market_regime_alpha/research`, `src/market_regime_alpha/features`, and `src/market_regime_alpha/candidates` are Legacy invariant sources only, not target Authority

Research is a consumer of Market/PIT facts and a producer of scoped evidence. It
cannot alter historical inputs, promote its own model, or create a Position.

## 1. Capability chain and semantic separations

```text
Market Fact
→ Universe Revision
→ Eligibility Assessment
→ Decision-input Dataset
→ Candidate Set
→ OPEN_DECISION_RUN / Decision Target Commitment
→ Market / ETF / Theme / Capital Context
→ Signal
→ Target-bound Forecast
→ Opportunity
→ Thesis / Strategy action
→ Portfolio Proposal
→ Risk Decision
→ Execution Intent
→ observed Fill
→ observed Fill-derived Position
→ TradeOutcome / Trade Attribution

Decision Target Commitment → Market Target Outcome
Market Target Outcome + Research Partition → Evaluation
→ Evidence → Research Assessment → Research Qualification Decision
```

The following are non-equivalences:

- Market Fact ≠ inferred Regime/Theme/Capital state.
- Universe membership ≠ Eligibility.
- Eligibility ≠ Candidate.
- Candidate ≠ Signal.
- Decision Target Commitment ≠ Outcome or Forecast.
- Signal ≠ Forecast.
- Forecast ≠ calibrated probability.
- Opportunity/Thesis ≠ Portfolio allocation.
- Proposal/Risk acceptance ≠ Intent.
- Intent ≠ Fill.
- Fill ≠ target quantity.
- Market Target Outcome ≠ Fill-derived TradeOutcome.
- Outcome ≠ Evaluation or Attribution.
- Assessment ≠ Qualification.
- Target horizon ≠ holding/exit time.
- `NO_ACTION` ≠ `HOLD`.

## 2. Market and Context model

Market/PIT owns raw facts. Decision Support owns inferred Context assessments:

| Context kind | Meaning | Required evidence boundary | Prohibited claim |
|---|---|---|---|
| `MARKET_REGIME` | inferred broad market condition for one Decision scope | exact Market bars/breadth/liquidity and model version visible at Decision time | raw exchange fact or future regime label |
| `ETF_ROTATION` | relative ETF segment/asset state | ETF instruments/classification membership, raw prices and methodology | proof of tradable rotation Alpha |
| `THEME_ROTATION` | state of declared theme classifications | PIT theme membership plus instrument facts and methodology | retrospective current-membership reconstruction |
| `CAPITAL_PROXY` | explicitly named flow/participation proxy | exact public facts, calculation and limits | hidden institutional intent or direct capital-flow fact |

Each assessment is immutable, has status and Evidence, and stores its component
metrics relationally. A “current state” is a view over assessments. There are no
table-per-state observations/transitions/current pointers. State transition is a
query comparing consecutive assessments unless a real business command consumes
a transition fact.

A Context kind survives only while it has a distinct consumer contract or
research question. Unsupported Context is valid `UNKNOWN` evidence; it is not
filled with defaults.

## 3. Selection lifecycle

1. `FreezeUniverse` resolves one immutable Universe revision from an explicit,
   immutable, content-identified scope specification and Decision-visible
   Market classification evidence. It never defaults to all current instruments.
2. Every scoped instrument receives `INCLUDED`, `EXCLUDED`, or `UNKNOWN`
   membership status; no symbol silently disappears.
3. Universe membership answers research-scope inclusion only. Suspension,
   special treatment, listing age, liquidity, and limit metadata are Eligibility
   facts and cannot exclude Universe members.
4. `AssessEligibility` applies every rule to every scoped member without short
   circuiting and persists each typed criterion result and exact Market lineage.
5. A criterion is `FAIL` only on explicit evidence; missing, stale, conflicting,
   or Decision-invisible evidence is `UNKNOWN`. The aggregate is `INELIGIBLE`
   when any rule fails, otherwise `UNKNOWN` when any rule is unknown, otherwise
   `ELIGIBLE`.
6. Listing-age units and liquidity measure/window/unit/operator/threshold are
   immutable policy data; there are no inherited defaults.
7. Candidate is permanently Selection-owned and consumes the real
   Research-owned Dataset and FeatureDefinition inputs. Policy components bind
   only numeric Feature Definitions; Candidate Set binds one immutable
   Decision-input Dataset, whose rows are the sole population.
8. Every Dataset row becomes `SELECTED`, `RANKED_NOT_SELECTED`, or
   `UNRANKABLE`. Any required non-`AVAILABLE` cell is strict complete-case
   `UNRANKABLE`; no imputation, gate rerun, or row deletion is permitted.
9. Rankable components use identity-neutral arithmetic midrank, exact-rational
   fixed-weight composite, competition rank, and Top-K with all boundary ties.
   Constant complete cross-sections use `0.5`; missing statuses never do.
10. Empty/no-rankable/constant/available sets are successful, queryable results
    with complete funnel and component diagnostics.
11. Candidate V1 reads no Decision Run, Context, Target, Outcome, Model/Model
    Version, Evidence, Assessment, or Qualification and expresses no probability,
    expected return, MFE/MAE, Forecast, Signal, or Entry authority.
12. `OPEN_DECISION_RUN` follows Candidate and precedes Context. It freezes a
    complete ordered requested Target roster even for an empty Candidate Set,
    then the Candidate × Target commitment/reference cross-product; it does not
    feed Target or Outcome back into Candidate.
13. Outcome, Partition, Experiment, Evaluation, Evidence, Assessment, optional
    Model, and Qualification follow only the dependency-coherent Roadmap.
    Research must not create a realized-label Authority that competes with
    Outcome facts.

Eligibility protects tradability and evidence sufficiency. Candidate selection
answers a research/decision ranking question. Neither can imply Entry.

## 4. Signal, Forecast, Opportunity, and Thesis

A Signal is a versioned assertion such as setup present/absent/unknown. It binds
one Candidate and Decision Run and preserves missingness. Signal values are not
probabilities.

A Forecast binds exactly:

- Decision Target Commitment and therefore Candidate, Decision Run and Target;
- Target checkpoint/metric;
- estimate, uncertainty interval/distribution semantics;
- calibration status and purpose-specific Qualification Decision if any;
- known/available times and Evidence.

A rule/heuristic Forecast has no Model placeholder. A model-backed Forecast has
one concrete `forecast_model_binding` to a Model Version that was produced by a
completed `MODEL_TRAINING` Evaluation and was selected for this later Decision
generation. Candidate, Target, Outcome, ordinary Evaluation, Evidence,
Assessment, and Qualification do not require a Model.

Raw scores remain raw. Probability fields are legal only when calibration method,
partition, metric, and qualification floor are satisfied for that exact purpose.

An Opportunity is the Strategy input bundle. It binds Candidate, Signal,
Forecast requirement/result, all required Context assessments, exact
Decision-time input Evidence, Decision time, and Strategy Version. It contains
no Risk Decision, risk authorization, accepted quantity, or account-limit
result. If the Strategy declares
Forecast required, absent or wrong-target Forecast is fail-closed. If Forecast is
not required, that fact is explicit in Strategy Version; it is not a legacy
fallback.

Universe, Eligibility, Dataset, Candidate, Decision Run, Target commitment, and
Decision reference are frozen before same-run Context.
`AssessContext` may read Market/PIT and the exact frozen Candidate scope, but its
result cannot alter that Universe revision, Eligibility result, Candidate Set,
or commitment roster. This one-way dependency prevents a Candidate/Context
cycle. Instrument
tradability belongs to Eligibility; account/Portfolio authorization belongs to
the sole post-Portfolio Risk Decision.

A Thesis is a falsifiable rationale over one Opportunity. Typed conditions state
entry, hold, invalidation, reduce, or exit observation requirements. A later
condition observation may lead a Strategy to a new action, but it does not edit
the original Thesis or Position. Exit is not inverse Entry.

## 5. Strategy, Portfolio, Risk, and Execution boundary

Strategy Version is immutable action policy. For each Opportunity it emits a
closed result such as `ENTER`, `ADD`, `HOLD`, `REDUCE`, `EXIT`,
`NO_ACTION`, `WAIT`, or `DATA_INSUFFICIENT` with reasons. Unsupported actions
do not collapse into empty output.

Portfolio combines Opportunities under one policy and emits a complete Proposal
and lines. It does not read future Outcome or write account state.

Evidence previously labelled “pre-strategy risk” is split into Market/PIT
facts, Eligibility reasons, Context metrics, or ordinary Evidence. No
pre-Strategy allow/deny result survives as a Risk Decision.

Risk reloads Proposal, exact account Authority epoch, current Fill-derived
Position, active Intent reservations, Decision-visible trading restrictions and
Risk Policy. It emits accepted/rejected/unknown authorization with every rule
result. Rejection cannot be bypassed by Strategy code, operator convenience, or
a new idempotency key.

Execution remains human-in-the-loop. Intent records authorized scope; observed
Fill is the only trade fact. Position and sleeve rules are frozen in the
[Authority Map](Authority-Map.md).

## 6. Target commitment and Market Target Outcome lifecycle

Target Definition is registered before a qualifying experiment or Decision. It
separates:

1. Decision reference;
2. outcome path/window;
3. checkpoint observations;
4. each derived metric and its exact observation-dependency shape.

Target Definition is provider-neutral: it freezes the business observation
rule, not a data vendor. The ordered Decision Run Target roster explicitly
selects the reference Provider Product for that Run, and the resulting exact
Market revision or Source Gap freezes actual Provider/Capture provenance.
Target registration closes its own relational checkpoint/metric/dependency
graph; a command receipt is idempotency/audit evidence, not closure Authority.

Before Context, `OpenDecisionRun` creates the sole canonical Decision Run for
the Candidate Set and freezes the ordered requested Target roster,
including when the Candidate population is empty, and binds every Candidate row
to every requested Target Definition. One independent Decision reference
observation stores the exact Decision-visible Market revision or Source Gap.
This full roster is the
non-repudiable ex-ante commitment; missing references remain explicit and no
future Outcome value is created.

Market Target Outcome settlement occurs after sources become due. One stable
root binds exactly one commitment; each attempt appends a full revision with
independent path, checkpoint, return, MFE, MAE, barrier, availability, finality,
and failure states. Exact retries reuse a request hash. Partial completion,
Provider correction, repaired coverage, or finality change appends typed direct
supersession; old revisions remain immutable.

Settlement separately records the latest admissible event time
(`observation_cutoff`) and source-known time (`knowledge_cutoff`). Neither is the
original DecisionTime. Replay reloads the exact Target, commitment/reference,
calendar, Market/PIT revisions/gaps, cutoffs, algorithm and code/config; it
cannot query a replacement Provider or current/latest facts. Complete source
path never manufactures an unavailable reference or metric.

The exact T+1 10:30 and 14:55 Raw reference semantics are specified in
[PostgreSQL, Temporal and Evidence Architecture](Data-and-Evidence-Architecture.md).
They incorporate the valid semantics originally established by historical
[ADR-014](decisions/ADR-014-Frozen-Target-Semantics-and-Independent-Correctness.md)
without retaining its compatibility implementation policy.
Market supplies generic exact/as-of facts; Research owns the Target Definition,
Decision Support applies and commits its initial-reference rule, and Outcome
applies its future path/checkpoint/metric settlement rules.
Research consumers receive realized facts only through the read-only Outcome
port and cannot import bars, Providers, or Outcome repositories.

## 7. Attribution

Market Attribution is run only against a frozen Market Target Outcome revision.
Trade Attribution is run only against a separate TradeOutcome whose subject is
an account/instrument episode with concrete opening/closing effective Fill roots
and a complete Fill roster that replays the Position from zero back to zero.
Fill Allocations enter only sleeve-specific Trade Attribution. Market Outcome
never becomes realized PnL, and TradeOutcome never becomes a Candidate Target
label. Cross-comparison is diagnostic only.

The applicable policy declares dimensions before calculation: Market, Context,
Candidate/Signal/Forecast, Strategy action, Portfolio selection/sizing,
execution costs, and residual policy.

Every line has status and evidence. Contributions must reconcile to the declared
total within numeric tolerance. If a denominator/dimension is missing or
reconciliation fails, affected lines or the Run are `NOT_ESTIMABLE`/
`REJECTED`; no unexplained residual is silently balanced. Attribution is
diagnosis, not causal proof and not an Outcome/Position writer.

## 8. Research objects

### Dataset

A Candidate-consumable Dataset is an immutable, content-addressed
`DECISION_INPUT` object. Its population is exactly the same-DecisionTime
intersection of `UniverseMember = INCLUDED` and
`EligibilityAssessment = ELIGIBLE`; no other instrument may appear and no member
of that intersection may disappear because a Feature is missing. Every bound
Feature has an explicit typed cell status.

It binds the exact Universe revision, Eligibility policy/assessments, Feature
Definitions, Market/PIT and Selection lineage, code/config identities, and
verified Artifact bytes. A closed Domain parser rejects all unrecognized fields
and in particular Target, Outcome, return, MFE/MAE, barrier, future observation,
realized label, and other posterior data. A future Evaluation/Target Dataset is
a different semantic owner and is not a mode or optional section of the
Decision-input manifest. PostgreSQL `dataset_source` uses closed roles and real
FKs; it is validated bidirectionally against the Artifact manifest.

### Feature Definition

A Feature Definition records calculation semantics only: semantic identity,
typed value/unit, frequency/window/lookback, source requirements, availability
rule, missingness policy, and deterministic algorithm/code/config identity. It
cannot store Alpha support, research maturity, external validation, assessment,
or qualification. Candidate V1 has no proven Feature-to-Feature dependency, so
this checkpoint creates no dependency abstraction.

### Experiment

An Experiment is registered before result access and freezes:

- hypothesis and one primary research change;
- one Target and the label-free Dataset/Candidate lineage implied by its
  Partition members;
- Features/Model/Strategy variants;
- partitions and their purposes;
- metrics, population, costs, multiple-testing and sensitivity rules;
- evidence ceiling and success/rejection/not-estimable criteria.

One primary change prevents causal ambiguity. A new change creates a new
Experiment; it does not mutate the old definition.

### Partitions

Purposes are distinct:

- `DISCOVERY`: exploratory selection and rejection;
- `VALIDATION`: correctness/robustness without promotion;
- `LOCKED_OOS`: pre-frozen independent evaluation;
- `FIT`: training or calibration fit;
- `PROSPECTIVE`: decisions committed before outcomes.

A Target-specific Partition root and its complete non-empty Decision Target
Commitment member roster are frozen atomically before any Outcome read.
Decision/Outcome-window bounds, purge, embargo, calendar, membership and Target
overlap rules are stored and reconciled. Every exact Outcome revision exposed
to an Evaluation appends a per-member ordinal access row; ordinal one is
first-access Authority. A Locked
OOS/Prospective Experiment binding must be committed while access count is zero
and before every ordinal-one row. Reusing an accessed Partition is diagnostic
only; no mutable “unlocked” flag or Artifact manifest can restore proof status.

For `PROSPECTIVE`, every member must additionally come from a live-clock Run
whose PostgreSQL commitment time predates the Target's first Outcome-window
event. A historical/replay Run can satisfy relational ordering but cannot be
relabeled Prospective.

### Evaluation and Assessment

An Evaluation Protocol freezes metrics, slices, missingness, costs and decision
rule before Outcome access. Every Evaluation Run requires an Experiment Run,
one frozen Partition, and that protocol; it does not require a Model.
Evaluation observations bind exact Partition access rows and exact Outcome
revisions returned by the read-only port. Evaluation produces typed metrics
with estimability; every metric/slice has a reconciled relational
included/excluded/not-estimable observation roster. Evaluation never writes
posterior labels into a Decision-input Dataset.
Every Partition member must have an Evaluation observation, including factual
`UNAVAILABLE`/`FAILED` revisions; `NOT_DUE`, missing settlement, or ambiguity
blocks terminalization instead of shrinking the sample.
The only Run transitions are `OPEN → INPUTS_ACQUIRED → COMPLETED`, or terminal
`FAILED` from either prior state. `NOT_ESTIMABLE` is a completed metric state,
not a missing observation or Run failure.

Research Assessment applies the predeclared decision rule and returns
`SUPPORTED`, `REJECTED`, `NOT_ESTIMABLE`, `INCONCLUSIVE`, `BLOCKED`, or
`FAILED`. Negative and inconclusive evidence is retained and queryable.

Research Assessment requires one Experiment, a complete non-empty roster of
that Experiment's terminal Evaluation Runs, and a complete concrete Evidence
Item set. Each Evidence Item requires one Evaluation Run in that roster and an
immutable Artifact FK; Research Qualification requires the Assessment, Policy,
every Policy floor result, and concrete floor-to-Evidence links. No generic
`(kind, id)`, JSON business owner, weak reference, or future nullable subject is
permitted. Assessment does not update Model/Strategy Version. A proposed
improvement gets a new immutable version and a new qualification request.

## 9. Evidence and proof boundary

The formal flow is:

```text
Engineering correctness
→ Source and temporal/PIT qualification
→ frozen Dataset and Experiment
→ Discovery (optional, exploratory)
→ separately frozen Formal OOS
→ calibration/economics where required
→ Prospective observation
→ purpose-specific Production admission
```

This is a dependency graph, not an automatic ladder. Evidence Class, origin,
Assessment Status, proof class, required floors, and floor statuses are specified
in [PostgreSQL, Temporal and Evidence Architecture](Data-and-Evidence-Architecture.md).

Examples:

- Passing unit/PostgreSQL tests can satisfy an Engineering floor only.
- A recorded free Provider capture remains Exploratory when archive/finality/
  availability is not qualified.
- Correct historical as-of reconstruction may satisfy PIT but not Formal OOS.
- A locked metric run can be `NOT_ESTIMABLE` and still be valid evidence.
- Prospective observations do not repair historical PIT or OOS gaps.
- Good returns do not establish calibration, execution integrity, or Production
  admission.
- `REJECTED` is a legitimate terminal research result.

## 10. Prospective lifecycle

A Prospective prediction is admissible only when:

1. the Decision Run and every input/evidence hash commit before its Decision
   deadline;
2. Runtime/database clocks and session are owner-resolved;
3. no later revision or outcome is visible to the command;
4. the Candidate/Signal/Forecast/Portfolio/Risk dossier is immutable;
5. the eventual Market Target Outcome references the precommitted Candidate and
   Target exactly;
6. missed deadlines, missing evidence, and no-action days remain in the sample;
7. restarts reuse idempotent receipts and do not rebuild from newer input.

A prospective attestation document is not needed as a separate Authority table.
The Run/Decision/Evidence/Outcome timestamps and dependencies prove or reject the
condition. A generated prospective report is a non-authoritative read model.

## 11. Model and Strategy qualification

Models and Strategies have stable family identity and immutable versions. A
Model Version is optional and can be registered only from a completed
`MODEL_TRAINING` Evaluation Run plus a fitted Artifact. Qualification is
purpose-scoped:

- a Model Version may be eligible for Exploratory Forecast but blocked for
  calibrated probability;
- a Strategy Version may be eligible for Shadow research but blocked for
  execution support;
- Production admission requires all policy floors and does not follow from
  “qualified” in another purpose.

Research Qualification uses its concrete Research Assessment subject. Future
Model and Strategy admission must define separate subject-specific relations;
they cannot turn Research Qualification into a generic subject registry.
Selection of a version is a query over current, non-superseded subject-specific
decisions plus a frozen selection policy. There is no mutable “Champion
pointer.” A later Run binds adopted Research Qualifications through its
concrete qualification roster/members; Model and Strategy versions use their
own concrete Forecast/Opportunity bindings after those parents exist. Replay
therefore never asks what is current now.

## 12. Research feedback

Outcome/Attribution may propose a hypothesis, challenger, degradation review, or
retirement assessment. Feedback cannot:

- mutate existing Feature/Target/Model/Strategy definitions;
- train on locked/prospective outcomes outside a new declared Dataset;
- auto-promote a version;
- erase negative evidence;
- lower Risk;
- write Execution or Position.

Every feedback experiment restarts the freeze/evaluate/qualify path with a new
identity. The only feedback edge is cross-generation:

```text
Outcome(n) → Evaluation(n) → Qualification(n) → DecisionRun(n+1)
```

No same-generation Evaluation, Assessment, Qualification, or Model edge may
return to Candidate, Target commitment, Context, Signal, Forecast, or Decision.
The Qualification-to-later-Run edge requires the concrete Run qualification
roster/member FKs and earlier-generation/time checks.

## 13. Capability preservation acceptance

Implementation cannot delete an old module/table/test path until:

1. its business capability appears in the
   [Capability Preservation Matrix](../references/WP-ARCHITECTURE-REFOUNDATION-01-Capability-Preservation-Matrix.md);
2. every valuable correctness rule appears in the
   [Domain Invariant Catalog](../references/WP-ARCHITECTURE-REFOUNDATION-01-Domain-Invariant-Catalog.md);
3. its current table is classified in the
   [283-table Disposition](../references/WP-ARCHITECTURE-REFOUNDATION-01-Table-Disposition.md);
4. target Domain and PostgreSQL tests prove the replacement;
5. architecture tests prove the old writer/reader/composition path is gone.

Code presence or a passing fixture cannot satisfy a research proof floor.
