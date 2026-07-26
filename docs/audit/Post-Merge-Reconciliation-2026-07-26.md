# Post-Merge Reconciliation Audit — 2026-07-26

> **Status:** CURRENT_STATUS  
> **Authority:** Commit-bound delta audit for reconciling PR #12 and PR #13 after both entered main  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Repository-Audit-Baseline-2026-07-26.md, ../status/Current-State.md, ../status/Capability-Matrix.md, ../roadmap/work-packages/WP-D0-Platform-Governance-Kernel.md  
> **Code Evidence:** baseline main@42fa35f172f16c7d86e516a9dee6d9b8c8e7a7be; validated reconciliation tree@1a6053b533e1199e8fdb0e7be7852aad2a2ad946

## Purpose

The original repository audit remains an immutable baseline tied to `main@96e41a12d86b3b5f7472c2d4e44011736b087b6b`. This document records only the delta created when:

1. PR #12 merged the Research Platform Kernel V1;
2. PR #13 subsequently merged documentation generated from the older baseline;
3. current-status documents therefore continued to describe PR #12 as pending.

The prior audit is not rewritten or retroactively relabelled.

## Merge sequence

| Item | Merge commit | Result |
|---|---|---|
| PR #12 — Research Platform Kernel V1 | `84e289a9616b70c61cc139c59e9bda8cd66a0975` | Added Platform contracts, Target/Evaluation Protocols, Experiment Governance, Model Registry and Multi-model Candidate Slice. |
| PR #13 — documentation reconstruction | `42fa35f172f16c7d86e516a9dee6d9b8c8e7a7be` | Added canonical documentation authority, Phase D specifications, status and roadmap, but retained pre-merge PR #12 assumptions. |

## Reconciliation findings

### F1 — current status understated merged code

`README.md`, `AGENTS.md`, Current State, Capability Matrix, Gap Register and WP-D0 still described the Platform Kernel as a Draft PR or not present on main.

Resolution: current documents now record the merged contracts and tests while distinguishing contract/prototype implementation from persistent operational authority.

### F2 — PR #12 architecture contract was placed in Constitution

`docs/constitution/10-Research-Platform-Kernel-V1.md` used a non-canonical Status and extended the frozen Constitution namespace beyond `00–09`.

Resolution: the original full text remains in Git history; a normalized historical merge contract is stored under `docs/archive/research-platform/`, and current authority is delegated to code/tests, status documents and WP-D0.

### F3 — PR #12 vertical-slice document lacked canonical metadata

`docs/research/Research-Platform-Vertical-Slice-V1.md` had no machine-readable Status header and was absent from canonical navigation.

Resolution: it is now a `CURRENT_RESEARCH_PROGRAM` document with code evidence, current limitations and explicit WP-D0 handoff.

### F4 — documentation validation was not enforced by normal CI

The documentation validator existed, but the standard CI workflow executed only pytest, Ruff and mypy. Mutation tests also did not assert the actual repository tree was valid.

Resolution: CI now runs `python scripts/check_docs_links.py` before tests, and the test suite includes a repository-level integration assertion.

## Corrected implementation interpretation

The merged repository contains a test-backed Platform Kernel for:

- Theory, Observable and Model contracts;
- Target and Evaluation Protocols;
- Frozen Experiment Protocol and access-budget mechanics;
- in-memory Model Registry lifecycle transitions;
- a first comparable Multi-model Candidate Slice.

It does not yet contain:

- durable Registry or Experiment Governance authority;
- a canonical daily Prediction Ledger;
- DailyResearchSnapshot runtime;
- CandidateRecommendation/EntryAssessment services;
- canonical Position, Holding or Exit authority;
- Outcome, Daily Review, Portfolio, Codex Evidence Pack or QuantDesk runtime;
- formal OOS Alpha or trading authority.

## WP-D0 consequence

WP-D0 is redefined from “merge/reconcile PR #12” to “harden the already-merged Platform Kernel.” Its remaining work includes lifecycle-bypass closure, DataEligibility/EvidenceLevel separation, persistence/recovery protocols, mypy coverage, B0/B1 equivalence and protocol-bound immutable PredictionRun artifacts.

## Validation evidence

GitHub Actions CI run `30203050356` (`CI #137`) completed successfully against reconciliation commit `1a6053b533e1199e8fdb0e7be7852aad2a2ad946`.

The workflow executed, in order:

```text
python scripts/check_docs_links.py     PASS
python -m pytest -q                    PASS
python -m ruff check .                 PASS
python -m mypy                         PASS
```

The documentation checker is now a first-class CI step rather than an out-of-band command. The pytest suite also validates the actual repository documentation tree through `docs_check.validate(docs_check.ROOT)`.

## Evidence boundary

This reconciliation corrects repository truth and CI enforcement only. It does not establish Alpha, a model winner, production readiness, provider qualification, broker execution or trading authority.

## Finalization note

The validation-evidence update changes audit text only; normal CI remains required on the final PR head before review or merge.
