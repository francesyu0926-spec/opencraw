from __future__ import annotations

import os
from dataclasses import dataclass

from .models import MonitorConfig


@dataclass
class ElasticsearchSettings:
    url: str
    username: str = ""
    password: str = ""


def resolve_elasticsearch(cfg: MonitorConfig) -> ElasticsearchSettings | None:
    """环境变量优先，其次为 config/cron_tasks.yaml 中的 elasticsearch 段。"""
    url = (
        os.environ.get("ELASTICSEARCH_URL")
        or os.environ.get("ES_URL")
        or (cfg.elasticsearch.url if cfg.elasticsearch else "")
    ).strip()
    if not url:
        return None

    username = (
        os.environ.get("ELASTICSEARCH_USER")
        or os.environ.get("ES_USERNAME")
        or (cfg.elasticsearch.username if cfg.elasticsearch else "")
    ).strip()
    password = os.environ.get("ELASTICSEARCH_PASSWORD") or os.environ.get(
        "ES_PASSWORD", ""
    ).strip()

    return ElasticsearchSettings(url=url.rstrip("/"), username=username, password=password)


def auth_headers(settings: ElasticsearchSettings) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("ELASTICSEARCH_API_KEY")
    if api_key:
        headers["Authorization"] = f"ApiKey {api_key}"
        return headers
    if settings.username and settings.password:
        import base64

        token = base64.b64encode(
            f"{settings.username}:{settings.password}".encode()
        ).decode()
        headers["Authorization"] = f"Basic {token}"
    return headers
