from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs

from scripts.cron_task_monitor.health_config import load_health_config
from scripts.cron_task_monitor.health_probe import (
    _cache_is_fresh,
    _collect_status_issues,
    extract_login_token,
    run_health_probe,
)

_LOGIN_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.c2lnbmF0dXJl"
_OTHER_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJyZWZyZXNoIjp0cnVlfQ.cmVmcmVzaA"


def _urlopen_cm(status: int, payload: bytes) -> Mock:
    resp = Mock()
    resp.getcode.return_value = status
    resp.read.return_value = payload
    cm = Mock()
    cm.__enter__ = Mock(return_value=resp)
    cm.__exit__ = Mock(return_value=False)
    return cm


def _health_up() -> bytes:
    return json.dumps(
        {"status": "UP", "checks": [{"id": "a", "status": "UP"}]}
    ).encode()


def _write_cache(path: Path, token: str, obtained_at: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "token": token,
                "obtained_at": obtained_at.astimezone(timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )


class HealthMonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = load_health_config("config/health_monitor.yaml")
        self._tmp = tempfile.TemporaryDirectory()
        self.cfg.token_cache_path = str(
            Path(self._tmp.name) / "health.token.cache.json"
        )
        self._saved_env: dict[str, str | None] = {}
        for key in (
            self.cfg.token_env,
            self.cfg.login_code_env,
            self.cfg.login_password_env,
        ):
            self._saved_env[key] = os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    def _use_login_env(self, password: str = "not-a-real-secret") -> None:
        os.environ[self.cfg.login_code_env] = "login-code"
        os.environ[self.cfg.login_password_env] = password

    def test_config(self) -> None:
        cfg = load_health_config("config/health_monitor.yaml")
        self.assertIn("health", cfg.url)
        self.assertEqual(cfg.method, "POST")
        self.assertEqual(cfg.expected_status, "UP")
        self.assertEqual(cfg.wecom_webhook_env, "WECOM_WEBHOOK_URL_HEALTH")
        self.assertEqual(
            cfg.login_url,
            "https://terminal.sfccn.com/terminal/zxt-web/login/pwd",
        )
        self.assertEqual(cfg.login_code_env, "QUOTES_LOGIN_CODE")
        self.assertEqual(cfg.login_password_env, "QUOTES_LOGIN_PASSWORD")
        self.assertEqual(cfg.token_env, "QUOTES_HEALTH_TOKEN")
        self.assertEqual(cfg.login_interval_hours, 12)
        self.assertEqual(cfg.token_cache_path, "config/health.token.cache.json")

    def test_cache_fresh_boundary(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.assertTrue(
            _cache_is_fresh(now - timedelta(hours=12) + timedelta(seconds=1), now, 12)
        )
        self.assertFalse(_cache_is_fresh(now - timedelta(hours=12), now, 12))

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

    def test_missing_credentials(self) -> None:
        result = run_health_probe(self.cfg)
        self.assertFalse(result.ok)
        self.assertIn(self.cfg.token_env, result.error)
        self.assertIn(self.cfg.login_code_env, result.error)
        self.assertIn(self.cfg.login_password_env, result.error)

    def test_partial_login_env_does_not_use_static_token(self) -> None:
        os.environ[self.cfg.login_code_env] = "login-code"
        os.environ[self.cfg.token_env] = "static-token"
        result = run_health_probe(self.cfg)
        self.assertFalse(result.ok)
        self.assertIn(self.cfg.login_password_env, result.error)
        self.assertNotIn("static-token", result.error)

    def test_extract_login_token_prefers_jwt_field(self) -> None:
        body = {
            "token": "not-a-jwt",
            "data": {"accessToken": _LOGIN_JWT, "refreshToken": _OTHER_JWT},
            "message": "ok",
        }
        self.assertEqual(extract_login_token(body), _LOGIN_JWT)

    def test_extract_login_token_scans_when_named_fields_are_absent(self) -> None:
        body = {"code": 0, "payload": {"session": _LOGIN_JWT}}
        self.assertEqual(extract_login_token(body), _LOGIN_JWT)
        self.assertIsNone(extract_login_token({"message": "no token here"}))

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
        result = run_health_probe(self.cfg)

        self.assertTrue(result.ok)
        self.assertEqual(result.root_status, "UP")
        self.assertEqual(result.check_count, 1)
        self.assertEqual(mock_urlopen.call_count, 1)
        called = mock_urlopen.call_args.args[0]
        self.assertEqual(called.full_url, self.cfg.url)
        self.assertEqual(called.get_header("Token"), "test-token")
        self.assertFalse(Path(self.cfg.token_cache_path).exists())

    @patch("scripts.cron_task_monitor.health_probe.urllib.request.urlopen")
    def test_login_then_health_up(self, mock_urlopen) -> None:
        login_body = json.dumps(
            {"code": 0, "data": {"token": _LOGIN_JWT}}
        ).encode()
        health_body = json.dumps(
            {
                "status": "UP",
                "checks": [
                    {"id": "cbd-quote-ws", "status": "UP"},
                    {"id": "cbd-quote-master", "status": "UP"},
                ],
            }
        ).encode()
        mock_urlopen.side_effect = [
            _urlopen_cm(200, login_body),
            _urlopen_cm(200, health_body),
        ]
        os.environ[self.cfg.login_code_env] = "login-code"
        os.environ[self.cfg.login_password_env] = "not-a-real-secret"
        os.environ[self.cfg.token_env] = "static-token"

        result = run_health_probe(self.cfg)

        self.assertTrue(result.ok)
        self.assertEqual(result.http_status, 200)
        self.assertEqual(result.root_status, "UP")
        self.assertEqual(result.check_count, 2)
        self.assertEqual(mock_urlopen.call_count, 2)

        login_req = mock_urlopen.call_args_list[0].args[0]
        self.assertEqual(login_req.full_url, self.cfg.login_url)
        self.assertEqual(login_req.get_method(), "POST")
        self.assertEqual(
            login_req.get_header("Content-type"),
            "application/x-www-form-urlencoded",
        )
        form = parse_qs(login_req.data.decode())
        self.assertEqual(form["loginCode"], ["login-code"])
        self.assertEqual(form["password"], ["not-a-real-secret"])

        health_req = mock_urlopen.call_args_list[1].args[0]
        self.assertEqual(health_req.full_url, self.cfg.url)
        self.assertEqual(health_req.get_header("Token"), _LOGIN_JWT)
        self.assertNotEqual(health_req.get_header("Token"), "static-token")
        self.assertNotIn("not-a-real-secret", result.error)
        cached = Path(self.cfg.token_cache_path).read_text(encoding="utf-8")
        self.assertNotIn("not-a-real-secret", cached)
        saved = json.loads(cached)
        self.assertEqual(saved["token"], _LOGIN_JWT)
        self.assertIn("obtained_at", saved)

    @patch("scripts.cron_task_monitor.health_probe.urllib.request.urlopen")
    def test_cache_hit_skips_login(self, mock_urlopen) -> None:
        path = Path(self.cfg.token_cache_path)
        _write_cache(
            path,
            _OTHER_JWT,
            datetime.now(timezone.utc) - timedelta(hours=1),
        )
        before = path.read_text(encoding="utf-8")
        mock_urlopen.return_value = _urlopen_cm(200, _health_up())
        self._use_login_env()

        result = run_health_probe(self.cfg)

        self.assertTrue(result.ok)
        self.assertEqual(result.root_status, "UP")
        self.assertEqual(mock_urlopen.call_count, 1)
        req = mock_urlopen.call_args.args[0]
        self.assertEqual(req.full_url, self.cfg.url)
        self.assertNotEqual(req.full_url, self.cfg.login_url)
        self.assertEqual(req.get_header("Token"), _OTHER_JWT)
        self.assertEqual(path.read_text(encoding="utf-8"), before)
        self.assertNotIn("not-a-real-secret", result.error)

    @patch("scripts.cron_task_monitor.health_probe.urllib.request.urlopen")
    def test_stale_cache_calls_login(self, mock_urlopen) -> None:
        path = Path(self.cfg.token_cache_path)
        _write_cache(
            path,
            _OTHER_JWT,
            datetime.now(timezone.utc) - timedelta(hours=13),
        )
        mock_urlopen.side_effect = [
            _urlopen_cm(200, json.dumps({"data": {"token": _LOGIN_JWT}}).encode()),
            _urlopen_cm(200, _health_up()),
        ]
        self._use_login_env()

        result = run_health_probe(self.cfg)

        self.assertTrue(result.ok)
        self.assertEqual(mock_urlopen.call_count, 2)
        login_req = mock_urlopen.call_args_list[0].args[0]
        health_req = mock_urlopen.call_args_list[1].args[0]
        self.assertEqual(login_req.full_url, self.cfg.login_url)
        self.assertEqual(health_req.full_url, self.cfg.url)
        self.assertEqual(health_req.get_header("Token"), _LOGIN_JWT)
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["token"], _LOGIN_JWT)
        self.assertNotIn("not-a-real-secret", path.read_text(encoding="utf-8"))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    @patch("scripts.cron_task_monitor.health_probe.urllib.request.urlopen")
    def test_health_401_refreshes_token(self, mock_urlopen) -> None:
        path = Path(self.cfg.token_cache_path)
        _write_cache(
            path,
            _OTHER_JWT,
            datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        mock_urlopen.side_effect = [
            urllib.error.HTTPError(
                self.cfg.url,
                401,
                "Unauthorized",
                hdrs=None,
                fp=io.BytesIO(b"denied"),
            ),
            _urlopen_cm(200, json.dumps({"data": {"token": _LOGIN_JWT}}).encode()),
            _urlopen_cm(200, _health_up()),
        ]
        self._use_login_env()

        result = run_health_probe(self.cfg)

        self.assertTrue(result.ok)
        self.assertEqual(result.http_status, 200)
        self.assertEqual(mock_urlopen.call_count, 3)
        first, login_req, retry = (
            call.args[0] for call in mock_urlopen.call_args_list
        )
        self.assertEqual(first.full_url, self.cfg.url)
        self.assertEqual(first.get_header("Token"), _OTHER_JWT)
        self.assertEqual(login_req.full_url, self.cfg.login_url)
        self.assertEqual(retry.full_url, self.cfg.url)
        self.assertEqual(retry.get_header("Token"), _LOGIN_JWT)
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["token"], _LOGIN_JWT)
        self.assertNotIn("not-a-real-secret", result.error)
        self.assertNotIn(_LOGIN_JWT, result.error)

    @patch("scripts.cron_task_monitor.health_probe.urllib.request.urlopen")
    def test_401_retries_health_once_then_stops(self, mock_urlopen) -> None:
        mock_urlopen.side_effect = [
            _urlopen_cm(200, json.dumps({"data": {"token": _OTHER_JWT}}).encode()),
            urllib.error.HTTPError(
                self.cfg.url,
                401,
                "Unauthorized",
                hdrs=None,
                fp=io.BytesIO(b"denied"),
            ),
            _urlopen_cm(200, json.dumps({"data": {"token": _LOGIN_JWT}}).encode()),
            urllib.error.HTTPError(
                self.cfg.url,
                403,
                "Forbidden",
                hdrs=None,
                fp=io.BytesIO(b"still-denied"),
            ),
        ]
        self._use_login_env()

        result = run_health_probe(self.cfg)

        self.assertFalse(result.ok)
        self.assertEqual(result.http_status, 403)
        self.assertEqual(mock_urlopen.call_count, 4)
        urls = [call.args[0].full_url for call in mock_urlopen.call_args_list]
        self.assertEqual(
            urls,
            [self.cfg.login_url, self.cfg.url, self.cfg.login_url, self.cfg.url],
        )
        self.assertEqual(
            mock_urlopen.call_args_list[3].args[0].get_header("Token"),
            _LOGIN_JWT,
        )
        self.assertNotIn("not-a-real-secret", result.error)
        self.assertNotIn(_LOGIN_JWT, result.error)

    @patch("scripts.cron_task_monitor.health_probe.urllib.request.urlopen")
    def test_unreadable_cache_calls_login(self, mock_urlopen) -> None:
        path = Path(self.cfg.token_cache_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{", encoding="utf-8")
        mock_urlopen.side_effect = [
            _urlopen_cm(200, json.dumps({"token": _LOGIN_JWT}).encode()),
            _urlopen_cm(200, _health_up()),
        ]
        self._use_login_env()

        result = run_health_probe(self.cfg)

        self.assertTrue(result.ok)
        self.assertEqual(mock_urlopen.call_args_list[0].args[0].full_url, self.cfg.login_url)
        self.assertEqual(
            mock_urlopen.call_args_list[1].args[0].get_header("Token"),
            _LOGIN_JWT,
        )

    @patch("scripts.cron_task_monitor.health_probe.urllib.request.urlopen")
    def test_login_http_failure(self, mock_urlopen) -> None:
        secret = "0123456789abcdef0123456789abcdef"
        mock_urlopen.side_effect = urllib.error.HTTPError(
            self.cfg.login_url,
            401,
            "Unauthorized",
            hdrs=None,
            fp=io.BytesIO(
                json.dumps(
                    {"password": secret, "token": _LOGIN_JWT, "msg": "bad"}
                ).encode()
            ),
        )
        os.environ[self.cfg.login_code_env] = "login-code"
        os.environ[self.cfg.login_password_env] = secret

        result = run_health_probe(self.cfg)

        self.assertFalse(result.ok)
        self.assertIn("401", result.error)
        self.assertNotIn(secret, result.error)
        self.assertNotIn(_LOGIN_JWT, result.error)
        self.assertNotIn("login-code", result.error)
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("scripts.cron_task_monitor.health_probe.urllib.request.urlopen")
    def test_login_json_without_token(self, mock_urlopen) -> None:
        secret = "fedcba9876543210fedcba9876543210"
        mock_urlopen.return_value = _urlopen_cm(
            200,
            json.dumps(
                {"code": 1, "message": f"rejected {secret}", "data": None}
            ).encode(),
        )
        os.environ[self.cfg.login_code_env] = "login-code"
        os.environ[self.cfg.login_password_env] = secret

        result = run_health_probe(self.cfg)

        self.assertFalse(result.ok)
        self.assertIn("未找到 Token", result.error)
        self.assertNotIn(secret, result.error)
        self.assertNotIn("login-code", result.error)
        self.assertEqual(mock_urlopen.call_count, 1)


if __name__ == "__main__":
    unittest.main()
