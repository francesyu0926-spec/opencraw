from __future__ import annotations

import json
import urllib.error
import urllib.request

from .elasticsearch_settings import auth_headers, resolve_elasticsearch
from .models import MonitorConfig


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
