from __future__ import annotations

from datetime import datetime

from .models import Alert, AlertKind, MonitorConfig
from .quote_utils import (
    CQuotesESError,
    calculate_time_diff_by_task,
    minutes_diff_exceeds_limit,
)


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
            cfg, task_name, "start_time", actual_start_time_str, 5, ref
        ):
            tasks_started_late.append(task_name)

    if not tasks_started_late:
        return []
    msg = f"以下任务未按时启动（延迟 > 5 分钟）：{', '.join(tasks_started_late)}"
    return _alerts_from_error(AlertKind.LATE_START, msg)


def check_task_ended_late(cfg: MonitorConfig, hits: list[dict], ref: datetime) -> list[Alert]:
    task_end_start_key = "任务执行完成:"
    task_end_target_key = ",耗时："
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

        expected_run_time = calculate_time_diff_by_task(cfg, task_name, ref)
        if actual_run_time > (expected_run_time + 10 * 60):
            tasks_completed_late.append(task_name)

    if not tasks_completed_late:
        return []
    msg = f"以下任务执行超时（延迟 > 10 分钟）：{', '.join(tasks_completed_late)}"
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
