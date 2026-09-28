"""敌机容器：出生时刻表、开火调度、回收与绘制。

与 `BulletField` 对称：两者都是「一堆同类实体的容器 + 每帧推进 + 画出来」。
区别在于敌机还多一件事——**按自己的时刻表开火**，而开火需要子弹场与自机位置，
所以 `update()` 要收下这两样。

弹幕长什么样不在这里，而在 `game/patterns/`；本模块只负责「什么时候、从哪、朝哪打」。
"""

# 为注解开启延迟求值，理由见 vector2.py 的同类注释
from __future__ import annotations

import random

import pygame

from touhou.core.collider import Collider
from touhou.core.vector2 import Vector2
from touhou.game.bulletField import BulletField
from touhou.game.entities.boss import Boss
from touhou.game.entities.enemy import Enemy
from touhou.game.levelData import BossSpawn, EnemySpawn
from touhou.game.patterns import PATTERN_REGISTRY, FiringContext


class EnemyField:
    def __init__(
        self,
        spawns: tuple[EnemySpawn, ...],
        rng: random.Random,
        bossSpawns: tuple[BossSpawn, ...] = (),
    ) -> None:
        self.spawns = spawns
        self.bossSpawns = bossSpawns
        # 随机数是**注入**的：随机弹型（long_random、随机中心）必须可复现，
        # 否则同一份输入产生不出同一个结果（docs/DESIGN.md「主循环」）。
        self.rng = rng
        self.active: list[Enemy] = []
        self.spawnCursor = 0
        self.bossCursor = 0
        # 场上的 BOSS（它同时也在 active 里）。UI 要它来画血条，而「哪个是 BOSS」
        # 不该让 UI 去 active 里 isinstance 一遍。
        self.boss: Boss | None = None
        # 用逻辑帧数计时、不用真实经过时间：固定步长下同一份输入必须给出同一场战斗。
        self.elapsedFrames = 0

    def __len__(self) -> int:
        return len(self.active)

    def scheduleComplete(self) -> bool:
        """所有出生计划耗尽且场上已无敌人。"""
        return (
            self.spawnCursor >= len(self.spawns)
            and self.bossCursor >= len(self.bossSpawns)
            and not self.active
            and self.boss is None
        )

    def update(self, bulletField: BulletField, playerPosition: Vector2) -> None:
        """推进一帧：推进场上的敌人、打出到点的齐射、回收离场的、再放出新到点的。

        **出生放在推进之后**，这样刚出场的敌机本帧不推进、`ageFrames` 是 0：
        它的第一帧就画在 `startPosition` 上，而「出生后第 N 帧开火」也严格落在
        `出生帧 + N` 上。放在之前的话每架敌机都会凭空老一帧，
        攻击时刻会整体提前一帧——不会崩，只是所有弹幕都早了 1/60 秒。
        BOSS 同理：它出生那帧不推进脚本，脚本的第一步（设血量、登记开火计划）
        落在下一帧。
        """
        self.elapsedFrames += 1

        for enemy in self.active:
            enemy.update()
            self.fire(enemy, bulletField, playerPosition)
        self.removeFinished()

        self.spawnDue(bulletField, playerPosition)

    def spawnDue(self, bulletField: BulletField, playerPosition: Vector2) -> None:
        """把到点的出生点放出来：先敌机，后 BOSS。

        两者都是「到点才出现」，所以共用 `elapsedFrames` 这个时钟。分开写是因为
        BOSS 还要在 `self.boss` 上记一笔，而那份记录是给 UI 用的。
        """
        spawns = self.spawns
        while (
            self.spawnCursor < len(spawns) and spawns[self.spawnCursor].frame <= self.elapsedFrames
        ):
            enemy = Enemy(spawns[self.spawnCursor])
            self.active.append(enemy)
            self.spawnCursor += 1
            # 也查一次：帧数为 0 的攻击应当在这一帧就打响（关卡数据里没有这么早的，
            # 但规则要自洽，否则「第 N 帧」在 N=0 处成了特例）。
            self.fire(enemy, bulletField, playerPosition)

        bosses = self.bossSpawns
        while (
            self.bossCursor < len(bosses) and bosses[self.bossCursor].atFrame <= self.elapsedFrames
        ):
            boss = Boss(bosses[self.bossCursor])
            self.active.append(boss)
            self.boss = boss
            self.bossCursor += 1
            self.fire(boss, bulletField, playerPosition)

    def fire(self, enemy: Enemy, bulletField: BulletField, playerPosition: Vector2) -> None:
        """把一架敌机本帧该打的齐射全部打出去。

        自机狙的角度在这里算**一次**，同一帧的多波共用。自机与敌机恰好重合时
        差向量是零向量，`angleDeg()` 按约定返回 180°（朝正下）而不是 NaN——
        所以这里不需要额外的守卫，但要知道那种情形下打的是固定方向。
        """
        due = enemy.dueAttacks()
        if not due:
            return

        aimAngleDeg = (playerPosition - enemy.position).angleDeg()
        for attack in due:
            PATTERN_REGISTRY[attack.pattern](
                attack.params,
                FiringContext(
                    field=bulletField,
                    origin=enemy.position,
                    aimAngleDeg=aimAngleDeg,
                    rng=self.rng,
                    volleyIndex=attack.volleyIndex,
                ),
            )

    def touches(self, collider: Collider) -> bool:
        """有没有敌机的**机体**碰到给定圆。与 `BulletField.hits` 对称。

        这里不排序也不分桶：这是每帧一次的自机判定，不是每颗子弹都要做一遍的
        事——敌机也就几十架，逐架比较完全够。真正需要粗筛的是自机子弹那条线
        （每帧几百发），见 game/collision.py。
        """
        return any(enemy.touches(collider) for enemy in self.active)

    def removeFinished(self) -> list[Enemy]:
        """把该移除的敌机摘掉，并**返回它们**。

        返回而不是丢弃，是因为「一架敌机退场」这件事有两个观测者，而且看法不同：
        容器只关心它别占着列表；`game/collision.py` 要的是「**被打死的**清不清弹」
        （`clearOnDeath`）。两者的判据不同——`isFinished()` 也包含「飞出场了」，
        而飞走的敌人不该清弹。所以移除只做一次，判据留给调用方各自表达。

        将来的道具掉落也挂在这个返回值上（`Enemy.isDead` 的注释已经写了
        「飞走的敌人不该掉东西」，那是同一条区分）。
        """
        finished = [enemy for enemy in self.active if enemy.isFinished()]
        self.active = [enemy for enemy in self.active if not enemy.isFinished()]
        if self.boss is not None and self.boss.isFinished():
            # BOSS 同时躺在 active 与 self.boss 里，摘的时候两处都要清。
            # 只清 active 的话 UI 会一直画着一条没有 BOSS 的血条。
            self.boss = None
        return finished

    def draw(self, canvas: pygame.Surface) -> None:
        """绘制全部敌机，以中心点对齐。

        不能写 position - halfSize：精灵的尺寸与判定半径是两回事，而
        `get_rect(center=...)` 对任何尺寸都准。理由同 BulletField.draw。
        """
        for enemy in self.active:
            frame = enemy.currentFrame()
            canvas.blit(frame, frame.get_rect(center=enemy.position.toTuple()))
