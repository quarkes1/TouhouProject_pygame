"""扇形（锥形）弹幕。

从一点打出一个对称的扇形：恰好 `bulletCount` 发，相邻两发夹角正好是
`deltaAngleDeg`，扇面总宽 `(bulletCount - 1) × deltaAngleDeg`。

扇形的生成式照参考项目：`for i in range(-N+1, N, 2)`，角度取
`基准角 + i × 相邻角差 × 0.5`。步长 2 配 0.5 的系数，正好让相邻两发差一个
`相邻角差`，且 N 为奇数时有正中一发、N 为偶数时没有——两种都在真实数据里出现过
（`bulletCount` 为 3 与 5 时居中，为 4 时不居中）。

基准角有两种来源：数据里写数字就用数字，写 `"player"` 就朝自机——后者由调用方
算好角度放进 `FiringContext.aimAngleDeg`，本模块不接触自机。
"""

# 为注解开启延迟求值，理由见 vector2.py 的同类注释
from __future__ import annotations

from dataclasses import dataclass

from touhou.game.entities.bullet import BulletSpec
from touhou.game.patterns.registry import FiringContext, registerPattern


@dataclass(frozen=True, slots=True)
class WideConeParams:
    """`wide_cone` 的参数。字段名与关卡数据里的名字一一对应。

    `baseAngleDeg` 为 `None` 表示自机狙。用 `None` 而不是数据里的 `"player"` 字符串：
    字符串会让这个字段变成「数字或字符串」，类型说不清；而这里的语义本来就是
    「有没有固定基准角」。
    """

    bulletCount: int
    coneCount: int
    bullet: BulletSpec
    speed: float
    deltaAngleDeg: float
    intervalFrames: float
    baseAngleDeg: float | None = None
    angularSpeed: float = 0.0

    @property
    def volleyCount(self) -> int:
        """「锥数」就是打几波。加载器只用这个统一名字排时序，弹型函数不读它。"""
        return self.coneCount


@registerPattern("wide_cone", WideConeParams)
def wideCone(params: WideConeParams, context: FiringContext) -> None:
    baseAngleDeg = context.aimAngleDeg if params.baseAngleDeg is None else params.baseAngleDeg

    for offset in range(-params.bulletCount + 1, params.bulletCount, 2):
        context.field.spawn(
            params.bullet,
            context.origin,
            baseAngleDeg + offset * params.deltaAngleDeg * 0.5,
            params.speed,
        )
