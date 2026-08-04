# H6 Composite Operational Evidence Delivery

> **Status:** CURRENT_STATUS
> **Authority:** Commit-bound H6 engineering delivery record
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-04
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../superpowers/specs/2026-08-04-h6-composite-operational-evidence-design.md, ../superpowers/plans/2026-08-04-h6-composite-operational-evidence.md, ../status/Current-State.md, ../status/Capability-Matrix.md, ../status/Gap-Register.md
> **Code Evidence:** Starting main `e2cb9add258056815d15462bc83dfc64f43ddb8e`; design checkpoint `0c910983c5a3ec02781bb45e24f0678464fbc6e0`; implementation checkpoint `f88aa33c8e12ce155abfb9bade6c77773dd78c41`; hardened checkpoint `654e025b97c5d9553d7614b4b5be0898272aacbc`.

## 1. Delivered boundary

H6 replaces the new operational path's false
`HISTORICAL_IMMUTABLE_ARCHIVE` label with an explicit dual-authority chain:

```text
verified Daily package
+ verified Supplemental package
+ content-addressed composition policy
→ terminal CompositeOperationalInputManifest
→ immutable package and append-only publication/replay index
→ ResearchInputBundleV2(OPERATIONAL_EXPLORATORY_ARCHIVE)
→ existing Platform V2 models
```

The implementation adds no model, Entry action, Thesis transition, H4
decision, ManualTrade, Fill, Position mutation or Broker Order. It grants no
trading authority and establishes neither formal PIT nor formal OOS Alpha.

## 2. Original defect and corrected authority model

The prior `adapt_operational_research_inputs()` built a V1 input bundle and
hard-coded `HISTORICAL_IMMUTABLE_ARCHIVE`. The Daily SourceManifest remained
the sole named source authority while the Supplemental SourceManifest appeared
only as an untyped lineage pair. The data were exploratory runtime composition,
not a historical archive.

H6 preserves Daily as `ArtifactEnvelope.source_manifest_id/hash` for H5 and
historical Reader compatibility, while a separate Composite Manifest names
both authorities, their roles, every component identity and every field-group
authority. The new Runner requires that manifest and cannot invoke the legacy
V1 adapter.

## 3. Domain and policy

`CompositeOperationalCompositionPolicy` has an independent canonical schema,
content hash and derived ID. It contains explicit required roles and field
authorities plus `EXACT_MATCH`, `FAIL_CLOSED`,
`EXACT_PREDICTION_POPULATION`, allowed eligibility and builder revision. H6
supports only `EXPLORATORY`; no production default is hidden in the Builder.

`CompositeOperationalInputManifest` is immutable and content-addressed.
`ASSEMBLING` is process-only. Published results are `VERIFIED`,
`DATA_INSUFFICIENT` or `CONFLICTED`, and only `VERIFIED` may enter research.
Conflicts outrank missingness. Every result retains:

```text
FORMAL_PIT_NOT_ESTABLISHED
FORMAL_OOS_ALPHA_NOT_ESTABLISHED
TRADING_AUTHORITY_NOT_GRANTED
```

Typed components separate Daily package/manifest, Universe, Eligibility,
Decision Price and PredictionRuns from Supplemental market, theme, capital,
symbol proxy, theme membership, ETF mapping/observation and optional stock-bar
evidence. Typed field references point to those components without duplicating
their values or replacing the original Artifacts.

H6 timestamps use whole-second UTC RFC3339 `Z` canonical form. Container
component availability is derived from the maximum explicit retrieval or
availability time in the verified underlying authority set; it is neither
copied from DecisionTime nor presented as package-publication time.

## 4. Builder validation

The Builder accepts verified package wrappers, reloads both exact-file
packages and validates:

- published Daily status and required snapshots;
- exact DecisionTime and availability no later than DecisionTime;
- exploratory eligibility and both SourceManifest identities;
- source Artifact membership and same-ID/same-hash consistency;
- equal PredictionRun populations;
- exact population coverage by memberships and symbol observations;
- Theme/Capital set agreement and valid membership themes;
- exact Theme proxy ETF, mapping and observation coverage;
- every policy-required component and field authority.

It records missing or conflicting facts instead of synthesizing replacements.
The operational V2 adapter reloads original packages and replays the Builder,
so an internally self-consistent but rewritten Composite package cannot enter
Platform V2.

## 5. Package and recovery

Each immutable H6 package contains exactly:

```text
artifact.json
manifest.json
SHA256SUMS.json
```

The Reader verifies exact files, checksums, canonical identities, policy,
components, both SourceManifest references and authority ceilings. Identical
publication is idempotent; an invalid or conflicting destination fails closed.

The service uses an explicit file-first boundary. It validates staging, uses
an atomic rename, then opens the SQLite transaction. A failure before rename
removes H6 staging. A failure after rename but before DB commit leaves a valid
package that the same command can verify and index on replay. A DB index whose
package is missing or mismatched fails closed. No cross-filesystem/SQLite
atomicity is claimed.

## 6. Migration 009 and repository

Migration 009 adds:

```text
composite_operational_manifests
composite_operational_components
composite_operational_field_authorities
composite_operational_commands
```

The migration is repeat-safe and has an isolated down path. All four tables
have validated UPDATE/DELETE append-only triggers; component/field/command
rows reference the manifest. `SQLiteCompositeOperationalRepository` uses
`BEGIN IMMEDIATE`, atomic projection/command insertion and complete rollback.

Command identity binds Daily, Supplemental and Composite package checksums,
both SourceManifests, policy, builder revision, creation time and result ID/hash.
Same key/same hash replays; same key/different hash rejects. Reads reconstruct
canonical JSON, compare every SQL projection, reload all packages and replay
the Builder. Weak schema, spoofed triggers, mutated projections, invalid JSON
and missing package files fail closed. SQLite remains a publication, command
and replay index, not raw evidence authority.

## 7. ResearchInputBundle V2 and compatibility

`ResearchEvidenceKind` adds only
`OPERATIONAL_EXPLORATORY_ARCHIVE`. `ResearchInputBundleV2` has an independent
schema and hash identity, embeds the Composite Manifest and policy, exposes
the unchanged Daily primary SourceManifest and binds Composite, Daily,
Supplemental and both SourceManifest identities in lineage.

`ResearchInputView` lets Market/Theme/Capital/Candidate models consume V1 and
V2 without duplicated model implementations. All four H6-produced component
Artifacts include the Composite ID/hash in input lineage; the Research Layer
Artifact binds both V2 bundle and Composite. Reader schema dispatch restores
V1 and V2 independently. The old adapter remains only for V1 canonical
compatibility; no operational Runner or CLI entry publishes through it.
V1 construction explicitly rejects `OPERATIONAL_EXPLORATORY_ARCHIVE`, so that
evidence kind cannot bypass the V2 Composite requirement.

## 8. H5 integration

The cross-stage test proves:

```text
Daily + Supplemental
→ VERIFIED H6 package
→ ResearchInputBundleV2
→ ResearchLayerArtifact
→ Signal + PathForecast
→ ThesisHealthObservationV2
```

H5 sees one consistent Daily primary SourceManifest and current research
lineage containing H6. Its private replay bundle remains explicitly
`H5_PRIVATE_REPLAY_BUNDLE` and `NOT_H6_AUTHORITY`. H5 Observation authority
remains exploratory, non-formal-OOS and non-trading.

## 9. Verification evidence

Baseline `main@e2cb9add258056815d15462bc83dfc64f43ddb8e` on Python 3.12:

```text
FULL_PYTEST = 1398 passed, 0 skipped, 0 failed
RUFF = PASS
MYPY = PASS, 258 source files
PACKAGE_BUILD = PASS
DOCUMENT_LINKS = PASS
GIT_DIFF_CHECK = PASS
```

Hardened implementation checkpoint `654e025b97c5d9553d7614b4b5be0898272aacbc`:

```text
H6_FOCUSED = 67 passed, 0 skipped, 0 failed
H4_FOCUSED_REGRESSION = 42 passed, 0 skipped, 0 failed
H5_FOCUSED_REGRESSION = 101 passed, 0 skipped, 0 failed
RESEARCH_CONTEXT = 396 passed, 0 skipped, 0 failed
PLATFORM_CONTEXT = 23 passed, 0 skipped, 0 failed
POSITION_CONTEXT = 91 passed, 0 skipped, 0 failed
APPLICATION_CONTEXT = 114 passed, 0 skipped, 0 failed
FULL_PYTEST = 1459 passed, 0 skipped, 0 failed, 8 subtests passed
RUFF = PASS
MYPY = PASS, 263 source files
PACKAGE_BUILD = PASS, migration 009 present in sdist/wheel
DOCUMENT_LINKS = PASS
GIT_DIFF_CHECK = PASS
```

The full run emitted six existing pandas DataFrame-fragmentation performance
warnings in `tests/test_top1000_return_leakage_attribution.py`; no test failed.
Remote Draft PR CI is not claimed in this local implementation checkpoint.

The final two-axis review checked repository standards and the H6 design/spec.
Its actionable findings were resolved at `654e025`: canonical time and
availability semantics, V1/V2 evidence-kind separation, missing-versus-
conflicting collection classification, narrowly scoped orphan cleanup, exact
CLI authority constants and additional relationship tests. The remaining
large-Builder maintainability concern is recorded as a separate P2 refactor,
not mixed into H6 behavior.

## 10. Remaining gaps and rollback

H6 does not provide a qualified real Supplemental producer, authenticated
producer signatures, a lockfile, H4.5 execution bridge, H7 scheduling/state,
H8 sustained Shadow operations or H9 formal validation.

Additional H7 prerequisites remain:

- `build_thesis_health.py` accepts canonical Thesis/Opportunity files rather
  than loading the current aggregate from Decision authority;
- H5 assessment freshness is one-shot and has no durable scheduling/retry or
  Position maximum-age policy;
- `position/thesis_health.py` is a large module needing a behavior-preserving
  refactor in a separate work package.

Rollback stops new H6 and V2 publication and re-enables no weaker operational
path. Existing H6 packages and migration 009 rows remain readable and
append-only; original Daily/Supplemental packages and all V1 historical Readers
remain unchanged. The isolated down migration is for controlled rollback only.

## 11. Maturity conclusion

```text
H6_COMPOSITE_OPERATIONAL_EVIDENCE = IMPLEMENTED_AND_VERIFIED
SHADOW_READY = NO
TRADING_AUTHORITY = NO
REAL_BROKER_AUTHORITY = NOT_IMPLEMENTED
PRODUCTION_READINESS = NOT_ESTABLISHED
```
