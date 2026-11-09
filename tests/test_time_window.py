from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.cron_task_monitor.config_loader import load_config
from scripts.cron_task_monitor.time_window import resolve_query_timestamp_range


class TimeWindowTests(unittest.TestCase):
    def test_rolling_in_batch_15m(self) -> None:
        cfg = load_config("config/cron_tasks.yaml")
        tz = ZoneInfo(cfg.timezone)
        ref = datetime(2025, 11, 3, 1, 30, tzinfo=tz)
        gte, lte = resolve_query_timestamp_range(cfg, ref)
        self.assertIn("2025-11-03T01:15:00", gte)
        self.assertIn("2025-11-03T01:30:00", lte)

    def test_schedule_config(self) -> None:
        cfg = load_config("config/cron_tasks.yaml")
        self.assertEqual(cfg.query_time_mode, "rolling_in_batch")
        self.assertEqual(cfg.schedule_interval_minutes, 15)

    def test_after_batch_window_still_rolling_15m(self) -> None:
        cfg = load_config("config/cron_tasks.yaml")
        tz = ZoneInfo(cfg.timezone)
        ref = datetime(2025, 11, 3, 15, 50, tzinfo=tz)
        gte, lte = resolve_query_timestamp_range(cfg, ref)
        self.assertLess(gte, lte)
        self.assertIn("2025-11-03T15:35:00", gte)
        self.assertIn("2025-11-03T15:50:00", lte)


if __name__ == "__main__":
    unittest.main()
