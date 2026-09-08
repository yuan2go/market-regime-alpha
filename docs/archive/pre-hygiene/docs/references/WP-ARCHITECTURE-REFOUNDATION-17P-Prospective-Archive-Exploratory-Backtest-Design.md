# WP-17P Prospective Archive Operations and Exploratory Backtest Design

> **Status:** CANONICAL_TARGET_ARCHITECTURE
> **Authority:** Frozen implementation contract for WP-17P
> **Baseline:** `origin/main@f67a4f34761516dab65825c38c4e81019f8c2dd1`
> **Scope:** exploratory retrospective research and first-party prospective evidence accumulation only
> **Owner:** Market & PIT, Research & Qualification, Decision Support, using the existing Runtime
> **Frozen:** 2026-09-03

## Decision

WP-17P establishes two permanently separate evidence lanes and uses the target
Authority graph to execute a bounded engineering/exploratory pilot:

```text
RETROSPECTIVE_BACKFILL
  real bytes captured now
  + real PostgreSQL known time
  + historical event-time simulation
  -> EXPLORATORY_RETROSPECTIVE only

PROSPECTIVE_CONTEMPORANEOUS
  captures after PostgreSQL archive_start_at
  + actual scheduled observation time
  + repeated revision observations
  -> first-party evidence accumulating over real future time
```

The ordinary PIT contract is unchanged:

```text
source known_at <= DecisionRun.decision_time
```

Historical facts downloaded during WP-17P are never assigned a historical
`known_at`, `source_available_at`, or finality claim. Retrospective simulation
uses a concrete dual-clock binding; it does not relax or branch the ordinary
PIT query contract. Formal PIT, Formal Dataset, LOCKED_OOS, PROSPECTIVE
Partition, Provider Qualification admission, and later Formal read ports reject
the retrospective lane and its evidence class.

WP-17P does not reopen the WP-16 Provider Gate. The immutable WP-15 BaoStock
Protocol, Capture, Artifact, Requirement results, and `REJECTED` Decision and
the immutable WP-16 blocker remain unchanged.

## Evidence vocabulary and ceilings

The Market archive lane vocabulary is closed:

```text
RETROSPECTIVE_BACKFILL
PROSPECTIVE_CONTEMPORANEOUS
```

The retrospective evidence class is exactly:

```text
EXPLORATORY_RETROSPECTIVE
```

It cannot be superseded or promoted in place. New first-party prospective
captures do not retroactively change old backfill rows. Repeated identical
Provider content is a recorded stability observation, not proof of Provider
finality. Missing historical publication or revision metadata remains:

```text
source_available_at = NULL
source_availability_status = UNKNOWN
provider_revision = UNKNOWN
revision_finality = UNKNOWN
```

The maximum WP-17P research claims are reproducible exploratory results and
first-party contemporaneous evidence accumulation. The following remain false
or blocked irrespective of metric values:

```text
FORMAL_PROVIDER_QUALIFICATION = BLOCKED
FORMAL_PIT = BLOCKED
FORMAL_OOS = NOT_RUN
PROSPECTIVE_PROVEN = NO
ALPHA_PROVEN = NO
MODEL_QUALIFIED = NO
PRODUCTION = NO_GO
```

## Archive Authority

Market & PIT owns a cohesive archive module. It adds four immutable relational
authorities:

```text
MarketArchive
MarketArchiveSlice
MarketArchiveCaptureObservation
MarketArchiveSeal
```

### MarketArchive

`StartMarketArchive` creates one root using PostgreSQL authoritative time. The
root freezes:

- exact lane;
- Provider and ProviderProduct revisions;
- exact exchange/calendar and requested fact kinds;
- timeframe and price basis;
- deterministic instrument-scope policy and its hash;
- requested start/end sessions for retrospective work;
- expected observation schedule for prospective work;
- resource budget and clean-stop thresholds;
- exact code/config Artifact identities and provenance;
- slice count/hash;
- PostgreSQL `archive_start_at`.

For `PROSPECTIVE_CONTEMPORANEOUS`, no slice or observation may have a request
start before `archive_start_at`. For `RETROSPECTIVE_BACKFILL`, the requested
event window may precede it, but every Capture retains its actual PostgreSQL
recorded/known time.

### Slice roster and recovery

`MarketArchiveSlice` is the complete, contiguous, non-empty work roster. Each
slice freezes exact Product request identity, instrument/calendar scope,
event-time range, expected row semantics, and ordinal. The caller supplies the
root request, not an arbitrary successful slice subset. PostgreSQL derives and
reconciles the root count/hash before registration succeeds.

Runtime Run/Step/Attempt/lease/fence remains the sole work-control owner.
Archive execution claims bounded Runtime work and performs:

```text
claim Runtime attempt
-> Provider I/O outside transaction
-> publish and verify content-addressed Artifact outside transaction
-> RecordCapture in short fenced transaction
-> NormalizeCapture using existing Market command
-> RecordArchiveCaptureObservation in short fenced transaction
-> complete Runtime attempt
```

No second scheduler, lease table, generic queue, or direct SQL writer is
introduced. An exact identical request replays; changed request fails closed.
Partial work leaves completed immutable slices and resumable pending/failed
slices. Resource preflight may cleanly stop remaining work as
`PARTIAL_WITH_RESOURCE_LIMIT`; existing raw Artifacts are never deleted to make
space.

### Capture observations, gaps, and revisions

Every observation concrete-FKs one archive slice and one `data_capture`; the
Capture already concrete-FKs the immutable Artifact. The observation freezes:

- schedule slot and observation ordinal;
- requested/provider/capture-started/capture-completed/recorded/known times;
- event/session range and exact Product;
- content hash and byte size;
- normalized revision count/hash;
- observed content relation to the previous observation: `FIRST`, `IDENTICAL`,
  `CHANGED`, or `FAILED`;
- actual timeliness state: `ON_TIME`, `LATE`, `MISSED`, or `NOT_APPLICABLE`.

Existing typed `SourceGap` remains the Market missing/malformed/unsupported
fact Authority. Archive rows bind exact gaps; they do not duplicate gap truth.
No silently dropped Provider row is allowed.

### Retrospective seal

`SealRetrospectiveArchive` runs only after every declared slice is terminal and
every success has an exact Capture/Artifact/normalization observation while
every failure has an exact SourceGap. It freezes PostgreSQL `sealed_at`, the
complete slice/capture/artifact/revision/gap roster hashes, and a
`knowledge_cutoff = sealed_at`. The seal is append-only and cannot be replaced.

Retrospective Dataset or backtest registration requires this seal. A partially
complete root may be sealed only with an explicit
`PARTIAL_WITH_GAPS`/`PARTIAL_WITH_RESOURCE_LIMIT` disposition and a complete
terminal gap roster; consumers cannot silently narrow it.

## Bounded pilot scope

The first execution is an `ENGINEERING_EXPLORATORY_PILOT`, not a CSI300 or
all-A-share research claim. It freezes:

- event window `2026-01-01` through the archive-start trading date;
- SSE/SZSE trading sessions actually returned by the Product, with missing
  semantics explicit;
- current accessible BaoStock Product revisions;
- full captured security-master/calendar responses used by the pilot;
- historical CSI300 membership/status only where the Product supplies it;
- a fixed-salt stable-hash selection of 32 eligible securities per historical
  roster and the deterministic union across sessions;
- raw/unadjusted daily and 5-minute bars (`adjustflag=3`);
- explicit Product limitations for unsupported 1-minute, publication/finality,
  membership/status, corporate-action, or price-basis evidence.

Stable hashing prevents return-based sampling; it does not make today's
membership backfill PIT. No return, Outcome, or later Candidate result may
participate in scope selection. Expansion beyond 32 securities is allowed only
as a new archive/backtest generation after resource preflight, never by
replacing the pilot.

## Dual-clock retrospective simulation

The typed value is:

```text
RetrospectiveSimulationClock
  archive_seal_id
  knowledge_cutoff       # exact PostgreSQL MarketArchiveSeal.sealed_at
  simulation_session_id
  simulated_event_cutoff # historical event boundary within the sealed archive
  evidence_class         # fixed EXPLORATORY_RETROSPECTIVE
```

Its invariants are:

```text
simulated_event_cutoff < knowledge_cutoff
all selected event_at <= simulated_event_cutoff
all source known_at <= knowledge_cutoff
all sources belong to the exact retrospective archive seal
```

The ordinary Dataset/Decision `decision_time` is the real
`knowledge_cutoff`. The historical event boundary is separately concrete-bound
and never substituted for `decision_time`. Typed retrospective applications
reuse existing owners:

```text
RegisterRetrospectiveDataset
BuildCandidateSet                         # existing command
OpenRetrospectiveDecisionRun
AssessContext / ProduceSignal / ProduceForecast
BuildOpportunity / BuildPortfolio / DecideRisk
SettleOutcome / AcquireOutcomeInputs / CompleteEvaluationRun
```

`RegisterRetrospectiveDataset` validates every exact Dataset source through a
Market-owned archive-seal read port: its event is not later than the simulated
cutoff, its actual `known_at` is not later than the knowledge cutoff, and its
Capture belongs to the seal. It creates the ordinary immutable Dataset and one
concrete `retrospective_dataset_binding`; it does not copy Dataset rows/cells.

`OpenRetrospectiveDecisionRun` creates the ordinary DecisionRun with
`decision_time = knowledge_cutoff`, resolves the exact historical
simulation-session reference revision, preserves its actual `known_at`, and
adds a concrete `retrospective_decision_run_binding`. The normal
`OpenDecisionRun` remains unchanged and cannot accept a retrospective clock.
Formal/PIT applications reject both retrospective binding tables.

Context, Signal, Forecast, Opportunity, Strategy, Portfolio, and Risk continue
to use their existing exact DecisionRun/commitment/source relationships.
Outcome continues to be the sole realized-label owner and resolves later event
observations at an exact requested knowledge cutoff. No retrospective command
computes labels from raw bars.

## Exploratory backtest predeclaration

Research & Qualification owns `ExploratoryBacktestRun` as a narrow lineage and
simulation-protocol root. It does not own or duplicate Dataset, Candidate,
Decision Support, Outcome, Portfolio, Risk, Partition, or Evaluation facts.

One atomic `RegisterExploratoryBacktestRun` freezes:

- the exact retrospective archive seal and evidence ceiling;
- one transparent primary hypothesis and exact Target version/hash;
- exact Feature, Candidate, Context, Signal, Forecast, Strategy, Portfolio,
  Risk and cost-policy identities;
- exact deterministic universe-scope policy;
- an ordered non-empty arm roster;
- an ordered chronological fold/session roster;
- FIT/VALIDATION boundaries, purge and embargo in trading sessions;
- exact EvaluationProtocol identities and metrics;
- code/config Artifacts, random seed and provenance;
- root child counts and deterministic hashes.

The first generation has exactly these arms:

```text
1 RULE_BASELINE
2 MODEL_CHALLENGER
```

The arms share the same universe, Target, chronological folds, cost assumptions
and Evaluation metrics. They may differ only in the frozen Forecast algorithm
binding. A material change appends a new run generation. Late arms/folds or
partial rosters are impossible through deferred database reconciliation.

Every retrospective Dataset and DecisionRun binds one exact Run/arm/fold/
simulation-session member. Partition still derives its complete commitment
roster from PostgreSQL. The declared population scope includes the exact
backtest arm/fold binding so complete baseline and challenger rosters cannot be
mixed or caller-selected. Only `FIT`, `VALIDATION`, or `DISCOVERY` Partition
purposes are legal; `LOCKED_OOS` and `PROSPECTIVE` fail closed.

## Model Authority

The minimal optional Model seam remains inside Research & Qualification:

```text
Model
ModelTrainingRun
ModelTrainingSample
ModelVersion
```

`Model` is a stable family identity. `OpenModelTrainingRun` requires a terminal
FIT Evaluation and derives the complete estimable/non-estimable sample roster
from exact `EvaluationObservation` and `EvaluationMetricObservation` rows. The
caller cannot supply performance or choose training members. Each sample binds
the exact Dataset row/feature cells and Outcome revision used by Evaluation.

The required ordering is:

```text
completed FIT samples
< ModelTrainingRun opened
< deterministic fit outside transaction
< immutable model Artifact published and verified
< ModelVersion registered
< later fold/generation ForecastModelBinding
```

`RegisterModelVersion` reloads the complete training roster, code/config
Artifacts, algorithm, hyperparameters, seed, training cutoff, fitted Artifact
hash/size, and training Evaluation identity. Missing/changed samples or Artifact
bytes fail closed. Model fitting has no database, Provider, network, or mutable
filesystem access inside a business transaction.

The first challenger is a simple deterministic regularized linear estimator.
Use a maintained numerical implementation already present after dependency
resolution when it preserves deterministic seed/config and Decimal boundary
conversion; otherwise use a reviewed closed-form/iterative implementation.
There is no large search or AutoML. The fitted coefficients and preprocessing
parameters are immutable content-addressed bytes.

Decision Support owns concrete `ForecastModelBinding`. It requires an existing
Forecast and exact ModelVersion, verifies that the Forecast DecisionRun belongs
to a later fold/generation than every training sample, and freezes inference
input/output hashes. Same-fold, same-generation, or earlier-decision binding is
rejected. Model is not a Candidate, Target, rule-based Forecast, or ordinary
Evaluation prerequisite. Outputs remain uncalibrated.

## Backtest Evaluation

Evaluation remains the only metric Authority. WP-17P extends its typed metric
source vocabulary rather than creating a report/DataFrame truth:

```text
OUTCOME_METRIC
FORECAST_OUTCOME_PAIR
CANDIDATE_DISPOSITION
SIGNAL_STATUS
PORTFOLIO_LINE
RISK_DECISION
```

Every metric observation concrete-FKs the existing canonical owner row from
which its inclusion/value/state is derived. `AcquireOutcomeInputs` still
creates the complete Outcome observation roster transactionally before Outcome
values leave the boundary. A backtest-specific acquisition extension freezes
the complete corresponding Decision-source roster in that same Evaluation
input generation; missing exact sources are explicit, never omitted.

V1 reducers include, where type-compatible:

- data, Signal and Forecast coverage/estimable rates;
- candidate population and selected ratio;
- Spearman RankIC or a Target-appropriate predictive metric;
- gross return and declared-cost net return;
- MFE, MAE and hit/barrier metrics;
- turnover, drawdown and exposure;
- Portfolio/Risk rejection rate;
- sample, included, excluded and not-estimable counts.

Reducers are deterministic and freeze reducer/source-value compatibility.
Cost observations are marked `ASSUMED_COST` unless separately supported by
empirical cost evidence. Every metric/slice retains included, excluded and
not-estimable members and reasons. A metric cannot complete until its complete
member Cartesian roster reconciles.

## Prospective capture schedule

The initial archive profile freezes decision-critical slots such as:

```text
D intraday
D DecisionTime-near
D close
D post-close/evening
D+1 pre-open
D+1 DecisionTime/Outcome observation
D+1 post-close
later verification
```

The first execution may occur after close. It may prove only:

```text
PROSPECTIVE_ARCHIVE_STARTED = true
POST_CLOSE_OPERATIONAL_SMOKE = complete or failed-with-gap
FIRST_PARTY_KNOWN_TIME = ACCUMULATING
```

Only a Capture whose actual `known_at` is at or before its actual scheduled
DecisionTime can support future prospective Decision evidence. A late capture
remains useful revision/gap evidence but cannot be relabeled contemporaneous.
No future Outcome is synthesized. Expected but absent slots become explicit
missed observations/SourceGaps.

## Composition and operator surface

The sole `bootstrap.py` target composition root constructs the archive,
retrospective Dataset/Decision, exploratory backtest, Model training/version,
model Forecast binding, Evaluation extensions, reconciliation and inspection
services. Infrastructure implements each owning context's typed ports.

A controlled `mra archive` and `mra exploratory-backtest` operator surface may
expose:

```text
start | resume | inspect | retry | gap-report | revision-report | daily-health
run | inspect
```

It invokes composed Application commands only. It is not target Runtime/CLI
hard cutover and never imports a concrete PostgreSQL repository into Domain or
Application code.

Qualification databases use disposable names and artifact roots and may be
recreated. The real operational archive uses a separately configured database
and external content-addressed Artifact root. Commands reject known test
database names for operational execution. Bootstrap verify is allowed; exact
OID recreate, teardown and destructive fixture cleanup are prohibited on the
operational database.

## Transactions, concurrency, and recovery

Every command follows existing global lock order and command support:

```text
short PostgreSQL transaction
-> Runtime fence first when claimed
-> owner root lock
-> complete child roster lock/read
-> exact hash reconciliation
-> append immutable rows
-> receipt/audit
-> commit
```

There is no Provider/network/filesystem I/O inside business transactions, no
nested transaction, no generic UoW/repository, no current/latest shortcut, no
blind unknown-commit retry, and no dual write. Identical concurrent requests
produce one truth plus exact replay; changed requests fail closed. Unknown
commit uses exact receipt/business probe before replay. Stale fences make zero
business/failure writes.

The read-only verifier recalculates archive root/slice/observation/seal hashes,
Artifact integrity, prospective ordinals/timeliness, dual-clock bounds,
backtest arms/folds, Dataset/Decision bindings, Model sample/version lineage,
Forecast generation order, Partition/Outcome/Evaluation completeness and
receipt/audit/Runtime provenance. It never calls a Provider, reconstructs
labels, selects current/latest rows, or mutates state. Success is:

```text
matched = true
mismatch_count = 0
```

## Real execution and resource safety

Qualification and real execution are ordered:

```text
freeze final implementation SHA
-> disposable PostgreSQL full qualification
-> create isolated operational PostgreSQL database and Artifact root
-> resource preflight
-> real retrospective pilot capture and seal
-> prospective archive start and real post-close/available-slot smoke
-> canonical baseline run
-> FIT Evaluation and ModelVersion
-> later-fold challenger run
-> Evaluation/replay/reconciliation
-> immutable Verification
```

The resource preflight freezes minimum free disk, reserved headroom, maximum
Artifact bytes, maximum slice bytes and stop policy. It runs before every
bounded batch. Insufficient resources produce a clean terminal partial status
and exact gaps; raw evidence is never deleted or overwritten.

The immutable Verification reports engineering, retrospective execution,
prospective accumulation, Model/backtest results, and Formal evidence ceilings
separately. Negative or not-estimable model results are successful scientific
execution, not an engineering failure.

## Non-scope

WP-17P does not authorize:

- weakening or rewriting WP-15/WP-16 evidence;
- Provider admission or qualified historical visibility;
- retrospective facts called Formal PIT;
- LOCKED_OOS or Formal campaign execution;
- prospective proof before sufficient real future observations;
- Calibration, AutoML or parameter mining;
- automatic broker trading or Production Admission;
- Runtime/CLI hard cutover or Legacy deletion.
