# Daily Quant Decision Artifact Specification V1

> **Schema:** `daily-quant-decision-artifact-v1`  
> **Work package:** `WP-DQS-1`  
> **Status:** approved implementation specification  
> **Authority ceiling:** `AUXILIARY_NOT_FORMAL_OOS`  
> **Decision owner:** human; no order or broker authority

## 1. Purpose and boundary

V1 freezes the information state and transparent outputs needed to reconstruct one daily research
decision. It defines three implemented objects:

```text
DailyResearchSnapshot
        ↓
CandidateRecommendation
        ↓
EntryAssessment
```

It also reserves the future semantics of `ManualTradeRecord`, `RecommendationOutcome`, and
`DailyReviewReport` without implementing them in WP-DQS-1.

The boundary preserves:

```text
Candidate Recommendation answers “what is ranked?”
Entry Assessment answers “is now suitable for initiation?”
Manual execution later records “what did the user actually do?”
Review later answers “what happened and why?”
```

No field in this Artifact is an order, fill, Portfolio Decision, Formal OOS result, or trading
authority.

## 2. Schema and exact file set

One Artifact directory contains exactly:

```text
manifest.json
daily_research_snapshot.json
candidate_recommendations.json
entry_assessments.json
report.md
SHA256SUMS.json
```

The directory name equals a content-derived `artifact_id` that binds the `snapshot_id`, snapshot
content hash, complete serialized snapshot record (including creation provenance), every
Recommendation and Entry Assessment identity, Authority, and the exact
implementation identity. `snapshot_id` remains the identity of the information state rather than
being overloaded as the package identity. Publication uses an owned staging directory and one
rename. Existing final or staging paths fail closed; files are never overwritten.

`SHA256SUMS.json` covers every other file. `manifest.json` binds the Schema, package and snapshot identities,
Authority, implementation identity, exact file set, and record counts.

## 3. Authority

V1 permits only:

```text
EXPLORATORY
AUXILIARY
TEST_ONLY_NOT_RESEARCH_EVIDENCE
```

`EXPLORATORY` and `AUXILIARY` inputs produce `NOT_FORMAL_OOS` evidence. They are not a workaround for
the blocked qualified Xuntou route. Test-only evidence retains
`TEST_ONLY_NOT_RESEARCH_EVIDENCE` as both its data and evidence classification and receives a
separate identity prefix; it never becomes research evidence.

## 4. Common identity rules

- JSON is canonicalized with sorted keys, UTF-8, no NaN/Infinity, and deterministic collection order.
- Hashes use lowercase SHA-256 with a `sha256:` prefix.
- Domain IDs derive from the canonical semantic payload, never from `created_at`, output path, or
  caller-supplied random values.
- `created_at` is operational provenance and must be timezone-aware and no earlier than Decision Time.
- Snapshot semantic identity excludes `created_at`; rerunning identical evidence produces the same
  `snapshot_id`. The package `artifact_id` separately binds the complete serialized snapshot record,
  so different creation provenance cannot reuse the same package identity.
- Every source evidence item has an exact content hash, `observed_at`, and `available_at`.
- `observed_at <= decision_time` and `available_at <= decision_time` are mandatory. Retrieval time is
  not a substitute for availability.

## 5. `DailyResearchSnapshot`

Required fields:

```text
schema_version
snapshot_id
decision_date
decision_time
timezone
universe_identity
market_data_identity
feature_registry_identity
registered_component_identities
model_identity
configuration_identity
market_context_identity
etf_snapshot_identity
theme_snapshot_identity
holdings_identity
source_artifacts
data_authority
created_at
content_hash
```

V1 rules:

- `decision_date` equals the Asia/Shanghai local date of `decision_time`.
- `timezone` is exactly `Asia/Shanghai`; the timestamp must have the corresponding UTC offset.
- Every `*_identity` is a non-empty stable identity. An unavailable optional upstream domain is
  represented by an explicit unavailable identity such as a versioned `...-unavailable-v1`, not an
  empty string or omitted field.
- `source_artifacts` is a non-empty, sorted tuple of `DecisionSourceArtifact` records:

```text
artifact_id
provider_id
content_hash
observed_at
available_at
data_authority
```

- Duplicate source artifact IDs are invalid.
- `registered_component_identities` is a non-empty, sorted, unique projection of the Feature
  Registry for components permitted in this Snapshot; each projected identity also has its own
  source Artifact lineage.
- Every Universe, market-data, Feature Registry, registered component, Candidate model,
  configuration, Market Context, ETF, Theme, holdings, Candidate Target, Entry model, and Entry
  configuration identity must equal one `source_artifacts[].artifact_id`. This closes temporal
  lineage for derived and explicitly unavailable upstream states; an unrelated timely source cannot
  authorize an unlinked identity.
- `content_hash` hashes the snapshot payload excluding `snapshot_id`, `content_hash`, and
  `created_at`; `snapshot_id` derives from that hash.

## 6. `CandidateRecommendation`

Required fields:

```text
schema_version
recommendation_id
decision_snapshot_id
instrument_type
symbol
candidate_rank
candidate_score
score_components
industry
themes
related_etfs
selection_reasons
risk_reasons
expected_horizon
target_definition
invalidation_conditions
data_quality
model_identity
data_authority
content_hash
```

Rules:

- V1 instrument types are `A_SHARE_STOCK` and `ETF`; they are never ranked together by this Artifact.
- Rank is positive. Within an instrument type, ranks are unique, contiguous from one, and must equal
  descending `candidate_score` order with symbol as the deterministic tie breaker.
- Candidate score and component values are finite model/rank scores, never probabilities.
- `score_components` is a sorted, non-empty tuple of identified finite contributions. Component
  identities are unique and each references a registered Feature, factor, model output, or
  explicitly versioned constant through the Snapshot's frozen `registered_component_identities`
  projection. Their contributions must sum to `candidate_score`.
- `selection_reasons` and `invalidation_conditions` are non-empty structured reason-code tuples.
- `themes` and `related_etfs` are sorted and unique; missing mapping is explicit in `data_quality` or
  risk reasons, never silently interpreted as no theme.
- CandidateRecommendation contains no Entry state, Holding action, suggested quantity, or order.
- `recommendation_id` and `content_hash` derive from every semantic field except those two identity
  fields.

## 7. `EntryAssessment`

Required fields:

```text
schema_version
entry_assessment_id
decision_snapshot_id
recommendation_id
entry_state
entry_score
entry_reasons
blocking_reasons
reference_price
preferred_price_zone
maximum_acceptable_price
invalidation_price
expected_mfe
expected_mae
risk_reward_estimate
uncertainty
model_identity
configuration_identity
data_authority
content_hash
```

`entry_state` is exactly one of:

```text
ENTER
WAIT_PULLBACK
WAIT_CONFIRMATION
REJECT
```

Rules:

- Entry Assessment references one existing recommendation from the same snapshot.
- `entry_score` is a finite decision score, not a probability.
- Positive prices are required when present. A preferred zone is `(lower, upper)` with
  `lower <= upper`; maximum acceptable and invalidation prices remain separate meanings.
- Expected MFE, expected MAE, risk/reward, and uncertainty are estimates. Missing estimates remain
  `null`; no neutral or zero default is introduced.
- `ENTER` requires no blocking reasons, a positive reference price, a preferred price zone, maximum
  acceptable price, invalidation price, and at least one Entry reason.
- For `ENTER`, reference price is inside the preferred zone and no higher than maximum acceptable
  price; maximum acceptable price covers the full preferred zone; invalidation is below reference.
- `REJECT` requires at least one blocking reason.
- A Recommendation with `data_quality=INSUFFICIENT` can only receive `REJECT`.
- Entry fields cannot change Candidate rank, score, components, reasons, target, or model identity.
- `entry_assessment_id` and `content_hash` derive from every semantic field except those two identity
  fields.

## 8. Future reserved contracts

### `ManualTradeRecord`

An append-only human execution observation will contain recommendation identity, action, trade date
and time, actual price and quantity, fees, human reason, plan-followed state, deviation reason,
creation time, Authority, and content hash. It will never mutate the recommendation or represent a
broker-confirmed fill unless a separate broker evidence contract exists.

### `RecommendationOutcome`

An outcome will reference the exact recommendation and Target identities, preserve observed and
available times, distinguish missing/unavailable/ambiguous evidence, and store next-session and
multi-session observations without changing the original decision Artifact.

### `DailyReviewReport`

A review will consume only verified original decision Artifacts plus identified outcome/manual
records. It will separate Candidate, Entry, lifecycle/Exit, context, data, and human-execution
attribution and allow multiple failure labels.

## 9. Publisher contract

The Publisher:

1. validates the snapshot and all records before filesystem mutation;
2. requires every recommendation and Entry Assessment to reference the root snapshot;
3. sorts records deterministically;
4. enforces one Entry Assessment per recommendation in V1;
5. derives the exact package `artifact_id` rather than accepting a caller-selected run ID;
6. writes the exact staged file set, hashes it, and atomically renames it;
7. refuses existing final or staging paths;
8. emits a deterministic Markdown report that contains Authority, identities, Candidate evidence,
   Entry evidence, risks, and invalidation conditions;
9. creates no broker, order, position, Target outcome, or Alpha result.

## 10. Semantic Reader contract

The Reader does more than verify checksums. It must:

- require the exact file set and checksum coverage;
- validate exact manifest fields and implementation module set;
- recompute current implementation hashes;
- parse every record with exact field sets and enum values;
- recompute all content hashes and IDs;
- recheck source availability against Decision Time;
- recheck reference integrity, ordering, rank uniqueness/contiguity, and Authority consistency;
- re-render `report.md` and compare exact bytes;
- return immutable domain objects and read-only manifest data.

A checksum-valid Artifact with changed Candidate values, Entry state, report content, source times,
identity fields, record ordering, extra files, or missing files must fail verification.

## 11. Implementation identity

The code-owned module set is exact:

```text
_contract_support.py
contracts.py
snapshot.py
recommendation.py
entry.py
policy.py
report.py
artifacts.py
reader.py
```

Registry, CLI, documentation, tests, and future model implementations are excluded. Changing an
unrelated Router or future Reader must not invalidate a historical daily Artifact.

## 12. Temporal and Authority acceptance tests

V1 tests must prove:

- future-observed or future-available source evidence is rejected;
- naive timestamps and wrong Decision Date/timezone are rejected;
- recommendation and Entry objects are frozen;
- publishing identical semantic content is deterministic and non-overwriting;
- modifying a recommendation or Entry Assessment and rewriting file checksums still fails semantic
  identity verification;
- arbitrary contiguous but wrong ranks fail Reader reconstruction rules;
- Entry references cannot cross snapshots or refer to missing recommendations;
- Candidate Target, score-component, Entry model, and Entry configuration identities cannot bypass
  the Snapshot's source/registry lineage;
- no missing Candidate is replaced by a lower-ranked fallback;
- test fixtures retain `TEST_ONLY_NOT_RESEARCH_EVIDENCE` and never receive `NOT_FORMAL_OOS` research
  evidence classification;
- the report is reconstructible from verified structured evidence.

## 13. Explicit non-goals

V1 does not implement stock/ETF Universe production, ETF/Theme strength, Candidate model changes,
Entry model logic, ManualTradeRecord persistence, Position State, Holding/Exit, outcomes, review,
Dashboard, scheduling, automated orders, broker integration, Portfolio construction, or Formal OOS
validation.
