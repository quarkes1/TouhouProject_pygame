"""全局常量。

速度单位统一为「像素/帧」。参考项目 NumPix/pygame-touhou 用的是「像素/秒」
（因为它跑变步长），本项目固定 60fps，因此按下式换算：

    pxPerFrame = pxPerSecond / 60

数值来源与取舍见 docs/superpowers/specs/2026-09-14-touhou-pygame-replica-design.md
§6.1。这些是起点值，需要实测调整。
"""

# —— 分辨率与布局 ——
LOGICAL_WIDTH = 640
LOGICAL_HEIGHT = 480
PLAYFIELD_X = 32
PLAYFIELD_Y = 16
PLAYFIELD_WIDTH = 384
PLAYFIELD_HEIGHT = 448

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
SHOOT_INTERVAL_FRAMES = 6
RESPAWN_INVINCIBILITY_FRAMES = 180
DEATHBOMB_WINDOW_FRAMES = 8  # 原作约 8 帧

# —— 资源 ——
START_LIVES = 3
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
