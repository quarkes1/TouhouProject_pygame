"""敌机。

沿轨迹飞行、贴图动画、血量与死亡，外加**按自己的时刻表开火**。
弹幕本身长什么样由 `game/patterns/` 决定，本类只负责「什么时候打」与「在哪打」。

轨迹是均匀三次 B 样条（core/spline.py），控制点、贴图与时刻表都由
game/levelData.py 从关卡数据备好。本类不知道单位换算、坐标原点这些事。

## 两个半径

敌机身上有**两个**判定半径，用途不同，别混：

| 字段 | 来源 | 给谁用 | 大小 |
|------|------|--------|------|
| `radius` | 关卡数据的 `hitboxRadius` | 自机子弹**打中**它 | 比贴图还大（妖精半宽 12，数据给 15） |
| `bodyRadius` | 贴图内切圆 × 系数 | 自机**撞上**它 | 比贴图略小 |

方向是相反的，而且是有意的：**被弹判定要「打得到」，撞机判定要「没真碰到就不算死」**。
把两个合成一个，必然有一边是错的。

单位值得单独说一句：`durationFrames` 是**走完整条轨迹要多少帧**，
所以每帧的轨迹参数增量是 `(len(path) - 1) / durationFrames`——一帧一帧地走，
走完正好是 `len(path) - 1` 个控制点区间。旧格式用的是「每秒走几个区间」的
`speed`，两者是倒数关系（迁移工具负责换算，见 docs/DESIGN.md「关卡数据格式」）。
"""

# 为注解开启延迟求值，理由见 vector2.py 的同类注释
from __future__ import annotations

import pygame

from touhou import constants
from touhou.core.collider import Collider, circlesOverlap
from touhou.core.spline import samplePath
from touhou.core.spriteSheet import SpriteSheet
from touhou.core.vector2 import Vector2
from touhou.game.levelData import EnemyAttack, EnemySpawn

# 每帧推进多少动画帧。与自机用同一个速率；速率取值需要实测调整。
ANIMATION_FRAMES_PER_TICK = 0.1


class Enemy(Collider):
    """一架敌机。

    继承 Collider 的道理与 Bullet 相同：敌机**是**一个判定圆。
    半径来自关卡数据而不是从贴图推导——数据的判定半径**很宽松**
    （妖精贴图半宽只有 12px，数据给的半径是 15px，比贴图还大），
    这与子弹判定半径远小于贴图正好相反，是有意的，不要「顺手修正」。
    """

    __slots__ = (
        "ageFrames",
        "animationFrame",
        "animationTimer",
        "attacks",
        "bodyRadius",
        "clearOnDeath",
        "hp",
        "nextAttack",
        "path",
        "spriteSheet",
        "u",
        "uPerFrame",
    )

    ageFrames: int
    animationFrame: int
    animationTimer: float
    attacks: tuple[EnemyAttack, ...]
    bodyRadius: float
    clearOnDeath: bool
    hp: int
    nextAttack: int
    path: tuple[Vector2, ...]
    spriteSheet: SpriteSheet
    u: float
    uPerFrame: float

    def __init__(self, spawn: EnemySpawn) -> None:
        super().__init__(spawn.enemyType.radius, Vector2(0.0, 0.0))
        self.reset(spawn)

    def reset(self, spawn: EnemySpawn) -> None:
        """把一架敌机恢复成「刚出生」的状态。

        与 Bullet 一样，__init__ 委托给 reset 以免两者漂移，reset 必须设满
        每一个字段。（敌机目前不复用对象，但接口先立住，免得将来引入池时
        要改动所有调用方。）

        `path` 与 `attacks` 直接引用 spawn 里的元组、不复制：关卡里 114 个敌人
        只有 20 条不同轨迹，复制一遍会让共享失效。两者都是不可变的，共享是安全的。
        """
        self.u = 0.0
        self.path = spawn.path
        self.uPerFrame = (len(spawn.path) - 1) / spawn.durationFrames
        self.hp = spawn.hp
        self.clearOnDeath = spawn.clearOnDeath
        self.attacks = spawn.attacks
        self.nextAttack = 0
        self.spriteSheet = spawn.enemyType.spriteSheet
        self.radius = spawn.enemyType.radius
        # 撞机判定半径：由**贴图**推出来的内切圆，再乘一个略小于 1 的系数。
        # 与上面那个（来自关卡数据、给自机子弹打的）是两回事：那一份比贴图还大
        # ——妖精贴图半宽 12，数据给的是 15——用它做撞机判定的话，玩家会在
        # 离敌机还有好几像素时就被撞死，看起来像是判定出错了。
        #
        # 两个判定服务的目标本来就不同：**被弹判定要「打得到」，撞机判定要
        # 「没真碰到就不算死」**。
        self.bodyRadius = (
            min(self.spriteSheet.frameWidth, self.spriteSheet.frameHeight)
            / 2
            * constants.ENEMY_BODY_RADIUS_FACTOR
        )
        self.position = samplePath(spawn.path, 0.0)
        self.animationFrame = 0
        self.animationTimer = 0.0
        self.ageFrames = 0

    def update(self) -> None:
        """推进一个固定逻辑步。

        与全项目一致，一步就是 1/60 秒，不接收时间增量——固定步长是弹幕游戏的
        正确性前提，见 docs/DESIGN.md「主循环」。
        """
        self.u += self.uPerFrame
        self.position = samplePath(self.path, self.u)
        self.ageFrames += 1
        self.advanceAnimation()

    def advanceAnimation(self) -> None:
        """把贴图动画往前推一点。

        单独成方法是为了让 `Boss` 复用：它覆盖了 `update`（改走脚本），
        而贴图动画与轨迹无关，不该跟着复制一遍。
        """
        self.animationTimer += ANIMATION_FRAMES_PER_TICK
        if self.animationTimer >= 1.0:
            self.animationTimer -= 1.0
            # 取模回绕不能省：getFrame 抛的是裸 IndexError，离真正的错误很远
            self.animationFrame = (self.animationFrame + 1) % self.spriteSheet.frameCount

    def dueAttacks(self) -> tuple[EnemyAttack, ...]:
        """取出本帧该打的齐射，并把游标推过去。

        攻击的时刻是**相对出生**的帧数，而 `ageFrames` 正是出生以来的 update()
        次数，两者直接比较即可——所以第一波在 `startFrame` 帧时打响，
        旧格式里那对应「敌机刚好走到第一个控制点」。

        一次性返回多波而不是一波：波间隔可能小于一帧的整数倍，逐帧判断才对得上
        时刻表。
        """
        due: list[EnemyAttack] = []
        while (
            self.nextAttack < len(self.attacks)
            and self.attacks[self.nextAttack].frame <= self.ageFrames
        ):
            due.append(self.attacks[self.nextAttack])
            self.nextAttack += 1
        return tuple(due)

    def touches(self, other: Collider) -> bool:
        """机体接触判定：自机贴到敌机身上了吗。

        **用 `bodyRadius` 而不是 `radius`**：后者是「被自机子弹打中」的判定，
        比贴图还大（那一份要保证打得到），拿它判撞机等于判定圈比眼睛看到的还大。
        理由与两个半径的来历见 `reset`。
        """
        return circlesOverlap(self.position, self.bodyRadius, other.position, other.radius)

    def damage(self, amount: int) -> None:
        self.hp -= amount

    def isDead(self) -> bool:
        """被打死了。将来的道具掉落挂在这里——飞走的敌人不该掉东西。"""
        return self.hp <= 0

    def hasLeft(self) -> bool:
        """已经走完轨迹飞出场了。"""
        return self.u > len(self.path) - 1

    def isFinished(self) -> bool:
        """该从场上移除了。容器用这个判断，而不是 isDead——两者语义不同。"""
        return self.isDead() or self.hasLeft()

    def currentFrame(self) -> pygame.Surface:
        """当前该绘制的画面。

        敌机贴图不跟着运动方向旋转（与子弹不同）：妖精立绘和弹刺球都是
        自带朝向的循环动画，转了反而不对。
        """
        return self.spriteSheet.getFrame(self.animationFrame)

    def __repr__(self) -> str:
        return f"Enemy(position={self.position}, u={self.u:g}, hp={self.hp})"
