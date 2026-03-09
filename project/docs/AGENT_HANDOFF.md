# 毕设项目交接文档（Agent Handoff）

更新时间：2026-03-09

## 1. 课题与目标

课题方向已冻结为：

1. 核心：基于 OpenFace 的实时视线估计优化
2. 应用：无障碍眼控输入系统（全键盘 + 候选词）
3. 评估：与 OpenFace baseline 对比（准确率/实时性/输入效率）

## 2. 已冻结决策

1. 开发环境：Ubuntu（无 GPU）
2. 主技术栈：Python 主控（必要时热点模块再下沉 C++）
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
   - `/home/lyh/workspace/run_rerank_demo.sh`
   - `/home/lyh/workspace/run_keyboard_mvp.sh`
   - `/home/lyh/workspace/run_keyboard_summary.sh`
4. 配置与工厂：
   - `src/gaze_mvp/config_loader.py`
   - `src/gaze_mvp/llm_factory.py`
   - `config/default.json`（新增 `llm` 字段）
5. 键盘日志分析脚本：
   - `scripts/summarize_keyboard_session.py`
6. 注视目标回放脚本：
   - `scripts/replay_dwell_targets.py`
   - `project/data/samples/dwell_targets_demo.csv`
   - `/home/lyh/workspace/run_dwell_replay.sh`

## 4. 关键路径与文档

1. 总规划文档：
   - `/home/lyh/workspace/毕业设计落地文档.md`
2. 启动确认清单：
   - `/home/lyh/workspace/项目启动确认清单.md`
3. OpenFace 安装验证记录：
   - `/home/lyh/workspace/OpenFace安装验证记录.md`

## 5. 当前阻塞与待确认

1. 摄像头实时验证待用户本机确认（自动化环境里无 `/dev/video0`）
2. OpenAI API 的具体模型名、环境变量与候选词 prompt 尚未写入配置（将在 `project/config` 中落地）

## 6. 下一步实现优先级（代码）

1. 先完成 baseline 流水线：
   - 调用 OpenFace
   - 解析 CSV 字段
   - 输出基础指标（成功率、帧数、gaze/pose 字段完整性）
2. 再完成眼控输入 MVP：
   - 标定
   - dwell 触发（事件流层已具备，待接真实眼控信号源）
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
