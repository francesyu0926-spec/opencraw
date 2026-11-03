# opencraw

行情相关运维工具集。

## 定时任务监控（§2.1）

见 [docs/cron_task_monitor.md](docs/cron_task_monitor.md)。

快速开始：

```bash
pip install -r requirements-monitor.txt
python -m scripts.cron_task_monitor -c config/cron_tasks.yaml --json
python -m unittest discover -s tests -p 'test_*.py'
```
