# 定时任务监控（§2.1）

## 执行计划（每天 00:00–05:00，每 15 分钟）

| 项目 | 配置 |
|------|------|
| 运行窗口 | **00:00–05:00**（`Asia/Shanghai`） |
| 频率 | **每 15 分钟** |
| ES 查询 | **`rolling_in_batch`**：在窗口内查 **最近 15 分钟** 日志 |

触发时刻示例：`00:00, 00:15, …, 04:45, 05:00`。

### Linux cron

见 `config/schedule.example.cron`。

### Windows 任务计划程序

1. 创建任务 → 触发器：**每天 00:00**
2. 勾选 **重复任务**，间隔 **15 分钟**，持续时间 **5 小时**
3. 操作：`powershell.exe -ExecutionPolicy Bypass -File D:\Document\CODE\opencraw\scripts\run_monitor_scheduled.ps1`
4. 环境变量：`ELASTICSEARCH_PASSWORD`、`WECOM_WEBHOOK_URL`（系统或任务里配置）

## 手动运行

```powershell
$env:ELASTICSEARCH_PASSWORD = "密码"
$env:WECOM_WEBHOOK_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."

python -m scripts.cron_task_monitor --print-elk-query   # 含 query_time_range
python -m scripts.cron_task_monitor --json
```

`--print-elk-query` 会输出当前时刻对应的 **gte/lte**（ISO8601，北京时间）。

## 查询时间模式（`query_time_mode`）

| 模式 | 含义 |
|------|------|
| `rolling_in_batch`（默认） | 在 `batch_window` 内，查 `[now-15m, now]` 与窗口的交集 |
| `batch_window` | 当日 `00:00` 至 `min(now, 05:00)` |
| `elastic` | 使用 YAML 里 `timestamp_gte` / `timestamp_lte`（如 `now/d`） |

## §2.2 WebSocket 探活

```powershell
pip install websockets
python -m scripts.cron_task_monitor --ws-monitor --json
```

- 地址与 subscribe 参数：`config/ws_monitor.yaml`
- 建连 → 发送订阅 JSON → 维持 **≥30 秒** → 收到推送 → **主动关闭**
- **08:30–09:00** 自动跳过（不告警）
- 失败走企业微信（`WECOM_WEBHOOK_URL`）
- 建议 **每 10 分钟** 跑一次（见 `config/schedule.example.cron`）

## 告警与企业微信（两个机器人）

| 监控 | 环境变量 | 配置 |
|------|----------|------|
| §2.1 ELK 定时任务 | **`WECOM_WEBHOOK_URL_ELK`** | `config/cron_tasks.yaml` → `wecom.webhook_env` |
| §2.2 WebSocket | **`WECOM_WEBHOOK_URL_WS`** | `config/ws_monitor.yaml` → `wecom.webhook_env` |

示例见 `config/wecom.env.example`。已配置对应变量时自动推送；**`--no-notify`** 可关闭。
