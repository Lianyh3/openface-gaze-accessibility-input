# Gaze MVP Baseline

本目录用于落地毕设第一阶段代码：

1. 调用 OpenFace `FeatureExtraction`
2. 解析输出 CSV
3. 产出 baseline 指标

## 目录

- `config/default.json`：默认配置
- `cpp_core/`：C++ 实时核心预留目录（含 M0 契约头文件）
- `src/gaze_mvp/`：核心模块
- `scripts/run_openface_baseline.py`：一键调用 OpenFace + 统计
- `scripts/summarize_openface_csv.py`：仅统计现有 CSV
- `scripts/evaluate_openface_runs.py`：批量评估多次 `webcam_*.csv`
- `scripts/demo_candidate_rerank.py`：单次候选词重排（OpenAI + 回退）
- `scripts/run_keyboard_mvp.py`：终端版虚拟键盘 MVP（含候选重排）
- `scripts/summarize_keyboard_session.py`：汇总键盘会话日志（jsonl）
- `scripts/evaluate_keyboard_task.py`：评估固定测试句任务（CER/CPM/WPM + 交互指标）
- `scripts/check_m0_contract.py`：校验 M0 跨语言接口契约（FrameFeatures/GazePoint/TargetEvent）
- `scripts/check_m1_alignment.py`：校验 M1 C++核心与 Python 参考实现对齐
- `scripts/check_m2_alignment.py`：校验 M2 C++核心与 Python 参考实现对齐（calibration + smoothing）
- `scripts/replay_dwell_targets.py`：回放注视目标序列并触发 dwell 事件
- `scripts/run_gaze_pipeline.py`：回放 gaze 坐标并执行命中测试 + dwell + 键盘事件（支持 `--runtime-backend {python,cpp}`）
- `scripts/run_gaze_cpp_pipeline.py`：用 C++ M1 回放后端驱动 Python 键盘事件流（M3 过渡版）
- `scripts/compare_runtime_backends.py`：比较 Python/C++ gaze 后端 wall time 与事件一致性
- `scripts/run_openface_live_pipeline.py`：启动 OpenFace 摄像头并实时驱动命中+dwell+键盘事件流（支持 `--runtime-backend {python,cpp}`）
- `scripts/run_end2end_batch.py`：批量端到端实验（baseline + live + 自动评估 + 汇总）
- `scripts/fit_9point_calibration.py`：根据 9 点标定样本拟合仿射映射参数
- `scripts/collect_9point_calibration.py`：在线引导采集 9 点标定数据（从增长中的CSV读取）
- `docs/AGENT_HANDOFF.md`：交接上下文

## 快速开始

```bash
cd /home/lyh/workspace/project
python3 scripts/summarize_openface_csv.py \
  --csv /home/lyh/workspace/OpenFace-OpenFace_2.2.0/test_out/sample1.csv
```

如需直接调用 OpenFace：

```bash
cd /home/lyh/workspace/project
python3 scripts/run_openface_baseline.py \
  --openface-bin /home/lyh/workspace/OpenFace-OpenFace_2.2.0/build_clean/bin/FeatureExtraction \
  --model-loc /home/lyh/workspace/OpenFace-OpenFace_2.2.0/build_clean/bin/model/main_clnf_wild.txt \
  --input-image /home/lyh/workspace/OpenFace-OpenFace_2.2.0/samples/sample1.jpg \
  --out-dir /home/lyh/workspace/project/data/raw/sample1_run
```

批量评估摄像头采集结果：

```bash
cd /home/lyh/workspace
bash run.sh eval
```

## AI 模块选型

当前建议主线：直连 OpenAI Responses API，LangChain 作为可选封装层，不阻塞主链路实现。

## 候选词增强 MVP

配置文件：

- `config/default.json` 中 `llm` 段定义 OpenAI 连接参数与模型。

环境变量：

```bash
export OPENAI_API_KEY="你的key"
```

单次重排示例：

```bash
cd /home/lyh/workspace/project
python3 scripts/demo_candidate_rerank.py \
  --prefix "我今天想去" \
  --candidates "图书馆,食堂,实验室,操场"
```

终端虚拟键盘 MVP：

```bash
cd /home/lyh/workspace/project
python3 scripts/run_keyboard_mvp.py
```

或使用根目录短命令：

```bash
cd /home/lyh/workspace
bash run.sh keyboard
```

单次重排也有短命令：

```bash
cd /home/lyh/workspace
bash run.sh rerank
```

进入交互后可使用：

- `dwell_key 我今天想去`（或别名 `type 我今天想去`）
- `dwell_pick 1`（或别名 `pick 1`）
- `dwell_back`（或别名 `back`）
- `refresh`（按当前 composing buffer 从候选池重算）

会话日志：

- 每次运行 `run_keyboard_mvp.py` 会自动写入 `data/logs/keyboard_session_*.jsonl`
- 汇总命令：

```bash
cd /home/lyh/workspace
bash run.sh summary
```

汇总报告新增交互指标（用于论文第5章）：

- 候选曝光统计：`candidate_exposure_total / top_exposed_candidates`
- dwell 触发时长统计：`dwell_elapsed_ms_summary`（mean/p50/p90）
- 撤销统计：`backspace_count / undo_backspace_count`

## 固定测试句评估（CER/WPM/CPM）

默认评估最新日志 + `T01` 目标句：

```bash
cd /home/lyh/workspace
bash run.sh task-eval
```

指定目标句：

```bash
cd /home/lyh/workspace
bash run.sh task-eval "我今天想去图书馆"
```

直接脚本（单次）：

```bash
cd /home/lyh/workspace/project
python3 scripts/evaluate_keyboard_task.py \
  --session-log /path/to/session.jsonl \
  --target-text "我今天想去图书馆"
```

批量映射评估（CSV）：

```bash
cd /home/lyh/workspace/project
python3 scripts/evaluate_keyboard_task.py \
  --mapping-csv /path/to/session_target_mapping.csv \
  --report-json /home/lyh/workspace/project/data/reports/keyboard_task_batch_report.json
```

样例任务清单：

- `data/samples/fixed_text_tasks_v1.csv`（`task_id,target_text,note`）

## M0 跨语言接口冻结校验

运行 M0 契约检查：

```bash
cd /home/lyh/workspace
bash run.sh m0-check
```

该命令会校验：

- 样例契约文件 `data/samples/m0_interface_alignment_samples.json`
- Python 契约模块 `src/gaze_mvp/runtime_contract.py`
- C++ 契约头文件 `cpp_core/include/gaze_core/contracts.h`

## M1 C++ 核心对齐校验

运行 M1 校验（normalizer + hit-test + dwell）：

```bash
cd /home/lyh/workspace
bash run.sh m1-check
```

该命令会：

- 编译 `cpp_core` 下 M1 回放程序（核心为 header-only `.hpp`）
- 运行 C++ 回放工具读取 gaze 样例
- 与 Python 参考实现逐事件对比（event_type/target_id/text/index/dwell_elapsed）

## M2 C++ 核心对齐校验

运行 M2 校验（calibration + smoothing）：

```bash
cd /home/lyh/workspace
bash run.sh m2-check
```

该命令会：

- 编译 `cpp_core` 下 M2 回放程序（核心为 header-only `.hpp`）
- 运行 C++ 回放工具读取 calibration/gaze 样例
- 与 Python 参考实现对比标定模型、拟合指标、EMA/OneEuro 轨迹

## C++ 后端闭环（M3 过渡）

运行 C++ M1 回放后端并接入 Python 键盘事件流：

```bash
cd /home/lyh/workspace
bash run.sh gaze-cpp
```

离线 gaze 管线也支持后端切换：

```bash
cd /home/lyh/workspace
bash run.sh gaze --runtime-backend cpp
```

## Python/C++ 后端对比

运行同一 gaze 样例下的 Python/C++ 后端对比：

```bash
cd /home/lyh/workspace
bash run.sh backend-compare
```

## Dwell 事件回放（眼控接口验证）

使用样例注视目标序列回放：

```bash
cd /home/lyh/workspace
bash run.sh dwell
```

样例数据：

- `data/samples/dwell_targets_demo.csv`（字段：`timestamp_ms,target_id`）

目标 ID 规则：

- `key:<text>` -> 输入文本
- `cand:<index>` -> 选择候选
- `action:back|commit|clear|refresh` -> 控制事件

## 坐标命中闭环（下一阶段入口）

使用 gaze 坐标 CSV 直接驱动完整事件流：

```bash
cd /home/lyh/workspace
bash run.sh gaze
```

等价命令：

```bash
cd /home/lyh/workspace/project
python3 scripts/run_gaze_pipeline.py \
  --gaze-csv /home/lyh/workspace/project/data/samples/gaze_points_demo.csv \
  --report-json /home/lyh/workspace/project/data/reports/gaze_pipeline_demo_report.json
```

输入 CSV 默认字段：

- `timestamp_ms`：毫秒时间戳
- `gaze_x`：注视点 x（默认假设 0~1）
- `gaze_y`：注视点 y（默认假设 0~1）

可用参数：

- `--x-min --x-max --y-min --y-max`：将原始坐标线性映射到 0~1（用于后续标定前后对比）
- `--candidate-slots`：候选区域槽位数量（当前默认布局支持最多 8）
- `--smoothing none|ema|one_euro`：切换时序平滑策略（默认 `none`）

样例文件：

- `data/samples/gaze_points_demo.csv`

## OpenFace 实时接入（摄像头 -> 输入事件）

直接启动 OpenFace 并实时读取增长中的 CSV，驱动 `hit-test -> dwell -> keyboard`：

```bash
cd /home/lyh/workspace
bash run.sh gaze-live --max-seconds 20 --print-events

# 使用 C++ M1 回放后端做实时过渡接入
bash run.sh gaze-live --runtime-backend cpp --max-seconds 20
```

等价命令：

```bash
cd /home/lyh/workspace/project
python3 scripts/run_openface_live_pipeline.py \
  --device 0 \
  --max-seconds 20 \
  --print-events \
  --report-json /home/lyh/workspace/project/data/reports/gaze_live_latest_report.json

# 切换实时后端
#   --runtime-backend python   默认，纯 Python runtime
#   --runtime-backend cpp      Python 预处理 + C++ M1 回放核心
```

常用参数：

- `--runtime-backend`：实时链路后端切换，支持 `python` 与 `cpp`
- `--x-col/--y-col`：默认读取 OpenFace 的 `gaze_angle_x/gaze_angle_y`
- `--x-min/--x-max/--y-min/--y-max`：线性归一化区间（未加载标定 JSON 时生效）
- `--calibration-json`：加载 9 点标定参数，优先替代线性区间归一化
- `--export-gaze-csv`：导出 `timestamp_ms,gaze_x,gaze_y`，可直接用于后续在线标定采集链路

平滑开关示例：

```bash
cd /home/lyh/workspace
bash run.sh gaze --smoothing ema --ema-alpha 0.35
```

```bash
cd /home/lyh/workspace
bash run.sh gaze --smoothing one_euro --one-euro-min-cutoff 1.0 --one-euro-beta 0.01
```

## 端到端批量实验（baseline + live + 自动评估）

一条命令完成：

1. baseline 摄像头链路批量采集（OpenFace CSV）
2. live 端到端任务采集（Python/C++ 后端）
3. 每轮自动计算 `CER/CPM/WPM`
4. 自动输出总汇总 `summary.json`

```bash
cd /home/lyh/workspace
bash run.sh e2e-batch --task-ids T01,T02 --python-repeats 2 --cpp-repeats 1
```

无图形界面场景（推荐）：

```bash
cd /home/lyh/workspace
bash run.sh e2e-batch \
  --execution-mode headless_replay \
  --task-ids T01,T02 \
  --python-repeats 2 \
  --cpp-repeats 1 \
  --force-heuristic-reranker
```

常用参数：

- `--baseline-runs`：baseline 采集轮次（默认 5）
- `--execution-mode`：`live`（摄像头交互）或 `headless_replay`（无界面脚本回放）
- `--max-seconds`：每轮 live 最大时长（默认 60）
- `--smoothing`：`none|ema|one_euro`
- `--auto-start`：跳过每轮开始前的回车确认
- `--continue-on-error`：单轮失败后继续后续轮次
- `--force-heuristic-reranker`：禁用在线 LLM 重排，保证候选索引可复现（headless 模式建议开启）

输出目录：

- `project/data/experiments/e2e_batch_*/summary.json`

## 9 点标定拟合与接入

拟合标定参数（样例）：

```bash
cd /home/lyh/workspace
bash run.sh calib
```

等价命令：

```bash
cd /home/lyh/workspace/project
python3 scripts/fit_9point_calibration.py \
  --points-csv /home/lyh/workspace/project/data/samples/calibration_points_9_demo.csv \
  --output-json /home/lyh/workspace/project/data/calibration/latest_affine_calibration.json
```

在 gaze 管线中使用标定参数：

```bash
cd /home/lyh/workspace/project
python3 scripts/run_gaze_pipeline.py \
  --gaze-csv /home/lyh/workspace/project/data/samples/gaze_points_demo.csv \
  --calibration-json /home/lyh/workspace/project/data/calibration/latest_affine_calibration.json
```

在线 9 点采集（实时引导）：

```bash
cd /home/lyh/workspace
bash run.sh calib-collect --source-csv /path/to/live_gaze.csv --auto-start
```

说明：

- `--source-csv` 应为实时增长的 CSV（至少包含 `gaze_x,gaze_y` 列）。
- 脚本会逐点采集并输出：
  - 标定点CSV：`data/calibration/sessions/latest_calibration_points.csv`
  - 拟合参数：`data/calibration/latest_affine_calibration.json`
  - 采集报告：`data/reports/latest_calibration_collection_report.json`
