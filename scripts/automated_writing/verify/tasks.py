from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")


class ApiType(str, Enum):
    SMART = "smart"
    SHARE = "share"


@dataclass(frozen=True)
class Task:
    name: str
    check_time: time
    api: ApiType
    key: str | None = None
    share_type: int | None = None
    weekdays_only: bool = True


TASKS: tuple[Task, ...] = (
    Task("盘前情报", time(7, 30), ApiType.SMART, key="丨盘前情报"),
    Task("A股避雷针", time(7, 40), ApiType.SMART, key="丨A股公告避雷针"),
    Task("早报推送", time(7, 55), ApiType.SHARE, share_type=1),
    Task("港股早报", time(8, 35), ApiType.SMART, key="丨港股早报"),
    Task("盘前线索", time(9, 5), ApiType.SMART, key="丨盘前线索"),
    Task("公告精选", time(19, 30), ApiType.SMART, key="丨公告精选"),
    Task("港股公告精选", time(20, 0), ApiType.SMART, key="丨港股公告精选"),
)


DEFAULT_EXECUTION_DELAY_MINUTES = 10
DEFAULT_EXECUTION_SLOT_MINUTES = 5


def now() -> datetime:
    override = os.environ.get("WRITING_MONITOR_AT", "").strip()
    if override:
        dt = datetime.fromisoformat(override.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=TZ)
        return dt.astimezone(TZ)
    return datetime.now(TZ)


def today_str() -> str:
    return now().strftime("%Y-%m-%d")


def is_workday(dt: datetime | None = None) -> bool:
    dt = dt or now()
    return dt.weekday() < 5


def should_run_task(task: Task, dt: datetime | None = None) -> bool:
    dt = dt or now()
    if task.weekdays_only and not is_workday(dt):
        return False
    return True


def is_due(task: Task, dt: datetime | None = None) -> bool:
    dt = dt or now()
    if not should_run_task(task, dt):
        return False
    check_dt = datetime.combine(dt.date(), task.check_time, tzinfo=TZ)
    return dt >= check_dt


def task_execution_slot(
    task: Task,
    dt: datetime | None = None,
    *,
    delay_minutes: int = DEFAULT_EXECUTION_DELAY_MINUTES,
    slot_minutes: int = DEFAULT_EXECUTION_SLOT_MINUTES,
    active_end: time | None = None,
) -> tuple[datetime, datetime] | None:
    """单次执行时段：[到点+delay, 到点+delay+slot)。非适用日或超出 active_end 返回 None。"""
    dt = dt or now()
    if not should_run_task(task, dt):
        return None
    start = datetime.combine(dt.date(), task.check_time, tzinfo=TZ) + timedelta(
        minutes=max(0, delay_minutes)
    )
    if active_end is not None and start.time() > active_end:
        return None
    end = start + timedelta(minutes=max(1, slot_minutes))
    if active_end is not None:
        cap = datetime.combine(dt.date(), active_end, tzinfo=TZ)
        if end > cap:
            end = cap
    if end <= start:
        return None
    return start, end


def _execution_params_from_env() -> tuple[int, int, time | None]:
    delay = int(
        os.environ.get(
            "WRITING_EXECUTION_DELAY_MINUTES", DEFAULT_EXECUTION_DELAY_MINUTES
        )
    )
    slot = int(
        os.environ.get(
            "WRITING_EXECUTION_SLOT_MINUTES", DEFAULT_EXECUTION_SLOT_MINUTES
        )
    )
    ae_raw = os.environ.get("WRITING_ACTIVE_END", "20:30").strip()
    active_end = _parse_hhmm(ae_raw) if ae_raw else None
    return delay, slot, active_end


def _parse_hhmm(value: str) -> time:
    hour, minute = (int(x) for x in value.strip().split(":", 1))
    return time(hour, minute)


def is_in_execution_slot(
    task: Task,
    dt: datetime | None = None,
    *,
    delay_minutes: int | None = None,
    slot_minutes: int | None = None,
    active_end: time | None = None,
) -> bool:
    """到点后 delay 分钟起，在单个 slot 内且命中 slot_minutes 墙钟对齐时执行一次。"""
    env_delay, env_slot, env_end = _execution_params_from_env()
    delay_minutes = env_delay if delay_minutes is None else delay_minutes
    slot_minutes = env_slot if slot_minutes is None else slot_minutes
    if active_end is None and os.environ.get("WRITING_ACTIVE_END") is not None:
        active_end = env_end
    elif active_end is None:
        active_end = env_end
    slot = task_execution_slot(
        task,
        dt,
        delay_minutes=delay_minutes,
        slot_minutes=slot_minutes,
        active_end=active_end,
    )
    if slot is None:
        return False
    start, end = slot
    ref = dt or now()
    if ref < start or ref >= end:
        return False
    align = max(1, slot_minutes)
    return ref.minute % align == 0


# 兼容旧名
def is_in_monitor_window(
    task: Task,
    dt: datetime | None = None,
    *,
    grace_minutes: int = DEFAULT_EXECUTION_DELAY_MINUTES,
    active_end: time | None = None,
) -> bool:
    return is_in_execution_slot(
        task,
        dt,
        delay_minutes=grace_minutes,
        slot_minutes=DEFAULT_EXECUTION_SLOT_MINUTES,
        active_end=active_end,
    )


def pending_message(task: Task) -> str:
    return f"未到监测时间（监测时间 {task.check_time.strftime('%H:%M')}）"


def get_task(name: str) -> Task:
    for task in TASKS:
        if task.name == name:
            return task
    raise KeyError(f"未知任务: {name}")
