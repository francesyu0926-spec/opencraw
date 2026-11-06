from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.cron_task_monitor.schedule_config import load_monitor_schedule
from scripts.cron_task_monitor.schedule_runner import is_job_due


class MonitorScheduleRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = load_monitor_schedule("config/monitor_schedule.yaml")
        self.tz = ZoneInfo(self.cfg.timezone)

    def _at(self, hhmm: str) -> datetime:
        h, m = (int(x) for x in hhmm.split(":", 1))
        return datetime(2026, 11, 4, h, m, tzinfo=self.tz)

    def test_health_every_five_minutes(self) -> None:
        job = self.cfg.jobs["health"]
        self.assertTrue(is_job_due(self._at("10:00"), job))
        self.assertTrue(is_job_due(self._at("10:05"), job))
        self.assertFalse(is_job_due(self._at("10:03"), job))

    def test_ws_every_ten_minutes(self) -> None:
        job = self.cfg.jobs["ws"]
        d = self.cfg.dispatcher_interval_minutes
        self.assertTrue(is_job_due(self._at("10:10"), job))
        self.assertTrue(is_job_due(self._at("10:05"), job, d))
        self.assertFalse(is_job_due(self._at("10:03"), job, d))

    def test_elk_window_and_interval(self) -> None:
        job = self.cfg.jobs["elk"]
        self.assertTrue(is_job_due(self._at("00:00"), job))
        self.assertTrue(is_job_due(self._at("05:00"), job))
        self.assertFalse(is_job_due(self._at("05:15"), job))
        self.assertFalse(is_job_due(self._at("10:00"), job))
        self.assertFalse(is_job_due(self._at("00:07"), job))

    def test_dispatcher_interval_config(self) -> None:
        self.assertEqual(self.cfg.dispatcher_interval_minutes, 5)


if __name__ == "__main__":
    unittest.main()
