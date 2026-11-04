from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
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


def now() -> datetime:
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


def pending_message(task: Task) -> str:
    return f"未到监测时间（监测时间 {task.check_time.strftime('%H:%M')}）"


def get_task(name: str) -> Task:
    for task in TASKS:
        if task.name == name:
            return task
    raise KeyError(f"未知任务: {name}")
