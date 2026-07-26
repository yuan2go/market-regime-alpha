# WP-D10 — Codex Research Feedback

> **Status:** ROADMAP  
> **Authority:** Executable implementation work package WP-D10  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, ../Phase-D-Work-Packages.md, ../../status/Gap-Register.md  
> **Code Evidence:** Acceptance evidence must be added when implemented

## Objective

Provide a sandboxed, evidence-pack-driven diagnosis and experiment-proposal workflow with human approval.

## Bounded contexts

- Review and Attribution
- Research Artifact
- Application and QuantDesk

## Dependencies

- WP-D8
- WP-D0 governance

## Inputs

- ResearchEvidencePack
- prior hypotheses/experiments
- rolling scorecards
- data quality/failure records

## Outputs

- CodexDiagnosis
- ImprovementProposal
- ExperimentProposal
- ProposalReview

## Expected files/modules

- src/market_regime_alpha/research_feedback/**
- src/market_regime_alpha/application/**
- tests/research_feedback/**

Exact files may change after code inspection, but ownership may not move outside the declared bounded contexts without an architecture decision.

## New or changed contracts

- ResearchEvidencePack
- CodexDiagnosis
- ExperimentProposal
- ProposalReview

## Code work

- evidence pack builder
- prompt/schema validation
- sandboxed proposal generation
- approval queue

## Tests

- facts cite evidence
- no sealed-test access outside budget
- no model mutation
- proposal requires falsifiable hypothesis/counter-evidence
- human approval gate

## Acceptance conditions

- Codex outputs typed FACT/INFERENCE/HYPOTHESIS/COUNTER_EVIDENCE/EXPERIMENT
- no automatic promotion/execution
- all proposals trace to evidence

## Evidence required

- schema fixtures
- red-team tests
- approved/rejected proposal examples

## Risks

- plausible post-hoc narratives
- prompt injection from artifacts
- research-space explosion

## Stop conditions

- evidence pack incomplete
- model would access sealed test
- proposal cannot isolate one primary change

When a stop condition occurs, publish a blocked/negative result. Do not expand scope or tune unrelated variables to manufacture success.

## Migration effect

Adds a governed assistant around existing research artifacts; it never becomes model/account authority.

## Documentation updates

- docs/research/Failure-Attribution.md
- docs/architecture/08-Deployment-Operations-Boundary.md
- docs/status/Gap-Register.md

## Explicit non-goals

- daily auto-tuning
- auto-commit to active model
- trade decisions
