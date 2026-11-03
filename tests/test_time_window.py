from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.cron_task_monitor.config_loader import load_config
from scripts.cron_task_monitor.time_window import resolve_query_timestamp_range


class TimeWindowTests(unittest.TestCase):
    def test_batch_window_after_five_am(self) -> None:
        cfg = load_config("config/cron_tasks.yaml")
        ref = datetime(2025, 11, 3, 16, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        gte, lte = resolve_query_timestamp_range(cfg, ref)
        self.assertTrue(gte.startswith("2025-11-03T00:00:00"))
        self.assertTrue(lte.startswith("2025-11-03T05:00:00"))
        self.assertIn("+08:00", gte)

    def test_batch_window_during_run(self) -> None:
        cfg = load_config("config/cron_tasks.yaml")
        ref = datetime(2025, 11, 3, 2, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        gte, lte = resolve_query_timestamp_range(cfg, ref)
        self.assertTrue(lte.startswith("2025-11-03T02:30:00"))


if __name__ == "__main__":
    unittest.main()
