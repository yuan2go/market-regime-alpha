# ThemeDirectionSnapshot

> **Status:** CURRENT_SPECIFICATION  
> **Authority:** Phase D contract specification for ThemeDirectionSnapshot  
> **Owner:** Theme Direction domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, Contract-Conventions.md, Error-Catalog.md, ../architecture/05-Phase-D-Daily-Decision-Engine-V1.md  
> **Code Evidence:** DESIGNED_ONLY; implementation evidence must update docs/status/Capability-Matrix.md

## Purpose

Freeze theme breadth, leadership and lifecycle evidence under an identified PIT mapping.

## Owner and authority

The **Theme Direction domain** owns this aggregate. Adjacent domains reference it by immutable identity and may not rewrite its fields.

## Inputs

- identified upstream artifact references;
- timezone-aware semantic times;
- exact model/config/code identities where applicable;
- explicit data quality and evidence authority;
- the registered schema version and validation policy.

## Outputs

- one immutable `ThemeDirectionSnapshot` JSON document;
- a canonical content hash and prefixed aggregate ID;
- persistence/API representations that preserve identical semantics;
- machine-readable validation errors when construction fails.

## Schema V1

| Field | Type | Presence | Nullable | Enum | Validation | Meaning |
|---|---|---|---|---|---|---|
| `snapshot_id` | `string` | required | no | — | ^themeds_[a-f0-9]{64}$ | Content-addressed ID. |
| `schema_version` | `string` | required | no | — | semantic version | Schema version. |
| `decision_time` | `datetime` | required | no | — | RFC3339 with offset | Evidence cutoff. |
| `theme_mapping_version` | `string` | required | no | — | PIT mapping identity | Membership mapping available by decision time. |
| `methodology_id` | `string` | required | no | — | registered method | Ranking/lifecycle method. |
| `rows` | `array[ThemeDirectionRow]` | required | no | — | unique theme_id | Complete eligible theme set. |
| `evidence_level` | `string` | required | no | `UNQUALIFIED`, `EXPLORATORY`, `REHEARSAL`, `FORMAL_RESEARCH`, `SHADOW_EVIDENCE` | exact enum | Authority ceiling. |
| `disposition` | `string` | required | no | `AVAILABLE`, `NO_PREDICTION`, `INSUFFICIENT_EVIDENCE`, `DATA_BLOCKED`, `INVALID` | exact enum | Result state. |
| `created_at` | `datetime` | required | no | — | RFC3339 UTC | Persistence time. |
| `content_hash` | `string` | required | no | — | 64 lowercase hex | Identity digest. |

### `ThemeDirectionRow`

| Field | Type | Presence | Nullable | Enum | Validation | Meaning |
|---|---|---|---|---|---|---|
| `theme_id` | `string` | required | no | — | registered theme | Theme identity. |
| `rank` | `integer` | required | no | — | >=1 | Relative rank. |
| `score` | `number` | required | no | — | finite | Composite score, not probability. |
| `breadth` | `number` | required | yes | — | 0..1 or null | Eligible member participation. |
| `leader_symbols` | `array[string]` | required | no | — | unique ordered | Leaders by declared rule. |
| `relative_strength` | `number` | required | yes | — | finite or null | Benchmark-relative strength. |
| `turnover_expansion` | `number` | required | yes | — | >=0 or null | Theme turnover expansion. |
| `phase` | `string` | required | no | `IGNITION`, `DIFFUSION`, `ACCELERATION`, `CLIMAX`, `DIVERGENCE`, `RETREAT`, `UNKNOWN` | exact enum | Quantified lifecycle state. |
| `phase_evidence` | `array[string]` | required | no | — | registered evidence codes | Reasons for phase. |

## Required/optional and null rules

- `required` means the key must be present even when its value is explicitly `null`.
- `optional` means the key may be absent; producers should prefer explicit null when absence is semantically meaningful.
- Null is never used to mean zero, false, empty population or successful computation.
- Action/status-specific nullability is validated by the error rules below.
- Unknown enum values fail validation; clients must not silently coerce them.

## Identity canonicalization

The common algorithm is defined in [Contract Conventions](Contract-Conventions.md). The identity payload for `ThemeDirectionSnapshot` contains:

- `schema_version`
- `decision_time`
- `theme_mapping_version`
- `methodology_id`
- `rows`
- `evidence_level`
- `disposition`

The `content_hash` field itself, transport metadata and database-generated row IDs are excluded. The public aggregate ID is:

```text
themeds_<sha256(identity_payload)>
```

## Time and PIT rules

- Every referenced input must have `available_time <= decision/as_of time`.
- `created_at` is persistence time and cannot be used as market availability.
- Future outcomes may only be attached through a separate outcome aggregate.
- Corrections create a new aggregate with `supersedes`; the original remains queryable.

## Validation and error codes

| Code | Name | Condition |
|---|---|---|
| `THEME-001` | `MAPPING_NOT_PIT` | Theme mapping was not available by decision_time. |
| `THEME-002` | `MEMBER_COVERAGE_TOO_LOW` | Eligible member coverage fails protocol. |
| `THEME-003` | `PHASE_WITHOUT_EVIDENCE` | Lifecycle phase lacks registered evidence. |

Common `DOCON-*` errors from [Error Catalog](Error-Catalog.md) also apply.

## Persistence mapping

Target mapping, not current implementation fact:

```text
PostgreSQL table: phase_d_theme_direction_snapshots
Primary logical key: aggregate ID
Immutable JSON column: payload_json
Indexed columns: schema_version, decision/as_of time, referenced root IDs, disposition/status
Object-store mirror: artifacts/phase-d/ThemeDirectionSnapshot/<yyyy-mm-dd>/<content_hash>.json
```

Rows are append-only. A correction inserts a new row and sets `supersedes`; no update mutates a result-affecting payload.

## API mapping

```text
GET  /api/v1/theme-direction-snapshots/{id}
GET  /api/v1/theme-direction-snapshots?decision_date={date}&cursor={cursor}
POST /api/v1/theme-direction-snapshots/validate
```

Only domains that own human-entered records may expose a create command. Computed aggregates are created by internal commands and exposed read-only through HTTP.

Responses include `ETag: "<content_hash>"`. Clients must use cursor pagination and must not reconstruct canonical decisions from projections.

## Full JSON example

```json
{
  "snapshot_id": "themeds_cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "schema_version": "1.0.0",
  "decision_time": "2026-07-27T14:50:00+08:00",
  "theme_mapping_version": "theme_map_20260727",
  "methodology_id": "theme_breadth_rs_v1",
  "rows": [
    {
      "theme_id": "theme_ai_application",
      "rank": 1,
      "score": 0.74,
      "breadth": 0.61,
      "leader_symbols": [
        "300033.SZ"
      ],
      "relative_strength": 0.024,
      "turnover_expansion": 1.31,
      "phase": "ACCELERATION",
      "phase_evidence": [
        "BREADTH_EXPANDING",
        "LEADER_CONFIRMATION"
      ]
    }
  ],
  "evidence_level": "EXPLORATORY",
  "disposition": "AVAILABLE",
  "created_at": "2026-07-27T06:51:11Z",
  "content_hash": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
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
