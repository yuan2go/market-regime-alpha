# MR-2B-F2A Exact-Context and Multi-Seed Conditionality Inputs

## Authority and scope

MR-2B-F2A produces `EXPLORATORY CONDITIONALITY INPUT EVIDENCE`. It does not run a
moving-block bootstrap, permute Context labels, promote a primary or secondary hypothesis,
select a model, or establish Formal OOS Alpha.

The immutable inputs are:

- Dataset `prr-dataset-fa40337727427b2f1ff63548`;
- verified MR-1 v4 run `mr1-c06821bf7db2dc787244`;
- the fixed nine B0/B1 models, four endpoints, three cost scenarios, and Top-5 policy.

## Exact 14:50 auxiliary-watchlist Context

Context schema `mr-2b-auxiliary-watchlist-context-v1` uses the accepted auxiliary watchlist,
not any model population and not the A-share market. The definition
`mr2b-accepted-watchlist-exact-1450-context-v1` requires every accepted symbol to have the
canonical 46 end-labelled bars:

```text
09:35–11:30 every five minutes
13:05–14:50 every five minutes
```

It requires the same prior-session cutoff grid and the prior 15:00 close. The exact 14:50 close
is the current reference; 14:55 and 15:00 bars are excluded. Amount change compares today and
the prior session through the same cutoff. No full-sample threshold or future Context label is
created.

## Multi-seed comparator evidence

Seeds `0..255` reuse `mr1-matched-k-sha256-rank-blind-v1`. Each logical selection is calculated
once for a model/date population and reused across endpoints and costs. Seeds form a same-day
reference distribution and are not independent Decision Dates. The quantile convention is
`linear-r7-quantile-v1`; model percentiles use `empirical-midrank-ties-v1`.

Seed 17 remains the MR-1 trace seed. F2A checks its symbols, selection identities, returns,
weights, missing-as-cash treatment and CLOSE cash lock against the verified MR-1 v4 Artifact.

## Actual run

Run `mr2b-f2a-47709a63823ff4c95402` was materialized from commit `dc965f3`.

- Context: 60 available dates, 0 unavailable; 27 UP, 33 DOWN, 0 FLAT.
- Logical selection slots: 691,200.
- Endpoint/cost/seed return rows: 1,658,880.
- Daily null summaries: 6,480.
- Daily Candidate excess rows: 6,480.
- Average unique selections per null group: 224.1083 of 256.
- Selection collision rate: 12.4577%; duplicates remain disclosed rather than removed.
- Seed 17 reconciliation: 6,480 / 6,480 exact matches; maximum difference 0.

The frozen descriptive input is B1-E / 10:30 / BASE / watchlist direction / daily net lift
versus the multi-seed median. Its UP-minus-DOWN mean difference is approximately
`-0.0000844753`. This is `DESCRIPTIVE_INPUT_ONLY`; it is not a hypothesis result.

## Limitations

- `CURRENT_WATCHLIST_BACKFILL_BIAS`
- `HISTORICAL_PIT_NOT_VERIFIED`
- `WATCHLIST_CONTEXT_IS_NOT_FULL_MARKET_CONTEXT`
- `MULTI_SEED_REFERENCE_IS_NOT_INDEPENDENT_TIME_EVIDENCE`
- `SINGLE_DATASET_ONLY`
- `NO_FORMAL_OOS`
- `REFERENCE_MARK_NOT_FILL_PROOF`
- `FEE_ASSUMPTIONS_REQUIRE_CURRENT_VERIFICATION`

MR-2B remains incomplete. F2B must separately predeclare and implement time-series uncertainty,
Context-label permutation, primary-hypothesis gating, secondary inventory and multiple-testing
disclosure.
