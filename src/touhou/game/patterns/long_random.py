"""随机角度的连发弹幕。

一发的每颗子弹各取一个 0~360° 的随机方向，所以形状不规整——它的作用不是
「一个好看的图形」，而是让一整个扇区同时变危险，逼玩家挪位置。

它是本项目里唯一真正依赖随机数的弹型，因此也是「随机数必须注入」这条决定的
第一个受益者：测试用固定种子就能断言**逐发精确**的角度，而全局 `random` 做不到
（docs/DESIGN.md「主循环」说明了确定性为什么是硬要求）。

随机角度取 `uniform(0, 360)`（连续）而不是参考项目的 `randint(0, 360)`（整数）：
连续值让相邻子弹不会出现肉眼可见的角度格点，而整数化对玩法没有任何好处。
"""

# 为注解开启延迟求值，理由见 vector2.py 的同类注释
from __future__ import annotations

from dataclasses import dataclass

from touhou import constants
from touhou.game.entities.bullet import BulletSpec
from touhou.game.patterns.registry import FiringContext, randomCentreOrigin, registerPattern


@dataclass(frozen=True, slots=True)
class LongRandomParams:
    """`long_random` 的参数。字段名与关卡数据里的名字一一对应。"""

    bulletCount: int
    burstCount: int
    bullet: BulletSpec
    speed: float
    intervalFrames: float
    randomCenter: bool = False
    angularSpeed: float = 0.0

    @property
    def volleyCount(self) -> int:
        """「波数」就是打几波。加载器只用这个统一名字排时序，弹型函数不读它。"""
        return self.burstCount


@registerPattern("long_random", LongRandomParams)
def longRandom(params: LongRandomParams, context: FiringContext) -> None:
    origin = (
        randomCentreOrigin(context, constants.BULLET_RANDOM_CENTER_OFFSET)
        if params.randomCenter
        else context.origin
    )

    for _ in range(params.bulletCount):
        angleDeg = context.rng.uniform(0.0, 360.0)
        context.field.spawn(params.bullet, origin, angleDeg, params.speed)
