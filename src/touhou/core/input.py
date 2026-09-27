"""输入抽象。

移动与射击要的是「这一帧按住没有」——轮询键盘状态。
暂停与菜单要的是「刚刚按下了」——用事件。两者用途不同，不混用。

所有输入收敛成不可变的 FrameInput。这样人工输入与将来的 AI / 录像回放
走同一条路径，逻辑层无需区分二者。详见 docs/DESIGN.md「输入」。
"""

# 统一开启延迟注解求值，理由见 vector2.py 的同类注释
from __future__ import annotations

from dataclasses import dataclass, replace
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


class PressLatch:
    """把「刚刚按下」攒起来，交给下一个真正执行的逻辑步。

    事件与固定步长循环结合有个真问题：**一次渲染帧可能跑 0~5 次逻辑步**
    （`MAX_STEPS_PER_FRAME`，卡顿时还有丢弃）。把事件直接填进当帧的
    FrameInput 会两头出错：

    - 一帧跑 3 步 → 同一次按键被当成 3 次 → 按一下 X 放出三个炸弹
    - 一帧跑 0 步 → 按键被丢掉 → 死亡炸弹那 8 帧窗口里按 X 没反应，
      而这正是它最要命的地方（规格 §8.5 把窗口边界钉死在帧数上，
      漏掉一次按下就直接判死）

    所以事件先攒成**计数**（不是布尔：一帧内确实可能按下两次），
    由第一个真正执行的逻辑步取走一个并减一。

    目前只有 X（炸弹）需要边沿语义——移动与射击要的都是「按住没有」，
    轮询就对。将来暂停键也要边沿语义时，把这个类扩成按 key 记账的字典，
    而不是在 main.py 里再开一个同类的闩锁。
    """

    __slots__ = ("pending",)

    def __init__(self) -> None:
        self.pending = 0

    def record(self) -> None:
        """记下一次按下。由事件循环调用。"""
        self.pending += 1

    def consume(self, frameInput: FrameInput) -> FrameInput:
        """取走一次按下，产出这一步的输入。

        **无论有没有存货都覆盖 bomb**，包括把它压回 False：传进来的
        frameInput 是 `readKeyboardInput` 轮询出来的「现在按着没有」，
        而按住 X 不放若被当成每帧一次按下，几秒就能把炸弹放空。
        轮询值只用来喂摇杆式的持续输入（移动、射击）。
        """
        pressed = self.pending > 0
        if pressed:
            self.pending -= 1
        return replace(frameInput, bomb=pressed)


@dataclass(frozen=True, slots=True)
class FrameInput:
    """一帧的输入状态。不可变——逻辑层不该改动输入。"""

    left: bool = False
    right: bool = False
    up: bool = False
    down: bool = False
    shoot: bool = False  # Z 键，按住即持续射击
    bomb: bool = False  # X 键，**边沿**语义：这一逻辑步按下过（见 PressLatch）
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

    这里给出的 bomb 是**轮询值**（现在按着没有）。它只有对不做边沿区分的
    调用方才有意义——主循环会拿 `PressLatch` 的结果把它覆盖掉，
    因为炸弹要的是「按下过一次」而不是「一直按着」。
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
