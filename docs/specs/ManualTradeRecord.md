# ManualTradeRecord

> **Status:** CURRENT_SPECIFICATION  
> **Authority:** Phase D contract specification for ManualTradeRecord  
> **Owner:** Manual Execution Record domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, Contract-Conventions.md, Error-Catalog.md, ../architecture/05-Phase-D-Daily-Decision-Engine-V1.md  
> **Code Evidence:** DESIGNED_ONLY; implementation evidence must update docs/status/Capability-Matrix.md

## Purpose

Record the human decision, order intent, actual fills and deviation from the system proposal without inferring missing trades.

## Owner and authority

The **Manual Execution Record domain** owns this aggregate. Adjacent domains reference it by immutable identity and may not rewrite its fields.

## Inputs

- identified upstream artifact references;
- timezone-aware semantic times;
- exact model/config/code identities where applicable;
- explicit data quality and evidence authority;
- the registered schema version and validation policy.

## Outputs

- one immutable `ManualTradeRecord` JSON document;
- a canonical content hash and prefixed aggregate ID;
- persistence/API representations that preserve identical semantics;
- machine-readable validation errors when construction fails.

## Schema V1

| Field | Type | Presence | Nullable | Enum | Validation | Meaning |
|---|---|---|---|---|---|---|
| `record_id` | `string` | required | no | — | ^mtrade_[a-f0-9]{64}$ | Content-addressed record. |
| `schema_version` | `string` | required | no | — | semantic version | Schema version. |
| `snapshot_id` | `string` | required | no | — | existing snapshot | Decision context. |
| `candidate_recommendation_id` | `string` | optional | yes | — | existing recommendation or null | Nullable for discretionary/non-system trade. |
| `entry_assessment_id` | `string` | optional | yes | — | existing assessment or null | System timing reference. |
| `user_decision` | `string` | required | no | `EXECUTE`, `SKIP`, `MODIFY`, `CANCEL` | exact enum | Human decision. |
| `decision_time` | `datetime` | required | no | — | RFC3339 with offset | Time decision was made. |
| `symbol` | `string` | required | no | — | canonical instrument ID | Instrument. |
| `side` | `string` | required | no | `BUY`, `SELL` | exact enum | Order side. |
| `order_intent` | `object` | required | yes | — | typed order object or null | Null for SKIP. |
| `broker_order_id` | `string` | optional | yes | — | broker reference or null | External order reference. |
| `fills` | `array[Fill]` | required | no | — | chronological | Actual fills; empty allowed. |
| `total_filled_quantity` | `integer` | required | no | — | >=0 and 100-share rule where applicable | Aggregate filled quantity. |
| `average_fill_price` | `decimal-string` | required | yes | — | >0 or null | Null when no fill. |
| `fees_cny` | `decimal-string` | required | no | — | >=0 | Observed or declared estimated fees. |
| `status` | `string` | required | no | `DECIDED`, `ORDERED`, `PARTIALLY_FILLED`, `FILLED`, `CANCELLED`, `REJECTED` | exact enum | Execution state. |
| `plan_followed` | `boolean` | required | yes | — | true/false/null | Null when no system proposal. |
| `deviation_type` | `string` | required | no | `NONE`, `SKIP`, `PRICE`, `QUANTITY`, `TIMING`, `SYMBOL`, `SIDE`, `OTHER` | exact enum | Primary deviation. |
| `deviation_reason` | `string` | required | yes | — | non-empty or null | Required when deviation_type != NONE. |
| `supersedes` | `string` | optional | yes | — | existing record or null | Correction lineage. |
| `created_at` | `datetime` | required | no | — | RFC3339 UTC | Persistence time. |
| `content_hash` | `string` | required | no | — | 64 lowercase hex | Identity digest. |

### `Fill`

| Field | Type | Presence | Nullable | Enum | Validation | Meaning |
|---|---|---|---|---|---|---|
| `fill_id` | `string` | required | no | — | unique within broker/account | Fill identity. |
| `fill_time` | `datetime` | required | no | — | RFC3339 with offset | Observed execution time. |
| `quantity` | `integer` | required | no | — | >0 | Filled shares. |
| `price` | `decimal-string` | required | no | — | >0 | Fill price. |
| `fee_cny` | `decimal-string` | required | no | — | >=0 | Allocated fee. |

## Required/optional and null rules

- `required` means the key must be present even when its value is explicitly `null`.
- `optional` means the key may be absent; producers should prefer explicit null when absence is semantically meaningful.
- Null is never used to mean zero, false, empty population or successful computation.
- Action/status-specific nullability is validated by the error rules below.
- Unknown enum values fail validation; clients must not silently coerce them.

## Identity canonicalization

The common algorithm is defined in [Contract Conventions](Contract-Conventions.md). The identity payload for `ManualTradeRecord` contains:

- `schema_version`
- `snapshot_id`
- `candidate_recommendation_id`
- `entry_assessment_id`
- `user_decision`
- `decision_time`
- `symbol`
- `side`
- `order_intent`
- `broker_order_id`
- `fills`
- `total_filled_quantity`
- `average_fill_price`
- `fees_cny`
- `status`
- `plan_followed`
- `deviation_type`
- `deviation_reason`
- `supersedes`

The `content_hash` field itself, transport metadata and database-generated row IDs are excluded. The public aggregate ID is:

```text
mtrade_<sha256(identity_payload)>
```

## Time and PIT rules

- Every referenced input must have `available_time <= decision/as_of time`.
- `created_at` is persistence time and cannot be used as market availability.
- Future outcomes may only be attached through a separate outcome aggregate.
- Corrections create a new aggregate with `supersedes`; the original remains queryable.

## Validation and error codes

| Code | Name | Condition |
|---|---|---|
| `MTR-001` | `FILL_TOTAL_MISMATCH` | Fill quantities/prices do not reconcile to aggregates. |
| `MTR-002` | `SKIP_WITH_ORDER` | SKIP contains order/fill data. |
| `MTR-003` | `DEVIATION_REASON_REQUIRED` | Non-NONE deviation lacks reason. |
| `MTR-004` | `INFERRED_RECORD_FORBIDDEN` | Record was inferred from a recommendation rather than observed. |

Common `DOCON-*` errors from [Error Catalog](Error-Catalog.md) also apply.

## Persistence mapping

Target mapping, not current implementation fact:

```text
PostgreSQL table: phase_d_manual_trade_records
Primary logical key: aggregate ID
Immutable JSON column: payload_json
Indexed columns: schema_version, decision/as_of time, referenced root IDs, disposition/status
Object-store mirror: artifacts/phase-d/ManualTradeRecord/<yyyy-mm-dd>/<content_hash>.json
```

Rows are append-only. A correction inserts a new row and sets `supersedes`; no update mutates a result-affecting payload.

## API mapping

```text
GET  /api/v1/manual-trade-records/{id}
GET  /api/v1/manual-trade-records?decision_date={date}&cursor={cursor}
POST /api/v1/manual-trade-records/validate
```

Only domains that own human-entered records may expose a create command. Computed aggregates are created by internal commands and exposed read-only through HTTP.

Responses include `ETag: "<content_hash>"`. Clients must use cursor pagination and must not reconstruct canonical decisions from projections.

## Full JSON example

```json
{
  "record_id": "mtrade_1111111111111111111111111111111111111111111111111111111111111111",
  "schema_version": "1.0.0",
  "snapshot_id": "drs_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "candidate_recommendation_id": "candrec_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
  "entry_assessment_id": "entry_ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
  "user_decision": "MODIFY",
  "decision_time": "2026-07-27T14:56:10+08:00",
  "symbol": "600519.SH",
  "side": "BUY",
  "order_intent": {
    "order_type": "LIMIT",
    "quantity": 100,
    "limit_price": "1425.00"
  },
  "broker_order_id": "manual-20260727-001",
  "fills": [
    {
      "fill_id": "fill-001",
      "fill_time": "2026-07-27T14:57:02+08:00",
      "quantity": 100,
      "price": "1424.50",
      "fee_cny": "5.00"
    }
  ],
  "total_filled_quantity": 100,
  "average_fill_price": "1424.50",
  "fees_cny": "5.00",
  "status": "FILLED",
  "plan_followed": false,
  "deviation_type": "PRICE",
  "deviation_reason": "User lowered limit price inside approved entry zone.",
  "supersedes": null,
  "created_at": "2026-07-27T06:58:00Z",
  "content_hash": "1111111111111111111111111111111111111111111111111111111111111111"
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
