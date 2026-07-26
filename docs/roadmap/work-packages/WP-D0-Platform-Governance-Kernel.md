# WP-D0 — Platform Governance Kernel Hardening

> **Status:** ROADMAP  
> **Authority:** Executable implementation work package WP-D0  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, ../Phase-D-Work-Packages.md, ../../status/Gap-Register.md, ../../audit/Post-Merge-Reconciliation-2026-07-26.md  
> **Code Evidence:** `src/market_regime_alpha/platform/**`; `tests/platform/test_research_platform_kernel.py`

## Objective

Harden the merged Research Platform Kernel so Model, Target, Evaluation and Experiment governance cannot be bypassed and can support later persistent daily orchestration without changing B0/B1 scoring semantics.

## Current starting point

The following are already merged on `main`:

- Theory/Observable/Model contracts;
- Target and Evaluation Protocols;
- Frozen Experiment Protocol and access budgets;
- in-memory Model Registry;
- first Multi-model Candidate Slice;
- focused platform tests.

WP-D0 is no longer a merge/rebase package. It is a post-merge hardening and compatibility package.

## Bounded contexts

- Research Artifact
- Feature and Factor
- Candidate Discovery
- Platform Governance

## Dependencies

- current merged Platform Kernel;
- existing FeatureDefinition/CandidateResearchDataset/ExperimentIdentity authorities;
- existing B0/B1 ranking implementations;
- current CI and documentation consistency checks.

## Inputs

- `src/market_regime_alpha/platform/**`;
- `src/market_regime_alpha/data/contracts.py::DataEligibility`;
- current Candidate Dataset and ranking contracts;
- current Target/Evaluation/Experiment definitions;
- current platform and Candidate tests.

## Outputs

- one canonical platform registry namespace;
- new registrations restricted to `DRAFT + UNQUALIFIED`;
- explicit, validated restoration path for historical snapshots;
- separate DataEligibility compatibility and model EvidenceLevel maturity;
- repository protocols for Registry and Experiment Governance persistence;
- protocol-bound, content-addressed Candidate PredictionRun;
- B0/B1 adapter equivalence evidence;
- platform package included in mypy scope;
- migration decision for the current `platform-b2-volume-momentum-v1` naming conflict.

## Expected files/modules

- `src/market_regime_alpha/platform/**`;
- `src/market_regime_alpha/data/contracts.py` only when a compatibility type is required;
- `tests/platform/**`;
- `pyproject.toml`;
- `docs/status/**`;
- `docs/research/**`;
- `docs/audit/**`.

Exact files may change after code inspection, but ownership may not move outside the declared bounded contexts without an architecture decision.

## New or changed contracts

- `ModelDefinition.supported_data_eligibilities`;
- `ModelRegistration` lifecycle evidence semantics;
- `ModelRegistryRepository`;
- `ExperimentGovernanceRepository`;
- `PredictionRun` and its identity/content hash;
- compatibility mapping for historical model IDs and artifacts.

## Code work

- close direct registration paths that can create advanced lifecycle states;
- add an explicit restore/import path that validates transition history, approvals and evidence references;
- separate `DataEligibility` from `EvidenceLevel` in definitions and run compatibility checks;
- rename in-memory implementations where needed and define persistence protocols without prematurely choosing a database;
- bind Multi-model Candidate execution to registered Model, Target, Evaluation and Frozen Experiment Protocol identities;
- emit immutable PredictionRun artifacts with full predictions and rejections;
- add adapters that preserve existing B0/B1 output semantics;
- resolve the transparent-composite model currently named B2 without reusing a historical identity silently;
- add all Platform Kernel modules to mypy coverage.

## Tests

- direct `ACTIVE`, `SHADOW` or `PROMOTION_CANDIDATE` registration is rejected;
- illegal lifecycle transitions and missing approval/evidence are rejected;
- restored snapshots require valid ordered transition history;
- DataEligibility compatibility is independent from model EvidenceLevel;
- validation/sealed-test budgets survive serialization and idempotent replay;
- protocol identity mismatch blocks a model run;
- PredictionRun identity and content hash are deterministic;
- old B0/B1 complete ranking, scores, ranks, rejections and coverage equal adapter outputs;
- historical model-ID migration is explicit;
- full docs checker, pytest, Ruff and mypy pass.

## Acceptance conditions

- one Model/Target/Evaluation/Experiment authority remains;
- no public API can bypass lifecycle promotion gates;
- data qualification and model evidence maturity are distinct types and checks;
- Platform code is included in mypy;
- B0/B1 behavior is unchanged through the Platform adapter;
- Multi-model runs reference frozen protocols and produce immutable PredictionRun artifacts;
- no duplicate registry or competing Candidate/Feature/Target ontology is introduced;
- Current State and Capability Matrix cite the delivered evidence.

## Evidence required

- successful CI run;
- contract compatibility matrix;
- lifecycle bypass regression tests;
- serialization/recovery evidence;
- before/after B0/B1 comparison artifact;
- PredictionRun hash/replay evidence;
- migration note for model IDs and old Platform Kernel documents.

## Risks

- parallel registries;
- premature database coupling;
- historical identity breakage;
- semantic drift in B0/B1;
- confusing input data eligibility with model evidence maturity;
- turning a mechanical slice into an unsupported model-winner claim.

## Stop conditions

- historical Artifact identity cannot be preserved or explicitly migrated;
- Constitution conflicts with the proposed governance semantics;
- B0/B1 equivalence test fails;
- fixing tests would require changing model weights, Target, Universe or ranking semantics;
- Provider/PIT semantics would need to be guessed;
- scope expands into DailyResearchSnapshot, Entry, Exit or broker execution.

When a stop condition occurs, publish a blocked/negative result. Do not expand scope or tune unrelated variables to manufacture success.

## Migration effect

Hardens the already-merged Platform Kernel into the canonical governance boundary used by WP-D1 onward. Legacy and existing research contracts remain behind explicit adapters until migrated. Historical Artifact IDs remain immutable.

## Documentation updates

- `docs/status/Current-State.md`;
- `docs/status/Capability-Matrix.md`;
- `docs/status/Gap-Register.md`;
- `docs/architecture/03-Research-Artifact-Architecture.md`;
- `docs/research/Candidate-Research.md`;
- `docs/audit/Post-Merge-Reconciliation-2026-07-26.md` or a later WP-D0 delivery audit.

## Explicit non-goals

- daily data ingestion;
- new Alpha model;
- model winner selection;
- changing B0/B1 weights or scoring;
- Entry/Holding/Exit implementation;
- automatic promotion;
- broker or real-order path.
