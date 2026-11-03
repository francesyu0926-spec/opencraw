from __future__ import annotations

from typing import Any

from .models import ElasticsearchConfig, MonitorConfig, TaskDefinition


def task_msg_keywords(task: TaskDefinition, cfg: MonitorConfig) -> list[str]:
    """ES 检索关键字：默认仅 match 任务 id（一个 should 条件）。"""
    raw = task.extra.get("elk_msg_keywords")
    if raw:
        if isinstance(raw, str):
            return [raw.strip()] if raw.strip() else [task.id]
        items = [str(k).strip() for k in raw if str(k).strip()]
        return [items[0]] if items else [task.id]

    return [task.id]


def build_msg_match_query(
    msg_keywords: list[str],
    *,
    message_field: str = "msg",
    timestamp_gte: str = "now/d",
    timestamp_lte: str = "now",
    size: int = 1000,
) -> dict[str, Any]:
    """
    与现网 quotemonitor 一致的 ES 查询结构：

    bool.should: 单个 match(msg, task.id)；minimum_should_match=1
    bool.filter: @timestamp range
    sort: @timestamp asc
    """
    should = [{"match": {message_field: kw}} for kw in msg_keywords if kw]
    if not should:
        should = [{"match_all": {}}]

    return {
        "size": size,
        "sort": [{"@timestamp": {"order": "asc"}}],
        "query": {
            "bool": {
                "should": should,
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
    keywords = task_msg_keywords(task, cfg)
    return build_msg_match_query(
        keywords,
        message_field=es.message_field or "msg",
        timestamp_gte=es.timestamp_gte or "now/d",
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
