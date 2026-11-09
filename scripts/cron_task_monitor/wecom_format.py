from __future__ import annotations

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
    passed: bool,
    monitor_item: str = "",
    note: str = "",
    subtasks: str = "",
    title: str | None = None,
) -> str:
    heading = title if title is not None else monitor_report_title(monitor_item)
    verdict = (
        '<font color="info">通过</font>'
        if passed
        else '<font color="warning">未通过</font>'
    )
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


def subtasks_display_for_job(job_id: str, info: dict) -> str:
    """ELK / 写稿企微报告中的子任务列表（id+中文名 或 写稿子任务名）。"""
    detail = info.get("detail") if isinstance(info.get("detail"), dict) else {}
    if job_id == "elk":
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
        rows = detail.get("results") or []
        names: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("task") or "").strip()
            if name and name not in names:
                names.append(name)
        if names:
            return "、".join(names)
    return ""


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
