"""均匀三次 B 样条（uniform cubic B-spline）。

敌机的轨迹是**控制点**，不是路径上的采样点——由本项目的规格文档
（`docs/superpowers/specs/` 里那份，结论已并入 docs/DESIGN.md「关卡数据与坐标系」）
确认，参考项目的 `BasisSpline` 实现的就是这个。

**为什么是 B 样条而不是 Catmull-Rom**：两者在同一条数据上产生不同路径。
B 样条是**逼近型**（曲线落在控制点的凸包内，不穿过中间控制点），
Catmull-Rom 是**插值型**（穿过每个控制点）。实测 114 条真实轨迹：
B 样条越出控制点包围盒 0.0000px，Catmull-Rom 最大越界 13.6px、21/114 条超 5px。
而关卡数据里那些重复控制点正是 B 样条的标准写法，不需要任何特判：
连写 3 次让曲线**恰好穿过**该点，连写 12～13 次就是**停在那里**。

纯数学、只依赖 Vector2，因此能脱离 pygame 与贴图被完整测试——
同 player.py 里 clampToPlayfield 的理由。
"""

# 本模块的签名引用了 Vector2 注解，3.13 下需要延迟求值，理由见 vector2.py
from __future__ import annotations

from collections.abc import Sequence

from touhou.core.vector2 import Vector2

# 均匀三次 B 样条的特征矩阵。行对应幂次 1、u、u²、u³，列对应四个控制点。
# 这就是规格里给的那张矩阵，展开自标准的 (1/6)[(1-u)³, 3u³-6u²+4, -3u³+3u²+3u+1, u³]。
BASIS = (
    (1 / 6, 2 / 3, 1 / 6, 0.0),
    (-1 / 2, 0.0, 1 / 2, 0.0),
    (1 / 2, -1.0, 1 / 2, 0.0),
    (-1 / 6, 1 / 2, -1 / 2, 1 / 6),
)


def samplePath(points: Sequence[Vector2], u: float) -> Vector2:
    """求路径在参数 u 处的位置。

    u 的定义域是 `[0, len(points) - 1]`：整数 u 对应控制点，相邻两个整数之间
    是第 `int(u)` 段曲线。超出定义域会被钳到两端。

    端点用**镜像外插**补齐（首端 `2*p[0] - p[1]`，末端同理）。这一步不是可选的：
    没有它，曲线在端点处只能给出四点的加权平均，u=0 得到的位置不等于起点。
    有了它，u=0 恰好等于 `points[0]`、u=len-1 恰好等于 `points[-1]`，
    于是「敌人从 start_position 出发」是精确成立的，不靠近似。
    """
    if not points:
        raise ValueError("轨迹至少要有一个控制点")

    lastIndex = len(points) - 1
    if lastIndex == 0:
        # 单点路径：整条轨迹就是一个点。这是退化输入，真实数据里没有，
        # 但关卡数据是手写的，不该让上游的笔误变成除零或 IndexError。
        return points[0]

    u = min(max(u, 0.0), float(lastIndex))
    # u 恰好等于 lastIndex 时 int() 会指到不存在的最后一段，所以要钳住段号
    segment = min(int(u), lastIndex - 1)
    t = u - segment

    weights = [sum(BASIS[power][column] * t**power for power in range(4)) for column in range(4)]
    controlPoints = [_controlPointAt(points, segment - 1 + offset) for offset in range(4)]

    return Vector2(
        sum(weights[k] * controlPoints[k].x for k in range(4)),
        sum(weights[k] * controlPoints[k].y for k in range(4)),
    )


def _controlPointAt(points: Sequence[Vector2], index: int) -> Vector2:
    """取控制点，越界时按镜像外插给出虚拟点。

    注意镜像是在**点**上做，不是在下标上做：`points[-1]` 对应的虚拟点是
    `2*p[0] - p[1]`（把曲线沿端点翻折），而不是 `points[1]`。取错的话端点
    仍然平滑，只是曲线不再从起点开始——不会崩，只会让敌机整体偏移一点点。
    """
    if index < 0:
        if len(points) == 1:
            return points[0]
        return points[0] * 2.0 - points[1]
    if index >= len(points):
        return points[-1] * 2.0 - points[-2]
    return points[index]
