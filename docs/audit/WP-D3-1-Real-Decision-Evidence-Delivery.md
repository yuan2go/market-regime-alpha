# WP-D3.1 Real Decision Evidence Delivery

> **Status:** CURRENT_STATUS
> **Authority:** Verified engineering and runtime delivery evidence for WP-D3.1
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-07-30
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** WP-D3-1-Real-Decision-Evidence-Baseline.md, ../architecture/decisions/ADR-002-Decision-Time-Security-Status-Evidence.md, ../superpowers/specs/2026-07-30-wp-d3-1-real-decision-evidence-design.md, ../superpowers/plans/2026-07-30-wp-d3-1-real-decision-evidence.md, ../status/Current-State.md
> **Code Evidence:** `feat/wp-d3-1-real-decision-evidence@347087c952cece0c7ee5cb475d717b4b098ee7da`; final documentation commit is recorded in Git history

## 1. Overall conclusion

```text
WP_D3_1_ENGINEERING_COMPLETE
REAL_1455_RUNTIME_VALIDATION_PENDING
PUBLIC_LIVE_STILL_DATA_BLOCKED
REAL_ARCHIVE_REPLAY_STILL_DATA_BLOCKED
```

`WP_D3_1_REAL_DECISION_EVIDENCE_CLOSED` is not established. The engineering
path can reach `OUTCOME_PENDING` from a fully qualified staged fixture and
from its offline Source Archive, but the real public run was intentionally
executed outside the 14:55 window. Its status and Quote evidence remained
unusable at the historical Decision Time and correctly produced no Candidate
output.

## 2. Baseline and Git delivery

```text
starting_main_head = 2ecf4aad5096fa8e978f2b4e73b7630a87415a32
branch = feat/wp-d3-1-real-decision-evidence
pr_25_merge_present = 8f10bd8
working_tree_delivery_files = source, tests, ADR, audit, plan and status only
```

The delivery is split into reversible commits:

```text
f772446 docs: audit and design wp-d3-1 decision evidence
879fa4b feat: add security status acquisition contracts
abd249b feat: bind security status provider evidence
d60fa91 feat: add security status stage artifact
a4c7358 refactor: split daily acquisition commands
dd291c6 fix: enforce decision-window status and quote availability
837ba97 feat: schedule staged public decision acquisition
d591628 test: prove three-stage recovery and replay equivalence
347087c fix: compose overlapping public provider declarations
```

## 3. Verified baseline problems

### BaoStock history status

`BaoStockHistoryClient` already requested `tradestatus` and `isST`, but the
normalized batch did not retain them. They are now preserved as typed
`PRIOR_SESSION_STATUS` observations with unknown historical availability and
finality. They never satisfy current critical status facts.

### Tencent status

`TencentCurrentQuoteClient` still emits `TradingStatus.UNKNOWN`. The Quote
product does not gain status authority through this work package.

### Missing current ST and listing facts

The real LIVE path previously created unknown placeholders. It now obtains an
independent BaoStock exact-date observation:

- daily `tradestatus`;
- daily `isST`;
- stock-basic `status`.

Only documented values are mapped. Missing, malformed, prior-date or late
evidence stays explicit and unusable.

### Decision-time scheduling

The previous `run` command fetched history immediately before Quote. History,
Security Status and Quote are now independent commands and immutable stages.
`finalize-run` constructs no network client and consumes only verified
receipts.

### Time semantics

Current status availability is bounded by actual retrieval time. It does not
claim Provider historical publication time. Quote usability now requires:

```text
event_time <= decision_time
available_time <= decision_time
retrieved_time <= decision_time
```

Status usability requires both availability and retrieval no later than
Decision Time. Protocol Decision Time remains independent of runtime
retrieval.

## 4. Implemented contracts and services

### Security Status Provider

`data/providers/public_composite/contracts.py` adds:

- `SecurityStatusFactType`;
- `SecurityStatusEvidenceScope`;
- `STStatus`;
- `ListingStatus`;
- `PublicSecurityStatusObservation`.

The observation binds symbol, typed value, PRIOR/CURRENT scope, event,
availability, retrieval, decision and policy-effective times, Provider/source
identity, authority, quality, reason, finality and eligibility.

`BaoStockSecurityStatusClient`:

- logs in once for the batch;
- applies a bounded socket timeout;
- isolates query errors per symbol;
- archives exact raw response bytes;
- queries the exact Decision Date;
- preserves unparsed and absent values;
- remains `EXPLORATORY`;
- declares `SECURITY_STATUS_PROVIDER_UNUSABLE` when no usable status fact
  exists.

### Three immutable acquisition stages

`PublicSourceAcquisitionStage` now has:

```text
HISTORY_SOURCE_FROZEN
SECURITY_STATUS_SOURCE_FROZEN
DECISION_QUOTE_SOURCE_FROZEN
```

V3 stage identity binds:

- RunRequestId;
- Decision Date and Decision Time;
- Provider Profile;
- Universe Policy;
- acquisition stage;
- normalized batch;
- every raw Payload Hash.

V1 and V2 readers remain routed and tested. V3 recovery accepts only an exact
scope match.

### Runner and Runtime Journal

`DailyLoopRunner` exposes:

```text
prepare_history
freeze_security_status
freeze_decision_quote
finalize_run
```

The existing `run` command is a convenience composition. Stage receipts remain
keyed by `RunRequestId`. Source publication derives and maps `DailyRunId`
without replacing the SQLite primary key.

Recovery tests cover:

- stage Artifact published before Receipt;
- Status failure after History;
- Quote failure after History and Status;
- repeat stage commands;
- Source Archive publication/receipt recovery;
- finalization with no Provider clients.

### Manifest, Quality and Eligibility

`build_security_status_source_evidence` projects only
`CURRENT_DECISION_SESSION` observations into current critical facts.
Prior-session status is a noncritical audit field.

Authority is fixed:

```text
Decision Time       -> PROTOCOL
Universe Membership -> UNIVERSE_POLICY
Eligibility         -> ELIGIBILITY_POLICY
Price/History/Status -> PROVIDER
```

Provider-wide unusable Status evidence is globally blocking. Individual
unknown/late status, late Quote, missing Price and short History exclude that
symbol. A combined test excludes five different symbols for five different
reasons and proves the remaining 15 continue through B0/B1 and
`OUTCOME_PENDING`.

### Feature, B0/B1, Recommendation and Entry

No Feature formula, Model weight, Target or ranker changed. Characterization
and archive-equivalence tests compare:

- Candidate Population;
- all Feature values;
- Prediction and Rejection;
- Score, Rank, Percentile and tie ordering;
- Coverage;
- Target ID and Dataset lineage;
- Feature Materialization lineage;
- per-model Top-5 Recommendations.

Entry remains `REJECT` or `WAIT_CONFIRMATION`. No `ENTER`, order, size,
position or Entry Price field was added.

### CLI

The CLI now supports:

```text
prepare-history
freeze-security-status
freeze-decision-quote
finalize-run
run
replay
settle
report
```

All four staged commands build the same deterministic RunRequest. `LIVE`
cannot use a local Source Archive and `REPLAY` constructs no Provider clients.

## 5. Fixture evidence

The fully staged 20-symbol fixture:

```text
status = OUTCOME_PENDING
candidate_population = 20
prediction_runs = 2
recommendations = 10
entry_assessments = 10 WAIT_CONFIRMATION
```

Its Source Archive is then recomputed in REPLAY without Provider clients.
Feature and complete B0/B1 projections match. Repeating the same Replay
command returns the same Artifact checksum.

The per-symbol isolation fixture:

```text
Trading Status UNKNOWN = 1 excluded
ST Status UNKNOWN = 1 excluded
Listing Status UNKNOWN = 1 excluded
Quote after Decision Time = 1 excluded
History insufficient = 1 excluded
remaining candidate population = 15
status = OUTCOME_PENDING
```

Fixture evidence is not represented as real public runtime evidence.

## 6. Real public LIVE evidence

The observed execution time was `2026-07-30 00:47 Asia/Shanghai`, outside the
controlled Decision window. A Decision Date of `2026-07-29` was used to prove
late evidence is rejected, not to claim a successful historical 14:55 run.

### Stage identities

```text
RunRequestId = run-request-49061cd1855fd64d7c83cf66
HistoryStage = source-stage-history-source-frozen-ffab94918671c91de56e6cd0
SecurityStatusStage = source-stage-security-status-source-frozen-d189e447d163ea6825ea09fc
DecisionQuoteStage = source-stage-decision-quote-source-frozen-1af22e562dda5e938d9d2e94
```

The stage raw inventories contain 20 BaoStock History Payloads, 20 BaoStock
Status Payloads and one Tencent Quote Payload. All three V3 scopes bind the
same request, `2026-07-29T14:55:00+08:00`,
`public-composite-live-v1`, and the frozen smoke policy.

### Source and decision identities

```text
DailyRunId = daily-run-95c801dbfaf1a3b9044e019a
SourceArchiveId = source-replay-5172f6671cf914d4f4ac291d
SourceManifestId = source-manifest-e07ce9c3e0478f831f46f203
DailyDecisionArtifactId = daily-decision-dbc9ca1f931f6727020bfae5
ReplayHash = sha256:73bf5614d4b14a109430071b501bd5fce3666bc52a606e1c176339475531ae20
```

Observed input counts:

```text
raw_payloads = 44
historical_daily_bars = 1200
quotes = 20
decision_price_observations = 20 INSUFFICIENT
```

BaoStock returned `TRADING`, `NOT_ST` and `LISTED` for all 20 exact-date
queries, but actual retrieval was after the historical Decision Time. Every
status fact therefore carries `STATUS_RETRIEVED_AFTER_DECISION`. No known value
was converted into usable decision evidence.

Result:

```text
status = DATA_BLOCKED
blocked_reason = GLOBAL_SECURITY_STATUS_PROVIDER_FAILURE
candidate_population = NOT_MATERIALIZED
prediction_runs = 0
recommendations = 0
entry_assessments = 0
```

The first finalization attempt exposed duplicate Provider limitations after
all three stages had already frozen. Commit `347087c` added deterministic
de-duplication. Re-running the identical command reused the three original
stage IDs and receipt completion times, then published the blocked Source
Archive and Decision Artifact. Focused recovery tests verify Provider call
counts for the same pattern.

## 7. Real Source Archive replay evidence

The real Source Archive was consumed with
`public-composite-replay-v1` into a separate Runtime Journal:

```text
RunRequestId = run-request-0d6014a0ef7b88e33bc8eeee
DailyRunId = daily-run-61bc671f2de6aa4fef18c93a
SourceArchiveId = source-replay-5172f6671cf914d4f4ac291d
DailyDecisionArtifactId = daily-decision-55e180a075a3e674b2a0d391
ReplayHash = sha256:e0a5aad156b3402467818ae967c6cf08ef457a9edc52260026d41e50444cc930
status = DATA_BLOCKED
blocked_reason = GLOBAL_SECURITY_STATUS_PROVIDER_FAILURE
```

The repeated Archive Replay and semantic `replay` command returned the same
Artifact ID and Replay Hash. REPLAY has no acquisition-client dependency and
the no-network boundary is covered by automated tests.

`settle` was not run for this real evidence because `DATA_BLOCKED` correctly
published no Recommendation. The existing MR1 settlement and report
reconstruction fixture tests remain green. The real blocked report was
successfully reconstructed.

## 8. Validation evidence

Final validation commands:

```text
python scripts/check_docs_links.py
python -m pytest -q
python -m mypy
python -m ruff check src tests scripts
python -m pip check
git diff --check
```

The final suite collected 1,109 tests. All passed; none failed or skipped.
The full pytest run emitted only existing pandas DataFrame-fragmentation
performance warnings from the Top-1000 backtest module. mypy, Ruff, pip check,
documentation validation and Git whitespace validation passed.

## 9. Authority boundary

```text
data_eligibility = EXPLORATORY
formal_pit = NOT_ESTABLISHED
formal_oos_alpha = NOT_ESTABLISHED
trading_authority = NOT_GRANTED
```

No successful operation, Fixture or real Provider response changes this
boundary.

## 10. Remaining gaps

1. A real trading-day 14:45–14:50 Status query must prove the BaoStock
   exact-date row is actually available before Decision Time.
2. A real 14:54:20–14:54:50 Tencent Quote freeze must complete before 14:55.
3. The real fixed-20 Source Archive must retain at least five eligible symbols
   and reach `OUTCOME_PENDING`.
4. The resulting real Archive Replay must reproduce nonempty Features, B0/B1
   PredictionRuns, Recommendations and Entry Assessments.
5. Formal PIT still requires qualified data authority; this public path
   remains exploratory even if the runtime window succeeds.
6. Real T+1 10:30 automated Settlement remains downstream of a real
   `OUTCOME_PENDING` run.

The next work remains WP-D3.1 runtime-window validation. WP-D3.2 settlement
automation and the 100–300 Operational Pool are not unlocked.
