"""环形弹幕。

一发打出一个**完整的圆环**：`bulletCount` 发均匀分布，相邻两发相隔
`360 / bulletCount` 度。连续几发之间，每一环整体比上一环多转 `deltaAngleDeg`，
于是逐环累积成螺旋——参考项目的原式是第 n 环的每发角度取
`(360 × k / 每环弹数 + n × 每环旋转角) % 360`。

「第几环」由调用方经 `FiringContext.volleyIndex` 告知：时序归调度方管，
本模块只管打**一环**。

**角度符号**：`deltaAngleDeg` 的正负决定螺旋往哪边绕。参考项目的角度是
「顺时针为正」的反面（见 docs/DESIGN.md 移植警告一），所以从它的数据迁移过来的
有符号角度**已经取过负**了，本模块直接用——别在这里再翻一次。
"""

# 为注解开启延迟求值，理由见 vector2.py 的同类注释
from __future__ import annotations

from dataclasses import dataclass

from touhou import constants
from touhou.game.entities.bullet import BulletSpec
from touhou.game.patterns.registry import FiringContext, randomCentreOrigin, registerPattern


@dataclass(frozen=True, slots=True)
class WideRingParams:
    """`wide_ring` 的参数。字段名与关卡数据里的名字一一对应。

    `randomCenter` 打开时，每一环的**圆心**绕敌人随机偏移（见
    `registry.randomCentreOrigin`），而不是固定打在敌人身上。
    """

    bulletCount: int
    ringCount: int
    bullet: BulletSpec
    speed: float
    deltaAngleDeg: float
    intervalFrames: float
    randomCenter: bool = False
    angularSpeed: float = 0.0

    @property
    def volleyCount(self) -> int:
        """「环数」就是打几波。加载器只用这个统一名字排时序，弹型函数不读它。"""
        return self.ringCount


@registerPattern("wide_ring", WideRingParams)
def wideRing(params: WideRingParams, context: FiringContext) -> None:
    origin = (
        randomCentreOrigin(context, constants.BULLET_RANDOM_CENTER_OFFSET)
        if params.randomCenter
        else context.origin
    )
    ringRotationDeg = context.volleyIndex * params.deltaAngleDeg

    for index in range(params.bulletCount):
        angleDeg = (360.0 * index / params.bulletCount + ringRotationDeg) % 360.0
        context.field.spawn(params.bullet, origin, angleDeg, params.speed)
