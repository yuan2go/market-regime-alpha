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

Test fixtures must carry `TEST_ONLY_NOT_RESEARCH_EVIDENCE` and are rejected by the formal preflight.
