# ETFDirectionSnapshot

> **Status:** CURRENT_SPECIFICATION  
> **Authority:** Phase D contract specification for ETFDirectionSnapshot  
> **Owner:** ETF Direction domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, Contract-Conventions.md, Error-Catalog.md, ../architecture/05-Phase-D-Daily-Decision-Engine-V1.md  
> **Code Evidence:** DESIGNED_ONLY; implementation evidence must update docs/status/Capability-Matrix.md

## Purpose

Freeze ranked ETF direction evidence at one decision time without granting trade authority.

## Owner and authority

The **ETF Direction domain** owns this aggregate. Adjacent domains reference it by immutable identity and may not rewrite its fields.

## Inputs

- identified upstream artifact references;
- timezone-aware semantic times;
- exact model/config/code identities where applicable;
- explicit data quality and evidence authority;
- the registered schema version and validation policy.

## Outputs

- one immutable `ETFDirectionSnapshot` JSON document;
- a canonical content hash and prefixed aggregate ID;
- persistence/API representations that preserve identical semantics;
- machine-readable validation errors when construction fails.

## Schema V1

| Field | Type | Presence | Nullable | Enum | Validation | Meaning |
|---|---|---|---|---|---|---|
| `snapshot_id` | `string` | required | no | — | ^etfds_[a-f0-9]{64}$ | Content-addressed ID. |
| `schema_version` | `string` | required | no | — | semantic version | Schema version. |
| `decision_time` | `datetime` | required | no | — | RFC3339 with offset | Evidence cutoff. |
| `etf_universe_id` | `string` | required | no | — | existing artifact | PIT ETF population. |
| `methodology_id` | `string` | required | no | — | registered model/method | Transparent ranking method. |
| `rows` | `array[ETFDirectionRow]` | required | no | — | unique symbol; rank starts at 1 | Complete eligible ETF ranking. |
| `data_quality_grade` | `string` | required | no | `A`, `B`, `C`, `BLOCKED` | exact enum | Input quality. |
| `evidence_level` | `string` | required | no | `UNQUALIFIED`, `EXPLORATORY`, `REHEARSAL`, `FORMAL_RESEARCH`, `SHADOW_EVIDENCE` | exact enum | Authority ceiling. |
| `disposition` | `string` | required | no | `AVAILABLE`, `NO_PREDICTION`, `INSUFFICIENT_EVIDENCE`, `DATA_BLOCKED`, `INVALID` | exact enum | Result state. |
| `created_at` | `datetime` | required | no | — | RFC3339 UTC | Persistence time. |
| `content_hash` | `string` | required | no | — | 64 lowercase hex | Identity digest. |

### `ETFDirectionRow`

| Field | Type | Presence | Nullable | Enum | Validation | Meaning |
|---|---|---|---|---|---|---|
| `symbol` | `string` | required | no | — | canonical instrument ID | ETF symbol. |
| `rank` | `integer` | required | no | — | >=1 and contiguous | Cross-sectional rank. |
| `score` | `number` | required | no | — | finite | Model score, not probability. |
| `relative_strength` | `number` | required | yes | — | finite or null | Declared-horizon relative strength. |
| `turnover_expansion` | `number` | required | yes | — | >=0 or null | Turnover ratio/proxy. |
| `flow_proxy` | `number` | optional | yes | — | finite or null | Provider-bounded capital-flow proxy. |
| `liquidity_grade` | `string` | required | no | `A`, `B`, `C`, `INELIGIBLE` | exact enum | Liquidity classification. |
| `related_theme_ids` | `array[string]` | required | no | — | sorted unique | Theme mapping identities. |

## Required/optional and null rules

- `required` means the key must be present even when its value is explicitly `null`.
- `optional` means the key may be absent; producers should prefer explicit null when absence is semantically meaningful.
- Null is never used to mean zero, false, empty population or successful computation.
- Action/status-specific nullability is validated by the error rules below.
- Unknown enum values fail validation; clients must not silently coerce them.

## Identity canonicalization

The common algorithm is defined in [Contract Conventions](Contract-Conventions.md). The identity payload for `ETFDirectionSnapshot` contains:

- `schema_version`
- `decision_time`
- `etf_universe_id`
- `methodology_id`
- `rows`
- `data_quality_grade`
- `evidence_level`
- `disposition`

The `content_hash` field itself, transport metadata and database-generated row IDs are excluded. The public aggregate ID is:

```text
etfds_<sha256(identity_payload)>
```

## Time and PIT rules

- Every referenced input must have `available_time <= decision/as_of time`.
- `created_at` is persistence time and cannot be used as market availability.
- Future outcomes may only be attached through a separate outcome aggregate.
- Corrections create a new aggregate with `supersedes`; the original remains queryable.

## Validation and error codes

| Code | Name | Condition |
|---|---|---|
| `ETF-001` | `DUPLICATE_SYMBOL` | Rows contain duplicate ETF symbols. |
| `ETF-002` | `NON_CONTIGUOUS_RANK` | Available ranking is not contiguous. |
| `ETF-003` | `UNSUPPORTED_FLOW_AUTHORITY` | Flow proxy exceeds provider contract. |

Common `DOCON-*` errors from [Error Catalog](Error-Catalog.md) also apply.

## Persistence mapping

Target mapping, not current implementation fact:

```text
PostgreSQL table: phase_d_etf_direction_snapshots
Primary logical key: aggregate ID
Immutable JSON column: payload_json
Indexed columns: schema_version, decision/as_of time, referenced root IDs, disposition/status
Object-store mirror: artifacts/phase-d/ETFDirectionSnapshot/<yyyy-mm-dd>/<content_hash>.json
```

Rows are append-only. A correction inserts a new row and sets `supersedes`; no update mutates a result-affecting payload.

## API mapping

```text
GET  /api/v1/etf-direction-snapshots/{id}
GET  /api/v1/etf-direction-snapshots?decision_date={date}&cursor={cursor}
POST /api/v1/etf-direction-snapshots/validate
```

Only domains that own human-entered records may expose a create command. Computed aggregates are created by internal commands and exposed read-only through HTTP.

Responses include `ETag: "<content_hash>"`. Clients must use cursor pagination and must not reconstruct canonical decisions from projections.

## Full JSON example

```json
{
  "snapshot_id": "etfds_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "schema_version": "1.0.0",
  "decision_time": "2026-07-27T14:50:00+08:00",
  "etf_universe_id": "univ_etf_20260727",
  "methodology_id": "etf_relative_strength_v1",
  "rows": [
    {
      "symbol": "510300.SH",
      "rank": 1,
      "score": 0.82,
      "relative_strength": 0.031,
      "turnover_expansion": 1.42,
      "flow_proxy": null,
      "liquidity_grade": "A",
      "related_theme_ids": [
        "theme_large_cap"
      ]
    }
  ],
  "data_quality_grade": "B",
  "evidence_level": "EXPLORATORY",
  "disposition": "AVAILABLE",
  "created_at": "2026-07-27T06:51:10Z",
  "content_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
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
