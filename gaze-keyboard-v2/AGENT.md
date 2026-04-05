# AGENT.md

本文件定义 `gaze-keyboard-v2` 目录下的开发约定，确保后续实现一致、可复现、可用于论文写作与答辩。

## 1. 项目目标

围绕论文题目《基于 OpenFace 的实时视线估计优化》，以“三层结构”推进：

1. 算法优化层
2. 系统实现层
3. 智能交互增强层（候选词补全）

## 2. 强制工程约束

1. 主输入链路固定为 **B方案：OpenFace CSV 持续写入 + 轮询增量读取**。
2. 所有模块必须通过统一数据契约通信，不允许隐式字段。
3. API 调用不可阻塞主输入链路，必须支持超时降级。
4. 所有实验必须能通过日志重放核心过程。

## 3. 推荐开发顺序

1. `common/contracts.py`
2. `common/config.py`
3. `algo/openface_stream.py`
4. `algo/calibrator.py`
5. `algo/smoother.py`
6. `algo/dwell_state_machine.py`
7. `system/keyboard_layout.py`
8. `system/hit_tester.py`
9. `system/input_controller.py`
10. `system/runtime.py`
11. `ai/prompt_builder.py`
12. `ai/codex_client.py`
13. `ai/candidate_engine.py`
14. `scripts/run_realtime_keyboard.py`

## 4. 代码风格与质量

1. Python 版本建议 3.10+。
2. 优先使用类型注解与 dataclass。
3. 每个模块需有最小可验证入口或单元测试桩。
4. 参数放入配置文件，不硬编码魔法数字。

## 5. 日志规范

最低日志类别：

- `raw_gaze`
- `runtime_event`
- `ai_event`
- `session_summary`

每条日志至少包含：`timestamp_ms`, `session_id`, `event_type`。

## 6. 实验规范

1. 至少支持 Baseline 与 AI-Enhanced 两组运行模式。
2. 保留配置快照，确保实验可复算。
3. 输出指标至少包含：完成时间、正确率、CPM、误触次数。

## 7. 变更策略

1. 先更新文档（设计/契约），再改代码。
2. 重大改动需在 README 中补充“变更说明”。
3. 优先保证主链路稳定，再做可视化与高级优化。
