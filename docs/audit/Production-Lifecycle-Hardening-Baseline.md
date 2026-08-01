# Production Lifecycle Hardening Baseline

> **Status:** CURRENT_STATUS
> **Authority:** Code-level baseline audit for WP-PDL-HARDENING
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-01
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md, ../roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md, Production-Decision-Lifecycle-Delivery.md, ../status/Current-State.md
> **Code Evidence:** Branch `feat/production-lifecycle-hardening-shadow-readiness`, baseline HEAD `a7ce0b444e77506a85e1c1c7b240c22c8421580d`

## 1. Workspace baseline

The audit started without fetch, pull, reset, clean, stash or history rewrite.
`origin/main` and the checked-out Phase 0–7 delivery HEAD both resolved to the
same baseline commit. A dedicated branch was created from that exact commit.

| Fact | Observed value |
|---|---|
| Source baseline | `origin/main@a7ce0b444e77506a85e1c1c7b240c22c8421580d` |
| Audit branch | `feat/production-lifecycle-hardening-shadow-readiness` |
| User change | `.idea/modules.xml`, one insertion |
| Untracked files | none before H0 documentation |
| Preservation | `.idea/modules.xml` was neither edited nor staged |

The local `main` reference was older than `origin/main`; it was not switched,
updated or merged. Implementation facts in this audit come from the checked-out
code at the exact baseline HEAD.

## 2. Required code and operation paths inspected

The audit read the required repository instructions, current status,
Architecture 09/10, WP-PDL, delivery audit and runbook, then inspected:

- `application/operational_research/contracts.py`, `bridge.py` and the
  supplemental Artifact reader/publisher;
- `application/trading_lifecycle/service.py`, `portfolio_risk.py`,
  `manual_execution.py` and `review.py`;
- Decision aggregate/repository code and migration 002;
- Portfolio lifecycle/services/serialization/repository code and migration 003;
- Manual Execution contracts/repository code and migration 004;
- Position authority and assessment models;
- Evaluation lifecycle and immutable review package;
- the corresponding CLI scripts and focused tests;
- Platform V2 evidence-kind contracts and the explicit trading-calendar
  authority.

The baseline is not inferred solely from README, Current State, or the prior
delivery audit.

## 3. Requested issue verification

| # | Initial concern | Result | Executable evidence |
|---|---|---|---|
| 1 | Portfolio only requires allocation-local positions | CONFIRMED, and stricter than “only requires”: it rejects extra existing holdings | `PortfolioConstructionService.construct` requires `set(current_positions) == allocation_symbols` |
| 2 | Risk evaluates only target positions | CONFIRMED | `_constraints` derives gross, symbol, theme and maximum loss exclusively from `portfolio.target_positions` |
| 3 | Fill cannot uniquely trace TradingThesis | CONFIRMED | `Fill` stores `manual_trade_id`; `ManualTradeRecord` has Risk/Portfolio/Target hashes but no Thesis or Opportunity identity |
| 4 | Position cannot distinguish Thesis/strategy books | CONFIRMED | `SQLiteManualExecutionRepository.all_fills` selects by account/symbol and `PositionProjector.project` has no Thesis/book input |
| 5 | Position lacks A-share sellability state | CONFIRMED | PositionSnapshot has total quantity, cost, PnL and lots; PositionLot has no available/frozen/trade-date/sellable-session fields |
| 6 | Risk available quantity is not Position Authority | CONFIRMED | caller creates `CurrentPositionInput.available_quantity`; neither Portfolio construction nor Risk requires a PositionSnapshot |
| 7 | REDUCE/EXIT can be blocked by normal Risk | CONFIRMED | ExitAssessment marks REDUCE/EXIT as requiring a new Portfolio/Risk decision; risk timeout always produces fail-closed TIMEOUT |
| 8 | Thesis health support is caller-authored | CONFIRMED | `ThesisHealthObservation` exposes public `signal_support`, `theme_support` and `capital_support` constructor/JSON fields |
| 9 | Bridge mislabels operational evidence as historical | CONFIRMED | `adapt_operational_research_inputs` sets `ResearchEvidenceKind.HISTORICAL_IMMUTABLE_ARCHIVE` |
| 10 | Supplemental manifest is not a downstream composite authority index | CONFIRMED | lineage arrays include supplemental IDs/hashes, but `ResearchInputBundle.source_manifest` is the Daily SourceManifest and has no typed per-field composite mapping |
| 11 | Holding/Exit lacks durable repository | CONFIRMED | models produce immutable assessment values only inside `LifecycleReviewRun`; no assessment Repository Protocol, SQLite table or state projection exists |
| 12 | Continuous Shadow operations are absent | CONFIRMED | no ShadowRun/scheduler receipt, lifecycle queue, exception queue, reconciliation queue, metric, alert or acknowledgement implementation was found |

## 4. Important refinements

### 4.1 Existing execution validation is real but incomplete

The execution repository is not an unvalidated ledger. At ManualTrade creation
it recomputes the independent RiskDecision, verifies the PortfolioDecision and
checks exact TargetPosition membership/hash. Fill scope is checked against the
ManualTradeRecord, Fill is append-only under SQLite triggers, and correction
records replace an execution deterministically during projection.

The gap begins before and after that validated segment: TargetPosition has a
Thesis ID, but ManualTradeRecord does not retain it, and Position/Outcome do not
validate the complete upstream chain.

### 4.2 Thesis “active” is not currently account scoped

TradingThesis V1 uses APPROVED, INVALIDATED and CLOSED states. The Decision
repository guarantees one Thesis per Opportunity, not one open Thesis per
account/symbol. TradingThesis has no account ID. H2 therefore introduces a
position-book/open-scope invariant without changing V1 state meanings.

### 4.3 Position is deterministic but not durable state

PositionSnapshot is a content-identified pure projection from all Fill records
in an account/symbol scope. It is rebuildable and detects overselling, but it
has no persisted projection table, external reconciliation event history,
T+1 calendar input or book-level attribution.

### 4.4 Outcome validates Fill balance, not full trade authority

TradeOutcome requires a closed Position, exact Fill ledger equality, balanced
long-only buys/sells and path evidence bound to entry Fill. It also receives a
TradingThesis. It does not receive ManualTradeRecord, PortfolioDecision or
RiskDecision values, so symbol equality and Fill scope cannot prove the full
Thesis-to-Risk chain.

### 4.5 A usable calendar authority already exists

`data/trading_calendar.py` resolves future sessions from explicit identified
exchange sessions and explicitly forbids weekday inference. H3 can reuse this
authority; a second calendar must not be introduced.

## 5. Documentation differences found

The runtime delivered by Phase 0–7 is present on the audited main baseline, but
several documents retained earlier target-state wording:

- AGENTS described the bridge and later contexts as documented but not
  canonical;
- Architecture 09 said the bounded packages defined only future ownership and
  Layer 1 was the only executable Platform V2 flow, while a later section in
  the same document acknowledged Phase 0–7 implementation;
- the WP-PDL phase descriptions and runbook mixed “planned” statements with
  implemented CLI/repository behavior;
- the Gap Register called the production-lifecycle baseline documentation-only
  despite separate implementation rows.

The H0 correction treats code/tests as implementation-fact authority. It does
not promote the delivered mechanics to qualified production or Shadow-ready
status.

## 6. Unchanged baseline quality gate

The following commands ran before H0 runtime changes:

| Command | Result |
|---|---|
| `git diff --check` | PASS |
| `python scripts/check_docs_links.py` | PASS |
| `python -m pytest -q tests/scripts/test_check_docs_links.py` | PASS — 8 tests |
| `python -m pytest -q tests/platform` | PASS — 23 tests |
| `python -m pytest -q` | PASS — complete suite; six pre-existing pandas fragmentation warnings |
| `python -m ruff check .` | PASS |
| `python -m mypy` | PASS — 248 source files |

The warnings came from the existing top-1000 backtest feature construction and
did not indicate a failure in the production lifecycle.

## 7. H0 conclusion

All twelve hardening concerns are real at the exact audited baseline. None
requires a second project, authority or service split. The accepted response is
the dependency-ordered H1–H9 work in WP-PDL-HARDENING and Architecture 11.

H0 changes documentation only. It establishes neither Shadow readiness nor a
formal Provider, PIT, OOS, calibration, production-parameter, broker or trading
authority.
