# 东方 Project 同人弹幕游戏 · 设计文档

- **日期**：2026-09-14
- **状态**：已评审通过，待编写实现计划
- **目标**：用 Python + pygame 复刻东方系列的基本关卡玩法，完成一个可通关的单关流程

---

## 1. 项目定位

用 Python 和 pygame 实现的东方 Project 同人弹幕游戏。v1 的完成标准是：**一个完整关卡可从开局玩到结算**，包含道中杂鱼波、中 BOSS、BOSS 符卡、道具回收、残机与炸弹。

明确**不是**的东西：这不是东方原作的移植或逆向工程。不解析原作 `th06.dat`，不逐帧还原原版逻辑。项目借用原作美术与音效素材，重新实现一套手感接近的弹幕玩法。

明确**不做**的 v1 功能：多关卡、存档、Replay 录像回放、标题菜单以外的完整菜单系统（设置界面）、联网。

---

## 2. 素材来源与授权

`assets/` 下的全部素材（立绘、子弹贴图、背景、BGM、音效、字体）以及 `assets/levels/level_1.json` 均来自 **[NumPix/pygame-touhou](https://github.com/NumPix/pygame-touhou)**（作者 Leonid Ushakov，**MIT 协议**）。

- 该项目的代码与素材**可以合法复用**，但**必须保留版权声明**。
- 从该项目复制的代码，需在函数注释中注明出处。
- 项目根目录需保留 `LICENSE` 文件（含原作者的 MIT 声明）。

东方 Project 原作版权归上海爱丽丝幻乐团（ZUN）所有。本项目为非商业同人作品。

### 参考项目清单

| 项目 | 协议 | 用途 |
|------|------|------|
| NumPix/pygame-touhou | MIT | 素材来源；关卡数据格式基础；`Vector2`、样条曲线轨迹、弹幕模板的移植来源 |
| Patchouli-CN/touhou-engine | **无 LICENSE** | **仅参考设计思想，不复制代码**。借鉴固定步长/确定性设计、弹幕数组化的性能思路 |

---

## 3. 技术选型

| 项目 | 选择 | 理由 |
|------|------|------|
| Python | **3.14+** | 用户现有环境 |
| pygame | **pygame-ce 2.5.8+** | 官方 `pygame` 2.6.1 **无 cp314 wheel**，需本地编译；pygame-ce 有现成安装包，API 完全兼容，代码中照常 `import pygame` |
| numpy | **不引入** | 见下方说明 |
| 向量库 | 自己实现 `Vector2`（纯 Python） | 同上 |
| 测试 | pytest | |
| Lint/Format | ruff | 行宽 100 |
| 类型检查 | mypy strict | |
| 打包 | pyinstaller | |

### 3.1 为什么不使用 numpy

参考项目的 `Vector2` 内部是 `np.array([x, y])`。本项目改为纯 Python 的两个 `float`。

原因：numpy 对**小数组**的单次运算比纯 Python 慢。`np.array([x, y])` 每次都要构造数组对象，这个开销远大于它省下的两次浮点加法。弹幕引擎每帧要做几万次向量加法、归一化、旋转，numpy 在此场景是负收益。

numpy 真正有价值的场景是**批量数组运算**。若将来弹幕数量增长到需要向量化处理（把全部子弹位置存成平行数组一次性更新），再重新引入。在那之前不引入。

**直接后果**：`AttackFunctions` 中使用的 `np.rad2deg` 需替换为标准库 `math.degrees`；掉落抽样的 `np.random.choice` 替换为 `random.choices`。

---

## 4. 目录结构

```
TouhouProject/
├── assets/                          # 【已存在】素材与关卡数据
│   ├── fonts/                       #   DFPPOPCorn-W12.ttf
│   ├── levels/                      #   level_1.json（将迁移到新格式）
│   ├── music/                       #   3 首 BGM + sounds/ 下 26 个音效
│   └── sprites/                     #   backgrounds/ effects/ entities/ projectiles_and_items/
├── src/
│   └── touhou/                      # Python 包
│       ├── __init__.py
│       ├── main.py                  # 入口：python -m touhou
│       ├── constants.py             # 全局常量（分辨率、判定半径、各类帧数等）
│       ├── core/                    # ① 通用 STG 内核（不 import 任何东方概念）
│       │   ├── gameLoop.py          #   固定步长主循环
│       │   ├── vector2.py           #   二维向量（纯 Python）
│       │   ├── collider.py          #   圆形碰撞
│       │   ├── spriteSheet.py       #   动画表 + 按角度预旋转缓存
│       │   ├── resourceCache.py     #   贴图/音效去重加载
│       │   └── paths.py             #   资源路径解析（开发/打包两种环境）
│       ├── game/                    # ② 东方玩法层
│       │   ├── world.py             #   一局游戏的全部状态（玩家、敌人、子弹、道具、RNG）
│       │   ├── entities/
│       │   │   ├── player.py
│       │   │   ├── enemy.py
│       │   │   ├── boss.py
│       │   │   ├── bullet.py
│       │   │   ├── item.py
│       │   │   └── effect.py
│       │   ├── systems/
│       │   │   ├── bulletPool.py    #   子弹对象池
│       │   │   ├── collision.py     #   碰撞检测与粗筛
│       │   │   ├── graze.py         #   擦弹判定
│       │   │   ├── bomb.py          #   炸弹与死亡炸弹
│       │   │   ├── itemDrop.py      #   掉落抽样
│       │   │   └── spawner.py       #   按帧刷怪
│       │   ├── patterns/            #   弹幕模板
│       │   │   ├── registry.py      #   @registerPattern 注册表
│       │   │   └── ...              #   ring / random / cone / wideCone / wideRing /
│       │   │                        #   longRandom / aimed / spiral
│       │   └── stage/
│       │       ├── levelSchema.py   #   关卡 dataclass 模型
│       │       ├── levelLoader.py   #   解析 + 校验
│       │       ├── stageRunner.py   #   按帧推进关卡
│       │       └── stage1.py        #   第 1 关 BOSS 脚本
│       ├── ui/                      # ③ HUD、标题菜单、结算
│       └── audio/                   # ④ BGM / SE 管理
├── tests/                           # pytest（与 src/ 平级）
├── tools/
│   └── migrateLevel.py              # 旧关卡格式 → 新格式转换脚本
├── dist/                            # 打包
│   ├── build.py                     #   pyinstaller 调用脚本（带参数校验 + 冒烟测试）
│   └── touhou.spec                  #   打包配置
├── docs/superpowers/specs/          # 设计文档（本文件）
├── pyproject.toml
├── requirements.txt
├── LICENSE                          # 含 NumPix 原作者 MIT 声明
├── README.md
└── .gitignore
```

### 4.1 `core/` 与 `game/` 的分层规则

**这是本项目最重要的结构约束。**

`core/` 放"任何弹幕射击游戏都会需要"的东西：向量、碰撞、动画表、主循环、资源加载。它**不得 import 任何东方相关概念**——`core/` 的代码里不应出现"自机""残机""符卡"等词。

`game/` 才知道自己在做东方：玩家、敌机、BOSS、子弹、道具、擦弹、炸弹、关卡加载与 BOSS 脚本。

**收益**：① `core/` 的数学与碰撞可以完全不启动 pygame 窗口就被测试，这是 `tests/` 能快速运行的前提；② 修改弹幕运动学算法时，改动范围清晰，不会波及 UI。

**验证方式**：`tests/` 中应有一个测试断言 `core/` 下的模块不 import `touhou.game`。

---

## 5. 核心运行时

### 5.1 固定步长主循环

**逻辑固定以 `STEP_SECONDS = 1/60` 秒推进，与真实帧率解耦。**

不使用参考项目的变步长设计（`position += velocity * deltaTime`）。原因：变步长下不同机器上弹幕速度不一致；帧率抖动时高速子弹可能单帧跨过判定点造成**穿透**；录像回放与逐帧调试无法进行。

采用累积器模式：

```python
accumulator += realDeltaSeconds
steps = 0
while accumulator >= STEP_SECONDS and steps < MAX_STEPS_PER_FRAME:
    world.update()
    accumulator -= STEP_SECONDS
    steps += 1
render()
```

`MAX_STEPS_PER_FRAME = 5` 是防止卡顿后雪崩的护栏：若某帧真实耗时 0.5 秒，不设上限会连跑 30 步导致渲染更慢、下一帧更卡，形成死循环。宁可让游戏"变慢"也不卡死。

**游戏逻辑内部不存在 `deltaTime` 概念**——每步就是固定的一帧。

### 5.2 确定性

所有随机数走**一个带种子的 `random.Random` 实例**，通过 `World.random` 访问，禁止使用全局 `random`。

```python
class World:
    def __init__(self, seed: int):
        self.random = random.Random(seed)
```

配合固定步长与逐帧输入抽象，游戏成为纯函数：`(种子, 输入序列) → 确定的结果`。v1 不实现录像，但埋下这条线成本极低，将来可白拿。

参考项目中 `AttackFunctions.random()` 使用全局 `random.randint`，移植时改为从 `world.random` 取。

### 5.3 输入抽象

移动与射击需要"这一帧是否按住"→ 轮询键盘状态。暂停与菜单选择需要"刚刚按下"→ 使用事件。两者不混用。

所有输入收敛为不可变对象：

```python
@dataclass(frozen=True, slots=True)
class FrameInput:
    left: bool = False
    right: bool = False
    up: bool = False
    down: bool = False
    shoot: bool = False    # Z
    bomb: bool = False     # X
    slow: bool = False     # Shift
```

键盘轮询把真实按键翻译成 `FrameInput`，游戏逻辑只认 `FrameInput`。人工输入与将来的 AI/回放走同一条路径，逻辑层无需区分。

### 5.4 渲染管线

**逻辑分辨率固定 640×480。游戏区 384×448，位于 (32, 16)。** 右侧 224px 为 HUD 区。

```
(0,0)                                    (640,0)
  ┌────────────────────────────────────────────┐
  │  ┌──────────────────────────┐              │
  │  │                          │    HUD       │
  │  │    游戏区 384×448         │    224 宽    │
  │  │    at (32, 16)           │              │
  │  │                          │   HiScore    │
  │  │                          │   Score      │
  │  │                          │   残机       │
  │  │                          │   炸弹       │
  │  │                          │   火力       │
  │  └──────────────────────────┘   擦弹       │
  └────────────────────────────────────────────┘
(0,480)                                (640,480)
```

每帧渲染到一张 640×480 的离屏 Surface，最后 **一次性整数倍缩放**到窗口：

| 倍率 | 窗口尺寸 | 用途 |
|------|---------|------|
| ×1 | 640×480 | 小窗口、调试 |
| ×2 | 1280×960 | 默认 |
| ×3 | 1920×1440 | 高分屏 |

使用 `pygame.transform.scale`（最近邻插值）。启动时自动选择能塞进显示器的最大整数倍，可在设置中手动切换。全屏为缩放后居中加黑边。

**必须整数倍**：非整数缩放会让像素变成大小不一的矩形，画面发糊。宁可留黑边。

### 5.5 性能策略

**结论：v1 使用纯 Python 对象，不做空间划分，但必须做贴图旋转缓存。**

依据（按 EoSD 一面强度，同屏峰值约 400~600 发子弹估算）：

- 弹幕 vs 自机判定点：每帧 N 次距离平方比较，600 × 60fps = 3.6 万次/秒，每次约 0.5μs → 约 1.8% 单核占用。**非瓶颈。**
- 子弹渲染：每帧 600 次 blit，带 alpha 的 16×16 blit 约 1~2μs → 每秒 3.6 万次，约 4~7% 占用。**非瓶颈。**
- **参考项目在 `Bullet.__init__` 中对 sprite sheet 的每一帧调用 `pygame.transform.rotate`**，子弹生成高峰期每秒数百发 × 每发数帧，单项即可耗尽预算。**这才是瓶颈。**

按优先级：

1. **按角度预旋转并缓存贴图。** 角度只有 360 种整数度，缓存 `(贴图, 角度)` 结果。**按需生成**——只有实际用到的角度才创建，避免一次性生成 360 张。
2. **子弹对象池 + `__slots__`。** 每帧创建数百对象带来 GC 压力，表现为周期性掉帧。改为复用固定批次对象、以 `alive` 标记生死，每帧原地压缩。`__slots__` 省去每实例的属性字典。
3. **碰撞分两档。** 自机判定点碰撞直接全量比较（见上方测算）。己方子弹 vs 敌机的碰撞按 y 坐标分桶粗筛（敌机通常只有几个）。

**v1 明确不做**：空间网格、numpy 向量化、多进程。

---

## 6. 玩法系统

### 6.1 常量起点值

以下集中定义在 `src/touhou/constants.py`。

**速度单位统一为「像素/帧」。** 参考项目使用「像素/秒」（因为它跑变步长），移植公式：

```
pxPerFrame = pxPerSecond / 60
```

| 值 | 来源 | 说明 |
|----|------|------|
| 自机速度 370 px/s → **6.17 px/帧** | 参考项目 `characters_data` | 低速模式为其一半，约 3.08 px/帧 |
| 射击间隔 **6 帧** | 参考项目 | 原为 `attack_timer >= 16` 且每帧 `+= 2.5`，实际间隔 16/2.5 = 6.4 帧 |
| 自机子弹速度 900 px/s → **15 px/帧** | 参考项目 | 伤害 1，判定半径 5 |
| 道具追尾速度 500 px/s → **8.33 px/帧** | 参考项目 | |

**先沿用参考项目的数值**——这套素材与关卡数据是在这些速度下调出来的平衡，从零另设一套没有依据。手感不满意时再调。

```python
LOGICAL_WIDTH = 640
LOGICAL_HEIGHT = 480
PLAYFIELD_X, PLAYFIELD_Y = 32, 16
PLAYFIELD_WIDTH, PLAYFIELD_HEIGHT = 384, 448

FPS = 60
MAX_STEPS_PER_FRAME = 5

# —— 自机 ——
PLAYER_HITBOX_RADIUS = 2          # 判定点（原作量级，参考项目未实现）
PLAYER_GRAZE_RADIUS = 18          # 擦弹圈，远大于判定点
PLAYER_SPEED_NORMAL = 370 / 60    # ≈ 6.17 px/帧
PLAYER_SPEED_SLOW = 370 / 120     # ≈ 3.08 px/帧，低速模式
PLAYER_SHOT_RADIUS = 5            # 自机子弹判定半径
SHOOT_INTERVAL_FRAMES = 6
RESPAWN_INVINCIBILITY_FRAMES = 180
DEATHBOMB_WINDOW_FRAMES = 8       # 原作约 8 帧

# —— 资源 ——
START_LIVES = 3
START_BOMBS = 3
POWER_MAX = 4.00
POWER_START = 2.40                # 沿用参考项目起始值
POWER_ITEM_LARGE = 0.02           # 沿用参考项目
POWER_ITEM_SMALL = 0.005          # 沿用参考项目
POC_LINE_OFFSET_Y = 112           # PoC 回收线距游戏区顶部
SCORE_EXTEND_STEP = 10_000_000

# —— 道具 ——
ITEM_RADIUS_LARGE = 12            # 能量(大)/满火力/1UP
ITEM_RADIUS_SMALL = 10            # 能量(小)/蓝点/星星
ITEM_FALL_GRAVITY = 10 / 60       # 下落加速度
ITEM_HOMING_DELAY_FRAMES = 90     # 追尾启动延迟（参考项目 t > 1.5 秒）
POINT_ITEM_BASE_SCORE = 30_000
POINT_ITEM_HEIGHT_BONUS = 70_000
```

### 6.2 自机（Player）

| 项目 | 行为 |
|------|------|
| 判定点 | 半径 2px。平时不可见，**按住 Shift 低速移动时显示** |
| 移动 | 6.17 px/帧，低速模式 3.08 px/帧。限制在游戏区内 |
| 射击 | 每 6 帧发射一次，弹幕形态由 `power` 决定 |
| 斜向立绘 | 左/右移动时使用倾斜版本（旋转约 7°），参考项目已实现 |
| 复活 | 残机 -1 后从游戏区底部升起，期间 180 帧无敌 |

速度、射速、弹幕形态放进**角色配置表**，不硬编码在逻辑里。

**立绘分帧**：`marisa_forward.png` 尺寸 200×50，参考项目按 `crop((25, 50))` 切分，即 **8 帧、每帧 25×50**。`marisa_bullet.png` 为 32×32 单帧。

### 6.3 火力（Power）

`power` 范围 `0.00 ~ 4.00`，决定自机弹幕条数与形状。拾取道具时累加，超过上限截断到 `4.00`。

**参考项目的火力实现存在缺陷，本项目重新设计。** 原实现的映射是：

```python
power_levels = [0, 1, 2, 3]
current_power = power_levels[int((len(power_levels) - 1) * power * 20 / 100)]
```

即 `index = int(0.6 * power)`。`power = 4.00` 时 `int(2.4) = 2`，**索引 3 永远取不到**——`power_levels` 数组的最后一项是死代码。而且调用方 `Player.shoot` 又先做了一次 `int(self.power)`，等于对火力做了两轮有损取整，中间档位大量重叠。

本项目改为**显式的档位表**，一眼能看出每个火力档对应几条弹道：

```python
# 每档：(所需最低 power, 弹道数)
MARISA_POWER_TIERS = [
    (0.00, 1),
    (1.00, 2),
    (2.00, 3),
    (3.00, 4),
    (4.00, 6),
]
```

查表得到弹道数后均分角度发射。档位表放在角色配置里，不同角色可以有不同的成长曲线。

### 6.4 擦弹（Graze）

**参考项目完全没有此系统。**

自机拥有两个同心圆：内圈 `PLAYER_HITBOX_RADIUS`（碰到即死），外圈 `PLAYER_GRAZE_RADIUS`（进入即计擦弹）。

子弹进入外圈且未命中内圈时：`graze += 1`，加少量分数，播放 `07-graze.wav`。

**每颗子弹只能擦一次**——`Bullet` 对象需要 `grazed` 标记位。

此机制不可省略：它把玩家往弹幕内部引导，而非向外躲避，是东方手感区别于普通弹幕游戏的核心。

### 6.5 炸弹与死亡炸弹（Bomb / Deathbomb）

**参考项目两者都没有。**

**炸弹（X 键）**：消耗一个炸弹库存，效果包含两段，缺一不可——
- 给予玩家一段无敌时间
- 清除场上敌弹（可转化为分数道具）

只有无敌没有清弹，玩家仍被弹幕困住；只有清弹没有无敌，按了等于白按。

**死亡炸弹（Deathbomb）**：被子弹命中后**不立即扣残机**，先进入一个 8 帧窗口：

```
命中 → 进入 dying 状态（8 帧倒计时）
     ├─ 窗口内按下 X → 转为一次炸弹，不死
     └─ 窗口超时     → 死亡，残机 -1
```

实现上，命中时进入 `dying` 状态而非直接 `takeDamage()`；状态机在窗口结束或炸弹按下时收尾。这是东方最有辨识度的机制之一。

### 6.6 道具系统

类型沿用 `level_1.json` 已定义的：`points`（蓝点）、`power_small`、`power_large`、`full_power`、`1up`。

| 道具 | 判定半径 | 效果 |
|------|---------|------|
| `power_large` | 12 | `power += 0.02`，`score += 10` |
| `power_small` | 10 | `power += 0.005`，`score += 10` |
| `full_power` | 12 | `power` 直接补满至 4.00 |
| `1up` | 12 | 残机 +1，播放 `06-extend.wav` |
| `points`（蓝点） | 10 | 分数**按高度计算**，见下方 |
| `star`（弹幕清除产物） | 10 | `score += 200`，必定追尾 |

- **掉落**：敌人死亡时按 `drop.list` + `drop.probabilities` 加权抽样。使用标准库 `random.choices`（替代参考项目的 `np.random.choice`）。
- **下落**：参考项目用一个巧妙写法——初速为 0 的自由落体。`t` 从 `-10` 起算，位置偏移为 `t² - 100`，因此 `t = -10` 时偏移恰好为 0，此后加速下落。本项目沿用该形式，但改用帧计数。
- **追尾**：`t` 超过阈值（约 90 帧）后以 8.33 px/帧 飞向自机。星星道具跳过延迟，立即追尾。

#### 蓝点的分数与 PoC 回收线

**蓝点的分数随拾取高度线性变化**：

```
score += 30_000 + 70_000 × (游戏区底边 - 拾取点 y) / 游戏区高度
```

在游戏区顶部拾取是 `100_000` 分，在底部拾取只有 `30_000` 分——**相差三倍多**。

**这正是 PoC 回收线的价值所在。** 已知参考项目没有实现 PoC：

- **PoC 回收线（Point of Collection）**：自机飞到游戏区顶部以下 `POC_LINE_OFFSET_Y` 以上的区域时，**全屏道具自动飞向自机**。

两条机制合起来才构成东方的刷分循环：玩家为了高分必须主动飞到屏幕顶部的高危区域，而 PoC 让这个冒险行为能一次性收走全屏道具作为回报。缺了 PoC，上压就只是纯粹的风险没有收益，玩家不会去；缺了高度计分，PoC 也就没有意义。**两者必须一起实现。**

#### 判定半径的说明

道具的收集判定使用**道具自身的半径**（10~12px）与自机碰撞，而非自机的 2px 判定点。因此实际拾取距离约为 13~15px，比"中弹距离"大得多——这是合理的：躲弹要精确，捡道具要宽松。

**不要**把道具收集距离写成自机判定半径，否则会出现"明明碰到了却捡不到"的诡异手感。

### 6.7 BOSS 系统

**参考项目完全没有任何 BOSS——这是本项目最大的新增模块。**

BOSS 需要：

- **血条分段（Phase）**：多段血量，打完一段进入下一段，段数显示于屏幕顶部
- **符卡（Spell Card）**：
  - 宣言动画（屏幕闪白、符卡名从右向左滚入、右下角显示剩余时间）
  - 限时（30~60 秒），超时判定为取得失败
  - 符卡奖励分：开局给分，被击中或超时则丢失，显示 `BONUS FAILED`
- **通常攻击**：符卡之间的普通弹幕段落，同样有血条
- **移动脚本**：BOSS 沿预设轨迹在场移动
- **中 BOSS**：道中出现的简化版，通常无符卡，血条短

**BOSS 用 Python 代码编写，采用生成器协程风格**：

```python
def rumiaBossScript(self, world):
    yield from self.moveTo(320, 120, frames=60)

    # 通常攻击一：自机狙扇形
    yield from self.runPhase(
        hp=800,
        script=self.normalAttack(spreadCount=5, spreadDeg=30,
                                 speed=2.5, intervalFrames=40),
    )

    # 符卡一
    yield from self.spellCard(
        name="闇符「ダークサイドオブザムーン」",
        hp=1000,
        timeoutFrames=45 * 60,
        script=self.pattern(...),
    )
```

**选择生成器的理由**：弹幕本质是"随时间展开的序列"，生成器天然表达这种顺序语义，读起来即"先移动，然后打一段通常攻击，然后宣言符卡"。相比 JSON 嵌套数组，可断点调试、可写单元测试、可组合复用（`normalAttack` 是可组合函数）。

**BOSS 立绘**：使用**程序化绘制的占位图形**（带光晕的多边形/圆 + 旋转动画，不同 BOSS 用不同颜色）。这样 BOSS 走与其他实体完全一致的 `SpriteSheet` 接口，将来替换为真实美术时逻辑代码零改动。

### 6.8 结算与生命

死亡 → 残机 -1 → 复活（180 帧无敌）→ 残机为 0 → Game Over。分数每达到 `SCORE_EXTEND_STEP` 时 Extend（加残机，播放 `06-extend.wav`）。

清关后进入结算画面：分数、擦弹数、最大连击、符卡回收数。参考项目的 `ScoreboardScene` 可作参考。

---

## 7. 关卡数据格式

### 7.1 现有格式的问题

现有 `level_1.json` 的攻击定义使用**位置参数数组**：

```json
"attacks": [["long_random", 3, 30, [[...sprite...], 16, 16, 4, [0,0]], 150, 1, 0.06, 0, true]]
```

问题：读懂需翻阅 `AttackFunctions.long_random` 的签名；增删或调序参数会**静默错位**而无任何报错；`150` 的单位是轨迹参数 `t` 而非帧（因触发条件为 `self.t >= attack_data[i][1]`），混用单位；`"size"` 与贴图实际尺寸重复；所有敌人平铺一个数组，看不出波次；关卡级元信息缺失；无 BOSS 挂载点。

### 7.2 新格式

**分层 + 具名参数 + 统一以帧为单位。**

```json
{
  "meta": {
    "name": "Stage 1",
    "background": ["assets", "sprites", "backgrounds", "background.png"],
    "bgm": ["assets", "music", "01.-A-Dream-that-is-more-Scarlet-than-Red_1.wav"],
    "durationFrames": 3900
  },
  "waves": [
    {
      "atFrame": 60,
      "spawns": [
        {
          "startPosition": [50, 0],
          "trajectory": [[50, 50], [50, 50], [50, 50], [-50, 150]],
          "durationFrames": 180,
          "sprite": {
            "path": ["assets", "sprites", "entities", "fairy_0.png"],
            "frameSize": [24, 19],
            "frameCount": 6
          },
          "hitboxRadius": 15,
          "hp": 10,
          "attacks": [
            {
              "pattern": "longRandom",
              "startFrame": 150,
              "params": {
                "bullet": {
                  "sprite": ["assets", "sprites", "projectiles_and_items", "kunai_0.png"],
                  "frameSize": [16, 16],
                  "frameCount": 4,
                  "hitboxRadius": 4
                },
                "bulletCount": 3,
                "burstCount": 30,
                "speed": 1,
                "intervalFrames": 4,
                "angularSpeed": 0,
                "randomCenter": true
              }
            }
          ],
          "drop": {
            "list": ["points", "power_small", "nothing"],
            "probabilities": [40, 30, 30]
          },
          "clearBulletsOnDeath": false
        }
      ]
    }
  ],
  "bosses": {
    "midboss": { "atFrame": 1800, "script": "touhou.game.stage.stage1.midbossScript" },
    "boss":    { "atFrame": 3000, "script": "touhou.game.stage.stage1.bossScript" }
  }
}
```

关键改动：

- **`pattern` + `params` 具名参数**：自解释；增删参数不会错位；多余参数被校验捕获
- **统一帧为单位**：`startFrame`、`intervalFrames`、`durationFrames`
- **`waves` 分组**：关卡读起来即"第 60 帧刷第一波"
- **`bosses` 挂载点**：值为 Python 脚本路径，加载器动态 import。JSON 管"何时出 BOSS"，代码管"BOSS 怎么打"
- **贴图信息自洽**：`frameSize` + `frameCount` 从单一来源推出

#### `trajectory` 的语义（必须明确）

**`trajectory` 是均匀三次 B 样条（uniform cubic B-spline）的控制点，不是路径上的采样点。**

参考项目的 `BasisSpline` 实现的是标准均匀三次 B 样条，特征矩阵为：

```
[ 1/6,  2/3,  1/6,   0 ]
[ -1/2,  0,    1/2,   0 ]
[ 1/2, -1,    1/2,   0 ]
[ -1/6, 1/2, -1/2, 1/6 ]
```

参数 `u` 定义在 `[0, len(points) - 1]` 上：`n = int(u)` 选取曲线段，`t = u mod 1` 是段内参数。端点通过镜像外插（`2*p[0] - p[1]`）补齐，使曲线恰好从首尾控制点附近开始与结束。

**坐标相对于游戏区左上角**，而非窗口或屏幕。例：`[50, 0]` 是距游戏区左边 50px、顶部 0px；`[-50, 150]` 是飞到游戏区左外侧 50px——**这是合法的，敌人就是该飞出屏幕**。

**用 `durationFrames` 取代 `speed`。** 参考项目的 `speed` 单位是"样条参数 u 每秒前进多少"（`t += speed * deltaTime`，配合 `u ∈ [0, 3]` 才是 3 秒），这个单位既难推理又和"帧"混用。改为直接声明"用多少帧走完这条轨迹"：

```
每帧 u 增量 = (len(trajectory) - 1) / durationFrames
```

`durationFrames: 180` 就是 3 秒飞完全程。语义直接，且天然与固定步长对齐。

**B 样条本身仍然保留**——它让敌人的移动轨迹天然平滑，转向不会有折角。参考项目的这一设计是好的，只是表达方式需要改。

### 7.3 弹幕模板注册表

JSON 中的 `"pattern": "longRandom"` 通过注册表解析：

```python
# src/touhou/game/patterns/registry.py
PATTERN_REGISTRY: dict[str, Callable] = {}

def registerPattern(name: str):
    def decorator(func):
        PATTERN_REGISTRY[name] = func
        return func
    return decorator
```

新增模板无需修改加载器——写好函数、挂上装饰器，JSON 中立即可用。

从参考项目移植的模板：`ring`、`random`、`cone`、`wideCone`、`wideRing`、`longRandom`。
新增：`aimed`（自机狙）、`spiral`（螺旋）。

所有模板生成的弹幕与 BOSS 脚本生成的弹幕走**同一接口**，引擎不区分来源。

### 7.4 旧数据迁移

编写 `tools/migrateLevel.py` 将旧 `level_1.json` 转为新格式，执行一次。旧文件已存在于 git 历史（`init commit`），不会丢失。转换脚本保留以备将来处理其他旧关卡。

### 7.5 校验策略

**不使用 JSON Schema**，改用 dataclass 定义关卡模型 + 显式校验函数。

理由在于错误信息质量：JSON Schema 报"不符合 schema 的分支 xxx"，手写校验可报 `waves[2].spawns[0].attacks[1].params.speed 应为数字，实际为字符串 "1"`。对 84KB 的手写关卡文件，这是"能修"与"不知从何修"的差别。

校验需覆盖：字段存在性、类型、数值范围、`pattern` 名存在于注册表、`drop.list` 与 `probabilities` 长度一致且概率和为 100、精灵路径文件存在、`frameSize` 与 `frameCount` 和图片实际尺寸自洽。

---

## 8. 工程规范

### 8.1 命名

| 类别 | 风格 | 示例 |
|------|------|------|
| 类名 | `PascalCase` | `SpriteSheet` |
| 函数/方法/变量/参数 | `lowerCamelCase` | `getRotated`、`angleDeg` |
| 模块级常量 | `UPPER_SNAKE_CASE` | `FPS` |
| 文件名 | 与其中主要类名一致 | `spriteSheet.py` |

与 PEP 8 的函数命名建议不一致，因此需在 ruff 中关闭 `N802`、`N803`、`N815`。

```python
class SpriteSheet:
    def __init__(self, surface, frameWidth):
        self.frameWidth = frameWidth
        self.rotatedCache: dict[int, list] = {}

    def getRotated(self, angleDeg: int):
        ...

FPS = 60
```

### 8.2 代码写给人读

代码与文档面向**人**，而非机器。

- 注释解释**为什么**，不复述代码在做什么
- 命名自解释，宁可长也不用 `d`、`tmp`、`data2`
- 函数长到需要滚动阅读时，考虑拆分

这不是审美偏好：弹幕游戏代码包含大量数学，半年后回看时唯一能依靠的就是命名与注释。

### 8.3 不重复造轮子

实现功能前先寻找现成方案。但**借鉴不等于抄袭**：注意对方开源协议。无 LICENSE 的项目意味着"保留所有权利"，可读其设计思路，不得复制代码。

### 8.4 配置文件

`pyproject.toml` 承载包元数据与全部工具配置：

```toml
[project]
name = "touhou"
requires-python = ">=3.14"
dependencies = ["pygame-ce>=2.5.8"]

[tool.ruff]
line-length = 100
lint.ignore = ["N802", "N803", "N815"]

[tool.mypy]
strict = true
```

mypy strict 的作用：弹幕引擎中 `Vector2`、`float`、`int` 混传频繁，"角度传成弧度"这类 bug 运行期表现为弹幕朝奇怪方向飞而非报错，类型标注能在编写期拦截。若过于繁琐可降级为非 strict。

### 8.5 测试策略

分三层，**重点是前两层**（均无需启动 pygame 窗口）：

1. **纯逻辑层（`core/`）**：向量运算、碰撞检测、样条插值。纯数学，测试价值最高。
   - 例：两圆相切时判定为碰撞；角度归一化到 `[0, 360)`
2. **玩法逻辑层（`game/`）**：擦弹计数（每颗子弹只擦一次）、死亡炸弹窗口边界（第 8 帧按键存活、第 9 帧死亡）、道具掉落概率分布、power 上限截断、关卡文件校验、`core/` 不依赖 `game/` 的分层断言。
3. **引擎层**：以 `SDL_VIDEODRIVER=dummy`、`SDL_AUDIODRIVER=dummy` 无头运行若干帧，验证不崩溃与帧数正确。不做像素级对比。

### 8.6 打包

`dist/build.py` 为带参数校验的脚本，而非裸 pyinstaller 调用：

```bash
python dist/build.py              # 单目录（启动快）
python dist/build.py --onefile    # 单文件（分发方便，启动慢）
```

- 必须显式将 `assets/` 纳入打包（pyinstaller 不自动收集非 `.py` 数据文件），遗漏会导致启动即崩，因此打包后需立即执行冒烟测试。
- **资源路径统一解析**：打包后 `__file__` 指向临时解压目录，与开发环境不同。

```python
# src/touhou/core/paths.py
def assetPath(*parts: str) -> Path:
    """开发时从项目根目录查找，打包后从 sys._MEIPASS 查找"""
```

### 8.7 Git

已关联 `origin`（`github.com/quarkes1/TouhouProject_pygame.git`），默认分支 `main`。

每个功能开独立分支，完成后合回 `main`。避免"弹幕系统重构到一半"的状态进入主干。

### 8.8 .gitignore

```
__pycache__/  *.pyc
.mypy_cache/  .ruff_cache/  .pytest_cache/
.venv/  venv/
build/
dist/*.exe  dist/*.spec
*.log
```

注意 `dist/` 中**保留** `build.py` 与 `touhou.spec`，仅忽略产物。

---

## 9. 待办事项

以下事项已在设计中确定，但需要在实际开发时落实：

1. **迁移 `level_1.json` 到新格式**——编写并运行 `tools/migrateLevel.py`。`speed: 1` 需按下式换算为 `durationFrames`：

   ```
   durationFrames = (len(trajectory) - 1) / speed × 60
   ```

   对 `speed: 1` 且 4 个控制点的敌人，即 `3 / 1 × 60 = 180` 帧。

2. **添加 `LICENSE` 文件**——包含 NumPix 原作者的 MIT 声明与本项目声明
3. **复核旧数据的合理性**，迁移时逐项确认：
   - `collider.radius: 15` 配合 24×19 的贴图——判定半径比贴图还大，可疑
   - `"time": 7` 字段——参考项目代码中未见使用，可能是废弃字段，需确认后决定保留或丢弃
   - `"length": 65`（关卡秒数）对应新格式的 `meta.durationFrames`，应为 `65 × 60 = 3900`
4. **`POC_LINE_OFFSET_Y`、`PLAYER_SPEED_*`、`SHOOT_INTERVAL_FRAMES` 等起点值需要实测调整**
5. **确认 `spiky_ball.png`（128×32，4 帧 32×32）的用途**——参考项目中未见明显使用，可能是未完成的素材
6. **参考项目的火力档位映射存在缺陷**（索引 3 永远取不到，且被两轮有损取整），已在本设计中重新设计，实现时不要照搬原代码

---

## 10. 实现顺序建议

以下顺序保证每一步都有可运行、可验证的产物：

1. **骨架**：`pyproject.toml`、目录结构、`LICENSE`、`.gitignore`、`constants.py`、`core/paths.py`
2. **`core/` 纯逻辑 + 测试**：`vector2`、`collider`、`spriteSheet`（含旋转缓存）、`gameLoop`。此阶段全部可单测，无需 pygame 窗口
3. **最小可跑画面**：`main.py` 打开 640×480 窗口、整数倍缩放、渲染一张背景、显示一个可移动的自机
4. **弹幕系统**：`bulletPool`、`patterns/registry`、移植 8 个模板
5. **敌机与关卡加载**：`enemy`、`levelLoader`、`levelSchema`、`spawner`、迁移 `level_1.json`
6. **对抗与手感**：`graze`、`bomb`/死亡炸弹、`itemDrop`、`item`、PoC 回收线
7. **BOSS**：`boss`、符卡宣言动画、血条分段、`stage1.py` 脚本
8. **HUD 与结算**：`ui/`、生命与残机、Extend、结算画面
9. **打包**：`dist/build.py`、`touhou.spec`、冒烟测试
