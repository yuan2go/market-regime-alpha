# Post-Consolidation Code Audit — 2026-07-26

> **Status:** CURRENT_STATUS  
> **Authority:** Commit-bound implementation-fact audit after branch consolidation  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../status/Current-State.md, ../status/Capability-Matrix.md, ../status/Gap-Register.md, Branch-Reconciliation-2026-07-26.md  
> **Code Evidence:** main@772ecfb09410588b5a406ad900d793a5850e60d5

## Objective

Reconcile current documentation with executable evidence after the historical
branches and the previously local daily-research branch were consolidated into
`main`.

This audit records implementation facts. It does not promote a model, establish
Alpha, grant provider authority or authorize trading.

## Scope and non-goals

This is a documentation-only reconciliation. It does not:

- modify a production contract, schema, Reader or Artifact;
- implement the Daily V1-to-V2 Adapter or a Canonical Daily contract;
- implement WP-D0 Registry, Governance, Repository or PredictionRun changes;
- change a model, factor, weight, Target, Universe or provider authority.

## Audited baseline

```text
actual_main_head = 772ecfb09410588b5a406ad900d793a5850e60d5
working_tree_status = clean
python_version = 3.12.13
open_pull_requests = 0 (GitHub REST observation at 2026-07-26, Asia/Shanghai)
dependency_check = pip check passed
```

The environment had `pytest`, `ruff` and `mypy`. It did not have `duckdb`,
`pyarrow` or `fastparquet`. Their absence is an environment fact, not by itself
a classification of the affected dependencies as optional or required.

## Method

The audit used the implementation-fact authority order:

1. current code;
2. current tests and static configuration;
3. reproducible Artifact mechanics;
4. current status documents;
5. commit-bound historical audits.

The audit inspected `src/market_regime_alpha/platform/**`,
`src/market_regime_alpha/daily_research/**`, their focused tests,
`pyproject.toml`, current architecture/specifications and Phase D work packages.

## Findings

| Capability | Implementation status | Evidence | Boundary |
|---|---|---|---|
| Identity, time, data, PIT universe/eligibility, Feature and Candidate spine | IMPLEMENTED_AND_VERIFIED | current packages and focused/full repository test history | no Formal OOS Alpha implied |
| Platform contracts and Target/Evaluation Protocols | IMPLEMENTED_AND_VERIFIED | `platform/contracts.py`, `target_evaluation.py`, platform tests | in-process research contracts |
| Multi-model mechanical Candidate Slice | IMPLEMENTED_PROTOTYPE | `platform/multi_model_slice.py`, platform tests | fixture/in-process mechanics; not a canonical PredictionRun |
| Model Registry and Experiment Governance | IMPLEMENTED_PROTOTYPE | `platform/model_registry.py`, `experiment_governance.py` | mutable in-memory dictionaries; no durable recovery boundary |
| Historical daily-research V1 contracts and Artifact/Reader | IMPLEMENTED_NON_CANONICAL | `daily_research/**`, `tests/daily_research/**` | fields differ from current Phase D specifications |
| Canonical Phase D DailyResearchSnapshot, CandidateRecommendation and EntryAssessment contracts | DESIGNED_ONLY | current specifications | namesake V1 cannot be renamed into compliance |
| Canonical Phase D DailyResearchSnapshot, CandidateRecommendation and EntryAssessment runtime/services | NOT_STARTED | no current-contract producer/service | follows contract convergence and dependency-ordered work packages |
| Canonical PredictionRun | NOT_STARTED | no immutable run contract with all WP-D0 identities | current multi-model slice is insufficient |
| Persistent Registry/Governance | NOT_STARTED | no repository protocols or recovery implementation | WP-D0 |
| Legacy Dividend-T and operational paths | LEGACY_ONLY | `dividend_t/**`, Legacy tests and adapters | no canonical platform/account authority |
| Qualified Xuntou PIT execution | BLOCKED_EXTERNAL_INPUT | qualified v4 contracts and blocker mechanics | requires real supported XtQuant input |

## Daily-research V1 evidence

The V1 package implements:

- immutable DailyResearchSnapshot, CandidateRecommendation and EntryAssessment
  dataclasses;
- content-derived identities and canonical JSON;
- cross-record aggregate validation;
- staged immutable Artifact publication;
- checksum and semantic reconstruction through a Reader;
- explicit test-only/exploratory authority ceilings.

Focused observations:

```text
python -m pytest -q tests/daily_research
44 passed

python -m pytest -q tests/platform
4 passed
```

The implementation is not the current Phase D contract. Material differences
include Source Manifest, Eligibility Snapshot, complete PredictionRun,
Experiment Protocol, evidence/data-quality semantics, dispositions,
supersession, expiry and calibration identities. Those differences require an
ADR, characterization evidence and an explicit migration boundary.

## Platform governance gaps

At the audited baseline:

- `ModelRegistry.register` accepts caller-supplied advanced lifecycle and
  evidence values;
- `ModelDefinition.supported_data_grades` uses `EvidenceLevel` where input
  `DataEligibility` is required;
- Registry and Experiment Governance are process-local;
- validation-access commands lack persistent idempotency keys;
- `src/market_regime_alpha/platform/**` is absent from the mypy file list;
- `platform-b2-volume-momentum-v1` is a fixed-weight transparent composite,
  not a regularized statistical B2;
- no B0/B1 adapter equivalence suite covers complete outputs and identities;
- `MultiModelCandidateSliceRun` is not the canonical immutable PredictionRun
  required by WP-D0.

## Evidence ceiling

```text
CODE_CONSOLIDATION_COMPLETE
CANDIDATE_RESEARCH_SPINE_MATURE
RESEARCH_EVIDENCE_GOVERNANCE_STRONG
PLATFORM_KERNEL_PROTOTYPE_IMPLEMENTED
DAILY_ARTIFACT_V1_IMPLEMENTED_NON_CANONICAL
DAILY_CONTRACT_CONVERGENCE_REQUIRED
WP_D0_NOT_COMPLETE
FORMAL_OOS_ALPHA_NOT_ESTABLISHED
TRADING_AUTHORITY_NOT_GRANTED
```

No test fixture, public-source run, V1 daily package or mechanical model slice
raises that ceiling.

## Validation evidence

The first full-suite attempt in the pre-existing shell environment failed
because the environment had not installed declared core dependencies
`duckdb` and `pyarrow`. `fastparquet` was also absent but is not declared and
is not required when `pyarrow` is installed.

The repository's standard CI installation is:

```text
python -m pip install -e ".[dev]"
```

After reproducing that installation without changing dependency declarations:

| Command | Result | Observation |
|---|---|---|
| `git diff --check` | PASS | no whitespace errors |
| `python scripts/check_docs_links.py` | PASS | documentation authority, links, evidence, supersession and inventory OK |
| `python -m pytest -q tests/scripts/test_check_docs_links.py` | PASS | 8 passed |
| `python -m pytest -q tests/platform` | PASS | 4 passed |
| `python -m pytest -q tests/daily_research` | PASS | 44 passed |
| `python -m pytest -q` | PASS | complete suite passed; six existing pandas fragmentation warnings |
| `python -m ruff check .` | PASS | all checks passed |
| `python -m mypy` | PASS | no issues in 138 source files |
| `python -m pip check` | PASS | no broken requirements |

The installation changed the local Python environment only. It did not change
`pyproject.toml`, `requirements.txt` or another tracked dependency file.

## Required sequence

```text
Post-Consolidation Documentation Reconciliation
→ Daily Research Contract Convergence ADR and characterization
→ WP-D0 Platform Governance Kernel Hardening
→ WP-D1
```

Daily contract convergence must preserve V1 schema, JSON, Reader semantics,
module hashes and historical Artifact identities. WP-D0 must not expand into
canonical Daily runtime, Entry, Exit, broker integration or new Alpha work.
