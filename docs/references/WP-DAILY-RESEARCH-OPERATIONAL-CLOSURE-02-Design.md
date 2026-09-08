# WP-DAILY-RESEARCH-OPERATIONAL-CLOSURE-02 — Design

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Operational implementation contract; no research, Provider, trading, or Production promotion
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-09-08
> **Baseline:** `origin/main@1562855928b2b7e839883838f367876cc49d7391`

## 1. Problem and boundary

The existing post-close slice already freezes one exact Model use, input
snapshot, prediction, Outcome plan and Evaluation plan on the canonical Market,
Dataset, Decision, Model, Outcome, Evaluation, Artifact and Runtime owners. This
work closes its operational continuation. It does not add a model, change the
frozen research protocol, create another scheduler, or make the draft target
schema a production or trading system.

The execution-time audit found three direct defects and two incomplete seams:

1. `daily_tick` emits `PROCESS_DOWNTIME_MISSED_PUBLICATION`, while the real
   abstention command rejects that reason.
2. pending Outcome discovery is limited to the current
   `experimental_model_use_id` and then compares old frozen plans with the current
   template; model replacement can therefore orphan published evaluation work.
3. prospective admission treats absence of a conflicting generation as proof of
   ownership. Before the first generation row exists, a foreign-series Run can
   pass that negative test.
4. the 64-session check limits the complete Model-use lifetime before subtracting
   already represented windows, rather than bounding only outstanding work.
5. prediction report generation has an immutable Artifact identity, but delivery
   has no durable, separately inspectable Runtime identity. Daily health does not
   expose all required continuation boundaries.

Historical failures, published reports, research results, registered migration
bytes and immutable Verification records remain unchanged. A missed-window record
is made at the current database time and remains an abstention; it is never
relabeled as a historical prediction.

## 2. Considered shapes

Three implementation shapes were considered:

- add daily task, report and notification tables plus a new dispatcher;
- infer everything by scanning Artifact receipts and perform notification as an
  unjournaled side effect;
- retain Runtime as the sole work/attempt journal, add exact read projections and
  narrow admission capabilities, and represent delivery as its own deterministic
  Runtime Run.

The third shape is selected. It preserves the existing owners, lock order,
transaction boundaries and replay model. It also makes prediction, report and
delivery different identities without introducing a parallel Authority. No DDL
is required: Run/Step/Attempt, command receipt and Artifact already carry the
needed durable state.

## 3. Exact prospective-series admission

The operational session gains a transient positive capability compiled from the
frozen manifest and prospective Runtime plan. The capability contains:

- exact series, generation, predecessor, Archive and Target identities;
- exact manifest/config hash and code SHA;
- exact Schedule identity/revision;
- exact Run ID, fire key and complete Step identity roster for each admitted Run.

Entering the capability first verifies that the manifest declares the supervisor
series. Claim and deadline-recovery admission then require the persisted Run,
Schedule, config hash, code SHA and complete Step roster to equal that capability.
For an initial predeclare, only its exact predeclare Run is admissible before the
generation exists. After predeclaration, capture and maintenance Runs additionally
require an exact canonical Archive/generation/series/Target/config binding. A
missing generation is no longer positive evidence.

The capability is process admission only. Runtime still owns claims, leases and
fences; Market still owns Archive facts. The existing per-series lock and database
writer lock are acquired in the same order, and no transaction or advisory-xact
lock spans Provider or Artifact byte I/O. Worker text and implementation-prefix
matching do not establish series ownership.

## 4. Daily work discovery and continuation

New prediction admission and old result settlement are separate decisions:

- the current template must still resolve an exact configured Model use, and a
  revoked, expired or not-yet-valid use cannot create a new prediction;
- historical work is discovered from every frozen `daily-outcome-*` Runtime Run,
  independent of the current use;
- each recovered plan is verified against its own immutable config Artifact,
  deterministic Run identity, original ModelVersion, Target, strategies, code SHA
  and input snapshot. Current template bytes never replace it.

Discovery is bounded and ordered by due/request time and Run identity. It returns
active, waiting and failed work. One item is allowed to fail validation or require
reconciliation without preventing later items in the same bounded scan from being
examined. Terminal failure is reported, never reopened or filtered away. Mature
claimable work is advanced with a bounded step budget; future work remains
`PENDING_MATURITY`; missing target observations receive the existing bounded
canonical collection allowance and then typed Outcome missingness.

Expired attempts are recovered before a new claim. A normal exception that leaves
an Attempt live is durably failed with a closed error code. A process death leaves
the lease for restart recovery. If an owner commit already finalized the Step but
the caller did not receive the return value, re-entry observes the terminal fact
or exact receipt and does not duplicate it. `WAITING`/unknown-effect and `FAILED`
Runs require explicit reconciliation; they are not automatically reset.

The downtime scan pages across the actual activation interval, subtracts existing
prediction and abstention Runs in bounded batches, and returns at most the current
outstanding-work budget. A long-lived use is therefore not rejected merely for
having more than 64 historical sessions.

## 5. Time, data and health

PostgreSQL clock and captured canonical `trading_session` facts remain the only
calendar source. No weekday calculation or silent next-date substitution is
introduced. Calendar exhaustion produces a typed daily state and health alert;
the existing prospective Market capture/normalization continuation remains the
only way to extend calendar evidence.

Published predictions and their input snapshots remain immutable. Late input,
missing or suspended members, SourceGap, exhausted observation rounds and cutoff
misses retain typed states. Target data is observed after maturity through the
canonical Market path; later corrections use existing append-only revisions and
do not rewrite Forecast or prior Outcome revisions.

The daily health projection reports at least:

- last successful prediction publication and report identity;
- pending-maturity, claimable-settlement, waiting and failed backlogs;
- calendar remaining-session count and last captured session;
- current Model-use active/revoked/expired/expiring state;
- latest relevant captured/normalized market observation and a factual freshness
  status, without turning freshness into Provider qualification.

Counts are explicitly bounded. A truncated projection says so and does not report
the partial count as complete.

## 6. Report, delivery and feedback

Prediction and Evaluation reports continue to be immutable Artifact projections.
Each report has a separate Artifact binding. Delivery, when explicitly configured,
uses a deterministic Runtime Run keyed by report Artifact and channel. Its Step
freezes the report hash, channel, expiry and delivery request hash.

The delivery adapter returns one of four facts: delivered with an opaque receipt;
proven not sent and retryable; terminal rejection; or unknown effect. Runtime
Attempt/receipt state provides persistent deduplication and attempt history.
`EXTERNAL_EFFECT_PROVEN_ABSENT` may resume a bounded retry; an unknown effect
enters `WAITING` and is never blindly resent. The Step deadline provides expiry.
No channel or credential yields `NOT_CONFIGURED` and no network call; this cannot
block prediction publication or historical Outcome/Evaluation recovery.

An Evaluation report exposes its frozen sampled, eligible, feature-ready,
predicted, mature and estimable denominators, model and rule-baseline comparison,
and a stable manual-follow-up key. Optional human disposition is an immutable
Artifact/receipt linked to that key. It cannot tune, qualify, promote or overwrite
an earlier negative result.

## 7. Acceptance and evidence ceiling

The minimum discriminating gate covers the real downtime handoff, wrong-series
initial admission, concurrent/lost-lock/recovery paths, model revoke/switch with
old settlement, calendar/cutoff/missing/late/repeat behavior, delivery dedup and
reconciliation with an isolated fake, and one disposable-PostgreSQL vertical
publication-to-Evaluation/report/replay chain. A clean build and installed-wheel
smoke must include all new modules/resources.

Synthetic clocks, fixtures and restored copies prove engineering behavior only.
They do not prove a real future prediction, Provider semantics, continuous
service, formal PIT/OOS Alpha, trading, Production readiness or delivery to a real
recipient. Actual immature predictions remain `PENDING`; this package does not
wait for, backfill or pre-announce a future result.
