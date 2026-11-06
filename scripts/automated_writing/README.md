# automated_writing（写稿任务验证）

自 [automated_writing](https://gitlab.com/) 项目 vendored 的 `verify` 包，由 opencraw 统一调度（job `writing`）或单独运行：

```powershell
python -m scripts.cron_task_monitor --writing-monitor --json
```

环境变量见 `config/writing.env.example`。任务到点见 `verify/tasks.py`；生产调度为 **到点 +10 分钟** 执行 **1 次**（`verify run --window`，见 `config/writing_monitor.yaml`）。
