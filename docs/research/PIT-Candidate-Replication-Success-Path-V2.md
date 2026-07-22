# PIT Candidate Replication Success Path V2

> **Status:** IMPLEMENTED; FORMAL EXECUTION BLOCKED BY MISSING XUNTOU V4 INPUT
>
> **Authority ceiling:** `REHEARSAL_NOT_FORMAL_OOS`

The success path accepts only evidence that passes `xuntou-pit-validation-bundle-v4` preflight.
It never promotes v3 rehearsal data, falls back to Tencent, or treats a test fixture as research
evidence.

## Pipeline

```text
qualified v4 evidence
→ explicit Validation partition specification
→ independently persisted immutable partition seal
→ exclusive-create first-open receipt
→ PIT Universe ∩ ELIGIBLE ∩ RESEARCH_ORDERABLE population
→ persisted Feature evidence
→ reconstructed frozen B1-E scores, complete-case model population, and rankings
→ 256-seed, same-population matched-K comparison
→ exact next-session 10:30 returns and frozen costs
→ chronological assessment
→ immutable success Artifact
→ semantic Reader reconstruction
```

Ranking Target, evaluation mark, and path Targets have separate versioned identities. Missing exact
10:30 evidence cannot fall back to daily close. Missing minute path evidence produces
`PATH_DIAGNOSTICS_UNAVAILABLE` and cannot change the primary assessment.

The formal runner stores partition governance under `.pit-validation-partitions/<partition-id>`
before B1-E scoring. The seal is content-addressed; the first-open receipt is created with exclusive
filesystem semantics. A failed run therefore leaves enough evidence to reject resealing or reopening
the same partition ID. The final success Artifact embeds both records but does not mutate them.

The qualified provider Artifact ID is taken only from the v4 semantic preflight and is reconstructed
from source-content and qualification identities by the success Reader. Universe, Eligibility, and
Orderability rows must share an exact scope; the Candidate Population is rebuilt from their
intersection and its row identities must match exactly. Raw input projections, including path
diagnostics, are bound into the content-addressed Run identity.

Formal materialization additionally requires `pit-replication-input-projection-v2`. Its exact field
set binds the qualified provider Artifact ID, source-content hash, raw-source hash map, every v4
evidence-section hash, and the complete projected payload. A caller-supplied non-test success input
or an unbound `replication_payload` is rejected before partition sealing.

Chronological output includes predeclared monthly and quarterly descriptive slices, population-size
slices, Feature completeness, Top-5 turnover, cost robustness, seed-panel stability, concentration,
and leave-one-date-out diagnostics. Liquidity slices are explicitly `UNAVAILABLE` unless the
Candidate rows persist the qualified liquidity evidence required to calculate them.

## Test-only evidence

The complete success branch is exercised with `TEST_ONLY_NOT_RESEARCH_EVIDENCE` fixtures. Those
runs use a distinct `test-only-pit-replication-v2-*` identity and cannot receive rehearsal or OOS
authority. Semantic tests alter Feature values, B1-E weights, ranks, selections, returns, costs,
provider input projections, evaluation marks, and partition evidence while rewriting checksums; the
Reader rejects each case. Explicitly missing Features remain outside the model population rather
than inflating the same-population matched-K comparator.

## Actual execution

No qualified Xuntou v4 bundle or XtQuant runtime is available locally. The formal CLI therefore
published verified blocker `pit-replication-v2-4985eec50a6c63ecf536` with no partition seal, first
open, Candidate metrics, or research result.

```text
FORMAL OOS ALPHA NOT ESTABLISHED
MODEL WINNER NOT SELECTED
NO MARKET REGIME GATE
NO TRADING AUTHORITY
```
