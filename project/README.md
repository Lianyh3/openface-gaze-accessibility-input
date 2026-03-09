# Gaze MVP Baseline

本目录用于落地毕设第一阶段代码：

1. 调用 OpenFace `FeatureExtraction`
2. 解析输出 CSV
3. 产出 baseline 指标

## 目录

- `config/default.json`：默认配置
- `src/gaze_mvp/`：核心模块
- `scripts/run_openface_baseline.py`：一键调用 OpenFace + 统计
- `scripts/summarize_openface_csv.py`：仅统计现有 CSV
- `scripts/evaluate_openface_runs.py`：批量评估多次 `webcam_*.csv`
- `scripts/demo_candidate_rerank.py`：单次候选词重排（OpenAI + 回退）
- `scripts/run_keyboard_mvp.py`：终端版虚拟键盘 MVP（含候选重排）
- `scripts/summarize_keyboard_session.py`：汇总键盘会话日志（jsonl）
- `scripts/replay_dwell_targets.py`：回放注视目标序列并触发 dwell 事件
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
bash run_eval.sh
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
bash run_keyboard_mvp.sh
```

单次重排也有短命令：

```bash
cd /home/lyh/workspace
bash run_rerank_demo.sh
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
bash run_keyboard_summary.sh
```

## Dwell 事件回放（眼控接口验证）

使用样例注视目标序列回放：

```bash
cd /home/lyh/workspace
bash run_dwell_replay.sh
```

样例数据：

- `data/samples/dwell_targets_demo.csv`（字段：`timestamp_ms,target_id`）

目标 ID 规则：

- `key:<text>` -> 输入文本
- `cand:<index>` -> 选择候选
- `action:back|commit|clear|refresh` -> 控制事件
