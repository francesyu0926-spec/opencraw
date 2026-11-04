from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from scripts.cron_task_monitor.env_file import load_env_file


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


if __name__ == "__main__":
    unittest.main()
