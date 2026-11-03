from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class WeChatBot:
    """与 mdimonitor cwechatbot 一致：企业微信机器人发文本。"""

    def __init__(self, webhook_url: str | None) -> None:
        self.webhook_url = (webhook_url or "").strip()

    @classmethod
    def from_env(cls, env_var: str) -> WeChatBot:
        return cls(os.environ.get(env_var, "").strip() or None)

    def send_text(self, content: str) -> bool:
        if not self.webhook_url or not content:
            return False
        payload = {"msgtype": "text", "text": {"content": content}}
        req = urllib.request.Request(
            self.webhook_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return body.get("errcode") == 0
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            return False
