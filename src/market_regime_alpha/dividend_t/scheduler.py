"""Scheduler factory for daily data sync and signal generation jobs."""

from __future__ import annotations

from collections.abc import Callable


def build_background_scheduler(
    *,
    daily_sync_job: Callable[[], None] | None = None,
    signal_job: Callable[[], None] | None = None,
):
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError as exc:
        raise RuntimeError("Install APScheduler to enable scheduled jobs.") from exc

    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    if daily_sync_job is not None:
        scheduler.add_job(daily_sync_job, "cron", hour=17, minute=30, id="dividend_t_daily_sync", replace_existing=True)
    if signal_job is not None:
        scheduler.add_job(signal_job, "cron", hour=8, minute=50, id="dividend_t_premarket_signal", replace_existing=True)
    return scheduler
