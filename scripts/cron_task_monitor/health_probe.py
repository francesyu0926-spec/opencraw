from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .health_config import HealthMonitorConfig


@dataclass
class HealthProbeResult:
    ok: bool
    error: str = ""
    http_status: int | None = None
    root_status: str = ""
    down_checks: list[str] = field(default_factory=list)
    check_count: int = 0
    raw_snippet: str = ""


def _collect_status_issues(
    body: Any,
    *,
    expected: str,
) -> tuple[str, list[str], int]:
    """Return (root_status, down_check_ids, check_count)."""
    if not isinstance(body, dict):
        raise ValueError("health JSON 根节点须为 object")

    root = str(body.get("status") or "")
    down: list[str] = []
    checks = body.get("checks")
    count = 0
    if isinstance(checks, list):
        for item in checks:
            if not isinstance(item, dict):
                continue
            count += 1
            cid = str(item.get("id") or f"check#{count}")
            st = str(item.get("status") or "")
            if st != expected:
                down.append(f"{cid}={st or '(missing)'}")

    return root, down, count


def run_health_probe(cfg: HealthMonitorConfig) -> HealthProbeResult:
    token = os.environ.get(cfg.token_env, "").strip()
    if not token:
        return HealthProbeResult(
            ok=False,
            error=f"未配置环境变量 {cfg.token_env}（行情 health 接口 Token）",
        )

    headers = {
        "Token": token,
        "Content-Type": "application/json; charset=utf-8",
    }
    req = urllib.request.Request(
        cfg.url,
        data=b"",
        headers=headers,
        method=cfg.method,
    )

    try:
        with urllib.request.urlopen(req, timeout=cfg.request_timeout_seconds) as resp:
            http_status = resp.getcode()
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        return HealthProbeResult(
            ok=False,
            error=f"HTTP {e.code}: {detail}",
            http_status=e.code,
            raw_snippet=detail,
        )
    except (urllib.error.URLError, TimeoutError) as e:
        return HealthProbeResult(ok=False, error=str(e))

    snippet = raw[:800]
    try:
        body = json.loads(raw)
    except json.JSONDecodeError as e:
        return HealthProbeResult(
            ok=False,
            error=f"响应非 JSON: {e}",
            http_status=http_status,
            raw_snippet=snippet,
        )

    try:
        root, down, count = _collect_status_issues(
            body, expected=cfg.expected_status
        )
    except ValueError as e:
        return HealthProbeResult(
            ok=False,
            error=str(e),
            http_status=http_status,
            raw_snippet=snippet,
        )

    result = HealthProbeResult(
        ok=True,
        http_status=http_status,
        root_status=root,
        down_checks=down,
        check_count=count,
        raw_snippet=snippet,
    )

    if root != cfg.expected_status:
        result.ok = False
        result.error = (
            f"总状态 {root or '(missing)'} != {cfg.expected_status}"
        )
        return result

    if down:
        result.ok = False
        result.error = "以下组件非 UP: " + ", ".join(down)
        return result

    return result
