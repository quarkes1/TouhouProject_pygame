"""一次性播放的动画。

一个 `Effect` = 一个位置 + 一串**已经烘好的**帧 + 一个播放进度。放完就没了，
不进对象池（一场战斗里它出现的次数就是死亡次数，个位数，池化没有意义）。

**为什么帧是烘好的**：死亡冲击波是一张 500×500 的环形贴图，动画是「由小到大
扩散 + 由亮到暗淡出」——每帧现算就是每帧 smoothscale 一张 500×500 的图，
三十帧下来是实打实的开销。尺寸与亮度的序列是固定的，所以烘一次、放的时候只
blit。这与「按角度预旋转缓存」是同一个道理（见 docs/DESIGN.md「性能」）。

贴图本身不由本模块加载：`Effect` 收的是烘好的帧，`bakeExpandingRing` 是把它
烘出来的纯函数。资源路径由调用方（main.py）负责，与 SpriteSheet / BulletSpec
的分工一致。
"""

# 为注解开启延迟求值，理由见 vector2.py 的同类注释
from __future__ import annotations

import pygame

from touhou.core.vector2 import Vector2


def expandingRingParams(
    index: int,
    frameCount: int,
    startScale: float,
    endScale: float,
    startAlpha: float,
    endAlpha: float,
) -> tuple[float, float]:
    """第 `index` 帧的（缩放, alpha）。线性推进，末帧正好取到终值。

    单独拆出来是为了**能不碰像素地测这条曲线**：烘出来的帧要验「越放越大、
    越放越淡」得逐像素扫一张 500×500 的图，而曲线本身是纯算术。
    """
    if frameCount <= 1:
        return startScale, startAlpha
    progress = index / (frameCount - 1)
    return (
        startScale + (endScale - startScale) * progress,
        startAlpha + (endAlpha - startAlpha) * progress,
    )


def bakeExpandingRing(
    surface: pygame.Surface,
    frameCount: int,
    startScale: float,
    endScale: float,
    startAlpha: float,
    endAlpha: float,
) -> tuple[pygame.Surface, ...]:
    """把一张环形贴图烘成「扩散 + 淡出」的一串帧。

    用 `smoothscale` 而不是最近邻：环是一圈渐变，放大时的锯齿会非常显眼；
    这是**一次性**的开销（每帧一次、只在加载时做），和窗口缩放那种每帧都要
    跑的场景不是一回事。

    淡出走 `BLEND_RGBA_MULT`（把整张图的 alpha 通道乘一个系数），不用
    `set_alpha`：后者作用在带逐像素 alpha 的表面上时，是「整体透明度」还是
    「覆盖逐像素 alpha」在各后端上并不一致，而相乘是明确的。
    """
    frames = []
    for index in range(frameCount):
        scale, alpha = expandingRingParams(
            index, frameCount, startScale, endScale, startAlpha, endAlpha
        )
        size = (
            max(1, round(surface.get_width() * scale)),
            max(1, round(surface.get_height() * scale)),
        )
        frame = pygame.transform.smoothscale(surface, size)
        frame.fill((255, 255, 255, round(alpha)), special_flags=pygame.BLEND_RGBA_MULT)
        frames.append(frame)
    return tuple(frames)


class Effect:
    """一个正在播放的一次性动画。

    与 `Bullet` 一样，`__init__` 委托给 `reset`——两者不会漂移，将来真进了池子
    也不用改调用方。
    """

    __slots__ = ("ageFrames", "frameIndex", "frames", "framesPerFrame", "position")

    ageFrames: int
    frameIndex: int
    framesPerFrame: int
    frames: tuple[pygame.Surface, ...]
    position: Vector2

    def __init__(
        self,
        frames: tuple[pygame.Surface, ...],
        position: Vector2,
        framesPerFrame: int = 1,
    ) -> None:
        self.reset(frames, position, framesPerFrame)

    def reset(
        self,
        frames: tuple[pygame.Surface, ...],
        position: Vector2,
        framesPerFrame: int = 1,
    ) -> None:
        """把动画恢复成「刚出生」。池复用的入口，所以必须设满每个字段。

        `position` 只拷分量、不存调用方传进来的那个 `Vector2` 对象——理由同
        `Bullet.reset`：直接存引用的话，自机一移动，已经放出去的冲击波会跟着跑。
        """
        self.position = Vector2(position.x, position.y)
        self.frames = frames
        self.framesPerFrame = framesPerFrame
        self.frameIndex = 0
        self.ageFrames = 0

    def update(self) -> None:
        """推进一帧。

        `frameIndex` 钳在上界内：容器是在 update 之后才回收放完的动画的，
        中间那一瞬间下标可能已经越界，而绘制不该为此抛一个裸 IndexError。
        是否放完由 `isFinished` 按**时间**判，不看这个被钳过的下标。
        """
        self.ageFrames += 1
        self.frameIndex = min(self.ageFrames // self.framesPerFrame, len(self.frames) - 1)

    def isFinished(self) -> bool:
        return self.ageFrames >= len(self.frames) * self.framesPerFrame

    def currentFrame(self) -> pygame.Surface:
        return self.frames[self.frameIndex]

    def __repr__(self) -> str:
        return (
            f"Effect(position={self.position}, "
            f"frame={self.frameIndex}/{len(self.frames)}, age={self.ageFrames})"
        )
