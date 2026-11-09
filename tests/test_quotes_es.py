"""对齐 mdimonitor/tests/test_quotes_es.py 的三类断言。"""

from __future__ import annotations

import os
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.cron_task_monitor.config_loader import load_config
from scripts.cron_task_monitor.mdimonitor_checks import (
    check_task_ended_late,
    check_task_failed,
    check_tasks_started_late,
    run_mdimonitor_checks,
)
from scripts.cron_task_monitor.quote_utils import msg_keywords_from_config
from scripts.cron_task_monitor.quotes_es import build_mdimonitor_query


class TestQuotesEsQuery(unittest.TestCase):
    def test_query_fixture_shape(self) -> None:
        keywords = ["CBD_QUOT_CBND_STK", "CBD_PUB_BOAR_INFO"]
        body = build_mdimonitor_query(keywords)
        bool_q = body["query"]["bool"]
        self.assertEqual(len(bool_q["should"]), 2)
        self.assertEqual(bool_q["minimum_should_match"], 1)
        ts = bool_q["filter"][0]["range"]["@timestamp"]
        self.assertEqual(ts["gte"], "now-15m")  # build_mdimonitor_query 默认；配置里为 now/d
        self.assertEqual(ts["lte"], "now")


class TestQuotesEsRules(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = load_config("config/cron_tasks.yaml")
        self.tz = ZoneInfo(self.cfg.timezone)
        self.ref = datetime(2025, 11, 3, 2, 0, tzinfo=self.tz)
        self.keywords = msg_keywords_from_config(self.cfg)

    def test_tasks_started_late(self) -> None:
        hits = [
            {
                "_source": {
                    "msg": "开始执行任务: CBD_PUB_BOAR_INFO,执行时间：2025-11-03 01:07:00",
                }
            }
        ]
        alerts = check_tasks_started_late(self.cfg, hits, self.ref)
        self.assertTrue(alerts)
        self.assertIn("未按时启动", alerts[0].message)

    def test_task_ended_late(self) -> None:
        hits = [
            {
                "_source": {
                    "msg": "开始执行任务: CBD_PUB_BOAR_INFO,执行时间：2025-11-03 01:00:01",
                }
            },
            {
                "_source": {
                    "msg": "任务执行完成:CBD_PUB_BOAR_INFO,耗时：900秒",
                }
            },
        ]
        alerts = check_task_ended_late(self.cfg, hits, self.ref)
        self.assertTrue(alerts)
        self.assertIn("执行超时", alerts[0].message)

    def test_task_failed(self) -> None:
        hits = [{"_source": {"msg": "CBD_QUOT_CBND_STK 执行失败，请检查"}}]
        alerts = check_task_failed(self.cfg, hits, self.keywords)
        self.assertTrue(alerts)
        self.assertIn("执行失败", alerts[0].message)

    def test_all_clear(self) -> None:
        hits = [
            {
                "_source": {
                    "msg": "开始执行任务: CBD_PUB_BOAR_INFO,执行时间：2025-11-03 01:00:05",
                }
            },
            {"_source": {"msg": "任务执行完成:CBD_PUB_BOAR_INFO,耗时：120秒"}},
        ]
        alerts = run_mdimonitor_checks(self.cfg, hits, self.keywords, self.ref)
        self.assertEqual(alerts, [])


@unittest.skipUnless(os.environ.get("ELASTICSEARCH_PASSWORD"), "需要 ES 密码")
class TestQuotesEsLive(unittest.TestCase):
    def test_search_smoke(self) -> None:
        from scripts.cron_task_monitor.quotes_es import search_hits

        cfg = load_config("config/cron_tasks.yaml")
        kws = msg_keywords_from_config(cfg)
        hits, err, _qtr = search_hits(cfg, kws)
        self.assertIsNone(err, err)
        self.assertIsInstance(hits, list)


if __name__ == "__main__":
    unittest.main()
