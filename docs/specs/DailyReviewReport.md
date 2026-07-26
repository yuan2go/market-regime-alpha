# DailyReviewReport

> **Status:** CURRENT_SPECIFICATION  
> **Authority:** Phase D contract specification for DailyReviewReport  
> **Owner:** Review and Attribution domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, Contract-Conventions.md, Error-Catalog.md, ../architecture/05-Phase-D-Daily-Decision-Engine-V1.md  
> **Code Evidence:** DESIGNED_ONLY; implementation evidence must update docs/status/Capability-Matrix.md

## Purpose

Aggregate immutable daily facts, layer-specific metrics, failures and controlled research proposals.

## Owner and authority

The **Review and Attribution domain** owns this aggregate. Adjacent domains reference it by immutable identity and may not rewrite its fields.

## Inputs

- identified upstream artifact references;
- timezone-aware semantic times;
- exact model/config/code identities where applicable;
- explicit data quality and evidence authority;
- the registered schema version and validation policy.

## Outputs

- one immutable `DailyReviewReport` JSON document;
- a canonical content hash and prefixed aggregate ID;
- persistence/API representations that preserve identical semantics;
- machine-readable validation errors when construction fails.

## Schema V1

| Field | Type | Presence | Nullable | Enum | Validation | Meaning |
|---|---|---|---|---|---|---|
| `report_id` | `string` | required | no | — | ^review_[a-f0-9]{64}$ | Content-addressed ID. |
| `schema_version` | `string` | required | no | — | semantic version | Schema version. |
| `review_date` | `date` | required | no | — | ISO-8601 | Review date. |
| `snapshot_id` | `string` | required | no | — | existing DailyResearchSnapshot | Daily root. |
| `data_quality_review` | `object` | required | no | — | typed section | Data facts and blocked items. |
| `candidate_review` | `object` | required | no | — | typed section | Candidate metrics. |
| `etf_review` | `object` | required | yes | — | typed section or null | ETF metrics when in scope. |
| `theme_review` | `object` | required | yes | — | typed section or null | Theme metrics when in scope. |
| `entry_review` | `object` | required | yes | — | typed section or null | Entry metrics when in scope. |
| `holding_review` | `object` | required | yes | — | typed section or null | Holding metrics when positions exist. |
| `exit_review` | `object` | required | yes | — | typed section or null | Exit metrics when positions exist. |
| `risk_review` | `object` | required | no | — | typed section | Risk observations. |
| `manual_execution_review` | `object` | required | yes | — | typed section or null | Execution/deviation metrics. |
| `failure_attribution_ids` | `array[string]` | required | no | — | sorted unique | Versioned failure records. |
| `rolling_20d_scorecard_id` | `string` | optional | yes | — | artifact or null | Provisional diagnostics. |
| `rolling_60d_scorecard_id` | `string` | optional | yes | — | artifact or null | Governance evidence. |
| `facts` | `array[object]` | required | no | — | evidence references required | Direct observations. |
| `inferences` | `array[object]` | required | no | — | confidence + supporting facts | Interpretations. |
| `hypotheses` | `array[object]` | required | no | — | falsifiable + counter-evidence | Research hypotheses. |
| `codex_proposal_ids` | `array[string]` | required | no | — | sorted unique | Proposals only; no automatic mutation. |
| `created_at` | `datetime` | required | no | — | RFC3339 UTC | Persistence time. |
| `content_hash` | `string` | required | no | — | 64 lowercase hex | Identity digest. |

## Required/optional and null rules

- `required` means the key must be present even when its value is explicitly `null`.
- `optional` means the key may be absent; producers should prefer explicit null when absence is semantically meaningful.
- Null is never used to mean zero, false, empty population or successful computation.
- Action/status-specific nullability is validated by the error rules below.
- Unknown enum values fail validation; clients must not silently coerce them.

## Identity canonicalization

The common algorithm is defined in [Contract Conventions](Contract-Conventions.md). The identity payload for `DailyReviewReport` contains:

- `schema_version`
- `review_date`
- `snapshot_id`
- `data_quality_review`
- `candidate_review`
- `etf_review`
- `theme_review`
- `entry_review`
- `holding_review`
- `exit_review`
- `risk_review`
- `manual_execution_review`
- `failure_attribution_ids`
- `rolling_20d_scorecard_id`
- `rolling_60d_scorecard_id`
- `facts`
- `inferences`
- `hypotheses`
- `codex_proposal_ids`

The `content_hash` field itself, transport metadata and database-generated row IDs are excluded. The public aggregate ID is:

```text
review_<sha256(identity_payload)>
```

## Time and PIT rules

- Every referenced input must have `available_time <= decision/as_of time`.
- `created_at` is persistence time and cannot be used as market availability.
- Future outcomes may only be attached through a separate outcome aggregate.
- Corrections create a new aggregate with `supersedes`; the original remains queryable.

## Validation and error codes

| Code | Name | Condition |
|---|---|---|
| `REV-001` | `FACT_WITHOUT_EVIDENCE` | Fact lacks artifact/data reference. |
| `REV-002` | `HYPOTHESIS_IN_FACT_SECTION` | Hypothesis is presented as fact. |
| `REV-003` | `MODEL_MUTATION_ATTEMPT` | Report attempts model mutation/promotion. |
| `REV-004` | `LAYER_METRIC_CONFLATION` | Candidate/Entry/Exit/Execution effects are not separated. |

Common `DOCON-*` errors from [Error Catalog](Error-Catalog.md) also apply.

## Persistence mapping

Target mapping, not current implementation fact:

```text
PostgreSQL table: phase_d_daily_review_reports
Primary logical key: aggregate ID
Immutable JSON column: payload_json
Indexed columns: schema_version, decision/as_of time, referenced root IDs, disposition/status
Object-store mirror: artifacts/phase-d/DailyReviewReport/<yyyy-mm-dd>/<content_hash>.json
```

Rows are append-only. A correction inserts a new row and sets `supersedes`; no update mutates a result-affecting payload.

## API mapping

```text
GET  /api/v1/daily-review-reports/{id}
GET  /api/v1/daily-review-reports?decision_date={date}&cursor={cursor}
POST /api/v1/daily-review-reports/validate
```

Only domains that own human-entered records may expose a create command. Computed aggregates are created by internal commands and exposed read-only through HTTP.

Responses include `ETag: "<content_hash>"`. Clients must use cursor pagination and must not reconstruct canonical decisions from projections.

## Full JSON example

```json
{
  "report_id": "review_6666666666666666666666666666666666666666666666666666666666666666",
  "schema_version": "1.0.0",
  "review_date": "2026-07-28",
  "snapshot_id": "drs_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "data_quality_review": {
    "grade": "B",
    "blocked_fields": []
  },
  "candidate_review": {
    "top_k_relative_return": 0.012,
    "coverage": 0.98
  },
  "etf_review": null,
  "theme_review": null,
  "entry_review": {
    "enter_count": 0,
    "wait_count": 1
  },
  "holding_review": null,
  "exit_review": null,
  "risk_review": {
    "theme_concentration": "MEDIUM"
  },
  "manual_execution_review": {
    "executed": 1,
    "plan_followed": false
  },
  "failure_attribution_ids": [],
  "rolling_20d_scorecard_id": null,
  "rolling_60d_scorecard_id": null,
  "facts": [
    {
      "code": "TOPK_OUTPERFORMED_TODAY",
      "evidence_id": "outcome_5555555555555555555555555555555555555555555555555555555555555555"
    }
  ],
  "inferences": [
    {
      "statement": "Recent volume expansion may be useful.",
      "confidence": "LOW",
      "supporting_fact_codes": [
        "TOPK_OUTPERFORMED_TODAY"
      ]
    }
  ],
  "hypotheses": [
    {
      "hypothesis_id": "hyp_volume_increment_001",
      "statement": "Volume expansion improves B1 after costs.",
      "invalidation": "No matched-K excess over 60 sessions."
    }
  ],
  "codex_proposal_ids": [
    "proposal_volume_ablation_001"
  ],
  "created_at": "2026-07-28T08:00:00Z",
  "content_hash": "6666666666666666666666666666666666666666666666666666666666666666"
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
