"""BOSS 血条。

与 `testHud.py` 同一套路：造几个数画一帧、比像素。血条只收裸值，所以这里
不需要 BOSS 对象。

另有一条**字形检查**：BOSS 的名字来自关卡数据、是数据驱动的文字，静态检查
覆盖不到它——「小悪魔」的「悪」就是这么发现的（简体的「恶」这个字体没有）。
"""

import pygame

from touhou import constants
from touhou.core.paths import assetPath
from touhou.game.levelData import loadLevel
from touhou.ui import bossBar, hud

OUTSIDE_COLOR = (255, 0, 255)


def freshCanvas() -> pygame.Surface:
    canvas = pygame.Surface((constants.LOGICAL_WIDTH, constants.LOGICAL_HEIGHT))
    canvas.fill(OUTSIDE_COLOR)
    return canvas


def renderBar(
    name: str = "小悪魔", hp: int = 400, maxHp: int = 400, segments: int = 1, segmentIndex: int = 0
) -> pygame.Surface:
    canvas = freshCanvas()
    bossBar.drawBossBar(canvas, name, hp, maxHp, segments, segmentIndex)
    return canvas


def barBytes(canvas: pygame.Surface) -> bytes:
    return pygame.image.tobytes(canvas.subsurface(bossBar.barRect()), "RGB")


def playfieldBytes(canvas: pygame.Surface) -> bytes:
    playfield = pygame.Rect(
        constants.PLAYFIELD_X,
        constants.PLAYFIELD_Y,
        constants.PLAYFIELD_WIDTH,
        constants.PLAYFIELD_HEIGHT,
    )
    return pygame.image.tobytes(canvas.subsurface(playfield), "RGB")


# —— 血条本身 ——


def testBarShowsTheHealthFraction():
    """满血与半血的像素必须不同——血条要真的按比例画。"""
    assert barBytes(renderBar(hp=400)) != barBytes(renderBar(hp=200))


def testBarIsFilledFromTheLeft():
    """血量从左往右填：满血时最左边和最右边都是亮的，半血时只有左边亮。"""
    full = renderBar(hp=400)
    half = renderBar(hp=200)
    rect = bossBar.barRect()
    left = (rect.x + 2, rect.centery)
    right = (rect.right - 3, rect.centery)

    assert full.get_at(left)[:3] == bossBar.FILL_COLOR
    assert full.get_at(right)[:3] == bossBar.FILL_COLOR
    assert half.get_at(left)[:3] == bossBar.FILL_COLOR
    assert half.get_at(right)[:3] != bossBar.FILL_COLOR


def testBarStaysInsideThePlayfield():
    """血条只画游戏区里那一条：画到外面去会渗进右侧 HUD 面板或下沿边带。"""
    canvas = renderBar()
    before = playfieldBytes(freshCanvas())
    painted = playfieldBytes(canvas)
    assert painted != before, "血条该画在游戏区里"

    outside = pygame.Rect(
        constants.PLAYFIELD_X,
        constants.PLAYFIELD_Y + constants.PLAYFIELD_HEIGHT,
        constants.PLAYFIELD_WIDTH,
        constants.LOGICAL_HEIGHT - constants.PLAYFIELD_Y - constants.PLAYFIELD_HEIGHT,
    )
    band = pygame.image.tobytes(freshCanvas().subsurface(outside), "RGB")
    assert pygame.image.tobytes(canvas.subsurface(outside), "RGB") == band, "渗进下沿边带了"


def testNoHealthMeansNothingIsDrawn():
    """`maxHp` 为 0 时**什么都不画**。

    BOSS 的血量是脚本第一次 `runPhase` 时才给的，那一帧之前没有「本段血量」
    这回事——画一条空槽比不画更让人困惑。
    """
    canvas = renderBar(hp=0, maxHp=0)
    assert pygame.image.tobytes(canvas, "RGB") == pygame.image.tobytes(freshCanvas(), "RGB")


def testPipsShowTheSegmentCount():
    """分段格子数 = segments：多一段就多一个格子。

    格子画在血条正下方，所以比那一行的像素。
    """

    def pipRow(segments: int) -> bytes:
        canvas = renderBar(segments=segments)
        rect = bossBar.barRect()
        row = pygame.Rect(rect.x, bossBar.PIP_TOP, rect.width, 4)
        return pygame.image.tobytes(canvas.subsurface(row), "RGB")

    assert pipRow(1) != pipRow(2), "段数变了格子却没变"
    assert pipRow(reader := 2) == pipRow(2), f"{reader} 段画了两遍应当一样"


def testPipsMarkTheCurrentSegment():
    """已经打到第几段要看得出：段号变了格子就变。"""
    assert renderBar(segments=3, segmentIndex=0) != renderBar(segments=3, segmentIndex=1)


# —— 名字 ——


def testNameIsDrawn():
    assert pygame.image.tobytes(renderBar(name="小悪魔"), "RGB") != pygame.image.tobytes(
        renderBar(name=""),
        "RGB",
    )


def testBossNamesInTheLevelHaveGlyphs():
    """关卡里 BOSS 的名字，这个字体得真的写得出来。

    **数据驱动的文字没法做静态检查**：名字写在 JSON 里，改一个字不会让任何
    代码报错，画面上只会多一个缺字方框。实测「小悪魔」的简写「小恶魔」就踩了
    这个坑——DFPPOPCorn-W12 里没有「恶」（有日文的「悪」）。

    测试要通过 `loadLevel` 拿真实数据，所以这里也顺带守住了「改数据别改坏」。
    """
    pygame.display.set_mode((1, 1))  # loadLevel 要加载贴图，需要一个显示表面
    level = loadLevel(assetPath("levels", "level_1.json"))

    assert level.bosses, "这一关该有 BOSS，否则这条测试什么也没测"
    for boss in level.bosses:
        for char in boss.name:
            assert hud.hasGlyph(char), (
                f"BOSS「{boss.name}」里的 U+{ord(char):04X} 这个字体没有字形，会画成方框"
            )
