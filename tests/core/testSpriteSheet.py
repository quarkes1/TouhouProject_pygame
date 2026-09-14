"""精灵动画表与按角度预旋转缓存。

缓存是弹幕性能的关键。参考项目在 Bullet.__init__ 里对 sprite sheet 的
每一帧都调用 pygame.transform.rotate——子弹生成高峰期每秒数百发、每发
旋转好几帧，这一项就能吃掉全部帧预算。
"""

import pygame
import pytest

from touhou.core import paths
from touhou.core.spriteSheet import SpriteSheet


@pytest.fixture
def sheet() -> SpriteSheet:
    """6 帧的测试用动画表（与 fairy_0.png 同尺寸同分帧）。"""
    surface = pygame.Surface((24 * 6, 19), pygame.SRCALPHA)
    return SpriteSheet(surface, 24, 19)


# —— 分帧 ——


def testFrameCountIsDerivedFromSurfaceWidth(sheet):
    assert sheet.frameCount == 6


def testGetFrameReturnsSurfaceOfRequestedSize(sheet):
    frame = sheet.getFrame(0)
    assert frame.get_width() == 24
    assert frame.get_height() == 19


def testGetFrameReturnsDistinctObjects(sheet):
    assert sheet.getFrame(0) is not sheet.getFrame(1)


def testMultiRowSheetIsSplitRowMajor():
    """多行动画表按行优先切分——先切完第一行再切第二行。

    给每个格子填不同的颜色，逐帧验证取到的是哪一格。只断言帧数为 6
    是不够的：列优先的切法同样会得到 6 帧，那样这个测试名就在撒谎。
    """
    surface = pygame.Surface((10 * 3, 20 * 2), pygame.SRCALPHA)
    colours = [
        (255, 0, 0, 255),
        (0, 255, 0, 255),
        (0, 0, 255, 255),
        (255, 255, 0, 255),
        (255, 0, 255, 255),
        (0, 255, 255, 255),
    ]
    for index, colour in enumerate(colours):
        column, row = index % 3, index // 3
        surface.fill(colour, pygame.Rect(column * 10, row * 20, 10, 20))

    multiRow = SpriteSheet(surface, 10, 20)

    assert multiRow.frameCount == 6
    for index, colour in enumerate(colours):
        assert multiRow.getFrame(index).get_at((5, 10)) == colour, (
            f"第 {index} 帧取到的不是预期的那一格，分帧顺序错了"
        )


def testFromFileLoadsRealAsset():
    real = SpriteSheet.fromFile(paths.assetPath("sprites", "entities", "fairy_0.png"), 24, 19)
    assert real.frameCount == 6
    assert real.getFrame(0).get_width() == 24


def testRejectsSurfaceSmallerThanOneFrame():
    """表面小到连一帧都切不出时必须立刻报错。

    不守卫的话 frameCount 会是 0，然后 player.py 的 advanceAnimation 里
    % frameCount 抛 ZeroDivisionError、getFrame 抛 IndexError——都远离
    真正的错误现场。Plan B 的加载器从 JSON 读帧尺寸，在构造时拦住比在
    动画循环里炸掉好查得多。
    """
    with pytest.raises(ValueError):
        SpriteSheet(pygame.Surface((10, 100), pygame.SRCALPHA), 24, 19)


def testRejectsNonPositiveFrameSize():
    with pytest.raises(ValueError):
        SpriteSheet(pygame.Surface((24, 19), pygame.SRCALPHA), 0, 19)


# —— 旋转缓存（性能关键路径）——


def testGetRotatedReturnsCachedObjectOnSecondCall(sheet):
    """第二次取同一角度必须返回同一个对象，否则说明缓存没生效。"""
    first = sheet.getRotated(0, 45)
    second = sheet.getRotated(0, 45)
    assert first is second


def testGetRotatedNormalizesAngleModuloThreeSixty(sheet):
    """370° 与 10° 是同一个方向，应该命中同一条缓存。"""
    assert sheet.getRotated(0, 370) is sheet.getRotated(0, 10)


def testGetRotatedHandlesNegativeAngle(sheet):
    assert sheet.getRotated(0, -10) is sheet.getRotated(0, 350)


def testGetRotatedDistinguishesDifferentAngles(sheet):
    assert sheet.getRotated(0, 0) is not sheet.getRotated(0, 90)


def testGetRotatedDistinguishesDifferentFrames(sheet):
    assert sheet.getRotated(0, 45) is not sheet.getRotated(1, 45)


def testCacheSizeStaysBounded(sheet):
    """缓存不能无限增长——角度归一到整数度后最多 360 个键。"""
    for angle in range(720):
        sheet.getRotated(0, angle)
    assert len(sheet.rotatedCache) == 360


def testGetRotatedPreservesApparentSize(sheet):
    """旋转后的图应该能容纳原图的对角线，不能把像素切掉。"""
    rotated = sheet.getRotated(0, 45)
    assert rotated.get_width() >= 24
    assert rotated.get_height() >= 19


def testGetRotatedFollowsClockwiseAngleConvention():
    """角度约定的方向锁：0° 正上、顺时针增大，标记块落在 上/右/下/左。

    在透明帧顶部中央放一个标记块，0/90/180/270° 旋转后标记必须依次落在
    上/右/下/左。Plan B 的自机狙、扇形、环形弹幕全部渲染自这个函数，
    内部旋转方向的负号一旦被去掉，所有定向图案会整体左右镜像——而纯缓存
    测试（只查键、不查像素）对此毫无反应。

    旋转后的外接矩形会变大，所以一律以返回图自己的中心为基准判断。
    """
    frame = pygame.Surface((16, 16), pygame.SRCALPHA)
    marker = (255, 0, 0, 255)
    frame.fill(marker, pygame.Rect(6, 0, 4, 4))  # 顶部中央的标记块
    markedSheet = SpriteSheet(frame, 16, 16)

    def markerPixels(surface: pygame.Surface) -> list[tuple[int, int]]:
        return [
            (x, y)
            for y in range(surface.get_height())
            for x in range(surface.get_width())
            if surface.get_at((x, y)) == marker
        ]

    # 方向 (dx, dy)：0° 上、90° 右、180° 下、270° 左
    for angle, (dx, dy) in ((0, (0, -1)), (90, (1, 0)), (180, (0, 1)), (270, (-1, 0))):
        rotated = markedSheet.getRotated(0, angle)
        centre = (rotated.get_width() // 2, rotated.get_height() // 2)
        pixels = markerPixels(rotated)
        assert pixels, f"{angle}° 旋转后找不到标记块"
        for x, y in pixels:
            # 四个角度恰好都是纯轴向，只检查该轴即可，另一个轴要求会误伤
            axisDelta = x - centre[0] if dx else y - centre[1]
            assert axisDelta * (dx or dy) > 0, f"{angle}° 时标记块不在预期一侧（{(dx, dy)}）"
