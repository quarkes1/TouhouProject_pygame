"""精灵动画表与按角度预旋转缓存。

旋转缓存是弹幕性能的关键，也是最容易被写砸的地方。参考项目
NumPix/pygame-touhou 在 Bullet.__init__ 里对 sprite sheet 的每一帧都
调用 pygame.transform.rotate——子弹生成高峰期每秒数百发、每发旋转好几帧，
这一项单独就能吃掉全部帧预算。

角度取整数度后只有 360 种取值，因此 (帧序号, 角度) 的组合可以安全缓存。
缓存按需生成：只有实际用到的角度才会被创建，不会一上来就造出 360 张图。
"""

# fromFile 的返回注解引用了 SpriteSheet 自身，3.13 下需要延迟求值，
# 理由见 vector2.py
from __future__ import annotations

from pathlib import Path

import pygame


class SpriteSheet:
    def __init__(self, surface: pygame.Surface, frameWidth: int, frameHeight: int) -> None:
        if frameWidth <= 0 or frameHeight <= 0:
            raise ValueError(f"帧尺寸必须为正数，收到 {frameWidth}x{frameHeight}")
        if surface.get_width() < frameWidth or surface.get_height() < frameHeight:
            raise ValueError(
                f"表面 {surface.get_width()}x{surface.get_height()} 小于一帧 "
                f"{frameWidth}x{frameHeight}，切不出任何帧"
            )

        self.frameWidth = frameWidth
        self.frameHeight = frameHeight

        # 缓存键是 (帧序号, 归一化后的整数角度)
        self.rotatedCache: dict[tuple[int, int], pygame.Surface] = {}

        self.frames: list[pygame.Surface] = []
        columns = surface.get_width() // frameWidth
        rows = surface.get_height() // frameHeight
        for row in range(rows):
            for column in range(columns):
                rect = pygame.Rect(column * frameWidth, row * frameHeight, frameWidth, frameHeight)
                # subsurface 是视图，copy 出独立副本避免共享底层像素
                self.frames.append(surface.subsurface(rect).copy())

    @classmethod
    def fromFile(cls, path: Path | str, frameWidth: int, frameHeight: int) -> SpriteSheet:
        """从图片文件加载。用 convert_alpha 转成显示格式，blit 会快很多。"""
        surface = pygame.image.load(str(path)).convert_alpha()
        return cls(surface, frameWidth, frameHeight)

    @property
    def frameCount(self) -> int:
        return len(self.frames)

    def getFrame(self, index: int) -> pygame.Surface:
        return self.frames[index]

    def getRotated(self, frameIndex: int, angleDeg: float) -> pygame.Surface:
        """取旋转到指定角度的帧，结果被缓存。

        角度按本项目的全局约定解释（0° 正上、顺时针增大），归一到
        [0, 360) 的整数度后作为缓存键，因此缓存键最多 360 × 帧数 个——
        吃满约 1.5 MB（4 帧 16×16 子弹表）到 14 MB（自机立绘），量级与
        取舍见 docs/DESIGN.md「性能」。

        pygame.transform.rotate 的度数是逆时针为正，而屏幕 y 轴向下，
        所以要取负号才能得到「顺时针增大」的视觉效果。
        """
        key = (frameIndex, int(angleDeg) % 360)
        cached = self.rotatedCache.get(key)
        if cached is None:
            cached = pygame.transform.rotate(self.frames[frameIndex], -key[1])
            self.rotatedCache[key] = cached
        return cached

    def __repr__(self) -> str:
        return f"SpriteSheet({self.frameWidth}x{self.frameHeight}, {self.frameCount} 帧)"
