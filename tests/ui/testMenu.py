"""标题、暂停和设置菜单。"""

from dataclasses import replace

import pygame
import pytest

from touhou.core.settings import Settings
from touhou.ui.menu import (
    SELECTED_COLOR,
    UNSELECTED_COLOR,
    Menu,
    MenuItem,
    OptionsMenu,
    drawTitle,
    drawTutorialPrompt,
    menuItemX,
    tutorialFont,
)


def testMenuWrapsAndConfirms():
    menu = Menu((MenuItem("开始游戏", "start"), MenuItem("退出", "quit")))

    assert menu.handleKey(pygame.K_UP) is None
    assert menu.selectedIndex == 1
    assert menu.handleKey(pygame.K_z) == "quit"


def testMenuSupportsDownEnterAndBackKeys():
    menu = Menu((MenuItem("开始", "start"), MenuItem("设置", "options")))

    menu.handleKey(pygame.K_DOWN)
    assert menu.handleKey(pygame.K_RETURN) == "options"
    assert menu.handleKey(pygame.K_x) == "back"
    assert menu.handleKey(pygame.K_ESCAPE) == "back"


def testOneKeyEventMovesExactlyOneMenuItem():
    menu = Menu((MenuItem("一", "one"), MenuItem("二", "two"), MenuItem("三", "three")))
    menu.handleKey(pygame.K_DOWN)
    assert menu.selectedIndex == 1


def testOptionsAdjustAndReturnUpdatedSettings():
    menu = OptionsMenu(Settings(bgmVolume=7))

    action, changed = menu.handleKey(pygame.K_RIGHT)

    assert action == "settingsChanged"
    assert changed.bgmVolume == 8


def testOptionsVolumesStayWithinBounds():
    high = OptionsMenu(Settings(bgmVolume=10))
    assert high.handleKey(pygame.K_RIGHT)[1].bgmVolume == 10

    low = OptionsMenu(Settings(soundVolume=0))
    low.selectedIndex = 1
    assert low.handleKey(pygame.K_LEFT)[1].soundVolume == 0


def testOptionsToggleFullscreenWithLeftRightOrConfirm():
    menu = OptionsMenu(Settings(fullscreen=False))
    menu.selectedIndex = 2

    action, changed = menu.handleKey(pygame.K_RIGHT)
    assert action == "settingsChanged"
    assert changed.fullscreen

    menu.settings = replace(changed, fullscreen=False)
    action, changed = menu.handleKey(pygame.K_z)
    assert action == "settingsChanged"
    assert changed.fullscreen


def testOptionsToggleCheaterWithLeftRightOrConfirm():
    menu = OptionsMenu(Settings(cheater=False))
    menu.selectedIndex = 3

    action, changed = menu.handleKey(pygame.K_RIGHT)
    assert action == "settingsChanged"
    assert changed.cheater

    menu.settings = replace(changed, cheater=False)
    action, changed = menu.handleKey(pygame.K_z)
    assert action == "settingsChanged"
    assert changed.cheater


@pytest.mark.parametrize("key", [pygame.K_x, pygame.K_ESCAPE])
def testOptionsBackKeysReturnWithoutChangingSettings(key):
    settings = Settings(bgmVolume=4, soundVolume=5, fullscreen=True)
    menu = OptionsMenu(settings)
    action, unchanged = menu.handleKey(key)
    assert action == "back"
    assert unchanged == settings


def testOptionsReturnItemConfirmsBack():
    menu = OptionsMenu(Settings())
    menu.selectedIndex = 4
    assert menu.handleKey(pygame.K_RETURN)[0] == "back"


def testLongMenuItemIsShiftedInsideLogicalCanvas():
    x = menuItemX(canvasWidth=640, textWidth=351, baseX=408, selected=False)

    assert x == 273
    assert x + 351 <= 624


def testTutorialPromptStaysInsideCanvas():
    canvas = pygame.Surface((640, 480))
    text = "TRAINING COMPLETE - Z: START  X: TITLE"

    panel = drawTutorialPrompt(canvas, text, True)

    assert pygame.Rect(0, 0, 640, 480).contains(panel)
    assert tutorialFont().size(text)[0] <= panel.width - 16


def testTitleDrawUsesDifferentColorsForSelection():
    canvas = pygame.Surface((640, 480))
    background = pygame.Surface(canvas.get_size())
    background.fill((1, 2, 3))
    menu = Menu((MenuItem("START", "start"), MenuItem("QUIT", "quit")))

    drawTitle(canvas, background, menu)

    colors = {canvas.get_at((x, y))[:3] for x in range(640) for y in range(480)}
    assert SELECTED_COLOR in colors
    assert UNSELECTED_COLOR in colors
