# WP-16 Real Provider Evidence Gate A Blocker Design

> **Status:** CANONICAL_TARGET_ARCHITECTURE
> **Authority:** Frozen WP-16 feasibility, stop, and re-entry contract; not Provider Qualification Authority
> **Baseline:** `origin/main@16a4ab1d0d42a4144ef1bd1dcd15ac4ba5ab1087`
> **Owner:** Market & PIT
> **Frozen:** 2026-09-02

## Decision

WP-16 stops before Provider integration because the exact execution environment
and the actually inspected Provider/Product set contain no accessible Product
with direct recorded evidence for both P0 requirements:

```text
HISTORICAL_AVAILABILITY = F
REVISION_FINALITY = F
```

The bounded conclusion is:

```text
NO_ACCESSIBLE_PROVIDER_EVIDENCE_SATISFIES_P0
```

It is not a claim that every Provider or unlicensed Product is objectively
incapable. Access-blocked and unverified Products retain `B` or `?`; absence of
evidence is never converted to `X`.

The resulting state is:

```text
WP16_GATE_A = BLOCKED
WP16 = BLOCKED_BY_EXTERNAL_PROVIDER_EVIDENCE
WP16_ENGINEERING_IMPLEMENTATION = NOT_STARTED_BY_GATE
NEW_PROVIDER_PROTOCOL = NOT_REGISTERED
NEW_PROVIDER_QUALIFICATION = NOT_RUN
FORMAL_PIT = BLOCKED
WP17 = NO-GO
```

The immutable WP-15 BaoStock Protocol, Capture, Artifact, complete Requirement
roster, and `REJECTED` Decision remain unchanged. This design neither revises
that result nor treats a new request as a repair of its historical Authority.

## Feasibility evidence vocabulary

The matrix uses exactly four states:

| State | Meaning |
|---|---|
| `F` | direct recorded evidence already supports the stated capability for the exact inspected Product/scope |
| `X` | the exact inspected Product or canonical adapter contract explicitly cannot supply the stated capability |
| `?` | capability evidence has not been established; no positive or negative conclusion is allowed |
| `B` | credential, runtime, license, entitlement, transport, or access blocks actual verification; underlying capability remains unproven |

An official feature page may establish that an interface family exists. It does
not by itself make a floor `F`. In particular, an update window, event timestamp,
download time, local database `known_at`, or a stable repeated response is not
the exact source revision's historical publication time or finality identity.

`X` is scoped to the exact row. An `X` for the current canonical BaoStock or
Tencent adapter contract is not a statement about every current or future
Product sold by that vendor.

## Corrected Gate A feasibility matrix

| Inspected Provider/Product | Coverage | Raw lineage | Historical availability | Known time | Revision/finality | Price basis | Trading calendar | Membership/status | Decision reference | Outcome path |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BaoStock `history_k_data_plus_5m_raw` canonical Product revision used by WP-15 | `F` | `F` | `X` | `F` | `X` | `F` | `?` | `?` | `?` | `?` |
| Tencent current quote canonical adapter surface | `?` | `?` | `X` | `?` | `X` | `?` | `X` | `X` | `?` | `X` |
| Tushare Pro daily/minute/calendar/status candidate products | `B` | `B` | `B` | `B` | `B` | `B` | `B` | `B` | `B` | `B` |
| Xuntou XtQuant/MiniQMT candidate products | `B` | `B` | `B` | `B` | `B` | `B` | `B` | `B` | `B` | `B` |
| Tonghuashun iFinD QuantAPI candidate products | `B` | `B` | `B` | `B` | `B` | `B` | `B` | `B` | `B` | `B` |
| Wind data-service candidate products | `B` | `B` | `B` | `B` | `B` | `B` | `B` | `B` | `B` | `B` |
| JQData candidate products | `B` | `B` | `B` | `B` | `B` | `B` | `B` | `B` | `B` | `B` |
| RQData candidate products | `B` | `B` | `B` | `B` | `B` | `B` | `B` | `B` | `B` | `B` |
| AKShare/EastMoney public endpoint candidate | `B` | `B` | `B` | `B` | `B` | `B` | `B` | `B` | `B` | `B` |

### Matrix interpretation

- BaoStock's `F` cells come only from the immutable WP-15 real Capture and
  Decision. Its historical-availability and finality `X` cells apply to the
  exact canonical Product revision whose adapter contract records
  `source_availability_status=UNKNOWN`, no `source_available_at`, and no
  Provider finality/revision metadata. The WP-15 Outcome-path result remains
  `REJECTED` for that frozen Protocol; the broader future Product capability is
  `?`, so the matrix does not promote that historical rejection into a
  permanent vendor claim.
- The current Tencent target adapter is explicitly a current-quote byte
  capture. It supplies neither a historical archive nor Provider-reported
  availability/finality metadata, so only that exact adapter surface receives
  P0 `X`.
- Tushare is installed, but no token or entitlement is configured. Official
  documentation describes daily/minute update windows and calendar/status
  APIs, but no actual response was available and no exact per-revision
  publication/finality contract was established. All floors therefore remain
  access-blocked, not failed.
- XtQuant is not importable, MiniQMT is not installed, and the retained
  capability probe produced no research evidence. Official documentation shows
  historical-data download interfaces but does not change the `B` result.
- iFinD official documentation shows historical/high-frequency data, exchange
  calendar, and point-in-time financial-data capabilities. It also describes
  general post-close ingestion timing. The execution environment has no iFinD
  SDK, token, client, or license, and the public response contract inspected in
  this WP does not establish exact historical minute publication timestamps or
  revision/finality/version semantics. Its capability is therefore `B`, with
  those unresolved contract questions remaining `?` behind the access block.
- Wind, JQData, and RQData are not installed or licensed in this environment.
  No capability conclusion is made.
- The attempted AKShare/EastMoney request failed at access time. AKShare is an
  aggregation library rather than evidence that the underlying endpoint
  publishes exact revision availability/finality metadata; every floor remains
  `B` for this execution.

Official feasibility references are the
[iFinD QuantAPI manual](https://quantapi.51ifind.com/gwstatic/static/ds_web/quantapi-web/help-center/manual.html),
[iFinD data FAQ](https://quantapi.51ifind.com/gwstatic/static/ds_web/quantapi-web/help-center/faq.html),
[Tushare daily interface](https://tushare.pro/document/1?doc_id=27),
[Tushare minute interface](https://tushare.pro/document/1?doc_id=234), and
[XtQuant interface documentation](https://docs.thinktrader.net/pages/36f5df/).
These pages are feasibility references, not recorded Provider Qualification
facts and not substitutes for captured bytes or vendor revision evidence.

## Gate A decision rule

Gate B may begin only when the exact execution environment can establish at
least one accessible Market-data Product for which both P0 cells are `F`.
Companion Products may supply calendar, membership, status, or other facts, but
they cannot assert availability/finality for another Product unless a vendor
contract concretely relates their publication record to that exact source
revision.

Because no inspected row satisfies the P0 conjunction, WP-16 performs none of
the following:

```text
new Provider adapter
schema change
multi-Product Qualification Authority
Provider Qualification Protocol registration
Provider Capture or finality observation
Provider Qualification Decision
qualified historical visibility
Formal PIT admission
```

No test fixture, mock response, manual web transcription, repeated-download
stability check, or relaxed requirement may reopen the gate.

## Re-entry contract

Gate A may be reopened only after at least one new external condition exists:

1. a new secure Provider credential, entitlement, runtime, or license is
   actually available to the execution environment;
2. a versioned vendor contract or machine-readable Provider response establishes
   exact historical publication/availability and revision/finality semantics;
3. a newly available Product exposes those facts with exact Provider/Product/
   revision identity; or
4. an existing access-blocked Product becomes executable and produces new
   direct evidence that changes one or more `B/?` cells.

Re-entry requires a fresh `origin/main` fetch, independent branch/worktree,
secret-safe environment audit, new real read-only capability probe, and a new
Gate A matrix. The prior WP-15 Decision and this blocker Verification remain
immutable. A viable implementation must create a new Product revision and a new
immutable Protocol/revision before its first qualifying Capture; it may not
reuse or mutate the rejected BaoStock Protocol.

The required external evidence package is frozen in the
[WP-16 External Provider Evidence Acquisition Checklist](WP-ARCHITECTURE-REFOUNDATION-16-External-Provider-Evidence-Acquisition-Checklist.md).

## Evidence ceiling

This design proves only a bounded feasibility stop for one exact repository SHA,
environment, time, and inspected Product set. It does not prove:

```text
any unlicensed vendor is incapable
Provider Qualification = REJECTED or INCONCLUSIVE for a new Protocol
Formal PIT
FIT / VALIDATION / LOCKED_OOS
Prospective evidence
Alpha or Production readiness
```
