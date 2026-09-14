"""圆形碰撞判定。"""

import pytest

from touhou.core.collider import Collider
from touhou.core.vector2 import Vector2


def testOverlappingCirclesCollide():
    a = Collider(2.0, Vector2(0, 0))
    b = Collider(3.0, Vector2(4.9, 0))
    assert a.checkCollision(b)


def testSeparatedCirclesDoNotCollide():
    a = Collider(2.0, Vector2(0, 0))
    b = Collider(3.0, Vector2(5.1, 0))
    assert not a.checkCollision(b)


def testTangentCirclesDoNotCollide():
    """相切（距离恰好等于半径和）判定为不碰撞——边缘擦过不算命中。"""
    a = Collider(2.0, Vector2(0, 0))
    b = Collider(3.0, Vector2(5.0, 0))
    assert not a.checkCollision(b)


def testCollisionIsSymmetric():
    a = Collider(2.0, Vector2(0, 0))
    b = Collider(3.0, Vector2(4.0, 0))
    assert a.checkCollision(b) == b.checkCollision(a)


def testSamePositionAlwaysCollides():
    a = Collider(1.0, Vector2(100, 100))
    b = Collider(1.0, Vector2(100, 100))
    assert a.checkCollision(b)


def testZeroRadiusColliderStillCollidesAtSamePoint():
    a = Collider(0.0, Vector2(10, 10))
    b = Collider(1.0, Vector2(10, 10))
    assert a.checkCollision(b)


def testCollisionIsCorrectOnTheDiagonal():
    """对角线方向的判定必须和轴对齐方向一致。

    这条是回归测试：参考项目 NumPix/pygame-touhou 的 check_collision 是：

        ((a.position - b.position) * (a.position - b.position)).length()
            < (a.radius + b.radius) ** 2

    Vector2 的 * 对两个向量做逐分量乘法，得到 [dx², dy²]，再取 .length()
    就是 sqrt(dx⁴ + dy⁴)——既不是距离也不是距离平方，两边量纲对不上，
    碰撞体实际不是圆。本例中距离恰好为 5、半径和也是 5，
    参考公式会算出 sqrt(3⁴ + 4⁴) ≈ 18.36 并与 25 比较，误判为碰撞。
    """
    a = Collider(2.0, Vector2(0, 0))
    b = Collider(3.0, Vector2(3, 4))  # 距离恰好 5 = 2 + 3
    assert not a.checkCollision(b)


def testDistanceSquaredToPoint():
    a = Collider(1.0, Vector2(0, 0))
    assert a.distanceSquaredTo(Vector2(3, 4)) == pytest.approx(25.0)


def testDistanceSquaredToOwnPositionIsZero():
    a = Collider(1.0, Vector2(7, 9))
    assert a.distanceSquaredTo(Vector2(7, 9)) == 0.0


def testDefaultPositionIsOrigin():
    assert Collider(1.0).position == Vector2(0, 0)
