"""弹幕场：所有在飞子弹的容器，兼对象池。

子弹出屏后不销毁，而是回到 free 列表等待复用，于是稳态下不再有新分配
（见 docs/DESIGN.md「子弹与弹幕场」）。

对象池**不单独成类**，因为「一颗弹什么时候被回收」完全由场决定，
池的唯一调用方就是场。把 active 与 free 两个列表放在同一个类里，
「一颗弹恰好在两者之一」这条不变量才只在一个地方可检查——而下面 releaseAt
里那三行的顺序正是这条不变量唯一会被写错的地方。
"""

# 统一开启延迟注解求值，理由见 vector2.py 的同类注释
from __future__ import annotations

import pygame

from touhou import constants
from touhou.core.collider import Collider
from touhou.core.vector2 import Vector2
from touhou.game.entities.bullet import Bullet, BulletSpec


def playfieldBounds() -> pygame.Rect:
    """回收判定用的矩形：游戏区外扩 BULLET_CULL_MARGIN。

    余量的唯一职责是**贴图占位**——子弹不能在自己还有像素落在游戏区内时被删掉。
    它不负责、也做不到「容忍从场外飞进来的子弹」，那件事由 isCulled 的速度方向
    判定承担。取值依据见 constants.py 里 BULLET_CULL_MARGIN 的注释。
    """
    return pygame.Rect(
        constants.PLAYFIELD_X,
        constants.PLAYFIELD_Y,
        constants.PLAYFIELD_WIDTH,
        constants.PLAYFIELD_HEIGHT,
    ).inflate(2 * constants.BULLET_CULL_MARGIN, 2 * constants.BULLET_CULL_MARGIN)


def isCulled(position: Vector2, velocity: Vector2, bounds: pygame.Rect) -> bool:
    """该不该回收：已经出场**并且**还在朝场外飞。

    不能只按「出矩形就回收」判。关卡里的敌人会在游戏区外开火：把
    level_1.json 的坐标换算到本项目的游戏区之后（换算见 game/levelData.py），
    控制点最远探到游戏区外 105px，而 **114 个敌人里有 105 个**至少有一个控制点
    落在「游戏区外扩 32px」的回收矩形之外。它们的子弹诞生在回收矩形之外，
    却朝场内飞——只按矩形判，这些子弹会在生成那一帧就被杀掉。

    而要塞下这些子弹，余量得开到 105px，那会让回收矩形面积变成游戏区的
    **2.3 倍**：子弹要飞出 105px 才回收，池占用与模拟量白涨一倍多。
    方向判定在边界上即回收、且永不误杀入场弹，代价同样是四次比较。

    `<=` / `>=`：场外静止的弹回不来了，该回收；场内静止的弹保留，
    「停下再转向」是合法弹型。

    写成模块级纯函数而不是 Bullet 的方法：子弹不该知道游戏区在哪，
    而且这样它能脱离 SpriteSheet 单独测试——同 player.py 里的 clampToPlayfield。
    """
    # 四条边各自判断：出界**且**还在朝外飞才算。`<=` / `>=` 让场外的静止弹
    # 被回收（回不来了），场内静止的弹保留（停下再转向是合法弹型）。
    return (
        (position.x < bounds.left and velocity.x <= 0)
        or (position.x > bounds.right and velocity.x >= 0)
        or (position.y < bounds.top and velocity.y <= 0)
        or (position.y > bounds.bottom and velocity.y >= 0)
    )


class BulletField:
    def __init__(self, bounds: pygame.Rect | None = None) -> None:
        # bounds 可注入，测试不必去凑游戏区的真实坐标
        self.bounds = playfieldBounds() if bounds is None else bounds
        self.active: list[Bullet] = []
        self.free: list[Bullet] = []

    def __len__(self) -> int:
        return len(self.active)

    def spawn(self, spec: BulletSpec, position: Vector2, angleDeg: float, speed: float) -> Bullet:
        """放出一颗子弹，复用池里的死弹；池空才新建。"""
        if self.free:
            bullet = self.free.pop()
            bullet.reset(spec, position, angleDeg, speed)
        else:
            bullet = Bullet(spec, position, angleDeg, speed)
        self.active.append(bullet)
        return bullet

    def update(self) -> None:
        """推进全部子弹，回收出场的。

        倒序遍历 + 交换删除，避免每帧拷一份列表。倒序保证每颗弹**恰好**推进一次：
        被换到位置 i 的那颗来自末尾，而末尾在倒序中已经处理过，且降序区间
        不会回头再访问 i。

        循环在入口就定住了 len()，所以本帧**期间**新 spawn 的弹不会被推进或回收。
        也就是说生成应当发生在 update() 之前——弹幕模板层就是这么调的。
        将来若真出现「子弹生子弹」的分裂弹型，由模板层走待处理队列，
        而不是让 spawn 在 update 中途生效。
        """
        for i in range(len(self.active) - 1, -1, -1):
            bullet = self.active[i]
            bullet.update()
            if isCulled(bullet.position, bullet.velocity, self.bounds):
                self.releaseAt(i)

    def releaseAt(self, index: int) -> None:
        """把 active[index] 交回池里。

        这三行的顺序是承重的。写成 `self.free.append(self.active.pop())` 是**错的**：
        pop() 取的是末尾元素，而此时末尾正是刚刚被复制进 index 的**幸存者**，
        不是死者——于是幸存者同时躺在 active 和 free 里（下一轮 spawn 会把它
        再发一次，同一颗弹被推进、绘制、碰撞两遍），而真正的死者泄漏。
        在「末尾那颗死」的场景下这个错误写法恰好是对的，所以只有
        「中间那颗死」的测试能抓到它。

        先赋值再 pop 也是必须的：反过来会在末位场景索引越界。
        """
        dead = self.active[index]
        self.active[index] = self.active[-1]
        self.active.pop()
        self.free.append(dead)

    def clear(self) -> None:
        """清空全场（炸弹、死亡、符卡切换都要用）。

        level_1.json 里有 4 个敌人带 clear_on_death，所以这不是预留接口。
        走与回收相同的 releaseAt，保证「怎么算释放」只有一处实现。
        """
        while self.active:
            self.releaseAt(len(self.active) - 1)

    def hits(self, collider: Collider) -> bool:
        """有没有子弹碰到给定圆。相切不算碰撞，沿用 Collider 的约定。"""
        for bullet in self.active:
            if bullet.checkCollision(collider):
                return True
        return False

    def draw(self, canvas: pygame.Surface) -> None:
        """绘制全部子弹，以中心点对齐。

        不能写 position - halfSize：旋转之后外接矩形会变大（实测 16×16 转到
        45° 变成 22×22），那样算会偏出 3px 以上。用 surface 自己的 rect 做
        center 对齐，任何角度都准。非直角角度有 pygame 整数取整带来的 ≤1px
        偏移——每颗弹角度固定，所以不会抖动，也不必修。
        """
        for bullet in self.active:
            frame = bullet.currentFrame()
            canvas.blit(frame, frame.get_rect(center=bullet.position.toTuple()))
