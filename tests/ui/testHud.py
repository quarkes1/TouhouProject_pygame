"""HUD。

HUD 只收裸值（残机、炸弹、火力），所以造几个数就能测，不需要自机——
这正是当初把它和 `game/` 隔开的目的。

**这里大半在测「画出来了没有」**，而这类断言很容易写成「函数被调用了」那种
自我实现的空壳。所以用像素：同一个 HUD 用不同的值画两遍，字节必须不同。
值没被画出来的话，两遍是一模一样的。
"""

import pygame
import pytest

from touhou import constants
from touhou.ui import hud

# 与面板色不同的底色。**必须不同**：底色若恰好等于面板色，
# 「什么都没画」与「画了面板」在采样时区分不出来——而那正是 HUD 没接线时的样子。
OUTSIDE_COLOR = (255, 0, 255)


def hudRect() -> pygame.Rect:
    return pygame.Rect(hud.HUD_X, 0, hud.HUD_WIDTH, constants.LOGICAL_HEIGHT)


def playfieldRect() -> pygame.Rect:
    return pygame.Rect(
        constants.PLAYFIELD_X,
        constants.PLAYFIELD_Y,
        constants.PLAYFIELD_WIDTH,
        constants.PLAYFIELD_HEIGHT,
    )


def freshCanvas() -> pygame.Surface:
    canvas = pygame.Surface((constants.LOGICAL_WIDTH, constants.LOGICAL_HEIGHT))
    canvas.fill(OUTSIDE_COLOR)
    return canvas


def renderHud(lives: int = 3, bombs: int = 3, power: float = 2.40) -> pygame.Surface:
    canvas = freshCanvas()
    hud.drawHud(canvas, lives, bombs, power)
    return canvas


def hudBytes(canvas: pygame.Surface) -> bytes:
    return pygame.image.tobytes(canvas.subsurface(hudRect()), "RGB")


def starRowBytes(canvas: pygame.Surface, row: int = hud.ROW_LIVES) -> bytes:
    """残机那一行星所在的一条，从星的起点一直量到画布右边缘。"""
    x, y = hud.rowValuePosition(row)
    rect = pygame.Rect(x, y, constants.LOGICAL_WIDTH - x, hud.STAR_SPACING)
    return pygame.image.tobytes(canvas.subsurface(rect), "RGB")


# —— 版式与范围 ——


def testHudFillsItsWholeStrip():
    """整条 HUD 都被刷上底色，不留上一帧的内容。

    用掩膜数「还等于底色的像素」而不是逐个 get_at：那是 224×480 次 Python 调用，
    而 from_threshold 在 C 里做同一件事。
    """
    strip = renderHud().subsurface(hudRect()).copy()
    leftover = pygame.mask.from_threshold(strip, OUTSIDE_COLOR, (1, 1, 1, 255))
    assert leftover.count() == 0, f"HUD 条里有 {leftover.count()} 个像素没被刷到"


def testHudDoesNotTouchThePlayfield():
    """HUD 只画自己那条。画到游戏区上就是压在画面上、且永远擦不掉的脏点。

    残机给 99：星是往右画的，多到放不下时最容易越界。
    """
    untouched = pygame.image.tobytes(freshCanvas().subsurface(playfieldRect()), "RGB")
    painted = pygame.image.tobytes(
        renderHud(lives=99, bombs=99, power=4.00).subsurface(playfieldRect()), "RGB"
    )
    assert painted == untouched, "游戏区被 HUD 动过了"


# —— 三个值都真的画出来了 ——


@pytest.mark.parametrize("changed", [{"lives": 4}, {"bombs": 2}, {"power": 1.00}])
def testEachValueChangesTheHud(changed):
    """残机、炸弹、火力各改一个，画出来的字节必须跟着变。

    三个值共用一条断言：值没被画出来的话，改它不会改变任何像素。
    """
    assert hudBytes(renderHud(**changed)) != hudBytes(renderHud())


def testPowerIsShownWithTwoDecimals():
    """火力的两位小数缺一不可：档位阈值是 1.00/2.00 这类整数，
    少一位就看不出「还差多少到下一档」。"""
    assert hudBytes(renderHud(power=2.40)) != hudBytes(renderHud(power=2.44))
    assert hudBytes(renderHud(power=2.40)) == hudBytes(renderHud(power=2.399))


def testStarOverflowIsClamped():
    """残机多到一行放不下时，多出来的星不再画。

    星是往右画的，画出去的会跑出画布——白做无用功，而且 HUD 的宽度或位置
    一旦变动就会变成真的脏点。

    只比**星那一行**：标签上的数字不设上限（那正是「星放不下时还读得出准确值」
    的保证），所以两边的标签本来就不同，整条比会永远不等。
    """
    assert starRowBytes(renderHud(lives=99)) == starRowBytes(renderHud(lives=hud.MAX_STARS))


# —— 字体 ——


def testEveryLabelCharacterHasAGlyph():
    """HUD 上每一个字都真有字形。

    **逐字比对，不能只比整词**：缺字时 pygame 画的是一个统一的方框，于是
    「炸弹」会渲染成「炸」加方框——与「残机」「火力」仍然互不相同，
    「三个词两两不等」那种断言照样全过。实测 DFPPOPCorn-W12 **就缺「弹」**，
    这条测试正是为它写的时候发现的。
    """
    for label in (hud.LABEL_LIVES, hud.LABEL_BOMBS, hud.LABEL_POWER):
        for char in label:
            assert hud.hasGlyph(char), (
                f"标签「{label}」里的 U+{ord(char):04X} 在这个字体里没有字形（会画成方框）"
            )


def testFontIsLoadedOnce():
    """字体只加载一次（2.8MB 的 ttf，每帧读一遍会明显掉帧）。"""
    assert hud.hudFont() is hud.hudFont()
    assert hud.starIcon() is hud.starIcon()


def testReleaseCachesDropsEverything():
    """`releaseCaches` 之后必须重新加载——它是 pygame.quit() 前的那一步。"""
    font = hud.hudFont()
    star = hud.starIcon()

    hud.releaseCaches()

    assert hud.hudFont() is not font
    assert hud.starIcon() is not star
