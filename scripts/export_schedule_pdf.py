#!/usr/bin/env python3
"""Export production monitor schedule and WeCom alert times to PDF."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "automated_writing"))

from scripts.cron_task_monitor.daily_boundary import _due_slot_minutes  # noqa: E402
from scripts.cron_task_monitor.schedule_config import load_monitor_schedule  # noqa: E402
from verify.tasks import TASKS  # noqa: E402

FONT_CANDIDATES = (
    Path(r"C:\Windows\Fonts\simhei.ttf"),
    Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf"),
)


def _pick_font() -> Path:
    for p in FONT_CANDIDATES:
        if p.is_file():
            return p
    raise FileNotFoundError(
        "未找到支持中文的字体文件（Windows 请确认 C:\\Windows\\Fonts\\simhei.ttf 存在）"
    )


def _fmt_minute(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def _chunk_list(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _hourly_times_in_window(start: str, end: str) -> list[str]:
    """Whole hours :00 within [start, end] (inclusive, minute precision)."""
    sh, sm = (int(x) for x in start.split(":", 1))
    eh, em = (int(x) for x in end.split(":", 1))
    start_m = sh * 60 + sm
    end_m = eh * 60 + em
    out: list[str] = []
    for h in range(24):
        m = h * 60
        if m % 60 != 0:
            continue
        if start_m <= end_m:
            if start_m <= m <= end_m:
                out.append(f"{h:02d}:00")
        else:
            if m >= start_m or m <= end_m:
                out.append(f"{h:02d}:00")
    return out


def _gather_lines() -> list[tuple[str, list[str]]]:
    prod_path = ROOT / "config/monitor_schedule.production.yaml"
    cfg = load_monitor_schedule(prod_path)
    cron = yaml.safe_load((ROOT / "config/cron_tasks.yaml").read_text(encoding="utf-8"))
    ws_cfg = yaml.safe_load((ROOT / "config/ws_monitor.yaml").read_text(encoding="utf-8"))
    wmon = yaml.safe_load((ROOT / "config/writing_monitor.yaml").read_text(encoding="utf-8"))

    sections: list[tuple[str, list[str]]] = []
    lines: list[str] = []
    lines.append(f"时区：{cfg.timezone}")
    lines.append(
        f"统一调度器：每 {cfg.dispatcher_interval_minutes} 分钟触发（:00/:05/:10/...）"
    )
    lines.append(f"配置来源：config/monitor_schedule.production.yaml")
    lines.append(f"文档生成时间：{datetime.now(ZoneInfo(cfg.timezone)).strftime('%Y-%m-%d %H:%M:%S')}")
    sections.append(("一、总览", lines))

    lines = []
    trial = cfg.notify_success_trial
    if trial and trial.enabled:
        jobs = "、".join(trial.jobs) if trial.jobs else "全部"
        lines.append(f"1. 整点企微（每 clock :00）：{jobs}")
        lines.append("   成功/失败均发 Markdown；本轮无 health/ws 时发「统一调度」心跳（health 机器人）")
    on_run = cfg.notify_on_run_complete
    if on_run:
        lines.append(f"2. 跑完即发：{'、'.join(on_run)}（每次 job 实际执行结束）")
    if cfg.notify_success_until:
        lines.append(
            f"3. 成功企微截止：{cfg.notify_success_until}（之后上述成功不发，失败仍发）"
        )
    lines.append("4. 日界企微：health / ws 每天首次、末次执行各 1 条（成败均发）")
    lines.append("   若与整点同一轮，只发整点一条，不重复")
    lines.append("5. 失败即时告警：health / ws 探活失败时立刻发（非整点也会发）")
    lines.append("6. 机器人：ELK / WS / Health / Writing 四个 webhook 分开配置")
    sections.append(("二、企微发送策略", lines))

    lines = []
    for jid, job in cfg.jobs.items():
        st = job.active_start or "00:00"
        en = job.active_end or "23:59"
        en_flag = "启用" if job.enabled else "停用"
        lines.append(
            f"· {jid}：每 {job.interval_minutes} 分钟 | 窗口 {st}~{en} | {en_flag}"
        )
        lines.append(f"  {job.description}")
    sections.append(("三、四大监控 Job 执行计划", lines))

    lines = []
    health = cfg.jobs["health"]
    ws_job = cfg.jobs["ws"]
    h_slots = _due_slot_minutes(health)
    w_slots = _due_slot_minutes(ws_job)
    if h_slots:
        lines.append(
            f"HTTP health 日界：首次 {_fmt_minute(h_slots[0])}，末次 {_fmt_minute(h_slots[-1])}"
        )
    if w_slots:
        lines.append(
            f"WebSocket 日界：首次 {_fmt_minute(w_slots[0])}，末次 {_fmt_minute(w_slots[-1])}"
        )
    h_hourly = _hourly_times_in_window(
        health.active_start or "09:00", health.active_end or "23:39"
    )
    w_hourly = _hourly_times_in_window(
        ws_job.active_start or "09:00", ws_job.active_end or "15:30"
    )
    for i, chunk in enumerate(_chunk_list(h_hourly, 8)):
        prefix = "HTTP 整点企微（约）：" if i == 0 else "    "
        lines.append(f"{prefix}{', '.join(chunk)}")
    for i, chunk in enumerate(_chunk_list(w_hourly, 8)):
        prefix = "WebSocket 整点企微（约）：" if i == 0 else "    "
        lines.append(f"{prefix}{', '.join(chunk)}")
    lines.append("说明：非整点成功一般不发企微；整点以外失败仍会告警。")
    sections.append(("四、HTTP / WebSocket 企微时间点", lines))

    sw = ws_cfg.get("skip_window") or {}
    lines = [
        f"探活跳过窗口：{sw.get('start', '-')} ~ {sw.get('end', '-')}（该时段不探活）",
        f"维持 {ws_cfg.get('hold_seconds', 30)}s 后断连；间隔 {int(ws_cfg.get('interval_seconds', 600)) // 60} 分钟",
    ]
    sections.append(("五、WebSocket 探活补充", lines))

    overrun = int(cron.get("overrun_after_end_threshold_minutes", 10))
    bw = cron.get("batch_window") or {}
    lines = [
        f"ELK 批次窗口：{bw.get('start', '00:00')} ~ {bw.get('end', '05:00')}",
        "调度：窗口内每 5 分钟检查是否有子任务处于监控窗，有则跑 ELK",
        f"企微：每次 ELK job 跑完即发（成功截止见 notify_success_until）",
        "",
        "子任务（计划执行 ~ 预期结束；监控至结束+{}min）：".format(overrun),
    ]
    for t in cron["tasks"]:
        lines.append(
            f"  · {t['name']}（{t['id']}）"
            f"  {t['scheduled_start']}~{t['expected_end']}"
        )
    sections.append(("六、ELK 任务与企微", lines))

    delay = int((wmon or {}).get("execution_delay_minutes") or 10)
    lines = [
        f"写稿窗口：07:00 ~ {(wmon or {}).get('active_end') or '20:30'}（仅工作日任务见下）",
        f"到点后 +{delay} 分钟，在 5 分钟槽内执行 1 次",
        "企微：每次 writing job 跑完即发（成功截止见 notify_success_until）",
        "",
        "任务到点 → 约执行 / 约发企微：",
    ]
    for t in TASKS:
        wd = "工作日" if t.weekdays_only else "每天"
        h, m = t.check_time.hour, t.check_time.minute + delay
        h += m // 60
        m %= 60
        lines.append(
            f"  · {t.name}：到点 {t.check_time.strftime('%H:%M')} → 约 {h:02d}:{m:02d} | {wd}"
        )
    sections.append(("七、自动化写稿与企微", lines))

    return sections


def _escape_paragraph(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _write_pdf(sections: list[tuple[str, list[str]]], out_path: Path) -> None:
    font_path = _pick_font()
    font_name = "ScheduleCJK"
    pdfmetrics.registerFont(TTFont(font_name, str(font_path)))

    title_style = ParagraphStyle(
        "DocTitle",
        fontName=font_name,
        fontSize=16,
        leading=22,
        spaceAfter=10,
    )
    heading_style = ParagraphStyle(
        "Section",
        fontName=font_name,
        fontSize=12,
        leading=18,
        spaceBefore=12,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "Body",
        fontName=font_name,
        fontSize=10,
        leading=15,
        spaceAfter=3,
        wordWrap="CJK",
    )

    story: list = [
        Paragraph(_escape_paragraph("opencraw 监控调度与企微发送时间表"), title_style),
    ]
    for title, lines in sections:
        story.append(Paragraph(_escape_paragraph(title), heading_style))
        for line in lines:
            if not line:
                story.append(Spacer(1, 4 * mm))
                continue
            story.append(Paragraph(_escape_paragraph(line), body_style))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="opencraw 监控调度与企微发送时间表",
    )
    doc.build(story)


def main() -> None:
    out = ROOT / "docs" / "opencraw-monitor-schedule.pdf"
    if len(sys.argv) > 1:
        out = Path(sys.argv[1]).resolve()
    sections = _gather_lines()
    _write_pdf(sections, out)
    print(f"OK: {out}")


if __name__ == "__main__":
    main()
