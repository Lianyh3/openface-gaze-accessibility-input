# Gaze Keyboard V2 实现状态文档

## 1. 文档目的

本文件用于记录当前阶段已落地实现的内容、验证状态、遗留问题与后续计划。
用于后续周回顾、论文同步与 Git 提交说明。

---

## 2. 当前实现范围（已落地）

### 2.1 工程与文档骨架
- `gaze-keyboard-v2/README.md`
- `gaze-keyboard-v2/AGENT.md`
- `gaze-keyboard-v2/project/README.md`
- `gaze-keyboard-v2/project/pyproject.toml`

### 2.2 核心模块（MVP 骨架）

#### common
- `common/contracts.py`
  - `RawGazeSample`
  - `ScreenGazePoint`
  - `DwellEvent`
  - `KeyboardAction`
  - `CandidateSuggestion`
- `common/config.py`
  - 使用 `pydantic` 实现配置模型与字段约束

#### algo
- `algo/openface_stream.py`
  - B 方案：OpenFace CSV 持续写入 + 轮询读取
- `algo/calibrator.py`
  - 线性映射版本（占位实现）
- `algo/smoother.py`
  - EMA 平滑
- `algo/dwell_state_machine.py`
  - 停留状态机：`enter/stay/fire/cancel`

#### system
- `system/keyboard_layout.py`
  - 基础 QWERTY 布局
- `system/hit_tester.py`
  - gaze 点命中键位
- `system/input_controller.py`
  - 字符、空格、退格输入逻辑
- `system/logger.py`
  - 事件日志：raw/runtime/ai/summary
- `system/runtime.py`
  - 端到端运行时编排

#### ai
- `ai/prompt_builder.py`
  - 候选词补全提示词模板
- `ai/codex_client.py`
  - `gpt-5.3-codex` API 调用与降级
- `ai/candidate_engine.py`
  - 前缀阈值、缓存、去重清洗

#### scripts
- `scripts/run_realtime_keyboard.py`
  - 运行入口（支持 AI 参数）
- `scripts/smoke_test_pipeline.py`
  - 最小闭环冒烟验证
- `scripts/smoke_test_runtime.py`
  - runtime 冒烟验证

---

## 3. 已验证结论

1. 最小链路已打通：
   `poll -> calibrate -> smooth -> hit -> dwell -> input`
2. dwell 触发后可写入文本（冒烟场景得到 `A`）
3. 日志已可落盘，支持后续复盘
4. AI 模块可接入，并支持失败降级（不阻塞主链路）

---

## 4. 当前已知限制（正常）

1. `calibrator` 仍为线性占位，尚未切换九点标定拟合
2. 候选词目前完成“生成与记录”，候选词 gaze 选择交互尚未做
3. 尚未完成实验统计脚本（CPM、误触率、候选使用率等自动汇总）
4. 尚未接入可视化 UI（属于 P2 可选）

---

## 5. 下一阶段建议（按优先级）

### P0（优先）
1. 候选词选择交互闭环（从建议到插入文本）
2. `eval_session.py`：从日志自动算指标
3. 九点标定参数化替换线性占位标定

### P1（建议）
1. 参数配置文件化（将关键参数转移到 `config/*.yaml`）
2. 误触抑制策略（热区扩展/目标吸附/refractory）
3. 运行时异常恢复与更细粒度错误日志

### P2（可选）
1. 可视化调试界面
2. 多布局键盘
3. 多语言候选策略

---

## 6. 论文映射回顾

- 第3章（算法优化）：`openface_stream + calibrator + smoother + dwell`
- 第4章（系统实现）：`runtime + keyboard + hit_test + logger`
- 第5章（实验分析）：`baseline vs ai-enhanced`（待补 `eval_session.py`）

---

## 7. 阶段完成定义（用于回顾打勾）

- [x] 工程目录与规范文档建立
- [x] B 方案输入链路可运行
- [x] 最小键盘输入闭环可运行
- [x] 日志体系可落地
- [x] AI 候选模块接入（含降级）
- [ ] 候选词选择闭环
- [ ] 实验统计脚本
- [ ] 九点标定替换

---

## 8. 本文档维护约定

每完成一次功能迭代，更新：
1. “当前实现范围”
2. “已知限制”
3. “阶段完成定义”

建议在每次 Git 提交前更新一次，保持文档与代码同步。
