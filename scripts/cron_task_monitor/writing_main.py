from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

from .env_file import find_repo_root, load_writing_monitor_env_files


def _ensure_verify_import_path(repo_root: Path) -> Path:
    aw_root = repo_root / "scripts" / "automated_writing"
    aw_str = str(aw_root)
    if aw_str not in sys.path:
        sys.path.insert(0, aw_str)
    return aw_root


def run_writing_monitor(
    config_path: Path,
    *,
    at: str | None,
    as_json: bool,
    dry_run: bool,
    notify: bool,
    no_notify: bool,
) -> int:
    """Run automated_writing verify (due tasks only). Failures notify via SFC_WECHAT_WEBHOOK_URL."""
    _ = notify  # verify CLI notifies on failure when webhook is set
    repo_root = find_repo_root(config_path)
    load_writing_monitor_env_files(repo_root=repo_root)
    aw_root = _ensure_verify_import_path(repo_root)
    if not (aw_root / "verify").is_dir():
        print(f"automated_writing verify package not found: {aw_root / 'verify'}", file=sys.stderr)
        return 2

    if dry_run:
        if as_json:
            print('{"mode":"writing_monitor","dry_run":true,"message":"skipped"}')
        else:
            print("writing_monitor dry_run: skipped")
        return 0

    from verify.cli import main as verify_main

    argv = ["run", "--due"]
    if no_notify:
        argv.append("--no-notify")
    if at:
        # verify uses wall-clock; scheduled --at is not wired into verify tasks yet
        pass

    if as_json:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = verify_main(argv)
        text = buf.getvalue().strip()
        if text:
            print(text)
        return code

    return verify_main(argv)
