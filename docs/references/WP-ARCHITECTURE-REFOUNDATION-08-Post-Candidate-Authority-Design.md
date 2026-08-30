# WP-ARCHITECTURE-REFOUNDATION-08 Post-Candidate Authority Design

> **Status:** CANONICAL_TARGET_ARCHITECTURE
> **Authority:** Detailed design record for the post-Candidate dependency and
> Market Target Outcome closure; canonical summaries remain in the architecture
> documents and Roadmap
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-30
> **Schema Epoch:** `MRA_REFOUNDATION_1`
> **Release/Cutover State:** `DRAFT / NOT_CUT_OVER`
> **Repository Audit Base:** `ba3655105e51873fa734234e740416ece8a6fb62`
> (`origin/main` after the execution-time fetch on 2026-08-30)
> **Code Evidence:** current source and SQL under `src/market_regime_alpha`,
> target draft under `src/market_regime_alpha/infrastructure/postgres`, legacy
> migrations 001--106, `tests`, and WP-01--WP-07 Verification records

This record closes design only. It adds no Python business implementation, DDL,
migration, seed, checksum, placeholder, Runtime dispatch, campaign, evidence
claim, or cutover. Current implementation truth remains the checked-out code,
PostgreSQL schema, tests, and reproducible artifacts.

## 1. Audit result and evidence ceiling

The target draft stops at Candidate. The target Runtime vocabulary currently
jumps from `BUILD_CANDIDATE_SET` to `ASSESS_CONTEXT`, and no target relation yet
owns Decision Run, Target commitment, Outcome, Research Partition, Experiment,
Evaluation, Model, Evidence, Assessment, or Qualification.

The Legacy implementation has multiple independent realized-fact paths:

| Current path | Real behavior | Current consumers | Target disposition |
|---|---|---|---|
| `application/controlled_operation/outcome_evidence.py` | reads settlement bars and derives a Decision reference, checkpoint return, MFE and MAE into an Artifact package | Prospective Outcome settlement and replay | merge factual semantics into Market Target Outcome; Artifact becomes bytes only |
| `application/controlled_operation/prospective_outcome.py` | extends factual observations with checkpoints, availability and barriers | Shadow settlement, Qualification and Runtime query paths | merge into one Outcome revision writer |
| `application/research_evaluation/target_semantics.py` and `targeted_outcome.py` | independently derive/validate checkpoint, return, MFE, MAE and barrier labels from bars/prices | panel, calibration, Formal OOS, model training and shadow economics | retain one numerical kernel behind Outcome Application; delete Research writer/property label path |
| `application/historical_corpus/historical_target_semantics.py` | independently derives historical reference/path/checkpoint/barrier states from normalized bars | historical materializer, correctness comparison and replay | preserve as characterization/replay evidence until the Outcome kernel covers it; no target writer |
| `application/historical_corpus/decision_materializer.py` | reads historical windows, creates labels and converts them into forecast samples, strategy results and evidence | Historical Runtime, Forecast, performance and research evidence | historical adapter registers facts/commitments and calls Outcome; consumers use Outcome port |
| `application/historical_corpus/alpha_correctness.py` and `phase_ii_service.py` | independently reconstruct the T+1 reference/return from normalized owner bars and derive execution timing proxies | correctness/failure indexing, Phase II gates and evidence | converge exact recomputation into Outcome replay; execution proxies become Evaluation diagnostics and never Fill proof |
| `application/historical_corpus/alpha_diagnostics.py` and `external_validation.py` | recalculate Target/gross returns from Target and hypothetical entry price fields | Alpha diagnostics and external-validation evidence | Evaluation consumes exact Outcome plus declared proxy; delete local Target-return truth |
| `application/research_validation/free_historical_samples.py` | calculates path return/MFE/MAE and daily-bar barrier ambiguity | historical samples, Forecast and qualification | delete calculation after archived facts are admitted through Outcome |
| `candidates/rehearsal_targets.py`, `candidates/rehearsal_opportunity_targets.py` and `research/tencent_composite_materialization.py` | calculate next-session return/MFE/MAE directly from future bars/closes | R5/PRR Candidate/Opportunity research runners and artifacts | preserve Target identities only; replace values with Outcome reads |
| `research/mr1_morning_pop.py` and `daily_decision/outcome.py` | calculate MR1 next-session 10:30, open-gap, MFE/MAE and barrier results | MR1 research and daily Outcome Artifact | preserve the MR1 Target contract; replace calculation with Outcome reads |
| `strategies/entry/materialization.py` | consumes future daily bars/suspensions and independently resolves barrier-first, timeout, missing and ambiguous path state | Entry rehearsal path observations and downstream Strategy paths | preserve Strategy entry rule only; Target barrier facts come from Outcome port/Evaluation |
| `strategies/path_outcomes.py` | calculates hypothetical strategy terminal return, path extrema and barrier order from price observations | `strategies/feedback.py`, strategy feedback and `strategy_path_outcome` | Evaluation consumes Market Target Outcome; delete separate label Authority |
| `application/strategy_shadow/contracts.py` and `strategy_shadow/economics.py` | calculate synthetic Fill/Position/exit returns and accept caller MFE/MAE | Strategy Shadow scorecards and feedback | Evaluation/Attribution consumes Outcome facts; synthetic fills never qualify for TradeOutcome |
| `evaluation/lifecycle.py` | derives realized PnL/return from effective Fills and a closed Position, plus trade-path MFE/MAE | rolling trade scorecards | preserve as the separate Fill-derived TradeOutcome branch |
| `research/mr1_candidate_baselines.py` and `research/prr_mvp_1.py` | derive exploratory trade/forward returns inside research runners | historical exploratory reports | replace with Evaluation over Outcome or delete with the Legacy runner |
| `research/pit_replication_success_v2.py` | recalculates gross portfolio returns from reference/evaluation prices | PIT replication report | replace by declared Evaluation metrics over exact Outcome observations |
| `dividend_t/memory.py` | creates forward-return labels by indexing future closes | Legacy setup-memory score | delete the future-label path; retain only independently characterized pre-Decision Feature semantics, if any |

The current all-day call chain is materially coupled:

```text
continuous-research CLI
→ ContinuousOutcomeSettlementService
→ FreeDataSettlementOperator.settle_day
→ BaoStock 5m acquisition + outcome Artifact publication
→ ResearchShadowOperations.settle
→ prospective_outcome_settlement + targeted_shadow_outcome(_label)
→ Research Evaluation panel/enrichment
→ Path calibration
```

The historical chain separately executes:

```text
HistoricalDecisionMaterializer._outcome_stage
→ historical normalized-bar windows
→ historical_target_semantics / targeted_outcome
→ historical_corpus_outcome_label
→ PathForecastSample / strategy economics / performance
→ historical_research_evidence / qualification consumers
```

Direct SQL readers of the label families include
`postgres_research_model.py`, `postgres_qualification.py`,
`postgres_calibration_qualification.py`, `path_calibration.py`,
`strategy_shadow/postgres_observations.py`, `strategy_shadow/economics.py`,
`formal_evaluation.py`, `ablation.py`, and Runtime query code.
`forecasting/path.py` and `forecasting/conditional.py` consume caller-built
realized samples; `holding_exit_validation.py`, `strategies/feedback.py`, and
historical multi-strategy/performance paths consume realized metrics. Current
Target/DTO definitions also live in `application/research_evaluation/targets.py`
and `platform/target_evaluation.py`; their useful vocabulary converges into
TargetDefinition/Checkpoint/Metric, not a writer.
None may retain a bars-to-label or caller-label path after target convergence.

The same search separated label truth from other price arithmetic. Historical
or same-Decision Feature returns remain Feature inputs. `position/assessment.py`
and `strategies/runtime.py` compute current mark-to-cost for a Fill-derived open
Position and remain Decision query inputs, not Market Target Outcome or closed
TradeOutcome. Strategy Shadow synthetic fills/results are Evaluation facts, not
observed Fills. This boundary prevents a broad arithmetic search from silently
promoting either Features or simulated execution into realized Authority.

The Legacy migration FK audit found real but family-local constraints, not the
target chain. Migration 035 binds prospective settlement to Shadow decision,
session, summary, and Runtime tick, while archive/Dataset/factual-evidence IDs
and all observations remain text/hash plus `payload_json`. Migration 039 FKs a
targeted label to its local protocol/definition, but Target semantics and label
facts remain JSON. Migrations 036/041 bind Evaluation datasets/panels to local
settlements and Shadow decisions while row-level labels remain payloads;
migration 074 projects `target_id` out of JSON without a Target FK. Migration
061 uses `artifact_kind`/`artifact_id` source bindings and payload training
targets. Later Locked-OOS and formal-evaluation tables add purpose-local
rosters, but no existing FK chain joins one Decision Target Commitment to one
revisioned Outcome and then to exact Partition access/Evaluation observations.
Those useful local constraints are migration/replay characterization evidence;
they do not justify preserving the parallel owners.

The execution-time read-only PostgreSQL probe found a reachable local
PostgreSQL 16.14 database named `market_regime_alpha`. Its
`market_regime_alpha` schema has 182 tables and migration head 55, while the
separate `wp_alpha_proof_02_20260825` historical proof schema has 283 tables
and migration head 106. No `mra` schema exists. The invoking shell had neither
`MARKET_REGIME_ALPHA_DATABASE_URL` nor
`MARKET_REGIME_ALPHA_DATABASE_SCHEMA`, and `pg_stat_activity` showed no other
session in that database, so no running Runtime/schema selection was observed.
Code defaults the configurable application schema to `market_regime_alpha`;
that default, a schema name, or the proof schema's completeness is not evidence
that a stopped Runtime currently owns either schema. The target epoch is
therefore physically absent, Legacy code/migrations remain implementation
authority, and Cutover must bind an explicitly configured database/schema and
verified schema OID rather than infer ownership from this inventory.

This audit proves engineering dependency and duplication only. It creates no
Formal PIT, Formal OOS Alpha, Provider, Prospective, trading, or Production
evidence.

## 2. Considered designs

### A. Generic subject registry

One `outcome(subject_kind, subject_id)` and generic Evidence/Qualification
references minimize relation count. PostgreSQL cannot FK a row to the declared
subject table, enforce subject-specific lifecycle, or prevent dangling IDs.
This repeats the current JSON/polymorphic Authority defect and is rejected.

### B. Consumer-owned labels

Research, Forecast, Calibration, Shadow, and Strategy could each keep a local
label table while sharing a helper function. Provider correction, availability,
finality, and replay would still yield multiple durable truths even if the
arithmetic happened to match. This is rejected.

### C. Decision-bound commitment and revisioned Outcome

`OpenDecisionRun` commits the complete Candidate × Target roster before Outcome
visibility. Outcome owns one stable subject per commitment and append-only full
snapshot revisions. Research consumers receive realized facts only through one
read-only port. Concrete FK chains protect every identity. This design is
approved despite the additional relations because those relations protect real
lifecycles rather than a table-count target.

## 3. Aggregate dependency DAG

The aggregate dependency graph is acyclic:

```text
Market/PIT → Dataset → CandidateSet → DecisionRun
                                      │
TargetDefinition → DecisionRunTarget ─┤
                                      v
                         DecisionTargetCommitment
                           ├→ DecisionReferenceObservation ← Market/PIT
                           ├→ Context/Signal/Forecast/Decision
                           ├→ MarketTargetOutcomeRevision ← Market/PIT
                           └→ ResearchPartitionMember ← ResearchPartition

Experiment → ExperimentPartition ← ResearchPartition
     │              │
     └→ ExperimentRun ───────────────┐
                                    v
EvaluationProtocol ───────────→ EvaluationRun
MarketTargetOutcomeRevision
     └─ read-only Outcome port → PartitionOutcomeAccess/EvaluationObservation
                                    │
                                    v
                              EvaluationMetric
                                    │
                                    v
                EvidenceItem → ResearchAssessment → ResearchQualification
                                                        │
                                                        v
                           DecisionRunQualificationRoster/Member(n+1)
```

The generation rule is:

```text
Outcome(n) → Evaluation(n) → Qualification(n) → DecisionRun(n+1)
```

No same-generation edge returns from Evaluation, Model, Assessment, or
Qualification to Candidate, Target commitment, Context, Signal, Forecast, or
Decision Run `(n)`. Every later-input binding records the source completion/
known time and must satisfy `source_known_at <= next DecisionTime`; any source
Evaluation's maximum Outcome DecisionTime must be strictly earlier than that
next DecisionTime. The `decision_run_research_qualification_roster` and member
rows are the concrete FK edge from accepted Research Qualifications to the
complete later-Run input roster; replay never resolves a mutable current/latest decision. A qualified
Model Version may be selected only by a later Decision Run through its concrete
owning binding. Runtime Step order plus repository validation and PostgreSQL
temporal/identity constraints reject delayed same-generation binding.

## 4. Target and Decision commitment

### TargetDefinition and TargetCheckpoint

Research & Qualification owns immutable `target_definition` and
`target_checkpoint` facts. A TargetDefinition freezes:

- stable code, version, content hash, instrument scope and price basis;
- Decision-reference role, exact session/time/grid rule and missing policy;
- observation horizon, calendar/session offset and corporate-action policy;
- required checkpoints, path extrema and barrier semantics;
- availability/finality requirements and algorithm/code/config Artifacts.

`target_checkpoint` stores every ordered observation/path checkpoint
relationally.
`target_metric_definition` stores every required/optional return, MFE, MAE,
barrier or other declared metric with its unit, reference/path/checkpoint shape
and completion rule. No business checkpoint, threshold, unit, role, metric, or
observation-dependency contract is hidden in JSON.

### OPEN_DECISION_RUN

`OPEN_DECISION_RUN` is mandatory immediately after `BUILD_CANDIDATE_SET` and
before `ASSESS_CONTEXT`. The command atomically writes:

1. one immutable `decision_run` bound to the exact Runtime Step, Candidate Set,
   DecisionTime, Runtime clock mode, PostgreSQL `commitment_recorded_at`, and
   code/config;
2. the complete non-empty ordered `decision_run_target` requested Target
   Definition roster, including its positive count/hash when the Candidate Set
   is empty;
3. one `decision_target_commitment` for every Candidate row × requested Target
   Definition, including `UNRANKABLE` and `RANKED_NOT_SELECTED` rows;
4. one `decision_reference_observation` per commitment with independent value,
   availability and finality states and concrete Market bar revision or Source
   Gap FK;
5. reconciled Candidate, Target, commitment, and reference-state counts;
6. command receipt, audit, and matching Runtime Attempt/Step finalization.

After Research Qualification is physically implemented, the qualified command
also writes one `decision_run_research_qualification_roster` and its complete
zero-or-more members. Root count/hash proves an intentional empty roster. Each
member binds one matching-purpose `ADMITTED` decision effective/known and
non-superseded at DecisionTime and proves strictly earlier source Outcome
generations. WP-09 creates neither relation nor a
nullable future column; the later package adds the real parent-dependent
relations and command behavior together.

The full cross-product prevents posterior selection of only successful labels.
The logical commitment identity is
`(candidate_id, decision_run_target_id)`; `decision_run_target` owns the unique
Decision Run/Target identity. The relational chain also carries
`candidate_set_id` so a Candidate from another set or a Target outside the
requested roster cannot bind.
The Decision reference must have `known_at <= DecisionTime`. Missing reference
evidence creates an explicit unavailable/failed commitment fact, never a zero or
a later substituted price. A later Provider correction cannot mutate the exact
reference revision that the Decision used.

Reference `value_status` is `COMPLETE`, `UNAVAILABLE`, or `FAILED`;
`availability_status` is `AVAILABLE`, `UNAVAILABLE`, or `FAILED`; finality is
independently `UNKNOWN`, `PROVISIONAL`, or `FINAL`. Value presence and concrete
bar/gap FK shape are constrained by those states.

Outcome is not created by this command. The commitment is the non-repudiable
ex-ante contract and contains no future value.

That relational order proves commitment-before-Outcome but is not alone a
Prospective claim: a historical replay can also create the rows in that order.
Prospective eligibility additionally requires a live Runtime clock and
`commitment_recorded_at` strictly before the Target's earliest Outcome-window
event, while every Decision input remains bounded by DecisionTime. Historical
or replay commitments remain valid engineering/historical subjects but cannot
be promoted to Prospective evidence.

## 5. Market Target Outcome

### Canonical subject and identity

The Domain aggregate is `MarketTargetOutcome`. Its subject is exactly one
`decision_target_commitment`, which already fixes Decision Run, Candidate,
instrument, Candidate Set, Dataset lineage, Target Definition, DecisionTime and
Decision reference. `market_target_outcome` is one-to-one with the commitment
and is created only when a due settlement attempt produces a factual result,
including explicit unavailability or failure.

It is not a trade, Position, Strategy, Forecast, Model, Evaluation or
Qualification result.

### Append-only revision model

Each settlement appends a full `market_target_outcome_revision` snapshot. An
exact request hash over commitment, observation cutoff, knowledge cutoff, exact
Market/PIT source revision roster, calendar, algorithm and code/config identity
is unique per Outcome. Exact retry returns the original revision.

The source roster is authoritative relational data in
`market_target_outcome_source`: each closed role has exactly one concrete
Market bar, fact, corporate-action, session, gap, or capture FK shape.
Observations bind a same-revision source row. Metrics bind a
`target_metric_definition`, while
`market_target_outcome_metric_observation` binds and reconciles every exact
same-revision observation used by that metric. The roster hash verifies these
relations; an Artifact manifest or hash alone cannot replace them.

`PARTIAL → COMPLETE`, Provider correction, changed finality, or repaired source
coverage appends a new revision with a concrete `supersedes_revision_id`.
`(outcome_id, revision_ordinal)` and `(outcome_id, request_hash)` are unique;
the superseded row belongs to the same Outcome and is the immediately preceding
ordinal. A unique non-null superseded-revision key plus root/leaf locking allows
at most one direct superseder and one leaf. The old revision and all of its
child facts remain immutable. A view may resolve the unique unsuperseded leaf,
but the view is not Authority.

An existing Evaluation observation remains bound to its exact old revision.
Correction can trigger a new Evaluation/Assessment/Qualification revision; it
cannot rewrite prior metrics or silently upgrade a prior decision.

Every revision stores independent dimensions:

| Dimension | Owner/state |
|---|---|
| Decision reference | immutable `decision_reference_observation`; value, availability and finality separate; never recomputed during settlement |
| Outcome path/window | persisted revision state `UNAVAILABLE`, `PARTIAL`, `COMPLETE`, or `FAILED`; `NOT_DUE` is a query result and creates no row |
| Checkpoint observation | one child observation per required checkpoint with independent value, availability and finality plus exact source |
| Return | one metric row with independent value, availability, finality, unit and dependencies |
| MFE | one metric row; `PARTIAL` may carry only a declared partial-path value; availability/finality remain separate |
| MAE | one metric row under the same independent rule |
| Barrier | one row per barrier metric/passage; availability/finality and intrabar ordering ambiguity are explicit |
| Availability | aggregate plus each observation/metric; exact source `available_at` and Outcome `known_at`; no missing-as-zero |
| Finality | aggregate plus each observation/metric: `UNKNOWN`, `PROVISIONAL`, or `FINAL`, separate from completeness |
| Failure | typed `market_target_outcome_reason` bound to a specific dimension and source |

Metric value presence is constrained by metric status. A complete aggregate does
not force every optional metric to be available; each Target Definition declares
which dimensions are required for aggregate completeness.

Observation/metric `value_status` is `COMPLETE`, `PARTIAL`, `UNAVAILABLE`, or
`FAILED` where the Target shape permits partiality. `availability_status` is
`AVAILABLE`, `UNAVAILABLE`, or `FAILED`; finality uses the independent vocabulary
above. Reasons bind the exact dimension whose state they explain.

### Temporal cutoffs

Settlement uses two different cutoffs:

- `observation_cutoff`: latest event time allowed in the Outcome window;
- `knowledge_cutoff`: latest `known_at` allowed for Market/PIT revisions in that
  settlement or replay.

The Market/PIT query is
`event_end <= observation_cutoff AND known_at <= knowledge_cutoff` plus the exact
Target scope and price basis. The original DecisionTime is used only for the
already-frozen Decision reference and commitment. Settlement/retrieval time is
never written back as DecisionTime, and retrospective availability is never
invented.

### Replay and correction

Replay reloads the exact Target Definition, commitment, Decision reference,
calendar, Market/PIT revisions, gaps, cutoffs and algorithm identity. It
recomputes the entire revision and compares root identity, states, values,
source FKs, hashes and reason set. It cannot query a replacement Provider or
current/latest facts. Proof requires `matched=true` with zero mismatches.

## 6. Research Partition, Experiment and first access

`FreezeResearchPartition` writes one immutable `research_partition` and its
complete non-empty `research_partition_member` roster in one transaction. The
root binds one Target Definition. A member binds one matching Decision Target
Commitment, and therefore one Dataset/Candidate/Target and DecisionTime.
Membership never stores Outcome values.

The root freezes:

- one exact Target Definition shared by every member;
- purpose: `DISCOVERY`, `FIT`, `VALIDATION`, `LOCKED_OOS`, or `PROSPECTIVE`;
- scope hash, Decision window, Outcome-window bound and exact calendar;
- purge-before/purge-after interval and embargo end;
- roster count/hash and code/config Artifacts.

Database range/exclusion constraints prevent overlapping effective windows for
the same scope where the protocol forbids overlap. Application reconciliation
proves each member lies inside its Decision window and that expanded Outcome,
purge, and embargo ranges do not cross a forbidden sibling partition.

`experiment` predeclares one research question, one primary change, one Target
Definition, protocol/code/config identities and acceptance semantics.
`experiment_partition` binds frozen partitions to explicit purposes and uses a
composite Target constraint so every member commitment matches the Experiment
Target.
`experiment_run` records one execution and does not imply a positive result.

For `LOCKED_OOS` or `PROSPECTIVE`, `RegisterExperiment` locks the Partition and
fails if any member already has an access row; the Experiment/Partition binding
and Experiment Run must therefore predate ordinal one. Reusing an already
accessed Partition may be valid for diagnostics, but it cannot recover a locked
or prospective proof claim.

`research_partition_outcome_access` is append-only and records every realized
Outcome revision made visible to an Evaluation Run. It has a monotonically
increasing access ordinal per member; ordinal one is the Authority for first
Outcome access. A Locked OOS roster is therefore proven by immutable members
and its declared Experiment binding created before every ordinal-one row, not by
a mutable `outcome_values_read` boolean or Artifact manifest.

A `PROSPECTIVE` Partition also rejects every member not opened under a live
clock before its Target's first Outcome-window event. This is independent of
first Outcome access and prevents historical backfill from impersonating a
prospective commitment.

This ledger proves system access order only. It cannot prove that a human lacked
external knowledge of an already-realized market period; Formal OOS admission
still needs the declared operator/process evidence floor and may remain blocked.

## 7. Evaluation and optional Model branch

An `evaluation_protocol` and its relational
`evaluation_protocol_metric` children freeze metrics, slices, direction,
missingness, cost policy and decision rule before Outcome access.

Every `evaluation_run` requires an Experiment Run, one frozen Research
Partition and one Evaluation Protocol. It does not require a Model. Its purpose
is one of `EXPERIMENT`, `MODEL_TRAINING`, `CALIBRATION`,
`FORECAST_EVALUATION`, or `QUALIFICATION_DIAGNOSTIC`.

Its only transitions are `OPEN → INPUTS_ACQUIRED → COMPLETED`, or terminal
`FAILED` from either prior state. `OPEN` freezes all pre-access parents;
`INPUTS_ACQUIRED` means the complete member access/observation roster committed;
`COMPLETED` means every declared metric/slice and its complete input roster
committed. There is no reopen or input replacement. `NOT_ESTIMABLE` is a metric
state in a completed Run, not a hidden omission or Run failure.

Each `evaluation_observation` FK-binds:

- its Evaluation Run;
- one Research Partition member/access ordinal;
- the exact Market Target Outcome revision returned through the Outcome port;
- the implied label-free Dataset, Candidate and Target through the commitment
  chain.

Acquisition must produce exactly one observation for every positive Partition
member, including an Outcome revision with a factual `UNAVAILABLE` or `FAILED`
result. `NOT_DUE`, absent due settlement, ambiguity, or a missing member blocks
terminalization; omission cannot change the sample.

`evaluation_metric` binds one declared protocol metric and stores a typed
status/value/unit/slice. `evaluation_metric_observation` records the complete
included/excluded/not-estimable member roster and reason for that metric/slice,
so sample membership cannot hide in an Artifact.
`evaluation_forecast_binding` is a branch row used only when a concrete
Forecast is evaluated. Neither Outcome nor Evaluation writes posterior fields
into `dataset`, `dataset_source`, Candidate, or Feature cells.

`model` is only a stable family identity. `model_version` exists only after a
completed `MODEL_TRAINING` Evaluation Run and requires its fitted Artifact,
feature/config identity and training Evaluation FK. Candidate, Target,
Commitment, Outcome, Experiment, ordinary Evaluation, Evidence, Assessment and
Qualification all exist without Model. A model-backed Forecast uses the
separate `forecast_model_binding`; the Version must be known by DecisionTime and
its training Outcome generations must be strictly earlier. Rule/heuristic
Forecasts have no empty or nullable Model placeholder.

Calibration is an Evaluation purpose over Outcome facts. It cannot reread bars
or accept caller-submitted labels. Qualification consumes typed Evaluation
Evidence; if a qualification diagnostic needs raw realized facts, it first
creates a `QUALIFICATION_DIAGNOSTIC` Evaluation Run and uses the same port.

## 8. Narrow read-only Outcome port

Outcome exposes one application query contract, conceptually:

```text
read_partition_outcomes(
    evaluation_run_id,
    partition_id,
    requested_knowledge_cutoff,
) -> tuple[MarketTargetOutcomeFact]
```

The DTO contains only commitment identity, Decision reference state, exact
revision identity, observation/metric/reason states and values, source revision
identities, cutoffs, availability, finality and hashes. It exposes no SQL,
repository, bars, provider client, label builder, or mutation method.

Resolution chooses the unique unsuperseded revision visible at the requested
knowledge cutoff; it never means unrestricted current/latest. A missing,
ambiguous, or multiply visible revision fails closed rather than substituting a
different Provider or an earlier/later value.

Research, Model, Evaluation, Calibration and Qualification code cannot import
Market repositories or Outcome persistence. The Research UoW records partition
access and Evaluation observations in the same short PostgreSQL transaction
that resolves the exact revisions; no DTO leaves the handler until that access
commit succeeds. Outcome rows remain read-only. Exact retry returns the same
access identities. Pure metric calculation occurs only after commit and later
completion binds results back to those access/observation IDs. Forecast
evaluation and Shadow economics consume Evaluation/Outcome DTOs rather than
constructing `PathForecastSample` or labels from bars. Producing a new Forecast
does not read realized facts from its own Decision generation.

## 9. Evidence, Assessment and Qualification

The post-Candidate Research evidence path is concrete rather than universal:

- `evidence_item` requires one terminal Evaluation Run and one immutable Artifact FK;
  class, origin, claim direction, observed time, content hash, proof ceiling and
  complete dependency count/hash are relational. `RecordEvidence` freezes the
  item and edge roster together. It has no `(kind, id)` subject and no JSON
  business Authority.
- `evidence_dependency` links EvidenceItem to EvidenceItem with concrete FKs,
  an allowed role, temporal non-decrease and DAG validation.
- `research_assessment` requires one Experiment, claim code/revision, complete
  non-empty Evaluation/Evidence counts and hashes, and a closed status. A new
  revision supersedes; negative, inconclusive and not-estimable results are
  immutable.
- `research_assessment_evaluation` is the complete terminal Evaluation Run
  roster; every Run belongs to that Experiment and has an explicit role.
- `research_assessment_evidence` is the complete concrete Evidence set; a
  composite FK requires every item's Evaluation Run in the Assessment roster.
- `research_qualification_policy` and floor rows freeze one research purpose and
  its proof requirements.
- `research_qualification_decision` requires one Research Assessment and one
  Policy. It cannot use a polymorphic subject.
- floor-result and floor-evidence rows require every policy floor and concrete
  `research_assessment_evidence` links from that decision's Assessment before
  the decision can finalize; decision, full floor vector and links commit
  atomically.

Research Qualification status is terminal and exactly `ADMITTED`, `REJECTED`,
`BLOCKED`, `NOT_ESTIMABLE`, `INCONCLUSIVE`, or `FAILED`. Only `ADMITTED` can be
adopted by a later Decision Run, with matching Research purpose and the exact
decision still non-superseded at that later DecisionTime. A later supersession
does not rewrite an already frozen Run roster.

Future Provider, Model, Strategy, Execution and Production qualification use
separate subject-specific binding/decision relations in their owning work
packages. They must not widen this Research decision into a generic registry or
add nullable future subject columns.

## 10. Market Target Outcome versus TradeOutcome

`MarketTargetOutcome` answers what the declared market path did after one
Candidate/Decision/Target commitment. It is independent of execution and may
exist when no trade was proposed or filled.

`TradeOutcome` answers what an actually opened and closed account/instrument
episode realized. Its immutable episode key, opening/closing effective Fill FKs
and complete `trade_outcome_fill_binding` roster are verified by replaying the
Fill-derived Position from zero exposure back to zero. It also binds fees/costs
and an explicit trade-path evidence window. Fill Allocation is an input only to
later sleeve-specific Trade Attribution, not the TradeOutcome subject. A Fill
correction appends a typed TradeOutcome supersession; it never edits the old
result. TradeOutcome cannot bind `decision_target_commitment` as its subject or
reuse Market Target Outcome metrics as realized PnL.

The catalog therefore uses separate concrete families:

- `market_target_outcome*` and `market_attribution_*`;
- `trade_outcome`, `trade_outcome_fill_binding`, `trade_outcome_metric`, and
  `trade_attribution_*`.

Cross-comparison is diagnostic Attribution only. No generic Outcome subject FK
or shared polymorphic metric table is permitted.

## 11. Commands, transactions and lock order

| Command | One transaction owns | External work before transaction |
|---|---|---|
| `RegisterTargetDefinition` | definition, checkpoints, metric definitions, receipt/audit/finalization | parse/validate code/config Artifacts |
| `OpenDecisionRun` | Run, requested Target roster, all commitments/references, reconciliations, receipt/audit/finalization | load immutable Candidate/Target inputs and resolve Decision-visible Market references |
| `SettleMarketTargetOutcome` | one full Outcome revision and children, receipt/audit/finalization | no Provider call; capture/normalization and pure calculation finish first |
| `FreezeResearchPartition` | root, complete members, reconciliation, receipt/audit/finalization | compute roster from commitments only; no Outcome read |
| `RegisterExperiment` | Experiment and partition bindings | protocol parsing only |
| `Open/AcquireOutcomeInputs/CompleteEvaluationRun` | predeclared Run; atomically committed access/observations before DTO release; later metrics and terminal receipt | pure metric calculation uses committed Outcome DTOs only |
| `RecordEvidence/AssessResearch/DecideResearchQualification` | each owner plus complete concrete bindings and receipt/audit | Artifact bytes verified before relational write |

Global acquisition order for participating roots is:

```text
live Runtime Run/Step/Attempt
→ immutable Artifact/definition/Market-revision rows in (kind, UUID) order
→ CandidateSet/Candidate
→ DecisionRun/DecisionTargetCommitment
→ Account → Portfolio/Risk → Intent → Fill/Allocation (execution branch)
→ MarketTargetOutcome or TradeOutcome
→ ResearchPartition
→ ExperimentRun/EvaluationRun
→ EvidenceItem → ResearchAssessment → ResearchQualificationDecision
```

No transaction performs Provider, filesystem or broker I/O. No Repository
method opens a nested transaction. A deterministic failure rolls back and uses
the owning narrow failure recorder under the same live-fence contract. A stale
fence writes nothing.

## 12. Concrete FK map

| Child | Required parent chain |
|---|---|
| `target_checkpoint`, `target_metric_definition` | `target_definition`; metric shape binds required checkpoints/roles concretely |
| `decision_run` | Runtime Step + `candidate_set` + code/config Artifacts |
| `decision_run_target` | Decision Run + Target Definition; complete ordered requested roster |
| `decision_target_commitment` | `(decision_run, candidate_set)` + `(candidate, candidate_set)` + `(decision_run_target, decision_run, target_definition)` |
| `decision_reference_observation` | commitment + exactly one concrete `market_bar_revision` or `source_gap` shape |
| `decision_run_research_qualification_roster` | unique Decision Run; complete zero-or-more member count/hash and reconciliation state |
| `decision_run_research_qualification_member` | roster + matching-purpose `ADMITTED` Research Qualification Decision; effective/known and non-superseded at DecisionTime, with strictly earlier source Outcome generations |
| `market_target_outcome` | unique commitment |
| `market_target_outcome_revision` | Outcome + optional direct superseded revision in the same Outcome |
| `market_target_outcome_source` | exact Outcome revision + exactly one closed-role concrete Market/PIT FK shape |
| Outcome observation/metric/reason | exact Outcome revision + Target checkpoint/metric definition + same-revision source where applicable |
| `market_target_outcome_metric_observation` | exact same-revision metric + observation + dependency role |
| `research_partition` | exact Target Definition + positive roster count/hash + calendar/Decision/Outcome/purge/embargo bounds |
| `research_partition_member` | partition + matching-Target commitment; copied Decision/Dataset/Candidate/Target keys composite-FK back to that commitment chain |
| `research_partition_outcome_access` | partition member + exact Outcome revision + Evaluation Run |
| `experiment_partition` | Experiment + Research Partition; composite Target/member reconciliation |
| `experiment_run` | Experiment + exact `experiment_partition` roster/config |
| `evaluation_run` | Experiment Run + `experiment_partition` belonging to the same Experiment + Evaluation Protocol |
| `evaluation_protocol_metric` | Evaluation Protocol |
| `evaluation_observation` | Evaluation Run + access row for that same Partition + exact Outcome revision |
| `evaluation_metric` | Evaluation Run + declared Evaluation Protocol metric |
| `evaluation_metric_observation` | exact Evaluation Metric + same-Run Evaluation Observation + inclusion state/reason |
| `evaluation_forecast_binding` | Evaluation observation + concrete Forecast |
| `model_version` | Model + completed MODEL_TRAINING Evaluation Run + fitted Artifact |
| `forecast_model_binding` | Forecast + Model Version; known-time and earlier-training-generation checks |
| `evidence_item` | Evaluation Run + Artifact |
| `evidence_dependency` | child EvidenceItem + parent EvidenceItem |
| `research_assessment` | Experiment + complete Evaluation/Evidence counts and hashes + optional prior Assessment only as typed supersession |
| `research_assessment_evaluation` | Assessment + terminal Evaluation Run from the same Experiment + role |
| `research_assessment_evidence` | Assessment + EvidenceItem whose Evaluation Run is in the Assessment roster |
| `research_qualification_policy_floor` | Research Qualification Policy |
| `research_qualification_decision` | Research Assessment + Research Qualification Policy + typed prior-decision supersession |
| `research_qualification_floor_result` | Decision + exact Policy floor |
| `research_qualification_floor_evidence` | floor result + an Assessment-Evidence binding from the decision's Assessment |
| `trade_outcome` | Account + Instrument + concrete opening/closing effective Fill roots for one closed derived episode + optional same-episode supersession |
| `trade_outcome_fill_binding` | TradeOutcome + every effective Fill revision in that episode |
| `trade_outcome_metric` | TradeOutcome + typed metric role and exact Fill/path dependencies |

There are no weak string references, arrays as lineage, generic registry rows,
JSON business owners, or future nullable FK placeholders.

## 13. Logical table catalog change

The previous 91-relation estimate is replaced, not patched around. The sole
catalog now enumerates 116 semantic relations: the implemented 40-relation
draft remains physically unchanged, while the design-only destination changes
as follows.

| Catalog area | Previous | Frozen WP-08 | Reason |
|---|---:|---:|---|
| Runtime/Market/Selection/Research Definition | 40 | 40 | no semantic change |
| Remaining Research & Qualification | 17 | 28 | explicit Target metrics, partition members/access, Evaluation protocol/metric input rosters and concrete Evidence/Assessment/Qualification bindings, including a multi-Evaluation Assessment roster |
| Decision Support | 18 | 24 | explicit requested Target roster, pre-Context Target commitment/reference, concrete later-generation Research Qualification roster/members and optional Model-backed Forecast branch |
| Market Outcome, TradeOutcome and Attribution | 6 | 14 | revision/supersession, relational source/metric dependencies and concrete Market/Trade subject separation |
| Execution & Account | 10 | 10 | no semantic change in this work package |
| **Total** | **91** | **116** | semantics, not quota |

The 76 design-only relations are not placeholders and are not added to DDL by
this work package.

## 14. Implementation order

The dependency-coherent work packages are:

1. **WP-09 Target Commitment and Decision Run Authority**;
2. Market Target Outcome settlement/revision and read-only port;
3. Research Partition roster/access and Experiment predeclaration;
4. Evaluation protocol/run/observation/metric over the Outcome port, without a
   Forecast child placeholder;
5. Evidence, Research Assessment and Research Qualification;
6. optional Model/ModelVersion and Calibration branches, without a Forecast
   child placeholder;
7. remaining Context/Signal/Forecast/Opportunity/Portfolio/Risk Decision
   Support, adding the Decision Run Research Qualification roster/members only
   now that their real parent exists, then `forecast_model_binding` and
   `evaluation_forecast_binding` only after their real Forecast parent;
8. Execution/Account, TradeOutcome and Attribution;
9. Runtime/CLI Cutover, then Legacy deletion under separate authorization.

This is implementation dependency order, not empirical promotion order. Model,
Decision Support, Execution, Attribution, cutover and deletion retain their own
exit gates.

## 15. Next work package

### WP-09 minimum scope

- Domain and ports for TargetDefinition/TargetCheckpoint/TargetMetricDefinition;
- `RegisterTargetDefinition`;
- DecisionRun, DecisionRunTarget, DecisionTargetCommitment and
  DecisionReferenceObservation;
- mandatory `OPEN_DECISION_RUN` Step between Candidate and Context;
- one test-only vertical slice from an existing Candidate Set to a fully
  reconciled commitment roster;
- concrete Target/Candidate/Market source FKs, command receipt, audit, fence,
  idempotency, concurrency and exact replay.

### Non-scope

- no Outcome root/revision or label computation;
- no Partition, Experiment, Evaluation, Model, Evidence, Assessment or
  Qualification table;
- no Context, Signal, Forecast, Opportunity, Portfolio, Risk, Execution,
  Attribution or TradeOutcome;
- no Legacy writer deletion, compatibility read, dual write, Runtime/CLI
  cutover, campaign or evidence promotion.

### TDD matrix

| Test first | Required proof |
|---|---|
| Target identity/checkpoint/metric vocabulary | immutable hash, exact order and relational metric/dependency shape; no JSON business semantics |
| Requested Target and Candidate × Target rosters | non-empty Target roster survives empty Candidate Set; every Candidate row committed exactly once per requested Target; counts/hash reconcile |
| Decision reference state | exact Decision-visible Market revision or explicit Source Gap; no late substitution |
| Commitment time/mode | Runtime clock mode and PostgreSQL recorded time freeze; replay/historical mode cannot later claim Prospective |
| Composite FK mismatch | wrong Candidate Set/Target/Decision Run/source is rejected by PostgreSQL |
| Runtime DAG | `BUILD_CANDIDATE_SET → OPEN_DECISION_RUN → ASSESS_CONTEXT`; no bypass |
| Idempotency/concurrency | exact retry returns one Run/roster; changed request fails; one writer wins |
| Fence/failure/crash | stale writer writes nothing; deterministic failure receipt is atomic; orphan bytes are non-authoritative |
| Replay | exact inputs produce identical identities/hash/roster and zero mismatches |
| Architecture | no Candidate-to-Research reverse import, Model prerequisite, generic registry, placeholder or Legacy import |
| Repository regression | full clean PostgreSQL and `uv run` gate; source/DDL change limited to WP-09 scope |

### Exit gate

WP-09 exits only when a Target roster and every Decision reference are fully
committed before Context or any Outcome visibility, with no Outcome placeholder
and no Model dependency. That exit authorizes the separate Outcome coding work
package, not Runtime cutover.

## 16. Explicit deferrals

- Model/ModelVersion fitting and selection: deferred until Evaluation exists.
- Context, Signal, Forecast, Opportunity, Thesis, Portfolio and Risk: deferred
  to Decision Support work; only the pre-Context envelope is in WP-09.
- Provider qualification/finality evidence: deferred to purpose-specific
  Qualification; Outcome records `UNKNOWN`/`PROVISIONAL` honestly.
- Fill-derived TradeOutcome and both attribution branches: deferred to
  Execution/Attribution work.
- Runtime/CLI cutover, baseline release/checksum freeze, Legacy writer/read
  deletion and database destruction: separately authorized only.
- Formal OOS, Alpha optimization, Prospective and Provider campaigns: not run.

## 17. Design exit

```text
WP-08 = DESIGN_APPROVED
IMPLEMENTATION_ORDER = AUTHORIZED
NEXT_WORK_PACKAGE = READY_FOR_IMPLEMENTATION
RUNTIME_CUTOVER = NO-GO
```

These statuses approve only the Target design and ordered engineering work.
They do not claim any post-Candidate table or Runtime behavior is implemented.
