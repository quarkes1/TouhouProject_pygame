"""自机移动与游戏区边界约束。"""

import pygame
import pytest

from touhou import constants
from touhou.core.input import FrameInput
from touhou.core.spriteSheet import SpriteSheet
from touhou.core.vector2 import Vector2
from touhou.game.entities.player import Player, clampToPlayfield


@pytest.fixture
def spriteSheet() -> SpriteSheet:
    """8 帧、每帧 25×50，与 marisa_forward.png 一致。"""
    surface = pygame.Surface((25 * 8, 50), pygame.SRCALPHA)
    return SpriteSheet(surface, 25, 50)


@pytest.fixture
def player(spriteSheet) -> Player:
    return Player(position=Vector2(200, 400), spriteSheet=spriteSheet)


# —— 边界约束（纯函数，可脱离 Player 单测）——


def testClampStopsAtLeftEdge():
    half = Vector2(12.5, 25)
    clamped = clampToPlayfield(Vector2(-100, 200), half)
    assert clamped.x == constants.PLAYFIELD_X + 12.5


def testClampStopsAtRightEdge():
    half = Vector2(12.5, 25)
    clamped = clampToPlayfield(Vector2(9999, 200), half)
    expected = constants.PLAYFIELD_X + constants.PLAYFIELD_WIDTH - 12.5
    assert clamped.x == expected


def testClampStopsAtTopEdge():
    half = Vector2(12.5, 25)
    clamped = clampToPlayfield(Vector2(200, -100), half)
    assert clamped.y == constants.PLAYFIELD_Y + 25


def testClampStopsAtBottomEdge():
    """自机立绘完整留在游戏区内，不会有一半个身子探出去。"""
    half = Vector2(12.5, 25)
    clamped = clampToPlayfield(Vector2(200, 9999), half)
    expected = constants.PLAYFIELD_Y + constants.PLAYFIELD_HEIGHT - 25
    assert clamped.y == expected


def testClampLeavesInteriorPositionUntouched():
    half = Vector2(12.5, 25)
    inside = Vector2(200, 300)
    assert clampToPlayfield(inside, half) == inside


# —— 移动 ——


def testPlayerMovesRightAtNormalSpeed(player):
    startX = player.position.x
    player.update(FrameInput(right=True))
    assert player.position.x == pytest.approx(startX + constants.PLAYER_SPEED_NORMAL)


def testPlayerDoesNotMoveWithoutInput(player):
    start = player.position
    player.update(FrameInput())
    assert player.position == start


def testSlowModeHalvesDistance(player):
    normal = Player(position=Vector2(200, 400), spriteSheet=player.spriteSheet)
    slow = Player(position=Vector2(200, 400), spriteSheet=player.spriteSheet)

    normal.update(FrameInput(right=True))
    slow.update(FrameInput(right=True, slow=True))

    normalDistance = normal.position.x - 200
    slowDistance = slow.position.x - 200
    assert slowDistance == pytest.approx(normalDistance / 2)


def testDiagonalMovementCoversSameDistanceAsCardinal(player):
    """斜向移动的距离必须和直线一致，否则玩家会靠斜走加速。"""
    cardinal = Player(position=Vector2(200, 200), spriteSheet=player.spriteSheet)
    diagonal = Player(position=Vector2(200, 200), spriteSheet=player.spriteSheet)

    cardinal.update(FrameInput(right=True))
    diagonal.update(FrameInput(right=True, down=True))

    assert (diagonal.position - Vector2(200, 200)).length() == pytest.approx(
        (cardinal.position - Vector2(200, 200)).length()
    )


def testPlayerCannotLeavePlayfieldByHoldingDirection(player):
    """一直按着右和上，最终必须停在边界上而不是飞出游戏区。"""
    for _ in range(500):
        player.update(FrameInput(right=True, up=True))

    halfWidth = player.spriteSheet.frameWidth / 2
    halfHeight = player.spriteSheet.frameHeight / 2
    assert player.position.x == pytest.approx(
        constants.PLAYFIELD_X + constants.PLAYFIELD_WIDTH - halfWidth
    )
    assert player.position.y == pytest.approx(constants.PLAYFIELD_Y + halfHeight)


# —— 立绘朝向 ——


def testFacingIsFlatWhenMovingVertically(player):
    player.update(FrameInput(up=True))
    assert player.facing == 0


def testFacingTiltsRightWhenMovingRight(player):
    player.update(FrameInput(right=True))
    assert player.facing == 1


def testFacingTiltsLeftWhenMovingLeft(player):
    player.update(FrameInput(left=True))
    assert player.facing == -1


# —— 动画 ——


def testAnimationAdvancesOverTime(player):
    for _ in range(constants.FPS):
        player.update(FrameInput())
    assert player.animationFrame > 0


def testAnimationFrameStaysInRange(player):
    for _ in range(600):
        player.update(FrameInput())
        assert 0 <= player.animationFrame < player.spriteSheet.frameCount
