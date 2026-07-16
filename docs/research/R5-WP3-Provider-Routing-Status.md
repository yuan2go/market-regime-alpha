# R5 WP-3 Provider Routing and Candidate Run Status

> **Status:** CURRENT
>
> **Infrastructure:** IMPLEMENTED
>
> **Real Xuntou provider-backed run:** NOT AVAILABLE
>
> **WP-3 overall:** PENDING REAL XUNTOU EVIDENCE

## Purpose

This document answers what the WP-3 execution path can do now. It does not redefine Xuntou native
fields; those semantics remain in `docs/specs/Xuntou-P0-Native-Field-Mapping.md`. It also does not
promote Tencent data to the canonical provider role.

## Implemented infrastructure

```text
Local hashed Xuntou documentation index                     IMPLEMENTED
Pure authority-aware provider router                        IMPLEMENTED
Xuntou normalized-export preflight                          IMPLEMENTED
ProviderRehearsalMarketArtifact -> Candidate panels         IMPLEMENTED
Shared fixed B0 / B1-A...E evaluation seam                  IMPLEMENTED
Tencent temporary exploratory backend                       IMPLEMENTED
Atomic non-overwriting success/failure artifacts            IMPLEMENTED
Source-aware command-line entry point                        IMPLEMENTED
XtQuant import-time dependency                              ABSENT
XtQuant runtime extraction                                  NOT IMPLEMENTED / NOT EXECUTED
Real Xuntou bundle execution                                NOT AVAILABLE
New source-aware Tencent CLI run                            NOT EXECUTED
B2 or automatic model selection                            NOT IMPLEMENTED
```

The previously recorded Tencent composite live run remains valid `EXPLORATORY` evidence, but it was
produced by the earlier Tencent-specific command. The new source-aware CLI has not been represented
as a live run merely because its infrastructure exists.

## Source-selection policy

The policy identity is:

```text
R5_CANDIDATE_DATA_SOURCE_SELECTION_V1
```

| Request | Xuntou preflight | Result |
|---|---|---|
| `AUTO`, minimum `EXPLORATORY` | `AVAILABLE` | Select Xuntou, maximum `REHEARSAL` |
| `AUTO`, minimum `EXPLORATORY` | `UNAVAILABLE` | Tencent may be selected, maximum `EXPLORATORY` |
| `AUTO` | `INVALID` | Fail closed; do not execute Tencent |
| `AUTO`, minimum `REHEARSAL` | Xuntou unavailable | Fail; Tencent cannot satisfy the request |
| explicit `XUNTOU` | bundle absent/invalid | Fail with explicit evidence |
| explicit `TENCENT` | available | Select Tencent, maximum `EXPLORATORY` |

The router selects one complete backend. It does not merge Xuntou and Tencent fields, and it never
uses Candidate count, score or model performance to change source.

## Xuntou Candidate path

The normalized-export path composes existing contracts:

```text
Xuntou P0 normalized export
        ↓
ProviderRehearsalMarketArtifact
        +
r5-provider-rehearsal-trading-eligibility@v2
        ↓
HistoricalTradingEligibilityArtifact
        ↓
Historical Universe membership ∩ exact-time Eligibility
        ↓
Candidate Population by Decision Time
        ↓
four baseline Features
        ↓
Close Return / MFE / MAE target-specific panels
        ↓
four B0 controls + fixed B1-A through B1-E
```

The runner requires an explicit liquidity threshold. It uses the Xuntou adapter's versioned
20-session median native-amount identity and does not hide a threshold in global configuration.
Next-session Targets are resolved only through the identified Trading Calendar.

The current Xuntou P0 buyability convention emits `NOT_BUYABLE` for confirmed suspension and
otherwise retains `UNKNOWN`. Consequently, a truthful current bundle can produce:

```text
NO_CANDIDATES_AFTER_ELIGIBILITY
```

That is a valid successful diagnostic result. It writes population/eligibility counts and an
explicit `NOT_PRODUCED` B0/B1 record. It does not weaken eligibility, convert `UNKNOWN` to eligible,
or switch to Tencent.

## Tencent temporary training path

The source-aware Tencent backend reuses the existing identified Tencent/local/BaoStock acquisition,
merge, quality and Candidate materialization contracts. It remains bounded to the configured
20-symbol research watchlist and 60 Decision Dates.

It preserves:

- source partitions, attempts, content hashes and locators;
- quality dispositions and retained source conflicts;
- current-watchlist backfill bias;
- historical availability, PIT, finality and adjustment limitations;
- the `EXPLORATORY` authority ceiling.

It does not write the Legacy Dividend-T/GitHub Pages snapshot and does not attach a Xuntou provider
identity.

## Run artifacts

Every successful run publishes one staged and content-hashed directory containing:

```text
manifest.json
provider_selection.json
source_artifacts.json
quality.json
candidate_panel_summary.json
b0_b1_evaluation.json
limitations.json
report.md
SHA256SUMS.json
```

Failed routing, preflight, quality or Candidate materialization produces only:

```text
manifest.json
failure.json
SHA256SUMS.json
```

Existing final or staging paths are never overwritten. The manifest identifies code/config,
selection policy and decision, actual Data Eligibility, provider/Dataset identities, Feature/Target
identities and limitations. `SHA256SUMS.json` covers every other exact output byte.

## Runtime command

Temporary automatic mode:

```bash
python3 scripts/run_wp3_candidate_research.py \
  --source auto \
  --minimum-eligibility exploratory
```

Explicit Xuntou normalized export:

```bash
python3 scripts/run_wp3_candidate_research.py \
  --source xuntou \
  --minimum-eligibility rehearsal \
  --xuntou-bundle /path/to/xuntou-p0-native-bundle-v3.json \
  --minimum-liquidity-value 50000000
```

The numeric threshold above is an invocation example, not a project-approved universal liquidity
threshold. Every real experiment must record and justify its selected value.

## Current authority and limitations

- Xuntou remains the canonical primary provider.
- Tencent remains temporary `EXPLORATORY` training data and later an explicit auxiliary.
- No route emits `FORMAL_RESEARCH`.
- No real Xuntou bundle, XtQuant runtime extraction or provider-backed B0/B1 result was available in
  this development environment.
- Xuntou historical full-population PIT completeness, availability SLAs, revision history, minute
  label semantics and generic historical `BUYABLE` evidence remain unverified.
- The new runner infrastructure does not close WP-3 by itself and makes no Alpha claim.
- B2, Entry, Lifecycle, Exit, Portfolio, execution and live-order responsibilities remain outside
  this work package.

## Next data-acquisition step

WP-3 now requires one authorized, exact-byte-hashed `xuntou-p0-native-bundle-v3` export. The first
run should audit source coverage and will likely produce an empty Candidate result under current
buyability semantics. A non-empty Xuntou B0/B1 run requires separately verified historical
Decision-Time evidence sufficient for the scoped `BUYABLE` classification; that evidence must be
reviewed as a mapping increment rather than invented in the runner.
