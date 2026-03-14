# 毕设项目交接文档（Agent Handoff）

更新时间：2026-03-14

## 1. 课题与目标

课题方向已冻结为：

1. 核心：基于 OpenFace 的实时视线估计优化
2. 应用：无障碍眼控输入系统（全键盘 + 候选词）
3. 评估：与 OpenFace baseline 对比（准确率/实时性/输入效率）

## 2. 已冻结决策

1. 开发环境：Ubuntu（无 GPU）
2. 主技术栈：C++ 核心 + Python 编排（分阶段迁移，保留 Python fallback）
3. OpenFace：使用官方 OpenFace 2.2.0（源码）
4. AI 增强：主线直连 OpenAI Responses API（LangChain 降级为可选封装）
5. Coze：不进入首版（作为可选扩展）
6. 首版交互：全键盘 + 候选词，dwell 默认 600ms

## 3. OpenFace 当前状态

1. 源码目录：
   - `/home/lyh/workspace/OpenFace-OpenFace_2.2.0`
2. 构建目录：
   - `/home/lyh/workspace/OpenFace-OpenFace_2.2.0/build_clean`
3. 已成功生成可执行：
   - `FeatureExtraction`
   - `FaceLandmarkVid`
   - `FaceLandmarkVidMulti`
   - `FaceLandmarkImg`
4. 为适配 Ubuntu 22.04 系统 dlib（19.10.0），已调整：
   - `CMakeLists.txt` 中 `find_package(dlib 19.13)` -> `find_package(dlib 19.10)`
5. 样例图验证通过：
   - `FeatureExtraction -f ../../samples/sample1.jpg` 已产出 `sample1.csv`

## 3.1 新增模块（2026-03-09）

1. 候选词重排：
   - `src/gaze_mvp/openai_responses_client.py`
   - `src/gaze_mvp/candidate_reranker.py`
2. 键盘 MVP 流程：
   - `src/gaze_mvp/keyboard_mvp.py`
   - `src/gaze_mvp/keyboard_event_flow.py`
   - `src/gaze_mvp/candidate_pool.py`
   - `src/gaze_mvp/dwell_detector.py`
   - `scripts/run_keyboard_mvp.py`
3. 单次重排验证脚本：
   - `scripts/demo_candidate_rerank.py`
   - `/home/lyh/workspace/run.sh rerank`
   - `/home/lyh/workspace/run.sh keyboard`
   - `/home/lyh/workspace/run.sh summary`
4. 配置与工厂：
   - `src/gaze_mvp/config_loader.py`
   - `src/gaze_mvp/llm_factory.py`
   - `config/default.json`（新增 `llm` 字段）
5. 键盘日志分析脚本：
   - `scripts/summarize_keyboard_session.py`
6. 注视目标回放脚本：
   - `scripts/replay_dwell_targets.py`
   - `project/data/samples/dwell_targets_demo.csv`
   - `/home/lyh/workspace/run.sh dwell`

## 3.2 新增模块（2026-03-10）

1. 坐标命中测试（gaze_x/gaze_y -> target_id）：
   - `src/gaze_mvp/gaze_hit_test.py`
2. 运行时闭环管线（hit-test -> dwell -> keyboard flow）：
   - `src/gaze_mvp/gaze_runtime_pipeline.py`
3. 坐标驱动脚本：
   - `scripts/run_gaze_pipeline.py`
   - `/home/lyh/workspace/run.sh gaze`
4. 样例与报告：
   - `project/data/samples/gaze_points_demo.csv`
   - `project/data/reports/gaze_pipeline_demo_report.json`

## 3.3 架构冻结补充（2026-03-10）

1. 迁移策略冻结为：`C++ 核心 + Python 编排`。
2. C++ 优先迁移模块：`dwell_detector / gaze_hit_test / calibration / smoothing`。
3. Python 保留模块：`keyboard_event_flow / candidate_reranker / openai client / scripts`。
4. 分阶段执行：M0-M4（接口冻结 -> 低风险迁移 -> 算法迁移 -> 实时接入 -> 性能验收）。

## 3.4 新增模块（2026-03-11）

1. 9 点标定拟合与参数加载：
   - `src/gaze_mvp/calibration.py`
   - `scripts/fit_9point_calibration.py`
2. 标定样例与短命令：
   - `project/data/samples/calibration_points_9_demo.csv`
   - `/home/lyh/workspace/run.sh calib`
3. 主管线接入：
   - `scripts/run_gaze_pipeline.py` 支持 `--calibration-json`

## 3.5 新增模块（2026-03-11）

1. 时序平滑：
   - `src/gaze_mvp/gaze_smoothing.py`（`EmaSmoother2D` / `OneEuroSmoother2D`）
2. 管线接入：
   - `src/gaze_mvp/gaze_runtime_pipeline.py` 支持可插拔 smoother
   - `scripts/run_gaze_pipeline.py` 支持 `--smoothing none|ema|one_euro`

## 3.6 新增模块（2026-03-13）

1. 在线 9 点采集（终端引导）：
   - `scripts/collect_9point_calibration.py`
2. 统一入口支持：
   - `/home/lyh/workspace/run.sh calib-collect --source-csv <path>`

## 3.7 新增模块（2026-03-13）

1. OpenFace 实时接入主脚本：
   - `scripts/run_openface_live_pipeline.py`
2. 统一入口支持：
   - `/home/lyh/workspace/run.sh gaze-live`
3. 能力：
   - 启动 OpenFace 摄像头采集并轮询增长中的输出 CSV
   - 将 `gaze_angle_x/gaze_angle_y` 映射到现有 `hit-test -> dwell -> keyboard` 事件链路
   - 支持 `--export-gaze-csv` 输出 `timestamp_ms,gaze_x,gaze_y`，用于标定采集链路复用

## 3.8 新增模块（2026-03-13）

1. 交互日志增强：
   - `src/gaze_mvp/dwell_detector.py`（新增 dwell 触发元信息）
   - `src/gaze_mvp/keyboard_event_flow.py`（日志新增 `event.metrics` 与 `analysis`）
2. 汇总能力增强：
   - `scripts/summarize_keyboard_session.py`
3. 能力：
   - 候选曝光统计（总曝光/Top曝光词）
   - dwell 时长统计（mean/p50/p90）
   - 撤销统计（`backspace_count` / `undo_backspace_count`）

## 3.9 新增模块（2026-03-13）

1. 固定测试句评估脚本：
   - `scripts/evaluate_keyboard_task.py`
2. 任务样例定义：
   - `data/samples/fixed_text_tasks_v1.csv`
3. 统一入口支持：
   - `/home/lyh/workspace/run.sh task-eval`
4. 能力：
   - 单次/批量评估会话日志，输出 `CER / CPM / WPM(5char)`。
   - 兼容旧日志与新日志字段（无 `metrics/analysis` 时自动降级）。
   - 聚合输出 `exact_match_rate`、平均 CER、平均输入速度与事件统计。

## 3.10 新增模块（2026-03-14）

1. M0 跨语言接口契约：
   - `cpp_core/include/gaze_core/contracts.h`
   - `src/gaze_mvp/runtime_contract.py`
2. 对齐样例与校验脚本：
   - `data/samples/m0_interface_alignment_samples.json`
   - `scripts/check_m0_contract.py`
3. 统一入口支持：
   - `/home/lyh/workspace/run.sh m0-check`
4. 能力：
   - 冻结 `FrameFeatures / GazePoint / TargetEvent` 字段定义
   - 支持用真实 session log 事件映射校验 `TargetEvent` 契约
   - 产出 `m0_contract_check_report.json` 作为接口冻结证据

## 3.11 新增模块（2026-03-14）

1. M1 C++ 核心实现（normalizer/hit-test/dwell）：
   - `cpp_core/include/gaze_core/runtime/m1.hpp`
   - `cpp_core/src/apps/m1_runtime_replay.cpp`
2. 对齐校验脚本：
   - `scripts/check_m1_alignment.py`
3. 统一入口支持：
   - `/home/lyh/workspace/run.sh m1-check`
4. 能力：
   - C++ 回放工具可直接读取 gaze csv 并输出 TargetEvent 序列
   - Python 参考实现与 C++ 结果逐事件对齐检查
   - 产出 `m1_alignment_check_report.json` 作为 M1 验收记录

## 3.12 新增模块（2026-03-14）

1. M2 C++ 核心实现（calibration/smoothing）：
   - `cpp_core/include/gaze_core/runtime/m2.hpp`
   - `cpp_core/src/apps/m2_runtime_replay.cpp`
2. 对齐校验脚本：
   - `scripts/check_m2_alignment.py`
3. 统一入口支持：
   - `/home/lyh/workspace/run.sh m2-check`
4. 能力：
   - C++ 实现仿射标定拟合（含 ridge 稳定项）并输出拟合指标
   - C++ 实现 `EMA` 与 `OneEuro` 2D 平滑，支持可配置参数
   - Python 参考实现与 C++ 数值对齐检查（模型参数/指标/轨迹）
   - 产出 `m2_alignment_check_report.json` 作为 M2 验收记录

## 3.13 新增模块（2026-03-14）

1. M3 过渡接入（C++回放后端 -> Python编排）：
   - `scripts/run_gaze_cpp_pipeline.py`
2. 统一入口支持：
   - `/home/lyh/workspace/run.sh gaze-cpp`
3. 能力：
   - 复用 C++ M1 回放工具输出 TargetEvent 序列
   - 由 Python `KeyboardEventFlow` 消费事件并产生日志与最终文本状态
   - 为后续 `pybind` 同进程接入保留事件契约与验证路径

## 3.14 新增模块（2026-03-14）

1. Python/C++ 后端切换与对比：
   - `scripts/run_gaze_pipeline.py`（新增 `--runtime-backend {python,cpp}`）
   - `scripts/compare_runtime_backends.py`
2. 统一入口支持：
   - `/home/lyh/workspace/run.sh backend-compare`
3. 能力：
   - 离线 gaze 管线可切换为 `cpp` 后端执行 `hit-test + dwell`
   - C++ 后端复用 Python 预处理（calibration/smoothing）后再进入 M1 回放核心
   - 产出 Python vs C++ wall time / 事件一致性对比报告，作为 M4 实验素材

## 4. 关键路径与文档

1. 总规划文档：
   - `/home/lyh/workspace/毕业设计落地文档.md`
2. 启动确认清单：
   - `/home/lyh/workspace/项目启动确认清单.md`
3. OpenFace 安装验证记录：
   - `/home/lyh/workspace/OpenFace安装验证记录.md`

## 5. 当前阻塞与待确认

1. OpenFace 实时输出流已接入，待补实机长时稳定性数据（多光照、多头姿）。
2. 已支持离线拟合 + 在线9点采集（终端引导）；后续可补图形化采集界面。
3. 固定测试句评估脚本已接入，待执行多轮实测并产出第5章对比表。
4. M3 过渡接入已落地，下一步可继续做同进程绑定（pybind）与实时流切换。

## 6. 下一步实现优先级（代码）

1. 先完成 baseline 流水线：
   - 调用 OpenFace
   - 解析 CSV 字段
   - 输出基础指标（成功率、帧数、gaze/pose 字段完整性）
2. 再完成眼控输入 MVP：
   - 标定
   - dwell 触发（已接坐标命中与 OpenFace 实时信号源）
   - 候选词增强（OpenAI Responses API，LangChain 可选）
3. 最后补实验脚本：
   - baseline vs 优化方法
   - 角误差/FPS/延迟/CER/WPM

## 7. 运行命令（已验证）

样例图：

```bash
cd /home/lyh/workspace/OpenFace-OpenFace_2.2.0/build_clean/bin
./FeatureExtraction \
  -mloc model/main_clnf_wild.txt \
  -f ../../samples/sample1.jpg \
  -out_dir /home/lyh/workspace/OpenFace-OpenFace_2.2.0/test_out
```

摄像头（待用户实机）：

```bash
cd /home/lyh/workspace/OpenFace-OpenFace_2.2.0/build_clean/bin
./FeatureExtraction \
  -mloc model/main_clnf_wild.txt \
  -device 0 \
  -out_dir /home/lyh/workspace/OpenFace-OpenFace_2.2.0/test_cam
```

坐标命中闭环（已验证）：

```bash
cd /home/lyh/workspace
bash run.sh gaze
```

OpenFace 实时输入闭环（新增）：

```bash
cd /home/lyh/workspace
bash run.sh gaze-live --max-seconds 20 --print-events
```
