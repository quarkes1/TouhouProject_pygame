"""一次性动画：烘帧、播放、回收。

`bakeExpandingRing` 的**曲线**（缩放与透明度的推进）单独测，不碰像素——
验证「越放越大、越放越淡」本来得扫一张 500×500 的图，而曲线是纯算术。
"""

import pygame
import pytest

from touhou.core.vector2 import Vector2
from touhou.game.effectField import EffectField
from touhou.game.entities.effect import Effect, bakeExpandingRing, expandingRingParams


def solidSurface(size: int = 16) -> pygame.Surface:
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    surface.fill((255, 255, 255, 255))
    return surface


# —— 曲线 ——


def testRingParamsStartAtTheStartAndEndAtTheEnd():
    first = expandingRingParams(0, 5, 0.25, 1.40, 255, 60)
    last = expandingRingParams(4, 5, 0.25, 1.40, 255, 60)
    assert first == pytest.approx((0.25, 255))
    assert last == pytest.approx((1.40, 60))


def testRingParamsGrowAndFadeMonotonically():
    params = [expandingRingParams(i, 8, 0.2, 1.5, 255, 0) for i in range(8)]
    scales = [scale for scale, _ in params]
    alphas = [alpha for _, alpha in params]
    assert scales == sorted(scales) and scales[0] < scales[-1], "环要越放越大"
    assert alphas == sorted(alphas, reverse=True) and alphas[0] > alphas[-1], "要越放越淡"


def testRingParamsWithASingleFrameUseTheStartValues():
    """只烘一帧时取起始值——除零的边界，也是「长度为 1 的序列」该有的样子。"""
    assert expandingRingParams(0, 1, 0.25, 1.40, 255, 60) == pytest.approx((0.25, 255))


# —— 烘帧 ——


def testBakeProducesOneFramePerStepAndGrowsThem():
    frames = bakeExpandingRing(solidSurface(), 4, 0.5, 2.0, 255, 0)
    assert len(frames) == 4
    sizes = [frame.get_width() for frame in frames]
    assert sizes == sorted(sizes) and sizes[0] < sizes[-1]


def testBakeFadesTheAlphaOut():
    """淡出走 alpha 通道的乘法，不是 `set_alpha`。

    拿一张实心方块来测：像素的 alpha 直接读出乘完的结果，一眼看得出来。环本身
    中空，边角那片透明像素乘多少还是 0，测不出东西。
    """
    frames = bakeExpandingRing(solidSurface(), 3, 1.0, 1.0, 255, 0)
    assert frames[0].get_at((0, 0))[3] == 255
    assert frames[-1].get_at((0, 0))[3] == 0


def testBakeKeepsEveryFrameBigEnoughToDraw():
    """缩到极小也不能出现 0 尺寸的表面——pygame 对 0 尺寸不是处处都友好。"""
    frames = bakeExpandingRing(solidSurface(4), 3, 0.0, 0.1, 255, 0)
    assert all(frame.get_width() >= 1 and frame.get_height() >= 1 for frame in frames)


def testBakeHandlesTheRealAsset():
    """真素材（500×500 的环形冲击波）能烘出来，且末帧比首帧大得多。

    这条守的是「素材被换掉」：换成长条的帧序列、或者尺寸变了，烘出来的东西
    就不再是扩散的环了。
    """
    from touhou.core.paths import assetPath

    ring = pygame.image.load(str(assetPath("sprites", "effects", "player_death_effect.png")))
    frames = bakeExpandingRing(ring.convert_alpha(), 5, 0.25, 1.40, 255, 60)
    assert len(frames) == 5
    assert frames[-1].get_width() > 2 * frames[0].get_width()


# —— 播放 ——


def testEffectAdvancesOneFrameEveryFramesPerFrame():
    frames = tuple(solidSurface(8 + i) for i in range(3))
    effect = Effect(frames, Vector2(10, 20), framesPerFrame=2)

    assert effect.frameIndex == 0, "出生时停在第一帧"
    effect.update()
    assert effect.frameIndex == 0, "第一张要播满 2 帧"
    effect.update()
    assert effect.frameIndex == 1
    effect.update()
    assert effect.frameIndex == 1
    effect.update()
    assert effect.frameIndex == 2


def testEffectFinishesExactlyAfterItsLastFrame():
    frames = tuple(solidSurface() for _ in range(3))
    effect = Effect(frames, Vector2(0, 0), framesPerFrame=2)

    for tick in range(6):  # 3 张 × 每张 2 帧
        assert not effect.isFinished(), f"第 {tick + 1} 帧不该已经放完"
        effect.update()
    assert effect.isFinished(), "第 6 帧放完才结束"


def testEffectKeepsDrawingWithoutRunningOffTheEnd():
    """放完之后接着画也不该抛 IndexError。

    容器是在 update 之后才回收的，中间那一瞬间下标已经越界；`currentFrame`
    钳在上界内，坏掉的只会是「多画了一帧最后一帧」，而不是一个裸 IndexError。
    """
    frames = tuple(solidSurface(8 + i) for i in range(3))
    effect = Effect(frames, Vector2(0, 0))
    for _ in range(10):
        effect.update()
    assert effect.isFinished()
    assert effect.currentFrame() is frames[-1]


def testEffectCopiesThePositionInsteadOfTheReference():
    """存的是分量的拷贝，不是那个 `Vector2` 对象——理由同 `Bullet.reset`：
    存引用的话，自机一移动，已经放出去的冲击波会跟着跑。
    """
    where = Vector2(100, 200)
    effect = Effect((solidSurface(),), where)
    where.x = 999
    assert effect.position.x == 100


# —— 容器 ——


def testFieldSpawnsUpdatesAndRecycles():
    field = EffectField()
    frames = tuple(solidSurface() for _ in range(2))

    field.spawn(frames, Vector2(50, 60))
    assert len(field) == 1

    field.update()
    assert len(field) == 1, "还有一帧没播完"
    field.update()
    assert len(field) == 0, "放完就该摘掉，与它在哪无关"


def testFieldDrawsTheCurrentFrameCentered():
    """以**中心点**对齐画在位置上。

    20×20 的框放在 (50, 50)，覆盖的是 [40, 60)——所以 (39, 50) 与 (60, 50)
    必须都是空的。按左上角画（blit 的原生语义）覆盖的会是 [50, 70)，
    (60, 50) 就有像素了，这条会红。
    """
    canvas = pygame.Surface((100, 100), pygame.SRCALPHA)
    field = EffectField()
    big = pygame.Surface((20, 20), pygame.SRCALPHA)
    big.fill((255, 0, 0, 255))
    field.spawn((big,), Vector2(50, 50))

    field.draw(canvas)

    assert canvas.get_at((50, 50))[:3] == (255, 0, 0), "中心该被画上"
    assert canvas.get_at((40, 50))[3] == 255, "左边缘在 40，属于这一帧"
    assert canvas.get_at((59, 50))[3] == 255, "右边缘在 59，属于这一帧"
    for outside in ((39, 50), (60, 50), (50, 39), (50, 60)):
        assert canvas.get_at(outside)[3] == 0, f"{outside} 落在一帧之外，不该有像素"
