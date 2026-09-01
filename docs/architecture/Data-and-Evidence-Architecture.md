# PostgreSQL, Temporal and Evidence Architecture

> **Status:** CANONICAL_TARGET_ARCHITECTURE
> **Authority:** Target logical schema, PIT, evidence, artifact, and cutover specification
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-09-01
> **Code Evidence:** target `src/market_regime_alpha/infrastructure/postgres`, `src/market_regime_alpha/shared`, `src/market_regime_alpha/runtime`, `src/market_regime_alpha/market`, `src/market_regime_alpha/selection`, `src/market_regime_alpha/research_qualification`, `tests/refoundation`; legacy `src/market_regime_alpha/persistence/postgres` remains current business implementation

This document is the sole Target logical table catalog. Current physical DDL,
relation/view counts, checksums, and exact-SHA engineering proof live in
[Current State](../status/Current-State.md) and the linked Verification records;
they are not copied into Canonical Architecture. The catalog follows required
semantics and is neither a quota nor a cutover claim.

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

The semantic relations below are the frozen logical catalog. Current physical
and design-only counts remain in Current State or the exact WP-08 design record;
they are not copied into Canonical Architecture and are never a quota,
physical-release claim, or permission to create placeholders. Deferred
subject-specific Provider, Model, Strategy, Execution, or Production
qualification may add concrete relations in their own approved work packages;
it may not preallocate nullable columns here.

### Runtime and provenance

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

### Market and PIT

| Table | Purpose | Lifecycle and key constraints |
|---|---|---|
| `provider` | stable source identity | unique code; no credential |
| `provider_product` | source/fact/time/price-basis contract | unique provider/product/revision; no qualification state; a later Research-owned Qualification Decision may reference this identity |
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

### Selection Core

| Table | Purpose | Lifecycle and key constraints |
|---|---|---|
| `universe` | stable Universe definition and explicit scope-spec identity | unique code; immutable purpose/config identity; never implicit all-current-instrument scope |
| `universe_revision` | frozen scope/config revision | universe/revision unique; Decision-time visibility basis and exact config hash |
| `universe_member` | complete included/excluded/unknown roster | unique revision/instrument; status/reason/evidence required |
| `eligibility_policy` | immutable typed Eligibility rule version | unique code/version/hash; active interval cannot overlap |
| `eligibility_rule` | ordered typed criterion within an Eligibility policy | unique policy/code/ordinal; kind, measure/window/unit/operator/threshold and missing behavior constrained |
| `eligibility_assessment` | per-instrument Decision-time result | unique universe revision/policy/instrument/decision time |
| `eligibility_reason` | criterion result and exact Market evidence | unique assessment/rule; typed result/observed/threshold/operator/reason and queryable lineage |

### Selection Candidate

Candidate remains permanently owned by `market_regime_alpha.selection` and is
separate from Universe/Eligibility. Candidate uses a separate narrow
Application/UoW and a
Selection-owned Research-input port; an Infrastructure adapter maps the real
Research definitions without a Selection-to-Research or Research-to-Selection
package import.

| Table | Purpose | Lifecycle and key constraints |
|---|---|---|
| `candidate_policy` | immutable V1 ranking policy | unique code/version/hash; `STRICT_COMPLETE_CASE`, arithmetic-midrank percentile, competition rank, `TOP_K`, `INCLUDE_ALL_BOUNDARY_TIES`, requested Top-K, component count, projection contract and exact code/config Artifact identities |
| `candidate_policy_component` | ordered required Feature component | unique policy/component, ordinal, and Feature Definition; binds one real numeric Feature Definition and stores only the canonical positive `declared_weight`; no Dataset, Model Version, normalized-weight, Target, Evidence, Qualification, or future identity |
| `candidate_set` | frozen Policy × Decision-input Dataset build and complete funnel | unique Policy/Dataset; Dataset is the only population; copied exact Dataset scope is composite-FK-bound; projection precision, ranking/component diagnostics, composite distinct count, boundary diagnostics and all reconciled counts are immutable; no Decision Run or later-context dependency |
| `candidate` | one terminal result for every Dataset row | unique Set/instrument and Set/population DatasetSource; disposition is `SELECTED`, `RANKED_NOT_SELECTED`, or `UNRANKABLE`; score/rank shape is constrained; competition rank is deliberately non-unique |
| `candidate_score_component` | one immutable typed calculation fact for every Candidate × Policy Component | unique Candidate/component; exact Feature/component identity, typed raw status/value/reason, deterministic cell/source-lineage hash, projected normalized weight, percentile and contribution; no DatasetSource array/GIN and no direct Evidence or later-context identity |

The five relations are the complete Candidate Authority. Dataset manifest bytes
plus relational `dataset_source` remain the sole Dataset lineage owner. A score
row stores only the Candidate computation facts and a deterministically
verifiable cell/source-lineage hash. Dossier queries follow
`candidate_set.dataset_id` to the immutable Dataset manifest and relational
sources. A direct CandidateComponent-to-DatasetSource relation may be considered
only after a measured future query profile; WP-07 creates no sixth Authority
table, business source array, or array-as-lineage index.

`candidate_policy_component.declared_weight` is the only weight Authority.
Candidate build converts the declared Decimals to exact rationals, normalizes by
their exact sum, and projects the result at the Candidate Set's versioned
decimal precision. Only the projected normalized weight is copied to each score
row beside its percentile and contribution. Finite PostgreSQL numerics need not
sum byte-for-byte to one when the exact rational is recurring; the exact
rational computation and versioned projection contract are semantic Authority.

The persisted `candidate_set.decimal_projection_precision` is restricted in
both Domain and PostgreSQL to the closed set
`{64, 128, 256, 512, 1024, 2048, 4096}`; arbitrary values such as 10 or 100 are
rejected. Candidate `policy_code` and `component_code` share the exact Domain/
DDL vocabulary `^[a-z][a-z0-9_]{0,99}$`, so hyphens are not legal Candidate
identities. The existing Eligibility code vocabulary is unchanged.

### Research Definition Core

The Research Definition Core checkpoint created the permanent
`market_regime_alpha.research_qualification` owner and only the definitions
that Candidate V1 demonstrably needed. Later WP-09 and WP-11 relations remain
in that same bounded context; no parallel Research Validity owner exists.

| Table | Purpose | Lifecycle and key constraints |
|---|---|---|
| `dataset` | immutable Decision-input Dataset identity and manifest binding | unique code/version and content hash; exact DecisionTime, Universe revision, Eligibility policy, manifest/code/config Artifact triples, complete population/cell counts; fixed Decision-input kind |
| `dataset_source` | exact relational lineage for one Dataset | closed role vocabulary; every role has concrete existing FK columns and a role-specific shape CHECK; included-member/eligible-assessment matching, Feature identity, and Market/PIT revision/session/gap/capture sources only; no polymorphic string ID or business JSON |
| `feature_definition` | immutable Feature calculation semantics | unique code/version/hash; typed value/unit, frequency/window/lookback, source requirements, availability/missingness, deterministic algorithm and exact code/config Artifact identity; no Alpha/maturity/evaluation/qualification state and no premature Feature dependency abstraction |

The Dataset Artifact is parsed through a closed Domain schema before the SQL
transaction. Its rows must exactly equal the same-DecisionTime intersection of
`UniverseMember = INCLUDED` and `EligibilityAssessment = ELIGIBLE`; every row
contains every bound Feature with an explicit status. Extra or missing rows,
silent Feature-driven row deletion, and fields for Target, Outcome, return,
MFE/MAE, barrier, future observation, realized label, or other posterior values
are rejected. Artifact and `dataset_source` lineage are validated bidirectionally
and cannot disagree.

### Target and Research Evaluation

The relations through `evaluation_metric_observation` are implemented in the
unreleased target baseline. They are not Candidate V1 prerequisites. Research
owns definitions, rosters, protocols, and Evaluation but never a bars-to-label
writer.

| Table | Purpose | Lifecycle and key constraints |
|---|---|---|
| `target_definition` | immutable Decision reference/horizon/path/metric protocol | unique code/version/hash; instrument scope, price basis, reference/session/calendar/horizon, availability/finality, algorithm and code/config Artifacts typed |
| `target_checkpoint` | ordered observation checkpoint/path grid | unique Target/ordinal/code; role, session offset, local time and required observation shape relational |
| `target_metric_definition` | typed required/optional Outcome metric semantics | unique Target/metric code; Target root requires at least one `REQUIRED` metric; each of the five kinds has exactly its Outcome-consumable reference/observation/path dependency shape; no JSON metric contract |
| `target_metric_dependency` | ordered metric-to-checkpoint dependency edge | unique Target/metric/dependency ordinal and checkpoint role; same-Target composite FKs, canonical hash and typed dependency semantics; no JSON dependency list |
| `research_partition` | frozen Target-specific Discovery/Fit/Validation/Locked-OOS/Prospective root | unique identity/hash; exact Target, Decision window, population scope, exact calendar, session-expanded Target horizon/purge/embargo protected range, purpose-specific overlap policy, positive roster count/hash, code/config and provenance |
| `research_partition_member` | complete non-empty pre-Outcome roster | PostgreSQL derives it from Target + Decision window + population scope; unique partition/commitment; composite FK matches the root Target chain; no caller roster and no Outcome value |
| `experiment` | predeclared question and one primary change | unique protocol hash; one Target plus code/config/acceptance semantics |
| `experiment_partition` | purpose-specific partition binding | unique Experiment/purpose/Partition; composite Target FK guarantees every member commitment uses the Experiment Target; partition frozen before Outcome access |
| `experiment_run` | one execution of frozen Experiment | unique Experiment/run key; exact bound `experiment_partition` roster/config and status; no positive-result implication |
| `evaluation_protocol` | pre-Outcome evaluation contract | unique code/version/hash; exact Target/purpose plus missingness, inclusion/exclusion and decision semantics frozen |
| `evaluation_protocol_metric` | relational metric/slice/rule declaration | unique protocol/metric/slice; direction, source value type, reducer compatibility, exact Candidate disposition when sliced, estimability and acceptance rule typed |
| `evaluation_run` | predeclared Evaluation execution | requires Experiment Run, one `experiment_partition` from the same Experiment and Evaluation Protocol; forward-only `OPEN → INPUTS_ACQUIRED → COMPLETED` or `FAILED`; purpose typed; no Model FK |
| `research_partition_outcome_access` | append-only Outcome visibility ledger owned by the Evaluation UoW | concrete Evaluation Run + member + exact Outcome revision; globally monotonic per-member access ordinal; ordinal one is first-access Authority; same transaction as observation/reconciliation |
| `evaluation_observation` | exact realized input to Evaluation | exactly one per Evaluation Run/member; binds same-Partition access and exact Market Target Outcome revision; commitment chain implies Dataset/Candidate/Target; unavailable/failed revisions remain present |
| `evaluation_metric` | typed result over declared protocol metric | unique Run/protocol metric/slice; status independent of value; complete input reconciliation |
| `evaluation_metric_observation` | exact member roster for one Evaluation metric/slice | unique Evaluation metric/observation; included/excluded/not-estimable state and reason relational; complete reconciliation to protocol missingness rule |

#### Deferred Research and Qualification

The following relations remain logical target design only and are not present
in the WP-11 baseline. Their dependency order remains frozen by WP-08; none may
be introduced as a placeholder or nullable future branch.

| Table | Purpose | Lifecycle and key constraints |
|---|---|---|
| `evaluation_forecast_binding` | optional Forecast-evaluation branch | concrete Evaluation observation/Forecast FK only when a real Forecast exists; implemented after the Forecast parent, never as a nullable branch placeholder |
| `model` | stable optional fitted-model family | unique code; no Target/Candidate/Outcome/Evaluation existence dependency |
| `model_version` | immutable fitted version lineage | requires completed `MODEL_TRAINING` Evaluation Run and fitted/code/config Artifacts; unique Model/version/hash; completion/known time explicit |
| `evidence_item` | immutable Evaluation evidence or counter-evidence | requires concrete terminal Evaluation Run and Artifact FKs; class/origin/claim direction/time/hash/ceiling plus complete dependency count/hash relational |
| `evidence_dependency` | exact evidence graph edge | unique child/parent/role; temporal non-decrease |
| `research_assessment` | governed Experiment-bound research claim revision | unique Experiment/claim/revision; non-empty Evaluation/Evidence counts and hashes, closed status and typed supersession; negative/inconclusive preserved |
| `research_assessment_evaluation` | complete terminal Evaluation roster for one Assessment | unique Assessment/Evaluation Run/role; every Run belongs to the Assessment Experiment; no current/latest lookup |
| `research_assessment_evidence` | complete concrete Assessment evidence set | unique Assessment/Evidence Item; composite FK requires the item's Evaluation Run in the Assessment roster; typed support/counter-evidence role |
| `research_qualification_policy` | immutable research-purpose floor contract | unique code/version/hash/purpose; decision rules typed |
| `research_qualification_policy_floor` | required/optional floor and acceptance rule | unique policy/floor; typed proof class and evidence requirement |
| `research_qualification_decision` | sole Research admission owner | exact Research Assessment + Policy/revision; typed status/supersession; no generic subject |
| `research_qualification_floor_result` | complete policy proof vector | unique decision/policy floor; every floor present; typed status/reason |
| `research_qualification_floor_evidence` | concrete Assessment Evidence for one floor result | unique floor result/Assessment-Evidence binding/role; the binding belongs to the decision's Assessment; no JSON or weak reference |

### Decision Support

| Table | Purpose | Lifecycle and key constraints |
|---|---|---|
| `decision_run` | frozen Decision-time envelope opened before Context | unique Candidate Set and Runtime Step/request; exact retry returns the sole Run while a changed same-Set request fails; required DecisionTime, Runtime clock mode, PostgreSQL commitment-recorded time, requested Target roster and code/config identities |
| `decision_run_target` | complete non-empty requested Target roster | unique Decision Run/Target and ordinal; Target remains Provider-neutral while this row explicitly selects and hashes the Decision-time reference Provider Product; positive count/hash reconciles even when Candidate Set is empty |
| `decision_target_commitment` | ex-ante Candidate × requested-Target contract | unique Candidate/Decision Run Target; composite Candidate Set/Target chain; every Candidate disposition committed before Outcome visibility |
| `decision_reference_observation` | independent initial-reference fact | unique commitment; value, availability and finality states separate; exactly one Decision-visible Market bar revision or Source Gap shape; `known_at <= DecisionTime` |
| `decision_run_research_qualification_roster` | complete later-generation Research Qualification input envelope | exactly one per Run after this real branch exists; zero-or-more member count/hash and reconciliation state prove an intentional empty roster |
| `decision_run_research_qualification_member` | concrete adopted Research Qualification | unique roster/Qualification/role; matching-purpose `ADMITTED` decision effective/known and non-superseded at DecisionTime; every source Outcome generation strictly earlier |
| `context_assessment` | typed Regime/ETF/Theme/Capital state | unique decision run/kind/scope; state/status/evidence |
| `context_metric` | typed metric supporting Context | unique assessment/metric; value/status/evidence |
| `signal` | setup assertion for one Candidate | unique decision run/candidate/signal kind/version |
| `forecast` | Target/checkpoint-bound forecast envelope | unique Decision Run/commitment/forecast kind; no Model requirement |
| `forecast_estimate` | checkpoint/metric estimate and uncertainty | unique forecast/checkpoint/estimate kind; calibration status |
| `forecast_model_binding` | optional model-backed Forecast branch | unique Forecast and concrete Model Version known by DecisionTime whose training Outcome generations are strictly earlier; absent for rules/heuristics, never nullable placeholder; later Model admission remains subject-specific |
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

### Market Outcome, TradeOutcome and Attribution

| Table | Purpose | Lifecycle and key constraints |
|---|---|---|
| `market_target_outcome` | stable subject for one commitment | unique required Decision Target Commitment; created by factual settlement only, never by Decision opening |
| `market_target_outcome_revision` | append-only full settlement snapshot | unique Outcome/revision ordinal and request hash; observation/knowledge cutoffs, source-roster/hash, aggregate path/availability/finality states; immediate same-Outcome supersession and one leaf only |
| `market_target_outcome_source` | exact relational source roster for one revision | unique revision/role/ordinal; closed role with exactly one concrete Market bar/fact/corporate-action/session/gap/capture FK shape; no `(kind,id)` or manifest lineage |
| `market_target_outcome_observation` | exact path/checkpoint observation | unique revision/Target checkpoint/role; value, availability and finality states separate; event/source times and concrete same-revision Outcome source FK |
| `market_target_outcome_metric` | return/MFE/MAE/barrier metric | unique revision/declared metric/checkpoint; value, availability and finality states separate; typed value/unit and concrete observation dependencies |
| `market_target_outcome_metric_reference` | exact Decision-reference dependency of a metric | unique metric/Target `REFERENCE` dependency; concrete FK to the root's immutable WP-09 `decision_reference_observation`; no recomputation or polymorphic dependency |
| `market_target_outcome_metric_observation` | exact Outcome-observation dependencies of a metric | unique metric/Target dependency; role limited to `OBSERVATION`/`PATH_MEMBER`; both rows belong to the same revision and matching Target checkpoint |
| `market_target_outcome_reason` | typed per-dimension unavailable/partial/failed reason | unique revision/dimension/reason/source; binds exact checkpoint/metric/source where applicable |
| `market_attribution_run` | declared Market Outcome attribution basis | unique Outcome revision/policy; status/total/reconciliation rule |
| `market_attribution_line` | Market dimension contribution | unique run/dimension/member; value/status; sum/remainder rule |
| `trade_outcome` | Fill/Position-derived realized trade revision | stable account/instrument episode key; concrete opening/closing effective Fill roots, typed same-episode supersession, fees/cost/path window; no Decision Target Commitment subject |
| `trade_outcome_fill_binding` | exact effective Fill lineage | unique TradeOutcome/effective Fill revision; complete episode roster and quantity/cost basis reconcile from zero exposure back to zero |
| `trade_outcome_metric` | typed PnL/return/cost/path metric | unique TradeOutcome/metric; value/status/unit and Fill/path evidence constrained |
| `trade_attribution_run` | declared TradeOutcome attribution basis | unique TradeOutcome/policy/revision; status/total/reconciliation rule |
| `trade_attribution_line` | Trade dimension contribution | unique run/dimension/member; concrete Fill Allocation binding where sleeve-scoped; value/status; sum/remainder rule |

### Execution and Account

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
`research_qualification_floor_matrix`. The unique unsuperseded
MarketTargetOutcome revision may also be exposed as a convenience view. A view
has no independent writer or retention contract and never becomes revision
Authority.

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
| Candidate | unique Set/instrument and Set/population-source; non-unique Set/rank and disposition/rank indexes; score-component Candidate and Feature lookups |
| Target commitment | unique Decision Run/Target roster and Candidate/requested-Target commitment plus composite Candidate Set integrity; reference status/due indexes; later concrete Run/Research-Qualification binding lookup |
| Partition roster/access | unique partition/commitment and member/access ordinal; Decision and Outcome-window range indexes; Locked-OOS first-access lookup |
| Evaluation | Run/Partition/protocol lookup; exact access/Outcome-revision observation binding; declared metric/slice and metric-member completeness |
| evidence graph | child/role and parent reverse indexes; no self-edge |
| Research Qualification | Assessment/Policy/revision uniqueness; policy-floor/result/evidence completeness indexes |
| Decision dossier | Decision Run foreign keys plus Candidate/instrument indexes |
| Market Target Outcome settlement | unique commitment and request hash; unsuperseded revision, due checkpoint/metric state, source-roster reverse indexes and metric-observation dependency indexes |
| TradeOutcome | closed Position-episode and effective Fill/allocation lookup; metric-status indexes |
| Fill projection | account/instrument/execution-time sequence; unique external execution/revision; correction-root lookup |
| reconciliation | account/epoch/observation and unresolved-difference partial index |
| artifact integrity | unique content hash; locator, unverified/mismatch and GC-grace partial indexes |

All child FKs have a leading index even when the query matrix does not list them.
Index-only duplicates are rejected during schema validation. Query plans, not
table count, determine later covering indexes.

### Mutability and retention

- Immutable/append-only: captures, Market revisions, Universe revisions/members,
  policies/rules, Candidate Sets, definitions, partitions, Experiments, Model
  Versions, Evidence, Research Assessments/Qualification decisions/results,
  Decision Target Commitments/references, Outcome revisions/children,
  TradeOutcomes, Attribution, Fills/corrections, basis events, observations,
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

Point/session facts use their exact event interval in the logical identity.
Effective-state timelines use the stable `effective_from` root; the current
visible revision owns and may close `effective_to`. Owner queries first select
one current visible revision per root and only then test whether its interval
covers the requested effective time. Each changed source value appends a
monotonically numbered revision with source capture, content hash, temporal
fields, and optional superseded ID. “Current” is an as-of query, not an updated
row. Corrections cannot be visible before their own `decision_visible_at`.

### Missing

No returned observation is not a numeric value. When an observation was expected,
`source_gap` records interval, reason, provider, attempt/capture, and status.
Downstream status becomes `UNKNOWN`/`UNAVAILABLE` according to its own contract;
it is never silently dropped or converted to zero.

### Placeholder

Raw placeholder bytes remain in `data_capture`. A placeholder with absent or
invalid OHLC does not create a valid `market_bar_revision`. It creates or links a
`source_gap` reason such as `NULL_OHLC_PLACEHOLDER`. Downstream selection cannot
use it as a price.

### Suspension

Suspension/trading status is a typed `instrument_fact_revision` backed by source
evidence. Missing bars, zero volume, a flat price, or a provider placeholder do
not alone prove suspension. A suspended session does not imply zero return and a
previous-session close is not a same-session Decision price.

### Session and calendar

Sessions come only from `trading_session`. Current A-share sessions require the
`Asia/Shanghai` timezone. Weekday inference and “next calendar day” are
prohibited. Bar intervals must fall on an allowed session grid,
preserve half-day/break rules, and have unique non-overlapping logical
identities.

## 5. Candidate and Eligibility Decision-time Evidence

`eligibility_assessment` is evaluated for every `universe_member` at one
Decision time:

- status is exactly `ELIGIBLE`, `INELIGIBLE`, or `UNKNOWN`;
- every `eligibility_rule` creates one `eligibility_reason`;
- each reason FK-binds that rule and stores its result, typed observed value,
  typed threshold/operator, reason, and exact queryable Market revision/gap
  lineage;
- every rule executes for every scoped instrument; no short circuit can discard
  diagnostic evidence;
- missing, stale, conflicting, or Decision-invisible Market evidence produces
  `UNKNOWN`, never silent exclusion;
- an explicit rule failure produces `INELIGIBLE`; otherwise any unknown rule
  produces `UNKNOWN`; only all-pass produces `ELIGIBLE`;
- the complete counts reconcile to Universe membership.

Candidate is a separate Selection-owned aggregate from Universe/Eligibility. It
binds one Candidate Policy to one immutable
Decision-input Dataset. That Dataset and its relational sources already prove
the sole Candidate Population:

```text
Dataset rows = UniverseMember(INCLUDED) intersection
               EligibilityAssessment(ELIGIBLE)
```

Candidate neither reloads this population from a broader Universe nor executes
Eligibility, Market hard gates, Context, Target, Outcome, Model, Evidence, or
Qualification logic. Every Dataset row produces exactly one `candidate` row.
Required Feature status `MISSING`, `UNKNOWN`, `STALE`, or `CONFLICT` produces
`UNRANKABLE`, with null score and rank, while retaining every typed score-
component row. It is never imputed and no row silently disappears. Complete
Dataset rows are `SELECTED` or `RANKED_NOT_SELECTED`.

For the common complete rankable cross-section, each required Feature uses an
identity-neutral arithmetic-midrank percentile. Only an `AVAILABLE` Feature
with one distinct value in that cross-section receives the special constant
assignment `0.5` and component status `CONSTANT`; an ordinary nonconstant
middle rank may naturally evaluate to `0.5` while remaining `AVAILABLE`. A
singleton rankable population therefore has
percentile `0.5` for every component, exact composite score `0.5`, and
competition rank `1`. No-rankable-row sets compute no percentile and have
ranking status `NOT_ESTIMABLE`. Mixed constant and distinguishing components
retain their fixed normalized weights and make the Set `AVAILABLE`; all-
constant components make the Set `CONSTANT`. `composite_distinct_count`
separately exposes cancellation into a composite tie.

Declared Decimal weights are normalized with exact rational arithmetic. The
exact component percentiles, normalized weights, contributions, composite
scores, equality classes, competition ranks, and Top-K boundary are computed
before a versioned canonical Decimal/PostgreSQL `numeric` projection. Constant
components contribute their fixed exact normalized weight times `0.5`; weights
are never redistributed. The stored composite is the projection of the exact
composite, not a claim that separately projected contributions add byte-exactly
to it.

Equal exact scores receive equal competition rank. There is no unique Set/rank
constraint and no instrument code, UUID, row order, or other identity tie-break.
Top-K selects every score at or above the K-th score boundary under
`INCLUDE_ALL_BOUNDARY_TIES`; actual selected count may exceed requested Top-K.
Boundary rank/group/overflow/tie diagnostics are immutable and queryable.

Candidate Set reconciliation is complete:

```text
population_count = rankable_count + unrankable_count
rankable_count = selected_count + ranked_not_selected_count
candidate row count = Dataset row count
score_component_count = population_count * policy component count
```

An empty Dataset yields a legal empty Candidate Set with zero Candidates,
ranking status `NOT_ESTIMABLE`, no percentile/boundary, and selected count zero.
Component `observed_count`, `distinct_count`, each raw non-available status count,
and `AVAILABLE`/`CONSTANT`/`NOT_ESTIMABLE` status are deterministically derived
from immutable Set × Policy Component × score rows, including zero-count rows
for an empty Set. Funnel and dossier read models expose both declared and actual
counts and trace source lineage through Candidate Set → Dataset manifest/
`dataset_source`; they are not new Authority.

A score is descriptive ranking output, not a probability, expected return,
MFE/MAE, Forecast, Signal, Entry, or authorization. Signal and Forecast remain
separate downstream facts. Candidate Set existence does not depend on Decision
Run, Target, Outcome, Model/ModelVersion, Evidence, Assessment, Qualification,
or a later-context placeholder.

## 6. Target commitment, Outcome, Partition access, and realized-fact port

A `target_definition` freezes:

- stable code/version/content hash and instrument scope;
- Decision-reference role and exact session/time/grid rule;
- exchange/session resolver, horizon meaning and observation window;
- ordered `target_checkpoint` observation/path grid;
- allowed price basis and corporate-action policy;
- path completeness, required metric/unit, availability and finality rules;
- missing/placeholder/suspension and ambiguous-barrier policy;
- deterministic algorithm plus exact code/config Artifact identities.

A horizon is an evaluation interval, never an automatic holding or exit rule.
All checkpoints, metric definitions, thresholds, roles, units, required
dimensions and observation-dependency shapes are relational children, not JSON
or Artifact-manifest business Authority.

### Ex-ante Decision Target commitment

`OPEN_DECISION_RUN` is a mandatory Runtime Step after
`BUILD_CANDIDATE_SET` and before `ASSESS_CONTEXT`. One transaction writes the
immutable `decision_run`, the complete Candidate × requested Target
`decision_run_target`/`decision_target_commitment` roster, and one
`decision_reference_observation` for every commitment. Reconciled counts and a
roster hash prove the requested Target set even for an empty Candidate Set and
prove that `SELECTED`, `RANKED_NOT_SELECTED`, and `UNRANKABLE` Candidates all
receive the same ex-ante treatment.

Once the real Research Qualification parent exists, the qualified form of this
command also freezes one `decision_run_research_qualification_roster` and its
complete zero-or-more members. The root count/hash proves an intentional empty
roster; every member uses a concrete accepted Qualification decision known by
DecisionTime and proves that all source Outcome Decision generations are
strictly earlier. WP-09 creates neither relation nor a future nullable column;
the later owning work package adds the real parent-dependent relations and
command behavior together.

The commitment logical identity is
`(candidate_id, decision_run_target_id)`. `decision_run_target` has the unique
Decision Run/Target identity; composite FKs also carry Candidate Set so a
Candidate from another Set or a Target outside the requested roster cannot
bind. The reference
observation has independent value, availability and finality states and binds
exactly one concrete Decision-visible `market_bar_revision` or `source_gap`
shape. Its `known_at` cannot exceed DecisionTime. A later Provider correction
never mutates this record of what the Decision used. No future value or Outcome
placeholder is written while opening the Decision Run.

Reference value status is `COMPLETE`, `UNAVAILABLE`, or `FAILED`; availability
is `AVAILABLE`, `UNAVAILABLE`, or `FAILED`; finality is independently `UNKNOWN`,
`PROVISIONAL`, or `FINAL`. State/value/source shape constraints fail closed.

Target Definition owns the rule. `OpenDecisionRun` applies its initial-reference
part through a narrow Market query; Outcome later applies its path/checkpoint/
metric part. Market exposes only generic exact/as-of sessions, bars, facts,
gaps, and lineage; it has no permanent `decision_reference_1455` interface.

Relational creation order proves that no Outcome row predates its commitment,
but does not by itself prove a prospective decision. Decision Run therefore
freezes its inherited Runtime clock mode and PostgreSQL
`commitment_recorded_at`. A `PROSPECTIVE` Partition admits a member only when
the Run used a live clock, the commitment was recorded before that Target's
earliest Outcome-window event, and all Decision inputs still satisfy the
DecisionTime knowledge cutoff. Historical/replay commitments remain valid for
engineering or declared historical Evaluation but can never acquire a
Prospective evidence ceiling.

For the retained T+1 10:30 research target, the Target reference rule requires
one same-session Asia/Shanghai five-minute bar ending exactly 14:55 with
`RAW_UNADJUSTED` basis, finite positive OHLC, legal price structure, verified
source/hash, and non-placeholder/non-suspended status. Zero matches is
`UNAVAILABLE`; conflicting/invalid matches are `FAILED`. Daily bars,
previous-session close, and last-available bars may be diagnostics only and
never supply the value.

### Independent state dimensions

`MarketTargetOutcome` is the sole market-label aggregate. Its subject is exactly
one `decision_target_commitment`; it is not a trade, Forecast, Model,
Evaluation, Qualification, or Strategy result. A stable root is created only
when a due settlement produces a factual complete, partial, unavailable, or
failed result. Each settlement appends a full
`market_target_outcome_revision` snapshot.

Every revision stores these independently:

- immutable `decision_reference_observation.status`;
- aggregate `outcome_window_status`;
- each `market_target_outcome_observation.status`;
- each `market_target_outcome_metric.status`;
- aggregate and per-observation/metric availability/finality;
- each typed `market_target_outcome_reason` failure or gap.

The revision's complete source roster lives in
`market_target_outcome_source`, whose closed roles use exactly-one concrete
Market/PIT FK shapes. Observations bind same-revision source rows. Every metric
binds one `target_metric_definition`.
`market_target_outcome_metric_reference` binds each declared `REFERENCE`
dependency directly to the immutable WP-09 Decision reference, while
`market_target_outcome_metric_observation` binds each declared `OBSERVATION` or
`PATH_MEMBER` dependency to its exact same-revision Outcome observation. Hashes
verify these rows; they never replace them. The split is the WP-10 concrete-FK
normalization of the WP-08 dependency concept and increases the logical catalog
from 117 to 118 relations without making relation count a quota.

Persisted Outcome-window status is `UNAVAILABLE`, `PARTIAL`, `COMPLETE`, or
`FAILED`. `NOT_DUE` is a due-work query result over commitment plus Target and
creates no Outcome row. Checkpoint/metric status is independently typed.
Finality is `UNKNOWN`, `PROVISIONAL`, or `FINAL` and never aliases completeness.
`PARTIAL` is valid for a path or declared partial-path metric, not an exact
point reference. Metric value presence is constrained by its own status;
missing is never zero.

Observation and metric value status is `COMPLETE`, `PARTIAL`, `UNAVAILABLE`, or
`FAILED` where its Target shape permits partiality. Availability is separately
`AVAILABLE`, `UNAVAILABLE`, or `FAILED`; reasons bind the exact dimension they
explain.

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

`market_target_outcome_metric` stores typed metric kind, status, numeric value,
unit, exact observation dependencies and calculation identity. Value must be
null for `UNAVAILABLE`/`FAILED`. Every observation keeps a same-revision Outcome
source FK whose closed shape reaches an exact Market revision or Source Gap. No
Outcome row rewrites a Decision, Forecast, Target Definition, Dataset,
Candidate, or Feature cell.

### Incremental settlement, correction, and replay

The unique settlement request hash covers commitment, `observation_cutoff`,
`knowledge_cutoff`, exact Market/PIT source revision roster, calendar,
algorithm, and code/config identities. Exact retry returns the original
revision. `PARTIAL → COMPLETE`, Provider correction, changed finality, or repaired
coverage appends a new full snapshot whose `supersedes_revision_id` references a
revision of the same root and immediately preceding ordinal. Unique root/ordinal,
root/request-hash and non-null superseded-revision keys plus root/leaf locking
permit one linear leaf only; every old revision and child fact remains
immutable.

An Evaluation observation keeps its exact revision FK. A correction may trigger
a new Evaluation/Assessment/Qualification revision but never edits or silently
promotes a result that consumed the older Outcome.

`observation_cutoff` is the latest event time admitted to the Outcome window.
`knowledge_cutoff` is the latest source `known_at` admitted to that settlement
or replay. Queries enforce both. The original DecisionTime applies only to the
already-frozen Decision reference. Settlement or retrieval time is never stored
as DecisionTime and never invents retrospective source availability.

Replay reloads the exact Target, commitment, reference, calendar, cutoffs,
Market/PIT revisions/gaps, algorithm, and code/config identities. It cannot call
a replacement Provider or query current/latest facts. Success requires
`matched=true` with zero identity, state, value, source, hash, or reason
mismatches.

### Research Partition and first Outcome access

`FreezeResearchPartition` writes an immutable root and its complete non-empty
`research_partition_member` commitment roster atomically, before reading any
Outcome. The root freezes one Target Definition, purpose (`DISCOVERY`, `FIT`, `VALIDATION`,
`LOCKED_OOS`, or `PROSPECTIVE`), Decision and Outcome-window bounds, exact
calendar, purge-before/purge-after, embargo end, roster count/hash, and
code/config Artifacts. Range/exclusion constraints and application
reconciliation prevent prohibited overlap or leakage after expanding Outcome,
purge, and embargo windows.

`research_partition_outcome_access` appends every exact Outcome revision exposed
to an Evaluation Run. Access ordinal is monotonic per member; ordinal one is the
Authority for first access. Locked-OOS status therefore comes from an immutable
pre-access roster plus Experiment binding created while the access count is
zero. A reused already-accessed Partition may support diagnostics but cannot
regain Locked-OOS/Prospective status. This proof never comes from a mutable
boolean or Artifact manifest.

The ledger proves system access order, not that a human lacked external
knowledge of an already-realized period. Formal OOS still requires its separate
operator/process evidence floor.

### Narrow read-only Outcome port

Research, Model, Evaluation, Calibration, Forecast evaluation, Shadow economics,
and Qualification consume realized market facts only through the Outcome
Application query port. Its DTO contains commitment/reference identity, exact
revision, observation/metric/reason states and values, source revision IDs,
cutoffs, availability, finality, and hashes. It exposes no bar, Provider,
repository, SQL, label-builder, or mutation interface. Research records
Partition access and Evaluation observations in the same short transaction that
resolves the exact revisions; no DTO leaves the handler before that commit.
Outcome rows remain read-only, exact retry returns the same access IDs, and pure
calculation later binds metrics to those committed observations. Research cannot
recalculate or persist a second label truth.

Input acquisition is complete over the Partition roster: every member receives
one exact Outcome revision, including a revision whose factual result is
`UNAVAILABLE` or `FAILED`. `NOT_DUE`, an absent due settlement, ambiguity, or a
missing member fails acquisition; it cannot become an omitted sample. A
terminal Evaluation therefore reconciles its observation count to the positive
Partition member count before any metric may finalize.

Evaluation Run lifecycle is one-way: `OPEN` freezes Experiment/Partition/
Protocol before access; `INPUTS_ACQUIRED` means the complete access and
observation rosters committed; `COMPLETED` means every declared metric/slice and
its full observation roster committed; `FAILED` is terminal from either prior
state. There is no reopen or input replacement. `NOT_ESTIMABLE` is a typed
metric result inside a valid completed Run, never a way to omit an input.

## 7. Evidence, Assessment, and Qualification semantics

Evaluation composes the label-free Dataset/Candidate/Target chain with a frozen
Partition and exact Outcome revisions; it never writes posterior values back to
Dataset, DatasetSource, Candidate, or Feature facts. Every Evaluation Run
requires an Experiment Run, one bound Research Partition, and one predeclared
Evaluation Protocol. It does not require a Model. A Model Version can exist only
after a completed `MODEL_TRAINING` Evaluation Run; model-backed Forecast is a
concrete optional child branch, not a nullable Model placeholder.

Evidence, Assessment, and Research Qualification are three separate axes with
concrete FK chains.

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

`research_assessment.status` is exactly:

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

`PRODUCTION` is reserved for a later subject-specific admission owner.
`research_qualification_decision` cannot grant Product, Provider, Model,
Strategy, Execution, broker, or Production admission; it owns only its declared
Research purpose.

`research_qualification_decision.status` is terminal and exactly `ADMITTED`,
`REJECTED`, `BLOCKED`, `NOT_ESTIMABLE`, `INCONCLUSIVE`, or `FAILED`.
`ADMITTED` requires every required Policy floor satisfied (or explicitly
not-applicable only where the Policy allows it). Correction or changed evidence
creates a typed superseding decision; it never mutates the old status or an old
Decision Run binding.

A `research_qualification_decision` declares one concrete Research Assessment,
one Research Qualification Policy, requested proof class, status, evidence
cutoff, and typed supersession. The Assessment binds one Experiment and a
complete non-empty roster of its terminal Evaluation Runs, so a decision may
combine declared Validation, Locked-OOS, Calibration, or Prospective results
without a cross-Experiment or current/latest lookup. It has one row for every
policy floor:

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

Each result FK-binds one required `research_qualification_policy_floor`; every
supporting row FK-binds a concrete `evidence_item`. Floor status is `SATISFIED`,
`MISSING`, `REJECTED`, `BLOCKED`, or `NOT_APPLICABLE`. Overall qualification
cannot exceed its weakest required floor. `PIT_INCOMPLETE` is represented
explicitly as `TEMPORAL_PIT = MISSING/REJECTED` under an Exploratory assessment;
it is never flattened into “evidence exists.” A Prospective capture can still be
PIT-incomplete for historical claims. Production is never inferred from a lower
class or from successful Runtime execution.

Every `evidence_item` requires one Evaluation Run and one immutable Artifact;
class, origin, claim direction, observation time, hash and proof ceiling are
relational. `RecordEvidence` freezes the item and its complete dependency
count/hash/edge roster together; `evidence_dependency` links only concrete
Evidence Items and is a validated DAG. `AssessResearch` freezes the Assessment
with its complete Evaluation and Evidence rosters;
`research_assessment_evaluation` freezes the complete terminal
Run roster; `research_assessment_evidence` freezes the complete Evidence set
and requires every item's Run in that roster. Floor-evidence rows bind the
concrete subset used for each decision floor. `DecideResearchQualification`
writes its terminal decision, every Policy floor result, and the complete
floor-evidence vector atomically.
There is no `(kind, id)`, JSON business Authority, weak reference, or future
nullable subject column. Future Provider, Model, Strategy, Execution, and
Production qualification require separate subject-specific relations in their
own work packages.

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

When deterministic validation fails, the business transaction is fully rolled
back. A new short owner UoW then locks the live Runtime claim before atomically
writing the failed receipt, failure audit, and Attempt/Step failure. Stale fences
produce no failure receipt or audit. This transaction contains no Artifact byte
I/O and no business write from the rolled-back attempt.

### Read verification

Every authoritative artifact read requires verified hash, size, existence, and
integrity. Consumers declare any additional freshness rule at their own narrow
read seam. Market's current consumer read policy is 24 hours: Market relational
queries reject stale or non-AVAILABLE capture evidence. That cadence is not a
permanent Foundation meaning for every future Artifact. An explicit
`VerifyArtifact` performs physical
hash/size I/O outside the PostgreSQL transaction, then appends verification and
refreshes integrity metadata in one short transaction. An exact command retry
uses the caller's idempotency key and returns the committed observation; a new
physical observation requires a new key. Missing/mismatch records an
append-only `artifact_verification` failure and blocks the consumer. It is not
silently re-downloaded from another Provider or repaired with different bytes.
Exact bytes may be re-published only under the same hash.

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
