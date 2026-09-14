"""窗口缩放。

每个逻辑像素要映射成整数个物理像素，否则像素画的方块会变成大小不一的
矩形，看起来像蒙了一层脏东西。宁可留黑边也不做非整数缩放。
"""

from typing import Final

# 缩放倍率的下限。返回 0 会让渲染尺寸为零，比窗口超出屏幕更糟。
MIN_SCALE_FACTOR: Final = 1


def chooseScaleFactor(
    displayWidth: int, displayHeight: int, logicalWidth: int, logicalHeight: int
) -> int:
    """选出能塞进显示器的最大整数倍率，最小为 1。

    显示器比逻辑分辨率还小时返回 1——此时窗口会超出屏幕，但至少能玩。
    """
    byWidth = displayWidth // logicalWidth
    byHeight = displayHeight // logicalHeight
    return max(MIN_SCALE_FACTOR, min(byWidth, byHeight))


def scaledSize(logicalWidth: int, logicalHeight: int, scaleFactor: int) -> tuple[int, int]:
    return (logicalWidth * scaleFactor, logicalHeight * scaleFactor)
