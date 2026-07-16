from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import DatasetId
from market_regime_alpha.core.time import RetrievedAt
from market_regime_alpha.data.contracts import DataEligibility
from scripts import run_tencent_composite_exploratory as cli


TZ = ZoneInfo("Asia/Shanghai")


def _watchlist(root: Path) -> Path:
    path = root / "watchlist.csv"
    path.write_text(
        "symbol,name,industry,is_cycle_stock,notes\n"
        + "".join(
            f"{index + 1:06d}.SZ,测试{index + 1},银行,false,测试\n"
            for index in range(20)
        ),
        encoding="utf-8",
    )
    return path


def test_cli_runs_candidate_before_dividend_refresh_and_writes_outputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    events: list[str] = []
    retrieved_at = RetrievedAt(datetime(2026, 7, 16, 16, 0, tzinfo=TZ))
    acquisition = SimpleNamespace(
        retrieved_at=retrieved_at,
        partitions=(),
        quote_partition=None,
        attempts=(),
        quotes={},
    )

    class FakeAcquirer:
        def acquire(self, **_kwargs):
            return acquisition

    prepared = SimpleNamespace(
        accepted_symbols=("000001.SZ",),
        common_session_dates=tuple(range(82)),
        quality=SimpleNamespace(success=True),
    )
    contract = SimpleNamespace(
        dataset_id=DatasetId("dataset-test"),
        eligibility=DataEligibility.EXPLORATORY,
        limitations=("CURRENT_WATCHLIST_BACKFILL_BIAS",),
    )
    candidate = SimpleNamespace(decision_date_count=60)
    refresh = SimpleNamespace(snapshot={"schema_version": 2, "rows": []}, diff={})

    monkeypatch.setattr(cli, "build_default_acquirer", lambda **_kwargs: FakeAcquirer())
    monkeypatch.setattr(cli, "merge_acquisition", lambda _acquisition: SimpleNamespace(conflicts=()))
    monkeypatch.setattr(cli, "prepare_composite_data", lambda *_args, **_kwargs: prepared)
    monkeypatch.setattr(cli, "build_contract_from_acquisition", lambda *_args, **_kwargs: contract)
    monkeypatch.setattr(
        cli,
        "run_tencent_composite_candidate_experiment",
        lambda **_kwargs: events.append("candidate") or candidate,
    )
    monkeypatch.setattr(cli, "frames_for_accepted_symbols", lambda *_args, **_kwargs: {"000001.SZ": object()})
    monkeypatch.setattr(
        cli,
        "refresh_dividend_t_from_composite",
        lambda **_kwargs: events.append("dividend") or refresh,
    )
    monkeypatch.setattr(cli, "current_git_revision", lambda: "abc123")

    def fake_write_run(**kwargs):
        events.append("artifacts")
        output = Path(kwargs["root"]) / kwargs["run_id"]
        output.mkdir(parents=True)
        return output

    monkeypatch.setattr(cli, "write_tencent_composite_run", fake_write_run)
    snapshot = tmp_path / "snapshot.json"

    code = cli.main(
        [
            "--watchlist",
            str(_watchlist(tmp_path)),
            "--output-root",
            str(tmp_path / "runs"),
            "--snapshot-output",
            str(snapshot),
            "--retrieved-at",
            "2026-07-16T16:00:00+08:00",
        ]
    )

    assert code == 0
    assert events == ["candidate", "dividend", "artifacts"]
    assert snapshot.exists()
