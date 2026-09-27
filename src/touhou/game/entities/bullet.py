"""敌弹。

一颗子弹 = 一个圆 + 一个速度 + 一张贴图。本模块只管「一颗弹是什么」，
成批的生成、推进、回收与绘制在 game/bulletField.py。

子弹对象会被**复用**（对象池，见 docs/DESIGN.md「子弹与弹幕场」），所以全部状态都在
reset() 里设置，而且必须设满每一个字段——漏掉一个就是「新弹继承上一发的状态」，
这是池化最经典的 bug。__init__ 直接委托给 reset，两者因此不会漂移。

扩展一律走「加字段」，**不要写 Bullet 的子类**：子类会牵出每类一个池、
子类 __slots__ 纪律（漏写会把 __dict__ 静默加回来）、热循环里的 isinstance 判断；
而加字段只是「一个 slot + reset 一行 + update 一行」。
"""

# 统一开启延迟注解求值，理由见 vector2.py 的同类注释
from __future__ import annotations

from dataclasses import dataclass

import pygame

from touhou.core.collider import Collider
from touhou.core.spriteSheet import SpriteSheet
from touhou.core.vector2 import Vector2

# 每帧推进多少动画帧。必须小于 1.0——update() 每个 tick 只推进一帧，
# 速率 ≥ 1.0 时动画会被静默卡住，而动画计时器会无限增长。
ANIMATION_FRAMES_PER_TICK = 0.1


@dataclass(frozen=True, slots=True)
class BulletSpec:
    """一种子弹类型的静态属性。弹幕模板持有它，spawn 时传进来。

    radius 是显式给的，**不从贴图推导**：判定半径与贴图尺寸无关。关卡数据里
    同一张 ellipse_bullet_0.png（24×24）在不同弹幕下分别用 4 和 6，说明它是
    每套弹幕各自的参数，而不是贴图的固有属性。按贴图尺寸硬推会让判定圈大出
    好几倍——游戏照跑，只是变得不公平，属于调试期才发现的那类 bug。

    frozen 使其可哈希，于是关卡加载器能按贴图路径 memoize。这一点是必须的：
    SpriteSheet.getRotated 的缓存是**每张表**一份，若给每一组攻击各建一张表，
    docs/DESIGN.md 承诺的「360 × 帧数」内存上界就会被乘上攻击组数
    （level_1.json 里有 122 组攻击）。

    rotatesToVelocity 也要逐弹种给：圆球弹（bullet_0）旋转不改变外观，
    给它旋转只会白占 360 个缓存条目——实测 getRotated(0, 0) 与 getFrame(0)
    并不是同一个对象，0° 旋转也会另存一份。

    `damage` **只有自机子弹用得到**（敌人血量 1/10/25/40 正是按伤害 1 调的）。
    敌弹也带着这个字段，但没有任何代码读它——敌弹命中自机是「碰到即死」，
    不分伤害。留着它是为了**不必为自机子弹另造一套实体**，见 docs/DESIGN.md
    「自机」一节里关于复用的取舍。
    """

    spriteSheet: SpriteSheet
    radius: float
    rotatesToVelocity: bool = True
    damage: int = 1


class Bullet(Collider):
    """一颗敌弹。

    继承 Collider 而不是组合：子弹**是**一个圆，这样 checkCollision 与
    position.y（将来按 y 粗筛要用）都是自然写法。实测子类加了 __slots__ 之后
    实例仍然没有 __dict__，池化想要的效果不会丢。
    """

    # 按字母序排：ruff 的 RUF023 要求如此，Collider 与 Vector2 也是这个风格
    __slots__ = (
        "ageFrames",
        "angleDeg",
        "animationFrame",
        "animationTimer",
        "damage",
        "rotatesToVelocity",
        "spriteSheet",
        "velocity",
    )

    velocity: Vector2
    angleDeg: float
    spriteSheet: SpriteSheet
    rotatesToVelocity: bool
    damage: int
    animationFrame: int
    animationTimer: float
    ageFrames: int

    def __init__(self, spec: BulletSpec, position: Vector2, angleDeg: float, speed: float) -> None:
        super().__init__(spec.radius, Vector2(0.0, 0.0))
        self.reset(spec, position, angleDeg, speed)

    def reset(self, spec: BulletSpec, position: Vector2, angleDeg: float, speed: float) -> None:
        """把一颗弹恢复成「刚生成」的状态。池复用的入口。

        只拷 position 的分量，不存调用方传进来的那个 Vector2 对象：弹幕模板
        必然会写 spawn(spec, enemy.position, ...)，直接存引用的话敌人一移动，
        所有引用它的子弹会一起跳（实测三颗弹的 x 从 100 全变成 140）。spawn
        不是每帧热路径，这一次分配可以忽略。

        speed 的单位是像素/帧（见 docs/DESIGN.md「数值常量与单位」）。关卡数据
        里写的是像素/秒，换算由关卡加载器负责，不要在这里补。
        """
        self.position = Vector2(position.x, position.y)
        self.radius = spec.radius
        self.velocity = Vector2.fromDeg(angleDeg, speed)
        self.angleDeg = angleDeg
        self.spriteSheet = spec.spriteSheet
        self.rotatesToVelocity = spec.rotatesToVelocity
        self.damage = spec.damage
        self.animationFrame = 0
        self.animationTimer = 0.0
        self.ageFrames = 0

    def update(self) -> None:
        """推进一帧。

        这里是位置**唯一**被推进的地方——加加速度、角速度、追踪时只改这里，
        别处的代码都不需要知道子弹有运动学。
        """
        self.position = self.position + self.velocity
        self.ageFrames += 1

        self.animationTimer += ANIMATION_FRAMES_PER_TICK
        if self.animationTimer >= 1.0:
            self.animationTimer -= 1.0
            # 取模回绕不能省：getFrame / getRotated 抛的是裸 IndexError，
            # 而且抛在离真正的错误很远的地方（testSpriteSheet 里有一条测试
            # 就是为这个存在的）。
            self.animationFrame = (self.animationFrame + 1) % self.spriteSheet.frameCount

    def currentFrame(self) -> pygame.Surface:
        """当前该绘制的画面。

        angleDeg 是**存下来的**，不是每帧从 velocity 反推的。实测
        Vector2.fromDeg(θ, 0) 对 θ = 0/45/90 都给出 (0.0, -0.0)，反推角度
        全是 0.0——也就是说反推会把这三个方向**全塌成正上**，停下再转向的
        弹型会因此画错方向。
        """
        if self.rotatesToVelocity:
            return self.spriteSheet.getRotated(self.animationFrame, self.angleDeg)
        return self.spriteSheet.getFrame(self.animationFrame)

    def __repr__(self) -> str:
        # 不覆盖的话会继承 Collider.__repr__，打印活跃列表时看不出这是子弹
        return f"Bullet(position={self.position}, angleDeg={self.angleDeg:g})"
