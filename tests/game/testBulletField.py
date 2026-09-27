"""弹幕场：生成、推进、回收、绘制与对象池。

本文件里最重要的是「回收时释放的必须是死者」那一组。那个 bug 只在
**中间那颗弹死**的时候显形——末尾那颗死时错误写法恰好是对的，
所以两种场景都必须测，缺一个就漏。
"""

import pygame
import pytest

from touhou.core.collider import Collider
from touhou.core.spriteSheet import SpriteSheet
from touhou.core.vector2 import Vector2
from touhou.game.bulletField import BulletField, isCulled, playfieldBounds
from touhou.game.entities.bullet import Bullet, BulletSpec

# 大部分机制测试用一张小矩形，坐标好算，也不受 constants 调参影响
BOUNDS = pygame.Rect(0, 0, 100, 100)


@pytest.fixture
def sheet() -> SpriteSheet:
    """16×16 单帧，完全不透明（绘制测试要靠它取质心）。"""
    surface = pygame.Surface((16, 16), pygame.SRCALPHA)
    surface.fill((255, 255, 255, 255))
    return SpriteSheet(surface, 16, 16)


@pytest.fixture
def spec(sheet) -> BulletSpec:
    return BulletSpec(spriteSheet=sheet, radius=3.0)


@pytest.fixture
def field() -> BulletField:
    return BulletField(bounds=BOUNDS)


def spawnOutbound(field: BulletField, spec: BulletSpec, position: Vector2) -> Bullet:
    """放一颗一步就会飞出场的弹。"""
    return field.spawn(spec, position, angleDeg=90, speed=100)


def bulletsOverlapping(one: list[Bullet], other: list[Bullet]) -> set[int]:
    return set(map(id, one)) & set(map(id, other))


# —— 生成与推进 ——


def testSpawnPlacesBulletAtPositionWithVelocity(field, spec):
    bullet = field.spawn(spec, Vector2(10.0, 20.0), angleDeg=90, speed=3.0)

    assert len(field) == 1
    assert bullet.position == Vector2(10.0, 20.0)
    assert bullet.velocity == Vector2.fromDeg(90, 3.0)


def testUpdateMovesEveryBullet(field, spec):
    first = field.spawn(spec, Vector2(10.0, 50.0), angleDeg=90, speed=2.0)
    second = field.spawn(spec, Vector2(20.0, 50.0), angleDeg=0, speed=2.0)

    field.update()

    assert first.position == Vector2(12.0, 50.0)
    assert second.position == Vector2(20.0, 48.0)


def testUpdateAdvancesEachBulletExactlyOnce(field, spec):
    """倒序遍历 + 交换删除不能把某颗弹推进两次或漏掉。

    三条命都留着，位置各不相同：一旦有弹被重复推进，位移就会翻倍。
    """
    bullets = [
        field.spawn(spec, Vector2(10.0 + 10 * index, 50.0), angleDeg=90, speed=1.0)
        for index in range(3)
    ]

    field.update()

    positions = [bullet.position.x for bullet in bullets]
    assert positions == [11.0, 21.0, 31.0]


# —— 回收：死者必须进池，幸存者必须留场 ——


def testCullingMiddleBulletReleasesTheDeadNotTheSurvivor(field, spec):
    """**本文件最重要的一条**：中间那颗弹死的时候，释放的必须是它自己。

    朴素写法 `self.free.append(self.active.pop())` 在这里出错：pop() 取的是末尾，
    而末尾此刻正是刚被复制进中间位置的**幸存者**。结果是幸存者同时躺在 active
    和 free 里（下一轮 spawn 会把它再发一次，同一颗弹被推进、绘制、碰撞两遍），
    真正的死者泄漏。末尾那颗死时那个写法恰好是对的，所以只测末尾等于没测。
    """
    survivorA = field.spawn(spec, Vector2(10.0, 50.0), angleDeg=0, speed=0)
    victim = spawnOutbound(field, spec, Vector2(95.0, 50.0))
    survivorB = field.spawn(spec, Vector2(50.0, 90.0), angleDeg=0, speed=0)

    field.update()

    assert len(field) == 2
    assert field.active == [survivorA, survivorB]
    assert field.free == [victim], "进池的必须是死者，不是被换下来的幸存者"
    assert bulletsOverlapping(field.active, field.free) == set(), (
        "同一颗弹不能同时躺在 active 和 free 里"
    )


def testCullingLastBulletReleasesIt(field, spec):
    """末尾那颗死。错误写法在这里恰好正确，所以这条单独跑绿也不代表没问题。"""
    survivor = field.spawn(spec, Vector2(10.0, 50.0), angleDeg=0, speed=0)
    victim = spawnOutbound(field, spec, Vector2(95.0, 50.0))

    field.update()

    assert field.active == [survivor]
    assert field.free == [victim]
    assert bulletsOverlapping(field.active, field.free) == set()


def testCullingEveryBulletLeavesNothingActive(field, spec):
    bullets = [spawnOutbound(field, spec, Vector2(95.0, 50.0)) for _ in range(4)]

    field.update()

    assert len(field) == 0
    assert sorted(map(id, field.free)) == sorted(map(id, bullets))


# —— 对象池 ——


def testCulledBulletIsReusedByNextSpawn(field, spec):
    """回收的弹会被下一发复用。`is` 是唯一能证明复用真的发生了的断言。"""
    victim = spawnOutbound(field, spec, Vector2(95.0, 50.0))
    field.update()

    reborn = field.spawn(spec, Vector2(10.0, 10.0), angleDeg=0, speed=1.0)

    assert reborn is victim


def testReusedBulletDoesNotInheritPreviousState(field, spec):
    """复用出来的弹不能带着上一发的速度。

    行为化断言：先放一颗慢弹、回收，再放一颗快弹，推进一步看位移。
    reset 漏设 velocity 的话，这里会按慢弹的速度走——而 mypy 不会告诉你。
    """
    # 贴着右边界生成，让它几步内出屏，同时确实长出 ageFrames 与动画状态
    slow = field.spawn(spec, Vector2(95.0, 50.0), angleDeg=90, speed=1.0)
    for _ in range(10):
        field.update()
        if len(field) == 0:
            break
    assert slow in field.free, "前置条件：慢弹应该已经出屏进池"

    reborn = field.spawn(spec, Vector2(10.0, 50.0), angleDeg=90, speed=7.0)
    assert reborn is slow

    field.update()
    assert reborn.position.x == pytest.approx(17.0), "复用的弹必须按新速度走，不是上一发的 1px"
    assert reborn.ageFrames == 1, "上一发的 ageFrames 不能残留"


def testPoolDoesNotGrowAcrossSpawnCullCycles(field, spec):
    """反复生成与回收不产生新对象，空闲列表也不堆积。"""
    first = spawnOutbound(field, spec, Vector2(95.0, 50.0))
    field.update()
    assert len(field.free) == 1

    for _ in range(50):
        reborn = field.spawn(spec, Vector2(95.0, 50.0), angleDeg=90, speed=100)
        assert reborn is first
        field.update()

    assert len(field) == 0
    assert len(field.free) == 1, "池里应当始终只有那一个对象"


def testClearReleasesEverything(field, spec):
    bullets = [
        field.spawn(spec, Vector2(10.0, 10.0 + 10 * index), angleDeg=0, speed=0)
        for index in range(5)
    ]

    field.clear()

    assert len(field) == 0
    assert sorted(map(id, field.free)) == sorted(map(id, bullets))
    assert bulletsOverlapping(field.active, field.free) == set()


def testClearThenSpawnReusesPooledObjects(field, spec):
    original = field.spawn(spec, Vector2(10.0, 10.0), angleDeg=0, speed=0)
    field.clear()

    reborn = field.spawn(spec, Vector2(20.0, 20.0), angleDeg=0, speed=0)

    assert reborn is original


# —— 回收判定（纯函数，脱离贴图）——


def testCulledWhenOutsideBoundsAndMovingFurtherOut():
    assert isCulled(Vector2(-5.0, 50.0), Vector2(-2.0, 0.0), BOUNDS)
    assert isCulled(Vector2(105.0, 50.0), Vector2(2.0, 0.0), BOUNDS)
    assert isCulled(Vector2(50.0, -5.0), Vector2(0.0, -2.0), BOUNDS)
    assert isCulled(Vector2(50.0, 105.0), Vector2(0.0, 2.0), BOUNDS)


def testNotCulledWhenInsideBounds():
    for position in (Vector2(0.0, 0.0), Vector2(50.0, 50.0), Vector2(99.0, 99.0)):
        assert not isCulled(position, Vector2(2.0, 2.0), BOUNDS)
        assert not isCulled(position, Vector2(-2.0, -2.0), BOUNDS)


def testNotCulledWhenOutsideButFlyingBackIn():
    """场外的弹只要朝内飞就不能回收——这正是矩形判定做不到的事。"""
    assert not isCulled(Vector2(-5.0, 50.0), Vector2(2.0, 0.0), BOUNDS)
    assert not isCulled(Vector2(105.0, 50.0), Vector2(-2.0, 0.0), BOUNDS)
    assert not isCulled(Vector2(50.0, -5.0), Vector2(0.0, 2.0), BOUNDS)
    assert not isCulled(Vector2(50.0, 105.0), Vector2(0.0, -2.0), BOUNDS)


def testStationaryBulletOutsideIsCulledButInsideIsKept():
    """场外静止的弹回不来了，回收；场内静止的弹留下——「停下再转向」是合法弹型。"""
    assert isCulled(Vector2(-5.0, 50.0), Vector2(0.0, 0.0), BOUNDS)
    assert isCulled(Vector2(105.0, 50.0), Vector2(0.0, 0.0), BOUNDS)
    assert not isCulled(Vector2(50.0, 50.0), Vector2(0.0, 0.0), BOUNDS)


# —— 回收判定（真实游戏区几何）——


def testInboundBulletBornLeftOfTheFieldSurvives(spec):
    """从游戏区左外侧生成、朝右飞进来的子弹必须活着。

    (-40.32, 193.92) 是真实数据：level_1.json 里敌 13 的 start_position，
    按 game/levelData.py 的换算落到游戏区左外侧，而它的下一个控制点是
    (103.68, 220.80)——确实朝右飞进场内。这样起手的敌人在全关卡里有 22 个。

    按矩形回收会把这类子弹在生成那一帧就杀掉。
    """
    field = BulletField()

    inbound = field.spawn(spec, Vector2(-40.32, 193.92), angleDeg=90, speed=3.0)
    field.update()

    assert inbound in field.active


def testInboundBulletBornRightOfTheFieldSurvives(spec):
    """从游戏区右外侧生成、朝左飞进来的子弹同理。

    (456.96, 158.72) 是真实的敌 36，朝左飞到 (310.40, 171.52)。
    这是全关卡里唯一一个右外侧起手朝内的敌人——所以它正是最容易被
    「矩形回收」误杀的那一个。
    """
    field = BulletField()

    inbound = field.spawn(spec, Vector2(456.96, 158.72), angleDeg=270, speed=3.0)
    field.update()

    assert inbound in field.active


def testInboundBulletBornAboveTheFieldSurvives(spec):
    """从游戏区上方生成、朝下飞的子弹同理。

    没有敌人的**起点**在竖直方向越出回收矩形（所以这条的坐标取自控制点
    而非起点）——y = -51.8 是全部控制点里最靠上的值。敌机飞行途中会经过
    这些控制点附近，所以竖直方向同样需要这条保证。
    四个方向的纯函数覆盖在 testNotCulledWhenOutsideButFlyingBackIn。
    """
    field = BulletField()

    inbound = field.spawn(spec, Vector2(200.0, -51.8), angleDeg=180, speed=3.0)
    field.update()

    assert inbound in field.active


def testOutboundBulletIsCulledAfterLeavingPlayfield(spec):
    """朝场外飞的弹越过边界（含出屏余量）之后要被回收，不能无限积累。"""
    field = BulletField()
    bounds = playfieldBounds()

    bullet = field.spawn(spec, Vector2(200.0, 300.0), angleDeg=90, speed=10.0)
    for _ in range(200):
        field.update()
        if not field.active:
            break

    assert len(field) == 0, "朝右飞的弹应当在越过右边界后离场"
    assert bullet.position.x > bounds.right


# —— 碰撞 ——


def testHitsDetectsOverlapAndRespectsTangentRule(field, spec):
    bullet = field.spawn(spec, Vector2(50.0, 50.0), angleDeg=0, speed=0)  # radius 3

    assert field.hits(Collider(radius=1.0, position=Vector2(50.0, 53.0)))
    # 相切不算碰撞，沿用 Collider 的约定（见 docs/DESIGN.md「关键接口约定」）
    assert not field.hits(Collider(radius=1.0, position=Vector2(50.0, 54.0)))
    assert not field.hits(Collider(radius=1.0, position=Vector2(50.0, 90.0)))
    assert bullet is field.active[0]


def testHitsIsFalseOnEmptyField(field):
    assert not field.hits(Collider(radius=1.0, position=Vector2(50.0, 50.0)))


# —— 绘制 ——


def opaqueCentroid(canvas: pygame.Surface) -> tuple[float, float]:
    pixels = [
        (x, y)
        for y in range(canvas.get_height())
        for x in range(canvas.get_width())
        if canvas.get_at((x, y))[:3] != (0, 0, 0)
    ]
    assert pixels, "画布上没有任何子弹像素"
    return (
        sum(x for x, _ in pixels) / len(pixels),
        sum(y for _, y in pixels) / len(pixels),
    )


@pytest.mark.parametrize("angleDeg", [0, 45, 90])
def testDrawCentersBulletOnPosition(field, spec, angleDeg):
    """子弹以 position 为中心绘制。

    不能写 position - halfSize：旋转后外接矩形会变大（16×16 转到 45° 变成
    22×22），那样算会整整偏出 3px。偏移半张图不会崩溃，只会让人打不中。
    """
    canvas = pygame.Surface((200, 200))
    canvas.fill((0, 0, 0))
    position = Vector2(100.0, 100.0)
    field.spawn(spec, position, angleDeg=angleDeg, speed=0)

    field.draw(canvas)

    centroidX, centroidY = opaqueCentroid(canvas)
    assert centroidX == pytest.approx(position.x, abs=1.0)
    assert centroidY == pytest.approx(position.y, abs=1.0)


def testManyBulletsShareOneRotatedSurface(field, spec, sheet):
    """同一角度的一批弹共用同一张预旋转贴图，不会各转各的。

    docs/DESIGN.md 把预旋转缓存称为「本项目最重要的性能设计」，参考项目的
    缺陷三正是每发子弹重复创建旋转贴图。这条不让它从后门溜回来——
    把旋转挪进 Bullet.__init__ 之类的地方就会让缓存条目随弹数增长。
    """
    canvas = pygame.Surface((400, 400))
    before = len(sheet.rotatedCache)

    for index in range(50):
        field.spawn(spec, Vector2(10.0 + index, 10.0), angleDeg=30, speed=0)
    field.draw(canvas)

    assert len(sheet.rotatedCache) == before + 1


# —— 帧序不变量 ——


def testSpawnDuringUpdateIsNotAdvancedThisFrame(field, spec, monkeypatch):
    """update() 期间新生成的弹，本帧不会被推进。

    倒序循环在入口就定住了 len()，所以循环里追加的弹落在遍历范围之外。
    也就是说生成必须发生在 update() 之前——弹幕模板层正是这么调的。
    将来若真要做「子弹生子弹」的分裂弹型，得由模板层走待处理队列；
    这条测试把当前的契约固定下来，免得有人以为 spawn 可以随时调。
    """
    field.spawn(spec, Vector2(10.0, 50.0), angleDeg=0, speed=0)
    newbornHolder: list[Bullet] = []
    originalUpdate = Bullet.update

    def updateAndSpawn(self: Bullet) -> None:
        originalUpdate(self)
        if not newbornHolder:
            newbornHolder.append(field.spawn(spec, Vector2(50.0, 50.0), angleDeg=0, speed=5.0))

    monkeypatch.setattr(Bullet, "update", updateAndSpawn)

    field.update()

    assert len(newbornHolder) == 1
    newborn = newbornHolder[0]
    assert newborn.ageFrames == 0, "本帧生成的弹不该被推进"
    assert newborn.position == Vector2(50.0, 50.0), "位置也不该动"
