"""东方风格的标题、设置和覆盖菜单。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import cache
from typing import Protocol

import pygame

from touhou.core.paths import assetPath
from touhou.core.settings import Settings

FONT_PATH_PARTS = ("fonts", "DFPPOPCorn-W12.ttf")
FONT_SIZE = 28
TITLE_FONT_SIZE = 38
SELECTED_COLOR = (255, 72, 96)
UNSELECTED_COLOR = (248, 240, 224)
SHADOW_COLOR = (32, 8, 16)
MENU_X = 408
MENU_Y = 205
ITEM_GAP = 43
SELECTED_OFFSET = -10


@dataclass(frozen=True, slots=True)
class MenuItem:
    label: str
    action: str


class MenuView(Protocol):
    items: tuple[MenuItem, ...]
    selectedIndex: int


class Menu:
    __slots__ = ("items", "selectedIndex")

    def __init__(self, items: tuple[MenuItem, ...], selectedIndex: int = 0) -> None:
        if not items:
            raise ValueError("菜单至少需要一项")
        self.items = items
        self.selectedIndex = selectedIndex % len(items)

    def handleKey(self, key: int) -> str | None:
        if key == pygame.K_UP:
            self.selectedIndex = (self.selectedIndex - 1) % len(self.items)
            return None
        if key == pygame.K_DOWN:
            self.selectedIndex = (self.selectedIndex + 1) % len(self.items)
            return None
        if key in (pygame.K_z, pygame.K_RETURN):
            return self.items[self.selectedIndex].action
        if key in (pygame.K_x, pygame.K_ESCAPE):
            return "back"
        return None


class OptionsMenu:
    __slots__ = ("items", "selectedIndex", "settings")

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.items = self._items()
        self.selectedIndex = 0

    def handleKey(self, key: int) -> tuple[str | None, Settings]:
        if key == pygame.K_UP:
            self.selectedIndex = (self.selectedIndex - 1) % len(self.items)
            return None, self.settings
        if key == pygame.K_DOWN:
            self.selectedIndex = (self.selectedIndex + 1) % len(self.items)
            return None, self.settings
        if key in (pygame.K_x, pygame.K_ESCAPE):
            return "back", self.settings
        if self.selectedIndex == 3 and key in (pygame.K_z, pygame.K_RETURN):
            return "back", self.settings

        direction = (1 if key == pygame.K_RIGHT else 0) - (1 if key == pygame.K_LEFT else 0)
        confirmToggle = key in (pygame.K_z, pygame.K_RETURN)
        changed = self.settings
        if self.selectedIndex == 0 and direction:
            changed = replace(
                changed, bgmVolume=max(0, min(10, changed.bgmVolume + direction))
            )
        elif self.selectedIndex == 1 and direction:
            changed = replace(
                changed, soundVolume=max(0, min(10, changed.soundVolume + direction))
            )
        elif self.selectedIndex == 2 and (direction or confirmToggle):
            changed = replace(changed, fullscreen=not changed.fullscreen)

        if changed == self.settings:
            return None, self.settings
        self.settings = changed
        self.items = self._items()
        return "settingsChanged", self.settings

    def _items(self) -> tuple[MenuItem, ...]:
        displayMode = "全屏" if self.settings.fullscreen else "窗口"
        return (
            MenuItem(f"BGM 音量  {self.settings.bgmVolume}", "bgmVolume"),
            MenuItem(f"音效音量  {self.settings.soundVolume}", "soundVolume"),
            MenuItem(f"显示模式  {displayMode}", "fullscreen"),
            MenuItem("返回", "back"),
        )


@cache
def menuFont() -> pygame.font.Font:
    return pygame.font.Font(str(assetPath(*FONT_PATH_PARTS)), FONT_SIZE)


@cache
def titleFont() -> pygame.font.Font:
    return pygame.font.Font(str(assetPath(*FONT_PATH_PARTS)), TITLE_FONT_SIZE)


def releaseCaches() -> None:
    menuFont.cache_clear()
    titleFont.cache_clear()


def drawTitle(canvas: pygame.Surface, background: pygame.Surface, menu: MenuView) -> None:
    """绘制标题背景和右侧纵向菜单。"""
    if background.get_size() == canvas.get_size():
        canvas.blit(background, (0, 0))
    else:
        pygame.transform.smoothscale(background, canvas.get_size(), canvas)

    shade = pygame.Surface(canvas.get_size(), pygame.SRCALPHA)
    shade.fill((32, 0, 8, 70))
    canvas.blit(shade, (0, 0))
    _drawShadowedText(canvas, titleFont(), "TouhouProject", (50, 62), UNSELECTED_COLOR)
    _drawMenuItems(canvas, menu)


def drawOverlayMenu(canvas: pygame.Surface, title: str, menu: MenuView) -> None:
    """在游戏最后一帧上覆盖暂停或结果菜单。"""
    veil = pygame.Surface(canvas.get_size(), pygame.SRCALPHA)
    veil.fill((8, 4, 12, 176))
    canvas.blit(veil, (0, 0))
    heading = titleFont().render(title, True, UNSELECTED_COLOR)
    canvas.blit(heading, heading.get_rect(center=(canvas.get_width() // 2, 125)))
    _drawMenuItems(canvas, menu, x=canvas.get_width() // 2 - 70, y=190)


def _drawMenuItems(
    canvas: pygame.Surface, menu: MenuView, x: int = MENU_X, y: int = MENU_Y
) -> None:
    font = menuFont()
    for index, item in enumerate(menu.items):
        selected = index == menu.selectedIndex
        color = SELECTED_COLOR if selected else UNSELECTED_COLOR
        itemX = x + (SELECTED_OFFSET if selected else 0)
        _drawShadowedText(canvas, font, item.label, (itemX, y + index * ITEM_GAP), color)


def _drawShadowedText(
    canvas: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    position: tuple[int, int],
    color: tuple[int, int, int],
) -> None:
    shadow = font.render(text, True, SHADOW_COLOR)
    canvas.blit(shadow, (position[0] + 2, position[1] + 2))
    canvas.blit(font.render(text, True, color), position)
