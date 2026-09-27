"""弹幕模板注册表。

关卡数据里的 `pattern` 名字通过这张表解析成具体的模板函数。**加模板不需要改加载器**：
写好函数、挂上 `@registerPattern`、在那个模块被 import 到即可（见
`patterns/__init__.py`）。

形态照规格 §7.3：`PATTERN_REGISTRY: dict[str, Callable]` + `registerPattern` 装饰器。
**但模板函数的签名是规格没写的**（它只给了注册表形态，`Callable` 没有参数化），
本项目定为 `(params, context) -> None`：

- `params` 是每个弹型各自的 frozen dataclass，字段名与关卡数据里的名字一一对应
- `context` 装齐一切外部依赖（见下）

**模板不接触自机、不接触全局状态**：发射点与瞄准角由调用方算好放进 `context`。
这样模板能脱离 pygame 场景与敌人对象被单独测试，自机狙的退化情形（自机与敌机重合）
也只在调用方一处处理。
"""

# 为注解开启延迟求值，理由见 vector2.py 的同类注释
from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from touhou.core.vector2 import Vector2
from touhou.game.bulletField import BulletField


@dataclass(frozen=True, slots=True)
class FiringContext:
    """一次齐射所需的**外部**依赖：在哪打、朝哪打、用什么随机数。

    「打什么子弹」属于参数（每个弹型的 params 里都有 `bullet`），不放这里——
    参数是数据，上下文是环境，这条界线让模板函数能脱离场景被单独测试。

    `rng` 是**注入**的，不是模块级全局 `random`：随机弹型必须可复现，否则
    「同一份输入产生同一个结果」这条（docs/DESIGN.md「主循环」）就废了，
    录像回放与逐帧调试也跟着一起废。规格 §5.2 也是这么要求的。

    `volleyIndex` 是这一发是本次攻击的第几波（从 0 起）。时序归调度方管、弹型只管
    打**一发**，但环形弹的「第 n 环整体旋转 n × 角度」需要知道 n，所以由调度方告知。
    """

    field: BulletField
    origin: Vector2
    aimAngleDeg: float
    rng: random.Random
    volleyIndex: int = 0


# 各弹型的 params 类型不同，注册表是异质的，所以参数取 Any。
# 用联合类型会让每个模板函数都被迫声明「我能接受任何一种 params」，那是假话。
PatternFunc = Callable[[Any, FiringContext], None]

PATTERN_REGISTRY: dict[str, PatternFunc] = {}
PATTERN_PARAMS: dict[str, type] = {}


class PatternParams(Protocol):
    """所有弹型参数都满足的形状，加载器只依赖这两项来排时序。

    - `volleyCount`：这套攻击一共打几波
    - `intervalFrames`：相邻两波隔多少帧

    `volleyCount` 在数据里各叫各的名字（`coneCount` / `ringCount` / `burstCount`，
    因为「锥数」「环数」「波数」对不同弹型含义不同），各参数类用 property 把它
    暴露成统一的名字。有了这条约定，**加模板就不需要改加载器**了。
    """

    @property
    def volleyCount(self) -> int: ...

    intervalFrames: float


def randomCentreOrigin(context: FiringContext, radius: float) -> Vector2:
    """「随机中心」的发射点：敌人位置 + 随机方向 × 半径。

    `wide_ring` 与 `long_random` 都有一个「随机中心」开关。打开时发射点不再固定在
    敌人身上，而是绕着敌人随机偏一点——所以同一组参数连续打出来的形状会散开，
    不会次次重合成一个死板的几何图形。

    随机数取自 `context.rng`（注入的、可播种的），所以同一个种子给出的偏移
    逐发可复现。
    """
    angleDeg = context.rng.uniform(0.0, 360.0)
    return context.origin + Vector2.fromDeg(angleDeg, radius)


def registerPattern(name: str, paramsType: type) -> Callable[[PatternFunc], PatternFunc]:
    """把模板函数与它的参数类型一起登记。

    `name` 显式给出而不是用函数名：关卡数据里的键与 Python 的命名风格未必一致
    （数据是 snake_case，规格的示例是 camelCase），显式传名可以把这件事解耦。

    **参数类型也要登记**，这是规格没规定、但「加模板不需要改加载器」必须的一步：
    加载器靠它把 JSON 里的具名参数建出来并校验。若不登记，每加一个模板都得回去
    改加载器，注册表就白设了。字段名与 JSON 里的名字一一对应，多一个少一个都会报错。
    """

    def decorator(func: PatternFunc) -> PatternFunc:
        if name in PATTERN_REGISTRY:
            raise ValueError(f"弹幕模板 {name!r} 被注册了两次")
        # 在这里就检查参数类满足 PatternParams：漏了 `volleyCount` 的模板会在
        # 「加载关卡时」才炸，而那时已经离出错的地方很远了。
        if not hasattr(paramsType, "volleyCount") or not hasattr(paramsType, "intervalFrames"):
            raise TypeError(f"弹幕模板 {name!r} 的参数类必须提供 volleyCount 与 intervalFrames")
        PATTERN_REGISTRY[name] = func
        PATTERN_PARAMS[name] = paramsType
        return func

    return decorator
