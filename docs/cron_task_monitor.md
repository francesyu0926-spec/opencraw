# 定时任务监控（§2.1）

## 生产调度（推荐）

时刻表见 `config/monitor_schedule.production.yaml`，入口 **`scripts/run_monitor_production.ps1`** / **`run_monitor_production.sh`**：

| Job | 频率 | 运行窗口 |
|-----|------|----------|
| `elk` | 每 **15** 分钟 | **00:00–05:00**（数据同步定时任务） |
| `ws` | 每 **10** 分钟 | **09:00–15:30**（模拟客户端探活） |
| `health` | 每 **15** 分钟 | **09:00–23:39** |
| `writing` | 每 **5** 分钟 | **07:00–20:30**（zxtop 写稿 7 项，失败企微） |

任务计划 / cron：**每 5 分钟**触发调度器（WS 10 分钟 / health·elk 15 分钟 / writing 5 分钟到期才执行）。

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_monitor_production.ps1 -Json
```

```bash
python -m scripts.cron_task_monitor --run-scheduled \
  --schedule-config config/monitor_schedule.production.yaml --json
```

**Windows 任务计划**：每天重复，间隔 **5 分钟**（触发调度器）；程序见上。

**Linux cron**：`*/5 * * * * .../run_monitor_production.sh`（见 `config/schedule.example.cron`）。

## 统一调度（开发/旧表）

`config/monitor_schedule.yaml`：health 5 分钟 / ws 10 分钟 / elk 0–5 点 15 分钟；调度器 **每 5 分钟**。入口 `scripts/run_scheduled_monitors.ps1`。

密钥文件（均 gitignore）：`config/elk.env`、`config/health.env`、`config/wecom.env`、`config/writing.env`（示例见 `*.example`）。

### 自动化写稿（writing）

代码来自 `scripts/automated_writing/`（`verify run --due`）。配置 **`config/writing.env`**：`SFC_ADMIN_CODE` / `SFC_ADMIN_PASSWORD`（与 automated_writing 一致），企微用 **`SFC_WECHAT_WEBHOOK_URL`** 或 **`wecom.env`** 中的 **`WECOM_WEBHOOK_URL_WRITING`**。

```powershell
python -m scripts.cron_task_monitor --writing-monitor --json
python -m scripts.cron_task_monitor --run-scheduled --schedule-config config/monitor_schedule.production.yaml --job writing --force --json
```

## §2.1 ELK 数据同步（单独运行）

| 项目 | 配置 |
|------|------|
| 运行窗口 | **00:00–05:00**（`Asia/Shanghai`） |
| 频率 | **每 15 分钟** |
| ES 查询 | **`rolling_in_batch`**：在窗口内查 **最近 15 分钟** 日志 |

触发时刻示例：`00:00, 00:15, …, 04:45, 05:00`。

旧入口 `scripts/run_monitor_scheduled.ps1` 仍可用（仅转发 ELK job 到统一调度）。

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

## §2.2 WebSocket 探活（模拟客户端 / 模拟用户）

运维侧独立 **监控客户端**，**每 10 分钟** 一轮（`config/ws_monitor.yaml` → `interval_seconds: 600`；生产见 `monitor_schedule.production.yaml`）：

1. **能否成功建立连接**（`connect_timeout_seconds`）
2. **能否维持连接 > 30 秒**（`hold_seconds`，计时结束后 **主动 `close`**，避免长连占资源）
3. **能否正确收发消息**：发送订阅 JSON → 至少收到 1 条推送，且含 **`quoteItems`**（视为业务行情消息正常；失败即告警）
4. **失败则告警**（仅失败）：`--ws-monitor` / 统一调度走 **`WECOM_WEBHOOK_URL_WS`**；成功不发企微

```powershell
pip install websockets
python -m scripts.cron_task_monitor --ws-monitor --json
# 长驻单进程（内置每 10 分钟一轮，逻辑同上）：
python -m scripts.cron_task_monitor --ws-daemon
```

- 配置：`config/ws_monitor.yaml`（六大指数订阅，与行情客户端一致）
- **08:30–09:00** 自动跳过（不告警、不探活）

## 行情 API Health

Token 来自登录接口，再放到 health 请求的 **Token** 头。登录最多每 **12 小时**一次，JWT 与取得时间写在 `config/health.token.cache.json`（已 gitignore）。未同时配置登录账号和密码时，才回退到静态 `QUOTES_HEALTH_TOKEN`（不写缓存）。

在仓库根目录执行时，若存在 **`config/health.env`**（及可选的 **`config/wecom.env`**），`--health-monitor` 会自动加载其中的变量（不覆盖 shell 里**已有非空值**的同名变量；UTF-8 BOM 与仅含空白的占位变量会被正确处理）。也可根据 `--health-config` 路径定位仓库根目录加载上述文件。可复制 `config/health.env.example` 为 `config/health.env` 并填入密钥（勿提交）。

也可在 shell 中手动 export：

```powershell
$env:QUOTES_LOGIN_CODE = "登录账号"
$env:QUOTES_LOGIN_PASSWORD = "密码的 SHA256 hex"
# 可选回退（登录变量都未设置时）：
# $env:QUOTES_HEALTH_TOKEN = "JWT"
$env:WECOM_WEBHOOK_URL_HEALTH = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."
python -m scripts.cron_task_monitor --health-monitor --json
```

Windows 计划任务可直接跑 `scripts/run_health_monitor.ps1`（同样会加载上述 env 文件后再调用 Python）。

- 缓存年龄小于 `login_interval_hours`（默认 **12**）时直接复用，不调用登录接口
- 缓存缺失、无法读取或超过 12 小时：`POST https://terminal.sfccn.com/terminal/zxt-web/login/pwd`（`application/x-www-form-urlencoded`：`loginCode`、`password`）一次，写入 JWT 后再探活
- health 返回 **401/403**：再登录一次，并只重试 health 一次
- health 为 `POST https://terminal.sfccn.com/terminal/quotes/api/health`，空 body，**Token** 请求头
- 解析 JSON：根 **`status`** 与 **`checks[]`** 中每一项的 **`status`** 均须为 **`UP`**，否则告警
- 配置：`config/health_monitor.yaml`；密钥示例 `config/health.env.example`（勿提交 loginCode、password、Token、webhook）

## 告警与企业微信（三个机器人）

**默认策略：仅失败告警。** 成功时不发企微；失败且已配置 webhook 时推送。

**临时（至 `2026-11-11`）**：生产表 `config/monitor_schedule.production.yaml` 中 **`notify_success_trial`** 开启时，在**整点（分钟为 00）**且本轮 job **执行成功**，会向**该 job 对应机器人**发送成功文本（Docker / `run_monitor_production.*` 无需加参数）。到期后将 `enabled: false` 或删除该段即可恢复仅失败告警。

| 监控 | 环境变量 | 配置 |
|------|----------|------|
| §2.1 ELK 定时任务 | **`WECOM_WEBHOOK_URL_ELK`** | `config/cron_tasks.yaml` → `wecom.webhook_env` |
| §2.2 WebSocket | **`WECOM_WEBHOOK_URL_WS`** | `config/ws_monitor.yaml` → `wecom.webhook_env` |
| 行情 API Health | **`WECOM_WEBHOOK_URL_HEALTH`** | `config/health_monitor.yaml` → `wecom.webhook_env` |
| 自动化写稿 | **`WECOM_WEBHOOK_URL_WRITING`** / **`SFC_WECHAT_WEBHOOK_URL`** | `config/writing.env` |

示例见 `config/wecom.env.example`。联调可用 **`--notify-success`** / **`-NotifySuccess`**（每轮全部 job 成功时发 ELK 机器人汇总，与整点 trial 互斥）。

**`--no-notify`** 可关闭全部通知（含整点成功）。
