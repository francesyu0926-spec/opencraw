from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from .elasticsearch_settings import auth_headers, resolve_elasticsearch
from .elk_query import build_task_search_body, extract_log_line
from .log_parser import parse_lines_for_task
from .models import ElasticsearchConfig, MonitorConfig, TaskDefinition, TaskRunRecord


def check_elasticsearch(cfg: MonitorConfig) -> tuple[bool, str]:
    settings = resolve_elasticsearch(cfg)
    if not settings:
        return False, "未配置 Elasticsearch URL（config.elasticsearch 或 ELASTICSEARCH_URL）"
    if settings.username and not settings.password:
        return (
            False,
            "已配置用户名但未设置密码环境变量 ELASTICSEARCH_PASSWORD（或 ES_PASSWORD）",
        )

    url = f"{settings.url}/_cluster/health"
    req = urllib.request.Request(url, headers=auth_headers(settings), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        status = body.get("status", "unknown")
        cluster = body.get("cluster_name", "")
        return True, f"连接成功 cluster={cluster} status={status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.reason}"
    except (urllib.error.URLError, TimeoutError) as e:
        return False, f"连接失败: {e}"


def query_task_from_elk(
    cfg: MonitorConfig,
    task: TaskDefinition,
    now: datetime,
) -> TaskRunRecord | None:
    settings = resolve_elasticsearch(cfg)
    if not settings or not task.log_index_pattern:
        return None

    tz = ZoneInfo(cfg.timezone)
    es_cfg = cfg.elasticsearch or ElasticsearchConfig()
    body = build_task_search_body(cfg, task)

    index = task.log_index_pattern
    url = f"{settings.url}/{index}/_search"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=auth_headers(settings),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:200]
        rec = TaskRunRecord(task_id=task.id, source="elk", status="missing_log")
        rec.raw_messages.append(f"elasticsearch HTTP {e.code}: {detail}")
        return rec
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        rec = TaskRunRecord(task_id=task.id, source="elk", status="missing_log")
        rec.raw_messages.append(f"elasticsearch query failed: {e}")
        return rec

    hits = payload.get("hits", {}).get("hits") or []
    field = es_cfg.message_field or "msg"
    lines: list[str] = []
    for hit in hits:
        src = hit.get("_source") or {}
        msg = extract_log_line(src, field)
        ts = src.get("@timestamp")
        if msg:
            if ts and str(ts) not in str(msg):
                lines.append(f"{ts} {msg}")
            else:
                lines.append(str(msg))

    if not lines:
        rec = TaskRunRecord(task_id=task.id, source="elk", status="missing_log")
        rec.raw_messages.append(
            f"elk: 0 hits index={index} query={json.dumps(body['query'], ensure_ascii=False)[:300]}"
        )
        return rec

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
    if local.status == "missing_log" and elk.status not in (None, "missing_log"):
        merged.status = elk.status
        merged.started_at = elk.started_at or merged.started_at
        merged.ended_at = elk.ended_at or merged.ended_at
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
    if a == "missing_log":
        return b
    if b == "missing_log":
        return a
    return a or b
