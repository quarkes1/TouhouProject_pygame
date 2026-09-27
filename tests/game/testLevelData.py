"""关卡数据的读取与校验。

本文件里最有价值的是**镜像对称**那条：关卡左右严格镜像，而这件事只有在坐标
换算做对时才成立——它把「数据以参考项目游戏区左上角为原点、换算只缩放不平移」
这个判断从推理变成了可执行的断言。

校验那几条同样重要：数据写错时必须**在加载那一刻、指着出错的地方**炸，
而不是等运行到那一波敌机时才炸——那时已经离出错的地方很远了。
"""

import json

import pytest

from touhou import constants
from touhou.core.paths import assetPath
from touhou.game.levelData import LevelFormatError, loadLevel

LEVEL_PATH = assetPath("levels", "level_1.json")

# 游戏区的竖直中轴（x 的镜像轴）
PLAYFIELD_MIRROR_AXIS = constants.PLAYFIELD_X + constants.PLAYFIELD_WIDTH / 2

# 迁移前的算法给同一份数据算出的总弹量，作为「语义不变」的锚点
EXPECTED_TOTAL_BULLETS = 6357


@pytest.fixture(scope="module")
def level():
    return loadLevel(LEVEL_PATH)


@pytest.fixture
def mutatedLevel(tmp_path):
    """把真实关卡文件改一处再加载，用来测校验报错。"""

    def load(mutate) -> object:
        raw = json.loads(LEVEL_PATH.read_text(encoding="utf-8"))
        mutate(raw)
        path = tmp_path / "level.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        return loadLevel(path)

    return load


# —— 坐标 ——


def testSpawnPointsAreMirrorSymmetricAboutThePlayfieldCentre(level):
    """出生点里有一整片严格左右镜像，镜像轴恰好是游戏区的中轴。

    114 个出生点里有 **72 个**能在镜像位置（y 相同、x 关于中轴对称）找到伙伴。
    **这条只有在坐标换算做对时才成立**：若误以为数据是窗口绝对坐标、换算时在
    参考空间里整体平移 50，这 72 个伙伴关系会全部断掉。

    ⚠️ 另外 42 个出生点**没有**镜像伙伴——关卡自己就是这么写的（`x=605` 的 21 个
    与 `x=-113` 的 21 个既不镜像也不同 y），不是换算丢的。所以断言的是「恰好 72」。
    """
    starts = [spawn.path[0] for spawn in level.spawns]

    def hasMirrorPartner(point) -> bool:
        mirrorX = 2 * PLAYFIELD_MIRROR_AXIS - point.x
        return any(
            other.x == pytest.approx(mirrorX, abs=1e-9)
            and other.y == pytest.approx(point.y, abs=1e-9)
            for other in starts
        )

    paired = sum(1 for point in starts if hasMirrorPartner(point))
    assert paired == 72, f"镜像出生点数量不对（{paired}），坐标原点可能错了"


def testHorizontalExcursionsAreEqualOnBothSides(level):
    """左右越界量严格相等——沿中轴镜像的直接推论，也是原点放对的旁证。"""
    xs = [point.x for spawn in level.spawns for point in spawn.path]
    left = constants.PLAYFIELD_X - min(xs)
    right = max(xs) - (constants.PLAYFIELD_X + constants.PLAYFIELD_WIDTH)

    assert left == pytest.approx(right, abs=1e-9)


# —— 内容 ——


def testLoadsEverySpawnAndWave(level):
    assert len(level.spawns) == 114
    assert level.name == "level_1"
    # 65 秒的杂鱼波 + BOSS 那一场（中 BOSS 在第 3840 帧出场，留 45 秒给它）。
    # 注意 `durationFrames` 目前**没有任何运行期消费者**——关卡不会因为时长到了
    # 就结束。这里改的是「这一关有多长」这个声明，不是行为。
    assert level.durationFrames == 110 * constants.FPS


def testLoadsTheMidboss(level):
    """中 BOSS 的挂载点真的被读进来了（不只是校验过格式）。

    这条守住「JSON 管何时出、代码管怎么打」这条分工的两半：时刻在数据里，
    脚本是已经 import 好的可调用对象，弹型参数也建好了。
    """
    assert len(level.bosses) == 1
    midboss = level.bosses[0]

    assert midboss.name == "小悪魔"
    assert midboss.atFrame == 3840.0
    assert midboss.segments == 1
    assert midboss.startPosition.y < constants.PLAYFIELD_Y, "从游戏区上方进场"

    # 攻击表建好了，而且是**共享实例**那套（子弹规格走 _Caches）
    assert sorted(midboss.attacks) == ["big", "kunai"]
    assert midboss.attacks["kunai"].pattern == "long_random"
    assert midboss.attacks["kunai"].params.intervalFrames == 20

    assert callable(midboss.script)
    assert midboss.script.__name__ == "midbossScript"

    # 真立绘：有就挂在挂载点上，尺寸与贴图一致（判定半径由 `Boss` 从短边推）
    assert midboss.spriteSheet is not None, "关卡数据里写了 sprite，就该建出表来"
    assert midboss.spriteSheet.frameWidth == 32
    assert midboss.spriteSheet.frameHeight == 48


def testBossSpriteIsOptional(mutatedLevel):
    """没写 `sprite` 是合法的——`Boss` 会自己烘一张占位图（规格 §6.7）。"""

    def mutate(raw):
        del raw["bosses"]["midboss"]["sprite"]

    assert mutatedLevel(mutate).bosses[0].spriteSheet is None


def testBadBossSpriteReportsItsLocation(mutatedLevel):
    """`sprite` 里写错帧数要当场报出来，且路径指到 `bosses.midboss.sprite`。"""

    def mutate(raw):
        raw["bosses"]["midboss"]["sprite"]["frameCount"] = 3

    with pytest.raises(LevelFormatError) as error:
        mutatedLevel(mutate)
    assert "bosses.midboss.sprite.frameCount" in str(error.value)


def testBossAppearsAfterTheLastWave(level):
    """中 BOSS 排在最后一波敌机之后——它是道中的收尾，不该与小怪波挤在一起。"""
    lastSpawnEnd = max(spawn.frame + spawn.durationFrames for spawn in level.spawns)
    assert level.bosses[0].atFrame > lastSpawnEnd, "BOSS 出场时最后一波敌机要已经飞完"


def testSpawnsAreSortedByFrame(level):
    frames = [spawn.frame for spawn in level.spawns]
    assert frames == sorted(frames)


def testSimultaneousSpawnsAreNotDeduplicated(level):
    """同刻出生的双生一个都不能少。

    36 组时刻各出现两次。用 dict/set 按时刻去重会静默丢掉每一对的一半——
    关卡看起来只是「敌人少了一半」，不会报错。
    """
    from collections import Counter

    counts = Counter(spawn.frame for spawn in level.spawns)
    assert sum(1 for count in counts.values() if count > 1) == 36
    assert sum(counts.values()) == 114


def testSpriteSheetsAndBulletSpecsAreShared(level):
    """贴图与子弹规格都收敛成共享实例。

    这不是优化而是正确性：旋转缓存是每张表一份，给 114 个敌人各建一张表会让
    docs/DESIGN.md 承诺的「360 × 帧数」上界乘以 114。

    子弹规格是 **3 个**而不是 2 个——因为同一张 `ellipse_bullet_0.png` 在
    `wide_cone` 里判定半径是 6、在 `wide_ring` 里是 4，按路径共享会让其中一种
    的判定圈凭空大一半。
    """
    sheets = {id(spawn.enemyType.spriteSheet) for spawn in level.spawns}
    assert len(sheets) == 2

    specs = {id(attack.params.bullet) for spawn in level.spawns for attack in spawn.attacks}
    assert len(specs) == 3
    assert {(spec.radius, spec.spriteSheet.frameWidth) for spec in _specsOf(level)} == {
        (4.0, 16),
        (6.0, 24),
        (4.0, 24),
    }


def _specsOf(level):
    seen = {}
    for spawn in level.spawns:
        for attack in spawn.attacks:
            seen[id(attack.params.bullet)] = attack.params.bullet
    return seen.values()


def testTotalBulletCountIsUnchangedByTheMigration(level):
    """迁移只该改变表达、不该改变语义——总弹量是最直接的那把尺。

    6357 这个数是迁移**之前**用旧格式算出来的；迁移后再算一次必须一样。
    """
    total = sum(attack.params.bulletCount for spawn in level.spawns for attack in spawn.attacks)
    assert total == EXPECTED_TOTAL_BULLETS


def testTrajectoryDurationCoversTheLeadInSegment(level):
    """`durationFrames` 覆盖的是**整条路径**，含 `startPosition → trajectory[0]` 那一段。

    第一个出生点（7 秒那波妖精）的 `trajectory` 是 4 个控制点、速度是 1，所以
    路径共 5 点、4 个区间，总时长 **240 帧**。

    规格给的迁移公式算的是 `(len(trajectory) - 1) / speed × 60 = 180`，因为它假定
    路径只有 `trajectory`。用它的数会让每架敌机比预期早走完一段——而且不会报错，
    只是所有敌机都快了 `len/(len-1)` 倍。这条把 240 这个数钉死。
    """
    first = min(level.spawns, key=lambda spawn: spawn.frame)

    assert len(first.path) == 5, "startPosition + 4 个轨迹控制点"
    assert first.durationFrames == 240.0


# —— 校验 ——


def testRejectsUnknownPattern(mutatedLevel):
    def mutate(raw):
        raw["waves"][0]["spawns"][0]["attacks"][0]["pattern"] = "no_such_pattern"

    with pytest.raises(LevelFormatError) as error:
        mutatedLevel(mutate)

    message = str(error.value)
    assert "waves[0].spawns[0].attacks[0].pattern" in message
    assert "no_such_pattern" in message


def testRejectsUnknownParameter(mutatedLevel):
    def mutate(raw):
        raw["waves"][0]["spawns"][0]["attacks"][0]["params"]["sped"] = 150

    with pytest.raises(LevelFormatError) as error:
        mutatedLevel(mutate)

    assert "未知参数" in str(error.value)
    assert "sped" in str(error.value)


def testRejectsMissingParameter(mutatedLevel):
    def mutate(raw):
        del raw["waves"][0]["spawns"][0]["attacks"][0]["params"]["bulletCount"]

    with pytest.raises(LevelFormatError) as error:
        mutatedLevel(mutate)

    assert "缺少参数" in str(error.value)
    assert "bulletCount" in str(error.value)


def testRejectsWrongParameterType(mutatedLevel):
    """数字写成字符串是旧格式的典型事故（`"speed": "1"`），要在加载时挡住。"""
    params = None

    def mutate(raw):
        nonlocal params
        params = raw["waves"][0]["spawns"][0]["attacks"][0]["params"]
        params["speed"] = "150"

    with pytest.raises(LevelFormatError) as error:
        mutatedLevel(mutate)

    assert "waves[0].spawns[0].attacks[0].params" in str(error.value)


def testRejectsProbabilitiesNotSummingTo100(mutatedLevel):
    def mutate(raw):
        raw["waves"][0]["spawns"][0]["drop"]["probabilities"] = [10, 10, 10]

    with pytest.raises(LevelFormatError) as error:
        mutatedLevel(mutate)

    assert "概率之和应为 100" in str(error.value)


def testRejectsDropListLengthMismatch(mutatedLevel):
    def mutate(raw):
        raw["waves"][0]["spawns"][0]["drop"]["list"] = ["points"]

    with pytest.raises(LevelFormatError) as error:
        mutatedLevel(mutate)

    assert "对不上" in str(error.value)


def testRejectsFrameCountThatDisagreesWithTheImage(mutatedLevel):
    """数据说的帧数必须跟图片切出来的对得上。

    旧格式把判定半径写在了帧数的位置上，正是「照着数位读」的典型事故；
    这条校验就是为那类错准备的——不核对图片的话，它会一路蒙混到渲染才炸。
    """

    def mutate(raw):
        raw["waves"][0]["spawns"][0]["sprite"]["frameCount"] = 999

    with pytest.raises(LevelFormatError) as error:
        mutatedLevel(mutate)

    message = str(error.value)
    assert "frameCount" in message
    assert "999" in message


def testRejectsWaveFrameInconsistentWithItsSpawns(mutatedLevel):
    def mutate(raw):
        raw["waves"][0]["atFrame"] = 1

    with pytest.raises(LevelFormatError) as error:
        mutatedLevel(mutate)

    assert "waves[0].atFrame" in str(error.value)


def testRejectsBooleanWhereNumberExpected(mutatedLevel):
    """`true` 在 Python 里能混进 `int`——写错成布尔值时必须挡住。"""

    def mutate(raw):
        raw["waves"][0]["spawns"][0]["hp"] = True

    with pytest.raises(LevelFormatError) as error:
        mutatedLevel(mutate)

    assert "hp" in str(error.value)


def testAcceptsTheRealLevel(level):
    """真实关卡必须能通过全部校验——上面那些校验不能是误报体质。"""
    assert len(level.spawns) == 114


def testBigBulletCarriesItsOwnRadiusAndRotationPolicy(level):
    """大玉：判定 35px、**不跟着速度转**。

    半径 35 是素材里那条判定圈量出来的（球体 36px，圈就画在球缘上）。
    「不转」不是省事：这张贴图 172×172，转一圈进预旋转缓存就是几十 MB
    （`SpriteSheet.getRotated` 的缓存是每张表一份），而圆球转了也看不出来。
    """
    bullet = level.bosses[0].attacks["big"].params.bullet

    # 贴图从原图的 172px 缩到 77px（0.45×），判定按同一比例给（35 → 15.75）：
    # 判定 ≈ 球体，这是原作大玉的手感。
    assert bullet.radius == pytest.approx(15.75)
    assert bullet.rotatesToVelocity is False
    assert bullet.spriteSheet.frameWidth == 77
    assert bullet.spriteSheet.frameCount == 1
    assert level.bosses[0].attacks["big"].params.bulletCount == 12
    # 比例断言写成**与原图比**：以后改缩放不用改这条，它守的是「贴图缩了判定
    # 也要跟着缩」——只缩贴图会做出判定圈比看得见的球还大的子弹。
    # 容差 1%：缩放后贴图尺寸要取整（172×0.45 = 77.4 → 77），比例因此差不到千分之五。
    assert bullet.radius / bullet.spriteSheet.frameWidth == pytest.approx(35 / 172, rel=0.01)


def testRotationPolicyDefaultsToTrue(mutatedLevel):
    """数据里没写 `rotatesToVelocity` 就按「要转」处理。

    与这个字段出现之前的行为一致——苦无那种尖头弹必须跟着速度转，不转就歪。
    """
    level = mutatedLevel(lambda raw: raw)
    assert level.bosses[0].attacks["kunai"].params.bullet.rotatesToVelocity is True


def testRejectsNonBooleanRotationPolicy(mutatedLevel):
    def mutate(raw):
        raw["bosses"]["midboss"]["attacks"]["kunai"]["params"]["bullet"]["rotatesToVelocity"] = (
            "yes"
        )

    with pytest.raises(LevelFormatError) as error:
        mutatedLevel(mutate)
    assert "bosses.midboss.attacks.kunai.params.bullet.rotatesToVelocity" in str(error.value)
