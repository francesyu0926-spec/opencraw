from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .elasticsearch_settings import ElasticsearchSettings, auth_headers, resolve_elasticsearch
from .models import ElasticsearchConfig, MonitorConfig

# 与 mdimonitor/tests/test_quotes_es.py query fixture 一致


def build_mdimonitor_query(
    msg_keywords: list[str],
    *,
    message_field: str = "msg",
    timestamp_gte: str = "now-15m",
    timestamp_lte: str = "now",
    size: int = 1000,
) -> dict[str, Any]:
    should = [{"match": {message_field: kw}} for kw in msg_keywords if kw]
    return {
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
        "size": size,
        "sort": [{"@timestamp": {"order": "asc"}}],
    }


def build_query_from_config(
    cfg: MonitorConfig,
    msg_keywords: list[str],
    ref: datetime | None = None,
) -> dict[str, Any]:
    from .time_window import resolve_query_timestamp_range

    es = cfg.elasticsearch or ElasticsearchConfig()
    gte, lte = resolve_query_timestamp_range(cfg, ref)
    return build_mdimonitor_query(
        msg_keywords,
        message_field=es.message_field or "msg",
        timestamp_gte=gte,
        timestamp_lte=lte,
        size=es.query_size or 1000,
    )


def default_indices(cfg: MonitorConfig) -> list[str]:
    es = cfg.elasticsearch or ElasticsearchConfig()
    if es.indices:
        return list(es.indices)
    return [
        "logstash-zxt-terminal-task-*",
        "logstash-sync-mongo-*",
    ]


def create_es_client(settings: ElasticsearchSettings):
    from elasticsearch import Elasticsearch

    hosts = [settings.url]
    kwargs: dict[str, Any] = {}
    if settings.username and settings.password:
        kwargs["basic_auth"] = (settings.username, settings.password)
    return Elasticsearch(hosts, **kwargs)


def search_hits(
    cfg: MonitorConfig,
    msg_keywords: list[str],
    ref: datetime | None = None,
) -> tuple[list[dict], str | None]:
    """返回 (hits, error)。优先 elasticsearch 库，失败时回退 urllib。"""
    settings = resolve_elasticsearch(cfg)
    if not settings:
        return [], "未配置 Elasticsearch"

    body = build_query_from_config(cfg, msg_keywords, ref)
    indices = default_indices(cfg)

    try:
        client = create_es_client(settings)
        result = client.search(index=indices, body=body)
        client.close()
        return result.get("hits", {}).get("hits") or [], None
    except Exception as exc:
        # urllib 回退
        import urllib.error
        import urllib.request

        index_path = ",".join(indices)
        url = f"{settings.url}/{index_path}/_search"
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=auth_headers(settings),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return payload.get("hits", {}).get("hits") or [], None
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:300]
            return [], f"HTTP {e.code}: {detail} (elasticsearch lib: {exc})"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e2:
            return [], f"{e2} (elasticsearch lib: {exc})"
