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

Context schema `mr-2b-auxiliary-watchlist-context-v2` uses the accepted auxiliary watchlist,
not any model population and not the A-share market. The definition
`mr2b-accepted-watchlist-exact-1450-context-v2` requires every accepted symbol to have the
canonical 46 end-labelled bars:

```text
09:35–11:30 every five minutes
13:05–14:50 every five minutes
```

It requires the same prior-session cutoff grid and the prior 15:00 close. The exact 14:50 close
is the current reference; 14:55 and 15:00 bars are excluded. Amount change compares today and
the prior session through the same cutoff. No full-sample threshold or future Context label is
created.

F2A v2 also persists
`mr-2b-auxiliary-watchlist-context-symbol-evidence-v1`. Its 1,200 rows retain each
date/symbol cutoff-grid count, exact endpoints, prior close, return, range and same-cutoff amount.
The verified reader reconstructs every daily Context metric and Context identity from these rows.

## Multi-seed comparator evidence

Seeds `0..255` reuse `mr1-matched-k-sha256-rank-blind-v1`. Each logical selection is calculated
once for a model/date population and reused across endpoints and costs. Seeds form a same-day
reference distribution and are not independent Decision Dates. The quantile convention is
`linear-r7-quantile-v1`; model percentiles use `empirical-midrank-ties-v1`.

Seed 17 remains the MR-1 trace seed. F2A checks its symbols, selection identities, returns,
weights, missing-as-cash treatment and CLOSE cash lock against the verified MR-1 v4 Artifact.

## Superseded v1 run

Run `mr2b-f2a-47709a63823ff4c95402` is
`SUPERSEDED_FOR_F2B_INPUT`. F2A v1 covered file bytes but did not fully reconstruct the Primary
projection and every derived table from immutable Dataset/MR-1 evidence. Its published aggregate
12.4577% collision figure also counted cash-locked groups as 256 duplicate empty selections; it
must not be interpreted as SHA-256 selection collision quality.

## Actual v2 run

Run `mr2b-f2a-99cd5a71a92fa5eb0366` uses schema `mr-2b-f2a-run-v2` and was
materialized from semantic source revision `43913d1`.

- Context: 60 available dates, 0 unavailable; 27 UP, 33 DOWN, 0 FLAT.
- Symbol-level Context evidence: 1,200 available rows.
- Logical selection slots: 691,200.
- Endpoint/cost/seed return rows: 1,658,880.
- Daily null summaries: 6,480.
- Daily Candidate excess rows: 6,480.
- Executed null groups: 5,670; cash-locked groups: 810.
- Mean unique selections among executed groups: 255.9810 of 256.
- Mean executed-only selection collision rate: approximately 0.00744%.
- Cash-locked groups have `selection_applicable = false` and null collision fields.
- Seed 17 reconciliation: 6,480 / 6,480 exact matches; maximum difference 0.
- Primary projection, coverage, null summaries and daily excess were recomputed successfully by
  the semantic reader; checksum-valid content tampering is rejected.

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
- `AUXILIARY_CONTEXT_NOT_MARKET_REGIME`
- `STATISTICAL_GATE_NOT_IMPLEMENTED`

F2A v2 remains immutable descriptive input evidence. Statistical inference is owned by F2B run
`mr2b-f2b-cfc48a658d50636610ac`; F2B did not modify or reinterpret these F2A tables. The frozen
directional Primary was not supported. See `MR-2B-F2B-Statistical-Closure.md` and
`MR-2B-Final-Assessment.md`.
