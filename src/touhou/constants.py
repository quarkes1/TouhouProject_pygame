"""全局常量。

速度单位统一为「像素/帧」。参考项目 NumPix/pygame-touhou 用的是「像素/秒」
（因为它跑变步长），本项目固定 60fps，因此按下式换算：

    pxPerFrame = pxPerSecond / 60

数值来源与取舍见 docs/DESIGN.md「数值常量与单位」。这些是起点值，需要实测调整。
"""

import math

# —— 分辨率与布局 ——
LOGICAL_WIDTH = 640
LOGICAL_HEIGHT = 480
PLAYFIELD_X = 32
PLAYFIELD_Y = 16
PLAYFIELD_WIDTH = 384
PLAYFIELD_HEIGHT = 448

# 参考项目的游戏区尺寸（它的 GAME_ZONE = 50, 50, 600, 700）。关卡数据的坐标以
# **它**的左上角为原点，而我们的游戏区是它的 0.64 倍（384/600 == 448/700）。
# 所以把关卡数据换算到我们的坐标系只需要缩放、不需要平移——依据见
# docs/DESIGN.md「关卡数据与坐标系」（镜像出生点的对称轴恰好落在它的中心线上）。
REFERENCE_PLAYFIELD_WIDTH = 600
REFERENCE_PLAYFIELD_HEIGHT = 700

# —— 主循环 ——
FPS = 60
STEP_SECONDS = 1.0 / FPS
MAX_STEPS_PER_FRAME = 5

# —— 自机 ——
PLAYER_HITBOX_RADIUS = 2  # 判定点，参考项目未实现
PLAYER_GRAZE_RADIUS = 18  # 擦弹圈，远大于判定点
PLAYER_SPEED_NORMAL = 370 / 60  # ≈ 6.17 px/帧
PLAYER_SPEED_SLOW = 370 / 120  # ≈ 3.08 px/帧，低速模式
PLAYER_SHOT_RADIUS = 5  # 自机子弹判定半径
PLAYER_SHOT_SPEED = 900 / 60  # 15 px/帧；规格 §6.1 给的原值是 900 像素/秒
PLAYER_SHOT_DAMAGE = 1  # 敌人血量（1/10/25/40）正是按伤害 1 调的
SHOOT_INTERVAL_FRAMES = 6
RESPAWN_INVINCIBILITY_FRAMES = 180
DEATHBOMB_WINDOW_FRAMES = 8  # 原作约 8 帧
BOMB_INVINCIBILITY_FRAMES = 180
# 复活时从游戏区下方升到出生点要多少帧。规格只说「从游戏区底部升起」，没给数字。
RESPAWN_RISE_FRAMES = 60
# 相邻弹道的夹角。规格说「查表得到弹道数后均分角度发射」，但**没给夹角**。
# 起点值，需要实测调整：太小则几条弹道糊成一条，太大则像霰弹枪不像魔理沙的集中火力。
PLAYER_SHOT_ANGLE_STEP_DEG = 6.0

# —— 敌机 ——
# 撞机判定半径 = 贴图内切圆半径 × 这个系数。**比贴图略小**，于是贴图最外圈
# 那几像素碰到不算死——「看起来没碰到却死了」是最招人骂的一类判定。
#
# 与关卡数据里那份 `hitboxRadius` 是两回事：那份**比贴图还大**（妖精半宽 12、
# 数据给 15），是给自机子弹打的。两个判定方向相反，理由见 enemy.py 的模块文档。
#
# 实测：弹刺球贴图 32×32、可见半径约 16.4px，所以撞机半径是 16 × 0.8 = 12.8；
# 妖精贴图 24×19（帧不是正方形，取内切圆）→ 9.5 × 0.8 = 7.6。
# 起点值，需要实测调整。
ENEMY_BODY_RADIUS_FACTOR = 0.8

# —— 死亡冲击波 ——
# 自机死亡时对**全屏敌机**的伤害。取 1 是因为关卡里的血量分布是 1/10/25/40，
# 而 114 架里有 98 架正好是 1 血——这个值刚好秒杀小怪，对精英只是掉一层皮，
# 符合「微小但能清场」的定位。要调手感就调这里。
PLAYER_DEATH_DAMAGE = 1

# —— 炸弹 ——
# 放雷时对**全屏敌机**的伤害。
#
# 关卡里的血量分布是 1/10/25/40，所以 38 的含义是：**一口气清掉所有小怪与
# 普通精英，只有 40 血的顶级精英能剩一口气**（留 2 血，再补两发自机子弹）。
# 这是「伤害高一些，但差一点打死满血精英怪」那个定位的落点。
#
# 比 `PLAYER_DEATH_DAMAGE` 高两个数量级是**刻意**的：死亡冲击波是白送的，
# 只够清小怪；雷是消耗品，原作里它就是打 BOSS 的主要手段之一。
# 起点值，需要实测调整。
PLAYER_BOMB_DAMAGE = 38
# 雷的动画放多少帧。**现在与死亡特效同一份素材、同一个时长**（见 main.py 的
# 调用点），所以这个数暂时与 `DEATH_EFFECT_FRAMES` 相等；等雷自己的美术到位时
# 它会先分家。起点值，需要实测调整。
BOMB_EFFECT_FRAMES = 30

# 冲击波动画：烘 BAKED 张、放 FRAMES 帧（每张播 FRAMES / BAKED 帧）。
# 30 帧是半秒，与死亡后「定住 → 从下方升起」的节奏对得上。
DEATH_EFFECT_FRAMES = 30
DEATH_EFFECT_BAKED_FRAMES = 10
# 环形贴图的缩放范围。贴图是 500×500，1.0 就已经盖住整个游戏区（384×448）；
# 取到 1.4 是为了让**环的边缘**也从画面外扫过去——环本身中空，可见的亮环
# 半径只有贴图边长的一半不到，1.0 时它才铺到游戏区的一半多一点。
DEATH_RING_START_SCALE = 0.25
DEATH_RING_END_SCALE = 1.40
# 由亮到暗。不淡出的话，动画放完那一帧会「啪」地整圈消失。
DEATH_RING_START_ALPHA = 255
DEATH_RING_END_ALPHA = 60

# —— 资源 ——
# 剩余**备命**数。残机 0 时玩家还在场上打（那是最后一条命），再死才出局，
# 所以 8 一共能死 9 次——HUD 上那个数字数的是「还能死几次不死」。
#
# 8 是**刻意偏高**的：本轮还没有难度选择，8 条命是给不会玩的人试弹幕用的
# （原作默认 3 条，靠选项里的「残机数」自己调）。等难度选项落地时，这里
# 应当变成难度表里的一项，而不是继续写死。
START_LIVES = 8
# 初始雷数，同时也是**死亡补雷的上限**（复活时不足这个数就补足，多了不动）。
START_BOMBS = 3
POWER_MAX = 4.00
POWER_START = 2.40  # 沿用参考项目起始值
POWER_ITEM_LARGE = 0.02  # 沿用参考项目
POWER_ITEM_SMALL = 0.005  # 沿用参考项目
POC_LINE_OFFSET_Y = 112  # PoC 回收线距游戏区顶部
SCORE_EXTEND_STEP = 10_000_000

# —— 道具 ——
ITEM_RADIUS_LARGE = 12  # 能量(大)/满火力/1UP
ITEM_RADIUS_SMALL = 10  # 能量(小)/蓝点/星星
ITEM_FALL_GRAVITY = 10 / 60  # 下落加速度
ITEM_HOMING_DELAY_FRAMES = 90  # 追尾启动延迟
ITEM_HOMING_SPEED = 500 / 60  # ≈ 8.33 px/帧
POINT_ITEM_BASE_SCORE = 30_000
POINT_ITEM_HEIGHT_BONUS = 70_000

# —— 子弹 ——
# 出屏余量：子弹要飞出游戏区这么远才回收，保证贴图完整离场而不是在边缘被削掉。
# 取值依据是「最大贴图的旋转外接矩形半宽」——现有最大的 32×32 转到 45° 约 45×45，
# 半宽约 23，取 32 留余量。将来若出现明显更大的弹（比如 96px 的 BOSS 弹），
# 这个值必须跟着放大，否则那颗弹会在贴边时静默消失。
# 注意它只负责贴图占位：出屏判定本身必须带速度方向（见 bulletField.isCulled），
# 因为关卡里的敌人会在游戏区外开火，子弹诞生在很远的地方却朝场内飞。
BULLET_CULL_MARGIN = 32

# 判定半径的默认值，需要实测调整。关卡数据里其实是带这个值的——sprite 描述的
# 第 4 个字段就是判定半径，格式为 [路径, 帧宽, 帧高, 判定半径, 偏移]。
# 注意它与贴图尺寸无关：level_1.json 里同一张 ellipse_bullet_0.png（24×24）
# 在不同弹幕下分别用 4 和 6，说明判定半径是**每套弹幕各自的参数**，
# 不是贴图的固有属性。下面两个数给代码里直接构造的弹幕当默认值；
# 关卡加载器应当优先取数据里的那一份。
BULLET_RADIUS_SMALL = 4.0
BULLET_RADIUS_LARGE = 6.0

# 「随机中心」弹幕（wide_ring / long_random 打开该开关时）的发射点相对敌人位置的
# 最大偏移。参考项目写的是 `Vector2.one().rotate(随机角) * 25`——`Vector2.one()`
# 的模长是 √2，所以半径是 25√2 ≈ 35.36px。
#
# **不缩放**：缩放规则见 docs/DESIGN.md「关卡数据与坐标系」——
# 只有关卡几何（敌人路径坐标）缩放，精灵、速度、判定半径与这个偏移都是
# 「角色尺度」的量，保持原值才能让它们的相对关系与原作一致。
BULLET_RANDOM_CENTER_OFFSET = 25 * math.sqrt(2)
