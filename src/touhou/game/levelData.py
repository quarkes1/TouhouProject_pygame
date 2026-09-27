"""关卡数据的读取与校验。

关卡文件是新格式（由 `tools/migrateLevel.py` 从参考项目的旧格式一次性转换而来，
字段说明见 docs/DESIGN.md「关卡数据格式」）。本模块做三件事：

1. 把 JSON 变成引擎要的数据类；
2. **校验**格式，错误信息带出错位置（`waves[2].spawns[0].attacks[1]...`），
   这样数据写错时是在加载那一刻、指着出错的地方炸，而不是等运行到那一步才炸；
3. 把贴图与子弹规格收敛成**共享实例**——旋转缓存是按表计的，给每次齐射各建一张表
   会把 docs/DESIGN.md 承诺的缓存上界乘以齐射次数。

**不消费** `drop`、`angularSpeed`：道具与曲线弹都还没实现，把它们的值读进来只会
变成没人验证的死数据。但**仍然校验**它们——格式错了要在加载时就发现，而不是等
实现到来那天才发现数据一直是坏的。

`bosses` 已经**真的被消费**了（中 BOSS 那一轮落地）：这里解析出 `BossSpawn`，
`script` 字段在加载时就动态 import 成可调用对象——所以脚本路径写错是加载时报错，
不是打到一半才炸。

校验的写法是「一列带类型的取值函数」：每个自己检查、自己报位置、返回收窄后的类型。
比「先 `_require` 再 `assert` 收窄」啰嗦，但断言不会在 `-O` 下消失，类型检查器也认。
`_require` 只留给「值之间的关系」那类校验（两项等长、概率和为 100）。
"""

# 为注解开启延迟求值，理由见 vector2.py 的同类注释
from __future__ import annotations

import importlib
import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, cast, get_args, get_origin, get_type_hints

from touhou.core.paths import assetPath
from touhou.core.spriteSheet import SpriteSheet
from touhou.core.vector2 import Vector2
from touhou.game.entities.bullet import BulletSpec
from touhou.game.patterns import PATTERN_PARAMS, PATTERN_REGISTRY

# 掉落概率必须归一到这个值。旧数据里 114 组掉落全部恰好是 100，所以这条校验不会
# 误报，却能挡住「手改了数值忘了配平」。
PROBABILITY_TOTAL = 100


class LevelFormatError(ValueError):
    """关卡数据的格式错误。信息里带出错位置。"""


@dataclass(frozen=True, slots=True)
class EnemyType:
    """一种敌人的静态属性。同一种敌人共用同一个实例（理由同下面的子弹规格）。"""

    spriteSheet: SpriteSheet
    radius: float


@dataclass(frozen=True, slots=True)
class EnemyAttack:
    """一条待触发的齐射。

    `frame` 是**相对该敌人出生**的帧数，不是关卡绝对帧——攻击的时刻本来就跟着
    敌人自己的时间轴走（旧格式里它用的是敌人轨迹参数 u）。注意关卡里
    `waves[].atFrame` 与 `spawns[].atFrame` 是**绝对**帧，两者含义不同。

    同一套攻击展开出的多波齐射**共享同一个 `params` 对象**（它是冻结的）。
    """

    frame: float
    pattern: str
    params: Any
    volleyIndex: int


@dataclass(frozen=True, slots=True)
class EnemySpawn:
    frame: float
    enemyType: EnemyType
    path: tuple[Vector2, ...]
    durationFrames: float
    hp: int
    clearOnDeath: bool
    attacks: tuple[EnemyAttack, ...]


@dataclass(frozen=True, slots=True)
class BossSpawn:
    """一个 BOSS 挂载点。

    **JSON 管「何时出 BOSS」与「打什么弹」，代码管「BOSS 怎么打」**（规格 §7.2）。
    这条分界线落在三个地方：

    - `atFrame` / `startPosition`：出场时刻与出场点（通常写在游戏区上方，
      让脚本第一条 `moveTo` 把它带进场）。
    - `attacks`：名字 → 齐射定义。参数走与敌机**同一套** `_buildParams`，
      于是子弹规格仍由 `_Caches` 共享（同一张贴图只有一份 SpriteSheet），
      格式错了也是加载时报错、带完整位置。脚本里现写子弹规格会绕开这两条。
    - `script`：行为本身。**血量不在这里**——它在脚本的 `runPhase(hp=...)` 里，
      两处都写必然对不上。

    `script` 是**已经 import 好**的可调用对象，不是字符串：字符串在 `_buildBoss` 里
    就解析掉了，所以运行期不会再有一次「按名字找函数」，脚本路径写错是加载关卡时
    报错、带完整位置，而不是打到一半才发现。
    """

    atFrame: float
    startPosition: Vector2
    name: str
    color: tuple[int, int, int]
    segments: int
    attacks: dict[str, EnemyAttack]
    script: Callable[[Any], Iterator[None]]
    # 真实立绘。**给了就用它**；没给则由 `color` 程序化生成一张占位图
    # （规格 §6.7 要的占位图形，见 entities/boss.py）——换成真美术时逻辑零改动。
    spriteSheet: SpriteSheet | None = None


@dataclass(frozen=True, slots=True)
class LevelData:
    name: str
    durationFrames: float
    spawns: tuple[EnemySpawn, ...]
    bosses: tuple[BossSpawn, ...]


# —— 带类型的取值函数：每个自己检查、自己报位置、返回收窄后的类型 ——


def _require(condition: bool, location: str, message: str) -> None:
    """校验值**之间**的关系（等长、和为 100 之类）。取单个值请用下面这几个。"""
    if not condition:
        raise LevelFormatError(f"{location}: {message}")


def _object(raw: object, location: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise LevelFormatError(f"{location}: 应当是一个对象，实际是 {type(raw).__name__}")
    return raw


def _array(raw: object, location: str) -> list[Any]:
    if not isinstance(raw, list):
        raise LevelFormatError(f"{location}: 应当是一个数组，实际是 {type(raw).__name__}")
    return raw


def _string(raw: object, location: str) -> str:
    if not isinstance(raw, str):
        raise LevelFormatError(f"{location}: 应当是字符串，实际是 {raw!r}")
    return raw


def _boolean(raw: object, location: str) -> bool:
    # bool 是 int 的子类，反过来 `1`/`0` 也会被 isinstance(x, bool) 挡掉，
    # 但 `True` 会混进数字校验里——所以两边的检查都要显式。
    if not isinstance(raw, bool):
        raise LevelFormatError(f"{location}: 应当是 true/false，实际是 {raw!r}")
    return raw


def _number(raw: object, location: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise LevelFormatError(f"{location}: 应当是数字，实际是 {raw!r}")
    return float(raw)


def _integer(raw: object, location: str) -> int:
    value = _number(raw, location)
    if value != int(value):
        raise LevelFormatError(f"{location}: 应当是整数，实际是 {raw!r}")
    return int(value)


def _point(raw: object, location: str) -> Vector2:
    coordinates = _array(raw, location)
    if len(coordinates) != 2:
        raise LevelFormatError(f"{location}: 应当是 [x, y]，实际是 {raw!r}")
    return Vector2(
        _number(coordinates[0], f"{location}[0]"), _number(coordinates[1], f"{location}[1]")
    )


# —— 贴图与子弹规格 ——


class _Caches:
    """一次加载内的共享实例表。

    三张表分开是有原因的：`SpriteSheet` 按（路径, 帧尺寸）共享，而 `BulletSpec`
    还要带上判定半径与旋转策略——**同一张 ellipse_bullet_0.png 在不同攻击里的判定
    半径不同**（4 与 6），按路径共享会让其中一种的判定圈凭空大一半；旋转策略同理
    （一个转一个不转是两种子弹）。
    """

    def __init__(self) -> None:
        self.sheets: dict[tuple[tuple[str, ...], int, int], SpriteSheet] = {}
        self.bullets: dict[tuple[tuple[str, ...], int, int, float, bool], BulletSpec] = {}
        self.enemies: dict[tuple[tuple[str, ...], int, int, float], EnemyType] = {}


def _levelPath(raw: object, location: str) -> tuple[tuple[str, ...], int, int]:
    """取 `{path, frameSize, frameCount}` 三件套，并核对帧数与图片一致。"""
    sprite = _object(raw, location)

    parts = _array(sprite.get("path"), f"{location}.path")
    if not parts or not all(isinstance(part, str) for part in parts):
        raise LevelFormatError(f"{location}.path: 应当是非空的字符串数组，实际是 {parts!r}")

    frameSize = _array(sprite.get("frameSize"), f"{location}.frameSize")
    if len(frameSize) != 2:
        raise LevelFormatError(f"{location}.frameSize: 应当是 [宽, 高]，实际是 {frameSize!r}")
    frameWidth = _integer(frameSize[0], f"{location}.frameSize[0]")
    frameHeight = _integer(frameSize[1], f"{location}.frameSize[1]")
    if frameWidth <= 0 or frameHeight <= 0:
        raise LevelFormatError(f"{location}.frameSize: 帧尺寸必须为正，实际是 {frameSize!r}")

    # 路径相对 assets/，加载器直接补前缀。旧格式的路径自带 "assets/"，
    # 透传会去找 assets/assets/...，是踩过的坑，新格式从数据里就把它去掉了。
    return tuple(parts), frameWidth, frameHeight


def _sheetFor(caches: _Caches, raw: object, location: str) -> SpriteSheet:
    parts, frameWidth, frameHeight = _levelPath(raw, location)

    key = (parts, frameWidth, frameHeight)
    if key not in caches.sheets:
        caches.sheets[key] = SpriteSheet.fromFile(assetPath(*parts), frameWidth, frameHeight)
    sheet = caches.sheets[key]

    # 数据里的 frameCount 必须跟图片实际切出来的帧数对上。旧格式把判定半径写在了
    # 帧数的位置上，那种错只有靠「跟图片核对」才能当场抓住。
    declared = _integer(_object(raw, location).get("frameCount"), f"{location}.frameCount")
    _require(
        declared == sheet.frameCount,
        f"{location}.frameCount",
        f"数据说 {declared} 帧，但图片按 {frameWidth}×{frameHeight} 切出来是 {sheet.frameCount} 帧",
    )
    return sheet


def _bulletSpecFor(caches: _Caches, raw: object, location: str) -> BulletSpec:
    spec = _object(raw, location)
    sheet = _sheetFor(caches, raw, location)
    radius = _number(spec.get("hitboxRadius"), f"{location}.hitboxRadius")
    _require(radius > 0, f"{location}.hitboxRadius", "判定半径必须为正")

    # 跟不跟着速度转是**逐弹种**的，不是全局开关：
    # - 圆球（大玉、圆弹）转了看不出差别，给它 360 个缓存条目纯是浪费——172×172 的
    #   大玉转一圈是几十 MB，而 `SpriteSheet.getRotated` 的缓存是每张表一份。
    # - 尖头弹（苦无）不跟着转会歪，必须转。
    # 缺省是 True：数据里没写就按「要转」处理，与这个字段出现之前的行为一致。
    rotates = _boolean(spec.get("rotatesToVelocity", True), f"{location}.rotatesToVelocity")

    parts, frameWidth, frameHeight = _levelPath(raw, location)
    # 缓存键要带上这两个：同一张贴图同尺寸但判定半径或旋转策略不同的，是两种子弹
    key = (parts, frameWidth, frameHeight, radius, rotates)
    if key not in caches.bullets:
        caches.bullets[key] = BulletSpec(
            spriteSheet=sheet, radius=radius, rotatesToVelocity=rotates
        )
    return caches.bullets[key]


# —— 攻击 ——


def _matchesHint(value: object, hint: object) -> bool:
    """值是否符合注解。只覆盖参数里实际出现的类型，认不出的注解一律放行。

    `float` 接受整数（JSON 里 `"angularSpeed": 0` 是整数，语义上是浮点），
    但两者都拒绝 `bool`——`true` 在 Python 里是 `int` 的子类，写错成布尔值
    会一路混进算术里。
    """
    if get_origin(hint) is not None:  # 形如 `float | None`
        return any(_matchesHint(value, argument) for argument in get_args(hint))
    if hint is float:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if hint is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if hint is bool:
        return isinstance(value, bool)
    if isinstance(hint, type):
        return isinstance(value, hint)
    return True


def _checkFieldTypes(instance: object, paramsType: type, location: str) -> None:
    """按参数类的注解逐个核对取值。

    没有这一步，`"speed": "150"` 这种错会**静默通过**：参数类只是普通 dataclass，
    不会检查注解，字符串要等某处拿它做算术时才炸，那时已经离出错的地方很远了。
    规格 §7.5 举的例子里正好就是这一条（`params.speed 应为数字，实际为字符串 "1"`）。
    """
    hints = get_type_hints(paramsType)
    for field in fields(paramsType):
        value = getattr(instance, field.name)
        if not _matchesHint(value, hints[field.name]):
            raise LevelFormatError(
                f"{location}.{field.name}: 应为 {hints[field.name]}，实际是 {value!r}"
            )


def _buildParams(pattern: str, raw: object, location: str, caches: _Caches) -> Any:
    params = _object(raw, location)
    if "bullet" not in params:
        raise LevelFormatError(f"{location}: 缺少 bullet")

    paramsType = PATTERN_PARAMS[pattern]
    expected = {field.name for field in fields(paramsType)}
    given = set(params)
    missing = expected - given
    unknown = given - expected
    _require(not missing, location, f"缺少参数 {sorted(missing)}")
    _require(not unknown, location, f"未知参数 {sorted(unknown)}")

    values = dict(params)
    values["bullet"] = _bulletSpecFor(caches, params["bullet"], f"{location}.bullet")
    try:
        instance = paramsType(**values)
    except TypeError as error:
        raise LevelFormatError(f"{location}: 参数类型不对（{error}）") from error

    _checkFieldTypes(instance, paramsType, location)
    return instance


def _validateDrop(raw: object, location: str) -> None:
    """掉落本轮不消费，但格式必须是对的（规格 §7.5 要求校验这一项）。"""
    drop = _object(raw, location)
    items = _array(drop.get("list"), f"{location}.list")
    probabilities = _array(drop.get("probabilities"), f"{location}.probabilities")
    _require(
        len(items) == len(probabilities),
        location,
        f"list 有 {len(items)} 项而 probabilities 有 {len(probabilities)} 项，对不上",
    )
    total = 0.0
    for index, probability in enumerate(probabilities):
        total += _number(probability, f"{location}.probabilities[{index}]")
    _require(
        total == PROBABILITY_TOTAL, f"{location}.probabilities", f"概率之和应为 100，实际是 {total}"
    )


def _resolveScript(path: str, location: str) -> Callable[[Any], Iterator[None]]:
    """把 `"touhou.game.stage.level1.midbossScript"` 这样的点分路径解析成函数。

    **规格 §7.2 点名了这条路**（「值为 Python 脚本路径，加载器动态 import」），
    所以这里没有走注册表那条路——那是 `patterns/` 的做法（静态注册 + 装饰器）。
    两条路各有各的道理：模板是「数据组合出弹幕」，脚本是「一整个 BOSS 的行为」，
    后者本来就该是一个可以随便写的 Python 文件。

    解析发生在**加载关卡时**：路径写错、函数改名，都会在那一刻带位置报错，
    而不是打到一半、脚本该跑的时候才炸。
    """
    moduleName, separator, attribute = path.rpartition(".")
    if not separator:
        raise LevelFormatError(f"{location}: 应当是「模块.函数」这样的点分路径，实际是 {path!r}")
    try:
        module = importlib.import_module(moduleName)
    except ImportError as error:
        raise LevelFormatError(f"{location}: 导不到模块 {moduleName!r}（{error}）") from error

    script = getattr(module, attribute, None)
    if script is None:
        raise LevelFormatError(f"{location}: 模块 {moduleName!r} 里没有 {attribute!r}")
    if not callable(script):
        raise LevelFormatError(f"{location}: {path!r} 不是可调用的（是个 {type(script).__name__}）")
    return cast(Callable[[Any], Iterator[None]], script)


def _buildBoss(raw: object, location: str, caches: _Caches) -> BossSpawn:
    """一个 BOSS 挂载点。字段少，但每个都要校验（规格 §7.5 的取向：早报、带位置）。"""
    boss = _object(raw, location)
    atFrame = _number(boss.get("atFrame"), f"{location}.atFrame")
    _require(atFrame >= 0, f"{location}.atFrame", f"出场时刻不能为负，实际是 {atFrame}")

    name = _string(boss.get("name"), f"{location}.name")
    color = _color(boss.get("color"), f"{location}.color")
    startPosition = _point(boss.get("startPosition"), f"{location}.startPosition")
    scripts = _string(boss.get("script"), f"{location}.script")
    script = _resolveScript(scripts, f"{location}.script")

    segments = _integer(boss.get("segments", 1), f"{location}.segments")
    _require(segments >= 1, f"{location}.segments", f"血条分段至少为 1，实际是 {segments}")

    rawSprite = boss.get("sprite")
    return BossSpawn(
        atFrame=atFrame,
        startPosition=startPosition,
        name=name,
        color=color,
        segments=segments,
        attacks=_buildBossAttacks(boss.get("attacks", {}), f"{location}.attacks", caches),
        script=script,
        # 与敌机走同一套贴图解析（`_sheetFor`），所以同一张图仍然只有一份
        spriteSheet=None
        if rawSprite is None
        else _sheetFor(caches, rawSprite, f"{location}.sprite"),
    )


def _buildBossAttacks(raw: object, location: str, caches: _Caches) -> dict[str, EnemyAttack]:
    """BOSS 的攻击表：名字 → 齐射定义。

    与敌机那条路共用 `_extractAttack`（弹型得存在、参数得合法），差别只在时序：
    敌机的时刻表由 `_expandAttacks` 在这里就展开成一条条绝对帧，而 BOSS 是脚本
    决定何时开火，所以只留「打什么」，`frame` / `volleyIndex` 填 0 占位。
    """
    attacks: dict[str, EnemyAttack] = {}
    for name, rawAttack in _object(raw, location).items():
        where = f"{location}.{name}"
        pattern, params = _extractAttack(rawAttack, where, caches)
        attacks[name] = EnemyAttack(frame=0.0, pattern=pattern, params=params, volleyIndex=0)
    return attacks


def _color(raw: object, location: str) -> tuple[int, int, int]:
    """`[r, g, b]`，三分量各 0~255。

    没有写成通用的「长度为 N 的整数数组」：`_point` 已经是「长度 2 的数字数组」的
    专用函数，再抽一层只会让两个调用点都多绕一道。
    """
    values = _array(raw, location)
    _require(len(values) == 3, location, f"应当是 [r, g, b] 三个分量，实际有 {len(values)} 个")
    channels = []
    for index, value in enumerate(values):
        channel = _integer(value, f"{location}[{index}]")
        _require(
            0 <= channel <= 255, f"{location}[{index}]", f"颜色分量应在 0~255，实际是 {channel}"
        )
        channels.append(channel)
    return (channels[0], channels[1], channels[2])


def _extractAttack(raw: object, location: str, caches: _Caches) -> tuple[str, Any]:
    """一套攻击里的「打什么」：弹型名 + 参数。

    敌机的时刻表与 BOSS 的攻击表共用这一段——两边都要求「弹型存在、参数合法」，
    差别只在**时序由谁排**：敌机由 `_expandAttacks` 在这里就展开成一条条绝对帧，
    BOSS 则由脚本决定何时开火。
    """
    attack = _object(raw, location)
    pattern = _string(attack.get("pattern"), f"{location}.pattern")
    if pattern not in PATTERN_REGISTRY:
        raise LevelFormatError(
            f"{location}.pattern: 未知模板 {pattern!r}，已注册的是 {sorted(PATTERN_REGISTRY)}"
        )
    params = _buildParams(pattern, attack.get("params"), f"{location}.params", caches)
    _require(
        params.volleyCount >= 1, f"{location}.params", f"波数至少为 1，实际是 {params.volleyCount}"
    )
    _require(
        params.intervalFrames >= 0,
        f"{location}.params",
        f"波间隔不能为负，实际是 {params.intervalFrames}",
    )
    return pattern, params


def _expandAttacks(raw: object, location: str, caches: _Caches) -> tuple[EnemyAttack, ...]:
    attacks: list[EnemyAttack] = []
    for index, rawAttack in enumerate(_array(raw, location)):
        where = f"{location}[{index}]"
        startFrame = _number(_object(rawAttack, where).get("startFrame"), f"{where}.startFrame")
        pattern, params = _extractAttack(rawAttack, where, caches)

        # 时序在这里就展开：之后运行期只需按 frame 走一遍排好的表，
        # 不必再知道「每套攻击打几波、隔多久」。
        attacks.extend(
            EnemyAttack(
                frame=startFrame + params.intervalFrames * volley,
                pattern=pattern,
                params=params,
                volleyIndex=volley,
            )
            for volley in range(params.volleyCount)
        )

    attacks.sort(key=lambda attack: attack.frame)
    return tuple(attacks)


# —— 出生点与关卡 ——


def _buildSpawn(raw: object, location: str, caches: _Caches) -> EnemySpawn:
    spawn = _object(raw, location)

    sprite = spawn.get("sprite")
    sheet = _sheetFor(caches, sprite, f"{location}.sprite")
    radius = _number(spawn.get("hitboxRadius"), f"{location}.hitboxRadius")
    _require(radius > 0, f"{location}.hitboxRadius", "判定半径必须为正")

    typeKey = (*_levelPath(sprite, f"{location}.sprite"), radius)
    if typeKey not in caches.enemies:
        caches.enemies[typeKey] = EnemyType(spriteSheet=sheet, radius=radius)

    trajectoryRaw = _array(spawn.get("trajectory"), f"{location}.trajectory")
    if not trajectoryRaw:
        raise LevelFormatError(f"{location}.trajectory: 至少要有一个控制点")
    trajectory = tuple(
        _point(item, f"{location}.trajectory[{index}]") for index, item in enumerate(trajectoryRaw)
    )

    durationFrames = _number(spawn.get("durationFrames"), f"{location}.durationFrames")
    _require(durationFrames > 0, f"{location}.durationFrames", "轨迹时长必须为正")

    hp = _integer(spawn.get("hp"), f"{location}.hp")
    _require(hp >= 1, f"{location}.hp", f"血量至少为 1，实际是 {hp}")

    _validateDrop(spawn.get("drop"), f"{location}.drop")

    startPosition = _point(spawn.get("startPosition"), f"{location}.startPosition")
    return EnemySpawn(
        frame=_number(spawn.get("atFrame"), f"{location}.atFrame"),
        enemyType=caches.enemies[typeKey],
        # start_position 是路径的第一个点，不是出生后要瞬移过去的位置。
        path=(startPosition, *trajectory),
        durationFrames=durationFrames,
        hp=hp,
        clearOnDeath=_boolean(spawn.get("clearBulletsOnDeath"), f"{location}.clearBulletsOnDeath"),
        attacks=_expandAttacks(spawn.get("attacks"), f"{location}.attacks", caches),
    )


def loadLevel(path: Path) -> LevelData:
    """读关卡文件。格式有问题时抛 `LevelFormatError`，信息里指出出错位置。"""
    root = _object(json.loads(path.read_text(encoding="utf-8")), "<根>")

    meta = _object(root.get("meta"), "meta")
    name = _string(meta.get("name"), "meta.name")
    durationFrames = _number(meta.get("durationFrames"), "meta.durationFrames")

    # BOSS 挂载点：键是角色名（`midboss` / `boss`），值是出场时刻与脚本入口。
    # 键名本身不参与语义（顺序由 atFrame 决定），只为了文件读起来像「这一关有哪些 BOSS」。
    caches = _Caches()
    bosses = [
        _buildBoss(rawBoss, f"bosses.{key}", caches)
        for key, rawBoss in _object(root.get("bosses", {}), "bosses").items()
    ]
    bosses.sort(key=lambda boss: boss.atFrame)
    spawns: list[EnemySpawn] = []
    for waveIndex, rawWave in enumerate(_array(root.get("waves"), "waves")):
        where = f"waves[{waveIndex}]"
        wave = _object(rawWave, where)
        rawSpawns = _array(wave.get("spawns"), f"{where}.spawns")
        if not rawSpawns:
            raise LevelFormatError(f"{where}.spawns: 至少要有一个出生点")

        waveSpawns = [
            _buildSpawn(item, f"{where}.spawns[{index}]", caches)
            for index, item in enumerate(rawSpawns)
        ]
        # 波上的 atFrame 只是分组起点（spawn 自带权威时刻），但冗余不允许不一致。
        waveAtFrame = _number(wave.get("atFrame"), f"{where}.atFrame")
        earliest = min(spawn.frame for spawn in waveSpawns)
        _require(
            waveAtFrame == earliest,
            f"{where}.atFrame",
            f"应等于本波最早的出生帧 {earliest}，实际是 {waveAtFrame}",
        )
        spawns.extend(waveSpawns)

    spawns.sort(key=lambda spawn: spawn.frame)
    return LevelData(
        name=name,
        durationFrames=durationFrames,
        spawns=tuple(spawns),
        bosses=tuple(bosses),
    )
