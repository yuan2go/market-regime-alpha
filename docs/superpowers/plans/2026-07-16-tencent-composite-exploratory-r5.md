# Tencent Composite Exploratory R5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and execute one identified Tencent-current plus local/BaoStock-history `EXPLORATORY` run for the 20-symbol watchlist, evaluate 60 completed R5 Candidate Decision Times with B0/B1, and refresh `dividend_t` from the same accepted data.

**Architecture:** Add a provider-neutral composite-source boundary under `research/` that retains row-level lineage, applies deterministic merge and quality rules, and emits only `DataEligibility.EXPLORATORY`. Reuse the existing R5 Candidate contracts and ranking implementations through exploratory Feature/Target materializers; keep the existing `dividend_t` model unchanged and inject the accepted composite frames through its provider interface.

**Tech Stack:** Python 3.12, dataclasses, pandas, existing Tencent/BaoStock adapters, pytest, Ruff, mypy, canonical JSON/SHA-256 identities.

## Global Constraints

- Xuntou remains the primary canonical R5 provider; Tencent, local cache, and BaoStock are explicit auxiliary sources.
- The authority ceiling is exactly `DataEligibility.EXPLORATORY`; never build `ProviderRehearsalMarketArtifact` from this path.
- The universe is `data/external/watchlists/dividend_t_watchlist.csv`, limited to its first 20 symbols.
- Use the latest 60 common completed Decision Dates, at least 21 prior warm-up sessions, and one following Target session.
- The run succeeds only when at least 16 of 20 symbols are accepted and at least 82 common complete sessions exist.
- The 14:55 Decision Time uses the latest valid 5-minute row with source timestamp no later than 14:50 under `tencent-composite-1455-one-full-5m-lag-v1`.
- Tencent owns valid current-session rows; local cache owns existing history; BaoStock fills historical gaps only.
- Preserve source conflicts, retrieval metadata, normalized content hashes, rejected symbols, and limitations.
- Do not infer ST, suspension, historical membership, listing age, price-limit regime, buyability, historical `available_at`, or provider bar finality.
- Do not change B0/B1 scoring semantics or Legacy `dividend_t` decision semantics.
- Every implementation task follows red-green-refactor and ends in one intentional commit.

---

## File Structure

Create focused files rather than extending `a_share_bars.py` or a single research God Object:

```text
src/market_regime_alpha/research/tencent_composite_contracts.py
    Immutable source, row, conflict, quality, prepared-session, and run-result contracts.

src/market_regime_alpha/research/tencent_composite_merge.py
    Frame normalization, deterministic source precedence, conflict retention, and session preparation.

src/market_regime_alpha/research/tencent_composite_quality.py
    Per-symbol quality dispositions, common-session selection, and the 16/20 run gate.

src/market_regime_alpha/research/tencent_composite_acquisition.py
    Injected Tencent/local/BaoStock acquisition with bounded retries and source manifests.

src/market_regime_alpha/research/tencent_composite_materialization.py
    Exploratory Candidate Population, Feature, and Target materialization without provider-availability claims.

src/market_regime_alpha/research/tencent_composite_runner.py
    B0 feature controls, the declared B1-A through B1-E ladder, panel evaluation, and run summary.

src/market_regime_alpha/research/tencent_composite_artifacts.py
    Non-overwriting run directory, canonical JSON outputs, Markdown report, and snapshot comparison.

src/market_regime_alpha/research/tencent_composite_dividend_t.py
    Read-only frame provider for accepted bars and `dividend_t` refresh orchestration.

scripts/run_tencent_composite_exploratory.py
    CLI composition root; no data semantics or model arithmetic.
```

Tests mirror those responsibilities under `tests/research/`, with existing Tencent parser tests retained in `tests/test_a_share_bars.py` and `tests/test_tencent_minute_cache.py`.

---

### Task 1: Freeze Composite Source and Authority Contracts

**Files:**
- Create: `src/market_regime_alpha/research/tencent_composite_contracts.py`
- Create: `tests/research/test_tencent_composite_contracts.py`

**Interfaces:**
- Consumes: `DataEligibility`, `DatasetContract`, `ProviderReference`, `SourceArtifactReference`, project identity/time wrappers.
- Produces: `CompositeSourceKind`, `CompositeDispositionCode`, `CompositeBar`, `CompositeSourcePartition`, `CompositeSourceConflict`, `CompositeSymbolDisposition`, `CompositeQualityReport`, `PreparedCompositeSession`, `PreparedCompositeData`, and `build_tencent_composite_dataset_contract(...)`.

- [ ] **Step 1: Write failing authority and validation tests**

```python
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.research.tencent_composite_contracts import (
    CompositeBar,
    CompositeSourceKind,
    build_tencent_composite_dataset_contract,
)


TZ = ZoneInfo("Asia/Shanghai")


def test_composite_contract_is_exploratory_and_not_pit() -> None:
    contract = build_tencent_composite_dataset_contract(
        watchlist_hash="sha256:watchlist",
        source_content_hashes=("sha256:local", "sha256:tencent"),
        code_revision="abc123",
        config_hash="sha256:config",
    )
    assert contract.eligibility is DataEligibility.EXPLORATORY
    assert contract.pit_correct_for_scope is False
    assert "CURRENT_WATCHLIST_BACKFILL_BIAS" in contract.limitations


def test_composite_bar_rejects_invalid_ohlc_and_naive_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        CompositeBar("000001.SZ", datetime(2026, 7, 1, 9, 35), 10, 11, 9, 10, 100, 1000, CompositeSourceKind.LOCAL)
    with pytest.raises(ValueError, match="OHLC"):
        CompositeBar(
            "000001.SZ",
            datetime(2026, 7, 1, 9, 35, tzinfo=TZ),
            10,
            9,
            10,
            10,
            100,
            1000,
            CompositeSourceKind.LOCAL,
        )
```

- [ ] **Step 2: Run the contract tests and verify the expected import failure**

Run: `python3 -m pytest tests/research/test_tencent_composite_contracts.py -v`

Expected: FAIL during collection with `ModuleNotFoundError: market_regime_alpha.research.tencent_composite_contracts`.

- [ ] **Step 3: Implement immutable contracts and deterministic exploratory Dataset identity**

```python
class CompositeSourceKind(str, Enum):
    TENCENT = "TENCENT"
    LOCAL = "LOCAL"
    BAOSTOCK = "BAOSTOCK"


class CompositeDispositionCode(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED_INSUFFICIENT_WARMUP = "REJECTED_INSUFFICIENT_WARMUP"
    REJECTED_INSUFFICIENT_DECISION_DATES = "REJECTED_INSUFFICIENT_DECISION_DATES"
    REJECTED_HISTORY_GAP = "REJECTED_HISTORY_GAP"
    REJECTED_TIMESTAMP_SEMANTICS = "REJECTED_TIMESTAMP_SEMANTICS"
    REJECTED_INVALID_PRICE = "REJECTED_INVALID_PRICE"
    REJECTED_SOURCE_CONFLICT = "REJECTED_SOURCE_CONFLICT"
    REJECTED_FETCH_FAILURE = "REJECTED_FETCH_FAILURE"


@dataclass(frozen=True, slots=True)
class CompositeBar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    source: CompositeSourceKind

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        values = (self.open, self.high, self.low, self.close)
        if any(not math.isfinite(value) or value <= 0 for value in values):
            raise ValueError("OHLC values must be finite and positive")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close) or self.low > self.high:
            raise ValueError("invalid OHLC relationship")
        if self.volume < 0 or self.amount < 0:
            raise ValueError("volume and amount must be non-negative")


def build_tencent_composite_dataset_contract(
    *,
    watchlist_hash: str,
    source_content_hashes: tuple[str, ...],
    code_revision: str,
    config_hash: str,
) -> DatasetContract:
    payload = {
        "schema_version": "tencent-composite-exploratory-v1",
        "watchlist_hash": watchlist_hash,
        "source_content_hashes": sorted(source_content_hashes),
        "code_revision": code_revision,
        "config_hash": config_hash,
    }
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return DatasetContract(
        dataset_id=DatasetId(f"tencent-composite-exploratory-{digest[:24]}"),
        schema_version="tencent-composite-exploratory-v1",
        eligibility=DataEligibility.EXPLORATORY,
        manifest_artifact_id=ArtifactId(f"tencent-composite-manifest-{digest[:24]}"),
        provider_references=(
            ProviderReference(ProviderId("provider-tencent-public"), "minute-and-quote", "observed-v1"),
            ProviderReference(ProviderId("provider-local-cache"), "dividend-t-5min-cache", "v1"),
            ProviderReference(ProviderId("provider-baostock"), "historical-5min-backfill", "v1"),
        ),
        pit_correct_for_scope=False,
        scope="20-symbol Tencent/local/BaoStock exploratory Candidate run",
        limitations=(
            "CURRENT_WATCHLIST_BACKFILL_BIAS",
            "HISTORICAL_AVAILABILITY_UNVERIFIED",
            "FIVE_MINUTE_BAR_LABEL_SEMANTICS_UNVERIFIED",
            "PRICE_ADJUSTMENT_REVISION_HISTORY_UNVERIFIED",
        ),
    )
```

Implement the remaining dataclasses with tuple fields, uniqueness checks, timezone-aware timestamps, and the invariant that `CompositeQualityReport.success` is true only for at least 16 accepted symbols and at least 82 common sessions.

- [ ] **Step 4: Run focused tests**

Run: `python3 -m pytest tests/research/test_tencent_composite_contracts.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the contracts**

```bash
git add src/market_regime_alpha/research/tencent_composite_contracts.py tests/research/test_tencent_composite_contracts.py
git commit -m "feat: define Tencent composite exploratory contracts"
```

---

### Task 2: Normalize and Merge Source Rows Without Losing Conflicts

**Files:**
- Create: `src/market_regime_alpha/research/tencent_composite_merge.py`
- Create: `tests/research/test_tencent_composite_merge.py`

**Interfaces:**
- Consumes: pandas frames with the existing `BAR_COLUMNS`, `CompositeBar`, and `CompositeSourceKind`.
- Produces: `normalize_composite_frame(frame, *, source) -> tuple[CompositeBar, ...]` and `merge_composite_bars(*, tencent, local, baostock, current_session) -> CompositeMergeResult`.

- [ ] **Step 1: Write failing precedence, conflict, and deduplication tests**

```python
def test_merge_uses_tencent_for_current_session_local_for_history_and_baostock_for_gaps() -> None:
    result = merge_composite_bars(
        tencent=(_bar("2026-07-16 09:35", 10.3, CompositeSourceKind.TENCENT),),
        local=(
            _bar("2026-07-15 09:35", 10.1, CompositeSourceKind.LOCAL),
            _bar("2026-07-16 09:35", 99.0, CompositeSourceKind.LOCAL),
        ),
        baostock=(
            _bar("2026-07-14 09:35", 9.9, CompositeSourceKind.BAOSTOCK),
            _bar("2026-07-15 09:35", 88.0, CompositeSourceKind.BAOSTOCK),
        ),
        current_session=date(2026, 7, 16),
    )
    assert [(bar.timestamp.date(), bar.source) for bar in result.bars] == [
        (date(2026, 7, 14), CompositeSourceKind.BAOSTOCK),
        (date(2026, 7, 15), CompositeSourceKind.LOCAL),
        (date(2026, 7, 16), CompositeSourceKind.TENCENT),
    ]
    assert len(result.conflicts) == 2


def test_normalize_rejects_duplicate_keys_and_invalid_timestamp() -> None:
    frame = pd.DataFrame([_row("2026-07-15 09:35", 10.0), _row("2026-07-15 09:35", 10.0)])
    with pytest.raises(ValueError, match="duplicate"):
        normalize_composite_frame(frame, source=CompositeSourceKind.LOCAL)
```

- [ ] **Step 2: Run the merge tests and verify failure**

Run: `python3 -m pytest tests/research/test_tencent_composite_merge.py -v`

Expected: FAIL because `tencent_composite_merge` does not exist.

- [ ] **Step 3: Implement strict frame normalization and explicit precedence**

```python
SOURCE_PRIORITY = {
    CompositeSourceKind.BAOSTOCK: 1,
    CompositeSourceKind.LOCAL: 2,
    CompositeSourceKind.TENCENT: 3,
}


def normalize_composite_frame(frame: Any, *, source: CompositeSourceKind) -> tuple[CompositeBar, ...]:
    required = {"symbol", "timestamp", "open", "high", "low", "close", "volume", "amount"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"composite frame missing columns: {sorted(missing)}")
    parsed = frame.copy()
    parsed["timestamp"] = pd.to_datetime(parsed["timestamp"], errors="raise")
    if parsed["timestamp"].dt.tz is None:
        parsed["timestamp"] = parsed["timestamp"].dt.tz_localize("Asia/Shanghai")
    keys = list(zip(parsed["symbol"].astype(str), parsed["timestamp"], strict=True))
    if len(keys) != len(set(keys)):
        raise ValueError("composite frame contains duplicate symbol/timestamp keys")
    return tuple(
        CompositeBar(
            symbol=str(row.symbol),
            timestamp=row.timestamp.to_pydatetime(),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume),
            amount=float(row.amount),
            source=source,
        )
        for row in parsed.itertuples(index=False)
    )


def merge_composite_bars(*, tencent, local, baostock, current_session):
    selected: dict[tuple[str, datetime], CompositeBar] = {}
    conflicts: list[CompositeSourceConflict] = []
    for candidate in sorted((*baostock, *local, *tencent), key=lambda bar: (bar.timestamp, SOURCE_PRIORITY[bar.source])):
        if candidate.source is CompositeSourceKind.TENCENT and candidate.timestamp.date() != current_session:
            continue
        key = (candidate.symbol, candidate.timestamp)
        existing = selected.get(key)
        if existing is not None and _numeric_payload(existing) != _numeric_payload(candidate):
            conflicts.append(CompositeSourceConflict(key, existing, candidate))
        if existing is None or SOURCE_PRIORITY[candidate.source] >= SOURCE_PRIORITY[existing.source]:
            selected[key] = candidate
    return CompositeMergeResult(
        bars=tuple(sorted(selected.values(), key=lambda bar: (bar.timestamp, bar.symbol))),
        conflicts=tuple(conflicts),
    )
```

The implementation must not drop conflicts merely because precedence selects one row.

- [ ] **Step 4: Run focused tests**

Run: `python3 -m pytest tests/research/test_tencent_composite_merge.py -v`

Expected: PASS.

- [ ] **Step 5: Commit normalization and merge behavior**

```bash
git add src/market_regime_alpha/research/tencent_composite_merge.py tests/research/test_tencent_composite_merge.py
git commit -m "feat: merge Tencent composite bars with provenance"
```

---

### Task 3: Prepare Complete Sessions and Enforce the 16/20 Quality Gate

**Files:**
- Create: `src/market_regime_alpha/research/tencent_composite_quality.py`
- Create: `tests/research/test_tencent_composite_quality.py`

**Interfaces:**
- Consumes: `CompositeMergeResult`, requested symbols, `decision_count`, `warmup_sessions`, `minimum_accepted_symbols`.
- Produces: `prepare_composite_data(...) -> PreparedCompositeData`; raises `TencentCompositeQualityGateError` when the whole run fails.

- [ ] **Step 1: Write failing tests for the conservative reference and run gate**

```python
def test_session_reference_uses_latest_row_no_later_than_1450() -> None:
    prepared = prepare_composite_data(
        _merge_result(symbol_count=16, session_count=82, include_1450=True, include_1455=True),
        requested_symbols=_symbols(20),
        decision_count=60,
        warmup_sessions=21,
        minimum_accepted_symbols=16,
    )
    session = prepared.session_for("000001.SZ", prepared.common_session_dates[-2])
    assert session.reference_timestamp.strftime("%H:%M") == "14:50"
    assert prepared.quality.success is True
    assert len(prepared.quality.accepted_symbols) == 16


def test_quality_gate_fails_below_sixteen_symbols() -> None:
    with pytest.raises(TencentCompositeQualityGateError, match="accepted symbols 15 < 16"):
        prepare_composite_data(
            _merge_result(symbol_count=15, session_count=82),
            requested_symbols=_symbols(20),
            decision_count=60,
            warmup_sessions=21,
            minimum_accepted_symbols=16,
        )


def test_quality_gate_requires_warmup_decisions_and_following_target() -> None:
    with pytest.raises(TencentCompositeQualityGateError, match="common complete sessions 81 < 82"):
        prepare_composite_data(
            _merge_result(symbol_count=16, session_count=81),
            requested_symbols=_symbols(20),
            decision_count=60,
            warmup_sessions=21,
            minimum_accepted_symbols=16,
        )
```

- [ ] **Step 2: Run the quality tests and verify failure**

Run: `python3 -m pytest tests/research/test_tencent_composite_quality.py -v`

Expected: FAIL because the quality module does not exist.

- [ ] **Step 3: Implement session aggregation, dispositions, and common-date selection**

```python
REFERENCE_CUTOFF = time(14, 50)
MINIMUM_BARS_PER_SESSION = 46


def _prepare_session(symbol: str, session_date: date, bars: tuple[CompositeBar, ...]) -> PreparedCompositeSession | None:
    ordered = tuple(sorted(bars, key=lambda bar: bar.timestamp))
    if len(ordered) < MINIMUM_BARS_PER_SESSION:
        return None
    reference_candidates = [bar for bar in ordered if bar.timestamp.timetz().replace(tzinfo=None) <= REFERENCE_CUTOFF]
    if not reference_candidates:
        return None
    reference = reference_candidates[-1]
    return PreparedCompositeSession(
        symbol=symbol,
        session_date=session_date,
        open=ordered[0].open,
        high=max(bar.high for bar in ordered),
        low=min(bar.low for bar in ordered),
        close=ordered[-1].close,
        amount=sum(bar.amount for bar in ordered),
        reference_price=reference.close,
        reference_timestamp=reference.timestamp,
        source_kinds=tuple(sorted({bar.source for bar in ordered}, key=lambda item: item.value)),
    )


def prepare_composite_data(
    merged: CompositeMergeResult,
    *,
    requested_symbols: tuple[str, ...],
    decision_count: int = 60,
    warmup_sessions: int = 21,
    minimum_accepted_symbols: int = 16,
) -> PreparedCompositeData:
    required_sessions = warmup_sessions + decision_count + 1
    sessions_by_symbol = _group_complete_sessions(merged.bars)
    accepted = tuple(sorted(symbol for symbol in requested_symbols if len(sessions_by_symbol.get(symbol, ())) >= required_sessions))
    common = tuple(sorted(set.intersection(*(set(sessions_by_symbol[symbol]) for symbol in accepted)))) if accepted else ()
    quality = _build_quality_report(requested_symbols, sessions_by_symbol, accepted, common, required_sessions)
    if len(accepted) < minimum_accepted_symbols:
        raise TencentCompositeQualityGateError(f"accepted symbols {len(accepted)} < {minimum_accepted_symbols}", quality)
    if len(common) < required_sessions:
        raise TencentCompositeQualityGateError(f"common complete sessions {len(common)} < {required_sessions}", quality)
    selected_dates = common[-required_sessions:]
    return PreparedCompositeData(
        accepted_symbols=accepted,
        common_session_dates=selected_dates,
        sessions=tuple(sessions_by_symbol[symbol][day] for day in selected_dates for symbol in accepted),
        quality=quality,
        limitations=("CURRENT_WATCHLIST_BACKFILL_BIAS", "tencent-composite-1455-one-full-5m-lag-v1"),
    )
```

Conflict findings remain visible. A conflict rejects a symbol only when the selected row cannot be resolved deterministically under the declared precedence or when the conflict violates OHLC validation.

- [ ] **Step 4: Run focused tests**

Run: `python3 -m pytest tests/research/test_tencent_composite_quality.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the quality gate**

```bash
git add src/market_regime_alpha/research/tencent_composite_quality.py tests/research/test_tencent_composite_quality.py
git commit -m "feat: gate Tencent composite data quality"
```

---

### Task 4: Acquire Identified Tencent, Local, and BaoStock Partitions

**Files:**
- Create: `src/market_regime_alpha/research/tencent_composite_acquisition.py`
- Create: `tests/research/test_tencent_composite_acquisition.py`
- Modify: `src/market_regime_alpha/data_sources/a_share_bars.py`
- Modify: `tests/test_a_share_bars.py`

**Interfaces:**
- Consumes: injected `TencentMinuteProvider`, `BaoStockADataProvider`, a local-cache reader, and `fetch_tencent_latest_quotes`.
- Produces: `read_local_5min_cache(...)`, `TencentCompositeAcquirer.acquire(...) -> CompositeAcquisitionResult`, source partitions, attempt records, normalized hashes, and current quotes.

- [ ] **Step 1: Characterize a public local-cache reader**

Add this test beside the existing local-cache provider tests:

```python
def test_read_local_5min_cache_preserves_normalized_rows_without_tencent_merge(self) -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "601919.SH_5min.csv"
        pd.DataFrame(
            {
                "symbol": ["601919.SH"],
                "timestamp": ["2026-07-15 09:35:00"],
                "open": [14.5],
                "high": [14.6],
                "low": [14.4],
                "close": [14.55],
                "volume": [1_000_000.0],
                "amount": [14_550_000.0],
                "source_freq": ["5min"],
            }
        ).to_csv(path, index=False)
        frame = read_local_5min_cache("601919.SH", cache_dir=directory)
    self.assertEqual(list(frame["timestamp"]), ["2026-07-15 09:35:00"])
    self.assertEqual(frame.attrs["data_source"], "local_csv_5min")
```

- [ ] **Step 2: Run the characterization test and verify failure**

Run: `python3 -m pytest tests/test_a_share_bars.py::AShareBarsTests::test_read_local_5min_cache_preserves_normalized_rows_without_tencent_merge -v`

Expected: FAIL because `read_local_5min_cache` is not exported.

- [ ] **Step 3: Add the thin public reader without changing merge behavior**

```python
def read_local_5min_cache(
    symbol: str,
    *,
    cache_dir: str | Path = DEFAULT_LOCAL_5MIN_CACHE_DIR,
    source_freq: str = "5min",
) -> Any:
    """Read one identified local cache partition without any network merge."""
    return _read_local_5min_cache(symbol, cache_dir=Path(cache_dir), source_freq=source_freq)
```

- [ ] **Step 4: Write failing acquisition tests with injected providers**

```python
def test_acquirer_records_attempts_hashes_and_all_three_source_partitions() -> None:
    acquirer = TencentCompositeAcquirer(
        tencent=FakeTencentProvider(),
        baostock=FakeBaoStockProvider(),
        local_reader=fake_local_reader,
        quote_fetcher=fake_quote_fetcher,
        retry_count=2,
    )
    result = acquirer.acquire(
        symbols=("000001.SZ",),
        start_date="2026-01-01",
        end_date="2026-07-16",
        retrieved_at=datetime(2026, 7, 16, 16, 0, tzinfo=TZ),
    )
    assert {partition.source for partition in result.partitions} == {
        CompositeSourceKind.TENCENT,
        CompositeSourceKind.LOCAL,
        CompositeSourceKind.BAOSTOCK,
    }
    assert all(partition.content_hash.startswith("sha256:") for partition in result.partitions)
    assert result.quote_partition.product == "latest-quote"
    assert result.quote_partition.content_hash.startswith("sha256:")
    assert result.attempts[0].success is True
    assert result.quotes["000001.SZ"].source == "tencent_qt_quote"
```

- [ ] **Step 5: Run the acquisition tests and verify failure**

Run: `python3 -m pytest tests/research/test_tencent_composite_acquisition.py -v`

Expected: FAIL because the acquisition module does not exist.

- [ ] **Step 6: Implement bounded retries and deterministic normalized partition hashes**

```python
class TencentCompositeAcquirer:
    def __init__(self, *, tencent, baostock, local_reader, quote_fetcher, retry_count: int = 2) -> None:
        self.tencent = tencent
        self.baostock = baostock
        self.local_reader = local_reader
        self.quote_fetcher = quote_fetcher
        self.retry_count = retry_count

    def acquire(self, *, symbols, start_date, end_date, retrieved_at):
        partitions = []
        attempts = []
        for symbol in symbols:
            local = self.local_reader(symbol)
            partitions.append(_partition(symbol, CompositeSourceKind.LOCAL, local, retrieved_at, f"local://{symbol}"))
            bao, bao_attempts = self._retry_frame(
                "baostock",
                symbol,
                lambda: self.baostock.minute_bars(symbol, freq="5min", start_date=start_date, end_date=end_date),
            )
            attempts.extend(bao_attempts)
            partitions.append(_partition(symbol, CompositeSourceKind.BAOSTOCK, bao, retrieved_at, f"baostock://{symbol}"))
            current, current_attempts = self._retry_frame(
                "tencent",
                symbol,
                lambda: self.tencent.minute_bars(symbol, freq="5min"),
            )
            attempts.extend(current_attempts)
            partitions.append(_partition(symbol, CompositeSourceKind.TENCENT, current, retrieved_at, f"tencent://minute/{symbol}"))
        quotes = self.quote_fetcher(symbols)
        quote_partition = _quote_partition(quotes, retrieved_at, "tencent://latest-quote")
        return CompositeAcquisitionResult(tuple(partitions), quote_partition, tuple(attempts), quotes, retrieved_at)
```

Hash normalized frames by canonical ordered records, never by pandas object repr. A failed source partition records its attempts and an empty partition; it does not invent rows.

- [ ] **Step 7: Run focused acquisition and existing adapter tests**

Run: `python3 -m pytest tests/research/test_tencent_composite_acquisition.py tests/test_a_share_bars.py tests/test_tencent_minute_cache.py -v`

Expected: PASS.

- [ ] **Step 8: Commit the acquisition boundary**

```bash
git add src/market_regime_alpha/data_sources/a_share_bars.py src/market_regime_alpha/research/tencent_composite_acquisition.py tests/test_a_share_bars.py tests/research/test_tencent_composite_acquisition.py
git commit -m "feat: acquire identified Tencent composite sources"
```

---

### Task 5: Materialize Exploratory R5 Features and Targets

**Files:**
- Modify: `src/market_regime_alpha/features/rehearsal_baselines.py`
- Modify: `tests/candidates/test_rehearsal_materializers.py`
- Create: `src/market_regime_alpha/research/tencent_composite_materialization.py`
- Create: `tests/research/test_tencent_composite_materialization.py`

**Interfaces:**
- Consumes: `PreparedCompositeData`, an `EXPLORATORY` `DatasetContract`, `DecisionTime`, `RetrievedAt`, and existing R5 Feature/Target definitions.
- Produces: `calculate_r5_baseline_feature_values(...)`, `materialize_tencent_composite_slice(...) -> tuple[CandidateResearchDataset, ...]`, one dataset for each of Return/MFE/MAE.

- [ ] **Step 1: Add a regression test for a pure baseline calculation helper**

```python
def test_pure_r5_baseline_calculator_matches_existing_formulas() -> None:
    closes = tuple(float(value) for value in range(80, 101))
    amounts = tuple(1_000_000.0 + index for index in range(21))
    values = calculate_r5_baseline_feature_values(
        prior_closes=closes,
        prior_amounts=amounts,
        reference_price=102.0,
    )
    assert values[MOMENTUM_5S_ID] == pytest.approx(102.0 / closes[-5] - 1.0)
    assert values[LIQUIDITY_20S_ID] == pytest.approx(math.log1p(median(amounts[-20:])))
    assert values[PRICE_VS_MA20_ID] == pytest.approx(102.0 / mean(closes[-20:]) - 1.0)
    assert values[VOLATILITY_20S_ID] is not None
```

- [ ] **Step 2: Run the helper test and verify failure**

Run: `python3 -m pytest tests/candidates/test_rehearsal_materializers.py::test_pure_r5_baseline_calculator_matches_existing_formulas -v`

Expected: FAIL because the helper does not exist.

- [ ] **Step 3: Extract the pure helper and delegate the existing materializer to it**

```python
def calculate_r5_baseline_feature_values(
    *,
    prior_closes: Sequence[float],
    prior_amounts: Sequence[float],
    reference_price: float | None,
) -> dict[FeatureDefinitionId, float | None]:
    momentum = reference_price / prior_closes[-5] - 1.0 if reference_price is not None and len(prior_closes) >= 5 else None
    volatility = None
    if len(prior_closes) >= 21:
        recent = prior_closes[-21:]
        volatility = pstdev(recent[index] / recent[index - 1] - 1.0 for index in range(1, len(recent)))
    liquidity = math.log1p(median(prior_amounts[-20:])) if len(prior_amounts) >= 20 else None
    price_vs_ma20 = reference_price / mean(prior_closes[-20:]) - 1.0 if reference_price is not None and len(prior_closes) >= 20 else None
    return {
        MOMENTUM_5S_ID: momentum,
        VOLATILITY_20S_ID: volatility,
        LIQUIDITY_20S_ID: liquidity,
        PRICE_VS_MA20_ID: price_vs_ma20,
    }
```

Replace only the duplicated arithmetic inside `materialize_r5_baseline_features`; preserve definitions, missingness, IDs, and output ordering.

- [ ] **Step 4: Write failing exploratory materialization tests**

```python
def test_materialized_slices_are_exploratory_and_use_retrieval_time_only_for_observed_targets() -> None:
    datasets = materialize_tencent_composite_slice(
        prepared=_prepared_data(),
        decision_date=date(2026, 7, 14),
        dataset_contract=_exploratory_contract(),
        retrieved_at=RetrievedAt(datetime(2026, 7, 16, 16, 0, tzinfo=TZ)),
        code_revision="abc123",
        config_hash="sha256:config",
    )
    assert len(datasets) == 3
    assert {dataset.target_id for dataset in datasets} == {
        R5_NEXT_SESSION_RETURN_TARGET_ID,
        R5_NEXT_SESSION_MFE_TARGET_ID,
        R5_NEXT_SESSION_MAE_TARGET_ID,
    }
    assert all(dataset.data_eligibility is DataEligibility.EXPLORATORY for dataset in datasets)
    assert all(dataset.rows[0].target.observed_at.isoformat() == "2026-07-16T16:00:00+08:00" for dataset in datasets)
```

- [ ] **Step 5: Run exploratory materialization tests and verify failure**

Run: `python3 -m pytest tests/research/test_tencent_composite_materialization.py -v`

Expected: FAIL because the materialization module does not exist.

- [ ] **Step 6: Implement direct exploratory Feature and Target artifacts**

```python
def materialize_tencent_composite_slice(*, prepared, decision_date, dataset_contract, retrieved_at, code_revision, config_hash):
    if dataset_contract.eligibility is not DataEligibility.EXPLORATORY or dataset_contract.pit_correct_for_scope:
        raise ValueError("Tencent composite slice requires non-PIT EXPLORATORY DatasetContract")
    decision_time = DecisionTime(datetime.combine(decision_date, time(14, 55), tzinfo=SHANGHAI_TZ))
    population = CandidatePopulation(
        universe_id=_watchlist_universe_id(dataset_contract.dataset_id, decision_date),
        decision_time=decision_time,
        symbols=prepared.accepted_symbols,
        source_dataset_ids=(dataset_contract.dataset_id,),
    )
    feature_materializations = _materialize_features(
        prepared=prepared,
        population=population,
        source_dataset_id=dataset_contract.dataset_id,
        code_revision=code_revision,
        config_hash=config_hash,
    )
    next_date = prepared.next_session_date(decision_date)
    target_materializations = _materialize_targets(
        prepared=prepared,
        population=population,
        next_date=next_date,
        observed_at=AvailabilityTime(retrieved_at.value),
        materialized_at=AsOfTime(retrieved_at.value),
        code_revision=code_revision,
        config_hash=config_hash,
    )
    return tuple(
        build_candidate_research_dataset(
            population=population,
            dataset_contracts=(dataset_contract,),
            feature_definitions=r5_baseline_feature_definitions(),
            feature_materializations=feature_materializations,
            target_contract=target_contract,
            target_materialization=target_materializations[target_contract.target_id],
            limitations=prepared.limitations,
        )
        for target_contract in r5_next_session_opportunity_target_contracts()
    )
```

The Feature materializer uses only sessions strictly earlier than `decision_date` plus that date's conservative reference price. The Target materializer uses only the following selected session and assigns `retrieved_at` as the honest time the historical outcome became available to this run.

- [ ] **Step 7: Run focused and existing Candidate materializer tests**

Run: `python3 -m pytest tests/research/test_tencent_composite_materialization.py tests/candidates/test_rehearsal_materializers.py tests/candidates/test_r5_opportunity_target_bundle.py -v`

Expected: PASS with unchanged existing R5 values.

- [ ] **Step 8: Commit materialization**

```bash
git add src/market_regime_alpha/features/rehearsal_baselines.py src/market_regime_alpha/research/tencent_composite_materialization.py tests/candidates/test_rehearsal_materializers.py tests/research/test_tencent_composite_materialization.py
git commit -m "feat: materialize exploratory Tencent Candidate slices"
```

---

### Task 6: Run B0 Controls and the Declared B1 Ladder

**Files:**
- Create: `src/market_regime_alpha/research/tencent_composite_runner.py`
- Create: `tests/research/test_tencent_composite_runner.py`

**Interfaces:**
- Consumes: 60 completed Decision Dates from `PreparedCompositeData`, three per-date Candidate datasets, existing B0/B1 rankers and panel evaluation.
- Produces: `r5_b1_exploratory_specs()`, `run_tencent_composite_candidate_experiment(...) -> TencentCompositeCandidateRun`.

- [ ] **Step 1: Write failing tests for the untuned B1 ladder and 60-date coverage**

```python
def test_b1_ladder_matches_declared_ablation_family() -> None:
    specs = r5_b1_exploratory_specs()
    assert tuple(specs) == ("B1-A", "B1-B", "B1-C", "B1-D", "B1-E")
    assert tuple(component.feature_id for component in specs["B1-A"].components) == (MOMENTUM_5S_ID,)
    assert PRICE_VS_MA20_ID not in {component.feature_id for component in specs["B1-D"].components}
    assert PRICE_VS_MA20_ID in {component.feature_id for component in specs["B1-E"].components}


def test_candidate_run_evaluates_sixty_dates_for_all_three_targets() -> None:
    result = run_tencent_composite_candidate_experiment(
        prepared=_prepared_data(session_count=82, symbol_count=16),
        dataset_contract=_exploratory_contract(),
        retrieved_at=RetrievedAt(datetime(2026, 7, 16, 16, 0, tzinfo=TZ)),
        code_revision="abc123",
        config_hash="sha256:config",
    )
    assert result.decision_date_count == 60
    assert len(result.target_runs) == 3
    assert all(target.panel.slice_count == 60 for target in result.target_runs)
    assert all(len(target.b0_evaluations) == 4 for target in result.target_runs)
    assert all(len(target.b1_evaluations) == 5 for target in result.target_runs)
    assert result.data_eligibility is DataEligibility.EXPLORATORY
```

- [ ] **Step 2: Run the runner tests and verify failure**

Run: `python3 -m pytest tests/research/test_tencent_composite_runner.py -v`

Expected: FAIL because the runner module does not exist.

- [ ] **Step 3: Implement fixed equal-weight B1-A through B1-E specifications**

```python
def _component(feature_id, direction, role):
    return CompositeFeatureComponent(feature_id=feature_id, direction=direction, weight=1.0, role=role)


def r5_b1_exploratory_specs() -> dict[str, TransparentCompositeSpec]:
    momentum = _component(
        MOMENTUM_5S_ID,
        CompositeFeatureDirection.HIGHER_IS_BETTER,
        CompositeFeatureRole.OPPORTUNITY,
    )
    liquidity = _component(
        LIQUIDITY_20S_ID,
        CompositeFeatureDirection.HIGHER_IS_BETTER,
        CompositeFeatureRole.QUALITY,
    )
    volatility = _component(
        VOLATILITY_20S_ID,
        CompositeFeatureDirection.LOWER_IS_BETTER,
        CompositeFeatureRole.RISK_PENALTY,
    )
    price_vs_ma = _component(
        PRICE_VS_MA20_ID,
        CompositeFeatureDirection.HIGHER_IS_BETTER,
        CompositeFeatureRole.QUALITY,
    )
    return {
        "B1-A": TransparentCompositeSpec((momentum,)),
        "B1-B": TransparentCompositeSpec((momentum, liquidity)),
        "B1-C": TransparentCompositeSpec((momentum, volatility)),
        "B1-D": TransparentCompositeSpec((momentum, liquidity, volatility)),
        "B1-E": TransparentCompositeSpec((momentum, liquidity, volatility, price_vs_ma)),
    }
```

- [ ] **Step 4: Implement chronological slice assembly and evaluation**

```python
def run_tencent_composite_candidate_experiment(*, prepared, dataset_contract, retrieved_at, code_revision, config_hash):
    decision_dates = prepared.common_session_dates[-61:-1]
    datasets_by_target: dict[TargetId, list[CandidateResearchDataset]] = defaultdict(list)
    for decision_date in decision_dates:
        for dataset in materialize_tencent_composite_slice(
            prepared=prepared,
            decision_date=decision_date,
            dataset_contract=dataset_contract,
            retrieved_at=retrieved_at,
            code_revision=code_revision,
            config_hash=config_hash,
        ):
            datasets_by_target[dataset.target_id].append(dataset)
    target_runs = tuple(
        _run_target_models(
            datasets=tuple(datasets_by_target[target_id]),
            code_revision=code_revision,
            config_hash=config_hash,
        )
        for target_id in sorted(datasets_by_target, key=str)
    )
    return TencentCompositeCandidateRun(
        data_eligibility=DataEligibility.EXPLORATORY,
        decision_dates=decision_dates,
        accepted_symbols=prepared.accepted_symbols,
        target_runs=target_runs,
        limitations=prepared.limitations,
    )
```

`_run_target_models` must create four B0 runs, one per frozen Feature, and five B1 runs per slice. It assembles one panel per Target and evaluates every model with `evaluate_candidate_ranking_panel(top_k=5)`. Model IDs include the Feature ID or B1 ladder name; no weight search is allowed.

- [ ] **Step 5: Run runner and existing B0/B1 tests**

Run: `python3 -m pytest tests/research/test_tencent_composite_runner.py tests/candidates/test_composite_baseline.py tests/candidates/test_baseline_ranking_evaluation_guards.py -v`

Expected: PASS.

- [ ] **Step 6: Commit the Candidate runner**

```bash
git add src/market_regime_alpha/research/tencent_composite_runner.py tests/research/test_tencent_composite_runner.py
git commit -m "feat: run Tencent exploratory B0 B1 experiments"
```

---

### Task 7: Write Non-Overwriting Run Artifacts and Human Report

**Files:**
- Create: `src/market_regime_alpha/research/tencent_composite_artifacts.py`
- Create: `tests/research/test_tencent_composite_artifacts.py`

**Interfaces:**
- Consumes: acquisition, merge, quality, Candidate run, and optional dividend refresh results.
- Produces: `write_tencent_composite_run(...) -> Path` and the exact seven files defined by the design.

- [ ] **Step 1: Write failing atomicity and manifest tests**

```python
def test_writer_creates_complete_non_overwriting_run(tmp_path: Path) -> None:
    output = write_tencent_composite_run(
        root=tmp_path,
        run_id="run-abc123",
        manifest=_manifest(),
        quality=_quality(),
        conflicts=(),
        candidate_run=_candidate_run(),
        dividend_refresh=_dividend_refresh(),
    )
    assert {path.name for path in output.iterdir()} == {
        "manifest.json",
        "quality.json",
        "source_conflicts.json",
        "candidate_panel_summary.json",
        "b0_b1_evaluation.json",
        "candidate_report.md",
        "dividend_t_refresh.json",
    }
    assert json.loads((output / "manifest.json").read_text())["data_eligibility"] == "EXPLORATORY"
    with pytest.raises(FileExistsError):
        write_tencent_composite_run(root=tmp_path, run_id="run-abc123", manifest=_manifest(), quality=_quality(), conflicts=(), candidate_run=_candidate_run(), dividend_refresh=_dividend_refresh())
```

- [ ] **Step 2: Run artifact tests and verify failure**

Run: `python3 -m pytest tests/research/test_tencent_composite_artifacts.py -v`

Expected: FAIL because the artifact module does not exist.

- [ ] **Step 3: Implement canonical JSON, staging, atomic rename, and Markdown rendering**

```python
OUTPUT_FILENAMES = (
    "manifest.json",
    "quality.json",
    "source_conflicts.json",
    "candidate_panel_summary.json",
    "b0_b1_evaluation.json",
    "candidate_report.md",
    "dividend_t_refresh.json",
)


def write_tencent_composite_run(*, root, run_id, manifest, quality, conflicts, candidate_run, dividend_refresh):
    final = Path(root) / run_id
    if final.exists():
        raise FileExistsError(f"run already exists: {final}")
    stage = Path(root) / f".{run_id}.staging"
    if stage.exists():
        raise FileExistsError(f"staging run already exists: {stage}")
    stage.mkdir(parents=True)
    try:
        _write_json(stage / "manifest.json", manifest)
        _write_json(stage / "quality.json", quality)
        _write_json(stage / "source_conflicts.json", conflicts)
        _write_json(stage / "candidate_panel_summary.json", candidate_run.panel_summary())
        _write_json(stage / "b0_b1_evaluation.json", candidate_run.evaluation_summary())
        (stage / "candidate_report.md").write_text(render_candidate_report(manifest, quality, candidate_run), encoding="utf-8")
        _write_json(stage / "dividend_t_refresh.json", dividend_refresh)
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final
```

The Markdown report leads with accepted/rejected symbols, authority limitations, data dates, and source conflicts before model metrics.

- [ ] **Step 4: Run artifact tests**

Run: `python3 -m pytest tests/research/test_tencent_composite_artifacts.py -v`

Expected: PASS.

- [ ] **Step 5: Commit artifact writing**

```bash
git add src/market_regime_alpha/research/tencent_composite_artifacts.py tests/research/test_tencent_composite_artifacts.py
git commit -m "feat: write Tencent exploratory run artifacts"
```

---

### Task 8: Refresh Dividend T From the Same Accepted Composite Frames

**Files:**
- Create: `src/market_regime_alpha/research/tencent_composite_dividend_t.py`
- Create: `tests/research/test_tencent_composite_dividend_t.py`
- Do not change: `src/market_regime_alpha/dividend_t/strategy.py`
- Do not change: `src/market_regime_alpha/dividend_t/cosco_timing.py`

**Interfaces:**
- Consumes: accepted merged bars, Tencent quotes, existing snapshot JSON, and `build_dividend_trend_snapshot(...)`.
- Produces: `CompositeFrameProvider`, `refresh_dividend_t_from_composite(...) -> DividendTRefreshResult`, and an additive before/after diff.

- [ ] **Step 1: Write failing provider and semantic-separation tests**

```python
def test_composite_frame_provider_exposes_only_accepted_symbols() -> None:
    provider = CompositeFrameProvider(frames={"000001.SZ": _frame(), "000002.SZ": _frame()})
    assert len(provider.minute_bars("000001.SZ")) > 0
    with pytest.raises(KeyError, match="not accepted"):
        provider.minute_bars("000003.SZ")


def test_refresh_keeps_candidate_rank_separate_from_dividend_action(tmp_path: Path) -> None:
    result = refresh_dividend_t_from_composite(
        watchlist_path=_watchlist(tmp_path),
        frames={"000001.SZ": _frame()},
        quotes={"000001.SZ": LatestQuote("000001.SZ", 10.5)},
        before_snapshot={"schema_version": 2, "rows": []},
        generated_at=datetime(2026, 7, 16, 16, 0, tzinfo=TZ),
    )
    row = result.snapshot["rows"][0]
    assert "candidate_rank" not in row
    assert "signal" in row
    assert result.diff["symbols"]["000001.SZ"]["after_status"] == "ok"
```

- [ ] **Step 2: Run dividend integration tests and verify failure**

Run: `python3 -m pytest tests/research/test_tencent_composite_dividend_t.py -v`

Expected: FAIL because the integration module does not exist.

- [ ] **Step 3: Implement the injected provider and additive snapshot diff**

```python
class CompositeFrameProvider:
    name = "tencent_composite_exploratory"
    data_source = "tencent_current+local_history+baostock_gap_fill"
    is_realtime = False

    def __init__(self, *, frames: Mapping[str, Any]) -> None:
        self._frames = dict(frames)

    def minute_bars(self, symbol, *, freq="5min", start_date=None, end_date=None):
        if symbol not in self._frames:
            raise KeyError(f"symbol not accepted by composite quality gate: {symbol}")
        frame = self._frames[symbol].copy()
        return _filter_frame(frame, start_date=start_date, end_date=end_date)


def refresh_dividend_t_from_composite(*, watchlist_path, frames, quotes, before_snapshot, generated_at):
    snapshot = build_dividend_trend_snapshot(
        watchlist_path=watchlist_path,
        limit=20,
        provider=CompositeFrameProvider(frames=frames),
        quotes=quotes,
        generated_at=generated_at,
    )
    return DividendTRefreshResult(snapshot=snapshot, diff=compare_dividend_snapshots(before_snapshot, snapshot))
```

The diff includes coverage, latest bar/source, signal, timing action, displayed 1/3/5-day values, support/resistance/stop, and data-insufficient state. It never injects Candidate ranking into Legacy action fields.

- [ ] **Step 4: Run focused and existing snapshot tests**

Run: `python3 -m pytest tests/research/test_tencent_composite_dividend_t.py tests/test_dividend_trend_snapshot.py tests/legacy/test_trend_snapshot_characterization.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the dividend refresh boundary**

```bash
git add src/market_regime_alpha/research/tencent_composite_dividend_t.py tests/research/test_tencent_composite_dividend_t.py
git commit -m "feat: refresh dividend T from composite data"
```

---

### Task 9: Add the CLI, Public Exports, Status Documentation, and Execute the First Run

**Files:**
- Create: `scripts/run_tencent_composite_exploratory.py`
- Create: `tests/research/test_tencent_composite_cli.py`
- Modify: `src/market_regime_alpha/research/__init__.py`
- Modify: `pyproject.toml`
- Modify: `docs/research/R5-Current-Status.md`

**Interfaces:**
- Consumes: every interface from Tasks 1-8.
- Produces: `main(argv: Sequence[str] | None = None) -> int`, a real run directory, refreshed `docs/data/dividend_trends.json`, exact command evidence, and current-status documentation.

- [ ] **Step 1: Write a failing CLI orchestration test with all network dependencies injected**

```python
def test_cli_runs_candidate_before_dividend_refresh_and_writes_identified_outputs(tmp_path: Path, monkeypatch) -> None:
    events: list[str] = []
    monkeypatch.setattr(cli, "build_default_acquirer", lambda **_: FakeAcquirer())
    monkeypatch.setattr(cli, "run_tencent_composite_candidate_experiment", lambda **_: events.append("candidate") or _candidate_run())
    monkeypatch.setattr(cli, "refresh_dividend_t_from_composite", lambda **_: events.append("dividend") or _refresh())
    code = cli.main([
        "--watchlist", str(_watchlist(tmp_path)),
        "--output-root", str(tmp_path / "runs"),
        "--snapshot-output", str(tmp_path / "dividend_trends.json"),
        "--retrieved-at", "2026-07-16T16:00:00+08:00",
    ])
    assert code == 0
    assert events == ["candidate", "dividend"]
    assert (tmp_path / "dividend_trends.json").exists()
```

- [ ] **Step 2: Run the CLI test and verify failure**

Run: `python3 -m pytest tests/research/test_tencent_composite_cli.py -v`

Expected: FAIL because the CLI script does not exist.

- [ ] **Step 3: Implement a thin CLI composition root**

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Tencent composite EXPLORATORY Candidate research")
    parser.add_argument("--watchlist", type=Path, default=DEFAULT_WATCHLIST_PATH)
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "data" / "processed" / "tencent_composite_exploratory")
    parser.add_argument("--snapshot-output", type=Path, default=DEFAULT_TREND_OUTPUT)
    parser.add_argument("--decision-count", type=int, default=60)
    parser.add_argument("--warmup-sessions", type=int, default=21)
    parser.add_argument("--minimum-accepted-symbols", type=int, default=16)
    parser.add_argument("--history-calendar-days", type=int, default=180)
    parser.add_argument("--timeout-seconds", type=float, default=8.0)
    parser.add_argument("--retry-count", type=int, default=2)
    parser.add_argument("--retrieved-at")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    retrieved_at = _retrieved_at(args.retrieved_at)
    watchlist = tuple(item.symbol for item in load_watchlist(args.watchlist)[:20])
    acquisition = build_default_acquirer(timeout_seconds=args.timeout_seconds, retry_count=args.retry_count).acquire(
        symbols=watchlist,
        start_date=(retrieved_at.value.date() - timedelta(days=args.history_calendar_days)).isoformat(),
        end_date=retrieved_at.value.date().isoformat(),
        retrieved_at=retrieved_at.value,
    )
    merged = merge_acquisition(acquisition)
    prepared = prepare_composite_data(
        merged,
        requested_symbols=watchlist,
        decision_count=args.decision_count,
        warmup_sessions=args.warmup_sessions,
        minimum_accepted_symbols=args.minimum_accepted_symbols,
    )
    contract = build_contract_from_acquisition(acquisition, args)
    candidate = run_tencent_composite_candidate_experiment(
        prepared=prepared,
        dataset_contract=contract,
        retrieved_at=RetrievedAt(retrieved_at.value),
        code_revision=current_git_revision(),
        config_hash=config_hash(args),
    )
    before = read_snapshot_if_present(args.snapshot_output)
    dividend = refresh_dividend_t_from_composite(
        watchlist_path=args.watchlist,
        frames=frames_for_accepted_symbols(merged, prepared.accepted_symbols),
        quotes=acquisition.quotes,
        before_snapshot=before,
        generated_at=retrieved_at.value,
    )
    write_dividend_trend_snapshot(dividend.snapshot, output_path=args.snapshot_output)
    write_tencent_composite_run_from_results(args.output_root, acquisition, merged, prepared, candidate, dividend)
    return 0
```

Catch `TencentCompositeQualityGateError` only at `main`, write a failed quality artifact, print its path to stderr, and return exit code `2`. Unexpected defects propagate with a traceback during development.

- [ ] **Step 4: Export intended public APIs and add new research files to mypy scope**

Add only stable contracts, acquisition, quality, runner, and artifact entry points to `research/__init__.py`. Add every new `src/market_regime_alpha/research/tencent_composite_*.py` file to `[tool.mypy].files`; do not broaden or suppress unrelated mypy errors.

- [ ] **Step 5: Run focused pre-live validation**

Run:

```bash
python3 -m pytest tests/research/test_tencent_composite_contracts.py tests/research/test_tencent_composite_merge.py tests/research/test_tencent_composite_quality.py tests/research/test_tencent_composite_acquisition.py tests/research/test_tencent_composite_materialization.py tests/research/test_tencent_composite_runner.py tests/research/test_tencent_composite_artifacts.py tests/research/test_tencent_composite_dividend_t.py tests/research/test_tencent_composite_cli.py -v
python3 -m ruff check src/market_regime_alpha/research src/market_regime_alpha/features/rehearsal_baselines.py scripts/run_tencent_composite_exploratory.py tests/research
python3 -m mypy
```

Expected: all new focused tests pass; Ruff passes for affected files; mypy has no errors in new Tencent composite files. Record any unrelated pre-existing result separately.

- [ ] **Step 6: Commit the executable path before live-source operation**

```bash
git add scripts/run_tencent_composite_exploratory.py tests/research/test_tencent_composite_cli.py src/market_regime_alpha/research/__init__.py pyproject.toml
git commit -m "feat: add Tencent composite exploratory runner"
```

- [ ] **Step 7: Run a one-symbol live Tencent smoke test**

Run:

```bash
python3 -c 'from market_regime_alpha.data_sources.tencent_minute_cache import fetch_tencent_1min_frame; frame = fetch_tencent_1min_frame("601919.SH", timeout_seconds=8.0); assert len(frame) > 0; print(frame[["symbol", "timestamp", "close"]].tail(1).to_string(index=False))'
```

Expected: exit code `0`, positive fetched row count, an aware/latest market timestamp, and no parser/schema exception. If the market is closed, retained rows from the latest session are valid smoke evidence; report their session date.

- [ ] **Step 8: Execute the full 20-symbol, 60-date exploratory run**

Run:

```bash
python3 scripts/run_tencent_composite_exploratory.py \
  --watchlist data/external/watchlists/dividend_t_watchlist.csv \
  --decision-count 60 \
  --warmup-sessions 21 \
  --minimum-accepted-symbols 16 \
  --snapshot-output docs/data/dividend_trends.json
```

Expected success criteria:

```text
accepted symbols >= 16
common complete sessions >= 82
evaluated Decision Dates = 60
Target families = Close Return / MFE / MAE
B0 controls per Target = 4
B1 ladder members per Target = 5
data eligibility = EXPLORATORY
dividend_t rows = 20 with accepted/rejected status visible
```

If the command returns `2`, inspect `quality.json`, repair only deterministic acquisition/parser/merge defects, add a regression test, rerun the smallest failing test, and commit the bounded fix. Do not relax the 16/20 or 82-session gates merely to obtain a passing run.

- [ ] **Step 9: Run broader affected and full repository checks**

Run:

```bash
python3 -m pytest tests/research tests/candidates tests/test_a_share_bars.py tests/test_tencent_minute_cache.py tests/test_dividend_trend_snapshot.py tests/legacy/test_trend_snapshot_characterization.py
python3 -m pytest
python3 -m ruff check .
python3 -m mypy
git diff --check
```

Expected: affected-area tests pass. For full commands, preserve the exact result; repair new regressions and report unrelated pre-existing failures without claiming a full pass.

- [ ] **Step 10: Update current status with actual evidence and commit outputs intentionally**

Update `docs/research/R5-Current-Status.md` with:

```text
Tencent composite exploratory auxiliary path        IMPLEMENTED
First 20-symbol live acquisition                    actual accepted/rejected counts
60-date B0/B1 exploratory run                       actual run ID or NOT AVAILABLE
Canonical provider authority                        unchanged; Xuntou remains primary
Data eligibility                                    EXPLORATORY
Test / Ruff / mypy status                           exact commands and results
```

Commit code/status separately from generated dashboard data when both changed:

```bash
git add docs/research/R5-Current-Status.md
git commit -m "docs: record Tencent exploratory run status"

git add docs/data/dividend_trends.json
git commit -m "data: refresh dividend trend snapshot from Tencent composite"
```

Do not commit large raw caches or processed run directories unless the repository's existing tracking policy explicitly includes them.

---

## Final Review Checklist

- [ ] Every requested symbol has an accepted or rejected disposition.
- [ ] Every partition has provider/product, retrieval time, locator, and normalized SHA-256.
- [ ] Source conflicts remain in `source_conflicts.json`.
- [ ] No code path can label the composite Dataset `REHEARSAL` or `FORMAL_RESEARCH`.
- [ ] Historical timestamps are not represented as proven provider `available_at`.
- [ ] Candidate Population limitations include `CURRENT_WATCHLIST_BACKFILL_BIAS`.
- [ ] Decision references use only source timestamps no later than 14:50.
- [ ] The evaluated panel has exactly 60 chronological completed Decision Dates.
- [ ] B0/B1 use existing score semantics and no final weight selection is claimed.
- [ ] Candidate rank and `dividend_t` action remain separate outputs.
- [ ] The actual live-source, focused, affected, and full-check results are reported separately.
- [ ] Working tree is clean, or every remaining path and reason is explained.
