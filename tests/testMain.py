"""主程序的无头集成测试。

规格 8.5 把测试策略分三层，这是第三层（引擎层）：以 dummy 驱动无头运行，
验证真实行为而不做像素级对比。main.py 此前是项目里唯一没有任何自动化
覆盖的文件——这一层就是为它留的。dummy 驱动下 set_mode 不需要显示器，
子代理环境里也一样能跑。

这里的测试断言的是行为而非「没崩溃」：走满累积器给出的步数、速度档位、
边界钳制、裁剪守卫、退出条件。缩放倍率一律钉死为 1，不依赖 dummy 驱动
报告的显示尺寸。
"""

import random
from dataclasses import replace

import pygame
import pytest
from tests.game.conftest import makeBossSpawn

from touhou import constants
from touhou import main as mainModule
from touhou.core.input import FrameInput
from touhou.core.settings import loadSettings
from touhou.core.vector2 import Vector2
from touhou.game.enemyField import EnemyField
from touhou.game.entities.boss import Boss
from touhou.game.entities.enemy import Enemy
from touhou.game.entities.player import State
from touhou.game.levelData import EnemySpawn
from touhou.ui import bossBar, hud

# 游戏区下沿与逻辑分辨率底边之间那条 16px 的边带
BAND_BELOW_PLAYFIELD = pygame.Rect(
    constants.PLAYFIELD_X,
    constants.PLAYFIELD_Y + constants.PLAYFIELD_HEIGHT,
    constants.PLAYFIELD_WIDTH,
    constants.LOGICAL_HEIGHT - constants.PLAYFIELD_Y - constants.PLAYFIELD_HEIGHT,
)


@pytest.fixture
def game(monkeypatch) -> mainModule.Game:
    monkeypatch.setattr(mainModule, "chooseScaleFactor", lambda *args: 1)
    return mainModule.Game()


@pytest.fixture
def application(monkeypatch, tmp_path) -> mainModule.Application:
    monkeypatch.setattr(mainModule, "chooseScaleFactor", lambda *args: 1)
    app = mainModule.Application(settingsPathOverride=tmp_path / "settings.json")
    yield app
    app.close()


def testApplicationStartsAtTitle(application):
    assert application.scene is mainModule.Scene.TITLE
    assert application.game is None


def testApplicationStartsAtLogicalSizeInsteadOfFillingDesktop(monkeypatch, tmp_path):
    monkeypatch.setattr(mainModule, "chooseScaleFactor", lambda *args: 3)
    app = mainModule.Application(settingsPathOverride=tmp_path / "settings.json")
    try:
        assert app.windowedSize == (constants.LOGICAL_WIDTH, constants.LOGICAL_HEIGHT)
        assert app.windowSize == app.windowedSize
    finally:
        app.close()


def testStartingAndRestartingCreateFreshGameSessions(application):
    application.startGame()
    first = application.game
    assert application.scene is mainModule.Scene.PLAYING

    application.restartGame()

    assert application.scene is mainModule.Scene.PLAYING
    assert application.game is not first


def testEscapePausesAndContinuePreservesSession(application):
    application.startGame()
    session = application.game
    postKeydown(pygame.K_ESCAPE)
    application.handleEvents()
    assert application.scene is mainModule.Scene.PAUSED

    postKeydown(pygame.K_z)
    application.handleEvents()

    assert application.scene is mainModule.Scene.PLAYING
    assert application.game is session


def testPausedApplicationDoesNotAdvanceTheGame(application):
    application.startGame()
    assert application.game is not None
    application.scene = mainModule.Scene.PAUSED
    before = application.game.backgroundOffset

    application.update()

    assert application.game.backgroundOffset == before


def testReturningToTitleDropsSessionAndPendingInput(application):
    application.startGame()
    assert application.game is not None
    application.game.pressLatch.record()
    application.game.accumulator.advance(constants.STEP_SECONDS / 2)

    application.returnToTitle()

    assert application.scene is mainModule.Scene.TITLE
    assert application.game is None


def testOptionsChangesAreAppliedAndSaved(application):
    postKeydown(pygame.K_DOWN)
    postKeydown(pygame.K_z)
    application.handleEvents()
    assert application.scene is mainModule.Scene.OPTIONS

    postKeydown(pygame.K_RIGHT)
    application.handleEvents()

    saved = loadSettings(application.settingsPathOverride)
    assert saved.bgmVolume == 8
    assert application.audio.settings.bgmVolume == 8


@pytest.mark.parametrize(
    ("windowSize", "expected"),
    [
        ((1280, 960), pygame.Rect(0, 0, 1280, 960)),
        ((1500, 1000), pygame.Rect(110, 20, 1280, 960)),
        ((320, 200), pygame.Rect(27, 0, 266, 200)),
    ],
)
def testCanvasDestinationIsCenteredAndNeverCropped(windowSize, expected):
    assert mainModule.canvasDestination(windowSize) == expected


def testResizeEventUpdatesWindowSize(application):
    pygame.event.post(pygame.event.Event(pygame.VIDEORESIZE, size=(900, 700), w=900, h=700))
    application.handleEvents()
    assert application.windowSize == (900, 700)
    assert application.windowedSize == (900, 700)


def testFullscreenRoundTripRestoresWindowedSize(application, monkeypatch):
    application.windowSize = (900, 700)
    application.windowedSize = (900, 700)
    calls = []

    def fakeSetMode(size, flags=0):
        calls.append((size, flags))
        return pygame.Surface((1920, 1080) if flags & pygame.FULLSCREEN else size)

    monkeypatch.setattr(pygame.display, "set_mode", fakeSetMode)
    application.settings = replace(application.settings, fullscreen=True)
    application._createWindow()
    application.settings = replace(application.settings, fullscreen=False)
    application._createWindow()

    assert calls[-1] == ((900, 700), pygame.RESIZABLE)


def testShippedMenuLabelsUseGlyphsAvailableInBundledFont(application):
    menus = (
        application.titleMenu,
        application.optionsMenu,
        application.pauseMenu,
        application.resultMenu,
    )
    labels = tuple(item.label for menu in menus for item in menu.items)

    assert labels
    assert all(label.isascii() for label in labels)


def testLastDeathMovesToGameOver(application):
    application.startGame()
    assert application.game is not None
    application.game.player.state = State.DEAD

    application.update()

    assert application.scene is mainModule.Scene.GAME_OVER


def testGapBetweenWavesIsNotStageClear(game):
    game.enemyField.active.clear()
    game.enemyField.spawnCursor = 0
    assert not game.isStageClear()


def testExhaustedLevelMovesToStageClear(application):
    application.startGame()
    assert application.game is not None
    game = application.game
    game.enemyField.spawnCursor = len(game.enemyField.spawns)
    game.enemyField.bossCursor = len(game.enemyField.bossSpawns)
    game.enemyField.active.clear()
    game.enemyField.boss = None
    game.enemyField.elapsedFrames = int(game.level.durationFrames)

    application.update()

    assert application.scene is mainModule.Scene.STAGE_CLEAR


@pytest.mark.parametrize("resultScene", [mainModule.Scene.GAME_OVER, mainModule.Scene.STAGE_CLEAR])
def testResultMenuCanRestartWithAFreshSession(application, resultScene):
    application.startGame()
    previous = application.game
    application.scene = resultScene

    postKeydown(pygame.K_z)
    application.handleEvents()

    assert application.scene is mainModule.Scene.PLAYING
    assert application.game is not previous


def testResultMenuCanReturnToTitle(application):
    application.startGame()
    application.scene = mainModule.Scene.GAME_OVER
    postKeydown(pygame.K_DOWN)
    postKeydown(pygame.K_z)

    application.handleEvents()

    assert application.scene is mainModule.Scene.TITLE
    assert application.game is None


def testNewSessionStartsStageMusic(application):
    application.startGame()
    assert application.audio.currentMusic == "stage"


def testBossArrivalSwitchesToBossMusic(application):
    application.startGame()
    assert application.game is not None

    def activeScript(boss):
        boss.hp = boss.maxHp = 100
        while True:
            yield

    boss = Boss(makeBossSpawn(script=activeScript))
    application.game.enemyField.active.append(boss)
    application.game.enemyField.boss = boss
    application.game.player.invincibleFrames = 9999

    application.update()
    application.update()

    assert application.audio.currentMusic == "boss"


def testGameDisablesTextInputForTheWindow(monkeypatch):
    """建窗口时必须关掉 SDL 的文本输入通道，否则中文输入法会截走按键。

    症状是「按一下 A 之后方向键全部失灵」——玩家按下字母键后输入法对窗口生效，
    `pygame.key.get_pressed()` 不再上报按键状态，而 Shift 或切英文输入法就恢复。
    pygame 建窗口时**默认开启**文本输入，所以这行不写就是这样。

    这条测试看起来只是「调没调那个函数」，但它守的是一个**在多数机器上复现不出来**
    的 bug：没有输入法的人测不出问题，删掉那一行的重构也不会变红。
    """
    calls = []
    monkeypatch.setattr(mainModule.pygame.key, "stop_text_input", lambda: calls.append(1))
    monkeypatch.setattr(mainModule, "chooseScaleFactor", lambda *args: 1)

    mainModule.Game()

    assert calls == [1], "Game() 应当调用一次 pygame.key.stop_text_input()"


def testPlayerAdvancesByNormalSpeedPerStep(game, monkeypatch):
    """一次逻辑步推进 PLAYER_SPEED_NORMAL，步数由累积器给出。"""
    monkeypatch.setattr(mainModule, "readKeyboardInput", lambda pressed: FrameInput(right=True))
    startX = game.player.position.x

    steps = game.accumulator.advance(2 * constants.STEP_SECONDS)
    assert steps == 2, "累积器应该正好给出 2 步"
    for _ in range(steps):
        game.update()

    assert game.player.position.x == pytest.approx(startX + steps * constants.PLAYER_SPEED_NORMAL)


def testSlowModeUsesSlowSpeed(game, monkeypatch):
    monkeypatch.setattr(
        mainModule, "readKeyboardInput", lambda pressed: FrameInput(right=True, slow=True)
    )
    startX = game.player.position.x
    game.update()
    assert game.player.position.x == pytest.approx(startX + constants.PLAYER_SPEED_SLOW)


def testHoldingDirectionClampsPlayerToPlayfieldEdge(game, monkeypatch):
    """按住方向足够久，自机必须停在游戏区边缘而不是飞出去。"""
    monkeypatch.setattr(
        mainModule, "readKeyboardInput", lambda pressed: FrameInput(right=True, up=True)
    )
    for _ in range(500):
        game.update()

    halfWidth = game.player.spriteSheet.frameWidth / 2
    halfHeight = game.player.spriteSheet.frameHeight / 2
    assert game.player.position.x == pytest.approx(
        constants.PLAYFIELD_X + constants.PLAYFIELD_WIDTH - halfWidth
    )
    assert game.player.position.y == pytest.approx(constants.PLAYFIELD_Y + halfHeight)


def testBandBelowPlayfieldStaysFreeOfBackgroundAfterScrolling(game):
    """游戏区下沿的边带不能被滚动的背景渗入。

    无缝滚动要把背景画两遍，第二遍的 y 坐标会一路排到游戏区底边之外；
    drawPlayfield 里的 set_clip 是唯一挡住它的东西。把滚动偏移设大到
    足以盖住整条边带，再比较渲染前后边带的字节——背景像素一旦渗入，
    字节必然变化。被改坏的代码不会崩溃，只会把画面弄脏，所以只能这么测。
    """
    band = game.canvas.subsurface(BAND_BELOW_PLAYFIELD)
    before = pygame.image.tobytes(band, "RGB")

    game.backgroundOffset = 300.0  # 第二遍 blit 将覆盖整条边带
    game.render()

    assert pygame.image.tobytes(band, "RGB") == before


def testEscapeStopsTheGame(game):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    game.handleEvents()
    assert not game.running


def testMainExitsCleanlyWhenQuitIsQueued(monkeypatch):
    """队列里放一个 QUIT，main() 应该跑完一帧循环后干净地返回。"""
    monkeypatch.setattr(mainModule, "chooseScaleFactor", lambda *args: 1)
    pygame.event.post(pygame.event.Event(pygame.QUIT))

    mainModule.main()  # 正常返回即通过；抛异常会直接失败
    assert not pygame.get_init(), "main() 退出后应该调用 pygame.quit()"

    # 恢复 conftest 建立的 pygame 状态，避免影响之后的测试
    pygame.init()
    pygame.display.set_mode((1, 1))


# —— 敌机与弹幕的接线 ——


def firstEnemyFrame(game) -> float:
    return game.level.spawns[0].frame


def testEnemiesAppearOnScheduleAndMove(game):
    """按关卡的出生时刻表放出敌机，并且它们真的在飞。

    这条同时守住了「时刻比较用的是逻辑帧而不是真实时间」：真实时间里这几百次
    update() 几乎不耗时，若拿真实时间比，一个敌人都不会出生。
    """
    appearAt = int(firstEnemyFrame(game))
    for _ in range(appearAt - 1):
        game.update()
    assert len(game.enemyField) == 0, f"第一个敌人第 {appearAt} 帧才出场"

    game.update()
    assert len(game.enemyField) >= 1

    for _ in range(30):
        game.update()
    positions = [enemy.position for enemy in game.enemyField.active]
    game.update()
    assert [enemy.position for enemy in game.enemyField.active] != positions, "敌机应当在移动"


def testEnemiesFireRealBarragesAtTheirScheduledFrames(game):
    """端到端验收：敌机真的按自己的时刻表打出弹幕。

    跑到第一波敌人的第一次攻击之后，场上必须出现子弹——而且**不是**临时生成器
    打的（那个已经删了）。炮口时刻取自关卡数据：第一个敌人的第一波在
    出生后 `attacks[0].frame` 帧。
    """
    spawn = game.level.spawns[0]
    assert spawn.attacks, "第一个敌人应当带着攻击参数"
    fireOnFrame = int(spawn.frame + spawn.attacks[0].frame)

    for _ in range(fireOnFrame - 1):
        game.update()
    assert len(game.bulletField) == 0, f"第 {fireOnFrame} 帧才开火"

    game.update()
    assert len(game.bulletField) > 0, f"第 {fireOnFrame} 帧应当已经开火"


def testTemporaryEmitterIsGone(game):
    """上一轮那段临时生成器要删干净，不能留着让人以为还在用。"""
    assert not hasattr(game, "emitTemporaryDanmaku")
    assert not any(name.startswith("EMITTER_") for name in vars(mainModule))


def testEnemiesDoNotBleedBelowThePlayfield(game):
    """敌机不许画进游戏区下沿之外的那条 16px 边带。

    边带是唯一没被别的绘制覆盖的区域（右侧 HUD 条会被 drawHud 重刷一遍），
    渗进去就是永久脏点。
    """
    game.render()
    band = game.canvas.subsurface(BAND_BELOW_PLAYFIELD)
    before = pygame.image.tobytes(band, "RGB")

    game.enemyField.active.append(
        Enemy(
            EnemySpawn(
                frame=0.0,
                enemyType=game.level.spawns[0].enemyType,
                path=(Vector2(200.0, 460.0),),
                durationFrames=60.0,
                hp=1,
                clearOnDeath=False,
                attacks=(),
            )
        )
    )
    game.render()

    assert pygame.image.tobytes(band, "RGB") == before


def testBulletsDoNotBleedBelowThePlayfield(game):
    """子弹不许画进游戏区下沿之外的那条 16px 边带。

    边带是唯一没被别的绘制覆盖的区域：右侧 HUD 条会被 drawHud 重刷一遍，
    所以往那里画漏了也看不出来；边带不会，渗进去就是永久脏点。
    子弹在 (200, 460) 生成——贴图半高 8px，正好有一半落在边带里。
    """
    game.render()
    band = game.canvas.subsurface(BAND_BELOW_PLAYFIELD)
    before = pygame.image.tobytes(band, "RGB")

    bulletSpec = game.level.spawns[0].attacks[0].params.bullet
    game.bulletField.spawn(bulletSpec, Vector2(200.0, 460.0), 0, 0)
    game.render()

    assert pygame.image.tobytes(band, "RGB") == before


# —— 炸弹的边沿输入（事件 → 闩锁 → 逻辑步）——


def postKeydown(key: int) -> None:
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key))


def testBombPressIsTakenByExactlyOneLogicStep(game, monkeypatch):
    """一帧跑 3 步时，同一次按下只能算一次。

    `MAX_STEPS_PER_FRAME` 是 5，卡顿之后补帧那一帧会连跑好几步。把事件直接
    填进当帧的输入的话，这一次按下会在三步里各放一个炸弹——按一下放三个。
    """
    calls = []
    monkeypatch.setattr(mainModule.Player, "useBomb", lambda self, *args: calls.append(1))

    postKeydown(pygame.K_x)
    game.handleEvents()

    steps = game.accumulator.advance(3 * constants.STEP_SECONDS)
    assert steps == 3, "这一帧该跑 3 步"
    for _ in range(steps):
        game.update()

    assert calls == [1], f"一次按下应当只走一次炸弹，实际 {len(calls)} 次"


def testBombPressSurvivesAFrameWithNoLogicStep(game):
    """一帧跑 0 步时，按下的 X 不能被丢掉。

    渲染帧率高于逻辑帧率时（或者卡顿之后），确实会出现「这一帧一步都不跑」。
    事件按帧消费、逻辑按步执行，两者对不上就会丢按键——而死亡炸弹的窗口
    只有 8 帧，丢一次按下就是白掉一条命。
    """
    game.player.enterDying()
    postKeydown(pygame.K_x)
    game.handleEvents()
    # 这一帧一步都没跑 —— 按键必须还在闩锁里等着
    assert game.pressLatch.pending == 1

    game.update()

    assert game.player.state is State.ALIVE
    assert game.player.lives == constants.START_LIVES


def testHeldBombKeyDoesNotDrainTheStock(game, monkeypatch):
    """按住 X 不放，炸弹一个都不该放。

    `readKeyboardInput` 给的 bomb 是「现在按着」，而炸弹要的是「刚刚按下过」。
    少了闩锁那一步，按住 X 会每帧放一个（180 帧无敌一过又是一个），
    几秒就能把库存放空。
    """
    monkeypatch.setattr(mainModule, "readKeyboardInput", lambda pressed: FrameInput(bomb=True))

    for _ in range(300):
        game.update()

    assert game.player.bombs == constants.START_BOMBS


# —— 自机的攻防（端到端）——


def stationaryEnemyAt(position: Vector2, game, hp: int) -> Enemy:
    return Enemy(
        EnemySpawn(
            frame=0.0,
            enemyType=game.level.spawns[0].enemyType,
            path=(Vector2(position.x, position.y),),
            durationFrames=600.0,
            hp=hp,
            clearOnDeath=False,
            attacks=(),
        )
    )


def testHoldingFireKillsAnEnemyAboveThePlayer(game, monkeypatch):
    """按住 Z，正上方的敌机被消灭。

    敌机场换成空的，只留一架停在自机正上方：关卡里的敌人会开火，而这条测的是
    「自机子弹 → 敌机掉血 → 敌机离场」这条线，不该让别的变量搅进来。
    """
    monkeypatch.setattr(mainModule, "readKeyboardInput", lambda pressed: FrameInput(shoot=True))
    game.enemyField = EnemyField((), random.Random(0))
    enemy = stationaryEnemyAt(
        Vector2(game.player.position.x, game.player.position.y - 120), game, hp=3
    )
    game.enemyField.active.append(enemy)

    for _ in range(60):
        game.update()

    assert enemy.isDead(), f"按住 Z 打了 60 帧，3 血敌机还剩 {enemy.hp} 血"
    assert len(game.enemyField) == 0, "死掉的敌机必须立刻离场，不能多留一帧"


def testShotsFlyUpAndAreRecycledOffscreen(game, monkeypatch):
    """自机子弹朝上飞，飞出游戏区后被回收——不是每帧无限堆积。"""
    monkeypatch.setattr(mainModule, "readKeyboardInput", lambda pressed: FrameInput(shoot=True))
    game.enemyField = EnemyField((), random.Random(0))

    for _ in range(120):
        game.update()
        assert len(game.shots) < 60, "子弹没有被回收，池子会一直涨"

    assert len(game.shots) == 0 or all(b.velocity.y < 0 for b in game.shots.active)


def testEnemyBulletCostsALife(game):
    """敌弹打中判定点：8 帧死亡炸弹窗口走完，残机 -1。"""
    enemyBulletSpec = game.level.spawns[0].attacks[0].params.bullet
    game.bulletField.spawn(enemyBulletSpec, game.player.position, 0, 0)

    game.update()
    assert game.player.state is State.DYING, "先给 8 帧死亡炸弹的机会，不立刻扣残机"
    assert game.player.lives == constants.START_LIVES

    for _ in range(constants.DEATHBOMB_WINDOW_FRAMES + 1):
        game.update()

    assert game.player.lives == constants.START_LIVES - 1
    assert game.player.isInvincible(), "复活之后应当有一段无敌"


def testWalkingIntoAnEnemyCostsALife(game, monkeypatch):
    """端到端：自机撞到敌机机体上会被撞死，走完死亡窗口后残机 -1。

    敌机场换成空的、只留一架停在自机正右方：关卡里的敌人会开火，而这条测的是
    「机体接触」这一条线。自机一直往右走，走到贴上为止。
    """
    monkeypatch.setattr(mainModule, "readKeyboardInput", lambda pressed: FrameInput(right=True))
    game.enemyField = EnemyField((), random.Random(0))
    # 走 20 帧就够贴上去（每帧 6.17px，敌机机体半径 12.8 + 判定点 2）
    game.enemyField.active.append(
        stationaryEnemyAt(Vector2(game.player.position.x + 100, game.player.position.y), game, hp=1)
    )

    game.update()
    for _ in range(30):
        game.update()
        if game.player.state is State.DYING:
            break
    assert game.player.state is State.DYING, "撞上去了却没死"

    for _ in range(constants.DEATHBOMB_WINDOW_FRAMES + 1):
        game.update()

    assert game.player.lives == constants.START_LIVES - 1


# —— 死亡冲击波（端到端）——


def testDeathShockwaveClearsBulletsAndKillsMobs(game, monkeypatch):
    """被弹打死：出特效、清空敌弹、一血小怪被秒——三件事同一帧。

    敌机场换成空的，只放一架停在自机正上方的一血小怪：关卡里的敌人会开火，
    而这条测的是「死亡 → 冲击波」这一条线。
    """
    monkeypatch.setattr(mainModule, "readKeyboardInput", lambda pressed: FrameInput())
    game.enemyField = EnemyField((), random.Random(0))
    mob = stationaryEnemyAt(
        Vector2(game.player.position.x, game.player.position.y - 120), game, hp=1
    )
    game.enemyField.active.append(mob)
    enemyBulletSpec = game.level.spawns[0].attacks[0].params.bullet
    for index in range(4):
        game.bulletField.spawn(enemyBulletSpec, Vector2(100 + 10 * index, 200), 0, 0)
    deathPlace = Vector2(game.player.position.x, game.player.position.y)
    # 一颗压在自机判定点上的敌弹，保证这一帧就被打死
    game.bulletField.spawn(enemyBulletSpec, game.player.position, 0, 0)

    for _ in range(constants.DEATHBOMB_WINDOW_FRAMES + 2):
        game.update()

    assert game.player.state is State.RESPAWNING, "前提：真的死了"
    assert len(game.effects) == 1, "该放一个死亡特效"
    assert game.effects.active[0].position == deathPlace, "而且炸在死亡的位置"
    assert len(game.bulletField) == 0, "敌弹该被清空"
    assert len(game.enemyField) == 0, "一血小怪该被冲击波秒掉"


def testDeathEffectIsDrawnOnTheCanvas(game):
    """死亡特效真的画在画面上。

    与自机子弹那条同一个道理：少一个 draw 调用的话，逻辑测试全绿而画面上一片
    空白。两次 render 之间不调 update（背景不滚动），所以这个区域变了就只能是
    特效。
    """
    rect = pygame.Rect(0, 0, 120, 120)
    rect.center = game.player.position.toTuple()

    game.render()
    before = pygame.image.tobytes(game.canvas.subsurface(rect), "RGB")

    game.effects.spawn(
        game.player.deathEffectFrames, game.player.position, game.player.deathEffectFramesPerFrame
    )
    game.render()
    after = pygame.image.tobytes(game.canvas.subsurface(rect), "RGB")

    assert before != after, "死亡特效没有被画出来"


def testDeathEffectExpires(game, monkeypatch):
    """特效放完就消失——不然每死一次就多一层永远擦不掉的环叠在画面上。

    这条同时守着 `Game.update` 里那句 `effects.update()`：漏掉它的话特效会
    永远停在第一帧，也不会被回收。

    等多少帧**不写成 `DEATH_EFFECT_FRAMES`**：那是「本来该放多久」，而这里要
    断言的是「迟早会回收」。写成同一个常量的话，帧数与张数的配比一变（比如
    张数多于帧数、每张至少播一帧），断言就会跟着变得时对时错。
    """
    monkeypatch.setattr(mainModule, "readKeyboardInput", lambda pressed: FrameInput())
    game.player.enterDying()
    for _ in range(constants.DEATHBOMB_WINDOW_FRAMES + 2):
        game.update()
    assert len(game.effects) == 1, "前提：这会儿刚放出来"

    for _ in range(200):
        game.update()

    assert len(game.effects) == 0, "放完就该消失"


def testDeathEffectFramesComeFromTheRealAsset(game):
    """死亡特效的帧是从 `player_death_effect.png` 烘出来的，而且不止一帧。

    守的是「素材路径写错」与「忘了烘」：这两种情况下 `deathEffectFrames` 会是
    空的或只有一帧，特效要么不显示要么不动。
    """
    frames = game.player.deathEffectFrames
    assert len(frames) == constants.DEATH_EFFECT_BAKED_FRAMES
    sizes = [frame.get_width() for frame in frames]
    assert sizes == sorted(sizes) and sizes[0] < sizes[-1], "环要从多小扩到多大"


# —— HUD 的接线 ——


def hudRect() -> pygame.Rect:
    return pygame.Rect(hud.HUD_X, 0, hud.HUD_WIDTH, constants.LOGICAL_HEIGHT)


def testHudShowsThePlayersOwnNumbers(game):
    """HUD 画的是自机身上的数。

    与「直接用同一组数调 drawHud」的结果逐字节比较：相等就说明画上去的
    确实来自自机（写死成常量、接错字段、压根没接线都会不等）。
    """
    game.player.lives = 1
    game.player.bombs = 0
    game.player.power = 4.00
    game.render()
    painted = pygame.image.tobytes(game.canvas.subsurface(hudRect()), "RGB")

    reference = pygame.Surface((constants.LOGICAL_WIDTH, constants.LOGICAL_HEIGHT)).convert()
    hud.drawHud(reference, 1, 0, 4.00)
    expected = pygame.image.tobytes(reference.subsurface(hudRect()), "RGB")

    assert painted == expected


# —— 自机的绘制 ——


def testPlayerShotsAreDrawnOnTheCanvas(game, monkeypatch):
    """自机子弹真的画在画面上。

    这条是补的：接第二个弹幕场时，`update` 里加上了它、`drawPlayfield` 里
    漏了对应的 draw 调用——子弹在飞、在打中敌机、全部逻辑测试都绿，就是画面
    上一个像素都没有。逻辑测试看不见「少画了一样东西」，只能比像素。

    两次 render 之间**不调 update**（背景不滚动、敌机不动、敌弹不飞），
    所以除自机子弹之外画面逐字节相同；这个区域变了就只能是子弹。
    """
    monkeypatch.setattr(mainModule, "readKeyboardInput", lambda pressed: FrameInput(shoot=True))
    game.enemyField = EnemyField((), random.Random(0))

    rect = pygame.Rect(0, 0, 40, 120)
    rect.midbottom = (int(game.player.position.x), int(game.player.position.y))

    for _ in range(20):
        game.update()
    assert len(game.shots) > 0, "按住 Z 二十帧了，场上该有子弹在飞"

    game.render()
    withShots = pygame.image.tobytes(game.canvas.subsurface(rect), "RGB")

    game.shots.clear()
    game.render()
    withoutShots = pygame.image.tobytes(game.canvas.subsurface(rect), "RGB")

    assert withShots != withoutShots, "自机子弹没有被画出来"


def testDeadPlayerIsNotDrawn(game):
    """出局之后画面上不该还有自机。

    两次 render 之间不调 update，背景不会滚动，所以除自机之外画面是逐字节
    相同的——这个区域变了，只可能是自机被画上/擦掉了。
    """
    rect = pygame.Rect(0, 0, 30, 60)
    rect.center = game.player.position.toTuple()

    game.render()
    alive = pygame.image.tobytes(game.canvas.subsurface(rect), "RGB")

    game.player.state = State.DEAD
    game.render()
    dead = pygame.image.tobytes(game.canvas.subsurface(rect), "RGB")

    assert alive != dead, "出局的自机不该还画在画面上"


def testHitboxIsDrawnOnlyInSlowMode(game):
    """判定点只在低速时画（规格 §6.2）。

    立绘有 25×50 而判定点直径 4px，不画出来玩家没法判断自己站得有多准；
    但常态下一直挂着又会挡视线，所以只在按住 Shift 时显示。
    """
    rect = pygame.Rect(0, 0, 64, 64)  # 判定点贴图是 64×64 的一整张
    rect.center = game.player.position.toTuple()

    game.player.slow = False
    game.render()
    fast = pygame.image.tobytes(game.canvas.subsurface(rect), "RGB")

    game.player.slow = True
    game.render()
    slow = pygame.image.tobytes(game.canvas.subsurface(rect), "RGB")

    assert fast != slow, "按住 Shift 之后判定点应当出现"


def testMainReleasesHudCachesBeforeQuitting(monkeypatch):
    """`main()` 退出后，HUD 还能重新渲染。

    字体对象绑在 font 模块的初始化状态上，`pygame.quit()` 之后再用它渲染会抛
    "Invalid font (font module quit since font created)"。缓存恰好让这个失效的
    对象活过了 quit——不缓存反而看不出来。所以「丢缓存」是缓存的对价，
    这条测试守的就是它（删掉 main() 里那次 releaseCaches 就会红）。
    """
    hud.hudFont()  # 先把缓存焐热，不然没什么可失效
    monkeypatch.setattr(mainModule, "chooseScaleFactor", lambda *args: 1)
    pygame.event.post(pygame.event.Event(pygame.QUIT))

    mainModule.main()

    # 恢复 pygame 状态，避免影响之后的测试
    pygame.init()
    pygame.display.set_mode((1, 1))
    canvas = pygame.Surface((constants.LOGICAL_WIDTH, constants.LOGICAL_HEIGHT))
    hud.drawHud(canvas, 3, 3, 2.40)  # 不抛异常即通过


# —— 中 BOSS（端到端）——


def testBossArrivesFiresAndDiesToPlayerFire(game, monkeypatch):
    """端到端：BOSS 按时刻表出场 → 打弹幕 → 被自机打死 → 清屏 + 爆炸。

    自机在这条测试里**常驻无敌**：它要守的是 BOSS 那条线，而脚本不会躲弹，
    不无敌的话自机每几帧就被打中一次，什么都测不准。
    """
    monkeypatch.setattr(mainModule, "readKeyboardInput", lambda pressed: FrameInput(shoot=True))
    bossFrame = int(game.level.bosses[0].atFrame)

    for _ in range(bossFrame - 1):
        game.player.invincibleFrames = 9999
        game.update()
    assert game.enemyField.boss is None, f"第 {bossFrame} 帧才出场"

    game.player.invincibleFrames = 9999
    game.update()
    boss = game.enemyField.boss
    assert boss is not None, f"第 {bossFrame} 帧该出场了"
    assert boss.maxHp == 0, "出生帧不推进脚本，所以还没有本段血量"

    for _ in range(120):
        game.player.invincibleFrames = 9999
        game.update()

    assert boss.maxHp > 0, "脚本该跑起来了（runPhase 给了本段血量）"
    assert len(game.bulletField) > 0, "BOSS 该在打弹幕"
    assert boss.position.y > 0, "该已经从游戏区上方进场了"

    boss.hp = 3
    for _ in range(180):
        game.player.invincibleFrames = 9999
        game.update()
        if game.enemyField.boss is None:
            break

    assert game.enemyField.boss is None, "被打死之后该离场"
    assert len(game.bulletField) == 0, "BOSS 倒下要清屏"
    assert len(game.effects) > 0, "该有爆炸特效"


def testBossBarIsDrawnOnlyWhileTheBossIsOnField(game):
    """血条只在 BOSS 在场时画。"""

    def barBytes() -> bytes:
        game.render()
        rect = pygame.Rect(
            constants.PLAYFIELD_X,
            constants.PLAYFIELD_Y,
            constants.PLAYFIELD_WIDTH,
            bossBar.PIP_TOP + 8 - constants.PLAYFIELD_Y,
        )
        return pygame.image.tobytes(game.canvas.subsurface(rect), "RGB")

    before = barBytes()
    assert game.enemyField.boss is None

    boss = Boss(makeBossSpawn())
    # 血量是脚本第一次 runPhase 给的。这条测试要的是「血条画不画」，
    # 所以直接把那一帧之后的模样摆出来，不跑脚本。
    boss.hp = boss.maxHp = 100
    game.enemyField.active.append(boss)
    game.enemyField.boss = boss

    assert barBytes() != before, "BOSS 在场时血条应当出现"

    game.enemyField.boss = None
    assert barBytes() == before, "BOSS 走了血条该消失"


def testADefeatedBossExplodesOnTheSpot(game):
    boss = Boss(makeBossSpawn())
    boss.hp = 0
    game.enemyField.active.append(boss)
    game.enemyField.boss = boss
    game.enemyField.removeFinished()

    game.celebrateBossDefeat(boss)

    assert len(game.effects) == 1
    assert game.effects.active[0].position == boss.position, "炸在倒下的地方"


def testARetreatingBossDoesNotExplode(game):
    """脚本跑完而退场的 BOSS 不该有爆炸——只有**被打死**的才炸。

    与「飞走的敌人不掉东西」是同一条区分：退场不是战死。
    """
    boss = Boss(makeBossSpawn())
    boss.hp = boss.maxHp = 100
    boss.scriptDone = True
    game.enemyField.active.append(boss)
    game.enemyField.boss = boss
    game.enemyField.removeFinished()
    assert game.enemyField.boss is None, "前提：它真的离场了"

    game.celebrateBossDefeat(boss)

    assert len(game.effects) == 0


def testBigBulletsNeverTouchTheRotationCache(game, monkeypatch):
    """大玉不跟着速度转，所以那条 172×172 的贴图**一条旋转缓存都不该有**。

    这是内存上界那条硬约束（docs/DESIGN.md「性能」）：预旋转缓存是每张表一份、
    键里含帧号，一张 172×172 转一圈（360 个角度、每个约 240×240）就是几十 MB。
    圆球转了看不出来，所以数据里写死 `rotatesToVelocity: false`——
    这条测试守的就是那个字段没有被人顺手删掉。
    """
    monkeypatch.setattr(mainModule, "readKeyboardInput", lambda pressed: FrameInput(shoot=True))
    bossFrame = int(game.level.bosses[0].atFrame)
    # 打到「大玉」那一节（脚本里排在扇形、环弹之后）
    for _ in range(bossFrame + 700):
        game.player.invincibleFrames = 9999
        game.update()

    bigs = [b for b in game.bulletField.active if b.spriteSheet.frameWidth == 77]
    assert bigs, "这一节该在打大玉"
    for bullet in bigs:
        assert bullet.radius == pytest.approx(15.75)
        assert bullet.spriteSheet.rotatedCache == {}, "大玉进了预旋转缓存，几十 MB 就没了"
