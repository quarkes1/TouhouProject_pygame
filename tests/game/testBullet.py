"""子弹类：状态、运动、渲染分支与池复用契约。

这个文件里最要紧的两条是「角度锁」和「reset 设满所有字段」——它们守的都是
**不会崩、只会让画面悄悄不对**的问题：角度符号写反时所有定向弹左右镜像，
reset 漏字段时新弹继承上一发的速度。缓存键层面的断言在这两种情况下全绿。
"""

import pygame
import pytest

from touhou.core.collider import Collider
from touhou.core.spriteSheet import SpriteSheet
from touhou.core.vector2 import Vector2
from touhou.game.entities.bullet import Bullet, BulletSpec


@pytest.fixture
def singleFrameSheet() -> SpriteSheet:
    """16×16 单帧，帧顶中央有一块 4×4 不透明标记。

    必须放可见像素：全透明帧旋转之后还是全透明，各角度字节级完全相同，
    任何方向断言都测不出东西（同 testPlayerMovement 里那张标记贴图的理由）。
    """
    surface = pygame.Surface((16, 16), pygame.SRCALPHA)
    surface.fill((255, 0, 0, 255), pygame.Rect(6, 0, 4, 4))
    return SpriteSheet(surface, 16, 16)


@pytest.fixture
def fourFrameSheet() -> SpriteSheet:
    """4 帧 × 16×16，每帧一种颜色，便于分辨当前是第几帧。"""
    surface = pygame.Surface((16 * 4, 16), pygame.SRCALPHA)
    for index in range(4):
        surface.fill((index * 60, 0, 0, 255), pygame.Rect(index * 16, 0, 16, 16))
    return SpriteSheet(surface, 16, 16)


@pytest.fixture
def spec(singleFrameSheet) -> BulletSpec:
    return BulletSpec(spriteSheet=singleFrameSheet, radius=3.0)


def markerFarthestSide(frame: pygame.Surface) -> str:
    """标记块跑到贴图的哪一侧。用于把角度方向钉死成像素事实。"""
    opaque = [
        (x, y)
        for y in range(frame.get_height())
        for x in range(frame.get_width())
        if frame.get_at((x, y))[3] > 0
    ]
    assert opaque, "帧里没有任何不透明像素，方向无从判断"

    centroidX = sum(x for x, _ in opaque) / len(opaque)
    centroidY = sum(y for _, y in opaque) / len(opaque)
    centerX = frame.get_width() / 2
    centerY = frame.get_height() / 2

    horizontal = centroidX - centerX
    vertical = centroidY - centerY
    if abs(horizontal) > abs(vertical):
        return "右" if horizontal > 0 else "左"
    return "下" if vertical > 0 else "上"


# —— 池化契约 ——


def testBulletHasNoInstanceDict(spec):
    """__slots__ 是真的在生效。

    实测：子类只要漏写 __slots__，实例就会**静默**重新长出 __dict__，
    池化想省的那笔开销无声无息地回来，不会有任何报错。
    """
    bullet = Bullet(spec, Vector2(10, 10), 0, 1)
    assert not hasattr(bullet, "__dict__")


def testSlotsDoNotOverlapBaseClassSlots():
    """重复声明基类已有的 slot 会被静默接受，并让那个字段占两份空间。

    所以「顺手把 position 也加进 Bullet.__slots__ 里更清楚」是个陷阱，
    这条把它挡在门外。
    """
    assert set(Bullet.__slots__).isdisjoint(Collider.__slots__)


def testResetSetsEveryField(spec, fourFrameSheet):
    """reset 之后没有任何字段残留上一发的状态。

    池化最经典的 bug：漏设一个字段，复用的弹就带着上一发的速度或贴图飞出去。
    mypy 给不了这个保证——它不会告诉你 reset 忘了某个 slot。
    """
    otherSheet = fourFrameSheet
    otherSpec = BulletSpec(spriteSheet=otherSheet, radius=9.0, rotatesToVelocity=False)

    bullet = Bullet(spec, Vector2(10, 10), 0, 5)
    for _ in range(30):  # 让动画与 ageFrames 都走起来
        bullet.update()

    bullet.reset(otherSpec, Vector2(200, 300), 180, 2)

    assert bullet.position == Vector2(200, 300)
    assert bullet.radius == 9.0
    assert bullet.angleDeg == 180
    assert bullet.spriteSheet is otherSheet
    assert bullet.rotatesToVelocity is False
    assert bullet.velocity == Vector2.fromDeg(180, 2)
    assert bullet.animationFrame == 0
    assert bullet.animationTimer == 0.0
    assert bullet.ageFrames == 0


def testResetDoesNotAliasCallerPosition(spec):
    """reset 只拷分量，不存调用方传进来的那个 Vector2。

    实测过：直接存引用的话，敌人一移动，所有引用它位置的子弹会一起跳。
    弹幕模板必然写 spawn(spec, enemy.position, ...)，所以这条必须守住。
    """
    enemyPosition = Vector2(100.0, 50.0)
    bullet = Bullet(spec, enemyPosition, 0, 1)

    enemyPosition.x += 40.0
    enemyPosition.y += 40.0

    assert bullet.position == Vector2(100.0, 50.0)


# —— 运动 ——


def testVelocityComesFromAngleAndSpeed(spec):
    """速度恒等于 fromDeg(angleDeg, speed)——角度与速度是同一个来源。"""
    for angleDeg in (0, 45, 90, 137, 180, 270, 359):
        bullet = Bullet(spec, Vector2(0, 0), angleDeg, 3.0)
        assert bullet.velocity == Vector2.fromDeg(angleDeg, 3.0)


def testAngleAgreesWithDirectionOfTravel(spec):
    """存下来的角度必须与真实飞行方向一致，否则弹幕会「飞对了但朝向错」。"""
    for angleDeg in (0, 90, 180, 270, 33):
        bullet = Bullet(spec, Vector2(0, 0), angleDeg, 4.0)
        assert Vector2.fromDeg(bullet.angleDeg, 1.0).toTuple() == pytest.approx(
            bullet.velocity.normalize().toTuple()
        )


def testUpdateMovesByVelocityPerFrame(spec):
    """速度单位是**像素/帧**。

    关卡数据里写的是像素/秒（150/200/250），换算由加载器负责。加载器若忘了除
    60，子弹会三帧穿过整个屏幕——这条把错误锁在加载器那一侧，不让它传染到引擎。
    """
    bullet = Bullet(spec, Vector2(200.0, 300.0), 0, 5.0)

    bullet.update()
    assert bullet.position.y == pytest.approx(295.0), "朝 0°（正上）一帧应移动 5px"

    for _ in range(2):
        bullet.update()
    assert bullet.position.y == pytest.approx(285.0), "累计三步应移动 15px，而不是按秒算的 15/60"


def testUpdateAdvancesAgeFrames(spec):
    bullet = Bullet(spec, Vector2(0, 0), 0, 1)
    for expected in range(1, 6):
        bullet.update()
        assert bullet.ageFrames == expected


# —— 渲染分支 ——


def testRotatingBulletUsesPreRotatedCache(spec, singleFrameSheet):
    """随速度旋转的弹走 getRotated，且命中的是缓存里的同一个对象。"""
    bullet = Bullet(spec, Vector2(0, 0), 30, 1)
    assert bullet.currentFrame() is singleFrameSheet.getRotated(0, 30)


def testNonRotatingBulletUsesOriginalFrame(singleFrameSheet):
    """圆球弹走 getFrame。

    实测 getRotated(0, 0) 与 getFrame(0) **不是**同一个对象——0° 旋转也会另存
    一份。所以给圆球弹关掉旋转不只是省 CPU，也是不白占 360 个缓存条目。
    """
    spec = BulletSpec(spriteSheet=singleFrameSheet, radius=3.0, rotatesToVelocity=False)
    bullet = Bullet(spec, Vector2(0, 0), 30, 1)

    assert bullet.currentFrame() is singleFrameSheet.getFrame(0)


def testAngleIsStoredNotDerivedFromVelocity(spec, singleFrameSheet):
    """零速弹的渲染方向必须仍是它被生成时的角度。

    实测：Vector2.fromDeg(θ, 0) 对 θ = 0/45/90 全都给出 (0.0, -0.0)，反推角度
    一律是 0.0。也就是说「从速度反推角度」会把这三个方向**全塌成正上**，
    停下再转向的弹型会画错方向。这条守住 angleDeg 是存下来的。
    """
    bullet = Bullet(spec, Vector2(0, 0), 90, 0)

    assert pygame.image.tobytes(bullet.currentFrame(), "RGBA") == pygame.image.tobytes(
        singleFrameSheet.getRotated(0, 90), "RGBA"
    )
    assert pygame.image.tobytes(bullet.currentFrame(), "RGBA") != pygame.image.tobytes(
        singleFrameSheet.getRotated(0, 0), "RGBA"
    ), "反推角度会让 90° 塌成 0°，那样这两者会相同"


def testMarkerTurnsClockwiseWithAngle(spec):
    """角度锁：0° 朝上、90° 朝右、180° 朝下、270° 朝左。

    getRotated 内部已经有一处取负（spriteSheet.py），外面再取一次负就正好转反，
    而那时所有缓存键层面的断言依然全绿。只有像素能锁住方向。
    """
    expected = {0: "上", 90: "右", 180: "下", 270: "左"}
    for angleDeg, side in expected.items():
        bullet = Bullet(spec, Vector2(0, 0), angleDeg, 1)
        assert markerFarthestSide(bullet.currentFrame()) == side, f"{angleDeg}° 应当朝{side}"


# —— 判定半径 ——


def testRadiusComesFromSpecNotSprite(spec):
    """判定半径来自 spec，不是从贴图尺寸推出来的。

    贴图 16×16 若被当成半径 8，判定圈会比设定值大出一倍多——游戏照跑，
    只是变得不公平，属于调试期才会发现的那类 bug。
    """
    bullet = Bullet(spec, Vector2(0, 0), 0, 1)  # spec 里 radius = 3.0
    target = Collider(radius=1.0, position=Vector2(0, 5))  # 距离 5 > 3 + 1

    assert not bullet.checkCollision(target)
    assert bullet.checkCollision(Collider(radius=1.0, position=Vector2(0, 3)))


# —— 动画 ——


def testSingleFrameSheetDoesNotAnimate(spec):
    """单帧贴图（现有的四张敌弹贴图都是）动画自然空转。"""
    bullet = Bullet(spec, Vector2(0, 0), 0, 1)
    for _ in range(100):
        bullet.update()
        assert bullet.animationFrame == 0


def testAnimationCyclesThroughAllFramesAndWraps(fourFrameSheet):
    """多帧贴图会推进，并且取模回绕——不回绕就会一路涨到 IndexError。"""
    spec = BulletSpec(spriteSheet=fourFrameSheet, radius=3.0)
    bullet = Bullet(spec, Vector2(0, 0), 0, 0)

    observed = set()
    for _ in range(500):
        bullet.update()
        observed.add(bullet.animationFrame)

    assert observed == {0, 1, 2, 3}, f"没有遍历全部 4 帧，只见到 {sorted(observed)}"


def testAnimationFrameStaysInRange(fourFrameSheet):
    """帧号恒在范围内。越界时 getFrame 抛的是裸 IndexError，离错误很远。"""
    spec = BulletSpec(spriteSheet=fourFrameSheet, radius=3.0)
    bullet = Bullet(spec, Vector2(0, 0), 0, 0)
    for _ in range(1000):
        bullet.update()
        assert 0 <= bullet.animationFrame < fourFrameSheet.frameCount
