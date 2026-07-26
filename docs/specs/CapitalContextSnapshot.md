# CapitalContextSnapshot

> **Status:** CURRENT_SPECIFICATION  
> **Authority:** Phase D contract specification for CapitalContextSnapshot  
> **Owner:** Capital Context domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, Contract-Conventions.md, Error-Catalog.md, ../architecture/05-Phase-D-Daily-Decision-Engine-V1.md  
> **Code Evidence:** DESIGNED_ONLY; implementation evidence must update docs/status/Capability-Matrix.md

## Purpose

Freeze market-wide liquidity and capital-context observations with explicit field availability.

## Owner and authority

The **Capital Context domain** owns this aggregate. Adjacent domains reference it by immutable identity and may not rewrite its fields.

## Inputs

- identified upstream artifact references;
- timezone-aware semantic times;
- exact model/config/code identities where applicable;
- explicit data quality and evidence authority;
- the registered schema version and validation policy.

## Outputs

- one immutable `CapitalContextSnapshot` JSON document;
- a canonical content hash and prefixed aggregate ID;
- persistence/API representations that preserve identical semantics;
- machine-readable validation errors when construction fails.

## Schema V1

| Field | Type | Presence | Nullable | Enum | Validation | Meaning |
|---|---|---|---|---|---|---|
| `snapshot_id` | `string` | required | no | — | ^capctx_[a-f0-9]{64}$ | Content-addressed ID. |
| `schema_version` | `string` | required | no | — | semantic version | Schema version. |
| `decision_time` | `datetime` | required | no | — | RFC3339 with offset | Evidence cutoff. |
| `source_manifest_id` | `string` | required | no | — | existing artifact | Provider lineage. |
| `market_turnover_cny` | `decimal-string` | required | yes | — | >=0 or null | Observed market turnover. |
| `turnover_change` | `number` | required | yes | — | finite or null | Change versus declared baseline. |
| `advance_decline_ratio` | `number` | required | yes | — | >=0 or null | Breadth proxy. |
| `limit_up_count` | `integer` | required | yes | — | >=0 or null | Count under declared exchange rules. |
| `limit_down_count` | `integer` | required | yes | — | >=0 or null | Count under declared exchange rules. |
| `financing_balance_change` | `number` | optional | yes | — | finite or null | Only when availability semantics are qualified. |
| `northbound_flow_cny` | `decimal-string` | optional | yes | — | finite decimal or null | Nullable when no qualified current field exists. |
| `field_availability` | `object` | required | no | — | one status per optional metric | AVAILABLE/NOT_AVAILABLE/STALE/UNQUALIFIED. |
| `liquidity_state` | `string` | required | no | `EXPANDING`, `NEUTRAL`, `CONTRACTING`, `STRESSED`, `UNKNOWN` | exact enum | Descriptive state only. |
| `evidence_level` | `string` | required | no | `UNQUALIFIED`, `EXPLORATORY`, `REHEARSAL`, `FORMAL_RESEARCH`, `SHADOW_EVIDENCE` | exact enum | Authority ceiling. |
| `disposition` | `string` | required | no | `AVAILABLE`, `INSUFFICIENT_EVIDENCE`, `DATA_BLOCKED`, `INVALID` | exact enum | Result state. |
| `created_at` | `datetime` | required | no | — | RFC3339 UTC | Persistence time. |
| `content_hash` | `string` | required | no | — | 64 lowercase hex | Identity digest. |

## Required/optional and null rules

- `required` means the key must be present even when its value is explicitly `null`.
- `optional` means the key may be absent; producers should prefer explicit null when absence is semantically meaningful.
- Null is never used to mean zero, false, empty population or successful computation.
- Action/status-specific nullability is validated by the error rules below.
- Unknown enum values fail validation; clients must not silently coerce them.

## Identity canonicalization

The common algorithm is defined in [Contract Conventions](Contract-Conventions.md). The identity payload for `CapitalContextSnapshot` contains:

- `schema_version`
- `decision_time`
- `source_manifest_id`
- `market_turnover_cny`
- `turnover_change`
- `advance_decline_ratio`
- `limit_up_count`
- `limit_down_count`
- `financing_balance_change`
- `northbound_flow_cny`
- `field_availability`
- `liquidity_state`
- `evidence_level`
- `disposition`

The `content_hash` field itself, transport metadata and database-generated row IDs are excluded. The public aggregate ID is:

```text
capctx_<sha256(identity_payload)>
```

## Time and PIT rules

- Every referenced input must have `available_time <= decision/as_of time`.
- `created_at` is persistence time and cannot be used as market availability.
- Future outcomes may only be attached through a separate outcome aggregate.
- Corrections create a new aggregate with `supersedes`; the original remains queryable.

## Validation and error codes

| Code | Name | Condition |
|---|---|---|
| `CAP-001` | `OPTIONAL_FIELD_WITHOUT_AVAILABILITY` | Optional metric lacks availability status. |
| `CAP-002` | `UNQUALIFIED_FIELD_USED` | Unqualified capital field contributes to formal state. |
| `CAP-003` | `COUNT_RULE_MISSING` | Limit count lacks exchange/rule identity. |

Common `DOCON-*` errors from [Error Catalog](Error-Catalog.md) also apply.

## Persistence mapping

Target mapping, not current implementation fact:

```text
PostgreSQL table: phase_d_capital_context_snapshots
Primary logical key: aggregate ID
Immutable JSON column: payload_json
Indexed columns: schema_version, decision/as_of time, referenced root IDs, disposition/status
Object-store mirror: artifacts/phase-d/CapitalContextSnapshot/<yyyy-mm-dd>/<content_hash>.json
```

Rows are append-only. A correction inserts a new row and sets `supersedes`; no update mutates a result-affecting payload.

## API mapping

```text
GET  /api/v1/capital-context-snapshots/{id}
GET  /api/v1/capital-context-snapshots?decision_date={date}&cursor={cursor}
POST /api/v1/capital-context-snapshots/validate
```

Only domains that own human-entered records may expose a create command. Computed aggregates are created by internal commands and exposed read-only through HTTP.

Responses include `ETag: "<content_hash>"`. Clients must use cursor pagination and must not reconstruct canonical decisions from projections.

## Full JSON example

```json
{
  "snapshot_id": "capctx_dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
  "schema_version": "1.0.0",
  "decision_time": "2026-07-27T14:50:00+08:00",
  "source_manifest_id": "srcm_20260727_1450",
  "market_turnover_cny": "987654321000.00",
  "turnover_change": 0.084,
  "advance_decline_ratio": 1.42,
  "limit_up_count": 63,
  "limit_down_count": 7,
  "financing_balance_change": null,
  "northbound_flow_cny": null,
  "field_availability": {
    "financing_balance_change": "NOT_AVAILABLE",
    "northbound_flow_cny": "NOT_AVAILABLE"
  },
  "liquidity_state": "EXPANDING",
  "evidence_level": "EXPLORATORY",
  "disposition": "AVAILABLE",
  "created_at": "2026-07-27T06:51:12Z",
  "content_hash": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
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
