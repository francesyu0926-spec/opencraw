from __future__ import annotations

import os
from typing import Iterable

import requests

from verify.checker import CheckResult, CheckStatus
from verify.logger import get_logger
from verify.tasks import now

DEFAULT_TIMEOUT = 10


def webhook_url() -> str | None:
    url = os.getenv("SFC_WECHAT_WEBHOOK_URL", "").strip()
    return url or None


def build_alert_content(results: Iterable[CheckResult], source: str = "run") -> str | None:
    failed = [
        item
        for item in results
        if item.status in (CheckStatus.FAILED, CheckStatus.ERROR)
    ]
    if not failed:
        return None

    checked_at = now().strftime("%Y-%m-%d %H:%M:%S")
    first = failed[0]
    status = "失败" if first.status == CheckStatus.FAILED else "错误"
    note = f"{first.task} [{status}]：{first.message}"
    return (
        f"### 自动化写稿监控测试报告\n"
        f"> 时间：{checked_at}\n"
        f"\n"
        f'结论：<font color="warning">未通过</font>\n'
        f"> 说明：{note}"
    )


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
