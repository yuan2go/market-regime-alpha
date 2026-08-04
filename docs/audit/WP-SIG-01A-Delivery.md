# WP-SIG-01A Delivery Evidence

> **Status:** CURRENT_STATUS
> **Authority:** Branch-local delivery record for Canonical Signal Authority Convergence and Operational Feature Handoff
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-04
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../architecture/14-Canonical-Signal-Authority-and-Operational-Feature-Handoff.md, ../status/Current-State.md, ../status/Capability-Matrix.md, ../status/Gap-Register.md
> **Code Evidence:** branch-local code and tests; exact final commit is recorded after checkpoint commit
> **Base:** `73b815f30756c3469079aa0961247ac328a41872`
> **Branch:** `feat/canonical-signal-authority-and-operational-feature-handoff`

## Scope delivered

- Universe-first Feature handoff and reference-only Candidate Feature View;
- Signal V3-only canonical production with V1/V2 compatibility retained;
- versioned factor requirement and session-aware freshness policies;
- Decimal-only canonical Signal model and exploratory model registration;
- immutable Tencent minute response/attempt archive, strict normalization and
  versioned 1m→5m resampling;
- explicit LOTS→SHARES policy and VWAP unit gates;
- real Feature execution modes with recoverable SQLite Run authority;
- Market Data and Feature physical Encoding V2 with selective Readers and V1
  migration;
- lifecycle input/receipt bindings and full-chain durable V3 recomputation;
- continued unavailable PathForecast sample authority and blocked Entry.

## Actual call chain

```text
TencentMinuteSourceClient.fetch
→ acquire_and_archive_minute_source
→ publish_raw_minute_source
→ RawMinuteSourceReader.read
→ normalize_tencent_minute_source
→ resample_one_to_five_minute
→ minute_normalization_to_dataset
→ build_combined_market_data_dataset
→ OperationalFeatureHandoffRunner.materialize_universe
→ FeatureMaterializationRunner.run
→ CandidateFeatureView.create
→ SignalInputAssemblerV3.assemble
→ CanonicalSignalModelV2.run
→ publish_signal_run_v3
→ SignalStageHandler.execute
→ run_durable_lifecycle_replay
→ PathForecast DATA_INSUFFICIENT
→ Entry BLOCKED_BY_MODEL_VALIDATION
```

## Compatibility boundary

| Authority | Read | Replay | New canonical production |
|---|---|---|---|
| Signal V1 | retained | retained in explicit historical compatibility | disabled |
| Signal V2 | retained | retained with old float semantics | disabled |
| Signal V3 | implemented | full recomputation | required |
| JSON storage V1 | retained | retained | opt-in compatibility only |
| Encoding V2 | implemented | semantic identity checked | default |

V1/V2 schema or logical hashes were not rewritten. Encoding checksums are
physical integrity evidence and do not replace canonical logical hashes.

## Same-fixture storage benchmark

The frozen branch environment ran the required offline fixture with 100
symbols, 250 daily sessions, 48 minute Bars per symbol and seven Feature
definitions. The optimized run reused the verified JSON V1 package and timing
record produced by the immediately preceding same-environment run; it rebuilt
Encoding V2 from the same logical input. No network was used.

| Measurement | JSON V1 | Encoding V2 | Result |
|---|---:|---:|---:|
| Output bytes | 132,595,413 | 18,704,356 | 85.8937% reduction |
| Cold materialization | 560.758255 s | 584.626303 s | V2/V1 1.042564; target met |
| Cached receipt | 6.010796 s | 8.413115 s | reported; not the selective-read target |
| Full read | 5.152686 s | 7.586604 s | reported; full logical reconstruction remains expensive |
| Selective read | 5.021434 s | 0.014638 s | 99.7085% reduction |
| Encoding-local peak memory | 376,689,949 B | 179,542,034 B | 52.3396% reduction |
| Artifact/file count | 3,007 | 2,326 | 22.6472% reduction |

The canonical Feature Bundle hash remained
`sha256:122364bcf37f9f89e55bb52249505da8e7bc79900fab87b3c2dc38c6b8f6c4b8`.
The Signal Artifact hash remained
`sha256:cc3fba33401029521a25f85d9815fd5e32fd9dc90794df41f6a64cf194174ad2`.
Replay equality was `true`. The benchmark status was `PASS`; this is storage
and Reader engineering evidence, not model-quality or Shadow evidence.

## Public minute-source smoke evidence

After the offline test gate, the new client performed one public Tencent smoke
acquisition for `600000.SH`; the raw Provider bytes and derived package remained
outside the repository under `/tmp`. The endpoint returned HTTP 200 JSON bytes
with a misdeclared `text/html` Content-Type. Strict Tencent-envelope validation
accepted the JSON and recorded
`PROVIDER_CONTENT_TYPE_MISMATCH_VALID_JSON`; no general HTML fallback was
introduced.

```text
response_received_at = 2026-08-04T18:35:51Z
source_artifact_id = raw-minute-source-948b785d3687b23c2bb73ee4
source_content_hash = sha256:948b785d3687b23c2bb73ee438b98590e5ae8072047da9d657465e8e91d02dde
raw_payload_hash = sha256:e24bcbb121c125b04dd2b4e53fde0d4eb1db153ca79ca0f2cdc1cf26c0ef7e8c
source_manifest_id = source-manifest-7a64048f57fea8f5cd96d13b
source_manifest_hash = sha256:7a64048f57fea8f5cd96d13be3a28875442eb16e1299ae5f55bda4477789f409
one_minute_bars = 240
five_minute_bars = 48
dataset_id = market-data-dataset-0809919401c6d97bbab4fe7c
dataset_hash = sha256:0809919401c6d97bbab4fe7ce391927d687bbd8bf2b51e4a9a08239035b6c82d
archive_replay_equal = true
dataset_replay_equal = true
data_eligibility = EXPLORATORY
formal_pit_status = FORMAL_PIT_NOT_ESTABLISHED
```

This is a single engineering smoke, not controlled 14:55, sustained Shadow,
formal Provider qualification or OOS Alpha evidence.

## Safety evidence ceiling

The minute Provider and Signal model are exploratory. This work establishes
engineering mechanics, not predictive validity. There is no formal OOS Alpha,
calibrated PathForecast, Opportunity creation, automatic Thesis approval,
ManualTrade, Fill, Broker integration, H7, H8 scheduler or H9 implementation.

```text
entry_model_empirically_validated = false
formal_oos_alpha = false
automatic_order_execution = false
broker_integration_proven = false
production_ready = false
```

## Verification record

The final pre-commit workspace observed:

```text
git diff --check = PASS
uv sync --frozen --extra dev --extra postgres = PASS, 77 packages checked
uv run python scripts/check_docs_links.py = PASS
uv run pytest -q tests/scripts/test_check_docs_links.py = PASS, 8 collected
uv run pytest -q tests/market_data = PASS, 44 collected
uv run pytest -q tests/features = PASS, 78 collected
uv run pytest -q tests/signals = PASS, 21 collected
uv run pytest -q tests/application/canonical_lifecycle = PASS, 353 collected
uv run pytest -q tests/architecture = PASS, 5 collected
uv run pytest -q = PASS, 2082 collected, 6 existing pandas warnings
uv run ruff check . = PASS
uv run mypy = PASS, 328 source files
uv run python -m build = PASS, sdist and wheel
100-symbol V1/V2 benchmark = PASS
```

Commit, PR and remote-CI identities are external delivery metadata and are
reported with the final handoff; this source document does not pre-claim a
future remote check result.
