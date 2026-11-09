from __future__ import annotations

from datetime import datetime

JOB_LABELS: dict[str, str] = {
    "health": "行情 HTTP 探活",
    "ws": "WebSocket 探活",
    "elk": "ELK 数据同步",
    "writing": "自动化写稿",
}


def monitor_report_title(monitor_item: str = "") -> str:
    """Report heading: 「{监控项}监控测试报告」；无监控项时用通用标题。"""
    item = monitor_item.strip()
    if not item:
        return "终端接口监控测试报告"
    return f"{item}监控测试报告"


def monitor_report_markdown(
    *,
    checked_at: str,
    passed: bool | None,
    monitor_item: str = "",
    note: str = "",
    subtasks: str = "",
    title: str | None = None,
) -> str:
    heading = title if title is not None else monitor_report_title(monitor_item)
    if passed is True:
        verdict = '<font color="info">通过</font>'
    elif passed is False:
        verdict = '<font color="warning">未通过</font>'
    else:
        verdict = '<font color="comment">进行中</font>'
    lines = [
        f"### {heading}",
        f"> 时间：{checked_at}",
    ]
    if subtasks.strip():
        lines.append(f"> 子任务：{subtasks.strip()}")
    lines.extend(["", f"结论：{verdict}"])
    if note.strip():
        lines.append(f"> 说明：{note.strip()}")
    return "\n".join(lines)


def _format_elk_task_row(row: dict) -> str:
    task_id = str(row.get("id") or "").strip()
    name = str(row.get("name") or "").strip()
    if task_id and name:
        return f"{task_id}（{name}）"
    return task_id or name


def report_checked_at_for_job(job_id: str, info: dict, fallback: datetime) -> str:
    """ELK 报告时间取 ES 查询结束时刻（lte），其它 job 用 fallback。"""
    detail = info.get("detail") if isinstance(info.get("detail"), dict) else {}
    if job_id == "elk":
        qtr = detail.get("query_time_range")
        if isinstance(qtr, dict) and qtr.get("lte"):
            lte = str(qtr["lte"]).strip()
            try:
                dt = datetime.fromisoformat(lte.replace("Z", "+00:00"))
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
    return fallback.strftime("%Y-%m-%d %H:%M:%S")


def subtasks_display_for_job(job_id: str, info: dict) -> str:
    """ELK / 写稿企微报告中的子任务列表（id+中文名 或 写稿子任务名）。"""
    detail = info.get("detail") if isinstance(info.get("detail"), dict) else {}
    if job_id == "elk":
        sub_rows = detail.get("subtask_results")
        if isinstance(sub_rows, list):
            labels = []
            for row in sub_rows:
                if not isinstance(row, dict) or row.get("status") != "passed":
                    continue
                label = _format_elk_task_row(
                    {"id": row.get("task_id"), "name": row.get("name")}
                )
                if label:
                    labels.append(label)
            if labels:
                return "、".join(labels)
            return ""
        passed = detail.get("passed_tasks")
        if isinstance(passed, list) and passed:
            labels = [
                _format_elk_task_row(item)
                for item in passed
                if isinstance(item, dict) and _format_elk_task_row(item)
            ]
            if labels:
                return "、".join(labels)
        monitored = detail.get("monitored_tasks")
        if isinstance(monitored, list) and monitored:
            labels = [
                _format_elk_task_row(item)
                for item in monitored
                if isinstance(item, dict) and _format_elk_task_row(item)
            ]
            if labels:
                return "、".join(labels)
        for key in ("task_ids", "msg_keywords"):
            raw = detail.get(key)
            if isinstance(raw, list) and raw:
                return "、".join(str(x).strip() for x in raw if str(x).strip())
    if job_id == "writing":
        monitored = detail.get("monitored_tasks")
        if isinstance(monitored, list):
            names = [
                str(item.get("name") or "").strip()
                for item in monitored
                if isinstance(item, dict) and str(item.get("name") or "").strip()
            ]
            if names:
                return "、".join(names)
        rows = detail.get("results") or []
        names = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("task") or "").strip()
            if name and name not in names:
                names.append(name)
        if names:
            return "、".join(names)
    return ""


def exit_code_to_report_passed(exit_code: int) -> bool | None:
    if exit_code == 0:
        return True
    if exit_code == 2:
        return None
    return False


def grace_note_for_job(job_id: str, info: dict) -> str:
    """预计结束后的宽限期内仍在执行 — 非通过也非未通过。"""
    detail = info.get("detail") if isinstance(info.get("detail"), dict) else {}
    if job_id != "elk":
        return info.get("description") or JOB_LABELS.get(job_id, job_id)
    sub_rows = detail.get("subtask_results") or []
    notes: list[str] = []
    for row in sub_rows:
        if not isinstance(row, dict) or row.get("status") != "in_progress":
            continue
        name = row.get("name") or row.get("task_id") or "ELK任务"
        notes.append(f"{name}【宽限观察中】")
    if notes:
        return "；".join(notes)
    return info.get("description") or JOB_LABELS.get(job_id, job_id)


def outcome_note_for_job(job_id: str, info: dict, exit_code: int) -> str:
    if exit_code == 0:
        return ""
    if exit_code == 2:
        return grace_note_for_job(job_id, info)
    return failure_note_for_job(job_id, info)


def failure_note_for_job(job_id: str, info: dict) -> str:
    detail = info.get("detail") if isinstance(info.get("detail"), dict) else {}
    if info.get("error"):
        return str(info["error"]).strip()
    if job_id == "health" and detail:
        err = detail.get("error") or detail.get("wecom_message")
        if err:
            return str(err).strip()
        down = detail.get("down_checks")
        if isinstance(down, list) and down:
            return str(down[0])
    if job_id == "ws" and detail and detail.get("error"):
        return str(detail["error"]).strip()
    if job_id == "elk" and detail:
        sub_rows = detail.get("subtask_results") or []
        notes: list[str] = []
        for row in sub_rows:
            if not isinstance(row, dict):
                continue
            st = row.get("status")
            if st == "in_progress" and not row.get("unresolved", False):
                continue
            if st not in ("failed", "in_progress"):
                continue
            name = row.get("name") or row.get("task_id") or "ELK任务"
            tag = "失败" if st == "failed" else "进行中"
            iss = row.get("issues") or []
            extra = f"（{'；'.join(str(x) for x in iss if x)}）" if iss else ""
            notes.append(f"{name}【{tag}】{extra}")
        if notes:
            return "；".join(notes)
        alerts = detail.get("alerts") or []
        if alerts and isinstance(alerts[0], dict) and alerts[0].get("message"):
            return str(alerts[0]["message"]).strip()
    if job_id == "writing" and detail:
        for row in detail.get("results") or []:
            if row.get("status") in ("failed", "error"):
                name = row.get("task") or "写稿任务"
                msg = row.get("message") or ""
                return f"{name}：{msg}".strip("：")
    return info.get("description") or JOB_LABELS.get(job_id, job_id)
