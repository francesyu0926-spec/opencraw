"""兼容旧 import；实现已迁至 quotes_es（对齐 mdimonitor）。"""

from __future__ import annotations

from typing import Any

from .models import MonitorConfig, TaskDefinition
from typing import Any

from .quotes_es import (
    build_quotes_es_search_body,
    build_task_search_body,
    extract_log_line,
    resolve_msg_keyword as task_msg_keyword,
)


def build_msg_match_query(
    msg_keywords: str | list[str],
    **kwargs: Any,
) -> dict[str, Any]:
    if isinstance(msg_keywords, list):
        keyword = msg_keywords[0] if msg_keywords else ""
    else:
        keyword = msg_keywords
    return build_quotes_es_search_body(keyword, **kwargs)


def task_msg_keywords(task: TaskDefinition, cfg: MonitorConfig) -> list[str]:
    return [task_msg_keyword(task)]


__all__ = [
    "build_msg_match_query",
    "build_task_search_body",
    "extract_log_line",
    "task_msg_keywords",
]
