"""窗口缩放倍率选择。

逻辑分辨率固定 640×480，整数倍缩放到窗口。非整数倍会让像素变成大小
不一的矩形、画面发糊，所以宁可留黑边。详见设计文档 §5.4。
"""

from touhou.core.display import chooseScaleFactor, scaledSize


def testTwoTimesOnA1280x960Display():
    assert chooseScaleFactor(1280, 960, 640, 480) == 2


def testLimitedByTheShorterAxis():
    """1920×1080 上宽度够 3 倍但高度只够 2 倍，取 2。"""
    assert chooseScaleFactor(1920, 1080, 640, 480) == 2


def testThreeTimesOnA1920x1440Display():
    assert chooseScaleFactor(1920, 1440, 640, 480) == 3


def testExactlyFittingDisplayGivesOne():
    assert chooseScaleFactor(640, 480, 640, 480) == 1


def testDisplaySmallerThanLogicalStillGivesOne():
    """显示器比逻辑分辨率还小时返回 1 而不是 0——返回 0 会让渲染尺寸为零。"""
    assert chooseScaleFactor(320, 240, 640, 480) == 1


def testNeverReturnsZero():
    for width in (0, 1, 100, 639):
        assert chooseScaleFactor(width, width, 640, 480) >= 1


def testWidthAxisCanBindBelowHeight():
    """宽度必须参与比较：宽只够 2 倍而高够 4 倍时，结果是 2 而不是 4。

    只按高度取的话窗口宽度会超出屏幕。既有用例两个轴同量级或高度更紧，
    宽度单独收紧的分支此前没有任何测试锁住。
    """
    assert chooseScaleFactor(1280, 2000, 640, 480) == 2


def testWidthAxisCanClampToOne():
    """宽只够 1 倍而高够 3 倍时，宽度把倍率压回下限 1。"""
    assert chooseScaleFactor(700, 1440, 640, 480) == 1


def testScaledSizeMultipliesBothAxes():
    assert scaledSize(640, 480, 2) == (1280, 960)


def testScaledSizeAtOneIsUnchanged():
    assert scaledSize(640, 480, 1) == (640, 480)
