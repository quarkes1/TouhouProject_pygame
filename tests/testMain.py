"""主程序的无头集成测试。

规格 8.5 把测试策略分三层，这是第三层（引擎层）：以 dummy 驱动无头运行，
验证真实行为而不做像素级对比。main.py 此前是项目里唯一没有任何自动化
覆盖的文件——这一层就是为它留的。dummy 驱动下 set_mode 不需要显示器，
子代理环境里也一样能跑。

这里的测试断言的是行为而非「没崩溃」：走满累积器给出的步数、速度档位、
边界钳制、裁剪守卫、退出条件。缩放倍率一律钉死为 1，不依赖 dummy 驱动
报告的显示尺寸。
"""

import pygame
import pytest

from touhou import constants
from touhou import main as mainModule
from touhou.core.input import FrameInput

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
