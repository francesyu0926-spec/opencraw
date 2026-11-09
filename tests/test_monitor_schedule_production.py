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
        d = self.cfg.dispatcher_interval_minutes
        self.assertTrue(is_job_due(self._at("00:00"), job, d))
        self.assertTrue(is_job_due(self._at("05:00"), job, d))
        self.assertFalse(is_job_due(self._at("05:15"), job))
        self.assertFalse(is_job_due(self._at("09:00"), job))

    def test_ws_business_window(self) -> None:
        job = self.cfg.jobs["ws"]
        self.assertEqual(job.interval_minutes, 10)
        self.assertFalse(is_job_due(self._at("08:45"), job))
        self.assertTrue(is_job_due(self._at("09:00"), job))
        self.assertTrue(is_job_due(self._at("15:30"), job))
        self.assertFalse(is_job_due(self._at("15:45"), job))
        self.assertTrue(
            is_job_due(self._at("09:05"), job, self.cfg.dispatcher_interval_minutes)
        )
        self.assertTrue(is_job_due(self._at("09:10"), job))
        self.assertFalse(
            is_job_due(self._at("09:33"), job, self.cfg.dispatcher_interval_minutes)
        )

    def test_health_catch_up_on_dispatcher_tick(self) -> None:
        job = self.cfg.jobs["health"]
        d = self.cfg.dispatcher_interval_minutes
        self.assertFalse(is_job_due(self._at("09:33"), job, d))
        self.assertTrue(is_job_due(self._at("09:35"), job, d))

    def test_health_extended_window(self) -> None:
        job = self.cfg.jobs["health"]
        self.assertFalse(is_job_due(self._at("08:45"), job))
        self.assertTrue(is_job_due(self._at("09:00"), job))
        self.assertTrue(is_job_due(self._at("23:30"), job))
        self.assertFalse(is_job_due(self._at("23:45"), job))
        self.assertFalse(is_job_due(self._at("02:00"), job))

    def test_ws_and_writing_weekdays_only_in_config(self) -> None:
        self.assertTrue(self.cfg.jobs["ws"].weekdays_only)
        self.assertTrue(self.cfg.jobs["writing"].weekdays_only)
        self.assertFalse(self.cfg.jobs["elk"].weekdays_only)
        self.assertFalse(self.cfg.jobs["health"].weekdays_only)

    def test_weekend_skips_ws_and_writing_jobs(self) -> None:
        import io
        import json
        from contextlib import redirect_stdout
        from pathlib import Path

        from scripts.cron_task_monitor.schedule_runner import run_scheduled_monitors

        buf = io.StringIO()
        with redirect_stdout(buf):
            run_scheduled_monitors(
                Path("config/monitor_schedule.production.yaml"),
                at="2026-11-07T10:00:00+08:00",
                as_json=True,
                dry_run=True,
                notify=False,
                no_notify=True,
            )
        payload = json.loads(buf.getvalue())
        by_reason = {s["job"]: s["reason"] for s in payload["jobs_skipped"]}
        self.assertEqual(by_reason.get("ws"), "weekend")
        self.assertEqual(by_reason.get("writing"), "weekend")
        self.assertNotIn("ws", payload["jobs_run"])
        self.assertNotIn("writing", payload["jobs_run"])


if __name__ == "__main__":
    unittest.main()
