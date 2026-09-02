# WP-15 Formal Research Proof Campaign Verification

> **Status:** CURRENT_STATUS
> **Verification State:** `WP15_PROVIDER_GATE_REJECTED / FORMAL_CAMPAIGN_STOPPED`
> **Authority:** Immutable execution ledger for one recorded-Provider gate; the PostgreSQL Provider Qualification Decision and exact captured Artifact remain business/evidence Authority
> **Owner:** Market Regime Alpha maintainers
> **Executed At:** 2026-09-02 (Asia/Shanghai)
> **Execution-Time Origin Main:** `origin/main@8067a4be74f697a01aaa996465c10ed5b45b5a7f`
> **WP-14 Verified Implementation:** `ca6f66b50ec2c55250cd82d2fa1ed6c5f35c29b8`
> **WP-14 Merged Main / Campaign Code SHA:** `8067a4be74f697a01aaa996465c10ed5b45b5a7f`
> **Containing Documentation Commit:** reported by the final handoff; this file does not claim a self-referential Git SHA
> **Schema Epoch:** `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`

```text
WP15_CAMPAIGN_EXECUTION = STOPPED_AT_PROVIDER_GATE
PROVIDER_QUALIFICATION = REJECTED
FORMAL_PIT = BLOCKED_BY_PROVIDER_GATE / NOT_RUN
LOCKED_OOS = BLOCKED_BY_PROVIDER_GATE / NOT_RUN
RESEARCH_QUALIFICATION = BLOCKED_BY_PROVIDER_GATE / NOT_RUN
PROSPECTIVE_CAMPAIGN = NOT_STARTED
PROSPECTIVE_PROVEN = NO
ALPHA_EVIDENCE = NOT_ESTABLISHED
ALPHA_PROVEN = NO
Runtime dispatch / CLI Cutover = NO-GO
Production = NO-GO
```

This is a successful execution of the mandatory first empirical gate and a
negative gate result. It is not `WP15_EXIT_GATE_PASS`. The rejection prevents
the frozen-hypothesis, Formal PIT, FIT, VALIDATION, LOCKED_OOS, Evaluation,
Evidence, Assessment, Research Qualification, and Prospective branches from
starting. No synthetic, mock, fixture, historical POC, guessed timestamp, or
alternate Provider was substituted.

## 1. Dependency preflight and exact code identity

WP-14 was pushed, reviewed, and merged through PR #97. A fresh fetch proved
that the independent WP-15 campaign worktree started at the exact merged main,
that the WP-14 implementation is an ancestor, and that the immutable WP-14
Verification is present.

```text
origin/main / campaign HEAD     8067a4be74f697a01aaa996465c10ed5b45b5a7f
WP-14 implementation           ca6f66b50ec2c55250cd82d2fa1ed6c5f35c29b8
WP-14 merge PR                 #97 / MERGED / 2026-09-02T08:52:53Z
branch                         agent/wp-15-formal-research-campaign
worktree                       isolated linked worktree wp-15-formal-research-campaign
root tree                      fc0ec844eb0fb266aebb12872e5833099abdbd58
source tree                    ccc42e2a732f0738c560d762ce3c61a1418c475e
tests tree                     4a2148ff361c057db68d4ee3e758266246b010dd
Market tree                    d0efafaa99e7cc575b619f1a3791112e432bb5f0
Runtime tree                   b01c45b9ca7009fe8ddc9cba227f2f656473c6c1
PostgreSQL tree                9bd9e87be8b4eab3173b69b685147a757e03e909
WP-14 Verification blob       8fd0b7205f31072dad26339d05bf24f72abbbcb6
baseline blob                  2b4f587da1f616ef6b0eeaf15621cbe1c116be50
```

The pre-existing `.idea/modules.xml` modification in the primary checkout was
never modified, staged, stashed, or committed. WP-15 changed no application,
domain, persistence, schema, Runtime, or Provider adapter code.

## 2. Real Provider and frozen purpose scope

Environment inspection found no Xuntou/XtQuant evidence bundle or configured
Provider credential. BaoStock was installed and its real public endpoint was
reachable, so the first gate used that actually available Product rather than
claiming the preferred Provider direction was available.

The protocol was registered before the capture and froze:

| Field | Frozen value |
|---|---|
| Provider / Product | `baostock / history_k_data_plus_5m_raw`, revision 1 |
| evidence class / purpose | `RECORDED_PROVIDER / HISTORICAL_PIT` |
| market / instrument / exchange | `A_SHARE / SSE_EQUITY_600519 / SSE` |
| resource | `sh.600519`, 2026-08-28 through 2026-09-01 |
| timeframe / basis | `MINUTE_5 / RAW_UNADJUSTED` (`adjustflag=3`) |
| DecisionTime rule | `SESSION_10_30_ASIA_SHANGHAI` |
| Outcome path | five trading sessions |
| requirements | all ten typed requirements, minimum count 1 and ratio 1 |
| protocol ID | `b510dfa0-dc94-5183-a3a1-a709ca068eb4` |
| protocol hash | `55f3ffc316b0f4812fe407824df8a60563b0062f2df1f610481a89e702f779da` |
| code Artifact | `deea00cb923e5d56a643d9b6e760dd3cd3ba47d7d872973d6f8a291f8be34806`, 2,478 bytes |
| config Artifact | `23cc197ad7f9775524eabace48a7cf54c4573dc25c609675c1f99df6def92605`, 638 bytes |

PostgreSQL authoritative ordering was:

```text
protocol registered_at       2026-09-02 17:09:00.129137+08
capture window               [17:08:59.114064, 17:10:15.114064)
capture_started_at           2026-09-02 17:09:01.003883+08
capture_completed_at         2026-09-02 17:09:01.152915+08
known_at                     2026-09-02 17:09:01.168800+08
evidence cutoff              2026-09-02 17:11:15.114064+08
decision decided_at          2026-09-02 17:10:15.200920+08
```

The Decision was deliberately completed only after the frozen capture window
closed. The ordering proves predeclaration before first capture, cutoff-safe
membership, and no posterior capture-roster shrink.

## 3. Real capture facts

The sole target composition root scheduled and executed one `SHADOW` Runtime
Run with one fenced `CAPTURE` Step. BaoStock returned success and 144 real
five-minute rows for `sh.600519`; the canonical adapter serialized the exact
response into a verified content-addressed Artifact.

```text
Runtime Run                   e5dde44b-1163-57f0-b78d-cc27397ce53f
Run / Step / Attempt          SUCCEEDED / SUCCEEDED / SUCCEEDED
fence token                   1
Capture receipt / audit       SUCCEEDED / CAPTURE_MARKET_DATA
Capture ID                    8598e2f8-b44e-4906-afa8-8510f5746c20
raw Artifact SHA-256          bc6478eaa090755e99e8e6f75f4dd4646195c603f151c8de38a956aa7fbca9ee
raw Artifact size             17,894 bytes
Provider result               error_code=0 / success
row / field count             144 / 10
first / last event            20260828093500000 / 20260901150000000
instrument / adjustflag       sh.600519 / 3
runtime_capture_lineage       true
artifact_verified             true
source_availability_status    UNKNOWN
source_available_at           NULL
provider_time                 NULL
limitation_code               HISTORICAL_AVAILABLE_TIME_NOT_PROVIDED
```

`known_at` is the database acquisition time. It is not reinterpreted as the
historical source publication/availability time. No timestamp was copied from
the bar event into `source_available_at` or `provider_time`.

## 4. Complete Provider qualification result

The immutable Decision is
`1f40e16d-4bab-510d-993f-199122c0b8da`, content hash
`9687190511749b01e2e51dd409ec5c8a938d3803ad3e4abeaf99e3991100120e`,
with `capture_count=1`, `requirement_result_count=10`, status `REJECTED`, and
reason `PROVIDER_REQUIREMENT_REJECTED`.

| # | Requirement | Result | Observed / satisfied | Reason |
|---:|---|---|---:|---|
| 1 | COVERAGE | SATISFIED | 1 / 1 | PROVIDER_REQUIREMENT_SATISFIED |
| 2 | RAW_SOURCE_LINEAGE | SATISFIED | 1 / 1 | PROVIDER_REQUIREMENT_SATISFIED |
| 3 | HISTORICAL_AVAILABILITY | REJECTED | 1 / 0 | PROVIDER_REQUIREMENT_THRESHOLD_FAILED |
| 4 | KNOWN_TIME | SATISFIED | 1 / 1 | PROVIDER_REQUIREMENT_SATISFIED |
| 5 | REVISION_FINALITY | REJECTED | 1 / 0 | PROVIDER_REQUIREMENT_THRESHOLD_FAILED |
| 6 | PRICE_BASIS | SATISFIED | 1 / 1 | PROVIDER_REQUIREMENT_SATISFIED |
| 7 | TRADING_CALENDAR | INCONCLUSIVE | 0 / 0 | INSUFFICIENT_PROVIDER_OBSERVATIONS |
| 8 | MEMBERSHIP_STATUS | INCONCLUSIVE | 0 / 0 | INSUFFICIENT_PROVIDER_OBSERVATIONS |
| 9 | DECISION_REFERENCE | INCONCLUSIVE | 0 / 0 | INSUFFICIENT_PROVIDER_OBSERVATIONS |
| 10 | OUTCOME_PATH | REJECTED | 5 / 0 | PROVIDER_REQUIREMENT_THRESHOLD_FAILED |

This scope therefore has neither an admitted Provider Decision nor qualified
historical visibility. Successful transport, exact bytes, acquisition time,
and raw price basis do not prove historical availability, revision finality,
calendar/membership evidence, Decision-reference coverage, or a complete
five-session Outcome path.

## 5. Reconciliation and stop proof

The owner read-only verifier returned:

```text
Protocol matched              true
Protocol mismatch_count       0
Decision matched              true
Decision mismatch_count       0
```

After the Decision, the isolated campaign database contained:

```text
Provider Protocol             1
Provider Capture              1
Provider Decision             1
Requirement Results          10
qualified bar visibility      0
Formal Research Campaign      0
Dataset                       0
Research Partition            0
Experiment                    0
Evaluation Run                0
```

Those zeroes are the executable stop condition. No hypothesis, Target,
Candidate baseline, cost assumption, FIT/VALIDATION/LOCKED_OOS roster, Outcome
access, Evaluation, Evidence, Assessment, Research Qualification, or
Prospective commitment was created after the failed Provider gate.

## 6. Database and command ledger

The campaign used a newly created isolated PostgreSQL 16.14 database. It was
not the WP-14 qualification database and did not reuse fixture evidence.

```text
database                       mra_wp15_campaign
database OID                   463145412
tables / views                 129 / 4
baseline SHA-256               df75c594bba25ab293723af615fcdad8f5b64781fddaf716f6fe586fffc8bc85
seed SHA-256                   9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11
catalog SHA-256                1d58cbace3120fb0c7048900bb5e162df8dfc40c2b4a26337b2e562093f03714
reference vocabulary SHA-256  52fd044a72334fe7334bacd7f5ef96cff72244f3f89fab1c48bcfa4ee095d0a6
SchemaManager.verify           PASS
```

| Command / check | Result |
|---|---|
| `git fetch origin main`; exact merged-main and WP-14 ancestry/Verification preflight | PASS |
| PostgreSQL 16 clean database create, target bootstrap, verify | PASS |
| real BaoStock login and `query_history_k_data_plus` capture | PASS |
| sole composition-root Runtime schedule/run/claim/fence/capture | PASS |
| raw Artifact SHA/size/readback and row-shape inspection | PASS |
| complete ten-floor Provider reducer | PASS, decision `REJECTED` |
| Protocol and Decision read-only reconciliation | PASS |
| no qualified visibility or downstream campaign Authority | PASS |
| `uv sync --frozen --extra dev --extra postgres` | PASS |
| canonical documentation inventory/metadata/links | PASS |
| documentation link unit tests plus target/legacy architecture boundaries | PASS, 38 tests |
| full repository engineering regression/static/build gates | NOT_RUN; no executable source/schema/test change, and this empirical result does not replace WP-14 exact-SHA qualification |
| GitHub Actions | `BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN` (`enabled=false`) |

Two superseded operator invocations are retained as failures rather than
promoted. The first documentation-test invocation exited because the fresh
worktree had not yet installed the dev extra; frozen `uv sync` corrected the
environment. The second named two nonexistent test paths and exited with pytest
code 4 after its preceding documentation checks passed. The corrected existing
paths then passed all 38 selected documentation and architecture tests. Neither
operator error changed repository or campaign Authority.

## 7. Failed gate and next required action

```text
EXACT_SHA = 8067a4be74f697a01aaa996465c10ed5b45b5a7f
FAILED_GATE = WP15_PROVIDER_QUALIFICATION_GATE
BLOCKER = RECORDED_PROVIDER_EVIDENCE_REJECTED
WHAT_IS_PROVEN = REAL_TRANSPORT + EXACT_CAPTURE_BYTES + RUNTIME_LINEAGE
                 + DATABASE_KNOWN_AT + RAW_PRICE_BASIS
                 + COMPLETE_TEN_FLOOR_DECISION + RECONCILIATION
WHAT_IS_NOT_PROVEN = HISTORICAL_AVAILABILITY + REVISION_FINALITY
                     + TRADING_CALENDAR + MEMBERSHIP_STATUS
                     + DECISION_REFERENCE + OUTCOME_PATH
                     + FORMAL_PIT + FIT/VALIDATION/LOCKED_OOS
                     + RESEARCH_QUALIFICATION + PROSPECTIVE + ALPHA
NEXT_REQUIRED_ACTION = obtain a real Provider/Product and recorded evidence
                       that satisfies the frozen purpose-specific requirements;
                       register a new immutable Protocol/revision and rerun the
                       Provider gate before any formal hypothesis is launched
```

The rejected Decision and captured bytes remain immutable negative evidence.
They must not be rewritten, relabeled, or bypassed by a caller assertion,
another current/latest lookup, a fixture, the historical BaoStock POC files, or
a weaker purpose silently substituted under the same campaign identity.
