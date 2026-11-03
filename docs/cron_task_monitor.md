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
# 或与 mdimonitor 一致的长驻循环（默认每 600 秒一轮，探活内 30 秒后主动断连）：
python -m scripts.cron_task_monitor --ws-daemon
```

- 地址与 subscribe 参数：`config/ws_monitor.yaml`（六大指数、`quoteItems` 校验与 mdimonitor WebSocket 客户端一致）
- 建连 → 发送订阅 JSON → **30 秒** 定时断连 → 推送须含 **`quoteItems`**，否则记失败并可选即时企微（`WeChatBot.send_text`，daemon 模式）
- **08:30–09:00** 自动跳过（不告警）
- 单次探活失败汇总告警走 **`WECOM_WEBHOOK_URL_WS`**（`--ws-monitor`）；cron 建议 **每 10 分钟**（见 `config/schedule.example.cron`）

## 行情 API Health

Token 来自登录接口，再放到 health 请求的 **Token** 头。登录最多每 **12 小时**一次，JWT 与取得时间写在 `config/health.token.cache.json`（已 gitignore）。未同时配置登录账号和密码时，才回退到静态 `QUOTES_HEALTH_TOKEN`（不写缓存）。

```powershell
$env:QUOTES_LOGIN_CODE = "登录账号"
$env:QUOTES_LOGIN_PASSWORD = "密码的 SHA256 hex"
# 可选回退（登录变量都未设置时）：
# $env:QUOTES_HEALTH_TOKEN = "JWT"
$env:WECOM_WEBHOOK_URL_HEALTH = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."
python -m scripts.cron_task_monitor --health-monitor --json
```

Windows 计划任务可直接跑 `scripts/run_health_monitor.ps1`（自动加载 `config/health.env` / `config/wecom.env`）。

- 缓存年龄小于 `login_interval_hours`（默认 **12**）时直接复用，不调用登录接口
- 缓存缺失、无法读取或超过 12 小时：`POST https://terminal.sfccn.com/terminal/zxt-web/login/pwd`（`application/x-www-form-urlencoded`：`loginCode`、`password`）一次，写入 JWT 后再探活
- health 返回 **401/403**：再登录一次，并只重试 health 一次
- health 为 `POST https://terminal.sfccn.com/terminal/quotes/api/health`，空 body，**Token** 请求头
- 解析 JSON：根 **`status`** 与 **`checks[]`** 中每一项的 **`status`** 均须为 **`UP`**，否则告警
- 配置：`config/health_monitor.yaml`；密钥示例 `config/health.env.example`（勿提交 loginCode、password、Token、webhook）

## 告警与企业微信（三个机器人）

| 监控 | 环境变量 | 配置 |
|------|----------|------|
| §2.1 ELK 定时任务 | **`WECOM_WEBHOOK_URL_ELK`** | `config/cron_tasks.yaml` → `wecom.webhook_env` |
| §2.2 WebSocket | **`WECOM_WEBHOOK_URL_WS`** | `config/ws_monitor.yaml` → `wecom.webhook_env` |
| 行情 API Health | **`WECOM_WEBHOOK_URL_HEALTH`** | `config/health_monitor.yaml` → `wecom.webhook_env` |

示例见 `config/wecom.env.example`。已配置对应变量时自动推送；**`--no-notify`** 可关闭。
