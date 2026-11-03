"""
ES 查询逻辑对齐 mdimonitor/tests/test_quotes_es.py：

- bool.should: 单个 match(msg, task_code)
- minimum_should_match: 1
- filter: @timestamp gte/lte
- size 1000, sort @timestamp asc
"""

from __future__ import annotations

import os
import unittest

from scripts.cron_task_monitor.config_loader import load_config
from scripts.cron_task_monitor.quotes_es import (
    build_quotes_es_search_body,
    build_task_search_body,
    resolve_msg_keyword,
)


class TestQuotesEs(unittest.TestCase):
    def test_build_quotes_es_search_body_structure(self) -> None:
        body = build_quotes_es_search_body(
            "CBD_QUOT_CBND_STK",
            timestamp_gte="now-15m",
            timestamp_lte="now",
        )
        bool_q = body["query"]["bool"]
        self.assertEqual(len(bool_q["should"]), 1)
        self.assertEqual(
            bool_q["should"][0],
            {"match": {"msg": "CBD_QUOT_CBND_STK"}},
        )
        self.assertEqual(bool_q["minimum_should_match"], 1)
        ts = bool_q["filter"][0]["range"]["@timestamp"]
        self.assertEqual(ts["gte"], "now-15m")
        self.assertEqual(ts["lte"], "now")
        self.assertEqual(body["size"], 1000)
        self.assertEqual(body["sort"], [{"@timestamp": {"order": "asc"}}])

    def test_resolve_msg_keyword_default_task_id(self) -> None:
        cfg = load_config("config/cron_tasks.yaml")
        task = next(t for t in cfg.tasks if t.id == "CBD_QUOT_CBND_STK")
        self.assertEqual(resolve_msg_keyword(task), "CBD_QUOT_CBND_STK")

    def test_build_task_search_body_from_yaml(self) -> None:
        cfg = load_config("config/cron_tasks.yaml")
        task = cfg.tasks[0]
        body = build_task_search_body(cfg, task)
        keyword = body["query"]["bool"]["should"][0]["match"]["msg"]
        self.assertEqual(keyword, task.id)

    @unittest.skipUnless(
        os.environ.get("ELASTICSEARCH_PASSWORD"),
        "需要 ELASTICSEARCH_PASSWORD 才跑联调",
    )
    def test_live_search_smoke(self) -> None:
        from scripts.cron_task_monitor.elasticsearch_settings import resolve_elasticsearch
        from scripts.cron_task_monitor.quotes_es import search_index

        cfg = load_config("config/cron_tasks.yaml")
        settings = resolve_elasticsearch(cfg)
        assert settings is not None
        task = cfg.tasks[0]
        body = build_task_search_body(cfg, task)
        payload, err = search_index(settings, task.log_index_pattern, body, timeout=30)
        self.assertIsNone(err, err)
        assert payload is not None
        total = payload.get("hits", {}).get("total")
        if isinstance(total, dict):
            count = total.get("value", 0)
        else:
            count = int(total or 0)
        self.assertGreaterEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
