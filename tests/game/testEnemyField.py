"""敌机容器：出生时刻表、开火调度、回收与自机狙。

容器是「谁在什么时候开火」这件事的唯一负责人：敌机自己只管走轨迹与到点提醒，
子弹长什么样归模板，而**自机狙的角度在这里算**——所以瞄准的退化情形与
「朝上打还是朝下打」这类错都归这个文件守。
"""

import random

import pygame
import pytest

from touhou.core.collider import Collider
from touhou.core.spriteSheet import SpriteSheet
from touhou.core.vector2 import Vector2
from touhou.game.bulletField import BulletField
from touhou.game.enemyField import EnemyField
from touhou.game.entities.bullet import BulletSpec
from touhou.game.entities.enemy import Enemy
from touhou.game.levelData import EnemyAttack, EnemySpawn, EnemyType
from touhou.game.patterns.long_random import LongRandomParams
from touhou.game.patterns.wide_cone import WideConeParams

SEED = 999

# 停在原地的敌人：单点路径，怎么走都在那一点上
STATIONARY = Vector2(200.0, 100.0)
PLAYER_BELOW = Vector2(200.0, 400.0)

from tests.game.conftest import makeBossSpawn


@pytest.fixture
def bullet() -> BulletSpec:
    surface = pygame.Surface((16, 16), pygame.SRCALPHA)
    surface.fill((255, 255, 255, 255))
    return BulletSpec(spriteSheet=SpriteSheet(surface, 16, 16), radius=3.0)


@pytest.fixture
def enemyType(bullet) -> EnemyType:
    return EnemyType(spriteSheet=bullet.spriteSheet, radius=8.0)


def aimedConeAttack(bullet, frame=0.0) -> EnemyAttack:
    params = WideConeParams(
        bulletCount=3,
        coneCount=1,
        bullet=bullet,
        speed=2.0,
        deltaAngleDeg=10.0,
        intervalFrames=0.0,
        baseAngleDeg=None,  # 自机狙
    )
    return EnemyAttack(frame=frame, pattern="wide_cone", params=params, volleyIndex=0)


def randomAttack(bullet, frame=0.0, bulletCount=5) -> EnemyAttack:
    params = LongRandomParams(
        bulletCount=bulletCount,
        burstCount=1,
        bullet=bullet,
        speed=2.0,
        intervalFrames=0.0,
        randomCenter=False,
    )
    return EnemyAttack(frame=frame, pattern="long_random", params=params, volleyIndex=0)


def stationarySpawn(enemyType, frame=0.0, attacks=(), position=None) -> EnemySpawn:
    return EnemySpawn(
        frame=frame,
        enemyType=enemyType,
        path=(STATIONARY if position is None else position,),
        durationFrames=60.0,
        hp=10,
        clearOnDeath=False,
        attacks=tuple(attacks),
    )


def makeField(spawns, seed=SEED) -> EnemyField:
    return EnemyField(tuple(spawns), random.Random(seed))


# —— 出生时刻表 ——


def testEnemiesAppearOnTheirFrame(enemyType):
    """`frame=3` 表示**第 3 次** update 出场——即关卡时钟走到第 3 帧。

    所以 7 秒那波敌人（frame=420）正好在第 420 次 update 出现。
    """
    field = makeField([stationarySpawn(enemyType, frame=3.0)])
    bulletField = BulletField()

    for _ in range(2):
        field.update(bulletField, PLAYER_BELOW)
        assert len(field) == 0

    field.update(bulletField, PLAYER_BELOW)
    assert len(field) == 1


def testSeveralEnemiesCanAppearOnTheSameFrame(enemyType):
    field = makeField([stationarySpawn(enemyType, frame=2.0) for _ in range(4)])
    bulletField = BulletField()

    for _ in range(2):
        field.update(bulletField, PLAYER_BELOW)

    assert len(field) == 4


# —— 开火 ——


def testEnemyFiresIntoTheGivenBulletField(enemyType, bullet):
    field = makeField([stationarySpawn(enemyType, attacks=[aimedConeAttack(bullet)])])
    bulletField = BulletField()

    field.update(bulletField, PLAYER_BELOW)

    assert len(bulletField) == 3, "一帧就该把这一波打完"


def testAttackFiresExactlyNFramesAfterBirth(enemyType, bullet):
    """`frame=5` 的齐射落在**出生帧 + 5**，不多不少。

    出生帧是第 1 次 update（敌机在这一帧出场、`ageFrames` 是 0）。所以第 5 次
    update 之后仍未开火，第 6 次正好打响。这条把「出生放在推进之后」那个修掉的
    差一帧钉死——放回推进之前，所有弹幕都会早 1/60 秒，而没有任何东西会报错。
    """
    field = makeField([stationarySpawn(enemyType, attacks=[aimedConeAttack(bullet, frame=5.0)])])
    bulletField = BulletField()

    for _ in range(5):
        field.update(bulletField, PLAYER_BELOW)
    assert len(bulletField) == 0, "第 5 帧还不该开火"

    field.update(bulletField, PLAYER_BELOW)
    assert len(bulletField) == 3, "第 6 帧（出生帧 + 5）该开火了"


@pytest.mark.parametrize(
    "playerPosition",
    [
        Vector2(200.0, 400.0),  # 正下方
        Vector2(200.0, -200.0),  # 正上方——参考项目在这种情形会打反
        Vector2(400.0, 0.0),  # 右上
        Vector2(0.0, 0.0),  # 左上
    ],
)
def testAimedAttacksPointAtThePlayerFromEverySide(enemyType, bullet, playerPosition):
    """自机在敌机的哪一侧都必须打对方向，尤其是**上方**。

    参考项目的瞄准用 `acos` 算，只覆盖 [0°, 180°]，自机跑到敌机上方时会
    垂直镜像、朝反方向打。而敌人通常从上方打下方的自机，所以那种错在真实关卡里
    从来不会暴露——只有在这里把自机放到各种方位才测得出来。
    """
    field = makeField([stationarySpawn(enemyType, attacks=[aimedConeAttack(bullet)])])
    bulletField = BulletField()

    field.update(bulletField, playerPosition)

    directionToPlayer = (playerPosition - STATIONARY).normalize()
    for fired in bulletField.active:
        # 扇形中轴那发应当正好指向自机；两侧各偏 10°，所以夹角不超过 15°。
        assert fired.velocity.normalize().dot(directionToPlayer) > 0.96


def testPlayerExactlyOnTopOfTheEnemyDoesNotCrash(enemyType, bullet):
    """自机与敌机重合时差向量是零向量——必须仍然打出子弹，而不是 NaN。"""
    field = makeField([stationarySpawn(enemyType, attacks=[aimedConeAttack(bullet)])])
    bulletField = BulletField()

    field.update(bulletField, STATIONARY)

    assert len(bulletField) == 3
    for fired in bulletField.active:
        assert fired.velocity.x == fired.velocity.x, "速度不能是 NaN"


# —— 确定性与随机 ——


def testSameSeedProducesTheSameBarrage(enemyType, bullet):
    """同一个种子跑两遍，逐发一致——这是「随机数注入」那条决定的可执行形式。"""

    def run(seed):
        field = makeField([stationarySpawn(enemyType, attacks=[randomAttack(bullet)])], seed)
        bulletField = BulletField()
        field.update(bulletField, PLAYER_BELOW)
        return [round(fired.angleDeg, 6) for fired in bulletField.active]

    assert run(SEED) == run(SEED)


def testDifferentSeedsProduceDifferentBarrages(enemyType, bullet):
    def run(seed):
        field = makeField([stationarySpawn(enemyType, attacks=[randomAttack(bullet)])], seed)
        bulletField = BulletField()
        field.update(bulletField, PLAYER_BELOW)
        return [round(fired.angleDeg, 6) for fired in bulletField.active]

    assert run(1) != run(2)


# —— 回收与清空 ——


def testFinishedEnemiesAreRemoved(enemyType):
    """走完轨迹的敌机必须被回收，否则一关下来会越积越多。

    这里用 DURATION_FRAMES 很小的一条轨迹让它很快走完。
    """
    spawn = EnemySpawn(
        frame=0.0,
        enemyType=enemyType,
        path=(Vector2(100.0, 100.0), Vector2(120.0, 100.0)),
        durationFrames=2.0,  # 2 帧走完
        hp=10,
        clearOnDeath=False,
        attacks=(),
    )
    field = makeField([spawn])
    bulletField = BulletField()

    for _ in range(10):
        field.update(bulletField, PLAYER_BELOW)

    assert len(field) == 0


def testDrawPaintsEnemiesOntoTheCanvas(enemyType):
    field = makeField([stationarySpawn(enemyType, frame=0.0)])
    bulletField = BulletField()
    field.update(bulletField, PLAYER_BELOW)

    canvas = pygame.Surface((400, 400))
    canvas.fill((0, 0, 0))
    field.draw(canvas)

    assert any(
        canvas.get_at((x, y))[:3] != (0, 0, 0) for x in range(180, 220) for y in range(80, 120)
    ), "敌机所在的方块内应当有非背景像素"


# —— 撞机查询 ——


def testTouchesFindsAnyEnemyOnTheField(enemyType):
    """与 `BulletField.hits` 对称：任一架的机体碰到就算碰到。"""
    field = makeField(
        [
            stationarySpawn(enemyType, frame=0.0, position=Vector2(60.0, 300.0)),
            stationarySpawn(enemyType, frame=0.0, position=Vector2(200.0, 100.0)),
        ]
    )
    field.update(BulletField(), PLAYER_BELOW)

    assert field.touches(Collider(radius=2.0, position=Vector2(200.0, 100.0)))
    assert field.touches(Collider(radius=2.0, position=Vector2(200.0, 106.0)))
    assert not field.touches(Collider(radius=2.0, position=Vector2(200.0, 140.0)))


def testTouchesIsFalseOnAnEmptyField():
    field = EnemyField((), random.Random(SEED))
    assert not field.touches(Collider(radius=2.0, position=Vector2(200.0, 100.0)))


def testTouchesUsesTheSmallerBodyRadius(enemyType):
    """贴图边缘外一点点：**打得中**（数据半径 8），但**撞不到**（机体 6.4）。"""
    enemy = Enemy(stationarySpawn(enemyType, frame=0.0, position=STATIONARY))
    field = EnemyField((), random.Random(SEED))
    field.active.append(enemy)
    betweenTheTwo = Collider(radius=1.0, position=Vector2(STATIONARY.x, STATIONARY.y + 8.5))

    assert enemy.checkCollision(betweenTheTwo), "前提：这个距离上子弹打得中"
    assert not field.touches(betweenTheTwo)


# —— BOSS 的挂载 ——


def testBossAppearsOnlyAtItsFrame():
    """BOSS 到点才出场：之前 `field.boss` 是 None，之后才在场上。"""
    field = EnemyField((), random.Random(SEED), (makeBossSpawn(atFrame=30.0),))

    for _ in range(29):
        field.update(BulletField(), PLAYER_BELOW)
        assert field.boss is None, "还没到点"
    assert len(field) == 0

    field.update(BulletField(), PLAYER_BELOW)

    assert field.boss is not None, "第 30 帧该出场了"
    assert field.boss in field.active, "BOSS 同时也在 active 里（碰撞、绘制都靠它）"


def testBossDoesNotActOnItsBirthFrame():
    """出生那一帧不推进脚本——与敌机「出生那帧不推进」是同一条规矩。

    于是脚本的第一步（设血量、登记开火计划）落在下一帧，而血条在那之前
    没有「本段血量」可画（`maxHp` 还是 0）。
    """
    field = EnemyField((), random.Random(SEED), (makeBossSpawn(atFrame=1.0),))
    field.update(BulletField(), PLAYER_BELOW)

    boss = field.boss
    assert boss is not None
    assert boss.ageFrames == 0, "出生帧不推进"
    assert boss.maxHp == 0, "脚本还没跑"

    field.update(BulletField(), PLAYER_BELOW)
    assert boss.ageFrames == 1


def testDefeatedBossLeavesTheFieldAndClearsTheRecord():
    field = EnemyField((), random.Random(SEED), (makeBossSpawn(atFrame=1.0),))
    field.update(BulletField(), PLAYER_BELOW)
    boss = field.boss
    assert boss is not None

    boss.hp = 0
    field.update(BulletField(), PLAYER_BELOW)

    assert field.boss is None, "死了就该清掉记录，否则 UI 会一直画着血条"
    assert boss not in field.active
    assert len(field) == 0


def testOldConstructorSignatureStillWorks():
    """不带 BOSS 参数的构造仍然可用（既有的调用点一个都不用改）。"""
    field = EnemyField((), random.Random(SEED))
    field.update(BulletField(), PLAYER_BELOW)
    assert field.boss is None
    assert len(field) == 0
