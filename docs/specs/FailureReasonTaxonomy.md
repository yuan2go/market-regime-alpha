# FailureReasonTaxonomy

> **Status:** CURRENT_SPECIFICATION  
> **Authority:** Phase D contract specification for FailureReasonTaxonomy  
> **Owner:** Review and Governance domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, Contract-Conventions.md, Error-Catalog.md, ../architecture/05-Phase-D-Daily-Decision-Engine-V1.md  
> **Code Evidence:** DESIGNED_ONLY; implementation evidence must update docs/status/Capability-Matrix.md

## Purpose

Version hierarchical, evidence-bound failure codes used by daily review and research governance.

## Owner and authority

The **Review and Governance domain** owns this aggregate. Adjacent domains reference it by immutable identity and may not rewrite its fields.

## Inputs

- identified upstream artifact references;
- timezone-aware semantic times;
- exact model/config/code identities where applicable;
- explicit data quality and evidence authority;
- the registered schema version and validation policy.

## Outputs

- one immutable `FailureReasonTaxonomy` JSON document;
- a canonical content hash and prefixed aggregate ID;
- persistence/API representations that preserve identical semantics;
- machine-readable validation errors when construction fails.

## Schema V1

| Field | Type | Presence | Nullable | Enum | Validation | Meaning |
|---|---|---|---|---|---|---|
| `taxonomy_id` | `string` | required | no | — | ^ftax_[a-f0-9]{64}$ | Content-addressed taxonomy. |
| `schema_version` | `string` | required | no | — | semantic version | Schema version. |
| `taxonomy_version` | `string` | required | no | — | semantic version | Business taxonomy version. |
| `effective_from` | `datetime` | required | no | — | RFC3339 | First allowed use. |
| `status` | `string` | required | no | `DRAFT`, `ACTIVE`, `RETIRED` | exact enum | Lifecycle state. |
| `codes` | `array[FailureCode]` | required | no | — | unique failure_code | Complete definitions. |
| `supersedes` | `string` | optional | yes | — | previous taxonomy or null | Version lineage. |
| `created_at` | `datetime` | required | no | — | RFC3339 UTC | Persistence time. |
| `content_hash` | `string` | required | no | — | 64 lowercase hex | Identity digest. |

### `FailureCode`

| Field | Type | Presence | Nullable | Enum | Validation | Meaning |
|---|---|---|---|---|---|---|
| `failure_code` | `string` | required | no | — | ^[A-Z][A-Z0-9_]{2,63}$ | Stable code. |
| `domain` | `string` | required | no | `DATA`, `UNIVERSE`, `FEATURE`, `MODEL`, `CANDIDATE`, `ENTRY`, `POSITION`, `HOLDING`, `EXIT`, `PORTFOLIO`, `EXECUTION`, `REVIEW`, `AI` | exact enum | Owning domain. |
| `description` | `string` | required | no | — | non-empty | Operational definition. |
| `required_evidence` | `array[string]` | required | no | — | non-empty for attributable codes | Evidence types. |
| `exclusion_rules` | `array[string]` | required | no | — | registered rules | Conditions that prevent assignment. |
| `parent_code` | `string` | optional | yes | — | existing code or null | Hierarchy. |
| `severity` | `string` | required | no | `INFO`, `WARNING`, `ERROR`, `BLOCKING` | exact enum | Operational severity. |
| `retryable` | `boolean` | required | no | — | true/false | Whether the run may retry after correction. |

## Required/optional and null rules

- `required` means the key must be present even when its value is explicitly `null`.
- `optional` means the key may be absent; producers should prefer explicit null when absence is semantically meaningful.
- Null is never used to mean zero, false, empty population or successful computation.
- Action/status-specific nullability is validated by the error rules below.
- Unknown enum values fail validation; clients must not silently coerce them.

## Identity canonicalization

The common algorithm is defined in [Contract Conventions](Contract-Conventions.md). The identity payload for `FailureReasonTaxonomy` contains:

- `schema_version`
- `taxonomy_version`
- `effective_from`
- `status`
- `codes`
- `supersedes`

The `content_hash` field itself, transport metadata and database-generated row IDs are excluded. The public aggregate ID is:

```text
ftax_<sha256(identity_payload)>
```

## Time and PIT rules

- Every referenced input must have `available_time <= decision/as_of time`.
- `created_at` is persistence time and cannot be used as market availability.
- Future outcomes may only be attached through a separate outcome aggregate.
- Corrections create a new aggregate with `supersedes`; the original remains queryable.

## Validation and error codes

| Code | Name | Condition |
|---|---|---|
| `FTX-001` | `DUPLICATE_CODE` | Failure code is duplicated. |
| `FTX-002` | `UNKNOWN_PARENT` | parent_code does not exist. |
| `FTX-003` | `HIERARCHY_CYCLE` | Parent graph contains a cycle. |
| `FTX-004` | `ATTRIBUTION_WITHOUT_EVIDENCE` | Code requires evidence that is absent. |

Common `DOCON-*` errors from [Error Catalog](Error-Catalog.md) also apply.

## Persistence mapping

Target mapping, not current implementation fact:

```text
PostgreSQL table: phase_d_failure_reason_taxonomies
Primary logical key: aggregate ID
Immutable JSON column: payload_json
Indexed columns: schema_version, decision/as_of time, referenced root IDs, disposition/status
Object-store mirror: artifacts/phase-d/FailureReasonTaxonomy/<yyyy-mm-dd>/<content_hash>.json
```

Rows are append-only. A correction inserts a new row and sets `supersedes`; no update mutates a result-affecting payload.

## API mapping

```text
GET  /api/v1/failure-reason-taxonomies/{id}
GET  /api/v1/failure-reason-taxonomies?decision_date={date}&cursor={cursor}
POST /api/v1/failure-reason-taxonomies/validate
```

Only domains that own human-entered records may expose a create command. Computed aggregates are created by internal commands and exposed read-only through HTTP.

Responses include `ETag: "<content_hash>"`. Clients must use cursor pagination and must not reconstruct canonical decisions from projections.

## Full JSON example

```json
{
  "taxonomy_id": "ftax_7777777777777777777777777777777777777777777777777777777777777777",
  "schema_version": "1.0.0",
  "taxonomy_version": "1.0.0",
  "effective_from": "2026-07-27T00:00:00+08:00",
  "status": "ACTIVE",
  "codes": [
    {
      "failure_code": "DATA_STALE",
      "domain": "DATA",
      "description": "A mandatory input exceeded its declared freshness SLA.",
      "required_evidence": [
        "source_manifest",
        "freshness_check"
      ],
      "exclusion_rules": [
        "FIELD_OPTIONAL_AND_UNUSED"
      ],
      "parent_code": null,
      "severity": "BLOCKING",
      "retryable": true
    },
    {
      "failure_code": "MODEL_NO_INCREMENT",
      "domain": "MODEL",
      "description": "A challenger failed its predeclared incremental metric.",
      "required_evidence": [
        "evaluation_run",
        "parent_comparator"
      ],
      "exclusion_rules": [],
      "parent_code": null,
      "severity": "WARNING",
      "retryable": false
    }
  ],
  "supersedes": null,
  "created_at": "2026-07-26T16:00:00Z",
  "content_hash": "7777777777777777777777777777777777777777777777777777777777777777"
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
