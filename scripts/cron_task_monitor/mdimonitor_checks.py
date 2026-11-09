from __future__ import annotations

from datetime import datetime, timedelta

from .models import Alert, AlertKind, MonitorConfig
from .quote_utils import (
    CQuotesESError,
    minutes_diff_exceeds_limit,
    task_completion_deadline,
    _find_task,
    _parse_hhmmss,
    _scheduled_dt,
)
from zoneinfo import ZoneInfo


def _alerts_from_error(kind: AlertKind, message: str) -> list[Alert]:
    return [
        Alert(
            kind=kind,
            task_id="",
            task_name="",
            message=message,
            notify="on-call",
            severity="critical",
        )
    ]


def check_tasks_started_late(
    cfg: MonitorConfig,
    hits: list[dict],
    ref: datetime,
) -> list[Alert]:
    task_begin_start_key = "开始执行任务: "
    task_begin_target_key = ",执行时间："
    tasks_started_late: list[str] = []
    limit = cfg.late_start_threshold_minutes

    for hit in hits:
        source = hit.get("_source") or {}
        source_msg = str(source.get("msg") or "")
        if not source_msg.startswith(task_begin_start_key):
            continue
        if task_begin_target_key not in source_msg:
            continue

        parts = (
            source_msg.replace(task_begin_start_key, "")
            .replace(task_begin_target_key, " ")
            .split()
        )
        if len(parts) < 2:
            continue
        task_name = parts[0]
        actual_start_time_str = parts[-1] if len(parts) == 2 else " ".join(parts[1:])

        if minutes_diff_exceeds_limit(
            cfg, task_name, "start_time", actual_start_time_str, limit, ref
        ):
            tasks_started_late.append(task_name)

    if not tasks_started_late:
        return []
    msg = (
        f"以下任务未按时启动（延迟 > {limit} 分钟）："
        f"{', '.join(tasks_started_late)}"
    )
    return _alerts_from_error(AlertKind.LATE_START, msg)


def check_task_ended_late(cfg: MonitorConfig, hits: list[dict], ref: datetime) -> list[Alert]:
    """执行超时：完成时刻晚于 预计结束 + overrun 分钟。"""
    task_begin_start_key = "开始执行任务: "
    task_begin_target_key = ",执行时间："
    task_end_start_key = "任务执行完成:"
    task_end_target_key = ",耗时："
    overrun = cfg.overrun_after_end_threshold_minutes
    tz = ZoneInfo(cfg.timezone)

    begin_at: dict[str, datetime] = {}
    for hit in hits:
        source = hit.get("_source") or {}
        source_msg = str(source.get("msg") or "")
        if not source_msg.startswith(task_begin_start_key):
            continue
        if task_begin_target_key not in source_msg:
            continue
        parts = (
            source_msg.replace(task_begin_start_key, "")
            .replace(task_begin_target_key, " ")
            .split()
        )
        if len(parts) < 2:
            continue
        task_name = parts[0]
        actual_start_time_str = parts[-1] if len(parts) == 2 else " ".join(parts[1:])
        actual = _parse_hhmmss(actual_start_time_str, tz, ref)
        if actual:
            begin_at[task_name] = actual

    tasks_completed_late: list[str] = []

    for hit in hits:
        source = hit.get("_source") or {}
        source_msg = str(source.get("msg") or "")
        if not source_msg.startswith(task_end_start_key):
            continue
        if task_end_target_key not in source_msg:
            continue

        cleaned = (
            source_msg.replace(task_end_start_key, "")
            .replace(task_end_target_key, " ")
            .replace("秒", "")
        )
        parts = cleaned.split()
        if len(parts) < 2:
            continue
        task_name, actual_run_time_str = parts[0], parts[1]
        try:
            actual_run_time = int(actual_run_time_str)
        except ValueError:
            continue

        deadline = task_completion_deadline(cfg, task_name, ref)
        if not deadline:
            continue

        start = begin_at.get(task_name)
        if start is None:
            task = _find_task(cfg, task_name)
            if not task:
                continue
            start = _scheduled_dt(ref, task.scheduled_start, tz)

        finish = start + timedelta(seconds=actual_run_time)
        if finish > deadline:
            tasks_completed_late.append(task_name)

    if not tasks_completed_late:
        return []
    msg = (
        f"以下任务执行超时（超过预计结束 + {overrun} 分钟）："
        f"{', '.join(tasks_completed_late)}"
    )
    return _alerts_from_error(AlertKind.OVERTIME, msg)


def check_task_failed(
    cfg: MonitorConfig,
    hits: list[dict],
    msg_keywords: list[str],
) -> list[Alert]:
    tasks_failed: list[str] = []

    for hit in hits:
        source = hit.get("_source") or {}
        source_msg = str(source.get("msg") or "")
        if "执行失败" not in source_msg:
            continue
        for keyword in msg_keywords:
            if keyword in source_msg:
                tasks_failed.append(keyword)

    if not tasks_failed:
        return []
    msg = f"以下任务执行失败：{', '.join(tasks_failed)} "
    return _alerts_from_error(AlertKind.EXECUTION_FAILED, msg)


def run_mdimonitor_checks(
    cfg: MonitorConfig,
    hits: list[dict],
    msg_keywords: list[str],
    ref: datetime,
) -> list[Alert]:
    alerts: list[Alert] = []
    alerts.extend(check_tasks_started_late(cfg, hits, ref))
    alerts.extend(check_task_ended_late(cfg, hits, ref))
    alerts.extend(check_task_failed(cfg, hits, msg_keywords))
    return alerts


def raise_if_errors(alerts: list[Alert]) -> None:
    if alerts:
        raise CQuotesESError("; ".join(a.message for a in alerts))
