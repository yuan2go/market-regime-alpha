# ExitAssessment

> **Status:** CURRENT_SPECIFICATION  
> **Authority:** Phase D contract specification for ExitAssessment  
> **Owner:** Exit domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, Contract-Conventions.md, Error-Catalog.md, ../architecture/05-Phase-D-Daily-Decision-Engine-V1.md  
> **Code Evidence:** DESIGNED_ONLY; implementation evidence must update docs/status/Capability-Matrix.md

## Purpose

Evaluate independent exit, reduction and monitoring reasons for an actual position.

## Owner and authority

The **Exit domain** owns this aggregate. Adjacent domains reference it by immutable identity and may not rewrite its fields.

## Inputs

- identified upstream artifact references;
- timezone-aware semantic times;
- exact model/config/code identities where applicable;
- explicit data quality and evidence authority;
- the registered schema version and validation policy.

## Outputs

- one immutable `ExitAssessment` JSON document;
- a canonical content hash and prefixed aggregate ID;
- persistence/API representations that preserve identical semantics;
- machine-readable validation errors when construction fails.

## Schema V1

| Field | Type | Presence | Nullable | Enum | Validation | Meaning |
|---|---|---|---|---|---|---|
| `assessment_id` | `string` | required | no | — | ^exit_[a-f0-9]{64}$ | Content-addressed ID. |
| `schema_version` | `string` | required | no | — | semantic version | Schema version. |
| `position_snapshot_id` | `string` | required | no | — | existing snapshot | Actual position evidence. |
| `symbol` | `string` | required | no | — | position symbol | Instrument. |
| `action` | `string` | required | no | `EXIT`, `REDUCE`, `WAIT_EXIT_CONFIRMATION`, `NO_ACTION` | exact enum | Exit assessment. |
| `exit_reason` | `string` | required | no | `PROFIT_TAKING`, `RISK_STOP`, `THESIS_INVALIDATION`, `TREND_INVALIDATION`, `STRUCTURE_BREAK`, `EXHAUSTION`, `TIME_EXPIRY`, `FORCED_EXIT`, `NONE` | exact enum | Primary reason. |
| `contributing_reason_codes` | `array[string]` | required | no | — | registered codes | Secondary evidence. |
| `urgency` | `string` | required | no | `NOW`, `NEXT_LIQUID_WINDOW`, `MONITOR` | exact enum | Execution urgency. |
| `quantity_fraction` | `number` | required | yes | — | 0<value<=1 or null | Required for EXIT/REDUCE. |
| `trigger_price` | `decimal-string` | optional | yes | — | >0 or null | Observed/reference trigger. |
| `expected_post_exit_regret` | `number` | optional | yes | — | >=0 or null | Research estimate only. |
| `model_id` | `string` | required | no | — | registered Exit model | Model identity. |
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

The common algorithm is defined in [Contract Conventions](Contract-Conventions.md). The identity payload for `ExitAssessment` contains:

- `schema_version`
- `position_snapshot_id`
- `symbol`
- `action`
- `exit_reason`
- `contributing_reason_codes`
- `urgency`
- `quantity_fraction`
- `trigger_price`
- `expected_post_exit_regret`
- `model_id`
- `model_version`
- `evidence_level`
- `expires_at`

The `content_hash` field itself, transport metadata and database-generated row IDs are excluded. The public aggregate ID is:

```text
exit_<sha256(identity_payload)>
```

## Time and PIT rules

- Every referenced input must have `available_time <= decision/as_of time`.
- `created_at` is persistence time and cannot be used as market availability.
- Future outcomes may only be attached through a separate outcome aggregate.
- Corrections create a new aggregate with `supersedes`; the original remains queryable.

## Validation and error codes

| Code | Name | Condition |
|---|---|---|
| `EXT-001` | `INVERSE_ENTRY_IMPLEMENTATION` | Exit was computed as inverse Entry score. |
| `EXT-002` | `EXIT_WITH_NONE_REASON` | EXIT/REDUCE uses NONE reason. |
| `EXT-003` | `ACTION_FIELD_MISMATCH` | Action-specific quantity/urgency fields are invalid. |
| `EXT-004` | `T1_UNSELLABLE` | Requested quantity exceeds available quantity. |

Common `DOCON-*` errors from [Error Catalog](Error-Catalog.md) also apply.

## Persistence mapping

Target mapping, not current implementation fact:

```text
PostgreSQL table: phase_d_exit_assessments
Primary logical key: aggregate ID
Immutable JSON column: payload_json
Indexed columns: schema_version, decision/as_of time, referenced root IDs, disposition/status
Object-store mirror: artifacts/phase-d/ExitAssessment/<yyyy-mm-dd>/<content_hash>.json
```

Rows are append-only. A correction inserts a new row and sets `supersedes`; no update mutates a result-affecting payload.

## API mapping

```text
GET  /api/v1/exit-assessments/{id}
GET  /api/v1/exit-assessments?decision_date={date}&cursor={cursor}
POST /api/v1/exit-assessments/validate
```

Only domains that own human-entered records may expose a create command. Computed aggregates are created by internal commands and exposed read-only through HTTP.

Responses include `ETag: "<content_hash>"`. Clients must use cursor pagination and must not reconstruct canonical decisions from projections.

## Full JSON example

```json
{
  "assessment_id": "exit_4444444444444444444444444444444444444444444444444444444444444444",
  "schema_version": "1.0.0",
  "position_snapshot_id": "pos_2222222222222222222222222222222222222222222222222222222222222222",
  "symbol": "600519.SH",
  "action": "WAIT_EXIT_CONFIRMATION",
  "exit_reason": "EXHAUSTION",
  "contributing_reason_codes": [
    "VOLUME_DIVERGENCE_EARLY"
  ],
  "urgency": "MONITOR",
  "quantity_fraction": null,
  "trigger_price": null,
  "expected_post_exit_regret": 0.012,
  "model_id": "exit-exhaustion-v1",
  "model_version": "1.0.0",
  "evidence_level": "EXPLORATORY",
  "expires_at": "2026-07-28T15:00:00+08:00",
  "content_hash": "4444444444444444444444444444444444444444444444444444444444444444"
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
