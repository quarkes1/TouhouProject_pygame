"""game/ 层测试共用的夹具。

自机的构造与推进要不少配料（立绘、子弹规格、两个子弹场），而多数测试只关心
其中一样——移动测试不该为了走一步去造两个弹幕场。这里给齐默认值，
测试只写自己关心的那部分。

**用 fixture 而不是测试文件里的公共函数**：`tests/game/` 不是包，
跨文件 import 得靠 pytest 往 sys.path 里塞路径，那是隐式契约；
fixture 由 pytest 自己解析，同名覆盖的规则也是明摆着的。
"""

import random

import pygame
import pytest

from touhou import constants
from touhou.core.input import FrameInput
from touhou.core.spriteSheet import SpriteSheet
from touhou.core.vector2 import Vector2
from touhou.game.bulletField import BulletField
from touhou.game.effectField import EffectField
from touhou.game.enemyField import EnemyField
from touhou.game.entities.bullet import BulletSpec
from touhou.game.entities.enemy import Enemy
from touhou.game.entities.player import Player
from touhou.game.levelData import EnemySpawn, EnemyType

PLAYER_FRAME_WIDTH = 25
PLAYER_FRAME_HEIGHT = 50
PLAYER_FRAME_COUNT = 8
PLAYER_START = Vector2(200.0, 400.0)
SHOT_FRAME_SIZE = 16
ENEMY_FRAME_SIZE = 24
ENEMY_RADIUS = 12.0
ENEMY_START = Vector2(200.0, 100.0)


@pytest.fixture
def spriteSheet() -> SpriteSheet:
    """8 帧、每帧 25×50，与 marisa_forward.png 一致。"""
    surface = pygame.Surface(
        (PLAYER_FRAME_WIDTH * PLAYER_FRAME_COUNT, PLAYER_FRAME_HEIGHT), pygame.SRCALPHA
    )
    return SpriteSheet(surface, PLAYER_FRAME_WIDTH, PLAYER_FRAME_HEIGHT)


@pytest.fixture
def tiltSpriteSheet() -> SpriteSheet:
    """单帧、帧上有可见标记块的自机立绘。

    全透明帧旋转之后还是全透明，三种朝向会**字节级完全相同**，任何断言都
    测不出倾斜。要测倾斜就必须有可见像素。
    """
    surface = pygame.Surface((PLAYER_FRAME_WIDTH, PLAYER_FRAME_HEIGHT), pygame.SRCALPHA)
    surface.fill((0, 255, 0, 255), pygame.Rect(10, 0, 4, 4))  # 顶部中央的标记块
    return SpriteSheet(surface, PLAYER_FRAME_WIDTH, PLAYER_FRAME_HEIGHT)


@pytest.fixture
def shotSpec() -> BulletSpec:
    """自机子弹的规格。半径与伤害取常量，与 main.py 里那份一致。"""
    surface = pygame.Surface((SHOT_FRAME_SIZE, SHOT_FRAME_SIZE), pygame.SRCALPHA)
    return BulletSpec(
        spriteSheet=SpriteSheet(surface, SHOT_FRAME_SIZE, SHOT_FRAME_SIZE),
        radius=constants.PLAYER_SHOT_RADIUS,
        rotatesToVelocity=False,
        damage=constants.PLAYER_SHOT_DAMAGE,
    )


@pytest.fixture
def enemyBulletSpec() -> BulletSpec:
    """敌弹的规格。判定半径取「小弹」那一档，与自机子弹刻意不同——
    这样「拿错了规格」在碰撞测试里会露馅。"""
    surface = pygame.Surface((16, 16), pygame.SRCALPHA)
    return BulletSpec(
        spriteSheet=SpriteSheet(surface, 16, 16),
        radius=constants.BULLET_RADIUS_SMALL,
    )


@pytest.fixture
def enemyType() -> EnemyType:
    surface = pygame.Surface((ENEMY_FRAME_SIZE, ENEMY_FRAME_SIZE), pygame.SRCALPHA)
    return EnemyType(
        spriteSheet=SpriteSheet(surface, ENEMY_FRAME_SIZE, ENEMY_FRAME_SIZE),
        radius=ENEMY_RADIUS,
    )


@pytest.fixture
def makeEnemy(enemyType):
    """造一架**停着不动**的敌机。

    轨迹只给一个控制点、`durationFrames` 随便给：单点轨迹每帧的参数增量是
    `(1 - 1) / duration = 0`，所以它永远停在 `path[0]`，也不会走完（`hasLeft`
    要 `u > 0`）。要测「飞走了」就直接改 `enemy.u`。
    """

    def build(position=None, hp=1, radius=None, clearOnDeath=False):
        where = ENEMY_START if position is None else position
        return Enemy(
            EnemySpawn(
                frame=0.0,
                enemyType=enemyType if radius is None else EnemyType(enemyType.spriteSheet, radius),
                path=(Vector2(where.x, where.y),),
                durationFrames=600.0,
                hp=hp,
                clearOnDeath=clearOnDeath,
                attacks=(),
            )
        )

    return build


@pytest.fixture
def deathEffectFrames() -> tuple[pygame.Surface, ...]:
    """假的死亡特效：三帧、尺寸递增的方块。

    真素材是一张 500×500 的环形冲击波，烘出来是几张几百像素的图——测试不需要
    那份像素，需要的是「帧序列会被逐帧播放、尺寸一帧比一帧大」。尺寸递增也让
    「画出来的是第几帧」可以从像素上认出来。
    """
    frames = []
    for index in range(3):
        size = 8 + 4 * index
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        surface.fill((255, 255, 255, 255))
        frames.append(surface)
    return tuple(frames)


@pytest.fixture
def bombEffectFrames() -> tuple[pygame.Surface, ...]:
    """假的放雷特效：**与死亡特效刻意不同**（两帧、扁而宽的方块）。

    生产里这两份帧现在是同一张图（雷还没有自己的美术），但测试里必须能分辨
    「炸的是哪一个」——都用同一份假帧的话，`effect.frames is ...` 这条断言
    永远为真，测不出东西。
    """
    frames = []
    for index in range(2):
        surface = pygame.Surface((20 + 6 * index, 6), pygame.SRCALPHA)
        surface.fill((255, 200, 80, 255))
        frames.append(surface)
    return tuple(frames)


@pytest.fixture
def makePlayer(spriteSheet, shotSpec, deathEffectFrames, bombEffectFrames):
    """造一个自机：位置、立绘、弹药与库存都可换，其余取默认值。"""

    def build(position=None, sheet=None, effectFrames=None, bombFrames=None, **kwargs):
        return Player(
            position=PLAYER_START if position is None else position,
            spriteSheet=spriteSheet if sheet is None else sheet,
            shotSpec=shotSpec,
            # 传 effectFrames=() / bombFrames=() 可以造一个「没有那份特效贴图」的自机
            deathEffectFrames=deathEffectFrames if effectFrames is None else effectFrames,
            bombEffectFrames=bombEffectFrames if bombFrames is None else bombFrames,
            **kwargs,
        )

    return build


@pytest.fixture
def player(makePlayer) -> Player:
    return makePlayer()


@pytest.fixture
def shots() -> BulletField:
    """自机子弹场。"""
    return BulletField()


@pytest.fixture
def enemyBullets() -> BulletField:
    """敌弹场。

    默认的 bounds 就是游戏区，所以出屏回收在测试里也照常生效——这与
    「子弹场不关心自己装的是谁的弹」是一致的，自机子弹朝上飞、敌弹朝下飞，
    同一条出屏规则管两边。
    """
    return BulletField()


@pytest.fixture
def enemies() -> EnemyField:
    """敌机场。默认空的——测自机时场上通常没有敌机，要用的测试自己往里放。"""
    return EnemyField((), random.Random(0))


@pytest.fixture
def effects() -> EffectField:
    """特效场。"""
    return EffectField()


@pytest.fixture
def runPlayer(shots, enemyBullets, enemies, effects):
    """推进**任意**一个自机一帧：`runPlayer(other, FrameInput(right=True))`。

    自机的 `update` 要收四个东西（往哪放弹、什么会打死我、什么会被我打死、
    放动画的场），而这个夹具把它们绑好——测试只写「推谁、按了什么」。
    要推别的自机就得用这个（`step` 认死了 `player` 那一个）。
    """

    def run(target: Player, frameInput: FrameInput) -> None:
        target.update(frameInput, shots, enemyBullets, enemies, effects)

    return run


@pytest.fixture
def step(player, runPlayer):
    """推进 `player` 一帧：`step(FrameInput(right=True))`。

    与 `runPlayer` 用的是同一次测试里的同一组场（fixture 在单个测试内是同一实例），
    所以两个混着写不会各推各的。
    """

    def run(frameInput: FrameInput) -> None:
        runPlayer(player, frameInput)

    return run


# —— BOSS ——


# BOSS 的出场点：游戏区上方，脚本第一条 moveTo 把它的进场做完
BOSS_START = Vector2(200.0, -40.0)


def _emptyBossScript(boss):
    """什么都不做的脚本：立刻跑完。用作「不关心行为」时的默认值。"""
    return
    yield


def makeBossSpawn(
    script=None, attacks=None, atFrame=0.0, name="ボス", segments=1, spriteSheet=None
):
    """造一个 BOSS 挂载点。

    不是 fixture 而是普通函数：它要能被当**夹具工厂**用（测试自己决定造几个、
    用什么脚本），而 fixture 的参数化在这种「每次调用都不同」的场景下反而绕。

    默认名字用日文的「ボス」而不是中文：这个字体（DFPPOPCorn）是日文字体，
    简体字缺得很厉害（「测试」两个字都没有），而名字是要画到血条上的。

    `spriteSheet` 缺省为 `None` = 没有真立绘，`Boss` 自己现画一张占位图。
    """
    from touhou.game.levelData import BossSpawn

    return BossSpawn(
        atFrame=atFrame,
        startPosition=Vector2(BOSS_START.x, BOSS_START.y),
        name=name,
        color=(200, 80, 120),
        segments=segments,
        attacks=attacks if attacks is not None else {},
        script=script if script is not None else _emptyBossScript,
        spriteSheet=spriteSheet,
    )
