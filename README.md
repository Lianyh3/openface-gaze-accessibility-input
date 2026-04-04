# openface-gaze-accessibility-input

毕业设计仓库，包含两类内容：

1. 论文写作文档（含章节草稿、参考文献、配图源文件）
2. 眼控输入系统代码（OpenFace + gaze pipeline + keyboard MVP）

当前策略：先保留现有代码与论文资产，后续由多 agent 分阶段重构。

## 仓库结构

- `project/`：主代码目录（Python 编排 + C++ 核心）
- `run.sh`：统一运行入口
- `docs/figures/`：论文插图源文件与导出包
- `论文*.md`：论文正文草稿与辅助写作文档
- `毕业设计落地文档.md`：总体落地方案

## 关键文档（论文不删）

- `毕业设计落地文档.md`
- `论文终稿_摘要关键词章节标题_贴模板版.md`
- `论文初稿_目录.md`
- `论文初稿_中文摘要.md`
- `论文初稿_英文摘要.md`
- `论文初稿_第1章_绪论.md`
- `论文初稿_第2章_相关技术与理论基础.md`
- `论文初稿_第3章_基于OpenFace的实时视线估计优化方法.md`
- `论文初稿_第4章_无障碍眼控输入系统设计与实现.md`
- `论文初稿_第5章_实验设计与结果分析.md`
- `论文初稿_第6章_结论与展望.md`
- `论文参考文献_真实文献清单.md`
- `docs/figures/*.drawio`

## 代码快速入口

查看命令总览：

```bash
bash run.sh help
```

常用命令：

```bash
bash run.sh keyboard
bash run.sh gaze
bash run.sh gaze-live
bash run.sh e2e-batch --execution-mode headless_replay --task-ids T01,T02
```

详细代码说明见：

- `project/README.md`
- `project/docs/AGENT_HANDOFF.md`
- `docs/REFACTOR_HANDOFF.md`

## 重构交接说明

为后续 agent 准备的重构入口文档：

- `docs/REFACTOR_HANDOFF.md`

包含内容：

1. 重构边界（哪些能动、哪些不要动）
2. 优先级与阶段拆分
3. 验收命令与提交规范
4. Windows + WSL2 迁移建议

## Skills（随仓库迁移）

已将 `lunwen` 技能随仓库存放到：

- `skills/lunwen`

新环境 clone 后安装到本机 Codex 目录：

```bash
bash scripts/install_lunwen_skill.sh --force
```

如希望直接软链接到仓库目录（便于后续同步）：

```bash
bash scripts/install_lunwen_skill.sh --force --link
```

安装后需重启 Codex 才会生效。
