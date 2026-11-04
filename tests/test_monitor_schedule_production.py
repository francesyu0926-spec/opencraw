from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.cron_task_monitor.schedule_config import load_monitor_schedule
from scripts.cron_task_monitor.schedule_runner import is_job_due


class ProductionScheduleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = load_monitor_schedule("config/monitor_schedule.production.yaml")
        self.tz = ZoneInfo(self.cfg.timezone)

    def _at(self, hhmm: str) -> datetime:
        h, m = (int(x) for x in hhmm.split(":", 1))
        return datetime(2026, 11, 4, h, m, tzinfo=self.tz)

    def test_dispatcher_five_minutes(self) -> None:
        self.assertEqual(self.cfg.dispatcher_interval_minutes, 5)

    def test_elk_midnight_window(self) -> None:
        job = self.cfg.jobs["elk"]
        self.assertTrue(is_job_due(self._at("00:00"), job))
        self.assertTrue(is_job_due(self._at("05:00"), job))
        self.assertFalse(is_job_due(self._at("05:15"), job))
        self.assertFalse(is_job_due(self._at("09:00"), job))

    def test_ws_business_window(self) -> None:
        job = self.cfg.jobs["ws"]
        self.assertEqual(job.interval_minutes, 10)
        self.assertFalse(is_job_due(self._at("08:45"), job))
        self.assertTrue(is_job_due(self._at("09:00"), job))
        self.assertTrue(is_job_due(self._at("15:30"), job))
        self.assertFalse(is_job_due(self._at("15:45"), job))
        self.assertFalse(is_job_due(self._at("09:05"), job))
        self.assertTrue(is_job_due(self._at("09:10"), job))

    def test_health_extended_window(self) -> None:
        job = self.cfg.jobs["health"]
        self.assertFalse(is_job_due(self._at("08:45"), job))
        self.assertTrue(is_job_due(self._at("09:00"), job))
        self.assertTrue(is_job_due(self._at("23:30"), job))
        self.assertFalse(is_job_due(self._at("23:45"), job))
        self.assertFalse(is_job_due(self._at("02:00"), job))


if __name__ == "__main__":
    unittest.main()
