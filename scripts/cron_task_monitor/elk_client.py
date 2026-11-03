from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from .elasticsearch_settings import resolve_elasticsearch
from .log_parser import parse_lines_for_task
from .models import ElasticsearchConfig, MonitorConfig, TaskDefinition, TaskRunRecord
from .quotes_es import (
    build_task_search_body,
    hits_to_log_lines,
    search_index,
)


def check_elasticsearch(cfg: MonitorConfig) -> tuple[bool, str]:
    import urllib.error
    import urllib.request

    from .elasticsearch_settings import auth_headers

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

    payload, err = search_index(settings, index, body)
    if err:
        rec = TaskRunRecord(task_id=task.id, source="elk", status="missing_log")
        rec.raw_messages.append(f"elasticsearch {err}")
        return rec

    field = es_cfg.message_field or "msg"
    lines = hits_to_log_lines(payload or {}, field)

    if not lines:
        rec = TaskRunRecord(task_id=task.id, source="elk", status="missing_log")
        rec.raw_messages.append(
            f"elk: 0 hits index={index} query={json.dumps(body['query'], ensure_ascii=False)[:300]}"
        )
        return rec

    record = parse_lines_for_task(task, lines, tz, cfg.monitor_log_prefix)
    record.source = "elk"
    return record
