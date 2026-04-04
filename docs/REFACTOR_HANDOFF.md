# REFACTOR HANDOFF

更新时间：2026-04-04

本文档用于给后续 agent 做代码重构接手，不用于替代论文正文。

## 1. 当前目标

1. 保留已有论文文档，不删除、不改名、不迁移路径。
2. 代码允许重构，但优先保证可运行与可验收。
3. 先做结构与工程化重构，再做算法替换。

## 2. 不可破坏项

1. 根目录所有 `论文*.md` 文件。
2. `毕业设计落地文档.md`。
3. `docs/figures/*.drawio` 及终版导出包。
4. 统一入口脚本 `run.sh`（允许内部实现调整，但命令名尽量兼容）。

## 3. 代码边界

主代码目录：`project/`

- Python：`project/src/gaze_mvp/`
- 脚本：`project/scripts/`
- C++ 核心：`project/cpp_core/`
- 配置：`project/config/default.json`

当前代码是“能跑优先”的状态，存在以下典型重构点：

1. 绝对路径耦合（例如 `/home/lyh/workspace/...`）
2. 脚本职责重叠（多个入口功能有交叉）
3. 运行参数与配置分散（CLI 参数与 json 配置重复）
4. 缺少统一测试入口（主要靠脚本手工验收）

## 4. 建议重构顺序

### Phase A: 工程化收敛（低风险）

1. 引入统一路径解析（项目根目录自动发现），消除硬编码绝对路径。
2. 统一日志与报告输出目录约定。
3. 保持 `run.sh` 命令兼容，内部改为调用单一 Python CLI。

### Phase B: 模块化拆分（中风险）

1. 抽象三层：
   - data adapters（OpenFace CSV / live stream）
   - runtime core（calibration / smoothing / hit-test / dwell）
   - app flow（keyboard / candidate rerank / event logging）
2. 将 `scripts/*.py` 逐步转为 thin wrapper。

### Phase C: 测试与基线固化（中风险）

1. 为关键模块补单元测试：
   - `calibration.py`
   - `gaze_smoothing.py`
   - `dwell_detector.py`
   - `gaze_hit_test.py`
2. 为关键脚本补最小端到端回归用例（headless）。

### Phase D: 平台迁移（可选）

1. 优先方案：Windows + WSL2（保留 Linux 工具链行为）。
2. 不建议直接 Windows-only 重写，先确保跨平台路径/换行兼容。

## 5. 最小验收命令

在仓库根目录执行：

```bash
bash run.sh help
bash run.sh m0-check
bash run.sh m1-check
bash run.sh m2-check
bash run.sh gaze --runtime-backend python
bash run.sh gaze --runtime-backend cpp
bash run.sh backend-compare
```

如无摄像头或图形界面，可优先使用离线/回放命令完成验收。

## 6. 提交建议

1. 每个阶段单独 PR（A/B/C/D）。
2. PR 说明里至少包含：
   - 改动范围
   - 风险点
   - 验收命令与结果
3. 不把大体积实验产物提交到 Git（`project/data/experiments/` 已忽略）。

## 7. 关联文档

1. 根目录总览：`README.md`
2. 代码说明：`project/README.md`
3. 历史交接：`project/docs/AGENT_HANDOFF.md`
