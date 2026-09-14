"""程序入口。

职责仅限接线：开窗口、装离屏画布、驱动固定步长主循环、把渲染委托出去。
游戏逻辑一律不写在这里。
"""

# 统一开启延迟注解求值，理由见 vector2.py 的同类注释
from __future__ import annotations

import pygame

from touhou import constants
from touhou.core.display import chooseScaleFactor, scaledSize
from touhou.core.gameLoop import FixedStepAccumulator
from touhou.core.input import readKeyboardInput
from touhou.core.paths import assetPath
from touhou.core.spriteSheet import SpriteSheet
from touhou.core.vector2 import Vector2
from touhou.game.entities.player import Player

BACKGROUND_PATH_PARTS = ("sprites", "backgrounds", "background.png")
PLAYER_SPRITE_PATH_PARTS = ("sprites", "entities", "marisa_forward.png")
PLAYER_FRAME_WIDTH = 25
PLAYER_FRAME_HEIGHT = 50
BACKGROUND_SCROLL_SPEED = 0.5  # 像素/帧，向下滚动


class Game:
    def __init__(self) -> None:
        pygame.init()

        info = pygame.display.Info()
        self.scaleFactor = chooseScaleFactor(
            info.current_w, info.current_h, constants.LOGICAL_WIDTH, constants.LOGICAL_HEIGHT
        )
        windowSize = scaledSize(constants.LOGICAL_WIDTH, constants.LOGICAL_HEIGHT, self.scaleFactor)

        self.window = pygame.display.set_mode(windowSize)
        pygame.display.set_caption("TouhouProject")

        # 所有绘制先落在这张 640×480 的画布上，最后一次性整数倍缩放
        self.canvas = pygame.Surface((constants.LOGICAL_WIDTH, constants.LOGICAL_HEIGHT)).convert()

        self.background = self.loadBackground()
        self.backgroundOffset = 0.0

        playerSpriteSheet = SpriteSheet.fromFile(
            assetPath(*PLAYER_SPRITE_PATH_PARTS), PLAYER_FRAME_WIDTH, PLAYER_FRAME_HEIGHT
        )
        self.player = Player(
            position=Vector2(
                constants.PLAYFIELD_X + constants.PLAYFIELD_WIDTH / 2,
                constants.PLAYFIELD_Y + constants.PLAYFIELD_HEIGHT - 60,
            ),
            spriteSheet=playerSpriteSheet,
        )

        self.accumulator = FixedStepAccumulator(
            constants.STEP_SECONDS, constants.MAX_STEPS_PER_FRAME
        )
        self.clock = pygame.time.Clock()
        self.running = True

    def loadBackground(self) -> pygame.Surface:
        """把 1200×800 的背景缩到游戏区大小。

        这里用 smoothscale 而非 scale：这是一次性的大幅缩小（1200→384），
        最近邻会丢像素丢得很难看。窗口缩放是另一回事——那里必须用最近邻
        保住像素画的边缘，见 blitToWindow。
        """
        raw = pygame.image.load(str(assetPath(*BACKGROUND_PATH_PARTS))).convert()
        return pygame.transform.smoothscale(
            raw, (constants.PLAYFIELD_WIDTH, constants.PLAYFIELD_HEIGHT)
        )

    def playfieldRect(self) -> pygame.Rect:
        return pygame.Rect(
            constants.PLAYFIELD_X,
            constants.PLAYFIELD_Y,
            constants.PLAYFIELD_WIDTH,
            constants.PLAYFIELD_HEIGHT,
        )

    def run(self) -> None:
        while self.running:
            realDeltaSeconds = self.clock.tick(constants.FPS) / 1000.0
            self.handleEvents()
            for _ in range(self.accumulator.advance(realDeltaSeconds)):
                self.update()
            self.render()

    def handleEvents(self) -> None:
        for event in pygame.event.get():
            # 两个退出条件合并成一个分支，并给条件起名。直接写
            # if a: ... elif b: ... 两段相同代码会被 ruff 的 SIM114 拦下，
            # 而合并成一行长表达式又不好读，所以拆出两个具名变量。
            isQuit = event.type == pygame.QUIT
            isEscape = event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
            if isQuit or isEscape:
                self.running = False

    def update(self) -> None:
        """推进一帧游戏逻辑。"""
        self.player.update(readKeyboardInput(pygame.key.get_pressed()))

        # 背景缓慢下滚，避免画面完全静止
        self.backgroundOffset = (
            self.backgroundOffset + BACKGROUND_SCROLL_SPEED
        ) % constants.PLAYFIELD_HEIGHT

    def render(self) -> None:
        self.drawPlayfield()
        self.drawHudPlaceholder()
        self.blitToWindow()
        pygame.display.flip()

    def drawPlayfield(self) -> None:
        """画游戏区。绘制被裁剪在游戏区矩形内。"""
        playfield = self.playfieldRect()

        # set_clip 是必须的：无缝滚动要把背景画两遍，第二遍的 y 坐标会一路
        # 排到游戏区底边之外，不裁剪的话会渗进下方那条 16px 的边带。
        previousClip = self.canvas.get_clip()
        self.canvas.set_clip(playfield)

        offset = int(self.backgroundOffset)
        self.canvas.blit(
            self.background,
            (constants.PLAYFIELD_X, constants.PLAYFIELD_Y - constants.PLAYFIELD_HEIGHT + offset),
        )
        self.canvas.blit(self.background, (constants.PLAYFIELD_X, constants.PLAYFIELD_Y + offset))

        self.drawPlayer()

        self.canvas.set_clip(previousClip)

    def drawPlayer(self) -> None:
        """以中心点对齐绘制自机。

        不能直接 blit 到 position——blit 的第二个参数是左上角，而
        position 是中心点。也没有用 position - halfSize：倾斜立绘经
        pygame.transform.rotate 之后外接矩形会变大，那样算会偏。
        用 surface 自己的 rect 做 center 对齐，两种立绘都准。
        """
        frame = self.player.currentFrame()
        self.canvas.blit(frame, frame.get_rect(center=self.player.position.toTuple()))

    def drawHudPlaceholder(self) -> None:
        """HUD 区先留空。真正的 HUD 在 Plan D 里实现。"""
        hudX = constants.PLAYFIELD_X + constants.PLAYFIELD_WIDTH
        pygame.draw.rect(
            self.canvas,
            (16, 16, 24),
            (hudX, 0, constants.LOGICAL_WIDTH - hudX, constants.LOGICAL_HEIGHT),
        )

    def blitToWindow(self) -> None:
        if self.scaleFactor == 1:
            self.window.blit(self.canvas, (0, 0))
            return
        pygame.transform.scale(
            self.canvas,
            scaledSize(constants.LOGICAL_WIDTH, constants.LOGICAL_HEIGHT, self.scaleFactor),
            self.window,
        )


def main() -> None:
    game = Game()
    try:
        game.run()
    finally:
        pygame.quit()


if __name__ == "__main__":
    # 不能写 sys.exit(main())——main() 声明返回 None，mypy strict 会报
    # func-returns-value。直接调用即可，进程正常退出。
    main()
