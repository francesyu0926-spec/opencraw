from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

from .ws_config import WsMonitorConfig


@dataclass
class WsProbeResult:
    ok: bool
    skipped: bool = False
    skip_reason: str = ""
    error: str = ""
    connected: bool = False
    hold_seconds: float = 0.0
    messages_received: int = 0
    sample_messages: list[str] = field(default_factory=list)


def in_skip_window(cfg: WsMonitorConfig, ref: datetime) -> tuple[bool, str]:
    tz = ZoneInfo(cfg.timezone)
    now = ref.astimezone(tz)
    sh, sm = (int(x) for x in cfg.skip_window_start.split(":", 1))
    eh, em = (int(x) for x in cfg.skip_window_end.split(":", 1))
    start = dt_time(sh, sm)
    end = dt_time(eh, em)
    t = now.time()
    if start <= end:
        if start <= t < end:
            return True, f"{cfg.skip_window_start}-{cfg.skip_window_end} 暂停 WS 监控"
    else:
        if t >= start or t < end:
            return True, f"{cfg.skip_window_start}-{cfg.skip_window_end} 暂停 WS 监控"
    return False, ""


async def _probe_async(cfg: WsMonitorConfig) -> WsProbeResult:
    import websockets

    result = WsProbeResult(ok=False)
    payload = json.dumps(cfg.subscribe_message, ensure_ascii=False)
    hold = max(30, int(cfg.hold_seconds))
    timeout = int(cfg.connect_timeout_seconds)

    try:
        async with websockets.connect(
            cfg.url,
            open_timeout=timeout,
            close_timeout=5,
            ping_interval=20,
            ping_timeout=10,
        ) as ws:
            result.connected = True
            await ws.send(payload)
            deadline = time.monotonic() + hold
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=min(5.0, remaining))
                    result.messages_received += 1
                    if len(result.sample_messages) < 3:
                        result.sample_messages.append(str(msg)[:500])
                except asyncio.TimeoutError:
                    continue
            result.hold_seconds = hold
            await ws.close()
    except Exception as e:
        result.error = str(e)
        return result

    if result.messages_received < 1:
        result.error = f"30 秒内未收到行情推送（subscribe 已发送）"
        return result

    result.ok = True
    return result


def run_ws_probe(cfg: WsMonitorConfig, ref: datetime | None = None) -> WsProbeResult:
    ref = ref or datetime.now(ZoneInfo(cfg.timezone))
    skipped, reason = in_skip_window(cfg, ref)
    if skipped:
        return WsProbeResult(ok=True, skipped=True, skip_reason=reason)

    try:
        return asyncio.run(_probe_async(cfg))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_probe_async(cfg))
        finally:
            loop.close()
