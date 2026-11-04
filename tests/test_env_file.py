from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from scripts.cron_task_monitor.env_file import (
    HealthEnvLoadReport,
    credential_env_hint,
    find_repo_root,
    load_env_file,
    load_health_monitor_env_files,
)


class EnvFileTests(unittest.TestCase):
    def test_load_env_file_sets_vars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / "health.env"
            env_path.write_text(
                "# comment\n"
                "\n"
                "QUOTES_LOGIN_CODE=from_file\n"
                'QUOTES_LOGIN_PASSWORD="quoted_secret"\n',
                encoding="utf-8",
            )
            keys = ("QUOTES_LOGIN_CODE", "QUOTES_LOGIN_PASSWORD")
            saved = {k: os.environ.pop(k, None) for k in keys}
            try:
                n = load_env_file(env_path)
                self.assertEqual(n, 2)
                self.assertEqual(os.environ["QUOTES_LOGIN_CODE"], "from_file")
                self.assertEqual(os.environ["QUOTES_LOGIN_PASSWORD"], "quoted_secret")
            finally:
                for k in keys:
                    if saved[k] is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = saved[k]

    def test_load_env_file_does_not_override_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / "health.env"
            env_path.write_text("QUOTES_LOGIN_CODE=from_file\n", encoding="utf-8")
            os.environ["QUOTES_LOGIN_CODE"] = "already_set"
            try:
                n = load_env_file(env_path)
                self.assertEqual(n, 0)
                self.assertEqual(os.environ["QUOTES_LOGIN_CODE"], "already_set")
            finally:
                os.environ.pop("QUOTES_LOGIN_CODE", None)

    def test_load_env_file_overrides_empty_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / "health.env"
            env_path.write_text(
                "QUOTES_LOGIN_CODE=from_file\n"
                "QUOTES_LOGIN_PASSWORD=secret\n",
                encoding="utf-8",
            )
            os.environ["QUOTES_LOGIN_CODE"] = ""
            os.environ["QUOTES_LOGIN_PASSWORD"] = "   "
            keys = ("QUOTES_LOGIN_CODE", "QUOTES_LOGIN_PASSWORD")
            try:
                n = load_env_file(env_path)
                self.assertEqual(n, 2)
                self.assertEqual(os.environ["QUOTES_LOGIN_CODE"], "from_file")
                self.assertEqual(os.environ["QUOTES_LOGIN_PASSWORD"], "secret")
            finally:
                for k in keys:
                    os.environ.pop(k, None)

    def test_load_env_file_utf8_bom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / "health.env"
            env_path.write_bytes(
                b"\xef\xbb\xbfQUOTES_LOGIN_CODE=bom_key\n"
                b"QUOTES_LOGIN_PASSWORD=bom_val\n"
            )
            keys = ("QUOTES_LOGIN_CODE", "QUOTES_LOGIN_PASSWORD")
            saved = {k: os.environ.pop(k, None) for k in keys}
            try:
                n = load_env_file(env_path)
                self.assertEqual(n, 2)
                self.assertEqual(os.environ["QUOTES_LOGIN_CODE"], "bom_key")
            finally:
                for k in keys:
                    if saved[k] is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = saved[k]

    def test_find_repo_root_from_module(self) -> None:
        root = find_repo_root()
        self.assertTrue((root / "config" / "health_monitor.yaml").is_file())

    def test_credential_env_hint_when_file_missing(self) -> None:
        report = HealthEnvLoadReport(
            repo_root="/repo",
            health_env_path="/repo/config/health.env",
            health_env_exists=False,
            health_env_keys_loaded=0,
            wecom_env_path="/repo/config/wecom.env",
            wecom_env_exists=False,
            wecom_env_keys_loaded=0,
        )
        hint = credential_env_hint(
            report,
            login_code_env="QUOTES_LOGIN_CODE",
            login_password_env="QUOTES_LOGIN_PASSWORD",
            token_env="QUOTES_HEALTH_TOKEN",
        )
        self.assertIn("未找到", hint)
        self.assertIn("health.env.example", hint)

    def test_load_health_monitor_env_ignores_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "scripts" / "cron_task_monitor").mkdir(parents=True)
            (root / "config" / "health.env").write_text(
                "QUOTES_LOGIN_CODE=from_repo_root\n", encoding="utf-8"
            )
            keys = ("QUOTES_LOGIN_CODE",)
            saved = {k: os.environ.pop(k, None) for k in keys}
            orig_cwd = os.getcwd()
            try:
                os.chdir("/tmp")
                load_health_monitor_env_files(root)
                self.assertEqual(os.environ["QUOTES_LOGIN_CODE"], "from_repo_root")
            finally:
                os.chdir(orig_cwd)
                for k in keys:
                    if saved[k] is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = saved[k]


if __name__ == "__main__":
    unittest.main()
