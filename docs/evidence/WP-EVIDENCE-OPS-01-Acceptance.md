# WP-EVIDENCE-OPS-01 Acceptance Evidence

> **Status:** CURRENT_STATUS
> **Authority:** Recorded-source engineering verification; not Live or Formal PIT evidence
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-09
> **Baseline:** `origin/main@ecbe40ab7a39ba87e460be0c268ffaab2baf4dd0`
> **Related Documents:** ../superpowers/specs/2026-08-09-prospective-formal-qualification-master-design.md, ../superpowers/plans/2026-08-09-prospective-formal-qualification-master.md, ../status/Current-State.md

## 1. Delivered authority boundary

The existing Canonical Free Runtime remains the only Runtime owner. One
`SUPPLEMENTAL_SOURCE_FROZEN` stage is added to its existing PostgreSQL-backed
Daily acquisition journal. It records exact BaoStock ETF-history bytes and exact
content-addressed operational-policy bytes. The bounded Operational Research
producer converts those verified inputs and the existing stock Dataset into the
existing supplemental evidence contract; WP-STATE-01 remains the sole owner of
Market, ETF, Theme, Capital, Dynamic Pool and Candidate facts.

```text
BaoStock stock history/status + Tencent DecisionTime quote
+ BaoStock 510300.SH history + exact operational policy
→ verified SourceManifest/Dataset/Feature
→ existing WP-STATE-01 owner
→ Market/ETF/Theme/Capital → Dynamic Pool → Candidate
→ bounded pre-Decision Tencent minute → Signal → Forecast → Summary
```

There is no automatic Provider fallback. The V1 policy is current-only,
effective-dated and explicit that an ETF proxy is not index membership. Capital
evidence consists only of observable amount, persistence, concentration,
diffusion and participation proxies. No hidden investor intent is asserted.

## 2. Acceptance matrix

| Requirement | Observed engineering evidence | Status |
| --- | --- | --- |
| real State owner, no synthetic receipt | PostgreSQL E2E loads the State System receipt and owned State/Pool/Candidate artifacts | PASS |
| no caller-built supplemental positive path | RESEARCH and SHADOW positive tests call the recorded BaoStock client and the bounded producer | PASS |
| complete operational evidence | non-empty ETF/Theme/Capital observations, Pool and Candidate reach `RESEARCH_CANDIDATE` | PASS |
| actual source lineage | Summary records consumed BaoStock ETF product and policy source; unused Provider products are absent | PASS |
| partial/missing evidence | typed ETF/Theme/Capital missingness remains `DATA_INSUFFICIENT`; no static substitute | PASS |
| Provider outage | BaoStock exception propagates after one request; no Tencent/AKShare/Tushare substitution | PASS |
| future/late evidence | source available after DecisionTime is rejected | PASS |
| restart/recovery | successful supplemental stage receipt is reused; Provider call count remains one and final identities match | PASS |
| deterministic replay/reuse | same inputs retain owner artifact identities; no-material-change reuses immutable artifacts | PASS |
| SHADOW trading boundary | Summary is produced with no Order, Fill, Broker or Position mutation | PASS |
| PRODUCTION boundary | free evidence cannot satisfy Production qualification | PASS |
| real exact-window operation | 2026-08-09 is not an A-share trading day; no simulated result is counted as Live | BLOCKED_EXTERNAL_WINDOW |

## 3. Persistence and migration

No new database authority or migration is introduced. Migrations 001–033 remain
the complete PostgreSQL schema. The new acquisition-stage value is persisted by
the existing text/JSON stage receipt contract, and all State, Pool, Governance,
Continuous, Controlled, Canonical and Decision writes remain with their current
PostgreSQL owners.

## 4. Verification boundary

The containing checkpoint was verified against PostgreSQL 16.14 with a
credential-bearing, loopback, test-only DSN and random isolated schemas. The
repository-wide test command collected 2,576 tests and completed with:

```text
2576 passed
0 failed
0 skipped
6 warnings
8 subtests passed
696.37 seconds
```

The warnings are existing pandas DataFrame fragmentation performance warnings
in `test_top1000_return_leakage_attribution.py`; they are not Provider, Runtime,
PostgreSQL or lineage failures. Frozen dependency sync, documentation links,
Ruff, mypy, build and `git diff --check` are reported in the final engineering
handoff for the containing checkpoint.

This checkpoint proves `ENGINEERING_PROVEN` only. It does not prove:

- `LIVE_PROVEN`;
- `PROSPECTIVE_SHADOW_PROVEN`;
- exploratory economic value;
- real Formal PIT, Formal OOS or Cost/Capacity evidence;
- model qualification or Production authorization.

The evidence ceiling remains `FREE_DATA_EXPLORATORY / PIT_INCOMPLETE`.
