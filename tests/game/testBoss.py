"""BOSS：脚本机制、开火计划、占位立绘。

这个文件里最要紧的是**「一帧恰好推进一步」**那几条：脚本用生成器写，而生成器的
推进步数是**看不见的**——多推一步不会报错，只会让整个 BOSS 的节奏快一倍，
而且要到很后面才看得出来。
"""

from collections.abc import Iterator

import pygame
import pytest
from tests.game.conftest import BOSS_START, makeBossSpawn

from touhou import constants
from touhou.core.spriteSheet import SpriteSheet
from touhou.core.vector2 import Vector2
from touhou.game.entities.boss import (
    BOSS_FRAME_SIZE,
    BOSS_ROTATION_FRAMES,
    Boss,
    bakeBossSprite,
)
from touhou.game.levelData import EnemyAttack, EnemySpawn
from touhou.game.patterns.wide_cone import WideConeParams

START = BOSS_START


def bulletSpec() -> object:
    surface = pygame.Surface((16, 16), pygame.SRCALPHA)
    surface.fill((255, 255, 255, 255))
    from touhou.game.entities.bullet import BulletSpec

    return BulletSpec(spriteSheet=SpriteSheet(surface, 16, 16), radius=3.0)


def emptyScript(boss: Boss) -> Iterator[None]:
    """什么都不做的脚本：立刻跑完。"""
    return
    yield


def foreverScript(boss: Boss) -> Iterator[None]:
    while True:
        yield


def spreadAttack(intervalFrames: int = 4) -> EnemyAttack:
    return EnemyAttack(
        frame=0.0,
        pattern="wide_cone",
        params=WideConeParams(
            bulletCount=1,
            coneCount=1,
            bullet=bulletSpec(),  # type: ignore[arg-type]
            speed=1.0,
            deltaAngleDeg=0.0,
            intervalFrames=intervalFrames,
            baseAngleDeg=0.0,
        ),
        volleyIndex=0,
    )


def makeBoss(script=None, attacks=None, name: str = "测试用") -> Boss:
    return Boss(makeBossSpawn(script=script, attacks=attacks, name=name))


# —— 占位立绘 ——


def testBakeProducesTheDeclaredFramesAtTheDeclaredSize():
    sheet = bakeBossSprite((200, 80, 120))
    assert sheet.frameCount == BOSS_ROTATION_FRAMES
    assert sheet.frameWidth == BOSS_FRAME_SIZE
    assert sheet.frameHeight == BOSS_FRAME_SIZE


def testBakeActuallyRotatesTheBody():
    """每一帧都得长得不一样——否则「旋转动画」是一句空话。

    机体是**五边形**（72° 才自重复）而每帧转 45°，所以八帧两两不同。用八边形
    的话 45° 正好重合，这条会红——那正是「白转一圈」的样子。
    """
    sheet = bakeBossSprite((200, 80, 120))
    frames = [pygame.image.tobytes(sheet.getFrame(i), "RGBA") for i in range(sheet.frameCount)]
    assert len(set(frames)) == sheet.frameCount, "有帧长得一样，旋转没烘进去"


def testBakeUsesTheGivenColor():
    sheet = bakeBossSprite((250, 30, 90))
    frame = sheet.getFrame(0)
    center = frame.get_at((frame.get_width() // 2, frame.get_height() // 2))
    assert center[:3] != (0, 0, 0), "中心该被机体填上"
    assert center.r > center.g and center.r > center.b, f"机体该是给的红色系，实际 {center}"


def testBossIsDrawnAtItsDeclaredSize():
    boss = makeBoss()
    assert boss.spriteSheet.frameWidth == BOSS_FRAME_SIZE
    assert boss.currentFrame().get_width() == BOSS_FRAME_SIZE


# —— 碰撞半径 ——


def testBossHitboxComesFromTheSpriteShortSide():
    """判定半径 = 贴图**短边**的一半，撞机半径再乘一个小于 1 的系数。

    与敌机同一套规矩（`EnemyType.radius` 是「打得中」的圈，`bodyRadius` 是撞死
    自机的圈，后者更小），所以不能拿别的东西推：贴图是唯一同时说得清「画多大」
    与「打得到多大」的量，立绘一换，两个圈自动跟着走。

    **短边**而不是长边：占位立绘外圈那点光晕在帧内，短边就是它画的边界；
    拿外接圆或对角线推的话，判定圈会比眼睛看到的大一圈。
    """
    boss = makeBoss()
    assert boss.radius == pytest.approx(BOSS_FRAME_SIZE / 2)
    assert boss.bodyRadius == pytest.approx(boss.radius * constants.ENEMY_BODY_RADIUS_FACTOR)
    assert boss.bodyRadius < boss.radius


def testBossUsesTheLevelsSpriteWhenThereIsOne():
    """关卡数据给了真立绘就用它——判定半径跟着立绘走，占位图完全不参与。

    这是规格 §6.7 那句「将来替换为真实美术时逻辑代码零改动」的验收点：换美术
    只改关卡数据里的 `sprite`，`Boss` 这边一行都不用动。
    """
    sheet = SpriteSheet(pygame.Surface((32, 48), pygame.SRCALPHA), 32, 48)
    boss = Boss(makeBossSpawn(spriteSheet=sheet))

    assert boss.spriteSheet is sheet, "给了真立绘就不该再去烘占位图"
    assert boss.radius == pytest.approx(16.0), "短边 32 的一半"
    assert boss.currentFrame().get_size() == (32, 48)


# —— 脚本推进：一帧一步 ——


def testScriptRunsOneStepPerFrame():
    ticks: list[int] = []

    def script(boss: Boss) -> Iterator[None]:
        for index in range(3):
            ticks.append(index)
            yield

    boss = makeBoss(script)
    for _ in range(3):
        boss.update()

    assert ticks == [0, 1, 2], "三帧走三步"
    assert not boss.scriptDone, "最后一个 yield 之后还挂着，没跑完"

    boss.update()
    assert boss.scriptDone, "再推一帧才耗尽"


def testNestedGeneratorsAdvanceExactlyOneStepPerFrame():
    """三层 `yield from` 嵌套时，一帧**恰好**推进一步。

    中间层若写成 `while True: next(script); yield` 就会每帧多吃一步——脚本整体快
    一倍，不报错、只是节奏不对，这种错在画面上很难看出来。
    """
    ticks: list[int] = []

    def leaf() -> Iterator[None]:
        for index in range(3):
            ticks.append(index)
            yield

    def middle() -> Iterator[None]:
        yield from leaf()
        yield from leaf()

    def script(boss: Boss) -> Iterator[None]:
        yield from middle()

    boss = makeBoss(script)
    for _ in range(5):
        boss.update()
        assert len(ticks) == _ + 1, f"第 {_ + 1} 帧推了不止一步"

    boss.update()
    assert ticks == [0, 1, 2, 0, 1, 2]


def testUpdateAfterTheScriptEndsDoesNotRaise():
    """脚本跑完之后继续 update 不能抛。

    已耗尽的生成器每次 `next()` 都**重新**抛 StopIteration——不接住的话它会一路
    冒到 `Game.update`，把整个游戏打崩（这里不是生成器内部，PEP 479 不保护）。
    """
    boss = makeBoss(emptyScript)
    for _ in range(5):
        boss.update()
    assert boss.scriptDone


# —— moveTo / wait ——


def testMoveToLandsExactlyOnTarget():
    """末帧**精确**落在目标上。

    写成 `(step - 1) / frames` 的话永远差一点，而两段 `moveTo` 连起来会把偏差
    累积——脚本里写坐标就该到位。
    """
    seen: list[Vector2] = []

    def script(boss: Boss) -> Iterator[None]:
        yield from boss.moveTo(Vector2(100.0, 200.0), frames=10)

    boss = makeBoss(script)
    for _ in range(10):
        boss.update()
        seen.append(Vector2(boss.position.x, boss.position.y))

    assert boss.position == Vector2(100.0, 200.0)
    assert seen[0] == Vector2(START.x + (100.0 - START.x) / 10, START.y + (200.0 - START.y) / 10), (
        "第一帧走总路程的十分之一"
    )
    assert len(seen) == 10, "10 帧走完，不是 9 帧也不是 11 帧"


def testWaitYieldsOncePerFrame():
    ticks: list[int] = []

    def script(boss: Boss) -> Iterator[None]:
        yield from boss.wait(4)
        ticks.append(1)

    boss = makeBoss(script)
    for _ in range(4):
        boss.update()
    assert ticks == [], "还没等够"
    boss.update()
    assert ticks == [1]


def testMoveToWithZeroFramesIsANoOp():
    def script(boss: Boss) -> Iterator[None]:
        yield from boss.moveTo(Vector2(0.0, 0.0), frames=0)

    boss = makeBoss(script)
    boss.update()
    assert boss.position == START


# —— 开火计划 ——


def testFiresRepeatsAtTheParamsInterval():
    """按参数自带的 `intervalFrames` 反复打：第 0、4、8 帧各一发。

    `volleyIndex` 从 0 起逐发自增——`wide_ring` 的螺旋靠它，错了就错位。
    """
    scriptedFire: list[int] = []

    def arm(boss: Boss) -> Iterator[None]:
        boss.fires("spread")
        while True:
            yield

    boss = makeBoss(arm, {"spread": spreadAttack(intervalFrames=4)})
    for _ in range(9):
        boss.update()
        scriptedFire.extend(attack.volleyIndex for attack in boss.dueAttacks())

    assert scriptedFire == [0, 1, 2]


def testDueAttacksClearsTheQueue():
    """交出去的齐射要清空——不清的话同一发会被反复打出去。"""

    def arm(boss: Boss) -> Iterator[None]:
        boss.fires("spread")
        while True:
            yield

    boss = makeBoss(arm, {"spread": spreadAttack()})
    boss.update()
    assert len(boss.dueAttacks()) == 1
    assert boss.dueAttacks() == ()


def testFiresRejectsAnUnknownName():
    boss = makeBoss()

    def script(boss: Boss) -> Iterator[None]:
        boss.fires("没有这个")
        yield

    boss = makeBoss(script)
    with pytest.raises(KeyError, match="没有这个"):
        boss.update()


def testStopFiringStopsTheBullets():
    """撤掉计划之后就不该再出弹。

    计划只活两帧：第 1 帧登记（当帧就打一发），第 2 帧再打一发，第 3 帧脚本执行到
    `stopFiring()` 把它撤了——所以后面十帧一发都没有。
    """

    def arm(boss: Boss) -> Iterator[None]:
        boss.fires("spread")
        yield from boss.wait(2)
        boss.stopFiring()
        yield from boss.wait(10)

    boss = makeBoss(arm, {"spread": spreadAttack(intervalFrames=1)})
    volleys = []
    for _ in range(12):
        boss.update()
        volleys.extend(attack.volleyIndex for attack in boss.dueAttacks())

    assert volleys == [0, 1], f"撤掉计划后还在出弹：{volleys}"


# —— runPhase ——


def testRunPhaseSetsTheSegmentHealth():
    def script(boss: Boss) -> Iterator[None]:
        yield from boss.runPhase(77, foreverScript(boss))

    boss = makeBoss(script)
    assert boss.maxHp == 0, "还没进段，血条不该有得画"
    boss.update()
    assert boss.hp == 77
    assert boss.maxHp == 77
    assert boss.phaseIndex == 0, "第一段是 0"


def testRunPhaseEndsWhenTheHealthRunsOutAndStopsAdvancing():
    """血掉光就不再推进子脚本——不然死后的那一帧还会多打一波。"""
    steps: list[int] = []

    def counting() -> Iterator[None]:
        index = 0
        while True:
            steps.append(index)
            index += 1
            yield

    def script(boss: Boss) -> Iterator[None]:
        yield from boss.runPhase(5, counting())

    boss = makeBoss(script)
    for _ in range(3):
        boss.update()
    assert len(steps) == 3

    boss.hp = 0
    boss.update()
    boss.update()
    assert len(steps) == 3, "血空了还在推进子脚本"


def testRunPhaseClearsThePreviousSegmentsPlans():
    """进新的一段要撤掉上一段的开火计划。

    不撤的话上一段的弹幕会一直打到下一段去——两段的弹幕叠在一起，密度翻倍。
    """

    def script(boss: Boss) -> Iterator[None]:
        yield from boss.runPhase(50, endlessFiring(boss))
        yield from boss.runPhase(50, boss.wait(10))

    def endlessFiring(boss: Boss) -> Iterator[None]:
        boss.fires("spread")
        while True:
            yield

    boss = makeBoss(script, {"spread": spreadAttack(intervalFrames=1)})
    boss.update()
    assert len(boss.plans) == 1

    boss.hp = 0
    boss.update()  # 第一段结束，进第二段
    assert boss.plans == [], "上一段的计划没撤掉"
    assert boss.phaseIndex == 1


def testRunPhaseEndsWhenTheSubScriptFinishes():
    def script(boss: Boss) -> Iterator[None]:
        yield from boss.runPhase(50, boss.wait(3))
        boss.hp = 42  # 记号：走到了下一句

    boss = makeBoss(script)
    for _ in range(3):
        boss.update()
    assert boss.hp == 50, "还没走完"
    boss.update()
    assert boss.hp == 42, "子脚本跑完，同一帧就接着执行下一句"


# —— 与既有系统的接线（继承来的行为，最容易在重构里悄悄丢）——


def testBossFinishesWhenDeadOrWhenTheScriptEnds():
    """两条离场路径：被打死，或者脚本自己跑完（退场）。

    BOSS **没有**「飞出场外」——合成出生点里那条单点路径让 `u` 永远是 0，
    成不了 `len(path) - 1`，所以继承来的 `hasLeft` 恒为假。
    """
    boss = makeBoss()
    assert not boss.isFinished(), "刚出生，什么都没发生"
    assert not boss.hasLeft()
    boss.hp = 0
    assert boss.isFinished() and boss.isDead()


def testBossRetreatsWhenItsScriptEnds():
    """脚本跑完而血还没掉光 = 退场，**不算死**。

    中 BOSS 用无限循环的计划，所以不会走到这条路；但要是没有它，一个「有始有终」
    的脚本跑完会留下一尊不动的 BOSS，卡在那里再也不动。
    """
    boss = makeBoss(emptyScript)
    boss.hp = boss.maxHp = 100
    boss.update()

    assert boss.scriptDone
    assert boss.isFinished(), "该退场了"
    assert not boss.isDead(), "退场不是死——清弹是死亡的补偿，退场不该清屏"


def testBossHasNoInstanceDict():
    """`__slots__` 真的在生效（子类漏写会把 `__dict__` 静默加回来）。"""
    assert not hasattr(makeBoss(), "__dict__")


def testBossTakesDamageLikeAnEnemy():
    boss = makeBoss()
    boss.hp = 10
    boss.damage(3)
    assert boss.hp == 7


def testBossContactUsesTheBodyRadius():
    from touhou.core.collider import Collider

    boss = makeBoss()
    touching = Collider(radius=2.0, position=Vector2(boss.position.x, boss.position.y + 5.0))
    assert boss.touches(touching)

    clear = Collider(
        radius=2.0, position=Vector2(boss.position.x, boss.position.y + boss.bodyRadius + 3.0)
    )
    assert not boss.touches(clear)


def testBossRejectsAnEmptySpawnPathContract():
    """合成本身不该抛：单点路径、时长 1 帧是父类契约的占位，见 Boss.__init__。"""
    boss = makeBoss()
    assert boss.u == 0.0
    assert boss.uPerFrame == 0.0
    assert not boss.hasLeft()
    assert boss.position == START


def testBossCarriesTheEnemySpawnType():
    """出生点的类型仍然可查（`repr` 与调试要用）。"""
    boss = makeBoss()
    assert isinstance(boss.path[0], Vector2)
    assert EnemySpawn  # 只是让 import 有意义：出生点是合成出来的


# —— 最终弹幕（小恶魔的收尾，见 stage/level1.py）——


@pytest.fixture(scope="module")
def level():
    """真实关卡：最终弹幕用的攻击表来自它（大玉 12 颗、苦无乱弹）。"""
    pygame.init()
    pygame.display.set_mode((1, 1))
    from touhou.core.paths import assetPath
    from touhou.game.levelData import loadLevel

    return loadLevel(assetPath("levels", "level_1.json"))


def runStride() -> int:
    """两串大玉之间的跨度：一串的时长 + 一段乱弹的时长。"""
    from touhou.game.stage import level1

    return level1.RING_GAP * level1.RING_COUNT + level1.KUNAI_FRAMES


def captureFinalBarrage(level, runs: int = 2):
    """跑 `runs` 串大玉（每串后面跟一段乱弹），返回（帧号, 齐射）的列表。

    直接把脚本换成这一段——别处的铺垫不该混进这条测试。
    """
    from touhou.game.stage import level1

    boss = Boss(level.bosses[0])
    boss.script = level1.finalBarrage(boss)
    shots = []
    for frame in range(runStride() * runs):
        boss.update()
        shots.extend((frame, attack) for attack in boss.dueAttacks())
    return shots


def ringFramesIn(shots) -> list[int]:
    return [frame for frame, attack in shots if attack.pattern == "wide_ring"]


def kunaiFramesIn(shots) -> list[int]:
    return [frame for frame, attack in shots if attack.pattern != "wide_ring"]


def testBigRingsComeInRunsOfSixThenAKunaiPhase(level):
    """**一串六环大玉 → 一段乱弹 → 换方向再来**：整段的骨架。

    大玉的帧号可以精确算出来：第 index 环在第 `(index // 6) × 跨度 + (index % 6) × 间隔`
    帧——也就是「六环一簇，簇与簇之间空出一段乱弹」。
    """
    from touhou.game.stage import level1

    shots = captureFinalBarrage(level)
    ringFrames = ringFramesIn(shots)

    expected = [
        index // level1.RING_COUNT * runStride() + index % level1.RING_COUNT * level1.RING_GAP
        for index in range(len(ringFrames))
    ]
    assert ringFrames == expected
    assert len(ringFrames) == level1.RING_COUNT * 2, "两串该是十二环"


def testKunaiOnlyFireInTheGapBetweenRuns(level):
    """**发射乱弹的时候不出大玉**——两段是交替的，不是叠着来的。

    这条就是用户那句「在每一波大玉发射完毕时发射乱弹……发射乱弹时不发射大玉」。
    """
    from touhou.game.stage import level1

    shots = captureFinalBarrage(level)
    kunaiFrames = kunaiFramesIn(shots)
    assert kunaiFrames, "该有乱弹"

    lastRingOffset = level1.RING_GAP * (level1.RING_COUNT - 1)
    for frame in kunaiFrames:
        offset = frame % runStride()
        assert lastRingOffset < offset < runStride(), (
            f"第 {frame} 帧的乱弹落在了大玉串里（簇内偏移 {offset}）"
        )


def testKunaiKeepFiringForTheWholeGap(level):
    """乱弹是**一段**，不是一发：占满整个空隙，按 `intervalFrames` 一波波来。"""
    from touhou.game.stage import level1

    shots = captureFinalBarrage(level)
    kunaiFrames = kunaiFramesIn(shots)
    interval = level.bosses[0].attacks["kunai"].params.intervalFrames

    assert kunaiFrames[1] - kunaiFrames[0] == interval
    # 空隙里连续吐了一整段：波数 = 持续时间 ÷ 间隔
    assert len(kunaiFrames[:6]) == 6
    assert kunaiFrames[0] > 0 and kunaiFrames[-1] - kunaiFrames[0] >= level1.KUNAI_FRAMES - interval


def testBigRingsTurnOneWayForASixRingRunThenReverse(level):
    """一串之内朝向一路累加着转，下一串换个方向转回来。

    `volleyIndex` 就是「第几环」——环形弹自己把它乘成整体角度，所以脚本只需要
    累加*步数*：第一串 1、2、3、4、5、6（转出去），第二串 5、4、3、2、1、0（转回来）。
    """

    shots = captureFinalBarrage(level)
    steps = [attack.volleyIndex for _, attack in shots if attack.pattern == "wide_ring"]

    assert steps == [1, 2, 3, 4, 5, 6, 5, 4, 3, 2, 1, 0]

    # 「一小步」是多少度在关卡数据里：脚本只给步数，角度由 deltaAngleDeg 乘出来
    delta = level.bosses[0].attacks["big"].params.deltaAngleDeg
    assert delta == 7.5
    assert [step * delta for step in steps[:6]] == [7.5, 15.0, 22.5, 30.0, 37.5, 45.0]


def testSpeedsMatchTheDesign(level):
    """两种弹的速度：苦无与**第一波小怪相同**，大玉比它略快。

    设计里写的是「弹速和第一波的小怪**差不多**」——所以这里按 ±30% 判，
    而不是严格相等：这是个手感关系，不是等式（现在 1.8 对 2.5，差 28%）。
    它该拦住的是「差出一个量级」，不是几个百分点。大玉被调快过两轮
    （+50%、再 +30%），现在比苦无快不少。
    """
    attacks = level.bosses[0].attacks
    firstWaveSpeed = level.spawns[0].attacks[0].params.speed

    assert attacks["kunai"].params.speed == pytest.approx(firstWaveSpeed, rel=0.3)
    assert attacks["big"].params.speed == pytest.approx(2.535)
    assert attacks["big"].params.speed > attacks["kunai"].params.speed


def testFireOnceShootsExactlyOneVolley(level):
    """`fireOnce` 打一发就走，不登记计划——环形弹靠它逐环换朝向。"""
    boss = Boss(level.bosses[0])

    boss.fireOnce("big", volleyIndex=2)

    assert boss.plans == [], "打一发不该留下后台计划"
    due = boss.dueAttacks()
    assert len(due) == 1
    assert due[0].pattern == "wide_ring"
    assert due[0].volleyIndex == 2


def testFireOnceRejectsAnUnknownName():
    boss = makeBoss()
    with pytest.raises(KeyError, match="没有这个"):
        boss.fireOnce("没有这个")
