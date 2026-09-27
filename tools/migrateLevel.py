"""把旧格式的关卡数据一次性迁移成新格式。

**旧格式**（参考项目的）把所有东西平铺在一个数组里，攻击参数是**位置数组**：
读懂要靠数位、增删或调序会**静默错位**而无任何报错、时间单位还混用
（`start_time` 与 `delay` 用的是敌人轨迹的 `u`，不是秒）。规格 §7.1 点名了这些硬伤。

**新格式**（规格 §7.2）：敌人分组进 `waves`、攻击写成 `pattern` + 具名 `params`、
时间统一成帧、坐标换算好写进文件、贴图路径相对 `assets/`。

用法：

    python tools/migrateLevel.py [源文件] [目标文件]

默认原地转换 `assets/levels/level_1.json`。旧内容留在 git 历史里。
转换是**一次性**的：源文件若已经是新格式，本工具会拒绝运行。

**迁移只该改变表达、不该改变语义**：转换后的关卡跑起来必须和转换前一样。
时间换算与坐标换算都要按下面的说明做，任何一处反了都会让敌机或弹幕错位，
而且不会报错。
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEVEL_PATH = PROJECT_ROOT / "assets" / "levels" / "level_1.json"

# 数据里的贴图路径已经从项目根算起、且带 "assets" 这一级；
# 新格式改为相对 assets/，于是加载器可以直接用 assetPath()，不必再剥前缀。
ASSET_PREFIX = "assets"

# 关卡里的坐标以**参考项目游戏区**的左上角为原点（600×700），
# 而我们的游戏区是它的 0.64 倍。换算依据见 docs/DESIGN.md「关卡数据与坐标系」。
REFERENCE_WIDTH = 600.0
REFERENCE_HEIGHT = 700.0
PLAYFIELD_X = 32.0
PLAYFIELD_Y = 16.0
PLAYFIELD_WIDTH = 384.0
PLAYFIELD_HEIGHT = 448.0

FPS = 60.0

# 出生时刻相隔超过这么多秒就算新的一波。**这个阈值只影响文件的可读性**
# （让关卡读起来像「第 N 帧刷第一波」），不参与任何运行期语义——
# 每个 spawn 自带权威时刻，见下面的 waves 说明。
WAVE_GAP_SECONDS = 1.0

ATTACK_ARITY = {"wide_cone": 10, "wide_ring": 10, "long_random": 9}


def scaledPoint(raw: list[float]) -> list[float]:
    """把关卡坐标换算到本项目游戏区（只缩放、不平移）。"""
    return [
        round(PLAYFIELD_X + raw[0] * PLAYFIELD_WIDTH / REFERENCE_WIDTH, 4),
        round(PLAYFIELD_Y + raw[1] * PLAYFIELD_HEIGHT / REFERENCE_HEIGHT, 4),
    ]


def pngSize(path: Path) -> tuple[int, int]:
    """读 PNG 头取真实尺寸。

    帧数是**从图片尺寸推出来的**，数据里没有也不该有这个字段——
    旧数据把判定半径写在帧数的位置上，正是「照着数位读」的典型事故。
    这里不引 pygame：工具只跑一次，不想为它多装一个依赖。
    """
    with path.open("rb") as handle:
        if handle.read(8) != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"{path} 不是 PNG 文件")
        handle.read(8)  # 跳过块长度与 "IHDR" 标记
        width, height = struct.unpack(">II", handle.read(8))
    return width, height


def migrateBullet(raw: list) -> dict:
    """迁移子弹描述：`[路径, 帧宽, 帧高, 判定半径, 偏移]`。"""
    parts = list(raw[0])
    if parts and parts[0] == ASSET_PREFIX:
        parts = parts[1:]
    frameWidth, frameHeight = raw[1], raw[2]
    radius = raw[3]

    imageWidth, imageHeight = pngSize(PROJECT_ROOT / "assets" / Path(*parts))
    frameCount = (imageWidth // frameWidth) * (imageHeight // frameHeight)
    if frameCount < 1:
        raise ValueError(
            f"{parts} 切不出任何一帧：图片 {imageWidth}×{imageHeight}，帧 {frameWidth}×{frameHeight}"
        )

    return {
        "path": parts,
        "frameSize": [frameWidth, frameHeight],
        "frameCount": frameCount,
        # 判定半径**不缩放**：它是「角色尺度」的调参量，与精灵、速度同属一类。
        # 只有关卡几何（位置）需要缩放，见 docs/DESIGN.md「关卡数据与坐标系」。
        "hitboxRadius": radius,
    }


def migrateAttack(raw: list, enemySpeed: float) -> dict:
    """迁移一条攻击。

    位置字段按弹型各自解释——**每种弹型的字段数与含义都不同**，
    这是旧格式最硬的一处伤：`wide_cone` 的第 4 位是字符串 "player"（自机狙），
    另两种的第 4 位是数字（弹速）。按固定下标统一解析会在 98/122 组上崩。

    时间单位：`start_time` 与 `delay` 是**敌人轨迹的 u**，不是秒。
    换算成秒要**除以**敌机速度（u 每秒前进 speed 个区间），再 ×60 得帧。
    乘反了会让每组间隔长 speed² 倍——对 2.4 的敌人是 5.76 倍，
    结果是 98 组攻击全部在敌机离场后才开火。docs/DESIGN.md 有这条警告。
    """
    kind = raw[0]
    if len(raw) != ATTACK_ARITY[kind]:
        raise ValueError(f"{kind} 应有 {ATTACK_ARITY[kind]} 个字段，实际 {len(raw)} 个")

    def toFrames(u: float) -> float:
        # 取到 4 位小数：`0.06 / 1 × 60` 在浮点里是 3.5999999999999996，
        # 写进文件既是噪声也会让「同一份数据换台机器比不相等」。
        return round(u / enemySpeed * FPS, 4)

    def toPixelPerFrame(referenceSpeed: float) -> float:
        """参考项目的**像素/秒** → 本项目的**像素/帧**。

        参考项目跑变步长，速度是像素/秒；本项目固定 60fps，引擎统一用像素/帧
        （constants.py 开头就写着这条约定，旧 main.py 里的临时生成器也是这么换算的：
        「150 像素/秒」写作 2.5 像素/帧）。

        **漏掉这一步不会报错**：子弹会以 150 像素/帧飞出去，三帧横穿整个游戏区
        然后被回收。画面上表现为「敌机在开火，但场上几乎没有子弹」——
        只有真的看一眼画面才发现得了。
        """
        return round(referenceSpeed / FPS, 4)

    bullet = migrateBullet(raw[3])
    if kind == "wide_cone":
        (
            _,
            bulletCount,
            coneCount,
            _,
            baseAngle,
            speed,
            deltaAngle,
            startTime,
            delay,
            angularSpeed,
        ) = raw
        params = {
            "bulletCount": bulletCount,
            "coneCount": coneCount,
            "bullet": bullet,
            # "player" 是「没有固定基准角、朝自机打」，用 null 表达比留着字符串好：
            # 留下字符串会让这个字段变成「数字或字符串」，类型说不清。
            "baseAngleDeg": None if baseAngle == "player" else baseAngle,
            "speed": toPixelPerFrame(speed),
            "deltaAngleDeg": deltaAngle,
            "intervalFrames": toFrames(delay),
            "angularSpeed": angularSpeed,
        }
    elif kind == "wide_ring":
        (
            _,
            bulletCount,
            ringCount,
            _,
            speed,
            startTime,
            delay,
            angularSpeed,
            deltaAngle,
            randomCenter,
        ) = raw
        params = {
            "bulletCount": bulletCount,
            "ringCount": ringCount,
            "bullet": bullet,
            "speed": toPixelPerFrame(speed),
            # **取负**：参考项目的角度是顺时针为正的反面（docs/DESIGN.md 移植警告一），
            # 所以有符号角度要翻一次，否则螺旋往反方向绕。
            "deltaAngleDeg": -deltaAngle,
            "intervalFrames": toFrames(delay),
            "randomCenter": randomCenter,
            "angularSpeed": angularSpeed,
        }
    else:
        _, bulletCount, burstCount, _, speed, startTime, delay, angularSpeed, randomCenter = raw
        params = {
            "bulletCount": bulletCount,
            "burstCount": burstCount,
            "bullet": bullet,
            "speed": toPixelPerFrame(speed),
            "intervalFrames": toFrames(delay),
            "randomCenter": randomCenter,
            "angularSpeed": angularSpeed,
        }

    return {"pattern": kind, "startFrame": round(toFrames(startTime), 4), "params": params}


def migrateSpawn(entry: dict) -> dict:
    trajectory = entry["trajectory"]
    speed = entry["speed"]

    # 轨迹时长：我们的路径是 `[start_position] + trajectory`，比 trajectory 多一段，
    # 所以分母是 len(trajectory) 而不是 len(trajectory) - 1。
    # 规格给的迁移公式用的是后者（它假定路径只有 trajectory），照抄会让敌机
    # 比预期早走完一段。每段的像素速度不变，只是总时长多一段。
    durationFrames = len(trajectory) / speed * FPS

    spriteParts = list(entry["sprite"]["path"])
    if spriteParts and spriteParts[0] == ASSET_PREFIX:
        spriteParts = spriteParts[1:]
    imageWidth, imageHeight = pngSize(PROJECT_ROOT / "assets" / Path(*spriteParts))
    frameWidth, frameHeight = entry["sprite"]["size"]

    return {
        "atFrame": round(entry["time"] * FPS, 4),
        "startPosition": scaledPoint(entry["start_position"]),
        "trajectory": [scaledPoint(point) for point in trajectory],
        "durationFrames": round(durationFrames, 4),
        "sprite": {
            "path": spriteParts,
            "frameSize": [frameWidth, frameHeight],
            "frameCount": (imageWidth // frameWidth) * (imageHeight // frameHeight),
        },
        "hitboxRadius": entry["collider"]["radius"],
        "hp": entry["hp"],
        "attacks": [migrateAttack(attack, speed) for attack in entry["attacks"]],
        "drop": entry["drop"],
        "clearBulletsOnDeath": entry["clear_on_death"],
    }


def groupIntoWaves(spawns: list[dict]) -> list[dict]:
    """按出生时刻把 spawn 分组进 waves。

    **每个 spawn 自带 `atFrame`，它是权威时刻**；波上的 `atFrame` 只等于本波最早的
    那个 spawn，纯粹为了让文件读起来像「第 N 帧刷第一波」。

    为什么不能让波内共用时刻：旧数据里同一波内的出生时刻是**错开**的
    （例如 50.0、50.1、50.4…52.5 秒），若压成同一个时刻，敌机会整波同时出现——
    那是迁移改变了语义，而迁移只该改变表达。
    """
    ordered = sorted(spawns, key=lambda spawn: spawn["atFrame"])
    gapFrames = WAVE_GAP_SECONDS * FPS

    waves: list[list[dict]] = []
    for spawn in ordered:
        if waves and spawn["atFrame"] - waves[-1][-1]["atFrame"] <= gapFrames:
            waves[-1].append(spawn)
        else:
            waves.append([spawn])

    return [{"atFrame": wave[0]["atFrame"], "spawns": wave} for wave in waves]


def migrate(old: dict) -> dict:
    if "waves" in old or "meta" in old:
        raise ValueError("源文件已经是新格式，本工具只做一次性迁移")

    spawns = [migrateSpawn(entry) for entry in old["enemies"]]
    return {
        "meta": {
            # 旧数据没有名字，用固定名；它本来就是第一关。
            "name": "level_1",
            "durationFrames": round(old["length"] * FPS, 4),
        },
        "waves": groupIntoWaves(spawns),
        # BOSS 挂载点：JSON 管「何时出 BOSS」，代码管「BOSS 怎么打」（规格 §6.7）。
        # 本关没有 BOSS，占位为空——加载器认识这个字段，但暂不加载脚本。
        "bosses": {},
    }


def summarize(level: dict) -> str:
    spawns = [spawn for wave in level["waves"] for spawn in wave["spawns"]]
    attacks = [attack for spawn in spawns for attack in spawn["attacks"]]
    bullets = sum(
        attack["params"]["bulletCount"]
        * (
            attack["params"].get("coneCount")
            or attack["params"].get("ringCount")
            or attack["params"].get("burstCount")
            or 1
        )
        for attack in attacks
    )
    byPattern: dict[str, int] = {}
    for attack in attacks:
        byPattern[attack["pattern"]] = byPattern.get(attack["pattern"], 0) + 1
    return (
        f"  波数 {len(level['waves'])}\n"
        f"  出生点 {len(spawns)}\n"
        f"  攻击 {len(attacks)} 组 {byPattern}\n"
        f"  总弹量 {bullets}"
    )


def isFlat(value: object) -> bool:
    return isinstance(value, list) and all(not isinstance(item, (list, dict)) for item in value)


def formatJson(value: object, level: int = 0) -> str:
    """写 JSON，但让「全是纯量的数组」留在同一行。

    `json.dumps(indent=2)` 会把数组里的每个数字单独放一行：坐标 `[64, 48]` 占两行、
    一串概率占三行，关卡文件因此从 84KB 涨到 243KB，而且扫读时看不清结构。
    坐标、帧尺寸、路径、概率这些本来就该一眼看完，这里把它们排成一行。

    嵌套数组（如 `trajectory` 的一串坐标）仍然逐项换行——每项自己是一行，
    因为那才是「一层一个意思」的层次。
    """
    pad = "  " * level
    inner = "  " * (level + 1)

    if isinstance(value, dict):
        if not value:
            return "{}"
        bodies = [
            f"{inner}{json.dumps(key, ensure_ascii=False)}: {formatJson(item, level + 1)}"
            for key, item in value.items()
        ]
        return "{\n" + ",\n".join(bodies) + f"\n{pad}}}"

    if isinstance(value, list):
        if not value:
            return "[]"
        if isFlat(value):
            return "[" + ", ".join(json.dumps(item, ensure_ascii=False) for item in value) + "]"
        bodies = [f"{inner}{formatJson(item, level + 1)}" for item in value]
        return "[\n" + ",\n".join(bodies) + f"\n{pad}]"

    return json.dumps(value, ensure_ascii=False)


def main(argv: list[str]) -> int:
    source = Path(argv[0]) if argv else DEFAULT_LEVEL_PATH
    target = Path(argv[1]) if len(argv) > 1 else source

    level = migrate(json.loads(source.read_text(encoding="utf-8")))
    # newline="\n" 是必须的：Windows 上 write_text 默认把 \n 转成 \r\n，而
    # .gitattributes 规定 `* text=auto eol=lf`。不写死的话 git 每次触碰这个文件
    # 都会重写一遍换行，diff 里永远带着噪声。
    target.write_text(formatJson(level) + "\n", encoding="utf-8", newline="\n")

    print(f"已迁移 {source} -> {target}")
    print(summarize(level))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
