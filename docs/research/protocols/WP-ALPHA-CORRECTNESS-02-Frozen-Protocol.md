# WP-ALPHA-CORRECTNESS-02 Frozen Protocol

> **Status:** CURRENT_RESEARCH_PROGRAM
> **Implementation State:** FROZEN_DESIGN / CODE_NOT_STARTED / RERUN_NOT_RUN
> **Authority:** Pre-result correctness and Discovery-only execution protocol
> **Decision Date:** 2026-08-26
> **Repository Baseline:** `main@1a92ee41b02dd94df9ef4488c59cba55df4674ce`
> **Architecture Decision:** [ADR-014](../../architecture/decisions/ADR-014-Frozen-Target-Semantics-and-Independent-Correctness.md)
> **Baseline Audit:** [WP-ALPHA-CORRECTNESS-02 Baseline Audit](../../references/WP-ALPHA-CORRECTNESS-02-Baseline-Audit.md)
> **Evidence Ceiling:** `DISCOVERY_ONLY / FREE_DATA / PIT_INCOMPLETE / FORMAL_OOS=false / PRODUCTION_QUALIFIED=false`

This protocol freezes the Target-correctness repair before business-code
implementation or any new Outcome computation. Executable identities produced
later must bind the final implementation SHA, exact Dataset revision, new
Target protocol revision and new Experiment identity. This document does not
create those owners and does not revise any historical Evidence.

## 1. Objective and terminal answers

The Work Package shall:

```text
extract and persist the 8 predecessor failures
-> freeze one Target semantic specification
-> converge materializer/checker/report/replay
-> rerun Discovery only under new identities
-> compare correctness and economics on explicit populations
-> issue GO or NO-GO
```

Correctness may end `CORRECTNESS_SUPPORTED`, `CORRECTNESS_FAILED`,
`PARTIALLY_REPRODUCED` or `PHYSICAL_REPRODUCTION_NOT_ESTABLISHED`. Research may
remain `REJECTED` or `NOT_ESTIMABLE`. A negative result is valid and immutable.

## 2. Immutable predecessor boundary

The following predecessor owners remain unchanged:

| Owner | Exact identity |
|---|---|
| Historical run | `historical-research-run-0382e3c92084432a7d7b9c36` |
| Command hash | `sha256:0382e3c92084432a7d7b9c365d1c34c5164cf67a9f3dc5a0b88270a3422b12b0` |
| Experiment | `research-experiment-definition:d242097bff7299a4ed61745aa4f6272807d83a549178ac2c0af268b261db6315@sha256:d242097bff7299a4ed61745aa4f6272807d83a549178ac2c0af268b261db6315` |
| Code revision | `3b58c2a5e374e413fa6fb934ccfe284f39740a40` |
| Target protocol | `outcome-target-protocol:6718c60fc274d65b69d14eb954ebb71be71605835ae0460289b628085d522fd5@sha256:6718c60fc274d65b69d14eb954ebb71be71605835ae0460289b628085d522fd5` |
| Primary Target | `outcome-target:853ede76b6e80de700beb7d785f81fbb0d0801a67ed860798c63f96c7915ab6b@sha256:853ede76b6e80de700beb7d785f81fbb0d0801a67ed860798c63f96c7915ab6b` |
| Raw owner | `historical-data-owner-c744a6181b03ab8215ddb4ba@sha256:c744a6181b03ab8215ddb4ba8112ca117bc109057b52cc25e05e00a195d48092` |
| Normalized owner | `historical-data-owner-6dcb5f3850c7909b8c15428d@sha256:6dcb5f3850c7909b8c15428d0e0a19a2e4f97d2695e3902e7d95bd0d6d1ef23c` |
| Calendar | `trading-calendar-c5b2e78e0cf5c9a405bc307a@sha256:c5b2e78e0cf5c9a405bc307a889e57bdf526e565054d214b40ffec220673c862` |
| Discovery Evidence | `historical-evidence-f61fffd7e47cfcb901f5932e` |
| Correctness Evidence | `historical-evidence-fda0316e89f0c9e8275a3710` |
| Correctness proof | `alpha-correctness-proof:9196bf13d40dde78f50ab3314ac511d05f952f91b4075bf5f201c755eeb1067b` |
| Locked scope | `frozen-locked-oos-scope:ed65a20e87fba32e48194f3c74592d880defa8ec972e593aa69f84217751c8b3` |

The predecessor conclusion remains `REJECTED / CORRECTNESS_FAILED / NO-GO`.
External was not admitted and Locked OOS Outcomes were not consumed.

## 3. Frozen predecessor failure population

Owner reload located exactly eight failed primary Target rows. All have a
complete twelve-bar T+1 09:30-10:30 path. The diagnostic Daily bar was the
previous trading session's suspended close and was incorrectly used as the
Decision reference.

| Decision | Symbol | T+1 | Persisted Decision / 10:30 | Decision-source condition | Label / Outcome component |
|---|---|---|---|---|---|
| 2025-01-06 | `002252.SZ` | 2025-01-07 | 7.22 / 6.83 | no Decision-session 5m bar; ignored Daily `historical-normalized-bar-cb5ea088850e7e2f5e29452b` | `target-outcome-label:09107f0f…`; `historical-outcome-f140cd48b5c4df1db4cf7ded` |
| 2025-01-16 | `000408.SZ` | 2025-01-17 | 29.5 / 32.45 | no Decision-session 5m bar; ignored Daily `historical-normalized-bar-7256ad960b8b48a5a30e0ebf` | `target-outcome-label:71fb5cb4…`; `historical-outcome-b83dc2e99e2f5ca84482afc9` |
| 2025-02-07 | `601211.SH` | 2025-02-10 | 17.78 / 17.86 | exact 14:55 placeholder has null OHLC; ignored Daily `historical-normalized-bar-f02c48502595066ced341806` | `target-outcome-label:772e6400…`; `historical-outcome-da5e5a06ce67fa26814715c2` |
| 2025-03-07 | `688126.SH` | 2025-03-10 | 20.56 / 19.32 | exact 14:55 placeholder has null OHLC; ignored Daily `historical-normalized-bar-d650ca13f18270fdab501926` | `target-outcome-label:a0aba2bf…`; `historical-outcome-0368756a1af172ac212c517a` |
| 2025-03-26 | `600803.SH` | 2025-03-27 | 19.65 / 20.04 | exact 14:55 placeholder has null OHLC; ignored Daily `historical-normalized-bar-6d4637dc8dc76f88ebad4bcf` | `target-outcome-label:4c993cca…`; `historical-outcome-c1aab7c3f789dcab083a6beb` |
| 2025-03-28 | `301269.SZ` | 2025-03-31 | 111.52 / 114.63 | no Decision-session 5m bar; ignored Daily `historical-normalized-bar-aac64528049d8263c8543b41` | `target-outcome-label:a133715f…`; `historical-outcome-29fd761b0346cf9eedf8fd02` |
| 2025-06-09 | `603019.SH` | 2025-06-10 | 61.9 / 68.09 | exact 14:55 placeholder has null OHLC; ignored Daily `historical-normalized-bar-3c7ed7c320afe008ce4195cd` | `target-outcome-label:48c65224…`; `historical-outcome-229dbfef4743c6a084560fe7` |
| 2025-06-09 | `688041.SH` | 2025-06-10 | 136.13 / 143.23 | exact 14:55 placeholder has null OHLC; ignored Daily `historical-normalized-bar-200d5976e1ea982b2505cb78` | `target-outcome-label:dbb93be3…`; `historical-outcome-229dbfef4743c6a084560fe7` |

This table is a design-time audit projection, not the requested durable
failure-detail artifact. The implementation must persist full, unabbreviated
label/component/artifact hashes, exact Decision/Target/diagnostic source IDs,
all twelve Target source IDs/hashes, Raw request references and classification
for every row.

The frozen final classifications are:

- three rows:
  `DECISION_EXACT_1455_BAR_MISSING_WITH_IGNORED_PREVIOUS_SUSPENDED_DAILY`;
- five rows:
  `DECISION_EXACT_1455_BAR_UNPRICED_PLACEHOLDER_WITH_IGNORED_PREVIOUS_SUSPENDED_DAILY`;
- shared predecessor discrepancy:
  `PERSISTED_DECISION_REFERENCE_VIOLATES_EXACT_1455_PROTOCOL`.

These classifications explain the historical failure. Under the new protocol
the same source facts are an independently reproducible unavailable Decision
state, not an estimable return and not a failed Outcome path.

## 4. Frozen Target Semantic Matrix

| Dimension | `COMPLETE` | `PARTIAL` | `UNAVAILABLE` | `FAILED` |
|---|---|---|---|---|
| Decision reference | one valid same-session Raw 5m bar ending exactly 14:55 | prohibited for this exact point rule | no qualifying priced bar; placeholder/suspension/missing | conflicting exact bars, invalid structure, adjustment or identity conflict |
| T+1 09:30-10:30 Outcome window | exact 12 valid Raw 5m bars on the exchange grid | non-empty proper valid subset | no valid observed path bar | duplicate/conflicting/overlapping/off-grid/adjusted/identity-invalid evidence |
| 10:30 checkpoint observation | exact valid Raw 5m close ending 10:30 | an explicit non-exact observation may be diagnostic only | exact checkpoint absent/unpriced | conflicting exact checkpoint evidence |
| Checkpoint return | complete Decision reference plus complete checkpoint observation | never calculated from a fallback | either dependency unavailable | either dependency failed or arithmetic invariant fails |
| MFE / MAE | complete Decision reference plus complete applicable path | no numeric partial-window MFE/MAE; coverage remains diagnostic | reference or path unavailable | source/price/arithmetic integrity failure |
| Barrier passages | complete reference/path; exact first containing bar | same-bar ordering explicitly ambiguous where 5m data cannot order touches | reference/path unavailable | contradictory barrier/source evidence |
| Entry/execution proxy | separately resolved observation strictly after information cutoff when required | explicitly bounded proxy only | no executable observation | temporal or lineage conflict |

### Decision reference eligibility

Only a same-session `MINUTE_5` Raw/unadjusted bar with local `event_end=14:55`,
valid OHLC and verified identity is eligible. Daily, previous-session and
last-available observations are diagnostic only. They carry explicit ignored
fallback reason codes and cannot affect any numeric value or population.

### Outcome preservation

Decision absence never deletes the Target label or observed T+1 path. Source
lineage, checkpoint observation, price-limit state, suspension/missingness,
corporate-action facts and window coverage remain factual fields. Derived
metrics are null with their own status/reasons when their Decision reference is
unavailable.

### Calendar, price limits and corporate actions

- The next session comes only from the frozen canonical Calendar owner.
- A non-trading day is never inferred as a session.
- A priced limit-up/limit-down bar remains a factual observation and is
  annotated; it does not prove fillability.
- Suspended or empty placeholder bars do not provide prices.
- Raw-only corporate-action policy remains fail closed. No adjusted/raw mixture
  is accepted to rescue a return.

## 5. Shared-semantics and independent-reproduction contract

The new Target protocol owns the declarative semantic specification. Both
materializer and checker use it, but perform separate source-owner reads.

The materializer persists all three status dimensions, exact source lineage,
diagnostic-only fallbacks and derived values. The checker reopens the physical
Normalized package, selects sources without reading persisted numerical output,
recomputes the semantic result, then compares statuses, values, boundaries and
lineage.

Correctness is supported when every persisted state is independently
reproduced. An honestly unavailable return is a supported correctness result,
not a failure.

## 6. New identity and compatibility contract

The logical revision strings are frozen before implementation:

```text
target semantic schema        = target-semantic-specification/v1
semantic revision             = wp-alpha-correctness-02-target-semantics/v1
OutcomeTargetProtocol schema  = outcome-target-protocol/v2
protocol_version              = phase-e-free-5m-exploratory-v2
TargetOutcomeLabel schema     = target-outcome-label/v3
failure detail schema         = alpha-correctness-failure-detail/v1
failure index schema          = alpha-correctness-failure-index/v1
correctness Evidence schema   = alpha-correctness-evidence-projection/v2
Experiment campaign key       = WP-ALPHA-CORRECTNESS-02-DISCOVERY-V1
```

The actual content-addressed IDs and hashes do not exist at this design
checkpoint. They are derived only after the final code SHA, exact Dataset and
complete configuration are bound.

The rerun shall create, before materialization:

- a new Target semantic revision and content hash;
- a new `OutcomeTargetProtocol` identity;
- a new primary Target identity if its serialized definition changes;
- a new `ResearchExperimentDefinition` identity;
- a new Historical run/command identity bound to the final code SHA;
- new Target labels, components, Evidence, failure indexes and reports.

The Discovery sessions, owner-resolved Universe, factor definitions and
directions, equal-weight composite, Top-5, cost, thresholds, inference and
multiple-testing rules remain unchanged. Legacy Target protocol v1 and Target
label v1/v2 readers remain supported. Old owner reload/replay dispatches by old
revision and must remain hash-identical.

Migration is additive from packaged head 104: fresh install and 104→new-head
upgrade create the same v3/failure-index shape without updating legacy rows.
Rollback is application-level only: prior code may ignore dormant new tables,
but no v3 owner is converted to v2 and no historical row is deleted. Fresh,
upgrade and prior-reader compatibility are mandatory tests.

## 7. Failure-index persistence contract

The typed failure index is append-only and content-addressed. Its canonical
payload includes:

```text
source run / predecessor correctness Evidence
source Experiment / Target protocol / Calendar
Raw and Normalized owners plus normalization revision
analysis code SHA and semantic revision
ordered full failure details
index identity and hash
```

Each detail includes the fields required by ADR-014 and has its own stable
identity/hash. PostgreSQL stores the owner and relational detail/source
projections; reload verifies exact equality. A canonical physical JSON artifact
may be emitted for operator portability, but its path is never Authority.

The post-fix correctness Evidence references the predecessor failure index and
its own zero-or-more discrepancy index. Reports must display details rather
than only aggregate counts.

## 8. Discovery-only execution and forbidden reads

The new run may access only the original 126 Discovery Decision sessions from
2025-01-02 through 2025-07-11 and their adjacent Target sessions through
2025-07-14. It must not materialize or evaluate the frozen External sessions or
any Locked OOS Outcome.

Acceptance requires all of the following remain unchanged/empty:

```text
locked_oos_evidence_consumption = 0
locked_oos_target_observation_consumption = 0
locked_oos_raw_evidence_unlock = 0
outcome_values_read = false
```

No factor direction, Universe, sample, Target horizon, Top-K, cost, threshold,
tolerance or stopping rule may change to improve results.

## 9. Required before/after comparison

The report shall compare predecessor and new runs for:

- Target `COMPLETE`, `PARTIAL`, `UNAVAILABLE` and `FAILED` counts by dimension;
- materializer/checker agreement and all failure classifications;
- common estimable population and rows lost/gained with reasons;
- RankIC, ICIR, positive IC ratio and dependence-aware uncertainty;
- Top-K gross/net, spread, turnover and drawdown;
- Universe, factor, Target and source-coverage identities/differences;
- exact effect of the eight corrected rows;
- causes of the older positive result versus the current adverse result.

Factor-direction reversal may be recorded only as a new untested hypothesis.
It is not executed in this Work Package.

## 10. Go / No-Go

`GO` means only that a separately reviewed new External Experiment may be
frozen later. It never starts External automatically. `GO` requires:

- `CORRECTNESS_SUPPORTED` under the new protocol;
- all eight predecessor failures persisted and explained;
- exact protocol/Data/code/Experiment identities frozen;
- full regression, migration, report and replay validation pass;
- no External or Locked OOS Outcome read;
- a credible explanation of old/new directional differences;
- Discovery economics that do not clearly reject the unchanged hypothesis.

Any unmet condition is `NO-GO`. In particular, correctness support alone is
insufficient. Adverse Discovery economics, unexplained sign reversal, required
direction/sample/threshold tuning, evidence-integrity failure or regression
failure preserves the negative result and stops before External, Forecast,
Strategy or Production work.

## 11. Validation contract

Implementation validation must cover semantic boundaries, placeholder and
suspension behavior, exact/missing 14:55, ignored Daily/nearest diagnostics,
complete/truncated windows, checkpoint/path independence, price limits,
corporate actions, materializer/checker equality, PostgreSQL fresh/upgrade
migration, append-only conflict behavior, idempotency/concurrency/lease/fence,
failure recovery, CLI/report/reload/replay, legacy Evidence compatibility and
External/Locked fail-closed access.

The complete repository validation ledger from `AGENTS.md` is required. Every
command is reported as `PASS`, `FAIL`, `NOT_RUN` or `BLOCKED`; no skip, xfail,
relaxed assertion or enlarged tolerance may hide a failure.
