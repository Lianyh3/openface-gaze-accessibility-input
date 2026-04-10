基于 OpenFace 的实时视线估计优化与课堂注意力检测系统 — 落地文档

项目名称：gaze-attention-system
版本：0.1.0
状态：Phase 3 完成，Phase 4 待实现

═══════════════════════════════════════════════════════════════════════════════

一、项目概述

本系统是一个 Windows 原生应用，用于实时检测课堂学生的注意力状态。核心技术路线：

  摄像头 → OpenFace 2.2.0 (子进程) → CSV 实时输出
    → Python 处理管线 (平滑、特征提取、判断)
    → PySide6 GUI 可视化 (状态指示灯、注视轨迹、统计信息)

毕设核心贡献：
  1. 注视方向平滑优化（对比 EMA、One Euro Filter）
  2. 多维特征融合（注视偏离 + 头部姿态 + 眨眼）
  3. 大模型 vs 规则引擎对比（GPT-4o-mini 与传统阈值判断）

═══════════════════════════════════════════════════════════════════════════════

二、技术栈

- Python 3.11+
- PySide6（GUI 框架）
- OpenFace 2.2.0（视线估计引擎，Windows 版本）
- OpenAI API（GPT-4o-mini，可选）
- 标准库：pathlib, json, subprocess, csv, math, statistics, time, logging

═══════════════════════════════════════════════════════════════════════════════

三、项目结构

gaze-attention-system/
├── pyproject.toml                          # Python 包配置
├── config/
│   └── default.json                        # 运行时配置（OpenFace 路径、参数）
├── src/gaze_input/                         # 核心库
│   ├── __init__.py
│   ├── openface_runner.py                  # OpenFace 子进程管理
│   ├── csv_parser.py                       # CSV 增量读取（半行容错）
│   ├── smoothing.py                        # 平滑算法（NoSmooth/EMA/OneEuro）
│   ├── label_schema.py                     # 注意力标签定义
│   ├── feature_extractor.py                # 多维特征提取 + 窗口聚合
│   ├── rule_engine.py                      # 规则引擎判断（基线）
│   ├── prompt_schema.py                    # GPT prompt 模板
│   ├── gpt_analyzer.py                     # GPT 大模型判断 + 降级
│   └── metrics.py                          # 评估指标计算
├── gui/
│   ├── __init__.py
│   ├── main_window.py                      # 主窗口（控制面板 + 仪表盘）
│   └── attention_dashboard.py              # 注意力仪表盘（状态灯、轨迹、统计）
├── scripts/
│   └── run_app.py                          # 主入口脚本
├── experiments/                            # 对比实验脚本（待实现）
│   ├── compare_smoothing.py
│   ├── compare_features.py
│   └── compare_gpt_vs_rules.py
└── data/
    ├── samples/                            # 测试数据
    └── results/                            # 实验结果输出

═══════════════════════════════════════════════════════════════════════════════

四、核心模块说明

【Phase 1 — 数据管线】✅ 完成

1. openface_runner.py
   - 启动 FeatureExtraction.exe 子进程
   - 管理生命周期（启动、健康检查、优雅关闭）
   - 返回输出 CSV 路径

2. csv_parser.py
   - 增量读取 OpenFace CSV（记录文件位置，只读新行）
   - 半行容错（最后一行不完整时跳过）
   - 低置信度过滤（confidence < 0.7 的帧丢弃）
   - 输出 FrameData 结构体

3. label_schema.py
   - 三级标签枚举：FOCUSED / DISTRACTED / SEVERELY_DISTRACTED / UNCERTAIN
   - 标注规范文档

【Phase 2 — 特征与判断】✅ 完成

4. smoothing.py（论文核心优化1）
   - NoSmooth：基线，无平滑
   - EMASmooth：指数移动平均（alpha 参数可配）
   - OneEuroSmooth：自适应低通滤波（min_cutoff, beta, d_cutoff 参数）
   - GazeSmoother：对 gaze_x 和 gaze_y 分别独立平滑

5. feature_extractor.py（论文核心优化2）
   - 滑动窗口特征提取（默认 2 秒窗口）
   - 特征包括：
     * 注视偏离度（均值、标准差、最大值）
     * 头部姿态（俯仰角、偏航角）
     * 眨眼强度和频率
     * 有效帧占比
   - 输出 FeatureWindow 结构体（JSON 可序列化）

6. rule_engine.py
   - 基于阈值的规则判断（基线方案）
   - 规则：
     * gaze_deviation > 0.3 → SEVERELY_DISTRACTED
     * head_yaw > 20° → SEVERELY_DISTRACTED
     * head_pitch > 15° → SEVERELY_DISTRACTED
     * gaze_deviation > 0.15 → DISTRACTED
     * 否则 → FOCUSED

7. gpt_analyzer.py（论文核心优化3）
   - 调用 OpenAI GPT-4o-mini API
   - 结构化输入：FeatureWindow JSON
   - 结构化输出：{"label": "...", "reason": "...", "confidence": 0.0-1.0}
   - 降级策略：API 失败时自动回退到规则引擎
   - 记录延迟和 token 消耗

8. prompt_schema.py
   - 系统 prompt：定义 GPT 的角色和输出格式
   - 用户 prompt 模板：填充窗口统计特征
   - 输出 schema 校验

9. metrics.py
   - MetricsAccumulator：累积预测结果
   - 计算：准确率、精确率、召回率、F1、误报率、漏报率
   - 计算：平均延迟、总 token 消耗

【Phase 3 — GUI】✅ 完成

10. main_window.py
    - PySide6 主窗口
    - 左侧控制面板：
      * 平滑算法选择（none/ema/one_euro）
      * 判断路径选择（规则引擎/GPT）
      * 开始/停止按钮
    - 右侧注意力仪表盘
    - 定时器驱动（~30fps）处理帧数据

11. attention_dashboard.py
    - StatusIndicator：状态指示灯（绿/黄/红）
    - GazeTrajectory：注视轨迹图（最近 100 个点）
    - AttentionDashboard：组合控件
      * 显示当前状态和原因
      * 显示注视轨迹
      * 显示帧数和延迟统计

【Phase 4 — 实验脚本】⏳ 待实现

12. experiments/compare_smoothing.py
    - 离线对比三种平滑算法
    - 指标：抖动量（标准差）、响应延迟

13. experiments/compare_features.py
    - 对比单特征 vs 多特征融合
    - 对比固定阈值 vs 滑动窗口

14. experiments/compare_gpt_vs_rules.py
    - 同一批标注数据，分别用规则引擎和 GPT 判断
    - 对比准确率、误报率、漏报率、延迟、成本

═══════════════════════════════════════════════════════════════════════════════

五、运行流程

1. 启动应用
   python scripts/run_app.py

2. 点击"开始检测"
   - 启动 OpenFace 子进程
   - 初始化处理管线（平滑、特征提取、判断）
   - 启动定时器，每 33ms 处理一批新帧

3. 实时处理
   - 读取 OpenFace CSV 新行
   - 平滑注视角度
   - 更新特征窗口
   - 提取聚合特征
   - 调用规则引擎或 GPT 判断
   - 更新 GUI（状态灯、轨迹、统计）

4. 停止检测
   - 点击"停止检测"
   - 优雅关闭 OpenFace 子进程
   - 清理资源

═══════════════════════════════════════════════════════════════════════════════

六、配置文件（config/default.json）

{
  "openface": {
    "bin_path": "D:/OpenFace/build/bin/Release/FeatureExtraction.exe",
    "device": 0,
    "output_dir": "./data/runtime"
  },
  "smoothing": {
    "method": "one_euro",
    "ema_alpha": 0.3,
    "one_euro_min_cutoff": 1.0,
    "one_euro_beta": 0.007,
    "one_euro_d_cutoff": 1.0
  },
  "feature": {
    "window_size_sec": 2.0,
    "min_valid_frame_ratio": 0.7,
    "confidence_threshold": 0.7,
    "gaze_baseline_x": 0.0,
    "gaze_baseline_y": 0.0
  },
  "rule_engine": {
    "gaze_deviation_mild": 0.15,
    "gaze_deviation_severe": 0.3,
    "head_yaw_threshold": 20.0,
    "head_pitch_threshold": 15.0,
    "severe_duration_sec": 8.0
  },
  "gpt": {
    "model": "gpt-4o-mini",
    "api_key_env": "OPENAI_API_KEY",
    "temperature": 0,
    "call_interval_sec": 3.0,
    "timeout_sec": 5.0,
    "fallback_to_rules": true
  },
  "gui": {
    "refresh_fps": 30,
    "timeline_history_sec": 60
  }
}

关键参数说明：
- openface.bin_path：修改为你编译的 FeatureExtraction.exe 路径
- smoothing.method：选择平滑算法（论文对比实验用）
- gpt.api_key_env：从环境变量读取 OpenAI API key
- rule_engine 中的阈值：可根据实验调整

═══════════════════════════════════════════════════════════════════════════════

七、依赖安装

pip install PySide6 numpy openai

═══════════════════════════════════════════════════════════════════════════════

八、论文对应关系

第3章 视线估计优化
  - 3.1 平滑优化：smoothing.py 中的三种算法对比
  - 3.2 特征融合：feature_extractor.py 中的多维特征设计
  - 3.3 实验对比：experiments/compare_smoothing.py 和 compare_features.py

第4章 系统设计与实现
  - 4.1 整体架构：main_window.py 的数据流
  - 4.2 核心模块：各个 src/gaze_input/*.py 的设计
  - 4.3 GUI 设计：gui/*.py 的界面和交互

第5章 实验与结果
  - 5.1 平滑算法对比：experiments/compare_smoothing.py 的结果
  - 5.2 特征方案对比：experiments/compare_features.py 的结果
  - 5.3 GPT vs 规则引擎：experiments/compare_gpt_vs_rules.py 的结果
  - 5.4 性能指标：metrics.py 计算的准确率、延迟、成本

═══════════════════════════════════════════════════════════════════════════════

九、已完成的工作

✅ Phase 0：环境搭建指引（用户手动完成）
✅ Phase 1：项目骨架 + 数据管线
  - pyproject.toml、config/default.json
  - openface_runner.py、csv_parser.py、label_schema.py
✅ Phase 2：特征与判断
  - smoothing.py（三种平滑算法）
  - feature_extractor.py（多维特征提取）
  - rule_engine.py、gpt_analyzer.py、prompt_schema.py、metrics.py
✅ Phase 3：GUI
  - main_window.py（主窗口 + 控制面板）
  - attention_dashboard.py（仪表盘 + 可视化）
  - scripts/run_app.py（主入口）

═══════════════════════════════════════════════════════════════════════════════

十、待完成的工作

⏳ Phase 4：实验脚本
  - experiments/compare_smoothing.py
  - experiments/compare_features.py
  - experiments/compare_gpt_vs_rules.py

⏳ 标注数据集
  - 需要收集 10-20 人的课堂视频
  - 手工标注注意力标签（FOCUSED/DISTRACTED/SEVERELY_DISTRACTED）
  - 用于实验对比和论文数据

⏳ 论文写作
  - 第3-5章的实验数据和图表
  - 性能对比分析

═══════════════════════════════════════════════════════════════════════════════

十一、快速开始

1. 编译 OpenFace 2.2.0（Windows 版本）
   - 参考 Phase 0 指引
   - 修改 config/default.json 中的 openface.bin_path

2. 安装依赖
   pip install PySide6 numpy openai

3. 设置 OpenAI API key（可选，不设置时自动降级到规则引擎）
   set OPENAI_API_KEY=sk-...

4. 运行应用
   python scripts/run_app.py

5. 点击"开始检测"，选择平滑算法和判断路径，观察实时结果

═══════════════════════════════════════════════════════════════════════════════

十二、常见问题

Q: OpenFace 编译失败？
A: 参考 Phase 0 的详细步骤，确保 Visual Studio、CMake、Git 都已安装。

Q: 摄像头无法识别？
A: 检查 config/default.json 中的 device 参数（0 = 默认摄像头）。

Q: GPT 调用超时？
A: 检查网络连接和 API key 是否正确。系统会自动降级到规则引擎。

Q: GUI 显示不正常？
A: 确保 PySide6 版本 >= 6.6，运行 pip install --upgrade PySide6。

═══════════════════════════════════════════════════════════════════════════════

十三、代码统计

总代码量：约 1200 行 Python
  - 核心库（src/gaze_input/）：约 650 行
  - GUI（gui/）：约 250 行
  - 主入口（scripts/）：约 50 行
  - 实验脚本（experiments/）：待实现

═══════════════════════════════════════════════════════════════════════════════

十四、下一步建议

1. 完成 Phase 4 实验脚本
2. 收集标注数据集（10-20 人）
3. 运行对比实验，生成论文数据
4. 撰写论文第3-5章
5. 答辩演示：实时运行系统，展示三种平滑算法的效果对比

═══════════════════════════════════════════════════════════════════════════════

═══════════════════════════════════════════════════════════════════════════════

十五、最新进度快照（2026-04-06 晚）

✅ 已新增与修复（本次对话完成）

1) OpenFace 启动稳定性
- 修复 pyproject 构建后端，`pip install -e .` 可正常安装
- OpenFaceRunner 支持 `mloc` 参数（模型路径）
- 启动时使用 OpenFace bin 目录作为工作目录，避免模型相对路径丢失
- 输出 CSV 改为绝对路径前缀（`-of` 绝对路径），避免 cwd 导致写错目录
- 启动前清理旧 `gaze_output.csv`，避免历史残留干扰

2) 实时数据链路
- CSV 增量解析器修复半行容错逻辑（更稳）
- GUI 每次启动会重置轨迹、状态和统计（干净会话）

3) 视线优化（论文核心）
- 新增 `adaptive_ema`（线性自适应 EMA）
- GUI 平滑选项新增 `adaptive_ema`
- 默认平滑方法改为 `adaptive_ema`
- 增加实时抖动指标显示：`抖动(std)`

4) 注意力判断规则优化
- 从“瞬时阈值触发”升级为“持续时间累积触发”
- 支持 faster recovery（衰减率参数）：
  - `severe_decay_rate`
  - `distracted_decay_rate`
- 阈值策略已放宽，减少误报“严重走神”

5) 基线偏置修复
- 增加“启动后短时自校准”逻辑（约 45 帧）
- 校准期间状态为 `UNCERTAIN`
- 用个体中性姿态/注视偏置做后续判断基线

═══════════════════════════════════════════════════════════════════════════════

十六、当前可运行能力（你现在就能演示）

- 已可实时运行：摄像头 → OpenFace → 平滑 → 特征 → 规则判定 → GUI
- 已支持 GPT 路径（未配置 key 时自动降级，不会崩溃）
- 已能观察三类核心可视化：状态、轨迹、抖动指标

启动命令：
- `python scripts/run_app.py`

═══════════════════════════════════════════════════════════════════════════════

十七、是否“实验完整、可写论文”

结论：
- 目前“系统实现章节（第4章）”基本可写
- “优化方法章节（第3章）”已具备代码基础，可写方法设计
- “实验结果章节（第5章）”还不完整，需要补数据与对比结果

还缺的最小闭环（建议按顺序）：
1. 采集并标注一批数据（至少 8-10 人，含专注/走神/严重走神片段）
2. 跑完三组实验并导出结果表：
   - 平滑算法对比（none/ema/adaptive_ema/one_euro）
   - 特征方案对比（单特征 vs 多特征）
   - 规则 vs GPT（准确率、误报、漏报、延迟、成本）
3. 固化参数与实验配置，保证可复现
4. 生成论文图表（趋势图、柱状图、混淆矩阵）

═══════════════════════════════════════════════════════════════════════════════

十八、后续你该怎么设计与优化（论文可直接写）

A. 系统设计（可写到第4章）
- 数据流分层：采集层、预处理层、判定层、展示层
- 判定双路：规则引擎（实时主路）+ GPT（低频复核）
- 失败降级：GPT 不可用自动回退规则引擎

B. 优化策略（可写到第3章）
1) 平滑优化
- 对比 no/ema/adaptive_ema/one_euro
- 指标：抖动 std、响应延迟（突变后回稳时间）

2) 特征优化
- 单特征（仅 gaze）vs 多特征（gaze+pose+blink）
- 固定阈值 vs 滑动窗口统计

3) 规则优化
- 累积触发 + 迟滞回归，降低误报
- 引入自校准，降低个体差异偏置

4) GPT优化
- 结构化 prompt + 固定输出 schema
- 低频调用（如 2-3s）+ 冲突裁决策略
- 统计 token 成本与延迟

C. 参数调优建议（当前默认可作为起点）
- `smoothing.method = adaptive_ema`
- `adaptive_ema_alpha_min=0.12, alpha_max=0.65, delta_ref=0.03`
- `gaze_deviation_mild=0.18, severe=0.35`
- `distracted_duration_sec≈2.2, severe_duration_sec≈6.0`

═══════════════════════════════════════════════════════════════════════════════

更新时间：2026-04-06
项目状态：Phase 3.5 完成（系统可运行 + 关键优化已落地），Phase 4 实验数据与结果待补齐
