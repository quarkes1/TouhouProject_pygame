"""输入抽象。

所有输入收敛成不可变的 FrameInput，游戏逻辑只认它。这样人工输入与将来
的 AI / 录像回放走同一条路径，逻辑层无需区分。详见 docs/DESIGN.md「输入」。
"""

import dataclasses

import pygame
import pytest

from touhou.core.input import FrameInput


def testDefaultInputIsAllFalse():
    frameInput = FrameInput()
    assert not any(
        (
            frameInput.left,
            frameInput.right,
            frameInput.up,
            frameInput.down,
            frameInput.shoot,
            frameInput.bomb,
            frameInput.slow,
        )
    )


def testInputIsImmutable():
    """不可变是确定性回放的前提——逻辑层不能偷偷改输入。

    精确断言 FrozenInstanceError 而非宽泛的 Exception：后者会被任意
    异常满足，包括被测代码里的真 bug。
    """
    with pytest.raises(dataclasses.FrozenInstanceError):
        FrameInput().shoot = True


def testDirectionIsZeroWhenNothingPressed():
    """没按方向键时方向向量必须是零向量，不能是 NaN。"""
    direction = FrameInput().direction()
    assert direction.x == 0.0
    assert direction.y == 0.0


def testDirectionIsNormalizedForCardinalDirections():
    assert FrameInput(right=True).direction().x == pytest.approx(1.0)
    assert FrameInput(left=True).direction().x == pytest.approx(-1.0)
    assert FrameInput(up=True).direction().y == pytest.approx(-1.0)
    assert FrameInput(down=True).direction().y == pytest.approx(1.0)


def testDiagonalDirectionIsNotLongerThanCardinal():
    """斜向必须归一化，否则玩家会靠斜走加速——这是个经典 bug。"""
    diagonal = FrameInput(right=True, down=True).direction()
    cardinal = FrameInput(right=True).direction()
    assert diagonal.length() == pytest.approx(cardinal.length())
    assert diagonal.length() == pytest.approx(1.0)


def testOppositeKeysCancelOut():
    direction = FrameInput(left=True, right=True).direction()
    assert direction.x == 0.0


def testOppositeKeysCancelOutOnOneAxisOnly():
    direction = FrameInput(left=True, right=True, up=True).direction()
    assert direction.x == 0.0
    assert direction.y == pytest.approx(-1.0)


def testDirectionOnAllFourKeysIsZero():
    direction = FrameInput(left=True, right=True, up=True, down=True).direction()
    assert direction.x == 0.0
    assert direction.y == 0.0


class FakeKeys:
    """只实现 __getitem__ 的假键盘状态，用来在不启动 pygame 的情况下测映射。"""

    def __init__(self, pressedKeys: set[int]) -> None:
        self.pressedKeys = pressedKeys

    def __getitem__(self, key: int) -> bool:
        return key in self.pressedKeys


def testReadKeyboardInputMapsArrowKeys():
    from touhou.core.input import readKeyboardInput

    result = readKeyboardInput(FakeKeys({pygame.K_LEFT, pygame.K_DOWN}))
    assert result.left and result.down
    assert not result.right and not result.up


def testReadKeyboardInputMapsActionKeys():
    from touhou.core.input import readKeyboardInput

    result = readKeyboardInput(FakeKeys({pygame.K_z, pygame.K_x, pygame.K_LSHIFT}))
    assert result.shoot and result.bomb and result.slow


def testReadKeyboardInputAcceptsEitherShift():
    from touhou.core.input import readKeyboardInput

    assert readKeyboardInput(FakeKeys({pygame.K_RSHIFT})).slow


def testReadKeyboardInputWithNothingPressed():
    from touhou.core.input import readKeyboardInput

    assert readKeyboardInput(FakeKeys(set())) == FrameInput()
