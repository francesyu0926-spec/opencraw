from __future__ import annotations

from .models import MonitorConfig


def resolve_monitor_mode(cfg: MonitorConfig, cli_mode: str) -> str:
    """解析实际监控模式：elk 只查 Elasticsearch，不读本地 log_dir。"""
    mode = (cli_mode or "auto").strip().lower()
    if mode != "auto":
        return mode

    cfg_mode = (cfg.monitor_mode or "auto").strip().lower()
    if cfg_mode in ("local", "elk", "both"):
        return cfg_mode

    if cfg.elasticsearch and cfg.elasticsearch.url:
        return "elk"
    return "local"
