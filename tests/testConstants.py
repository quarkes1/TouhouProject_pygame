"""常量的自洽性。

不测具体数值（那些是要调的），只测它们之间的关系是否成立。
"""
from touhou import constants


def testPlayfieldFitsInsideLogicalResolution():
    """游戏区必须完整落在逻辑分辨率内，否则自机有一半在屏幕外。"""
    assert constants.PLAYFIELD_X + constants.PLAYFIELD_WIDTH <= constants.LOGICAL_WIDTH
    assert constants.PLAYFIELD_Y + constants.PLAYFIELD_HEIGHT <= constants.LOGICAL_HEIGHT


def testPlayfieldIsAnchoredInsideTheLeftPortion():
    """游戏区靠左，右侧留出的宽度就是 HUD 区。"""
    hudWidth = constants.LOGICAL_WIDTH - (constants.PLAYFIELD_X + constants.PLAYFIELD_WIDTH)
    assert hudWidth > 0
    assert constants.PLAYFIELD_X > 0, "游戏区不该贴着窗口左边缘"


def testStepSecondsMatchesFrameRate():
    assert constants.STEP_SECONDS == 1.0 / constants.FPS


def testSlowModeIsSlowerThanNormalMode():
    assert constants.PLAYER_SPEED_SLOW < constants.PLAYER_SPEED_NORMAL
    assert constants.PLAYER_SPEED_SLOW > 0


def testPowerConstantsAreOrdered():
    assert 0 < constants.POWER_START < constants.POWER_MAX
    assert constants.POWER_ITEM_SMALL < constants.POWER_ITEM_LARGE


def testPoCLineFallsInsidePlayfield():
    """PoC 回收线必须落在游戏区内部，否则永远触发不到或一进场就触发。"""
    assert 0 < constants.POC_LINE_OFFSET_Y < constants.PLAYFIELD_HEIGHT


def testGrazeRadiusIsLargerThanHitbox():
    """擦弹圈必须大于判定点，否则擦弹系统没有存在空间。"""
    assert constants.PLAYER_GRAZE_RADIUS > constants.PLAYER_HITBOX_RADIUS
