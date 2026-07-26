# RecommendationOutcome

> **Status:** CURRENT_SPECIFICATION  
> **Authority:** Phase D contract specification for RecommendationOutcome  
> **Owner:** Review and Attribution domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, Contract-Conventions.md, Error-Catalog.md, ../architecture/05-Phase-D-Daily-Decision-Engine-V1.md  
> **Code Evidence:** DESIGNED_ONLY; implementation evidence must update docs/status/Capability-Matrix.md

## Purpose

Attach an observed target/path result to a frozen recommendation without mutating the original prediction.

## Owner and authority

The **Review and Attribution domain** owns this aggregate. Adjacent domains reference it by immutable identity and may not rewrite its fields.

## Inputs

- identified upstream artifact references;
- timezone-aware semantic times;
- exact model/config/code identities where applicable;
- explicit data quality and evidence authority;
- the registered schema version and validation policy.

## Outputs

- one immutable `RecommendationOutcome` JSON document;
- a canonical content hash and prefixed aggregate ID;
- persistence/API representations that preserve identical semantics;
- machine-readable validation errors when construction fails.

## Schema V1

| Field | Type | Presence | Nullable | Enum | Validation | Meaning |
|---|---|---|---|---|---|---|
| `outcome_id` | `string` | required | no | — | ^outcome_[a-f0-9]{64}$ | Content-addressed ID. |
| `schema_version` | `string` | required | no | — | semantic version | Schema version. |
| `recommendation_id` | `string` | required | no | — | existing recommendation | Frozen prediction. |
| `target_id` | `string` | required | no | — | registered target | Outcome definition. |
| `observed_at` | `datetime` | required | yes | — | RFC3339 or null | Null until/unless observed. |
| `observation_status` | `string` | required | no | `AVAILABLE`, `NOT_YET_OBSERVED`, `UNAVAILABLE`, `INVALID` | exact enum | Outcome state. |
| `entry_reference_price` | `decimal-string` | required | yes | — | >0 or null | Target start price. |
| `exit_reference_price` | `decimal-string` | required | yes | — | >0 or null | Target end price. |
| `absolute_return` | `number` | required | yes | — | finite or null | Gross return. |
| `benchmark_return` | `number` | required | yes | — | finite or null | Declared benchmark return. |
| `relative_return` | `number` | required | yes | — | finite or null | absolute minus benchmark. |
| `mfe` | `number` | required | yes | — | >=0 or null | Maximum favorable excursion. |
| `mae` | `number` | required | yes | — | <=0 convention or null | Maximum adverse excursion. |
| `path_event` | `string` | required | yes | `UP_FIRST`, `DOWN_FIRST`, `TIMEOUT`, `NOT_APPLICABLE`, null | enum or null | Path ordering. |
| `cost_adjusted_return` | `number` | required | yes | — | finite or null | Return after declared costs. |
| `cost_model_id` | `string` | required | yes | — | registered cost model or null | Required when cost-adjusted return exists. |
| `source_manifest_id` | `string` | required | no | — | existing artifact | Outcome data lineage. |
| `created_at` | `datetime` | required | no | — | RFC3339 UTC | Persistence time. |
| `content_hash` | `string` | required | no | — | 64 lowercase hex | Identity digest. |

## Required/optional and null rules

- `required` means the key must be present even when its value is explicitly `null`.
- `optional` means the key may be absent; producers should prefer explicit null when absence is semantically meaningful.
- Null is never used to mean zero, false, empty population or successful computation.
- Action/status-specific nullability is validated by the error rules below.
- Unknown enum values fail validation; clients must not silently coerce them.

## Identity canonicalization

The common algorithm is defined in [Contract Conventions](Contract-Conventions.md). The identity payload for `RecommendationOutcome` contains:

- `schema_version`
- `recommendation_id`
- `target_id`
- `observed_at`
- `observation_status`
- `entry_reference_price`
- `exit_reference_price`
- `absolute_return`
- `benchmark_return`
- `relative_return`
- `mfe`
- `mae`
- `path_event`
- `cost_adjusted_return`
- `cost_model_id`
- `source_manifest_id`

The `content_hash` field itself, transport metadata and database-generated row IDs are excluded. The public aggregate ID is:

```text
outcome_<sha256(identity_payload)>
```

## Time and PIT rules

- Every referenced input must have `available_time <= decision/as_of time`.
- `created_at` is persistence time and cannot be used as market availability.
- Future outcomes may only be attached through a separate outcome aggregate.
- Corrections create a new aggregate with `supersedes`; the original remains queryable.

## Validation and error codes

| Code | Name | Condition |
|---|---|---|
| `OUT-001` | `METRICS_BEFORE_OBSERVATION` | Outcome metrics exist before target availability. |
| `OUT-002` | `AVAILABLE_WITH_NULL_METRICS` | Required metrics missing for AVAILABLE status. |
| `OUT-003` | `TARGET_IDENTITY_MISMATCH` | Computation does not match registered target. |
| `OUT-004` | `COST_MODEL_MISSING` | Cost-adjusted return lacks cost model. |

Common `DOCON-*` errors from [Error Catalog](Error-Catalog.md) also apply.

## Persistence mapping

Target mapping, not current implementation fact:

```text
PostgreSQL table: phase_d_recommendation_outcomes
Primary logical key: aggregate ID
Immutable JSON column: payload_json
Indexed columns: schema_version, decision/as_of time, referenced root IDs, disposition/status
Object-store mirror: artifacts/phase-d/RecommendationOutcome/<yyyy-mm-dd>/<content_hash>.json
```

Rows are append-only. A correction inserts a new row and sets `supersedes`; no update mutates a result-affecting payload.

## API mapping

```text
GET  /api/v1/recommendation-outcomes/{id}
GET  /api/v1/recommendation-outcomes?decision_date={date}&cursor={cursor}
POST /api/v1/recommendation-outcomes/validate
```

Only domains that own human-entered records may expose a create command. Computed aggregates are created by internal commands and exposed read-only through HTTP.

Responses include `ETag: "<content_hash>"`. Clients must use cursor pagination and must not reconstruct canonical decisions from projections.

## Full JSON example

```json
{
  "outcome_id": "outcome_5555555555555555555555555555555555555555555555555555555555555555",
  "schema_version": "1.0.0",
  "recommendation_id": "candrec_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
  "target_id": "R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_V1",
  "observed_at": "2026-07-28T10:30:00+08:00",
  "observation_status": "AVAILABLE",
  "entry_reference_price": "1424.50",
  "exit_reference_price": "1452.00",
  "absolute_return": 0.019305,
  "benchmark_return": 0.0041,
  "relative_return": 0.015205,
  "mfe": 0.026,
  "mae": -0.008,
  "path_event": "UP_FIRST",
  "cost_adjusted_return": 0.0187,
  "cost_model_id": "a_share_manual_base_cost_v1",
  "source_manifest_id": "srcm_20260728_1030",
  "created_at": "2026-07-28T02:31:00Z",
  "content_hash": "5555555555555555555555555555555555555555555555555555555555555555"
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
