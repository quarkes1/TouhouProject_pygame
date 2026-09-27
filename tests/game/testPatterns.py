"""三种弹幕模板。

这里的断言是**逐个角度**的，不是「大概是个扇形」：弹幕打歪了不会崩、只会让关卡
变得不对，而「形状差不多」这种断言在角度符号写反时照样绿。
自机狙那条尤其重要——参考项目正是在自机位于敌机上方时把扇形整体垂直镜像，
而那种错**只有让目标出现在上半屏**的测试才抓得到（纯数学版见 tests/core/testVector2.py）。

参数的构造走下面的工厂函数：波数与波间隔是**调度**用的，与「弹型打成什么形状」
无关，绝大多数测试不关心，写进每个构造里只会淹没重点。
"""

import random

import pygame
import pytest

from touhou import constants
from touhou.core.spriteSheet import SpriteSheet
from touhou.core.vector2 import Vector2
from touhou.game.bulletField import BulletField
from touhou.game.entities.bullet import BulletSpec
from touhou.game.patterns import PATTERN_REGISTRY, FiringContext
from touhou.game.patterns.long_random import LongRandomParams, longRandom
from touhou.game.patterns.wide_cone import WideConeParams, wideCone
from touhou.game.patterns.wide_ring import WideRingParams, wideRing

SEED = 12345


@pytest.fixture
def bullet() -> BulletSpec:
    surface = pygame.Surface((16, 16), pygame.SRCALPHA)
    surface.fill((255, 255, 255, 255))
    return BulletSpec(spriteSheet=SpriteSheet(surface, 16, 16), radius=3.0)


@pytest.fixture
def field() -> BulletField:
    return BulletField()


def cone(bullet, bulletCount, deltaAngleDeg, baseAngleDeg=None) -> WideConeParams:
    return WideConeParams(
        bulletCount=bulletCount,
        coneCount=1,
        bullet=bullet,
        speed=2.0,
        deltaAngleDeg=deltaAngleDeg,
        intervalFrames=0.0,
        baseAngleDeg=baseAngleDeg,
    )


def ring(bullet, bulletCount, deltaAngleDeg, randomCenter=False) -> WideRingParams:
    return WideRingParams(
        bulletCount=bulletCount,
        ringCount=1,
        bullet=bullet,
        speed=2.0,
        deltaAngleDeg=deltaAngleDeg,
        intervalFrames=0.0,
        randomCenter=randomCenter,
    )


def randomBurst(bullet, bulletCount, randomCenter=False) -> LongRandomParams:
    return LongRandomParams(
        bulletCount=bulletCount,
        burstCount=1,
        bullet=bullet,
        speed=2.0,
        intervalFrames=0.0,
        randomCenter=randomCenter,
    )


def context(field, aimAngleDeg=0.0, rng=None, volleyIndex=0) -> FiringContext:
    return FiringContext(
        field=field,
        origin=Vector2(200.0, 200.0),
        aimAngleDeg=aimAngleDeg,
        rng=rng if rng is not None else random.Random(SEED),
        volleyIndex=volleyIndex,
    )


def anglesOf(field: BulletField) -> list[float]:
    return [round(bullet.angleDeg, 6) for bullet in field.active]


# —— 扇形 ——


def testConeFiresExactlyTheRequestedBulletsAtEvenSpacing(field, bullet):
    wideCone(cone(bullet, 5, 15.0), context(field))

    assert anglesOf(field) == [-30.0, -15.0, 0.0, 15.0, 30.0]


def testConeUsesTheBaseAngleWhenGiven(field, bullet):
    wideCone(cone(bullet, 3, 10.0, baseAngleDeg=100.0), context(field, aimAngleDeg=0.0))

    assert anglesOf(field) == [90.0, 100.0, 110.0]


def testConeWithEvenBulletCountHasNoCentreBullet(field, bullet):
    """4 发时没有正中一发——`range(-N+1, N, 2)` 的自然结果，真实数据里也有这种。"""
    wideCone(cone(bullet, 4, 10.0), context(field))

    assert anglesOf(field) == [-15.0, -5.0, 5.0, 15.0]


@pytest.mark.parametrize("aimAngleDeg", [0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0])
def testAimedConeCentresOnTheAimDirection(field, bullet, aimAngleDeg):
    """自机狙：扇形的中轴必须正好指向自机，八个方位都要对。

    只测下半屏是不够的——参考项目的 acos 瞄准在**上半屏**会垂直镜像，
    而敌机通常从上方打下方的自机，所以那种错在端到端测试里永远看不见。
    """
    wideCone(cone(bullet, 3, 10.0), context(field, aimAngleDeg=aimAngleDeg))

    # 扇形**不做**角度归一化（子弹对任意角度都正常，取模是多余的操作），
    # 所以这里也按模 360 比——比的是方向，不是数字落在哪个区间。
    assert [angle % 360 for angle in anglesOf(field)] == [
        (aimAngleDeg - 10.0) % 360,
        aimAngleDeg % 360,
        (aimAngleDeg + 10.0) % 360,
    ]


def testAimedConeAnglesAgreeWithTheDirectionToTheTarget(field, bullet):
    """算出来的角度要真的**指得中**目标，而不只是数字对得上。

    这条把瞄准与 `Vector2.angleDeg` 的约定绑在一起：若有人改用 `acos` 那类只覆盖
    [0°, 180°] 的写法，自机在敌机上方时打出的方向会与实际方向相反。
    这里直接拿方向向量比，不看角度数字。
    """
    origin = Vector2(200.0, 400.0)
    target = Vector2(120.0, 100.0)  # 左上方，正是会中招的方向

    wideCone(
        cone(bullet, 1, 10.0),
        FiringContext(
            field=field,
            origin=origin,
            aimAngleDeg=(target - origin).angleDeg(),
            rng=random.Random(SEED),
        ),
    )

    fired = field.active[0]
    assert fired.velocity.normalize().toTuple() == pytest.approx(
        (target - origin).normalize().toTuple()
    )


# —— 环形 ——


def testRingFiresEvenlySpacedBullets(field, bullet):
    wideRing(ring(bullet, 4, 0.0), context(field))

    assert anglesOf(field) == [0.0, 90.0, 180.0, 270.0]


def testRingRotatesByVolleyIndex(field, bullet):
    """第 n 环整体比第 0 环多转 `n × deltaAngleDeg`——螺旋就是这么累积出来的。"""
    wideRing(ring(bullet, 4, 10.0), context(field, volleyIndex=3))

    assert anglesOf(field) == [30.0, 120.0, 210.0, 300.0]


def testRingSpiralDirectionFollowsTheSign(field, bullet):
    """`deltaAngleDeg` 的正负决定螺旋往哪边绕，这条把符号钉死。

    迁移工具会把参考项目的有符号角度取负（它的旋转方向与我们相反），所以必须确认
    「负角往另一边绕」——否则整关的螺旋都会绕反，而且不会有任何东西报错。
    """
    wideRing(ring(bullet, 3, 10.0), context(field, volleyIndex=1))
    assert anglesOf(field) == [10.0, 130.0, 250.0]

    field.clear()
    wideRing(ring(bullet, 3, -10.0), context(field, volleyIndex=1))
    assert anglesOf(field) == [350.0, 110.0, 230.0]


def testRingNormalizesAnglesIntoRange(field, bullet):
    wideRing(ring(bullet, 3, -100.0), context(field, volleyIndex=1))

    assert all(0.0 <= angle < 360.0 for angle in anglesOf(field))


# —— 随机 ——


def testRandomFiresRequestedBulletCount(field, bullet):
    longRandom(randomBurst(bullet, 7), context(field))

    assert len(field) == 7


def testRandomIsReproducibleForTheSameSeed(bullet):
    """同一个种子必须给出逐发相同的弹幕。

    这条守住「随机数注入」这个决定：换成全局 `random` 就复现不了，
    而确定性是固定步长存在的理由（docs/DESIGN.md「主循环」）。
    """
    first = BulletField()
    longRandom(randomBurst(bullet, 5), context(first, rng=random.Random(SEED)))
    second = BulletField()
    longRandom(randomBurst(bullet, 5), context(second, rng=random.Random(SEED)))

    assert anglesOf(first) == anglesOf(second)


def testRandomDiffersForDifferentSeeds(bullet):
    first = BulletField()
    longRandom(randomBurst(bullet, 5), context(first, rng=random.Random(1)))
    second = BulletField()
    longRandom(randomBurst(bullet, 5), context(second, rng=random.Random(2)))

    assert anglesOf(first) != anglesOf(second)


def testRandomCentreOffsetsTheOriginAndIsReproducible(bullet):
    """「随机中心」：发射点绕敌人随机偏，偏移量不超过约定半径，且同种子可复现。"""
    origin = Vector2(200.0, 200.0)

    offsets = []
    for _ in range(2):
        field = BulletField()
        longRandom(
            randomBurst(bullet, 6, randomCenter=True),
            FiringContext(field=field, origin=origin, aimAngleDeg=0.0, rng=random.Random(SEED)),
        )
        offsets.append([(b.position - origin).length() for b in field.active])

    assert offsets[0] == pytest.approx(offsets[1]), "同种子必须给出同样的偏移"
    assert max(offsets[0]) == pytest.approx(constants.BULLET_RANDOM_CENTER_OFFSET, abs=1e-9)


def testRandomCentreDisabledKeepsBulletsAtTheOrigin(field, bullet):
    longRandom(randomBurst(bullet, 4, randomCenter=False), context(field))

    assert all(b.position == Vector2(200.0, 200.0) for b in field.active)


# —— 退化输入与共享 ——


@pytest.mark.parametrize("bulletCount", [0, 1, 2])
def testSmallBulletCountsDoNotCrash(field, bullet, bulletCount):
    """弹数为 0/1/2 都不能崩。真实数据里最小是 3，但格式没有禁止更小的数。"""
    wideCone(cone(bullet, bulletCount, 10.0), context(field))
    assert len(field) == bulletCount

    field.clear()
    wideRing(ring(bullet, bulletCount, 10.0), context(field))
    assert len(field) == bulletCount

    field.clear()
    longRandom(randomBurst(bullet, bulletCount), context(field))
    assert len(field) == bulletCount


def testRotatedSurfacesAreSharedAcrossBullets(bullet):
    """旋转贴图按 (帧, 角度) 共享，不按子弹数增长。

    320 发弹只有 8 个角度，所以只该有 8 条缓存。这条守的是
    docs/DESIGN.md 称为「本项目最重要的性能设计」的那件事：参考项目的缺陷三
    正是每发子弹各自 `transform.rotate` 一次。若有人把旋转挪进 `Bullet.__init__`
    之类的地方，缓存就会随弹数涨到 320。
    """
    field = BulletField()
    params = ring(bullet, 8, 0.0)

    for _ in range(40):
        wideRing(params, context(field, volleyIndex=0))
    field.draw(pygame.Surface((400, 400)))

    assert len(field) == 320
    assert len(bullet.spriteSheet.rotatedCache) == 8


def testManyVolleysStayBoundedByDistinctAngles(bullet):
    """逐环旋转时缓存条目数只随**不同角度**增长，与发射次数无关。"""
    field = BulletField()
    params = ring(bullet, 4, 90.0)

    for volley in range(30):
        wideRing(params, context(field, volleyIndex=volley))
    field.draw(pygame.Surface((400, 400)))

    angles = {int(bullet_.angleDeg) % 360 for bullet_ in field.active}
    assert len(field) == 120
    assert len(bullet.spriteSheet.rotatedCache) == len(angles)


def testRegistryKnowsAllThreePatterns():
    assert {"wide_cone", "wide_ring", "long_random"} <= set(PATTERN_REGISTRY)
