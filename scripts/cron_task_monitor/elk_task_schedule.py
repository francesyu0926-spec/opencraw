from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .models import MonitorConfig, TaskDefinition


def _parse_hhmm(value: str) -> time:
    hour, minute = (int(x) for x in value.strip().split(":", 1))
    return time(hour, minute)


def _combine(day: datetime, hhmm: str, tz: ZoneInfo) -> datetime:
    t = _parse_hhmm(hhmm)
    return datetime.combine(day.date(), t, tzinfo=tz)


def _in_hhmm_window(now: datetime, start_hhmm: str, end_hhmm: str) -> bool:
    start_t = _parse_hhmm(start_hhmm)
    end_t = _parse_hhmm(end_hhmm)
    t = now.time().replace(second=0, microsecond=0)
    if start_t <= end_t:
        return start_t <= t <= end_t
    return t >= start_t or t <= end_t


def _task_expected_end_dt(
    cfg: MonitorConfig, task: TaskDefinition, now: datetime
) -> tuple[datetime, datetime]:
    """计划开始、预期结束（当日；结束早于开始则 +1 天）。"""
    tz = ZoneInfo(cfg.timezone)
    start = _combine(now, task.scheduled_start, tz)
    end = _combine(now, task.expected_end, tz)
    if end <= start:
        end += timedelta(days=1)
    return start, end


def task_plan_end(
    cfg: MonitorConfig, task: TaskDefinition, now: datetime
) -> datetime:
    """子任务计划结束时刻（不含 overrun 宽限期）。"""
    _, end = _task_expected_end_dt(cfg, task, now)
    return end


def task_monitor_window(
    cfg: MonitorConfig,
    task: TaskDefinition,
    now: datetime,
) -> tuple[datetime, datetime]:
    """单任务监控窗口：[计划开始, 预期结束 + overrun]（当日，跨日结束自动 +1 天）。"""
    start, end = _task_expected_end_dt(cfg, task, now)
    monitor_end = end + timedelta(minutes=cfg.overrun_after_end_threshold_minutes)
    return start, monitor_end


def is_task_in_monitor_window(
    cfg: MonitorConfig,
    task: TaskDefinition,
    now: datetime,
) -> bool:
    if not _in_hhmm_window(now, cfg.batch_window_start, cfg.batch_window_end):
        return False
    start, monitor_end = task_monitor_window(cfg, task, now)
    return start <= now <= monitor_end


def active_elk_task_ids(cfg: MonitorConfig, now: datetime) -> list[str]:
    """当前时刻应纳入 ELK 巡检的任务 ID（按各任务计划时间，非整表 15 分钟）。"""
    return [
        task.id
        for task in cfg.tasks
        if is_task_in_monitor_window(cfg, task, now)
    ]


def elk_task_ids_in_evaluation_scope(
    cfg: MonitorConfig, task_ids: list[str], now: datetime
) -> list[str]:
    """未过预计结束时间的进行中任务不在评估范围内。"""
    by_id = {t.id: t for t in cfg.tasks}
    scoped: list[str] = []
    for tid in task_ids:
        task = by_id.get(tid)
        if task is None:
            scoped.append(tid)
            continue
        if now > task_plan_end(cfg, task, now):
            scoped.append(tid)
    return scoped


def is_elk_job_due(
    now: datetime,
    *,
    cron_cfg: MonitorConfig,
    dispatcher_interval_minutes: int,
    job_interval_minutes: int | None = None,
    job_enabled: bool = True,
) -> bool:
    """ELK job：batch 窗内有子任务在监控窗内，并按 job 间隔（默认 15 分钟）对齐。"""
    if not job_enabled:
        return False
    in_window = active_elk_task_ids(cron_cfg, now)
    if not in_window:
        return False
    if not elk_task_ids_in_evaluation_scope(cron_cfg, in_window, now):
        return False
    interval = max(
        1,
        job_interval_minutes
        if job_interval_minutes is not None
        else cron_cfg.schedule_interval_minutes or 15,
    )
    dispatcher = max(1, dispatcher_interval_minutes)
    minute_of_day = now.hour * 60 + now.minute
    remainder = minute_of_day % interval
    if remainder == 0:
        return True
    if remainder > dispatcher:
        return False
    return now.minute % dispatcher == 0
