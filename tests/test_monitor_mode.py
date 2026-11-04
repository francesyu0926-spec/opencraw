from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.cron_task_monitor.config_loader import load_config
from scripts.cron_task_monitor.evaluator import evaluate_task
from scripts.cron_task_monitor.models import TaskRunRecord


class MonitorModeTests(unittest.TestCase):
    def test_config_monitor_mode_elk(self) -> None:
        cfg = load_config("config/cron_tasks.yaml")
        self.assertEqual(cfg.monitor_mode, "elk")

    def test_elk_missing_log_message(self) -> None:
        cfg = load_config("config/cron_tasks.yaml")
        task = cfg.tasks[0]
        rec = TaskRunRecord(task_id=task.id, source="elk", status="missing_log")
        rec.raw_messages.append("elk: 0 hits index=logstash-sync-mongo-*")
        tz = ZoneInfo(cfg.timezone)
        now = datetime(2025, 11, 3, 8, 0, tzinfo=tz)
        alerts = evaluate_task(cfg, task, rec, now, monitor_mode="elk")
        self.assertEqual(len(alerts), 1)
        self.assertIn("ELK", alerts[0].message)
        self.assertNotIn("/usr/local", alerts[0].message)


if __name__ == "__main__":
    unittest.main()
