"""关卡迁移工具。

工具在 `tools/` 下（不进 `src/` 包，它是一次性的开发工具），所以这里按路径加载它。

最要紧的两条是**单位换算的方向**与**时长公式的分母**：两处都反过一次，
而两处反了都不会报错——只会让弹幕全部排在敌机离场之后、或让敌机快
`len/(len-1)` 倍。数字必须逐个钉死。
"""

import importlib.util
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "migrateLevel", PROJECT_ROOT / "tools" / "migrateLevel.py"
)
assert _spec is not None and _spec.loader is not None
migrateLevel = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrateLevel)

FAIRY_SPRITE = ["assets", "sprites", "entities", "fairy_0.png"]
KUNAI = [["assets", "sprites", "projectiles_and_items", "kunai_0.png"], 16, 16, 4, [0, 0]]


# —— 坐标 ——


def testScalesReferenceCornersOntoOurPlayfield():
    """参考游戏区的四角换算后正好落在我们游戏区的四角——只缩放、不平移。"""
    assert migrateLevel.scaledPoint([0, 0]) == [32.0, 16.0]
    assert migrateLevel.scaledPoint([600, 700]) == [416.0, 464.0]
    assert migrateLevel.scaledPoint([300, 350]) == [224.0, 240.0], "中心对中心"


# —— 子弹 ——


def testFrameCountIsDerivedFromTheImage():
    """帧数从图片推出来，不采信数据。

    旧数据把判定半径写在帧数的位置上（苦无写 4、橄榄写 6），而两张图分别是
    16×16 与 24×24——「照着数位读」的典型事故。工具必须自己去量图片。
    """
    bullet = migrateLevel.migrateBullet(
        [["assets", "sprites", "entities", "fairy_0.png"], 24, 19, 15, [0, 0]]
    )

    assert bullet["frameSize"] == [24, 19]
    assert bullet["frameCount"] == 6, "fairy_0.png 是 144×19，按 24×19 切是 6 帧"


def testSpritePathDropsTheLeadingAssetsComponent():
    """路径改为相对 assets/，这样加载器直接用 assetPath()，不必再剥前缀。"""
    bullet = migrateLevel.migrateBullet(
        [["assets", "sprites", "entities", "fairy_0.png"], 24, 19, 15, [0, 0]]
    )

    assert bullet["path"] == ["sprites", "entities", "fairy_0.png"]


def testHitboxRadiusIsNotScaled():
    """判定半径是「角色尺度」的量，保持原值；只有关卡几何（位置）缩放。"""
    bullet = migrateLevel.migrateBullet(
        [["assets", "sprites", "entities", "fairy_0.png"], 24, 19, 15, [0, 0]]
    )

    assert bullet["hitboxRadius"] == 15


# —— 攻击：单位与字段 ——


def testAttackIntervalDividesByEnemySpeed():
    """`delay` 的单位是敌人轨迹的 u，换秒要**除以**敌机速度。

    弹刺球 `speed=2.4`、`delay=0.75` → `0.75 / 2.4 × 60 = 18.75` 帧。
    乘反了（×2.4）会得到 108 帧——每个间隔长 5.76 倍，结果是 98 组攻击全部排在
    敌机离场之后。docs/DESIGN.md 那条移植警告讲的就是这件事，方向不能反。
    """
    attack = ["wide_cone", 3, 4, KUNAI, "player", 150, 10, 1, 0.75, 0]

    migrated = migrateLevel.migrateAttack(attack, enemySpeed=2.4)

    assert migrated["params"]["intervalFrames"] == pytest.approx(18.75)
    assert migrated["startFrame"] == pytest.approx(1 / 2.4 * 60)


def testBulletSpeedIsConvertedFromPerSecondToPerFrame():
    """弹速的单位是**像素/秒**，要换成**像素/帧**——引擎统一用后者。

    参考项目跑变步长（像素/秒），本项目固定 60fps（像素/帧）。**漏掉这一步不会报错**：
    子弹会以 150 像素/帧飞出去、三帧横穿整个游戏区然后被回收，画面上表现为
    「敌机在开火，但场上几乎没有子弹」。这条守卫是补上它之前用肉眼发现的。
    """
    attack = ["long_random", 3, 30, KUNAI, 150, 1, 0.06, 0, True]

    migrated = migrateLevel.migrateAttack(attack, enemySpeed=1.0)

    assert migrated["params"]["speed"] == pytest.approx(2.5), "150 像素/秒 = 2.5 像素/帧"


def testAttackStartFrameIsInFramesNotSeconds():
    attack = ["long_random", 3, 30, KUNAI, 150, 1, 0.06, 0, True]

    migrated = migrateLevel.migrateAttack(attack, enemySpeed=1.0)

    assert migrated["startFrame"] == 60.0
    assert migrated["params"]["intervalFrames"] == pytest.approx(3.6)


def testAimedConeBecomesNoneInsteadOfThePlayerString():
    """`"player"` 在数据里是「没有固定基准角」，用 `None` 表达比留字符串好：

    留下字符串会让这个字段变成「数字或字符串」，类型说不清。
    """
    aimed = migrateLevel.migrateAttack(
        ["wide_cone", 3, 4, KUNAI, "player", 150, 10, 1, 0.5, 0], 1.0
    )
    fixed = migrateLevel.migrateAttack(["wide_cone", 3, 4, KUNAI, 90, 150, 10, 1, 0.5, 0], 1.0)

    assert aimed["params"]["baseAngleDeg"] is None
    assert fixed["params"]["baseAngleDeg"] == 90


def testRingRotationIsNegated():
    """参考项目的旋转方向与我们相反，有符号角度必须取负——否则螺旋绕反。"""
    migrated = migrateLevel.migrateAttack(
        ["wide_ring", 3, 60, KUNAI, 200, 1, 0.2, 0, 13, False], 1.0
    )

    assert migrated["params"]["deltaAngleDeg"] == -13


def testRingKeepsItsOwnFieldCount():
    """三种弹型的字段数与含义都不同：`long_random` 是 9 元、另两种 10 元。

    按固定下标统一解析会在 98/122 组上崩——工具必须按弹型分别解包。
    """
    ring = migrateLevel.migrateAttack(["wide_ring", 10, 10, KUNAI, 150, 1, 0.15, 0, 50, True], 1.0)
    random_ = migrateLevel.migrateAttack(["long_random", 3, 30, KUNAI, 150, 1, 0.06, 0, True], 1.0)

    assert ring["params"]["ringCount"] == 10
    assert "ringCount" not in random_["params"]
    assert random_["params"]["burstCount"] == 30


def testRejectsAnAttackWithTheWrongFieldCount():
    with pytest.raises(ValueError, match="应有 10 个字段"):
        migrateLevel.migrateAttack(["wide_ring", 10, 10, KUNAI, 150, 1, 0.15, 0, 50], 1.0)


# —— 出生点 ——


def testDurationFramesCoversTheLeadInSegment():
    """路径 = `[startPosition] + trajectory`，比 trajectory 多一段，所以分母是 `len(trajectory)`。

    规格给的公式用 `len(trajectory) - 1`，因为它假定路径只有 trajectory。照抄会让
    每架敌机比预期早走完一段——也就是所有敌机都快 `len/(len-1)` 倍（4 点轨迹快 33%）。
    """
    entry = {
        "time": 7,
        "start_position": [50, 0],
        "trajectory": [[50, 50], [50, 50], [50, 50], [-50, 150]],
        "speed": 1,
        "sprite": {"size": [24, 19], "path": FAIRY_SPRITE},
        "collider": {"radius": 15, "offset": [0, 0]},
        "hp": 10,
        "attacks": [],
        "drop": {"list": ["points"], "probabilities": [100]},
        "clear_on_death": False,
    }

    migrated = migrateLevel.migrateSpawn(entry)

    assert len(entry["trajectory"]) == 4
    assert migrated["durationFrames"] == 240.0, "4 段 × 60 帧，不是规格公式的 180"
    assert migrated["atFrame"] == 420.0


# —— 波分组 ——


def testWaveGroupingKeepsEachSpawnOwnFrame():
    """波内每个 spawn 自带时刻，分组不能把错峰压平。

    同一波里的出生时刻本来就是错开的（例如 50.0、50.1、50.4…52.5 秒）。若让它们
    共用波上的时刻，敌机会整波同时出现——那是迁移改变了语义，而迁移只该改变表达。
    """
    spawns = [
        {"atFrame": 3000.0},
        {"atFrame": 3006.0},
        {"atFrame": 3012.0},
        {"atFrame": 3120.0},  # 间隔超过 1 秒，属于下一波
    ]

    waves = migrateLevel.groupIntoWaves(spawns)

    assert len(waves) == 2
    assert [spawn["atFrame"] for spawn in waves[0]["spawns"]] == [3000.0, 3006.0, 3012.0]
    assert waves[1]["atFrame"] == 3120.0


def testWaveAtFrameIsTheEarliestSpawnInIt():
    waves = migrateLevel.groupIntoWaves([{"atFrame": 600.0}, {"atFrame": 660.0}])

    assert waves[0]["atFrame"] == 600.0


# —— 幂等与格式 ——


def testRefusesToMigrateAnAlreadyMigratedLevel():
    """一次性工具：源文件已是新格式时必须拒绝，而不是把 waves 当成 enemies 读。"""
    with pytest.raises(ValueError, match="已经是新格式"):
        migrateLevel.migrate({"meta": {"name": "x"}, "waves": []})


def testFormattedJsonKeepsFlatArraysOnOneLine():
    """坐标、帧尺寸、路径这类纯量数组排成一行。

    `json.dumps(indent=2)` 会把每个数字单独放一行，关卡文件因此从 84KB 涨到 243KB，
    而且扫读时看不清结构——可读性正是新格式的卖点。
    """
    text = migrateLevel.formatJson({"trajectory": [[64.0, 48.0], [0.0, 112.0]]})

    assert "[64.0, 48.0]" in text
    assert "[\n" in text, "嵌套数组仍然逐项换行"


def testTheCommittedLevelIsTheNewFormat():
    """仓库里那份关卡文件必须已经是新格式——迁移跑过了，不该留下旧文件。"""
    raw = json.loads(
        (PROJECT_ROOT / "assets" / "levels" / "level_1.json").read_text(encoding="utf-8")
    )

    assert "meta" in raw and "waves" in raw
    assert "enemies" not in raw, "旧格式的字段不该还在"
