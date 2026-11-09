from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .models import MonitorConfig, TaskDefinition


class CQuotesESError(Exception):
    """与 mdimonitor utils.CQuotesESError 一致，用于告警文案。"""


def resolve_task_id_for_cli(cfg: MonitorConfig, requested: str) -> str | None:
    """将 --task 参数映射为 cron_tasks.yaml 中的 id（兼容误写的 _2 后缀）。"""
    needle = requested.strip()
    if not needle:
        return None
    by_id = {t.id: t for t in cfg.tasks}
    if needle in by_id:
        return needle
    for task in cfg.tasks:
        if needle == task.name:
            return task.id
    if needle.endswith("_2"):
        base = needle[:-2]
        if base in by_id:
            return base
    if f"{needle}_2" in by_id:
        return f"{needle}_2"
    return None


def expand_cli_task_ids(cfg: MonitorConfig, requested: list[str] | None) -> set[str]:
    if not requested:
        return set()
    resolved: set[str] = set()
    for raw in requested:
        tid = resolve_task_id_for_cli(cfg, raw)
        if tid:
            resolved.add(tid)
    return resolved


def msg_keywords_from_config(cfg: MonitorConfig, task_ids: set[str] | None = None) -> list[str]:
    """对齐 data.Task：取任务常量名（id），过滤含 __ 的键在 YAML 中不会出现。"""
    keywords: list[str] = []
    for task in cfg.tasks:
        if task_ids and task.id not in task_ids:
            continue
        keywords.append(task.id)
    return keywords


def _find_task(cfg: MonitorConfig, task_name: str) -> TaskDefinition | None:
    for task in cfg.tasks:
        if task_name in (task.id, task.name):
            return task
    return None


def _parse_hhmmss(value: str, tz: ZoneInfo, ref: datetime) -> datetime | None:
    value = value.strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%H:%M:%S",
        "%H:%M",
    ):
        try:
            dt = datetime.strptime(value, fmt)
            if fmt.startswith("%H"):
                return datetime.combine(ref.date(), dt.time(), tzinfo=tz)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=tz)
            return dt.astimezone(tz)
        except ValueError:
            continue
    return None


def _scheduled_dt(ref: datetime, hhmm: str, tz: ZoneInfo) -> datetime:
    hour, minute = (int(x) for x in hhmm.split(":", 1))
    return datetime.combine(ref.date(), time(hour, minute), tzinfo=tz)


def task_completion_deadline(
    cfg: MonitorConfig, task_name: str, ref: datetime
) -> datetime | None:
    """预计结束时刻 + overrun（执行超时截止）。"""
    task = _find_task(cfg, task_name)
    if not task:
        return None
    tz = ZoneInfo(cfg.timezone)
    end = _scheduled_dt(ref, task.expected_end, tz)
    start = _scheduled_dt(ref, task.scheduled_start, tz)
    if end <= start:
        end += timedelta(days=1)
    return end + timedelta(minutes=cfg.overrun_after_end_threshold_minutes)


def calculate_time_diff_by_task(cfg: MonitorConfig, task_name: str, ref: datetime) -> int:
    """计划执行时长（秒）：expected_end - scheduled_start。"""
    task = _find_task(cfg, task_name)
    if not task:
        return 0
    tz = ZoneInfo(cfg.timezone)
    start = _scheduled_dt(ref, task.scheduled_start, tz)
    end = _scheduled_dt(ref, task.expected_end, tz)
    if end <= start:
        end += timedelta(days=1)
    return int((end - start).total_seconds())


def minutes_diff_exceeds_limit(
    cfg: MonitorConfig,
    task_name: str,
    kind: str,
    actual_time_str: str,
    limit_minutes: int,
    ref: datetime,
) -> bool:
    if kind != "start_time":
        return False
    task = _find_task(cfg, task_name)
    if not task:
        return False
    tz = ZoneInfo(cfg.timezone)
    actual = _parse_hhmmss(actual_time_str, tz, ref)
    if not actual:
        return False
    planned = _scheduled_dt(ref, task.scheduled_start, tz)
    return (actual - planned).total_seconds() > limit_minutes * 60
