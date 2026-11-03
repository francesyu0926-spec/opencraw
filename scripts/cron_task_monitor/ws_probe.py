from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import logging.config
import time
from dataclasses import dataclass, field
from datetime import datetime, time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

from .cwechatbot import WeChatBot
from .ws_config import WsMonitorConfig

wssClientLogger = logging.getLogger("wssClientLogger")


def _setup_logging() -> None:
    conf = Path("logging.conf")
    if conf.is_file():
        logging.config.fileConfig(conf, disable_existing_loggers=False)
    elif not wssClientLogger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(name)s %(levelname)s %(message)s",
        )


@dataclass
class WsProbeResult:
    ok: bool
    skipped: bool = False
    skip_reason: str = ""
    error: str = ""
    connected: bool = False
    hold_seconds: float = 0.0
    messages_received: int = 0
    quote_items_ok: bool = False
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


async def schedule_disconnect(websocket, is_connected: bool, hold_seconds: float) -> None:
    try:
        await asyncio.sleep(hold_seconds)
        if is_connected and websocket:
            await websocket.close()
    except asyncio.CancelledError:
        wssClientLogger.info("Disconnect scheduler is cancelled")


async def _probe_async(
    cfg: WsMonitorConfig,
    wechatbot: WeChatBot | None = None,
) -> WsProbeResult:
    import websockets

    result = WsProbeResult(ok=False)
    payload = json.dumps(cfg.subscribe_message, ensure_ascii=False)
    hold = max(30, int(cfg.hold_seconds))
    timeout = int(cfg.connect_timeout_seconds)
    must_contain = cfg.message_must_contain or "quoteItems"

    wssClientLogger.info(
        "Task starts - %s",
        time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())),
    )

    is_connected = False
    scheduled_task: asyncio.Task | None = None

    try:
        async with websockets.connect(cfg.url, open_timeout=timeout) as websocket:
            wssClientLogger.info("Connected successfully. Start listening...")
            is_connected = True
            result.connected = True
            scheduled_task = asyncio.create_task(
                schedule_disconnect(websocket, is_connected, hold)
            )

            await websocket.send(payload)

            try:
                async for message in websocket:
                    result.messages_received += 1
                    text = str(message)
                    wssClientLogger.info("Received: %s", text[:500])
                    if len(result.sample_messages) < 3:
                        result.sample_messages.append(text[:500])

                    if must_contain not in text:
                        error_message = f"Wrong message received: {text[:500]}"
                        wssClientLogger.error(error_message)
                        result.error = error_message
                        if wechatbot:
                            wechatbot.send_text(error_message)
                        return result

                    result.quote_items_ok = True

            except websockets.exceptions.ConnectionClosedOK:
                wssClientLogger.info("Connection closed normally")
            except websockets.exceptions.ConnectionClosedError as error:
                error_message = (
                    f"Connection closed with error: {error.code}, {error.reason}"
                )
                wssClientLogger.error(error_message)
                result.error = error_message
                if wechatbot:
                    wechatbot.send_text(error_message)
                return result
            except Exception as e:
                error_message = f"Unexpected error: {e}"
                wssClientLogger.error(error_message)
                result.error = error_message
                if wechatbot:
                    wechatbot.send_text(error_message)
                return result
            finally:
                is_connected = False
                if scheduled_task:
                    scheduled_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await scheduled_task

    except Exception as e:
        error_message = f"Unexpected error: {e}"
        wssClientLogger.error(error_message)
        result.error = error_message
        if wechatbot:
            wechatbot.send_text(error_message)
        return result

    result.hold_seconds = hold
    if not result.quote_items_ok:
        result.error = f"{hold} 秒内未收到含 {must_contain} 的行情推送"
        return result

    result.ok = True
    wssClientLogger.info(
        "Task ended - %s",
        time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())),
    )
    return result


async def websocket_client_loop(cfg: WsMonitorConfig) -> None:
    """长驻进程：每轮探活后 sleep interval_seconds（默认 600），对齐 schedule_task。"""
    _setup_logging()
    wssClientLogger.info("Scheduled task begins ...")
    wechatbot = WeChatBot.from_env(cfg.wecom_webhook_env)
    interval = max(60, int(cfg.interval_seconds))

    while True:
        now = datetime.now(ZoneInfo(cfg.timezone))
        skipped, reason = in_skip_window(cfg, now)
        if skipped:
            wssClientLogger.info("Skip: %s", reason)
            await asyncio.sleep(interval)
            continue

        await _probe_async(cfg, wechatbot if wechatbot.webhook_url else None)

        wssClientLogger.info(
            "Reconnect after %s seconds ...",
            interval,
        )
        await asyncio.sleep(interval)


def run_ws_probe(
    cfg: WsMonitorConfig,
    ref: datetime | None = None,
    *,
    use_wechat_on_error: bool = False,
) -> WsProbeResult:
    _setup_logging()
    ref = ref or datetime.now(ZoneInfo(cfg.timezone))
    skipped, reason = in_skip_window(cfg, ref)
    if skipped:
        return WsProbeResult(ok=True, skipped=True, skip_reason=reason)

    bot = (
        WeChatBot.from_env(cfg.wecom_webhook_env)
        if use_wechat_on_error
        else None
    )

    try:
        return asyncio.run(_probe_async(cfg, bot))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_probe_async(cfg, bot))
        finally:
            loop.close()


def run_ws_daemon(cfg: WsMonitorConfig) -> None:
    try:
        asyncio.run(websocket_client_loop(cfg))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(websocket_client_loop(cfg))
        finally:
            loop.close()
