# PostgreSQL, Temporal and Evidence Architecture

> **Status:** CANONICAL_TARGET_ARCHITECTURE
> **Authority:** Target logical schema, PIT, evidence, artifact, and cutover specification
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-27
> **Implementation State:** DESIGN_CHECKPOINT_ONLY
> **Code Evidence:** `src/market_regime_alpha/persistence/postgres/schema.py`, `src/market_regime_alpha/persistence/postgres/migrations/*.sql`, `tests/persistence/postgres`

The current baseline contains 283 tables. The target logical catalog contains
**91 tables**. This count follows required semantics; it is not a reduction KPI.
The physical DDL does not exist in this checkpoint.

## 1. Database rules

- PostgreSQL 16 is the sole relational Authority.
- Target application schema: `mra`.
- Primary keys are application-generated `uuid`; declared natural identities
  also have unique constraints.
- All business timestamps are `timestamptz`; exchange sessions additionally use
  `date` and IANA timezone identifiers.
- Prices, quantities, rates, money, and metrics use bounded `numeric` precision;
  floats do not carry canonical financial values.
- Closed business vocabularies are typed in Python and enforced by
  `CHECK (value IN (...))` in the baseline.
- Foreign keys default to `ON DELETE RESTRICT`. Cascades are limited to
  subordinate rows that cannot exist outside their immutable root.
- Every foreign-key access path has a leading index. Every major as-of query has
  a composite index matching equality columns before time/range columns.
- Immutable/revision tables are append-only; one shared database guard rejects
  update/delete outside the offline maintenance role.
- No partitioning is present initially. It may be introduced only from measured
  retention volume and query plans, without changing Authority.
- JSONB is permitted only for opaque provider headers, schema-versioned
  diagnostics, or presentation metadata. Stable business facts, lifecycle,
  reasons, metrics, and lineage are relational.
- Read views are replaceable and are not counted as tables.

## 2. Frozen target table catalog

### Runtime and provenance — 13 tables

| Table | Purpose | Lifecycle and key constraints |
|---|---|---|
| `schema_epoch` | one-row architecture epoch and baseline/seed checksum | singleton; immutable; epoch/checksums exact |
| `schema_migrations` | forward-only migrations within the epoch | unique version/name/checksum; applied timestamp |
| `command_receipt` | command idempotency and committed result | unique kind/scope/key; immutable request hash; result FK/hash |
| `runtime_schedule` | typed schedule revisions | unique schedule/revision; at most one enabled revision |
| `runtime_run` | one frozen invocation | unique schedule/fire identity; valid Run transition/timestamps |
| `runtime_step` | logical DAG node and current fence/state | unique run/step key; non-negative monotonic fence |
| `runtime_step_dependency` | typed Step DAG edges | unique predecessor/successor; no self-edge; cycle checked at plan time |
| `runtime_attempt` | leased/fenced execution claim | unique step/attempt no and fence; one live Attempt per Step |
| `audit_event` | append-only operator/system mutation audit | command receipt and aggregate/version links; no secrets |
| `artifact` | content-addressed metadata and verified locator | unique SHA-256/size/media type; declared integrity state |
| `artifact_dependency` | exact artifact derivation edges | unique parent/child/role; no self-edge |
| `artifact_verification` | append-only hash/size/existence verification | artifact/time/verifier/result; mismatch immutable |
| `artifact_gc_candidate` | two-pass orphan quarantine | unique artifact; first/second seen and operator disposition |

### Market and PIT — 12 tables

| Table | Purpose | Lifecycle and key constraints |
|---|---|---|
| `provider` | stable source identity | unique code; no credential |
| `provider_product` | source/fact/time/price-basis contract | unique provider/product/revision; qualification link optional but explicit |
| `data_capture` | exact request/response capture metadata | provider product + artifact; DB capture times; request hash; status |
| `instrument` | stable security/ETF/index identity | unique internal code; exchange/type/lifecycle checks |
| `instrument_identifier` | effective-dated provider/exchange identifiers | no overlapping scheme/provider value or instrument interval |
| `trading_session` | exchange calendar/session bounds | unique exchange/session date; valid local/UTC bounds and state |
| `classification` | index/industry/theme taxonomy node | unique taxonomy/code/revision |
| `classification_membership_revision` | PIT instrument membership | logical key/revision; effective/available/known times; source evidence |
| `market_bar_revision` | raw or adjusted OHLCV revision | instrument/timeframe/interval/basis/revision unique; legal OHLC; capture/evidence FK |
| `instrument_fact_revision` | typed suspension/status/shares/limit/reference fact | kind-specific typed value check; logical key/revision unique |
| `corporate_action_revision` | dividends/splits/rights/conversions revision | action identity/revision unique; ex/record/pay session and factors constrained |
| `source_gap` | expected observation missing/placeholder/conflict | source/scope/interval/kind unique; typed reason/status |

### Universe, Eligibility, and Candidate — 12 tables

| Table | Purpose | Lifecycle and key constraints |
|---|---|---|
| `universe` | stable Universe definition identity | unique code; immutable purpose |
| `universe_revision` | frozen policy/source/config revision | universe/revision unique; decision visibility basis and artifact hash |
| `universe_member` | complete included/excluded/unknown roster | unique revision/instrument; status/reason/evidence required |
| `eligibility_policy` | immutable typed Eligibility rule version | unique code/version/hash; active interval cannot overlap |
| `eligibility_rule` | ordered typed criterion within an Eligibility policy | unique policy/code/ordinal; operator, value type and missing behavior constrained |
| `eligibility_assessment` | per-instrument Decision-time result | unique universe revision/policy/instrument/decision time |
| `eligibility_reason` | criterion result and exact evidence | unique assessment/criterion; typed result/observed/threshold/evidence FK |
| `candidate_policy` | immutable selection/ranking/tie policy | unique code/version/hash; selection cardinality and tie behavior typed |
| `candidate_policy_component` | ordered Feature/weight/direction policy component | unique policy/feature and ordinal; finite decimal weight |
| `candidate_set` | frozen complete Candidate funnel | exact Decision Run/universe/policy/dataset/model/config; scope counts reconcile |
| `candidate` | admitted eligible instrument/rank/score | unique set/instrument and set/rank; eligibility FK must match instrument |
| `candidate_score_component` | typed factor contribution and missingness | unique candidate/feature; numeric value/status/source evidence |

### Research and Qualification — 20 tables

| Table | Purpose | Lifecycle and key constraints |
|---|---|---|
| `dataset` | immutable dataset identity/manifest | unique content hash/semantic version; artifact and PIT scope |
| `dataset_source` | exact source fact/artifact dependencies | unique dataset/source/role; evidence-time constraint |
| `feature_definition` | immutable feature/factor semantics | unique code/version/hash; units/window/missing policy typed |
| `target_definition` | immutable Decision reference/horizon/metric protocol | unique code/version/hash; price basis and calendar policy typed |
| `target_checkpoint` | ordered target path/checkpoint grid | unique target/ordinal and target/session-offset/local-time |
| `research_partition` | frozen Discovery/OOS/Prospective membership/time slice | unique identity/hash; non-overlap/purge/embargo constraints |
| `experiment` | predeclared hypothesis and primary change | unique protocol hash; dataset/target/code/config |
| `experiment_partition` | purpose-specific partition binding | unique experiment/purpose; partition frozen before outcome access |
| `experiment_run` | one execution of frozen Experiment | unique experiment/run key; status and artifact/result hash |
| `model` | stable model family identity | unique code |
| `model_version` | immutable fitted/model artifact lineage | unique model/version/hash; dataset/feature/partition FKs |
| `evaluation_run` | predeclared evaluation execution | experiment/model/partition/protocol and status |
| `evaluation_metric` | typed metric value/estimability | unique run/metric/slice; status independent of value |
| `evidence_item` | immutable typed evidence or counter-evidence | class/origin/scope/time/hash; artifact optional with consistency check |
| `evidence_dependency` | exact evidence graph edge | unique child/parent/role; temporal non-decrease |
| `assessment` | governed conclusion over one claim/evidence set | immutable revision; closed Assessment Status; claim/purpose typed |
| `qualification_policy` | immutable purpose-specific required-floor contract | unique code/version/hash; required floors and decision rules typed |
| `qualification_policy_floor` | required/optional floor definition and acceptance rule | unique policy/floor; typed rule, proof class and evidence requirement |
| `qualification_decision` | sole purpose-scoped admission owner | subject/purpose/revision unique; supersession; decision status |
| `qualification_floor_result` | complete qualification proof vector | unique decision/floor; every required floor present; evidence FK |

### Decision Support — 18 tables

| Table | Purpose | Lifecycle and key constraints |
|---|---|---|
| `decision_run` | frozen Decision-time envelope | unique runtime step/request; Candidate/policy/code/config identities |
| `context_assessment` | typed Regime/ETF/Theme/Capital state | unique decision run/kind/scope; state/status/evidence |
| `context_metric` | typed metric supporting Context | unique assessment/metric; value/status/evidence |
| `signal` | setup assertion for one Candidate | unique decision run/candidate/signal kind/version |
| `forecast` | Target/model-bound forecast envelope | unique decision run/candidate/target/model version |
| `forecast_estimate` | checkpoint/metric estimate and uncertainty | unique forecast/checkpoint/estimate kind; calibration status |
| `opportunity` | exact decision evidence binding; never Risk authorization | unique decision run/candidate/strategy version; required FK consistency; no `risk_decision` FK |
| `thesis` | immutable falsifiable thesis revision | opportunity/revision unique; status follows typed lifecycle |
| `thesis_condition` | entry/hold/invalidation/exit evidence condition | unique thesis/ordinal; typed condition and evidence requirement |
| `strategy` | stable Strategy family identity | unique code |
| `strategy_version` | immutable action policy semantics | unique strategy/version/hash; qualification referenced, not embedded |
| `portfolio_policy` | immutable allocation policy | unique code/version/hash; typed cash/exposure/turnover constraints |
| `portfolio_proposal` | complete allocation decision envelope | unique decision run/policy; totals/counts reconcile |
| `portfolio_line` | instrument/strategy proposed allocation | unique proposal/opportunity; signed quantity/weight constraints |
| `risk_policy` | immutable Risk limits/evidence requirements | unique code/version/hash |
| `risk_rule` | ordered typed limit/evidence rule within a Risk policy | unique policy/code/ordinal; subject, operator, unit and missing behavior constrained |
| `risk_decision` | accepted/rejected/unknown authorization | unique proposal/account/policy/decision time; versioned account evidence |
| `risk_reason` | typed binding/limit result | unique decision/rule/instrument; observed/limit/status/evidence |

### Outcome and Attribution — 6 tables

| Table | Purpose | Lifecycle and key constraints |
|---|---|---|
| `outcome` | Target-bound factual settlement envelope | unique decision subject/target; independent dimension statuses |
| `outcome_observation` | exact Decision/path/checkpoint observation | unique outcome/checkpoint/role; market revision/evidence/status |
| `outcome_metric` | return/MFE/MAE/barrier/economic metric | unique outcome/metric; status/value/units and dependency checks |
| `outcome_reason` | typed unavailable/partial/failed reason | unique outcome/dimension/reason/source |
| `attribution_run` | declared attribution basis and reconciliation total | unique outcome/policy/revision; status/total |
| `attribution_line` | dimension contribution | unique run/dimension/member; value/status; sum/remainder rule |

### Execution and Account — 10 tables

| Table | Purpose | Lifecycle and key constraints |
|---|---|---|
| `account` | stable external/manual account identity | unique provider/account key; no credentials |
| `account_authority_epoch` | explicit account cut-in/opening boundary | unique account/epoch; one active; evidence/observation |
| `position_basis_event` | typed opening/corporate-action/reconciliation delta | kind-specific FK/check; account/instrument/effective time; append-only |
| `execution_intent` | human-approved bounded execution request/reservation | unique account/idempotency and proposal line; state/quantity limits |
| `fill` | observed Fill and append-only corrections | unique provider execution/revision; intent/account/instrument consistency |
| `fill_allocation` | effective Fill quantity assigned to Strategy Version | unique fill/strategy/opportunity; allocations bounded by Fill |
| `broker_observation` | immutable account snapshot metadata | account/as-of/capture unique; artifact/hash |
| `broker_observation_line` | observed cash/position/order line | observation/kind/instrument/external key unique |
| `reconciliation` | canonical-versus-broker comparison | unique epoch/observation/policy; terminal status |
| `reconciliation_difference` | typed per-dimension difference | unique reconciliation/kind/instrument; canonical/observed/delta/status |

### Replaceable views

Initial views include `current_market_fact`,
`current_classification_membership`, `current_universe`,
`candidate_funnel`, `current_position`, `current_strategy_sleeve`,
`decision_dossier`, `run_trace`, `artifact_integrity_status`, and
`qualification_floor_matrix`. A view has no independent writer or retention
contract.

### Physical key and index baseline

The baseline DDL must include, at minimum:

| Query/invariant | Required key/index shape |
|---|---|
| due Runtime claim | partial index on runnable Step state/backoff time plus Run state; unique live Attempt per Step |
| command idempotency | unique `(command_kind, scope_id, idempotency_key)`; request hash included for exact re-read |
| Market bar as-of | `(instrument_id, timeframe, price_basis, event_end, decision_visible_at DESC, revision_no DESC)` |
| typed fact as-of | `(instrument_id, fact_kind, effective_from, decision_visible_at DESC, revision_no DESC)` |
| classification PIT | `(classification_id, instrument_id, effective_from, decision_visible_at DESC, revision_no DESC)` |
| session resolution | unique `(exchange_code, session_date)` plus UTC-boundary lookup |
| Universe/Eligibility | unique revision/member and assessment policy/instrument/time; indexes for status funnels |
| Candidate | unique Set/instrument and Set/rank; score-component Feature lookup |
| evidence graph | child/role and parent reverse indexes; no self-edge |
| qualification | unique subject/purpose/revision; policy-floor/result completeness indexes |
| Decision dossier | Decision Run foreign keys plus Candidate/instrument indexes |
| Outcome settlement | unique decision subject/Target; checkpoint/metric status and unsettled-work indexes |
| Fill projection | account/instrument/execution-time sequence; unique external execution/revision; correction-root lookup |
| reconciliation | account/epoch/observation and unresolved-difference partial index |
| artifact integrity | unique content hash; locator, unverified/mismatch and GC-grace partial indexes |

All child FKs have a leading index even when the query matrix does not list them.
Index-only duplicates are rejected during schema validation. Query plans, not
table count, determine later covering indexes.

### Mutability and retention

- Immutable/append-only: captures, Market revisions, Universe revisions/members,
  policies/rules, Candidate Sets, definitions, partitions, Experiments, Model
  Versions, Evidence, Assessments, Qualification decisions/results, Decisions,
  Outcomes, Attribution, Fills/corrections, basis events, observations,
  reconciliation results and audit.
- Guarded lifecycle mutation: Run, Step, live Attempt lease/heartbeat,
  Command Receipt pending-to-terminal, Execution Intent and schedule enablement.
  Version/fence/state predicates make every transition compare-and-set.
- Replaceable: views, generated documents, caches, staging bytes and
  unreferenced report encodings.
- Decision/Evidence/Qualification/Fill/basis/audit rows and any artifact they
  transitively reference have no time-based automatic deletion.
- Unreferenced Runtime diagnostics or artifact bytes may be cleaned only by an
  explicit retention command after dependency, legal/pin, active-Run, and
  two-pass orphan checks. Cascades never delete upstream evidence.
- Partitioning is deferred. Candidate thresholds for later review are measured
  write volume, retention cost, vacuum pressure and dominant time-range plans;
  calendar-year aesthetics alone are insufficient.

## 3. Temporal vocabulary

All temporal fields are distinct and never aliased:

| Field | Meaning | Authority |
|---|---|---|
| `event_start/event_end` | interval in which the real market event occurred | source fact plus normalization |
| `session_id` | owner-resolved exchange session and local boundaries | `trading_session` |
| `effective_from/effective_to` | business-valid interval, e.g. membership/status | normalized revision |
| `provider_time` | timestamp asserted in provider content/header | raw capture; untrusted by itself |
| `source_available_at` | evidenced time the exact source revision became available | provider-product contract/evidence |
| `capture_started_at/capture_completed_at` | local acquisition interval from PostgreSQL clock | `data_capture` |
| `recorded_at` | canonical row commit time from PostgreSQL clock | owning table |
| `known_at` | earliest time this system actually possessed and recorded the exact revision | `greatest(capture_completed_at, recorded_at)` |
| `decision_visible_at` | time used by the declared PIT mode | rule below, frozen on revision |
| `decision_time` | instant at which a Decision input set is frozen | `decision_run` |
| `settled_at` | time an Outcome/observation was persisted after availability | Outcome owner |

Timestamps are UTC in storage and converted with explicit IANA zones. A trading
date without exchange and timezone is not a session identity.

### Decision visibility

An input is visible only when:

1. its logical effective/event interval includes the Decision boundary;
2. its `decision_visible_at <= decision_time`;
3. its revision was not superseded by another revision that was already visible
   at that Decision time;
4. the declared price basis/fact kind/provider product is permitted;
5. its source/evidence/hash and required qualification verify;
6. it is not missing, placeholder, invalid, or conflicting;
7. Universe and classification membership use the same as-of rule.

The default and every prospective/operational mode use:

```text
decision_visible_at = known_at
```

A historical reconstruction may set
`decision_visible_at = source_available_at < known_at` **only** when the exact
provider product has a Qualification Decision covering archive completeness,
revision/finality, publication latency, and identity for that fact/date range.
The fact revision stores that qualification ID and visibility basis
`QUALIFIED_HISTORICAL`. Free/public or unqualified backfills use `known_at`,
usually their retrieval time, and therefore cannot pretend they were locally
known in the past. Later qualification appends a new qualified revision/dataset;
it never edits old visibility.

A caller cannot pass `visible=true` or choose “latest.” As-of selection is an
owner query ordered by `decision_visible_at, revision_no` within one logical key.

## 4. Market/PIT semantics

### Raw and adjusted

`price_basis` is closed and mandatory:
`RAW_UNADJUSTED`, `FORWARD_ADJUSTED`, `BACKWARD_ADJUSTED`, or another
explicitly approved basis. Different bases are different logical series. An
adjustment never overwrites Raw and cannot become a formal Decision/execution
price unless the Target explicitly allows that basis. The initial Target policy
accepts only Raw/unadjusted tradable prices.

### Revisions

A logical Market fact is identified without revision by instrument, fact kind,
event/effective interval, timeframe, price basis, and provider product. Each
changed source value appends a monotonically numbered revision with source
capture, content hash, temporal fields, and optional superseded ID. “Current” is
an as-of query, not an updated row. Corrections cannot be visible before their
own `decision_visible_at`.

### Missing

No returned observation is not a numeric value. When an observation was expected,
`source_gap` records interval, reason, provider, attempt/capture, and status.
Downstream status becomes `UNKNOWN`/`UNAVAILABLE` according to its own contract;
it is never silently dropped or converted to zero.

### Placeholder

Raw placeholder bytes remain in `data_capture`. A placeholder with absent or
invalid OHLC does not create a valid `market_bar_revision`. It creates or links a
`source_gap` reason such as `UNPRICED_PLACEHOLDER`. Downstream selection cannot
use it as a price.

### Suspension

Suspension/trading status is a typed `instrument_fact_revision` backed by source
evidence. Missing bars, zero volume, a flat price, or a provider placeholder do
not alone prove suspension. A suspended session does not imply zero return and a
previous-session close is not a same-session Decision price.

### Session and calendar

Sessions come only from `trading_session`. Weekday inference and “next calendar
day” are prohibited. Bar intervals must fall on an allowed session grid,
preserve half-day/break rules, and have unique non-overlapping logical
identities.

## 5. Candidate and Eligibility Decision-time Evidence

`eligibility_assessment` is evaluated for every `universe_member` at one
Decision time:

- status is exactly `ELIGIBLE`, `INELIGIBLE`, or `UNKNOWN`;
- every `eligibility_rule` creates one `eligibility_reason`;
- each reason FK-binds that rule and stores its result, typed observed value,
  typed threshold/operator, and exact `evidence_item_id`;
- every evidence dependency must be Decision-visible;
- missing required evidence produces `UNKNOWN`, never silent exclusion;
- an explicit negative rule produces `INELIGIBLE`;
- the complete counts reconcile to Universe membership.

`candidate_set` binds the exact Universe revision, Eligibility policy and
assessments, Candidate policy and ordered components, Dataset, Feature
definitions, Model Version if used, Decision time, code SHA, and config
artifact. It records total,
eligible, ineligible, unknown, selected, and rejected counts.

A `candidate` must reference a matching `ELIGIBLE` assessment. Rank uniqueness
and deterministic tie policy are constrained. Each score component is relational
and FK-bound to its Candidate policy component and Feature definition, with
numeric/status value, missingness, source Evidence, and direction/weight. A
score is not a probability. Signal and Forecast remain
downstream facts with separate owners.

This model makes empty Candidate Sets valid and auditable and prevents table
reduction from hiding Eligibility or Candidate evidence in a temporary frame or
generic JSON payload.

## 6. Target, Horizon, Outcome, MFE/MAE, and availability

A `target_definition` freezes:

- Decision reference rule;
- exchange/session resolver;
- horizon meaning;
- ordered `target_checkpoint` grid;
- allowed price basis;
- path completeness rule;
- required metrics and units;
- missing/placeholder/suspension/corporate-action policy;
- semantic content hash.

A horizon is an evaluation interval, never an automatic holding or exit rule.

### Frozen initial Decision reference

For the retained T+1 10:30 research target, the Decision reference requires one
same-session Asia/Shanghai five-minute bar ending exactly 14:55 with
`RAW_UNADJUSTED` basis, finite positive OHLC, legal price structure, verified
source/hash, and non-placeholder/non-suspended status. Zero matches is
`UNAVAILABLE`; conflicting/invalid matches are `FAILED`. Daily bars,
previous-session close, and last-available bars may be diagnostics only and
never supply the value.

### Independent state dimensions

Every Outcome stores these independently:

- `decision_reference_status`;
- `outcome_window_status`;
- each `outcome_observation.status`;
- each `outcome_metric.status`.

Closed status: `COMPLETE`, `PARTIAL`, `UNAVAILABLE`, `FAILED`. `PARTIAL` is
valid for a path or diagnostic family, not an exact point reference.

For the initial T+1 path, the next session is calendar-resolved and the exact
09:30–10:30 five-minute grid is required. Every observation retains the exact
Market revision and Evidence. A complete path can coexist with an unavailable
Decision reference.

- checkpoint return needs a complete Decision reference and exact checkpoint;
- MFE/MAE need complete Decision reference and complete applicable path;
- a partial path never produces complete MFE/MAE;
- if Decision reference is unavailable, MFE/MAE are unavailable even when the
  path is complete;
- same-bar barrier ordering may remain partial while MFE/MAE are complete;
- missing/suspension is not zero; price-limit observation is not fillability.

`outcome_metric` stores typed metric kind, status, numeric value, unit, reference
observation, path requirement, and calculation version. Value must be null for
`UNAVAILABLE`/`FAILED`. `outcome_reason` uses a closed reason vocabulary.
`available_at`/`settled_at` cannot precede required source visibility. No Outcome
row rewrites a Decision, Forecast, or Target Definition.

## 7. Evidence, Assessment, and Qualification semantics

These are three separate axes.

### Evidence Class

`evidence_item.evidence_class`:

- `SOFTWARE_VERIFICATION`
- `SOURCE_CAPTURE`
- `TEMPORAL_LINEAGE`
- `DATASET_LINEAGE`
- `RESEARCH_RESULT`
- `MODEL_RESULT`
- `DECISION_TRACE`
- `OUTCOME_OBSERVATION`
- `EXECUTION_OBSERVATION`
- `REPLAY_COMPARISON`
- `OPERATOR_ATTESTATION`

`origin_class` is also explicit:
`FIXTURE`, `RECORDED_PROVIDER`, `QUALIFIED_ARCHIVE`,
`PROSPECTIVE_CAPTURE`, `DERIVED_CANONICAL`, `BROKER_REPORTED`,
`OBSERVED_FILL`, or `OPERATOR_ATTESTED`. Origin limits the evidence ceiling; a
fixture cannot become Provider or Prospective proof.

### Assessment Status

`assessment.status` is exactly:

- `PENDING`
- `SUPPORTED`
- `REJECTED`
- `NOT_ESTIMABLE`
- `INCONCLUSIVE`
- `BLOCKED`
- `FAILED`

Negative, inconclusive, and not-estimable results are immutable evidence, not
errors to hide. `FAILED` means the assessment itself violated integrity or could
not execute as specified.

### Qualification / Proof Class

Named proof classes are scopes, **not an ordinal scalar**:

- `ENGINEERING` — code/constraint/replay behavior;
- `EXPLORATORY` — discovery on explicitly limited evidence;
- `PIT_QUALIFIED` — declared historical Decision visibility established;
- `FORMAL_OOS` — pre-frozen independent partition evaluated under protocol;
- `PROSPECTIVE` — decisions frozen before later outcomes under a live clock;
- `PRODUCTION` — purpose-specific operational/risk/admission authorization.

A Qualification Decision declares subject, purpose, requested proof class,
status, policy revision, evidence cutoff, and supersession. It has one row for
every required floor:

- `SOFTWARE_CORRECTNESS`
- `SOURCE_QUALITY`
- `TEMPORAL_PIT`
- `UNIVERSE_INTEGRITY`
- `SAMPLE_ADEQUACY`
- `EVALUATION_PROTOCOL`
- `FORMAL_OOS`
- `CALIBRATION`
- `ECONOMICS_COST_CAPACITY`
- `PROSPECTIVE_EVIDENCE`
- `EXECUTION_INTEGRITY`
- `RISK_ADMISSION`
- `OPERATIONS_RECOVERY`

Each result FK-binds one required `qualification_policy_floor`. Floor status
is `SATISFIED`, `MISSING`, `REJECTED`, `BLOCKED`, or
`NOT_APPLICABLE` with exact Evidence. Overall qualification cannot exceed its
weakest required floor. `PIT_INCOMPLETE` is represented explicitly as
`TEMPORAL_PIT = MISSING/REJECTED` under an Exploratory assessment; it is never
flattened into “evidence exists.” A Prospective capture can still be
PIT-incomplete for historical claims. Production is never inferred from a lower
class or from successful Runtime execution.

## 8. Artifact/PostgreSQL consistency

Artifact identity is SHA-256 over canonical bytes. Locator, filename, directory,
and object-store ETag are not identity.

### Commit protocol

1. produce bytes in a private staging location;
2. fsync/close, compute hash and size, and compare to the producer's canonical
   serialization;
3. publish atomically by hash (local rename) or remote put-if-absent;
4. read metadata/head and, when required, bytes to verify size/hash;
5. begin a short PostgreSQL transaction;
6. insert/reload `artifact`, dependencies, and the business row that references
   it;
7. write command receipt/audit/Runtime finalization and commit.

A database row cannot reference bytes that were not verified before commit.
Database failure after publish leaves harmless content-addressed orphan bytes;
it never leaves a canonical row pointing at a known-missing object.

### Read verification

Every authoritative read checks metadata identity, expected size, and hash at
the policy cadence. Missing/mismatch records an append-only
`artifact_verification` failure and blocks the consumer. It is not silently
re-downloaded from another Provider or repaired with different bytes. Exact
bytes may be re-published only under the same hash.

### Orphan cleanup

A scanner compares physical hashes to `artifact` and relational references:

- first unreferenced sighting creates `artifact_gc_candidate`;
- a second scan after the retention grace verifies still unreferenced,
  unpinned, and not in a live staging/Run window;
- deletion requires the maintenance role and audit;
- referenced, pinned, quarantined-integrity, or unresolved artifacts are never
  auto-deleted;
- disappearance after deletion receives a final verification record.

Database metadata orphaned from missing bytes is an integrity incident, not a GC
candidate. Physical bytes with no row are safe to retain until the two-pass rule.

### Retention

Raw captures, qualification evidence, observed Fills, audit, and evidence used by
a decision/assessment are retained according to explicit policy and cannot be
cascaded from a deleted read model. Large datasets/panels/models/reports live as
artifacts; query-critical identities, statuses, metrics, and lineage remain
relational.

## 9. Hard Cutover and schema epoch

Expected epoch:

```text
MRA_REFOUNDATION_1
```

Ordinary bootstrap is permitted only when the configured application database
has no `mra` schema and no recognized legacy Market Regime Alpha catalog, or
when `mra.schema_epoch` exactly matches epoch, baseline checksum, and seed
checksum. Any object with absent/mismatched epoch yields
`SCHEMA_EPOCH_MISMATCH` or `LEGACY_SCHEMA_PRESENT` before DDL or writer
construction.

The target starts with one immutable `001_baseline.sql`. Once released, it is
never edited. Future changes use forward-only `002+` migrations with stored
checksums. No downgrade and no v1/v2/v3 compatibility schema remains; rollback
restores a backup or switches to a separately created database.

Destructive recreate is an offline, explicit, two-phase operator action only.
It requires exact database name/OID, owner, detected epoch or approved legacy
catalog hash, backup attestation, zero unexpected objects/connections, generated
challenge, and second invocation with that challenge. It refuses system/default
databases and never runs at startup. The preferred legacy cutover is a newly
provisioned empty database; old database disposal is separate and recoverable
until operator confirmation.

Details and consequences are recorded in
[ADR-015](decisions/ADR-015-Hard-Cutover-and-Schema-Epoch.md).

## 10. Bootstrap and seed

Empty database proof:

```text
connect
→ verify empty/allowed catalog
→ create mra schema
→ apply 001_baseline in one controlled transaction
→ insert schema epoch/migration checksum
→ initialize closed reference vocabulary and default runtime step catalog
→ verify constraints/indexes/views/checksums
→ run canonical capture-to-evidence smoke
```

Seeds contain only architecture epoch and stable system reference vocabulary.
They do not invent Providers, instruments, market facts, research results,
accounts, qualification, or Production admission.

Required database tests cover empty bootstrap, idempotent verify, wrong epoch,
legacy catalog detection, interrupted baseline, checksum drift, seed drift,
constraints, FK indexes, concurrent commands/fences, clean recreate plan/apply,
and proof that ordinary startup performs no destructive DDL.
