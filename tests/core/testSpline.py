"""均匀三次 B 样条。

本文件守着「我们用的是哪一种样条」。B 样条是**逼近型**（曲线落在控制点凸包内、
不穿过中间控制点），Catmull-Rom 是**插值型**（穿过每个控制点）——两者在同一条
数据上给出不同路径，而选错的后果是敌机整体走样、不会崩溃。

用真实关卡数据跑的凸包与坐标测试在 tests/game/testLevelData.py：
core/ 不该去读 assets/（分层见 docs/DESIGN.md「分层」）。
"""

import math

import pytest

from touhou.core.spline import samplePath
from touhou.core.vector2 import Vector2


def v(*pairs: tuple[float, float]) -> list[Vector2]:
    return [Vector2(x, y) for x, y in pairs]


def assertLandsOn(actual: Vector2, expected: Vector2) -> None:
    """比较位置，容忍浮点误差。

    B 样条的权重是 1/6、2/3 这类二进制无法精确表示的数，所以「曲线恰好落在
    控制点上」这个**代数上精确成立**的性质，在浮点里只能到 1e-15 量级。

    注意：`Vector2.__repr__` 用 `:g` 格式化，会把这点误差显示成完全相同的
    `Vector2(3, 4) == Vector2(3, 4)`——只看失败信息会以为断言没道理。
    """
    assert actual.toTuple() == pytest.approx(expected.toTuple(), abs=1e-9)


SQUARE = v((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0))


# —— 端点：镜像外插换来的性质 ——


def testStartsAtFirstControlPoint():
    """u=0 落在首控制点**上**，而不是控制点多边形内部。

    这不是 B 样条的自带性质，是镜像外插换来的：没有外插，曲线在端点处只能给出
    四个点的加权平均，起点会落在多边形里面。「敌人从 start_position 出发」
    就靠这条成立。
    """
    assertLandsOn(samplePath(SQUARE, 0.0), SQUARE[0])


def testEndsAtLastControlPoint():
    assertLandsOn(samplePath(SQUARE, 3.0), SQUARE[-1])


def testClampsOutsideTheParameterRange():
    assertLandsOn(samplePath(SQUARE, -5.0), SQUARE[0])
    assertLandsOn(samplePath(SQUARE, 99.0), SQUARE[-1])


# —— 逼近型 vs 插值型（本文件的核心）——


def testDoesNotPassThroughInteriorControlPoints():
    """B 样条**不**穿过中间控制点——这是它与 Catmull-Rom 的分水岭。

    若有人把实现换成插值型，这条会红；而只看端点、连续性与单调性的测试全都
    不会红。被控制点「拉」向多边形内部是 B 样条换取转弯平滑的代价，
    也是关卡数据格式所假定的行为。
    """
    assert (samplePath(SQUARE, 1.0) - SQUARE[1]).length() > 1.0
    assert (samplePath(SQUARE, 2.0) - SQUARE[2]).length() > 1.0


def testTripleControlPointIsPassedThrough():
    """连写三次的控制点会被曲线**穿过**——这是 B 样条的标准写法。

    关卡数据里 16 条轨迹都以前三点重复开头（全是妖精），意思就是「曲线从这个
    入口点开始」。它与上面那条一起把样条类型钉死：插值型会连中间点也穿过，
    逼近型只在三次重复处穿过。
    """
    points = v((100.0, 50.0), (100.0, 50.0), (100.0, 50.0), (300.0, 200.0), (500.0, 100.0))

    assertLandsOn(samplePath(points, 0.0), Vector2(100.0, 50.0))
    assertLandsOn(samplePath(points, 1.0), Vector2(100.0, 50.0))


def testRepeatedControlPointsMeanStandingStill():
    """连写十几次的控制点让曲线**停在那里**。

    敌 70/71（hp 40 的精英）整条轨迹 13 个点全相同，就是「飞进来然后僵持」。
    这也是为什么样条不需要任何「重复点 = 停住」的特判——B 样条自己就对。
    """
    points = [Vector2(400.0, 100.0)] + [Vector2(200.0, 300.0)] * 13

    for u in (2.0, 5.0, 9.0, 12.0):
        assertLandsOn(samplePath(points, u), Vector2(200.0, 300.0))


def testStaysInsideTheControlPointHull():
    """凸包性质：曲线不会越出控制点的包围盒。

    这正是选 B 样条的实际收益——Catmull-Rom 在急转弯外侧会越界（实测真实数据
    最大 13.6px），而敌机越过游戏区边界会被回收逻辑误伤。
    """
    points = v((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0), (-50.0, 50.0))

    for step in range(401):
        position = samplePath(points, step / 100.0)
        assert -50.0 <= position.x <= 100.0
        assert 0.0 <= position.y <= 100.0


# —— 参数定义域与连续性 ——


def testIsContinuousAcrossSegmentBoundaries():
    """段与段之间不能跳变，否则敌机会瞬移。

    边界两侧各取一个极小量比较——这是「C⁰ 连续」的可执行形式。
    """
    for boundary in (1.0, 2.0):
        before = samplePath(SQUARE, boundary - 1e-9)
        after = samplePath(SQUARE, boundary + 1e-9)
        assert (after - before).length() < 1e-6


def testParameterDomainIsNotNormalizedToZeroOne():
    """u 的定义域是 `[0, n-1]`，不是 `[0, 1]`。

    若有人把它当成归一化参数，整条轨迹会被压缩进第一段里：走完 u∈[0,1] 就
    以为走完了全程。所以比较两段参数区间走过的弧长——按段算的那段必须是
    全程的一条**边**（正方形四边等长，一段约占全程 1/3），而不是全部。
    """

    def arcLength(until: float) -> float:
        total = 0.0
        previous = samplePath(SQUARE, 0.0)
        steps = 2000
        for step in range(1, steps + 1):
            current = samplePath(SQUARE, until * step / steps)
            total += (current - previous).length()
            previous = current
        return total

    whole = arcLength(3.0)
    firstSegment = arcLength(1.0)

    assert firstSegment < whole * 0.6, "第一段不该占掉全程的大半"
    assert firstSegment > whole * 0.15, "第一段也不该被压成零"


# —— 退化输入 ——


def testSinglePointPathStaysAtThatPoint():
    assertLandsOn(samplePath(v((7.0, 8.0)), 0.0), Vector2(7.0, 8.0))
    assertLandsOn(samplePath(v((7.0, 8.0)), 5.0), Vector2(7.0, 8.0))


def testTwoPointPathDoesNotDivideByZero():
    points = v((0.0, 0.0), (10.0, 0.0))

    assertLandsOn(samplePath(points, 0.0), Vector2(0.0, 0.0))
    assertLandsOn(samplePath(points, 1.0), Vector2(10.0, 0.0))
    assert math.isfinite(samplePath(points, 0.5).x)


def testEntirelyIdenticalPathStaysThere():
    """整条轨迹全同——真实数据里敌 70/71 就是这样。"""
    points = [Vector2(3.0, 4.0)] * 13

    for step in range(14):
        assertLandsOn(samplePath(points, float(step)), Vector2(3.0, 4.0))


def testEmptyPathIsRejected():
    with pytest.raises(ValueError):
        samplePath([], 0.0)


def testNeverProducesNaNOnRealShapedInput():
    """真实数据的形状（重复点 + 长直线 + 急转弯）不能产出 NaN 或无穷。"""
    points = v((50.0, 0.0), (50.0, 50.0), (50.0, 50.0), (50.0, 50.0), (-50.0, 150.0))

    for step in range(1001):
        position = samplePath(points, step / 250.0)
        assert math.isfinite(position.x)
        assert math.isfinite(position.y)
