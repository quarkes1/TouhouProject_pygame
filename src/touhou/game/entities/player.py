"""自机。

本阶段只实现移动、边界约束与立绘动画。射击、擦弹、炸弹、死亡与复活
在后续计划中加入。

边界约束抽成模块级函数 clampToPlayfield，是为了能脱离 Player 对象
单独测试——它是纯数学，没有理由要求测试先构造一个精灵表。
"""

# 统一开启延迟注解求值，理由见 vector2.py 的同类注释
from __future__ import annotations

import pygame

from touhou import constants
from touhou.core.input import FrameInput
from touhou.core.spriteSheet import SpriteSheet
from touhou.core.vector2 import Vector2

# 每帧推进多少动画帧。立绘是 8 帧循环，这个速度大约每 10 帧换一张。
ANIMATION_FRAMES_PER_TICK = 0.1


def clampToPlayfield(position: Vector2, halfSize: Vector2) -> Vector2:
    """把位置限制在游戏区内，保证整个立绘不越界。

    halfSize 是立绘半宽半高——用立绘尺寸而非判定点做约束，因为玩家看到的
    是立绘，立绘探出边界会显得很怪，哪怕判定点还在场内。

    倾斜 ±7° 后立绘外接矩形从 25×50 涨到约 30×52，贴边时外接矩形会探出
    游戏区约 2.5px。实测（marisa_forward.png 第 0 帧，±7°，四边贴齐）探出
    的部分全部是透明像素，可见像素全部在游戏区内，所以钳制沿用平帧
    halfSize 即可，不必加宽——加宽只会让自机在离边更远处提前停下。
    """
    minX = constants.PLAYFIELD_X + halfSize.x
    maxX = constants.PLAYFIELD_X + constants.PLAYFIELD_WIDTH - halfSize.x
    minY = constants.PLAYFIELD_Y + halfSize.y
    maxY = constants.PLAYFIELD_Y + constants.PLAYFIELD_HEIGHT - halfSize.y

    return Vector2(min(max(position.x, minX), maxX), min(max(position.y, minY), maxY))


class Player:
    def __init__(
        self,
        position: Vector2,
        spriteSheet: SpriteSheet,
        speedNormal: float = constants.PLAYER_SPEED_NORMAL,
        speedSlow: float = constants.PLAYER_SPEED_SLOW,
    ) -> None:
        self.position = position
        self.spriteSheet = spriteSheet
        self.speedNormal = speedNormal
        self.speedSlow = speedSlow

        # -1 左倾 / 0 直立 / +1 右倾
        self.facing = 0
        self.animationFrame = 0
        self.animationTimer = 0.0
        self.slow = False

    def update(self, frameInput: FrameInput) -> None:
        """推进一帧。"""
        self.slow = frameInput.slow
        direction = frameInput.direction()
        self.move(direction)
        self.updateFacing(direction)
        self.advanceAnimation()

    def move(self, direction: Vector2) -> None:
        """按当前速度档位移动一步，并钳制在游戏区内。

        速度档位来自 self.slow，而它只在 update() 里由 FrameInput 写入；
        绕过 update() 直接调 move() 会沿用上一帧的档位（初始为全速）。
        这是有意为之：move 是 update 的内部步骤，不是公共入口。
        """
        speed = self.speedSlow if self.slow else self.speedNormal
        self.position = clampToPlayfield(self.position + direction * speed, self.halfSize())

    def halfSize(self) -> Vector2:
        return Vector2(self.spriteSheet.frameWidth / 2, self.spriteSheet.frameHeight / 2)

    def updateFacing(self, direction: Vector2) -> None:
        """左右移动时立绘倾斜，纯垂直或静止时回正。"""
        if direction.x > 0:
            self.facing = 1
        elif direction.x < 0:
            self.facing = -1
        else:
            self.facing = 0

    def advanceAnimation(self) -> None:
        self.animationTimer += ANIMATION_FRAMES_PER_TICK
        if self.animationTimer >= 1.0:
            self.animationTimer -= 1.0
            self.animationFrame = (self.animationFrame + 1) % self.spriteSheet.frameCount

    def currentFrame(self) -> pygame.Surface:
        """当前应该绘制的画面。

        倾斜立绘本阶段直接用旋转实现；后续若要更精细的表现，可换成
        预先烘焙好三组贴图。
        """
        if self.facing == 0:
            return self.spriteSheet.getFrame(self.animationFrame)
        return self.spriteSheet.getRotated(self.animationFrame, -7 if self.facing < 0 else 7)
