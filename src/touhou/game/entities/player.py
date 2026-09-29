"""自机。

移动、立绘、边界约束（原有）加上**射击、炸弹、受击与残机**。

## 状态机

规格只点名了 `dying`，其余三态是这里定的：

```
alive ──被弹命中──> dying（8 帧死亡炸弹窗口，不能动也不能射）
                     ├─ 窗口内按下 X 且还有炸弹 → 消耗一枚、清空敌弹、回复无敌 → alive
                     └─ 超时 → 残机 -1、雷补足 → respawning（从下方升起 + 无敌）→ alive
                                                                                  │
                                                            残机已是 0 时再死 ──> dead
```

- **残机是「剩余备命」**：残机 0 时玩家还在场上（那是最后一条命），再死才出局。
  所以先判再减，`START_LIVES = 3` 一共能死 4 次。详见 `die()`。
- **死亡补雷**：复活时若雷不足 `START_BOMBS` 枚就补足，多了不动。理由见 `die()`。
- **`dying` 期间不能移动**：被击中的那一刻就该定住（规格没写，这里定）。
- **无敌期间再中弹忽略**；`dying` 期间再中弹也忽略（窗口已经在跑）。
- **`dead`（最后一条命也没了）本轮不做 Game Over**：没有结算画面可去，所以只是停止复活。

## 为什么 `update()` 要收下两个子弹场

自机要开火就得往场上放子弹、要用炸弹就得清空敌弹——**这不是可选依赖**，
离了它们这两件事做不了。`EnemyField.update(bulletField, playerPosition)` 是同一个取向。
"""

# 为注解开启延迟求值，理由见 vector2.py 的同类注释
from __future__ import annotations

import enum

import pygame

from touhou import constants
from touhou.core.collider import Collider
from touhou.core.input import FrameInput
from touhou.core.spriteSheet import SpriteSheet
from touhou.core.vector2 import Vector2
from touhou.game import collision
from touhou.game.bulletField import BulletField
from touhou.game.effectField import EffectField
from touhou.game.enemyField import EnemyField
from touhou.game.entities.bullet import BulletSpec

# 每帧推进多少动画帧。立绘是 8 帧循环，这个速度大约每 10 帧换一张。
ANIMATION_FRAMES_PER_TICK = 0.1

# 无敌时立绘每隔几帧隐去一次，做出闪烁效果。
# 没有它的话「现在是不是无敌」肉眼完全看不出来——而这是玩家最需要的信息之一。
BLINK_PERIOD_FRAMES = 4

# 魔理沙的火力档位：每档是（所需最低 power, 弹道数）。
#
# 规格 §6.3 给了这张表，并**点名参考项目的实现有缺陷**（`int(0.6 * power)` 让索引 3
# 永远取不到，还被两轮有损取整），所以不要照搬原代码。
#
# 放在这里而不是 constants.py：它是**角色**的属性。规格说「速度、射速、弹幕形态
# 放进角色配置表，不硬编码在逻辑里」——等有第二个自机时再抽成真正的配置表，
# 现在为一个人建一张表只是形式主义。
MARISA_POWER_TIERS: tuple[tuple[float, int], ...] = (
    (0.00, 1),
    (1.00, 2),
    (2.00, 3),
    (3.00, 4),
    (4.00, 6),
)


class State(enum.Enum):
    ALIVE = enum.auto()
    DYING = enum.auto()
    RESPAWNING = enum.auto()
    DEAD = enum.auto()


def _framesPerFrame(frames: tuple[pygame.Surface, ...], totalFrames: int) -> int:
    """一张特效图播几帧：总时长 ÷ 张数。

    **总时长是调参量**（`DEATH_EFFECT_FRAMES` / `BOMB_EFFECT_FRAMES`），张数是
    美术量——改了张数不该顺手把手感也改了，所以这个除法只在这里做一次。

    内外两层 `max(1, ...)` 各管一件事：内层是除零兜底（张数为 0 时这张表根本
    不会被读，放特效的地方会先返回）；外层保证张数多于总帧数时每张至少播一帧，
    而不是出现「一张播 0 帧」的卡死。
    """
    return max(1, totalFrames // max(1, len(frames)))


def clampToPlayfield(position: Vector2, halfSize: Vector2) -> Vector2:
    """把位置限制在游戏区内，保证整个立绘不越界。

    halfSize 是立绘半宽半高——用立绘尺寸而非判定点做约束，因为玩家看到的
    是立绘，立绘探出边界会显得很怪，哪怕判定点还在场内。

    倾斜 ±7° 后立绘外接矩形从 25×50 涨到约 30×52，贴边时外接矩形会探出
    游戏区约 2.5px。实测（marisa_forward.png 第 0 帧，±7°，四边贴齐）探出
    的部分全部是透明像素，可见像素全部在游戏区内，所以钳制沿用平帧
    halfSize 即可，不必加宽——加宽只会让自机在离边更远处提前停下。
    """
    minX = constants.PLAYFIELD_X + halfSize.x
    maxX = constants.PLAYFIELD_X + constants.PLAYFIELD_WIDTH - halfSize.x
    minY = constants.PLAYFIELD_Y + halfSize.y
    maxY = constants.PLAYFIELD_Y + constants.PLAYFIELD_HEIGHT - halfSize.y

    return Vector2(min(max(position.x, minX), maxX), min(max(position.y, minY), maxY))


def laneCountForPower(power: float, tiers: tuple[tuple[float, int], ...]) -> int:
    """按火力查弹道数：取**不超过当前火力**的最高档。

    纯函数，与档位表分开，所以五个档位可以逐个测——本轮 `power` 固定为
    `POWER_START`（没有道具，没人能改变它），可达的档位只有一个，
    但查表本身要能被完整验证。
    """
    lanes = tiers[0][1]
    for minimumPower, tierLanes in tiers:
        if power >= minimumPower:
            lanes = tierLanes
    return lanes


def shotAnglesDeg(laneCount: int, stepDeg: float) -> tuple[float, ...]:
    """把 N 条弹道均分在正上方两侧，返回各自的绝对角度。

    **规格只说了「均分角度发射」，没给夹角**，所以 `stepDeg` 是起点值。
    奇数条有正中一条、偶数条没有——与扇形弹幕同一个道理。

    这也是纯函数：自机的位置、火力、状态都不影响「N 条弹道朝哪打」。
    """
    centerIndex = (laneCount - 1) / 2
    return tuple((index - centerIndex) * stepDeg for index in range(laneCount))


class Player(Collider):
    """自机。

    继承 `Collider` 的道理与 `Bullet`、`Enemy` 相同：自机**是**一个判定圆，
    于是 `bulletField.hits(player)` 直接就能用，不必再拆一个碰撞体出来。

    注意 `radius` 是**判定点半径**（2px），而立绘半宽半高走 `halfSize()`——
    两者刻意不同：躲弹要精确，画面上看到的却是 25×50 的立绘。
    """

    __slots__ = (
        "ageFrames",
        "animationFrame",
        "animationTimer",
        "bombEffectFrames",
        "bombEffectFramesPerFrame",
        "bombs",
        "cheater",
        "deathEffectFrames",
        "deathEffectFramesPerFrame",
        "dyingFrames",
        "facing",
        "invincibleFrames",
        "lives",
        "power",
        "respawnFrames",
        "respawnPosition",
        "shotCooldown",
        "shotSpec",
        "slow",
        "speedNormal",
        "speedSlow",
        "spriteSheet",
        "state",
    )

    ageFrames: int
    animationFrame: int
    animationTimer: float
    bombEffectFrames: tuple[pygame.Surface, ...]
    bombEffectFramesPerFrame: int
    bombs: int
    cheater: bool
    deathEffectFrames: tuple[pygame.Surface, ...]
    deathEffectFramesPerFrame: int
    dyingFrames: int
    facing: int
    invincibleFrames: int
    lives: int
    power: float
    respawnFrames: int
    respawnPosition: Vector2
    shotCooldown: int
    shotSpec: BulletSpec
    slow: bool
    speedNormal: float
    speedSlow: float
    spriteSheet: SpriteSheet
    state: State

    def __init__(
        self,
        position: Vector2,
        spriteSheet: SpriteSheet,
        shotSpec: BulletSpec,
        deathEffectFrames: tuple[pygame.Surface, ...] = (),
        bombEffectFrames: tuple[pygame.Surface, ...] = (),
        speedNormal: float = constants.PLAYER_SPEED_NORMAL,
        speedSlow: float = constants.PLAYER_SPEED_SLOW,
        lives: int = constants.START_LIVES,
        bombs: int = constants.START_BOMBS,
        power: float = constants.POWER_START,
        cheater: bool = False,
    ) -> None:
        super().__init__(constants.PLAYER_HITBOX_RADIUS, position)
        self.spriteSheet = spriteSheet
        # 子弹规格**只建一份**（调用方建好传进来，与 spriteSheet 同样的做法：
        # `Player` 不碰资源路径）。它是冻结的，所有子弹共用一份，
        # `SpriteSheet.getRotated` 的缓存因此也只有一份。
        self.shotSpec = shotSpec
        # 死亡与放雷的特效用的是自机自己的贴图（同一类资源），所以也由调用方烘好
        # 传进来。默认空元组 = 不画特效；测状态机的测试因此不必准备素材。
        #
        # 两者是**两份独立的帧**，虽然现在传进来的是同一份（暂时复用扩散环，见
        # main.py 的调用点）：原作的死亡特效与炸弹特效是两套画面，等雷的美术到位
        # 时只换 `bombEffectFrames`，不需要动死亡那一份。
        self.deathEffectFrames = deathEffectFrames
        self.deathEffectFramesPerFrame = _framesPerFrame(
            deathEffectFrames, constants.DEATH_EFFECT_FRAMES
        )
        self.bombEffectFrames = bombEffectFrames
        self.bombEffectFramesPerFrame = _framesPerFrame(
            bombEffectFrames, constants.BOMB_EFFECT_FRAMES
        )
        self.speedNormal = speedNormal
        self.speedSlow = speedSlow
        self.lives = lives
        self.bombs = bombs
        self.power = power
        self.cheater = cheater
        # 复活时从这个位置升起，也就是出生点
        self.respawnPosition = Vector2(position.x, position.y)

        # -1 左倾 / 0 直立 / +1 右倾
        self.facing = 0
        self.animationFrame = 0
        self.animationTimer = 0.0
        self.slow = False
        self.state = State.ALIVE
        self.invincibleFrames = 0
        self.dyingFrames = 0
        self.respawnFrames = 0
        # 0 = 现在就能开火，所以按下 Z 的第一步就打出第一发
        self.shotCooldown = 0
        self.ageFrames = 0

    # —— 对外可问的状态 ——

    def isAlive(self) -> bool:
        return self.state is State.ALIVE

    def isInvincible(self) -> bool:
        return self.invincibleFrames > 0

    def canBeHit(self) -> bool:
        """能不能被弹打中。无敌与 `dying` 期间都不算。"""
        return not self.cheater and self.state is State.ALIVE and not self.isInvincible()

    def isVisible(self) -> bool:
        """这一帧该不该画出来。

        无敌期间闪烁。没有这个的话「现在是不是无敌」肉眼看不出来——
        而玩家刚复活/刚放完炸弹时最需要知道的就是这件事。
        """
        if self.state is State.DEAD:
            return False
        if not self.isInvincible():
            return True
        return (self.ageFrames // BLINK_PERIOD_FRAMES) % 2 == 0

    def laneCount(self) -> int:
        return laneCountForPower(self.power, MARISA_POWER_TIERS)

    # —— 每帧推进 ——

    def update(
        self,
        frameInput: FrameInput,
        shots: BulletField,
        enemyBullets: BulletField,
        enemies: EnemyField,
        effects: EffectField,
    ) -> None:
        """推进一帧。

        五个参数按「我打出去的 → 会打死我的 → 我打得死的 → 放动画的」排，
        类型两两不同，所以顺序传错会被 mypy 拦下（strict 模式，`BulletField`
        与 `EnemyField` 不是同一个类型）。
        """
        self.slow = frameInput.slow
        self.ageFrames += 1
        self.advanceInvincibility()

        if self.state is State.DYING:
            self.updateDying(frameInput, enemyBullets, enemies, effects)
            return
        if self.state is State.RESPAWNING:
            self.updateRespawning()
            return
        if self.state is State.DEAD:
            return

        direction = frameInput.direction()
        self.move(direction)
        self.updateFacing(direction)
        self.advanceAnimation()

        # 先判命中再开火：这一帧被击中的话不该还能打出一发。
        # 敌弹与敌机机体是同一种后果（都是死），所以合在一个判断里；撞机用的是
        # 敌机的**机体半径**（比贴图略小），见 Enemy.touches。
        if self.canBeHit() and (enemyBullets.hits(self) or enemies.touches(self)):
            self.enterDying()
            return

        self.updateShooting(frameInput, shots)
        self.updateBomb(frameInput, enemies, enemyBullets, effects)

    def move(self, direction: Vector2) -> None:
        """按当前速度档位移动一步，并钳制在游戏区内。

        速度档位来自 self.slow，而它只在 update() 里由 FrameInput 写入；
        绕过 update() 直接调 move() 会沿用上一帧的档位（初始为全速）。
        这是有意为之：move 是 update 的内部步骤，不是公共入口。
        """
        speed = self.speedSlow if self.slow else self.speedNormal
        self.position = clampToPlayfield(self.position + direction * speed, self.halfSize())

    def halfSize(self) -> Vector2:
        return Vector2(self.spriteSheet.frameWidth / 2, self.spriteSheet.frameHeight / 2)

    def updateFacing(self, direction: Vector2) -> None:
        """左右移动时立绘倾斜，纯垂直或静止时回正。"""
        if direction.x > 0:
            self.facing = 1
        elif direction.x < 0:
            self.facing = -1
        else:
            self.facing = 0

    def advanceAnimation(self) -> None:
        self.animationTimer += ANIMATION_FRAMES_PER_TICK
        if self.animationTimer >= 1.0:
            self.animationTimer -= 1.0
            self.animationFrame = (self.animationFrame + 1) % self.spriteSheet.frameCount

    def advanceInvincibility(self) -> None:
        if self.invincibleFrames > 0:
            self.invincibleFrames -= 1

    # —— 射击 ——

    def updateShooting(self, frameInput: FrameInput, shots: BulletField) -> None:
        """按住 Z 就按固定间隔发弹。

        `shotCooldown` 是**倒计时**：还剩几帧才能开火，0 表示现在就能开。
        写成倒计时而不是「已经攒了几帧」，是为了让「松手时归零」自然地产出
        **按下的第一步就出弹**——攒帧数的话第一发要等满 6 帧（100ms），
        按下去到出弹有一段能感觉到的空白。归零在这里就是「攒够了」。
        """
        if not frameInput.shoot:
            self.shotCooldown = 0
            return

        if self.shotCooldown > 0:
            self.shotCooldown -= 1
            return

        # 减一是因为这一步本身算一帧：置 6 会变成每 7 帧一发。
        self.shotCooldown = constants.SHOOT_INTERVAL_FRAMES - 1
        self.fire(shots)

    def fire(self, shots: BulletField) -> None:
        """打出一组弹幕。弹道数由火力档位决定，均分在正上方两侧。"""
        for angleDeg in shotAnglesDeg(self.laneCount(), constants.PLAYER_SHOT_ANGLE_STEP_DEG):
            shots.spawn(self.shotSpec, self.position, angleDeg, constants.PLAYER_SHOT_SPEED)

    # —— 炸弹 ——

    def updateBomb(
        self,
        frameInput: FrameInput,
        enemies: EnemyField,
        enemyBullets: BulletField,
        effects: EffectField,
    ) -> None:
        if frameInput.bomb:
            self.useBomb(enemies, enemyBullets, effects)

    def useBomb(self, enemies: EnemyField, enemyBullets: BulletField, effects: EffectField) -> bool:
        """放一次雷：消耗一枚库存、清空全场敌弹、全屏敌机掉一大截血、给自己一段无敌。

        规格 §6.5 强调前两半**缺一不可**：「只有无敌没有清弹，玩家仍被弹幕困住；
        只有清弹没有无敌，按了等于白按」。

        ## 伤害

        伤害与消弹都在 `collision.playerBombShockwave` 里（游戏规则归碰撞模块，
        与死亡冲击波同一条路），这里只负责自机自己的账：扣库存、给无敌、放特效。
        伤害值见 `constants.PLAYER_BOMB_DAMAGE`：清得掉小怪与普通精英，40 血的
        顶级精英差一点打死。

        清掉的敌弹**不转化成道具**——道具系统还没有（星星、PoC 回收线、高度计分
        要一起做，规格说这两件事「必须一起实现」）。等道具落地时在这里补上。

        ## 特效

        `spawnBombEffect` 与消弹、掉血是**同一个事件**的三个表现，所以三句挨在
        一起，中间不插条件——与 `die()` 里死亡冲击波那一段是同一条规矩。

        两条守卫各管一件事：`bombs <= 0` 是没得放；`isInvincible()` 是**无敌期间
        不许再放**——少了后者，连按 X 能把库存一次放空，而每颗雷自带 180 帧
        无敌，等于白扔。返回值让调用方能区分「放了」与「没放成」。
        """
        if self.bombs <= 0 or self.isInvincible():
            return False
        self.bombs -= 1
        self.spawnBombEffect(effects)
        collision.playerBombShockwave(enemies, enemyBullets)
        self.invincibleFrames = constants.BOMB_INVINCIBILITY_FRAMES
        return True

    def spawnBombEffect(self, effects: EffectField) -> None:
        """在自机所在位置放一次放雷特效。没配贴图时不画，与死亡特效同一套判据。"""
        if not self.bombEffectFrames:
            return
        effects.spawn(self.bombEffectFrames, self.position, self.bombEffectFramesPerFrame)

    # —— 受击、死亡与复活 ——

    def enterDying(self) -> None:
        """被弹命中：**不立刻扣残机**，先进死亡炸弹窗口。"""
        self.state = State.DYING
        self.dyingFrames = constants.DEATHBOMB_WINDOW_FRAMES

    def updateDying(
        self,
        frameInput: FrameInput,
        enemyBullets: BulletField,
        enemies: EnemyField,
        effects: EffectField,
    ) -> None:
        """死亡炸弹窗口。

        帧数要数准，规格把边界钉死了（§8.5）：**第 8 帧按 X 存活、第 9 帧死亡**。
        所以窗口的 8 帧里按键都算，而第 9 帧连按键都不再看——下面两个 return
        的先后顺序就是这条边界，别调换。

        `dyingFrames` 在进入时是 8，每帧减一：
        第 1~8 帧递减（其间按键即活），第 9 帧进来时已是 0，直接死。

        按 X 走的就是 `useBomb`，包括它的两条守卫。其中「无敌期间不许再放」那条
        在这里不会拦下玩家：进入窗口的唯一入口是 `update` 里的 `canBeHit()`，
        而它已经排除了无敌的情形。

        **死亡炸弹成功时不放死亡冲击波**：那次不是死亡，`die()` 根本没被调用，
        所以不扣残机、不补雷、不炸死亡特效。炸弹自己的那一份（消弹、伤害、
        特效）照旧——它已经是一次货真价实的雷了，见 `useBomb`。
        """
        if self.dyingFrames <= 0:
            self.die(enemies, enemyBullets, effects)
            return
        if frameInput.bomb and self.useBomb(enemies, enemyBullets, effects):
            self.state = State.ALIVE
            return
        self.dyingFrames -= 1

    def die(self, enemies: EnemyField, enemyBullets: BulletField, effects: EffectField) -> None:
        """死亡：残机 -1、补雷、复活，外加**死亡冲击波**。

        **`lives` 是「剩余备命」，所以先判再减**：残机 0 时玩家还在场上打
        （那就是最后一条命），再死一次才出局。于是 `START_LIVES = 8` 一共能死
        9 次——这与原作一致，HUD 上那个数字从第一天起数的是「还能死几次不死」。
        写成「先减再判」的话残机 1 死亡就直接出局，白少一条命。

        ## 死亡冲击波

        死亡会做三件事：**出特效**（爆炸的光环）、**清空全场敌弹**、**全屏敌机
        掉一点血**。它们是同一个事件，必须同帧发生——特效是给人看的，消弹是给
        玩家的补偿，掉血是给敌人的账。清弹与掉血在 `collision.playerDeathShockwave`
        里（游戏规则），特效在这里放（自机的死亡贴图是自机自己的资源，与
        `spriteSheet` / `shotSpec` 同一类），**两条相邻的语句就是这个「同帧」的
        实现**，中间不要插条件。

        冲击波在「最后一条命也没了」时同样发生：那是死亡，只是不再复活。
        """
        self.spawnDeathEffect(effects)
        collision.playerDeathShockwave(enemies, enemyBullets)

        if self.lives <= 0:
            # 最后一条命也没了。本轮不做 Game Over：没有结算画面可去，所以只是
            # 停止复活，游戏继续跑（敌机照飞来）。结果画面落地时在这里接上。
            self.state = State.DEAD
            return

        self.lives -= 1
        self.state = State.RESPAWNING
        self.respawnFrames = constants.RESPAWN_RISE_FRAMES
        self.invincibleFrames = constants.RESPAWN_INVINCIBILITY_FRAMES
        # 死亡补雷：不足 START_BOMBS 枚就补到 START_BOMBS 枚，多了不动。
        # 原作就是这么做的，理由是手感——后期弹幕越来越密，手里没雷的话复活
        # 之后只能靠躲，翻不了盘；补雷让「死了一次」不至于变成不可逆的劣势。
        #
        # 补的是**复活时**的库存，所以死亡炸弹不能靠它续命：那次消耗发生在
        # 死亡之前，而这里是在死之后才补的。
        self.bombs = max(self.bombs, constants.START_BOMBS)
        self.dyingFrames = 0
        self.shotCooldown = 0
        self.facing = 0

    def spawnDeathEffect(self, effects: EffectField) -> None:
        """在**死亡的位置**放一次死亡特效。

        位置要在 `die()` 里取：`updateRespawning` 之后自机就跑到游戏区下方
        去了，那时再取就炸在屏幕外面。没配贴图时不画（`deathEffectFrames`
        为空），测状态机的测试因此不必为此准备素材。
        """
        if not self.deathEffectFrames:
            return
        effects.spawn(self.deathEffectFrames, self.position, self.deathEffectFramesPerFrame)

    def updateRespawning(self) -> None:
        """从游戏区下方升到出生点。升起期间不可操作（`update` 直接返回）。"""
        self.respawnFrames -= 1
        startY = constants.PLAYFIELD_Y + constants.PLAYFIELD_HEIGHT + self.halfSize().y
        progress = 1.0 - max(self.respawnFrames, 0) / constants.RESPAWN_RISE_FRAMES

        if self.respawnFrames <= 0:
            self.position = Vector2(self.respawnPosition.x, self.respawnPosition.y)
            self.state = State.ALIVE
            return
        self.position = Vector2(
            self.respawnPosition.x,
            startY + (self.respawnPosition.y - startY) * progress,
        )

    # —— 绘制 ——

    def currentFrame(self) -> pygame.Surface:
        """当前应该绘制的画面。

        倾斜立绘本阶段直接用旋转实现；后续若要更精细的表现，可换成
        预先烘焙好三组贴图。
        """
        if self.facing == 0:
            return self.spriteSheet.getFrame(self.animationFrame)
        return self.spriteSheet.getRotated(self.animationFrame, -7 if self.facing < 0 else 7)
