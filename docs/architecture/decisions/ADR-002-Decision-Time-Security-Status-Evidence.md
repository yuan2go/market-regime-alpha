# ADR-002 — Decision-Time Security Status Evidence

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Accepted architecture decision for public decision-time security-status evidence
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-07-30
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** README.md, ../../audit/WP-D3-1-Real-Decision-Evidence-Baseline.md, ../../superpowers/specs/2026-07-30-wp-d3-1-real-decision-evidence-design.md, ../../superpowers/plans/2026-07-30-wp-d3-1-real-decision-evidence.md
> **Code Evidence:** `main@2ecf4aad5096fa8e978f2b4e73b7630a87415a32`; implementation evidence is added after delivery

## Decision status

`ACCEPTED` on 2026-07-30.

## Context

WP-D3 separates protocol, Provider, Universe Policy and Eligibility Policy
authority and freezes BaoStock history and Tencent quotes independently. Real
LIVE remains fail-closed because Tencent does not establish current trading,
ST or listing status. BaoStock history responses contain `tradestatus` and
`isST`, but the existing path discards those columns and, more importantly, a
prior-session value cannot prove a current decision-time fact.

Fetching history and quotes in one CLI invocation also lets history acquisition
consume the 14:55 quote window. A later retrieval cannot be made valid by the
protocol's earlier Decision Time.

## Decision

### 1. Freeze Security Status as an independent source stage

The public LIVE acquisition sequence has three immutable evidence stages:

```text
HISTORY_SOURCE_FROZEN
SECURITY_STATUS_SOURCE_FROZEN
DECISION_QUOTE_SOURCE_FROZEN
```

The Application exposes each stage independently. Finalization is network-free
and consumes only verified stage receipts.

### 2. Represent status facts independently

Security-status evidence distinguishes:

```text
TRADING_STATUS
ST_STATUS
LISTING_STATUS
```

Suspension is represented by `TRADING_STATUS=SUSPENDED`; it is never conflated
with ST or listing state. Each observation retains event, availability,
retrieval, decision and policy-effective time independently, plus Provider,
source Artifact, authority, quality, reason, finality and eligibility.

### 3. Preserve prior-session status without promoting it

BaoStock daily `tradestatus` and `isST` values are archived as
`PRIOR_SESSION_STATUS`. They are useful lineage and diagnostics but cannot
satisfy a current decision-session critical fact.

Current status is eligible for SourceManifest projection only when the Provider
returned the exact decision-date observation and the observation was retrieved
and available no later than Decision Time. Unknown or late evidence remains
unknown.

### 4. Use BaoStock as an exploratory current observation

The LIVE profile queries exact decision-date BaoStock daily status and stock
basic listing status, preserves the raw responses and maps only documented
values. Actual retrieval time is the observation's availability bound. This
does not establish historical publication time, formal PIT or licensed
authority.

If BaoStock has not published an exact-date row by the decision window, the
fact remains unknown and that symbol is excluded. No static list, symbol
pattern or previous session may replace it.

### 5. Bind stages to the complete request scope

The new V3 acquisition-stage identity binds:

- RunRequestId;
- Decision Date and Decision Time;
- Provider Profile;
- Universe Policy;
- acquisition stage;
- normalized batch content and every raw payload hash.

V1 and V2 readers remain supported. V3 orphan recovery requires an exact scope
match, preventing cross-request or cross-date evidence reuse.

### 6. Enforce the decision window at all time boundaries

A quote is usable only when:

```text
event_time <= decision_time
available_time <= decision_time
retrieved_time <= decision_time
```

Current status is usable only when its availability and retrieval times are no
later than Decision Time. A protocol Decision Time never backdates Provider
evidence.

### 7. Preserve fail-closed, per-symbol isolation

Unknown, late, suspended, ST, delisted or otherwise insufficient facts exclude
the affected symbol with explicit reasons. Provider-wide failure, corrupt or
mis-scoped evidence, missing policy authority, or a final population below
five globally blocks the run.

## Alternatives considered

### Treat Tencent's unknown status as trading

Rejected because absence of evidence is not evidence of normal trading.

### Promote prior-session BaoStock status

Rejected because the status can change before or during the decision session
and the product does not prove current availability through the prior row.

### Maintain a static current-status list

Rejected because it is not auditable decision-time Provider evidence and cannot
establish suspension, ST or listing changes.

### Loosen the eligibility or quality gate

Rejected because it would manufacture candidates by weakening a safety
boundary instead of supplying missing facts.

## Consequences

Positive:

- current status has explicit, replayable Provider lineage;
- history acquisition no longer consumes the quote window;
- each stage is independently retryable without repeated Provider access;
- late and unknown facts remain visible per symbol;
- offline replay receives the exact same frozen evidence.

Costs and limitations:

- BaoStock may not expose the exact-date daily status row before 14:55;
- a real decision-window run is still required to qualify the runtime behavior;
- public evidence remains exploratory and does not establish formal PIT;
- three stage receipts add orchestration and compatibility tests.

## Invariants

Implementation must stop or exclude rather than:

- convert unknown status to known status;
- use prior-session facts as current facts;
- backdate retrieval or availability;
- accept a quote acquired after Decision Time;
- reuse a stage from another RunRequest;
- call a network Provider during replay or finalization;
- alter Feature, B0/B1, Target, Recommendation or Entry semantics;
- raise the existing research or trading authority ceiling.
