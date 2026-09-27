"""关卡 BOSS。

BOSS 与敌机**在引擎眼里是同一种东西**：有血量、有判定圈、被自机子弹打、撞死自机、
死了要离场。所以 `Boss` 继承 `Enemy`，那些行为全部复用——`collision.py` 一行都不用改，
撞机判定、清弹、y 分桶、绘制都照常生效。两者的差别只有两处：

| | `Enemy` | `Boss` |
|---|---|---|
| 怎么动 | 沿样条轨迹（`u += uPerFrame`） | 脚本驱动（`moveTo` / `wait`） |
| 怎么开火 | 查时刻表（`dueAttacks`） | 开火计划（`fires`） |

## 脚本

规格 §6.7 定了写法：BOSS 的行为用**生成器协程**描述，读起来就是「先移动，然后打
一段通常攻击」。`Boss.update()` 每帧只 `next()` 一次脚本：

```python
def midbossScript(boss: Boss) -> Iterator[None]:
    boss.fires("spread")                       # 后台开始打
    yield from boss.moveTo(Vector2(192, 120), frames=60)   # 前台：边挪边打
    yield from boss.wait(180)
    boss.stopFiring()
```

**移动走 yield、开火走计划——这条分工不是风格问题**：`yield from` 是顺序的，
`yield from boss.fires(...)` 会把控制权一直交给它直到它返回，于是 BOSS 就没法边挪
边打，而边挪边打正是 BOSS 的常态。所以 `fires` 不 yield（登记一条后台计划），
`moveTo` / `wait` 才 yield（每帧一步）。

**一帧恰好推进一步**：三层 `yield from` 嵌套（脚本 → `runPhase` → 子脚本）时，
`update()` 每帧只 `next()` 一次，`yield from` 把这一步透传到最内层，中间所有层一起
挂起——不会一帧两步，也不会漏帧。有专门的测试钉这一条。

## 脚本不接触引擎

`fires` 登记的计划每帧把「该打的齐射」排进 `pending`，`dueAttacks()` 返回并清空它。
于是 `EnemyField.fire()` 那条现成的路径（算自机狙角度 → 查模板注册表 → 用注入的 rng
与 volleyIndex）原样复用，**脚本里看不到子弹场、自机、随机数**——随机弹幕因此仍然是
「同一份输入产生同一场战斗」。

弹型参数也来自**关卡数据**（`bosses.<名字>.attacks`），不是脚本里现写：脚本自带
子弹规格的话，加载器那套「同一张贴图只有一份 SpriteSheet」的保证就绕过去了，
旋转缓存会成倍地涨，而且同一颗子弹会在 JSON 与 Python 里各写一份、必然漂移。
"""

# 为注解开启延迟求值，理由见 vector2.py 的同类注释
from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass, replace

import pygame

from touhou import constants
from touhou.core.spriteSheet import SpriteSheet
from touhou.core.vector2 import Vector2
from touhou.game.entities.enemy import Enemy
from touhou.game.levelData import BossSpawn, EnemyAttack, EnemySpawn, EnemyType

# 占位立绘：帧边长（游戏区 384×448、自机立绘 25×50，BOSS 比自机大一圈半）
BOSS_FRAME_SIZE = 64
# 绕中心转一圈烘几帧。8 帧 = 每帧 45°，而机体是**五边形**（72° 才自重复）——
# 所以每一帧看起来都不一样，旋转看得见。用八边形的话 45° 正好重合，白转。
BOSS_ROTATION_FRAMES = 8
BOSS_SIDES = 5
# 多边形外接圆 / 帧边长。**这就是「打得中」的半径**（`EnemyType.radius`）：
# 贴图外圈那点光晕不算数，否则判定圈会比眼睛看到的大。
BOSS_BODY_RADIUS_RATIO = 0.36
# 光晕画到多大（帧边长的比例）。纯装饰，不参与任何判定。
BOSS_GLOW_RADIUS_RATIO = 0.48
BOSS_GLOW_RINGS = 4


@dataclass(slots=True)
class FiringPlan:
    """一条开火计划：按参数自带的节拍反复打，直到被撤掉。

    节拍取 `params.intervalFrames`（与关卡数据里敌机那套**同一个字段**），
    `volleyIndex` 从 0 起逐发自增——`wide_ring` 的「第 n 环整体旋转」靠的就是它，
    所以这里的自增方式必须与加载器 `_expandAttacks` 一致，否则螺旋会错位。
    """

    attack: EnemyAttack
    elapsedFrames: int = 0
    volleyIndex: int = 0

    def due(self) -> EnemyAttack | None:
        """本帧要打的齐射（没有就是 None），并把节拍往前推一拍。

        `max(1, ...)`：数据允许 `intervalFrames` 为 0（敌机那边是「所有波挤在同一帧」），
        而这里拿它做取模的除数——不兜住就是 ZeroDivisionError。
        """
        interval = max(1, round(self.attack.params.intervalFrames))
        firesNow = self.elapsedFrames % interval == 0
        self.elapsedFrames += 1
        if not firesNow:
            return None
        attack = replace(self.attack, volleyIndex=self.volleyIndex)
        self.volleyIndex += 1
        return attack


def bakeBossSprite(
    color: tuple[int, int, int],
    frameSize: int = BOSS_FRAME_SIZE,
    frameCount: int = BOSS_ROTATION_FRAMES,
) -> SpriteSheet:
    """画一张占位 BOSS 立绘：带光晕的多边形，绕中心旋转的 frameCount 帧。

    规格 §6.7 要求 BOSS 立绘用**程序化占位图形**（「将来替换为真实美术时逻辑代码
    零改动」），所以形状与配色都在这里、由数据里的颜色参数化，实体那边只认
    `SpriteSheet` 这个接口。

    **帧是烘出来的**（转 N 个角度写进一张横向表），不走 `SpriteSheet.getRotated`：
    那个缓存是每张表一份、键里含帧号，大尺寸立绘转一圈的内存上界正是
    docs/DESIGN.md「性能」里点名最贵的一档。烘表只占 N 帧。
    """
    sheet = pygame.Surface((frameSize * frameCount, frameSize), pygame.SRCALPHA)
    glow = _glowSurface(color, frameSize)
    body = _bodySurface(color, frameSize)

    for index in range(frameCount):
        cell = pygame.Rect(index * frameSize, 0, frameSize, frameSize)
        sheet.blit(glow, cell.topleft)
        # 只转机体：光晕是圆的，转了看不出来，没必要每帧重画一遍
        rotated = pygame.transform.rotate(body, -360.0 * index / frameCount)
        sheet.blit(rotated, rotated.get_rect(center=cell.center))

    return SpriteSheet(sheet, frameSize, frameSize)


def _bodySurface(color: tuple[int, int, int], frameSize: int) -> pygame.Surface:
    """机体：一个正多边形，外接圆半径 = `BOSS_BODY_RADIUS_RATIO` × 帧边长。

    外接圆决定了它旋转时占的最大范围——转多少度都不会超出这个圆，所以烘帧时
    不必为每帧留不同的余量。
    """
    surface = pygame.Surface((frameSize, frameSize), pygame.SRCALPHA)
    centerX = centerY = frameSize / 2
    radius = frameSize * BOSS_BODY_RADIUS_RATIO
    # 从正上方起画第一个顶点，让「朝上」这件事在帧 0 是确定的
    points = [
        (
            centerX + radius * math.sin(2 * math.pi * index / BOSS_SIDES),
            centerY - radius * math.cos(2 * math.pi * index / BOSS_SIDES),
        )
        for index in range(BOSS_SIDES)
    ]
    pygame.draw.polygon(surface, color, points)
    # 描边比机体亮一档，边缘才看得出形状
    outline = tuple(min(255, channel + 70) for channel in color)
    pygame.draw.polygon(surface, outline, points, width=2)
    pygame.draw.circle(surface, outline, (centerX, centerY), radius * 0.28)
    return surface


def _glowSurface(color: tuple[int, int, int], frameSize: int) -> pygame.Surface:
    """光晕：几圈由外到内、越来越不透明的同心圆。

    每圈画在**自己的临时表面**上再 blit 下来：`pygame.draw` 在带逐像素 alpha 的
    表面上到底做不做混合，各版本与各驱动的行为并不一致，而 blit 一定是混合。
    """
    surface = pygame.Surface((frameSize, frameSize), pygame.SRCALPHA)
    center = (frameSize / 2, frameSize / 2)
    for ring in range(BOSS_GLOW_RINGS):
        progress = (ring + 1) / BOSS_GLOW_RINGS
        radius = frameSize * BOSS_GLOW_RADIUS_RATIO * (1.0 - ring / (BOSS_GLOW_RINGS + 2))
        layer = pygame.Surface((frameSize, frameSize), pygame.SRCALPHA)
        pygame.draw.circle(layer, (*color, round(18 + 10 * progress)), center, radius)
        surface.blit(layer, (0, 0))
    return surface


class Boss(Enemy):
    """一个关卡的 BOSS。

    继承 `Enemy` 而不是另起一类：碰撞、撞机、清弹、回收、绘制全都复用，见模块文档。
    构造时合成一个**退化的 `EnemySpawn`**（单点路径、`durationFrames=1`）喂给父类，
    于是继承来的 `hasLeft()` 恒为假（`u` 永远是 0，成不了 `len(path) - 1`），
    `isFinished()` 自然退化成「只有死了才离场」，一行都不用覆盖。
    """

    __slots__ = (
        "attacksByName",
        "maxHp",
        "name",
        "pending",
        "phaseIndex",
        "plans",
        "script",
        "scriptDone",
        "segments",
    )

    attacksByName: dict[str, EnemyAttack]
    maxHp: int
    name: str
    pending: list[EnemyAttack]
    phaseIndex: int
    plans: list[FiringPlan]
    script: Iterator[None]
    scriptDone: bool
    segments: int

    def __init__(self, spawn: BossSpawn) -> None:
        # 有真立绘就用真立绘，没有才现画一张占位图（规格 §6.7：换美术时逻辑零改动）
        sheet = spawn.spriteSheet if spawn.spriteSheet is not None else bakeBossSprite(spawn.color)
        # 判定半径与敌机同一套规矩：贴图短边的一半（「打得中」的圈宁可宽松），
        # 撞机半径再乘 0.8（见下面）。占位图那条 `BOSS_BODY_RADIUS_RATIO` 只管
        # **画出来多大**，不参与判定。
        enemyType = EnemyType(
            spriteSheet=sheet, radius=min(sheet.frameWidth, sheet.frameHeight) / 2
        )
        super().__init__(
            EnemySpawn(
                frame=spawn.atFrame,
                enemyType=enemyType,
                # 单点路径：BOSS 的位置全由脚本摆布，轨迹只是父类契约的占位
                path=(Vector2(spawn.startPosition.x, spawn.startPosition.y),),
                durationFrames=1.0,
                # 占位血量：真正的血由脚本的 runPhase 给。这里**必须是正数**，
                # 否则 isDead() 一上来就为真，BOSS 会在出生那一帧被当成死掉的回收掉。
                hp=1,
                # BOSS 倒下要清屏（原作的规矩），这条走的是碰撞模块里那条
                # 「被打死的清弹」的路，与敌机的 clearOnDeath 是同一个字段
                clearOnDeath=True,
                attacks=(),
            )
        )
        # 撞机半径**不能**用 Enemy 那条「贴图内切圆 × 系数」的算法：BOSS 贴图外圈是
        # 透明光晕，算出来会比「打得中」的半径还大——玩家离着十几像素就被撞死，
        # 正是 enemy.py 模块文档里点名的那类事故。直接由机体半径推。
        self.bodyRadius = self.radius * constants.ENEMY_BODY_RADIUS_FACTOR

        self.name = spawn.name
        self.segments = spawn.segments
        self.attacksByName = spawn.attacks
        self.maxHp = 0
        # 当前是第几段。**初始是 -1**：还没进第一段。`runPhase` 进段时 +1，
        # 于是第一段是 0——血条的格子是「index <= phaseIndex 就点亮」，
        # 从 0 起才对得上。
        self.phaseIndex = -1
        self.pending = []
        self.plans = []
        self.scriptDone = False
        self.script = spawn.script(self)

    # —— 每帧推进 ——

    def update(self) -> None:
        """推进一帧：脚本走一步、开火计划打一拍、贴图转一点。

        **一帧只 `next()` 一次脚本**，见模块文档「一帧恰好推进一步」。

        脚本排在计划之前：本帧 `fires(...)` 登记的计划，**本帧就打第一发**
        ——顺序反过来的话每种弹幕都会慢一帧才开始，而「登记了却不出弹」
        在画面上看不出来。
        """
        self.ageFrames += 1
        self.advanceAnimation()

        if not self.scriptDone:
            try:
                next(self.script)
            except StopIteration:
                # 脚本跑完就标记，之后不再 next——已耗尽的生成器每次 next 都会再抛
                # StopIteration，在普通函数里它会一路冒到 Game.update 把游戏打崩。
                self.scriptDone = True

        self.updatePlans()

    def updatePlans(self) -> None:
        for plan in self.plans:
            attack = plan.due()
            if attack is not None:
                self.pending.append(attack)

    def isFinished(self) -> bool:
        """该离场了：被打死，**或者脚本自己跑完**。

        「脚本跑完而血还没掉光」= BOSS 退场（原作里「时间到了就撤」），走的是与
        「敌机飞出场外」同一条路——**不清弹**：清弹是死亡的补偿，见
        `collision.removeAndHandleDeaths`。

        中 BOSS 用的是无限循环的开火计划，所以它只会被打死；这条规则是给
        「有始有终」的脚本准备的退场机制，不然那种脚本跑完会留下一尊不动的 BOSS。
        """
        return self.isDead() or self.scriptDone

    def dueAttacks(self) -> tuple[EnemyAttack, ...]:
        """把本帧排队的齐射交出去并清空。

        复用的就是 `Enemy` 那条「本帧该打的齐射」通道，所以 `EnemyField.fire()`
        原样可用：自机狙的角度由它按**本帧**的自机位置算，`rng` 也是它注入的。
        """
        due = tuple(self.pending)
        self.pending.clear()
        return due

    # —— 脚本助手 ——

    def fires(self, name: str) -> None:
        """登记一条开火计划。**不是生成器，不 yield**——见模块文档。"""
        if name not in self.attacksByName:
            raise KeyError(
                f"{self.name} 没有名为 {name!r} 的攻击；"
                f"关卡数据里定义的是 {sorted(self.attacksByName)}"
            )
        self.plans.append(FiringPlan(self.attacksByName[name]))

    def stopFiring(self) -> None:
        """撤掉全部开火计划。"""
        self.plans.clear()

    def fireOnce(self, name: str, volleyIndex: int = 0) -> None:
        """立刻打**一发**，不登记计划。

        `volleyIndex` 是「这是第几环」——环形弹的「第 n 环整体旋转 n × deltaAngleDeg」
        就靠它。一发一发地打（而不是用 `fires` 的计划）是为了让脚本能**逐环换角度**：
        计划里的 volleyIndex 是自增的，没法在中间改方向，而「左右交替旋转」那种
        图案正需要每环指定朝向。

        参数仍然来自关卡数据（名字查 `attacksByName`），脚本不碰子弹规格。
        """
        if name not in self.attacksByName:
            raise KeyError(
                f"{self.name} 没有名为 {name!r} 的攻击；"
                f"关卡数据里定义的是 {sorted(self.attacksByName)}"
            )
        self.pending.append(replace(self.attacksByName[name], volleyIndex=volleyIndex))

    def moveTo(self, target: Vector2, frames: int) -> Iterator[None]:
        """在 frames 帧里线性移到 target，每帧让出一帧。

        末帧**精确**落在 target 上（用 `step / frames`，不是 `(step - 1) / frames`
        那种永远差一点的写法）：脚本里写坐标就该到位，否则连着两段 `moveTo`
        会把偏差累积起来。`frames <= 0` 是空操作——不移动，也不占帧。
        """
        start = Vector2(self.position.x, self.position.y)
        for step in range(1, frames + 1):
            self.position = start + (target - start) * (step / frames)
            yield

    def wait(self, frames: int) -> Iterator[None]:
        """原地等 frames 帧。后台的开火计划照常打。"""
        for _ in range(frames):
            yield

    def runPhase(self, hp: int, script: Iterator[None]) -> Iterator[None]:
        """一段血：本段血量设为 hp，然后每帧推进 script，直到血掉光或 script 跑完。

        **进入时撤掉上一段的开火计划**——不撤的话上一段的弹幕会一直打到下一段去。

        血归零就结束这一段，判据放在推进**之前**：血一空就不再出弹了。

        子脚本写「一直打下去」的形状就行（`while True: yield` 之类），段的结束由
        玩家的输出决定——这与原作一致，符卡与通常攻击都是打到没血为止。

        子脚本**自己跑完**时，本段在**同一帧**结束：生成器耗尽不消耗帧，下一句脚本
        语句紧接着就执行（所以段与段的交界处不会多出空白帧，也不会多打一波）。
        """
        self.hp = hp
        self.maxHp = hp
        self.phaseIndex += 1
        self.stopFiring()
        while self.hp > 0:
            try:
                next(script)
            except StopIteration:
                return
            yield

    def __repr__(self) -> str:
        return (
            f"Boss(name={self.name!r}, position={self.position}, "
            f"hp={self.hp}/{self.maxHp}, scriptDone={self.scriptDone})"
        )
