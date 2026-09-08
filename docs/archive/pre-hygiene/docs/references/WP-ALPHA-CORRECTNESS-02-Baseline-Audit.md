# WP-ALPHA-CORRECTNESS-02 Baseline Audit

> **Status:** HISTORICAL
> **Authority:** Read-only pre-implementation audit checkpoint
> **Audit Date:** 2026-08-26
> **Starting Main:** `1a92ee41b02dd94df9ef4488c59cba55df4674ce`
> **Feature Branch:** `agent/wp-alpha-correctness-02`
> **Evidence Ceiling:** `DESIGN_INPUT / DISCOVERY_ONLY / NO_NEW_RESEARCH_CLAIM`

This audit records the repository, database and immutable owner state inspected
before WP-ALPHA-CORRECTNESS-02 business-code changes. It does not revise the
predecessor Experiment, produce Target Evidence or qualify research.

## Repository and workspace

- `origin/main` and the isolated worktree both resolved to
  `1a92ee41b02dd94df9ef4488c59cba55df4674ce`, merge commit for PR #78.
- Work is isolated on `agent/wp-alpha-correctness-02`; `main` is not checked out
  or modified in this worktree.
- The original checkout was on
  `agent/wp-portfolio-execution-authority-01@10689a4db772be5a546a64448fcc6f39f6988412`
  with one pre-existing modification, `.idea/modules.xml`. It was neither
  modified nor staged.
- The immutable source/evidence checkout
  `wp-alpha-proof-02@b86f7855784a9b5dcd81131091447ffc15409b5e`
  was clean. Its `.local/wp-alpha-proof-02-artifacts` root was available with
  3,281 files.
- Dependency inputs were frozen by
  `pyproject.toml@sha256:de0d5442d9a50b5126acf85c762ebccb0212afcb9ba43abebfe8b7900ebe5fda`
  and
  `uv.lock@sha256:bdb074383769cae39d2938fbfdb004a11322db85b13a7b3238e035203c40ec12`.
  Dependency sync for the feature worktree had not run at audit time.

Recent relevant `main` history inspected:

| Revision | Meaning |
|---|---|
| `1a92ee4` | merge PR #78, WP-ALPHA-PROOF-02 delivery record |
| `8e71535` | merge PR #77, WP-ALPHA-PROOF-02 branch |
| `fc51ffc` | merge PR #76, Alpha Proof implementation/evidence series |
| `2554ead` | terminal WP-ALPHA-PROOF-02 report and status |
| `22e3b34` | regression seams aligned with canonical runtime |
| `a4564e2` | main-to-Alpha-Proof schema-upgrade coverage |
| `6913c40` | packaged migration-head authority coverage |

## Runtime and dependency baseline

| Item | Observed state |
|---|---|
| Shell Python | 3.12.13 (`pyenv` shim) |
| Existing validation virtualenv Python | 3.12.2 |
| uv | 0.11.7 |
| PostgreSQL client/server family | 16.14 |
| Packaged migration head | 104, `historical_outcome_forecast_fk_index` |
| Original campaign database/schema | `market_regime_alpha.wp_alpha_proof_02_20260825` |
| Original campaign schema head | 104 |

The audit used read-only PostgreSQL and owner-reload paths. It applied no
migration and wrote no campaign, Evidence, artifact or access event.

## Governance and evidence read set

The audit read `AGENTS.md`, `docs/README.md`, all four current architecture
documents, Current State, Gap Register, Roadmap, Capability Matrix, the frozen
WP-ALPHA-PROOF-02 protocol and execution report, Golden Loop V2 contract/report,
the negative-results registry and relevant migration/test contracts. Historical
reports were treated as immutable evidence, while executable code and database
owners controlled implementation facts.

The predecessor Evidence boundary is:

- Discovery run `historical-research-run-0382e3c92084432a7d7b9c36`;
- Experiment
  `research-experiment-definition:d242097bff7299a4ed61745aa4f6272807d83a549178ac2c0af268b261db6315`;
- correctness proof
  `alpha-correctness-proof:9196bf13d40dde78f50ab3314ac511d05f952f91b4075bf5f201c755eeb1067b`;
- `37,367` Target rows supported, `425` partial and `8` failed;
- Discovery mean RankIC `-0.0911379`, ICIR `-0.496474`, positive-IC ratio
  `0.348485`, Top-5 gross `-0.00089056` and net `-0.00299088`;
- terminal state `REJECTED / CORRECTNESS_FAILED / NO-GO`;
- Formal PIT `PIT_INCOMPLETE`, External not admitted and Locked OOS Outcome
  consumption rows zero with `outcome_values_read=false`.

The immutable execution report contains the abbreviated Raw-owner locator
`historical-data-owner-c744a67a4ec2113a2bdb4e13`. Direct PostgreSQL owner
reload and canonical-hash verification resolve the actual owner as
`historical-data-owner-c744a6181b03ab8215ddb4ba@sha256:c744a6181b03ab8215ddb4ba8112ca117bc109057b52cc25e05e00a195d48092`.
The historical report is not rewritten; this audit records the discrepancy and
uses executable owner authority for the correction protocol.

Full predecessor identities are frozen in the
[WP-ALPHA-CORRECTNESS-02 protocol](../research/protocols/WP-ALPHA-CORRECTNESS-02-Frozen-Protocol.md).

## Executable call-chain audit

The real canonical path is one existing runtime/operator plane:

```text
continuous-research CLI operation historical-phase-ii
-> HistoricalPhaseIIOperator
-> HistoricalPhaseIIResearchService
-> HistoricalDecisionMaterializer
-> PostgreSQL Historical materialization repositories
-> HistoricalAlphaCorrectnessChecker
-> PostgreSQL Historical Evidence repository / immutable artifact encoding
-> CLI report projection / Historical runner replay / downstream gates
```

Files inspected at each seam:

- CLI/entry:
  [`continuous_research.py`](../../src/market_regime_alpha/cli/continuous_research.py);
- operator/service:
  [`phase_ii_operator.py`](../../src/market_regime_alpha/application/historical_corpus/phase_ii_operator.py)
  and
  [`phase_ii_service.py`](../../src/market_regime_alpha/application/historical_corpus/phase_ii_service.py);
- materializer/checker:
  [`decision_materializer.py`](../../src/market_regime_alpha/application/historical_corpus/decision_materializer.py)
  and
  [`alpha_correctness.py`](../../src/market_regime_alpha/application/historical_corpus/alpha_correctness.py);
- Target domain:
  [`targeted_outcome.py`](../../src/market_regime_alpha/application/research_evaluation/targeted_outcome.py);
- PostgreSQL owners:
  [`postgres_repository.py`](../../src/market_regime_alpha/application/historical_corpus/postgres_repository.py),
  [`postgres_materialization.py`](../../src/market_regime_alpha/application/historical_corpus/postgres_materialization.py),
  [`postgres_evidence.py`](../../src/market_regime_alpha/application/historical_corpus/postgres_evidence.py)
  and
  [`postgres_session_owner.py`](../../src/market_regime_alpha/application/historical_research/postgres_session_owner.py);
- replay and Locked gate:
  [`runner.py`](../../src/market_regime_alpha/application/historical_research/runner.py)
  and
  [`postgres_locked_oos_scope.py`](../../src/market_regime_alpha/application/historical_corpus/postgres_locked_oos_scope.py).

No second Runtime, runner, file authority or non-PostgreSQL write path is
required or permitted by the approved design.

## Located semantic mismatch

Current executable behavior explains all eight failures:

1. the materializer selects the latest eligible same-session five-minute price
   and otherwise falls back to a Daily close at or before Decision time;
2. the checker independently requires a priced exact 14:55 five-minute bar;
3. `TargetOutcomeLabel` v2 assumes a numeric Decision reference and does not
   represent Decision, path and derived-metric state independently;
4. current correctness Evidence projects bounded aggregate summaries rather
   than a durable, owner-reloadable eight-row failure index.

Owner reload found three rows with no Decision-session five-minute bar and five
with an exact 14:55 placeholder whose OHLC is null. Every fallback Daily row is
from the preceding trading session and has `SUSPENDED` status. Every T+1
09:30-10:30 source path contains the exact twelve valid five-minute bars.

The approved repair therefore preserves the observed path while setting the
Decision reference and its dependent metrics unavailable. The exact matrix,
identity rules and compatibility boundary are frozen in
[ADR-014](../architecture/decisions/ADR-014-Frozen-Target-Semantics-and-Independent-Correctness.md).

## Pre-implementation capability state

| Level | WP-ALPHA-CORRECTNESS-02 state |
|---|---|
| `CODE_IMPLEMENTED` | false |
| `CANONICAL_WIRED` | false |
| `TEST_EXECUTED` | documentation checks only; business tests not run |
| `RUNTIME_PROVEN` | false |
| `RESEARCH_QUALIFIED` | false |
| `PRODUCTION_QUALIFIED` | false |

Design-checkpoint validation:

| Command | Result |
|---|---|
| `python scripts/check_docs_links.py` | `PASS` |
| `python -m pytest -q tests/scripts/test_check_docs_links.py` | `PASS` (`7 passed`) |
| `git diff --check` | `PASS` |
| Business tests, PostgreSQL integration, full pytest, Ruff, mypy and build | `NOT_RUN` at this docs-only checkpoint; required after implementation |

This audit authorizes no External or Locked OOS read and does not change the
predecessor terminal conclusion.
