# HoldingAssessment

> **Status:** CURRENT_SPECIFICATION  
> **Authority:** Phase D contract specification for HoldingAssessment  
> **Owner:** Position Lifecycle domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, Contract-Conventions.md, Error-Catalog.md, ../architecture/05-Phase-D-Daily-Decision-Engine-V1.md  
> **Code Evidence:** DESIGNED_ONLY; implementation evidence must update docs/status/Capability-Matrix.md

## Purpose

Evaluate whether an actual position should be held, added, reduced, rotated or receive no model action.

## Owner and authority

The **Position Lifecycle domain** owns this aggregate. Adjacent domains reference it by immutable identity and may not rewrite its fields.

## Inputs

- identified upstream artifact references;
- timezone-aware semantic times;
- exact model/config/code identities where applicable;
- explicit data quality and evidence authority;
- the registered schema version and validation policy.

## Outputs

- one immutable `HoldingAssessment` JSON document;
- a canonical content hash and prefixed aggregate ID;
- persistence/API representations that preserve identical semantics;
- machine-readable validation errors when construction fails.

## Schema V1

| Field | Type | Presence | Nullable | Enum | Validation | Meaning |
|---|---|---|---|---|---|---|
| `assessment_id` | `string` | required | no | — | ^hold_[a-f0-9]{64}$ | Content-addressed ID. |
| `schema_version` | `string` | required | no | — | semantic version | Schema version. |
| `position_snapshot_id` | `string` | required | no | — | existing snapshot | Actual position evidence. |
| `symbol` | `string` | required | no | — | symbol present in position snapshot | Position. |
| `action` | `string` | required | no | `HOLD`, `ADD`, `REDUCE`, `ROTATE`, `NO_ACTION` | exact enum | Lifecycle assessment. |
| `thesis_status` | `string` | required | no | `VALID`, `WEAKENING`, `INVALID`, `UNKNOWN` | exact enum | Thesis state. |
| `add_zone` | `object` | optional | yes | — | price zone or null | Allowed only for ADD. |
| `reduce_fraction` | `number` | optional | yes | — | 0<value<=1 or null | Required for REDUCE. |
| `rotation_target_id` | `string` | optional | yes | — | candidate/strategy ref or null | Required for ROTATE. |
| `reason_codes` | `array[string]` | required | no | — | registered codes | Evidence. |
| `invalidation_condition` | `object` | required | yes | — | registered rule or null | Thesis boundary. |
| `model_id` | `string` | required | no | — | registered lifecycle model | Model identity. |
| `model_version` | `string` | required | no | — | immutable version | Version. |
| `evidence_level` | `string` | required | no | `UNQUALIFIED`, `EXPLORATORY`, `REHEARSAL`, `FORMAL_RESEARCH`, `SHADOW_EVIDENCE`, `LIVE_OBSERVED` | exact enum | Authority ceiling. |
| `expires_at` | `datetime` | required | no | — | > as_of_time | Assessment validity. |
| `content_hash` | `string` | required | no | — | 64 lowercase hex | Identity digest. |

## Required/optional and null rules

- `required` means the key must be present even when its value is explicitly `null`.
- `optional` means the key may be absent; producers should prefer explicit null when absence is semantically meaningful.
- Null is never used to mean zero, false, empty population or successful computation.
- Action/status-specific nullability is validated by the error rules below.
- Unknown enum values fail validation; clients must not silently coerce them.

## Identity canonicalization

The common algorithm is defined in [Contract Conventions](Contract-Conventions.md). The identity payload for `HoldingAssessment` contains:

- `schema_version`
- `position_snapshot_id`
- `symbol`
- `action`
- `thesis_status`
- `add_zone`
- `reduce_fraction`
- `rotation_target_id`
- `reason_codes`
- `invalidation_condition`
- `model_id`
- `model_version`
- `evidence_level`
- `expires_at`

The `content_hash` field itself, transport metadata and database-generated row IDs are excluded. The public aggregate ID is:

```text
hold_<sha256(identity_payload)>
```

## Time and PIT rules

- Every referenced input must have `available_time <= decision/as_of time`.
- `created_at` is persistence time and cannot be used as market availability.
- Future outcomes may only be attached through a separate outcome aggregate.
- Corrections create a new aggregate with `supersedes`; the original remains queryable.

## Validation and error codes

| Code | Name | Condition |
|---|---|---|
| `HOLD-001` | `NO_ACTION_AS_HOLD_FORBIDDEN` | NO_ACTION was interpreted as HOLD. |
| `HOLD-002` | `ACTION_FIELD_MISMATCH` | Action-specific field is missing or unexpectedly present. |
| `HOLD-003` | `SYMBOL_NOT_IN_POSITION` | Assessment symbol is absent from actual position snapshot. |

Common `DOCON-*` errors from [Error Catalog](Error-Catalog.md) also apply.

## Persistence mapping

Target mapping, not current implementation fact:

```text
PostgreSQL table: phase_d_holding_assessments
Primary logical key: aggregate ID
Immutable JSON column: payload_json
Indexed columns: schema_version, decision/as_of time, referenced root IDs, disposition/status
Object-store mirror: artifacts/phase-d/HoldingAssessment/<yyyy-mm-dd>/<content_hash>.json
```

Rows are append-only. A correction inserts a new row and sets `supersedes`; no update mutates a result-affecting payload.

## API mapping

```text
GET  /api/v1/holding-assessments/{id}
GET  /api/v1/holding-assessments?decision_date={date}&cursor={cursor}
POST /api/v1/holding-assessments/validate
```

Only domains that own human-entered records may expose a create command. Computed aggregates are created by internal commands and exposed read-only through HTTP.

Responses include `ETag: "<content_hash>"`. Clients must use cursor pagination and must not reconstruct canonical decisions from projections.

## Full JSON example

```json
{
  "assessment_id": "hold_3333333333333333333333333333333333333333333333333333333333333333",
  "schema_version": "1.0.0",
  "position_snapshot_id": "pos_2222222222222222222222222222222222222222222222222222222222222222",
  "symbol": "600519.SH",
  "action": "HOLD",
  "thesis_status": "VALID",
  "add_zone": null,
  "reduce_fraction": null,
  "rotation_target_id": null,
  "reason_codes": [
    "TREND_INTACT",
    "NO_EXIT_TRIGGER"
  ],
  "invalidation_condition": {
    "rule_id": "close_below_reference_low_v1",
    "parameters": {
      "price": "1380.00"
    }
  },
  "model_id": "holding-baseline-v1",
  "model_version": "1.0.0",
  "evidence_level": "EXPLORATORY",
  "expires_at": "2026-07-28T15:00:00+08:00",
  "content_hash": "3333333333333333333333333333333333333333333333333333333333333333"
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
