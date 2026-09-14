"""输入抽象。

移动与射击要的是「这一帧按住没有」——轮询键盘状态。
暂停与菜单要的是「刚刚按下了」——用事件。两者用途不同，不混用。

所有输入收敛成不可变的 FrameInput。这样人工输入与将来的 AI / 录像回放
走同一条路径，逻辑层无需区分二者。详见设计文档 §5.3。
"""

# 统一开启延迟注解求值，理由见 vector2.py 的同类注释
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pygame

from touhou.core.vector2 import Vector2


class KeyState(Protocol):
    """按键盘键常量索引的键盘状态视图。

    pygame.key.get_pressed() 的返回值满足这个协议，测试用的假对象也满足它。

    定义成协议而不是 pygame 的具体类型（ScancodeWrapper），是为了让输入翻译
    可以脱离 pygame 单独测试——用具体类型的话，测试里的假键盘状态不满足它，
    mypy 会在调用处报错，那条"脱离 pygame 测试"的设计目标就废了。
    用 Any 则等于没有契约，读签名看不出这个参数到底要什么形状。
    """

    def __getitem__(self, key: int) -> bool: ...


@dataclass(frozen=True, slots=True)
class FrameInput:
    """一帧的输入状态。不可变——逻辑层不该改动输入。"""

    left: bool = False
    right: bool = False
    up: bool = False
    down: bool = False
    shoot: bool = False  # Z 键
    bomb: bool = False  # X 键
    slow: bool = False  # Shift 键

    def direction(self) -> Vector2:
        """方向键翻译成的移动方向，已归一化。

        归一化保证斜向不会比直线快。全部松开或相反方向同时按下时
        normalize 会返回零向量（而非 NaN），自机因此原地不动。
        """
        horizontal = (1.0 if self.right else 0.0) - (1.0 if self.left else 0.0)
        vertical = (1.0 if self.down else 0.0) - (1.0 if self.up else 0.0)
        return Vector2(horizontal, vertical).normalize()


def readKeyboardInput(pressed: KeyState) -> FrameInput:
    """把键盘状态翻译成 FrameInput。

    pressed 是 pygame.key.get_pressed() 的返回值（可用键常量索引）。
    测试时传一个只实现 __getitem__ 的假对象即可，不必启动 pygame。
    """
    return FrameInput(
        left=bool(pressed[pygame.K_LEFT]),
        right=bool(pressed[pygame.K_RIGHT]),
        up=bool(pressed[pygame.K_UP]),
        down=bool(pressed[pygame.K_DOWN]),
        shoot=bool(pressed[pygame.K_z]),
        bomb=bool(pressed[pygame.K_x]),
        slow=bool(pressed[pygame.K_LSHIFT] or pressed[pygame.K_RSHIFT]),
    )
