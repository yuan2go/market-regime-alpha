# WP-3 Provider Routing and Candidate Runs Design

> **Status:** PROPOSED — approved conversational design, pending written-spec review
> **Date:** 2026-07-16
> **Authority:** Bounded WP-3 engineering design under `AGENTS.md`; the Constitution and current R5 authority documents remain higher authority

## 1. Purpose

WP-3 needs a reproducible Candidate-research execution path before a real XtQuant runtime is
available in this repository environment. Tencent data may temporarily support model-research
dataset construction, but it must remain `EXPLORATORY`. Xuntou remains the canonical primary
provider and is the only currently approved route to a provider-backed `REHEARSAL` WP-3 result.

This design adds an explicit data-source routing policy and a shared R5 B0/B1 run boundary. It does
not turn provider fallback into trading logic and does not treat a successful public-data request as
proof of PIT correctness.

## 2. Provider Roles

The provider roles are fixed for this increment:

| Provider path | Current role | Maximum data eligibility | Future role |
| --- | --- | --- | --- |
| Xuntou / ThinkTrader / XtQuant normalized export | Canonical primary | `REHEARSAL` | Canonical primary |
| Tencent current + identified local history + BaoStock gap fill | Temporary training path | `EXPLORATORY` | Explicit auxiliary |
| Eastmoney and other public sources | Out of scope for the first router | No new authority | Possible explicit auxiliary |

Tencent does not close WP-3. WP-3 is complete only after a real, content-hashed Xuntou export has
successfully produced a `REHEARSAL` run artifact. Before that event, the router and runner may be
implemented and Tencent exploratory runs may exercise the engineering path, but current status must
continue to say that the real Xuntou provider-backed run is unavailable.

## 3. Selected Approach

Use a capability- and authority-aware run router.

Rejected alternatives:

- Whole-provider exception fallback is too weak because it cannot distinguish provider absence
  from an invalid bundle or semantic contract violation.
- Field-level automatic source mixing is premature because it would require per-field PIT,
  adjustment, availability, finality and source-precedence contracts not established by WP-3.

The first router selects one complete run backend. It does not merge Xuntou and Tencent evidence
inside one Candidate dataset.

## 4. Architecture

```text
Run Request
source mode: AUTO / XUNTOU / TENCENT
required research authority
        ↓
Provider Capability Preflight
        ↓
DataSourceSelectionPolicy
        ├── valid Xuntou bundle supplied
        │       ↓
        │   Xuntou normalized adapter
        │       ↓
        │   ProviderRehearsalMarketArtifact
        │       ↓
        │   REHEARSAL Candidate path
        │
        └── Xuntou genuinely unavailable
                ↓
            existing Tencent composite acquisition
                ↓
            EXPLORATORY Candidate path
        ↓
Shared fixed B0 / B1 evaluation boundary
        ↓
Immutable identified run directory
```

The router lives in `market_regime_alpha.research`. It composes providers, Candidate materializers
and run artifacts without changing canonical Data, Universe, Feature or Candidate contracts.

## 5. Source Selection Contracts

Add a focused source-routing module with immutable contracts:

```text
CandidateDataSource
    XUNTOU
    TENCENT_COMPOSITE

CandidateRunSourceMode
    AUTO
    XUNTOU
    TENCENT

ProviderAvailabilityStatus
    AVAILABLE
    UNAVAILABLE
    INVALID

ProviderCapabilityReport
    source
    availability_status
    maximum_data_eligibility
    supported_evidence
    unsupported_evidence
    limitations
    input_identity

ProviderSelectionAttempt
    source
    disposition
    reason_code
    detail

ProviderSelectionDecision
    selected_source
    selected_data_eligibility
    attempts
    limitations
    policy_version
    deterministic decision identity
```

The router accepts preflight reports. It does not perform network I/O itself. This keeps selection
deterministic and makes provider access independently testable.

## 6. Selection Policy

The first policy is versioned as:

```text
R5_CANDIDATE_DATA_SOURCE_SELECTION_V1
```

Rules:

1. Explicit `XUNTOU` mode accepts only an `AVAILABLE` Xuntou report and otherwise fails.
2. Explicit `TENCENT` mode accepts only an `AVAILABLE` Tencent composite report and always caps the
   result at `EXPLORATORY`.
3. `AUTO` checks Xuntou first.
4. `AUTO` selects Xuntou when a bundle is present and passes schema, hash and semantic preflight.
5. `AUTO` may select Tencent only when Xuntou is genuinely `UNAVAILABLE`, such as no bundle being
   supplied or no authorized runtime/export being present.
6. Xuntou `INVALID` is a fail-closed condition. It must not route to Tencent, because doing so would
   hide corrupt input or a mapping-contract failure.
7. A requested authority above the selected provider's ceiling is rejected.
8. No route may emit `FORMAL_RESEARCH`.
9. Every route records all attempts and the exact reason for selection or rejection.

Valid empty Candidate results remain valid. The router must not change source merely because the
selected provider produces zero eligible Candidates under the declared policy.

## 7. Provider Preflight Boundaries

### 7.1 Xuntou

Xuntou preflight receives an optional normalized bundle path. When supplied, it verifies the file
exists and invokes the existing strict loader/adapter boundary. Adapter errors are classified as
`INVALID`, not `UNAVAILABLE`.

Successful preflight exposes the resulting `ProviderRehearsalMarketArtifact` and its content-derived
Dataset, source-artifact and provider identities. It does not import XtQuant.

### 7.2 Tencent

Tencent preflight uses the existing composite acquisition and quality contracts. It preserves the
current Tencent/local/BaoStock source partitions, attempts, content hashes, conflicts and quality
dispositions. It remains bounded to the current 20-symbol experimental population until a separate
research charter changes that scope.

Tencent preflight must not synthesize:

- historical PIT membership;
- historical ST or suspension completeness;
- listing-age authority;
- Decision-Time buyability;
- provider bar finality;
- historical availability;
- price-adjustment revision history.

## 8. Candidate Pipeline

### 8.1 Xuntou REHEARSAL path

The provider market artifact is converted through existing contracts:

```text
ProviderRehearsalMarketArtifact
        +
Provider-Rehearsal Eligibility Policy v2
        ↓
HistoricalTradingEligibilityArtifact
        ↓
HistoricalPITUniverseArtifact ∩ Eligibility
        ↓
CandidatePopulation per Decision Time
        ↓
R5 baseline Feature materializations
        ↓
Close Return / MFE / MAE Target bundle
        ↓
three target-specific Candidate panels
```

The runner must use the artifact's identified Trading Calendar to resolve next sessions. It must not
infer weekdays or `decision_date + 1 day`.

The current provider-rehearsal Eligibility v2 policy requires explicit Decision-Time buyability.
The conservative Xuntou P0 adapter currently returns `UNKNOWN` except for confirmed suspension,
which returns `NOT_BUYABLE`. Consequently, a truthful Xuntou bundle can produce a valid empty
Candidate Population. The runner must preserve that outcome as
`NO_CANDIDATES_AFTER_ELIGIBILITY`, write eligibility diagnostics, and omit misleading B0/B1
metrics. It must not weaken v2, treat `UNKNOWN` as eligible, or switch to Tencent merely because the
Xuntou Candidate Population is empty.

Closing WP-3 with a non-empty Xuntou B0/B1 run therefore additionally requires future verified
runtime/export evidence that can support the scoped `BUYABLE` classification. That evidence may
justify a separately reviewed mapping increment; this design does not invent it.

### 8.2 Tencent EXPLORATORY path

The existing Tencent composite preparation and materialization remain the owner of exploratory
source semantics. The new orchestration may call that boundary but must not relabel its output as a
provider rehearsal artifact.

### 8.3 Shared baseline evaluation

Both paths use the same fixed, untuned comparison set:

- four B0 single-feature controls;
- B1-A through B1-E transparent composite ablations;
- separate evaluation for Close Return, MFE and MAE;
- no winner selection;
- no B2 model;
- no parameter grid;
- no probability output.

Common output metrics remain descriptive RankIC, top-K target mean and coverage metrics already
defined by the Candidate evaluation contracts.

## 9. Immutable Run Artifacts

Every successful run writes an atomic, non-overwriting directory. A staging directory is completed
and validated before one filesystem rename publishes the run.

The first artifact set is:

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

The manifest records:

- run ID;
- code revision;
- config hash;
- selected source and policy version;
- actual Data Eligibility;
- provider and Dataset identities;
- source locators, retrieval times and content hashes;
- Decision Time convention;
- Feature and Target identities;
- Candidate-population and coverage counts;
- all limitations;
- exact artifact filenames and hashes.

Failed preflight or quality-gate decisions write a separate non-overwriting failure artifact with no
Candidate evaluation. A public or Legacy snapshot is not updated by this WP-3 runner.

## 10. CLI Composition Root

Add one CLI for the source-aware Candidate run. Its intended interface is:

```text
python3 scripts/run_wp3_candidate_research.py \
  --source auto \
  --minimum-eligibility exploratory \
  --xuntou-bundle /path/to/bundle.json \
  --output-root data/processed/r5_candidate_runs
```

Relevant modes:

```text
--source auto
--source xuntou --xuntou-bundle ...
--source tencent
--minimum-eligibility exploratory
--minimum-eligibility rehearsal
```

`--minimum-eligibility` defaults to `exploratory`. When it is `rehearsal`, `AUTO` must fail if a
valid Xuntou input is unavailable; it must not satisfy the request with Tencent. No CLI option can
request `FORMAL_RESEARCH`.

The CLI owns argument parsing, Git revision capture and composition only. Provider semantics, routing,
Candidate arithmetic and artifact serialization remain in separate modules.

## 11. Local Provider Documentation Reference

Create a local, summarized provider reference under:

```text
docs/references/providers/xuntou/
```

It contains:

- one index of the supplied MiniQMT and Xuntou URLs;
- retrieval date and source title;
- evidence tier (`XUNTOU_FIRST_PARTY` or `SUPPLEMENTARY_MINIQMT`);
- SHA-256 of the retrieved page bytes when retrieval succeeds;
- paraphrased API, field, period and runtime notes relevant to P0/WP-3;
- explicit unknown PIT, availability, finality and revision semantics;
- links to the normative mapping specification.

The repository does not mirror full third-party HTML. This avoids stale copies and copyright or
licensing ambiguity while retaining a reproducible research index.

Sources include:

- `https://www.miniqmt.com/pages/docs/xtdata.html`
- `https://dict.thinktrader.net/nativeApi/start_now.html`
- `https://dict.thinktrader.net/nativeApi/xtdata.html`
- `https://dict.thinktrader.net/dictionary/stock.html`
- `https://dict.thinktrader.net/dictionary/industry.html`
- `https://dict.thinktrader.net/nativeApi/download_xtquant.html`
- `https://dict.thinktrader.net/innerApi/data_function.html`

## 12. Error Handling

Use stable error codes rather than generic fallback exceptions. The minimum families are:

```text
PROVIDER_ROUTE_REQUIRED_SOURCE_UNAVAILABLE
PROVIDER_ROUTE_SOURCE_INVALID
PROVIDER_ROUTE_AUTHORITY_UNSUPPORTED
PROVIDER_ROUTE_NO_ELIGIBLE_SOURCE
WP3_XUNTOU_BUNDLE_REQUIRED
WP3_XUNTOU_PREFLIGHT_FAILED
WP3_TENCENT_QUALITY_GATE_FAILED
WP3_CANDIDATE_MATERIALIZATION_FAILED
WP3_RUN_ARTIFACT_ALREADY_EXISTS
WP3_RUN_ARTIFACT_INCOMPLETE
```

Provider absence, provider invalidity, quality rejection and valid empty Candidate populations are
different states and must remain distinguishable.

## 13. Testing Strategy

Implementation follows focused TDD.

### Router tests

- `AUTO` prefers valid Xuntou.
- `AUTO` uses Tencent only when Xuntou is unavailable.
- invalid Xuntou fails closed and does not fall back.
- explicit modes never select a different provider.
- requested authority cannot exceed the selected ceiling.
- selection identity is deterministic and changes with result-affecting semantics.

### Xuntou pipeline tests

- a small normalized fixture traverses adapter, eligibility, Population, Features, three Targets,
  panels and B0/B1 evaluation;
- missing required evidence remains `UNKNOWN` and may produce a valid empty population;
- no future Feature observation is admitted;
- next session is calendar-resolved;
- output remains `REHEARSAL` and never `FORMAL_RESEARCH`.

### Tencent integration tests

- router output remains `EXPLORATORY`;
- current-watchlist bias and source limitations are retained;
- existing source partitions and conflicts are not erased;
- no Xuntou provider identity is attached.

### Artifact and CLI tests

- successful artifact set is complete, hashed, atomic and non-overwriting;
- failed runs contain no misleading Candidate evaluation;
- a write failure removes staging output;
- CLI tests inject provider boundaries and perform no network access.

Focused tests run before affected-area tests. Full `pytest`, Ruff and mypy are attempted at the end,
with exact pre-existing failures reported rather than hidden.

## 14. Documentation and Status Rules

Update the current status to distinguish:

```text
WP-3 source-aware runner infrastructure       IMPLEMENTED
Tencent temporary training run path           EXPLORATORY
Real Xuntou provider-backed REHEARSAL run      NOT AVAILABLE or COMPLETED from actual evidence
WP-3 overall                                  PENDING until real Xuntou run
```

The existence of a router, CLI or Tencent run does not permit writing “WP-3 complete.”

## 15. Non-Goals

This increment does not implement:

- B2 or later models;
- automatic model selection;
- field-level multi-provider merging;
- Eastmoney adapter expansion;
- XtQuant runtime extraction;
- Level-2 data;
- Entry, Position Lifecycle or Exit targets;
- Portfolio or execution logic;
- live order placement;
- calibrated probabilities;
- `FORMAL_RESEARCH` promotion.

## 16. Acceptance Criteria

The design is implemented when:

1. supplied provider documents have a local summarized, hashed reference index;
2. provider routing is deterministic, authority-aware and fail-closed;
3. Xuntou remains primary and Tencent remains temporary `EXPLORATORY`;
4. one source-aware CLI can execute either backend without import-time XtQuant dependency;
5. the Xuntou normalized-export path can build multi-date Candidate panels and fixed B0/B1 results
   when complete v2 eligibility evidence is available, while an incomplete truthful bundle emits a
   valid identified no-Candidate outcome instead of fabricated metrics;
6. Tencent can exercise the temporary training path without receiving rehearsal authority;
7. all successful and failed runs have complete non-overwriting evidence artifacts;
8. missing or ambiguous evidence is never converted into a convenient value;
9. public APIs expose only intended contracts and entry functions;
10. current status documents distinguish implemented infrastructure from a real provider run.
