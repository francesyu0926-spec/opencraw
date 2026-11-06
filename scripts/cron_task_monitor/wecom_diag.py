from __future__ import annotations

import json
import sys
from typing import Any

from .notifier import (
    DEFAULT_WEBHOOK_ENV_ELK,
    DEFAULT_WEBHOOK_ENV_HEALTH,
    DEFAULT_WEBHOOK_ENV_WS,
    DEFAULT_WEBHOOK_ENV_WRITING,
    resolve_webhook_url,
    resolve_webhook_url_health,
    resolve_webhook_url_ws,
    resolve_webhook_url_writing,
    send_text_message,
)

_CHANNELS: tuple[tuple[str, str, Any], ...] = (
    ("elk", DEFAULT_WEBHOOK_ENV_ELK, resolve_webhook_url),
    ("ws", DEFAULT_WEBHOOK_ENV_WS, resolve_webhook_url_ws),
    ("health", DEFAULT_WEBHOOK_ENV_HEALTH, resolve_webhook_url_health),
    ("writing", DEFAULT_WEBHOOK_ENV_WRITING, resolve_webhook_url_writing),
)


def webhook_status() -> dict[str, dict[str, str | bool]]:
    out: dict[str, dict[str, str | bool]] = {}
    for channel, env_name, resolver in _CHANNELS:
        url = resolver()
        out[channel] = {
            "env": env_name,
            "configured": bool(url),
            "url_hint": (url[:48] + "…") if url and len(url) > 48 else (url or ""),
        }
    return out


def warn_missing_webhooks(*, to_stderr: bool = True) -> list[str]:
    missing: list[str] = []
    for channel, env_name, resolver in _CHANNELS:
        if not resolver():
            missing.append(f"{channel} ({env_name})")
    if missing and to_stderr:
        print(
            "WARN: 未配置企微 webhook: " + ", ".join(missing),
            file=sys.stderr,
        )
    return missing


def run_check_wecom(*, send_test: bool, as_json: bool) -> int:
    status = webhook_status()
    tests: dict[str, dict] = {}
    exit_code = 0

    if send_test:
        for channel, _, resolver in _CHANNELS:
            if not resolver():
                tests[channel] = {"skipped": True, "reason": "未配置 webhook"}
                continue
            ok, msg = send_text_message(
                f"【opencraw 企微自检】channel={channel} 发送测试",
                channel=channel,
            )
            tests[channel] = {"ok": ok, "message": msg}
            if not ok:
                exit_code = 1

    payload = {"webhooks": status, "send_test": send_test}
    if tests:
        payload["test_results"] = tests

    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for ch, info in status.items():
            flag = "OK" if info["configured"] else "MISSING"
            print(f"{ch}: {flag} ({info['env']})")
        if send_test:
            for ch, tr in tests.items():
                print(f"  test {ch}: {tr}")

    if not send_test and any(not v["configured"] for v in status.values()):
        exit_code = 1
    return exit_code
