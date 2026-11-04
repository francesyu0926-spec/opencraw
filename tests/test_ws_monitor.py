from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.cron_task_monitor.ws_config import load_ws_config
from scripts.cron_task_monitor.ws_probe import in_skip_window


class WsMonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = load_ws_config("config/ws_monitor.yaml")

    def test_skip_window_morning(self) -> None:
        tz = ZoneInfo(self.cfg.timezone)
        ref = datetime(2025, 11, 3, 8, 45, tzinfo=tz)
        skipped, reason = in_skip_window(self.cfg, ref)
        self.assertTrue(skipped)
        self.assertIn("08:30", reason)

    def test_not_skipped_outside_window(self) -> None:
        tz = ZoneInfo(self.cfg.timezone)
        ref = datetime(2025, 11, 3, 10, 0, tzinfo=tz)
        skipped, _ = in_skip_window(self.cfg, ref)
        self.assertFalse(skipped)

    def test_subscribe_payload(self) -> None:
        self.assertEqual(self.cfg.subscribe_message.get("action"), "subscribe")
        self.assertEqual(self.cfg.subscribe_message.get("topic"), "quote")
        self.assertGreaterEqual(self.cfg.hold_seconds, 30)
        self.assertEqual(self.cfg.message_must_contain, "quoteItems")
        self.assertEqual(self.cfg.interval_seconds, 600)
        self.assertEqual(self.cfg.wecom_webhook_env, "WECOM_WEBHOOK_URL_WS")


if __name__ == "__main__":
    unittest.main()
