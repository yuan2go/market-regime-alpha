# DailyResearchSnapshot

> **Status:** CURRENT_SPECIFICATION  
> **Authority:** Phase D contract specification for DailyResearchSnapshot  
> **Owner:** Daily Decision domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, Contract-Conventions.md, Error-Catalog.md, ../architecture/05-Phase-D-Daily-Decision-Engine-V1.md  
> **Code Evidence:** DESIGNED_ONLY; implementation evidence must update docs/status/Capability-Matrix.md

## Purpose

Freeze the complete, point-in-time evidence root for one decision instant.

## Owner and authority

The **Daily Decision domain** owns this aggregate. Adjacent domains reference it by immutable identity and may not rewrite its fields.

## Inputs

- identified upstream artifact references;
- timezone-aware semantic times;
- exact model/config/code identities where applicable;
- explicit data quality and evidence authority;
- the registered schema version and validation policy.

## Outputs

- one immutable `DailyResearchSnapshot` JSON document;
- a canonical content hash and prefixed aggregate ID;
- persistence/API representations that preserve identical semantics;
- machine-readable validation errors when construction fails.

## Schema V1

| Field | Type | Presence | Nullable | Enum | Validation | Meaning |
|---|---|---|---|---|---|---|
| `snapshot_id` | `string` | required | no | — | ^drs_[a-f0-9]{64}$ | Content-addressed aggregate identifier. |
| `schema_version` | `string` | required | no | — | semantic version | Contract schema version. |
| `decision_date` | `date` | required | no | — | ISO-8601 date | Trading decision date. |
| `decision_time` | `datetime` | required | no | — | RFC3339 with offset | Information cutoff for every referenced input. |
| `timezone` | `string` | required | no | `Asia/Shanghai` | exact enum | Semantic market timezone. |
| `market_session_id` | `string` | required | no | — | existing calendar identity | Referenced session must be open for the instrument scope. |
| `calendar_artifact_id` | `string` | required | no | — | existing artifact | Calendar evidence. |
| `source_manifest_id` | `string` | required | no | — | existing artifact | Exact provider/source inputs. |
| `universe_snapshot_id` | `string` | required | no | — | existing artifact | PIT stock/ETF population. |
| `eligibility_snapshot_id` | `string` | required | no | — | existing artifact | Tradability decisions. |
| `context_refs` | `object` | required | yes | — | known keys only | market/ETF/theme/capital context identities; null when explicitly unavailable. |
| `feature_matrix_id` | `string` | required | yes | — | existing artifact or null | Feature materialization; null only when blocked before feature stage. |
| `candidate_prediction_run_ids` | `array[string]` | required | no | — | unique ordered IDs | Complete model runs; empty only for blocked/no-prediction disposition. |
| `entry_assessment_run_ids` | `array[string]` | required | no | — | unique ordered IDs | May be empty when Entry is outside the run scope. |
| `position_snapshot_id` | `string` | optional | yes | — | existing artifact or null | Actual position state at decision time. |
| `experiment_protocol_ids` | `array[string]` | required | no | — | sorted unique IDs | Frozen protocols governing the run. |
| `evidence_level` | `string` | required | no | `UNQUALIFIED`, `EXPLORATORY`, `REHEARSAL`, `FORMAL_RESEARCH`, `SHADOW_EVIDENCE`, `LIVE_OBSERVED` | exact enum | Maximum evidence authority. |
| `disposition` | `string` | required | no | `AVAILABLE`, `NO_PREDICTION`, `INSUFFICIENT_EVIDENCE`, `DATA_BLOCKED`, `INVALID` | exact enum | Aggregate result state. |
| `data_quality_grade` | `string` | required | no | `A`, `B`, `C`, `BLOCKED` | exact enum | Worst required-input quality grade. |
| `supersedes` | `string` | optional | yes | — | existing snapshot ID or null | Correction lineage; original remains immutable. |
| `created_at` | `datetime` | required | no | — | RFC3339 UTC | Persistence time, not market availability time. |
| `content_hash` | `string` | required | no | — | 64 lowercase hex | SHA-256 of the identity payload. |

## Required/optional and null rules

- `required` means the key must be present even when its value is explicitly `null`.
- `optional` means the key may be absent; producers should prefer explicit null when absence is semantically meaningful.
- Null is never used to mean zero, false, empty population or successful computation.
- Action/status-specific nullability is validated by the error rules below.
- Unknown enum values fail validation; clients must not silently coerce them.

## Identity canonicalization

The common algorithm is defined in [Contract Conventions](Contract-Conventions.md). The identity payload for `DailyResearchSnapshot` contains:

- `schema_version`
- `decision_date`
- `decision_time`
- `timezone`
- `market_session_id`
- `calendar_artifact_id`
- `source_manifest_id`
- `universe_snapshot_id`
- `eligibility_snapshot_id`
- `context_refs`
- `feature_matrix_id`
- `candidate_prediction_run_ids`
- `entry_assessment_run_ids`
- `position_snapshot_id`
- `experiment_protocol_ids`
- `evidence_level`
- `disposition`
- `data_quality_grade`
- `supersedes`

The `content_hash` field itself, transport metadata and database-generated row IDs are excluded. The public aggregate ID is:

```text
drs_<sha256(identity_payload)>
```

## Time and PIT rules

- Every referenced input must have `available_time <= decision/as_of time`.
- `created_at` is persistence time and cannot be used as market availability.
- Future outcomes may only be attached through a separate outcome aggregate.
- Corrections create a new aggregate with `supersedes`; the original remains queryable.

## Validation and error codes

| Code | Name | Condition |
|---|---|---|
| `DRS-001` | `REFERENCE_AFTER_DECISION_TIME` | A referenced artifact was not available by decision_time. |
| `DRS-002` | `BLOCKED_WITH_PREDICTIONS` | Blocked snapshot contains prediction runs. |
| `DRS-003` | `EVIDENCE_LEVEL_INFLATION` | Snapshot evidence exceeds a required input. |
| `DRS-004` | `SESSION_IDENTITY_MISMATCH` | Decision date/time and market session disagree. |

Common `DOCON-*` errors from [Error Catalog](Error-Catalog.md) also apply.

## Persistence mapping

Target mapping, not current implementation fact:

```text
PostgreSQL table: phase_d_daily_research_snapshots
Primary logical key: aggregate ID
Immutable JSON column: payload_json
Indexed columns: schema_version, decision/as_of time, referenced root IDs, disposition/status
Object-store mirror: artifacts/phase-d/DailyResearchSnapshot/<yyyy-mm-dd>/<content_hash>.json
```

Rows are append-only. A correction inserts a new row and sets `supersedes`; no update mutates a result-affecting payload.

## API mapping

```text
GET  /api/v1/daily-research-snapshots/{id}
GET  /api/v1/daily-research-snapshots?decision_date={date}&cursor={cursor}
POST /api/v1/daily-research-snapshots/validate
```

Only domains that own human-entered records may expose a create command. Computed aggregates are created by internal commands and exposed read-only through HTTP.

Responses include `ETag: "<content_hash>"`. Clients must use cursor pagination and must not reconstruct canonical decisions from projections.

## Full JSON example

```json
{
  "snapshot_id": "drs_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "schema_version": "1.0.0",
  "decision_date": "2026-07-27",
  "decision_time": "2026-07-27T14:50:00+08:00",
  "timezone": "Asia/Shanghai",
  "market_session_id": "session_sse_20260727",
  "calendar_artifact_id": "art_calendar_20260727",
  "source_manifest_id": "srcm_20260727_1450",
  "universe_snapshot_id": "univ_a_share_liquid_20260727",
  "eligibility_snapshot_id": "elig_20260727_1450",
  "context_refs": {
    "market": "mktctx_20260727_1450",
    "etf": "etfctx_20260727_1450",
    "theme": "themectx_20260727_1450",
    "capital": "capctx_20260727_1450"
  },
  "feature_matrix_id": "fm_20260727_1450",
  "candidate_prediction_run_ids": [
    "pred_b0_20260727",
    "pred_b1_20260727"
  ],
  "entry_assessment_run_ids": [],
  "position_snapshot_id": null,
  "experiment_protocol_ids": [
    "exp_candidate_lane_v1"
  ],
  "evidence_level": "EXPLORATORY",
  "disposition": "AVAILABLE",
  "data_quality_grade": "B",
  "supersedes": null,
  "created_at": "2026-07-27T06:51:12Z",
  "content_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
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

Legacy fields may be exposed through an adapter only after characterization
tests prove semantic compatibility. The adapter records its source identity and
cannot increase evidence authority. The binding V1 freeze, field matrix and
blocked-migration rules are defined in
[ADR-Daily-Research-Contract-Convergence](../architecture/decisions/ADR-Daily-Research-Contract-Convergence.md).
