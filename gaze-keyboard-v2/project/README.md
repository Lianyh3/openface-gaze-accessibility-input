# Gaze Keyboard V2 - Project

本目录承载可执行代码实现（与根目录文档分离）。

## 当前已完成

- 数据契约模块：`src/gaze_keyboard/common/contracts.py`
- 配置模块：`src/gaze_keyboard/common/config.py`
- OpenFace B方案输入骨架：`src/gaze_keyboard/algo/openface_stream.py`
- 算法基础模块：`calibrator.py`、`smoother.py`、`dwell_state_machine.py`
- 系统基础模块：`keyboard_layout.py`、`hit_tester.py`、`input_controller.py`
- 最小闭环运行脚本：`scripts/run_realtime_keyboard.py`
- 运行时模块：`src/gaze_keyboard/system/runtime.py`
- 日志模块：`src/gaze_keyboard/system/logger.py`
- 回归验证脚本：`scripts/smoke_test_pipeline.py`、`scripts/smoke_test_runtime.py`

## 安装（推荐）

在 `gaze-keyboard-v2/project` 目录下执行：

```bash
python -m pip install -e .
```

安装后可直接运行脚本，无需手工设置 `PYTHONPATH`。

## 快速运行（骨架验证）

```bash
python scripts/run_realtime_keyboard.py --csv "path/to/openface.csv" --poll-ms 40 --max-iterations 20
```

## 运行冒烟测试（推荐每次改动后执行）

```bash
python scripts/smoke_test_pipeline.py
python scripts/smoke_test_runtime.py
```

预期输出：

```text
[OK] smoke pipeline passed. text='A'
[OK] runtime smoke passed. text='A'
```

说明：
- 当前脚本已支持从 CSV 输入到 dwell 触发输入的最小闭环；
- 已接入运行时日志、会话 summary 与 AI 候选补全（可选开关）。

## 启用 AI 候选补全（可选）

请先设置环境变量：

```bash
# Windows PowerShell
$env:OPENAI_API_KEY="your-key"
```

再运行：

```bash
python scripts/run_realtime_keyboard.py --csv "path/to/openface.csv" --ai-enabled --ai-top-k 5
```
