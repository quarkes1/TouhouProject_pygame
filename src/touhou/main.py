"""程序入口。

职责仅限接线：开窗口、装离屏画布、驱动固定步长主循环、把渲染委托出去。
游戏逻辑一律不写在这里。
"""

# 统一开启延迟注解求值，理由见 vector2.py 的同类注释
from __future__ import annotations

import random
from enum import Enum, auto
from pathlib import Path

import pygame

from touhou import constants
from touhou.core.audio import AudioManager
from touhou.core.display import chooseScaleFactor, scaledSize
from touhou.core.gameLoop import FixedStepAccumulator
from touhou.core.input import PressLatch, readKeyboardInput
from touhou.core.paths import assetPath
from touhou.core.settings import loadSettings, saveSettings
from touhou.core.spriteSheet import SpriteSheet
from touhou.core.vector2 import Vector2
from touhou.game import collision
from touhou.game.bulletField import BulletField
from touhou.game.effectField import EffectField
from touhou.game.enemyField import EnemyField
from touhou.game.entities.boss import Boss
from touhou.game.entities.bullet import BulletSpec
from touhou.game.entities.effect import bakeExpandingRing
from touhou.game.entities.player import Player, State
from touhou.game.levelData import loadLevel
from touhou.game.tutorial import TutorialController
from touhou.ui import bossBar, hud
from touhou.ui import menu as menuUi

BACKGROUND_PATH_PARTS = ("sprites", "backgrounds", "background.png")
PLAYER_SPRITE_PATH_PARTS = ("sprites", "entities", "marisa_forward.png")
PLAYER_FRAME_WIDTH = 25
PLAYER_FRAME_HEIGHT = 50
PLAYER_SHOT_SPRITE_PATH_PARTS = ("sprites", "projectiles_and_items", "marisa_bullet.png")
PLAYER_SHOT_FRAME_SIZE = 32  # 单帧 32×32 的一道光弹，不是帧表
PLAYER_HITBOX_PATH_PARTS = ("sprites", "effects", "player_hitbox.png")
DEATH_EFFECT_PATH_PARTS = ("sprites", "effects", "player_death_effect.png")
BACKGROUND_SCROLL_SPEED = 0.5  # 像素/帧，向下滚动
LEVEL_PATH_PARTS = ("levels", "level_1.json")
TUTORIAL_LEVEL_PATH_PARTS = ("levels", "tutorial.json")
TITLE_BACKGROUND_PATH_PARTS = ("sprites", "backgrounds", "title_screen_wallpaper.jpg")

# 随机弹幕的种子。**写死而不是取时间**：同一份输入必须产生同一场战斗，
# 否则录像回放与逐帧调试都无从谈起（docs/DESIGN.md「主循环」）。
# 要换一种随机局面就改这个数。
RANDOM_SEED = 20260927


class Scene(Enum):
    TITLE = auto()
    OPTIONS = auto()
    PLAYING = auto()
    TUTORIAL = auto()
    PAUSED = auto()
    GAME_OVER = auto()
    STAGE_CLEAR = auto()


def canvasDestination(windowSize: tuple[int, int]) -> pygame.Rect:
    """计算保持 4:3、居中且不裁切的画布目标矩形。"""
    windowWidth, windowHeight = windowSize
    logicalWidth = constants.LOGICAL_WIDTH
    logicalHeight = constants.LOGICAL_HEIGHT
    if windowWidth * logicalHeight <= windowHeight * logicalWidth:
        width = max(1, windowWidth)
        height = max(1, windowWidth * logicalHeight // logicalWidth)
    else:
        height = max(1, windowHeight)
        width = max(1, windowHeight * logicalWidth // logicalHeight)
    return pygame.Rect((windowWidth - width) // 2, (windowHeight - height) // 2, width, height)


def presentCanvas(
    window: pygame.Surface, canvas: pygame.Surface, windowSize: tuple[int, int]
) -> None:
    """把固定逻辑画布等比缩放到窗口中央，只保留最小必要边带。"""
    destination = canvasDestination(windowSize)
    window.fill((0, 0, 0))
    if destination.size == canvas.get_size():
        window.blit(canvas, destination)
    elif destination.width < canvas.get_width():
        window.blit(pygame.transform.smoothscale(canvas, destination.size), destination)
    else:
        window.blit(pygame.transform.scale(canvas, destination.size), destination)
    pygame.display.flip()


class Game:
    def __init__(
        self,
        window: pygame.Surface | None = None,
        canvas: pygame.Surface | None = None,
        levelPath: Path | None = None,
    ) -> None:
        pygame.init()

        # Info() 必须在 set_mode 之前取：实测 set_mode(640, 480) 之后
        # Info() 报告的是窗口尺寸（640×480）而不是显示器尺寸，倍率会被
        # 静默钉死成 ×1。这条调用顺序是「倍率反映真实显示器」的前提，
        # 任何把 set_mode 提前的重构都会让每次启动都变成 ×1 小窗。
        if window is None:
            info = pygame.display.Info()
            self.scaleFactor = chooseScaleFactor(
                info.current_w, info.current_h, constants.LOGICAL_WIDTH, constants.LOGICAL_HEIGHT
            )
            windowSize = scaledSize(
                constants.LOGICAL_WIDTH, constants.LOGICAL_HEIGHT, self.scaleFactor
            )
            self.window = pygame.display.set_mode(windowSize, pygame.RESIZABLE)
        else:
            self.window = window
            self.scaleFactor = 1
        pygame.display.set_caption("TouhouProject")

        # 关掉 SDL 的文本输入通道。**必须在 set_mode 之后调用。**
        #
        # 不关的话中文输入法会截走按键：pygame 建窗口时默认开启文本输入，
        # 于是输入法对窗口生效，玩家按下任意字母键（比如 A）之后
        # `pygame.key.get_pressed()` 就不再上报按键状态了——表现为
        # 「按了 A 之后方向键全部失灵」，而按住 Shift 或把输入法切到英文就恢复。
        # 这个 bug 在没有输入法的机器上复现不出来。
        #
        # 本项目不需要文字输入（将来做记分板输入名字时再按需 start_text_input）。
        pygame.key.stop_text_input()

        # 所有绘制先落在这张 640×480 的画布上，最后一次性整数倍缩放
        self.canvas = (
            canvas or pygame.Surface((constants.LOGICAL_WIDTH, constants.LOGICAL_HEIGHT)).convert()
        )

        self.background = self.loadBackground()
        self.backgroundOffset = 0.0

        playerSpriteSheet = SpriteSheet.fromFile(
            assetPath(*PLAYER_SPRITE_PATH_PARTS), PLAYER_FRAME_WIDTH, PLAYER_FRAME_HEIGHT
        )
        # 判定点只在低速时画（规格 §6.2）。立绘有 25×50 而判定点直径 4px，
        # 不画出来的话玩家没法判断自己站得有多准，而这正是低速模式存在的意义。
        self.hitboxSprite = pygame.image.load(
            str(assetPath(*PLAYER_HITBOX_PATH_PARTS))
        ).convert_alpha()

        # 冲击波特效：**一张**环形贴图（500×500，中空），不是帧序列——动画得靠缩放
        # 烘出来。烘一次、放的时候只 blit，理由见 effect.py。
        #
        # 自机死亡与 BOSS 倒下用的是同一份帧：素材是同一张，烘两遍只是白占内存。
        # 存在 `self` 上而不是从 `self.player` 里摸——BOSS 的特效不该依赖自机实例。
        self.ringFrames = bakeExpandingRing(
            pygame.image.load(str(assetPath(*DEATH_EFFECT_PATH_PARTS))).convert_alpha(),
            constants.DEATH_EFFECT_BAKED_FRAMES,
            constants.DEATH_RING_START_SCALE,
            constants.DEATH_RING_END_SCALE,
            constants.DEATH_RING_START_ALPHA,
            constants.DEATH_RING_END_ALPHA,
        )
        self.ringFramesPerFrame = max(1, constants.DEATH_EFFECT_FRAMES // len(self.ringFrames))

        self.player = Player(
            position=Vector2(
                constants.PLAYFIELD_X + constants.PLAYFIELD_WIDTH / 2,
                constants.PLAYFIELD_Y + constants.PLAYFIELD_HEIGHT - 60,
            ),
            spriteSheet=playerSpriteSheet,
            shotSpec=BulletSpec(
                spriteSheet=SpriteSheet.fromFile(
                    assetPath(*PLAYER_SHOT_SPRITE_PATH_PARTS),
                    PLAYER_SHOT_FRAME_SIZE,
                    PLAYER_SHOT_FRAME_SIZE,
                ),
                radius=constants.PLAYER_SHOT_RADIUS,
                # 不跟着速度旋转：marisa_bullet 是一道竖直的光弹，转了反而歪。
                rotatesToVelocity=False,
                damage=constants.PLAYER_SHOT_DAMAGE,
            ),
            deathEffectFrames=self.ringFrames,
            # 放雷暂时复用死亡那份扩散环（雷还没有自己的美术），但**传的是同一份
            # 帧对象**、不是一个「共用开关」：等雷的素材到位，这里换一张烘好的表
            # 就行，`Player` 那边一行不用动。
            bombEffectFrames=self.ringFrames,
        )

        self.accumulator = FixedStepAccumulator(
            constants.STEP_SECONDS, constants.MAX_STEPS_PER_FRAME
        )
        self.clock = pygame.time.Clock()
        self.running = True
        self.pressLatch = PressLatch()

        self.bulletField = BulletField()
        # 自机子弹**另一个场**：两条碰撞路径互不相干（敌弹打自机、自机弹打敌机），
        # 共用一个列表只会互相干扰。
        self.shots = BulletField()
        self.effects = EffectField()
        self.level = loadLevel(levelPath or assetPath(*LEVEL_PATH_PARTS))
        # BOSS 与敌机同一个容器：BOSS 在引擎眼里就是「有血量的、会被打的东西」，
        # 见 entities/boss.py。用关键字传，免得两个元组位置搞反。
        self.enemyField = EnemyField(
            spawns=self.level.spawns,
            rng=random.Random(RANDOM_SEED),
            bossSpawns=self.level.bosses,
        )

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

            # 炸弹走**事件**而不是轮询：要的是「刚刚按下」。这里只记一笔，
            # 由下一个真正执行的逻辑步取走——一次渲染帧可能跑 0~5 步，
            # 记在当帧的输入里会让一次按下变成三次（或整帧被丢掉）。
            if event.type == pygame.KEYDOWN and event.key == pygame.K_x:
                self.pressLatch.record()

    def update(self) -> None:
        """推进一帧游戏逻辑。

        顺序是承重的，尤其那句「子弹先飞、再动自机与敌机」：新放出的子弹
        必须**晚于**自己那个场的 update()，才会停在炮口而不是凭空飞出一帧。
        """
        # 三个场先推进。自机的命中判定在后面，于是它比较的是**同一帧**的两个
        # 位置——自机这一步刚走到的位置 vs 敌弹这一步刚飞到的位置。反过来写
        # 的话自机拿新位置去比旧弹位，判定永远慢一帧。
        #
        # 特效也在这里推进（而不是紧挨着自机）：这样死亡那一帧放出的冲击波
        # 停在第一帧，与子弹「出生那帧停在炮口」是同一条规矩。
        self.bulletField.update()
        self.shots.update()
        self.effects.update()

        frameInput = self.pressLatch.consume(readKeyboardInput(pygame.key.get_pressed()))
        self.player.update(frameInput, self.shots, self.bulletField, self.enemyField, self.effects)

        # BOSS 有可能死在这两步中的任何一步：`enemyField.update` 里回收，或者
        # `resolvePlayerShots` 里结算。所以先留一份引用，等两步都走完再看它还在不在。
        bossBefore = self.enemyField.boss

        # 敌机在自己 update 里打出齐射。它排在 bulletField.update() 之后，
        # 所以本帧新放出的敌弹不推进（契约见 bulletField.update 的注释）；
        # 自机位置在这一句之前已经更新过，于是自机狙瞄的是**本帧**的自机。
        self.enemyField.update(self.bulletField, self.player.position)

        # 结算自机子弹打到了谁。必须排在这两个场都动完之后：子弹与敌机
        # 这一帧的最终位置都定下来了，判定才不会漏掉「本帧刚好撞上」的那一发。
        collision.resolvePlayerShots(self.shots, self.enemyField, self.bulletField)
        self.celebrateBossDefeat(bossBefore)

        # 背景缓慢下滚，避免画面完全静止
        self.backgroundOffset = (
            self.backgroundOffset + BACKGROUND_SCROLL_SPEED
        ) % constants.PLAYFIELD_HEIGHT

    def celebrateBossDefeat(self, bossBefore: Boss | None) -> None:
        """BOSS 被打倒的那一帧，在原地炸一下。

        位置要从 `bossBefore` 上取——走到这里 `enemyField.boss` 已经是 None 了。
        引用还在，对象还在，`position` 也还是倒下那一刻的位置。

        **只有被打死的才炸**：脚本自己跑完而退场（血还没掉光）不该有爆炸，
        与「飞走的敌人不掉东西」是同一条区分。
        """
        if bossBefore is None or self.enemyField.boss is not None:
            return
        if not bossBefore.isDead():
            return
        self.effects.spawn(self.ringFrames, bossBefore.position, self.ringFramesPerFrame)

    def isStageClear(self) -> bool:
        """时刻表结束且场上已清空时，当前关卡完成。"""
        return (
            self.enemyField.elapsedFrames >= self.level.durationFrames
            and self.enemyField.scheduleComplete()
        )

    def render(self, present: bool = True) -> None:
        self.drawPlayfield()
        # 血条排在游戏区之后（不然会被子弹盖住）、HUD 之前（它只占游戏区那 384px，
        # 与右侧面板不重叠）。BOSS 不在场时它自己什么都不画。
        self.drawBossBar()
        # HUD 只收裸值，不认自机对象——它因此可以脱离游戏逻辑单独测试。
        hud.drawHud(self.canvas, self.player.lives, self.player.bombs, self.player.power)
        if present:
            self.blitToWindow()

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

        # 层次：敌机 → 自机 → 特效 → 自机子弹 → 敌弹，与原作一致（自己的弹压在
        # 敌机之上，敌弹压在一切之上——躲弹时最该看清的就是它）。
        # 特效压在自机之上：自机死亡的冲击波是**盖着自机**炸开的。
        self.drawEnemies()
        self.drawPlayer()
        self.effects.draw(self.canvas)
        # 在裁剪区内画子弹：它们因此不会渗进右侧 HUD 条，也不会掉进游戏区下沿
        # 那条 16px 边带。这不是可选的——关卡里的敌人会在游戏区外（含 HUD 区）
        # 开火，子弹从那里飞进场内。
        self.shots.draw(self.canvas)
        self.bulletField.draw(self.canvas)

        self.canvas.set_clip(previousClip)

    def blitCentered(self, surface: pygame.Surface, center: Vector2) -> None:
        """把贴图以**中心点**对齐画到 center 处。

        不能直接 blit(position)——blit 的第二个参数是左上角，而 position 是
        中心点。也不能用 position - halfSize：经 pygame.transform.rotate 之后
        外接矩形会变大（实测 16×16 转到 45° 变成 22×22），那样算会偏出 3px 以上。
        用 surface 自己的 rect 做 center 对齐，任何尺寸与角度都准。
        """
        self.canvas.blit(surface, surface.get_rect(center=center.toTuple()))

    def drawPlayer(self) -> None:
        # 无敌期间立绘闪烁。没有这一条的话「现在是不是无敌」肉眼看不出来，
        # 而刚复活、刚放完炸弹时玩家最需要知道的就是这件事。
        if not self.player.isVisible():
            return

        self.blitCentered(self.player.currentFrame(), self.player.position)

        # 判定点只在**低速**时画（规格 §6.2）。常态下 4px 的判定点会一直
        # 悬在立绘中间，反而干扰视线；按住 Shift 才显示，正好配上「慢下来精确躲弹」。
        if self.player.slow and self.player.isAlive():
            self.blitCentered(self.hitboxSprite, self.player.position)

    def drawEnemies(self) -> None:
        self.enemyField.draw(self.canvas)

    def drawBossBar(self) -> None:
        boss = self.enemyField.boss
        if boss is None:
            return
        bossBar.drawBossBar(
            self.canvas,
            boss.name,
            boss.hp,
            boss.maxHp,
            boss.segments,
            boss.phaseIndex,
        )

    def blitToWindow(self) -> None:
        presentCanvas(self.window, self.canvas, self.window.get_size())


class Application:
    """窗口、场景、设置和单局游戏会话的拥有者。"""

    def __init__(self, settingsPathOverride: Path | None = None) -> None:
        pygame.init()
        # 启动时使用原生逻辑尺寸，给窗口边框、任务栏和用户拖拽留出空间。
        # 画面会在 VIDEORESIZE 后按窗口实际大小重新缩放。
        self.windowSize = (constants.LOGICAL_WIDTH, constants.LOGICAL_HEIGHT)
        self.windowedSize = self.windowSize
        self.settingsPathOverride = settingsPathOverride
        self.settings = loadSettings(settingsPathOverride)
        self.window = self._createWindow()
        pygame.display.set_caption("TouhouProject")
        pygame.key.stop_text_input()
        self.canvas = pygame.Surface((constants.LOGICAL_WIDTH, constants.LOGICAL_HEIGHT)).convert()
        self.titleBackground = pygame.image.load(
            str(assetPath(*TITLE_BACKGROUND_PATH_PARTS))
        ).convert()
        self.audio = AudioManager(self.settings)
        self.audio.playMusic("title")
        self.scene = Scene.TITLE
        self.running = True
        self.clock = pygame.time.Clock()
        self.game: Game | None = None
        self.tutorial: TutorialController | None = None
        self.pausedScene = Scene.PLAYING
        self.titleMenu = menuUi.Menu(
            (
                menuUi.MenuItem("START", "start"),
                menuUi.MenuItem("TUTORIAL", "tutorial"),
                menuUi.MenuItem("OPTION", "options"),
                menuUi.MenuItem("QUIT", "quit"),
            )
        )
        self.optionsMenu = menuUi.OptionsMenu(self.settings)
        self.pauseMenu = menuUi.Menu(
            (
                menuUi.MenuItem("CONTINUE", "continue"),
                menuUi.MenuItem("RESTART", "restart"),
                menuUi.MenuItem("RETURN TO TITLE", "title"),
                menuUi.MenuItem("QUIT", "quit"),
            )
        )
        self.resultMenu = menuUi.Menu(
            (
                menuUi.MenuItem("RESTART", "restart"),
                menuUi.MenuItem("RETURN TO TITLE", "title"),
                menuUi.MenuItem("QUIT", "quit"),
            )
        )
        self.previousBoss: Boss | None = None
        self.previousPlayerState: State | None = None
        self.previousShotCount = 0
        self.previousBombs = 0

    def _createWindow(self) -> pygame.Surface:
        if self.settings.fullscreen:
            window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            self.windowSize = window.get_size()
            return window
        self.windowSize = self.windowedSize
        return pygame.display.set_mode(self.windowedSize, pygame.RESIZABLE)

    def run(self) -> None:
        while self.running:
            realDeltaSeconds = self.clock.tick(constants.FPS) / 1000.0
            self.handleEvents()
            if self.scene in (Scene.PLAYING, Scene.TUTORIAL) and self.game is not None:
                for _ in range(self.game.accumulator.advance(realDeltaSeconds)):
                    self.update()
            self.render()

    def startGame(self) -> None:
        self.game = Game(self.window, self.canvas)
        self.tutorial = None
        self.scene = Scene.PLAYING
        self._resetSessionInput()
        self.previousBoss = None
        self.previousPlayerState = self.game.player.state
        self.previousShotCount = len(self.game.shots)
        self.previousBombs = self.game.player.bombs
        self.audio.playMusic("stage")

    def startTutorial(self) -> None:
        self.game = Game(self.window, self.canvas, assetPath(*TUTORIAL_LEVEL_PATH_PARTS))
        self.tutorial = TutorialController()
        self.scene = Scene.TUTORIAL
        self._resetSessionInput()
        self.previousBoss = None
        self.previousPlayerState = self.game.player.state
        self.previousShotCount = len(self.game.shots)
        self.previousBombs = self.game.player.bombs
        self.audio.playMusic("stage")

    def restartGame(self) -> None:
        self.startGame()

    def returnToTitle(self) -> None:
        if self.game is not None:
            self._resetSessionInput()
        self.game = None
        self.tutorial = None
        self.scene = Scene.TITLE
        self.audio.playMusic("title")

    def _resetSessionInput(self) -> None:
        if self.game is None:
            return
        self.game.accumulator.reset()
        self.game.pressLatch.pending = 0

    def handleEvents(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                continue
            if event.type == pygame.VIDEORESIZE and not self.settings.fullscreen:
                self.windowSize = (max(1, event.w), max(1, event.h))
                self.windowedSize = self.windowSize
                self.window = pygame.display.set_mode(self.windowSize, pygame.RESIZABLE)
                if self.game is not None:
                    self.game.window = self.window
                continue
            if event.type != pygame.KEYDOWN:
                continue
            self._handleKey(event.key)

    def _handleKey(self, key: int) -> None:
        if self.scene is Scene.TITLE:
            self._handleTitleKey(key)
        elif self.scene is Scene.OPTIONS:
            self._handleOptionsKey(key)
        elif self.scene is Scene.PLAYING:
            if key == pygame.K_ESCAPE:
                self.pausedScene = Scene.PLAYING
                self.scene = Scene.PAUSED
                self._resetSessionInput()
                self.audio.playSound("cancel")
            elif key == pygame.K_x and self.game is not None:
                self.game.pressLatch.record()
        elif self.scene is Scene.TUTORIAL:
            self._handleTutorialKey(key)
        elif self.scene is Scene.PAUSED:
            self._handlePauseKey(key)
        elif self.scene in (Scene.GAME_OVER, Scene.STAGE_CLEAR):
            self._handleResultKey(key)

    def _handleTitleKey(self, key: int) -> None:
        previous = self.titleMenu.selectedIndex
        action = self.titleMenu.handleKey(key)
        self._playMenuFeedback(previous, self.titleMenu.selectedIndex, action)
        if action == "start":
            self.startGame()
        elif action == "tutorial":
            self.startTutorial()
        elif action == "options":
            self.scene = Scene.OPTIONS
        elif action == "quit" or action == "back":
            self.running = False

    def _handleOptionsKey(self, key: int) -> None:
        previous = self.optionsMenu.selectedIndex
        action, settings = self.optionsMenu.handleKey(key)
        self._playMenuFeedback(previous, self.optionsMenu.selectedIndex, action)
        if action == "settingsChanged":
            fullscreenChanged = settings.fullscreen != self.settings.fullscreen
            self.settings = settings
            saveSettings(settings, self.settingsPathOverride)
            self.audio.applySettings(settings)
            if fullscreenChanged:
                self.window = self._createWindow()
                if self.game is not None:
                    self.game.window = self.window
        elif action == "back":
            self.scene = Scene.TITLE

    def _handlePauseKey(self, key: int) -> None:
        previous = self.pauseMenu.selectedIndex
        action = self.pauseMenu.handleKey(key)
        self._playMenuFeedback(previous, self.pauseMenu.selectedIndex, action)
        if action == "continue" or action == "back":
            self.scene = self.pausedScene
            self._resetSessionInput()
        elif action == "restart":
            if self.pausedScene is Scene.TUTORIAL:
                self.startTutorial()
            else:
                self.restartGame()
        elif action == "title":
            self.returnToTitle()
        elif action == "quit":
            self.running = False

    def _handleResultKey(self, key: int) -> None:
        previous = self.resultMenu.selectedIndex
        action = self.resultMenu.handleKey(key)
        self._playMenuFeedback(previous, self.resultMenu.selectedIndex, action)
        if action == "restart":
            self.restartGame()
        elif action == "title" or action == "back":
            self.returnToTitle()
        elif action == "quit":
            self.running = False

    def _handleTutorialKey(self, key: int) -> None:
        if self.tutorial is None or self.game is None:
            return
        if self.tutorial.completed:
            if key in (pygame.K_z, pygame.K_RETURN):
                self.startGame()
            elif key in (pygame.K_x, pygame.K_ESCAPE):
                self.returnToTitle()
            return

        self.tutorial.observeKey(key)
        if key == pygame.K_ESCAPE:
            self.pausedScene = Scene.TUTORIAL
            self.scene = Scene.PAUSED
            self._resetSessionInput()
            self.audio.playSound("cancel")
        elif key == pygame.K_x:
            self.game.pressLatch.record()

    def _playMenuFeedback(self, before: int, after: int, action: str | None) -> None:
        if before != after:
            self.audio.playSound("select")
        elif action == "back":
            self.audio.playSound("cancel")
        elif action is not None:
            self.audio.playSound("confirm")

    def update(self) -> None:
        if self.scene in (Scene.PLAYING, Scene.TUTORIAL) and self.game is not None:
            self.game.update()
            self._syncGameplayAudio()
            if self.scene is Scene.TUTORIAL:
                return
            if self.game.player.state is State.DEAD:
                self.scene = Scene.GAME_OVER
                self._resetSessionInput()
            elif self.game.isStageClear():
                self.scene = Scene.STAGE_CLEAR
                self._resetSessionInput()

    def _syncGameplayAudio(self) -> None:
        if self.game is None:
            return
        player = self.game.player
        if len(self.game.shots) > self.previousShotCount:
            self.audio.playSound("shot")
        if player.bombs < self.previousBombs:
            self.audio.playSound("bomb")
        if player.state is not self.previousPlayerState:
            if player.state is State.DYING:
                self.audio.playSound("damage")
            elif player.state in (State.RESPAWNING, State.DEAD):
                self.audio.playSound("death")
        if self.game.enemyField.boss is not None and self.previousBoss is None:
            self.audio.playMusic("boss")

        self.previousShotCount = len(self.game.shots)
        self.previousBombs = player.bombs
        self.previousPlayerState = player.state
        self.previousBoss = self.game.enemyField.boss

    def render(self) -> None:
        if self.scene is Scene.TITLE:
            menuUi.drawTitle(self.canvas, self.titleBackground, self.titleMenu)
        elif self.scene is Scene.OPTIONS:
            menuUi.drawTitle(self.canvas, self.titleBackground, self.optionsMenu)
        elif self.game is not None:
            self.game.render(present=False)
            if self.scene is Scene.TUTORIAL and self.tutorial is not None:
                menuUi.drawTutorialPrompt(
                    self.canvas, self.tutorial.currentPrompt, self.tutorial.completed
                )
            elif self.scene is Scene.PAUSED:
                menuUi.drawOverlayMenu(self.canvas, "PAUSE", self.pauseMenu)
            elif self.scene is Scene.GAME_OVER:
                menuUi.drawOverlayMenu(self.canvas, "GAME OVER", self.resultMenu)
            elif self.scene is Scene.STAGE_CLEAR:
                menuUi.drawOverlayMenu(self.canvas, "STAGE CLEAR", self.resultMenu)
        presentCanvas(self.window, self.canvas, self.windowSize)

    def close(self) -> None:
        self.audio.close()
        menuUi.releaseCaches()
        hud.releaseCaches()


def main() -> None:
    application = Application()
    try:
        application.run()
    finally:
        application.close()
        pygame.quit()


if __name__ == "__main__":
    # 不能写 sys.exit(main())——main() 声明返回 None，mypy strict 会报
    # func-returns-value。直接调用即可，进程正常退出。
    main()
