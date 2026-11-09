from __future__ import annotations

import json
import unittest

from scripts.cron_task_monitor.schedule_runner import _parse_captured_job_detail


class WritingDetailParseTests(unittest.TestCase):
    def test_parse_json_with_log_prefix(self) -> None:
        body = {
            "checked_at": "2026-11-09T07:40:00+08:00",
            "results": [{"task": "盘前情报", "status": "passed"}],
        }
        captured = f"2026-11-09 07:40:00 [INFO] log line\n{json.dumps(body, ensure_ascii=False)}"
        parsed = _parse_captured_job_detail(captured)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["results"][0]["task"], "盘前情报")


if __name__ == "__main__":
    unittest.main()
