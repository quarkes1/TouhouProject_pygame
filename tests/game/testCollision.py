"""自机子弹 vs 敌机的碰撞。

分两件事测：**结算**（扣血、子弹消失、清弹、移除）与**粗筛的等价性**
（y 分桶是纯性能措施，唯一要守的性质是「不改变结果」）。
"""

import random
from dataclasses import replace

import pytest

from touhou import constants
from touhou.core.vector2 import Vector2
from touhou.game.bulletField import BulletField
from touhou.game.collision import (
    hitEnemy,
    playerBombShockwave,
    playerDeathShockwave,
    resolvePlayerShots,
)
from touhou.game.enemyField import EnemyField


def fieldWith(enemies) -> EnemyField:
    """一个只装着给定敌机的场，省去造关卡数据。"""
    field = EnemyField((), random.Random(0))
    field.active = list(enemies)
    return field


def spawnAt(field, spec, position, angleDeg=0.0):
    """放一颗**不动**的子弹（速度为 0），位置正好是要测的地方。"""
    return field.spawn(spec, Vector2(position.x, position.y), angleDeg, 0.0)


# —— 结算 ——


def testShotDamagesEnemyAndDisappears(shots, enemyBullets, shotSpec, makeEnemy):
    """命中扣血、子弹消失，敌机还在（血没掉完）。"""
    enemy = makeEnemy(position=Vector2(200, 100), hp=3)
    spawnAt(shots, shotSpec, enemy.position)

    resolvePlayerShots(shots, fieldWith([enemy]), enemyBullets)

    assert enemy.hp == 3 - constants.PLAYER_SHOT_DAMAGE
    assert len(shots) == 0, "自机子弹不穿透，打中就该消失"


def testKilledEnemyLeavesTheFieldAndIsReported(shots, enemyBullets, shotSpec, makeEnemy):
    enemy = makeEnemy(position=Vector2(200, 100), hp=1)
    spawnAt(shots, shotSpec, enemy.position)
    field = fieldWith([enemy])

    finished = resolvePlayerShots(shots, field, enemyBullets)

    assert enemy.isDead()
    assert len(field) == 0, "打死的敌机必须立刻离场，不能多留一帧还能被打"
    assert finished == [enemy], "返回退场名单，供调用方接掉落之类"


def testShotDamageComesFromTheSpec(shots, enemyBullets, shotSpec, makeEnemy):
    """伤害取自子弹规格，不是写死在结算里的 1。

    敌人血量有 1/10/25/40 四档，将来有强化弹时这条就是它的地基。
    """
    enemy = makeEnemy(position=Vector2(200, 100), hp=25)
    spawnAt(shots, replace(shotSpec, damage=5), enemy.position)

    resolvePlayerShots(shots, fieldWith([enemy]), enemyBullets)

    assert enemy.hp == 20


def testMissLeavesBothAlone(shots, enemyBullets, shotSpec, makeEnemy):
    """没碰到就什么都不发生——这条守的是「判定半径没被写错成贴图尺寸」。"""
    enemy = makeEnemy(position=Vector2(200, 100), hp=3)
    # 敌机半径 12 + 子弹半径 5 = 17，放 40px 外必不相交
    spawnAt(shots, shotSpec, Vector2(200, 140))

    resolvePlayerShots(shots, fieldWith([enemy]), enemyBullets)

    assert enemy.hp == 3
    assert len(shots) == 1


def testClearOnDeathEmptiesEnemyBullets(shots, enemyBullets, shotSpec, enemyBulletSpec, makeEnemy):
    """带 clearOnDeath 的精英被打死时清空全场敌弹（关卡数据里那 4 个敌人）。"""
    enemy = makeEnemy(position=Vector2(200, 100), hp=1, clearOnDeath=True)
    for x in range(3):
        spawnAt(enemyBullets, enemyBulletSpec, Vector2(100 + 10 * x, 200))
    spawnAt(shots, shotSpec, enemy.position)

    resolvePlayerShots(shots, fieldWith([enemy]), enemyBullets)

    assert len(enemyBullets) == 0


def testClearOnDeathStaysSilentWithoutTheFlag(
    shots, enemyBullets, shotSpec, enemyBulletSpec, makeEnemy
):
    enemy = makeEnemy(position=Vector2(200, 100), hp=1, clearOnDeath=False)
    spawnAt(enemyBullets, enemyBulletSpec, Vector2(100, 200))
    spawnAt(shots, shotSpec, enemy.position)

    resolvePlayerShots(shots, fieldWith([enemy]), enemyBullets)

    assert len(enemyBullets) == 1


def testFlyingAwayDoesNotClearBullets(enemyBullets, enemyBulletSpec, makeEnemy):
    """**飞出场外**的敌机不清弹，哪怕它带着 clearOnDeath。

    判据必须是「被打死」而不是「退场」：`isFinished()` 两者都包含，
    写成它就会让精英敌人飞走时替玩家清掉一屏弹——白送一个大便宜。
    """
    enemy = makeEnemy(position=Vector2(200, 100), clearOnDeath=True)
    enemy.u = 999.0  # 走完整条轨迹
    assert enemy.isFinished() and not enemy.isDead()

    spawnAt(enemyBullets, enemyBulletSpec, Vector2(100, 200))
    shots = BulletField()

    finished = resolvePlayerShots(shots, fieldWith([enemy]), enemyBullets)

    assert finished == [enemy], "飞走的也算退场，要能被告知"
    assert len(enemyBullets) == 1, "但清弹只跟死亡绑"


# —— 死亡冲击波 ——


def testShockwaveClearsEveryEnemyBullet(shots, enemyBullets, enemyBulletSpec, makeEnemy):
    for x in range(6):
        spawnAt(enemyBullets, enemyBulletSpec, Vector2(100 + 10 * x, 200))

    playerDeathShockwave(fieldWith([makeEnemy()]), enemyBullets)

    assert len(enemyBullets) == 0


def testShockwaveDamagesEveryEnemyOnScreen(shots, enemyBullets, makeEnemy):
    """全屏掉血：离得远的、离得近的，一起掉。"""
    near = makeEnemy(position=Vector2(200, 200), hp=40)
    far = makeEnemy(position=Vector2(50, 400), hp=10)
    field = fieldWith([near, far])

    playerDeathShockwave(field, enemyBullets)

    assert near.hp == 40 - constants.PLAYER_DEATH_DAMAGE
    assert far.hp == 10 - constants.PLAYER_DEATH_DAMAGE


def testShockwaveKillsTheOneHitPointMobs(enemyBullets, makeEnemy):
    """一血小怪被秒——关卡里 114 架有 98 架是 1 血，「微小但能清场」指的就是这个。

    这条同时钉住了伤害值：调大调小都会让它红（调大就秒不掉精英的档位感、
    调小就秒不了小怪）。
    """
    mobs = [makeEnemy(position=Vector2(50 * i, 100), hp=1) for i in range(5)]
    field = fieldWith(mobs)

    finished = playerDeathShockwave(field, enemyBullets)

    assert len(field) == 0, "一血小怪应当全清"
    assert {id(enemy) for enemy in finished} == {id(enemy) for enemy in mobs}, "退场名单要报全"
    assert all(enemy.isDead() for enemy in mobs)


def testShockwaveRespectsClearOnDeath(enemyBullets, enemyBulletSpec, makeEnemy):
    """冲击波打死的精英同样清弹——与自机子弹打死的是同一条规则。

    这里敌弹刚被冲击波清空过，所以看不出差别；但**判据必须走同一处**
    （`removeAndHandleDeaths`），否则将来顺序一变，同一个字段就有两套行为。
    """
    elite = makeEnemy(position=Vector2(200, 100), hp=1, clearOnDeath=True)
    spawnAt(enemyBullets, enemyBulletSpec, Vector2(100, 200))

    finished = playerDeathShockwave(fieldWith([elite]), enemyBullets)

    assert finished == [elite]
    assert len(enemyBullets) == 0


def testShockwaveOnlyChipsTheElites(enemyBullets, makeEnemy):
    """血量 10/25/40 的精英扛得住——「微小」两个字的边界。"""
    elite = makeEnemy(position=Vector2(200, 100), hp=10)

    playerDeathShockwave(fieldWith([elite]), enemyBullets)

    assert not elite.isDead()
    assert elite.hp == 10 - constants.PLAYER_DEATH_DAMAGE


def testShockwaveDoesNotKillAnythingAboveOneHitPoint(enemyBullets, makeEnemy):
    """二血的也扛得住，只掉到 1。

    **这条数字面量、不引用常量**：伤害调到 2 就会连二血的也秒掉，而关卡里血量
    的下一档直接跳到 10——2~9 这一段本来就不该有东西被一击清掉。写成
    `hp == 2 - constants.PLAYER_DEATH_DAMAGE` 的话，改常量时两边一起变，
    这个变异就永远测不出来。
    """
    tough = makeEnemy(position=Vector2(200, 100), hp=2)

    playerDeathShockwave(fieldWith([tough]), enemyBullets)

    assert not tough.isDead()
    assert tough.hp == 1


# —— 放雷的冲击波 ——


def testBombShockwaveClearsEveryEnemyBullet(enemyBullets, enemyBulletSpec, makeEnemy):
    for x in range(6):
        spawnAt(enemyBullets, enemyBulletSpec, Vector2(100 + 10 * x, 200))

    playerBombShockwave(fieldWith([makeEnemy()]), enemyBullets)

    assert len(enemyBullets) == 0


def testBombShockwaveWipesOutEverythingButTheToughest(enemyBullets, makeEnemy):
    """雷的定位：小怪与普通精英全清，只有 40 血的顶级精英剩一口气。

    **40 那一档的断言是「还剩多少」而不是「没死」**——写成后者的话，伤害调到
    100 时这条依然绿，而「差一点打死满血精英」正是这个数值存在的理由。
    """
    mob = makeEnemy(position=Vector2(200, 100), hp=1)
    elite = makeEnemy(position=Vector2(60, 380), hp=10)
    tough = makeEnemy(position=Vector2(300, 200), hp=40)
    field = fieldWith([mob, elite, tough])

    finished = playerBombShockwave(field, enemyBullets)

    assert len(field) == 1 and field.active[0] is tough, "只有顶级精英留在场上"
    assert {id(enemy) for enemy in finished} == {id(mob), id(elite)}, "退场名单要报全"
    assert tough.hp == 2, "40 - 38：差一点点，两发自机子弹补掉"


def testBombShockwaveRespectsClearOnDeath(enemyBullets, enemyBulletSpec, makeEnemy):
    """雷打死的敌人同样走上「被打死时清弹」那条路。

    这里的敌弹本来就会被雷清空，所以看不出差别；但它钉的是**走同一处结算**
    （`removeAndHandleDeaths`），否则同一个字段会分裂出两套行为。
    """
    elite = makeEnemy(position=Vector2(200, 100), hp=1, clearOnDeath=True)
    spawnAt(enemyBullets, enemyBulletSpec, Vector2(100, 200))

    finished = playerBombShockwave(fieldWith([elite]), enemyBullets)

    assert finished == [elite]
    assert len(enemyBullets) == 0


def testBombShockwaveHitsHarderThanTheDeathShockwave(enemyBullets, makeEnemy):
    """两个伤害值必须分开：死亡冲击波只打掉一层皮，雷要能清场。

    合成一个带参数的函数会让下一个人以为这两个数该一起调，所以这里把它们
    的关系显式钉住。
    """
    assert constants.PLAYER_BOMB_DAMAGE > constants.PLAYER_DEATH_DAMAGE

    died = makeEnemy(position=Vector2(200, 100), hp=40)
    playerDeathShockwave(fieldWith([died]), enemyBullets)
    bombed = makeEnemy(position=Vector2(200, 100), hp=40)
    playerBombShockwave(fieldWith([bombed]), enemyBullets)

    assert bombed.hp < died.hp


# —— y 分桶粗筛 ——


class CountingShot:
    """只实现 `hitEnemy` 用到的两样（radius 与 checkCollision）的假子弹。

    用假的而不是真的 Bullet，是为了**把比较次数数出来**：那正是分桶省下的东西。
    """

    def __init__(self, position: Vector2, radius: float, colliding: set[int]) -> None:
        self.position = position
        self.radius = radius
        self.colliding = colliding
        self.compared: list[int] = []

    def checkCollision(self, enemy) -> bool:
        self.compared.append(id(enemy))
        return id(enemy) in self.colliding


def orderedPair(enemies):
    """把敌机按 y 排好，并备好 `hitEnemy` 要的三个参数。"""
    ordered = sorted(enemies, key=lambda enemy: enemy.position.y)
    orderedYs = [enemy.position.y for enemy in ordered]
    maxRadius = max((enemy.radius for enemy in ordered), default=0.0)
    return ordered, orderedYs, maxRadius


@pytest.mark.parametrize("targetIndex", [0, 15, 29])
def testBucketingOnlyComparesYNeighbours(makeEnemy, targetIndex):
    """分桶确实把比较次数降下来了，不是「排完序还是全扫一遍」。

    比较次数必须**恰好**等于 y 邻近的那几架。三个取样位置都要测：
    只测末端的话，「窗口上界没生效（不 break）」会让它从窗口一路扫到列表末尾
    ——而末端后面已经没有元素，这个退化就正好溜过去了。

    两侧边界各有一个变异会被这条抓住：起点算错、上界不收。
    窗口放宽（比如写成两倍半径）也在这里露馅，因为它比该比的多。
    """
    enemies = [makeEnemy(position=Vector2(200, 10 * y)) for y in range(30)]
    ordered, orderedYs, maxRadius = orderedPair(enemies)
    shot = CountingShot(Vector2(200, enemies[targetIndex].position.y), 5.0, colliding=set())

    assert hitEnemy(shot, ordered, orderedYs, maxRadius) is None, "这批假子弹一个都不该命中"

    window = shot.radius + maxRadius
    neighbours = [enemy for enemy in enemies if abs(enemy.position.y - shot.position.y) <= window]
    assert len(shot.compared) == len(neighbours)
    assert len(shot.compared) < len(enemies)


def testBucketingStillFindsTheFarthestEnemy(makeEnemy):
    """窗口的另一半：y 最远的那架若真相交，必须照样打得中。

    起点算错（比如拿 `y + window` 去 bisect）会让最远的那架永远被跳过，
    而它在画面上「明明打中了」。
    """
    enemies = [makeEnemy(position=Vector2(200, 10 * y)) for y in range(30)]
    ordered, orderedYs, maxRadius = orderedPair(enemies)
    target = enemies[-1]
    shot = CountingShot(Vector2(200, target.position.y), 5.0, colliding={id(target)})

    assert hitEnemy(shot, ordered, orderedYs, maxRadius) is target


# —— 分桶与朴素全量比较逐一等价 ——


def naiveHits(shots, enemies) -> None:
    """朴素写法：每颗子弹扫一遍**全部**敌机，取 y 最小的那个相交者。

    这份实现是给测试当参照物的，所以刻意与 `collision.py` 不共用任何东西。
    """
    ordered = sorted(enemies, key=lambda enemy: enemy.position.y)
    for index in range(len(shots.active) - 1, -1, -1):
        shot = shots.active[index]
        for enemy in ordered:
            if shot.checkCollision(enemy):
                enemy.damage(shot.damage)
                shots.releaseAt(index)
                break


def buildWorld(rng, makeEnemy, spec, radiusRange=(4.0, 20.0)):
    """一片随机的战场：敌机散布在整个游戏区，子弹从下往上撒。"""
    enemies = [
        makeEnemy(
            position=Vector2(rng.uniform(0, 384), rng.uniform(0, 448)),
            hp=rng.randint(1, 6),
            radius=rng.uniform(*radiusRange),
        )
        for _ in range(12)
    ]
    shots = BulletField()
    for _ in range(40):
        spawnAt(shots, spec, Vector2(rng.uniform(0, 384), rng.uniform(0, 448)))
    return enemies, shots


def survivorState(enemies):
    """活着的敌机的可观测状态（位置 + 血量），排序后便于整体比较。"""
    return sorted(
        (round(enemy.position.x, 6), round(enemy.position.y, 6), enemy.hp)
        for enemy in enemies
        if not enemy.isFinished()
    )


def shotState(shots):
    return sorted((round(b.position.x, 6), round(b.position.y, 6)) for b in shots.active)


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def testBucketingGivesExactlyTheSameResultAsFullScan(seed, makeEnemy, shotSpec, enemyBullets):
    """同一片战场，分桶与朴素全量比较必须给出**完全相同**的伤害分布与去留。

    分桶只该省掉无用的比较，不该改变任何结果——它唯一的风险（窗口算窄了、
    漏掉本该相交的敌机）恰恰是随机对照能抓住的：漏一次，血量就对不上。
    """
    enemiesA, shotsA = buildWorld(random.Random(seed), makeEnemy, shotSpec)
    enemiesB, shotsB = buildWorld(random.Random(seed), makeEnemy, shotSpec)
    assert shotState(shotsA) == shotState(shotsB), "两边必须是同一片战场"

    resolvePlayerShots(shotsA, fieldWith(enemiesA), enemyBullets)
    naiveHits(shotsB, enemiesB)

    assert survivorState(enemiesA) == survivorState(enemiesB)
    assert shotState(shotsA) == shotState(shotsB)


def testBucketingStaysEquivalentWithBossSizedRadii(makeEnemy, shotSpec, enemyBullets):
    """半径极大的敌人（BOSS 那种）也要与朴素全量比较**逐一相同**。

    分桶的窗口是「子弹半径 + 敌机最大半径」——BOSS 一进 `active`，这个数就从
    十几涨到二十几。窗口变宽只是多扫几架，不该改变结果，但这条算式此前只在
    小半径下被验证过，所以把极值也钉一遍。
    """
    for seed in (11, 12):
        enemiesA, shotsA = buildWorld(
            random.Random(seed), makeEnemy, shotSpec, radiusRange=(22.0, 30.0)
        )
        enemiesB, shotsB = buildWorld(
            random.Random(seed), makeEnemy, shotSpec, radiusRange=(22.0, 30.0)
        )

        resolvePlayerShots(shotsA, fieldWith(enemiesA), enemyBullets)
        naiveHits(shotsB, enemiesB)

        assert survivorState(enemiesA) == survivorState(enemiesB)
        assert shotState(shotsA) == shotState(shotsB)
