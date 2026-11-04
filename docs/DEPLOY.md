# opencraw 监控部署操作说明

本文档对应发布压缩包 `opencraw-monitor-deploy-*.zip` 内的完整部署流程（HTTP health、WebSocket、ELK 数据同步）。

## 1. 包内文件清单

| 路径 | 说明 |
|------|------|
| `requirements-monitor.txt` | Python 依赖 |
| `Dockerfile` / `.dockerignore` | 容器部署（可选） |
| `config/monitor_schedule.production.yaml` | **生产**调度时刻表 |
| `config/monitor_schedule.yaml` | 开发/旧调度时刻表 |
| `config/cron_tasks.yaml` | ELK 任务与索引配置 |
| `config/ws_monitor.yaml` | WebSocket 探活配置 |
| `config/health_monitor.yaml` | HTTP health 配置 |
| `config/*.env.example` | 密钥模板（复制后填写，勿提交 Git） |
| `config/schedule.example.cron` | Linux cron 示例 |
| `scripts/cron_task_monitor/` | 监控程序 |
| `scripts/run_monitor_production.ps1` | **Windows 生产调度入口** |
| `scripts/run_monitor_production.sh` | **Linux 生产调度入口** |
| `scripts/run_scheduled_monitors.ps1` | Windows 开发/旧调度入口 |
| `scripts/run_scheduled_monitors.sh` | Linux 开发/旧调度入口 |
| `scripts/run_health_monitor.ps1` | 仅 health（可选） |
| `scripts/run_monitor_scheduled.ps1` | 兼容旧 ELK 计划任务（可选） |
| `docs/cron_task_monitor.md` | 功能与告警说明 |

**压缩包内不含**（需在目标机自行创建）：`config/elk.env`、`config/health.env`、`config/wecom.env`、`config/health.token.cache.json`。

## 2. 环境要求

- **Python**：3.11（与 `python:3.11-alpine` 镜像一致）
- **网络**：可访问 ES、行情 terminal 域名、企业微信 webhook
- **Linux 额外**：`python3`、`pip`；WebSocket 探活依赖 `websockets`（已写在 requirements 中）

## 3. 配置密钥（必做）

在解压目录 `opencraw/` 下：

```bash
cd opencraw/config
cp elk.env.example elk.env
cp health.env.example health.env
cp wecom.env.example wecom.env
```

编辑三个 `.env` 文件（**勿打包、勿上传仓库**）：

| 文件 | 主要变量 |
|------|----------|
| `elk.env` | `ELASTICSEARCH_PASSWORD`（及可选 `ELASTICSEARCH_URL` / `USER`） |
| `health.env` | `QUOTES_LOGIN_CODE`、`QUOTES_LOGIN_PASSWORD`（SHA256 hex）；或静态 `QUOTES_HEALTH_TOKEN` |
| `wecom.env` | `WECOM_WEBHOOK_URL_ELK`、`WECOM_WEBHOOK_URL_WS`、`WECOM_WEBHOOK_URL_HEALTH` |

## 4. 方式 A：本机 Python 部署

### 4.1 安装依赖

```bash
cd opencraw
python -m pip install -r requirements-monitor.txt
```

国内可选镜像：

```bash
python -m pip install -r requirements-monitor.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 4.2 自检

```bash
export PYTHONPATH=.
set -a && source config/elk.env && source config/wecom.env && set +a   # Linux
# Windows PowerShell 请用 scripts/run_scheduled_monitors.ps1 自动加载 env

python -m scripts.cron_task_monitor --check-elk
python -m scripts.cron_task_monitor --run-scheduled --dry-run --json
python -m scripts.cron_task_monitor --run-scheduled --force-scheduled --job health --json
```

### 4.3 定时运行（推荐：统一调度）

**Linux cron**（每 5 分钟）：

```bash
chmod +x scripts/run_scheduled_monitors.sh
crontab -e
# 增加一行（路径按实际修改）：
*/5 * * * * /opt/opencraw/scripts/run_scheduled_monitors.sh >> /var/log/opencraw_monitors.log 2>&1
```

**Windows 任务计划程序**：

1. 触发器：每天，重复 **5 分钟**，持续 **1 天**
2. 操作：`powershell.exe -ExecutionPolicy Bypass -File D:\path\to\opencraw\scripts\run_scheduled_monitors.ps1 -Json`
3. 密钥已通过 `config/*.env` 加载，无需在任务里写密码

调度说明见 `config/monitor_schedule.yaml`（health 5 分钟 / ws 10 分钟 / elk 00:00–05:00 每 15 分钟）。

## 5. 方式 B：Docker 部署

### 5.1 Docker Compose（推荐）

在解压目录（含 `docker-compose.yml`）准备好 `config/*.env` 后：

```bash
# 可选：避免 Docker 把缓存路径建成目录（Linux/macOS）
touch config/health.token.cache.json

docker compose up -d --build
docker compose logs -f
```

`docker-compose.yml` 会：

- 读取 `config/elk.env`、`health.env`、`wecom.env`
- 挂载 `./config/health.token.cache.json` 持久化登录 JWT（默认 12 小时）
- 每 **300 秒** 执行 `--run-scheduled --json --notify-success`

停止：`docker compose down`

### 5.2 仅 docker build / run

```bash
docker build -t opencraw-monitor .

docker run -d --name opencraw-monitor --restart unless-stopped \
  --env-file config/elk.env \
  --env-file config/health.env \
  --env-file config/wecom.env \
  -v "$(pwd)/config/health.token.cache.json:/app/config/health.token.cache.json" \
  opencraw-monitor
```

### 5.3 查看日志

```bash
docker logs -f opencraw-monitor
# 或 Compose：
docker compose logs -f
```

## 6. 告警与排错

| 现象 | 处理 |
|------|------|
| 未配置 `QUOTES_LOGIN_*` / `QUOTES_HEALTH_TOKEN` | 检查 `config/health.env` 是否创建并挂载 |
| ELK 查询失败 | `elk.env` 密码、`cron_tasks.yaml` 中 ES 地址与索引 |
| Windows `urlopen Errno 2` | 设置 `SSL_CERT_FILE` 指向 certifi 证书，或使用 `run_scheduled_monitors.ps1`（已尝试自动设置） |
| 08:30–09:00 WS 无告警 | 正常跳过窗口，见 `ws_monitor.yaml` |

详细行为见 [cron_task_monitor.md](./cron_task_monitor.md)。

## 7. 升级

1. 停止 cron / 容器 / 计划任务  
2. 备份 `config/*.env` 与 `config/health.token.cache.json`  
3. 解压新包覆盖程序与 YAML（**不要覆盖** 上述密钥与缓存）  
4. `pip install -r requirements-monitor.txt` 或 `docker build` 重新构建  
5. 执行 4.2 自检后恢复调度  

## 8. 重新打部署包（维护者）

在源码仓库根目录：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\pack_deploy.ps1
```

生成 `dist/opencraw-monitor-deploy-YYYYMMDD.zip`。

**密钥单独打包**（与程序包分开发，勿上传 Git）：

```powershell
# 确保 config/elk.env、health.env、wecom.env 已填写真实值
powershell -ExecutionPolicy Bypass -File scripts\pack_secrets.ps1
```

生成 `dist/opencraw-secrets-config-YYYYMMDD.zip`（内含上述三个文件 + `密钥解压说明.txt`）。
