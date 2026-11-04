from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from scripts.cron_task_monitor.env_file import (
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

    def test_load_health_monitor_env_ignores_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "repo"
            root.mkdir()
            (root / "config").mkdir()
            (root / "scripts" / "cron_task_monitor").mkdir(parents=True)
            (root / "config" / "health.env").write_text(
                "QUOTES_LOGIN_CODE=from_repo_root\n", encoding="utf-8"
            )
            other_cwd = base / "elsewhere"
            other_cwd.mkdir()
            keys = ("QUOTES_LOGIN_CODE",)
            saved = {k: os.environ.pop(k, None) for k in keys}
            orig_cwd = os.getcwd()
            try:
                os.chdir(other_cwd)
                load_health_monitor_env_files(repo_root=root)
                self.assertEqual(os.environ["QUOTES_LOGIN_CODE"], "from_repo_root")
            finally:
                os.chdir(orig_cwd)
                for k in keys:
                    if saved[k] is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = saved[k]

    def test_load_health_monitor_env_from_config_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "config"
            config_dir.mkdir()
            (root / "scripts" / "cron_task_monitor").mkdir(parents=True)
            (config_dir / "health.env").write_text(
                "QUOTES_LOGIN_CODE=anchored\n", encoding="utf-8"
            )
            (config_dir / "health_monitor.yaml").write_text(
                "url: https://example.test/health\n", encoding="utf-8"
            )
            saved = os.environ.pop("QUOTES_LOGIN_CODE", None)
            try:
                load_health_monitor_env_files(
                    config_path=root / "config" / "health_monitor.yaml"
                )
                self.assertEqual(os.environ.get("QUOTES_LOGIN_CODE"), "anchored")
            finally:
                if saved is None:
                    os.environ.pop("QUOTES_LOGIN_CODE", None)
                else:
                    os.environ["QUOTES_LOGIN_CODE"] = saved


if __name__ == "__main__":
    unittest.main()
