from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VISUAL_SCRIPT = PROJECT_ROOT / "backtesting" / "build_ma_crossover_visual.py"


def load_visual_module():
    spec = importlib.util.spec_from_file_location("build_ma_crossover_visual", VISUAL_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {VISUAL_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VisualizationTests(unittest.TestCase):
    def test_visual_payload_matches_sample_data(self) -> None:
        module = load_visual_module()
        bars = module.load_ohlcv_csv(PROJECT_ROOT / "data" / "raw" / "sample_etf_ohlcv.csv", symbol="SAMPLE_ETF")
        result = module.run_moving_average_crossover(bars, fast_window=3, slow_window=8)

        payload = module.build_visual_payload(
            bars,
            result,
            data_path=PROJECT_ROOT / "data" / "raw" / "sample_etf_ohlcv.csv",
        )

        self.assertEqual(payload["meta"]["symbol"], "SAMPLE_ETF")
        self.assertEqual(len(payload["points"]), 40)
        self.assertEqual(payload["points"][0]["close"], 100.0)
        self.assertIn("total_return", payload["metrics"])

    def test_html_embeds_chart_data_and_svg_targets(self) -> None:
        module = load_visual_module()
        payload = {
            "meta": {
                "title": "ETF 均线交叉可视化",
                "subtitle": "价格、均线、交易信号和权益曲线",
                "symbol": "SAMPLE_ETF",
                "data_path": "sample.csv",
                "start": "2026-01-02",
                "end": "2026-01-05",
                "rows": 2,
                "fast_window": 3,
                "slow_window": 8,
            },
            "metrics": {
                "initial_cash": 10000.0,
                "final_equity": 10000.0,
                "total_return": 0.0,
                "annualized_return": 0.0,
                "max_drawdown": 0.0,
                "sharpe": None,
                "trade_events": 0,
                "completed_trades": 0,
                "win_rate": None,
            },
            "points": [
                {"date": "2026-01-02", "close": 100.0, "fast_ma": None, "slow_ma": None, "signal": 0, "equity": 10000.0},
                {"date": "2026-01-05", "close": 101.0, "fast_ma": None, "slow_ma": None, "signal": 0, "equity": 10000.0},
            ],
        }

        html = module.build_html(payload)
        embedded = html.split('<script id="chart-data" type="application/json">', 1)[1].split("</script>", 1)[0]

        self.assertIn('id="priceChart"', html)
        self.assertIn('id="equityChart"', html)
        self.assertEqual(json.loads(embedded)["meta"]["symbol"], "SAMPLE_ETF")


if __name__ == "__main__":
    unittest.main()

