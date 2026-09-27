"""特效容器：在播的一次性动画，推进与绘制。

与 `BulletField`、`EnemyField` 对称，但**没有对象池**：特效一次只出现一两个，
池化省下的那点分配还不如它带来的状态泄漏风险。`Effect` 仍然写了完整的
`reset`，所以将来真要池化，改的只是这里。

这里的「回收」是**从 active 里摘掉**，不是像子弹那样按坐标剔除：特效的寿命由
它自己的帧数决定，放完就该消失，与它在哪无关。
"""

# 为注解开启延迟求值，理由见 vector2.py 的同类注释
from __future__ import annotations

import pygame

from touhou.core.vector2 import Vector2
from touhou.game.entities.effect import Effect


class EffectField:
    def __init__(self) -> None:
        self.active: list[Effect] = []

    def __len__(self) -> int:
        return len(self.active)

    def spawn(
        self,
        frames: tuple[pygame.Surface, ...],
        position: Vector2,
        framesPerFrame: int = 1,
    ) -> Effect:
        """在 position 处放一个动画。"""
        effect = Effect(frames, position, framesPerFrame)
        self.active.append(effect)
        return effect

    def update(self) -> None:
        """推进全部特效，把放完的摘掉。

        **倒序遍历 + 交换删除**，与 `BulletField.update` 同一套写法与理由：
        倒序保证每个特效恰好推进一次。

        推进的是**调用这一刻已经在场上的全部**特效。所以「出生那帧不推进」不是
        这里保证的，而是主循环的顺序保证的：`Game.update` 先 `effects.update()`
        再跑自机，于是自机死亡那一帧放出的冲击波停在第一帧——与子弹「出生那帧
        停在炮口」是同一条规矩。
        """
        for index in range(len(self.active) - 1, -1, -1):
            effect = self.active[index]
            effect.update()
            if effect.isFinished():
                self.active[index] = self.active[-1]
                self.active.pop()

    def draw(self, canvas: pygame.Surface) -> None:
        """绘制全部特效，以中心点对齐。

        与别处一样用 `get_rect(center=...)`：环是放大过的，尺寸每帧都在变，
        自己算半宽半高迟早会偏。
        """
        for effect in self.active:
            frame = effect.currentFrame()
            canvas.blit(frame, frame.get_rect(center=effect.position.toTuple()))
