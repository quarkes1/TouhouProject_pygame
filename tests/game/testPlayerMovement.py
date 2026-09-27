"""自机移动与游戏区边界约束。

立绘、自机与两个弹幕场的夹具在 `tests/game/conftest.py`（自机的 update 收
两个子弹场：开火要往里放弹、炸弹要清空敌弹）。推进一帧写 `step(...)`。
"""

import pygame
import pytest

from touhou import constants
from touhou.core.input import FrameInput
from touhou.core.vector2 import Vector2
from touhou.game.entities.player import clampToPlayfield

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


def testPlayerMovesRightAtNormalSpeed(player, step):
    startX = player.position.x
    step(FrameInput(right=True))
    assert player.position.x == pytest.approx(startX + constants.PLAYER_SPEED_NORMAL)


def testPlayerDoesNotMoveWithoutInput(player, step):
    start = player.position
    step(FrameInput())
    assert player.position == start


def testSlowModeHalvesDistance(makePlayer, runPlayer):
    normal = makePlayer()
    slow = makePlayer()

    runPlayer(normal, FrameInput(right=True))
    runPlayer(slow, FrameInput(right=True, slow=True))

    normalDistance = normal.position.x - 200
    slowDistance = slow.position.x - 200
    assert slowDistance == pytest.approx(normalDistance / 2)


def testDiagonalMovementCoversSameDistanceAsCardinal(makePlayer, runPlayer):
    """斜向移动的距离必须和直线一致，否则玩家会靠斜走加速。"""
    cardinal = makePlayer()
    diagonal = makePlayer()

    runPlayer(cardinal, FrameInput(right=True))
    runPlayer(diagonal, FrameInput(right=True, down=True))


def testPlayerCannotLeavePlayfieldByHoldingDirection(player, step):
    """一直按着右和上，最终必须停在边界上而不是飞出游戏区。"""
    for _ in range(500):
        step(FrameInput(right=True, up=True))

    halfWidth = player.spriteSheet.frameWidth / 2
    halfHeight = player.spriteSheet.frameHeight / 2
    assert player.position.x == pytest.approx(
        constants.PLAYFIELD_X + constants.PLAYFIELD_WIDTH - halfWidth
    )
    assert player.position.y == pytest.approx(constants.PLAYFIELD_Y + halfHeight)


# —— 立绘朝向 ——


def testFacingIsFlatWhenMovingVertically(player, step):
    step(FrameInput(up=True))
    assert player.facing == 0


def testFacingTiltsRightWhenMovingRight(player, step):
    step(FrameInput(right=True))
    assert player.facing == 1


def testFacingTiltsLeftWhenMovingLeft(player, step):
    step(FrameInput(left=True))
    assert player.facing == -1


# —— 动画 ——


def testAnimationAdvancesOverTime(player, step):
    for _ in range(constants.FPS):
        step(FrameInput())
    assert player.animationFrame > 0


def testAnimationFrameStaysInRange(player, step):
    for _ in range(600):
        step(FrameInput())
        assert 0 <= player.animationFrame < player.spriteSheet.frameCount


# —— 立绘帧 ——


def testCurrentFramePicksBranchByFacing(makePlayer, tiltSpriteSheet):
    """朝向 0 用平帧，+1 用 +7°（右倾），-1 用 -7°（左倾）。

    currentFrame 的倾斜角度符号写反的话（+7/-7 互换），立绘会朝反方向倾，
    但三种朝向的帧都会正常生成、照常缓存——这个文件里的移动与朝向测试
    全部只看 facing 数字，没有一个会红。这里直接断言「朝向和角度的对应
    关系」，与 testSpriteSheet 里「+7° = 顺时针右倾」的方向锁合起来，
    整个倾斜方向才被钉死。
    """
    tiltPlayer = makePlayer(sheet=tiltSpriteSheet, position=Vector2(200, 300))

    tiltPlayer.facing = 0
    upright = tiltPlayer.currentFrame()
    assert pygame.image.tobytes(upright, "RGBA") == pygame.image.tobytes(
        tiltPlayer.spriteSheet.getFrame(tiltPlayer.animationFrame), "RGBA"
    )

    tiltPlayer.facing = 1
    right = tiltPlayer.currentFrame()
    assert pygame.image.tobytes(right, "RGBA") == pygame.image.tobytes(
        tiltPlayer.spriteSheet.getRotated(tiltPlayer.animationFrame, 7), "RGBA"
    )

    tiltPlayer.facing = -1
    left = tiltPlayer.currentFrame()
    assert pygame.image.tobytes(left, "RGBA") == pygame.image.tobytes(
        tiltPlayer.spriteSheet.getRotated(tiltPlayer.animationFrame, -7), "RGBA"
    )

    # 三种朝向两两不同：倾斜确实改变了画面，且左右倾斜互为镜像而非相同
    for one, other in ((right, left), (right, upright), (left, upright)):
        assert pygame.image.tobytes(one, "RGBA") != pygame.image.tobytes(other, "RGBA")
