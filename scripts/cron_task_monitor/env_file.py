from __future__ import annotations

import os
from pathlib import Path


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def _env_has_value(key: str) -> bool:
    return bool(os.environ.get(key, "").strip())


def _repo_roots(anchor: Path | None) -> list[Path]:
    """Candidate repo roots: from health config path, then cwd."""
    roots: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        resolved = path.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        roots.append(resolved)

    if anchor is not None:
        yaml_path = anchor if anchor.is_absolute() else Path.cwd() / anchor
        yaml_path = yaml_path.resolve()
        if yaml_path.parent.name == "config":
            add(yaml_path.parent.parent)

    add(Path.cwd())
    return roots


def load_env_file(path: Path) -> int:
    """Load KEY=VALUE lines from path into os.environ (missing keys only).

    Skips blank lines and # comments. Does not override non-empty env vars.
    Empty or whitespace-only values already in the environment are replaced.
    Returns the number of variables set.
    """
    if not path.is_file():
        return 0

    set_count = 0
    raw = path.read_text(encoding="utf-8-sig")
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().lstrip("\ufeff")
        if not key:
            continue
        if _env_has_value(key):
            continue
        os.environ[key] = _strip_optional_quotes(value.strip())
        set_count += 1
    return set_count


def load_health_monitor_env_files(*, config_path: Path | None = None) -> None:
    """Load config/health.env then config/wecom.env from repo root or cwd."""
    load_all_monitor_env_files(
        anchor=config_path,
        include_elk=False,
    )


def load_all_monitor_env_files(
    *,
    anchor: Path | None = None,
    include_elk: bool = True,
) -> None:
    """Load elk.env, health.env, wecom.env from repo root or cwd (in that order)."""
    rel_paths: list[Path] = []
    if include_elk:
        rel_paths.append(Path("config/elk.env"))
    rel_paths.extend((Path("config/health.env"), Path("config/wecom.env")))
    loaded: set[Path] = set()
    for root in _repo_roots(anchor):
        for rel in rel_paths:
            path = (root / rel).resolve()
            if path in loaded:
                continue
            loaded.add(path)
            load_env_file(path)
