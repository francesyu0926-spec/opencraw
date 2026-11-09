from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Shanghai")


def _at(iso: str) -> datetime:
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ)


def _env_writing_defaults(monkeypatch) -> None:
    monkeypatch.setenv("WRITING_EXECUTION_DELAY_MINUTES", "10")
    monkeypatch.setenv("WRITING_EXECUTION_SLOT_MINUTES", "5")
    monkeypatch.setenv("WRITING_ACTIVE_END", "20:30")


def test_writing_job_not_due_before_execution_minute(monkeypatch) -> None:
    _env_writing_defaults(monkeypatch)
    monkeypatch.setenv("WRITING_MONITOR_AT", "2026-11-06T07:35:00+08:00")
    from scripts.cron_task_monitor.writing_task_schedule import (
        active_writing_task_names,
        is_writing_job_due,
    )

    cfg = ROOT / "config" / "writing_monitor.yaml"
    now = _at("2026-11-06T07:35:00+08:00")
    assert active_writing_task_names(now, config_path=cfg, repo_root=ROOT) == []
    assert not is_writing_job_due(
        now,
        config_path=cfg,
        repo_root=ROOT,
        dispatcher_interval_minutes=5,
    )


def test_writing_job_runs_once_at_check_plus_10(monkeypatch) -> None:
    _env_writing_defaults(monkeypatch)
    monkeypatch.setenv("WRITING_MONITOR_AT", "2026-11-06T07:40:00+08:00")
    from scripts.cron_task_monitor.writing_task_schedule import (
        active_writing_task_names,
        is_writing_job_due,
    )

    cfg = ROOT / "config" / "writing_monitor.yaml"
    now = _at("2026-11-06T07:40:00+08:00")
    names = active_writing_task_names(now, config_path=cfg, repo_root=ROOT)
    assert names == ["盘前情报"]
    assert is_writing_job_due(
        now,
        config_path=cfg,
        repo_root=ROOT,
        dispatcher_interval_minutes=5,
    )


def test_not_repeat_at_0745_same_task(monkeypatch) -> None:
    _env_writing_defaults(monkeypatch)
    monkeypatch.setenv("WRITING_MONITOR_AT", "2026-11-06T07:45:00+08:00")
    from scripts.cron_task_monitor.writing_task_schedule import active_writing_task_names

    cfg = ROOT / "config" / "writing_monitor.yaml"
    assert active_writing_task_names(
        _at("2026-11-06T07:45:00+08:00"), config_path=cfg, repo_root=ROOT
    ) == []


def test_hk_notice_executes_at_2010(monkeypatch) -> None:
    import sys

    _env_writing_defaults(monkeypatch)
    sys.path.insert(0, str(ROOT / "scripts" / "automated_writing"))
    monkeypatch.setenv("WRITING_MONITOR_AT", "2026-11-06T20:10:00+08:00")
    from verify.tasks import get_task, is_in_execution_slot

    task = get_task("港股公告精选")
    assert is_in_execution_slot(task, _at("2026-11-06T20:10:00+08:00"))
    assert not is_in_execution_slot(task, _at("2026-11-06T20:15:00+08:00"))
