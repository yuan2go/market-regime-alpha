# CandidateRecommendation

> **Status:** CURRENT_SPECIFICATION  
> **Authority:** Phase D contract specification for CandidateRecommendation  
> **Owner:** Candidate Discovery domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, Contract-Conventions.md, Error-Catalog.md, ../architecture/05-Phase-D-Daily-Decision-Engine-V1.md  
> **Code Evidence:** DESIGNED_ONLY; implementation evidence must update docs/status/Capability-Matrix.md

## Purpose

Project one immutable CandidatePrediction into an explainable decision-support record without creating Entry or trade authority.

## Owner and authority

The **Candidate Discovery domain** owns this aggregate. Adjacent domains reference it by immutable identity and may not rewrite its fields.

## Inputs

- identified upstream artifact references;
- timezone-aware semantic times;
- exact model/config/code identities where applicable;
- explicit data quality and evidence authority;
- the registered schema version and validation policy.

## Outputs

- one immutable `CandidateRecommendation` JSON document;
- a canonical content hash and prefixed aggregate ID;
- persistence/API representations that preserve identical semantics;
- machine-readable validation errors when construction fails.

## Schema V1

| Field | Type | Presence | Nullable | Enum | Validation | Meaning |
|---|---|---|---|---|---|---|
| `recommendation_id` | `string` | required | no | — | ^candrec_[a-f0-9]{64}$ | Content-addressed ID. |
| `schema_version` | `string` | required | no | — | semantic version | Schema version. |
| `snapshot_id` | `string` | required | no | — | existing DailyResearchSnapshot | Daily root. |
| `prediction_run_id` | `string` | required | no | — | existing complete prediction run | Authoritative full ranking ledger. |
| `symbol` | `string` | required | no | — | canonical instrument ID | Instrument. |
| `instrument_type` | `string` | required | no | `STOCK`, `ETF` | exact enum | Instrument class. |
| `rank` | `integer` | required | no | — | >=1 | Rank in complete eligible population. |
| `score` | `number` | required | no | — | finite | Model output. |
| `score_type` | `string` | required | no | `RAW_SCORE`, `STANDARDIZED_SCORE`, `CALIBRATED_PROBABILITY` | exact enum | Prevents score/probability conflation. |
| `calibration_id` | `string` | optional | yes | — | existing calibration or null | Required only for CALIBRATED_PROBABILITY. |
| `score_components` | `object` | required | no | — | finite numeric values | Versioned component contributions. |
| `selection_reason_codes` | `array[string]` | required | no | — | registered codes | Machine-readable reasons. |
| `risk_reason_codes` | `array[string]` | required | no | — | registered codes | Machine-readable risks. |
| `industry_id` | `string` | optional | yes | — | PIT mapping or null | Industry identity. |
| `theme_ids` | `array[string]` | required | no | — | sorted unique | PIT themes. |
| `related_etf_ids` | `array[string]` | required | no | — | sorted unique | Mapped ETFs. |
| `expected_horizon` | `string` | required | no | — | registered horizon | Prediction horizon, not holding rule. |
| `target_id` | `string` | required | no | — | registered target | Prediction objective. |
| `model_id` | `string` | required | no | — | registered model | Model identity. |
| `model_version` | `string` | required | no | — | immutable version | Model version. |
| `data_quality_grade` | `string` | required | no | `A`, `B`, `C`, `BLOCKED` | exact enum | Input quality. |
| `evidence_level` | `string` | required | no | `UNQUALIFIED`, `EXPLORATORY`, `REHEARSAL`, `FORMAL_RESEARCH`, `SHADOW_EVIDENCE` | exact enum | Authority ceiling. |
| `disposition` | `string` | required | no | `RECOMMENDED`, `OBSERVE`, `NO_ACTION`, `INSUFFICIENT_EVIDENCE`, `DATA_BLOCKED` | exact enum | Presentation disposition, not Entry. |
| `expires_at` | `datetime` | required | no | — | > decision_time | Recommendation validity end. |
| `content_hash` | `string` | required | no | — | 64 lowercase hex | Identity digest. |

## Required/optional and null rules

- `required` means the key must be present even when its value is explicitly `null`.
- `optional` means the key may be absent; producers should prefer explicit null when absence is semantically meaningful.
- Null is never used to mean zero, false, empty population or successful computation.
- Action/status-specific nullability is validated by the error rules below.
- Unknown enum values fail validation; clients must not silently coerce them.

## Identity canonicalization

The common algorithm is defined in [Contract Conventions](Contract-Conventions.md). The identity payload for `CandidateRecommendation` contains:

- `schema_version`
- `snapshot_id`
- `prediction_run_id`
- `symbol`
- `instrument_type`
- `rank`
- `score`
- `score_type`
- `calibration_id`
- `score_components`
- `selection_reason_codes`
- `risk_reason_codes`
- `industry_id`
- `theme_ids`
- `related_etf_ids`
- `expected_horizon`
- `target_id`
- `model_id`
- `model_version`
- `data_quality_grade`
- `evidence_level`
- `disposition`
- `expires_at`

The `content_hash` field itself, transport metadata and database-generated row IDs are excluded. The public aggregate ID is:

```text
candrec_<sha256(identity_payload)>
```

## Time and PIT rules

- Every referenced input must have `available_time <= decision/as_of time`.
- `created_at` is persistence time and cannot be used as market availability.
- Future outcomes may only be attached through a separate outcome aggregate.
- Corrections create a new aggregate with `supersedes`; the original remains queryable.

## Validation and error codes

| Code | Name | Condition |
|---|---|---|
| `CAN-001` | `PROBABILITY_WITHOUT_CALIBRATION` | Probability score lacks calibration identity. |
| `CAN-002` | `RANK_NOT_IN_LEDGER` | Rank/symbol does not match complete prediction run. |
| `CAN-003` | `ACTION_FIELD_FORBIDDEN` | Candidate contains Entry/Exit/trade action. |
| `CAN-004` | `MAPPING_NOT_PIT` | Industry/theme/ETF mapping is not PIT-qualified. |

Common `DOCON-*` errors from [Error Catalog](Error-Catalog.md) also apply.

## Persistence mapping

Target mapping, not current implementation fact:

```text
PostgreSQL table: phase_d_candidate_recommendations
Primary logical key: aggregate ID
Immutable JSON column: payload_json
Indexed columns: schema_version, decision/as_of time, referenced root IDs, disposition/status
Object-store mirror: artifacts/phase-d/CandidateRecommendation/<yyyy-mm-dd>/<content_hash>.json
```

Rows are append-only. A correction inserts a new row and sets `supersedes`; no update mutates a result-affecting payload.

## API mapping

```text
GET  /api/v1/candidate-recommendations/{id}
GET  /api/v1/candidate-recommendations?decision_date={date}&cursor={cursor}
POST /api/v1/candidate-recommendations/validate
```

Only domains that own human-entered records may expose a create command. Computed aggregates are created by internal commands and exposed read-only through HTTP.

Responses include `ETag: "<content_hash>"`. Clients must use cursor pagination and must not reconstruct canonical decisions from projections.

## Full JSON example

```json
{
  "recommendation_id": "candrec_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
  "schema_version": "1.0.0",
  "snapshot_id": "drs_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "prediction_run_id": "pred_b1_20260727",
  "symbol": "600519.SH",
  "instrument_type": "STOCK",
  "rank": 3,
  "score": 0.714,
  "score_type": "STANDARDIZED_SCORE",
  "calibration_id": null,
  "score_components": {
    "momentum": 0.43,
    "volume_expansion": 0.21,
    "low_volatility": 0.074
  },
  "selection_reason_codes": [
    "MOMENTUM_TOP_DECILE",
    "VOLUME_EXPANDING"
  ],
  "risk_reason_codes": [
    "THEME_CONCENTRATION_MEDIUM"
  ],
  "industry_id": "sw_food_beverage_v20260727",
  "theme_ids": [
    "theme_consumer"
  ],
  "related_etf_ids": [
    "510150.SH"
  ],
  "expected_horizon": "NEXT_SESSION_1030",
  "target_id": "R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_V1",
  "model_id": "platform-b1-balanced",
  "model_version": "1.0.0",
  "data_quality_grade": "B",
  "evidence_level": "EXPLORATORY",
  "disposition": "RECOMMENDED",
  "expires_at": "2026-07-27T15:00:00+08:00",
  "content_hash": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
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
