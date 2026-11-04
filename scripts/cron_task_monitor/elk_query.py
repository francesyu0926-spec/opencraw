"""兼容 import；请使用 quotes_es.build_mdimonitor_query。"""

from .quotes_es import build_mdimonitor_query as build_msg_match_query
from .quotes_es import build_query_from_config as build_task_search_body

__all__ = ["build_msg_match_query", "build_task_search_body"]
