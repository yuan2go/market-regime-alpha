# H6 Composite Operational Evidence Manifest Design

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Approved bounded design for H6 Composite Operational Evidence
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-04
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../../architecture/10-Production-Decision-Lifecycle.md, ../../architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md, ../../roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md, ../../status/Current-State.md
> **Code Evidence:** Design starts from merged PR #31 at `origin/main@e2cb9add258056815d15462bc83dfc64f43ddb8e`; hardened implementation checkpoint `654e02556080d1476b399ee5145989be743f47a0`.

## 1. Goal and bounded context

H6 makes the authority of operational research composition explicit:

```text
verified Phase D Daily Decision package
+ verified Supplemental Research Evidence package
+ explicit composition policy
→ terminal CompositeOperationalInputManifest
→ immutable exact-file package
→ append-only SQLite publication/replay index
→ ResearchInputBundleV2
→ existing Platform V2 research models
```

The manifest is a content-addressed authority index. It proves which original
authority owns each component and field group, but does not copy or replace
the original evidence. It cannot promote public/exploratory inputs to formal
PIT, formal OOS Alpha, production or trading authority.

H6 does not implement H4.5, H7, H8 or H9; it creates no Broker Order,
ManualTrade, Fill, Position mutation, Thesis-health transition or reducing-risk
decision.

## 2. Baseline facts and root cause

At `main@e2cb9add258056815d15462bc83dfc64f43ddb8e`:

- PR #30 (H4) and PR #31 (H5) are merged; migration 008 is current;
- `adapt_operational_research_inputs()` verifies a Daily package and a
  Supplemental bundle, then constructs `ResearchInputBundle` V1;
- that bridge hard-codes `ResearchEvidenceKind.HISTORICAL_IMMUTABLE_ARCHIVE`
  even though the composition is an operational exploratory snapshot;
- `ResearchInputBundle.source_manifest` and every Platform V2 Envelope retain
  only the Daily SourceManifest as the primary source authority;
- the Supplemental SourceManifest is present only as an undifferentiated input
  ID/hash pair, so consumers cannot prove its composition role or field scope;
- Platform V2 models, publisher and Reader accept only V1 input bundles;
- verified Daily and Supplemental package Readers already establish exact file
  sets, checksums and canonical reconstruction and can be reused.

The verified starting gate is 1398 tests passed, Ruff PASS, configured mypy
PASS over 258 source files, build PASS, documentation-link PASS and
`git diff --check` PASS.

## 3. Chosen architecture

H6 adds four isolated layers under `application/operational_research`:

1. `composite_manifest.py`: immutable policy, typed component/field
   references, terminal manifest and deterministic builder;
2. `composite_artifact.py`: exact three-file publisher and semantic Reader;
3. `composite_repository.py` and `sqlite_composite_repository.py`: storage
   Protocol, command/replay contract and migration 009 adapter;
4. `composite_service.py`: file-first application orchestration and crash
   recovery.

Platform V2 gains an independent `ResearchInputBundleV2` schema and a
read-only `ResearchInputView` Protocol. Existing models depend on the view;
publisher/Reader dispatch by exact input schema. V1 remains byte-for-byte and
hash compatible.

The old direct Daily + Supplemental → V1 adapter remains explicitly legacy
compatibility behavior. The operational CLI may no longer call it.

## 4. Composition status

`CompositeOperationalCompositionStatus` contains:

```text
ASSEMBLING
VERIFIED
DATA_INSUFFICIENT
CONFLICTED
```

`ASSEMBLING` is process-only and cannot be published. A manifest is immutable
and terminal: `VERIFIED`, `DATA_INSUFFICIENT` or `CONFLICTED`. Only `VERIFIED`
may create `ResearchInputBundleV2` or enter Platform V2. Missing required
evidence or coverage produces `DATA_INSUFFICIENT`; contradictory identity,
time, source or coverage claims produce `CONFLICTED`.

## 5. Content-addressed composition policy

`CompositeOperationalCompositionPolicy` has schema
`composite-operational-composition-policy-v1` and binds:

```text
profile_id
required_component_roles
required_field_authorities
allowed_data_eligibility
decision_time_policy
source_conflict_policy
coverage_policy
builder_revision
policy_id / policy_hash
```

There are no implicit values. H6 V1 supports only:

```text
decision_time_policy = EXACT_MATCH
source_conflict_policy = FAIL_CLOSED
coverage_policy = EXACT_PREDICTION_POPULATION
allowed_data_eligibility = [EXPLORATORY]
```

Any other policy value is rejected rather than silently approximated. Policy
identity covers sorted, unique typed requirements and all policy strings.

## 6. Typed component and field authority references

`CompositeOperationalComponentRole` includes:

```text
DAILY_DECISION_ARTIFACT
DAILY_SOURCE_MANIFEST
UNIVERSE_SNAPSHOT
ELIGIBILITY_SNAPSHOT
DECISION_PRICE_SNAPSHOT
PREDICTION_RUN
SUPPLEMENTAL_EVIDENCE_BUNDLE
SUPPLEMENTAL_SOURCE_MANIFEST
MARKET_OBSERVATION
THEME_OBSERVATION
CAPITAL_OBSERVATION
SYMBOL_OBSERVATION
THEME_MEMBERSHIP
ETF_THEME_MAPPING
ETF_OBSERVATION
STOCK_DAILY_BAR
```

A component reference binds role, scope key, artifact ID/hash, original
SourceManifest ID/hash, availability time and `EXPLORATORY` eligibility.
`(role, scope_key)` is unique. Reusing one artifact ID with a different hash is
a conflict; using the same original source for multiple typed scopes with the
same hash is allowed.

H6 canonical timestamps normalize to whole-second UTC RFC3339 with a `Z`
suffix before identity calculation. A container reference uses the maximum
explicit retrieval/availability time of its verified underlying authority set;
it does not invent availability from DecisionTime and does not claim the later
package-publication time was known at DecisionTime.

`CompositeOperationalFieldGroup` separates Daily authority:

```text
PRICE, TRADING_STATUS, ST_LISTING_STATUS, HISTORY,
UNIVERSE, ELIGIBILITY, PREDICTION_POPULATION
```

from Supplemental authority:

```text
MARKET_OBSERVATION, THEME_OBSERVATION, CAPITAL_OBSERVATION,
SYMBOL_CAPITAL_PROXY, THEME_MEMBERSHIP, ETF_THEME_MAPPING,
ETF_OBSERVATION, STOCK_DAILY_BAR
```

A field authority reference points to an existing typed component. It contains
no field value and cannot replace the original Artifact. `(field_group,
scope_key)` is unique. Policy requirements state the permitted component role
for each field group and the builder proves the reference exists.

## 7. Composite manifest

`CompositeOperationalInputManifest` uses schema
`composite-operational-input-manifest-v1` and binds:

- manifest identity/hash, terminal status, DecisionTime and created time;
- policy ID/hash and builder revision;
- Daily package, Daily SourceManifest, Supplemental package and Supplemental
  SourceManifest identities/hashes;
- complete component and field-authority references;
- missing evidence, source conflicts, reason codes and limitations;
- the fixed authority ceiling.

The fixed ceiling is:

```text
data_eligibility = EXPLORATORY
formal_pit = FORMAL_PIT_NOT_ESTABLISHED
formal_oos_alpha = FORMAL_OOS_ALPHA_NOT_ESTABLISHED
trading_authority = TRADING_AUTHORITY_NOT_GRANTED
```

Canonical restoration recomputes the semantic hash and identity, validates
sorting/uniqueness, revalidates policy ID/hash and rejects any authority
inflation.

## 8. Builder validation and classification

`CompositeOperationalManifestBuilder` accepts only
`VerifiedPhaseDDailyDecisionArtifact`,
`VerifiedSupplementalResearchEvidence`, a canonical-round-tripped policy and
an explicit timezone-aware `created_at`.

It validates:

- exact package Readers already proved package file/checksum integrity;
- Daily status and required snapshots;
- exact Daily/Supplemental DecisionTime;
- evidence availability no later than DecisionTime and manifest creation no
  earlier than DecisionTime;
- both SourceManifest identities/hashes and `EXPLORATORY` eligibility;
- each referenced source Artifact exists in its original SourceManifest;
- one artifact ID never maps to multiple hashes;
- all PredictionRuns have the same complete population;
- theme membership and symbol observation exactly cover that population;
- Theme and Capital theme sets match and all membership themes exist;
- Theme proxy ETFs, ETF mappings and ETF observations exactly match;
- every policy-required component role and field authority exists.

It never invents evidence. Missing package content, empty required collections
or absent authorities produce `DATA_INSUFFICIENT`. Time/identity/source,
population or exact-coverage contradictions produce `CONFLICTED`. A terminal
hard conflict takes precedence over missing evidence.

## 9. Immutable package and recovery

Each composite manifest package contains exactly:

```text
artifact.json
manifest.json
SHA256SUMS.json
```

`artifact.json` is the canonical composite manifest. `manifest.json` is the
reconstructible package projection and embeds the full canonical composition
policy. The Reader checks the exact file set, hashes, canonical manifest
identity, component identities, both SourceManifest identities, policy and
authority ceiling.

Publishing the same content-derived manifest twice returns the existing valid
package. An existing path with different or invalid content fails closed.
Staging directories use a manifest-prefixed temporary name and are removed on
failure; explicit orphan-staging recovery deletes only verified H6 staging
names under the configured H6 root.

## 10. Repository and migration 009

Migration 009 creates:

```text
composite_operational_manifests
composite_operational_components
composite_operational_field_authorities
composite_operational_commands
```

All tables are append-only through validated UPDATE/DELETE triggers. The
repository starts `BEGIN IMMEDIATE`, checks command idempotency, writes the
manifest and all projections, writes the command ledger and commits once.
Any error rolls back the complete SQLite transaction.

The command hash binds the idempotency key semantics to Daily and Supplemental
package identities/checksum hashes, both SourceManifests, policy ID/hash,
created time, builder revision and resulting manifest identity/hash. Same key
and hash replays the exact manifest; same key with another hash is rejected.

The repository stores package paths, source package paths, canonical policy
and command JSON as a publication/replay index. On read it:

1. reloads and verifies the immutable package;
2. validates every SQL projection against the canonical manifest;
3. reloads the original Daily and Supplemental packages;
4. re-runs the builder with the persisted policy and created time;
5. compares the replay result to the stored manifest.

It does not store or become a replacement authority for original raw data.
Weak schema, foreign keys or triggers fail repository initialization.

## 11. File/SQLite transaction boundary

H6 does not claim cross-storage atomicity. The application service executes:

```text
load verified source packages
→ build terminal manifest
→ write and verify staging package
→ atomic rename to final package
→ BEGIN IMMEDIATE
→ persist manifest/components/fields/command index
→ SQLite commit
```

Recovery is explicit:

- before rename: remove the orphan H6 staging directory;
- after package publication but before DB commit: replay verifies the existing
  package, then inserts the absent index transaction;
- DB row with missing or mismatched package: fail closed with reconciliation
  required;
- valid package without DB row: the same idempotent command repairs the index.

## 12. ResearchInputBundle V2 and V1 compatibility

`ResearchEvidenceKind` adds only
`OPERATIONAL_EXPLORATORY_ARCHIVE`. Existing
`SYNTHETIC_FIXTURE` and `HISTORICAL_IMMUTABLE_ARCHIVE` values remain valid.

`ResearchInputBundleV2` has schema `research-input-bundle-v2`, preserves the
model-readable fields and adds:

```text
evidence_kind = OPERATIONAL_EXPLORATORY_ARCHIVE
primary_source_manifest
composite_manifest
composite_manifest_id
composite_manifest_hash
```

Its primary SourceManifest is the Daily SourceManifest. The V2 bundle requires
a `VERIFIED` manifest and exact matching Daily/Supplemental identities. Its
lineage contains the Composite Manifest ID/hash and all required source
references.

`ArtifactEnvelope.source_manifest_id/hash` continues to mean the Daily primary
SourceManifest. Platform Market/Theme/Capital/Candidate envelopes include the
Composite Manifest ID/hash directly through V2 input lineage. The Research
Layer envelope binds both the V2 bundle ID/hash and Composite Manifest ID/hash.
H5 therefore sees a consistent primary SourceManifest while H6 composition
remains fully provable.

`ResearchInputView` exposes common read-only model fields. Platform models do
not fork. Reader schema dispatch restores V1 with the existing Reader and V2
with the strict V2 Reader. No V1 field or hash meaning changes, historical
packages and synthetic fixtures remain readable, and V1 cannot represent new
operational evidence.

## 13. Operational application and CLI

`CompositeOperationalEvidenceApplicationService` loads both verified source
packages, canonicalizes policy, builds and publishes the terminal package,
then calculates the package-bound command hash and persists or replays the
index. This ordering is deliberate: the command binds all three package
checksum identities. It runs no research model.

`scripts/build_composite_operational_manifest.py` requires Daily package,
Supplemental package, policy, database, package root, explicit created time and
idempotency key. It outputs manifest ID/hash, terminal status, reason/missing/
conflict codes and the authority ceiling.

`scripts/run_operational_research.py run` requires `--composite-package` plus
the original Daily and Supplemental package paths needed to materialize model
inputs. It verifies all three packages, proves that the Composite Manifest
binds the exact sources, replays the Builder, requires `VERIFIED`, constructs
V2 directly, runs the existing Platform runner and prints the H6 identity plus
unchanged authority limits.
The old direct adapter remains importable for historical compatibility tests
but is named and documented as legacy and is not reachable from the new CLI.

## 14. H5 integration and authority boundary

The cross-stage proof is:

```text
Daily + Supplemental
→ VERIFIED Composite package
→ ResearchInputBundleV2
→ ResearchLayerArtifact
→ SignalSnapshot
→ PathForecast
→ ThesisHealthObservationV2
```

The generated research chain retains one Daily primary SourceManifest and
proves Composite Manifest lineage through the V2 bundle. The H5 private replay
bundle remains explicitly `NOT_H6_AUTHORITY` and does not replace H6.

H6 does not fix these recorded gaps:

- `H5_CANONICAL_DECISION_INPUT_NOT_REPOSITORY_AUTHORITY`;
- H5 assessment exact-time coupling and absent durable scheduling/Position age;
- oversized `position/thesis_health.py`;
- H4.5 ExitAssessment-to-reducing-risk execution bridge;
- H7 durable Holding/Exit lifecycle and T+1 projector integration.

## 15. Test matrix

Tests cover:

- policy/manifest round trips, identities, roles, authorities and ceiling;
- valid, missing and conflicting builder cases for every required relationship;
- V2 construction gates and V1 exact compatibility;
- package file sets, checksums, semantic tamper and idempotent publication;
- migration/schema/triggers, save/read/restart, projections, idempotency,
  rollback and builder replay;
- pre/post-rename crash recovery and DB/package reconciliation;
- composite CLI, operational V2 CLI and rejection of non-verified manifests;
- Platform V2 lineage and H5 end-to-end consumption;
- focused H4/H5 regression and full repository gates.

## 16. Rollback and forward repair

The code rollback removes only the H6 V2 operational route; V1 Readers and
historical packages remain valid. Migration 009 down drops only H6 triggers
and tables and removes version 9 from `pdl_schema_migrations`. Published H6
packages remain immutable evidence and may be re-indexed after forward repair.
No rollback edits Daily, Supplemental, H4, H5, ManualTrade or Fill data.

## 17. Completion and non-claims

H6 is complete only when domain, package, SQLite, CLI, V1/V2 compatibility,
H5 integration, H4/H5 regression, full gates and commit-bound documentation
all pass.

Even then:

```text
FORMAL_PIT_NOT_ESTABLISHED
FORMAL_OOS_ALPHA_NOT_ESTABLISHED
SHADOW_READY_NOT_ESTABLISHED
TRADING_AUTHORITY_NOT_GRANTED
REAL_BROKER_AUTHORITY_NOT_IMPLEMENTED
PRODUCTION_READINESS_NOT_ESTABLISHED
```
