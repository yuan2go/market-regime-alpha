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

The current v3 run is `mr2b-f2b-v3-11899de582c7a5ee0ee6`, using Dataset
`prr-dataset-fa40337727427b2f1ff63548`, MR-1 `mr1-c06821bf7db2dc787244`, and F2A
`mr2b-f2a-99cd5a71a92fa5eb0366`. It also binds verified v2 run
`mr2b-f2b-v2-3bc505b9e92138ffa2f8`, its checksum identity, and its semantic-projection hash into the
v3 Run ID. The earlier v3 run `mr2b-f2b-v3-bb34b06f7446aa0af9e7` remains historical evidence but
is superseded for current identity authority because its v2 comparison was not identity-bound.

`v2_vs_v3_semantic_diff.json` reports `EXACT_MATCH`: UP 27, DOWN 33, observed effect
`-0.0000844753476525215`, bootstrap 95% interval
`[-0.002375137060807993, 0.0023412463545652395]`, circular-shift p-value `0.5`, and
`PRIMARY_HYPOTHESIS_NOT_SUPPORTED`. The identity/Reader contract changed; the frozen statistical
meaning did not.

The current missing-provider PIT v2 evidence is
`pit-replication-v2-21c5fb99c1dac32565e0` with status
`BLOCKED_EXTERNAL_PROVIDER_INPUT`. It produced no replication result.

The PIT v2 Reader now requires an exact manifest field set, code-owned authority constants, and a
full preflight hash plus the versioned v3/v4 provider contract. Checksum-valid edits cannot promote
provider, data eligibility, authority, product, membership source, provider Dataset identity, or
Tencent fallback semantics.

## Authority boundary

This migration establishes byte and semantic identity. It does not establish Formal OOS Alpha,
select a model winner, restore the rejected auxiliary-watchlist Gate, or grant trading authority.
