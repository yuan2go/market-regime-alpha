# WP-D0 — Platform Governance Kernel

> **Status:** ROADMAP  
> **Authority:** Executable implementation work package WP-D0  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, ../Phase-D-Work-Packages.md, ../../status/Gap-Register.md  
> **Code Evidence:** Acceptance evidence must be added when implemented

## Objective

Reconcile and merge a single platform kernel for Model, Target, Evaluation and Experiment governance without changing B0/B1 semantics.

## Bounded contexts

- Research Artifact
- Feature and Factor
- Candidate Discovery

## Dependencies

- Draft PR #12 or equivalent reviewed implementation
- current main research artifact contracts

## Inputs

- existing FeatureDefinition/CandidateResearchDataset/ExperimentIdentity contracts
- PR #12 Model Registry/Target/Evaluation/Experiment contracts
- current CI baseline

## Outputs

- one canonical registry namespace
- model lifecycle and evidence-level gates
- migration decision for PR #12
- compatibility tests

## Expected files/modules

- src/market_regime_alpha/platform/**
- src/market_regime_alpha/research/**
- tests/platform/**
- docs/status/**
- docs/specs/**

Exact files may change after code inspection, but ownership may not move outside the declared bounded contexts without an architecture decision.

## New or changed contracts

- ModelDefinition
- TargetDefinition
- EvaluationProtocol
- FrozenExperimentProtocol
- ModelLifecycleRecord

## Code work

- review PR #12 against main
- remove duplicate identities
- add adapters to existing contracts
- add persistence boundary only where required

## Tests

- identity stability
- illegal lifecycle transition rejection
- validation/sealed-test budget enforcement
- B0/B1 output equivalence through adapter
- full pytest/ruff/mypy

## Acceptance conditions

- one model/target/evaluation/experiment authority
- B0/B1 ranking unchanged
- ACTIVE requires human approval and evidence
- no duplicate registry class remains

## Evidence required

- CI run
- contract compatibility matrix
- migration note
- before/after B0/B1 artifact hashes

## Risks

- parallel registries
- premature abstraction
- semantic drift in B0/B1

## Stop conditions

- identity conflict cannot be resolved without changing historical artifacts
- PR #12 semantics contradict Constitution
- B0/B1 equivalence test fails

When a stop condition occurs, publish a blocked/negative result. Do not expand scope or tune unrelated variables to manufacture success.

## Migration effect

Establishes the canonical kernel used by later work; Legacy and current research contracts remain behind adapters until migrated.

## Documentation updates

- docs/status/Current-State.md
- docs/status/Capability-Matrix.md
- docs/architecture/03-Research-Artifact-Architecture.md
- docs/specs/README.md

## Explicit non-goals

- daily data ingestion
- new Alpha model
- model winner
- automatic promotion
