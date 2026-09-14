# TouhouProject

用 Python 和 pygame 做的东方 Project 同人弹幕游戏。目标是复刻东方系列的基本关卡玩法：道中杂鱼波、中 BOSS、BOSS 符卡、道具回收、残机与炸弹，一整套从开局到结算的完整流程。

需要说清楚的是，这个项目**不是**东方原作的移植或逆向工程。我们不去解包原作的 `th06.dat`，也不打算逐帧还原原版逻辑。它是一份原创代码，借用原作的美术与音效素材，重新实现一套手感接近的弹幕玩法。如果你要找的是"能跑原版数据"的实现，那么 `Patchouli-CN/touhou-engine` 才是你要的东西。

## 素材来源与致谢

`assets/` 目录下的全部素材——立绘、子弹贴图、背景、BGM、音效、字体，以及 `assets/levels/level_1.json` 这份关卡数据——都来自 [NumPix/pygame-touhou](https://github.com/NumPix/pygame-touhou)，作者 Leonid Ushakov，以 MIT 协议发布。

这意味着我们在法律上可以复用它的代码和素材，但**必须保留版权声明**。如果你从它的代码里抄了某个函数，请在那个函数的注释里写明出处，并把原作者的名字保留在 `LICENSE` 和这里。

东方 Project 原作的一切版权归上海爱丽丝幻乐团（ZUN）所有。这是一个非商业的同人作品。

## 环境要求

需要 **Python 3.13 或更高版本**。

项目跑在一个专用的 conda 环境里，这样和机器上其他 Python 安装互不干扰：

```bash
conda create -n touhou python=3.13
conda activate touhou
pip install -e ".[dev]"
```

（若 `conda activate` 报 `Run 'conda init' before 'conda activate'`，先跑一次 `conda init cmd.exe` 并重开终端。环境已经建好的话，直接用绝对路径 `D:\Anaconda3\envs\touhou\python.exe` 也能做同样的事。）

之所以不直接用 Anaconda 的 base 环境：那里面通常已经有上千个由 conda 管理的包，往里面混装 pip 包是 conda 环境损坏的常见原因。独立环境更干净。

**调用解释器时请写清楚是哪一个。** 一台机器上往往装着好几个 Python，PATH 的先后决定了 `python` 这个名字最终指向谁——很容易落到某个没装依赖的解释器上，然后收到一个莫名其妙的 `ModuleNotFoundError`。要么先 `conda activate touhou`，要么直接写解释器的绝对路径。

关于 **pygame-ce**：它是官方 `pygame` 的社区分支，API 完全兼容——你在代码里照样写 `import pygame`。我们选它是因为它维护更活跃、发布节奏更快、而且是官方的超集。需要说明的是这**不是硬性要求**：官方 `pygame` 在 Python 3.13 上同样有现成的安装包，想换回去把依赖名改掉即可。

```bash
pip install pygame-ce
```

除此之外只依赖标准库。**我们没有引入 numpy**，原因见下面「为什么不用 numpy」一节。

## 快速开始

**最省事的跑法：直接写解释器的绝对路径，不需要任何额外设置。**

```bat
D:\Anaconda3\envs\touhou\python.exe -m touhou
```

想用短一点的命令，可以先把环境激活（见下方「两个常见报错」）：

```bat
conda activate touhou
python -m touhou
```

其余命令一律用同一个解释器：

```bat
D:\Anaconda3\envs\touhou\python.exe -m pytest          :: 跑测试
D:\Anaconda3\envs\touhou\python.exe dist\build.py      :: 打包成 exe（调用 pyinstaller）
```

### 两个常见报错

**`CondaError: Run 'conda init' before 'conda activate'`**
conda 还没对当前终端做过初始化。跑一次 `conda init cmd.exe`（或把 `cmd.exe` 换成你用的 shell），**然后重开终端**。不想动配置就一直用上面的绝对路径，效果一样。

**`No module named touhou`**
说明 `python` 这个名字指向了别的解释器。这台机器上装了多个 Python，PATH 的先后决定了 `python` 指向谁——实际会落到 MSYS2 工具链自带的那个，它里面没有本项目的依赖。这就是为什么上面所有命令都写成绝对路径。

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
├── src/
│   └── touhou/                  # Python 包本体
│       ├── main.py              #   程序入口
│       ├── core/                #   通用 STG 内核（与东方无关）
│       ├── game/                #   东方玩法层
│       ├── ui/                  #   界面：HUD、菜单、结算
│       └── audio/               #   BGM 与音效播放
├── tests/                       # 测试
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

`assets/levels/level_1.json` 是一份声明式的关卡描述，来自参考项目。它把道中杂鱼波次写成了数据：敌人从哪个坐标出场、沿着什么轨迹飞、有多少血、什么时候开火、打死了掉什么道具。

```json
{
  "start_position": [50, 0],
  "trajectory": [[50, 50], [50, 50], [50, 50], [-50, 150]],
  "speed": 1,
  "hp": 10,
  "attacks": [["long_random", 3, 30, [...], 150, 1, 0.06, 0, true]],
  "drop": { "list": ["points", "power_small", "nothing"], "probabilities": [40, 30, 30] }
}
```

这个格式对付成批刷的杂鱼很好用，改数值不用碰代码，调关卡很快。但它**不适合写 BOSS 符卡**——符卡需要阶段切换、多个发射器协同、血量分段、宣言动画，硬塞进 JSON 会变成嵌套地狱。

所以我们的做法是**杂鱼走数据，BOSS 走代码**：道中波次继续用 JSON 描述，BOSS 的符卡用 Python 写。两者最终都会归到同一套弹幕模板接口上，引擎里不区分"来自 JSON 的弹幕"和"来自代码的弹幕"。

关于关卡格式的完整字段说明，见 `docs/` 下的设计文档。

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

这套风格和 PEP 8 的默认建议不完全一致（PEP 8 规定函数名用 `snake_case`），所以我们关掉了 ruff 中对应的检查项 `N802` / `N803` / `N815`。类型标注和变量名仍然按标准来写。

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

引擎底座已经搭好，`python -m touhou` 能开出窗口跑起来：640×480 逻辑分辨率、整数倍缩放的窗口、固定步长主循环、输入抽象、自机移动（含低速模式与游戏区边界钳制）、立绘动画与左右倾斜、无缝下滚背景，以及覆盖这些行为的自动化测试（含无头集成测试）。

游戏玩法本身尚未开始：射击、敌机、子弹与符卡在下一个计划（Plan B）中实现。

设计决定与取舍的权威记录是 `docs/DESIGN.md`（与代码同步维护，代码注释里「见设计文档」指的都是它）；分阶段的计划文档在 `docs/superpowers/` 下，是有意不进版本控制的本地工作文件。
