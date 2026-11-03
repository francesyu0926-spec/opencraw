from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .elasticsearch_settings import ElasticsearchSettings, auth_headers
from .models import ElasticsearchConfig, MonitorConfig, TaskDefinition

# 查询 DSL 对齐 mdimonitor/tests/test_quotes_es.py：
# bool.should 内单个 match(msg, task_code) + @timestamp range + sort asc


def resolve_msg_keyword(task: TaskDefinition) -> str:
    """match 关键字：默认任务 id；可选 elk_msg_keywords 取第一个。"""
    raw = task.extra.get("elk_msg_keywords")
    if raw:
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        if isinstance(raw, list):
            for item in raw:
                s = str(item).strip()
                if s:
                    return s
    return task.id


def build_quotes_es_search_body(
    msg_keyword: str,
    *,
    message_field: str = "msg",
    timestamp_gte: str = "now-15m",
    timestamp_lte: str = "now",
    size: int = 1000,
) -> dict[str, Any]:
    """构造 ES _search body（与 mdimonitor test_quotes_es 相同结构）。"""
    return {
        "size": size,
        "sort": [{"@timestamp": {"order": "asc"}}],
        "query": {
            "bool": {
                "should": [{"match": {message_field: msg_keyword}}],
                "minimum_should_match": 1,
                "filter": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": timestamp_gte,
                                "lte": timestamp_lte,
                            }
                        }
                    }
                ],
            }
        },
        "_source": [message_field, "message", "msg", "@timestamp"],
    }


def build_task_search_body(cfg: MonitorConfig, task: TaskDefinition) -> dict[str, Any]:
    es = cfg.elasticsearch or ElasticsearchConfig()
    keyword = resolve_msg_keyword(task)
    return build_quotes_es_search_body(
        keyword,
        message_field=es.message_field or "msg",
        timestamp_gte=es.timestamp_gte or "now-15m",
        timestamp_lte=es.timestamp_lte or "now",
        size=es.query_size or 1000,
    )


def extract_log_line(source: dict[str, Any], message_field: str) -> str | None:
    msg = source.get(message_field)
    if msg is None:
        msg = source.get("msg") or source.get("message")
    if msg is None:
        return None
    if isinstance(msg, list):
        msg = " ".join(str(x) for x in msg)
    return str(msg)


def search_index(
    settings: ElasticsearchSettings,
    index: str,
    body: dict[str, Any],
    *,
    timeout: int = 30,
) -> tuple[dict[str, Any] | None, str | None]:
    """
    执行 ES _search。成功返回 (payload, None)；失败返回 (None, error_message)。
    """
    url = f"{settings.url}/{index}/_search"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=auth_headers(settings),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        return None, f"HTTP {e.code}: {detail}"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        return None, str(e)


def hits_to_log_lines(
    payload: dict[str, Any],
    message_field: str,
) -> list[str]:
    hits = payload.get("hits", {}).get("hits") or []
    lines: list[str] = []
    for hit in hits:
        src = hit.get("_source") or {}
        msg = extract_log_line(src, message_field)
        ts = src.get("@timestamp")
        if not msg:
            continue
        if ts and str(ts) not in str(msg):
            lines.append(f"{ts} {msg}")
        else:
            lines.append(str(msg))
    return lines
