# ADR — Daily Research Contract Convergence

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Architecture decision for historical daily V1 compatibility and canonical Phase D ownership
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-08
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../05-Phase-D-Daily-Decision-Engine-V1.md, ../../specs/DailyResearchSnapshot.md, ../../specs/CandidateRecommendation.md, ../../specs/EntryAssessment.md, ../../status/Capability-Matrix.md
> **Code Evidence:** source branch@169f620d3b8bc62a0f746898f398cc1d289e0d02; reconciled main baseline@bd3f9753fbf1431f6b8d53e121c6ac252b224cbc; path:src/market_regime_alpha/daily_research; path:tests/daily_research/test_v1_characterization.py

## Decision

The implemented `market_regime_alpha.daily_research` V1 package is a frozen
compatibility layer with implementation status `IMPLEMENTED_NON_CANONICAL`.
It is not the implementation of the current Phase D DailyResearchSnapshot,
CandidateRecommendation or EntryAssessment specifications.

The current Phase D specifications remain the only canonical target authority.
There will not be two current Daily authorities.

V1 remains readable and verifiable. Its schema versions, JSON field sets,
enums, identity algorithms, Reader behavior, implementation-module set and
module bytes are frozen by characterization tests. Historical V1 Artifacts
remain immutable.

## Current implementation note

WP-D0 and later platform, lifecycle and PostgreSQL work packages have advanced
since this decision was written. Their current implementation status is owned
by `docs/status/Current-State.md` and `docs/status/Capability-Matrix.md`; the
sequencing statements below are retained as decision chronology. The active
decision carried forward by this ADR is the frozen, non-canonical V1 boundary
and its fail-closed migration rules. It does not lower or replace any newer
authority boundary.

## Context

V1 was implemented from a historical specification before the current Phase D
contracts were established. The two generations reuse names while differing in
identity, lineage, evidence, data-quality, disposition, expiry, supersession,
PredictionRun and Position semantics.

Renaming V1 fields or classes would conceal those differences. Modifying a V1
module would also change the module hashes recorded in V1 manifests and could
make a historical Artifact fail semantic verification.

## Authority dimensions

The converged platform keeps three independent dimensions:

```text
DataEligibility
EvidenceLevel
ModelLifecycleStatus
```

`UNQUALIFIED` belongs to `DataEligibility`; it is not an EvidenceLevel.
WP-D0 will establish the Constitution-compatible EvidenceLevel ladder:

```text
E0_IDEA
E1_EXPLORATORY
E2_REPRODUCIBLE
E3_CONTROLLED_VALIDATION
E4_OOS_VALIDATED
E5_SEALED_TESTED
E6_PROMOTION_CANDIDATE
```

New model registration will start at:

```text
ModelLifecycleStatus.DRAFT
EvidenceLevel.E0_IDEA
```

Input qualification will be expressed only through:

```text
ModelDefinition.supported_data_eligibilities
PredictionRun.input_data_eligibility
```

This ADR does not implement those WP-D0 contracts.

## V1 freeze boundary

The frozen implementation modules are:

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

Their exact hashes at the audited baseline are asserted by
`tests/daily_research/test_v1_characterization.py`.

Future compatibility work must be placed outside these modules. A necessary
V1 defect correction requires a new explicit V1 schema/Reader version and a
supersession decision; it cannot overwrite the frozen files or historical
Artifacts.

## Canonical V2 boundary

Canonical V2 will own:

- identified calendar, SourceManifest, UniverseSnapshot and
  EligibilitySnapshot inputs;
- explicit context and FeatureMatrix identities;
- complete, protocol-bound PredictionRuns;
- independent Candidate Recommendation and Entry Assessment projections;
- DataEligibility, Data Quality, EvidenceLevel and disposition as separate
  fields;
- expiry, supersession and calibration identities where applicable;
- actual-position references only from Manual/Broker evidence.

Canonical V2 contracts and a production Adapter are not implemented in this
PR. Their implementation waits until WP-D0 has stabilized Model, Experiment,
EvidenceLevel and PredictionRun identities.

## Adapter protocol boundary

A future Adapter must be a separate module and must conceptually expose a
read-only assessment before conversion:

```text
assess_v1_snapshot(source_identity, v1_snapshot, migration_context)
assess_v1_recommendation(source_identity, v1_recommendation, migration_context)
assess_v1_entry(source_identity, v1_entry, migration_context)
```

The assessment result must contain:

```text
source_v1_identity
source_v1_schema_version
adapter_protocol_version
migration_rule_ids
migration_rule_versions
original_values
compatible_fields
information_loss_fields
blocked_fields
result
```

Allowed results are:

```text
MIGRATION_COMPATIBLE
MIGRATION_COMPATIBLE_WITH_INFORMATION_LOSS
MIGRATION_BLOCKED_MISSING_REQUIRED_IDENTITY
MIGRATION_BLOCKED_UNQUALIFIED_PIT_MAPPING
MIGRATION_BLOCKED_AMBIGUOUS_LEGACY_SEMANTICS
MIGRATION_BLOCKED_UNSTABLE_CANONICAL_DEPENDENCY
```

Conversion is allowed only after assessment proves that every required V2
field is supplied by identified external evidence or an unambiguous frozen
rule. The Adapter creates a new V2 identity and preserves the source V1
identity. It never reuses a V1 ID as a V2 ID.

## Legacy EvidenceLevel migration

Historical `EvidenceLevel.UNQUALIFIED` is ambiguous and must never be mapped in
bulk.

| Proven historical meaning | Migration |
|---|---|
| model has no qualifying research evidence | `EvidenceLevel.E0_IDEA` |
| input data is not qualified for research claims | `DataEligibility.UNQUALIFIED` |
| provenance cannot distinguish the meanings | `MIGRATION_BLOCKED_AMBIGUOUS_LEGACY_SEMANTICS` |

Every migration attempt, including a blocked or ambiguous result, must retain:

```text
original_value
source_identity
migration_rule_id
migration_rule_version
result_dimension
migrated_value
migration_result
```

`migrated_value` is null for a blocked result. The original value and rule
provenance remain mandatory.

## Field-level migration matrix

### DailyResearchSnapshot

| V1 field | V2 field | semantic relation | compatible | requires adapter | information loss | migration rule |
|---|---|---|---|---|---|---|
| `snapshot_id` | `snapshot_id` | different identity algorithms and payloads | no | yes | no | create a new V2 ID; retain `source_v1_snapshot_id` |
| `schema_version` | `schema_version` | distinct schema generations | no | yes | no | never rewrite V1 version |
| `decision_date` | `decision_date` | same market-date concept | yes | yes | no | copy after calendar validation |
| `decision_time` | `decision_time` | same cutoff concept | conditional | yes | no | require canonical calendar/session agreement |
| `timezone` | `timezone` | both require Asia/Shanghai | yes | yes | no | exact enum mapping |
| `universe_identity` | `universe_snapshot_id` | generic V1 identity versus PIT snapshot | no | yes | yes | require an identified PIT UniverseSnapshot or block |
| `market_data_identity` | `source_manifest_id` | dataset identity is not a SourceManifest | no | yes | yes | require a compatibility SourceManifest or block |
| `source_artifacts` | `source_manifest_id` | partial provider lineage | conditional | yes | yes | preserve rows as sources; do not claim completeness |
| none | `calendar_artifact_id` | required V2 identity absent | no | yes | yes | external identified evidence required |
| none | `market_session_id` | required V2 identity absent | no | yes | yes | external identified evidence required |
| none | `eligibility_snapshot_id` | required V2 identity absent | no | yes | yes | external identified evidence required |
| `feature_registry_identity` | `feature_matrix_id` | registry is not materialization | no | yes | yes | identified FeatureMatrix required |
| `registered_component_identities` | component lineage | definitions/components only | conditional | yes | no | preserve as source lineage, not FeatureMatrix |
| `model_identity` | `candidate_prediction_run_ids` | model ID is not a complete run | no | yes | yes | canonical PredictionRun required |
| `configuration_identity` | PredictionRun/Experiment lineage | partial configuration reference | conditional | yes | yes | preserve as source; require canonical protocol identities |
| context identities | `context_refs` | similar references with different unavailable semantics | conditional | yes | yes | require typed context identities; sentinels do not become null silently |
| `holdings_identity` | `position_snapshot_id` | V1 does not prove fill-derived Position authority | no | yes | yes | actual-position evidence required or null only when V2 permits |
| none | `entry_assessment_run_ids` | required V2 run references absent | no | yes | yes | canonical Entry run identities required when Entry is in scope; otherwise use the V2-permitted empty collection |
| none | `experiment_protocol_ids` | absent | no | yes | yes | identified frozen protocols required |
| `data_authority` | referenced `PredictionRun.input_data_eligibility` | V1 authority is not canonical run input qualification | no | yes | yes | do not add eligibility to the Snapshot; require provenance-backed PredictionRun qualification or block |
| none | `evidence_level` | absent | no | yes | yes | registry/evidence record required |
| none | `data_quality_grade` | absent | no | yes | yes | canonical quality report required |
| none | `disposition` | absent | no | yes | yes | derive only from a canonical run result |
| none | `supersedes` | absent | no | yes | yes | null for first V2 projection; never invent V1 revision history |
| `created_at` | `created_at` | persistence time | yes | yes | no | copy as source metadata; exclude from market availability |
| `content_hash` | `content_hash` | different identity payloads | no | yes | no | preserve V1 hash and compute a new V2 hash |

### CandidateRecommendation

| V1 field | V2 field | semantic relation | compatible | requires adapter | information loss | migration rule |
|---|---|---|---|---|---|---|
| `recommendation_id` | `recommendation_id` | different identity payloads | no | yes | no | new V2 ID with V1 source reference |
| `schema_version` | `schema_version` | distinct schema generations | no | yes | no | preserve V1 version and emit a new V2 version |
| `decision_snapshot_id` | `snapshot_id` | depends on successful snapshot migration | conditional | yes | no | require mapped V2 snapshot |
| none | `prediction_run_id` | required authoritative ledger absent | no | yes | yes | canonical PredictionRun required |
| `instrument_type` | `instrument_type` | `A_SHARE_STOCK` versus `STOCK` vocabulary | yes | yes | no | explicit enum map |
| `symbol` | `symbol` | same instrument key if registry agrees | conditional | yes | no | canonical instrument validation |
| `candidate_rank` | `rank` | same ranking concept | conditional | yes | no | verify against complete PredictionRun |
| `candidate_score` | `score` | finite model score | conditional | yes | no | verify against PredictionRun |
| none | `score_type` | V1 score is explicitly not a probability | yes | yes | no | map only to `RAW_SCORE` |
| none | `calibration_id` | no V1 calibration | yes | yes | no | null; calibrated probability is forbidden |
| `score_components` | `score_components` | identified component contributions | conditional | yes | no | preserve component identities and sum invariant |
| reason strings | reason codes | strings are not necessarily registered codes | conditional | yes | yes | registry validation required or block |
| `industry` | `industry_id` | label does not prove PIT mapping | no | yes | yes | qualified PIT mapping required |
| `themes` | `theme_ids` | labels do not prove PIT mapping | no | yes | yes | qualified PIT mapping required |
| `related_etfs` | `related_etf_ids` | symbols do not prove PIT relation | no | yes | yes | qualified PIT mapping required |
| `expected_horizon` | `expected_horizon` | similar text versus registered horizon | conditional | yes | no | registered identity/rule required |
| `target_definition` | `target_id` | similar identity | conditional | yes | no | verify in canonical Target authority |
| `model_identity` | `model_id` | similar identity | conditional | yes | no | verify in hardened Registry |
| none | `model_version` | absent | no | yes | yes | registry lookup required; never infer from ID |
| `data_quality` | `data_quality_grade` | non-isomorphic enums | no | yes | yes | canonical quality evidence required |
| `data_authority` | referenced `PredictionRun.input_data_eligibility`; separate `evidence_level` | one V1 field cannot populate either canonical run qualification or model evidence | no | yes | yes | do not add eligibility to Recommendation; require dimension-specific provenance or block |
| none | `disposition` | absent | no | yes | yes | canonical projection policy required |
| none | `expires_at` | absent | no | yes | yes | explicit policy/protocol required |
| `invalidation_conditions` | source extension | no direct current field | no | yes | yes | preserve in source extension; do not discard silently |
| `content_hash` | `content_hash` | different identity payloads | no | yes | no | preserve old hash and compute new hash |

### EntryAssessment

| V1 field | V2 field | semantic relation | compatible | requires adapter | information loss | migration rule |
|---|---|---|---|---|---|---|
| `entry_assessment_id` | `assessment_id` | different identity payloads | no | yes | no | create V2 ID and retain V1 source |
| `schema_version` | `schema_version` | distinct schema generations | no | yes | no | preserve V1 version and emit a new V2 version |
| `decision_snapshot_id` | `snapshot_id` | depends on snapshot migration | conditional | yes | no | require mapped V2 snapshot |
| `recommendation_id` | `candidate_recommendation_id` | depends on recommendation migration | conditional | yes | no | require mapped V2 recommendation |
| `entry_state` | Entry assessment disposition | assessment outcome, not Strategy Action | conditional | yes | no | explicit enum map; WAIT/REJECT never become strategy actions |
| none | `NO_ACTION` disposition | absent in V1 | no | yes | yes | never infer |
| `preferred_price_zone` | `entry_zone` | float bounds lack currency/decimal policy | conditional | yes | yes | identified CNY precision policy required |
| `maximum_acceptable_price` | same | similar price limit | conditional | yes | yes | decimal/currency conversion policy required |
| `invalidation_price` | `invalidation_condition` | price is not a registered rule object | no | yes | yes | create only from an explicit registered rule |
| `invalidation_price` | `reference_stop` | same numeric boundary only under an identified price basis | conditional | yes | yes | map only with explicit currency, price basis and decimal policy; otherwise block |
| `entry_score` | source extension | no V2 field | no | yes | yes | preserve; never call it probability |
| `reference_price` | source extension | no V2 field | no | yes | yes | preserve with price basis if known |
| `expected_mfe` | `expected_mfe` | similar estimate | conditional | yes | no | require identified model/distribution |
| `expected_mae` | `expected_mae` | similar estimate | conditional | yes | no | require sign/unit convention match |
| `risk_reward_estimate` | `risk_reward` | similar derived estimate | conditional | yes | no | require declared derivation |
| `uncertainty` | source extension | no V2 field | no | yes | yes | preserve with definition if known |
| reason strings | reason codes | strings may not be registered | conditional | yes | yes | registry validation required |
| `model_identity` | `model_id` | similar identity | conditional | yes | no | verify as Entry model |
| `configuration_identity` | source extension/protocol ref | no direct V2 field | no | yes | yes | preserve; require canonical protocol separately |
| none | `model_version` | absent | no | yes | yes | registry lookup required |
| none | `data_quality_grade` | absent | no | yes | yes | canonical quality evidence required |
| `data_authority` | upstream PredictionRun input qualification; separate `evidence_level` | one V1 field cannot populate either dimension | no | yes | yes | do not add eligibility to EntryAssessment; require dimension-specific provenance or block |
| none | `expires_at` | absent | no | yes | yes | explicit policy/protocol required |
| `content_hash` | `content_hash` | different identity payloads | no | yes | no | preserve old hash and compute new hash |

## Consequences

Positive:

- historical V1 Artifacts remain verifiable;
- the current Phase D contracts retain a single authority;
- missing semantics are visible and fail closed;
- WP-D0 can establish one EvidenceLevel and PredictionRun authority before a
  production Adapter depends on them.

Costs:

- most historical V1 packages cannot be converted without external canonical
  lineage;
- V1 fields with useful but non-canonical information require source
  extensions or explicit information-loss records;
- a complete production Adapter is deferred.

## Deferred work

After WP-D0:

1. update current Phase D schemas to the stabilized EvidenceLevel vocabulary;
2. resolve `created_at`/`supersedes` schema consistency for
   CandidateRecommendation and EntryAssessment;
3. implement V2 contracts in a new canonical module;
4. implement the Adapter Protocol and structured blocked results;
5. add golden V1→V2 migration fixtures;
6. integrate the Adapter only in the dependency-ordered Daily work packages.

## Non-goals

- no production V1→V2 Adapter;
- no Canonical Daily runtime;
- no PredictionRun implementation;
- no Model Registry or Experiment Governance change;
- no PIT, Position, Model Version, Expiry, Data Quality or Evidence inference;
- no Alpha, provider or trading-authority change.
