"""弹幕模板包。

**import 这个包就会把模板登记进 `PATTERN_REGISTRY`**——注册靠的是各模块里的
`@registerPattern` 装饰器，所以那些模块必须真的被 import 到。下面这几行看似没用，
删掉之后关卡加载器就会在解析 `pattern` 时报「未知模板」。这与 `vector2.py` 顶上
那句 `from __future__ import annotations` 是同一类东西：看着多余，删了就坏。
"""

from touhou.game.patterns import long_random, wide_cone, wide_ring
from touhou.game.patterns.registry import (
    PATTERN_PARAMS,
    PATTERN_REGISTRY,
    FiringContext,
    PatternFunc,
    PatternParams,
    randomCentreOrigin,
    registerPattern,
)

__all__ = [
    "PATTERN_PARAMS",
    "PATTERN_REGISTRY",
    "FiringContext",
    "PatternFunc",
    "PatternParams",
    "long_random",
    "randomCentreOrigin",
    "registerPattern",
    "wide_cone",
    "wide_ring",
]
