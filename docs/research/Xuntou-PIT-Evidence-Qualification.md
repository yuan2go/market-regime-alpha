# Xuntou PIT Evidence Qualification

> **Status:** IMPLEMENTED CONTRACT / EXTERNAL INPUT BLOCKED

The qualification receipt is derived from nine independent requirements: historical membership,
security master, ST history, suspension history, decision-time orderability, verified amount unit,
bar finality, availability, and next-session evaluation path. `pit_correct_for_scope` is true only
when all nine are true and no current-membership backfill is present.

Each requirement is derived from a content-addressed evidence section over an explicit
Decision-Time × symbol scope. A nine-boolean `qualification_inputs` summary cannot produce
`AVAILABLE`. Successful qualification also derives the `QualifiedPITMarketArtifact` identity; the
input cannot self-assign that identity or its authority.

The current macOS probe reports `EXTERNAL_XTQUANT_RUNTIME_REQUIRED`. Historical membership, quote,
ST, suspension, price-limit, timezone, and finality semantics remain `UNVERIFIED`; no research
evidence was produced.

The V4 preflight outcomes are:

- `AVAILABLE` only for evidence-derived qualification;
- `BLOCKED_EXTERNAL_PROVIDER_INPUT` when the authorized external input/runtime is absent;
- `INVALID_PIT_EVIDENCE` for malformed, v3-promoted, or test-only input;
- `INSUFFICIENT_PROVIDER_CAPABILITY` when structurally V4 input lacks a required qualified domain.

There is no Tencent fallback. V3 remains REHEARSAL. No Alpha, model-winner, production, or trading
authority is created.
