# gaze-attention-system（简化可运行版）

基于 OpenFace 的实时视线估计与课堂注意力检测系统。

## 1. 环境准备

- Python 3.11+
- Windows 下可执行的 OpenFace `FeatureExtraction.exe`

安装依赖：

```bash
pip install -e .
```

如果你不走 editable 安装，也可：

```bash
pip install PySide6 numpy openai
```

## 2. 配置

编辑 `config/default.json`：

- `openface.bin_path` 改为本机 `FeatureExtraction.exe` 绝对路径
- `openface.device` 默认 0（摄像头）
- 若使用 GPT，设置环境变量 `OPENAI_API_KEY`

## 3. 启动 GUI

```bash
python scripts/run_app.py
```

界面中可选择：
- 平滑算法：`none / ema / one_euro`
- 判断路径：`规则引擎 / GPT`

## 4. 跑实验（最小版本）

先保证有一份 OpenFace 输出 CSV（例如 `data/runtime/gaze_output.csv`），然后：

```bash
python experiments/compare_smoothing.py --csv data/runtime/gaze_output.csv
python experiments/compare_features.py --csv data/runtime/gaze_output.csv
python experiments/compare_gpt_vs_rules.py --csv data/runtime/gaze_output.csv
```

## 5. 当前实现说明

- 已优先保证“先跑起来”：
  - OpenFace 子进程稳定启动/停止
  - CSV 增量读取支持半行容错
  - 实时 GUI 状态显示
  - 三个实验脚本可直接运行（最小可用）

- 后续可逐步增强：
  - 标注数据对齐与完整评估指标（准确率/F1/误报率）
  - GPT 输出 schema 的更严格校验与重试
  - 更细的时延与成本统计
