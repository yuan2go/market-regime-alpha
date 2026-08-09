# WP-PIT-01 Formal Point-in-Time Authority Convergence Design

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Merge-readiness design for WP-PIT-01 / Draft PR #42
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-08
> **Supersedes:** The first WP-PIT-01 design on the unmerged branch
> **Superseded By:** None
> **Related Documents:** ../../../AGENTS.md, ../../architecture/domains/00-Data-Source-and-PIT.md, ../../status/Current-State.md
> **Code Evidence:** Completion is established only by the final-commit PostgreSQL, authority-resolution, concurrency, leakage, replay and repository quality gates.

## 1. Scope and evidence ceiling

This correction stays inside the existing Data Source and PIT bounded context.
It does not create a second PIT system, change Model lifecycle ownership, grant
Entry authority, implement H8/H9, add a UI, integrate a Broker or promote any
public Provider.

Passing the engineering gates may establish only:

```text
FORMAL_PIT_ENGINEERING_AUTHORITY_IMPLEMENTED
```

It cannot establish:

```text
REAL_PROVIDER_FORMAL_PIT_ESTABLISHED
FORMAL_PIT_VALIDATED
FORMAL_OOS
SHADOW
PRODUCTION
```

## 2. Compatibility decision

No durable PIT v1 instance exists. The audit found:

- no tracked PIT v1 Artifact outside the unmerged implementation, tests and
  documentation;
- no PIT v1 package under the local `artifacts/` tree;
- no PIT authority table in any schema of the configured local PostgreSQL
  database;
- no existing formal Artifact or Replay reference to a PIT v1 evidence ID.

Migration 028 and all PIT contracts are therefore corrected in place before
merge. No v1 Reader/writer split is introduced. This avoids creating permanent
compatibility debt for an unmerged, fixture-only contract.

## 3. Confirmed defects

### 3.1 Required-fact collision

`FormalPITValidationRequest` currently deduplicates only complete
`PITRequiredFact` values. `PostgresPITAuthority._as_of` then builds a dict keyed
only by `logical_key`. Different kinds or subjects can therefore overwrite one
another after coverage validation.

The corrected contract requires `logical_key` to be globally unique within a
request/query. Exact duplicates are also rejected rather than silently
deduplicated. A typed `PITContractError` is raised by:

- `FormalPITValidationRequest.create` and direct construction;
- `PITAsOfQuery.create` and direct construction;
- the PostgreSQL as-of and validate entry points before SQL selection.

### 3.2 Caller-authored Artifact authority

The current ledger compares caller-authored IDs and hashes but never resolves
them through canonical Readers. A fabricated, internally consistent graph can
therefore produce satisfied fixture evidence.

The corrected design adds one narrow resolution seam:

```text
PITArtifactAuthorityResolver
→ existing canonical Reader
→ reconstructed canonical object
→ exact kind / ID / hash / schema / temporal / eligibility verification
→ immutable PITArtifactAuthorityResolution
→ PostgreSQL resolution receipt
```

The resolution receipt is an index and admission proof for an authority owned
elsewhere. It does not copy or replace Dataset, Universe, Feature or
SourceManifest ownership.

The production filesystem resolver reuses existing strict Readers for types
that have them. A type without a reliable canonical Reader fails with a typed
`PITArtifactAuthorityUnavailableError`. In particular, the current real
composition must fail closed for any unresolved Eligibility, Model
Configuration or Validation Protocol authority. Tests may inject a bounded
fixture resolver; such results remain `FIXTURE` evidence.

Every admitted fact binds the exact Source Qualification ID/hash that admitted
it, plus the exact Artifact and SourceManifest resolution IDs/hashes. Validation
also binds resolutions for Dataset, SourceManifest, Universe, Eligibility,
Feature materializations, Model Configuration and Validation Protocol.

### 3.3 Global revision serialization

The current `pit-authority-revision/global` advisory lock gives a committed
prefix but serializes every source qualification, fact and validation.

Three designs were compared:

1. **Global committed prefix.** Simple replay, but maximum write throughput is
   bounded by one complete PIT transaction at a time.
2. **Scope revision vectors.** Allows concurrency, but adds vector snapshots,
   cross-scope consistency policy and replay/CAS complexity that is not needed
   for the current PostgreSQL boundary.
3. **PostgreSQL transaction snapshot plus explicit immutable selections.** A
   `REPEATABLE READ` validation transaction sees one commit-visible database
   snapshot. The evidence stores the exact selected Fact, Source Qualification
   and Artifact Resolution identities/hashes. This is selected.

The identity sequence remains an append-only audit order. Because PostgreSQL
sequence allocation is not commit ordering, `authority_revision` becomes an
audit watermark only; it is not a historical-world prefix and is never the
sole replay authority.

## 4. Contracts

### 4.1 Artifact resolution

`PITArtifactKind` is a closed enum covering the authority types accepted by the
PIT boundary, including SourceManifest, Market Data Dataset, Trading Calendar,
Universe, Eligibility, Feature Materialization, Adjustment Policy, Model
Configuration, Validation Protocol, Provider Evidence and Provider Archive.

`PITArtifactAuthorityResolution` binds:

- reference kind, Artifact ID and canonical content hash;
- reconstructed canonical type and schema;
- Reader contract name/version;
- data eligibility and formal-PIT status when the canonical type exposes them;
- available/effective/decision time metadata when the canonical type exposes
  it;
- physical package checksum when the Reader provides one;
- resolution time, actor and reason.

Only the configured resolver can create a resolution during
`record_artifact_resolution`. Other commands accept references, not caller-made
resolution receipts.

### 4.2 Provider qualification

`PITSourceEvidenceLevel` is ordered explicitly:

```text
FIXTURE
REPLAY
FREE_DATA_EXPLORATORY
PIT_INCOMPLETE
FORMAL_PIT_CANDIDATE
FORMAL_PIT_PROVIDER
```

`PITProviderEvidenceKind` supplies typed evidence such as Provider contract,
historical availability, revision policy, dataset versioning, archive
integrity and independent validation. Formal qualification requires the full
policy-defined evidence set, and every evidence reference must have a canonical
resolution receipt.

`ProviderQualificationPolicy` is content-addressed and bound into each
qualification. The repository default caps Tencent, BaoStock, AKShare and free
Tushare at exploratory/incomplete levels and caps the current Xuntou direction
at candidate pending real evidence. No default Provider can reach
`FORMAL_PIT_PROVIDER`. Tests use an explicit fixture policy, which does not
change the production ceiling.

A `FORMAL_RESEARCH` fact requires an active exact-source qualification at
`FORMAL_PIT_PROVIDER`. The recorded fact stores that qualification ID/hash.
Qualification/suspension takes an exclusive source lock; fact admission takes a
shared source lock, allowing unrelated facts under the same stable source to
proceed concurrently while making qualification races deterministic.

### 4.3 Temporal evidence mode

`PITFactEvidenceMode` distinguishes:

```text
PROSPECTIVE_CAPTURED_PIT
HISTORICAL_PROVIDER_PIT
```

Both modes retain Event Time, Effective interval and Provider Available Time.
The database records `system_imported_at`; a caller cannot supply or backdate
it.

Prospective evidence requires:

```text
provider_available_at <= decision_time
provider_recorded_at <= decision_time
system_imported_at <= decision_time
```

Historical Provider PIT permits a later system import and later provider
recording of the historical archive, but requires all of:

- historical `provider_available_at` no later than DecisionTime;
- non-empty Provider revision and Provider dataset version;
- an exact resolved Provider Archive ID/hash;
- typed historical availability, revision and archive evidence;
- an active `FORMAL_PIT_PROVIDER` qualification under the bound policy.

The system import time remains factual and may be later than DecisionTime. It
is never rewritten to impersonate historical availability.

### 4.4 Missing evidence

Formal validation maps missing required facts to typed codes, including:

```text
HISTORICAL_AVAILABLE_AT_UNAVAILABLE
HISTORICAL_THEME_MEMBERSHIP_UNAVAILABLE
HISTORICAL_ETF_MEMBERSHIP_UNAVAILABLE
HISTORICAL_ST_STATUS_UNAVAILABLE
HISTORICAL_SUSPENSION_STATUS_UNAVAILABLE
HISTORICAL_LISTING_STATUS_UNAVAILABLE
CORPORATE_ACTION_AUTHORITY_UNAVAILABLE
```

Current ST, suspension, listing, Theme or ETF state is never used as a
historical substitute. Missing/unknown authority always rejects.

## 5. Transaction, lock and snapshot model

The global PIT revision lock is removed only after replay ceases to depend on a
revision prefix.

Lock scopes are:

```text
pit-idempotency/<idempotency_key>                 exclusive
pit-artifact-resolution/<kind:id:hash>            exclusive
pit-source-qualification/<manifest:provider:contract> exclusive for qualification
pit-source-qualification/<manifest:provider:contract> shared for fact admission
pit-fact/<scope_id:logical_key>                    exclusive for fact CAS
```

There is no global validation lock. Lock acquisition order is stable:
idempotency, source, then fact aggregate.

As-of reads and validation use PostgreSQL `REPEATABLE READ`. Validation performs
all coverage, Artifact resolution, qualification and fact selection reads from
one transaction snapshot, then stores the snapshot and evidence in the same
transaction. Different logical keys, symbols and scopes can write concurrently.
Corrections for one logical key remain serialized and checked by revision plus
supersession CAS.

## 6. Immutable replay

`PITAsOfSnapshot` stores explicit selected bindings. Each binding contains:

- Fact ID/hash;
- Source Qualification ID/hash;
- fact Artifact Resolution ID/hash;
- SourceManifest Resolution ID/hash;
- evidence mode.

`FormalPITEvidenceArtifact` additionally stores every lineage Artifact
Resolution ID/hash used by validation.

Replay loads the stored request, snapshot and evidence; restores only the named
Facts, qualifications and resolutions; verifies every ID/hash; and reruns the
pure validation projection against that immutable set. Replay never asks for
the latest fact and never reconstructs a historical world using
`authority_revision <= cutoff`.

Consequently later corrections, source suspension, Provider revision/import or
Model Governance changes cannot alter an existing Formal PIT result.

## 7. Model Governance boundary

The existing bridge remains narrow:

```text
satisfied FormalPITEvidenceArtifact
→ ModelQualificationEvidence(FORMAL_PIT)
```

It records evidence only. It does not issue a qualification decision, mutate a
Model lifecycle, assign a Champion, activate Production or bypass Entry.

## 8. Verification

Tests must include:

- exact duplicate and cross-kind/cross-subject logical-key attacks, including
  direct dataclass construction and repository-entry bypass attempts;
- forged Artifact, SourceManifest and wrong-kind resolution attacks;
- default-policy rejection of public/free and unknown formal Providers;
- prospective late import and valid/invalid historical Provider PIT imports;
- future event/effective/available/recorded state and expired-state leakage;
- typed Theme, ETF, ST, suspension, listing and corporate-action missingness;
- concurrent different-key, different-symbol and different-scope writes;
- same-key correction CAS and qualification/fact races;
- validation during concurrent ingestion under a stable snapshot;
- replay after correction, source suspension, Provider revision/import and
  Model Governance changes;
- strict existing Readers and fail-closed missing Reader types;
- PostgreSQL 16 migration, append-only triggers and isolated schemas.

The final gate is:

```bash
uv sync --frozen --extra dev --extra postgres
uv run python scripts/check_docs_links.py
uv run pytest
uv run ruff check .
uv run mypy
uv run python -m build
git diff --check
```
