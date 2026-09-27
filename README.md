# TouhouProject

用 Python 和 pygame 做的东方 Project 同人弹幕游戏。目标是复刻东方系列的基本关卡玩法：道中杂鱼波、中 BOSS、BOSS 符卡、道具回收、残机与炸弹，一整套从开局到结算的完整流程。

需要说清楚的是，这个项目**不是**东方原作的移植或逆向工程。我们不去解包原作的 `th06.dat`，也不打算逐帧还原原版逻辑。它是一份原创代码，借用原作的美术与音效素材，重新实现一套手感接近的弹幕玩法。如果你要找的是"能跑原版数据"的实现，那么 `Patchouli-CN/touhou-engine` 才是你要的东西。

## 素材来源与致谢

`assets/` 目录下的全部素材——立绘、子弹贴图、背景、BGM、音效、字体，以及 `assets/levels/level_1.json` 这份关卡数据——都来自 [NumPix/pygame-touhou](https://github.com/NumPix/pygame-touhou)，作者 Leonid Ushakov，以 MIT 协议发布。

这意味着我们在法律上可以复用它的代码和素材，但**必须保留版权声明**。如果你从它的代码里抄了某个函数，请在那个函数的注释里写明出处，并把原作者的名字保留在 `LICENSE` 和这里。

东方 Project 原作的一切版权归上海爱丽丝幻乐团（ZUN）所有。这是一个非商业的同人作品。

## 运行

在项目根目录下执行一条命令就够了：

```bash
python run.py
```

不用装包，不用建虚拟环境，不用配 `PYTHONPATH`。`run.py` 会把自己所在目录的 `src/` 挂进 `sys.path` 再启动游戏，**所有路径都由脚本自身的位置推出来，没有一处写死的绝对路径**，所以整个目录拷到哪台机器、从哪个目录调用它都一样（`tests/testRun.py` 里有测试守着这条）。

它只要求三件事：**Python 3.13 或更高**、装了 `pygame-ce`、目录里有 `src/` 和 `assets/`。缺哪一样它都会直接说该补什么，而不是丢一个 `ModuleNotFoundError` 让你猜：

```bash
python -m pip install -r requirements.txt
```

机器上装了多个 Python 时，命令里写清楚用哪一个，比如 Windows 上 `py -3.13 run.py`。

> 为什么不直接写 `python -m touhou`？那条命令要求 `touhou` 这个包能被 import，而源码树里默认不成立——包在 `src/` 下。`pip install -e .` 能解决，但要先有 pip、先建环境，而且换台机器得再来一遍；`PYTHONPATH=src python -m touhou` 只在 POSIX 上成立，Windows 的 cmd 与 PowerShell 各是另一种写法，**没有一条三平台通用的**。顺带一提，非 editable 的 `pip install .` 是**装得上但跑不起来**的：包装进 site-packages 之后，`core/paths.py` 那套「往上数三级找项目根」的算法会指向 site-packages 的父目录，而 `assets/` 既不在那儿也没被打进 wheel。

## 环境要求（开发）

想跑测试、`ruff`、`mypy` 的话才需要这一步；只是玩游戏的话上面那条命令就够。

需要 **Python 3.13 或更高版本**（`pyproject.toml` 的 `requires-python` 与 `run.py` 的 `MINIMUM_PYTHON` 两处一致，有测试比对）。

项目跑在一个专用的 conda 环境里，这样和机器上其他 Python 安装互不干扰：

```bash
conda create -n touhou python=3.13
conda activate touhou
pip install -e ".[dev]"
```

**不要写死环境路径。** 环境装在哪由 conda 自己的配置决定，每台机器都可能不同——
要拿它的路径就用 `conda env list` 查，而不是照抄某份文档里的字符串（那种路径通常只
在写它的那台机器上成立）。三种调用方式任选：

```bash
conda activate touhou                     # 之后 python / pytest / ruff 都能直接用
conda run -n touhou python run.py         # 不激活也能跑，且不需要 conda init
conda env list                            # 想知道解释器在哪，看这个
```

第二种最省事：它绕开了 `conda init` 那一步，命令里也写清了用哪个环境，
不会落到别的解释器上。（已实测：`conda run -n touhou python -m pytest -q` 跑通全部测试。

这里 `python run.py` 与 `python -m touhou` 是等价的——`pip install -e .` 之后包
已经可 import，`run.py` 挂的那条路径只是多余的一层。日常开发用哪个都行；对外
分发时只用 `run.py`，因为它不依赖那个安装步骤。）

之所以不直接用 base 环境：它里面通常已经有上千个由 conda 管理的包，往里面混装 pip 包是 conda 环境损坏的常见原因。独立环境更干净。

**调用解释器时请写清楚是哪一个。** 一台机器上往往装着好几个 Python，PATH 的先后决定了 `python` 这个名字最终指向谁——很容易落到某个没装依赖的解释器上，然后收到一个莫名其妙的 `ModuleNotFoundError`。用上面任一种方式都行，就是别裸敲 `python`。

关于 **pygame-ce**：它是官方 `pygame` 的社区分支，API 完全兼容——你在代码里照样写 `import pygame`。我们选它是因为它维护更活跃、发布节奏更快、而且是官方的超集。需要说明的是这**不是硬性要求**：官方 `pygame` 在 Python 3.13 上同样有现成的安装包，想换回去把依赖名改掉即可。

```bash
pip install pygame-ce
```

除此之外只依赖标准库。**我们没有引入 numpy**，原因见下面「为什么不用 numpy」一节。


### 三个常见报错

**`CondaError: Run 'conda init' before 'conda activate'`**
conda 还没对当前终端做过初始化。两条路：跑一次 `conda init cmd.exe`（或把 `cmd.exe` 换成你用的 shell）**然后重开终端**；或者不初始化，改用 `conda run -n touhou python ...`——它一样能找到环境，还省掉改终端配置这一步。

**`No module named touhou`**
用 `python -m touhou` 时会见到。说明 `python` 这个名字指向了别的解释器，或者包还没装（`python -m touhou` 要求先 `pip install -e .`）。一台机器上往往装着好几个 Python，PATH 的先后决定 `python` 指向谁，很可能落到一个没装本项目依赖的上面，`where python` 能看出实际用的是哪一个。**改用 `python run.py` 就不会有这个问题**——它自己挂 `src/`，不依赖任何安装。

**`CondaToSNonInteractiveError: Terms of Service have not been accepted`**
`conda create` / `conda install` 在拉 Anaconda 的 `defaults` 频道时要求先接受它的服务条款。**接受条款会产生法律约束**（Anaconda 对商业用途另有要求），所以这一步得由你自己决定要不要做，谁都不该替你按同意。

不想接受的话，改用社区频道 conda-forge 即可，功能上没有区别：

```bash
conda create -n touhou python=3.13 -c conda-forge --override-channels
```

注意 `--override-channels` 不能省——它的作用正是**不**去碰 `defaults`。以后在这个环境里装 conda 包时同样带上 `-c conda-forge --override-channels`；而 `pip install` 走 PyPI，不受影响。

游戏的操作方式沿用原作：

| 按键 | 功能 |
|------|------|
| 方向键 | 移动 |
| Z | 射击 / 菜单确认 |
| X | 释放炸弹 |
| Shift | 低速移动（会显示判定点） |
| Esc | 暂停 / 返回 |

## 项目结构

```
TouhouProject/
├── assets/                      # 素材与关卡数据
│   ├── fonts/                   #   字体（DFPPOPCorn，东方同人圈标准字体）
│   ├── levels/                  #   关卡数据（见下方说明）
│   ├── music/                   #   BGM 与 26 个音效
│   └── sprites/                 #   贴图
├── run.py                       # 启动脚本：免安装、免配置（见「运行」）
├── src/
│   └── touhou/                  # Python 包本体
│       ├── main.py              #   程序入口
│       ├── core/                #   通用 STG 内核（与东方无关）
│       ├── game/                #   东方玩法层
│       ├── ui/                  #   界面：HUD、菜单、结算
│       └── audio/               #   BGM 与音效播放
├── tests/                       # 测试
├── tools/                       # 一次性开发工具（关卡格式迁移、从素材图里抠弹）
├── dist/                        # 打包脚本与产物
├── docs/                        # 设计文档
├── pyproject.toml               # 包元数据与工具配置
└── README.md
```

### 为什么 `core/` 和 `game/` 要分成两层

这是整个项目最重要的结构决定。

`core/` 里放的是"任何一款弹幕射击游戏都会需要"的东西：二维向量、圆形碰撞检测、精灵动画表、固定步长的主循环、资源缓存。它**不 import 任何和东方有关的概念**——在 `core/` 的代码里你找不到"自机""残机""符卡"这些词。

`game/` 才知道自己在做东方：这里有玩家、敌机、BOSS、子弹、道具、擦弹判定、炸弹系统，以及读关卡文件、跑 BOSS 脚本的逻辑。

分成两层有两个实际好处。第一，`core/` 的数学和碰撞可以完全不启动 pygame 窗口就被测试——`tests/` 能快速跑起来，靠的就是这条边界。第二，当你需要改弹幕的运动学算法时，你知道该改哪里，而且不会一不小心碰坏 HUD 的代码。参考项目 `pygame-touhou` 把这两层揉在了一起，结果 `GameScene.py` 一个文件装下了所有东西，超过十一KB。

### 关卡数据

`assets/levels/level_1.json` 是一份声明式的关卡描述：敌人从哪个坐标出场、沿着什么轨迹飞、有多少血、什么时候开火、打死了掉什么道具。

```json
{
  "atFrame": 420.0,
  "startPosition": [64.0, 16.0],
  "trajectory": [[64.0, 48.0], [64.0, 48.0], [64.0, 48.0], [0.0, 112.0]],
  "durationFrames": 240.0,
  "hp": 10,
  "attacks": [
    { "pattern": "long_random", "startFrame": 60.0,
      "params": { "bulletCount": 3, "burstCount": 30, "speed": 2.5,
                  "intervalFrames": 3.6, "randomCenter": true, "bullet": { ... } } }
  ],
  "drop": { "list": ["points", "power_small", "nothing"], "probabilities": [40, 30, 30] }
}
```

这个格式对付成批刷的杂鱼很好用，改数值不用碰代码，调关卡很快。但它**不适合写 BOSS 符卡**——符卡需要阶段切换、多个发射器协同、血量分段、宣言动画，硬塞进 JSON 会变成嵌套地狱。

所以我们的做法是**杂鱼走数据，BOSS 走代码**：道中波次继续用 JSON 描述，BOSS 的符卡用 Python 写。两者最终都会归到同一套弹幕模板接口上，引擎里不区分"来自 JSON 的弹幕"和"来自代码的弹幕"。

上面的 JSON 是**我们自己的格式**，由 `tools/migrateLevel.py` 从参考项目的旧格式（攻击参数是位置数组、时间单位混用）一次性转换而来，旧内容留在 git 历史里。字段说明与迁移时要处理的坑都在 `docs/DESIGN.md`「关卡数据格式」，加载时带校验、报错会指出出错的位置。

## 代码约定

### 命名

类名用大驼峰 `PascalCase`，函数、方法、变量用小驼峰 `lowerCamelCase`，模块级常量用全大写下划线 `UPPER_SNAKE_CASE`。文件名与其中的类名保持一致。

```python
class SpriteSheet:
    def __init__(self, surface, frameWidth):
        self.frameWidth = frameWidth
        self.rotatedCache: dict[int, list] = {}

    def getRotated(self, angleDeg: int): ...


FPS = 60
```

这套风格和 PEP 8 的默认建议不完全一致（PEP 8 规定函数名用 `snake_case`），所以我们关掉了 ruff 中对应的检查项 `N802` / `N803` / `N815` / `N999`。类型标注和变量名仍然按标准来写。

### 写给人看的代码

代码和文档是写给**人**读的，不是写给机器读的。

这意味着几件具体的事。注释要解释**为什么**这么写，而不是复述代码在做什么——`# 把 x 加一` 这种注释不如没有。函数名和变量名要能自解释，宁可长一点也别用 `d`、`tmp`、`data2` 这种名字。一个函数如果长到需要滚动才能看完，通常说明它该拆了。

这一条不是审美偏好。弹幕游戏的代码里有大量数学，半年后回来看时你唯一能依靠的就是命名和注释。

### 不重复造轮子

需要实现某个功能时，先去找现成的方案——GitHub 上有大量东方同人和弹幕射击相关的项目可以借鉴。但**借鉴不等于抄袭**：注意对方的开源协议，没有 LICENSE 的项目（比如 `Patchouli-CN/touhou-engine`）意味着"保留所有权利"，可以读它的设计思路，但不要复制代码。

本项目明确参考过的：
- **NumPix/pygame-touhou**（MIT）——素材来源；关卡数据格式；`Vector2` 和样条曲线轨迹的实现
- **Patchouli-CN/touhou-engine**（无 LICENSE，仅参考设计）——固定步长与确定性设计、弹幕数组化的性能思路

## 为什么不用 numpy

参考项目用 numpy 表示二维向量：`Vector2` 内部就是一个 `np.array([x, y])`。我们在自己的实现里改成了纯 Python 的两个浮点数。

原因是 numpy 对**小数组**的单次运算其实比纯 Python 慢。`np.array([x, y])` 每次都要构造一个数组对象，这个开销远大于它省下的那两次浮点加法。而弹幕引擎每帧要做几万次向量加法、归一化、旋转——在这种场景下，numpy 是纯粹的负收益。

numpy 真正有价值的场景是**批量数组运算**：一次对几千个数字做同样的操作。如果将来弹幕数量涨到需要向量化处理（比如把全部子弹的位置存成平行的数组，一次性更新），那时我们会重新引入它。但在那之前，纯 Python 更简单也更快。

## 当前进度

引擎底座已经搭好，`python run.py` 能开出窗口跑起来：640×480 逻辑分辨率、整数倍缩放的窗口、固定步长主循环、输入抽象、自机移动（含低速模式与游戏区边界钳制）、立绘动画与左右倾斜、无缝下滚背景，以及覆盖这些行为的自动化测试（含无头集成测试）。

弹幕底座也已完成：子弹对象（带对象池与 `__slots__`）、按角度预旋转缓存的渲染分支、出屏回收、碰撞查询，以及成批推进与绘制它们的弹幕场。

敌机也已完成：沿**均匀三次 B 样条**轨迹飞行（`core/spline.py`）、贴图动画、血量与死亡。

**弹幕模板层也已完成**：三种弹型（`wide_cone` / `wide_ring` / `long_random`）走一张注册表，敌机按自己的轨迹时刻开火，随机数可播种——同一份输入产生同一场战斗。主程序里那段临时生成器已经删掉。

关卡数据也换了格式：`assets/levels/level_1.json` 现在是本项目自己的格式（由 `tools/migrateLevel.py` 从参考项目的旧格式一次性转换而来），攻击参数从「位置数组」变成具名参数，加载时带校验、报错会指出出错的位置。

**自机也能攻能守了**：射击（火力档位决定弹道数，子弹打中敌机会扣血、打死会消失）、炸弹（消耗一枚、清空全场敌弹、**全屏敌机掉一大截血**、给自己一段无敌，死亡后补足到 3 枚）、受击与残机（死亡炸弹窗口、复活无敌、立绘闪烁、**撞到敌机机体也是死**）、**死亡冲击波**（爆开一圈光环，同时清空全场敌弹、全屏敌机各掉一点血——刚好秒杀 1 血小怪），外加一个右侧的 HUD 显示残机 / 雷 / 火力。雷的伤害（38）是按关卡的血量档位定的：1/10/25 血的一发清光，40 血的顶级精英差一点。自机子弹复用 `Bullet` 与 `BulletField`，只是另开一个场；自机子弹打敌机走 `game/collision.py` 的 y 分桶粗筛；一次性动画（死亡特效与放雷特效——雷暂时复用死亡那份扩散环）走 `game/effectField.py`。

敌机身上有**两个判定半径**：被自机子弹打中的那个来自关卡数据、比贴图还大（保证打得到），撞机用的那个由贴图内切圆乘系数算出来、**比贴图略小**（保证「没真碰到就不算死」）。

**BOSS 也落地了（中 BOSS 小恶魔）**：行为用**生成器协程**写（规格 §6.7 定的写法），关卡数据只管「何时出 BOSS」与「打什么弹」、脚本管「怎么打」；立绘用真实贴图（`assets/sprites/entities/boss.png`），关卡数据里没给 `sprite` 时才回退到程序化占位图形（带光晕的五边形 + 旋转）；屏幕顶部有血条与名字。BOSS 与敌机在引擎眼里是同一种东西，所以 `Boss` 继承 `Enemy` —— 碰撞、撞机、清屏、y 分桶全部复用，`collision.py` 一行没改。

小恶魔的弹幕里也用上了从素材图抠出来的**大玉**（判定 35px、不跟速度旋转）。

boss 战目前**只有中 BOSS**：一管血、无符卡。符卡宣言、分段血条、残机对应的结算与关底 BOSS 都还没做。

所以 `python run.py` 现在是一关真的能打的弹幕：114 架敌机依次进场、按各自的时刻表打出扇形与螺旋，你可以按住 Z 打回去、按 X 放雷、被打中后有 8 帧死亡炸弹的机会。残机是**剩余备命**（0 时还有最后一条命）；起始残机暂定 8 条，是给不会玩的人试弹幕用的，等难度选项落地时会变成难度表里的一项。**还没有的**是道具、擦弹、BOSS 符卡、结算画面与音频。

设计决定与取舍的权威记录是 `docs/DESIGN.md`（与代码同步维护，代码注释里「见设计文档」指的都是它）；分阶段的计划文档在 `docs/superpowers/` 下，是有意不进版本控制的本地工作文件。
