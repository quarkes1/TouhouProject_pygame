"""二维向量运算。

角度约定（全局，见设计文档「关键接口约定」）：
    0° = 正上方（屏幕 -y），角度增大 = 屏幕上的顺时针方向
    0° -> (0,-1)、90° -> (1,0)、180° -> (0,1)、270° -> (-1,0)
"""

import math

import pytest

from touhou.core.vector2 import Vector2

# —— 基本运算 ——


def testAddition():
    assert Vector2(1, 2) + Vector2(3, 4) == Vector2(4, 6)


def testSubtraction():
    assert Vector2(3, 4) - Vector2(1, 2) == Vector2(2, 2)


def testScalarMultiplication():
    assert Vector2(1, 2) * 3 == Vector2(3, 6)


def testScalarDivision():
    assert Vector2(3, 6) / 3 == Vector2(1, 2)


def testNegation():
    assert -Vector2(1, -2) == Vector2(-1, 2)


def testEqualityWithNonVectorIsFalse():
    assert Vector2(1, 2) != (1, 2)


# —— 长度 ——


def testLength():
    assert Vector2(3, 4).length() == 5.0


def testLengthSquared():
    """碰撞检测用平方长度比较，省掉开方。"""
    assert Vector2(3, 4).lengthSquared() == 25.0


# —— 归一化 ——


def testNormalizeProducesUnitLength():
    assert Vector2(3, 4).normalize().length() == pytest.approx(1.0)


def testNormalizeKeepsDirection():
    assert Vector2(0, 5).normalize() == Vector2(0, 1)


def testNormalizeZeroVectorReturnsZero():
    """零向量归一化必须返回零向量而不是 NaN。

    自机没有按方向键时方向向量就是零向量，这个守卫是必须的。
    """
    result = Vector2(0, 0).normalize()
    assert result == Vector2(0, 0)
    assert not math.isnan(result.x)
    assert not math.isnan(result.y)


# —— 点积 ——


def testDotProduct():
    assert Vector2(1, 2).dot(Vector2(3, 4)) == 11


def testDotProductOfPerpendicularVectorsIsZero():
    assert Vector2(1, 0).dot(Vector2(0, 1)) == 0


# —— 角度约定（全局约定，必须锁死）——


def testFromDegZeroPointsUp():
    x, y = Vector2.fromDeg(0).toTuple()
    assert x == pytest.approx(0.0)
    assert y == pytest.approx(-1.0)


def testFromDegNinetyPointsRight():
    x, y = Vector2.fromDeg(90).toTuple()
    assert x == pytest.approx(1.0)
    assert y == pytest.approx(0.0)


def testFromDegOneEightyPointsDown():
    x, y = Vector2.fromDeg(180).toTuple()
    assert x == pytest.approx(0.0)
    assert y == pytest.approx(1.0)


def testFromDegTwoSeventyPointsLeft():
    x, y = Vector2.fromDeg(270).toTuple()
    assert x == pytest.approx(-1.0)
    assert y == pytest.approx(0.0)


def testFromDegRespectsMagnitude():
    assert Vector2.fromDeg(0, magnitude=7.5).length() == pytest.approx(7.5)


def testUpAndRightHelpers():
    assert Vector2.up() == Vector2(0, -1)
    assert Vector2.right() == Vector2(1, 0)


# —— 角度与旋转 ——


def testAngleDegIsInverseOfFromDeg():
    for degrees in (0, 45, 90, 135, 180, 225, 270, 315):
        assert Vector2.fromDeg(degrees).angleDeg() == pytest.approx(degrees)


def testAngleDegIsAlwaysInZeroToThreeSixty():
    assert 0 <= Vector2(-1, -1).angleDeg() < 360


def testRotateDegTurnsUpIntoRight():
    """把「正上」顺时针转 90° 应该得到「正右」。

    这里必须用 approx：math.cos(math.radians(90)) 得到的是 6.1e-17 而不是 0，
    所以旋转结果是 (1.0, -6.1e-17)，与精确的 (1.0, 0.0) 并非逐位相等。
    本文件里其他所有含三角函数的断言都用了 approx，这一条没有理由是例外。

    注意比较的是 toTuple() 而非向量本身：Vector2.__eq__ 对 Approx 对象返回
    NotImplemented，pytest 会退化成精确比较，反而仍然失败。
    """
    rotated = Vector2.up().rotateDeg(90)
    assert rotated.toTuple() == pytest.approx(Vector2.right().toTuple())


def testRotateDegByThreeSixtyIsIdentity():
    rotated = Vector2(3, -4).rotateDeg(360)
    assert rotated.x == pytest.approx(3.0)
    assert rotated.y == pytest.approx(-4.0)


def testRotateDegPreservesLength():
    assert Vector2(3, 4).rotateDeg(37).length() == pytest.approx(5.0)


def testRotateDegIsConsistentWithFromDeg():
    """旋转角度与绝对角度必须用同一套方向约定，否则弹幕会朝反方向飞。"""
    for degrees in range(0, 360, 30):
        rotated = Vector2.fromDeg(0).rotateDeg(degrees)
        assert rotated.angleDeg() == pytest.approx(degrees % 360)


# —— 其他 ——


def testToTuple():
    assert Vector2(1.5, -2.5).toTuple() == (1.5, -2.5)


def testRepresentationIsReadable():
    assert "1" in repr(Vector2(1, 2))
