"""HUD：残机、炸弹、火力。

它填的是游戏区右侧那条 224px 的深色带（`drawHudPlaceholder` 曾经的占位区）。

**只接收裸值**：`drawHud(canvas, lives, bombs, power)` 收的是三个数，
不是玩家对象。这样它既能脱离自机单独测试（造三个数就能画一帧），
也不会因为自机将来多出别的状态而改动——HUD 只画它认识的那三样。

不做分数、不做擦弹数、不做符卡名：那些系统本轮还不存在，
画一个永远是 0 的计数器只会让人以为它坏了。
"""

# 为注解开启延迟求值，理由见 vector2.py 的同类注释
from __future__ import annotations

from functools import cache

import pygame

from touhou import constants
from touhou.core.paths import assetPath

FONT_PATH_PARTS = ("fonts", "DFPPOPCorn-W12.ttf")
STAR_PATH_PARTS = ("sprites", "projectiles_and_items", "star_item.png")

# 只用一个字号：字再大就得换行了，而 HUD 只有 224px 宽。
FONT_SIZE = 20

# —— 版式 ——
# 三行自上而下：残机、炸弹、火力。每行是「标签 + 下一行的值」，
# 与原作右侧面板的排布一致。
HUD_X = constants.PLAYFIELD_X + constants.PLAYFIELD_WIDTH
HUD_WIDTH = constants.LOGICAL_WIDTH - HUD_X
MARGIN_X = 16
FIRST_ROW_Y = 36
ROW_HEIGHT = 72
VALUE_GAP_Y = 26

ROW_LIVES = 0
ROW_BOMBS = 1
ROW_POWER = 2

# 星的间距比星本身（16px）大一点，免得连成一片
STAR_SPACING = 20

# 一行放得下的星数。**必须钳制**：星是往右画的，越过 HUD 右边界的部分会压在
# 游戏区上（HUD 在游戏区之后绘制，所以是 HUD 盖住游戏区，反着画就是脏点）。
# 标签上的数字不受这个上限影响，再多的残机也读得出准确值。
MAX_STARS = (HUD_WIDTH - 2 * MARGIN_X) // STAR_SPACING

# —— 配色 ——
# HUD 区压暗，与游戏区分开；文字用暖白，火力值用魔理沙的粉色做强调。
PANEL_COLOR = (16, 16, 24)
LABEL_COLOR = (168, 176, 200)
VALUE_COLOR = (255, 255, 255)
POWER_COLOR = (255, 144, 176)

# 三个标签都受字体的字形限制，改之前先看这里。
#
# **DFPPOPCorn-W12 里没有「弹」（U+5F39）**，实测「炸弹」会渲染成「炸」加一个
# 缺字方框。所以炸弹那一行用玩家惯用的单字「雷」，而不是「炸弹」。
# 缺字时 pygame 画的是一个统一的方框，肉眼一眼能看出坏掉，但代码看不出来——
# tests/ui/testHud.py 里有一条逐字比对字形指纹的测试守着这件事，
# 换标签时它会红，别把它删了。
LABEL_LIVES = "残机"
LABEL_BOMBS = "雷"
LABEL_POWER = "火力"


@cache
def hudFont() -> pygame.font.Font:
    """HUD 字体，全进程只加载一次。

    DFPPOPCorn-W12.ttf 有 2.8MB，每帧 Font() 一次是实打实的开销。
    `cache` 的 key 是空元组，等于一个模块级单例，只是不必手写 global。
    """
    return pygame.font.Font(str(assetPath(*FONT_PATH_PARTS)), FONT_SIZE)


@cache
def starIcon() -> pygame.Surface:
    """残机与炸弹的星形图标（16×16），只加载一次。"""
    return pygame.image.load(str(assetPath(*STAR_PATH_PARTS))).convert_alpha()


def hasGlyph(char: str) -> bool:
    """这个字体里有没有这个字。

    **缺字时 pygame 不报错、也不返回空**——它画一个统一的方框。所以「字体缺字」
    这件事在代码里完全看不出来，只有肉眼盯着画面才发现得了（「炸弹」曾经渲染成
    「炸」加一个方框，就是因为 DFPPOPCorn-W12 里没有「弹」）。

    判据是**私用区**（U+E000 起，保证没有字形）的渲染结果：所有缺字画的都是同一个
    方框，字节级相同。测试拿它守所有的界面文字；将来要做「缺字替换成别的词」
    也可以用它。

    一次只判一个字。整串判要逐字来——`render("炸X")` 与 `render("炸Y")` 本来就
    不同，哪怕 X 与 Y 都是方框。
    """
    signature = _glyphSignature(char)
    return all(signature != _glyphSignature(chr(0xE000 + offset)) for offset in range(4))


def _glyphSignature(text: str) -> bytes:
    return pygame.image.tobytes(hudFont().render(text, True, LABEL_COLOR), "RGBA")


def releaseCaches() -> None:
    """丢掉字体与图标。**`pygame.quit()` 之前必须调用。**

    字体对象绑在 font 模块的初始化状态上，quit 之后再用它渲染会抛
    `Invalid font (font module quit since font created)`。缓存恰恰让这个
    失效的对象活过了 quit——不缓存的话每次渲染都会新建一个，反而看不出来。
    所以清理是缓存的对价，写在这里而不是让 main 去猜该清什么。
    """
    hudFont.cache_clear()
    starIcon.cache_clear()


def rowTop(row: int) -> int:
    """第 row 行的标签纵坐标。"""
    return FIRST_ROW_Y + row * ROW_HEIGHT


def rowLabelPosition(row: int) -> tuple[int, int]:
    return (HUD_X + MARGIN_X, rowTop(row))


def rowValuePosition(row: int) -> tuple[int, int]:
    return (HUD_X + MARGIN_X, rowTop(row) + VALUE_GAP_Y)


def drawText(
    canvas: pygame.Surface, text: str, position: tuple[int, int], color: tuple[int, int, int]
) -> None:
    """在左上角对齐处画一行字。

    开抗锯齿（第二个参数 True）：字号小，不抗锯齿的字边缘很难看。
    """
    canvas.blit(hudFont().render(text, True, color), position)


def drawHud(canvas: pygame.Surface, lives: int, bombs: int, power: float) -> None:
    """把整个 HUD 条画出来。

    先整条刷底色，再逐行画字——刷底色同时抹掉上一帧的内容，
    所以 HUD 不需要每帧被别处擦干净。
    """
    canvas.fill(PANEL_COLOR, (HUD_X, 0, HUD_WIDTH, constants.LOGICAL_HEIGHT))

    drawCountRow(canvas, ROW_LIVES, LABEL_LIVES, lives)
    drawCountRow(canvas, ROW_BOMBS, LABEL_BOMBS, bombs)

    drawText(canvas, LABEL_POWER, rowLabelPosition(ROW_POWER), LABEL_COLOR)
    # 两位小数：火力的档位阈值是 1.00 / 2.00 这类整数，少一位就看不出
    # 「还差多少到下一档」，而这是玩家最想知道的事。
    drawText(canvas, f"{power:.2f}", rowValuePosition(ROW_POWER), POWER_COLOR)


def drawCountRow(canvas: pygame.Surface, row: int, label: str, count: int) -> None:
    """画一行「标签 + 数字」加一排星。

    数字与星**都要**：星是给眼睛的（一眼看出还剩几条命），
    数字是给准确值的（星数超过一行放得下的时候，只有数字还准）。
    """
    drawText(canvas, f"{label} {count}", rowLabelPosition(row), LABEL_COLOR)

    star = starIcon()
    x, y = rowValuePosition(row)
    for index in range(min(count, MAX_STARS)):
        canvas.blit(star, (x + index * STAR_SPACING, y))
