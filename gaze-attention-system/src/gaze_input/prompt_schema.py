"""GPT prompt 模板与输出 schema 定义。"""

SYSTEM_PROMPT = """你是一个课堂注意力分析助手。根据学生的视线和头部姿态特征数据，判断其注意力状态。

你必须严格按照以下 JSON 格式输出，不要输出任何其他内容：
{"label": "focused|distracted|severely_distracted", "reason": "简短原因", "confidence": 0.0-1.0}

判断标准：
- focused: 注视偏离小，头部姿态稳定
- distracted: 注视有一定偏离，或头部有轻微转动
- severely_distracted: 注视严重偏离，或头部大幅低头/转头，或眨眼异常频繁"""

USER_TEMPLATE = """以下是过去 {window_sec:.1f} 秒的学生行为特征统计：

注视偏离度: 均值={gaze_deviation_mean:.4f}, 标准差={gaze_deviation_std:.4f}, 最大值={gaze_deviation_max:.4f}
头部俯仰角: 均值={head_pitch_mean:.1f}°, 最大绝对值={head_pitch_max:.1f}°
头部偏航角: 均值={head_yaw_mean:.1f}°, 最大绝对值={head_yaw_max:.1f}°
眨眼强度均值: {blink_intensity_mean:.2f}, 眨眼次数: {blink_count}
有效帧数: {frame_count}, 有效帧占比: {valid_ratio:.1%}

请判断该学生的注意力状态。"""

# GPT 输出的期望 schema（用于校验）
OUTPUT_KEYS = {"label", "reason", "confidence"}
VALID_LABELS = {"focused", "distracted", "severely_distracted"}
