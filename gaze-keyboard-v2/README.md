# Gaze Keyboard V2

面向毕业论文《基于 OpenFace 的实时视线估计优化》的重构工程目录。

本目录用于按“三层结构”实现系统：

1. 算法优化层（OpenFace 原始数据 -> 可用 gaze 点）
2. 系统实现层（实时眼控虚拟键盘）
3. 智能交互增强层（候选词补全，gpt-5.3-codex API）

---

## 1. 目录规划

```text
gaze-keyboard-v2/
  README.md
  AGENT.md
  project/
    src/
      gaze_keyboard/
        algo/
        system/
        ai/
        common/
    scripts/
    config/
    logs/
```

---

## 2. 当前阶段

当前为 **文档与工程骨架阶段**，尚未开始写具体业务代码。

后续编码顺序建议：

1. `common/contracts.py`：数据契约（RawGazeSample、ScreenGazePoint、DwellEvent...）
2. `algo/openface_stream.py`：B 方案 CSV 增量轮询
3. `algo/calibrator.py` + `algo/smoother.py` + `algo/dwell_state_machine.py`
4. `system/keyboard_layout.py` + `system/hit_tester.py` + `system/runtime.py`
5. `ai/prompt_builder.py` + `ai/codex_client.py` + `ai/candidate_engine.py`
6. `scripts/run_realtime_keyboard.py`：端到端入口

---

## 3. 运行目标（MVP）

MVP 完成标准：

- 实时读取 OpenFace CSV 增量数据
- 将 gaze 映射到屏幕坐标并完成基本平滑
- 可通过 dwell 在虚拟键盘触发输入
- 记录会话日志用于后续实验分析

增强目标：

- 接入 AI 候选词补全
- API 超时自动降级，不阻塞主链路

---

## 4. 与论文映射

- 第3章：算法优化（标定、平滑、异常过滤、停留触发）
- 第4章：系统实现（实时输入链路与键盘系统）
- 第5章：实验分析（Baseline vs AI-Enhanced）

---

## 5. 注意事项

- 当前项目主接入方案固定为：**OpenFace CSV 持续写入 + 轮询读取（B方案）**
- 录制回放仅用于复现实验，不作为主交互链路
- 所有关键过程需记录日志，确保实验可复现
