from __future__ import annotations

import atexit
import os
import sys
from pathlib import Path

from verify.logger import _log_dir

_LOCK_HANDLE = None


def _lock_path() -> Path:
    return _log_dir() / ".daemon.lock"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import subprocess

        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            check=False,
        )
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def acquire_daemon_lock() -> None:
    global _LOCK_HANDLE
    lock_path = _lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if lock_path.exists():
        try:
            old_pid = int(lock_path.read_text(encoding="utf-8").strip())
        except ValueError:
            old_pid = 0
        if _pid_alive(old_pid):
            print(f"已有守护进程在运行 (PID={old_pid})，请勿重复启动", file=sys.stderr)
            raise SystemExit(1)
        lock_path.unlink(missing_ok=True)

    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print("已有守护进程在运行，请勿重复启动", file=sys.stderr)
        raise SystemExit(1) from None

    _LOCK_HANDLE = fd
    os.write(fd, str(os.getpid()).encode("utf-8"))

    def _release() -> None:
        global _LOCK_HANDLE
        if _LOCK_HANDLE is not None:
            os.close(_LOCK_HANDLE)
            _LOCK_HANDLE = None
        lock_path.unlink(missing_ok=True)

    atexit.register(_release)


def release_daemon_lock() -> None:
    global _LOCK_HANDLE
    lock_path = _lock_path()
    if _LOCK_HANDLE is not None:
        os.close(_LOCK_HANDLE)
        _LOCK_HANDLE = None
    lock_path.unlink(missing_ok=True)
