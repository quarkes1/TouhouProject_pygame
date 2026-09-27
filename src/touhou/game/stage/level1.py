"""第一关（`assets/levels/level_1.json`）的 BOSS 脚本。

中 BOSS **小恶魔**：一管血、无符卡，进场之后左右横移换弹幕。
规格 §6.7 对中 BOSS 的定义就是「道中出现的简化版，通常无符卡，血条短」，
所以这里没有符卡宣言、没有分段血条——那些是关底 BOSS 的东西。

写法先读一遍 `game/entities/boss.py` 的模块文档：**移动走 yield（前台，每帧一步），
开火走计划（后台，由 `Boss.update` 每帧推一拍）**。这条分工是「边挪边打」能成立的
原因；`yield from boss.fires(...)` 那种写法会把控制权永远交出去，BOSS 就动不了了。
"""

from collections.abc import Iterator

from touhou.core.vector2 import Vector2
from touhou.game.entities.boss import Boss

# 本段血量。**起点值，需要实测调整。**
#
# 自机满中约 30 伤害/秒（火力 2.40 → 3 条弹道、6 帧一组），实战因走位与躲弹打折到
# 15~21，所以 420 血约 20~28 秒——中 BOSS 该有的长度（原作里是「一段检查点」的量级）。
# 血量是这个 BOSS **唯一的节奏旋钮**：雷没有伤害，死亡冲击波每死一次也才掉 1 血，
# 所以玩家的输出只有自机子弹一条来源。
MIDBOSS_HP = 420

# 站位。坐标写死在脚本里而不是进关卡数据：规格的目录树里 BOSS 行为本来就是 Python
# 文件，等第二个 BOSS 要复用同一套走位时再抽出来。
CENTER = Vector2(192.0, 120.0)

# —— 最终弹幕的节拍 ——
# 相邻两环大玉隔多少帧。
#
# 这个数管的是「环与环分不分得开」：大玉 2.54 px/帧、球体直径 33px，走完一个球位
# 要 13 帧，隔 30 帧出下一环（76px）就是两个多球位开外——看得出来是一环一环在左右
# 转。**大玉的速度和这个数要一起调**，不然几环连成一条河，设计就白做了。
RING_GAP = 30
# 一串打几**环**大玉，然后换方向。
# **换方向的节奏就是它**：六环朝同一侧转，下一串再朝另一侧。
RING_COUNT = 6
# 换方向的间隙里打多久的乱弹。这期间**不出大玉**——两段弹幕是交替的，不是叠着来的。
KUNAI_FRAMES = 120


def midbossScript(boss: Boss) -> Iterator[None]:
    """小恶魔：一整段血，打光就完。"""
    yield from boss.runPhase(MIDBOSS_HP, patrol(boss))


def patrol(boss: Boss) -> Iterator[None]:
    """小恶魔的全部弹幕：**进场，然后一直是最终弹幕**。

    早先那两节铺垫（扇形、环弹）是按用户要求去掉的——她一进场就进最终弹幕。

    **进场那一句不能省**：出生点在游戏区上方（数据里的 `startPosition`），
    不走这一步她会停在屏幕外，玩家什么都看不到。

    **无限循环**：这一段的结束由玩家的输出决定（血打光），不是由脚本跑完决定
    ——原作的通常攻击就是打到没血为止。血空的那一帧 `runPhase` 会跳出循环，
    这个生成器随之被丢弃（里面没有 `try/finally`，没有要收尾的东西）。
    """
    yield from boss.moveTo(CENTER, frames=90)
    yield from finalBarrage(boss)


def finalBarrage(boss: Boss) -> Iterator[None]:
    """最终弹幕：**一串六环大玉 → 一段乱弹 → 换方向再来**，如此反复。

    - **大玉**：一串六环，一环 12 颗、相邻 30°（见关卡数据里的 `big`），
      每 `RING_GAP` 帧一环。一串之内朝向一路累加着转（第一环 +1 步、第二环 +2 步……）。
    - **乱弹**：一串打完、**换方向的那一刻**开一段苦无（每颗随机方向），
      持续 `KUNAI_FRAMES` 帧。**这一段里不出大玉**——两段是交替的。
    - 苦无的弹速与第一波小怪**差不多**（2.0 px/帧，小怪是 2.5），比大玉
      （2.535 px/帧）慢一些。它从 BOSS 身上往四面八方撒，而上一串大玉还在往外
      飘——两段弹幕因此在同一片区域里**叠着**，这正是设计里要的效果。
      （它们不互相追赶：大玉快、苦无慢，二者只是共存。）
    """
    ringSteps = 0
    direction = 1
    while True:
        # 一串大玉：每 RING_GAP 帧一环，朝向一路转过去
        for _ in range(RING_COUNT):
            ringSteps += direction
            boss.fireOnce("big", volleyIndex=ringSteps)
            yield from boss.wait(RING_GAP)

        # 换方向，并且在一串打完的间隙里打乱弹：这段期间**不出大玉**
        direction = -direction
        boss.stopFiring()
        boss.fires("kunai")
        yield from boss.wait(KUNAI_FRAMES)
        boss.stopFiring()
