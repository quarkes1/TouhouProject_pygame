"""自机子弹 vs 敌机的碰撞。

规格 §5.5 把碰撞分两档：**自机判定点 vs 敌弹全量比较**（弹药基数不大，实测够用），
**自机子弹 vs 敌机按 y 坐标分桶粗筛**。这个模块是第二档——自机判定点那一档直接
用 `BulletField.hits(player)`，不必新写。

**分桶省的是什么**：敌机通常只有几架，所以收益不在敌机那一侧，而在子弹这一侧。
自机子弹每帧几百发，逐发扫一遍全部敌机是 O(弹 × 敌)；按 y 排好序之后，
每发只需要比较 y 邻近的那几架。写成朴素的全量比较结果完全一样，
只是每帧多做几百次无用的距离比较——所以它是个**纯性能措施**，
测试要证明它与朴素写法逐一等价。
"""

# 为注解开启延迟求值，理由见 vector2.py 的同类注释
from __future__ import annotations

from bisect import bisect_left

from touhou import constants
from touhou.game.bulletField import BulletField
from touhou.game.enemyField import EnemyField
from touhou.game.entities.bullet import Bullet
from touhou.game.entities.enemy import Enemy


def resolvePlayerShots(
    shots: BulletField, enemies: EnemyField, enemyBullets: BulletField
) -> list[Enemy]:
    """把自机子弹与敌机的碰撞结算掉：扣血、子弹消失、敌机死亡则移除。

    **子弹不穿透**：打中一发就消失。规格没规定，这里定——穿透会让一条弹道
    在敌机排队飞来时打出成倍的伤害，而伤害值是按单发调的。

    返回**本帧退场的敌机**（打死的与飞走的），供调用方接掉落之类。
    """
    # 按 y 排序一次，供所有子弹共用。敌机很少，这一次排序的成本可以忽略。
    ordered = sorted(enemies.active, key=lambda enemy: enemy.position.y)
    orderedYs = [enemy.position.y for enemy in ordered]
    maxEnemyRadius = max((enemy.radius for enemy in ordered), default=0.0)

    # 倒序遍历 + swap-remove：`releaseAt` 会把末尾那颗换到当前下标，
    # 而末尾在倒序里已经处理过，所以每颗子弹恰好处理一次。
    for index in range(len(shots.active) - 1, -1, -1):
        shot = shots.active[index]
        hit = hitEnemy(shot, ordered, orderedYs, maxEnemyRadius)
        if hit is not None:
            hit.damage(shot.damage)
            shots.releaseAt(index)

    return removeAndHandleDeaths(enemies, enemyBullets)


def removeAndHandleDeaths(enemies: EnemyField, enemyBullets: BulletField) -> list[Enemy]:
    """摘掉退场的敌机，并处理「被打死时清弹」。

    **凡是有东西能让敌机掉血的地方，都要走这里**——否则 `clearOnDeath` 只在
    自机子弹打死的那些敌人身上生效，死亡冲击波打死的就不生效，同一个字段
    两套行为。

    清弹的判据是「**被打死**」而不是「退场」：`isFinished()` 两者都包含，
    而清弹是死亡的补偿，飞出场外的敌人没有理由替玩家解围。
    """
    finished = enemies.removeFinished()
    for enemy in finished:
        if enemy.isDead() and enemy.clearOnDeath:
            enemyBullets.clear()
    return finished


def damageAllEnemies(enemies: EnemyField, enemyBullets: BulletField, amount: int) -> list[Enemy]:
    """全场敌机一起掉血。自机死亡的冲击波走这条。"""
    for enemy in enemies.active:
        enemy.damage(amount)
    return removeAndHandleDeaths(enemies, enemyBullets)


def playerDeathShockwave(enemies: EnemyField, enemyBullets: BulletField) -> list[Enemy]:
    """自机死亡的冲击波：清空全场敌弹 + 全屏敌机掉一点血。

    两件事与死亡特效**同帧**发生、缺一不可——它们是同一个事件（「自机炸了」）
    的三个表现，只是分在三个模块里：特效是给人看的，消弹是给玩家的补偿，
    掉血是给敌人的账。调用点见 `Player.die`。

    伤害值见 `constants.PLAYER_DEATH_DAMAGE`：关卡里 114 架敌机有 98 架正好是
    1 血，所以它**刚好秒杀小怪**，对 10/25/40 血的精英只是掉一层皮。

    「全屏」取的是 `active` 里的全部敌机，不是「画面上看得见的那些」：敌机几乎
    总是飞在游戏区内，而冲击波的环本身会被游戏区裁剪矩形切掉，两者对得上。
    """
    enemyBullets.clear()
    return damageAllEnemies(enemies, enemyBullets, constants.PLAYER_DEATH_DAMAGE)


def playerBombShockwave(enemies: EnemyField, enemyBullets: BulletField) -> list[Enemy]:
    """放雷的冲击波：清空全场敌弹 + 全屏敌机掉一大截血。

    与 `playerDeathShockwave` **形状完全一样、只有伤害值不同**，但仍写成两条
    函数而不是带参数的注入口：调用点不同（一个在 `Player.die`、一个在
    `Player.useBomb`），而两处的伤害是两个独立的手感旋钮——死亡冲击波只能
    打掉一层皮，雷要能清场，把它们合成一个带参数的函数只会让下一个人以为
    这两个数该一起调。

    伤害值见 `constants.PLAYER_BOMB_DAMAGE`（38）：1/10/25 血的敌人当场蒸发，
    40 血的顶级精英剩 2 血。与死亡冲击波一样，「全屏」取的是 `active` 里的
    全部敌机，包括画面上看不见的那些。
    """
    enemyBullets.clear()
    return damageAllEnemies(enemies, enemyBullets, constants.PLAYER_BOMB_DAMAGE)


def hitEnemy(
    shot: Bullet, ordered: list[Enemy], orderedYs: list[float], maxEnemyRadius: float
) -> Enemy | None:
    """这颗子弹碰到了哪架敌机。没碰到返回 `None`。

    只在 y 邻近的敌机里找：`|dy|` 超过「子弹半径 + 最大敌机半径」的敌机不可能相交
    （圆相交的必要条件是两圆心距小于半径和，而圆心距 ≥ |dy|）。

    **前置条件**：`ordered` 按 `position.y` 升序，且 `orderedYs` 是它的 y 序列
    （提前算好是为了能二分）。三者由 `resolvePlayerShots` 每帧算一次、所有子弹共用
    ——所以它是个模块内函数，不是给调用方随手用的接口；参数拆开传只是为了让
    分桶本身能被单独测（比较次数要能数出来）。
    """
    window = shot.radius + maxEnemyRadius
    start = bisect_left(orderedYs, shot.position.y - window)
    for enemy in ordered[start:]:
        if enemy.position.y > shot.position.y + window:
            break
        if shot.checkCollision(enemy):
            return enemy
    return None
