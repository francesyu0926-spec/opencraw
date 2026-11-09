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


def is_task_elk_schedulable(
    cfg: MonitorConfig,
    task: TaskDefinition,
    now: datetime,
    *,
    follow_up_minutes: int = 0,
) -> bool:
    """计划开始～监控结束；结束后另保留 follow_up 分钟以便收尾评估、发企微。"""
    if not _in_hhmm_window(now, cfg.batch_window_start, cfg.batch_window_end):
        return False
    start, monitor_end = task_monitor_window(cfg, task, now)
    sched_end = monitor_end + timedelta(minutes=max(0, follow_up_minutes))
    return start <= now <= sched_end


def active_elk_task_ids(
    cfg: MonitorConfig, now: datetime, *, follow_up_minutes: int = 0
) -> list[str]:
    """当前时刻应触发 ELK 的任务 ID（含监控窗结束后的 follow_up 收尾轮）。"""
    follow = max(0, follow_up_minutes)
    return [
        task.id
        for task in cfg.tasks
        if is_task_elk_schedulable(cfg, task, now, follow_up_minutes=follow)
    ]


def elk_follow_up_minutes(
    cfg: MonitorConfig,
    job_interval_minutes: int,
    dispatcher_interval_minutes: int = 5,
) -> int:
    """
    监控硬截止后的收尾窗：至少覆盖 overrun 宽限，并保留 ≥1 次巡检周期。
    告警：未迟到 +6min、超时 +11min → 5 分钟巡检可在宽限内多次轮询。
    """
    interval = max(1, job_interval_minutes)
    dispatcher = max(1, dispatcher_interval_minutes)
    overrun = max(0, cfg.overrun_after_end_threshold_minutes)
    return max(interval, overrun + dispatcher)


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


def elk_task_ids_in_monitoring_scope(
    cfg: MonitorConfig,
    task_ids: list[str],
    now: datetime,
    *,
    follow_up_minutes: int = 0,
) -> list[str]:
    """可输出结论的窗：计划开始 ~ 监控结束 + follow_up（与 ELK 调度收尾窗一致）。"""
    by_id = {t.id: t for t in cfg.tasks}
    follow = max(0, follow_up_minutes)
    scoped: list[str] = []
    for tid in task_ids:
        task = by_id.get(tid)
        if task is None:
            scoped.append(tid)
            continue
        start, monitor_end = task_monitor_window(cfg, task, now)
        sched_end = monitor_end + timedelta(minutes=follow)
        if start <= now <= sched_end:
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
    """ELK job：batch 窗内有子任务可调度，并按 job 间隔（默认 5 分钟）对齐。"""
    if not job_enabled:
        return False
    dispatcher = max(1, dispatcher_interval_minutes)
    interval = max(
        1,
        job_interval_minutes
        if job_interval_minutes is not None
        else cron_cfg.schedule_interval_minutes or 5,
    )
    follow_up = elk_follow_up_minutes(cron_cfg, interval, dispatcher)
    in_window = active_elk_task_ids(cron_cfg, now, follow_up_minutes=follow_up)
    if not in_window:
        return False
    minute_of_day = now.hour * 60 + now.minute
    remainder = minute_of_day % interval
    if remainder == 0:
        return True
    if remainder > dispatcher:
        return False
    return now.minute % dispatcher == 0
