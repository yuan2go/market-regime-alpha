from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from market_regime_alpha.dividend_t.cosco_timing import get_cosco_timing_from_free_sources
from market_regime_alpha.notifications import send_notifications


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POSITION_FILE = PROJECT_ROOT / "data" / "local" / "portfolio" / "positions.json"
ACTION_LABELS = {
    "BUY_T_TIMING": "买点",
    "SELL_T_TIMING": "卖点",
    "STOP_T_WAIT": "风险卖点，等待",
    "WAIT_STALE_DATA": "数据过期，等待",
    "WAIT_DAILY_WEAK": "日线偏弱，等待",
    "WAIT_CONFIRMATION": "等待分时确认",
    "WAIT_LATE_SESSION": "尾盘等待",
    "WAIT_STRONG_TREND": "强趋势保护，暂不卖出",
    "WAIT": "等待",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a COSCO Shipping Holdings timing report.")
    parser.add_argument(
        "--provider",
        default="fast",
        help="fast, auto, strict, tencent-direct, eastmoney-direct, tencent, eastmoney, akshare, baostock, yfinance, or tushare",
    )
    parser.add_argument("--no-persist", action="store_true", help="Do not write the latest snapshot to parquet.")
    parser.add_argument("--push", action="store_true", help="Send the report through configured notification channels.")
    parser.add_argument("--notify-channel", default="auto", help="auto, feishu, or a comma-separated channel list.")
    args = parser.parse_args()

    result = get_cosco_timing_from_free_sources(provider=args.provider, persist=not args.no_persist)
    data = result.to_dict()
    report = format_report(data)
    print(report)
    if args.push:
        print()
        print("推送结果：")
        for item in send_notifications(report, channels=args.notify_channel):
            status = "成功" if item.success else "失败"
            print(f"- {item.channel}：{status}，{item.message}")


def format_report(data: dict[str, Any]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if data.get("status") == "data_unavailable":
        attempts = _format_attempts(data.get("data_attempts") or [])
        steps = "\n".join(f"- {item}" for item in data.get("required_user_steps") or [])
        return (
            f"中远海控买卖点识别提醒\n"
            f"生成时间：{now}\n"
            f"状态：数据不可用\n"
            f"原因：{data.get('message')}\n"
            f"数据源尝试：\n{attempts}\n"
            f"耗时：\n{_format_runtime_profile(data.get('runtime_profile') or [])}\n"
            f"需要处理：\n{steps}"
        )

    prices = data["prices"]
    force = data["force"]
    daily = data.get("daily_context") or {}
    intraday = data.get("intraday_context") or {}
    position = _load_position()
    pnl_line = _format_position(position, prices.get("current_price"))
    attempts = _format_attempts(data.get("data_attempts") or [])
    reasons = "\n".join(f"- {item}" for item in (data.get("reasons") or [])[:4])
    warnings = "\n".join(f"- {item}" for item in (data.get("warnings") or [])[:4]) or "- 无"

    return (
        f"中远海控买卖点识别提醒\n"
        f"生成时间：{data.get('generated_at') or now}\n"
        f"数据源：{data.get('data_source')}\n"
        f"K线时间：{data.get('timestamp')}，数据年龄：{data.get('data_age_minutes')} 分钟，"
        f"新鲜度：{data.get('freshness_status')}\n"
        f"动作：{_format_action(data.get('action'))}，置信分：{data.get('confidence')}，趋势：{data.get('trend_state')}\n"
        f"时间尺度：日线 {daily.get('state', '-')} / D {daily.get('score', '-')}，"
        f"盘中 {intraday.get('state', '-')} / I {intraday.get('score', '-')}，"
        f"仓位系数 {daily.get('position_multiplier', '-')}\n"
        f"价格：现价 {prices.get('current_price')}，支撑 {prices.get('support_price')}，"
        f"压力 {prices.get('resistance_price')}\n"
        f"参考：买入 {prices.get('buy_reference_price')}，卖出 {prices.get('sell_reference_price')}，"
        f"止损/失效 {prices.get('stop_price')}，回补 {prices.get('buy_back_reference_price')}\n"
        f"买卖力：force_ratio {force.get('force_ratio')}，买压 {force.get('buy_pressure')}，"
        f"卖压 {force.get('sell_pressure')}\n"
        f"评分：G {data['attention'].get('score')}，Z {data['certainty'].get('score')}，"
        f"记忆 {data['memory'].get('score')}，卖压 {data['sell_pressure'].get('score')}，"
        f"盈亏比 {data.get('risk_reward_ratio')}\n"
        f"{pnl_line}\n"
        f"理由：\n{reasons}\n"
        f"警告：\n{warnings}\n"
        f"数据源尝试：\n{attempts}\n"
        f"耗时：\n{_format_runtime_profile(data.get('runtime_profile') or [])}\n"
        f"说明：仅作为手动操作参考，不自动下单。"
    )


def _load_position() -> dict[str, Any] | None:
    if not POSITION_FILE.exists():
        return None
    try:
        payload = json.loads(POSITION_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    positions = payload.get("positions") if isinstance(payload, dict) else None
    if not isinstance(positions, list):
        return None
    for item in positions:
        if item.get("symbol") == "601919.SH":
            return item
    return None


def _format_position(position: dict[str, Any] | None, current_price: float | None) -> str:
    if not position or current_price is None:
        return "持仓：未读取到本地持仓记录。"
    shares = float(position.get("shares") or 0)
    cost = float(position.get("cost_price") or position.get("price") or 0)
    if shares <= 0 or cost <= 0:
        return "持仓：本地持仓记录不完整。"
    pnl = (float(current_price) - cost) * shares
    pnl_pct = (float(current_price) / cost - 1.0) * 100
    return f"持仓：{shares:.0f} 股，成本 {cost:.3f}，浮动盈亏 {pnl:.2f} 元，{pnl_pct:.2f}%"


def _format_action(action: object) -> str:
    action_code = str(action or "")
    if not action_code:
        return "-"
    label = ACTION_LABELS.get(action_code)
    return f"{label}（{action_code}）" if label else action_code


def _format_attempts(attempts: list[dict[str, Any]]) -> str:
    if not attempts:
        return "- 无"
    lines = []
    for item in attempts:
        status = "成功" if item.get("success") else "失败"
        if item.get("success"):
            detail = f"{item.get('rows')} 行"
        else:
            detail = item.get("message") or f"{item.get('rows')} 行"
        elapsed = item.get("elapsed_seconds")
        elapsed_text = f"，{elapsed} 秒" if isinstance(elapsed, (int, float)) else ""
        lines.append(f"- {item.get('provider')}：{status}，{detail}{elapsed_text}")
    return "\n".join(lines)


def _format_runtime_profile(profile: list[dict[str, Any]]) -> str:
    if not profile:
        return "- 无"
    lines = []
    for item in profile:
        step = item.get("step") or "-"
        elapsed = item.get("elapsed_seconds")
        rows = item.get("rows")
        provider = item.get("provider")
        detail = []
        if provider:
            detail.append(str(provider))
        if rows is not None:
            detail.append(f"{rows} 行")
        suffix = f"，{'，'.join(detail)}" if detail else ""
        lines.append(f"- {step}：{elapsed} 秒{suffix}")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
