"""BOSS 血条。

画在**游戏区顶部**（规格 §6.7：「血条分段（Phase）……段数显示于屏幕顶部」）。

与 `ui/hud.py` 同一套路：**只收裸值**，不 import `game/` 里的任何东西——所以它能
脱离 BOSS 单独测试（造几个数画一帧、比像素），也不会因为 BOSS 将来多出别的状态
而改动。

一条血条画的是**本段**的血：BOSS 的每一段（通常攻击 / 符卡）各有各的血量，原作的
规矩也是这样。总段数与当前段号画在血条下方的小格子里，所以「还剩几段」一眼看得出。

`maxHp <= 0` 时**什么都不画**：BOSS 的血量是脚本第一次 `runPhase` 时才给的，
那一帧之前没有「本段血量」这回事——画一条空槽比不画更让人困惑。
"""

# 为注解开启延迟求值，理由见 vector2.py 的同类注释
from __future__ import annotations

import pygame

from touhou import constants
from touhou.ui import hud

# 版式：整条压在游戏区顶部，左右各留一段，免得顶到边界
BAR_MARGIN_X = 56
BAR_HEIGHT = 8
BAR_TOP = constants.PLAYFIELD_Y + 34
NAME_TOP = constants.PLAYFIELD_Y + 10
# 分段小格子
PIP_SIZE = 9
PIP_GAP = 5
PIP_TOP = BAR_TOP + BAR_HEIGHT + 5

# 配色：底槽压暗、血量亮，边框比底槽再亮一点（不然贴在深色背景上看不出边界）
TRACK_COLOR = (48, 40, 56)
FILL_COLOR = (255, 150, 190)
BORDER_COLOR = (120, 108, 132)
PIP_DONE_COLOR = (255, 150, 190)
PIP_TODO_COLOR = (72, 64, 84)


def barRect() -> pygame.Rect:
    """血条的矩形。**单独暴露给测试用**——按像素采样时要能算出该看哪儿。"""
    return pygame.Rect(
        constants.PLAYFIELD_X + BAR_MARGIN_X,
        BAR_TOP,
        constants.PLAYFIELD_WIDTH - 2 * BAR_MARGIN_X,
        BAR_HEIGHT,
    )


def drawBossBar(
    canvas: pygame.Surface,
    name: str,
    hp: int,
    maxHp: int,
    segments: int,
    segmentIndex: int,
) -> None:
    """画血条、名字与分段格子。

    `hp` / `maxHp` 是本段的血量；`segments` 是总段数、`segmentIndex` 是当前第几段
    （从 0 起，已经打完的那些格子是亮的）。
    """
    if maxHp <= 0:
        return

    rect = barRect()
    canvas.fill(TRACK_COLOR, rect)
    filledWidth = round(rect.width * min(1.0, max(0.0, hp / maxHp)))
    if filledWidth > 0:
        canvas.fill(FILL_COLOR, pygame.Rect(rect.x, rect.y, filledWidth, rect.height))
    pygame.draw.rect(canvas, BORDER_COLOR, rect, width=1)

    drawPips(canvas, rect, segments, segmentIndex)

    font = hud.hudFont()
    text = font.render(name, True, FILL_COLOR)
    canvas.blit(text, text.get_rect(midtop=(rect.centerx, NAME_TOP)))


def drawPips(canvas: pygame.Surface, rect: pygame.Rect, segments: int, segmentIndex: int) -> None:
    """血条下方那一排小格子：亮的是已经打完的段（含正在打的这一段）。

    格子居中排。段数很少（通常 1~5），所以不必考虑放不下——真放不下的话
    `PIP_SIZE` 与 `PIP_GAP` 就该调小，而不是让格子跑出游戏区。
    """
    totalWidth = segments * PIP_SIZE + (segments - 1) * PIP_GAP
    left = rect.centerx - totalWidth // 2
    for index in range(segments):
        color = PIP_DONE_COLOR if index <= segmentIndex else PIP_TODO_COLOR
        canvas.fill(color, pygame.Rect(left + index * (PIP_SIZE + PIP_GAP), PIP_TOP, PIP_SIZE, 4))
