from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import TaskDefinition, TaskRunRecord

# [TASK_MONITOR] task=CBD_PUB_BOARD_INFO event=start ts=2025-11-03T01:00:01+08:00
STRUCTURED_RE = re.compile(
    r"\[TASK_MONITOR\]\s+task=(?P<task>\S+)\s+event=(?P<event>start|end)"
    r"(?:\s+status=(?P<status>success|failure|running))?"
    r"(?:\s+ts=(?P<ts>\S+))?",
    re.IGNORECASE,
)

# 2025-11-03 01:00:01 ... 或 2025/11/03 01:00:01
GENERIC_TS_RE = re.compile(
    r"(?P<ts>\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2}:\d{2})"
)

START_KW = re.compile(r"(任务开始|开始执行|job\s+start|event=start|\bSTART\b)", re.I)
END_OK_KW = re.compile(r"(执行成功|任务完成|job\s+success|event=end.*success|成功结束|\bSUCCESS\b)", re.I)
END_FAIL_KW = re.compile(
    r"(执行失败|任务失败|job\s+fail|event=end.*failure|异常退出|\b(FAIL|ERROR|Exception)\b)",
    re.I,
)


def _parse_ts(raw: str, tz: ZoneInfo) -> datetime | None:
    raw = raw.strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(raw.replace("Z", "+0000"), fmt)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=tz)
            return dt.astimezone(tz)
        except ValueError:
            continue
    return None


def _line_timestamp(line: str, tz: ZoneInfo) -> datetime | None:
    m = GENERIC_TS_RE.search(line)
    if m:
        return _parse_ts(m.group("ts"), tz)
    return None


def parse_lines_for_task(
    task: TaskDefinition,
    lines: list[str],
    tz: ZoneInfo,
    monitor_prefix: str,
) -> TaskRunRecord:
    record = TaskRunRecord(task_id=task.id, source="local")
    prefix = monitor_prefix or "[TASK_MONITOR]"

    for line in lines:
        if task.id not in line and prefix not in line:
            # 仍允许仅通过结构化 task= 匹配
            if f"task={task.id}" not in line:
                continue

        record.raw_messages.append(line.rstrip())

        structured = STRUCTURED_RE.search(line.replace(prefix, "[TASK_MONITOR]"))
        if structured and structured.group("task") == task.id:
            event = structured.group("event").lower()
            ts = structured.group("ts")
            dt = _parse_ts(ts, tz) if ts else _line_timestamp(line, tz)
            status = (structured.group("status") or "").lower() or None
            if event == "start" and dt:
                if record.started_at is None or dt < record.started_at:
                    record.started_at = dt
            elif event == "end" and dt:
                if record.ended_at is None or dt > record.ended_at:
                    record.ended_at = dt
                if status in ("success", "failure"):
                    record.status = status
            continue

        if task.id not in line:
            continue

        ts = _line_timestamp(line, tz)
        if START_KW.search(line) and ts:
            if record.started_at is None or ts < record.started_at:
                record.started_at = ts
        if END_FAIL_KW.search(line):
            if ts and (record.ended_at is None or ts > record.ended_at):
                record.ended_at = ts
            record.status = "failure"
        elif END_OK_KW.search(line):
            if ts and (record.ended_at is None or ts > record.ended_at):
                record.ended_at = ts
            record.status = "success"

    if record.status is None:
        if record.ended_at:
            record.status = "unknown"
        elif record.started_at:
            record.status = "running"
    return record


def collect_log_files(log_dir: str, log_glob: str) -> list[Path]:
    base = Path(log_dir)
    if not base.is_dir():
        return []
    return sorted(base.glob(log_glob))


def read_today_lines(
    files: list[Path],
    tz: ZoneInfo,
    run_date: datetime,
) -> list[str]:
    """读取与 run_date 同自然日相关的日志行（按行首时间或文件 mtime）。"""
    day = run_date.date()
    out: list[str] = []
    for fp in files:
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        file_mtime = datetime.fromtimestamp(fp.stat().st_mtime, tz=tz)
        for line in text.splitlines():
            ts = _line_timestamp(line, tz)
            if ts and ts.date() == day:
                out.append(line)
            elif ts is None and file_mtime.date() == day:
                out.append(line)
    return out


def analyze_local_task(
    task: TaskDefinition,
    tz: ZoneInfo,
    now: datetime,
    monitor_prefix: str,
) -> TaskRunRecord:
    files = collect_log_files(task.log_dir, task.log_glob)
    if not files:
        rec = TaskRunRecord(task_id=task.id, source="local", status="missing_log")
        rec.raw_messages.append(f"log_dir not found or empty: {task.log_dir}")
        return rec
    lines = read_today_lines(files, tz, now)
    return parse_lines_for_task(task, lines, tz, monitor_prefix)
