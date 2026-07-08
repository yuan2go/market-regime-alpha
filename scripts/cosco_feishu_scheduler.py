from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_SCRIPT = PROJECT_ROOT / "scripts" / "cosco_timing_report.py"
RUN_TIMES = (
    (9, 35),
    (10, 5),
    (10, 35),
    (11, 5),
    (13, 5),
    (13, 35),
    (14, 5),
    (14, 35),
    (15, 5),
)


def main() -> None:
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError as exc:
        raise SystemExit("Install APScheduler with `pip install -r requirements.txt`.") from exc

    scheduler = BlockingScheduler(timezone="Asia/Shanghai")
    for hour, minute in RUN_TIMES:
        scheduler.add_job(
            send_report,
            "cron",
            day_of_week="mon-fri",
            hour=hour,
            minute=minute,
            second=0,
            id=f"cosco_feishu_{hour:02d}_{minute:02d}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    print("中远海控飞书调度器已启动。")
    print("发送时间：09:35, 10:05, 10:35, 11:05, 13:05, 13:35, 14:05, 14:35, 15:05")
    print("推送通道：飞书机器人。停止调度器请按 Ctrl+C 或结束对应 tmux 会话。")
    scheduler.start()


def send_report() -> None:
    command = [
        sys.executable,
        str(REPORT_SCRIPT),
        "--provider",
        "fast",
        "--no-persist",
        "--push",
        "--notify-channel",
        "feishu",
    ]
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{started_at}] running {' '.join(command)}", flush=True)
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env=None,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        print(f"report command timed out after {exc.timeout} seconds", file=sys.stderr, flush=True)
        if exc.stdout:
            print(exc.stdout, flush=True)
        if exc.stderr:
            print(exc.stderr, file=sys.stderr, flush=True)
        return
    if completed.stdout:
        print(completed.stdout, flush=True)
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, flush=True)
    if completed.returncode != 0:
        print(f"report command failed with exit code {completed.returncode}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
