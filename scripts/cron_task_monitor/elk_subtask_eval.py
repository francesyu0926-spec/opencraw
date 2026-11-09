from __future__ import annotations

from datetime import datetime

from .elk_task_schedule import task_monitor_window
from .mdimonitor_checks import run_mdimonitor_checks
from .models import Alert, AlertKind, MonitorConfig


def _msg_relates_to_task(msg: str, task_id: str, task_name: str) -> bool:
    if task_id in msg:
        return True
    return bool(task_name and task_name in msg)


def _task_has_completion(hits: list[dict], task_id: str, task_name: str) -> bool:
    for hit in hits:
        source = hit.get("_source") or {}
        msg = str(source.get("msg") or "")
        if "任务执行完成" not in msg:
            continue
        if _msg_relates_to_task(msg, task_id, task_name):
            return True
    return False


def _mdimonitor_alerts_for_task(
    alerts: list[Alert], task_id: str, task_name: str
) -> list[Alert]:
    """批量巡检文案里可能含多个任务名，只保留与当前子任务相关的告警。"""
    out: list[Alert] = []
    for alert in alerts:
        msg = alert.message or ""
        if task_id in msg or (task_name and task_name in msg):
            out.append(alert)
    return out


def _alerts_for_subtask_result(result: dict) -> list[Alert]:
    if result.get("status") != "failed":
        return []
    tid = str(result.get("task_id") or "")
    name = str(result.get("name") or tid)
    issues = result.get("issues") or []
    note = "；".join(str(x) for x in issues if str(x).strip()) or f"{name} 未通过巡检"
    return [
        Alert(
            kind=AlertKind.EXECUTION_FAILED,
            task_id=tid,
            task_name=name,
            message=f"{name}（{tid}）：{note}",
            notify="on-call",
            severity="critical",
        )
    ]


def evaluate_elk_subtasks(
    cfg: MonitorConfig,
    hits: list[dict],
    task_ids: list[str],
    ref: datetime,
) -> tuple[list[dict], int]:
    """
  子任务成功：① 未延迟启动 ② 未执行失败 ③ 未执行超时，且日志中已有「任务执行完成」。
  监控窗内尚无完成日志则为 in_progress（本轮不算成功）。
  """
    by_id = {t.id: t for t in cfg.tasks}
    results: list[dict] = []

    for tid in task_ids:
        task = by_id.get(tid)
        if task is None:
            results.append(
                {
                    "task_id": tid,
                    "name": tid,
                    "status": "failed",
                    "issues": ["未知任务 ID"],
                }
            )
            continue

        mdimonitor_alerts = _mdimonitor_alerts_for_task(
            run_mdimonitor_checks(cfg, hits, [tid], ref),
            tid,
            task.name,
        )
        issues = [a.message for a in mdimonitor_alerts]
        has_complete = _task_has_completion(hits, tid, task.name)
        _, monitor_end = task_monitor_window(cfg, task, ref)

        if mdimonitor_alerts:
            status = "failed"
        elif has_complete:
            status = "passed"
        elif ref > monitor_end:
            status = "failed"
            issues.append("监控窗口结束前未见「任务执行完成」日志")
        else:
            status = "in_progress"
            issues = []

        results.append(
            {
                "task_id": tid,
                "name": task.name,
                "status": status,
                "issues": issues,
            }
        )

    exit_code = 0
    if not results:
        return results, exit_code
    if any(r["status"] == "failed" for r in results):
        exit_code = 1
    elif any(r["status"] == "in_progress" for r in results):
        exit_code = 1
    return results, exit_code


def alerts_from_subtask_results(results: list[dict]) -> list[Alert]:
    alerts: list[Alert] = []
    for item in results:
        alerts.extend(_alerts_for_subtask_result(item))
    return alerts
