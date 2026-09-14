"""圆形碰撞判定。

参考项目 NumPix/pygame-touhou 的 check_collision 在数学上是错的：

    ((target.position - self.position) * (target.position - self.position)).length()
        < (self.radius + target.radius) ** 2

Vector2 的 * 对两个向量做逐分量乘法，得到 [dx², dy²]，再取 .length() 就是
sqrt(dx⁴ + dy⁴)——既不是距离也不是距离平方。两边量纲对不上，判定的边界
不是一个圆。本实现不复刻该缺陷，回归测试见 tests/core/testCollider.py
的 testCollisionIsCorrectOnTheDiagonal。
"""

# 方法签名引用了 Collider 自身，3.13 下需要延迟求值，理由见 vector2.py
from __future__ import annotations

from touhou.core.vector2 import Vector2


class Collider:
    __slots__ = ("position", "radius")

    def __init__(self, radius: float, position: Vector2 | None = None) -> None:
        self.radius = radius
        self.position = position if position is not None else Vector2.zero()

    def checkCollision(self, other: Collider) -> bool:
        """两圆是否重叠。

        用长度平方与半径和的平方比较，省掉一次开方。严格小于号意味着
        相切不算碰撞——弹幕游戏里边缘擦过不该算命中。
        """
        threshold = self.radius + other.radius
        return (other.position - self.position).lengthSquared() < threshold * threshold

    def distanceSquaredTo(self, point: Vector2) -> float:
        """到某点的距离平方。

        擦弹判定要拿同一个距离跟两个不同半径比较（判定点半径和擦弹半径），
        所以单独暴露这个方法，省得每次重算。
        """
        return (point - self.position).lengthSquared()

    def __repr__(self) -> str:
        return f"Collider(radius={self.radius}, position={self.position})"
