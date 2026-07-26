# PositionSnapshot

> **Status:** CURRENT_SPECIFICATION  
> **Authority:** Phase D contract specification for PositionSnapshot  
> **Owner:** Position Lifecycle domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, Contract-Conventions.md, Error-Catalog.md, ../architecture/05-Phase-D-Daily-Decision-Engine-V1.md  
> **Code Evidence:** DESIGNED_ONLY; implementation evidence must update docs/status/Capability-Matrix.md

## Purpose

Freeze actual account position state from manual-ledger or broker-reconciled evidence; never derive it from recommendations.

## Owner and authority

The **Position Lifecycle domain** owns this aggregate. Adjacent domains reference it by immutable identity and may not rewrite its fields.

## Inputs

- identified upstream artifact references;
- timezone-aware semantic times;
- exact model/config/code identities where applicable;
- explicit data quality and evidence authority;
- the registered schema version and validation policy.

## Outputs

- one immutable `PositionSnapshot` JSON document;
- a canonical content hash and prefixed aggregate ID;
- persistence/API representations that preserve identical semantics;
- machine-readable validation errors when construction fails.

## Schema V1

| Field | Type | Presence | Nullable | Enum | Validation | Meaning |
|---|---|---|---|---|---|---|
| `position_snapshot_id` | `string` | required | no | — | ^pos_[a-f0-9]{64}$ | Content-addressed ID. |
| `schema_version` | `string` | required | no | — | semantic version | Schema version. |
| `account_scope_id` | `string` | required | no | — | registered pseudonymous scope | No secrets/account credentials. |
| `as_of_time` | `datetime` | required | no | — | RFC3339 with offset | Position observation cutoff. |
| `source_type` | `string` | required | no | `MANUAL_LEDGER`, `BROKER_RECONCILED` | exact enum | Authority source. |
| `positions` | `array[PositionRow]` | required | no | — | unique symbol | Actual positions. |
| `cash_available_cny` | `decimal-string` | required | yes | — | >=0 or null | Null if not observed. |
| `total_equity_cny` | `decimal-string` | required | yes | — | >=0 or null | Null if not observed. |
| `reconciliation_status` | `string` | required | no | `UNVERIFIED`, `MATCHED`, `MISMATCH`, `BLOCKED` | exact enum | Ledger/broker reconciliation. |
| `source_record_ids` | `array[string]` | required | no | — | sorted unique | ManualTradeRecord/broker source IDs. |
| `supersedes` | `string` | optional | yes | — | existing snapshot or null | Correction lineage. |
| `created_at` | `datetime` | required | no | — | RFC3339 UTC | Persistence time. |
| `content_hash` | `string` | required | no | — | 64 lowercase hex | Identity digest. |

### `PositionRow`

| Field | Type | Presence | Nullable | Enum | Validation | Meaning |
|---|---|---|---|---|---|---|
| `symbol` | `string` | required | no | — | canonical instrument ID | Instrument. |
| `quantity` | `integer` | required | no | — | >=0 | Total shares. |
| `available_quantity` | `integer` | required | no | — | 0..quantity | Sellable quantity under T+1. |
| `average_cost_cny` | `decimal-string` | required | yes | — | >=0 or null | Average cost. |
| `market_price_cny` | `decimal-string` | required | yes | — | >=0 or null | Observed mark. |
| `market_value_cny` | `decimal-string` | required | yes | — | >=0 or null | Derived mark value. |
| `unrealized_pnl_cny` | `decimal-string` | required | yes | — | finite or null | Derived P&L. |
| `open_trade_record_ids` | `array[string]` | required | no | — | sorted unique | Contributing actual trades. |
| `thesis_reference_id` | `string` | optional | yes | — | existing thesis or null | Research thesis reference. |

## Required/optional and null rules

- `required` means the key must be present even when its value is explicitly `null`.
- `optional` means the key may be absent; producers should prefer explicit null when absence is semantically meaningful.
- Null is never used to mean zero, false, empty population or successful computation.
- Action/status-specific nullability is validated by the error rules below.
- Unknown enum values fail validation; clients must not silently coerce them.

## Identity canonicalization

The common algorithm is defined in [Contract Conventions](Contract-Conventions.md). The identity payload for `PositionSnapshot` contains:

- `schema_version`
- `account_scope_id`
- `as_of_time`
- `source_type`
- `positions`
- `cash_available_cny`
- `total_equity_cny`
- `reconciliation_status`
- `source_record_ids`
- `supersedes`

The `content_hash` field itself, transport metadata and database-generated row IDs are excluded. The public aggregate ID is:

```text
pos_<sha256(identity_payload)>
```

## Time and PIT rules

- Every referenced input must have `available_time <= decision/as_of time`.
- `created_at` is persistence time and cannot be used as market availability.
- Future outcomes may only be attached through a separate outcome aggregate.
- Corrections create a new aggregate with `supersedes`; the original remains queryable.

## Validation and error codes

| Code | Name | Condition |
|---|---|---|
| `POS-001` | `RECOMMENDATION_DERIVATION_FORBIDDEN` | Position was derived from recommendation. |
| `POS-002` | `AVAILABLE_QUANTITY_EXCEEDS_TOTAL` | Sellable quantity exceeds total. |
| `POS-003` | `RECONCILIATION_MISMATCH` | Manual ledger and broker evidence disagree. |
| `POS-004` | `SOURCE_RECORD_MISSING` | Actual trade source record is missing. |

Common `DOCON-*` errors from [Error Catalog](Error-Catalog.md) also apply.

## Persistence mapping

Target mapping, not current implementation fact:

```text
PostgreSQL table: phase_d_position_snapshots
Primary logical key: aggregate ID
Immutable JSON column: payload_json
Indexed columns: schema_version, decision/as_of time, referenced root IDs, disposition/status
Object-store mirror: artifacts/phase-d/PositionSnapshot/<yyyy-mm-dd>/<content_hash>.json
```

Rows are append-only. A correction inserts a new row and sets `supersedes`; no update mutates a result-affecting payload.

## API mapping

```text
GET  /api/v1/position-snapshots/{id}
GET  /api/v1/position-snapshots?decision_date={date}&cursor={cursor}
POST /api/v1/position-snapshots/validate
```

Only domains that own human-entered records may expose a create command. Computed aggregates are created by internal commands and exposed read-only through HTTP.

Responses include `ETag: "<content_hash>"`. Clients must use cursor pagination and must not reconstruct canonical decisions from projections.

## Full JSON example

```json
{
  "position_snapshot_id": "pos_2222222222222222222222222222222222222222222222222222222222222222",
  "schema_version": "1.0.0",
  "account_scope_id": "account_research_manual_01",
  "as_of_time": "2026-07-28T09:20:00+08:00",
  "source_type": "MANUAL_LEDGER",
  "positions": [
    {
      "symbol": "600519.SH",
      "quantity": 100,
      "available_quantity": 0,
      "average_cost_cny": "1424.55",
      "market_price_cny": "1430.00",
      "market_value_cny": "143000.00",
      "unrealized_pnl_cny": "545.00",
      "open_trade_record_ids": [
        "mtrade_1111111111111111111111111111111111111111111111111111111111111111"
      ],
      "thesis_reference_id": "thesis_candidate_b1_20260727"
    }
  ],
  "cash_available_cny": "50000.00",
  "total_equity_cny": "193000.00",
  "reconciliation_status": "UNVERIFIED",
  "source_record_ids": [
    "mtrade_1111111111111111111111111111111111111111111111111111111111111111"
  ],
  "supersedes": null,
  "created_at": "2026-07-28T01:20:05Z",
  "content_hash": "2222222222222222222222222222222222222222222222222222222222222222"
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
