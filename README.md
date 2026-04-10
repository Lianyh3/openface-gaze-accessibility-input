# openface-gaze-accessibility-input

本仓库用于本科毕业论文《基于 OpenFace 的实时视线估计优化》的工程实现与写作支撑。

> 说明：论文题目不变；当前技术主线已从“眼控键盘”收敛为“实时视线优化 + 注意力状态识别 + LLM 解释反馈”。

---

## 当前主线（已更新）

### 研究目标

构建一个可复现、可量化评估的实时系统，完成三件事：

1. **OpenFace 视线估计优化**（稳态与抗漂移）
2. **注意力状态识别**（专注/分心/疲劳风险）
3. **大模型解释反馈**（自然语言提醒与建议）

### 应用落地点

- 主落地点：**上课专注度辅助系统（PC端）**
- 次落地点（扩展讨论）：医疗/养老无障碍交互

---

## 仓库结构（顶层）

- `gaze-keyboard-v2/project/`：当前主代码目录（Python）
- `docs/`：设计文档、方案文档、图表相关
- `论文*.md`：论文章节草稿与写作规范文档
- `run.sh`：历史统一脚本入口（部分命令面向旧主线）

---

## 代码运行入口（当前有效）

以下命令默认在：

`d:\openface-gaze-accessibility-input-master\gaze-keyboard-v2\project`

### 1) 实时运行：无障碍呼叫面板（用于调试 gaze 稳定性）

```bash
python scripts/run_accessible_call_panel.py --csv logs/live_openface.csv --session-id call-panel-live
```

常用参数：

- `--mirror-x`：镜像修正（左右反向时开启）
- `--gain-x / --gain-y`：横纵向增益
- `--min-confidence`：置信度过滤阈值
- `--smooth-alpha`：平滑强度
- `--dwell-ms`：驻留触发阈值
- `--blink-threshold`：眨眼确认阈值

### 2) 批量实验：Baseline/Ours/Ours+Blink

```bash
python scripts/run_call_panel_experiments.py --csv logs/live_openface.csv --session-prefix exp-call-panel --max-iterations 500
```

### 3) 日志评估：输出实验指标

```bash
python scripts/eval_call_panel_logs.py --log-dir logs --session-prefix exp-call-panel --output-csv logs/exp_call_panel_metrics.csv
```

---

## 当前实验口径（论文对照）

### 对照组

- `baseline`：固定驻留，无眨眼确认
- `ours`：自适应驻留
- `ours_blink`：自适应驻留 + 眨眼确认

### 指标建议

- 视线稳定性（抖动幅度/轨迹方差）
- 误触相关指标（误触率、取消率）
- 交互效率（平均触发间隔、任务完成时间）
- 主观评分（疲劳感、可用性）

---

## 与旧主线的关系说明

- 旧主线（眼控键盘、候选词输入）代码仍保留，便于历史复现。
- 论文与后续实验请以本 README 的“当前主线”为准。
- 如出现文档冲突，以本文件和 `gaze-keyboard-v2/project` 下脚本实际行为为准。

---

## 论文写作建议（简版）

建议正文按以下闭环组织：

1. 问题定义：实时眼动在稳定性与实用性上的瓶颈
2. 方法设计：滤波/抗漂移/阈值策略 + 状态识别 + LLM 反馈
3. 系统实现：模块、参数、日志契约
4. 实验对照：baseline vs ours vs ours+blink
5. 结论与边界：在哪些条件下有效，哪些场景仍需改进

---

## 关键说明

- 本仓库用于教学/科研验证，不用于医疗诊断或安全关键控制。
- LLM 模块用于解释与建议，不替代底层状态判定逻辑。
