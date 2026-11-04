from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.cron_task_monitor.config_loader import load_config
from scripts.cron_task_monitor.evaluator import evaluate_task
from scripts.cron_task_monitor.log_parser import analyze_local_task, parse_lines_for_task
from scripts.cron_task_monitor.models import TaskDefinition


REPO_ROOT = Path(__file__).resolve().parents[1]


class CronTaskMonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = load_config(REPO_ROOT / "config" / "cron_tasks.yaml")
        self.tz = ZoneInfo(self.cfg.timezone)

    def test_structured_log_success(self) -> None:
        task = TaskDefinition(
            id="CBD_PUB_BOARD_INFO",
            name="主题成分股",
            scheduled_start="01:00",
            expected_end="01:03",
            log_index_pattern="logstash-sync-mongo-*",
            server="test",
            log_dir="/tmp",
        )
        lines = Path(REPO_ROOT / "tests/fixtures/sample_task.log").read_text().splitlines()
        record = parse_lines_for_task(task, lines, self.tz, self.cfg.monitor_log_prefix)
        self.assertEqual(record.status, "success")
        self.assertIsNotNone(record.started_at)
        self.assertIsNotNone(record.ended_at)

        now = datetime(2025, 11, 3, 1, 4, tzinfo=self.tz)
        alerts = evaluate_task(self.cfg, task, record, now)
        self.assertEqual(alerts, [])

    def test_late_start_alert(self) -> None:
        task = TaskDefinition(
            id="CBD_BOARD_INFO",
            name="主题",
            scheduled_start="01:00",
            expected_end="01:05",
            log_index_pattern="",
            server="test",
            log_dir="/tmp",
        )
        lines = [
            "2025-11-03 01:07:00 [TASK_MONITOR] task=CBD_BOARD_INFO event=start ts=2025-11-03T01:07:00+08:00",
            "2025-11-03 01:08:00 [TASK_MONITOR] task=CBD_BOARD_INFO event=end status=success ts=2025-11-03T01:08:00+08:00",
        ]
        record = parse_lines_for_task(task, lines, self.tz, self.cfg.monitor_log_prefix)
        now = datetime(2025, 11, 3, 1, 8, tzinfo=self.tz)
        alerts = evaluate_task(self.cfg, task, record, now)
        kinds = {a.kind.value for a in alerts}
        self.assertIn("late_start", kinds)

    def test_no_start_alert(self) -> None:
        task = self.cfg.tasks[0]
        record = parse_lines_for_task(task, [], self.tz, self.cfg.monitor_log_prefix)
        now = datetime(2025, 11, 3, 1, 6, tzinfo=self.tz)
        alerts = evaluate_task(self.cfg, task, record, now)
        self.assertTrue(any(a.kind.value == "no_start" for a in alerts))

    def test_local_log_dir_integration(self) -> None:
        fixture = REPO_ROOT / "tests/fixtures/sample_task.log"
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            (log_dir / "sync.log").write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
            task = TaskDefinition(
                id="CBD_PUB_BOARD_INFO",
                name="主题成分股",
                scheduled_start="01:00",
                expected_end="01:03",
                log_index_pattern="",
                server="test",
                log_dir=str(log_dir),
            )
            now = datetime(2025, 11, 3, 1, 3, tzinfo=self.tz)
            record = analyze_local_task(task, self.tz, now, self.cfg.monitor_log_prefix)
            self.assertEqual(record.status, "success")


if __name__ == "__main__":
    unittest.main()
