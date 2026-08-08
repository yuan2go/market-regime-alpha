# WP-PIT-01 Formal Point-in-Time Authority Design

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Implementation design for WP-PIT-01
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-08
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../../../AGENTS.md, ../../architecture/domains/00-Data-Source-and-PIT.md, ../../status/Current-State.md
> **Code Evidence:** Completion is established only by the final-commit PostgreSQL, leakage, replay and repository quality gates.

## 1. Decision

WP-PIT-01 adds one PostgreSQL Point-in-Time Authority inside the existing Data
Source and PIT bounded context. It does not add PIT logic to Model Governance
and does not treat existing caller declarations such as `pit_correct_for_scope`
or `FormalPitStatus.PIT_CORRECT_FOR_DECLARED_SCOPE` as proof.

Three shapes were considered:

1. Extend the Xuntou V4 research validator. This preserves useful provider
   mapping checks but is provider-specific, file-oriented and has no durable
   revision/as-of authority.
2. Add more PIT booleans and timestamps to existing Dataset, Universe and
   Feature Artifacts. This repeats temporal selection logic and continues to
   trust producers.
3. Add a generic append-only bitemporal fact ledger, deterministic as-of query,
   validation receipt and governance bridge. This is selected because it gives
   every current and future Provider one authoritative temporal seam while
   retaining the existing domain Artifacts as referenced outputs.

## 2. Authority model

One `PITFactRevision` represents one revision of one logical fact. It binds:

- scope, logical key, fact kind and subject;
- event time and effective interval;
- source available time and source recorded time;
- PostgreSQL-generated ingest time and monotonically increasing authority
  revision;
- explicit supersession/revision lineage;
- normalized Artifact identity/hash and SourceManifest identity/hash;
- provider contract identity, canonical value and DataEligibility.

Before any `FORMAL_RESEARCH` fact is admitted, the same authority requires an
explicit, evidence-referenced `PITSourceQualification` for the exact
SourceManifest hash, Provider and contract. Qualification and suspension are
append-only revisions. A caller-set DataEligibility value alone is never source
authority.

The ledger is append-only. A correction inserts the next revision and names the
immediately preceding fact. It cannot UPDATE or DELETE history. PostgreSQL
transaction advisory locks serialize global revision allocation and per-logical-
key CAS. Command hashes make retries idempotent and conflicting reuse fail.

`PITAsOfQuery` resolves exactly the requested logical keys using facts whose:

```text
event_time <= decision_time
effective_from <= decision_time < effective_to (when present)
available_at <= decision_time
recorded_at <= decision_time
ingested_at <= decision_time
authority_revision <= requested_revision
```

For each logical key it returns the greatest visible fact revision. Missing or
ambiguous facts are not silently carried forward; the result is rejected.
PostgreSQL `ingested_at` is an as-of predicate and cannot be backdated by a caller.
Historical replay pins the original authority revision so later ingestion or
correction cannot rewrite an earlier result.

## 3. Formal validation

A `FormalPITValidationRequest` binds the exact Dataset, SourceManifest,
Universe, Eligibility, Feature materialization, configuration, code, validation
protocol and Model Version Lineage identities. It also declares the complete
symbol scope and required fact keys.

The formal policy requires, per declared symbol:

- market data;
- historical Universe membership;
- trading status and suspension state;
- ST state;
- listing state;
- trading eligibility;

and requires one trading-calendar fact plus every declared Feature
materialization. PIT-adjusted inputs require explicit adjustment-factor facts;
research-back-adjusted data is always rejected. Optional fundamental,
index/industry/theme membership and ETF facts receive the same temporal and
revision checks when present.

Validation also requires all selected facts to be `FORMAL_RESEARCH`, exact
Artifact/SourceManifest lineage coverage, feature availability no later than
DecisionTime, and exact Model configuration/code/protocol lineage. Every pass
or rejection produces an immutable `FormalPITEvidenceArtifact` and PostgreSQL
receipt with stable reason codes.

Legacy historical Universe/Eligibility helpers remain readable research paths,
but they cannot produce Formal PIT evidence because they lack the PostgreSQL
recorded/ingest/revision chain.

## 4. Governance integration

The PIT bounded context owns validation and replay. A thin bridge converts only
a satisfied PIT Evidence Artifact into the existing
`ModelQualificationEvidence(FORMAL_PIT)` contract. The PostgreSQL Model
Governance repository verifies that the referenced PIT evidence exists, passed,
and matches the exact model/definition/lineage before accepting it. Directly
forged or failed PIT references are rejected.

Recording Formal PIT evidence does not issue a qualification decision, change a
model lifecycle, assign a Champion, or grant Production authorization.

## 5. Canonical call chain

```text
Provider Source Artifact / SourceManifest
→ explicit PostgreSQL PIT Source Qualification
→ PostgreSQL PIT Fact revisions
→ revision-pinned PIT as-of snapshot
→ Dataset / Universe / Eligibility / Feature lineage validation
→ immutable Formal PIT Evidence Artifact
→ existing Model Governance FORMAL_PIT evidence
→ explicit qualification decision (separate action)
→ Runtime Selector
→ Decision Runtime
```

## 6. Fail-closed boundary

Validation rejects future events/effective intervals, late availability,
recording or server ingestion, missing source qualification, suspended sources,
missing keys, revision gaps, wrong supersession, duplicate authority,
current-state substitution, incomplete Universe/eligibility coverage, future
Feature availability, unbound Artifact hashes, unqualified input authority,
back-adjusted prices, replay drift and unavailable PostgreSQL.

No in-memory fallback, current-database-state fallback or caller PIT boolean may
create a satisfied evidence result.

## 7. Verification and evidence ceiling

Tests use PostgreSQL 16 and cover migration 028, append-only protection,
idempotency, CAS/concurrent correction, accepted/rejected as-of queries,
revision-pinned replay, every requested leakage attack and Model Governance
consumption. Full pytest, Ruff, mypy, docs and build remain required.

Passing these gates establishes PIT engineering mechanics only. Repository
fixtures are not a qualified Provider archive. WP-PIT-01 does not establish
Formal OOS, Economic Validation, Alpha, Shadow or Production authority.
