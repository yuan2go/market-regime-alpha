# EntryAssessment

> **Status:** CURRENT_SPECIFICATION  
> **Authority:** Phase D contract specification for EntryAssessment  
> **Owner:** Entry domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, Contract-Conventions.md, Error-Catalog.md, ../architecture/05-Phase-D-Daily-Decision-Engine-V1.md  
> **Code Evidence:** DESIGNED_ONLY; implementation evidence must update docs/status/Capability-Matrix.md

## Purpose

Assess whether opening now, waiting, or rejecting adds value relative to the frozen Candidate baseline.

## Owner and authority

The **Entry domain** owns this aggregate. Adjacent domains reference it by immutable identity and may not rewrite its fields.

## Inputs

- identified upstream artifact references;
- timezone-aware semantic times;
- exact model/config/code identities where applicable;
- explicit data quality and evidence authority;
- the registered schema version and validation policy.

## Outputs

- one immutable `EntryAssessment` JSON document;
- a canonical content hash and prefixed aggregate ID;
- persistence/API representations that preserve identical semantics;
- machine-readable validation errors when construction fails.

## Schema V1

| Field | Type | Presence | Nullable | Enum | Validation | Meaning |
|---|---|---|---|---|---|---|
| `assessment_id` | `string` | required | no | — | ^entry_[a-f0-9]{64}$ | Content-addressed ID. |
| `schema_version` | `string` | required | no | — | semantic version | Schema version. |
| `snapshot_id` | `string` | required | no | — | existing snapshot | Daily root. |
| `candidate_recommendation_id` | `string` | required | no | — | existing recommendation | Candidate evidence. |
| `action` | `string` | required | no | `ENTER`, `WAIT_PULLBACK`, `WAIT_CONFIRMATION`, `REJECT`, `NO_ACTION` | exact enum | Entry decision-support action. |
| `entry_zone` | `object` | required | yes | — | {lower,upper,currency}; null allowed | Required for ENTER/WAIT_PULLBACK when price bounded. |
| `maximum_acceptable_price` | `decimal-string` | required | yes | — | >0 or null | Required for ENTER unless market-order policy explicitly permits null. |
| `invalidation_condition` | `object` | required | yes | — | registered rule or null | Required for ENTER. |
| `reference_stop` | `decimal-string` | optional | yes | — | >0 or null | Research reference, not guaranteed execution. |
| `expected_mfe` | `number` | optional | yes | — | finite or null | Only from identified model/empirical distribution. |
| `expected_mae` | `number` | optional | yes | — | <=0 convention or null | Only from identified model/empirical distribution. |
| `risk_reward` | `number` | optional | yes | — | >=0 or null | Derived from declared price/target/stop assumptions. |
| `entry_reason_codes` | `array[string]` | required | no | — | registered codes | Positive evidence. |
| `rejection_reason_codes` | `array[string]` | required | no | — | registered codes | Wait/reject evidence. |
| `model_id` | `string` | required | no | — | registered Entry model | Model identity. |
| `model_version` | `string` | required | no | — | immutable version | Model version. |
| `data_quality_grade` | `string` | required | no | `A`, `B`, `C`, `BLOCKED` | exact enum | Input quality. |
| `evidence_level` | `string` | required | no | `UNQUALIFIED`, `EXPLORATORY`, `REHEARSAL`, `FORMAL_RESEARCH`, `SHADOW_EVIDENCE` | exact enum | Authority ceiling. |
| `expires_at` | `datetime` | required | no | — | > decision_time | Assessment validity end. |
| `content_hash` | `string` | required | no | — | 64 lowercase hex | Identity digest. |

## Required/optional and null rules

- `required` means the key must be present even when its value is explicitly `null`.
- `optional` means the key may be absent; producers should prefer explicit null when absence is semantically meaningful.
- Null is never used to mean zero, false, empty population or successful computation.
- Action/status-specific nullability is validated by the error rules below.
- Unknown enum values fail validation; clients must not silently coerce them.

## Identity canonicalization

The common algorithm is defined in [Contract Conventions](Contract-Conventions.md). The identity payload for `EntryAssessment` contains:

- `schema_version`
- `snapshot_id`
- `candidate_recommendation_id`
- `action`
- `entry_zone`
- `maximum_acceptable_price`
- `invalidation_condition`
- `reference_stop`
- `expected_mfe`
- `expected_mae`
- `risk_reward`
- `entry_reason_codes`
- `rejection_reason_codes`
- `model_id`
- `model_version`
- `data_quality_grade`
- `evidence_level`
- `expires_at`

The `content_hash` field itself, transport metadata and database-generated row IDs are excluded. The public aggregate ID is:

```text
entry_<sha256(identity_payload)>
```

## Time and PIT rules

- Every referenced input must have `available_time <= decision/as_of time`.
- `created_at` is persistence time and cannot be used as market availability.
- Future outcomes may only be attached through a separate outcome aggregate.
- Corrections create a new aggregate with `supersedes`; the original remains queryable.

## Validation and error codes

| Code | Name | Condition |
|---|---|---|
| `ENT-001` | `ENTER_WITHOUT_INVALIDATION` | ENTER lacks invalidation condition. |
| `ENT-002` | `PRICE_ZONE_INVERTED` | entry_zone lower exceeds upper. |
| `ENT-003` | `PATH_TARGET_NOT_AVAILABLE` | Future path target leaked into decision. |
| `ENT-004` | `NO_ACTION_WITH_TRADE_FIELDS` | NO_ACTION carries entry price/size fields. |

Common `DOCON-*` errors from [Error Catalog](Error-Catalog.md) also apply.

## Persistence mapping

Target mapping, not current implementation fact:

```text
PostgreSQL table: phase_d_entry_assessments
Primary logical key: aggregate ID
Immutable JSON column: payload_json
Indexed columns: schema_version, decision/as_of time, referenced root IDs, disposition/status
Object-store mirror: artifacts/phase-d/EntryAssessment/<yyyy-mm-dd>/<content_hash>.json
```

Rows are append-only. A correction inserts a new row and sets `supersedes`; no update mutates a result-affecting payload.

## API mapping

```text
GET  /api/v1/entry-assessments/{id}
GET  /api/v1/entry-assessments?decision_date={date}&cursor={cursor}
POST /api/v1/entry-assessments/validate
```

Only domains that own human-entered records may expose a create command. Computed aggregates are created by internal commands and exposed read-only through HTTP.

Responses include `ETag: "<content_hash>"`. Clients must use cursor pagination and must not reconstruct canonical decisions from projections.

## Full JSON example

```json
{
  "assessment_id": "entry_ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
  "schema_version": "1.0.0",
  "snapshot_id": "drs_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "candidate_recommendation_id": "candrec_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
  "action": "WAIT_PULLBACK",
  "entry_zone": {
    "lower": "1410.00",
    "upper": "1432.00",
    "currency": "CNY"
  },
  "maximum_acceptable_price": "1432.00",
  "invalidation_condition": {
    "rule_id": "break_reference_low_v1",
    "parameters": {
      "price": "1380.00"
    }
  },
  "reference_stop": "1378.00",
  "expected_mfe": 0.034,
  "expected_mae": -0.018,
  "risk_reward": 1.89,
  "entry_reason_codes": [
    "CANDIDATE_QUALITY_ACCEPTED"
  ],
  "rejection_reason_codes": [
    "PRICE_EXTENSION_HIGH"
  ],
  "model_id": "entry-location-volume-v1",
  "model_version": "1.0.0",
  "data_quality_grade": "B",
  "evidence_level": "EXPLORATORY",
  "expires_at": "2026-07-27T15:00:00+08:00",
  "content_hash": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
}
```

The example is illustrative and does not claim a live market result.

## Invariants

1. The owning domain is the only writer.
2. Result-affecting data is immutable and content-addressed.
3. Missing mandatory evidence fails closed.
4. Evidence level cannot exceed required input authority.
5. Scores are not probabilities unless the schema carries a valid calibration identity.

## Failure behavior

Construction returns structured errors and does not persist an aggregate when an invariant fails. A blocked operational run may persist a separate blocked aggregate only when its schema explicitly permits the blocked disposition and forbids fabricated result fields.

## Non-goals

- no automatic broker order;
- no silent provider/evidence promotion;
- no mutable overwrite;
- no Alpha, probability or profitability claim without declared evidence;
- no cross-domain ownership collapse.

## Migration

Legacy fields may be exposed through an adapter only after characterization tests prove semantic compatibility. The adapter records its source identity and cannot increase evidence authority.
