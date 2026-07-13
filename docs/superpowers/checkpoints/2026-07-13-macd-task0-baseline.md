# MACD staged implementation — Task 0 baseline

Date: 2026-07-13 (Asia/Shanghai)

## Authorization boundary

The final MACD specification is approved for staged implementation. Production promotion is not authorized before completion and independent review of the Stage 7 out-of-sample report.

The production defaults must remain:

- `score_weight=0.0`
- `conflict_gate_enabled=False`

Plan code fragments are implementation guidance, not text to copy mechanically. Every task must first inspect the current code structure, then proceed in this order:

1. add a failing test;
2. make the smallest implementation that satisfies it;
3. run focused tests;
4. run related regression tests;
5. create an independent commit.

## Repository baseline

- Baseline Git commit: `b6183b5ced2cd480cb351642d501f14237314c56`
- Baseline commit subject: `docs: plan intent-aware MACD implementation`
- Branch: `main`
- Upstream state: `main...origin/main [ahead 3]`
- Worktree before environment inspection: clean
- Repository root: `/Users/yuan/projects/market-regime-alpha`

`uv run --extra dev` generated an untracked `uv.lock` because this checkout did not contain one. The file was removed and is not part of the staged implementation.

## Python and dependency environment

- System Python: `3.12.13`
- Project Python through uv: `3.12.2`
- uv: `0.11.7`
- Project package: `market-regime-alpha 0.1.0`
- pandas: `3.0.3`
- pytest: `9.1.1`
- Ruff: `0.15.21`
- mypy: `2.2.0`

Other direct runtime dependencies resolved by uv at the baseline include akshare 1.18.64, APScheduler 3.11.3, baostock 0.9.3, DuckDB 1.5.4, FastAPI 0.139.0, Polars 1.42.1, PyArrow 25.0.0, Tushare 1.4.29, Uvicorn 0.51.0, yfinance 1.5.1, and psycopg 3.3.4 for the optional PostgreSQL extra.

## Verification baseline

Commands were run before implementation changes:

```text
uv run --extra dev pytest -q
uv run --extra dev ruff check src tests scripts backtesting
uv run --extra dev mypy
```

Results:

- pytest: passed, 198 tests collected/executed;
- Ruff: `All checks passed!`;
- mypy: `Success: no issues found in 12 source files`.

## Known historical failures and warnings

No historical test, Ruff, or mypy failure was present at this baseline.

The full test run emitted six pre-existing pandas `PerformanceWarning` instances from `backtesting/run_top1000_screened_portfolio_backtest.py` at lines 3091, 3097, and 3103. They report a highly fragmented DataFrame in two leakage-attribution tests. These are performance warnings, not correctness failures, and are unrelated to the MACD implementation scope.

## Stop conditions carried forward

Implementation must stop rather than add a temporary compatibility path if any of the following occurs:

- an unexplained baseline failure;
- a conflict between `SignalIntent` and actual trading semantics;
- unavailable point-in-time adjustment data;
- ambiguous bar timestamp or closed-bar eligibility;
- multiple MACD sizing owners in one pipeline;
- inability to preserve legacy output when `score_weight=0`;
- any change to the production baseline defaults.
