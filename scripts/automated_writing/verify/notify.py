from __future__ import annotations

import os
from typing import Iterable

import requests

from verify.checker import CheckResult, CheckStatus
from verify.logger import get_logger
from verify.tasks import now, today_str

DEFAULT_TIMEOUT = 10


def webhook_url() -> str | None:
    url = os.getenv("SFC_WECHAT_WEBHOOK_URL", "").strip()
    return url or None


def _format_failure_lines(results: Iterable[CheckResult]) -> list[str]:
    lines: list[str] = []
    for item in results:
        if item.status not in (CheckStatus.FAILED, CheckStatus.ERROR):
            continue
        status = "失败" if item.status == CheckStatus.FAILED else "错误"
        line = f"> **{item.task}** [{status}]：{item.message}"
        if item.matched_title:
            line += f"\n> 匹配标题：{item.matched_title}"
        lines.append(line)
    return lines


def build_alert_content(results: Iterable[CheckResult], source: str = "run") -> str | None:
    lines = _format_failure_lines(results)
    if not lines:
        return None

    checked_at = now().strftime("%Y-%m-%d %H:%M:%S")
    header = (
        f"### 自动化写稿任务监测告警\n"
        f"> 日期：{today_str()}\n"
        f"> 时间：{checked_at}\n"
        f"> 来源：{source}\n"
    )
    return header + "\n".join(lines)


def send_wechat_markdown(content: str) -> bool:
    url = webhook_url()
    if not url:
        get_logger().warning("未配置 SFC_WECHAT_WEBHOOK_URL，跳过企微通知")
        return False

    logger = get_logger()
    try:
        response = requests.post(
            url,
            json={"msgtype": "markdown", "markdown": {"content": content}},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errcode") != 0:
            logger.error("企微通知发送失败: %s", payload.get("errmsg") or payload)
            return False
        logger.info("企微通知已发送")
        return True
    except requests.RequestException as exc:
        logger.error("企微通知请求失败: %s", exc)
        return False


def notify_failures(results: Iterable[CheckResult], source: str = "run") -> bool:
    content = build_alert_content(results, source=source)
    if not content:
        return False
    return send_wechat_markdown(content)


def notify_failure(result: CheckResult, source: str = "daemon") -> bool:
    return notify_failures([result], source=source)
