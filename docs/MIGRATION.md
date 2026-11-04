# 定时任务监控 — 迁移包说明

## 最小运行依赖

| 路径 | 说明 |
|------|------|
| `requirements-monitor.txt` | Python 依赖 |
| `config/cron_tasks.yaml` | 任务时间、ES、索引 |
| `config/elk.env.example` | ES 密码（复制为 `config/elk.env`） |
| `config/wecom.env.example` | 企业微信 Webhook（复制为 `config/wecom.env`） |
| `scripts/cron_task_monitor/` | 监控程序 |
| `scripts/run_monitor_scheduled.ps1` | Windows 00:00–05:00 计划任务入口（可选） |
| `config/schedule.example.cron` | Linux cron 示例（可选） |

## 安装步骤

```bash
pip install -r requirements-monitor.txt
# 配置环境变量或 elk.env / wecom.env
export ELASTICSEARCH_PASSWORD=...
export WECOM_WEBHOOK_URL=...

cd <解压目录>
PYTHONPATH=. python -m scripts.cron_task_monitor --check-elk
PYTHONPATH=. python -m scripts.cron_task_monitor --json
```

Windows：在仓库根目录执行，`$env:PYTHONPATH="."`，无需 export。

## 目录结构（解压后）

```
opencraw/
├── config/
├── docs/
├── scripts/
│   ├── run_monitor_scheduled.ps1
│   └── cron_task_monitor/
├── tests/                 # 可选，迁移后可删
├── requirements-monitor.txt
└── README.md
```

## 不需要迁移

- `.git/`、`__pycache__/`、`*.pyc`
- 任务机上的 `/usr/local/zxt/...` 日志路径（仅 ELK 模式）
