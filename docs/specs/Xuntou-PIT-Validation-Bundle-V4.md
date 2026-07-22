# Xuntou PIT Validation Bundle V4

> **Schema:** `xuntou-pit-validation-bundle-v4`
> **Authority ceiling:** `CONTROLLED_REPLICATION_INPUT`
> **Status:** contract implemented; real input unavailable

V4 is a new evidence contract. `xuntou-p0-native-bundle-v3` remains REHEARSAL and can never be
renamed, self-declared, or limitation-stripped into V4.

## Required source identity

The export records provider/product, contract version, retrieval/export timestamps, SHA-256 source
bytes, a non-semantic locator role, redacted entitlement class, runtime/XtQuant versions, and
`Asia/Shanghai`. Sensitive account identifiers are excluded.

## Required evidence domains

- effective-dated security master with listing/delisting and availability evidence;
- complete historical membership snapshots, including explicit lookup completeness;
- ST/*ST/PT intervals with effective and availability times;
- decision-time suspension/trading status;
- 14:55 quote/order-book evidence and a derived `RESEARCH_ORDERABLE`, `NOT_ORDERABLE`, or `UNKNOWN`;
- explicit amount currency/unit/scale/aggregation/adjustment contract;
- raw, unadjusted bars with observed, available, finalized, and revision identities;
- versioned completed-bar convention for the 14:55 research mark;
- next-session 09:30–10:30 minute path and an exact 10:30 evaluation mark;
- a complete minute path before any first-hit/MFE/MAE ordering diagnostic is enabled.

`RESEARCH_ORDERABLE` means only that frozen decision-time evidence permits a simulated normal buy
intent. It is not historical fill proof, queue priority, or a slippage guarantee.

## Qualification

`pit_correct_for_scope` is derived by the project validator. Input declarations are ignored. Every
required domain must be complete; current-membership backfill, late availability, unknown quote,
ambiguous amount units, incomplete finality, or missing 10:30 minute evidence fails closed.

The normalized bundle must contain all of these code-owned fields:

```text
schema_version
mapping_contract_id
conventions {
  completed 1m END_TIME label at 14:55,
  60-second freshness,
  Decision-Time availability cutoff,
  exact next-session 10:30 close mark,
  complete 1m 09:30-through-10:30 path
}
source_artifact
raw_source_hashes
evidence_scope { decision_times, symbols }
evidence_sections {
  historical_membership,
  security_master,
  st_history,
  suspension_history,
  orderability,
  liquidity_unit,
  bar_finality,
  availability,
  evaluation_path
}
```

Every evidence section contains `records` and a canonical `content_hash` of those records. The
source Artifact content hash is the canonical identity of the sorted raw-source hash map. The
validator verifies exact Decision-Time/symbol coverage where applicable, recomputes orderability,
checks amount units, availability/finality, requires a finalized 14:55 Decision-Time bar, and
reconstructs every 1-minute label from 09:30 through the exact next-session 10:30 mark.
`qualification_inputs` booleans have no authority and are not read by the v4 preflight.

When all evidence qualifies, the preflight derives `QualifiedPITMarketArtifact.provider_artifact_id`
from the source content hash and qualification receipt. A bundle-supplied provider Artifact ID is
not authoritative.

Test fixtures must carry `TEST_ONLY_NOT_RESEARCH_EVIDENCE` and are rejected by the formal preflight.
