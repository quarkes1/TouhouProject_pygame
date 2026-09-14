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
