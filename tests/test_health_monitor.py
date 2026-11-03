from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from scripts.cron_task_monitor.health_config import load_health_config
from scripts.cron_task_monitor.health_probe import (
    _collect_status_issues,
    run_health_probe,
)


class HealthMonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = load_health_config("config/health_monitor.yaml")

    def test_config(self) -> None:
        self.assertIn("health", self.cfg.url)
        self.assertEqual(self.cfg.method, "POST")
        self.assertEqual(self.cfg.expected_status, "UP")
        self.assertEqual(self.cfg.wecom_webhook_env, "WECOM_WEBHOOK_URL_HEALTH")

    def test_collect_all_up(self) -> None:
        body = {
            "status": "UP",
            "checks": [
                {"id": "cbd-quote-ws", "status": "UP"},
                {"id": "cbd-quote-master", "status": "UP"},
            ],
        }
        root, down, count = _collect_status_issues(body, expected="UP")
        self.assertEqual(root, "UP")
        self.assertEqual(down, [])
        self.assertEqual(count, 2)

    def test_collect_down_component(self) -> None:
        body = {
            "status": "UP",
            "checks": [{"id": "cbd-quote-ws", "status": "DOWN"}],
        }
        _, down, _ = _collect_status_issues(body, expected="UP")
        self.assertEqual(down, ["cbd-quote-ws=DOWN"])

    def test_collect_root_down(self) -> None:
        body = {"status": "DOWN", "checks": []}
        root, down, _ = _collect_status_issues(body, expected="UP")
        self.assertEqual(root, "DOWN")
        self.assertEqual(down, [])

    def test_missing_token(self) -> None:
        os.environ.pop(self.cfg.token_env, None)
        result = run_health_probe(self.cfg)
        self.assertFalse(result.ok)
        self.assertIn(self.cfg.token_env, result.error)

    @patch("scripts.cron_task_monitor.health_probe.urllib.request.urlopen")
    def test_probe_ok(self, mock_urlopen) -> None:
        payload = json.dumps(
            {
                "status": "UP",
                "checks": [{"id": "a", "status": "UP"}],
            }
        ).encode()
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.getcode.return_value = 200
        mock_resp.read.return_value = payload

        os.environ[self.cfg.token_env] = "test-token"
        try:
            result = run_health_probe(self.cfg)
        finally:
            os.environ.pop(self.cfg.token_env, None)

        self.assertTrue(result.ok)
        self.assertEqual(result.root_status, "UP")
        self.assertEqual(result.check_count, 1)


if __name__ == "__main__":
    unittest.main()
