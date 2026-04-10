"""注意力标签定义。"""

from enum import Enum


class AttentionLabel(Enum):
    """三级注意力标签。"""
    FOCUSED = "focused"                        # 专注：持续看屏幕方向，头姿稳定
    DISTRACTED = "distracted"                  # 走神：短时偏离 2-5 秒
    SEVERELY_DISTRACTED = "severely_distracted" # 严重走神：持续偏离 >8s / 低头 / 频繁转头
    UNCERTAIN = "uncertain"                    # 有效帧不足，无法判定
