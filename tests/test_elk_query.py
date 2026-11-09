from __future__ import annotations

import unittest

from scripts.cron_task_monitor.config_loader import load_config
from scripts.cron_task_monitor.elk_query import build_msg_match_query, build_task_search_body
from scripts.cron_task_monitor.quote_utils import msg_keywords_from_config


class ElkQueryTests(unittest.TestCase):
    def test_build_msg_match_query_structure(self) -> None:
        body = build_msg_match_query(
            ["CBD_PUB_BOAR_INFO_2", "CBD_QUOT_CBND_STK_2"],
            message_field="msg",
            timestamp_gte="now-15m",
            timestamp_lte="now",
        )
        q = body["query"]["bool"]
        self.assertEqual(q["minimum_should_match"], 1)
        self.assertEqual(len(q["should"]), 2)

    def test_build_task_search_body(self) -> None:
        cfg = load_config("config/cron_tasks.yaml")
        kws = msg_keywords_from_config(cfg)
        body = build_task_search_body(cfg, kws)
        self.assertIn("query", body)
        self.assertGreaterEqual(len(body["query"]["bool"]["should"]), 1)


if __name__ == "__main__":
    unittest.main()
