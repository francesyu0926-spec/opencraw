#!/usr/bin/env python3
"""Export Table 1: four jobs — window, interval, WeCom — to PDF."""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

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
        "未找到中文字体（Windows 需 simhei.ttf；Linux 可装文泉驿或 Noto CJK）"
    )


def _fmt_minute(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def _safe_xml_text(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _parse_hhmm(s: str) -> dt_time:
    h, m = (int(x) for x in s.strip().split(":", 1))
    return dt_time(h, m)


def _writing_wecom_html(
    *,
    delay: int,
    slot: int,
    active_end_str: str,
    until_s: str,
    tz_name: str,
) -> str:
    """Time-only WeCom copy: per configured writing subtask windows."""
    tz = ZoneInfo(tz_name)
    cap = _parse_hhmm(active_end_str)
    cap_m = cap.hour * 60 + cap.minute
    ref = date(2026, 1, 5)  # Monday

    parts: list[str] = [
        "· <b>每个写稿子任务</b>仅在「到点时刻 + 延迟分钟数」起的执行窗内、且与统一调度 5 分钟轮对齐时跑一轮检查",
        f"· 延迟 <b>{delay}</b> 分钟，执行槽 <b>{slot}</b> 分钟；日界截止 <b>{_safe_xml_text(active_end_str)}</b>",
        f"· 企微：<b>该轮检查结束后</b>即发；成功类发至 <b>{until_s}</b>（之后仅失败仍发）",
        "· 各子任务约执行窗（窗内完成即发；多为工作日）：",
    ]
    for t in TASKS:
        wd = "工作日" if t.weekdays_only else "每天"
        start = datetime.combine(ref, t.check_time, tzinfo=tz) + timedelta(minutes=delay)
        end = start + timedelta(minutes=max(1, slot))
        end_cap = datetime.combine(ref, cap, tzinfo=tz)
        if end > end_cap:
            end = end_cap
        if start >= end:
            continue
        # skip if window entirely after active_end
        st_m = start.hour * 60 + start.minute
        if st_m > cap_m:
            continue
        parts.append(
            f"　· {_safe_xml_text(t.name)}：到点 {t.check_time.strftime('%H:%M')} → "
            f"窗 {_safe_xml_text(start.strftime('%H:%M'))}～{_safe_xml_text(end.strftime('%H:%M'))}（{wd}）"
        )
    return "<br/>".join(parts)


def _make_table(
    data: list[list],
    col_widths: list[float],
    font_name: str,
    *,
    header_row: int = 1,
) -> Table:
    style_cmds = [
        ("FONT", (0, 0), (-1, -1), font_name, 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cccccc")),
    ]
    if header_row > 0:
        style_cmds.extend(
            [
                ("BACKGROUND", (0, 0), (-1, header_row - 1), colors.HexColor("#4472C4")),
                ("TEXTCOLOR", (0, 0), (-1, header_row - 1), colors.whitesmoke),
                ("FONT", (0, 0), (-1, header_row - 1), font_name, 9),
            ]
        )
    if len(data) > header_row:
        style_cmds.append(
            (
                "ROWBACKGROUNDS",
                (0, header_row),
                (-1, -1),
                [colors.white, colors.HexColor("#F5F5F5")],
            )
        )
    t = Table(data, colWidths=col_widths, repeatRows=header_row)
    t.setStyle(TableStyle(style_cmds))
    return t


def _build_story(font_name: str) -> list:
    prod_path = ROOT / "config/monitor_schedule.production.yaml"
    cfg = load_monitor_schedule(prod_path)
    cron = yaml.safe_load((ROOT / "config/cron_tasks.yaml").read_text(encoding="utf-8"))
    ws_cfg = yaml.safe_load((ROOT / "config/ws_monitor.yaml").read_text(encoding="utf-8"))
    wmon = yaml.safe_load((ROOT / "config/writing_monitor.yaml").read_text(encoding="utf-8"))

    title_style = ParagraphStyle(
        "T",
        fontName=font_name,
        fontSize=15,
        leading=20,
        spaceAfter=6,
    )
    meta = ParagraphStyle(
        "M",
        fontName=font_name,
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#444444"),
        wordWrap="CJK",
    )
    h2 = ParagraphStyle(
        "H2",
        fontName=font_name,
        fontSize=12,
        leading=16,
        spaceBefore=4,
        spaceAfter=8,
    )
    cell_style = ParagraphStyle(
        "c",
        fontName=font_name,
        fontSize=8.5,
        leading=11.5,
        wordWrap="CJK",
    )

    health = cfg.jobs["health"]
    ws_job = cfg.jobs["ws"]
    h_slots = _due_slot_minutes(health)
    w_slots = _due_slot_minutes(ws_job)
    sw = ws_cfg.get("skip_window") or {}
    until_s = _safe_xml_text(str(cfg.notify_success_until or "（见配置）"))
    bw = cron.get("batch_window") or {}
    delay = int((wmon or {}).get("execution_delay_minutes") or 10)
    slot = int((wmon or {}).get("execution_slot_minutes") or 5)
    w_end = (wmon or {}).get("active_end") or "20:30"

    def cell(txt: str) -> Paragraph:
        return Paragraph(txt, cell_style)

    story: list = [
        Paragraph("监控调度与企微发送时间表", title_style),
        Paragraph(
            f"时区 {_safe_xml_text(cfg.timezone)}　生成 {_safe_xml_text(datetime.now(ZoneInfo(cfg.timezone)).strftime('%Y-%m-%d %H:%M'))}",
            meta,
        ),
        Spacer(1, 6 * mm),
        Paragraph("表一 · 四类监控任务：时间窗口、轮询与企微", h2),
    ]

    cw = [72, 72, 48, 278]
    main_rows: list[list] = [
        [
            cell("<b>任务</b>"),
            cell("<b>active 窗口</b>"),
            cell("<b>interval</b>"),
            cell("<b>企微触发</b>"),
        ],
    ]
    job_title_cn = {
        "elk": "ELK 数据同步",
        "ws": "WebSocket 探活",
        "health": "行情 HTTP 探活",
        "writing": "自动化写稿",
    }

    for jid, job in cfg.jobs.items():
        st = job.active_start or "全天"
        en = job.active_end or "全天"
        title_cn = job_title_cn.get(jid, jid)

        if jid == "elk":
            wecom_txt = (
                f"· 在上述 active 窗口内，每轮检查<b>结束后</b>即发<br/>"
                f"· 成功类消息发至 <b>{until_s}</b>（之后仅失败仍发）<br/>"
                f"· 夜里批次约 {_safe_xml_text(str(bw.get('start', '00:00')))}"
                f"～{_safe_xml_text(str(bw.get('end', '05:00')))}，各数据任务时段以配置为准"
            )
        elif jid == "ws":
            wecom_txt = (
                "· <b>失败</b>：检测到后立即发<br/>"
                "· <b>整点小结</b>：约每个整点 :00（该轮在跑时）<br/>"
                "· <b>日界</b>：当天第一次 / 最后一次检查后各 1 条"
            )
            if w_slots:
                wecom_txt += (
                    f"<br/>　（首尾约 {_safe_xml_text(_fmt_minute(w_slots[0]))}、"
                    f"{_safe_xml_text(_fmt_minute(w_slots[-1]))}"
                    f"；{_safe_xml_text(str(sw.get('start', '?')))}～{_safe_xml_text(str(sw.get('end', '?')))} 跳过不测；"
                    f"{_safe_xml_text(_fmt_minute(w_slots[-1]))} 之后当日无 ws 整点小结）"
                )
        elif jid == "health":
            wecom_txt = (
                "· <b>失败</b>：检测到后立即发<br/>"
                "· <b>整点小结</b>：约每个整点 :00（该轮在跑时）<br/>"
                "· <b>日界</b>：当天第一次 / 最后一次检查后各 1 条<br/>"
                "· 非整点成功一般不发小结"
            )
            if h_slots:
                wecom_txt += (
                    f"<br/>　（首尾约 {_safe_xml_text(_fmt_minute(h_slots[0]))}、"
                    f"{_safe_xml_text(_fmt_minute(h_slots[-1]))}）"
                )
        else:
            wecom_txt = _writing_wecom_html(
                delay=delay,
                slot=slot,
                active_end_str=str(w_end),
                until_s=until_s,
                tz_name=cfg.timezone,
            )

        interval_cell = f"{job.interval_minutes}<br/>min"
        if jid == "writing":
            interval_cell = (
                f"{job.interval_minutes} min<br/><font size=\"7\">"
                "（调度器 5 min；按各子任务到点窗触发）</font>"
            )

        main_rows.append(
            [
                cell(f"<b>{_safe_xml_text(title_cn)}</b>"),
                cell(f"{_safe_xml_text(st)}<br/>～<br/>{_safe_xml_text(en)}"),
                cell(interval_cell),
                cell(wecom_txt),
            ]
        )

    story.append(_make_table(main_rows, cw, font_name))
    return story


def _write_pdf(out_path: Path) -> None:
    font_path = _pick_font()
    font_name = "ScheduleCJK"
    pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
    story = _build_story(font_name)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="监控调度与企微发送时间表",
    )
    doc.build(story)


def main() -> None:
    out = ROOT / "docs" / "opencraw-monitor-schedule.pdf"
    if len(sys.argv) > 1:
        out = Path(sys.argv[1]).resolve()
    _write_pdf(out)
    print(f"OK: {out}")


if __name__ == "__main__":
    main()
