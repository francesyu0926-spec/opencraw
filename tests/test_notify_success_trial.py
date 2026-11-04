from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.cron_task_monitor.schedule_config import (
    NotifySuccessTrial,
    is_on_hour_tick,
    load_monitor_schedule,
    notify_success_trial_active,
)


def test_production_yaml_has_trial_until_nov_11() -> None:
    cfg = load_monitor_schedule("config/monitor_schedule.production.yaml")
    assert cfg.notify_success_trial is not None
    assert cfg.notify_success_trial.enabled
    assert cfg.notify_success_trial.on_hour_only
    assert cfg.notify_success_trial.until == "2026-11-11"


def test_trial_active_on_hour_before_until() -> None:
    trial = NotifySuccessTrial(enabled=True, on_hour_only=True, until="2026-11-11")
    tz = ZoneInfo("Asia/Shanghai")
    assert notify_success_trial_active(
        datetime(2026, 11, 4, 10, 0, tzinfo=tz), trial
    )
    assert not notify_success_trial_active(
        datetime(2026, 11, 4, 10, 5, tzinfo=tz), trial
    )


def test_on_hour_tick_grace_before_hour() -> None:
    tz = ZoneInfo("Asia/Shanghai")
    assert is_on_hour_tick(datetime(2026, 11, 4, 17, 59, 30, tzinfo=tz))
    assert is_on_hour_tick(datetime(2026, 11, 4, 18, 0, 0, tzinfo=tz))
    assert not is_on_hour_tick(datetime(2026, 11, 4, 17, 58, 0, tzinfo=tz))


def test_trial_inactive_after_until() -> None:
    trial = NotifySuccessTrial(enabled=True, on_hour_only=True, until="2026-11-11")
    tz = ZoneInfo("Asia/Shanghai")
    assert not notify_success_trial_active(
        datetime(2026, 11, 12, 9, 0, tzinfo=tz), trial
    )
