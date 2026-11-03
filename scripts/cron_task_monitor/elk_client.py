from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .log_parser import parse_lines_for_task
from .models import MonitorConfig, TaskDefinition, TaskRunRecord


def _es_base_url() -> str | None:
    url = os.environ.get("ELASTICSEARCH_URL") or os.environ.get("ES_URL")
    if url:
        return url.rstrip("/")
    return None


def _es_auth_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("ELASTICSEARCH_API_KEY")
    if api_key:
        headers["Authorization"] = f"ApiKey {api_key}"
        return headers
    user = os.environ.get("ELASTICSEARCH_USER")
    password = os.environ.get("ELASTICSEARCH_PASSWORD")
    if user and password:
        import base64

        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    return headers


def query_task_from_elk(
    cfg: MonitorConfig,
    task: TaskDefinition,
    now: datetime,
) -> TaskRunRecord | None:
    base = _es_base_url()
    if not base or not task.log_index_pattern:
        return None

    tz = ZoneInfo(cfg.timezone)
    day_start = datetime.combine(now.date(), datetime.min.time(), tzinfo=tz)
    day_end = datetime.combine(now.date(), datetime.max.time(), tzinfo=tz)

    # @timestamp 或 message 中包含 TASK_MONITOR / task id
    body: dict[str, Any] = {
        "size": 500,
        "sort": [{"@timestamp": {"order": "asc"}}],
        "query": {
            "bool": {
                "filter": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": day_start.isoformat(),
                                "lte": day_end.isoformat(),
                            }
                        }
                    },
                    {
                        "query_string": {
                            "query": f'task:{task.id} OR message:"task={task.id}" OR message:"{task.id}"',
                            "default_field": "message",
                        }
                    },
                ]
            }
        },
        "_source": ["message", "@timestamp"],
    }

    index = task.log_index_pattern
    url = f"{base}/{index}/_search"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=_es_auth_headers(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        rec = TaskRunRecord(task_id=task.id, source="elk", status="missing_log")
        rec.raw_messages.append("elasticsearch query failed")
        return rec

    hits = payload.get("hits", {}).get("hits") or []
    lines: list[str] = []
    for hit in hits:
        src = hit.get("_source") or {}
        msg = src.get("message")
        ts = src.get("@timestamp")
        if msg:
            if ts and str(ts) not in str(msg):
                lines.append(f"{ts} {msg}")
            else:
                lines.append(str(msg))

    if not lines:
        return TaskRunRecord(task_id=task.id, source="elk", status="missing_log")

    record = parse_lines_for_task(task, lines, tz, cfg.monitor_log_prefix)
    record.source = "elk"
    return record


def merge_records(local: TaskRunRecord, elk: TaskRunRecord | None) -> TaskRunRecord:
    if elk is None:
        return local
    merged = TaskRunRecord(task_id=local.task_id, source="merged")
    merged.started_at = _earlier(local.started_at, elk.started_at)
    merged.ended_at = _later(local.ended_at, elk.ended_at)
    merged.status = _pick_status(local.status, elk.status)
    merged.raw_messages = (local.raw_messages + elk.raw_messages)[-50:]
    return merged


def _earlier(a: datetime | None, b: datetime | None) -> datetime | None:
    if a and b:
        return min(a, b)
    return a or b


def _later(a: datetime | None, b: datetime | None) -> datetime | None:
    if a and b:
        return max(a, b)
    return a or b


def _pick_status(a: str | None, b: str | None) -> str | None:
    if a == "failure" or b == "failure":
        return "failure"
    if a == "success" or b == "success":
        return "success"
    return a or b
