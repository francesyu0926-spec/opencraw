from __future__ import annotations

import sys
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

DEFAULT_DELAY_MINUTES = 10
DEFAULT_SLOT_MINUTES = 5


def _parse_hhmm(value: str) -> time:
    hour, minute = (int(x) for x in value.strip().split(":", 1))
    return time(hour, minute)


def load_writing_schedule_settings(config_path: Path) -> tuple[int, int, time | None]:
    """从 writing_monitor.yaml 读取 delay / slot / active_end。"""
    delay = DEFAULT_DELAY_MINUTES
    slot = DEFAULT_SLOT_MINUTES
    active_end: time | None = time(20, 30)
    if not config_path.is_file():
        return delay, slot, active_end
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return delay, slot, active_end
    if data.get("execution_delay_minutes") is not None:
        delay = max(0, int(data["execution_delay_minutes"]))
    elif data.get("monitor_grace_minutes") is not None:
        delay = max(0, int(data["monitor_grace_minutes"]))
    if data.get("execution_slot_minutes") is not None:
        slot = max(1, int(data["execution_slot_minutes"]))
    end_raw = data.get("active_end")
    if end_raw:
        active_end = _parse_hhmm(str(end_raw))
    elif end_raw is None and "active_end" in data:
        active_end = None
    return delay, slot, active_end


def _ensure_verify_path(repo_root: Path) -> None:
    aw = repo_root / "scripts" / "automated_writing"
    aw_str = str(aw)
    if aw_str not in sys.path:
        sys.path.insert(0, aw_str)


def active_writing_task_names(
    now: datetime,
    *,
    config_path: Path,
    repo_root: Path,
) -> list[str]:
    _ensure_verify_path(repo_root)
    from verify.tasks import TASKS, is_in_execution_slot

    delay, slot, active_end = load_writing_schedule_settings(config_path)
    return [
        task.name
        for task in TASKS
        if is_in_execution_slot(
            task,
            now,
            delay_minutes=delay,
            slot_minutes=slot,
            active_end=active_end,
        )
    ]


def is_writing_job_due(
    now: datetime,
    *,
    config_path: Path,
    repo_root: Path,
    dispatcher_interval_minutes: int,
    job_enabled: bool = True,
) -> bool:
    if not job_enabled:
        return False
    if not active_writing_task_names(
        now, config_path=config_path, repo_root=repo_root
    ):
        return False
    dispatcher = max(1, dispatcher_interval_minutes)
    minute_of_day = now.hour * 60 + now.minute
    remainder = minute_of_day % dispatcher
    if remainder == 0:
        return True
    if remainder > dispatcher:
        return False
    return now.minute % dispatcher == 0
