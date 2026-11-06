from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.cron_task_monitor.daily_boundary import daily_boundary_kind
from scripts.cron_task_monitor.schedule_config import load_monitor_schedule


def test_production_ws_first_last_slots() -> None:
    cfg = load_monitor_schedule("config/monitor_schedule.production.yaml")
    tz = ZoneInfo("Asia/Shanghai")
    ws = cfg.jobs["ws"]
    assert daily_boundary_kind(datetime(2026, 11, 6, 9, 0, tzinfo=tz), ws) == "first"
    assert daily_boundary_kind(datetime(2026, 11, 6, 15, 30, tzinfo=tz), ws) == "last"
    assert daily_boundary_kind(datetime(2026, 11, 6, 15, 20, tzinfo=tz), ws) is None
    assert daily_boundary_kind(datetime(2026, 11, 6, 16, 0, tzinfo=tz), ws) is None


def test_production_health_first_last_slots() -> None:
    cfg = load_monitor_schedule("config/monitor_schedule.production.yaml")
    tz = ZoneInfo("Asia/Shanghai")
    health = cfg.jobs["health"]
    assert daily_boundary_kind(datetime(2026, 11, 6, 9, 0, tzinfo=tz), health) == "first"
    assert daily_boundary_kind(datetime(2026, 11, 6, 23, 30, tzinfo=tz), health) == "last"
    assert daily_boundary_kind(datetime(2026, 11, 6, 23, 45, tzinfo=tz), health) is None
