from __future__ import annotations

import unittest

from scripts.cron_task_monitor.config_loader import load_config
from scripts.cron_task_monitor.elk_query import build_task_search_body, task_msg_keywords
from scripts.cron_task_monitor.models import MonitorConfig, TaskDefinition


class ElkQueryTests(unittest.TestCase):
    def test_build_msg_match_query_structure(self) -> None:
        from scripts.cron_task_monitor.elk_query import build_msg_match_query

        body = build_msg_match_query(
            ["CBD_PUB_BOARD_INFO", "主题成分股"],
            message_field="msg",
            timestamp_gte="now-15m",
            timestamp_lte="now",
        )
        q = body["query"]["bool"]
        self.assertEqual(q["minimum_should_match"], 1)
        self.assertEqual(len(q["should"]), 2)  # build_msg_match_query 仍支持多关键字入参
        self.assertEqual(q["should"][0], {"match": {"msg": "CBD_PUB_BOARD_INFO"}})
        self.assertEqual(q["filter"][0]["range"]["@timestamp"]["gte"], "now-15m")
        self.assertEqual(body["size"], 1000)

    def test_task_keywords_from_config(self) -> None:
        cfg = load_config("config/cron_tasks.yaml")
        task = cfg.tasks[0]
        kws = task_msg_keywords(task, cfg)
        self.assertEqual(kws, ["CBD_PUB_BOARD_INFO"])

    def test_build_task_search_body(self) -> None:
        cfg = load_config("config/cron_tasks.yaml")
        body = build_task_search_body(cfg, cfg.tasks[0])
        self.assertIn("query", body)
        self.assertEqual(body["query"]["bool"]["should"][0]["match"]["msg"], "CBD_PUB_BOARD_INFO")


if __name__ == "__main__":
    unittest.main()
