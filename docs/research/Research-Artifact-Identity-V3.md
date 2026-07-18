# Research Artifact Identity V3

> **Status:** IMPLEMENTED
> **Authority:** EXPLORATORY evidence integrity only

## Why v3 exists

F2B v2 remains immutable historical evidence, but its Reader allowed an Artifact to choose the
implementation-module keys that would be revalidated. Its identity also included the extensible
verifier registry even though registry routing does not participate in statistical computation.

F2B v3 corrects both boundaries without modifying the frozen v1/v2 modules:

- code owns the exact seven-module statistical implementation set;
- missing, empty, and extra implementation hashes fail closed;
- the cross-version registry is excluded from statistical identity;
- v1, v2, and v3 route to their own semantic Readers;
- PIT blocked and invalid evidence use distinct v2 Schemas and exact file sets.

## Actual evidence

The actual v3 run is `mr2b-f2b-v3-bb34b06f7446aa0af9e7`, using Dataset
`prr-dataset-fa40337727427b2f1ff63548`, MR-1 `mr1-c06821bf7db2dc787244`, and F2A
`mr2b-f2a-99cd5a71a92fa5eb0366`.

`v2_vs_v3_semantic_diff.json` reports `EXACT_MATCH`: UP 27, DOWN 33, observed effect
`-0.0000844753476525215`, bootstrap 95% interval
`[-0.002375137060807993, 0.0023412463545652395]`, circular-shift p-value `0.5`, and
`PRIMARY_HYPOTHESIS_NOT_SUPPORTED`. The identity/Reader contract changed; the frozen statistical
meaning did not.

The actual missing-provider PIT v2 evidence is
`pit-replication-v2-c681ed11199027ea819d` with status
`BLOCKED_EXTERNAL_PROVIDER_INPUT`. It produced no replication result.

## Authority boundary

This migration establishes byte and semantic identity. It does not establish Formal OOS Alpha,
select a model winner, restore the rejected auxiliary-watchlist Gate, or grant trading authority.
