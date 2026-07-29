# WP-D3 Public LIVE Semantic Closure Audit

> **Status:** CURRENT_STATUS
> **Authority:** Commit-bound code, test and runtime evidence report for the fixed 20-symbol public-data daily loop
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-07-29
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** Run-First-Daily-Platform-Delivery.md, ../superpowers/plans/2026-07-29-public-live-semantic-closure.md, ../status/Current-State.md, ../status/Capability-Matrix.md, ../status/Gap-Register.md
> **Code Evidence:** `feat/public-live-semantic-closure@2ce6773d597286cbb39a08d3b0f9a2d08983b1d3`; `src/market_regime_alpha`; `tests`

## 1. Overall conclusion

```text
PUBLIC_LIVE_STILL_DATA_BLOCKED
```

The public LIVE path now closes its protocol, policy, source-freeze, recovery and per-symbol
failure semantics without inventing Provider facts. It acquired and archived real BaoStock and
Tencent bytes, but the observed run did not establish a usable 14:55 quote or qualified current
trading, ST and listing status. All 20 symbols were therefore explicitly `INELIGIBLE`, and the
run published a verified `DATA_BLOCKED` Artifact.

A v2 Fixture Archive with explicit independent status evidence reaches `OUTCOME_PENDING`, and
the existing B0/B1/Outcome flow remains operational. A real public Archive does not yet reach
`OUTCOME_PENDING`, so the criteria for expanding to a 100–300 Operational Pool are not met.

## 2. Baseline

| Field | Observed value |
|---|---|
| synchronized main HEAD | `f99f6330192f410cde47234f2fc519818d269d76` |
| branch | `feat/public-live-semantic-closure` |
| runtime evidence commit | `2ce6773d597286cbb39a08d3b0f9a2d08983b1d3` |
| scope | fixed 20-symbol A-share Smoke Pool |
| data authority | `DataEligibility.EXPLORATORY` |
| formal PIT | `NOT_ESTABLISHED` |
| formal OOS Alpha | `NOT_ESTABLISHED` |
| trading authority | `NOT_GRANTED` |

The branch preserves `daily_research` V1 and its tests with zero changes. B0/B1 rankers, weights,
Target identity and Entry semantics were not changed.

## 3. Original problem verification

| Concern | Verified code fact before/after | Test evidence |
|---|---|---|
| BaoStock History Available Time | `live_clients.py::BaoStockHistoryClient` keeps `available_time=None`; it does not map retrieval time to historical availability | `test_baostock_live_history_uses_prior_unadjusted_daily_product` |
| History Finality | prior daily rows remain `UNKNOWN` under `HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1`; Feature admission is exploratory-only and cannot establish formal PIT | `test_history_semantics_remain_exploratory`, `test_public_daily_history_materializes_r5_features` |
| Tencent Trading Status | Tencent normalization remains `TradingStatus.UNKNOWN`; no UNKNOWN-to-TRADING conversion exists | `test_unknown_trading_status_is_explicit` |
| Universe Membership | v2 membership is a boolean policy fact bound to the immutable `a-share-smoke-pool@v1` policy payload, not Tencent/BaoStock | `test_smoke_pool_membership_has_policy_lineage`, `test_membership_does_not_claim_provider_authority` |
| Eligibility | a separate policy Artifact records `ELIGIBLE`, `INELIGIBLE` or `UNKNOWN` and reasons over explicit inputs | `test_single_symbol_unknown_status_excludes_symbol_not_global_run` |
| Decision Time | v2 Decision Time comes from `DailyRunCommand` through protocol authority; late runtime retrieval does not make the protocol fact future data | `test_decision_time_is_protocol_fact`, `test_decision_time_not_blocked_by_late_runtime_retrieval` |
| Feature Pipeline | prior BaoStock daily close/amount plus Decision Quote materialize the four existing R5 Features without formula changes | `test_public_daily_history_materializes_r5_features`, `test_feature_values_match_frozen_fixture_baseline` |
| Global vs per-symbol blocking | Provider/Archive/Protocol/Policy integrity blocks globally; symbol facts exclude only that symbol; population below five blocks the run | `test_global_provider_failure_blocks_run`, `test_partial_symbol_failure_preserves_remaining_population` |

## 4. Implemented modules

### Source facts and Provider

- `data/source_manifest.py` routes unchanged v1 payloads and v2 authority/value facts separately.
- `manifest_builder.py` declares protocol, Provider, Universe Policy and Eligibility Policy
  authority explicitly.
- `BaoStockHistoryClient` requests prior-session unadjusted daily bars (`frequency=d`,
  `adjustflag=3`), not 90-day five-minute history.
- Tencent event time and actual HTTP retrieval time remain separate.
- Quotes or status retrieved after Decision Time become explicit per-symbol insufficiency.

### Staged acquisition and recovery

- `PublicCompositeLiveProfile.acquire_history()` and `acquire_current()` are separate stages.
- `public-source-acquisition-stage-v2` binds the stage to `RunRequestId`.
- SQLite stores `AcquisitionStageReceipt` pointers only; immutable files remain Evidence
  Authority.
- A restart first verifies and claims an orphan stage Artifact published before its Receipt.
- A frozen history stage is reused after Quote failure; LIVE never changes to Replay or a local
  cache.

### Quality, Universe and Feature

- `evaluate_daily_data_quality()` preserves v1 behavior and applies two-level v2 blocking.
- ST status, listing status and Provider trading status are distinct facts.
- Eligibility is a policy decision, not a Provider claim.
- all configured symbols receive an explicit reconciliation result.
- prior public daily history can feed the existing Feature formulas only under the recorded
  exploratory limitation.

### Artifact and Reader

- DailyRun identity binds the SourceManifest hash and every actual source content hash.
- v2 SourceManifest semantics are nested in the existing Phase D Artifact without changing
  historical `daily_research` V1.
- stage, Source Archive, PredictionRun, Daily Decision and Daily Review readers verify checksum
  and semantic identity.
- `DATA_BLOCKED` keeps PredictionRun, Recommendation and EntryAssessment empty.

## 5. Runtime evidence

Runtime directories are ephemeral `/tmp` locators. IDs and hashes below are the stable evidence
identities.

### 5.1 v2 Fixture Replay, Settlement and Report

| Field | Value |
|---|---|
| decision date | `2025-02-03` |
| RunRequestId | `run-request-b38aa7c7bed148b21d256359` |
| DailyRunId | `daily-run-e39062262b3fb39d7a7add8b` |
| Source Archive | `source-replay-94d2e80d3eb05b15bb934971` |
| SourceManifest | `source-manifest-883073fabaec7ba3263bc87d` |
| Decision Artifact | `daily-decision-c2e95f7b80f6bafb367d85ef` |
| Decision replay hash | `sha256:c3b030633380b524495542b813d71e75ac5d66ccd37dc0f08c6163353e1bb379` |
| Candidate population | `20` |
| PredictionRun / Prediction count | `2 / 40` |
| Recommendation / EntryAssessment count | `10 / 10` |
| Entry state | `WAIT_CONFIRMATION` only |
| Review Artifact | `daily-review-artifact-4600835a87bb9c2b669eb50f` |
| Review hash | `sha256:0a16735cd92ebde6694550b5b4186fe41b11e412faf089b855b3e5a51a29faf5` |
| outcome coverage | `1.0` |

`run`, `replay`, `settle` and `report` all completed. Settlement appended a successor Artifact
without modifying the T-day decision.

### 5.2 Ten-session Fixture Replay

All ten sessions produced 20-symbol populations, two full PredictionRuns (40 Predictions), ten
Recommendations, ten EntryAssessments, stable repeated hashes and a Review with outcome coverage
`1.0`.

| Date | DailyRunId | Decision Artifact | Replay hash |
|---|---|---|---|
| `2025-02-03` | `daily-run-b84aa2d9528aa607721afdf8` | `daily-decision-fafa6c42bf962621f1a29f87` | `sha256:231042ee2add69454aee2adf60dbd1a96a52a8f70e886ad8f4508e08acdcec75` |
| `2025-02-04` | `daily-run-d52e0a109569b958713ec42f` | `daily-decision-f8c93a11d234a9ed9a8c92eb` | `sha256:f285587886c4ad9d8ca432eeac79312e75a107b15219424aaf4afc9c307fe499` |
| `2025-02-05` | `daily-run-983d87c6af395035651125d8` | `daily-decision-5665b1fe13d83953fa50c944` | `sha256:24d662510118b841b40aeed39520a6d77f9e4001aa66781869ac91c87df8d5a3` |
| `2025-02-06` | `daily-run-b08f6c5ffcd063210390a813` | `daily-decision-234ddcdb6ecebc7229338b87` | `sha256:5cca935a85e98ce83a42e255e984145333aa640f704605aa12eeac2a703a301c` |
| `2025-02-07` | `daily-run-f6beea969d1d6b2043550743` | `daily-decision-4bcc7b551c4417a9ea745a90` | `sha256:229adca6e6e129c36dc6ded19887a3afff0f430d16696ddbaddf0478b393a305` |
| `2025-02-10` | `daily-run-04b544a59c767c4ad3213d27` | `daily-decision-a01d1e66f9da0b7d57823b88` | `sha256:5dcbd9dbc13450b6b2097ff3a3acfa7e9c0659bcab43ec79e8b00e24aac5bf88` |
| `2025-02-11` | `daily-run-2f16732734679840bc3731dd` | `daily-decision-5feef83b05bd8ce2d8fafbbf` | `sha256:0c8a9e5759dde610817e0bf022d78403c3634c17191f14013c4dcd8f6b50aa10` |
| `2025-02-12` | `daily-run-16579b97dc0a3fa6e85507e5` | `daily-decision-24442a44a7428975443f9694` | `sha256:0a1132b1bb37639836f6b28d37610e35d03f6f176fa72bfab4033f08961fcbb6` |
| `2025-02-13` | `daily-run-4572d3339131d02b8832ebed` | `daily-decision-37403caf24741171f790e77c` | `sha256:2e27ed51fbf7e20e14c09e41f15b60e7c7949e4f678756977dac7c4980bbc047` |
| `2025-02-14` | `daily-run-291d098c0c6ec364a84018ae` | `daily-decision-8380a8829e6372a2f53d90fc` | `sha256:84d6cc54416af08b20ffe28e6c8cbed3801fb783c6ce3d545df121f9694ccd5c` |

### 5.3 Real public LIVE dry run

The run executed at approximately 22:00 Asia/Shanghai for Decision Time
`2026-07-29T14:55:00+08:00`. It did not reinterpret the late Quote as a 14:55 mark.

| Field | Value |
|---|---|
| status | `DATA_BLOCKED` |
| RunRequestId | `run-request-41d28cf069a3d79a91f7a5b9` |
| DailyRunId | `daily-run-5a87c9bec6ef504035beb4b6` |
| Source Archive | `source-replay-87fb6fc04527f004cfa633bf` |
| SourceManifest | `source-manifest-1325fbc0bb93e2fb614b9cf1` |
| SourceManifest hash | `sha256:1325fbc0bb93e2fb614b9cf124f88dcc88e2841710b3b88e5eb8710197a96c0e` |
| Decision Artifact | `daily-decision-13546db606da9ddf0685d7eb` |
| replay hash | `sha256:b3da2e0cfb469c50b07d89b6719e02b38d4209c7b3096decb294d38a20d98619` |
| history stage | `source-stage-history-source-frozen-b247be4374d164401a5042d6` |
| quote stage | `source-stage-decision-quote-source-frozen-af98ef32a17b6d1352ff0ecd` |
| raw payload / bar / quote count | `24 / 1200 / 20` |
| SourceManifest field count | `141` |
| Candidate population | `0` |
| Prediction / Recommendation / Entry count | `0 / 0 / 0` |
| blocked reason | `CANDIDATE_POPULATION_INSUFFICIENT` |

All 20 price facts were `INSUFFICIENT` because their actual availability was after Decision Time.
All 20 Tencent trading statuses remained `UNKNOWN`. Independent ST and listing statuses were also
unknown, so all 20 policy decisions were `INELIGIBLE`.

An identical LIVE command reused the same two stage Artifacts, one Source Archive and one Decision
Artifact. Reader replay returned the same hash.

### 5.4 Real public Archive Replay

The immutable LIVE Source Archive above was consumed offline by
`public-composite-replay-v1`. It made no network call and reproduced the same semantic block.

| Field | Value |
|---|---|
| status | `DATA_BLOCKED` |
| DailyRunId | `daily-run-7e30933a8ceb0192ef36c446` |
| Decision Artifact | `daily-decision-6faf8a0a36a425858d54daff` |
| repeated replay hash | `sha256:10ade52c8e176f2d006a82133f1f26edca7a49c431b275553baf85df4da89523` |

The hash is stable within this RunRequest. It differs from the LIVE decision hash because the
RunRequest and DailyRun identity intentionally bind the LIVE versus REPLAY command semantics.

## 6. Authority boundary

```text
data_eligibility = EXPLORATORY
formal_pit = NOT_ESTABLISHED
formal_oos_alpha = NOT_ESTABLISHED
trading_authority = NOT_GRANTED
```

No successful fixture or operational execution grants model promotion, Entry `ENTER`, position,
order or broker authority.

## 7. Validation

| Command | Observed result |
|---|---|
| `python -m pytest -q` | PASS — 1,087 collected/passed, 0 failed, 0 skipped; 6 pre-existing pandas fragmentation warnings |
| `python -m mypy` | PASS — 181 source files |
| `python -m ruff check src tests scripts` | PASS |
| `python scripts/check_docs_links.py` | PASS |
| `python -m pytest -q tests/scripts/test_check_docs_links.py` | PASS — 8 passed |
| `python -m pip check` | PASS — no broken requirements |
| `git diff --check` | PASS |

Focused validation also covered `tests/application/daily_loop`, `tests/data`, `tests/features`,
`tests/universe`, `tests/platform`, `tests/daily_decision` and `tests/candidates`.

## 8. Remaining gaps

1. Tencent public Quote does not qualify current trading status.
2. The public path has no qualified same-day ST, delisting or listing-status source.
3. the observed LIVE run was outside the 14:55 Decision window.
4. public Provider history has no original historical publication timestamp and remains
   exploratory-only.
5. a real public Archive has not reached `OUTCOME_PENDING`.
6. T+1 exact 10:30 automatic acquisition/scheduling remains unverified with real Provider data.
7. Formal PIT still requires Xuntou or another qualified data product.

## 9. Next work package decision

The entry criteria for `WP-D4: 100–300 Operational Pool` are not satisfied because a real public
Archive does not reach `OUTCOME_PENDING`. The next work remains WP-D3 closure:

```text
qualified same-day security-status evidence
-> controlled 14:55 acquisition window
-> real Archive Replay to OUTCOME_PENDING
```

Only after those facts are observed with stable Replay hashes may the Operational Pool expansion
be proposed.
