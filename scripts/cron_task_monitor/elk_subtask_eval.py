from __future__ import annotations

from datetime import datetime

from .elk_task_schedule import (
    elk_follow_up_minutes,
    elk_task_ids_in_monitoring_scope,
    task_monitor_window,
    task_plan_end,
)
from .mdimonitor_checks import run_mdimonitor_checks
from .models import Alert, AlertKind, MonitorConfig


def _task_log_id_aliases(task_id: str) -> tuple[str, ...]:
    """配置 id 与 ES 文案不一致时互为别名（如 NC_LISTSTOCK_GLANCE ↔ NC_LISTSTOCK_GLANCE_2）。"""
    if task_id.endswith("_2") and len(task_id) > 2:
        base = task_id[:-2]
        return (task_id, base) if base != task_id else (task_id,)
    return (task_id, f"{task_id}_2")


def _msg_relates_to_task(msg: str, task_id: str, task_name: str) -> bool:
    for alias in _task_log_id_aliases(task_id):
        if alias in msg:
            return True
    return bool(task_name and task_name in msg)


def _task_has_start(hits: list[dict], task_id: str, task_name: str) -> bool:
    """命中「开始执行」类日志且与任务相关，即视为已开始。"""
    markers = ("开始执行任务", "开始执行")
    for hit in hits:
        source = hit.get("_source") or {}
        msg = str(source.get("msg") or "")
        if not any(marker in msg for marker in markers):
            continue
        if _msg_relates_to_task(msg, task_id, task_name):
            return True
    return False


def _task_has_failure(hits: list[dict], task_id: str, task_name: str) -> bool:
    for hit in hits:
        source = hit.get("_source") or {}
        msg = str(source.get("msg") or "")
        if "执行失败" not in msg:
            continue
        if _msg_relates_to_task(msg, task_id, task_name):
            return True
    return False


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
        if any(alias in msg for alias in _task_log_id_aliases(task_id)) or (
            task_name and task_name in msg
        ):
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
  监控窗内子任务均输出结论；预计结束前以「进行中」为主，结束后再做通过/失败判定。
  """
    by_id = {t.id: t for t in cfg.tasks}
    follow_up = elk_follow_up_minutes(
        cfg, cfg.schedule_interval_minutes or 5, cfg.schedule_interval_minutes or 5
    )
    results: list[dict] = []
    for tid in elk_task_ids_in_monitoring_scope(
        cfg, task_ids, ref, follow_up_minutes=follow_up
    ):
        task = by_id.get(tid)
        if task is None:
            results.append(
                {
                    "task_id": tid,
                    "name": tid,
                    "status": "failed",
                    "issues": ["未知任务 ID"],
                    "unresolved": True,
                }
            )
            continue

        has_start = _task_has_start(hits, tid, task.name)
        has_failure = _task_has_failure(hits, tid, task.name)
        has_complete = _task_has_completion(hits, tid, task.name)
        plan_end = task_plan_end(cfg, task, ref)
        _, monitor_end = task_monitor_window(cfg, task, ref)

        if ref <= plan_end:
            # 预计结束前只判失败或进行中，不因历史「完成」日志提前通过
            issues: list[str] = []
            if has_failure:
                status = "failed"
                issues.append("日志中出现「执行失败」")
            else:
                status = "in_progress"
            unresolved = status == "failed"
            in_grace = status == "in_progress"
        else:
            mdimonitor_alerts = _mdimonitor_alerts_for_task(
                run_mdimonitor_checks(cfg, hits, [tid], ref),
                tid,
                task.name,
            )
            issues = [a.message for a in mdimonitor_alerts]
            if mdimonitor_alerts:
                status = "failed"
            elif has_failure:
                status = "failed"
                if not any("执行失败" in str(x) for x in issues):
                    issues.append("日志中出现「执行失败」")
            elif has_complete:
                status = "passed"
            elif ref > monitor_end:
                status = "failed"
                issues.append(
                    "监控窗口结束前未见「任务执行完成」日志"
                    if has_start
                    else "未见「开始执行任务」日志"
                )
            elif has_start:
                status = "in_progress"
                issues = []
            else:
                status = "failed"
                issues.append("未见「开始执行任务」日志")

            unresolved = status == "failed"
            in_grace = status == "in_progress"

        results.append(
            {
                "task_id": tid,
                "name": task.name,
                "status": status,
                "issues": issues,
                "unresolved": unresolved,
                "in_grace": in_grace,
            }
        )

    exit_code = 0
    if not results:
        return results, exit_code
    if any(r.get("unresolved") for r in results):
        exit_code = 1
    elif any(r.get("status") == "in_progress" for r in results):
        exit_code = 2
    return results, exit_code


def alerts_from_subtask_results(results: list[dict]) -> list[Alert]:
    alerts: list[Alert] = []
    for item in results:
        alerts.extend(_alerts_for_subtask_result(item))
    return alerts
