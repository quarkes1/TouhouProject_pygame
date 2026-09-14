"""二维向量。

刻意不用 numpy：numpy 对小数组的单次运算比纯 Python 慢——np.array([x, y])
每次都要构造数组对象，这个开销远大于它省下的两次浮点加法。弹幕引擎每帧
要做几万次向量运算，numpy 在这里是负收益。详见 docs/DESIGN.md「为什么不使用 numpy」。

角度约定（全局，见 docs/DESIGN.md「关键接口约定」）：
    0° 指向正上方（屏幕 -y），角度增大为屏幕上的顺时针方向。
    0° -> 正上、90° -> 正右、180° -> 正下、270° -> 正左

  选它的理由：屏幕坐标系 y 轴向下，标准旋转矩阵 [[cos,-sin],[sin,cos]]
  在这个坐标系里看起来本就是顺时针，所以 rotateDeg 就是一次普通矩阵乘法，
  不需要任何符号翻转。

  注意：参考项目 NumPix/pygame-touhou 的旋转方向与此相反（它的 rotate 用
  行向量乘矩阵，等价于旋转负角度），因此从它的关卡数据移植角度值时必须
  取负——ourAngle = (-referenceAngle) % 360，否则定向弹幕会整体左右镜像。
"""

# 本模块的方法签名引用了 Vector2 自身。Python 3.13 及更早版本会在类体
# 执行时立即求值注解，那时类名还没绑定，会直接 NameError；延迟求值
# （PEP 649）要到 3.14 才默认开启。这个 import 看着没用，但删掉就崩。
from __future__ import annotations

import math


class Vector2:
    __slots__ = ("x", "y")

    def __init__(self, x: float = 0.0, y: float = 0.0) -> None:
        self.x = x
        self.y = y

    def __add__(self, other: Vector2) -> Vector2:
        return Vector2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Vector2) -> Vector2:
        return Vector2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> Vector2:
        return Vector2(self.x * scalar, self.y * scalar)

    def __truediv__(self, scalar: float) -> Vector2:
        return Vector2(self.x / scalar, self.y / scalar)

    def __neg__(self) -> Vector2:
        return Vector2(-self.x, -self.y)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Vector2):
            return NotImplemented
        return self.x == other.x and self.y == other.y

    def __repr__(self) -> str:
        return f"Vector2({self.x:g}, {self.y:g})"

    def length(self) -> float:
        # math.hypot 比 sqrt(x*x + y*y) 更快也更不容易溢出
        return math.hypot(self.x, self.y)

    def lengthSquared(self) -> float:
        """长度平方。碰撞检测用它比较，可以省掉一次开方。"""
        return self.x * self.x + self.y * self.y

    def normalize(self) -> Vector2:
        """返回同方向的单位向量。零向量返回零向量，不产生 NaN。"""
        length = self.length()
        if length == 0.0:
            return Vector2(0.0, 0.0)
        return Vector2(self.x / length, self.y / length)

    def dot(self, other: Vector2) -> float:
        return self.x * other.x + self.y * other.y

    def rotateDeg(self, degrees: float) -> Vector2:
        """按本项目的角度约定旋转（顺时针为正）。

        数学形式上仍是标准旋转矩阵；因为屏幕 y 轴向下，逆时针的数学正方向
        在视觉上表现为顺时针，正好与 fromDeg 的约定一致。
        """
        radians = math.radians(degrees)
        cosA = math.cos(radians)
        sinA = math.sin(radians)
        return Vector2(self.x * cosA - self.y * sinA, self.x * sinA + self.y * cosA)

    def angleDeg(self) -> float:
        """返回本向量对应的角度，范围 [0, 360)。与 fromDeg 互为逆运算。

        零向量返回 180.0（atan2(0.0, -0.0) 是 π），而不是报错或 0。零向量
        本没有角度可言，现在没有调用方，真正的契约留给 Plan B 的定向弹幕
        定——届时若要改语义，从这里开始。
        """
        return math.degrees(math.atan2(self.x, -self.y)) % 360

    def toTuple(self) -> tuple[float, float]:
        return (self.x, self.y)

    @staticmethod
    def fromDeg(degrees: float, magnitude: float = 1.0) -> Vector2:
        """从角度构造向量。0° 指向正上方，角度增大为顺时针。"""
        radians = math.radians(degrees)
        return Vector2(math.sin(radians) * magnitude, -math.cos(radians) * magnitude)

    @staticmethod
    def zero() -> Vector2:
        return Vector2(0.0, 0.0)

    @staticmethod
    def right() -> Vector2:
        return Vector2(1.0, 0.0)

    @staticmethod
    def up() -> Vector2:
        return Vector2(0.0, -1.0)
