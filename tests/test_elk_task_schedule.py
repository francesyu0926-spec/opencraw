from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.cron_task_monitor.config_loader import load_config
from scripts.cron_task_monitor.elk_task_schedule import (
    active_elk_task_ids,
    elk_follow_up_minutes,
    elk_task_ids_in_evaluation_scope,
    is_elk_job_due,
    is_task_in_monitor_window,
    task_monitor_window,
)

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "cron_tasks.yaml")
TZ = ZoneInfo("Asia/Shanghai")


def _at(h: int, m: int) -> datetime:
    return datetime(2026, 11, 6, h, m, tzinfo=TZ)


def test_pub_boar_in_window_at_0105() -> None:
    task = next(t for t in CFG.tasks if t.id == "CBD_PUB_BOAR_INFO")
    assert is_task_in_monitor_window(CFG, task, _at(1, 5))


def test_pub_boar_out_before_start() -> None:
    task = next(t for t in CFG.tasks if t.id == "CBD_PUB_BOAR_INFO")
    assert not is_task_in_monitor_window(CFG, task, _at(0, 55))


def test_trading_day_window_until_0415() -> None:
    task = next(t for t in CFG.tasks if t.id == "CBD_TRD_DT_RECNT_2")
    start, end = task_monitor_window(CFG, task, _at(4, 0))
    assert start.hour == 4 and start.minute == 0
    assert end.hour == 4 and end.minute == 16
    assert is_task_in_monitor_window(CFG, task, _at(4, 10))
    assert not is_task_in_monitor_window(CFG, task, _at(2, 0))


def test_active_ids_at_0110_includes_multiple() -> None:
    ids = active_elk_task_ids(CFG, _at(1, 10))
    assert "CBD_PUB_BOAR_INFO" in ids
    assert "NC_LISTSTOCK_GLANCE" in ids
    assert "CBD_TRD_DT_RECNT_2" not in ids
    assert "NC_TQ_SK_XDRY_2" not in ids


def test_follow_up_window_at_0220_schedules_dict_task() -> None:
    """监控窗结束后 follow_up 内仍触发 ELK（便于收尾企微）。"""
    follow = elk_follow_up_minutes(CFG, 5, 5)
    assert follow == 16
    kwargs = dict(cron_cfg=CFG, dispatcher_interval_minutes=5, job_interval_minutes=5)
    assert is_elk_job_due(_at(2, 20), **kwargs)
    window = active_elk_task_ids(CFG, _at(2, 20), follow_up_minutes=follow)
    assert "CBD_SECURITY_DICT_2" in window


def test_no_evaluation_scope_at_0200_boundary() -> None:
    window = active_elk_task_ids(CFG, _at(2, 0))
    scoped = elk_task_ids_in_evaluation_scope(CFG, window, _at(2, 0))
    assert "NC_LISTSTOCK_GLANCE" not in scoped
    assert scoped == []


def test_elk_job_not_due_at_noon() -> None:
    assert not is_elk_job_due(_at(12, 0), cron_cfg=CFG, dispatcher_interval_minutes=5)


def test_evaluation_scope_excludes_before_plan_end() -> None:
    window = active_elk_task_ids(CFG, _at(1, 5))
    assert "NC_LISTSTOCK_GLANCE" in window
    scoped = elk_task_ids_in_evaluation_scope(CFG, window, _at(1, 5))
    assert "NC_LISTSTOCK_GLANCE" not in scoped
    assert "CBD_PUB_BOAR_INFO" in scoped


def test_elk_job_due_on_5min_tick() -> None:
    kwargs = dict(cron_cfg=CFG, dispatcher_interval_minutes=5, job_interval_minutes=5)
    assert is_elk_job_due(_at(1, 0), **kwargs)
    assert is_elk_job_due(_at(1, 5), **kwargs)
    assert is_elk_job_due(_at(1, 10), **kwargs)
    assert is_elk_job_due(_at(1, 15), **kwargs)
