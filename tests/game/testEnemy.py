"""敌机：轨迹推进、开火时刻、血量、判定半径与共享。

单位是本文件最要紧的一条：`durationFrames` 是**走完整条轨迹要多少帧**，
不是像素/帧、也不是「每秒走几个控制点区间」。读错的话敌机会以错误的速度爬行，
且没有任何报错——只有断言位移量才能锁住它。
"""

import pygame
import pytest

from touhou import constants
from touhou.core.collider import Collider
from touhou.core.paths import assetPath
from touhou.core.spline import samplePath
from touhou.core.spriteSheet import SpriteSheet
from touhou.core.vector2 import Vector2
from touhou.game.entities.enemy import Enemy
from touhou.game.levelData import EnemyAttack, EnemySpawn, EnemyType, loadLevel
from touhou.game.patterns.long_random import LongRandomParams

LEVEL_PATH = assetPath("levels", "level_1.json")

# 夹具用 4 个控制点的路径 = 3 个区间；180 帧走完就是每区间 60 帧（1 秒）。
PATH = tuple(Vector2(200.0, 100.0 + 50.0 * step) for step in range(4))
DURATION_FRAMES = 180.0


@pytest.fixture(scope="module")
def level():
    return loadLevel(LEVEL_PATH)


@pytest.fixture
def sheet() -> SpriteSheet:
    """4 帧 × 16×16，纯色便于分辨帧号。"""
    surface = pygame.Surface((16 * 4, 16), pygame.SRCALPHA)
    for index in range(4):
        surface.fill((index * 60, 0, 0, 255), pygame.Rect(index * 16, 0, 16, 16))
    return SpriteSheet(surface, 16, 16)


@pytest.fixture
def spawn(sheet) -> EnemySpawn:
    return EnemySpawn(
        frame=0.0,
        enemyType=EnemyType(spriteSheet=sheet, radius=12.0),
        path=PATH,
        durationFrames=DURATION_FRAMES,
        hp=10,
        clearOnDeath=False,
        attacks=(),
    )


def spawnWith(sheet, attacks) -> EnemySpawn:
    return EnemySpawn(
        frame=0.0,
        enemyType=EnemyType(spriteSheet=sheet, radius=12.0),
        path=PATH,
        durationFrames=DURATION_FRAMES,
        hp=10,
        clearOnDeath=False,
        attacks=attacks,
    )


# —— 池化与共享契约 ——


def testEnemyHasNoInstanceDict(spawn):
    """__slots__ 真的在生效。子类漏写会把 __dict__ 静默加回来。"""
    assert not hasattr(Enemy(spawn), "__dict__")


def testSlotsDoNotOverlapBaseClassSlots():
    assert set(Enemy.__slots__).isdisjoint(Collider.__slots__)


def testResetSetsEveryField(spawn, sheet):
    """reset 之后不留上一条路径的状态。"""
    otherPath = (Vector2(0.0, 0.0), Vector2(10.0, 0.0), Vector2(20.0, 0.0))
    other = EnemySpawn(
        frame=0.0,
        enemyType=EnemyType(spriteSheet=sheet, radius=5.0),
        path=otherPath,
        durationFrames=90.0,
        hp=99,
        clearOnDeath=True,
        attacks=(),
    )
    enemy = Enemy(spawn)
    for _ in range(30):
        enemy.update()

    enemy.reset(other)

    assert enemy.u == 0.0
    assert enemy.path is otherPath
    assert enemy.uPerFrame == pytest.approx(2.0 / 90.0)
    assert enemy.hp == 99
    assert enemy.clearOnDeath is True
    assert enemy.radius == 5.0
    assert enemy.nextAttack == 0
    assert enemy.ageFrames == 0
    assert enemy.animationFrame == 0
    assert enemy.animationTimer == 0.0


def testPathAndAttacksAreSharedNotCopied(spawn):
    """path 直接引用 spawn 里的元组——关卡里 114 个敌人只有 20 条不同轨迹。"""
    enemy = Enemy(spawn)
    assert enemy.path is spawn.path
    assert enemy.attacks is spawn.attacks


# —— 轨迹推进（单位陷阱）——


def testTraversesOneControlPointIntervalPerSecond(spawn):
    """4 个控制点、180 帧的路径：一秒（60 步）恰好走完一个控制点区间。

    这条锁住 `durationFrames` 的含义。若有人把它当成「每秒走几个区间」，
    这一秒会走 180 个区间而不是 1 个——位移差 180 倍，而没有任何东西会报错。
    """
    enemy = Enemy(spawn)
    for _ in range(constants.FPS):
        enemy.update()

    assert enemy.u == pytest.approx(1.0)


def testPositionFollowsTheSpline(spawn):
    """位置恒等于路径在 u 处的取值——不自己另算一套。"""
    enemy = Enemy(spawn)
    for _ in range(37):
        enemy.update()

    assert enemy.position.toTuple() == pytest.approx(samplePath(spawn.path, enemy.u).toTuple())


def testStartsAtTheFirstControlPoint(spawn):
    assert Enemy(spawn).position.toTuple() == pytest.approx(spawn.path[0].toTuple())


def testStopsAtTheEndInsteadOfRunningOff(spawn):
    enemy = Enemy(spawn)
    for _ in range(constants.FPS * 20):
        enemy.update()

    assert enemy.position.toTuple() == pytest.approx(spawn.path[-1].toTuple())


# —— 开火时刻 ——


def testNoAttacksBeforeTheirFrame(sheet):
    params = LongRandomParams(
        bulletCount=1, burstCount=1, bullet=None, speed=1.0, intervalFrames=0.0
    )
    spawn = spawnWith(
        sheet, (EnemyAttack(frame=10.0, pattern="long_random", params=params, volleyIndex=0),)
    )
    enemy = Enemy(spawn)

    for _ in range(9):
        enemy.update()
        assert enemy.dueAttacks() == ()

    enemy.update()
    assert len(enemy.dueAttacks()) == 1, "第 10 帧该打了"


def testEachVolleyFiresExactlyOnce(sheet):
    params = LongRandomParams(
        bulletCount=1, burstCount=1, bullet=None, speed=1.0, intervalFrames=0.0
    )
    attacks = tuple(
        EnemyAttack(frame=float(frame), pattern="long_random", params=params, volleyIndex=index)
        for index, frame in enumerate((5, 10, 15))
    )
    enemy = Enemy(spawnWith(sheet, attacks))

    fired: list[int] = []
    for _ in range(30):
        enemy.update()
        fired.extend(attack.volleyIndex for attack in enemy.dueAttacks())

    assert fired == [0, 1, 2], "每一波恰好打一次，且按时刻先后"


def testDueAttacksCanReturnSeveralInOneFrame(sheet):
    """同一帧到点的多波要一次全打出去，不能一帧只打一波。"""
    params = LongRandomParams(
        bulletCount=1, burstCount=1, bullet=None, speed=1.0, intervalFrames=0.0
    )
    attacks = tuple(
        EnemyAttack(frame=7.0, pattern="long_random", params=params, volleyIndex=index)
        for index in range(3)
    )
    enemy = Enemy(spawnWith(sheet, attacks))

    for _ in range(7):
        enemy.update()

    assert len(enemy.dueAttacks()) == 3


# —— 离场与死亡 ——


def testHasLeftAfterThePathEnds(spawn):
    enemy = Enemy(spawn)
    assert not enemy.hasLeft()

    for _ in range(constants.FPS * 4):
        enemy.update()

    assert enemy.hasLeft()


def testIsFinishedCoversBothExits(spawn):
    """被打死与飞出场是两回事，但都该被容器移除。

    两者语义必须分开：将来的道具掉落挂在 isDead 上——飞走的敌人不该掉东西。
    """
    byDamage = Enemy(spawn)
    byDamage.damage(10)
    assert byDamage.isDead() and byDamage.isFinished()
    assert not byDamage.hasLeft()

    byFlight = Enemy(spawn)
    for _ in range(constants.FPS * 4):
        byFlight.update()
    assert byFlight.isFinished() and byFlight.hasLeft()
    assert not byFlight.isDead()


def testDamageReducesHpAndKillsAtZero(spawn):
    enemy = Enemy(spawn)

    enemy.damage(4)
    assert enemy.hp == 6 and not enemy.isDead()

    enemy.damage(6)
    assert enemy.hp == 0 and enemy.isDead()


# —— 判定半径 ——


def testRadiusComesFromTheDataNotTheSprite(spawn):
    """判定半径来自数据，不从贴图尺寸推导。

    spawn 的贴图是 16×16（半宽 8），而半径给的是 12——已经比贴图宽了。
    若有人改成按贴图推导，下面第一条命中断言会红。
    """
    enemy = Enemy(spawn)

    assert enemy.radius == 12.0
    assert enemy.checkCollision(Collider(radius=1.0, position=Vector2(200.0, 112.0)))
    # 相切不算碰撞，沿用 Collider 的约定
    assert not enemy.checkCollision(Collider(radius=1.0, position=Vector2(200.0, 114.0)))


def testFairyRealHitboxExceedsItsSpriteHalfWidth(level):
    """用真实数据复现「判定圈比贴图宽」这件事。

    妖精贴图 24×19，半宽只有 12，数据给半径 15。按贴图推半径的话，
    贴图边缘外 1px 处就不会命中——玩家能贴着妖精飞过去，而且没有任何报错。
    """
    fairySpawn = next(
        spawn for spawn in level.spawns if spawn.enemyType.spriteSheet.frameWidth == 24
    )
    enemy = Enemy(fairySpawn)
    halfWidth = fairySpawn.enemyType.spriteSheet.frameWidth / 2

    assert enemy.radius > halfWidth
    justOutsideTheSprite = Vector2(enemy.position.x + halfWidth + 1.0, enemy.position.y)
    assert enemy.checkCollision(Collider(radius=1.0, position=justOutsideTheSprite))


# —— 撞机判定半径：与上面那个方向相反 ——


def testBodyRadiusIsSmallerThanTheSprite(spawn):
    """撞机半径**比贴图小**——贴图最外圈那几像素碰到不算死。

    与 `radius`（刚证明它比贴图大）正好相反，这是有意的：被弹判定要「打得到」，
    撞机判定要「没真碰到就不算死」。两个合成一个的话，必然有一边是错的。
    """
    enemy = Enemy(spawn)  # 贴图 16×16，半宽 8
    assert enemy.bodyRadius == pytest.approx(8.0 * constants.ENEMY_BODY_RADIUS_FACTOR)
    assert enemy.bodyRadius < 8.0


def testTouchesUsesTheBodyRadiusNotTheDataRadius(spawn):
    """把两个半径的差别钉在**同一个位置**上：打得中，但撞不到。

    距离取在两者之间（spawn：数据半径 12、机体半径 6.4、判定点 1）。
    把 `touches` 写成 `checkCollision` 的话，这条会红。
    """
    enemy = Enemy(spawn)
    betweenTheTwo = Collider(radius=1.0, position=Vector2(200.0, 109.0))

    assert enemy.checkCollision(betweenTheTwo), "自机子弹在这个距离上应当打得到"
    assert not enemy.touches(betweenTheTwo), "撞机判定要更严格"


def testTouchesOnTheBodyItself(spawn):
    enemy = Enemy(spawn)
    assert enemy.touches(Collider(radius=1.0, position=Vector2(200.0, 105.0)))


def testTouchingExcludesTangent(spawn):
    """相切不算碰撞——与 `checkCollision` 是同一条约定（它们共用 circlesOverlap）。"""
    enemy = Enemy(spawn)
    tangent = Collider(radius=1.0, position=Vector2(200.0, 100.0 + enemy.bodyRadius + 1.0))
    assert not enemy.touches(tangent)


def testNonSquareSpriteUsesTheInscribedCircle(level):
    """帧不是正方形时取**内切**圆（短的那条边），不是外接。

    妖精贴图是 24×19。取半宽 12 的话，自机在妖精正上方或正下方、画面上明明
    还差 2.5px 才碰到的时候就会被撞死——「比贴图略小」这句话在竖直方向上是反的。
    """
    fairySpawn = next(
        spawn for spawn in level.spawns if spawn.enemyType.spriteSheet.frameWidth == 24
    )
    sheet = fairySpawn.enemyType.spriteSheet
    assert sheet.frameWidth != sheet.frameHeight, "这条测试要的是一张非正方形的贴图"
    enemy = Enemy(fairySpawn)
    halfHeight = sheet.frameHeight / 2

    assert enemy.bodyRadius == pytest.approx(halfHeight * constants.ENEMY_BODY_RADIUS_FACTOR)
    # 正下方：超出机体半径就没碰到（判定点半径取 2）。按半宽算的话这里会误判成撞上
    assert not enemy.touches(
        Collider(radius=2.0, position=Vector2(enemy.position.x, enemy.position.y + 10.5))
    )


def testRealMobBodyRadiusIsSlightlySmallerThanItsSprite(level):
    """真实数据：98 架小怪（弹刺球）贴图 32×32、可见半径约 16.4，撞机半径 12.8。

    两侧都断言：比贴图小（不然贴图边缘蹭一下就死），但也没小到形同虚设
    （系数写错一位就是这种）。
    """
    mobSpawn = next(spawn for spawn in level.spawns if spawn.hp == 1)
    enemy = Enemy(mobSpawn)
    halfWidth = mobSpawn.enemyType.spriteSheet.frameWidth / 2

    assert enemy.bodyRadius < halfWidth, "撞机判定要比贴图略小"
    assert enemy.bodyRadius > halfWidth * 0.6, "但也不能小得几乎判不到"


# —— 渲染 ——


def testCurrentFrameDoesNotRotate(spawn, sheet):
    """敌机贴图不跟着运动方向旋转（与子弹不同）。"""
    assert Enemy(spawn).currentFrame() is sheet.getFrame(0)


def testAnimationCyclesAndWraps(spawn):
    enemy = Enemy(spawn)
    observed = set()
    for _ in range(600):
        enemy.update()
        observed.add(enemy.animationFrame)

    assert observed == {0, 1, 2, 3}


def testAnimationFrameStaysInRange(spawn, sheet):
    enemy = Enemy(spawn)
    for _ in range(1000):
        enemy.update()
        assert 0 <= enemy.animationFrame < sheet.frameCount


# —— 真实数据 ——


def testRealEnemyFilesAlongItsLevelPath(level):
    """用关卡里的真实敌人跑一遍：出发生效、中途在动、最后离场。"""
    spawn = max(level.spawns, key=lambda spawn: len(spawn.path))
    enemy = Enemy(spawn)
    startPosition = enemy.position

    for _ in range(constants.FPS * 2):
        enemy.update()
    assert (enemy.position - startPosition).length() > 1.0, "敌机应该已经在沿轨迹移动"

    for _ in range(int(spawn.durationFrames) + constants.FPS):
        enemy.update()

    assert enemy.hasLeft(), f"{spawn.durationFrames / 60:.2f} 秒后应该已经走完"


def testNoVolleyIsScheduledAfterItsEnemyHasLeft(level):
    """全部 122 组攻击里，没有一波排在敌机离场之后。

    这条是本轮最有力的**数据级**校验，来自规格文档那句「时间单位混用」：
    旧格式的 `start_time`/`delay` 用的是轨迹参数 u，换算成帧时要**除以**敌机速度。
    乘反了的话（乘 2.4 而不是除），弹刺球那 98 组攻击会全部排到离场之后——
    表现为「敌机飞走了才开火」，而这条断言会当场指出是哪些。
    """
    late = [
        (index, spawn.attacks[-1].frame, spawn.durationFrames)
        for index, spawn in enumerate(level.spawns)
        if spawn.attacks and spawn.attacks[-1].frame > spawn.durationFrames
    ]
    assert late == [], f"这些敌人的齐射排在离场之后（序号, 末波帧, 轨迹总帧）: {late[:5]}"
