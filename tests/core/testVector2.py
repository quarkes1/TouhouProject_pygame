"""二维向量运算。

角度约定（全局，见 docs/DESIGN.md「关键接口约定」）：
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


def testAimingAtATargetPointsAtItFromEveryDirection():
    """自机狙：从一点瞄准另一点，算出的角度必须真的指向目标。

    参考项目就是用 acos（点积反余弦）算瞄准的，那只覆盖 [0°, 180°]，等于
    丢掉了目标在源点上方还是下方这一半信息：自机跑到敌人上方时，锥形弹会整体
    垂直镜像、朝反方向打。八个方位里正上、右上、左上三个会中招，所以八个都要测。

    **为什么必须在纯数学层测、不能靠端到端测试兜底**：实测 arccos 写法在
    下半屏（90°–270°）**完全正确**，只在**上半屏**出错。而敌人发射点在游戏区
    上沿、自机被钳制在游戏区里，自机永远在发射点**下方**——瞄准角恒在下半屏。
    所以「敌人打自机」这种端到端场景**再怎么写也抓不到这个 bug**；这正是它在
    参考项目里长期没暴露的原因。只有让目标出现在上半屏的测试才有用，就是这一条。

    也无法靠上一条互逆测试兜底：那条测的是 `Vector2.angleDeg` 与 `fromDeg` 互为
    逆运算，只要 `angleDeg` 本身没被改坏它就绿。而参考项目这个 bug 根本不在共享的
    向量方法里——它在**攻击代码**里，照抄时也会落在我们的攻击代码里，比如另写一个
    `aimAt(origin, target)` 或把点积反余弦内联在某处。那种改法不碰 `Vector2`。
    这条测的是「瞄准」这个**操作**的结果，公式写在哪儿都躲不过。

    （顺带记一笔：把 `angleDeg` 真的换成 arccos 写法时，互逆测试因为角度列表里
    恰好有 0、45、315 而**会**红。但那是运气，不是设计——它的用意从来不是覆盖瞄准。）

    失败时不会崩溃，只会让弹幕「飞得对但打向错误方向」——比崩溃难查得多。
    """
    origin = Vector2(200.0, 200.0)
    offsets = {
        "正下": (0.0, 200.0),
        "正上": (0.0, -200.0),
        "正右": (200.0, 0.0),
        "正左": (-200.0, 0.0),
        "右下": (200.0, 200.0),
        "左下": (-200.0, 200.0),
        "右上": (200.0, -200.0),
        "左上": (-200.0, -200.0),
    }
    for name, offset in offsets.items():
        target = origin + Vector2(*offset)
        aimAngleDeg = (target - origin).angleDeg()  # 这就是自机狙那一行
        assert Vector2.fromDeg(aimAngleDeg, 1.0).toTuple() == pytest.approx(
            (target - origin).normalize().toTuple()
        ), f"瞄准{name}的目标时打偏了"


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
