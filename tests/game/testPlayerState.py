"""自机的状态机：受击、死亡炸弹、复活、射击与炸弹。

规格把两处边界钉死了，这个文件的大部分篇幅都在守它们：
死亡炸弹窗口（§8.5：第 8 帧按 X 存活、第 9 帧死亡）与复活无敌（180 帧）。
其余的状态划分（`dying` 之外的三态）是本项目定的，见 player.py 的模块文档。

`step` 夹具推的是 `player` 夹具里那个自机；要推自己造的自机（改过残机、
火力、炸弹数的那种）就用 `runPlayer(other, FrameInput(...))`。
"""

import pytest

from touhou import constants
from touhou.core.input import FrameInput
from touhou.core.vector2 import Vector2
from touhou.game.entities.player import (
    BLINK_PERIOD_FRAMES,
    MARISA_POWER_TIERS,
    State,
    laneCountForPower,
    shotAnglesDeg,
)

# —— 查表：五档火力（纯函数，可脱离自机单测）——


@pytest.mark.parametrize(
    ("power", "lanes"),
    [
        (0.00, 1),  # 下限
        (0.99, 1),  # 差一点到下一档
        (1.00, 2),  # 恰好到档
        (1.99, 2),  # 差一点到 3 条那一档
        (2.40, 3),  # 本轮的起始火力
        (3.00, 4),
        (3.99, 4),
        (4.00, 6),  # 上限
        (9.99, 6),  # 超过上限也只取最高档
    ],
)
def testLaneCountForPower(power, lanes):
    """取**不超过当前火力**的最高档。

    规格 §6.3 点名参考项目的实现有缺陷（`int(0.6 * power)` 让索引 3 永远取不到，
    还被两轮有损取整），所以这张表要逐档验证，不能只测一个值。
    """
    assert laneCountForPower(power, MARISA_POWER_TIERS) == lanes


def testLaneCountBelowEveryTierStillFires():
    """火力低于第一档也要有弹道——取不到档就返回 0 的话自机一发都打不出来。"""
    assert laneCountForPower(-5.0, MARISA_POWER_TIERS) == 1


@pytest.mark.parametrize("laneCount", [1, 2, 3, 4, 6])
def testShotAnglesAreSymmetricAroundStraightUp(laneCount):
    angles = shotAnglesDeg(laneCount, constants.PLAYER_SHOT_ANGLE_STEP_DEG)
    assert len(angles) == laneCount
    assert sum(angles) == pytest.approx(0.0), "左右对称，角度和必须是 0"


@pytest.mark.parametrize("laneCount", [1, 3, 5])
def testOddLaneCountHasOneStraightUp(laneCount):
    assert 0.0 in shotAnglesDeg(laneCount, constants.PLAYER_SHOT_ANGLE_STEP_DEG)


@pytest.mark.parametrize("laneCount", [2, 4, 6])
def testEvenLaneCountHasNoStraightUp(laneCount):
    """偶数条没有正中一条——否则中间那条会和它旁边那条挤在一起。"""
    assert 0.0 not in shotAnglesDeg(laneCount, constants.PLAYER_SHOT_ANGLE_STEP_DEG)


def testAdjacentLanesAreOneStepApart():
    assert shotAnglesDeg(4, 6.0) == pytest.approx((-9.0, -3.0, 3.0, 9.0))


# —— 射击 ——


def testFirstVolleyComesOnThePressFrame(player, step, shots):
    """按下的**第一步**就出弹，不是等满 6 帧。

    等满 6 帧是 100ms 的空白，按下去到出弹能感觉到；而射击是自机最主要的
    输出手段，手感全在这一下上。
    """
    step(FrameInput(shoot=True))
    assert len(shots) == player.laneCount()


def testHoldingShootFiresEveryInterval(player, step, shots):
    """按住就一直打：第一发在按下的那一步，之后每 SHOOT_INTERVAL_FRAMES 帧一发。"""
    counts = []
    for _ in range(constants.SHOOT_INTERVAL_FRAMES * 3):
        step(FrameInput(shoot=True))
        counts.append(len(shots))

    interval = constants.SHOOT_INTERVAL_FRAMES
    assert counts == [(index // interval + 1) * player.laneCount() for index in range(len(counts))]


def testReleasingShootStopsFiring(player, step, shots):
    step(FrameInput(shoot=True))
    for _ in range(10):
        step(FrameInput())
    assert len(shots) == player.laneCount(), "松手之后不再出弹"


def testPressingAgainFiresImmediately(player, step, shots):
    """松开再按，第一发立刻出来——6 帧间隔是「一直按住」的节奏，不是硬直。"""
    step(FrameInput(shoot=True))
    step(FrameInput())
    step(FrameInput(shoot=True))
    assert len(shots) == 2 * player.laneCount()


@pytest.mark.parametrize(
    ("power", "lanes"),
    [(0.00, 1), (1.00, 2), (2.40, 3), (3.00, 4), (4.00, 6)],
)
def testPlayerFiresOneBulletPerLaneOfItsPowerTier(makePlayer, runPlayer, shots, power, lanes):
    """五档火力各打一次，弹道数必须与档位表一致。"""
    shooter = makePlayer(power=power)
    runPlayer(shooter, FrameInput(shoot=True))
    assert len(shots) == lanes


def testFiredBulletsUseThePlayersSpecAndGoUp(player, step, shots):
    """子弹用的是自机那一份规格（贴图同一张、命中同一份缓存），且朝上飞。"""
    step(FrameInput(shoot=True))
    expected = shotAnglesDeg(player.laneCount(), constants.PLAYER_SHOT_ANGLE_STEP_DEG)
    assert sorted(bullet.angleDeg for bullet in shots.active) == pytest.approx(sorted(expected))
    for bullet in shots.active:
        assert bullet.velocity.y < 0, "自机子弹朝上打，写反了会朝着自己人飞"
        assert bullet.spriteSheet is player.shotSpec.spriteSheet
        assert bullet.damage == player.shotSpec.damage


# —— 炸弹 ——


def testBombCostsOneAndClearsEnemyBullets(player, step, enemyBullets, enemyBulletSpec):
    for x in range(5):
        enemyBullets.spawn(enemyBulletSpec, Vector2(100 + 10 * x, 200), 0, 0)

    step(FrameInput(bomb=True))

    assert player.bombs == constants.START_BOMBS - 1
    assert len(enemyBullets) == 0, "炸弹的清弹那一半"
    assert player.invincibleFrames == constants.BOMB_INVINCIBILITY_FRAMES, "炸弹的无敌那一半"


def testBombDoesNothingWithoutStock(makePlayer, runPlayer, enemyBullets, enemyBulletSpec):
    broke = makePlayer(bombs=0)
    enemyBullets.spawn(enemyBulletSpec, Vector2(200, 300), 0, 0)

    runPlayer(broke, FrameInput(bomb=True))

    assert len(enemyBullets) == 1, "没有库存就清不掉"


def testBombDoesNotStackWhileInvincible(player, step, enemyBullets):
    """无敌期间再按 X 不该再吃一枚库存。

    没有这条守卫的话，按住 X 连按几下就能把库存一次放空——而每个炸弹给
    180 帧无敌，等于白扔。
    """
    step(FrameInput(bomb=True))
    remaining = player.bombs
    step(FrameInput(bomb=True))
    assert player.bombs == remaining


def testBombDamagesEveryEnemyOnScreen(
    player, step, enemies, enemyBulletSpec, enemyBullets, makeEnemy
):
    """全屏伤害：1 血小怪与 25 血精英当场蒸发，40 血精英差一点。

    血量分布来自真实关卡（98 架 1 血、12 架 10 血、2 架 25 血、2 架 40 血），
    所以这三档就是「雷打完之后场上还剩什么」的全部答案。
    """
    mob = makeEnemy(position=Vector2(200, 100), hp=1)
    elite = makeEnemy(position=Vector2(60, 380), hp=25)
    tough = makeEnemy(position=Vector2(300, 200), hp=40)
    enemies.active.extend([mob, elite, tough])

    step(FrameInput(bomb=True))

    assert mob.isDead(), "一血小怪该被雷清掉"
    assert elite.isDead(), "25 血精英也该被雷清掉"
    assert not tough.isDead(), "40 血顶级精英**故意**差一点——它要剩一口气"
    assert tough.hp == 40 - constants.PLAYER_BOMB_DAMAGE
    assert [enemy for enemy in enemies.active] == [tough], "打死的要立刻离场"
    assert len(enemyBullets) == 0, "清弹与伤害是同一件事的两半"


def testBombSpawnsTheEffectAtThePlayerPosition(player, step, effects, bombEffectFrames):
    """雷的爆炸画在**自机所在的位置**——雷是以自机为中心炸开的。"""
    player.position = Vector2(120, 300)

    step(FrameInput(bomb=True))

    assert len(effects) == 1, "放一次雷该有一个特效"
    assert effects.active[0].position == Vector2(120, 300)
    assert effects.active[0].frames is bombEffectFrames


def testBombWithoutStockDoesNoDamageAndNoEffect(makePlayer, runPlayer, effects, enemies, makeEnemy):
    """没库存时按 X 什么都不会发生——包括伤害与特效。

    守卫写在消耗之前，所以「没放成」的那次不该留下任何痕迹：多了个特效的话，
    玩家会以为自己放出雷了。
    """
    broke = makePlayer(bombs=0)
    mob = makeEnemy(position=Vector2(200, 100), hp=1)
    enemies.active.append(mob)

    runPlayer(broke, FrameInput(bomb=True))

    assert mob.hp == 1, "没库存就没有全屏伤害"
    assert len(effects) == 0, "没库存就没有特效"


# —— 受击与无敌 ——


def testHitEntersDyingWithoutLosingALife(player, step, enemyBullets, enemyBulletSpec):
    """被弹命中先进死亡炸弹窗口，**不立刻扣残机**。"""
    enemyBullets.spawn(enemyBulletSpec, player.position, 0, 0)

    step(FrameInput())

    assert player.state is State.DYING
    assert player.lives == constants.START_LIVES


def testHitStopsThePlayer(player, step, enemyBullets, enemyBulletSpec):
    """被击中的那一刻就定住。

    规格没写这一条，是本项目定的——但「已经死了还能动」会让人以为判定没生效。
    """
    enemyBullets.spawn(enemyBulletSpec, player.position, 0, 0)
    step(FrameInput())
    frozen = player.position

    step(FrameInput(right=True))

    assert player.position == frozen
    assert player.state is State.DYING


def testTheFrameYouAreHitYouDoNotFire(player, step, shots, enemyBullets, enemyBulletSpec):
    """被命中的**那一帧**打不出弹。

    这一条是 `update` 里「先判命中、命中就 return」存在的唯一理由：去掉那个
    return，玩家会在被打中的同一帧照样打出一组弹（而且那组弹还会在死亡炸弹
    窗口里继续飞）。必须在同一帧上按 Z，隔一帧再按试不出来——那时状态已经是
    `dying`，早就不开火了。
    """
    enemyBullets.spawn(enemyBulletSpec, player.position, 0, 0)

    step(FrameInput(shoot=True))

    assert player.state is State.DYING
    assert len(shots) == 0


def testTouchingAnEnemyKillsThePlayer(player, runPlayer, enemies, makeEnemy, shots):
    """撞到敌机机体上也是死——与被弹打中是同一种后果。

    顺带钉住「命中判定排在开火之前」：撞死的那一帧不该还能打出一发。
    """
    enemies.active.append(makeEnemy(position=Vector2(player.position.x, player.position.y - 4)))

    runPlayer(player, FrameInput(shoot=True))

    assert player.state is State.DYING
    assert len(shots) == 0, "被撞死的那一帧不该还能开火"


def testEnemyContactIsNotCheckedOutsideTheHitbox(player, runPlayer, enemies, makeEnemy):
    """贴着敌机但没碰到判定点就不算——判定圈不能比看起来还大。"""
    # conftest 的敌机：贴图 24×24 → 机体半径 9.6；数据半径 12。
    # 放在机体半径 + 判定点半径（9.6 + 2）之外、数据半径 + 判定点（12 + 2）之内。
    enemies.active.append(makeEnemy(position=Vector2(player.position.x, player.position.y - 13.0)))

    runPlayer(player, FrameInput())

    assert player.state is State.ALIVE, "这个距离只该「打得中」，不该「撞得到」"


def testInvinciblePlayerIgnoresEnemyContact(player, runPlayer, enemies, makeEnemy):
    player.invincibleFrames = 120
    enemies.active.append(makeEnemy(position=Vector2(player.position.x, player.position.y)))

    runPlayer(player, FrameInput())

    assert player.state is State.ALIVE
    assert player.lives == constants.START_LIVES


def testInvinciblePlayerIgnoresHits(player, step, enemyBullets, enemyBulletSpec):
    player.invincibleFrames = 120
    enemyBullets.spawn(enemyBulletSpec, player.position, 0, 0)

    step(FrameInput())

    assert player.state is State.ALIVE
    assert player.lives == constants.START_LIVES


def testInvincibilityRunsOut(player, step, enemyBullets, enemyBulletSpec):
    """无敌是有限的——这条守的是「无敌帧数真的在减」，不是永远无敌。"""
    player.invincibleFrames = 1
    step(FrameInput())
    assert not player.isInvincible()

    enemyBullets.spawn(enemyBulletSpec, player.position, 0, 0)
    step(FrameInput())

    assert player.state is State.DYING


def testInvinciblePlayerBlinks(player, step):
    """无敌期间立绘闪烁，否则「现在是不是无敌」肉眼看不出来。"""
    player.invincibleFrames = 1000
    seen = set()
    for _ in range(2 * BLINK_PERIOD_FRAMES):
        step(FrameInput())
        seen.add(player.isVisible())
    assert seen == {True, False}


# —— 死亡炸弹窗口（规格 §8.5 把边界钉死了）——


def testDeathBombOnTheEighthFrameSurvives(player, step):
    """第 8 帧按 X：转成一次炸弹、不扣残机。"""
    player.enterDying()
    for _ in range(constants.DEATHBOMB_WINDOW_FRAMES - 1):
        step(FrameInput())
    assert player.state is State.DYING, "8 帧窗口还没走完"

    step(FrameInput(bomb=True))  # 第 8 帧

    assert player.state is State.ALIVE
    assert player.lives == constants.START_LIVES, "死亡炸弹的定义就是不用死"
    assert player.bombs == constants.START_BOMBS - 1


def testDeathBombOnTheNinthFrameIsTooLate(player, step):
    """第 9 帧按 X：窗口已过，照死。"""
    player.enterDying()
    for _ in range(constants.DEATHBOMB_WINDOW_FRAMES):
        step(FrameInput())
    assert player.state is State.DYING, "第 9 帧才判死"

    step(FrameInput(bomb=True))  # 第 9 帧

    assert player.state is not State.DYING
    assert player.lives == constants.START_LIVES - 1
    assert player.bombs == constants.START_BOMBS, "人都死了，炸弹不该被消耗"


def testDeathBombOnTheFirstFrameSurvives(player, step):
    player.enterDying()
    step(FrameInput(bomb=True))
    assert player.state is State.ALIVE
    assert player.lives == constants.START_LIVES


def testDeathBombNeedsStock(makePlayer, runPlayer):
    """没有炸弹时窗口照常走完——不能靠按 X 续命。"""
    broke = makePlayer(bombs=0)
    broke.enterDying()

    for _ in range(constants.DEATHBOMB_WINDOW_FRAMES + 1):
        runPlayer(broke, FrameInput(bomb=True))

    assert broke.lives == constants.START_LIVES - 1
    assert broke.state is not State.DYING


# —— 复活与残机 ——


def testRespawnRisesFromBelowThePlayfield(player, step, enemies, enemyBullets, effects):
    playfieldBottom = constants.PLAYFIELD_Y + constants.PLAYFIELD_HEIGHT
    player.enterDying()
    player.die(enemies, enemyBullets, effects)

    assert player.state is State.RESPAWNING
    assert player.lives == constants.START_LIVES - 1
    assert player.invincibleFrames == constants.RESPAWN_INVINCIBILITY_FRAMES

    step(FrameInput())
    assert player.position.y > playfieldBottom, "从游戏区下方升起"

    for _ in range(constants.RESPAWN_RISE_FRAMES - 2):
        step(FrameInput(right=True))
    assert player.state is State.RESPAWNING
    assert player.position.x == pytest.approx(player.respawnPosition.x), "升起期间不可操作"

    step(FrameInput())
    assert player.state is State.ALIVE
    assert player.position == player.respawnPosition


def testRespawnKeepsInvincibilityAfterRising(player, step, enemies, enemyBullets, effects):
    """升起结束后剩余的无敌时间仍然有效——否则一复活就会被同一波弹打死。"""
    player.enterDying()
    player.die(enemies, enemyBullets, effects)
    for _ in range(constants.RESPAWN_RISE_FRAMES):
        step(FrameInput())

    assert player.state is State.ALIVE
    assert player.isInvincible()
    assert player.invincibleFrames == constants.RESPAWN_INVINCIBILITY_FRAMES - (
        constants.RESPAWN_RISE_FRAMES
    )


def testTheLastSpareStillRespawns(makePlayer, runPlayer):
    """残机 1 时死亡应当**照样复活**，只是残机变成 0。

    这是玩家实测报上来的 bug：原来的写法是「先减再判」，残机 1 减成 0 就
    直接出局，白白少一条命。残机显示的是剩余备命，0 表示「最后一条命、
    没有备命了」——玩家还在场上打。
    """
    lastSpare = makePlayer(lives=1)
    lastSpare.enterDying()
    for _ in range(constants.DEATHBOMB_WINDOW_FRAMES + 1):
        runPlayer(lastSpare, FrameInput())

    assert lastSpare.lives == 0
    assert lastSpare.state is State.RESPAWNING, "还有最后一条命，要复活"

    for _ in range(constants.RESPAWN_RISE_FRAMES):
        runPlayer(lastSpare, FrameInput())
    assert lastSpare.state is State.ALIVE
    assert lastSpare.lives == 0, "残机 0 是合法的游戏内状态"


def testWithNoSpareLeftDyingEndsTheRun(makePlayer, runPlayer, shots):
    """残机 0 时再死：不再复活。

    本轮没有结算画面可去，所以游戏只是不再把自机放回来（敌人照飞来）。
    结果画面落地时这条测试要跟着改。
    """
    noSpare = makePlayer(lives=0)
    noSpare.enterDying()
    for _ in range(constants.DEATHBOMB_WINDOW_FRAMES + 1):
        runPlayer(noSpare, FrameInput())

    assert noSpare.lives == 0
    assert noSpare.state is State.DEAD
    assert not noSpare.isVisible(), "出局之后不该还画着自机"

    for _ in range(30):
        runPlayer(noSpare, FrameInput(right=True, shoot=True))
    assert noSpare.state is State.DEAD, "出局之后既不复活也不再开火"
    assert len(shots) == 0


def testStartLivesAllowsOneMoreDeath(makePlayer, runPlayer):
    """初始残机 3 一共能死 4 次：3 次掉备命，第 4 次出局。"""
    player = makePlayer()

    for death in range(constants.START_LIVES):
        player.enterDying()
        for _ in range(constants.DEATHBOMB_WINDOW_FRAMES + 1):
            runPlayer(player, FrameInput())
        assert player.lives == constants.START_LIVES - 1 - death
        assert player.state is State.RESPAWNING, f"第 {death + 1} 次死亡应当复活"

    player.enterDying()
    for _ in range(constants.DEATHBOMB_WINDOW_FRAMES + 1):
        runPlayer(player, FrameInput())
    assert player.state is State.DEAD, "第 4 次死亡才是出局"


# —— 死亡冲击波（特效 + 消弹 + 全屏掉血，三件事同帧）——


def _deathStep(player, runPlayer, frames=constants.DEATHBOMB_WINDOW_FRAMES + 1):
    """把死亡炸弹窗口走完，让 `die()` 发生。"""
    player.enterDying()
    for _ in range(frames):
        runPlayer(player, FrameInput())


def testDeathSpawnsTheEffectAtTheDeathPosition(player, runPlayer, effects, deathEffectFrames):
    elsewhere = Vector2(120, 300)
    player.position = elsewhere

    _deathStep(player, runPlayer)

    assert len(effects) == 1, "死亡该放一个特效"
    effect = effects.active[0]
    assert effect.position == elsewhere, "特效要炸在**死亡的位置**，不是复活点"
    assert effect.position != player.respawnPosition, (
        "这两个位置在这条测试里必须不同，否则测不出东西"
    )
    assert effect.frames is deathEffectFrames


def testDeathClearsEnemyBulletsAndDamagesEveryEnemy(
    player, runPlayer, enemyBullets, enemyBulletSpec, enemies, makeEnemy
):
    """消弹与掉血和特效**同一帧**发生——它们是同一个事件。"""
    for x in range(4):
        enemyBullets.spawn(enemyBulletSpec, Vector2(100 + 10 * x, 200), 0, 0)
    mob = makeEnemy(position=Vector2(200, 100), hp=1)
    elite = makeEnemy(position=Vector2(60, 380), hp=25)
    enemies.active.extend([mob, elite])

    _deathStep(player, runPlayer)

    assert len(enemyBullets) == 0, "死亡要清空全场敌弹"
    assert mob.isDead(), "一血小怪该被冲击波秒掉"
    assert elite.hp == 25 - constants.PLAYER_DEATH_DAMAGE
    assert [enemy for enemy in enemies.active] == [elite], "打死的小怪要立刻离场"


def testDeathBombIsABombNotADeath(
    player,
    runPlayer,
    effects,
    bombEffectFrames,
    enemyBullets,
    enemyBulletSpec,
    enemies,
    makeEnemy,
):
    """死亡炸弹救回来的那次**不是死亡**：不扣残机、不补雷、不走死亡那份结算。

    但炸弹自己的那一份照旧——它已经是一次货真价实的雷了：消弹、全屏伤害、
    放雷特效三样都在。判据用**伤害值**区分两条路：死亡冲击波只打
    `PLAYER_DEATH_DAMAGE`（1），雷打 `PLAYER_BOMB_DAMAGE`（38），所以一架
    40 血的精英剩下的血是两条路的分水岭。
    """
    for x in range(3):
        enemyBullets.spawn(enemyBulletSpec, Vector2(100 + 10 * x, 200), 0, 0)
    elite = makeEnemy(position=Vector2(200, 100), hp=40)
    enemies.active.append(elite)

    player.enterDying()
    runPlayer(player, FrameInput(bomb=True))

    assert player.state is State.ALIVE, "前提：这次死亡炸弹成功了"
    assert player.lives == constants.START_LIVES, "没死就不该扣残机"
    assert player.bombs == constants.START_BOMBS - 1, "代价是一枚雷"

    assert len(enemyBullets) == 0, "雷自己的清弹照旧"
    assert elite.hp == 40 - constants.PLAYER_BOMB_DAMAGE, "雷自己的伤害照旧"
    assert elite.hp != 40 - constants.PLAYER_DEATH_DAMAGE, (
        "这一条就是「不是死亡」：走死亡那条路的话只掉 1 血"
    )

    assert [effect.frames for effect in effects.active] == [bombEffectFrames], (
        "放的是雷的特效，不是死亡特效"
    )


def testTheLastDeathAlsoFiresAShockwave(
    makePlayer, runPlayer, effects, enemyBullets, enemies, makeEnemy
):
    """最后一条命也没了的那次同样是死亡，冲击波照样发生。"""
    noSpare = makePlayer(lives=0)
    mob = makeEnemy(position=Vector2(200, 100), hp=1)
    enemies.active.append(mob)

    _deathStep(noSpare, runPlayer)

    assert noSpare.state is State.DEAD
    assert len(effects) == 1
    assert mob.isDead()


def testPlayerWithoutDeathFramesSkipsTheEffect(
    makePlayer, runPlayer, effects, enemyBullets, enemies
):
    """没配贴图时不画特效，但消弹与掉血照常——它们不是「有没有素材」的问题。"""
    bare = makePlayer(effectFrames=())

    _deathStep(bare, runPlayer)

    assert len(effects) == 0
    assert bare.state is State.RESPAWNING


# —— 死亡补雷 ——


def _dieOnce(player, runPlayer):
    """走完一次完整的死亡（窗口超时）。"""
    player.enterDying()
    for _ in range(constants.DEATHBOMB_WINDOW_FRAMES + 1):
        runPlayer(player, FrameInput())


def testDeathRefillsBombs(makePlayer, runPlayer):
    """死亡后雷不足 START_BOMBS 枚就补足。"""
    player = makePlayer(bombs=1)

    _dieOnce(player, runPlayer)

    assert player.bombs == constants.START_BOMBS


def testDeathRefillIsNotACap(makePlayer, runPlayer):
    """补雷只补不减：本来就有更多的话不动它。

    现在还没有道具能让人超过 START_BOMBS，但「补足」与「重置」是两条不同的
    规则，写成 `self.bombs = START_BOMBS` 会在将来有道具时**倒扣**玩家的雷。
    """
    player = makePlayer(bombs=constants.START_BOMBS + 2)

    _dieOnce(player, runPlayer)

    assert player.bombs == constants.START_BOMBS + 2


def testDeathBombConsumptionIsNotRefunded(player, step, enemyBullets):
    """死亡炸弹救回来的那次**不算死亡**，雷不该被补回去。

    补雷发生在 `die()` 里，而死亡炸弹走的是另一条路（消耗一枚、活下来）。
    两条路混在一起的话，玩家可以「按 X 续命 + 白拿回那枚雷」，等于无限雷。
    """
    player.enterDying()
    step(FrameInput(bomb=True))
    assert player.state is State.ALIVE
    assert player.bombs == constants.START_BOMBS - 1, "用掉的那枚不该被补回来"
