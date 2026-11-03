from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .models import Alert, AlertKind, MonitorConfig, TaskDefinition, TaskRunRecord


def _combine(run_date: datetime, hhmm: str, tz: ZoneInfo) -> datetime:
    hour, minute = (int(x) for x in hhmm.split(":", 1))
    return datetime.combine(run_date.date(), time(hour, minute), tzinfo=tz)


def evaluate_task(
    cfg: MonitorConfig,
    task: TaskDefinition,
    record: TaskRunRecord,
    now: datetime,
    *,
    monitor_mode: str = "local",
) -> list[Alert]:
    tz = ZoneInfo(cfg.timezone)
    scheduled_start = _combine(now, task.scheduled_start, tz)
    expected_end = _combine(now, task.expected_end, tz)
    if expected_end <= scheduled_start:
        expected_end += timedelta(days=1)

    alerts: list[Alert] = []
    notify = task.notify or "on-call"

    def alert(kind: AlertKind, message: str, severity: str) -> None:
        alerts.append(
            Alert(
                kind=kind,
                task_id=task.id,
                task_name=task.name,
                message=message,
                notify=notify,
                severity=severity,
            )
        )

    if record.status == "missing_log":
        use_elk = monitor_mode == "elk" or record.source in ("elk", "merged")
        if use_elk:
            detail = (
                record.raw_messages[-1]
                if record.raw_messages
                else f"index={task.log_index_pattern}"
            )
            alert(
                AlertKind.MISSING_LOG,
                f"ELK 未查到任务日志（{task.id}，{detail}）",
                "warning",
            )
        else:
            alert(
                AlertKind.MISSING_LOG,
                f"未找到任务日志目录或文件：{task.log_dir}（server={task.server}）",
                "warning",
            )
        return alerts

    late_deadline = scheduled_start + timedelta(minutes=cfg.late_start_threshold_minutes)
    overrun_deadline = expected_end + timedelta(
        minutes=cfg.overrun_after_end_threshold_minutes
    )

    if record.started_at is None:
        if now >= late_deadline:
            alert(
                AlertKind.NO_START,
                f"未检测到启动日志，已超过计划开始 {task.scheduled_start} "
                f"{cfg.late_start_threshold_minutes} 分钟"
                + (
                    f"（ELK index={task.log_index_pattern}）"
                    if monitor_mode == "elk"
                    else f"（server={task.server}）"
                ),
                "critical",
            )
        return alerts

    if record.started_at > late_deadline:
        delay = record.started_at - scheduled_start
        alert(
            AlertKind.LATE_START,
            f"延迟启动 {int(delay.total_seconds() // 60)} 分钟，"
            f"计划 {task.scheduled_start}，实际 {record.started_at.strftime('%H:%M:%S')}",
            "warning",
        )

    if record.status == "failure":
        alert(
            AlertKind.EXECUTION_FAILED,
            (
                f"任务执行失败（ELK index={task.log_index_pattern}）"
                if monitor_mode == "elk"
                else f"任务执行失败（server={task.server}，log={task.log_dir}）"
            ),
            "critical",
        )
        return alerts

    finished_ok = record.status == "success" and record.ended_at is not None
    if not finished_ok and now >= overrun_deadline:
        alert(
            AlertKind.OVERTIME,
            f"超过预计结束 {task.expected_end} 后 "
            f"{cfg.overrun_after_end_threshold_minutes} 分钟仍未成功完成",
            "critical",
        )
    elif record.ended_at and record.ended_at > expected_end + timedelta(
        minutes=cfg.overrun_after_end_threshold_minutes
    ):
        alert(
            AlertKind.OVERTIME,
            f"结束时间 {record.ended_at.strftime('%H:%M:%S')} 晚于允许的最晚完成时刻",
            "warning",
        )

    return alerts
